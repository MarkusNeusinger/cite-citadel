"""Headless-browser smoke test for the offline viewer's JavaScript (~2k lines of app.js).

The 2026-07 audit flagged the viewer JS as one of the two riskiest untested surfaces: every
other viewer test asserts on the built HTML string, so a syntax error or boot crash in app.js
would ship invisibly. This file loads the real built document in headless Chromium and drives
the core interactions — boot, sidebar, search, page open, citation popover, keyboard focus —
asserting zero page errors throughout.

Opt-in by design (the offline suite stays browser-free): it self-skips unless the `browser`
dependency group is installed (`uv sync --group browser && uv run playwright install chromium`).
CI runs it in the dedicated `viewer-smoke` job. `CITADEL_TEST_BROWSER` overrides the chromium
executable for environments with a pre-provisioned browser build.
"""

from __future__ import annotations

import os

import pytest

from citadel import viewer


pytest.importorskip("playwright.sync_api", reason="optional browser group not installed")

from playwright.sync_api import sync_playwright  # noqa: E402


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        exe = os.environ.get("CITADEL_TEST_BROWSER")
        try:
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
        except Exception as e:  # noqa: BLE001 - no usable chromium is a skip, not a failure
            pytest.skip(f"no usable chromium: {e}")
        yield b
        b.close()


@pytest.fixture
def viewer_page(browser, tmp_citadel, seed_page):
    """A freshly built two-page + one-source viewer, loaded in a new browser page. Yields the
    playwright page; asserts on teardown that NO page error (uncaught JS exception) fired."""
    (tmp_citadel.raw / "a.md").write_text(
        "# Coffee Overview\n\nEspresso is brewed under nine bars of pressure.\n", encoding="utf-8"
    )
    seed_page(
        "concepts/espresso.md",
        {
            "type": "Concept",
            "title": "Espresso",
            "description": "A brew method.",
            "tags": ["brewing", "coffee"],
            "resource": "raw/a.md",
        },
        "Espresso uses nine bars of pressure.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - lines 3-3 (ingested 2026-06-22)\n",
    )
    seed_page(
        "concepts/caffeine.md",
        {
            "type": "Concept",
            "title": "Caffeine",
            "description": "The stimulant.",
            "tags": ["coffee"],
            "resource": "raw/a.md",
        },
        "See [Espresso](./espresso.md) for the shot.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - n (ingested 2026-06-22)\n",
    )
    out = viewer.write_viewer()

    errors: list[str] = []
    page = browser.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(out.as_uri())
    page.wait_for_selector("#page-list a.navitem")  # app.js booted and rendered the sidebar
    yield page
    page.close()
    assert errors == [], f"viewer JS reported errors: {errors}"


def test_boot_renders_sidebar_and_graph(viewer_page):
    titles = viewer_page.locator("#page-list a.navitem").all_inner_texts()
    assert any("Espresso" in t for t in titles)
    assert any("Caffeine" in t for t in titles)
    # The map SVG holds one node group per page (source nodes are a toggle, pages always show).
    # The graph draws inside a requestAnimationFrame settle loop, so the sidebar being rendered
    # does not imply the nodes exist yet — wait for them instead of counting immediately.
    viewer_page.wait_for_selector("#graph g.node")
    assert viewer_page.locator("#graph g.node").count() >= 2


def test_open_page_renders_reader_and_citation_popover(viewer_page):
    viewer_page.click("#page-list a.navitem[data-page='concepts/espresso.md']")
    reader = viewer_page.locator("#reader")
    reader.wait_for()
    assert "Espresso uses nine bars of pressure" in reader.inner_text()
    assert "#" in viewer_page.url  # hash routing carries the open page

    # Hovering the inline [^s1] marker must raise the source popover with the cited line.
    viewer_page.hover("#reader sup.fnref a[data-pop]")
    pop = viewer_page.locator("#srcpop")
    pop.wait_for(state="visible")
    assert "nine bars of pressure" in pop.inner_text()


def test_search_filters_and_recovers(viewer_page):
    search = viewer_page.locator("#search")
    search.fill("pressure")
    viewer_page.wait_for_selector("#page-list a.result")
    results = viewer_page.locator("#page-list a.result[data-page]").all_inner_texts()
    assert any("Espresso" in t for t in results)
    assert not any("Caffeine" in t for t in results)  # AND-matched: caffeine page lacks the term

    search.fill("zz-no-such-term-zz")
    viewer_page.wait_for_selector("#page-list p.ext")
    assert "No matches" in viewer_page.locator("#page-list").inner_text()

    search.fill("")
    viewer_page.wait_for_selector("#page-list a.navitem")  # full nav returns after clearing


def test_slash_focuses_search(viewer_page):
    viewer_page.keyboard.press("/")
    assert viewer_page.evaluate("document.activeElement && document.activeElement.id") == "search"


def test_sources_sidebar_tree_and_overview_table(viewer_page):
    """The Sources axis renders as a folder tree (folders as <details>, leaves = FILENAMES) and
    links an "#sources" overview: one table row per source with filename, folder, provenance, and
    citation count. The fixture's one source (raw/a.md, cited by both pages) yields a single
    'raw' folder holding one 'a.md' leaf."""
    viewer_page.click("#source-list details.src-axis summary")
    folder = viewer_page.locator("#source-list details.src-dir > summary")
    assert folder.count() == 1
    assert "raw" in (folder.first.inner_text() or "").lower()  # CSS may uppercase summaries
    viewer_page.click("#source-list details.src-dir > summary")
    leaf = viewer_page.locator("#source-list a.navitem.src")
    assert leaf.count() == 1
    assert "a.md" in (leaf.first.inner_text() or "")  # the filename, not the embedded title

    viewer_page.click("#source-list a.src-overview")
    reader = viewer_page.locator("#reader")
    reader.wait_for()
    viewer_page.wait_for_selector("#reader table.src-table")
    rows = viewer_page.locator("#reader table.src-table tbody tr")
    assert rows.count() == 1
    row_text = rows.first.inner_text()
    assert "a.md" in row_text
    assert "2" in row_text  # cited by both fixture pages
    # Clicking the file cell opens the embedded source itself.
    viewer_page.click("#reader table.src-table a[data-source]")
    reader.wait_for()
    assert "nine bars of pressure" in reader.inner_text()


def test_spacey_angle_citation_renders_as_live_source_link(browser, tmp_citadel, seed_page):
    """A citation into a path containing SPACES must be written in the angle form
    (``[t](<../../raw/my report.md>)`` — grammar.split_link_target's decided rule), and the viewer
    must render it like any other citation: a live source link, a source-aware inline marker, and a
    Sources group under the file — never the "unresolved citations" fallback bucket the angle form
    used to land in because the JS link regexes only accepted whitespace-free targets."""
    (tmp_citadel.raw / "my report.md").write_text("# My Report\n\nThe measured value was 42.\n", encoding="utf-8")
    seed_page(
        "concepts/widget.md",
        {
            "type": "Concept",
            "title": "Widget",
            "description": "A thing.",
            "tags": ["x"],
            "resource": "raw/my report.md",
        },
        "The value is 42.[^s1]\n\n## Sources\n\n"
        "[^s1]: [My Report](<../../raw/my report.md>), lines 3-3 (ingested 2026-06-22)\n",
    )
    out = viewer.write_viewer()

    errors: list[str] = []
    page = browser.new_page()
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.goto(out.as_uri())
    page.wait_for_selector("#page-list a.navitem")
    page.click("#page-list a.navitem[data-page='concepts/widget.md']")
    page.wait_for_selector("#reader details.sources")

    # The compacted Sources block groups the citation under a LIVE source link.
    assert page.locator("#reader details.sources a.srclink").count() == 1
    # text_content reads the collapsed <details> too: no unresolved bucket, no literal markdown.
    sources_text = page.locator("#reader details.sources").text_content() or ""
    assert "unresolved citations" not in sources_text
    assert "](<" not in sources_text
    # The inline [^s1] marker resolved its source (the fnSrc map parsed the angle-form def).
    assert page.locator("#reader sup.fnref.has-src").count() == 1
    # Clicking the source link opens the embedded source content.
    page.click("#reader details.sources summary")
    page.click("#reader details.sources a.srclink")
    reader = page.locator("#reader")
    reader.wait_for()
    assert "measured value was 42" in reader.inner_text()

    page.close()
    assert errors == [], f"viewer JS reported errors: {errors}"
