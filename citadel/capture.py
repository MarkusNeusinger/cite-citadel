"""Conversational capture — the append-only bridge from a chat into ``raw/``.

``citadel capture`` and the ``wiki_capture`` MCP tool append ONE attributed, dated note to a
monthly capture log under the primary raw root (``raw/captures/YYYY-MM.md``). The log is an
ordinary raw SOURCE: the next ``citadel ingest`` / ``wiki_ingest`` folds the entry into the wiki
through the normal staged, validated lifecycle, citing the log with real ``[^sN]`` line-locator
citations — capture itself NEVER touches the wiki, so every provenance guarantee (staging,
diff-by-hash, the validation gate, reconcile on later appends) applies unchanged.

Design notes:

- **Append-only, monthly rolling.** Entries only ever accumulate; an appended entry changes the
  log's sha, so the manifest sees a CHANGED source and the next run reconciles it (update, don't
  re-append — exactly the designed lifecycle). One file per month keeps any single log small and
  its reconciles cheap, while `lines A-B` locators into it stay stable within a month's file.
- **Attributed claims, not facts.** A captured statement enters the wiki as "X said Y on DATE"
  per the attribution rules (`genres/chat.md` / core.md) — "X said Y" is never flattened into
  "Y is true". The `source` argument is that attribution; entries without one still carry their
  timestamp.
- **Why raw/, not a wiki write.** The audit (docs/audit-2026-07.md § 3.1) requires any write
  surface to stay mediated. Writing an append-only log under ``raw/`` is the strongest form of
  that: the captured text becomes an immutable-once-ingested source with verifiable line
  locators, and the LLM-owned wiki is only ever written by the staged agent lifecycle.

The whole module is offline and deterministic — no LLM, no network.
"""

from __future__ import annotations

import contextlib
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import config, manifest


# Folder under the primary raw root the capture logs land in.
CAPTURES_SUBDIR = "captures"

# Upper bound on one captured note. Capture is for statements worth keeping from a conversation,
# not for bulk import — a whole transcript belongs in raw/ as its OWN file (see docs/capture.md),
# where dedup, chunking, and per-file provenance work as designed. The cap keeps an accidental
# paste-the-world call from bloating a monthly log that every later append re-reconciles.
CAPTURE_MAX_CHARS = 100_000

_HEADER_TITLE = "# Captured notes — "

# The per-log append lock (see :func:`_capture_lock`): how often/long to retry acquiring it, and
# how old (mtime) a leftover lock from a crashed capture may get before it is reclaimed. A capture
# holds the lock for milliseconds, so the retry budget (~5s) resolves any real contention and the
# staleness window (30s) is generous. Module constants so tests can shrink them.
_LOCK_RETRIES = 50
_LOCK_WAIT_S = 0.1
_LOCK_STALE_S = 30.0


@contextmanager
def _capture_lock(log_path: Path):
    """A tiny cross-process mutex around one log's read-modify-write, so two concurrent captures
    (the MCP server and the CLI, say) can never interleave read→append→replace and silently drop
    each other's note (``atomic_write_text`` alone only prevents TORN files, not lost updates).

    Same primitive as ``runlock.py`` — ``O_CREAT | O_EXCL``, atomic on POSIX filesystems, NTFS,
    and SMB shares — but deliberately NOT the workspace run lock: capture only touches ``raw/``
    and must keep working while a long ingest/curate run holds that one. The lockfile is a hidden
    dotfile sibling of the log (``.<log>.lock``), so the discovery walk (which skips dotfiles)
    can never pick a leftover lock up as a source."""
    lock = log_path.with_name(f".{log_path.name}.lock")
    for _ in range(_LOCK_RETRIES):
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            reclaimed = False
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > _LOCK_STALE_S:
                    lock.unlink()
                    reclaimed = True
            if not reclaimed:
                time.sleep(_LOCK_WAIT_S)
    else:
        raise RuntimeError(
            f"could not acquire the capture lock at {lock} - another capture appears stuck; "
            "retry, or delete the lock file if no capture is running"
        )
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


def _header(month: str) -> str:
    """The fixed intro block a fresh monthly log starts with — it tells the ingest agent (and a
    human reader) exactly what kind of source this is: dated, attributed conversational notes."""
    return (
        f"{_HEADER_TITLE}{month}\n"
        "\n"
        "Notes captured from conversations via `citadel capture` / the `wiki_capture` MCP tool.\n"
        "Each entry is a dated statement by its stated speaker — treat every claim as attributed\n"
        '("X said Y"), not as established fact. `citadel ingest` folds entries into the wiki,\n'
        "citing this file.\n"
    )


def _one_line(value: str) -> str:
    """Collapse a (possibly multi-line) heading/attribution argument to one clean line."""
    return " ".join(str(value).split())


@dataclass(frozen=True)
class CaptureResult:
    """What one capture appended and where — enough for the caller to cite or ingest it."""

    path: Path  # absolute path of the capture log
    key: str  # canonical source key (config.rel_or_abs_posix) — what a citation uses
    start_line: int  # first line of the appended entry (1-based, the future locator range)
    end_line: int  # last line of the appended entry
    in_walk: bool  # whether a configured raw root covers the log (discovery will find it)

    def render(self) -> str:
        """The human/MCP-facing confirmation (ASCII-only, like all console output)."""
        lines = [
            f"Captured to {self.key} (lines {self.start_line}-{self.end_line}).",
            "Run `citadel ingest` (or the wiki_ingest MCP tool) to fold it into the wiki.",
        ]
        if not self.in_walk:
            lines.append(
                f"note: {self.key} lies under no configured raw root (CITADEL_RAW_DIRS), so a "
                f"default ingest run will not discover it - ingest it explicitly: "
                f"`citadel ingest {self.key}`."
            )
        return "\n".join(lines) + "\n"


def capture(text: str, source: str = "", topic: str = "") -> CaptureResult:
    """Append one note to this month's capture log and return where it landed.

    ``text`` is the statement to keep (newlines allowed; CRLF normalized); ``source`` attributes
    it (who said it / where it came from — e.g. ``"Kim, chat with Claude"``); ``topic`` is an
    optional heading hint. Raises :class:`ValueError` on an empty or oversized text — the two
    caller mistakes worth refusing loudly (an MCP client that miscomputed its argument must not
    silently write an empty entry, nor dump a whole transcript into the log).

    The read-modify-write runs under a per-log cross-process lock (:func:`_capture_lock`), so two
    concurrent captures serialize instead of one silently overwriting the other's note, and the
    write itself is atomic (``config.atomic_write_text``), so a concurrent reader — including an
    ingest run's discovery walk — never sees a torn log; the appended entry is picked up as a
    new/changed source on the NEXT run either way.
    """
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if not normalized.strip():
        raise ValueError("nothing to capture: the text is empty")
    if len(normalized) > CAPTURE_MAX_CHARS:
        raise ValueError(
            f"capture text is too large ({len(normalized)} chars > {CAPTURE_MAX_CHARS}): "
            "save it as its own file under raw/ instead (see docs/capture.md) - capture is for "
            "single notes, ingest handles whole transcripts"
        )

    stamp = manifest.now_iso()  # the ingested_at stamp format — one grammar for all timestamps
    month = stamp[:7]
    path = Path(config.RAW_DIR) / CAPTURES_SUBDIR / f"{month}.md"
    config.robust_mkdir(path.parent)

    heading = f"## {stamp} — {_one_line(topic) or 'note'}"
    entry_lines = [heading, ""]
    attribution = _one_line(source)
    if attribution:
        entry_lines += [f"From: {attribution}", ""]
    entry_lines += normalized.split("\n")

    with _capture_lock(path):
        try:
            existing = path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            existing = _header(month)
        # Normalize the tail to exactly one blank separator line, so entries stay uniformly
        # spaced no matter how the previous write ended (hand edits included).
        base = existing.rstrip("\n") + "\n\n"
        start_line = base.count("\n") + 1
        end_line = start_line + len(entry_lines) - 1
        config.atomic_write_text(path, base + "\n".join(entry_lines) + "\n")

    return CaptureResult(
        path=path,
        key=config.rel_or_abs_posix(path),
        start_line=start_line,
        end_line=end_line,
        in_walk=config.root_covering(path) is not None,
    )
