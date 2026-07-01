"""Offline tests for the self-contained HTML viewer.

No browser, no network: every test only calls build_bundle/build_html/write_viewer/view and
asserts on strings (webbrowser.open is monkeypatched). Filesystem state is redirected to
tmp_path by monkeypatching config.* (same approach as test_ingest).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from citadel import config, okf, store, viewer


def _wire_tmp_wiki(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Redirect all config paths at a fresh tmp wiki/raw layout. Return (wiki, raw)."""
    repo = tmp_path
    wiki, raw, docs = repo / "wiki", repo / "raw", repo / "docs"
    for d in (wiki, raw, docs):
        d.mkdir(parents=True, exist_ok=True)
    (repo / "SCHEMA.md").write_text("# SCHEMA\n", encoding="utf-8")
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", docs, raising=False)
    return wiki, raw


def _seed(wiki: Path, rel_path: str, frontmatter: dict, body: str) -> None:
    target = wiki / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def _two_page_wiki(wiki: Path) -> None:
    _seed(
        wiki,
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
    _seed(
        wiki,
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


def test_bundle_embeds_cited_sources(tmp_path, monkeypatch):
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text(
        "# Coffee Overview\n\nCoffee is a brewed drink made from roasted beans.\n", encoding="utf-8"
    )
    _two_page_wiki(wiki)
    sources = viewer.build_bundle()["sources"]

    assert "raw/a.md" in sources
    s = sources["raw/a.md"]
    assert s["missing"] is False
    assert s["title"] == "Coffee Overview"
    assert "brewed drink" in s["body"]
    assert "brewed drink" in s["snippet"]
    # Both pages cite raw/a.md (resource frontmatter + a ## Sources footnote link).
    assert set(s["cited_by"]) == {"concepts/espresso.md", "concepts/caffeine.md"}


def test_binary_pdf_source_is_openable_not_unavailable(tmp_path, monkeypatch):
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    # A real PDF is binary (not UTF-8). It must not be reported as missing — instead it carries an
    # "open the original file" href so the browser can show it natively.
    (raw / "a.pdf").write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n")
    _seed(
        wiki,
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


def test_missing_source_is_flagged_not_fatal(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)  # cites raw/a.md, but the raw file is absent
    s = viewer.build_bundle()["sources"]["raw/a.md"]
    assert s["missing"] is True
    assert s["body"] == ""
    assert set(s["cited_by"]) == {"concepts/espresso.md", "concepts/caffeine.md"}


def test_build_html_makes_sources_clickable(tmp_path, monkeypatch):
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("# A\n\nbody text\n", encoding="utf-8")
    _two_page_wiki(wiki)
    html = viewer.build_html()
    # The inlined viewer renders raw citations as clickable source links and can open them.
    assert "data-source" in html
    assert "srclink" in html
    assert "openSource" in html
    # Still fully offline with an embedded source present.
    for bad in ("http://", "https://", "cdn", " src=", "fetch("):
        assert bad not in html, f"network reference present: {bad!r}"


def test_sources_keyed_by_browser_identity_in_nested_layout(tmp_path, monkeypatch):
    # When wiki/ is NOT a direct child of the repo root (e.g. CITADEL_WIKI_DIR=sub/wiki), the citation
    # climbs further but the in-browser resolver clamps '..' at the wiki root. The embedded source
    # must be keyed under that SAME clamped id, else the citation can't find it.
    repo = tmp_path
    wiki, raw, docs = repo / "sub" / "wiki", repo / "raw", repo / "docs"
    for d in (wiki, raw, docs):
        d.mkdir(parents=True, exist_ok=True)
    (repo / "SCHEMA.md").write_text("# SCHEMA\n", encoding="utf-8")
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", docs, raising=False)
    (raw / "x.md").write_text("# X source\n\ndetail\n", encoding="utf-8")
    # From repo/sub/wiki/concepts/p.md to repo/raw/x.md is '../../../raw/x.md'.
    _seed(
        wiki,
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites x.[^s1]\n\n## Sources\n\n[^s1]: [raw/x.md](../../../raw/x.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    # Keyed by the clamped identity the browser produces, not the WIKI_DIR.parent-relative '../raw/x.md'.
    assert "raw/x.md" in sources
    assert "../raw/x.md" not in sources
    assert sources["raw/x.md"]["cited_by"] == ["concepts/p.md"]


def test_sources_truncated_when_oversized(tmp_path, monkeypatch):
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    big = "x" * (viewer._SOURCE_MAX_CHARS + 50)
    (raw / "a.md").write_text(big, encoding="utf-8")
    _two_page_wiki(wiki)
    s = viewer.build_bundle()["sources"]["raw/a.md"]
    assert s["truncated"] is True
    assert len(s["body"]) == viewer._SOURCE_MAX_CHARS


def test_manifest_model_and_repo_and_uncited(tmp_path, monkeypatch):
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("# A\n\ncited\n", encoding="utf-8")
    (raw / "lonely.md").write_text("# Lonely\n\nuncited\n", encoding="utf-8")
    (wiki / ".citadel_ingested.json").write_text(
        json.dumps(
            {
                "raw/a.md": {"sha256": "h1", "model": "claude:sonnet"},
                "raw/lonely.md": {"sha256": "h2", "model": "copilot:gpt"},
                "raw/somerepo": {"kind": "git", "commit": "abc", "model": "claude:sonnet"},
            }
        ),
        encoding="utf-8",
    )
    _two_page_wiki(wiki)
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


def test_citation_inside_code_fence_is_not_a_source(tmp_path, monkeypatch):
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "real.md").write_text("# Real\n\nx\n", encoding="utf-8")
    (raw / "fenced.md").write_text("# Fenced\n\ny\n", encoding="utf-8")
    _seed(
        wiki,
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Real cite.[^s1]\n\n```\n[raw/fenced.md](../../raw/fenced.md)\n```\n\n"
        "## Sources\n\n[^s1]: [raw/real.md](../../raw/real.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "raw/real.md" in sources
    assert "raw/fenced.md" not in sources  # the fenced citation is a literal, not provenance


def test_angle_bracket_citation_is_discovered(tmp_path, monkeypatch):
    # A citation written in markdown's <...> target form must still be discovered and embedded
    # (store._split_link_target strips the brackets); the in-browser resolveLink strips them too.
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "x.md").write_text("# X\n\nbody\n", encoding="utf-8")
    _seed(
        wiki,
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites x.[^s1]\n\n## Sources\n\n[^s1]: [raw/x.md](<../../raw/x.md>) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "raw/x.md" in sources
    assert sources["raw/x.md"]["cited_by"] == ["concepts/p.md"]


def test_docs_citation_is_a_source(tmp_path, monkeypatch):
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (config.DOCS_DIR / "ref.md").write_text("# Reference\n\nspec\n", encoding="utf-8")
    _seed(
        wiki,
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites a doc.[^s1]\n\n## Sources\n\n[^s1]: [docs/ref.md](../../docs/ref.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "docs/ref.md" in sources
    assert sources["docs/ref.md"]["title"] == "Reference"


def test_bundle_contains_pages_links_tags(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)
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


def test_build_html_embeds_and_round_trips(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)
    html = viewer.build_html()
    assert "Espresso" in html and "concepts/caffeine.md" in html
    m = re.search(r'<script id="bundle" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert m, "embedded bundle script not found"
    parsed = json.loads(m.group(1).replace("<\\/", "</"))
    assert parsed == viewer.build_bundle()


def test_build_html_is_offline(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)
    html = viewer.build_html()
    for bad in ("http://", "https://", "cdn", " src=", "fetch("):
        assert bad not in html, f"network reference present: {bad!r}"


def test_build_html_escapes_script_close(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed(
        wiki,
        "concepts/x.md",
        {"type": "Concept", "title": "X"},
        "danger </script><b>x</b> end.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    html = viewer.build_html()
    assert "<\\/script>" in html  # the body's </script> was escaped
    assert "danger </script>" not in html  # ...and not left raw inside the data blob
    # exactly one real closing </script> per real <script> tag (bundle + viewer js)
    assert html.count("<script") == html.count("</script>")


def test_write_viewer_creates_file_and_load_skips(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)
    path = viewer.write_viewer()
    assert path.exists() and path.suffix == ".html" and path.name.startswith(".")
    assert path.read_text(encoding="utf-8") == viewer.build_html()
    # The generated artifact must not be loaded as a wiki page.
    assert not any(p.rel_path.endswith(".citadel_viewer.html") for p in store.load())


def test_view_no_open_returns_zero(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)
    calls = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda *a, **k: calls.append(a))
    rc = viewer.view(open_browser=False)
    assert rc == 0
    assert calls == []  # browser not launched
    assert (wiki / ".citadel_viewer.html").exists()


def test_view_handles_no_browser(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)

    def boom(*a, **k):
        raise viewer.webbrowser.Error("no browser")

    monkeypatch.setattr(viewer.webbrowser, "open", boom)
    rc = viewer.view(open_browser=True)  # must not crash
    assert rc == 0
    assert (wiki / ".citadel_viewer.html").exists()


def test_empty_wiki(tmp_path, monkeypatch):
    _wire_tmp_wiki(tmp_path, monkeypatch)
    html = viewer.build_html()
    assert '"pages":[]' in html.replace(" ", "")
    assert "<!doctype html>" in html


def test_cli_view_wires_up():
    from citadel import cli

    args = cli.build_parser().parse_args(["view", "--no-open"])
    assert args.func is cli.cmd_view
    assert args.open_browser is False
