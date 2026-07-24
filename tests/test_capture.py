"""Offline tests for the conversational-capture bridge (``citadel/capture.py``): the append-only
``raw/captures/YYYY-MM.md`` log, its CLI twin (``citadel capture``), the ``wiki_capture`` MCP
tool's never-raises contract, and the hand-off into the normal ingest lifecycle (a captured note
is just a pending raw source)."""

from __future__ import annotations

import io

import pytest

from citadel import capture as capture_mod
from citadel import cli, config, ingest, server


# --- capture() ---------------------------------------------------------------------------


def test_capture_creates_monthly_log_with_header(tmp_citadel):
    res = capture_mod.capture("Prod is on version 12.", source="Kim", topic="prod version")
    assert res.path.parent == tmp_citadel.raw / capture_mod.CAPTURES_SUBDIR
    assert res.path.name.endswith(".md")
    text = res.path.read_text(encoding="utf-8")
    assert text.startswith("# Captured notes")
    assert "From: Kim" in text
    assert "prod version" in text
    assert "Prod is on version 12." in text
    # The key is the canonical workspace-relative source key a citation would use.
    assert res.key == f"raw/captures/{res.path.name}"
    assert res.in_walk


def test_capture_line_range_points_at_the_entry(tmp_citadel):
    """start/end line are the future ``lines A-B`` citation locator — they must bracket exactly
    the appended entry (heading first, text last)."""
    res = capture_mod.capture("Line one.\nLine two.", source="Kim")
    lines = res.path.read_text(encoding="utf-8").splitlines()
    assert lines[res.start_line - 1].startswith("## ")
    assert lines[res.end_line - 1] == "Line two."
    assert "Line one." in lines[res.start_line - 1 : res.end_line]


def test_capture_appends_second_entry_one_header(tmp_citadel):
    first = capture_mod.capture("First note.")
    second = capture_mod.capture("Second note.")
    assert second.path == first.path
    text = second.path.read_text(encoding="utf-8")
    assert text.count("# Captured notes") == 1
    assert text.count("\n## ") == 2
    assert second.start_line > first.end_line
    # The earlier entry's locator range still points at the same content (append-only).
    lines = text.splitlines()
    assert lines[first.end_line - 1] == "First note."


def test_capture_without_source_or_topic(tmp_citadel):
    res = capture_mod.capture("Bare note.")
    text = res.path.read_text(encoding="utf-8")
    assert "From:" not in text
    assert "Bare note." in text
    lines = text.splitlines()
    assert lines[res.start_line - 1].endswith("note")


def test_capture_normalizes_crlf_and_collapses_multiline_args(tmp_citadel):
    res = capture_mod.capture("a\r\nb\rc", source="Kim\nover two lines", topic="t1\nt2")
    text = res.path.read_text(encoding="utf-8")
    assert "\r" not in text
    assert "From: Kim over two lines" in text
    assert "t1 t2" in text
    assert text.splitlines()[res.end_line - 1] == "c"


def test_capture_rejects_empty_text(tmp_citadel):
    with pytest.raises(ValueError, match="empty"):
        capture_mod.capture("   \n\n ")


def test_capture_rejects_oversized_text(tmp_citadel):
    with pytest.raises(ValueError, match="too large"):
        capture_mod.capture("x" * (capture_mod.CAPTURE_MAX_CHARS + 1))


def test_capture_outside_walk_roots_warns(tmp_citadel, monkeypatch):
    """With CITADEL_RAW_DIRS replacing the walk list (primary root not included), the log is
    written but flagged: a default ingest run would never discover it."""
    monkeypatch.setattr(config, "RAW_DIRS", [tmp_citadel.root / "elsewhere"])
    res = capture_mod.capture("Orphaned note.")
    assert res.path.is_file()
    assert not res.in_walk
    assert "no configured raw root" in res.render()


def test_render_names_key_locator_and_ingest(tmp_citadel):
    out = capture_mod.capture("A note.").render()
    assert "Captured to raw/captures/" in out
    assert "lines " in out
    assert "ingest" in out


# --- hand-off into the ingest lifecycle --------------------------------------------------


def test_captured_note_is_an_ordinary_pending_source(tmp_citadel, fake_agent, cite_page):
    """The whole design: capture never touches the wiki; the log is discovered as a pending raw
    source and folded in by a normal ingest session that cites it."""
    res = capture_mod.capture("Citadel uses BM25 ranking.", source="Markus")
    assert not any(tmp_citadel.wiki.rglob("*.md"))  # capture wrote nothing into the wiki
    agent = fake_agent(side_effect=lambda rel_key, *a, **k: cite_page("concepts/search.md", rel_key, "BM25 ranks."))
    report = ingest.ingest()
    assert agent.calls == [(res.key, "ingest")]
    assert not report.errors
    assert res.key in tmp_citadel.read_manifest()


def test_second_capture_reconciles_the_changed_log(tmp_citadel, fake_agent, cite_page):
    """An appended entry changes the log's sha, so the next run runs a RECONCILE session —
    update-don't-append, exactly the changed-source lifecycle."""
    res = capture_mod.capture("First fact.")
    agent = fake_agent(side_effect=lambda rel_key, *a, **k: cite_page("concepts/fact.md", rel_key, "A fact."))
    ingest.ingest()
    capture_mod.capture("Second fact.")
    ingest.ingest()
    assert agent.calls == [(res.key, "ingest"), (res.key, "reconcile")]


# --- CLI twin ----------------------------------------------------------------------------


def test_cli_capture_happy_path(tmp_citadel, capsys):
    rc = cli.main(["capture", "Kim said prod is on 12.", "--from", "Kim", "--topic", "prod"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Captured to raw/captures/" in out
    log = next((tmp_citadel.raw / "captures").glob("*.md"))
    assert "Kim said prod is on 12." in log.read_text(encoding="utf-8")


def test_cli_capture_reads_stdin_dash(tmp_citadel, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("Piped note.\n"))
    rc = cli.main(["capture", "-"])
    assert rc == 0
    log = next((tmp_citadel.raw / "captures").glob("*.md"))
    assert "Piped note." in log.read_text(encoding="utf-8")


def test_cli_capture_empty_text_exits_2(tmp_citadel, capsys):
    rc = cli.main(["capture", "   "])
    assert rc == 2
    assert "error:" in capsys.readouterr().err
    assert not (tmp_citadel.raw / "captures").exists()


# --- wiki_capture MCP tool ---------------------------------------------------------------


def test_wiki_capture_appends_and_reports(tmp_citadel):
    out = server.wiki_capture("Kim said prod is on 12.", source="Kim")
    assert "Captured to raw/captures/" in out
    log = next((tmp_citadel.raw / "captures").glob("*.md"))
    assert "Kim said prod is on 12." in log.read_text(encoding="utf-8")


def test_wiki_capture_empty_text_is_error_string(tmp_citadel):
    out = server.wiki_capture("   ")
    assert out.startswith("error:")
    assert not (tmp_citadel.raw / "captures").exists()


def test_wiki_capture_never_raises(tmp_citadel, monkeypatch):
    def boom(*a, **k):
        raise OSError("disk gone")

    monkeypatch.setattr(capture_mod, "capture", boom)
    out = server.wiki_capture("x")
    assert out.startswith("error: capture failed:")
