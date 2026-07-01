"""Offline tests for the self-contained HTML viewer.

No browser, no network: every test only calls build_bundle/build_html/write_viewer/view and
asserts on strings (webbrowser.open is monkeypatched). Filesystem state is redirected to
tmp_path by the shared ``tmp_citadel`` fixture (see conftest.py).
"""

from __future__ import annotations

import json
import re

from citadel import manifest, store, viewer


def _two_page_wiki(seed_page) -> None:
    seed_page(
        "concepts/espresso.md",
        {
            "type": "Concept",
            "title": "Espresso",
            "description": "A brew method.",
            "tags": ["brewing", "coffee"],
            "resource": "raw/a.md",
        },
        "Espresso uses pressure.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n (ingested 2026-06-22)\n",
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


def _embedded_bundle(html: str) -> tuple[str, dict]:
    """Pull the embedded JSON bundle out of a built viewer document: returns ``(blob, bundle)``
    where ``blob`` is the raw (still ``<\\/``-escaped) script payload and ``bundle`` is the dict
    parsed after the documented unescape."""
    m = re.search(r'<script id="bundle" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert m, "embedded bundle script not found"
    blob = m.group(1)
    return blob, json.loads(blob.replace("<\\/", "</"))


def test_bundle_embeds_cited_sources(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text(
        "# Coffee Overview\n\nCoffee is a brewed drink made from roasted beans.\n", encoding="utf-8"
    )
    _two_page_wiki(seed_page)
    sources = viewer.build_bundle()["sources"]

    assert "raw/a.md" in sources
    s = sources["raw/a.md"]
    assert s["missing"] is False
    assert s["title"] == "Coffee Overview"
    assert "brewed drink" in s["body"]
    assert "brewed drink" in s["snippet"]
    # Both pages cite raw/a.md (resource frontmatter + a ## Sources footnote link).
    assert set(s["cited_by"]) == {"concepts/espresso.md", "concepts/caffeine.md"}


def test_binary_pdf_source_is_openable_not_unavailable(tmp_citadel, seed_page):
    # A real PDF is binary (not UTF-8). It must not be reported as missing — instead it carries an
    # "open the original file" href so the browser can show it natively.
    (tmp_citadel.raw / "a.pdf").write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n")
    seed_page(
        "concepts/x.md",
        {"type": "Concept", "title": "X"},
        "Body cites a pdf.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.pdf](../../raw/a.pdf) - n\n",
    )
    s = viewer.build_bundle()["sources"]["raw/a.pdf"]
    assert s["missing"] is False
    assert s["kind"] == "binary"
    assert s["body"] == ""
    assert s["href"] == "../raw/a.pdf"
    assert s["cited_by"] == ["concepts/x.md"]


def test_missing_source_is_flagged_not_fatal(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)  # cites raw/a.md, but the raw file is absent
    s = viewer.build_bundle()["sources"]["raw/a.md"]
    assert s["missing"] is True
    assert s["body"] == ""
    assert set(s["cited_by"]) == {"concepts/espresso.md", "concepts/caffeine.md"}


def test_build_html_makes_sources_clickable(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text("# A\n\nbody text\n", encoding="utf-8")
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    # The inlined viewer renders raw citations as clickable source links and can open them.
    assert "data-source" in html
    assert "srclink" in html
    assert "openSource" in html
    # Still fully offline with an embedded source present.
    for bad in ("http://", "https://", "cdn", " src=", "fetch("):
        assert bad not in html, f"network reference present: {bad!r}"


def test_sources_keyed_by_browser_identity_in_nested_layout(tmp_path, make_citadel, seed_page):
    # When wiki/ is NOT a direct child of the repo root (e.g. CITADEL_WIKI_DIR=sub/wiki), the citation
    # climbs further but the in-browser resolver clamps '..' at the wiki root. The embedded source
    # must be keyed under that SAME clamped id, else the citation can't find it.
    cit = make_citadel(wiki=tmp_path / "sub" / "wiki")
    (cit.raw / "x.md").write_text("# X source\n\ndetail\n", encoding="utf-8")
    # From repo/sub/wiki/concepts/p.md to repo/raw/x.md is '../../../raw/x.md'.
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites x.[^s1]\n\n## Sources\n\n[^s1]: [raw/x.md](../../../raw/x.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    # Keyed by the clamped identity the browser produces, not the WIKI_DIR.parent-relative '../raw/x.md'.
    assert "raw/x.md" in sources
    assert "../raw/x.md" not in sources
    assert sources["raw/x.md"]["cited_by"] == ["concepts/p.md"]


def test_sources_truncated_when_oversized(tmp_citadel, seed_page):
    big = "x" * (viewer._SOURCE_MAX_CHARS + 50)
    (tmp_citadel.raw / "a.md").write_text(big, encoding="utf-8")
    _two_page_wiki(seed_page)
    s = viewer.build_bundle()["sources"]["raw/a.md"]
    assert s["truncated"] is True
    assert len(s["body"]) == viewer._SOURCE_MAX_CHARS


def test_manifest_model_and_repo_and_uncited(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text("# A\n\ncited\n", encoding="utf-8")
    (tmp_citadel.raw / "lonely.md").write_text("# Lonely\n\nuncited\n", encoding="utf-8")
    tmp_citadel.manifest_path.write_text(
        json.dumps(
            {
                "raw/a.md": {"sha256": "h1", "model": "claude:sonnet"},
                "raw/lonely.md": {"sha256": "h2", "model": "copilot:gpt"},
                "raw/somerepo": {"kind": "git", "commit": "abc", "model": "claude:sonnet"},
            }
        ),
        encoding="utf-8",
    )
    _two_page_wiki(seed_page)
    sources = viewer.build_bundle()["sources"]
    # Model attribution flows from the manifest onto the cited source.
    assert sources["raw/a.md"]["model"] == "claude:sonnet"
    # A tracked-but-uncited file still appears, with an empty cited_by.
    assert "raw/lonely.md" in sources
    assert sources["raw/lonely.md"]["cited_by"] == []
    assert sources["raw/lonely.md"]["model"] == "copilot:gpt"
    # A git-repository entry is a folder, not a file — it is never embedded as a source.
    assert "raw/somerepo" not in sources
    assert all(s["key"] != "raw/somerepo" for s in sources.values())


def test_format2_manifest_provenance_decorates_sources(tmp_citadel, seed_page):
    """Regression: the bundle reads the manifest through ``manifest.load()``, which unwraps the
    stamped format-2 file (``{"meta", "sources"}``) that ``manifest.save`` writes. The old
    private viewer reader returned that RAW dict, so on a format-2 manifest the model
    attribution silently vanished and the tracked-but-uncited source never surfaced."""
    (tmp_citadel.raw / "a.md").write_text("# A\n\ncited\n", encoding="utf-8")
    (tmp_citadel.raw / "lonely.md").write_text("# Lonely\n\nuncited\n", encoding="utf-8")
    manifest.save(
        {
            "raw/a.md": {"sha256": "h1", "model": "claude:sonnet"},
            "raw/lonely.md": {"sha256": "h2", "model": "copilot:gpt"},
        }
    )
    _two_page_wiki(seed_page)
    sources = viewer.build_bundle()["sources"]
    assert sources["raw/a.md"]["model"] == "claude:sonnet"  # provenance decoration from the wrapped file
    assert "raw/lonely.md" in sources  # tracked-but-uncited still surfaces
    assert sources["raw/lonely.md"]["model"] == "copilot:gpt"
    # The envelope keys themselves must never leak in as phantom sources.
    assert all(s["key"] not in ("meta", "sources") for s in sources.values())


def test_citation_inside_code_fence_is_not_a_source(tmp_citadel, seed_page):
    (tmp_citadel.raw / "real.md").write_text("# Real\n\nx\n", encoding="utf-8")
    (tmp_citadel.raw / "fenced.md").write_text("# Fenced\n\ny\n", encoding="utf-8")
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Real cite.[^s1]\n\n```\n[raw/fenced.md](../../raw/fenced.md)\n```\n\n"
        "## Sources\n\n[^s1]: [raw/real.md](../../raw/real.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "raw/real.md" in sources
    assert "raw/fenced.md" not in sources  # the fenced citation is a literal, not provenance


def test_angle_bracket_citation_is_discovered(tmp_citadel, seed_page):
    # A citation written in markdown's <...> target form must still be discovered and embedded
    # (store._split_link_target strips the brackets); the in-browser resolveLink strips them too.
    (tmp_citadel.raw / "x.md").write_text("# X\n\nbody\n", encoding="utf-8")
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites x.[^s1]\n\n## Sources\n\n[^s1]: [raw/x.md](<../../raw/x.md>) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "raw/x.md" in sources
    assert sources["raw/x.md"]["cited_by"] == ["concepts/p.md"]


def test_docs_citation_is_a_source(tmp_citadel, seed_page):
    (tmp_citadel.docs / "ref.md").write_text("# Reference\n\nspec\n", encoding="utf-8")
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites a doc.[^s1]\n\n## Sources\n\n[^s1]: [docs/ref.md](../../docs/ref.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "docs/ref.md" in sources
    assert sources["docs/ref.md"]["title"] == "Reference"


def test_bundle_contains_pages_links_tags(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    b = viewer.build_bundle()

    by_path = {p["rel_path"]: p for p in b["pages"]}
    assert set(by_path) == {"concepts/espresso.md", "concepts/caffeine.md"}
    assert by_path["concepts/espresso.md"]["title"] == "Espresso"
    assert by_path["concepts/espresso.md"]["tags"] == ["brewing", "coffee"]
    # caffeine -> espresso edge; espresso has caffeine as a backlink.
    assert by_path["concepts/caffeine.md"]["outbound"] == ["concepts/espresso.md"]
    assert by_path["concepts/espresso.md"]["inbound"] == ["concepts/caffeine.md"]
    assert {"source": "concepts/caffeine.md", "target": "concepts/espresso.md"} in b["edges"]
    # tags / types match the store helpers.
    assert set(b["tags"]["coffee"]) == {"concepts/espresso.md", "concepts/caffeine.md"}
    assert b["types"]["Concept"] == ["concepts/caffeine.md", "concepts/espresso.md"]


def test_build_html_embeds_and_round_trips(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    assert "Espresso" in html and "concepts/caffeine.md" in html
    _, parsed = _embedded_bundle(html)
    assert parsed == viewer.build_bundle()


def test_build_html_is_offline(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    for bad in ("http://", "https://", "cdn", " src=", "fetch("):
        assert bad not in html, f"network reference present: {bad!r}"


def test_build_html_escapes_script_close(tmp_citadel, seed_page):
    seed_page(
        "concepts/x.md",
        {"type": "Concept", "title": "X"},
        "danger </script><b>x</b> end.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    html = viewer.build_html()
    assert "<\\/script>" in html  # the body's </script> was escaped
    assert "danger </script>" not in html  # ...and not left raw inside the data blob
    # exactly one real closing </script> per real <script> tag (bundle + viewer js)
    assert html.count("<script") == html.count("</script>")


def test_write_viewer_creates_file_and_load_skips(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    path = viewer.write_viewer()
    assert path.exists() and path.suffix == ".html" and path.name.startswith(".")
    assert path.read_text(encoding="utf-8") == viewer.build_html()
    # The generated artifact must not be loaded as a wiki page.
    assert not any(p.rel_path.endswith(".citadel_viewer.html") for p in store.load())


def test_view_no_open_returns_zero(tmp_citadel, seed_page, monkeypatch):
    _two_page_wiki(seed_page)
    calls = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda *a, **k: calls.append(a))
    rc = viewer.view(open_browser=False)
    assert rc == 0
    assert calls == []  # browser not launched
    assert (tmp_citadel.wiki / ".citadel_viewer.html").exists()


def test_view_handles_no_browser(tmp_citadel, seed_page, monkeypatch):
    _two_page_wiki(seed_page)

    def boom(*a, **k):
        raise viewer.webbrowser.Error("no browser")

    monkeypatch.setattr(viewer.webbrowser, "open", boom)
    rc = viewer.view(open_browser=True)  # must not crash
    assert rc == 0
    assert (tmp_citadel.wiki / ".citadel_viewer.html").exists()


def test_empty_wiki(tmp_citadel):
    html = viewer.build_html()
    assert '"pages":[]' in html.replace(" ", "")
    assert "<!doctype html>" in html


def test_bundle_page_stats_counts_cites_llm_contradictions(tmp_citadel, seed_page):
    body = (
        "Espresso uses pressure.[^s1] It is strong.[^s2]\n\n"
        "A model-supplied note.[^llm1]\n\n"
        "> [!CONTRADICTION]\n"
        "> raw/a.md says 9 bar [^s1]; raw/b.md says 8 bar [^s2].\n\n"
        "```\n[^s9]\n```\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - n\n"
        "[^s2]: [raw/b.md](../../raw/b.md) - n\n"
        "[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-22)\n"
    )
    seed_page("concepts/espresso.md", {"type": "Concept", "title": "Espresso"}, body)
    page = next(p for p in viewer.build_bundle()["pages"] if p["rel_path"] == "concepts/espresso.md")
    # 2 raw cites in prose + 2 inside the contradiction callout; the fenced [^s9] and the
    # trailing ## Sources definitions ([^sN]:) are not counted.
    assert page["cites"] == 4
    # Inline [^llm1]; the ## Sources definition is not counted as a use.
    assert page["llm"] == 1
    assert page["contradictions"] == 1


def test_bundle_page_stats_zero_when_clean(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)  # one [^s1] each, no llm, no contradiction
    by_path = {p["rel_path"]: p for p in viewer.build_bundle()["pages"]}
    assert by_path["concepts/espresso.md"]["cites"] == 1
    assert by_path["concepts/espresso.md"]["llm"] == 0
    assert by_path["concepts/espresso.md"]["contradictions"] == 0


def test_bundle_page_stats_ignores_fenced_and_sources_examples(tmp_citadel, seed_page):
    # A page that DOCUMENTS the citation/contradiction format must not have its example markers
    # counted: a callout inside a code fence is not a real contradiction, and a footnote marker
    # mentioned inside another footnote's ## Sources definition note is not an inline use.
    body = (
        "Real fact.[^s1]\n\n"
        "Here is how the contradiction format looks:\n\n"
        "```\n"
        "> [!CONTRADICTION]\n"
        "> raw/a.md says X [^s7]; raw/b.md says Y [^s8].\n"
        "```\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - derived alongside [^s2], see [^llm9] (ingested 2026-06-22)\n"
        "[^s2]: [raw/b.md](../../raw/b.md) - n\n"
    )
    seed_page("concepts/format.md", {"type": "Concept", "title": "Format"}, body)
    page = next(p for p in viewer.build_bundle()["pages"] if p["rel_path"] == "concepts/format.md")
    assert page["contradictions"] == 0  # the fenced callout is documentation, not a real one
    assert page["cites"] == 1  # only the inline [^s1]; fenced [^s7]/[^s8] and the def-note [^s2] excluded
    assert page["llm"] == 0  # the [^llm9] mentioned in the def note is not an inline use


def test_build_html_has_fulltext_search_badges_and_facets(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text("# A\n\nbody text\n", encoding="utf-8")
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    # Full-text search over bodies + result highlighting, the sidebar badge/facet machinery, and
    # the reader jump-to-contradiction/LLM affordance are all present in the inlined viewer.
    for marker in (
        "searchResults",
        "applyHighlight",
        "renderResults",
        "badgesHtml",
        "renderFacets",
        "data-facet",
        "data-jump",
        "<mark>",
        'id="facets"',
    ):
        assert marker in html, f"missing viewer feature marker: {marker!r}"
    # (The offline guarantee is asserted by test_build_html_is_offline /
    # test_build_html_makes_sources_clickable — not re-scanned here, since those substrings can
    # legitimately occur inside embedded source/page text on a real wiki.)


def test_golden_bundle_structural_invariants(tmp_citadel, seed_page):
    """Golden test on the BUILT document over a seeded 3-page wiki, pinning exactly three
    invariants of the Python-side embedding rules on the real artifact: the embedded page map
    contains the seeded rel_paths, cross-page links resolve to wiki-root-relative ids, and a
    literal ``</script>`` in a body escape-round-trips through the data blob (in place of any
    Python-vs-JS runtime parity test — no JS runtime in the suite)."""
    seed_page("concepts/alpha.md", {"type": "Concept", "title": "Alpha"}, "Links to [Beta](./beta.md).\n")
    seed_page("concepts/beta.md", {"type": "Concept", "title": "Beta"}, "Links to [Gamma](../misc/gamma.md).\n")
    seed_page("misc/gamma.md", {"type": "Note", "title": "Gamma"}, "Contains a literal </script> tag in prose.\n")
    blob, bundle = _embedded_bundle(viewer.build_html())

    # The '</' escape: gamma's literal '</script>' must not close the data <script> early in the
    # raw blob, and must round-trip back to '</script>' after the documented unescape.
    assert "<\\/script> tag in prose" in blob
    assert "</script> tag in prose" not in blob
    by_path = {p["rel_path"]: p for p in bundle["pages"]}
    assert "</script> tag in prose" in by_path["misc/gamma.md"]["body"]

    # The embedded page map contains exactly the seeded rel_paths.
    assert set(by_path) == {"concepts/alpha.md", "concepts/beta.md", "misc/gamma.md"}

    # Resolved hrefs between the pages: relative links resolve to wiki-root-relative ids in
    # outbound/inbound (edges are derived from outbound).
    assert by_path["concepts/alpha.md"]["outbound"] == ["concepts/beta.md"]
    assert by_path["concepts/beta.md"]["outbound"] == ["misc/gamma.md"]
    assert by_path["misc/gamma.md"]["inbound"] == ["concepts/beta.md"]


def test_cli_view_wires_up():
    from citadel import cli

    args = cli.build_parser().parse_args(["view", "--no-open"])
    assert args.func is cli.cmd_view
    assert args.open_browser is False
