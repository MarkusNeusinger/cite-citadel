"""Tests for the ingest progress reporter's spinner line.

A long source path (e.g. one on a mounted network drive) used to wrap the terminal: the spinner
line is rewritten in place with a leading ``\\r``, but a wrapped line spans several physical rows
and ``\\r`` only returns to the start of the LAST one — so every 0.1s repaint left the earlier
rows on screen and the path appeared printed over and over. The fix clips the rewritten spinner
line to a single terminal row; the full, untruncated path still prints on the completion line.

No real TTY is involved — output goes to an in-memory stream and the terminal width is
monkeypatched, so the tests are deterministic. The example paths below are fictional.
"""

from __future__ import annotations

import io

from citadel import progress


# A long, fictional out-of-repo source key, of the shape that wrapped the terminal.
_LONG_KEY = "//fileserver/share/projects/data/wiki/raw/sub/EXAMPLE_LONG_DOCUMENT.md"


# --- the spinner line is clipped to one row (the "printed over and over" bug) ------------


def test_paint_clips_to_terminal_width(monkeypatch):
    """A spinner repaint is clipped to one row (width - 1), with an ASCII ellipsis — so it cannot
    wrap and leave earlier rows behind on each carriage-return rewrite."""
    stream = io.StringIO()
    prog = progress.ConsoleProgress(stream=stream)
    monkeypatch.setattr(prog, "_term_width", lambda: 40)

    prog._paint("x" * 200)

    frame = stream.getvalue().split("\r")[-1]
    assert len(frame) <= 39
    assert frame.endswith("...")
    assert "\n" not in frame  # single row, no wrap


def test_paint_holds_one_row_invariant_for_degenerate_widths(monkeypatch):
    """A misreported / pathological terminal width (0 or 1 columns) must still clip to a single row
    — it clips to empty rather than falling through and emitting the full, wrap-prone line."""
    for width in (0, 1):
        stream = io.StringIO()
        prog = progress.ConsoleProgress(stream=stream)
        monkeypatch.setattr(prog, "_term_width", lambda w=width: w)

        prog._paint("x" * 200)

        frame = stream.getvalue().split("\r")[-1].rstrip(" ")
        assert frame == ""  # nothing that could wrap
        assert "\n" not in stream.getvalue()


def test_short_line_is_not_clipped(monkeypatch):
    """A line that already fits is left exactly as-is (no spurious ellipsis)."""
    stream = io.StringIO()
    prog = progress.ConsoleProgress(stream=stream)
    monkeypatch.setattr(prog, "_term_width", lambda: 80)

    prog._paint("[3/88] raw/notes.md  |  10.0s")

    frame = stream.getvalue().split("\r")[-1]
    assert frame == "[3/88] raw/notes.md  |  10.0s"


def test_repeated_paint_overwrites_instead_of_stacking(monkeypatch):
    """Successive repaints of a long label each start with a carriage return and stay within the
    width, so the output is a sequence of overwriting frames — never a growing pile of full lines."""
    stream = io.StringIO()
    prog = progress.ConsoleProgress(stream=stream)
    monkeypatch.setattr(prog, "_term_width", lambda: 50)

    for _ in range(5):
        prog._paint(f"[3/88] {_LONG_KEY}  |  10.0s")  # the long label, as the spinner would build

    out = stream.getvalue()
    assert out.count("\r") == 5  # one overwriting frame per repaint
    for frame in out.split("\r")[1:]:
        assert len(frame) <= 49  # every frame fits one row, so none can wrap


# --- the full path still reaches the console (completion line + report) ------------------


def test_completion_line_prints_full_path():
    """The per-file completion line shows the FULL source path (it is written once, terminated by a
    newline — wrapping is fine there, it is never repainted). A StringIO is not a TTY, so no spinner
    thread runs and the output is deterministic."""
    stream = io.StringIO()
    prog = progress.ConsoleProgress(stream=stream)
    assert prog.tty is False

    prog("source_start", {"index": 3, "total": 88, "source": _LONG_KEY})
    prog(
        "source_done",
        {"index": 3, "total": 88, "source": _LONG_KEY, "created": 1, "updated": 0, "deleted": 0, "seconds": 751.3},
    )

    out = stream.getvalue()
    assert _LONG_KEY in out  # full, untruncated path on the completion line
    assert "[3/88] OK" in out
    assert "1 created" in out


def test_error_line_prints_full_path():
    """An error line likewise carries the full source path and the error text."""
    stream = io.StringIO()
    prog = progress.ConsoleProgress(stream=stream)
    prog("source_error", {"index": 1, "total": 1, "source": _LONG_KEY, "error": "CLI not found", "seconds": 0.2})
    out = stream.getvalue()
    assert _LONG_KEY in out
    assert "CLI not found" in out
