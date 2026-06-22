"""Offline tests for the self-contained HTML viewer.

No browser, no network: every test only calls build_bundle/build_html/write_viewer/view and
asserts on strings (webbrowser.open is monkeypatched). Filesystem state is redirected to
tmp_path by monkeypatching config.* (same approach as test_ingest).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from okf_wiki import config, okf, store, viewer


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
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew method.",
         "tags": ["brewing", "coffee"], "resource": "raw/a.md"},
        "Espresso uses pressure.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - n (ingested 2026-06-22)\n",
    )
    _seed(
        wiki, "concepts/caffeine.md",
        {"type": "Concept", "title": "Caffeine", "description": "The stimulant.",
         "tags": ["coffee"], "resource": "raw/a.md"},
        "See [Espresso](./espresso.md) for the shot.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - n (ingested 2026-06-22)\n",
    )


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
    m = re.search(
        r'<script id="bundle" type="application/json">(.*?)</script>', html, re.DOTALL
    )
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
        wiki, "concepts/x.md", {"type": "Concept", "title": "X"},
        "danger </script><b>x</b> end.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    html = viewer.build_html()
    assert "<\\/script>" in html          # the body's </script> was escaped
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
    assert not any(p.rel_path.endswith(".okf_viewer.html") for p in store.load())


def test_view_no_open_returns_zero(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)
    calls = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda *a, **k: calls.append(a))
    rc = viewer.view(open_browser=False)
    assert rc == 0
    assert calls == []  # browser not launched
    assert (wiki / ".okf_viewer.html").exists()


def test_view_handles_no_browser(tmp_path, monkeypatch):
    wiki, _ = _wire_tmp_wiki(tmp_path, monkeypatch)
    _two_page_wiki(wiki)

    def boom(*a, **k):
        raise viewer.webbrowser.Error("no browser")

    monkeypatch.setattr(viewer.webbrowser, "open", boom)
    rc = viewer.view(open_browser=True)  # must not crash
    assert rc == 0
    assert (wiki / ".okf_viewer.html").exists()


def test_empty_wiki(tmp_path, monkeypatch):
    _wire_tmp_wiki(tmp_path, monkeypatch)
    html = viewer.build_html()
    assert '"pages":[]' in html.replace(" ", "")
    assert "<!doctype html>" in html


def test_cli_view_wires_up():
    from okf_wiki import cli

    args = cli.build_parser().parse_args(["view", "--no-open"])
    assert args.func is cli.cmd_view
    assert args.open_browser is False
