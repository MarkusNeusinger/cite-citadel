"""In-memory snapshot cache for the wiki page load — the long-lived READ process's fix for
"every call re-walks and re-parses the whole wiki from disk" (the 2026-07 audit's finding 1.2.6
and the remainder of its § 1.3 retrieval assessment).

The wiki IS the database, and that stays literally true here: nothing is persisted, no index file
is written, and the cache holds only what a plain :func:`citadel.store_core.load` just produced.
What it adds is a **cheap validity test** — one stat-only walk (no file is opened) whose result is
compared against the walk taken when the snapshot was built. At 1000 pages that walk costs ~4 ms
against the ~700 ms the parse costs, so a warm ``wiki_search`` drops from ~1.4 s to ~0.1 s while
still reading the filesystem's own answer to "did anything change?" on every single call.

**Correctness comes first, three times over:**

1. *Bracketed fingerprints.* The snapshot is only stored when the stat walk taken BEFORE the load
   equals the one taken AFTER it. A file rewritten mid-load would otherwise pair old content with
   a new stamp — the one failure mode that could go stale forever.
2. *A settle window.* A snapshot whose newest stamp is younger than :data:`_SETTLE_NS` is not
   stored at all, because a filesystem with coarse timestamps (FAT's 2 s, some SMB/NFS mounts) can
   hide a same-tick rewrite behind an unchanged ``(size, mtime, ctime)``. Freshly written wikis
   therefore keep re-loading — exactly the pre-cache behavior — until they stop changing. The
   window is checked when the snapshot is STORED and never again, and that is sufficient: once a
   stamp is older than the coarsest tick, any later write necessarily lands in a later tick and so
   moves it.
3. *A single slot, keyed by the wiki directory.* Ingest redirects ``config.WIKI_DIR`` at its
   per-source staging copy; a snapshot of one directory can never be served for another, and the
   single slot means the unbounded stream of staging dirs cannot accumulate entries.

On top of that the mutating lifecycles do not consult it at all: :func:`paused` brackets ingest
and curate, so the diff-by-hash machinery that decides what to promote always reads the truth from
disk, and the cache is dropped on both ends of the run.

**Enablement.** Off by default. ``citadel serve`` — the long-lived reader the finding is about —
opts in via :func:`enable`; one-shot CLI commands load once anyway and gain nothing worth the
risk surface. ``CITADEL_PAGE_CACHE`` overrules either way (``1`` = on wherever the cache is
consulted, ``0`` = never, ``auto`` = the per-process opt-in).

:func:`memo` additionally hangs derived, page-shaped values off the live snapshot — used for
search's per-page term-frequency tables, the *other* half of a search call's cost. They die with
the snapshot they were computed from, so an invalidation can never leave a stale index behind.

Cost: one wiki's parsed pages plus (once searched) their term-frequency tables stay resident —
roughly the size of the wiki's text again, on the order of 10-20 MB for a 1000-page wiki. A single
slot, dropped on every invalidation, bounds it to one wiki at a time.
"""

from __future__ import annotations

import functools
import os
import time
from contextlib import contextmanager
from typing import Any, Callable

from . import config


# A snapshot whose newest file stamp is younger than this (relative to the moment it was taken) is
# never stored: within one coarse filesystem timestamp tick, a rewrite of the same byte length is
# invisible to the stat walk. 2 s covers FAT's notorious 2-second mtime granularity, which is the
# worst case among filesystems citadel already hardens for. Clock skew on a network share only ever
# costs the cache (a share whose clock runs ahead simply never settles -> plain uncached loads).
_SETTLE_NS = 2_000_000_000


class _Snapshot:
    """One cached load: the pages, the stat fingerprint they were parsed at, the skip predicate
    that produced the walk, the identity set that guards :func:`memo`, and the derived-value
    memos. Held in a single module-level slot."""

    __slots__ = ("key", "fingerprint", "pages", "skip", "ids", "memos")

    def __init__(self, key: str, fingerprint: tuple, pages: list, skip: Callable[[str], bool]):
        self.key = key
        self.fingerprint = fingerprint
        self.pages = pages
        self.skip = skip
        # id() is only unique among LIVE objects, so membership is checked against the pages this
        # snapshot itself keeps alive; a foreign page never enters the memo and can therefore never
        # collide with a recycled address.
        self.ids = {id(page) for page in pages}
        self.memos: dict[str, dict[int, Any]] = {}


_snapshot: _Snapshot | None = None
_opted_in = False
_pause_depth = 0


def enabled() -> bool:
    """True when the cache may be consulted: never inside :func:`paused`, otherwise
    ``CITADEL_PAGE_CACHE`` (``on``/``off``) or, under its ``auto`` default, whether this process
    opted in with :func:`enable`."""
    if _pause_depth:
        return False
    mode = getattr(config, "PAGE_CACHE", "auto")
    if mode == "off":
        return False
    if mode == "on":
        return True
    return _opted_in


def enable() -> None:
    """Opt this process in (``citadel serve``). No-op under ``CITADEL_PAGE_CACHE=0``, which is
    checked at every consult, not here."""
    global _opted_in
    _opted_in = True


def disable() -> None:
    """Opt this process back out and drop any snapshot."""
    global _opted_in
    _opted_in = False
    invalidate()


def invalidate() -> None:
    """Drop the snapshot (and, with it, every derived memo). Called by the in-process wiki
    mutators and on both ends of :func:`paused`; the stat fingerprint covers everything else."""
    global _snapshot
    _snapshot = None


def reset() -> None:
    """Full reset of the module's process-global state — opt-in flag, pause depth, snapshot.
    For tests, which must not inherit one test's cache state in the next."""
    global _pause_depth
    _pause_depth = 0
    disable()


@contextmanager
def paused():
    """Bracket a run that MUTATES the wiki (ingest, curate): the cache is dropped on entry, never
    consulted inside, and dropped again on exit. The staged lifecycles decide what to promote by
    diffing content hashes of what is on disk — that answer must always come from disk, and no
    speed-up on a path whose unit of work is a multi-minute agent session is worth the risk.
    Re-entrant, so a nested run (curate inside ingest, a future composition) stays paused until the
    outermost one finishes."""
    global _pause_depth
    _pause_depth += 1
    invalidate()
    try:
        yield
    finally:
        _pause_depth -= 1
        invalidate()


def bypass(func):
    """Decorator form of :func:`paused`, worn by the mutating lifecycle entry points
    (``ingest.ingest``, ``curate.curate``) so EVERY caller — CLI, MCP, refresh, a test — gets the
    guarantee by construction rather than by remembering to ask for it."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with paused():
            return func(*args, **kwargs)

    return wrapper


def fingerprint(wiki_dir, skip: Callable[[str], bool]) -> tuple[tuple, int] | None:
    """A stat-only fingerprint of every file :func:`citadel.store_core.load` would parse:
    ``((rel_path, size, mtime_ns, ctime_ns), …)`` sorted by path, plus the newest stamp seen (for
    the settle window). No file is opened. ``ctime_ns`` rides along because on POSIX it also moves
    on a rename/replace that preserves size and mtime.

    ONE iterative ``os.scandir`` walk, like ingest's discovery — a ``DirEntry`` carries the stat
    the directory listing already produced, which on Windows makes this walk nearly free. It
    mirrors :func:`citadel.store_core._load_pages`'s traversal exactly: hidden directories are not
    entered, a symlinked directory is not recursed into (``os.walk``'s ``followlinks=False``
    default), and a symlink TO A FILE is stat'd through to its target, because that is the file
    the load would parse.

    Returns None when the cache is not enabled (so the walk is not even paid for) or when the walk
    hits any OS error — an unreadable or vanishing directory means "cannot vouch for this", which
    must degrade to an uncached load, never to a guess."""
    if not enabled():
        return None
    root = str(wiki_dir)
    entries: list[tuple[str, int, int, int]] = []
    newest = 0
    stack = [root]
    try:
        while stack:
            current = stack.pop()
            with os.scandir(current) as it:
                for entry in it:
                    if entry.name.startswith("."):
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                        continue
                    if not entry.name.endswith(".md") or skip(entry.name) or not entry.is_file():
                        continue
                    st = entry.stat()
                    rel = os.path.relpath(entry.path, root).replace(os.sep, "/")
                    entries.append((rel, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
                    newest = max(newest, st.st_mtime_ns, st.st_ctime_ns)
    except OSError:
        return None
    entries.sort()
    return (tuple(entries), newest)


def get(wiki_dir) -> list | None:
    """The cached pages for ``wiki_dir`` when the wiki is provably unchanged since they were
    parsed, else None (and a stale snapshot is dropped). The returned list is a fresh shallow copy,
    so a caller that sorts/filters/extends it in place cannot corrupt the snapshot — the Page
    objects themselves are shared, which is what makes :func:`memo` hit."""
    snap = _snapshot
    if snap is None or not enabled():
        return None
    if snap.key != str(wiki_dir):
        return None
    current = fingerprint(wiki_dir, snap.skip)
    if current is None or current[0] != snap.fingerprint[0]:
        invalidate()
        return None
    return list(snap.pages)


def put(wiki_dir, pages: list, before: tuple | None, skip: Callable[[str], bool]) -> None:
    """Store a just-completed load as the snapshot — but only when it can be vouched for: caching
    must be enabled, the pre-load fingerprint (``before``, None when it was not taken) must equal a
    freshly taken post-load one, and that fingerprint must have SETTLED (see :data:`_SETTLE_NS`).
    Anything else leaves the cache empty, which is simply the uncached behavior."""
    global _snapshot
    if before is None or not enabled():
        return
    after = fingerprint(wiki_dir, skip)
    if after is None or after != before:
        return
    if time.time_ns() - after[1] < _SETTLE_NS:
        return
    # The snapshot keeps its OWN list: the caller was handed this one on the miss path, and a
    # caller that sorts or clears it (:func:`get` hands out copies for exactly that reason) must
    # not be able to corrupt what the next reader is served.
    _snapshot = _Snapshot(str(wiki_dir), after, list(pages), skip)


def memo(page, key: str, factory: Callable[[], Any]) -> Any:
    """A derived value for ``page``, computed once per snapshot (search's per-page term-frequency
    tables). Uncached — a plain ``factory()`` call — whenever the cache is off or the page is not
    part of the live snapshot, so the value is never shared with a page the cache does not hold
    alive. Values are handed out by reference and must be treated as read-only by callers."""
    snap = _snapshot
    if snap is None or not enabled() or id(page) not in snap.ids:
        return factory()
    slot = snap.memos.setdefault(key, {})
    pid = id(page)
    if pid not in slot:
        slot[pid] = factory()
    return slot[pid]
