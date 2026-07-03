"""Ingest progress reporting (offline): the optional progress callback ingest() drives, and the
ASCII-only console renderer. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from conftest import delete_citing_pages

from citadel import ingest


def test_ingest_emits_progress_events(tmp_citadel, fake_agent, transformer_page):
    """ingest() drives a progress callback: start -> source_start/done -> finalize -> done."""
    raw = tmp_citadel.raw
    fake_agent(transformer_page)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    events = []
    ingest.ingest(progress=lambda ev, data: events.append((ev, data)))

    names = [e for e, _ in events]
    assert names[0] == "start"
    for expected in ("source_start", "source_done", "finalize", "done"):
        assert expected in names, f"missing event: {expected}"
    start = next(d for e, d in events if e == "start")
    assert start == {"pending": 1, "skipped": 0, "moved": 0, "unreadable": 0, "deleted": 0, "repos": 0}
    done = next(d for e, d in events if e == "source_done")
    assert done["source"] == "raw/notes.md"
    assert done["index"] == 1 and done["total"] == 1
    assert done["created"] == 1 and done["updated"] == 0
    assert "seconds" in done


def test_mixed_run_progress_vocabulary_and_order_are_pinned(
    repo_wiki, fake_agent, seed_cited_deleted_source, make_repo, cite_page
):
    """SourceJob unification pin (docs/refactor-plan.md Z7): the progress-event vocabulary for a
    MIXED run — one pending file + one repo + one deleted source — is frozen exactly as it is
    today, so collapsing the three per-source loops behind one job loop cannot change what a
    progress consumer sees: the event names, the exact payload keys of every event, and the
    per-GROUP index/total counters that restart at 1 for each source kind.

    The group ORDER is DELETIONS first, then files, then repos (corpus-discovered fix,
    project-history wave 3): a delete cleanup must strip a vanished source's stale provenance
    BEFORE a pending source's session touches a page that still cites it, or that pre-existing
    stale citation fails the pending session's validation (bad_source) and rolls it back
    fruitlessly. The event VOCABULARY is unchanged — only the deliberate order is."""
    raw = repo_wiki.raw
    (raw / "note.md").write_text("a note\n", encoding="utf-8")
    make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})
    # A tracked source that vanished from disk, still cited -> one delete-cleanup session.
    seed_cited_deleted_source()

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if kind == "delete":
            delete_citing_pages(rel_key)
            return
        slug = rel_key.rsplit("/", 1)[-1].replace(".", "-")
        cite_page(f"misc/{slug}.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    events: list[tuple[str, dict]] = []
    ingest.ingest(progress=lambda ev, data: events.append((ev, dict(data))))

    assert [e for e, _ in events] == [
        "start",
        "source_start",
        "source_done",  # the deletion cleanup
        "source_start",
        "source_done",  # the pending file
        "source_start",
        "source_done",  # the repo
        "finalize",
        "done",
    ]
    assert events[0][1] == {"pending": 1, "skipped": 0, "moved": 0, "unreadable": 0, "deleted": 1, "repos": 1}
    # Deletions first, then files, then repos — and per-GROUP counters restarting at 1/1.
    assert [d["source"] for e, d in events if e == "source_start"] == ["raw/gone.md", "raw/note.md", "raw/svc"]
    for event, data in events:
        if event == "source_start":
            assert set(data) == {"index", "total", "source"}
            assert data["index"] == 1 and data["total"] == 1
        elif event == "source_done":
            assert set(data) == {"index", "total", "source", "created", "updated", "deleted", "seconds"}
    done = events[-1][1]
    assert set(done) == {
        "processed",
        "created",
        "updated",
        "deleted",
        "broken",
        "moved",
        "unreadable",
        "sources_deleted",
    }
    assert done["processed"] == 2 and done["sources_deleted"] == 1 and done["broken"] == 0


def test_ingest_progress_default_is_silent(tmp_citadel, fake_agent, transformer_page):
    """No progress arg -> no callback invoked (MCP/non-interactive path stays quiet)."""
    raw = tmp_citadel.raw
    fake_agent(transformer_page)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")
    report = ingest.ingest()  # must not raise without a progress callback
    assert "raw/notes.md" in report.processed


def test_console_progress_renders_ascii_without_tty():
    """ConsoleProgress on a non-TTY stream prints one plain line per file, ASCII-only."""
    import io

    from citadel.progress import ConsoleProgress

    buf = io.StringIO()  # isatty() -> False, so no spinner thread
    p = ConsoleProgress(stream=buf)
    p("start", {"pending": 2, "skipped": 1})
    p("source_start", {"index": 1, "total": 2, "source": "raw/a.md"})
    p(
        "source_done",
        {"index": 1, "total": 2, "source": "raw/a.md", "created": 2, "updated": 1, "deleted": 1, "seconds": 12.4},
    )
    p("source_error", {"index": 2, "total": 2, "source": "raw/b.md", "error": "boom", "seconds": 1.0})
    p("finalize", {})
    out = buf.getvalue()

    assert "Ingesting 2 file(s) (1 already up to date)" in out
    assert "[1/2] OK  raw/a.md" in out and "2 created, 1 updated, 1 deleted" in out
    assert "[2/2] ERR raw/b.md" in out and "boom" in out
    assert "Rebuilding indexes" in out
    out.encode("ascii")  # must be ASCII-only (safe on any Windows code page)
