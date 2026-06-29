"""A tiny, dependency-free progress reporter for the ingest CLI.

A spinner + per-file status line so a slow multi-file ingest (one LLM CLI call per file)
shows how far along it is instead of looking hung. Deliberately **ASCII-only and ANSI-free**
so it is safe on any Windows console code page — the same cp1252 boxes that hit
``UnicodeDecodeError`` before would choke on braille spinners / box-drawing. On a TTY it
animates a spinner with elapsed time on one rewritten line — **clipped to the terminal width**
so a long source path can never wrap onto extra rows (a wrapped line defeats the ``\r`` rewrite
and stacks a fresh copy of itself on every repaint); on a non-TTY (piped / CI) it degrades to
one plain line per file. The full, untruncated source path is still printed on the per-file
completion line and in the final report. The spinner runs on a daemon thread while the blocking
LLM subprocess call runs on the main thread.

Wired in only by the CLI (``cmd_ingest``); the MCP server passes no progress, so its stdio
stays clean. Drive it by calling the instance: ``progress(event, data_dict)``.
"""

from __future__ import annotations

import itertools
import os
import sys
import threading
import time

_FRAMES = "|/-\\"


class ConsoleProgress:
    """Render ``ingest`` progress events to a stream (default ``sys.stderr``, so stdout
    keeps the final report)."""

    def __init__(self, stream=None):
        self.stream = stream if stream is not None else sys.stderr
        try:
            self.tty = bool(self.stream.isatty())
        except Exception:  # noqa: BLE001
            self.tty = False
        self._stop: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._t0 = 0.0
        self._label = ""
        self._last_len = 0
        self._lock = threading.Lock()

    # ``progress(event, data)`` entry point -> dispatch to on_<event>.
    def __call__(self, event: str, data: dict) -> None:
        getattr(self, "on_" + event, self._ignore)(**data)

    def _ignore(self, **_) -> None:
        pass

    def on_start(
        self, pending: int, skipped: int, moved: int = 0, unreadable: int = 0,
        deleted: int = 0, repos: int = 0
    ) -> None:
        bits = []
        if skipped:
            bits.append(f"{skipped} already up to date")
        if moved:
            bits.append(f"{moved} reorganized")
        if unreadable:
            bits.append(f"{unreadable} unreadable")
        if pending == 0 and repos == 0 and deleted == 0:
            extra = f" ({', '.join(bits)})" if bits else ""
            self._writeln(f"Nothing to ingest{extra}.")
            return
        if pending == 0 and repos == 0:
            # Deleted-only run: the headline already names the deleted count, so leave it out of
            # `extra` (otherwise "Reconciling 2 deleted source(s) (2 source(s) deleted)...").
            extra = f" ({', '.join(bits)})" if bits else ""
            self._writeln(f"Reconciling {deleted} deleted source(s){extra}...")
            return
        # Ingesting run: surface the deleted count as secondary context alongside the counts.
        if deleted:
            bits.append(f"{deleted} source(s) deleted")
        extra = f" ({', '.join(bits)})" if bits else ""
        counts = []
        if pending:
            counts.append(f"{pending} file(s)")
        if repos:
            counts.append(f"{repos} repo(s)")
        self._writeln(f"Ingesting {' + '.join(counts)}{extra}...")

    def on_source_start(self, index: int, total: int, source: str) -> None:
        self._label = f"[{index}/{total}] {source}"
        self._t0 = time.monotonic()
        if self.tty:
            self._start_spinner()

    def on_source_done(
        self, index: int, total: int, source: str,
        created: int, updated: int, deleted: int, seconds: float
    ) -> None:
        self._stop_spinner()
        bits = []
        if created:
            bits.append(f"{created} created")
        if updated:
            bits.append(f"{updated} updated")
        if deleted:
            bits.append(f"{deleted} deleted")
        summary = ", ".join(bits) if bits else "no changes"
        self._finishln(f"[{index}/{total}] OK  {source}  -  {summary}  ({seconds:.1f}s)")

    def on_source_error(
        self, index: int, total: int, source: str, error: str, seconds: float
    ) -> None:
        self._stop_spinner()
        self._finishln(f"[{index}/{total}] ERR {source}  -  {error}  ({seconds:.1f}s)")

    def on_finalize(self) -> None:
        self._writeln("Rebuilding indexes...")

    def on_done(self, **_) -> None:
        pass

    # ---- spinner (daemon thread; only on a TTY) ----
    def _start_spinner(self) -> None:
        self._stop = threading.Event()

        def spin() -> None:
            for ch in itertools.cycle(_FRAMES):
                if self._stop is None or self._stop.is_set():
                    break
                elapsed = time.monotonic() - self._t0
                self._paint(f"{self._label}  {ch}  {elapsed:.1f}s")
                self._stop.wait(0.1)

        self._thread = threading.Thread(target=spin, daemon=True)
        self._thread.start()

    def _stop_spinner(self) -> None:
        if self._stop is not None:
            self._stop.set()
            if self._thread is not None:
                self._thread.join(timeout=0.3)
        self._stop = None
        self._thread = None

    # ---- output helpers (carriage-return rewrite; no ANSI) ----
    def _term_width(self) -> int:
        """Best-effort terminal column count for the output stream (fallback 80). Used to keep the
        rewritten spinner line on ONE physical row."""
        try:
            return os.get_terminal_size(self.stream.fileno()).columns
        except Exception:  # noqa: BLE001 - not a real terminal / no fileno
            return 80

    def _fit(self, text: str) -> str:
        """Clip ``text`` to one terminal row. The spinner line is rewritten in place with a leading
        ``\\r``; if it is wider than the terminal it wraps onto extra rows, and the ``\\r`` only
        returns to the start of the LAST row — so every repaint leaves the earlier rows on screen and
        the line appears printed over and over. Keeping it to ``width - 1`` columns (ASCII-only ``...``
        ellipsis, per this module's no-Unicode rule) guarantees a single, cleanly overwritten row.

        ``keep`` is clamped to ``>= 0`` so a degenerate / misreported width (0 or 1 columns) clips to
        an empty string rather than falling through and emitting the full, wrap-prone line — the
        one-row invariant must hold even then."""
        keep = max(0, self._term_width() - 1)
        if len(text) <= keep:
            return text
        if keep <= 3:
            return text[:keep]
        return text[: keep - 3] + "..."

    def _paint(self, text: str) -> None:
        with self._lock:
            text = self._fit(text)
            pad = max(0, self._last_len - len(text))
            self._raw("\r" + text + " " * pad)
            self._last_len = len(text)

    def _finishln(self, text: str) -> None:
        with self._lock:
            pad = max(0, self._last_len - len(text)) if self.tty else 0
            self._raw(("\r" if self.tty else "") + text + " " * pad + "\n")
            self._last_len = 0

    def _writeln(self, text: str) -> None:
        with self._lock:
            self._raw(text + "\n")

    def _raw(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except Exception:  # noqa: BLE001 - output must never break ingest
            pass
