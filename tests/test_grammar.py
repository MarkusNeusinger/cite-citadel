"""The shared citation grammar (citadel.grammar) and its two decided rules, pinned:

(A) a citation into a configured source root (raw/ or docs/) is LEGAL provenance — lint
    must not flag it as a structural broken link (check is authoritative);
(B) a link inside a ``` code fence is literal text — excluded from broken-link detection,
    exactly as the span rewriters treat it.
"""

from __future__ import annotations

from conftest import errors_of

from citadel import grammar, lint, store, validate


# --- resolution (A): a docs/ citation is a legal source citation, in check AND lint --------


def test_docs_citation_passes_check_and_lint(tmp_citadel, seed_page):
    """A [^sN] footnote citing an existing file under DOCS_DIR passes `citadel check` (it always
    did) AND lint structurally — lint used to report it under broken_links and flip ok()
    (resolution A)."""
    (tmp_citadel.raw / "notes.md").write_text("# notes\nfact\n", encoding="utf-8")
    (tmp_citadel.docs / "okf-reference.md").write_text("# OKF\nspec\n", encoding="utf-8")
    seed_page(
        "concepts/docs-cite.md",
        {"type": "Concept", "title": "Docs cite", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "A fact from the spec.[^s1]\n\n## Sources\n\n[^s1]: [OKF reference](../../docs/okf-reference.md)\n",
    )
    pages = store.load()
    assert errors_of(validate.validate_all(pages)) == []  # check: authoritative, and green
    report = lint.lint(pages)
    assert report.broken_links == []  # resolution (A): no structural flag for a docs/ citation
    assert report.bad_sources == []
    assert report.ok()


def test_inline_docs_link_is_not_a_broken_link(tmp_citadel, seed_page):
    """An inline prose link into docs/ (not a footnote) is a source citation too — skipped by
    the shared detector, so lint agrees with check instead of calling it broken (resolution A)."""
    (tmp_citadel.raw / "notes.md").write_text("# notes\n", encoding="utf-8")
    (tmp_citadel.docs / "ref.md").write_text("# Ref\n", encoding="utf-8")
    seed_page(
        "concepts/inline-docs.md",
        {"type": "Concept", "title": "Inline docs", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "See the [spec](../../docs/ref.md) for details.[^s1]\n\n## Sources\n\n[^s1]: [n](../../raw/notes.md)\n",
    )
    pages = store.load()
    assert errors_of(validate.validate_all(pages)) == []
    report = lint.lint(pages)
    assert report.broken_links == []
    assert report.ok()


# --- resolution (B): a fenced link is literal text, everywhere -----------------------------


_FENCED_BODY = (
    "Real prose fact.[^s1] More prose here.\n\n"
    "Example of the link syntax:\n\n"
    "```\n"
    "[example](missing-page.md)\n"
    "```\n\n"
    "## Sources\n\n"
    "[^s1]: [notes](../../raw/notes.md)\n"
)


def test_fenced_dead_link_is_literal_text(tmp_citadel, seed_page):
    """A dead .md link inside a ``` fence is documentation, not a link: excluded from
    find_broken_links (so check passes) and from lint's broken_links — matching what the
    rewriters already did to the same span (resolution B)."""
    (tmp_citadel.raw / "notes.md").write_text("# notes\n", encoding="utf-8")
    seed_page(
        "concepts/fenced.md",
        {"type": "Concept", "title": "Fenced", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        _FENCED_BODY,
    )
    pages = store.load()
    assert store.find_broken_links(pages) == []
    assert errors_of(validate.validate_all(pages)) == []
    report = lint.lint(pages)
    assert report.broken_links == []
    assert report.ok()


def test_unfenced_dead_link_is_still_broken(tmp_citadel, seed_page):
    """The SAME link outside the fence stays a structural broken link in check AND lint, and
    both report the identical (page, resolved-target) pair — one shared detector."""
    (tmp_citadel.raw / "notes.md").write_text("# notes\n", encoding="utf-8")
    seed_page(
        "concepts/unfenced.md",
        {"type": "Concept", "title": "Unfenced", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "A real [example](missing-page.md) link.[^s1]\n\n## Sources\n\n[^s1]: [notes](../../raw/notes.md)\n",
    )
    pages = store.load()
    expected = [("concepts/unfenced.md", "concepts/missing-page.md")]
    assert store.find_broken_links(pages) == expected
    assert any(i.category == "broken_link" for i in errors_of(validate.validate_all(pages)))
    report = lint.lint(pages)
    assert report.broken_links == expected  # byte-for-byte the check detector's answer
    assert not report.ok()


# --- grammar primitives ---------------------------------------------------------------------


def test_iter_lines_fence_semantics():
    """The one fence implementation: the ``` delimiter line itself counts as code, a language
    tag on the opener is fine, and indentation before the fence is tolerated."""
    body = "a\n```python\ncode\n  ```\nb\n"
    assert list(grammar.iter_lines(body)) == [
        ("a", False),
        ("```python", True),
        ("code", True),
        ("  ```", True),
        ("b", False),
    ]


def test_iter_lines_keepends_reassembles_byte_identically():
    """keepends=True (the rewriters' mode) round-trips the body byte-for-byte."""
    body = "x\r\n```\ny\n```\nz\n"
    assert "".join(line for line, _ in grammar.iter_lines(body, keepends=True)) == body


def test_prose_lines_views():
    body = "# Title\nfact\n```\nfenced\n```\n## Sources\n[^s1]: x\n## After\ntail\n"
    assert list(grammar.prose_lines(body)) == ["# Title", "fact", "## Sources", "[^s1]: x", "## After", "tail"]
    assert list(grammar.prose_lines(body, skip_sources=True)) == ["# Title", "fact", "## After", "tail"]


def test_is_source_citation_reads_config_roots_at_call_time(tmp_citadel):
    """Containment in RAW_DIR/DOCS_DIR (lexical, existence NOT required); wiki cross-links,
    external URLs, and anchors are not citations. The roots are read from config at call
    time — multi-root (PR4) extends the default in place, not the signature."""
    assert grammar.is_source_citation("concepts/a.md", "../../raw/x.md")
    assert grammar.is_source_citation("concepts/a.md", "../../docs/ref.pdf")
    assert not grammar.is_source_citation("concepts/a.md", "./b.md")
    assert not grammar.is_source_citation("concepts/a.md", "https://example.com/raw/x.md")
    assert not grammar.is_source_citation("concepts/a.md", "#sources")


def test_absolute_citation_targets_are_source_links():
    """Pre-paves docs/refactor-plan.md Z3: non-sibling raw roots are cited by ABSOLUTE posix
    path, which must classify as a source citation (skipped by rewriters/detectors), never as
    a rewritable wiki cross-link — pinned NOW so PR4 cannot silently miscategorize it."""
    assert grammar.resolves_to_source("/mnt/share/raw-archive/x.md")
    assert grammar.resolves_to_source("C:/share/raw-archive/x.md")
    assert grammar.resolves_to_source("../raw-archive/x.md")  # ..-escape stays a source link
    assert not grammar.resolves_to_source("concepts/b.md")


def test_resolved_md_links_shared_detector():
    """One pass: keeps only genuine wiki cross-links — no citations, no fenced literals, no
    external/anchor targets — resolved to wiki-root-relative identities."""
    body = (
        "See [B](./b.md), [raw](../../raw/x.md), and [docs](../../docs/y.md).\n"
        "```\n[fenced](./dead.md)\n```\n"
        "[ext](https://e.com/x.md) and [anchor](#top).\n"
    )
    assert grammar.resolved_md_links("concepts/a.md", body) == [("./b.md", "concepts/b.md")]


def test_split_link_target_forms():
    assert grammar.split_link_target('../../raw/x.md "note"') == ("../../raw/x.md", ' "note"')
    assert grammar.split_link_target("<../../raw/x.md>") == ("../../raw/x.md", "")
    assert grammar.split_link_target("plain.md") == ("plain.md", "")
