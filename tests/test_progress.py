"""Tests for the ingest progress reporter and its short source-key display.

Two things are guaranteed here, both of which exist because a long absolute source key (an
out-of-repo source on a mounted network drive) used to flood the console during a multi-file
ingest:

1. **The key is shortened** (``citadel.config.display_key``) — the whole prefix before the raw
   folder is dropped, through three fallback tiers so it works even when the configured root and
   the key share no common text (a Windows drive letter mapped to a share).
2. **Every printed line stays on ONE row** — the reporter renders through ``rich``, which would
   otherwise WRAP an over-wide line onto extra rows.

No real TTY is involved — output goes to an in-memory stream (so ``rich`` renders plain,
un-animated text) and the console width is set explicitly, keeping the tests deterministic. The
example paths below are fictional.
"""

from __future__ import annotations

import io
from pathlib import Path

from citadel import config, llm, progress


# A long, fictional out-of-repo source key, of the shape that flooded the terminal.
_LONG_KEY = "//fileserver/share/projects/data/wiki/raw/sub/EXAMPLE_LONG_DOCUMENT.md"
# The raw/ folder that key lives under (a network drive), and the short form the console should show:
# the long prefix before raw/ is dropped, leaving just the path from the raw folder down.
_LONG_KEY_RAW_DIR = "//fileserver/share/projects/data/wiki/raw"
_LONG_KEY_SHORT = "raw/sub/EXAMPLE_LONG_DOCUMENT.md"


def _reporter(stream, width=200, spinner=True):
    """A reporter writing to ``stream`` at a fixed console width (a StringIO is not a TTY, so rich
    renders plain text and no live region is started)."""
    prog = progress.ConsoleProgress(stream=stream, spinner=spinner)
    prog.console.width = width
    return prog


# --- tier 1: an exact prefix match against a configured root ------------------------------


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


# --- tier 2: the mapped-drive case, where prefixes share no common text --------------------


def test_display_key_cuts_at_the_root_folder_name_when_prefixes_disagree(monkeypatch):
    """A Windows drive letter mapped to a share: the root is configured as ``T:/proj/raw`` but the
    key travelled as the UNC path the drive points at. Nothing relates the two textually, so the
    prefix match fails — and the fallback cuts at the last segment NAMED like the root, yielding
    the same short key the matching branch would have."""
    monkeypatch.setattr(config, "RAW_DIR", Path("T:/proj/raw"))
    monkeypatch.setattr(config, "DOCS_DIR", Path("T:/proj/docs"))

    key = "//fileserver.corp.example.internal/proj/raw/sub/notes.pdf"

    assert config.display_key(key) == "raw/sub/notes.pdf"


def test_display_key_cuts_at_the_last_root_named_segment(monkeypatch):
    """When the folder name occurs more than once, the LAST occurrence wins — that is the real
    root, not a same-named directory somewhere up the share."""
    monkeypatch.setattr(config, "RAW_DIR", Path("T:/raw"))
    monkeypatch.setattr(config, "DOCS_DIR", Path("T:/docs"))

    assert config.display_key("//host/raw/archive/raw/notes.md") == "raw/notes.md"


# --- tier 3: an absolute key under no known root at all ------------------------------------


def test_display_key_clips_an_unrecognized_absolute_key(monkeypatch):
    """A long absolute key belonging to NO configured root (a stale manifest entry from an earlier
    layout) still must not flood the console: the identifying tail is kept and the dropped prefix is
    marked with an ASCII ``.../``."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    monkeypatch.setattr(config, "DOCS_DIR", Path("//fileserver/share/projects/data/wiki/docs"))

    short = config.display_key("//other.very.long.host.example/share/dept/2026/archive/file.txt")

    assert short == ".../2026/archive/file.txt"
    assert "other.very.long.host" not in short


def test_display_key_leaves_a_short_absolute_key_unchanged(monkeypatch):
    """Clipping only kicks in past the kept tail length — a short absolute key is left alone, so we
    never mangle something that was already readable."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    monkeypatch.setattr(config, "DOCS_DIR", Path("//fileserver/share/projects/data/wiki/docs"))
    assert config.display_key("//other/place/file.txt") == "//other/place/file.txt"


def test_display_key_always_returns_normalized_str(monkeypatch):
    """Every path returns a normalized ``str`` — backslashes normalized rather than dropped, and a
    non-str (``Path``) input still comes back as a str."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    # A backslash (Windows-style) key not under RAW_DIR is normalized, then clipped.
    assert config.display_key("\\\\host\\share\\other\\file.txt") == ".../share/other/file.txt"
    result = config.display_key(Path("//other/place/file.txt"))
    assert isinstance(result, str)


# --- the printed lines ---------------------------------------------------------------------


def test_completion_line_shows_short_path(monkeypatch):
    """The per-file START and completion lines show the SHORT key (prefix before raw/ dropped), not
    the long network path. A StringIO is not a TTY, so there is no live region — the source is
    announced up front (so you see which file is in flight) and again on completion."""
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    stream = io.StringIO()
    prog = _reporter(stream)
    assert prog.tty is False
    assert prog.live_mode is False

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
    prog = _reporter(stream)
    prog("source_error", {"index": 1, "total": 1, "source": _LONG_KEY, "error": "CLI not found", "seconds": 0.2})
    out = stream.getvalue()
    assert _LONG_KEY_SHORT in out
    assert "//fileserver" not in out
    assert "CLI not found" in out


def test_every_printed_line_stays_on_one_row(monkeypatch):
    """The one-row invariant: rich WRAPS by default, which is exactly how a long key turned a
    scrolling ingest into a wall of text. Lines are printed no-wrap with an ellipsis overflow, so a
    label far wider than the console still occupies a single row."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream, width=40)

    prog("source_error", {"index": 1, "total": 1, "source": "x" * 400, "error": "y" * 400, "seconds": 0.2})

    rows = [ln for ln in stream.getvalue().split("\n") if ln]
    assert len(rows) == 1
    assert len(rows[0]) <= 40


def test_a_narrow_terminal_sacrifices_the_path_not_the_money(monkeypatch):
    """When the verdict does not fit, the SOURCE KEY is what gets clipped — and from the left, so
    the identifying filename survives. Clipping from the right (rich's default) would drop the
    cost/tokens/model at the end of the line, which is the most valuable part of it."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream, width=100)

    prog(
        "source_done",
        {
            "index": 1,
            "total": 1,
            "source": "raw/a/deeply/nested/and/very/long/folder/chain/quarterly-report.pdf",
            "created": 2,
            "updated": 0,
            "deleted": 0,
            "seconds": 18.4,
            "usage": llm.SessionUsage(cost_usd=0.0123, input_tokens=534000, output_tokens=4560),
            "model": "claude-opus-5",
        },
    )

    row = stream.getvalue().strip()
    assert len(row) <= 100
    assert "quarterly-report.pdf" in row  # the identifying tail of the path survived
    assert "raw/a/deeply" not in row  # its head was dropped
    assert "$0.0123" in row and "534k in / 4.6k out" in row and "claude-opus-5" in row


def test_the_key_keeps_a_floor_even_when_the_tail_fills_the_row(monkeypatch):
    """Past the point where clipping the path would buy enough room, the key stops shrinking: a
    verdict that names no file at all is worse than one whose tail is trimmed. The floor is why the
    priority order ends at "filename", not at "spend"."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream, width=60)

    prog(
        "source_done",
        {
            "index": 1,
            "total": 1,
            "source": "raw/a/deeply/nested/and/very/long/folder/chain/quarterly-report.pdf",
            "created": 2,
            "updated": 0,
            "deleted": 0,
            "seconds": 18.4,
            "usage": llm.SessionUsage(cost_usd=0.0123, input_tokens=534000, output_tokens=4560),
            "model": "claude-opus-5",
        },
    )

    rows = [ln for ln in stream.getvalue().split("\n") if ln]
    assert len(rows) == 1
    assert "report.pdf" in rows[0]  # the file is still named


def test_a_pathological_width_still_yields_one_row(monkeypatch):
    """A degenerate console width must not break the layout math — the key degrades to the ellipsis
    (or nothing) rather than pushing the line onto extra rows."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream, width=10)

    prog("source_error", {"index": 1, "total": 1, "source": "raw/" + "x" * 200, "error": "boom", "seconds": 0.2})

    rows = [ln for ln in stream.getvalue().split("\n") if ln]
    assert len(rows) == 1


# --- the money: what the session actually cost, per source ---------------------------------


def test_completion_line_reports_cost_tokens_and_model(monkeypatch):
    """The verdict line carries the session's spend and the model that ACTUALLY ran, so a long
    ingest shows what each source cost as it scrolls past."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream)

    prog(
        "source_done",
        {
            "index": 1,
            "total": 1,
            "source": "raw/notes.md",
            "created": 2,
            "updated": 0,
            "deleted": 0,
            "seconds": 18.4,
            "usage": llm.SessionUsage(cost_usd=0.0123, input_tokens=1234, output_tokens=456),
            "model": "claude-opus-5",
        },
    )

    out = stream.getvalue()
    assert "$0.0123" in out
    assert "1.2k in / 456 out" in out
    assert "claude-opus-5" in out


def test_completion_line_omits_what_the_backend_never_reported(monkeypatch):
    """A backend that reports no cost (or no prompt tokens) renders NOTHING for it — never a ``0``
    or ``$0.00`` that would read like a real, measured figure."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream)

    prog(
        "source_done",
        {
            "index": 1,
            "total": 1,
            "source": "raw/notes.md",
            "created": 1,
            "updated": 0,
            "deleted": 0,
            "seconds": 2.0,
            "usage": llm.SessionUsage(output_tokens=456, aic=2.5083),
            "model": None,
        },
    )

    out = stream.getvalue()
    assert "456 out" in out
    assert "2.5083 AIC" in out
    assert "$" not in out  # no cost was reported
    assert " in " not in out  # no prompt-token count was reported


def test_completion_line_without_usage_is_unchanged(monkeypatch):
    """Usage is optional: an emitter that passes none (or a backend that reported nothing) still
    produces the plain verdict line."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream)

    prog(
        "source_done",
        {"index": 1, "total": 2, "source": "raw/a.md", "created": 0, "updated": 0, "deleted": 0, "seconds": 1.0},
    )

    out = stream.getvalue()
    assert "[1/2] OK" in out
    assert "no changes" in out


# --- a chunked source: which pass is running ----------------------------------------------


def test_segment_event_names_the_pass_off_a_tty(monkeypatch):
    """Off the live region a chunked source's passes get their own lines — the only way to see
    that a source folded in over hours is progressing rather than hung."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream)

    prog("source_start", {"index": 1, "total": 2, "source": "raw/big.pdf"})
    prog("source_segment", {"index": 1, "total": 2, "source": "raw/big.pdf", "part": 3, "parts": 8})
    out = stream.getvalue()

    assert "[1/2] raw/big.pdf  part 3/8" in out
    out.encode("ascii")


def test_completion_line_names_the_pass_count(monkeypatch):
    """The verdict of a chunked source says how many passes it took: the cost on that line is the
    SUM over all of them, which reads very differently once you know it bought eight sessions."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream)

    prog("source_start", {"index": 1, "total": 1, "source": "raw/big.pdf"})
    prog("source_segment", {"index": 1, "total": 1, "source": "raw/big.pdf", "part": 8, "parts": 8})
    prog(
        "source_done",
        {"index": 1, "total": 1, "source": "raw/big.pdf", "created": 2, "updated": 0, "deleted": 0, "seconds": 9.0},
    )

    assert "8 parts" in stream.getvalue()


def test_error_line_says_which_pass_died(monkeypatch):
    """A failed chunked source names the pass it died on — the run bought that many sessions and
    promoted nothing, and (with resume on) the next run continues exactly there."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream)

    prog("source_start", {"index": 1, "total": 1, "source": "raw/big.pdf"})
    prog("source_segment", {"index": 1, "total": 1, "source": "raw/big.pdf", "part": 7, "parts": 8})
    prog(
        "source_error",
        {"index": 1, "total": 1, "source": "raw/big.pdf", "error": "the 'copilot' CLI timed out", "seconds": 9.0},
    )
    out = stream.getvalue()

    assert "ERR" in out and "part 7/8" in out and "timed out" in out


def test_segment_state_does_not_leak_into_the_next_source(monkeypatch):
    """Per-source segment state is dropped with the source's verdict: the NEXT source's line must
    not inherit a pass count from the chunked one before it."""
    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    stream = io.StringIO()
    prog = _reporter(stream)

    prog("source_start", {"index": 1, "total": 2, "source": "raw/big.pdf"})
    prog("source_segment", {"index": 1, "total": 2, "source": "raw/big.pdf", "part": 8, "parts": 8})
    prog(
        "source_done",
        {"index": 1, "total": 2, "source": "raw/big.pdf", "created": 1, "updated": 0, "deleted": 0, "seconds": 1.0},
    )
    prog("source_start", {"index": 2, "total": 2, "source": "raw/small.md"})
    prog(
        "source_done",
        {"index": 2, "total": 2, "source": "raw/small.md", "created": 1, "updated": 0, "deleted": 0, "seconds": 1.0},
    )

    second = [line for line in stream.getvalue().splitlines() if "raw/small.md" in line]
    assert second and all("parts" not in line for line in second)


# --- the paths citadel itself prints -------------------------------------------------------


def test_display_path_is_workspace_relative(monkeypatch, tmp_path):
    """A path citadel writes under the workspace (an LLM transcript) prints RELATIVE to it: on a
    network-drive workspace the absolute form is a ~200-char UNC string announced once per agent
    session, which wraps over several rows and buries the progress display."""
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path)
    log = tmp_path / ".citadel_llm_logs" / "20260818-152715.4240.1.log"
    assert config.display_path(log) == ".citadel_llm_logs/20260818-152715.4240.1.log"


def test_display_path_falls_back_to_the_key_shortening(monkeypatch, tmp_path):
    """A path OUTSIDE the workspace is handed to display_key, so it is collapsed against a raw
    root (or clipped) instead of printed in full."""
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))
    assert config.display_path(_LONG_KEY) == _LONG_KEY_SHORT


def test_display_path_shortens_even_when_resolution_fails(monkeypatch, tmp_path):
    """A path that cannot be resolved at all (a dead mount) is exactly the long absolute one this
    exists to shorten, so it takes the same display_key fallback as a path outside the workspace —
    the error path must not be the one that prints the full UNC string."""
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(config, "RAW_DIR", Path(_LONG_KEY_RAW_DIR))

    real = config._safe_resolve

    def boom(path):
        # Only the WORKSPACE root is unreachable — the raw root still resolves, which is what
        # display_key needs to collapse the key.
        if str(path) == str(tmp_path):
            raise OSError("the mount is gone")
        return real(path)

    monkeypatch.setattr(config, "_safe_resolve", boom)
    assert config.display_path(_LONG_KEY) == _LONG_KEY_SHORT


def test_display_path_never_raises_on_a_relative_or_empty_value(monkeypatch, tmp_path):
    """Display-only: every fallback returns a normalized string rather than blowing up console
    output (a relative path is already short and is passed through)."""
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    assert config.display_path("logs\\a.log") == "logs/a.log"
    assert config.display_path("") == ""


def test_format_tokens_is_compact_and_never_raises():
    """The at-a-glance token form, and its defensive fallback for a value that is not a count."""
    assert progress.format_tokens(456) == "456"
    assert progress.format_tokens(1234) == "1.2k"
    assert progress.format_tokens(534_000) == "534k"
    assert progress.format_tokens(1_200_000) == "1.2M"
    assert progress.format_tokens(None) == "?"


def test_console_output_never_breaks_an_ingest(monkeypatch):
    """A stream that blows up on write must not propagate — console output is cosmetic and can
    never be allowed to fail a run that has already spent real money."""

    class Exploding(io.StringIO):
        def write(self, *_args, **_kwargs):
            raise OSError("terminal vanished")

    monkeypatch.setattr(config, "RAW_DIR", Path("/nowhere"))
    prog = _reporter(Exploding())

    prog("start", {"pending": 1, "skipped": 0})
    prog("source_start", {"index": 1, "total": 1, "source": "raw/a.md"})
    prog(
        "source_done",
        {"index": 1, "total": 1, "source": "raw/a.md", "created": 1, "updated": 0, "deleted": 0, "seconds": 1.0},
    )
    prog("finalize", {})
    prog("done", {})
