"""Unit tests for store.neighbors_text — the wiki_neighbors / ``citadel neighbors`` provider: a page's
links out, backlinks, and cited-source keys, so an AI can walk the graph without relative-path math."""

from __future__ import annotations

import pytest

from citadel import store


def test_lists_out_links_backlinks_and_cited_sources(tmp_citadel, seed_page):
    (tmp_citadel.raw / "notes.md").write_text("# N\nfact\n", encoding="utf-8")
    seed_page(
        "concepts/a.md",
        {"type": "Concept", "title": "A", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "A links to [B](b.md).[^s1] More.[^s2]\n\n## Sources\n\n"
        "[^s1]: [raw/notes.md](../../raw/notes.md), lines 1-1\n"
        "[^s2]: [raw/notes.md](../../raw/notes.md), lines 2-2\n",
    )
    seed_page(
        "concepts/b.md", {"type": "Concept", "title": "B", "description": "d", "tags": ["t"]}, "B links to [A](a.md).\n"
    )

    out = store.neighbors_text("concepts/a.md")

    assert out.startswith("# Neighbors of concepts/a.md — A")
    assert "## Links out (1)" in out and "- concepts/b.md — B" in out
    assert "## Linked from (1)" in out  # b.md links back to a.md
    assert "## Cites sources (1)" in out and "- raw/notes.md — 2 citations" in out  # two footnotes, one file


def test_missing_link_target_is_flagged(tmp_citadel, seed_page):
    seed_page(
        "concepts/a.md", {"type": "Concept", "title": "A", "description": "d", "tags": ["t"]}, "See [Gone](ghost.md).\n"
    )

    out = store.neighbors_text("concepts/a.md")

    assert "- concepts/ghost.md — (missing)" in out
    assert "## Linked from (0)" in out and "- (none)" in out


def test_missing_page_raises_file_not_found(tmp_citadel):
    with pytest.raises(FileNotFoundError):
        store.neighbors_text("concepts/nope.md")
