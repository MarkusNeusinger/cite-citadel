"""Offline integration tests for ingest: idempotency, apply-ops, contradiction marker.

``llm.plan_pages`` is monkeypatched to a deterministic fake, so these run with NO
network and NO API key (the anthropic SDK need not even be installed). All filesystem
state is redirected to ``tmp_path`` by monkeypatching ``config.*`` attributes, so every
module that references ``config.WIKI_DIR`` / ``config.RAW_DIR`` / etc. at call-time picks
up the temp layout.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from okf_wiki import config, ingest, lint, store


# A counter so tests can assert the fake LLM is called exactly once per source.
_CALLS: dict[str, int] = {"n": 0}


def fake_plan_pages(raw_name, raw_text, digest):
    """Deterministic stand-in for the single Anthropic structured-output call.

    Returns a fixed ops list: one Concept page with a per-fact GFM footnote that links
    relatively to the raw file, plus a trailing '## Sources' section.
    """
    _CALLS["n"] += 1
    return [
        {
            "op": "write",
            "type": "Concept",
            "title": "Transformer",
            "rel_path": "",
            "description": "self-attention model",
            "tags": ["ml"],
            "body": (
                "Transformers use self-attention.[^s1]\n\n"
                "## Sources\n\n"
                "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n"
            ),
        }
    ]


def fake_plan_pages_contradiction(raw_name, raw_text, digest):
    """Fake op whose body contains a '> [!CONTRADICTION]' callout."""
    _CALLS["n"] += 1
    return [
        {
            "op": "write",
            "type": "Note",
            "title": "Q3 Revenue",
            "rel_path": "",
            "description": "Conflicting revenue figures.",
            "tags": ["finance"],
            "body": (
                "Revenue figures conflict across sources.[^s1][^s2]\n\n"
                "> [!CONTRADICTION]\n"
                "> raw/a.md says revenue grew 12% [^s1]; "
                "raw/b.md says it grew 9% [^s2].\n\n"
                "## Sources\n\n"
                "[^s1]: [raw/a.md](../../raw/a.md) - report a (ingested 2026-06-21)\n"
                "[^s2]: [raw/b.md](../../raw/b.md) - report b (ingested 2026-06-21)\n"
            ),
        }
    ]


def fake_plan_pages_echoed_frontmatter(raw_name, raw_text, digest):
    """Fake whose body wrongly starts with a YAML frontmatter block — as some models
    do when they mimic the digest. _apply_op must strip it."""
    _CALLS["n"] += 1
    return [
        {
            "op": "write",
            "type": "Concept",
            "title": "Transformer",
            "rel_path": "",
            "description": "self-attention model",
            "tags": ["ml"],
            "body": (
                "---\ntype: Concept\ntitle: Transformer\n---\n\n"
                "Transformers use self-attention.[^s1]\n\n"
                "## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - notes\n"
            ),
        }
    ]


def _wire_tmp_wiki(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Redirect all config paths at a fresh tmp wiki/raw layout. Return (wiki, raw)."""
    _CALLS["n"] = 0

    repo = tmp_path
    wiki = repo / "wiki"
    raw = repo / "raw"
    docs = repo / "docs"
    for d in (wiki, raw, docs):
        d.mkdir(parents=True, exist_ok=True)

    # A SCHEMA.md so anything reading config.SCHEMA_PATH works (llm is faked, but be safe).
    schema_path = repo / "SCHEMA.md"
    schema_path.write_text("# SCHEMA\n\ntest schema\n", encoding="utf-8")

    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", docs, raising=False)
    monkeypatch.setattr(config, "SCHEMA_PATH", schema_path, raising=False)
    monkeypatch.setattr(config, "INDEX_PATH", wiki / "index.md", raising=False)
    monkeypatch.setattr(config, "LOG_PATH", wiki / "log.md", raising=False)
    monkeypatch.setattr(
        config, "MANIFEST_PATH", wiki / ".okf_ingested.json", raising=False
    )
    return wiki, raw


def test_ingest_creates_pages(tmp_path, monkeypatch):
    """Creates a page with the footnote, regenerates index, appends log, updates manifest."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "plan_pages", fake_plan_pages)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    assert _CALLS["n"] == 1
    assert "raw/notes.md" in report.processed
    assert not report.errors

    page = wiki / "concepts" / "transformer.md"
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "[^s1]" in text
    assert "## Sources" in text
    assert "../../raw/notes.md" in text
    # write_page stamps a timestamp into frontmatter.
    assert "timestamp:" in text
    # page-level resource: defaults to the primary raw source even when the op
    # itself omits it.
    assert "resource: raw/notes.md" in text

    # Page is the rel_path that ingest reported — a CREATE (did not exist before).
    assert "concepts/transformer.md" in report.pages_written
    assert "concepts/transformer.md" in report.pages_created
    assert report.pages_updated == []

    # index.md regenerated and mentions the new page.
    index_text = (wiki / "index.md").read_text(encoding="utf-8")
    assert "transformer.md" in index_text

    # log.md appended.
    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "ingest" in log_text
    assert "created" in log_text
    assert "deleted" in log_text

    # manifest updated with the source's hash.
    import json

    manifest_text = (wiki / ".okf_ingested.json").read_text(encoding="utf-8")
    manifest_data = json.loads(manifest_text)
    assert "raw/notes.md" in manifest_data


def test_ingest_strips_echoed_frontmatter(tmp_path, monkeypatch):
    """A body that wrongly includes its own frontmatter block is cleaned, so the
    written page has exactly one frontmatter block (no doubling)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "plan_pages", fake_plan_pages_echoed_frontmatter)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    ingest.ingest()
    text = (wiki / "concepts" / "transformer.md").read_text(encoding="utf-8")
    # Exactly two lines that are exactly '---' (one frontmatter block: open + close).
    assert text.split("\n").count("---") == 2
    assert text.startswith("---\n")
    assert "Transformers use self-attention.[^s1]" in text


def test_reingest_is_noop(tmp_path, monkeypatch):
    """Running ingest twice on the same raw file is idempotent: 2nd processes nothing."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "plan_pages", fake_plan_pages)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    first = ingest.ingest()
    assert first.processed == ["raw/notes.md"]
    assert _CALLS["n"] == 1

    second = ingest.ingest()
    assert second.processed == []
    assert "raw/notes.md" in second.skipped
    # The fake LLM was NOT called a second time.
    assert _CALLS["n"] == 1


def _seed_page(wiki: Path, rel_path: str, frontmatter: dict, body: str) -> None:
    """Write an OKF page directly under the temp wiki (bypassing ingest)."""
    from okf_wiki import okf

    target = wiki / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def test_merge_then_delete_with_redirect_repoints_links(tmp_path, monkeypatch):
    """A merge expressed as write(survivor) + delete(absorbed, redirect=survivor):
    the absorbed page is removed, the survivor holds the merged body, and an inbound
    cross-link from a THIRD page is repointed to the survivor so nothing breaks."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    # Seed two existing pages: one to be absorbed, and a third that links to it.
    _seed_page(
        wiki,
        "concepts/attention.md",
        {"type": "Concept", "title": "Attention", "resource": "raw/old.md"},
        "Attention is a mechanism.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )
    _seed_page(
        wiki,
        "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "resource": "raw/old.md"},
        "See [Attention](./attention.md) for details.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("Self-attention merges attention.\n", encoding="utf-8")

    def fake(raw_name, raw_text, digest):
        return [
            {
                "op": "write",
                "type": "Concept",
                "title": "Self-Attention",
                "rel_path": "concepts/self-attention.md",
                "description": "merged",
                "tags": ["ml"],
                "body": (
                    "Self-attention subsumes attention.[^s1]\n\n## Sources\n\n"
                    "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-22)\n"
                ),
            },
            {
                "op": "delete",
                "rel_path": "concepts/attention.md",
                "redirect": "concepts/self-attention.md",
            },
        ]

    monkeypatch.setattr(ingest.llm, "plan_pages", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert not report.errors
    assert "concepts/self-attention.md" in report.pages_written
    assert "concepts/attention.md" in report.pages_deleted
    # The absorbed page is gone; the survivor exists.
    assert not (wiki / "concepts" / "attention.md").exists()
    assert (wiki / "concepts" / "self-attention.md").exists()
    # The third page's inbound link was repointed to the survivor — no broken link.
    # (os.path.relpath yields 'self-attention.md', which resolves the same as './…'.)
    linker = (wiki / "concepts" / "linker.md").read_text(encoding="utf-8")
    assert "(self-attention.md)" in linker
    assert "(./attention.md)" not in linker
    assert report.broken_links == []
    # And lint confirms the repointed link actually resolves (no broken links).
    assert lint.lint().broken_links == []


def test_delete_missing_page_is_reported_not_fatal(tmp_path, monkeypatch):
    """A delete of a non-existent page is a non-fatal error; the source still finalises."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(raw_name, raw_text, digest):
        return [{"op": "delete", "rel_path": "concepts/ghost.md"}]

    monkeypatch.setattr(ingest.llm, "plan_pages", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" in report.processed  # finalised despite the bad delete
    assert any("no such page" in e for e in report.errors)
    assert report.pages_deleted == []


def test_delete_protected_file_refused(tmp_path, monkeypatch):
    """A delete targeting a generated file (index.md) is refused; the file survives."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki,
        "concepts/real.md",
        {"type": "Concept", "title": "Real", "resource": "raw/notes.md"},
        "A real page.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/notes.md](../../raw/notes.md) - n (ingested 2026-06-22)\n",
    )
    store.rebuild_indexes()  # creates wiki/index.md and concepts/index.md
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(raw_name, raw_text, digest):
        # index.md is in the existing set (rebuild wrote concepts/index.md), but
        # delete_page must refuse it regardless.
        return [{"op": "delete", "rel_path": "concepts/index.md"}]

    monkeypatch.setattr(ingest.llm, "plan_pages", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    # Either refused as a protected-file error, or skipped as not-a-loadable-page; in
    # both cases the index file must still exist and nothing is deleted.
    assert report.pages_deleted == []
    assert (wiki / "concepts" / "index.md").exists()


def test_lint_flags_fabricated_source(tmp_path, monkeypatch):
    """A page citing a raw file that does not exist is flagged and flips lint.ok()."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki,
        "concepts/made-up.md",
        {"type": "Concept", "title": "Made Up", "resource": "raw/ghost.md"},
        "An uncited-source fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/ghost.md](../../raw/ghost.md) - ghost (ingested 2026-06-22)\n",
    )
    report = lint.lint()
    assert ("concepts/made-up.md", "../../raw/ghost.md") in report.bad_sources
    assert not report.ok()


def test_lint_clean_when_source_exists(tmp_path, monkeypatch):
    """The same page passes once its cited raw file actually exists."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "real.md").write_text("real source\n", encoding="utf-8")
    _seed_page(
        wiki,
        "concepts/grounded.md",
        {"type": "Concept", "title": "Grounded", "resource": "raw/real.md"},
        "A grounded fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/real.md](../../raw/real.md) - real (ingested 2026-06-22)\n",
    )
    report = lint.lint()
    assert report.bad_sources == []


def test_contradiction_marker_preserved(tmp_path, monkeypatch):
    """A contradiction marker in the op body survives the write and lint flags it."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "plan_pages", fake_plan_pages_contradiction)

    (raw / "a.md").write_text("Revenue grew 12%.\n", encoding="utf-8")

    report = ingest.ingest()
    assert not report.errors
    assert report.pages_written

    written_rel = report.pages_written[0]
    page = wiki / Path(written_rel)
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "> [!CONTRADICTION]" in text

    # lint over the freshly written wiki lists the page under contradictions.
    lint_report = lint.lint()
    assert written_rel in lint_report.contradictions


# --- review-hardening regression tests -------------------------------------------------


def test_delete_of_just_written_page_is_refused(tmp_path, monkeypatch):
    """DATA-LOSS GUARD: an op list that both writes AND deletes the same rel_path must keep
    the page (the delete is refused), even though writes apply before deletes."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(raw_name, raw_text, digest):
        return [
            {
                "op": "write", "type": "Concept", "title": "Big",
                "rel_path": "concepts/big.md", "description": "d", "tags": [],
                "body": "A fact.[^s1]\n\n## Sources\n\n"
                        "[^s1]: [raw/notes.md](../../raw/notes.md) - n (ingested 2026-06-22)\n",
            },
            {"op": "delete", "rel_path": "concepts/big.md"},
        ]

    monkeypatch.setattr(ingest.llm, "plan_pages", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "concepts/big.md" in report.pages_written
    assert report.pages_deleted == []
    assert (wiki / "concepts" / "big.md").exists()  # NOT destroyed
    assert any("just written" in e for e in report.errors)


def test_recreate_slug_does_not_repoint_inbound_links(tmp_path, monkeypatch):
    """If a slug deleted-with-redirect by one source is RECREATED by a later source in the
    same run, inbound links must keep pointing at the live page, not the stale redirect."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    for rel, title in (("a", "A"), ("b", "B")):
        _seed_page(
            wiki, f"concepts/{rel}.md",
            {"type": "Concept", "title": title, "resource": "raw/old.md"},
            f"{title} page.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/old.md](../../raw/old.md) - o (ingested 2026-06-21)\n",
        )
    _seed_page(
        wiki, "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "resource": "raw/old.md"},
        "See [A](./a.md).[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - o (ingested 2026-06-21)\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "s1.md").write_text("delete a redirect b\n", encoding="utf-8")
    (raw / "s2.md").write_text("recreate a\n", encoding="utf-8")

    def fake(raw_name, raw_text, digest):
        if raw_name.endswith("s1.md"):
            return [{"op": "delete", "rel_path": "concepts/a.md", "redirect": "concepts/b.md"}]
        return [{
            "op": "write", "type": "Concept", "title": "A", "rel_path": "concepts/a.md",
            "description": "new", "tags": [],
            "body": "New A.[^s1]\n\n## Sources\n\n"
                    "[^s1]: [raw/s2.md](../../raw/s2.md) - n (ingested 2026-06-22)\n",
        }]

    monkeypatch.setattr(ingest.llm, "plan_pages", fake)
    report = ingest.ingest([str(raw / "s1.md"), str(raw / "s2.md")])

    assert "concepts/a.md" in report.pages_deleted   # s1 removed it
    assert "concepts/a.md" in report.pages_written   # s2 recreated it
    assert (wiki / "concepts" / "a.md").exists()
    linker = (wiki / "concepts" / "linker.md").read_text(encoding="utf-8")
    assert "](./a.md)" in linker          # link NOT repointed to b.md
    assert report.broken_links == []


def test_rewrite_links_skips_code_fences_and_substrings():
    """The link rewrite touches only genuine link spans: a literal ](old) inside a fenced
    code block is left intact, and only the real cross-link is repointed."""
    body = (
        "See [Old](./old.md) for details.\n\n"
        "```\n"
        "documented syntax: [X](./old.md)\n"
        "```\n\n"
        "End.\n"
    )
    out = store._rewrite_body_links(
        "concepts/page.md", body, {"concepts/old.md": "concepts/new.md"}
    )
    assert "[Old](new.md)" in out          # real link repointed
    assert "[X](./old.md)" in out          # fenced literal left intact
    assert out.count("(new.md)") == 1


def test_lint_allows_and_surfaces_llm_sourced_fact(tmp_path, monkeypatch):
    """A model-supplied [^llmN] fact is NOT flagged as fabricated, but IS surfaced under
    llm_facts for transparency; the page still passes lint."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/with-llm.md",
        {"type": "Concept", "title": "With LLM", "resource": "raw/real.md"},
        "An essential, high-confidence model fact.[^llm1]\n\n## Sources\n\n"
        "[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-22)\n",
    )
    report = lint.lint()
    assert report.bad_sources == []
    assert "concepts/with-llm.md" in report.llm_facts
    assert report.ok()


def test_lint_flags_bare_and_undefined_sources(tmp_path, monkeypatch):
    """A bare-path (un-linked) source def and a used-but-undefined marker are both flagged."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/sloppy.md",
        {"type": "Concept", "title": "Sloppy", "resource": "raw/x.md"},
        "Fact one.[^s1] Fact two.[^s2]\n\n## Sources\n\n"
        "[^s1]: raw/x.md (ingested 2026-06-22)\n",  # bare path, no markdown link; s2 undefined
    )
    report = lint.lint()
    details = [t for r, t in report.bad_sources if r == "concepts/sloppy.md"]
    assert any("no resolvable source link" in d for d in details)
    assert any("[^s2] used but undefined" in d for d in details)
    assert not report.ok()


def test_lint_tolerates_link_title_and_code_fences(tmp_path, monkeypatch):
    """A link title in a Sources def, and an example def inside a code fence, do not cause
    false-positive fabricated-source failures."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "x.md").write_text("src\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/titled.md",
        {"type": "Concept", "title": "Titled", "resource": "raw/x.md"},
        'A fact.[^s1]\n\n'
        '```\n'
        '[^sN]: [raw/example.md](../../raw/example.md) - how to cite\n'
        '```\n\n'
        '## Sources\n\n'
        '[^s1]: [raw/x.md](../../raw/x.md "the title") - note (ingested 2026-06-22)\n',
    )
    report = lint.lint()
    assert report.bad_sources == []
    assert report.ok()


# --- OKF compliance + tags + backlinks + suggested-links --------------------------------


def test_indexes_have_no_frontmatter(tmp_path, monkeypatch):
    """OKF: index.md (top + per-folder) must NOT carry YAML frontmatter."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"]},
        "Alpha body.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    store.rebuild_indexes()
    top = (wiki / "index.md").read_text(encoding="utf-8")
    folder = (wiki / "concepts" / "index.md").read_text(encoding="utf-8")
    assert top.startswith("# Wiki Index") and not top.startswith("---")
    assert "type: Index" not in top
    assert folder.startswith("# concepts") and not folder.startswith("---")
    # tags surfaced as a section in the reserved index.md (no rogue tags.md)
    assert "## Tags" in top and "### x (1)" in top
    assert not (wiki / "tags.md").exists()


def test_index_shows_backlinks(tmp_path, monkeypatch):
    """The top index lists who references each page (the backlink graph)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/a.md", {"type": "Concept", "title": "Alpha", "resource": "raw/a.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    _seed_page(
        wiki, "concepts/b.md", {"type": "Concept", "title": "Beta", "resource": "raw/a.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    store.rebuild_indexes()
    top = (wiki / "index.md").read_text(encoding="utf-8")
    assert "referenced by:" in top
    assert "[Beta](concepts/b.md)" in top


def test_log_is_frontmatter_free_with_date_headings(tmp_path, monkeypatch):
    """OKF: log.md has no frontmatter and groups entries under ## YYYY-MM-DD headings."""
    import re as _re

    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    store.append_log("did a thing")
    log = (wiki / "log.md").read_text(encoding="utf-8")
    assert log.startswith("# Log") and not log.startswith("---")
    assert "type: Log" not in log
    assert _re.search(r"(?m)^## \d{4}-\d{2}-\d{2}$", log)
    assert "did a thing" in log


def test_tag_catalog_and_suggested_links(tmp_path, monkeypatch):
    """tag_catalog groups pages by tag; lint suggests an un-linked mention (advisory)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("src\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "tags": ["brewing", "coffee"], "resource": "raw/a.md"},
        "Espresso is pressure brewing.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    _seed_page(
        wiki, "concepts/caffeine.md",
        {"type": "Concept", "title": "Caffeine", "tags": ["coffee"], "resource": "raw/a.md"},
        "Espresso carries caffeine.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    catalog = store.tag_catalog()
    assert set(catalog) == {"brewing", "coffee"}
    assert {p.rel_path for p in catalog["coffee"]} == {
        "concepts/espresso.md", "concepts/caffeine.md"
    }

    report = lint.lint()
    assert (
        "concepts/caffeine.md",
        "concepts/espresso.md (mentions 'Espresso')",
    ) in report.suggested_links
    assert report.ok()  # advisory only


def test_suggested_links_skips_already_linked(tmp_path, monkeypatch):
    """A page that already links a concept is not nagged to link it again."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/espresso.md", {"type": "Concept", "title": "Espresso", "resource": "raw/a.md"},
        "Espresso.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    _seed_page(
        wiki, "concepts/caffeine.md", {"type": "Concept", "title": "Caffeine", "resource": "raw/a.md"},
        "See [Espresso](./espresso.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    report = lint.lint()
    caffeine_suggestions = [t for r, t in report.suggested_links if r == "concepts/caffeine.md"]
    assert not any("espresso.md" in s for s in caffeine_suggestions)


# --- ingest progress reporting ---------------------------------------------------------


def test_ingest_emits_progress_events(tmp_path, monkeypatch):
    """ingest() drives a progress callback: start -> source_start/done -> finalize -> done."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "plan_pages", fake_plan_pages)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    events = []
    ingest.ingest(progress=lambda ev, data: events.append((ev, data)))

    names = [e for e, _ in events]
    assert names[0] == "start"
    for expected in ("source_start", "source_done", "finalize", "done"):
        assert expected in names, f"missing event: {expected}"
    start = next(d for e, d in events if e == "start")
    assert start == {"pending": 1, "skipped": 0}
    done = next(d for e, d in events if e == "source_done")
    assert done["source"] == "raw/notes.md"
    assert done["index"] == 1 and done["total"] == 1
    assert done["created"] == 1 and done["updated"] == 0
    assert "seconds" in done


def test_ingest_progress_default_is_silent(tmp_path, monkeypatch):
    """No progress arg -> no callback invoked (MCP/non-interactive path stays quiet)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "plan_pages", fake_plan_pages)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")
    report = ingest.ingest()  # must not raise without a progress callback
    assert "raw/notes.md" in report.processed


def test_console_progress_renders_ascii_without_tty():
    """ConsoleProgress on a non-TTY stream prints one plain line per file, ASCII-only."""
    import io
    from okf_wiki.progress import ConsoleProgress

    buf = io.StringIO()  # isatty() -> False, so no spinner thread
    p = ConsoleProgress(stream=buf)
    p("start", {"pending": 2, "skipped": 1})
    p("source_start", {"index": 1, "total": 2, "source": "raw/a.md"})
    p("source_done", {"index": 1, "total": 2, "source": "raw/a.md",
                      "created": 2, "updated": 1, "deleted": 1, "seconds": 12.4})
    p("source_error", {"index": 2, "total": 2, "source": "raw/b.md",
                       "error": "boom", "seconds": 1.0})
    p("finalize", {})
    out = buf.getvalue()

    assert "Ingesting 2 file(s) (1 already up to date)" in out
    assert "[1/2] OK  raw/a.md" in out and "2 created, 1 updated, 1 deleted" in out
    assert "[2/2] ERR raw/b.md" in out and "boom" in out
    assert "Rebuilding indexes" in out
    out.encode("ascii")  # must be ASCII-only (safe on any Windows code page)


def test_ingest_distinguishes_created_vs_updated(tmp_path, monkeypatch):
    """First ingest of a page is a create; re-ingesting (existing page) is an update."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "plan_pages", fake_plan_pages)

    (raw / "notes.md").write_text("first\n", encoding="utf-8")
    r1 = ingest.ingest()
    assert "concepts/transformer.md" in r1.pages_created
    assert r1.pages_updated == []

    # Change the raw file so it re-ingests; the page now exists -> update, not create.
    (raw / "notes.md").write_text("second, changed\n", encoding="utf-8")
    r2 = ingest.ingest()
    assert "concepts/transformer.md" in r2.pages_updated
    assert r2.pages_created == []
