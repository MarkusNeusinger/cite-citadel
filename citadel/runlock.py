"""Cross-process workspace run lock — one mutating citadel run at a time.

Two concurrent runs on the same workspace are silently destructive at three independent layers:
the stale-staging sweep removes the other run's in-flight staging copy, ``_promote``'s
set-difference prune deletes pages the other run just promoted, and the manifest/failures saves
are last-write-wins (the loser's completed sources get re-ingested, duplicating pages). So
``ingest`` and ``curate`` take ONE exclusive lockfile for the whole run and a second run fails
loud with a message naming the holder.

The lock lives NEXT TO the wiki dir (a sibling dotfile, exactly like the staging copies) so it
guards the same filesystem the staging/promote machinery mutates — including a
``CITADEL_WIKI_DIR`` pointed outside the workspace — and never inside the wiki itself, where the
wikigit history layer would commit it.

Acquisition is ``O_CREAT | O_EXCL`` (atomic on POSIX filesystems, NTFS, and SMB shares). The file
carries pid + host + start time. A leftover lock from a dead run is reclaimed two ways: on the
same host a non-running pid frees it immediately (POSIX only — probing a pid via ``os.kill`` is
unsafe on Windows); anywhere, a lock whose mtime is older than the staleness window frees it.
Long runs keep their mtime fresh via :func:`heartbeat` at every per-source boundary, so the
window only has to outlive ONE agent session, not the whole run.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import time
from contextlib import contextmanager
from pathlib import Path

from . import config


LOCK_NAME = ".citadel_run.lock"


class RunLockError(RuntimeError):
    """Another citadel run holds the workspace lock. Subclasses RuntimeError so the CLI's
    top-level handler and the MCP tools' never-raise wrappers both render it as a friendly
    one-line error instead of a traceback."""


def lock_path() -> Path:
    """The lockfile's location: a dotfile sibling of the wiki dir (read at call time so tests
    can monkeypatch the config layout)."""
    return config.WIKI_DIR.parent / LOCK_NAME


def _stale_after_s() -> float:
    """How old (mtime) a lock may get before it is presumed dead. Heartbeats fire per source,
    so a live run's lock is never older than one agent session — two timeouts plus margin is
    generous, with an hour as the floor. With audio support on, a pending recording may spend a
    whole whisper transcription inside the per-source boundary before its extra heartbeat fires
    (ingest heartbeats again right after transcribing), so the window must also outlive one
    transcription — else a long transcription would let a second run reclaim a LIVE lock."""
    budget = 2.0 * config.LLM_TIMEOUT
    if config.AUDIO_SUPPORT:
        budget = max(budget, float(config.WHISPER_TIMEOUT) + config.LLM_TIMEOUT)
    return max(budget, 3600.0)


def _pid_alive(pid: int) -> bool | None:
    """Whether ``pid`` runs on THIS host: True/False on POSIX, None (unknowable) on Windows —
    ``os.kill`` there cannot probe without side effects, so staleness falls back to mtime."""
    if os.name != "posix":
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OSError, PermissionError):
        return True  # exists but owned by someone else — definitely alive
    return True


def _is_stale(path: Path, holder: dict) -> bool:
    """A lock is reclaimable when its holder is a dead pid on this host, or its mtime fell out
    of the staleness window (covers other hosts, Windows, and unparseable lockfiles)."""
    pid = holder.get("pid")
    if holder.get("host") == socket.gethostname() and isinstance(pid, int):
        alive = _pid_alive(pid)
        if alive is False:
            return True
        # alive True: definitely running; alive None (Windows): fall through to mtime.
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        return False  # vanished or unreadable — let the acquire retry sort it out
    return age > _stale_after_s()


def heartbeat() -> None:
    """Refresh the lock's mtime (best-effort) so a long multi-source run never looks stale.
    Called at every per-source boundary; a failure never breaks the run.

    Only refreshes a lock THIS process still owns (same pid + host guard as the release path):
    if this run stalled past the staleness window and another run legitimately reclaimed the
    lock, bumping the new holder's mtime would mask ITS staleness — so a foreign lock is left
    strictly alone."""
    path = lock_path()
    with contextlib.suppress(OSError, ValueError):
        holder = json.loads(path.read_text(encoding="utf-8"))
        if holder.get("pid") == os.getpid() and holder.get("host") == socket.gethostname():
            os.utime(path)


@contextmanager
def hold(kind: str):
    """Acquire the workspace run lock for the duration of the block; release on the way out.

    Raises :class:`RunLockError` (a RuntimeError) when another live run holds it — naming the
    holder and the lockfile so a user can delete it by hand after a hard crash on Windows,
    where pid staleness cannot be probed."""
    path = lock_path()
    config.robust_mkdir(path.parent)
    payload = {
        "pid": os.getpid(),
        "host": socket.gethostname(),
        "kind": kind,
        "started": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    acquired = False
    for _attempt in range(2):
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder: dict = {}
            with contextlib.suppress(OSError, ValueError):
                holder = json.loads(path.read_text(encoding="utf-8"))
            if _is_stale(path, holder):
                with contextlib.suppress(OSError):
                    path.unlink()
                continue  # reclaimed — retry the exclusive create once
            raise RunLockError(
                f"another citadel {holder.get('kind', 'run')} is already running on this workspace "
                f"(pid {holder.get('pid', '?')} on {holder.get('host', '?')}, "
                f"started {holder.get('started', '?')}) - wait for it to finish, "
                f"or delete {path} if that run is dead"
            ) from None
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        acquired = True
        break
    if not acquired:
        raise RunLockError(f"could not acquire the run lock at {path} - is another run racing this one?")
    try:
        yield
    finally:
        # Only remove a lock that is still OURS — never clobber a lock a later run reclaimed
        # (possible only if this process stalled past the staleness window).
        with contextlib.suppress(OSError, ValueError):
            holder = json.loads(path.read_text(encoding="utf-8"))
            if holder.get("pid") == payload["pid"] and holder.get("host") == payload["host"]:
                path.unlink()
