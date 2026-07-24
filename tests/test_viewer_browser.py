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
