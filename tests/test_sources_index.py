"""Offline tests for the by-source provenance axis: the generated ``## Sources`` section in
``index.md`` (store.rebuild_indexes) and the ``wiki_sources`` MCP tool (server).

The provenance catalog (``sources/index.md``) is skipped by the page loader, so it never shows
up in ``wiki_search``; these tests pin the two ways it IS surfaced. No network, no LLM — a tmp
wiki plus a small hand-written manifest.
"""

from __future__ import annotations

from citadel import manifest, server, store


def test_index_renders_sources_section(tmp_citadel, seed_page):
    """rebuild_indexes surfaces a '## Sources' section listing each tracked raw source with its
    citing-page count and a link to the raw file — the by-source axis, visible from index.md."""
    (tmp_citadel.raw / "a.md").write_text("raw a\n", encoding="utf-8")
    (tmp_citadel.raw / "b.md").write_text("raw b\n", encoding="utf-8")
    manifest.save({"raw/a.md": manifest.make_entry("sha-a", model="sonnet"), "raw/b.md": manifest.make_entry("sha-b")})
    seed_page(
        "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.", "tags": ["coffee"], "resource": "raw/a.md"},
    )

    store.rebuild_indexes()
    index = tmp_citadel.index_path.read_text(encoding="utf-8")

    assert "## Sources" in index
    assert "2 ingested raw source(s)" in index
    assert "[sources/index.md](sources/index.md)" in index
    # raw/a.md is cited (via the page's resource frontmatter); raw/b.md is not.
    assert "[raw/a.md](../raw/a.md) — cited by 1 page" in index
    assert "[raw/b.md](../raw/b.md) — uncited" in index


def test_index_has_no_sources_section_without_manifest(tmp_citadel, seed_page):
    """No tracked source -> no '## Sources' section (and no stale sources/index.md)."""
    seed_page(
        "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.", "tags": ["coffee"], "resource": "raw/a.md"},
    )
    store.rebuild_indexes()
    index = tmp_citadel.index_path.read_text(encoding="utf-8")
    assert "## Sources" not in index
    assert not (tmp_citadel.wiki / "sources" / "index.md").exists()


def test_wiki_sources_tool_returns_catalog(tmp_citadel, seed_page):
    """The wiki_sources MCP tool returns the generated provenance catalog, incl. the model."""
    (tmp_citadel.raw / "a.md").write_text("raw a\n", encoding="utf-8")
    manifest.save({"raw/a.md": manifest.make_entry("sha-a", model="sonnet")})
    seed_page(
        "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.", "tags": ["coffee"], "resource": "raw/a.md"},
    )
    store.rebuild_indexes()

    out = server.wiki_sources()
    assert "# Sources" in out
    assert "raw/a.md" in out
    assert "sonnet" in out  # the importing model is shown in the catalog


def test_wiki_sources_tool_no_catalog(tmp_citadel):
    """With nothing ingested, wiki_sources returns a friendly message, not an error/traceback."""
    out = server.wiki_sources()
    assert "No sources catalog yet" in out
