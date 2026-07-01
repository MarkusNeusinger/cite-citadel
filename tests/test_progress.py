"""Tests for the ingest progress reporter's spinner line and its short source-key display.

A long source path (e.g. one on a mounted network drive) used to wrap the terminal: the spinner
line is rewritten in place with a leading ``\\r``, but a wrapped line spans several physical rows
and ``\\r`` only returns to the start of the LAST one — so every 0.1s repaint left the earlier
rows on screen and the path appeared printed over and over. The fix clips the rewritten spinner
line to a single terminal row, AND the source is now shown by its short key (the long prefix before
the ``raw/`` folder is dropped) so a network path stays on one line and names the in-flight file.

No real TTY is involved — output goes to an in-memory stream and the terminal width is
monkeypatched, so the tests are deterministic. The example paths below are fictional.
"""

from __future__ import annotations

import io
from pathlib import Path

from citadel import config, progress


# A long, fictional out-of-repo source key, of the shape that wrapped the terminal.
_LONG_KEY = "//fileserver/share/projects/data/wiki/raw/sub/EXAMPLE_LONG_DOCUMENT.md"
# The raw/ folder that key lives under (a network drive), and the short form the console should show:
# the long prefix before raw/ is dropped, leaving just the path from the raw folder down.
_LONG_KEY_RAW_DIR = "//fileserver/share/projects/data/wiki/raw"
_LONG_KEY_SHORT = "raw/sub/EXAMPLE_LONG_DOCUMENT.md"


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


# --- an out-of-repo source key is shortened for the console (the long network prefix is dropped) --


def test_display_key_drops_prefix_before_raw(monkeypatch):
    """An absolute out-of-repo key under RAW_DIR collapses to ``raw/<below>`` — the whole
    network-drive prefix before the raw folder is dropped."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    assert config.display_key(_LONG_KEY) == _LONG_KEY_SHORT


def test_display_key_leaves_in_repo_key_unchanged(monkeypatch):
    """A repo-relative key is already short — it is returned verbatim (never resolved against the
    CWD, and never mistaken for a child of RAW_DIR)."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    assert config.display_key("raw/notes.md") == "raw/notes.md"


def test_display_key_leaves_unrelated_absolute_key_unchanged(monkeypatch):
    """An absolute key that is NOT under RAW_DIR/DOCS_DIR is left as-is — we only strip a KNOWN
    prefix, never guess one."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    monkeypatch.setattr(config, "DOCS_DIR", Path("//fileserver/share/projects/data/wiki/docs"))
    assert config.display_key("//other/place/file.txt") == "//other/place/file.txt"


def test_completion_line_shows_short_path(monkeypatch):
    """The per-file START and completion lines show the SHORT key (prefix before raw/ dropped), not
    the long network path. A StringIO is not a TTY, so no spinner thread runs — the source is
    announced up front (so you see which file is in flight) and again on completion."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    stream = io.StringIO()
    prog = progress.ConsoleProgress(stream=stream)
    assert prog.tty is False

    prog("source_start", {"index": 3, "total": 88, "source": _LONG_KEY})
    prog(
        "source_done",
        {"index": 3, "total": 88, "source": _LONG_KEY, "created": 1, "updated": 0, "deleted": 0, "seconds": 751.3},
    )

    out = stream.getvalue()
    assert _LONG_KEY_SHORT in out  # short key on both the start and the completion line
    assert "//fileserver" not in out  # the long network prefix is gone
    assert "[3/88] raw/sub/EXAMPLE_LONG_DOCUMENT.md ..." in out  # up-front start line names the file
    assert "[3/88] OK" in out
    assert "1 created" in out


def test_error_line_shows_short_path(monkeypatch):
    """An error line likewise carries the SHORT source key and the error text."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    stream = io.StringIO()
    prog = progress.ConsoleProgress(stream=stream)
    prog("source_error", {"index": 1, "total": 1, "source": _LONG_KEY, "error": "CLI not found", "seconds": 0.2})
    out = stream.getvalue()
    assert _LONG_KEY_SHORT in out
    assert "//fileserver" not in out
    assert "CLI not found" in out
