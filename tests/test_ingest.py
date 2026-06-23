"""Offline integration tests for the agentic ingest (no CLI, no network).

``llm.run_ingest_session`` is monkeypatched to a deterministic fake that WRITES FILES into the
temp wiki (simulating the agent editing the wiki directly). This exercises the real
snapshot/diff/validate-and-restamp/rename-repair/rollback path against ``tmp_path`` — a stronger
integration test than stubbing a return value. All filesystem state is redirected to ``tmp_path``
by monkeypatching ``config.*`` (including ``REPO_ROOT``, which is exactly what the agentic
session's ``cwd`` reads), so no real CLI is ever spawned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from okf_wiki import config, ingest, lint, okf, store, validate


# A counter so tests can assert the fake session runs exactly once per source.
_CALLS: dict[str, int] = {"n": 0}


def _agent_write(rel_path: str, frontmatter: dict, body: str) -> None:
    """Simulate the agent writing a wiki page file directly (no timestamp — the system
    stamps it). Writes canonical OKF via okf.dump into the temp WIKI_DIR."""
    target = config.WIKI_DIR / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def fake_session_transformer(rel_key):
    """Deterministic stand-in for one agentic ingest session: writes a single Concept page
    with a per-fact GFM footnote linking relatively to the raw file + a ## Sources section."""
    _CALLS["n"] += 1
    _agent_write(
        "concepts/transformer.md",
        {
            "type": "Concept",
            "title": "Transformer",
            "description": "self-attention model",
            "tags": ["ml"],
            "resource": "raw/notes.md",
        },
        "Transformers use self-attention.[^s1]\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n",
    )


def fake_session_contradiction(rel_key):
    """A session that writes a page containing a '> [!CONTRADICTION]' callout (type Note -> misc)."""
    _CALLS["n"] += 1
    _agent_write(
        "misc/q3-revenue.md",
        {
            "type": "Note",
            "title": "Q3 Revenue",
            "description": "Conflicting revenue figures.",
            "tags": ["finance"],
            "resource": "raw/a.md",
        },
        "Revenue figures conflict across sources.[^s1][^s2]\n\n"
        "> [!CONTRADICTION]\n"
        "> raw/a.md says revenue grew 12% [^s1]; raw/b.md says it grew 9% [^s2].\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - report a (ingested 2026-06-21)\n"
        "[^s2]: [raw/b.md](../../raw/b.md) - report b (ingested 2026-06-21)\n",
    )


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
    monkeypatch.setattr(config, "AGENT_RULES_PATH", repo / "AGENT_INGEST.md", raising=False)
    monkeypatch.setattr(config, "INDEX_PATH", wiki / "index.md", raising=False)
    monkeypatch.setattr(config, "LOG_PATH", wiki / "log.md", raising=False)
    monkeypatch.setattr(
        config, "MANIFEST_PATH", wiki / ".okf_ingested.json", raising=False
    )
    return wiki, raw


def _seed_page(wiki: Path, rel_path: str, frontmatter: dict, body: str) -> None:
    """Write an OKF page directly under the temp wiki (bypassing ingest)."""
    target = wiki / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


# --- core ingest flow -------------------------------------------------------------------


def test_ingest_creates_pages(tmp_path, monkeypatch):
    """The agent's edits are discovered via the diff, validated + re-stamped, indexed, logged."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

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
    # write_page (the re-stamp) stamps a timestamp into frontmatter.
    assert "timestamp:" in text
    assert "resource: raw/notes.md" in text

    assert "concepts/transformer.md" in report.pages_written
    assert "concepts/transformer.md" in report.pages_created
    assert report.pages_updated == []

    index_text = (wiki / "index.md").read_text(encoding="utf-8")
    assert "transformer.md" in index_text

    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "ingest" in log_text and "created" in log_text and "deleted" in log_text

    import json

    manifest_data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/notes.md" in manifest_data


def test_reingest_is_noop(tmp_path, monkeypatch):
    """Running ingest twice on the same raw file is idempotent: 2nd processes nothing."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    first = ingest.ingest()
    assert first.processed == ["raw/notes.md"]
    assert _CALLS["n"] == 1

    second = ingest.ingest()
    assert second.processed == []
    assert "raw/notes.md" in second.skipped
    assert _CALLS["n"] == 1  # the fake session was NOT run a second time


def test_ingest_distinguishes_created_vs_updated(tmp_path, monkeypatch):
    """First ingest of a page is a create; re-ingesting (existing page) is an update."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("first\n", encoding="utf-8")
    r1 = ingest.ingest()
    assert "concepts/transformer.md" in r1.pages_created
    assert r1.pages_updated == []

    # Change the raw file so it re-ingests; the page now exists -> update, not create.
    (raw / "notes.md").write_text("second, changed\n", encoding="utf-8")
    r2 = ingest.ingest()
    assert "concepts/transformer.md" in r2.pages_updated
    assert r2.pages_created == []


def test_restamp_canonicalizes_and_stamps(tmp_path, monkeypatch):
    """A page the agent wrote without a timestamp comes out with a system-set timestamp."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest()
    assert not report.errors
    text = (wiki / "concepts" / "transformer.md").read_text(encoding="utf-8")
    # Exactly one frontmatter block (open + close), and a stamped timestamp.
    assert text.split("\n").count("---") == 2
    assert text.startswith("---\n")
    assert "timestamp:" in text


def test_embedded_frontmatter_in_body_is_error(tmp_path, monkeypatch):
    """If the agent echoes a second '---' YAML block into the BODY, validation flags it."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key):
        _agent_write(
            "concepts/echoed.md",
            {
                "type": "Concept",
                "title": "Echoed",
                "description": "d",
                "tags": ["x"],
                "resource": "raw/notes.md",
            },
            "---\ntype: Concept\ntitle: Echoed\n---\n\nA fact.[^s1]\n\n"
            "## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert any("embedded_frontmatter" in e for e in report.errors)


def test_ingest_missing_type_rolls_back(tmp_path, monkeypatch):
    """A page the agent wrote with no 'type' fails validation -> the WHOLE source is rolled
    back (all-or-nothing): error collected, source NOT processed, the invalid page is gone,
    and a pre-existing page is left intact."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key):
        _agent_write(
            "concepts/bad.md",
            {"title": "Bad", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert "raw/notes.md" not in report.processed  # rolled back -> not marked done
    assert any("invalid page concepts/bad.md" in e and "type" in e for e in report.errors)
    assert not (wiki / "concepts" / "bad.md").exists()  # rolled back, not left behind
    assert (wiki / "concepts" / "keep.md").exists()  # pre-existing page untouched


def test_missing_required_field_rolls_back(tmp_path, monkeypatch):
    """STRICT: a page missing 'tags' (or any required field) fails the gate and the source
    is rolled back (not marked done)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key):
        _agent_write(
            "concepts/notags.md",
            {"type": "Concept", "title": "No Tags", "description": "d", "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert any("tags" in e for e in report.errors)
    assert "raw/notes.md" not in report.processed
    assert not (wiki / "concepts" / "notags.md").exists()


def test_ingest_no_changes_marks_done(tmp_path, monkeypatch):
    """An agent that changes nothing is still 'processed' (and re-runs skip it)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key):
        _CALLS["n"] += 1  # writes nothing

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("nothing new\n", encoding="utf-8")

    report = ingest.ingest()
    assert "raw/notes.md" in report.processed
    assert report.pages_created == [] and report.pages_updated == [] and report.pages_deleted == []
    assert not report.errors

    second = ingest.ingest()
    assert "raw/notes.md" in second.skipped
    assert _CALLS["n"] == 1


def test_diff_classifies_created_updated_deleted():
    """Unit test of the content-hash diff."""
    before = {"a.md": "h1", "b.md": "h2", "c.md": "h3"}
    after = {"a.md": "h1", "b.md": "CHANGED", "d.md": "h4"}
    created, updated, deleted = ingest._diff(before, after)
    assert created == ["d.md"]
    assert updated == ["b.md"]
    assert deleted == ["c.md"]


def test_reserved_files_excluded_from_diff(tmp_path, monkeypatch):
    """Even if the agent scribbles on a reserved file, it is excluded from the diff and
    regenerated; only real pages are reported."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key):
        _agent_write(
            "concepts/foo.md",
            {"type": "Concept", "title": "Foo", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        (config.WIKI_DIR / "index.md").write_text("GARBAGE the agent should not write\n", encoding="utf-8")

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert "concepts/foo.md" in report.pages_created
    assert "index.md" not in report.pages_created and "index.md" not in report.pages_updated
    # index.md was regenerated by finalize, not left as the agent's garbage.
    assert (wiki / "index.md").read_text(encoding="utf-8").startswith("# Wiki Index")


def test_agent_merge_repoints_inbound_link(tmp_path, monkeypatch):
    """A merge: the agent writes the survivor, deletes the absorbed page, AND repoints the
    inbound link itself (its job). No broken link remains."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("Self-attention merges attention.\n", encoding="utf-8")

    _seed_page(
        wiki, "concepts/attention.md",
        {"type": "Concept", "title": "Attention", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
        "Attention is a mechanism.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )
    _seed_page(
        wiki, "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
        "See [Attention](./attention.md) for details.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )

    def fake(rel_key):
        _agent_write(
            "concepts/self-attention.md",
            {"type": "Concept", "title": "Self-Attention", "description": "merged", "tags": ["ml"], "resource": "raw/notes.md"},
            "Self-attention subsumes attention.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-22)\n",
        )
        (config.WIKI_DIR / "concepts" / "attention.md").unlink()
        # The agent repoints the inbound link itself.
        _agent_write(
            "concepts/linker.md",
            {"type": "Concept", "title": "Linker", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
            "See [Self-Attention](./self-attention.md) for details.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert not report.errors
    assert "concepts/self-attention.md" in report.pages_written
    assert "concepts/attention.md" in report.pages_deleted
    assert not (wiki / "concepts" / "attention.md").exists()
    assert (wiki / "concepts" / "self-attention.md").exists()
    linker = (wiki / "concepts" / "linker.md").read_text(encoding="utf-8")
    assert "self-attention.md" in linker and "(./attention.md)" not in linker
    assert report.broken_links == []
    assert lint.lint().broken_links == []


def test_repair_renames_repoints_after_rename(tmp_path, monkeypatch):
    """A pure rename (delete old + create same-title new) where the agent forgot the inbound
    link: the deterministic Python safety net repoints it via store.rewrite_links."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("rename a\n", encoding="utf-8")

    _seed_page(
        wiki, "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    _seed_page(
        wiki, "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )

    def fake(rel_key):
        # Rename a.md -> aa.md (SAME title 'Alpha'); do NOT touch linker.
        (config.WIKI_DIR / "concepts" / "a.md").unlink()
        _agent_write(
            "concepts/aa.md",
            {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
            "Alpha (renamed).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "concepts/a.md" in report.pages_deleted
    assert "concepts/aa.md" in report.pages_created
    linker = (wiki / "concepts" / "linker.md").read_text(encoding="utf-8")
    assert "aa.md" in linker and "(./a.md)" not in linker
    assert report.broken_links == []


def test_agent_delete_leaves_broken_link_surfaced(tmp_path, monkeypatch):
    """If the agent deletes a page and forgets an inbound link (and it's not a rename the net
    can fix), the broken link is SURFACED in the report and fails lint."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("delete a\n", encoding="utf-8")

    _seed_page(
        wiki, "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    _seed_page(
        wiki, "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )

    def fake(rel_key):
        (config.WIKI_DIR / "concepts" / "a.md").unlink()  # nothing created in its place

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "concepts/a.md" in report.pages_deleted
    assert ("concepts/linker.md", "concepts/a.md") in report.broken_links
    assert lint.lint().broken_links != []


def test_failed_session_rolls_back(tmp_path, monkeypatch):
    """A session that raises after a partial write is rolled back: the wiki returns to its
    pre-source state, the source is NOT marked done, and the error is collected."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key):
        _agent_write(
            "concepts/partial.md",
            {"type": "Concept", "title": "Partial", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "Half-written.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        raise RuntimeError("boom mid-session")

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("boom mid-session" in e for e in report.errors)
    assert not (wiki / "concepts" / "partial.md").exists()  # rolled back
    assert (wiki / "concepts" / "keep.md").exists()  # untouched

    # Source is retried next run (not in the manifest).
    import json

    manifest_path = wiki / ".okf_ingested.json"
    if manifest_path.exists():
        assert "raw/notes.md" not in json.loads(manifest_path.read_text(encoding="utf-8"))


def test_contradiction_marker_preserved(tmp_path, monkeypatch):
    """A contradiction marker the agent wrote survives the validate+restamp and lint flags it."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_contradiction)

    (raw / "a.md").write_text("Revenue grew 12%.\n", encoding="utf-8")
    (raw / "b.md").write_text("Revenue grew 9%.\n", encoding="utf-8")

    report = ingest.ingest()
    assert not report.errors
    assert report.pages_written

    written_rel = report.pages_written[0]
    page = wiki / Path(written_rel)
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "> [!CONTRADICTION]" in text

    lint_report = lint.lint()
    assert written_rel in lint_report.contradictions


# --- progress reporting -----------------------------------------------------------------


def test_ingest_emits_progress_events(tmp_path, monkeypatch):
    """ingest() drives a progress callback: start -> source_start/done -> finalize -> done."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)
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
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)
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


# --- lint / store / okf-compliance (independent of the ingest mechanism) ----------------


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


def test_lint_flags_wikilink(tmp_path, monkeypatch):
    """A [[wiki-style]] link is flagged and flips lint.ok()."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("src\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/wikilinked.md",
        {"type": "Concept", "title": "Wikilinked", "resource": "raw/a.md"},
        "See [[Some Page]] for more.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    report = lint.lint()
    assert ("concepts/wikilinked.md", "Some Page") in report.wikilinks
    assert not report.ok()


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
