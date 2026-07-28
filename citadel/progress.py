"""The live console reporter for the ingest CLI, rendered with `rich`.

A slow multi-file ingest (one LLM CLI call per file) has to show how far along it is instead of
looking hung. On a terminal this renders a **live region** at the bottom of the screen — one
spinner row per source that is currently in flight, plus an overall progress bar — while finished
sources scroll away above it as permanent one-line verdicts carrying what the session actually
COST:

    [2/3] OK  raw/notes.md  18.4s  2 created  $0.0123  1.2k in / 456 out  claude-opus-5

Rich owns the terminal handling this module used to do by hand (one-row clipping, in-place
repaint, width detection), which is what makes ``--jobs N`` legible: several sources are in flight
at once and each gets its OWN spinner row, where a single carriage-return-rewritten line could
only ever name one of them.

**Windows safety is preserved deliberately, not by accident.** The spinner is pinned to rich's
ASCII ``line`` spinner (``|/-\\``) and every string this module composes is ASCII-only, so a cp1252
console never sees a glyph it cannot encode; rich's own legacy-console fallbacks cover the bar. On
top of that, every write goes through :meth:`ConsoleProgress._guard` — console output must never
be able to break an ingest, so a rendering/encoding failure is swallowed exactly as the old
hand-rolled writer swallowed it.

Off a TTY (piped / CI) — and whenever the live region is suppressed (``--verbose``, whose streamed
agent transcript would fight the live region for the same stderr) — it degrades to a plain START
line per source followed by that source's verdict line, so you can always see WHICH file the
session is working on right now.

Every source is shown by its **short** key (``citadel.config.display_key``): the long prefix before
the ``raw/`` folder that an out-of-repo source on a mounted network drive carries is dropped, so
``//fileserver/.../raw/sub/notes.pdf`` prints as ``raw/sub/notes.pdf``. The full canonical key is
still what the final report and the manifest record.

Wired in only by the CLI (``cmd_ingest`` / ``cmd_refresh``); the MCP server passes no progress, so
its stdio stays clean. Drive it by calling the instance: ``progress(event, data_dict)``.
"""

from __future__ import annotations

import sys
import threading

from rich.console import Console, Group
from rich.live import Live
from rich.progress import BarColumn, MofNCompleteColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Column
from rich.text import Text

from . import config


# rich's ASCII spinner: the exact ``|/-\`` frames this module animated by hand before, chosen so a
# Windows console on a legacy code page can always encode the live region.
_SPINNER = "line"


def format_tokens(count) -> str:
    """A compact ASCII token count for a one-line verdict: ``456`` / ``1.2k`` / ``534k`` / ``1.2M``.

    The exact figures stay in the run report, ``citadel status`` and the manifest; this is the
    at-a-glance form, so it trades precision for staying inside one terminal row. Never raises on a
    weird value — it renders console output, which must not be able to fail a run."""
    try:
        n = int(count)
    except (TypeError, ValueError):
        return "?"
    if n < 1000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1000:.1f}k".replace(".0k", "k")
    return f"{n / 1_000_000:.1f}M".replace(".0M", "M")


# The columns a verdict line always reserves for the source key, however long the tail gets. Below
# this the line would name no file at all, which is worse than letting the tail's right-hand end be
# trimmed — so this is the floor of the priority order "filename > spend > the rest of the path".
_MIN_KEY_COLS = 24


def _shorten(text: str, budget: int) -> str:
    """``text`` clipped from the LEFT to ``budget`` columns, marked with an ASCII ``...``.

    Clipping from the left keeps the filename — the identifying end of a path — which is the
    opposite of rich's right-hand ellipsis overflow. ``budget`` is whatever the fixed parts of a
    verdict line left over, so it can legitimately go non-positive on a very narrow terminal; the
    result then degrades to the ellipsis alone rather than blowing the one-row invariant."""
    if len(text) <= budget:
        return text
    if budget <= 3:
        return "..."[: max(0, budget)]
    return "..." + text[-(budget - 3) :]


def usage_bits(usage, model: str | None) -> list[tuple[str, str]]:
    """The ``(text, style)`` fragments describing what one source's session spent — cost, tokens,
    AI credits, and the model that actually ran.

    Only fields the backend genuinely REPORTED appear (an unknown side is omitted, never rendered
    as a ``0`` that reads like a real count), so a backend that prices itself and one that only
    counts tokens each say exactly what they know. ``llm`` is imported lazily to keep this module
    importable without pulling the LLM layer in."""
    from . import llm

    bits: list[tuple[str, str]] = []
    if usage is not None:
        cost = getattr(usage, "cost_usd", None)
        if cost is not None:
            bits.append((llm.format_cost(cost), "green"))
        tokens = [
            f"{format_tokens(count)} {label}"
            for count, label in (
                (getattr(usage, "input_tokens", None), "in"),
                (getattr(usage, "output_tokens", None), "out"),
            )
            if count is not None
        ]
        if tokens:
            bits.append((" / ".join(tokens), "cyan"))
        aic = getattr(usage, "aic", None)
        if aic is not None:
            bits.append((f"{llm.format_aic(aic)} AIC", "cyan"))
    if model:
        bits.append((str(model), "magenta"))
    return bits


class ConsoleProgress:
    """Render ``ingest`` progress events to a stream (default ``sys.stderr``, so stdout keeps the
    final report).

    ``spinner=False`` turns the live region off while keeping every printed line — that is the
    ``--verbose`` mode, where the agent transcript streams to the same stream."""

    def __init__(self, stream=None, spinner=True):
        self.stream = stream if stream is not None else sys.stderr
        self.spinner = spinner
        # `highlight=False` keeps rich from re-coloring numbers and paths inside our own text, and
        # everything is passed as a `Text` object rather than markup (`markup=False`) so a source
        # path containing `[...]` can never be swallowed as a markup tag.
        self.console = Console(file=self.stream, highlight=False, markup=False, soft_wrap=False)
        try:
            self.tty = bool(self.stream.isatty())
        except Exception:  # noqa: BLE001
            self.tty = False
        self._lock = threading.RLock()
        self._live: Live | None = None
        self._sources: Progress | None = None
        self._overall: Progress | None = None
        self._overall_task = None
        self._tasks: dict[str, object] = {}

    # ``progress(event, data)`` entry point -> dispatch to on_<event>.
    def __call__(self, event: str, data: dict) -> None:
        getattr(self, "on_" + event, self._ignore)(**data)

    def _ignore(self, **_) -> None:
        pass

    @property
    def live_mode(self) -> bool:
        """Whether the animated live region is in play (a real terminal, and not ``--verbose``)."""
        return self.tty and self.spinner

    # ---- events -------------------------------------------------------------------------

    def on_start(
        self,
        pending: int,
        skipped: int,
        moved: int = 0,
        unreadable: int = 0,
        deleted: int = 0,
        repos: int = 0,
        jobs: int = 1,
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
            self._print(Text(f"Nothing to ingest{extra}.", style="dim"))
            return
        if pending == 0 and repos == 0:
            # Deleted-only run: the headline already names the deleted count, so leave it out of
            # `extra` (otherwise "Reconciling 2 deleted source(s) (2 source(s) deleted)...").
            extra = f" ({', '.join(bits)})" if bits else ""
            self._begin(deleted, Text(f"Reconciling {deleted} deleted source(s){extra}", style="bold"))
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
        headline = Text(f"Ingesting {' + '.join(counts)}{extra}", style="bold")
        if jobs > 1:
            headline.append(f"  [{jobs} at a time]", style="dim")
        self._begin(pending + repos + deleted, headline)

    def on_source_start(self, index: int, total: int, source: str) -> None:
        label = f"[{index}/{total}] {config.display_key(source)}"
        if self.live_mode:
            self._add_task(source, label)
        else:
            # No live region (a non-TTY pipe, or --verbose whose live agent transcript follows):
            # the spinner is what normally names the in-flight source, so without it print an
            # up-front START line — otherwise the streamed session (or the eventual verdict line)
            # gives no clue WHICH file is being worked on right now.
            self._print(Text(f"{label} ...", style="dim"))

    def on_source_done(
        self,
        index: int,
        total: int,
        source: str,
        created: int,
        updated: int,
        deleted: int,
        seconds: float,
        usage=None,
        model: str | None = None,
    ) -> None:
        changes = []
        if created:
            changes.append(f"{created} created")
        if updated:
            changes.append(f"{updated} updated")
        if deleted:
            changes.append(f"{deleted} deleted")
        tail = [(", ".join(changes), "") if changes else ("no changes", "dim")]
        tail.extend(usage_bits(usage, model))
        self._finish(source, self._verdict(index, total, "OK", "bold green", source, seconds, tail))

    def on_source_retry(self, index: int, total: int, source: str, seconds: float) -> None:
        """``--jobs N`` only: this source's session was clean but a CONCURRENT source promoted a
        page it also wrote, so nothing was promoted and it is re-run serially at the end of its
        group (where it merges into what the other source left). Neither an OK nor an ERR — the
        source's real verdict is the re-run's."""
        tail = [("raced another source; re-running serially", "yellow")]
        line = self._verdict(index, total, "RE-RUN", "bold yellow", source, seconds, tail)
        # The re-run emits its own source_start/done pair, so this attempt must NOT advance the
        # overall bar — the source has not reached its real verdict yet.
        self._finish(source, line, advance=False)

    def on_source_error(self, index: int, total: int, source: str, error: str, seconds: float) -> None:
        line = self._verdict(index, total, "ERR", "bold red", source, seconds, [(str(error), "red")])
        self._finish(source, line)

    def on_finalize(self) -> None:
        self._print(Text("Rebuilding indexes...", style="dim"))

    def on_done(self, **_) -> None:
        self._stop()

    # ---- rendering ----------------------------------------------------------------------

    def _verdict(self, index, total, tag: str, style: str, source: str, seconds: float, tail) -> Text:
        """One source's permanent verdict line: ``[2/3] OK  raw/notes.md  18.4s  <tail...>``.

        The line must fit ONE row, so something has to give when it does not. The priority order is
        **filename > spend > the rest of the path**: the key is clipped from the LEFT (its filename
        tail is what identifies it) down to a floor of :data:`_MIN_KEY_COLS`, and only once that
        floor is reached does the tail's right-hand end get trimmed by the printer. Rich's default
        — clip the whole line from the right — would drop the cost and the model first, which is
        exactly backwards: the tail is what the run is judged by and it is the short part."""
        head = Text()
        head.append(f"[{index}/{total}] ", style="dim")
        head.append(tag, style=style)
        head.append("  ")
        rest = Text()
        rest.append(f"  {seconds:.1f}s", style="dim")
        for text, text_style in tail:
            rest.append("  ")
            rest.append(text, style=text_style)
        budget = max(_MIN_KEY_COLS, self._width() - head.cell_len - rest.cell_len)
        head.append(_shorten(config.display_key(source), budget))
        head.append_text(rest)
        return head

    def _width(self) -> int:
        """The console's column count, defensively (a fallback of 80 keeps the layout math sane if
        rich cannot determine a width)."""
        try:
            return int(self.console.width) or 80
        except Exception:  # noqa: BLE001
            return 80

    def _begin(self, total: int, headline: Text) -> None:
        """Print the run headline and, on a terminal, open the live region."""
        self._print(headline)
        if not self.live_mode:
            return

        def build() -> None:
            self._sources = Progress(
                SpinnerColumn(spinner_name=_SPINNER, style="cyan"),
                TextColumn("{task.description}", table_column=Column(no_wrap=True, overflow="ellipsis")),
                TimeElapsedColumn(),
                console=self.console,
            )
            self._overall = Progress(
                TextColumn("Sources", style="dim"),
                BarColumn(complete_style="green", finished_style="green"),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=self.console,
            )
            self._overall_task = self._overall.add_task("", total=max(1, total))
            # `transient` keeps the finished live region from lingering under the final report; the
            # permanent record is the per-source verdict lines printed above it.
            self._live = Live(
                Group(self._sources, self._overall), console=self.console, refresh_per_second=10, transient=True
            )
            self._live.start()

        self._guard(build)

    def _add_task(self, source: str, label: str) -> None:
        def add() -> None:
            if self._sources is None:
                return
            self._tasks[source] = self._sources.add_task(label, total=None)

        with self._lock:
            self._guard(add)

    def _finish(self, source: str, line: Text, advance: bool = True) -> None:
        """Retire the source's live row, print its permanent verdict line above the live region,
        and advance the overall bar."""
        with self._lock:

            def done() -> None:
                task = self._tasks.pop(source, None)
                if task is not None and self._sources is not None:
                    self._sources.remove_task(task)
                if advance and self._overall is not None and self._overall_task is not None:
                    self._overall.advance(self._overall_task)

            self._guard(done)
            self._print(line)

    def _stop(self) -> None:
        with self._lock:
            self._guard(lambda: self._live.stop() if self._live is not None else None)
            self._live = None
            self._sources = None
            self._overall = None
            self._overall_task = None
            self._tasks.clear()

    def _print(self, renderable) -> None:
        """Print one permanent line. While the live region is up, rich renders it ABOVE the region
        so the animated rows stay pinned to the bottom.

        ``no_wrap``/``overflow`` hold the ONE-ROW invariant the hand-rolled writer used to enforce
        by clipping: rich would otherwise WRAP an over-wide line onto extra rows, which is how a
        long absolute source key turns a scrolling ingest into a wall of text."""
        with self._lock:
            self._guard(lambda: self.console.print(renderable, no_wrap=True, overflow="ellipsis", crop=True))

    def _guard(self, fn) -> None:
        """Run a console operation, swallowing anything it raises — console output must never be
        able to break an ingest (an unencodable glyph on a legacy code page, a closed stream, a
        terminal that vanished)."""
        try:
            fn()
        except Exception:  # noqa: BLE001 - output must never break ingest
            pass
