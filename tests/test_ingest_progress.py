"""Ingest progress reporting (offline): the optional progress callback ingest() drives, and the
ASCII-only console renderer. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

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
