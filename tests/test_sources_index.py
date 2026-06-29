"""Offline tests for the by-source provenance axis: the generated ``## Sources`` section in
``index.md`` (store.rebuild_indexes) and the ``wiki_sources`` MCP tool (server).

The provenance catalog (``sources/index.md``) is skipped by the page loader, so it never shows
up in ``wiki_search``; these tests pin the two ways it IS surfaced. No network, no LLM — a tmp
wiki plus a small hand-written manifest.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, manifest, okf, server, store


def _wire_tmp_wiki(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path
    wiki, raw = repo / "wiki", repo / "raw"
    for d in (wiki, raw):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "MANIFEST_PATH", wiki / ".citadel_ingested.json", raising=False)
    monkeypatch.setattr(config, "INDEX_PATH", wiki / "index.md", raising=False)
    return wiki


def _seed(wiki: Path, rel_path: str, frontmatter: dict, body: str = "Body.\n") -> None:
    target = wiki / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def test_index_renders_sources_section(tmp_path, monkeypatch):
    """rebuild_indexes surfaces a '## Sources' section listing each tracked raw source with its
    citing-page count and a link to the raw file — the by-source axis, visible from index.md."""
    wiki = _wire_tmp_wiki(tmp_path, monkeypatch)
    (tmp_path / "raw" / "a.md").write_text("raw a\n", encoding="utf-8")
    (tmp_path / "raw" / "b.md").write_text("raw b\n", encoding="utf-8")
    manifest.save(
        {
            "raw/a.md": manifest.make_entry("sha-a", model="sonnet"),
            "raw/b.md": manifest.make_entry("sha-b"),
        }
    )
    _seed(
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.",
         "tags": ["coffee"], "resource": "raw/a.md"},
    )

    store.rebuild_indexes()
    index = (wiki / "index.md").read_text(encoding="utf-8")

    assert "## Sources" in index
    assert "2 ingested raw source(s)" in index
    assert "[sources/index.md](sources/index.md)" in index
    # raw/a.md is cited (via the page's resource frontmatter); raw/b.md is not.
    assert "[raw/a.md](../raw/a.md) — cited by 1 page" in index
    assert "[raw/b.md](../raw/b.md) — uncited" in index


def test_index_has_no_sources_section_without_manifest(tmp_path, monkeypatch):
    """No tracked source -> no '## Sources' section (and no stale sources/index.md)."""
    wiki = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed(
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.",
         "tags": ["coffee"], "resource": "raw/a.md"},
    )
    store.rebuild_indexes()
    index = (wiki / "index.md").read_text(encoding="utf-8")
    assert "## Sources" not in index
    assert not (wiki / "sources" / "index.md").exists()


def test_wiki_sources_tool_returns_catalog(tmp_path, monkeypatch):
    """The wiki_sources MCP tool returns the generated provenance catalog, incl. the model."""
    wiki = _wire_tmp_wiki(tmp_path, monkeypatch)
    (tmp_path / "raw" / "a.md").write_text("raw a\n", encoding="utf-8")
    manifest.save({"raw/a.md": manifest.make_entry("sha-a", model="sonnet")})
    _seed(
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.",
         "tags": ["coffee"], "resource": "raw/a.md"},
    )
    store.rebuild_indexes()

    out = server.wiki_sources()
    assert "# Sources" in out
    assert "raw/a.md" in out
    assert "sonnet" in out  # the importing model is shown in the catalog


def test_wiki_sources_tool_no_catalog(tmp_path, monkeypatch):
    """With nothing ingested, wiki_sources returns a friendly message, not an error/traceback."""
    _wire_tmp_wiki(tmp_path, monkeypatch)
    out = server.wiki_sources()
    assert "No sources catalog yet" in out
