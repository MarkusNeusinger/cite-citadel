"""Lint / store / OKF-compliance checks over hand-seeded pages (independent of the ingest
mechanism, offline): fabricated sources, wikilinks, LLM-sourced facts, generated indexes/log,
tag catalog, and suggested links.
"""

from __future__ import annotations

import pytest

from citadel import linkgraph, lint, okf, store


def test_lint_flags_fabricated_source(tmp_citadel, seed_page):
    """A page citing a raw file that does not exist is flagged and flips lint.ok()."""
    seed_page(
        "concepts/made-up.md",
        {"type": "Concept", "title": "Made Up", "resource": "raw/ghost.md"},
        "An uncited-source fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/ghost.md](../../raw/ghost.md) - ghost (ingested 2026-06-22)\n",
    )
    report = lint.lint()
    assert ("concepts/made-up.md", "../../raw/ghost.md") in report.bad_sources
    assert not report.ok()


def test_lint_clean_when_source_exists(tmp_citadel, seed_page):
    """The same page passes once its cited raw file actually exists."""
    raw = tmp_citadel.raw
    (raw / "real.md").write_text("real source\n", encoding="utf-8")
    seed_page(
        "concepts/grounded.md",
        {"type": "Concept", "title": "Grounded", "resource": "raw/real.md"},
        "A grounded fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/real.md](../../raw/real.md) - real (ingested 2026-06-22)\n",
    )
    report = lint.lint()
    assert report.bad_sources == []


def test_lint_flags_wikilink(tmp_citadel, seed_page):
    """A [[wiki-style]] link is flagged and flips lint.ok()."""
    raw = tmp_citadel.raw
    (raw / "a.md").write_text("src\n", encoding="utf-8")
    seed_page(
        "concepts/wikilinked.md",
        {"type": "Concept", "title": "Wikilinked", "resource": "raw/a.md"},
        "See [[Some Page]] for more.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    report = lint.lint()
    assert ("concepts/wikilinked.md", "Some Page") in report.wikilinks
    assert not report.ok()


def test_rewrite_links_skips_code_fences_and_substrings():
    """The link rewrite touches only genuine link spans: a literal ](old) inside a fenced
    code block is left intact, and only the real cross-link is repointed."""
    body = "See [Old](./old.md) for details.\n\n```\ndocumented syntax: [X](./old.md)\n```\n\nEnd.\n"
    out = linkgraph._rewrite_body_links("concepts/page.md", body, {"concepts/old.md": "concepts/new.md"})
    assert "[Old](new.md)" in out  # real link repointed
    assert "[X](./old.md)" in out  # fenced literal left intact
    assert out.count("(new.md)") == 1


@pytest.mark.parametrize("rel_path", ["index.md", "log.md", "concepts/index.md",
        "concepts\\index.md",  # windows separator must not bypass the guard, ".citadel_ingested.json", ""])
def test_write_page_refuses_generated_files(tmp_citadel, rel_path):
    """write_page carries delete_page's reserved-name guard: a programmatic write (e.g. curate)
    can NEVER clobber a generated/reserved file (index.md, any per-folder index.md, log.md, a
    dotfile, or the empty path) — it raises before touching disk, even with valid frontmatter."""
    wiki = tmp_citadel.wiki
    before = (wiki / rel_path).read_bytes() if rel_path and (wiki / rel_path).is_file() else None
    with pytest.raises(okf.OKFError):
        store.write_page(rel_path, {"type": "Concept", "title": "Clobber"}, "body\n")
    if before is not None:  # a pre-existing generated file is left byte-for-byte intact
        assert (wiki / rel_path).read_bytes() == before


def test_lint_allows_and_surfaces_llm_sourced_fact(tmp_citadel, seed_page):
    """A model-supplied [^llmN] fact is NOT flagged as fabricated, but IS surfaced under
    llm_facts for transparency; the page still passes lint."""
    seed_page(
        "concepts/with-llm.md",
        {"type": "Concept", "title": "With LLM", "resource": "raw/real.md"},
        "An essential, high-confidence model fact.[^llm1]\n\n## Sources\n\n"
        "[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-22)\n",
    )
    report = lint.lint()
    assert report.bad_sources == []
    assert "concepts/with-llm.md" in report.llm_facts
    assert report.ok()


def test_lint_flags_bare_and_undefined_sources(tmp_citadel, seed_page):
    """A bare-path (un-linked) source def and a used-but-undefined marker are both flagged."""
    seed_page(
        "concepts/sloppy.md",
        {"type": "Concept", "title": "Sloppy", "resource": "raw/x.md"},
        "Fact one.[^s1] Fact two.[^s2]\n\n## Sources\n\n"
        "[^s1]: raw/x.md (ingested 2026-06-22)\n",  # bare path, no markdown link; s2 undefined
    )
    report = lint.lint()
    details = [t for r, t in report.bad_sources if r == "concepts/sloppy.md"]
    assert any("no resolvable source link" in d for d in details)
    assert any("[^s2] used but undefined" in d for d in details)
    assert not report.ok()


def test_lint_tolerates_link_title_and_code_fences(tmp_citadel, seed_page):
    """A link title in a Sources def, and an example def inside a code fence, do not cause
    false-positive fabricated-source failures."""
    raw = tmp_citadel.raw
    (raw / "x.md").write_text("src\n", encoding="utf-8")
    seed_page(
        "concepts/titled.md",
        {"type": "Concept", "title": "Titled", "resource": "raw/x.md"},
        "A fact.[^s1]\n\n"
        "```\n"
        "[^sN]: [raw/example.md](../../raw/example.md) - how to cite\n"
        "```\n\n"
        "## Sources\n\n"
        '[^s1]: [raw/x.md](../../raw/x.md "the title") - note (ingested 2026-06-22)\n',
    )
    report = lint.lint()
    assert report.bad_sources == []
    assert report.ok()


def test_indexes_have_no_frontmatter(tmp_citadel, seed_page):
    """OKF: index.md (top + per-folder) must NOT carry YAML frontmatter."""
    wiki = tmp_citadel.wiki
    seed_page(
        "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"]},
        "Alpha body.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    store.rebuild_indexes()
    top = (wiki / "index.md").read_text(encoding="utf-8")
    folder = (wiki / "concepts" / "index.md").read_text(encoding="utf-8")
    assert top.startswith("# Wiki Index") and not top.startswith("---")
    assert "type: Index" not in top
    assert folder.startswith("# concepts") and not folder.startswith("---")
    assert "## Tags" in top and "### x (1)" in top
    assert not (wiki / "tags.md").exists()


def test_index_shows_backlinks(tmp_citadel, seed_page):
    """The top index lists who references each page (the backlink graph)."""
    wiki = tmp_citadel.wiki
    seed_page(
        "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "resource": "raw/a.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    seed_page(
        "concepts/b.md",
        {"type": "Concept", "title": "Beta", "resource": "raw/a.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    store.rebuild_indexes()
    top = (wiki / "index.md").read_text(encoding="utf-8")
    assert "referenced by:" in top
    assert "[Beta](concepts/b.md)" in top


def test_log_is_frontmatter_free_with_date_headings(tmp_citadel):
    """OKF: log.md has no frontmatter and groups entries under ## YYYY-MM-DD headings."""
    import re as _re

    store.append_log("did a thing")
    log = tmp_citadel.log_path.read_text(encoding="utf-8")
    assert log.startswith("# Log") and not log.startswith("---")
    assert "type: Log" not in log
    assert _re.search(r"(?m)^## \d{4}-\d{2}-\d{2}$", log)
    assert "did a thing" in log


def test_tag_catalog_and_suggested_links(tmp_citadel, seed_page):
    """tag_catalog groups pages by tag; lint suggests an un-linked mention (advisory)."""
    raw = tmp_citadel.raw
    (raw / "a.md").write_text("src\n", encoding="utf-8")
    seed_page(
        "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "tags": ["brewing", "coffee"], "resource": "raw/a.md"},
        "Espresso is pressure brewing.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    seed_page(
        "concepts/caffeine.md",
        {"type": "Concept", "title": "Caffeine", "tags": ["coffee"], "resource": "raw/a.md"},
        "Espresso carries caffeine.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    catalog = store.tag_catalog()
    assert set(catalog) == {"brewing", "coffee"}
    assert {p.rel_path for p in catalog["coffee"]} == {"concepts/espresso.md", "concepts/caffeine.md"}

    report = lint.lint()
    assert ("concepts/caffeine.md", "concepts/espresso.md (mentions 'Espresso')") in report.suggested_links
    assert report.ok()  # advisory only


def test_suggested_links_skips_already_linked(tmp_citadel, seed_page):
    """A page that already links a concept is not nagged to link it again."""
    seed_page(
        "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "resource": "raw/a.md"},
        "Espresso.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    seed_page(
        "concepts/caffeine.md",
        {"type": "Concept", "title": "Caffeine", "resource": "raw/a.md"},
        "See [Espresso](./espresso.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    report = lint.lint()
    caffeine_suggestions = [t for r, t in report.suggested_links if r == "concepts/caffeine.md"]
    assert not any("espresso.md" in s for s in caffeine_suggestions)
