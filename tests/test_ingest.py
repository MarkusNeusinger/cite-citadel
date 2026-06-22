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

    # Page is the rel_path that ingest reported.
    assert "concepts/transformer.md" in report.pages_written

    # index.md regenerated and mentions the new page.
    index_text = (wiki / "index.md").read_text(encoding="utf-8")
    assert "transformer.md" in index_text

    # log.md appended.
    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "ingest" in log_text
    assert "pages written" in log_text

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
