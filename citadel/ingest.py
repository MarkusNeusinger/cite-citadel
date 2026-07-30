"""Orchestrate one ingest run: drive an agentic CLI, then re-impose the invariants.

For each pending source the agent (``llm.run_ingest_session``) reads the raw file, searches
the wiki, and **edits the wiki page files directly** — there is no ops JSON to apply. This
module does the deterministic work around that autonomy:

- run the agent against a **per-source staging copy** of the wiki (a sibling directory), so the
  **live wiki is never the agent's scratch space**: a clean source is promoted onto the live
  wiki, and a failed or aborted (Ctrl+C) one is discarded with the live wiki untouched
  (promote-once per source, all-or-nothing — the full story lives on
  :func:`_run_agent_sessions`);
- snapshot the wiki BEFORE and AFTER each session and **diff by content hash** to learn what
  the agent created/updated/deleted (no return value needed);
- **validate + re-stamp** every changed page (``validate.validate_page`` re-imposes required
  fields / citations / link form; ``store.write_page`` canonicalizes YAML and stamps the
  ``timestamp`` the agent was told not to write); collect any validation errors;
- **repair renames** the agent may not have fully repointed (deterministic inbound-link fix
  via ``store.rewrite_links``, derived from the diff);
- once per run, rebuild indexes, surface broken links, and append a log line.

Idempotent: sources whose sha already matches the manifest are skipped (unless deliberately
re-read with ``--force``), and a source is marked done only on a clean session.
``llm.run_ingest_session`` is the single outside call (tests monkeypatch it with a fake that
writes files into the temp wiki).
"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import os
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent import futures
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import (
    config,
    extract,
    failures,
    grammar,
    llm,
    manifest,
    okf,
    pagecache,
    pdftext,
    repo,
    resume,
    runlock,
    store,
    transcribe,
    validate,
    wikigit,
)
from .okf import Page


# How many leading bytes to sniff when deciding whether a raw file holds text the agent can
# read. 64 KiB is plenty to classify text vs. binary without reading a huge file into memory.
_SNIFF_BYTES = 65536
# Bytes that count as "text" (the classic git binary heuristic): printable ASCII, the common
# whitespace/control bytes, plus EVERY high byte (0x80–0xFF) so UTF-8 / Latin-1 text is not
# misread as binary. A NUL byte — or a high proportion of other control bytes — marks a file
# binary. PDFs are detected separately by their magic header (the agent's reader extracts text
# from them), so they are not rejected here.
_TEXT_BYTES = bytes({7, 8, 9, 10, 11, 12, 13, 27} | set(range(0x20, 0x7F)) | set(range(0x80, 0x100)))

# Image sources the agent can read VISUALLY (its CLI reader displays them). Recognized by extension
# AND magic bytes, so a renamed text file is not mistaken for an image — it falls through to the
# normal text sniff instead. Gated by config.IMAGE_SUPPORT.
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


@dataclass
class IngestReport:
    processed: list[str]
    skipped: list[str]
    pages_written: list[str]  # = pages_created + pages_updated (union, in write order)
    errors: list[str]
    # The model/backend that imported this run's sources, surfaced so the report says WHICH model
    # ran. Starts as the CONFIGURED label (config.ingest_model_label) and is upgraded in place to
    # the model the backend REPORTED serving as soon as a session names one (_record_spend) — the
    # same id the per-source manifest entries are stamped with.
    model: str = ""
    pages_deleted: list[str] = field(default_factory=list)
    # (source_rel_path, target) cross-links left dangling after this run — should be empty.
    broken_links: list[tuple[str, str]] = field(default_factory=list)
    pages_created: list[str] = field(default_factory=list)  # pages that did not exist before
    pages_updated: list[str] = field(default_factory=list)  # existing pages that were rewritten
    # (old_rel_key, new_rel_key) for sources recognized as only MOVED/reorganized (same bytes
    # under a new path) — not re-ingested; their wiki references are repointed deterministically.
    moved: list[tuple[str, str]] = field(default_factory=list)
    # rel-keys of sources with no extractable text (binary/unsupported) — NOT ingested, logged.
    unreadable: list[str] = field(default_factory=list)
    # Subset of ``unreadable`` whose bytes read as 100% NUL — cloud-only placeholders (Dropbox/
    # OneDrive online-only files seen through WSL/SMB), surfaced with a make-it-available-offline
    # hint instead of the generic binary message.
    cloud_placeholders: list[str] = field(default_factory=list)
    # (dropped_key, kept_key) for same-basename document files skipped in favor of another format.
    duplicates: list[tuple[str, str]] = field(default_factory=list)
    # (forced_key, kept_key) for same-basename pairs a FORCED run ingested ALONGSIDE the kept
    # sibling (a forced run bypasses the dedup drop — nothing was skipped, both formats are in the wiki).
    duplicates_forced: list[tuple[str, str]] = field(default_factory=list)
    # (rel_key, size_bytes) for sources skipped at discovery because they exceed
    # CITADEL_MAX_SOURCE_BYTES — never hashed, never ingested, and (like an ignore-pattern match)
    # never recorded in the manifest or the failures catalog. Reported so a size skip is visible.
    oversized: list[tuple[str, int]] = field(default_factory=list)
    # rel-keys of tracked sources that VANISHED from disk (a full run only): their provenance is
    # reconciled out of the wiki by a cleanup agent session, then the manifest key is dropped.
    sources_deleted: list[str] = field(default_factory=list)
    # `--jobs N` only: sources whose session raced a CONCURRENT source's promote over the same page
    # and were therefore re-run serially afterwards (the re-run's own success/failure is reported
    # like any other source's). Surfaced because it is the one place parallel ingest costs money a
    # serial run would not have spent — a corpus that races often wants a lower --jobs.
    raced: list[str] = field(default_factory=list)
    # Chunked sources that CONTINUED from an earlier run's checkpoint instead of restarting at
    # segment 1 ("raw/book.txt (segments 1-3 of 7 restored)") — see citadel/resume.py. Recorded
    # whether or not the resumed source then succeeded: the earlier work was reused either way.
    resumed: list[str] = field(default_factory=list)
    # rel-keys of FRESH sources (a plain ingest — not a reconcile, not a delete cleanup) whose
    # session succeeded but changed NOTHING: no page created, updated, or deleted. Suspicious by
    # construction — a brand-new source that contributes zero facts is usually a session that
    # under-delivered, yet it is marked done and never revisited on its own. Surfaced as a WARNING
    # so it is easy to spot and retry (`citadel ingest --retry`, or `--force <path>`).
    no_pages: list[str] = field(default_factory=list)
    # The wiki-history note from wikigit.autocommit ("wiki git: committed <sha>", or a warning
    # naming what was skipped and why) — empty when the history layer had nothing to say.
    wiki_git: str = ""
    # What this run's agent sessions cost, summed over EVERY session that reported usage —
    # failed sources included (their money was spent too; only the manifest stamp is
    # success-only). None when no backend reported anything (copilot, the test fakes).
    usage: llm.SessionUsage | None = None

    def render(self) -> str:
        """Human-readable multi-line summary for CLI/MCP."""
        lines: list[str] = []
        if self.model:
            lines.append(f"Model: {self.model}")
        lines.append(
            f"Ingest complete: {len(self.processed)} processed, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.pages_created)} created, "
            f"{len(self.pages_updated)} updated, "
            f"{len(self.pages_deleted)} deleted, "
            f"{len(self.moved)} reorganized, "
            f"{len(self.sources_deleted)} sources removed, "
            f"{len(self.unreadable)} unreadable, "
            f"{len(self.duplicates)} duplicate(s) skipped, "
            f"{len(self.errors)} errors."
        )
        described = self.usage.describe() if self.usage is not None else ""
        if described:
            lines.append(f"LLM usage: {described}.")
        if self.processed:
            lines.append("Processed:")
            lines.extend(f"  - {p}" for p in self.processed)
        if self.pages_created:
            lines.append("Pages created:")
            lines.extend(f"  - {p}" for p in self.pages_created)
        if self.pages_updated:
            lines.append("Pages updated:")
            lines.extend(f"  - {p}" for p in self.pages_updated)
        if self.pages_deleted:
            lines.append("Pages deleted (restructured):")
            lines.extend(f"  - {p}" for p in self.pages_deleted)
        if self.moved:
            lines.append("Reorganized (recognized as moved; not re-ingested):")
            lines.extend(f"  - {old} -> {new}" for old, new in self.moved)
        if self.sources_deleted:
            lines.append("Sources removed (deleted from disk; citations reconciled out):")
            lines.extend(f"  - {s}" for s in self.sources_deleted)
        if self.resumed:
            lines.append("Resumed (continued from an earlier run's checkpoint):")
            lines.extend(f"  - {r}" for r in self.resumed)
        if self.raced:
            lines.append("Re-run serially (raced another source's promote over the same page):")
            lines.extend(f"  - {r}" for r in self.raced)
        if self.unreadable:
            lines.append("Unreadable (no extractable text; not ingested):")
            for p in self.unreadable:
                if p in self.cloud_placeholders:
                    lines.append(
                        f"  - {p}  (reads as all NUL bytes - a cloud-only placeholder? make it available offline)"
                    )
                else:
                    lines.append(f"  - {p}")
        if self.oversized:
            lines.append(f"Oversized (over CITADEL_MAX_SOURCE_BYTES = {_human_bytes(config.MAX_SOURCE_BYTES)}):")
            lines.extend(f"  - {key} ({_human_bytes(size)})" for key, size in self.oversized)
        if self.duplicates:
            lines.append("Skipped as duplicate (same basename as another format that was ingested):")
            lines.extend(f"  - {dropped} (kept {kept})" for dropped, kept in self.duplicates)
        if self.duplicates_forced:
            lines.append("Duplicate formats deliberately ingested (forced):")
            lines.extend(f"  - {d} (ingested alongside {kept} — forced)" for d, kept in self.duplicates_forced)
        if self.skipped:
            lines.append("Skipped (already ingested):")
            lines.extend(f"  - {p}" for p in self.skipped)
        if self.no_pages:
            lines.append("WARNING — ingested but produced NO wiki changes (no page created, updated, or deleted):")
            lines.extend(f"  - {p}" for p in self.no_pages)
            lines.append(
                "  These sources are marked done and will not be revisited automatically. "
                "Retry them with `citadel ingest --retry` (or `citadel ingest --force <path>`)."
            )
        if self.broken_links:
            lines.append("WARNING — broken cross-links (run `citadel lint`):")
            lines.extend(f"  - {src} -> {tgt}" for src, tgt in self.broken_links)
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in self.errors)
            lines.append(
                "  Failed sources stay in the failures catalog (`citadel status` lists them) and are "
                "retried on the next run — or right away with `citadel ingest --retry`."
            )
        if self.wiki_git:
            lines.append(self.wiki_git)
        return "\n".join(lines)


def _same_path(a: Path, b: Path) -> bool:
    """True if ``a`` and ``b`` resolve to the same location (never raises)."""
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a == b


def _resolved_or_self(path: Path) -> Path:
    """``path.resolve()`` falling back to ``path`` itself on an OS error (mirroring
    :func:`_same_path`'s guard) — the once-per-root identity the deletion sweep compares."""
    try:
        return path.resolve()
    except OSError:
        return path


def _is_ignored_name(name: str) -> bool:
    """True if ``name`` (a file OR directory BASENAME) matches one of the configured OS/junk-file
    ignore globs (``config.IGNORE_PATTERNS``), matched case-insensitively. Such entries are noise
    (Windows ``Thumbs.db``/``desktop.ini``, macOS ``.DS_Store``, Office ``~$`` lock files, editor
    swap/backup files) and are skipped entirely during discovery: never ingested, never recorded in
    the manifest or the failures catalog. Read at call time so tests/env can override the list."""
    lowered = name.lower()
    return any(fnmatch.fnmatchcase(lowered, pattern.lower()) for pattern in config.IGNORE_PATTERNS)


def _is_wiki_internal(path: Path) -> bool:
    """True when ``path`` is at or under the LIVE wiki directory — the generated, LLM-owned layer,
    which is never a raw source.

    This is the self-ingest guard. A layout whose raw root sits ABOVE the wiki — a whole mounted
    drive walked as one root (``CITADEL_RAW_DIRS=T:\\`` with the wiki at ``T:\\llmWiki\\ds\\wiki``)
    — would otherwise discover the wiki's own pages as sources and fold the wiki into itself, run
    after run, each pass citing the last. Nothing else prevented it: the wiki dir is not hidden and
    matches no ignore pattern, so the only workaround was a hand-written
    ``CITADEL_IGNORE_PATTERNS`` entry.

    Containment is ``grammar.is_within`` — purely lexical, no ``resolve()`` and no ``abspath()`` —
    so the check costs nothing per directory entry and can never block (or syscall) on a dead
    mount. ``path`` must therefore already be ABSOLUTE, which every walk-built path and every
    ``config.source_path_for_key`` result is; the one caller that can be handed a relative path (an
    explicitly requested one, typed by the user) normalizes it itself.

    Deliberately the process-wide ``config.WIKI_DIR`` rather than ``config.wiki_dir()``: what must
    never be scanned is the LIVE wiki, whichever per-source staging copy the current context is
    redirected to (staging copies are hidden dotdir siblings, which discovery already skips)."""
    return grammar.is_within(path, config.WIKI_DIR)


def _explicit_path(raw: str | os.PathLike) -> Path:
    """One EXPLICITLY requested path (``citadel ingest <paths…>``, ``wiki_ingest``), with ``~``
    expanded — the same courtesy every other configured path already gets
    (``config._resolve_dir_entry``, ``workspace.init``, ``CITADEL_WORKSPACE``); the ingest
    arguments were the outlier.

    It matters most where this PR's other fixes do: a POSIX shell expands ``~`` before citadel ever
    sees it, but Windows ``cmd.exe`` (and PowerShell, for a native binary's arguments) does not, so
    ``citadel ingest ~/ws/raw/notes.md`` arrived as a literal ``~`` directory that stat'ed away to
    nothing. It also closes the same gap in the wiki guard: an unexpanded path could not be
    recognized as wiki-internal (it merely failed to resolve, so nothing was ingested — but the
    guard must hold by construction, not by a downstream accident).

    ``os.path.expanduser`` rather than ``Path.expanduser``: the latter RAISES on an unresolvable
    home (``~nosuchuser``), and discovery must never raise on user input — the stdlib function
    returns such a path unchanged instead."""
    return Path(os.path.expanduser(raw))


def _is_untrackable_key(key: str) -> bool:
    """True for a tracked key that must not be tracked AT ALL any more — the run-start migration
    sweep's predicate: an OS/junk basename (an ignore pattern added after it was recorded) or a
    path inside the wiki itself (a page self-ingested before :func:`_is_wiki_internal` guarded
    discovery). Both keep existing on disk, so deletion detection would never clean them up."""
    return _is_ignored_name(PurePosixPath(key).name) or _is_wiki_internal(config.source_path_for_key(key))


def _exceeds_size_cap(size: int) -> bool:
    """True when ``config.MAX_SOURCE_BYTES`` is set and a file of ``size`` bytes is over it — the
    discovery SIZE ceiling that complements the name-matching ignore patterns. Read at call time;
    0 (the default) means no limit."""
    cap = config.MAX_SOURCE_BYTES
    return cap > 0 and size > cap


def _human_bytes(size: int) -> str:
    """A short ASCII rendering of a byte count for the report ("10.6 GB") — console output stays
    ASCII-only, so no multiplication sign or non-breaking space sneaks in."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"  # unreachable; keeps the return type total


def _is_repo_source(path: Path) -> bool:
    """True if ``path`` should be ingested as ONE repo source: repo support is on, it is a repo
    dir (``.git``/``.citadelsource``), and it is NOT a configured corpus root (``RAW_DIR`` or any
    ``RAW_DIRS`` member) itself. The latter guard matters because a user may keep a whole raw
    root under git for backup — that must still be scanned file-by-file (its repo SUB-folders
    are the sources), not collapsed into one."""
    if not (config.REPO_SUPPORT and repo.is_repo_dir(path)):
        return False
    return not any(_same_path(path, root) for root in config.source_roots())


@dataclass
class _Walk:
    """Everything ONE discovery pass over the raw roots learned — files WITH their stat (the
    scan-cache quick check consumes it, killing the per-candidate ``is_file()``/hash), the repo
    dirs found, and the operational-safety facts the deletion sweep is scoped by: every walk
    error (a flaky SMB subdirectory), the roots that could not be entered at all (an unmounted
    share), and the roots discovery actually ENTERED (top-level scandir succeeded). A root that
    is missing, errors at top level, or hides files behind a flaky listing must NEVER read as
    "the user deleted these sources": any error anywhere zeroes the
    sweep for the whole run, so entered-vs-clean needs no per-root error bookkeeping."""

    files: list[tuple[Path, os.stat_result]] = field(default_factory=list)
    repos: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # OSErrors below an entered root
    unreachable: list[Path] = field(default_factory=list)  # roots that could not be entered at all
    entered_roots: list[Path] = field(default_factory=list)  # roots whose top-level scandir succeeded
    # (path, size) for files skipped by the CITADEL_MAX_SOURCE_BYTES ceiling — never hashed, never
    # ingested, but reported, so a size skip is visible instead of silent.
    oversized: list[tuple[Path, int]] = field(default_factory=list)
    # Directories skipped because they ARE (or are inside) the wiki — a raw root that sits above
    # the wiki dir. Reported once per run so the exclusion is visible, never inferred as absence.
    excluded_wiki: list[Path] = field(default_factory=list)


def _scan_tree(root: Path, walk: _Walk) -> None:
    """ONE iterative ``os.scandir`` walk over ``root``, appending onto ``walk`` — this replaces
    the two ``os.walk`` passes (files + repos) with a single traversal whose ``DirEntry.stat``
    results are kept for the scan-cache quick check.

    Skip rules: hidden names (leading ``.``), OS/junk ignore globs (:func:`_is_ignored_name`), the
    wiki directory itself (:func:`_is_wiki_internal` — the generated layer is never a source), files
    over the size ceiling (:func:`_exceeds_size_cap`), and — with repo support on — no descending
    into a git repository (collected as one repo source instead). Any other file type in any
    sub-folder is picked up; ``follow_symlinks=False`` throughout, so a symlinked directory is never
    recursed into (a cycle on a share must not hang discovery). Deterministic order (names sorted
    per directory, depth-first). NEVER raises: a top-level failure marks the root unreachable; a
    failure deeper in records a walk error (either one disarms the deletion sweep — see
    :func:`ingest`)."""
    if _is_wiki_internal(Path(root)):
        # The configured raw root IS the wiki (or lives inside it). Refuse the whole walk rather
        # than scan generated pages back in as sources — and, by never entering, leave this root
        # out of ``entered_roots``, so the deletion sweep is not armed for a root nothing scanned.
        walk.excluded_wiki.append(Path(root))
        return
    at_root = True
    stack: list[Path] = [Path(root)]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError as exc:
            if at_root:
                walk.unreachable.append(Path(root))
                return
            walk.errors.append(f"{d}: {exc}")
            continue
        if at_root:
            walk.entered_roots.append(Path(root))
            at_root = False
        subdirs: list[Path] = []
        for entry in entries:
            name = entry.name
            if name.startswith(".") or _is_ignored_name(name):
                continue
            path = Path(d) / name
            try:
                if entry.is_dir(follow_symlinks=False):
                    if _is_wiki_internal(path):
                        # The wiki dir under a raw root: prune it whole. Its pages are generated,
                        # never sources — ingesting them would fold the wiki into itself.
                        walk.excluded_wiki.append(path)
                    # Deliberately NOT _is_repo_source: its corpus-root guard resolve()s every root per call
                    # — too costly per-directory on a network share (a subdir is never a configured root here).
                    elif config.REPO_SUPPORT and repo.is_repo_dir(path):
                        walk.repos.append(path)  # one repo source; the file walk stops here
                    else:
                        subdirs.append(path)
                elif entry.is_file(follow_symlinks=False):
                    st = entry.stat(follow_symlinks=False)
                    # The size ceiling is applied HERE, on the stat the walk already took: an
                    # oversized file is never opened, never hashed, and never classified — which
                    # is the whole point (a folder of multi-GB machine-data dumps otherwise costs
                    # a full sha256 stream per file before anything can call it unreadable).
                    if _exceeds_size_cap(st.st_size):
                        walk.oversized.append((path, st.st_size))
                    else:
                        walk.files.append((path, st))
            except OSError as exc:
                walk.errors.append(f"{path}: {exc}")
        stack.extend(reversed(subdirs))  # LIFO -> depth-first in sorted order


def _discover_walk(paths: list[str] | None) -> _Walk:
    """Resolve requested paths (or default to every configured raw root, ``config.RAW_DIRS``)
    into one :class:`_Walk`. A requested file path is stat'ed and taken as-is (even a hidden name,
    an ignore-matched one, or one over the size ceiling — explicit wins, as before; one that is
    missing or not a regular file is silently dropped, replacing the old per-candidate
    ``is_file()``); a requested directory contributes its whole subtree — unless it is itself a repo
    source, which :func:`_discover_repos` handles. Roots are de-duplicated by resolved path.

    The ONE thing explicit does NOT win over is :func:`_is_wiki_internal`: a path inside the wiki is
    generated output, not a source, so naming it directly cannot make it one either."""
    walk = _Walk()
    if paths:
        for raw in paths:
            p = _explicit_path(raw)
            # abspath (not resolve) so a RELATIVE argument — `citadel ingest wiki/x.md` from the
            # workspace root — is still recognized as wiki-internal, without a filesystem round trip.
            if _is_wiki_internal(Path(os.path.abspath(p))):
                walk.excluded_wiki.append(p)
                continue
            if p.is_dir():
                if not _is_repo_source(p):
                    _scan_tree(p, walk)
                continue
            try:
                st = os.stat(p)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                walk.files.append((p, st))
        return walk
    seen: set[Path] = set()
    for root in config.RAW_DIRS:
        try:
            resolved = Path(root).resolve()
        except OSError:
            resolved = Path(root)
        if resolved in seen:
            continue
        seen.add(resolved)
        _scan_tree(Path(root), walk)
    return walk


def _candidates(paths: list[str] | None) -> list[Path]:
    """The candidate FILE list for requested paths (or all raw roots) — the path-only view over
    :func:`_discover_walk` (discovery itself keeps the walk's stats for the quick check).
    Unused by :func:`ingest` itself; kept as the thin test-facing seam the discovery tests
    drive the walk through."""
    return [p for p, _st in _discover_walk(paths).files]


def _sweep_gone(keys, exclude_keys: set[str], swept_roots: list[Path] | None) -> tuple[list[str], list[str]]:
    """The candidates-then-confirm deletion sweep shared by the file and repo partitions.

    ``keys`` are the tracked manifest keys of one kind; ``exclude_keys`` the ones this run
    accounted for (walked/seen, or the source side of a detected move — a reorganize whose
    references get repointed, not a deletion). ``swept_roots`` is the caller's ONE sweep
    decision: None = no sweep at all (a path-scoped run, a degraded walk, or the
    workspace-identity guard), else exactly the roots discovery entered this run. The remaining
    guards, in order (operational safety is the point):

    - a key under NO configured root (``config.root_covering``) whose file is gone lands in
      ``out_of_root`` (an explicit out-of-root ingest, a root removed from the config) —
      reported by the caller, never swept;
    - a key whose root was not swept this run (unreachable/unentered) is kept and re-checked
      next run;
    - a surviving candidate is positively CONFIRMED gone with ``.exists()`` — the seen-set diff
      only ever nominates.

    Returns ``(deleted, out_of_root)``, both in sorted-key order. The swept roots are resolved
    ONCE up front and each distinct covering root once, so the candidate loop costs no
    per-candidate ``resolve()`` (previously O(candidates x roots) stats on a dead mount)."""
    deleted: list[str] = []
    out_of_root: list[str] = []
    if swept_roots is None:
        return deleted, out_of_root
    swept_ids = {_resolved_or_self(Path(root)) for root in swept_roots}
    root_swept: dict[Path, bool] = {}
    for key in sorted(keys):
        if key in exclude_keys:
            continue
        path = config.source_path_for_key(key)
        root = config.root_covering(path)
        if root is None:
            if not path.exists():
                out_of_root.append(key)
            continue
        if root not in root_swept:
            root_swept[root] = _resolved_or_self(Path(root)) in swept_ids
        if not root_swept[root]:
            continue  # its root was unreachable this run: retry next run, never sweep
        if path.exists():
            continue  # the walk raced/missed it but it IS on disk: never swept
        deleted.append(key)
    return deleted, out_of_root


def _discover_repos(paths: list[str] | None, walk: _Walk) -> list[Path]:
    """The repo sources to ingest: the repo dirs the walk found under the raw roots (or under an
    explicitly requested directory), plus an explicitly requested path that is itself a repo.
    De-duplicated by resolved path, sorted. Empty when repo support is off (the walk then
    descended into repos file-by-file — the legacy behavior).

    The walk's own repo list is already wiki-free (:func:`_scan_tree` prunes the wiki before the
    repo test), but an EXPLICIT path needs the same guard here: a wiki dir under
    ``CITADEL_WIKI_GIT`` holds a ``.git``, so naming it would otherwise digest the whole wiki as a
    repo source."""
    if not config.REPO_SUPPORT:
        return []
    found: list[Path] = list(walk.repos)
    if paths:
        for raw in paths:
            p = _explicit_path(raw)
            if _is_wiki_internal(Path(os.path.abspath(p))):
                continue
            if p.is_dir() and _is_repo_source(p):
                found.append(p)
    seen: set[Path] = set()
    unique: list[Path] = []
    for p in found:
        try:
            resolved = p.resolve()
        except OSError:
            resolved = p
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(p)
    return sorted(unique, key=lambda p: manifest.rel_key(p))


def _is_ingestible(path: Path) -> bool:
    """True if the agent has a realistic chance of extracting text from this raw file.

    We try to OPEN everything rather than allow-listing extensions: plain text and code
    (``.txt``/``.py``/``.sql``/``.json``/…) read directly, and a PDF (detected by its ``%PDF-``
    magic) is handed to the agent because its reader can pull text out. Only a "weird binary" —
    a NUL byte, or a high proportion of non-text bytes in the sniffed prefix — is rejected; the
    caller logs those as unreadable instead of spending an LLM session on a blob. An empty file
    is ingestible (the agent simply finds nothing to add), not a binary failure.

    PowerPoint/Word files are NOT classified here: they are ZIP binaries that would fail this sniff,
    so :func:`_partition_sources` routes them through :mod:`citadel.extract` instead (a deck with
    extractable text is pending; a text-free one is unreadable) — done once there, not re-sniffed."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(_SNIFF_BYTES)
    except OSError:
        return False
    if not chunk:
        return True
    if chunk[:5] == b"%PDF-":
        return True
    if b"\x00" in chunk:
        return False
    nontext = chunk.translate(None, _TEXT_BYTES)
    return (len(nontext) / len(chunk)) <= 0.30


def _reads_as_cloud_placeholder(path: Path) -> bool:
    """True when a non-empty file's sniffed prefix reads as 100% NUL bytes — the signature of a
    cloud-only placeholder (a Dropbox/OneDrive "online-only" file reports its full size, but a read
    through WSL or SMB yields only zeros until the sync client hydrates it). Distinguishing this
    from a genuine binary turns the unreadable report into an actionable hint AND changes the
    bookkeeping: hydration restores the real bytes without touching size/mtime, so such a file must
    never be stat-cached as done (see the unreadable finalization in :func:`ingest`). Never raises."""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(_SNIFF_BYTES)
    except OSError:
        return False
    return bool(chunk) and not chunk.strip(b"\x00")


def _looks_like_image(head: bytes) -> bool:
    """True if ``head`` (the first bytes of a file) carries a common image format's magic:
    PNG/JPEG/GIF/BMP/TIFF/WEBP. Cheap signature check so a text file renamed ``.png`` is not sent to
    the agent as an image (it fails this and is sniffed as text instead)."""
    if head.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"GIF87a", b"GIF89a", b"BM")):
        return True
    if head[:2] in (b"II", b"MM") and head[2:4] in (b"*\x00", b"\x00*"):  # TIFF (little/big-endian)
        return True
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"  # WEBP (RIFF container)


def _is_image_source(path: Path) -> bool:
    """True when image ingestion is on (``config.IMAGE_SUPPORT``) and ``path`` is a recognized image
    (image extension AND matching magic). Such a source is handed to the agent to READ VISUALLY —
    the CLI's file reader displays images — instead of being rejected by :func:`_is_ingestible` as a
    NUL-byte binary. Never raises."""
    if not config.IMAGE_SUPPORT or path.suffix.lower() not in _IMAGE_EXTS:
        return False
    try:
        with open(path, "rb") as fh:
            return _looks_like_image(fh.read(16))
    except OSError:
        return False


# Document-export formats among which a same-basename group is deduplicated (a deck saved as both
# .pptx and .pdf, a doc saved as .docx and .pdf, etc.). A group is collapsed ONLY when EVERY member
# is one of these, so a hand-authored notes.md sharing a stem with notes.pdf is never dropped. The
# order is the KEEP preference (earliest wins): PDF first, then modern Office, then legacy.
_DEDUP_PRIORITY = [".pdf", ".docx", ".docm", ".doc", ".pptx", ".pptm", ".ppt", ".xlsx", ".xlsm", ".xls"]
_DEDUP_EXTS = set(_DEDUP_PRIORITY)


def _dedup_rank(ext: str) -> int:
    """Preference rank of a document extension for same-basename dedup (lower = kept first)."""
    return _DEDUP_PRIORITY.index(ext) if ext in _DEDUP_PRIORITY else len(_DEDUP_PRIORITY)


def _dedup_by_basename(
    pending: list[Path], manifest_dict: dict[str, manifest.Entry]
) -> tuple[list[Path], list[tuple[str, str]], set[Path]]:
    """Collapse same-folder, same-basename groups of DOCUMENT-export formats to a single kept file.

    Returns ``(kept, duplicates, dropped)``: ``duplicates`` is ``[(dropped_key, kept_key)]`` for the
    report/failures record, ``dropped`` the Paths removed from pending. Only a group whose members
    are ALL document formats (:data:`_DEDUP_EXTS`) is collapsed — so a plain-text/markdown/code/image
    source sharing a stem with a document is left alone.

    Two cases:
    - both formats are NEW this run → keep the preferred one (:func:`_dedup_rank`, PDF first), drop
      the rest;
    - a same-basename document was ALREADY ingested in another format (still on disk) → skip the new
      one(s), keeping what is already in the wiki (so re-runs are stable and no second copy sneaks
      in). Grouping is by the sources' posix identity keys, so pending and manifest members compare
      in the same space."""
    # A CHANGED document source is BOTH pending and in the manifest; excluding pending keys here
    # keeps it from matching itself as an "already-ingested sibling" and being dropped as a
    # duplicate of itself (which would stop it re-ingesting).
    pending_keys = {manifest.rel_key(p) for p in pending}
    ingested: dict[tuple[str, str], str] = {}
    for k, v in manifest_dict.items():
        if manifest.is_repo_entry(v) or k in pending_keys:
            continue
        kp = PurePosixPath(k)
        if kp.suffix.lower() in _DEDUP_EXTS and config.source_path_for_key(k).exists():
            ingested.setdefault((str(kp.parent), kp.stem.lower()), k)

    groups: dict[tuple[str, str], list[Path]] = {}
    for p in pending:
        kp = PurePosixPath(manifest.rel_key(p))
        groups.setdefault((str(kp.parent), kp.stem.lower()), []).append(p)

    kept: list[Path] = []
    duplicates: list[tuple[str, str]] = []
    dropped: set[Path] = set()
    for gid, members in groups.items():
        if not all(m.suffix.lower() in _DEDUP_EXTS for m in members):
            kept.extend(members)  # a non-document shares this stem: leave the whole group alone
            continue
        if gid in ingested:
            # A same-basename document is already in the wiki (another format): skip the new one(s).
            for m in members:
                dropped.add(m)
                duplicates.append((manifest.rel_key(m), ingested[gid]))
            continue
        if len(members) == 1:
            kept.append(members[0])
            continue
        winner = min(members, key=lambda m: (_dedup_rank(m.suffix.lower()), m.suffix.lower()))
        kept.append(winner)
        for m in members:
            if m is winner:
                continue
            dropped.add(m)
            duplicates.append((manifest.rel_key(m), manifest.rel_key(winner)))
    return kept, duplicates, dropped


@dataclass
class _Scan:
    """:func:`_partition_sources`'s result (attribute access only — see the field comments
    there). ``hashed`` carries the (sha, stat) taken for every candidate whose content hash
    became known this run — the single-hash currency the caller threads into ``mark_done``/the
    failures catalog instead of re-hashing; ``mutated`` is True when a manifest entry was
    refreshed/backfilled in place (the caller must save); ``out_of_root`` lists the gone tracked
    keys under no configured raw root (logged, never swept)."""

    pending: list[Path]
    skipped: list[str]
    moved: list[tuple[str, str, str, bool]]
    unreadable: list[Path]
    deleted: list[str]
    office_text: dict[Path, str]
    images: set[Path]
    duplicates: list[tuple[str, str]]
    duplicates_forced: list[tuple[str, str]] = field(default_factory=list)
    hashed: dict[str, tuple[str, os.stat_result]] = field(default_factory=dict)
    mutated: bool = False
    out_of_root: list[str] = field(default_factory=list)
    unreadable_tracked: list[str] = field(default_factory=list)
    # Pending audio/video sources — transcribed through the whisper seam (citadel.transcribe) in
    # the per-source job, so a missing/failing whisper CLI is a retryable per-source error.
    audio: set[Path] = field(default_factory=set)


def _partition_sources(
    paths: list[str] | None,
    manifest_dict: dict[str, manifest.Entry],
    failures_dict: dict[str, dict] | None = None,
    full_rescan: bool = False,
    walk: _Walk | None = None,
    swept_roots: list[Path] | None = None,
    force: bool = False,
) -> _Scan:
    """Split candidates into a :class:`_Scan` in one walk. ``walk`` is the (possibly
    pre-computed) discovery walk — :func:`ingest` hoists it so ``swept_roots`` (the ONE sweep
    decision, see below) can be derived from it once and passed to BOTH partitions; a direct
    caller may omit both.

    - ``pending``: new/changed files with novel, readable content — fed to the agent (sorted,
      de-duplicated by resolved path).
    - ``skipped``: rel-keys whose sha already matches the manifest (already ingested).
    - ``moved``: ``(old_key, new_key, sha, old_gone)`` for a file that appeared under a NEW path
      whose bytes were already ingested under another key — a reorganize (rename/move) or a
      duplicate. Recognized, NOT re-ingested. ``old_gone`` is True when the prior path no longer
      exists on disk (a real move, so its wiki references get repointed).
    - ``unreadable``: files with no extractable text (binary/unsupported) — logged, not ingested.
    - ``deleted``: rel-keys tracked in the manifest whose file VANISHED from disk and is NOT the
      source side of a move — their provenance is reconciled out of the wiki by a cleanup agent
      session. Candidates come from the walked-seen-set diff and go through the shared
      :func:`_sweep_gone` guard set, scoped by ``swept_roots`` — the caller's one sweep decision
      (None = no sweep at all: a path-scoped run, a degraded walk, or the workspace-identity
      guard; operational safety is the point).
    - ``office_text``: ``{src_path: extracted_text}`` for the pending PowerPoint/Word/Excel sources
      (``.pptx``/``.docx``/``.xlsx`` and their macro-enabled + legacy ``.ppt``/``.doc``/``.xls``
      siblings) whose text was extracted here to classify them — reused by the agent step so an
      Office file is parsed exactly once per run, not twice.
    - ``images``: the subset of ``pending`` that are image files (read visually by the agent, not
      text-extracted) — so the agent step drives them with the ``image`` propagation.
    - ``duplicates``: ``[(dropped_key, kept_key)]`` for same-basename document files skipped in
      favor of another format (see :func:`_dedup_by_basename`), when ``config.DEDUP_BY_BASENAME`` is
      on. The dropped files are removed from ``pending`` (and from ``office_text``/``images``).
      On a FORCED run nothing is dropped: the pairs land in ``duplicates_forced`` instead — the
      requested file is ingested ALONGSIDE its kept sibling and the report says so.

    Already-tracked candidates go through the scan-cache quick check first
    (:func:`manifest.entry_trusts_stat` over the walk's stat): a trusted entry is skipped with
    ZERO content reads; anything else is stream-hashed exactly ONCE (the sha is threaded through
    ``hashed`` to ``mark_done``), and an unchanged-content hit refreshes/backfills the entry's
    stat cache in place (``mutated``). Untracked candidates consult the failures catalog's
    sha+stat the same way, so an unchanged stuck source (duplicate twin, unreadable binary) is
    re-evaluated without being re-hashed. ``full_rescan`` bypasses both quick checks.

    ``force`` (``ingest --force``) goes one deliberate step further:
    it bypasses the quick checks AND the sha short-circuit, so an unchanged already-ingested
    candidate lands in ``pending`` and is re-read by the agent — the caller's changed-keys logic
    then gives a tracked key ``kind="reconcile"``, never a plain ingest (the rationale lives on
    :func:`_partition_repos`). It also bypasses the same-basename dedup DROP: the explicitly
    requested file is ingested even when a sibling format was kept, with ``duplicates_forced``
    carrying the kept-alongside pairs as the report's divergence record (nothing is dropped
    from ``pending``).

    Move/duplicate detection only fires for a genuinely NEW path (``key not in manifest_dict``):
    an in-place edit of an already-tracked file is always re-ingested, even if its new content
    happens to match another file. It matches against tracked shas AND against content already
    accepted as pending earlier in the SAME run, so a byte-identical copy in a second root folds
    in exactly once.
    """
    by_sha: dict[str, list[str]] = {}
    for k, v in manifest_dict.items():
        if manifest.is_repo_entry(v):
            continue  # repo sources are versioned by commit, not sha — handled separately
        by_sha.setdefault(manifest.entry_sha(v), []).append(k)
    failures_dict = failures_dict if failures_dict is not None else {}

    walk = walk if walk is not None else _discover_walk(paths)
    # One name for the twice-used trust decision: the stat quick checks (manifest AND failures
    # catalog) may trust a recorded sha+stat only when neither --full-rescan nor --force distrusts it.
    trust_cache = not full_rescan and not force
    pending: list[Path] = []
    skipped: list[str] = []
    moved: list[tuple[str, str, str, bool]] = []
    unreadable: list[Path] = []
    # Tracked (already-ingested) sources whose re-hash failed this run — skipped but surfaced.
    unreadable_tracked: list[str] = []
    # Office sources extracted here -> their text, so the agent step writes the temp .md without a
    # second ZIP/XML parse. Keyed by the same Path objects carried in `pending`.
    office_text: dict[Path, str] = {}
    # Pending image sources — the agent reads these VISUALLY (no text extraction here).
    images: set[Path] = set()
    # Pending audio/video sources — transcribed lazily in the per-source job, NOT here: partition
    # must stay cheap, and a whisper failure has to be a retryable per-source error.
    audio: set[Path] = set()
    # (sha, walk stat) for every candidate whose content hash became known — quick-check reuse or
    # ONE stream-hash — threaded through to mark_done/the failures catalog (no second hash).
    hashed: dict[str, tuple[str, os.stat_result]] = {}
    # Same-run duplicate recognition: content already accepted as pending under another key this
    # run (a byte-identical copy in a second root) is a duplicate, not a second agent session.
    pending_by_sha: dict[str, str] = {}
    mutated = False
    seen: set[Path] = set()
    seen_keys: set[str] = set()
    for src, st in walk.files:
        try:
            resolved = src.resolve()
        except OSError:
            resolved = src
        if resolved in seen:
            continue
        seen.add(resolved)
        key = manifest.rel_key(src)
        seen_keys.add(key)
        entry = manifest_dict.get(key)
        untracked_sha: str | None = None
        if entry is not None:
            file_entry = not manifest.is_repo_entry(entry)
            if file_entry and trust_cache and manifest.entry_trusts_stat(entry, st):
                # The scan-cache quick check: (size, mtime_ns) match and the entry is not racy —
                # the recorded sha stands, no content read at all.
                skipped.append(key)
                continue
            try:
                sha = manifest.file_sha256(src)
            except OSError:
                # An already-ingested source that became unreadable (permissions / transient IO)
                # must NOT crash the whole run — it is already in the wiki, so treat it as
                # skipped rather than a fresh source. But surface it (a NOTE per run, like the
                # sweep skips): a tracked file that stays unreadable — share glitch, permission
                # change, on-disk corruption — would otherwise read as "ingested, nothing to do"
                # forever.
                skipped.append(key)
                unreadable_tracked.append(key)
                continue
            hashed[key] = (sha, st)
            if file_entry and not force and sha == manifest.entry_sha(entry):
                # Unchanged content behind a stale/absent stat cache (a touched-but-identical
                # file, a pre-PR4 entry, --full-rescan): refresh/backfill the entry in place —
                # keeping the recorded model/rules_version/ingested_at + usage stamp (no session
                # ran, so neither the last-checked stamp nor the cost may move) — so the next run
                # quick-skips it.
                manifest_dict[key] = manifest.make_entry(
                    sha,
                    manifest.entry_model(entry),
                    manifest.entry_rules_version(entry),
                    st=st,
                    ingested_at=manifest.entry_ingested_at(entry),
                    **manifest.entry_usage(entry),
                )
                mutated = True
                skipped.append(key)
                continue
            # Changed bytes (sha is the sole arbiter) — or a FORCED re-read of unchanged ones:
            # fall through to classification below.
        else:
            fentry = failures_dict.get(key)
            fsha = fentry.get("sha256") if isinstance(fentry, dict) else None
            if fsha and trust_cache and manifest.entry_trusts_stat(fentry, st):
                # An unchanged stuck source (dedup-dropped twin, unreadable binary, erroring
                # session) — the failures catalog is its scan cache: reuse the recorded sha so
                # it is re-EVALUATED below without being re-hashed forever.
                sha = str(fsha)
            else:
                # New/changed content. Hash once — this single stream-hash serves move detection
                # AND is passed through to mark_done. Fail closed on an OS read error (a
                # brand-new source we cannot read) by treating it as unreadable.
                try:
                    sha = manifest.file_sha256(src)
                except OSError:
                    unreadable.append(src)
                    continue
            hashed[key] = (sha, st)
            untracked_sha = sha
            prior = sorted(k for k in by_sha.get(sha, []) if k != key)
            if not prior and pending_by_sha.get(sha, key) != key:
                prior = [pending_by_sha[sha]]
            if prior:
                gone = sorted(k for k in prior if not config.source_path_for_key(k).exists())
                old_key = gone[0] if gone else prior[0]
                moved.append((old_key, key, sha, bool(gone)))
                continue
        if extract.is_office_source(src):
            # PowerPoint/Word: extract the text ONCE here (a ZIP the byte-sniff would reject). Cache
            # it so the agent step reuses it instead of re-parsing the same ZIP/XML. Text -> pending;
            # a text-free deck (all images) is unreadable, exactly like any other binary.
            text = extract.extract_text(src)
            if text.strip():
                office_text[src] = text
                pending.append(src)
            else:
                unreadable.append(src)
                continue
        elif _is_image_source(src):
            # An image the agent reads visually — routed to pending BEFORE the binary sniff (which
            # would reject its NUL bytes). No text is extracted here; the agent opens it by path.
            images.add(src)
            pending.append(src)
        elif transcribe.is_audio_source(src):
            # An audio/video recording (CITADEL_AUDIO_SUPPORT) — routed to pending BEFORE the
            # binary sniff. Transcription happens in the per-source job, not here: a missing or
            # failing whisper CLI must be a retryable per-source error, never a partition-time
            # crash — and never a permanent unreadable mark that would need --force to undo.
            audio.add(src)
            pending.append(src)
        elif not _is_ingestible(src):
            unreadable.append(src)
            continue
        else:
            pending.append(src)
        if untracked_sha is not None:
            pending_by_sha.setdefault(untracked_sha, key)

    # Deleted sources — the tracked FILE keys the walk did not see, run through the shared
    # candidates-then-confirm sweep (:func:`_sweep_gone` holds the full guard set; ``swept_roots``
    # is the caller's one sweep decision). Repo keys are excluded — repo deletions are detected by
    # _partition_repos, not the file sweep. Also excluded: the source side of a detected move —
    # its old path is gone too, but that is a reorganize (references get repointed), not a
    # deletion to reconcile away.
    moved_old = {old_key for old_key, _new, _sha, old_gone in moved if old_gone}
    file_keys = [k for k, v in manifest_dict.items() if not manifest.is_repo_entry(v)]
    deleted, out_of_root = _sweep_gone(file_keys, moved_old | seen_keys, swept_roots)
    # Collapse same-basename document duplicates (e.g. report.pptx + report.pdf) to one kept file,
    # dropping the rest from pending (and from the office/image side-tables). Recorded for the run.
    # A FORCED run bypasses the drop — the requested file is ingested ALONGSIDE its kept
    # sibling — so its pairs are classified separately and pending stays intact.
    duplicates: list[tuple[str, str]] = []
    duplicates_forced: list[tuple[str, str]] = []
    if config.DEDUP_BY_BASENAME:
        kept, pairs, dropped = _dedup_by_basename(pending, manifest_dict)
        if force:
            duplicates_forced = pairs
        else:
            pending = kept
            duplicates = pairs
            for p in dropped:
                office_text.pop(p, None)
                images.discard(p)
                audio.discard(p)
    return _Scan(
        pending=sorted(pending),
        skipped=skipped,
        moved=moved,
        unreadable=unreadable,
        deleted=deleted,
        office_text=office_text,
        images=images,
        duplicates=duplicates,
        duplicates_forced=duplicates_forced,
        hashed=hashed,
        mutated=mutated,
        out_of_root=out_of_root,
        unreadable_tracked=unreadable_tracked,
        audio=audio,
    )


@dataclass
class _RepoJob:
    """One pending repo source: its on-disk ``path``, its source key (``raw/acme-service``), the
    session ``kind`` (``"repo"`` first time / ``"repo-reconcile"`` on a later commit), and the
    ``old_commit`` to diff against on a reconcile (None for a first ingest; a forced re-read
    ignores it and re-digests in full — see :func:`_partition_repos`)."""

    path: Path
    key: str
    kind: str
    old_commit: str | None


def _partition_repos(
    repo_paths: list[Path],
    manifest_dict: dict[str, manifest.Entry],
    swept_roots: list[Path] | None,
    force: bool = False,
) -> tuple[list[_RepoJob], list[tuple[str, str, str]], list[str], list[str], list[str]]:
    """Split discovered repos into ``(pending, moved, deleted, skipped, out_of_root)``.

    - ``pending``: repos that are new (``kind="repo"``) or whose commit changed since last ingest
      (``kind="repo-reconcile"``, carrying the old commit for the diff). With ``force`` a
      repo already at its stored commit is NOT skipped: it lands here as ``kind="repo-reconcile"``
      — never ``"repo"``, because a first-time brief would DUPLICATE the pages the wiki already
      holds for it (the same rule gives a forced sha-matching FILE ``kind="reconcile"``, never a
      plain ingest) — and the forced session re-reads a FULL digest, ``only=None`` with no change
      summary: there may be no commit diff to consult, and the point of forcing is to re-verify
      everything.
    - ``moved``: ``(old_key, new_key, identity)`` for a repo that appeared under a NEW path whose
      base commit matches a tracked repo whose old folder is gone — a rename; references get
      repointed, not re-ingested.
    - ``deleted``/``out_of_root``: tracked repo keys whose folder vanished, through the shared
      :func:`_sweep_gone` guard set — scoped exactly like the file sweep by ``swept_roots``, the
      caller's one sweep decision (None = no sweep at all).
    - ``skipped``: repo keys already at the current commit (nothing to do).
    """
    repo_keys = {k: v for k, v in manifest_dict.items() if manifest.is_repo_entry(v)}
    by_commit: dict[str, list[str]] = {}
    for k, v in repo_keys.items():
        base = manifest.entry_commit(v).split("+", 1)[0]
        if base and not base.startswith("snap."):
            by_commit.setdefault(base, []).append(k)

    pending: list[_RepoJob] = []
    moved: list[tuple[str, str, str]] = []
    skipped: list[str] = []
    seen: set[Path] = set()
    for path in repo_paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        key = manifest.rel_key(path)
        ident = repo.identity(path)
        stored = manifest_dict.get(key)
        if not force and manifest.is_repo_entry(stored) and manifest.entry_commit(stored) == ident:
            skipped.append(key)
            continue
        if key not in manifest_dict:
            base = ident.split("+", 1)[0]
            if base and not base.startswith("snap."):
                gone = sorted(
                    k for k in by_commit.get(base, []) if k != key and not config.source_path_for_key(k).exists()
                )
                if gone:
                    moved.append((gone[0], key, ident))
                    continue
        old_commit = manifest.entry_commit(stored) if manifest.is_repo_entry(stored) else None
        kind = "repo-reconcile" if old_commit else "repo"
        pending.append(_RepoJob(path=path, key=key, kind=kind, old_commit=old_commit))

    moved_old = {old for old, _new, _ident in moved}
    walked_keys = {manifest.rel_key(p) for p in repo_paths}
    deleted, out_of_root = _sweep_gone(repo_keys, moved_old | walked_keys, swept_roots)
    return pending, moved, deleted, skipped, out_of_root


def _hash_pages(pages: list[Page]) -> dict[str, str]:
    """``{rel_path: sha256(on-disk bytes)}`` for the given pages. Hash the bytes (not the
    parsed body) so a frontmatter-only change still registers; skip a page that vanished
    mid-read."""
    snap: dict[str, str] = {}
    for page in pages:
        try:
            target = okf.safe_join(config.wiki_dir(), page.rel_path)
            snap[page.rel_path] = hashlib.sha256(target.read_bytes()).hexdigest()
        except (okf.OKFError, OSError):
            continue
    return snap


def _snapshot() -> dict[str, str]:
    """Content-hash snapshot of every CURRENT non-reserved wiki page. Reuses ``store.load``
    so reserved files (index.md, log.md, ``*/index.md``, dotfiles) are excluded by the
    loader's own rule — one source of truth for 'what is a page'."""
    return _hash_pages(store.load())


def _diff(before: dict[str, str], after: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    """``(created, updated, deleted)``, each sorted. created = in after not before;
    deleted = in before not after; updated = in both with a changed hash."""
    created = sorted(k for k in after if k not in before)
    deleted = sorted(k for k in before if k not in after)
    updated = sorted(k for k in after if k in before and after[k] != before[k])
    return created, updated, deleted


def _canonical_resource_key(resource: str, rel_key: str) -> str | None:
    """Return the canonical source key to replace a changed page's ``resource`` with, or None to
    leave it untouched.

    The ingest agent occasionally records a SHORTENED ``resource`` for an out-of-repo source: for a
    file whose real key is an absolute path (``//host/share/raw/notes.pdf`` — what a source on a
    mounted network drive resolves to), it writes the conventional repo-relative ``raw/notes.pdf``
    that every schema example uses. That short form does not resolve to a real file (the file is on
    the drive, not under the repo), so it (a) fails ``bad_resource`` validation and rolls the whole
    source back — discarding a long, expensive session over a cosmetic path mismatch — and (b) would
    not equal the manifest key, so a later move/delete of the source could not find the page
    (``store.find_raw_references`` matches the ``resource`` frontmatter against the EXACT key).

    Repair ONLY the unambiguous case: the written value does not resolve to a file, it shares the
    source key's basename, and the source key itself resolves. Then the page plainly names THIS
    source — canonicalize it to ``rel_key``. A ``resource`` that already resolves (a valid source,
    possibly a DIFFERENT one on a page this session merged into) or whose basename differs is left
    alone, so a legitimately different ``resource`` is never clobbered. For an in-repo source the
    agent's ``raw/x.md`` already equals ``rel_key``, so this is a no-op — the in-repo path is
    unchanged."""
    written = (resource or "").strip().replace("\\", "/")
    canon = rel_key.replace("\\", "/")
    if not written or written == canon:
        return None
    if config.source_path_for_key(written).is_file():
        return None  # already points at a real file — don't second-guess it
    same_basename = written.rsplit("/", 1)[-1] == canon.rsplit("/", 1)[-1]
    if same_basename and config.source_path_for_key(canon).is_file():
        return canon
    return None


def _validate_and_restamp(rel_paths: list[str], rel_key: str) -> list[str]:
    """Re-impose invariants on each changed page (``validate.validate_page``) and, if clean,
    canonicalize + re-stamp it through ``store.write_page`` (so the YAML is canonical, the
    ``type`` is enforced, and a fresh UTC ``timestamp`` is set even though the agent wrote the
    file). Before validating, a changed page whose ``resource`` is a shortened-but-broken reference
    to the source being ingested is canonicalized to its real key (:func:`_canonical_resource_key`),
    so an out-of-repo source the agent recorded as ``raw/<file>`` is repaired rather than failing the
    run. Returns one error string per error-severity validation issue; when any are returned the
    caller rolls the whole source back (all-or-nothing), so an invalid page never persists in the
    wiki — the issues are surfaced in the report instead."""
    errors: list[str] = []
    for rel_path in sorted(set(rel_paths)):
        try:
            page = store.read_page(rel_path)
        except (FileNotFoundError, okf.OKFError) as exc:
            errors.append(f"{rel_key}: re-read {rel_path}: {exc}")
            continue
        canonical = _canonical_resource_key(str(page.frontmatter.get("resource") or ""), rel_key)
        if canonical is not None:
            page.frontmatter["resource"] = canonical
        bad = [
            issue
            for issue in validate.validate_page(rel_path, page.frontmatter, page.body)
            if issue.severity == "error"
        ]
        if bad:
            for issue in bad:
                errors.append(f"{rel_key}: invalid page {rel_path}: {issue.category}: {issue.detail}")
            continue
        try:
            store.write_page(rel_path, page.frontmatter, page.body)
        except okf.OKFError as exc:
            errors.append(f"{rel_key}: rewrite {rel_path}: {exc}")
    return errors


def _repair_renames(before_pages: list[Page], created: list[str], deleted: list[str]) -> None:
    """Deterministic safety net for inbound links the agent may not have fully repointed.

    A page that was DELETED while a page with the SAME title was CREATED this source is a
    rename/move; repoint every inbound cross-link from the old path to the new one via the
    tested ``store.rewrite_links``. A merge into a page whose title CHANGES (or a pre-existing
    survivor) is not auto-derivable here — the agent is asked to repoint those itself, and
    ``find_broken_links``/``lint`` surface anything missed."""
    if not deleted or not created:
        return
    created_by_title: dict[str, list[str]] = {}
    for rel_path in created:
        try:
            page = store.read_page(rel_path)
        except (FileNotFoundError, okf.OKFError):
            continue
        title = str(page.frontmatter.get("title") or "").strip().lower()
        if title:
            created_by_title.setdefault(title, []).append(rel_path)

    before_by_path = {p.rel_path: p for p in before_pages}
    rename_map: dict[str, str] = {}
    for old in deleted:
        page = before_by_path.get(old)
        if not page:
            continue
        title = str(page.frontmatter.get("title") or "").strip().lower()
        matches = created_by_title.get(title, [])
        if title and len(matches) == 1 and matches[0] != old:
            rename_map[old] = matches[0]
    if rename_map:
        store.rewrite_links(rename_map)


# Deleting a directory tree can transiently fail or lag when the wiki lives on a network share
# (``CITADEL_WIKI_DIR`` pointing at an SMB/UNC path): a file may be momentarily locked (antivirus,
# indexing, an open handle) or the share may still report the directory present right after its
# contents were removed. Retry a handful of times before giving up.
_RMTREE_ATTEMPTS = 5


def _robust_rmtree(path: str | os.PathLike) -> None:
    """Best-effort recursive delete of a staging tree — the share-hardened
    :func:`config.robust_rmtree` under ingest's own name (it lives in ``config`` because resume's
    checkpoint slots need exactly the same read-only-bit/retry handling)."""
    config.robust_rmtree(path, attempts=_RMTREE_ATTEMPTS)


def _sha256(path: Path) -> str:
    """sha256 hexdigest of a file's bytes, streamed so a large page stays memory-bounded."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _files_equal(a: Path, b: Path) -> bool:
    """True if ``b`` exists and is byte-identical to ``a`` (size short-circuit, then content hash).
    A transient read error counts as 'not equal' so the safer path (re-copy) is taken."""
    try:
        if not b.exists():
            return False
        if a.stat().st_size != b.stat().st_size:
            return False
        return _sha256(a) == _sha256(b)
    except OSError:
        return False


def _robust_copy_file(src: Path, dst: Path, attempts: int = _RMTREE_ATTEMPTS) -> None:
    """Copy ``src`` -> ``dst`` ATOMICALLY: write a temp sibling, then ``os.replace`` it into place
    (atomic on one volume), retrying the network-share hiccups that flake a single copy. If every
    attempt fails the temp is cleaned up and the error is raised with ``dst`` LEFT UNTOUCHED — so a
    live page is never observed truncated/half-written (the caller fails the source and retries next
    run, keeping the page's previous content)."""
    tmp = dst.with_name(dst.name + ".citadeltmp")
    for attempt in range(attempts):
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            return
        except OSError:
            with contextlib.suppress(OSError):
                if tmp.exists():
                    tmp.unlink()
            if attempt == attempts - 1:
                raise  # leave dst as it was — never a half-written live page
            time.sleep(0.2 * (attempt + 1))


# Monotonic per-process counter so each staging dir gets a UNIQUE name — see _make_staging.
_STAGING_SEQ = 0
# Guards the counter itself: with `--jobs N` several workers mint staging names at once, and two
# sources sharing a staging directory is exactly the merge-into-leftover-content failure the unique
# name exists to prevent.
_STAGING_SEQ_LOCK = threading.Lock()

# THE serialization point for every touch of the LIVE wiki: cloning it into a staging copy (plus
# recording that clone's base state) and promoting a finished source back onto it. Sessions — the
# minutes-long part — run fully in parallel OUTSIDE this lock; what it serializes is milliseconds of
# file copying, so it costs throughput nothing and buys the two properties `--jobs N` needs:
#   * a staging copy is a point-in-time image of the live wiki, never a half-promoted mixture;
#   * two promotes can never interleave their copy-over and prune phases.
# It is a plain lock, not the workspace run lock (:mod:`runlock`): that one keeps two PROCESSES off
# one workspace, this one keeps two threads of ONE run off one live wiki.
_LIVE_WIKI_LOCK = threading.Lock()


def _staging_prefix(live: Path) -> str:
    """The shared filename prefix of this wiki's staging siblings (``.<name>.staging.``)."""
    return f".{live.name}.staging."


def _sweep_stale_staging(live: Path) -> None:
    """Best-effort removal of EVERY staging sibling of ``live`` — called ONCE at run start,
    under the exclusive workspace run lock (:mod:`runlock`), where any staging dir on disk is
    by definition a leftover from a dead run (they are inert dotfiles, but we don't let them
    pile up). This used to run inside every :func:`_make_staging` call, which is exactly what
    made two concurrent runs destructive: the first run's next source rm-tree'd the second
    run's IN-FLIGHT staging copy mid-session."""
    with contextlib.suppress(OSError):
        for sibling in live.parent.iterdir():
            if sibling.name.startswith(_staging_prefix(live)):
                _robust_rmtree(sibling)


def _make_staging(live: Path) -> Path:
    """Create a fresh STAGING copy of the live wiki and return its path.

    Staging is a SIBLING of the live wiki (same parent, same depth) — never a system temp dir —
    so every relative citation/cross-link the agent writes (``../../raw/x.md`` and page-to-page
    links) resolves identically before and after the promote. The agent edits this copy, so the
    live wiki is never the scratch space.

    The staging name is UNIQUE per call (pid + a monotonic counter), so a copy can NEVER merge into
    leftover content from a crashed run and resurrect pages that were deleted — the live wiki is
    always copied into a brand-new directory. Stale siblings from earlier crashed runs are swept
    once at run start (:func:`_sweep_stale_staging`), never here — a per-call sweep would delete a
    concurrent run's in-flight staging. On a copy failure the
    partial staging is cleaned up before the error propagates (the caller reports it and the live
    wiki is untouched). When the live wiki does not exist yet (first run) staging starts empty."""
    global _STAGING_SEQ
    parent = live.parent
    prefix = _staging_prefix(live)
    with _STAGING_SEQ_LOCK:
        _STAGING_SEQ += 1
        seq = _STAGING_SEQ
    staging = parent / f"{prefix}{os.getpid()}.{seq}"
    _robust_rmtree(staging)  # paranoia: clear an identical-named leftover before a clean copy
    try:
        if live.is_dir():
            # Skip any half-written *.citadeltmp left in live by an interrupted promote, so a stray
            # temp never rides along into staging (and back out again). A wiki-history `.git`
            # (wikigit) stays out too: _promote never syncs hidden dirs anyway, and copying a
            # whole repository per source would only burn I/O.
            shutil.copytree(live, staging, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.citadeltmp", ".git"))
        else:
            config.robust_mkdir(staging)
    except OSError:
        _robust_rmtree(staging)
        raise
    return staging


def _redirect_wiki(staging: Path):
    """Point every wiki-derived config path — and ``CITADEL_WIKI_DIR`` for the child processes the
    session spawns (the agentic CLI and the ``citadel check`` it shells out to) — at ``staging``
    for the duration of one session, so the agent reads/writes/validates the STAGING copy rather
    than the live wiki. The raw/docs dirs are left untouched.

    Thin alias for :func:`config.wiki_redirect`, kept under ingest's own name because this is where
    the staging discipline lives. The redirect is CONTEXT-local, not process-global: it never
    assigns ``config.WIKI_DIR`` or ``os.environ`` (the child's copy is built per spawn by
    ``config.child_env``), which is precisely what lets ``--jobs N`` keep several sources staged at
    once — each worker thread holds its own redirect, and the main thread still sees the live
    wiki."""
    return config.wiki_redirect(staging)


def _is_reserved_name(name: str) -> bool:
    """True for files the promote must NOT sync: the generated nav files (``index.md``/``log.md`` at
    any level), any dotfile (the ``.citadel_ingested.json`` manifest, etc.), and a half-written
    ``*.citadeltmp`` temp. Finalize regenerates the indexes and the ingest loop owns the manifest, so a
    per-source promote never lays a stale one down."""
    return name.startswith(".") or name in ("index.md", "log.md") or name.endswith(".citadeltmp")


def _content_files(root: Path) -> dict[str, Path]:
    """Map ``relposix -> abs path`` for every non-reserved file under ``root`` (skipping hidden
    dirs and :func:`_is_reserved_name` files) — the agent-authored content a promote syncs."""
    out: dict[str, Path] = {}
    if not Path(root).is_dir():
        return out
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in files:
            if _is_reserved_name(name):
                continue
            p = Path(dirpath) / name
            out[p.relative_to(root).as_posix()] = p
    return out


def _sha256_or_none(path: Path) -> str | None:
    """:func:`_sha256` that answers None instead of raising on an unreadable/vanished file — so a
    comparison against a recorded base hash treats it as "not what the base had" (the conservative
    answer) rather than blowing up a promote."""
    try:
        return _sha256(path)
    except OSError:
        return None


def _content_hashes(root: Path) -> dict[str, str]:
    """``{relposix: sha256}`` over :func:`_content_files` — a wiki's content state as bytes, not as
    timestamps. Taken (`--jobs N` only) of the fresh STAGING clone, which is byte-for-byte the live
    wiki this source started from, so its promote can tell "this page is exactly what I started
    from" from "another source changed it while I was working". A file that vanishes or cannot be
    read mid-walk is simply omitted, which reads as "absent" — the conservative answer, since it
    makes the promote treat it as changed rather than silently overwriting it."""
    out: dict[str, str] = {}
    for rel, path in _content_files(root).items():
        with contextlib.suppress(OSError):
            out[rel] = _sha256(path)
    return out


class _ConcurrentChange(Exception):
    """The live wiki moved under a staged source: a page this promote would write or prune is no
    longer what it was when the source was cloned, because a CONCURRENT source's promote (only
    possible under ``--jobs N``) landed there first.

    Never a data-loss path — it is raised BEFORE the promote writes anything, so the live wiki keeps
    the other source's work untouched. The caller re-runs this source SERIALLY, at the end of its
    group: the fresh session then sees the page the other source wrote and merges into it, which is
    exactly what a serial run would have done in the first place."""


def _assert_base_unchanged(live: Path, base: dict[str, str], rels: set[str]) -> None:
    """Raise :class:`_ConcurrentChange` if any of ``rels`` no longer matches ``base`` in the live
    wiki. Only the paths a promote is about to TOUCH are checked: a concurrent source that created
    or rewrote some unrelated page is no conflict at all — that is the whole point of running
    sources in parallel."""
    for rel in sorted(rels):
        target = live / rel
        current: str | None = None
        with contextlib.suppress(OSError):
            if target.is_file():
                current = _sha256(target)
        if current != base.get(rel):
            raise _ConcurrentChange(
                f"another source changed {rel} while this one was being folded in "
                "(re-running it serially so it merges into the current wiki)"
            )


def _promote(staging: Path, live: Path, allow_emptying: bool = False, base: dict[str, str] | None = None) -> None:
    """Copy a validated STAGING wiki's CONTENT onto the LIVE wiki WITHOUT ever emptying or
    half-writing it.

    Only the agent-authored content pages are synced — the generated ``index.md``/``log.md`` and the
    manifest are excluded (finalize regenerates the indexes; the loop owns the manifest), so a
    promote never lays a stale index down. Non-destructive order: every changed/new page is written
    into live FIRST (each atomically, via :func:`_robust_copy_file`), so at every instant the live
    wiki holds at least its previous content; only THEN are the pages the agent deleted pruned. A
    promote interrupted partway therefore leaves live a SUPERSET of valid pages — never an empty or
    corrupt tree — which a later full run reconciles. Directory creation tolerates the network
    share's WinError 183 race.

    Safety valve: an ingest/reconcile session must never reduce the live wiki to ZERO content pages.
    If staging carries no content page (a buggy/looping/adversarial session that deleted everything)
    while the live wiki has some, the promote is REFUSED — raising so the caller fails the source and
    retries it next run, with the live wiki left exactly as it was rather than emptied.
    ``allow_emptying`` lifts that guard for a ``delete`` cleanup, where removing the last source's
    only page legitimately leaves the wiki empty.

    ``base`` — the content hashes of the wiki this source was CLONED from (:func:`_content_hashes`
    over its staging copy, recorded only under ``--jobs N``) — makes the promote base-aware, which is what lets two sources
    promote onto one wiki without eating each other's work:

    * WHAT IS WRITTEN is this source's own delta — the staging files that differ from the BASE, not
      from the current live wiki. Staging also holds untouched copies of every page the source did
      not write, and judging those by "differs from live" would let this promote revert a page a
      concurrent source had just rewritten;
    * the PRUNE is likewise derived from the base, so a page a concurrent source created (absent
      from this source's base AND from its staging copy) is left alone instead of being deleted as
      "the agent removed it";
    * every path this promote would write or prune must still match the base, else
      :class:`_ConcurrentChange` is raised BEFORE anything is written and the source is re-run
      serially — the two sessions disagreed about one page, and a stale session must never win.

    ``base=None`` (the default, and the whole of the serial path) keeps the original semantics
    byte-for-byte: prune whatever live has and staging does not, no conflict check, no extra
    hashing."""
    staging, live = Path(staging), Path(live)
    config.robust_mkdir(live)

    staging_content = _content_files(staging)
    live_content = _content_files(live)

    staging_pages = [r for r in staging_content if r.endswith(".md")]
    # What "the wiki had pages" means for the anti-emptying valve: with a base, the wiki AS THIS
    # SOURCE FOUND IT — a page a concurrent source added in the meantime is not this session's to
    # answer for, in either direction.
    had_pages = [r for r in (live_content if base is None else base) if r.endswith(".md")]
    if not allow_emptying and not staging_pages and had_pages:
        raise okf.OKFError(
            "refusing to promote: the session left the wiki with no content pages "
            "(treated as a failed source so the live wiki is not emptied)"
        )

    if base is None:
        changed = {rel: src for rel, src in staging_content.items() if not _files_equal(src, live / rel)}
        pruned = set(live_content) - set(staging_content)
    else:
        # With a base, a promote applies THIS source's own delta and nothing else. Which pages the
        # source touched is decided against its base — not against the current live wiki — because
        # its staging copy also holds untouched copies of every page it did NOT write: judging by
        # "differs from live" would make a page a CONCURRENT source just rewrote look like this
        # source's change, and copying the staging copy over it would silently revert that work.
        changed = {rel: src for rel, src in staging_content.items() if _sha256_or_none(src) != base.get(rel)}
        pruned = (set(base) & set(live_content)) - set(staging_content)
        # NOTE for the reader: this is a per-FILE merge, not a per-line one. Two sources that wrote
        # the same page do not get merged here — that is what the conflict below is for.
        # Before the first byte is written: refuse a promote built on a wiki that has moved on.
        _assert_base_unchanged(live, base, set(changed) | pruned)
        # A page whose bytes already match live needs no write (a re-run that reproduced it exactly).
        changed = {rel: src for rel, src in changed.items() if not _files_equal(src, live / rel)}

    # 1. Copy-over FIRST (atomic per page, only when the bytes differ).
    for rel, src in changed.items():
        dst = live / rel
        config.robust_mkdir(dst.parent)
        _robust_copy_file(src, dst)

    # 2. Prune the content pages the agent deleted (reserved/generated files are left untouched).
    for rel in pruned:
        with contextlib.suppress(OSError):
            (live / rel).unlink()

    # 3. Best-effort sweep of any leftover *.citadeltmp from an earlier promote that was hard-killed
    #    between copyfile and os.replace. They are excluded from sync AND prune (reserved), so
    #    without this they could linger on the live wiki indefinitely.
    #    Only the CONTENT temps this step can actually have created are swept: a HIDDEN temp
    #    (`.citadel_ingested.json.<pid>.citadeltmp`) belongs to an in-flight atomic_write_text of the
    #    manifest/failures catalog — under `--jobs N` the main thread is saving one of those while a
    #    worker promotes, and deleting it out from under the writer turned a routine manifest save
    #    into a FileNotFoundError. Those temps are the writer's own to clean up.
    with contextlib.suppress(OSError):
        for dirpath, dirnames, filenames in os.walk(live):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if name.startswith(".") or not name.endswith(".citadeltmp"):
                    continue
                with contextlib.suppress(OSError):
                    (Path(dirpath) / name).unlink()

    # 4. Drop directories left empty by the prune (bottom-up), but keep the live root itself.
    #    Hidden trees are exempt, exactly like the sync/prune above (_content_files skips them):
    #    a wiki-history `.git` legitimately holds empty dirs (a fresh repo's objects/ and refs/ —
    #    removing them corrupts the repository), and the same goes for e.g. an `.obsidian/`.
    for dirpath, _dirs, _files in os.walk(live, topdown=False):
        d = Path(dirpath)
        if d == live:
            continue
        if any(part.startswith(".") for part in d.relative_to(live).parts):
            continue
        with contextlib.suppress(OSError):
            if not any(d.iterdir()):
                d.rmdir()


@dataclass
class _SourceOutcome:
    """Result of one agent-driven source (ingest / reconcile / delete). ``ok`` means the edit
    was validated and promoted onto the live wiki (the caller still updates the manifest + report);
    ``ok is False`` means nothing was promoted — the live wiki is unchanged — and ``errors`` says
    why. ``usage`` is what the source's session(s) reported costing (segments combined; also set
    on a FAILED outcome when earlier segments completed — that money was spent even though the
    work was rolled back), or None when no session reported anything."""

    ok: bool
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    usage: llm.SessionUsage | None = None
    # What EARLIER runs already paid for the segments a resume checkpoint restored. Kept apart from
    # ``usage`` on purpose: the run report must count only what THIS run spent (the earlier run
    # reported its own), while the manifest stamp must cover every session whose work is in the
    # wiki — "one combined usage, matching promote-once semantics" — across the runs that produced
    # it. Like every manifest stamp it is success-only: a FAILED attempt's spend stays on the run
    # report that paid it, exactly as for a single-session source.
    carried_usage: llm.SessionUsage | None = None
    # Human-readable note when this source continued from a checkpoint ("" when it did not).
    resumed_note: str = ""
    # `--jobs N` only: the session was clean, but a CONCURRENT source's promote had changed a page
    # this one would have written (:class:`_ConcurrentChange`), so nothing was promoted. Not a
    # failure — the caller re-runs the source serially before the run ends, and only if THAT fails
    # does it become one.
    conflict: bool = False


@dataclass
class _Resume:
    """One chunked source's resume context (:mod:`citadel.resume`) — the identity of its
    multi-segment job plus the checkpoint an earlier run left, if any is still adoptable.

    Built by the pending-file job (only there: a repo digest, an image, a deletion cleanup and a
    curate cluster are all single-session, so there is nothing to resume), and consumed by
    :func:`_run_agent_sessions`. ``checkpoint`` is set to None the moment a guard refuses it, so
    the runner's own fallback path and the caller see the same "start at segment 1" state."""

    plan: resume.Plan
    checkpoint: resume.Checkpoint | None = None


def _plan_shape(passes) -> str:
    """Fingerprint a chunked source's pass plan by CONTENT — the chunking threshold, each pass's
    segment/line-window position, and the sha256 of the prepared text it hands the agent.

    Deliberately not the temp PATHS (``_office_write_temp`` mints a fresh random dir every run) and
    deliberately not just the segment count: an extraction change (a pypdf upgrade, a
    re-transcription, a re-tuned ``CITADEL_MAX_SOURCE_CHARS``) can keep the count while moving the
    boundaries, and "segment 3" would then name text its predecessor never saw. "" means the shape
    could not be determined — the caller then simply does not checkpoint."""
    digest = hashlib.sha256(f"{config.MAX_SOURCE_CHARS}".encode())
    for read_key, segment, window in passes:
        digest.update(f"\x1e{segment}|{window}|".encode())
        if read_key:
            try:
                # A read_key is workspace-RELATIVE when the temp landed inside the workspace and
                # absolute otherwise (config.rel_or_abs_posix) — resolve it the same way every
                # other consumer does, never as a bare Path against this process's CWD.
                digest.update(_sha256(config.source_path_for_key(read_key)).encode("ascii"))
            except (OSError, okf.OKFError, ValueError):
                return ""
    return digest.hexdigest()


def _resume_context(rel_key: str, kind: str, sha: str | None, passes, model: str, rules_ver: str) -> _Resume | None:
    """The :class:`_Resume` context for one pending source, or None when resume does not apply.

    It applies to CHUNKED sources only (a single-pass source has no earlier segment to save) and
    only when discovery actually hashed the file: a null sha would make the identity check compare
    ``None == None`` and could re-adopt a checkpoint after the source's bytes changed — sha256 is
    the sole arbiter of "changed" everywhere else, and it stays so here. An indeterminable pass
    shape (a temp read file that vanished) likewise opts the source out rather than guessing.

    Adopting a checkpoint COUNTS (``resume.note_attempt``): a segment that fails deterministically
    would otherwise re-fail cheaply and quietly forever, so after :data:`resume.ATTEMPT_CAP`
    fruitless resumes the checkpoint is dropped and the source is retried in full.

    A FORCED re-read (``--force``, and therefore ``citadel refresh``) deliberately still resumes:
    force means "read this source again now", and an interrupted forced re-read is exactly the
    expensive job worth continuing — a `refresh` slice that dies at segment 5 of 7 should not have
    to re-buy segments 1-4 on the next scheduled run. It cannot cross-adopt a normal run's work
    either way, since forcing changes the session ``kind`` (reconcile, not ingest) and the kind is
    part of the identity."""
    if not resume.enabled() or len(passes) < 2 or not sha:
        return None
    shape = _plan_shape(passes)
    if not shape:
        return None
    plan = resume.Plan(
        key=rel_key,
        sha=sha,
        kind=kind,
        model=model,
        rules_version=rules_ver,
        total=len(passes),
        shape=shape,
        knobs=resume.knob_stamp(),
    )
    checkpoint = resume.load(plan)
    if checkpoint is not None:
        resume.note_attempt(checkpoint)
    return _Resume(plan=plan, checkpoint=checkpoint)


def _usage_from_fields(fields: dict) -> llm.SessionUsage | None:
    """The inverse of :func:`_usage_fields`: a manifest-shaped usage dict (as carried in a resume
    checkpoint) back into a :class:`llm.SessionUsage`, or None when it says nothing."""
    if not fields:
        return None
    return llm.SessionUsage(
        cost_usd=fields.get("cost_usd"),
        input_tokens=fields.get("tokens_in"),
        output_tokens=fields.get("tokens_out"),
        aic=fields.get("aic"),
    )


def _usage_fields(usage: llm.SessionUsage | None) -> dict:
    """A source's combined session usage as ``manifest.make_entry`` / ``make_repo_entry`` kwargs
    (``cost_usd``/``tokens_in``/``tokens_out``/``aic``, only the known fields) — the
    one translation from the llm-layer shape to the manifest-layer stamp, so the done-hooks stay
    one-liners. ``model`` is deliberately NOT part of this: it is provenance, stamped through
    :func:`_stamp_model` into the entry's own ``model`` field, not usage."""
    if usage is None:
        return {}
    out: dict = {}
    for key, value in (
        ("cost_usd", usage.cost_usd),
        ("aic", usage.aic),
        ("tokens_in", usage.input_tokens),
        ("tokens_out", usage.output_tokens),
    ):
        if value is not None:
            out[key] = value
    return out


def _stamp_model(usage: llm.SessionUsage | None, fallback: str) -> str:
    """The model label to RECORD for a finished source: what the backend reported actually
    serving the session (``config.model_label_for``), else ``fallback`` — the run's configured
    label (``config.ingest_model_label``). The reported id is the only honest one: the configured
    model is a request the backend may not have honored (``auto``, a fallback, a stale ``.env``),
    and a wiki that claims an unused model misleads every later audit of its provenance."""
    reported = usage.model if isinstance(usage, llm.SessionUsage) else None
    return config.model_label_for(reported) if reported else fallback


def _sha_shared_by_other_entry(manifest_dict: dict, sha: str | None, exclude_key: str) -> bool:
    """True when a manifest entry OTHER than ``exclude_key`` still records content hash ``sha``.

    The transcript/PDF caches are CONTENT-addressed (keyed by sha256), so two byte-identical
    sources under different keys share ONE cache file. Pruning that file when one of them changes
    or is deleted would break offline verification (lint/``wiki_raw``/viewer) for the survivors
    until they re-extract. This guard gates every prune: only the LAST reference to a sha may
    drop its cache entry. Repo entries carry a commit identity, not a content sha, so they never
    hold a transcript/PDF cache entry and are skipped."""
    if not sha:
        return False
    for key, entry in manifest_dict.items():
        if key == exclude_key or manifest.is_repo_entry(entry):
            continue
        if manifest.entry_sha(entry) == sha:
            return True
    return False


def _checkpoint_delta(
    staging: Path, live: Path, base: dict[str, str] | None = None
) -> tuple[list[str], list[str]] | None:
    """``(changed, removed)`` — this source's own delta, exactly as :func:`_promote` computes it —
    or None when it must not be recorded at all.

    Computed with the PROMOTE's own file-level view (:func:`_content_files` + :func:`_files_equal`),
    never from the per-segment page diffs: those miss the link repairs ``_repair_renames`` writes
    into pages no session touched (and any non-``.md`` file), and their union across segments can
    even resurrect a page a later segment deliberately deleted. A checkpoint must describe exactly
    what would have shipped, so it is derived from exactly what ships.

    ``base`` — the clone snapshot, present only under ``--jobs N`` — is what keeps that true when
    the wiki is moving. Measured against the CURRENT live wiki, a page a CONCURRENT source created
    between this source's clone and this checkpoint reads as "in live, not in my staging", i.e. as a
    deletion THIS source made, and one it rewrote reads as a change of this source's with the clone's
    stale bytes. A checkpoint is durable, so such a delta outlives the parallel run: replayed by a
    later — even strictly serial — run, it deletes a fully-ingested source's page off the live wiki
    with no conflict, no error and no delete session. Measured against the base, the delta is this
    source's alone (the promote's exact rule), and the concurrent work is simply not in it.

    The refusal mirrors the promote's anti-emptying valve: a staging tree with no content page while
    the wiki this source started from had some is a wipe-the-wiki delta (a vanished/rm-tree'd staging
    reads exactly like this), and :func:`_promote` would refuse it — so it must never be persisted as
    a replayable one."""
    staged = _content_files(staging)
    started_from = _content_files(live) if base is None else base
    if not [rel for rel in staged if rel.endswith(".md")] and [rel for rel in started_from if rel.endswith(".md")]:
        return None
    if base is None:
        changed = sorted(rel for rel, src in staged.items() if not _files_equal(src, live / rel))
    else:
        changed = sorted(rel for rel, src in staged.items() if _sha256_or_none(src) != base.get(rel))
    removed = sorted(set(started_from) - set(staged))
    return changed, removed


def _adopt_checkpoint(ctx: _Resume, staging: Path, live: Path, rel_key: str) -> tuple[list, list, list] | None:
    """Replay ``ctx``'s checkpoint into the fresh ``staging`` copy and return the
    ``(created, updated, deleted)`` it landed there, or None when it must not be used.

    Three gates, in cost order — all offline, all before a single agent token is spent:

    1. the base-state guard (:func:`resume.replay`): every page the delta touches must still be, in
       the live wiki, what it was when the checkpoint was written;
    2. re-validation of every replayed page — the same ``_validate_and_restamp`` every agent pass
       goes through, so a page whose cited raw source has since been deleted can never be promoted
       (it also re-stamps the timestamps, which would otherwise be the earlier run's);
    3. no cross-link may be broken that the live wiki did not already have broken — ``validate_page``
       has no cross-page view, and a link target removed between runs would otherwise land as a
       fresh dangling link on an already-promoted wiki.

    Returning None is NEVER a source failure: the caller drops the checkpoint and restarts the
    source at segment 1 in this same run, which is exactly the pre-resume behavior."""
    with _redirect_wiki(staging):
        # Baseline the cross-links BEFORE the replay: staging is still a byte copy of live here, so
        # this is the set of breakages the wiki already lives with (which resume must not be blamed
        # for, and must not repair).
        before_broken = set(store.find_broken_links(store.load()))
        written = resume.replay(ctx.checkpoint, staging, live)
        if written is None:
            return None
        # Validate exactly what the replay put on disk (its return value, not the record's own
        # list): a delta it could not apply in full has already refused above.
        if _validate_and_restamp([rel for rel in written if rel.endswith(".md")], rel_key):
            return None
        if set(store.find_broken_links(store.load())) - before_broken:
            return None
    # Classify by the recorded base state, so the run report/log/progress counts describe what the
    # promote will actually land — a resumed source that says "2 created" while 22 pages appear is
    # the exact converse of the report-claims-only-what-is-live rule. Only PAGES are reported: the
    # delta is the promote's file-level set (any non-reserved file), while the report's vocabulary
    # is the page diff's, so a stray non-`.md` file is replayed but never counted as a page.
    pages = [rel for rel in ctx.checkpoint.pages if rel.endswith(".md")]
    created = sorted(rel for rel in pages if ctx.checkpoint.bases.get(rel) is None)
    updated = sorted(rel for rel in pages if ctx.checkpoint.bases.get(rel) is not None)
    return created, updated, sorted(rel for rel in ctx.checkpoint.removed if rel.endswith(".md"))


def _write_checkpoint(
    ctx: _Resume, completed: int, staging: Path, live: Path, usage: dict, base: dict[str, str] | None = None
) -> None:
    """Record ``completed`` segments' work for this source. Best-effort by contract — any failure
    just means the next run starts at segment 1, so nothing here may raise into the session loop.

    Cost: one staging↔live comparison plus a copy of the (growing) delta per segment, i.e. O(wiki)
    per segment for a chunked source. Deliberately paid rather than optimized: deriving the delta
    from the promote's own view is what makes a replay equivalent to an unbroken run, and this is
    strictly cheaper than the per-source staging COPY the same run already makes — and invisible
    beside the agent session each segment costs."""
    try:
        delta = _checkpoint_delta(staging, live, base)
        if delta is not None:
            # `base` travels on to resume.save as the state the delta must be guarded against: the
            # wiki this source was CLONED from, not the (possibly moved-on) live wiki at save time.
            # Recording the latter would have the replay guard verify "live unchanged since I
            # saved" while the delta means "live as of my clone" — the wrong invariant, and one a
            # concurrent promote slips straight through.
            resume.save(ctx.plan, completed, staging, live, delta[0], delta[1], usage, bases=base)
    except Exception:  # noqa: BLE001 - a checkpoint may never cost a run its source
        pass


def _run_agent_sessions(
    session_fns,
    rel_key: str,
    extra_check=None,
    allow_emptying: bool = False,
    resume_ctx: _Resume | None = None,
    concurrent: bool = False,
) -> _SourceOutcome:
    """Run one source's agent session(s) — a single pass, or every segment of a chunked source —
    against ONE staging copy, with full all-or-nothing safety. Shared by every job kind
    (ingest/reconcile, repo, deletion cleanup).

    Makes a STAGING copy of the live wiki (a sibling dir), redirects the agent + its ``citadel
    check`` there, then for EACH ``session_fn`` in order: snapshots staging, calls the session
    (the agent edits the STAGING copy — never the live wiki), diffs to learn what that pass
    changed, validates + re-stamps the changed pages (fail fast: an invalid segment stops the
    source right there — later segments never run), and repoints renamed-page links. A later
    segment therefore sees — and merges into — what the earlier segments wrote in the SAME
    staging copy. After the last session an optional ``extra_check()`` post-condition runs (used
    by deletion cleanup to assert no reference to the removed source survived).

    PROMOTION HAPPENS EXACTLY ONCE, after the last session passes (no silently partial imports): the non-destructive copy-over-then-prune that can never empty
    or half-write the live wiki, which thus only ever contains FULLY imported sources. A
    failure/timeout/interrupt at segment N still discards the whole staging copy and promotes
    NOTHING — that part of the trade-off is the guarantee itself and does not move.

    What ``resume_ctx`` changes is only who pays for it again. With a resume context (chunked
    sources only — :func:`_resume_context`), each completed segment records the delta it produced
    as a checkpoint beside the wiki, and a later run REPLAYS that delta into its fresh staging copy
    and continues at segment N instead of re-buying segments 1..N-1 (:mod:`citadel.resume`). The
    replay is gated offline — base state, re-validation, no new broken links — and any refusal
    falls back to a clean staging copy and segment 1 IN THIS RUN, so the pre-resume behavior is the
    floor, never the failure mode. ``CITADEL_RESUME=0`` (or any non-chunked source) skips the
    machinery entirely.

    On ANY failure — a validation error, a failed post-condition, or an exception from a session
    — the live wiki is left exactly as it was and ``ok`` is False; the caller leaves the source
    un-committed so it is retried next run. A propagating ``BaseException`` (Ctrl+C) during a
    session likewise leaves the live wiki untouched (nothing is promoted); during the brief
    promote it can leave that ONE source partially applied — a SUPERSET of valid pages, never an
    emptied wiki — which a later full run reconciles. Either way it re-raises for the caller's
    loop to capture. Staging is always discarded in ``finally``. The caller owns the manifest +
    report bookkeeping (different for a completed source vs. a removed one).

    ``concurrent`` (set only by the ``--jobs N`` driver) says another source may be staging or
    promoting at the same time. It changes nothing about a session — it makes the two moments that
    touch the LIVE wiki safe under that: the clone is taken under :data:`_LIVE_WIKI_LOCK` together
    with a hash snapshot of what was cloned, and the promote runs under the same lock against that
    base (see :func:`_promote`). A promote refused because a concurrent source got to one of these
    pages first comes back as ``conflict`` rather than an error — the driver re-runs the source
    serially, and the live wiki is untouched either way.

    An EMPTY ``session_fns`` (a deleted source nothing cites) succeeds immediately with zero page
    changes — before a staging copy is even made."""
    started = time.monotonic()
    if not session_fns:
        return _SourceOutcome(True)
    live = config.wiki_dir()
    base: dict[str, str] | None = None
    staging: Path | None = None
    created: list[str] = []
    updated: list[str] = []
    deleted: list[str] = []
    # Each session's backend-reported usage (None from the test fakes / silent backends),
    # combined into the outcome on EVERY return path — a rolled-back source still spent money.
    usage_parts: list[llm.SessionUsage | None] = []
    # What earlier runs already paid for the segments a checkpoint restores (see _SourceOutcome).
    carried: dict = {}
    resumed_note = ""

    def clone() -> tuple[Path, dict[str, str] | None]:
        """A staging copy of the live wiki plus (concurrent runs only) the base state it copied.

        The lock covers the COPY alone; the base is then hashed off the fresh staging tree, which
        is a byte-exact copy of exactly what was cloned — same hashes, half the disk I/O (the wiki
        is read once, not twice), and every other worker's clone/promote is unblocked that much
        sooner. It must still happen HERE, before anything mutates staging: a resume replay writes
        into it a few lines below, and those pages are not part of the wiki this source started
        from."""
        with _LIVE_WIKI_LOCK:
            staging = _make_staging(live)
        return staging, (_content_hashes(staging) if concurrent else None)

    try:
        staging, base = clone()
        # RESUME: replay an earlier run's completed segments into this fresh staging copy, so only
        # the remaining ones have to be paid for again. Every guard failure falls back to a full
        # start on a clean staging copy IN THIS RUN — never a failed source, never a wasted session.
        start_at = 0
        if resume_ctx is not None and resume_ctx.checkpoint is not None:
            seeded = _adopt_checkpoint(resume_ctx, staging, live, rel_key)
            if seeded is None:
                resume.clear(rel_key)
                resume_ctx.checkpoint = None
                _robust_rmtree(staging)
                staging, base = clone()
            else:
                created, updated, deleted = list(seeded[0]), list(seeded[1]), list(seeded[2])
                start_at = resume_ctx.checkpoint.completed
                carried = dict(resume_ctx.checkpoint.usage)
                resumed_note = f"{rel_key} (segments 1-{start_at} of {len(session_fns)} restored from checkpoint)"
        with _redirect_wiki(staging):
            prev_pages = store.load()
            prev = _hash_pages(prev_pages)
            for i in range(start_at, len(session_fns)):
                result = session_fns[i]()  # the agent edits the STAGING copy, never the live wiki
                usage_parts.append(result if isinstance(result, llm.SessionUsage) else None)

                after = _snapshot()
                seg_created, seg_updated, seg_deleted = _diff(prev, after)

                val_errors = _validate_and_restamp(seg_created + seg_updated, rel_key)
                if val_errors:
                    return _SourceOutcome(
                        False,
                        errors=val_errors,
                        seconds=time.monotonic() - started,
                        usage=llm.combine_usage(usage_parts),
                        carried_usage=_usage_from_fields(carried),
                        resumed_note=resumed_note,
                    )

                _repair_renames(prev_pages, seg_created, seg_deleted)

                created.extend(seg_created)
                updated.extend(seg_updated)
                deleted.extend(seg_deleted)
                if resume_ctx is not None:
                    # AFTER the rename repairs (they are part of what would be promoted) and before
                    # the re-baseline. Written for the LAST segment too: a promote that then fails
                    # leaves the whole source replayable for free instead of re-buying every pass.
                    _write_checkpoint(
                        resume_ctx,
                        i + 1,
                        staging,
                        live,
                        _usage_fields(llm.combine_usage([*usage_parts, _usage_from_fields(carried)])),
                        base,
                    )
                if i + 1 < len(session_fns):
                    # Re-baseline on the validated/re-stamped state, so the next segment's diff
                    # (and its validation) covers exactly what THAT segment changes. Nothing
                    # consumes it after the LAST session, so it is skipped there.
                    prev_pages = store.load()
                    prev = _hash_pages(prev_pages)

            if extra_check is not None:
                post_errors = extra_check()
                if post_errors:
                    return _SourceOutcome(
                        False,
                        created,
                        updated,
                        deleted,
                        post_errors,
                        time.monotonic() - started,
                        usage=llm.combine_usage(usage_parts),
                        carried_usage=_usage_from_fields(carried),
                        resumed_note=resumed_note,
                    )

        # Every session was clean: commit the source onto the live wiki (config now points back
        # at live). This is the ONLY step that touches the live wiki, it happens ONCE per source,
        # and it is non-destructive — so an interrupt here still cannot empty it. Under `--jobs N`
        # it is also the only step that has to exclude its siblings (one promote at a time, checked
        # against the state this source was cloned from).
        with _LIVE_WIKI_LOCK:
            _promote(staging, live, allow_emptying=allow_emptying, base=base)
        if resume_ctx is not None:
            resume.clear(rel_key)  # the work is live now: the checkpoint has nothing left to save
        return _SourceOutcome(
            True,
            created,
            updated,
            deleted,
            [],
            time.monotonic() - started,
            usage=llm.combine_usage(usage_parts),
            carried_usage=_usage_from_fields(carried),
            resumed_note=resumed_note,
        )
    except _ConcurrentChange as exc:
        # Not a failure: the work was fine, the wiki simply moved under it (only reachable with
        # `--jobs N`). Nothing was promoted, so the live wiki still holds the OTHER source's
        # version; the driver re-runs this source serially against it. The spend is reported like
        # any other — that session was paid for.
        return _SourceOutcome(
            False,
            errors=[f"{rel_key}: {exc}"],
            seconds=time.monotonic() - started,
            usage=llm.combine_usage(usage_parts),
            carried_usage=_usage_from_fields(carried),
            resumed_note=resumed_note,
            conflict=True,
        )
    except Exception as exc:  # noqa: BLE001 - collect per-source, keep going; live wiki untouched
        # A raising session never returned its usage, but the backend may still have reported
        # what the FAILED attempt cost (claude's error envelope, copilot/agy's stdout stream) — llm
        # carries that on the exception, so the run total honors "failed sessions included".
        salvaged = getattr(exc, "session_usage", None)
        usage_parts.append(salvaged if isinstance(salvaged, llm.SessionUsage) else None)
        return _SourceOutcome(
            False,
            errors=[f"{rel_key}: {exc}"],
            seconds=time.monotonic() - started,
            usage=llm.combine_usage(usage_parts),
            carried_usage=_usage_from_fields(carried),
            resumed_note=resumed_note,
        )
    finally:
        # Discard staging on every exit (a clean source already promoted it; a failed or
        # interrupted one never touched the live wiki). A flaky share that refuses the delete only
        # leaves an inert sibling for the next run to clear — the live wiki is never at risk.
        if staging is not None:
            _robust_rmtree(staging)


@dataclass
class _SourceJob:
    """ONE per-source unit of agent-driven work — the shared shape behind :func:`ingest`'s single
    per-source loop (the three near-duplicate loops — pending files,
    repos, deletion cleanups — collapse behind this; :func:`_run_source_jobs` owns the
    emit/report/failures vocabulary once).

    - ``key``: the source key — the report/failures/progress identity.
    - ``build_sessions``: plans the source's agent session(s), returning ``(session_fns, tmpdirs,
      resume_ctx)``: the callables run in order against ONE shared staging copy
      (:func:`_run_agent_sessions`), the temp dirs the loop removes afterwards, and — for a CHUNKED
      source only — the :class:`_Resume` context that lets the runner continue from an earlier
      run's checkpoint (None everywhere else: every other job kind is a single session). It may
      raise — recorded as a per-source ``prepare_error`` failure, never aborting the run. An EMPTY
      session list means there is nothing for an agent to do (a deleted source nothing cites):
      the job succeeds immediately with zero page changes.
    - ``on_success``: the post-success bookkeeping that differs per kind — the manifest stamp
      (``mark_done`` / repo entry / key drop), clearing the failure record, the per-source
      manifest save, and which report list the source lands in. Takes exactly one argument, the
      outcome's combined session usage (``llm.SessionUsage | None``) so the manifest stamp can
      record what the verification cost; the page changes already went into the report before it
      runs, so a job needs no view of the diff.
      (``citadel curate`` deliberately BYPASSES ``_SourceJob`` — its per-cluster report, different
      vocabulary, and NOOP outcome do not fit here — and rides :func:`_run_agent_sessions`
      directly, so nothing consumes a per-source outcome through this seam.)
    - ``extra_check``/``allow_emptying``: passed through to the session runner (deletion cleanup
      asserts no reference survived and may legitimately empty the wiki).
    - ``sha_stat``: the (sha256, stat) discovery already took for the source, threaded into the
      failures catalog so an unchanged stuck source joins the stat quick check.
    - ``warn_no_pages``: True for a FRESH source (a plain ingest of a new key, file or repo) —
      a successful session that then changed NOTHING lands on ``report.no_pages`` as a warning.
      Deliberately False for reconciles (an unchanged verdict is a legitimate outcome of
      re-reading a source, and ``citadel refresh`` would otherwise flag its whole slice) and for
      delete cleanups (empty means nothing cited the source — the expected case).
    """

    key: str
    build_sessions: Callable[[], tuple[list[Callable[[], llm.SessionUsage | None]], list[str], "_Resume | None"]]
    on_success: Callable[[llm.SessionUsage | None], None]
    prepare_error: str
    extra_check: Callable[[], list[str]] | None = None
    allow_emptying: bool = False
    sha_stat: tuple[str | None, os.stat_result | None] = (None, None)
    warn_no_pages: bool = False


@dataclass
class _JobRun:
    """One ATTEMPT at one source, as the driver sees it — the value a worker hands back.

    Exactly one of the three outcome fields is set: ``prepare_exc`` (planning raised — a per-source
    failure, never a run-aborting one), ``interrupt`` (a ``BaseException`` such as Ctrl+C escaped the
    session runner, which already rolled the source back), or ``outcome`` (the session runner's
    verdict, including a ``conflict`` that asks for a serial re-run). ``index``/``total`` are the
    source's position in its group — carried on the run so a re-run keeps the number the progress
    output already showed."""

    job: _SourceJob
    index: int
    total: int
    outcome: _SourceOutcome | None = None
    prepare_exc: Exception | None = None
    interrupt: BaseException | None = None


def _attempt_source(job: _SourceJob, index: int, total: int, emit, concurrent: bool) -> _JobRun:
    """Plan and run ONE source's session(s) — the whole minutes-long part — and return what
    happened, touching NO shared bookkeeping. That is what makes it safe to call from a worker
    thread under ``--jobs N``: the report, the manifest and the failures catalog are the main
    thread's alone (:func:`_record_source_run`), so nothing here needs a lock beyond the live-wiki
    one the session runner takes around its clone and promote."""
    # Keep the run lock's mtime fresh at every source boundary, so a long multi-source run never
    # crosses the staleness window another process could reclaim the lock through.
    runlock.heartbeat()
    emit("source_start", index=index, total=total, source=job.key)
    run = _JobRun(job=job, index=index, total=total)
    # Plan the session(s). A prepare failure (a temp write, a digest build) is a per-source error,
    # NOT a run-aborting one.
    try:
        sessions, tmpdirs, resume_ctx = job.build_sessions()
    except Exception as exc:  # noqa: BLE001 - per-source, keep going
        run.prepare_exc = exc
        return run
    try:
        run.outcome = _run_agent_sessions(
            sessions,
            job.key,
            extra_check=job.extra_check,
            allow_emptying=job.allow_emptying,
            resume_ctx=resume_ctx,
            concurrent=concurrent,
        )
    except BaseException as exc:  # noqa: BLE001 - Ctrl+C etc.: runner rolled back; captured
        run.interrupt = exc
    finally:
        # Always remove every temp dir the plan produced (success, error, or interrupt).
        for tmp in tmpdirs:
            shutil.rmtree(tmp, ignore_errors=True)
    return run


def _record_spend(outcome: _SourceOutcome, report: IngestReport) -> None:
    """Book what one attempt COST and what it REUSED — the two facts that hold whatever its verdict
    was, so they have exactly one owner instead of one per branch.

    The run's usage total counts every outcome: a failed (or raced) source's sessions were paid for
    too; only the per-source manifest stamp is success-only. A restored checkpoint is recorded the
    same way — the earlier segments were reused whether or not this attempt went on to promote.

    Called from :func:`_record_source_run` and, separately, from the ``--jobs N`` conflict path,
    whose source is re-run serially instead of being recorded: it still spent a session and may
    still have replayed a checkpoint, and a report that hid that would be understating the run.
    Deliberately NOT wired through the interrupt path: an interrupted run re-raises and its report
    is never rendered (_ingest_run's capture-finalize-reraise), so the in-flight source's partial
    usage has no surface to appear on — the completed sources' manifest stamps were already saved
    per-source with their usage intact."""
    report.usage = llm.combine_usage([report.usage, outcome.usage])
    # The first session that NAMES its model upgrades the report's label from "what we asked for"
    # to "what actually ran" (the manifest entries are stamped with the same id per source).
    if isinstance(outcome.usage, llm.SessionUsage) and outcome.usage.model:
        report.model = config.model_label_for(outcome.usage.model)
    if outcome.resumed_note:
        report.resumed.append(outcome.resumed_note)


def _record_source_run(run: _JobRun, emit, report: IngestReport, failures_dict, model) -> None:
    """Book ONE finished attempt into the run's shared state — report lists, the persistent
    failures catalog, the job's success hook (manifest stamp + save), and the closing progress
    event. MAIN THREAD ONLY, so the manifest/failures/report writes stay single-threaded exactly as
    they were before ``--jobs N``; the concurrency lives entirely in :func:`_attempt_source`.

    Page changes reach the report only on success — a failed or interrupted source promotes
    nothing, so the report claims nothing for it. A ``conflict`` outcome never reaches here: the
    driver re-runs that source serially first."""
    job, index, total = run.job, run.index, run.total
    sha, st = job.sha_stat
    if run.prepare_exc is not None:
        detail = f"{job.key}: {job.prepare_error}: {run.prepare_exc}"
        report.errors.append(detail)
        failures.record(failures_dict, job.key, failures.ERROR, detail, model, sha=sha, st=st)
        emit("source_error", index=index, total=total, source=job.key, error=str(run.prepare_exc), seconds=0.0)
        return
    outcome = run.outcome
    if outcome is None:  # an interrupted attempt: the caller re-raises, nothing to book
        return
    _record_spend(outcome, report)  # cost + any restored checkpoint, before the ok/failed branch
    if not outcome.ok:
        # Nothing was promoted (the live wiki is untouched) and the source is NOT marked
        # done, so it is retried next run. Persist the failure for triage.
        report.errors.extend(outcome.errors)
        detail = outcome.errors[0] if outcome.errors else f"{job.key}: agent session failed"
        failures.record(failures_dict, job.key, failures.reason_for(detail), detail, model, sha=sha, st=st)
        emit(
            "source_error",
            index=index,
            total=total,
            source=job.key,
            error=outcome.errors[0] if outcome.errors else "",
            seconds=outcome.seconds,
        )
        return
    report.pages_created.extend(outcome.created)
    report.pages_updated.extend(outcome.updated)
    report.pages_written.extend(outcome.created + outcome.updated)
    report.pages_deleted.extend(outcome.deleted)
    if job.warn_no_pages and not (outcome.created or outcome.updated or outcome.deleted):
        # A fresh source folded in with zero page changes: marked done below, so without this
        # warning it would silently never contribute anything (see IngestReport.no_pages).
        report.no_pages.append(job.key)
    # The manifest stamp covers every session whose work this promote landed — this run's plus
    # whatever an earlier run already paid for the segments a checkpoint restored — while
    # ``report.usage`` above stays strictly this run's spend, so nothing is double-counted
    # across runs and `citadel status` never under-reports a resumed source.
    stamped = llm.combine_usage([outcome.usage, outcome.carried_usage])
    job.on_success(stamped)
    emit(
        "source_done",
        index=index,
        total=total,
        source=job.key,
        created=len(outcome.created),
        updated=len(outcome.updated),
        deleted=len(outcome.deleted),
        seconds=outcome.seconds,
        # The console reports what THIS run spent (matching the run report's total), but names the
        # model from the full stamp — a resumed source's model is known even when every segment
        # this run ran came back from a checkpoint.
        usage=outcome.usage,
        model=getattr(stamped, "model", None),
    )


def _run_source_jobs(
    jobs: list[_SourceJob], emit, report: IngestReport, failures_dict, model, workers: int = 1
) -> BaseException | None:
    """Drive one GROUP of :class:`_SourceJob`s (deletion cleanups, files, or repos) through the
    ONE shared per-source loop: emit ``source_start``, plan the session(s), run them all-or-nothing
    against a single staging copy, then either record the failure (report + persistent failures
    catalog + ``source_error``) or run the job's success bookkeeping and emit ``source_done``.

    The progress vocabulary is frozen (pinned by tests): ``index``/``total`` count within THIS
    group, restarting at 1 per group, and the event payload keys are exactly what the three
    former loops emitted. Page changes reach the report only on success — a failed or interrupted
    source promotes nothing, so the report claims nothing for it.

    ``workers`` > 1 (``citadel ingest --jobs N``) runs that many sources CONCURRENTLY — see
    :func:`_run_source_jobs_parallel`. ``workers`` of 1, and any group of a single source, take the
    serial path, which is the original loop line for line.

    A ``BaseException`` (Ctrl+C) is RETURNED, not raised — the caller captures it, skips the
    remaining groups, finalizes the completed sources, and re-raises (the frozen
    capture-finalize-reraise pattern). The in-flight source was already rolled back by the
    session runner's ``finally``."""
    if workers <= 1 or len(jobs) <= 1:
        return _run_serially(list(enumerate(jobs, 1)), len(jobs), emit, report, failures_dict, model)
    return _run_source_jobs_parallel(jobs, emit, report, failures_dict, model, workers)


def _run_serially(
    numbered: list[tuple[int, _SourceJob]], total: int, emit, report: IngestReport, failures_dict, model
) -> BaseException | None:
    """Run ``(index, job)`` pairs one after another — the whole serial path, and the tail of the
    parallel one (a source whose promote raced another is re-run here, keeping its original
    index/total so the progress numbering stays honest)."""
    for index, job in numbered:
        run = _attempt_source(job, index, total, emit, concurrent=False)
        if run.interrupt is not None:
            return run.interrupt
        _record_source_run(run, emit, report, failures_dict, model)
    return None


def _run_source_jobs_parallel(
    jobs: list[_SourceJob], emit, report: IngestReport, failures_dict, model, workers: int
) -> BaseException | None:
    """Run one group's sources through a bounded thread pool, then re-run serially whichever of
    them raced another source's promote.

    What each worker does is exactly what the serial loop does — plan, stage, run the session(s),
    validate, promote — with two differences, both inside :func:`_run_agent_sessions`: the clone and
    the promote take :data:`_LIVE_WIKI_LOCK`, and the promote is checked against the state its clone
    was taken from. Everything a run SHARES (report lists, the manifest, the failures catalog) is
    written here on the main thread as results arrive, so those writes stay serial and the manifest
    is still saved per completed source.

    Sources are folded in in COMPLETION order, which is not submission order — the wiki is a set of
    pages, not a log, so nothing depends on it; the report's lists simply read in the order sources
    finished.

    Interrupts: a Ctrl+C reaches the main thread (and, being in the same process group, the agent
    subprocesses too). The first ``BaseException`` from either side wins — queued sources are
    cancelled and their workers told to stop before starting anything new, in-flight ones roll
    themselves back — and it is returned for the caller's capture-finalize-reraise. Sources that had
    already finished cleanly are still recorded, so an interrupt never throws away work the run
    already paid for and promoted."""
    total = len(jobs)
    abort = threading.Event()
    interrupt: BaseException | None = None
    conflicted: list[tuple[int, _SourceJob]] = []
    recorded: set[int] = set()

    def attempt(index: int, job: _SourceJob) -> _JobRun | None:
        # A cancelled-too-late worker must not start a session: once the run is aborting, the only
        # correct thing a queued source can do is nothing at all.
        if abort.is_set():
            return None
        return _attempt_source(job, index, total, emit, concurrent=True)

    with futures.ThreadPoolExecutor(max_workers=min(workers, total), thread_name_prefix="citadel-ingest") as pool:
        submitted = [pool.submit(attempt, index, job) for index, job in enumerate(jobs, 1)]
        try:
            for future in futures.as_completed(submitted):
                if future.cancelled():
                    # A cancelled future is only ever produced by the abort below, so its
                    # `CancelledError` would be caught there and discarded in favour of the
                    # interrupt that caused it — correct, but only by that reasoning. Skipping it
                    # here (as the drain loop already does) keeps the property local: `result()` is
                    # called on completed work only.
                    continue
                run = future.result()
                if run is None:
                    continue
                if run.interrupt is not None:
                    interrupt = interrupt if interrupt is not None else run.interrupt
                    abort.set()
                    for pending in submitted:
                        pending.cancel()
                    continue
                if run.outcome is not None and run.outcome.conflict:
                    # Nothing was promoted, so this attempt is NOT recorded as a source outcome —
                    # but what it spent and what it replayed are facts of this run either way, and
                    # the source goes into the serial tail below (where it can no longer race
                    # anybody).
                    _record_spend(run.outcome, report)
                    report.raced.append(run.job.key)
                    conflicted.append((run.index, run.job))
                    emit("source_retry", index=run.index, total=total, source=run.job.key, seconds=run.outcome.seconds)
                    continue
                _record_source_run(run, emit, report, failures_dict, model)
                recorded.add(run.index)
        except BaseException as exc:  # noqa: BLE001 - Ctrl+C while waiting: stop dispatching
            interrupt = interrupt if interrupt is not None else exc
            abort.set()
            for pending in submitted:
                pending.cancel()
        # Leaving the `with` joins whatever is still running (their sessions roll back on the same
        # interrupt); their results are drained below rather than dropped.
    if interrupt is not None:
        for future in submitted:
            if not future.done() or future.cancelled():
                continue
            with contextlib.suppress(Exception):
                run = future.result()
                # Only completed, PROMOTED work is booked during an abort: it is already on the live
                # wiki, so leaving it out of the manifest would just make the next run pay again.
                if run is not None and run.outcome is not None and run.outcome.ok and run.index not in recorded:
                    _record_source_run(run, emit, report, failures_dict, model)
                    recorded.add(run.index)
        return interrupt
    if conflicted:
        # The serial tail: no other source can be promoting now, so these re-runs see the wiki the
        # winner left behind and merge into it — the result a serial run would have produced.
        return _run_serially(sorted(conflicted, key=lambda pair: pair[0]), total, emit, report, failures_dict, model)
    return None


def _office_write_temp(text: str, name: str, media: list[tuple[str, bytes]] | None = None) -> tuple[str, str]:
    """Materialize already-extracted Office ``text`` as a fresh temp ``.md`` (named after the
    source's ``name``) for the agent to READ, and return ``(read_key, tmpdir)``: ``read_key`` is the
    path the agent reads (it still cites the ORIGINAL source), and ``tmpdir`` is the temp directory
    the caller MUST remove after the session. Raises ``OSError`` only if the temp file cannot be
    written — handled per-source by the caller, never aborting the whole run.

    ``media`` is the source's embedded raster images (from :func:`extract.extract_media`): each is
    written into a ``media/`` subfolder beside the text file so the agent can VIEW the diagrams and
    charts the text extractor cannot capture. The extraction already happened once in
    :func:`_partition_sources` / here, so the ``.pptx``/``.docx`` is never parsed for text twice."""
    tmpdir = tempfile.mkdtemp(prefix="okf_extract_")
    try:
        out = Path(tmpdir) / (Path(name).stem + ".md")
        out.write_text(text, encoding="utf-8")
        if media:
            media_dir = Path(tmpdir) / "media"
            media_dir.mkdir(exist_ok=True)
            for fname, data in media:
                (media_dir / Path(fname).name).write_bytes(data)
    except OSError:
        # Don't leak the temp dir if the write fails — the caller never sees it to clean up.
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    return config.rel_or_abs_posix(out), tmpdir


def _read_source_text(src: Path) -> str | None:
    """The decoded text of a plain-text source, for size-based chunking, or None when it should NOT
    be chunked here: a PDF (binary — its ``%PDF-`` magic; the agent's reader extracts the text) or a
    file we cannot read. Decoded with ``errors="replace"`` so an odd byte never raises. Only called
    for pending, non-Office, non-image sources (already sniffed as text by :func:`_is_ingestible`)."""
    try:
        with open(src, "rb") as fh:
            if fh.read(5) == b"%PDF-":
                return None
        return src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _text_atoms(text: str, max_chars: int) -> list[str]:
    """Break ``text`` into atoms each at most ``max_chars`` long, preferring paragraph boundaries,
    then line boundaries, then hard character slices for a pathological single long line."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        if len(para) <= max_chars:
            out.append(para)
            continue
        for line in para.split("\n"):
            if len(line) <= max_chars:
                out.append(line)
            else:
                out.extend(line[i : i + max_chars] for i in range(0, len(line), max_chars))
    return [a for a in out if a.strip()]


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into ordered segments each at most ``max_chars`` long (packing whole
    paragraphs/lines together), or ``[text]`` when it already fits / chunking is off. Used to feed a
    large source to the agent in several sequential passes."""
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    segments: list[str] = []
    cur = ""
    for atom in _text_atoms(text, max_chars):
        candidate = atom if not cur else cur + "\n\n" + atom
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            if cur:
                segments.append(cur)
            cur = atom
    if cur:
        segments.append(cur)
    return segments or [text]


def _line_windows(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Split ``text`` into contiguous 1-based inclusive LINE ranges, packing whole lines so each
    window stays at most ``max_chars`` characters (a single over-long line still gets its own
    window — lines are the atom here, never split). The windows cover every line in order, so a
    reader working window k of the SAME file sees the file's true line numbers — the point:
    unlike :func:`_split_text` slices, nothing ever rebases the numbering."""
    lines = text.splitlines()
    windows: list[tuple[int, int]] = []
    start, size = 1, 0
    for i, line in enumerate(lines, 1):
        cost = len(line) + 1
        if size and size + cost > max_chars:
            windows.append((start, i - 1))
            start, size = i, 0
        size += cost
    if start <= len(lines):
        windows.append((start, len(lines)))
    return windows or [(1, 1)]


def _prepare_passes(
    src: Path, office: str | None, is_image: bool, is_audio: bool = False, is_pdf: bool = False
) -> tuple[list[tuple[str | None, tuple[int, int] | None, tuple[int, int] | None]], list[str]]:
    """Plan the agent session(s) for one pending source and return ``(passes, tmpdirs)``.

    Each pass is ``(read_key, segment, line_range)``: ``read_key`` is the temp ``.md`` the agent
    reads (None = read the source file directly), ``segment`` is ``(part, total)`` for a chunked
    large source (None = single pass), and ``line_range`` — audio/PDF-extract only — is the
    1-based inclusive line window of the FULL prepared text this pass processes. ``tmpdirs`` are
    temp directories the caller MUST remove afterwards.

    - image: one pass, read the file directly (viewed visually).
    - a chunked AUDIO transcript or PDF text-layer extraction is NOT sliced into rebased temp
      files: every pass reads the SAME full prepared text (its line numbers are identical to the
      verification cache's) and carries the line window to process — so ``lines A-B`` locators
      stay correct by construction (a sliced temp restarts numbering at 1 and would silently
      mis-ground every chunked locator).
    - a source (pre-extracted Office text, or — when chunking is on — a readable non-PDF text
      file) whose content exceeds ``config.MAX_SOURCE_CHARS`` is SPLIT into segments, one pass
      each.
    - a small Office file / audio transcript / PDF extraction: one pass reading the prepared text.
    - anything else (small plain text, a PDF without a usable text layer, an image-less binary
      the agent reads): one pass reading the file directly (unchanged behavior).

    ``is_audio`` marks the ``office`` text as a whisper transcript, ``is_pdf`` as a pypdf
    text-layer extraction: same temp-file plumbing, but line-window chunking (above) and no media
    extraction (an ``.mp3``/``.pdf`` is not a ZIP to unzip).

    Raises ``OSError`` if a temp segment/extract file can't be written (handled per-source)."""
    if is_image:
        return [(None, None, None)], []
    max_chars = config.MAX_SOURCE_CHARS
    # Content we could chunk: pre-extracted Office/transcript/PDF text, or (chunking on) a
    # readable text source.
    content = office
    if content is None and max_chars > 0:
        content = _read_source_text(src)
    if content is not None and max_chars > 0 and len(content) > max_chars:
        if is_audio or is_pdf:
            windows = _line_windows(content, max_chars)
            read_key, tmp = _office_write_temp(content, src.name, None)
            return [(read_key, (i, len(windows)), w) for i, w in enumerate(windows, 1)], [tmp]
        segments = _split_text(content, max_chars)
        # A chunked Office source keeps its embedded images: attached to the FIRST segment's temp,
        # exactly like the small-Office branch below — without this, a deck whose extracted text
        # crossed the chunking threshold silently lost its diagrams/charts.
        media = extract.extract_media(src) if office is not None and config.IMAGE_SUPPORT else []
        passes: list[tuple[str | None, tuple[int, int] | None, tuple[int, int] | None]] = []
        tmpdirs: list[str] = []
        try:
            for i, seg in enumerate(segments, 1):
                read_key, tmp = _office_write_temp(seg, src.name, media if i == 1 else None)
                passes.append((read_key, (i, len(segments)), None))
                tmpdirs.append(tmp)
        except OSError:
            for tmp in tmpdirs:
                shutil.rmtree(tmp, ignore_errors=True)
            raise
        return passes, tmpdirs
    if office is not None:
        # Small Office file: one pass reading the extracted text — plus its embedded images (decks
        # and docs often carry diagrams/charts/screenshots the text extractor can't see), written
        # beside the text for the agent to VIEW. Skipped when image support is off — and for an
        # audio transcript or PDF extraction, which have no OOXML media to extract.
        media = extract.extract_media(src) if config.IMAGE_SUPPORT and not (is_audio or is_pdf) else []
        read_key, tmp = _office_write_temp(office, src.name, media)
        return [(read_key, None, None)], [tmp]
    # Small plain text, a PDF without a usable text layer, or any other agent-readable source:
    # read the file directly.
    return [(None, None, None)], []


def _pending_session(
    rel_key: str,
    kind: str,
    read_key: str | None,
    segment: tuple[int, int] | None = None,
    line_range: tuple[int, int] | None = None,
) -> llm.SessionUsage | None:
    """Drive ONE ingest/reconcile agent session, passing through the backend's usage report
    (:class:`llm.SessionUsage` or None) for the outcome's accounting. When ``read_key`` is set
    (an Office source or a large-source segment whose text was extracted), point the agent at it
    via ``read_path``; otherwise call exactly as before so a non-Office source — and every
    existing test's faked session — is byte-for-byte unchanged. ``segment`` carries
    ``(part, total)`` for a chunked source, ``line_range`` the transcript window of a chunked
    AUDIO pass (the full-transcript lines this pass processes); each is passed to the backend
    ONLY when set, so every pre-existing call shape stays byte-for-byte unchanged."""
    if line_range is not None:
        return llm.run_ingest_session(rel_key, kind=kind, read_path=read_key, segment=segment, line_range=line_range)
    if read_key and segment is not None:
        return llm.run_ingest_session(rel_key, kind=kind, read_path=read_key, segment=segment)
    if read_key:
        return llm.run_ingest_session(rel_key, kind=kind, read_path=read_key)
    if segment is not None:
        return llm.run_ingest_session(rel_key, kind=kind, segment=segment)
    return llm.run_ingest_session(rel_key, kind=kind)


def retry_candidates() -> tuple[list[str], list[str]]:
    """The source keys ``citadel ingest --retry`` re-runs, as ``(failed, uncited)``.

    - ``failed``: every source in the failures catalog that is still on disk — errored / timed-out
      / unreadable records alike (an unchanged unreadable file is re-evaluated for free, and a
      fixed one — hydrated placeholder, re-exported document — now ingests). Deliberate skips
      stay skipped: a same-basename ``duplicate`` record is a decision, not a failure, and a
      ``curate`` record is keyed by a PAGE, not a source (``citadel curate --retry`` owns those).
    - ``uncited``: every INGESTED source that no wiki page cites (the same
      ``store.citing_pages_map`` verdict as the ``Referenced by`` column of
      ``wiki/sources/index.md``, and ``citadel status``'s ``NO PAGES`` marker) — a session was
      paid for, the source is marked done, and yet nothing in the wiki carries its facts. These
      are re-run as FORCED reconciles.

    Both lists are sorted and disjoint (a key can only be in one catalog); vanished files are
    excluded — a retry cannot read what is not there (a vanished INGESTED source is the deletion
    sweep's job, not a retry's). Read-only: computing candidates changes nothing. Best-effort
    like ``status``'s marker: a wiki that cannot be traversed degrades to an empty ``uncited``
    list instead of taking the recovery command down — the failed sources are still retried,
    which is exactly the situation ``--retry`` exists for."""
    failed: list[str] = []
    for key, entry in sorted(failures.load().items()):
        if not isinstance(entry, dict):
            continue
        if entry.get("reason") in (failures.DUPLICATE, failures.CURATE):
            continue
        if config.source_path_for_key(key).exists():
            failed.append(key)
    manifest_dict = manifest.load()
    uncited: list[str] = []
    if manifest_dict:
        try:
            refs = store.citing_pages_map(list(manifest_dict))
        except Exception:  # noqa: BLE001 - recovery must degrade, never crash on a broken wiki
            refs = None
        if refs is not None:
            uncited = [
                key for key in sorted(manifest_dict) if not refs.get(key) and config.source_path_for_key(key).exists()
            ]
    return failed, uncited


@pagecache.bypass
def ingest(
    paths: list[str] | None = None,
    progress=None,
    full_rescan: bool = False,
    force: bool = False,
    jobs: int | None = None,
) -> IngestReport:
    """Run one ingest. Exactly one source = one all-or-nothing agent job (a chunked source runs
    several ``llm.run_ingest_session`` passes inside that one job).

    Before the per-source loop, candidates are partitioned (``_partition_sources``) into
    pending / already-ingested / **reorganized** (a file that only moved or is a byte-for-byte
    duplicate — recognized, not re-ingested; a real move repoints the wiki's resource/citation
    references and re-keys the manifest) / **unreadable** (no extractable text, e.g. a binary —
    logged and marked done, never fed to the agent; an all-NUL cloud-only placeholder is instead
    kept re-evaluated so it ingests once hydrated) / **deleted** (a tracked source that
    vanished from disk — full runs only). Discovery is incremental: the manifest doubles as the
    scan cache, so an unchanged corpus is skipped on stat alone (``full_rescan=True`` — the
    ``--full-rescan`` flag — distrusts that cache and re-hashes everything; sha stays the sole
    arbiter, so unchanged sources are re-stamped, not re-ingested).

    ``force`` (the ``--force`` flag) deliberately re-reads the
    requested sources even when nothing changed: the quick check AND the sha short-circuit are
    bypassed, so a sha-matching tracked source lands in pending and runs ``kind="reconcile"``,
    a tracked repo at its stored commit runs ``kind="repo-reconcile"`` over a FULL re-digest
    (never a first-time brief — the rationale lives on :func:`_partition_repos`), a persisted
    UNREADABLE/ERROR failure record is re-evaluated (and cleared on success), and a
    dedup-dropped key is ingested exactly as requested (the report records the divergence).
    On success the manifest is re-stamped with the CURRENT model + rules_version — the point of
    forcing after a model/rules upgrade. One short-circuit force deliberately does NOT bypass: a
    chunked source's resume checkpoint (:func:`_resume_context`). Forcing is what ``citadel
    refresh`` drives, and an interrupted forced re-read is exactly the expensive job worth
    continuing rather than re-buying; a checkpoint from a NON-forced run can't be adopted anyway,
    since forcing changes the session kind. ``force`` without explicit paths is refused HERE with a
    ValueError (one agent session per source must never hit the whole corpus by accident; the
    CLI pre-empts it with the same message and a friendly exit 2), and a path-scoped run never
    sweeps deletions (``swept_roots=None`` below).

    Deletion detection is guarded (operational safety over
    thoroughness): candidates come from the walked-seen-set diff, each positively confirmed with
    ``.exists()``; any walk error aborts the entire sweep for the run; an unreachable root
    contributes no candidates; keys under no configured root are logged, never swept; and a
    workspace-identity mismatch whose keys do not resolve refuses the sweep outright.

    Per pending source: the agent's pass(es) run all-or-nothing against a per-source STAGING
    copy, promoted once per source — the full story lives on :func:`_run_agent_sessions`.
    A source already tracked in the manifest but with new bytes is a re-ingest, run with
    ``kind="reconcile"`` so the agent UPDATES/REMOVES the stale facts it produced rather than
    only appending. On a per-source exception (a missing/unusable CLI, a timeout, etc.) — or a
    Ctrl+C — nothing is promoted, the error is collected, and the source is retried next run.

    Per deleted source (full run only, run BEFORE the pending sources): if any wiki page still
    cites it, run a ``kind="delete"`` cleanup session that strips those facts/citations, gated by
    a post-condition that the wiki no longer references it (else the whole cleanup is rolled back
    and retried); then drop its manifest key. A deleted source nothing cites is simply dropped
    from the manifest. Running deletions first is load-bearing (the per-source-job group-order
    comment in the body carries the full why). Finalization
    (rebuild_indexes + find_broken_links + append_log) happens once, if any source was processed,
    reorganized, found unreadable, or removed.

    The per-source loop itself is ONE shared implementation (:class:`_SourceJob` +
    :func:`_run_source_jobs`): deletion cleanups, files, and repos differ only in how their
    sessions are planned and in their post-success bookkeeping.

    ``jobs`` (``citadel ingest --jobs N``; None takes :data:`config.JOBS`, default 1) is how many
    sources may be folded in CONCURRENTLY. 1 is the strictly serial behavior citadel has always
    had. Above 1, each source still gets its own staging copy and its own all-or-nothing promote —
    what changes is that N of them are in flight at once, promoting one at a time against the wiki
    state they were cloned from; a source whose promote raced another one over the same page is
    re-run serially before the run ends (``report.raced``). Every guarantee is unmoved: one promote
    per source, nothing partial on the live wiki, the manifest still saved per completed source. The
    real cost is cross-linking — concurrent sessions cannot see each other's new pages — which is
    why the default stays 1 and the knob is documented as a throughput trade, not a free win.

    ``progress`` is an optional ``progress(event, data)`` callback (run start, before/after
    each source, before finalization); None for non-interactive callers. A failing callback
    never breaks ingest.
    """
    workers = config.JOBS if jobs is None else jobs
    if workers < 1:
        raise ValueError(f"--jobs must be at least 1 (got {workers}); 1 means the serial default.")
    if force and not paths:
        # The API-layer twin of the CLI's exit-2 refusal (which pre-empts this with the same
        # message), so a programmatic caller cannot force the whole corpus by accident either.
        # The MCP server's wiki_ingest does not expose force at all.
        raise ValueError(
            "--force requires explicit paths (a forced re-read runs one agent session per "
            "source; name the files or directories to force, e.g. `citadel ingest --force raw/notes.md`)."
        )

    # ONE mutating run per workspace: the staging sweep, promote's prune, and the manifest/
    # failures saves are all destructive under concurrency (see runlock's module docstring).
    # A second run fails loud here instead of silently eating the first one's work.
    with runlock.hold("ingest"):
        _sweep_stale_staging(config.wiki_dir())
        # Same place, same reason: under the exclusive lock, leftovers on disk belong to dead runs.
        # Age-based only — a checkpoint's own guards decide whether it is USABLE (see resume.sweep).
        resume.sweep()
        return _ingest_run(paths, progress, full_rescan=full_rescan, force=force, jobs=workers)


def _ingest_run(paths: list[str] | None, progress, *, full_rescan: bool, force: bool, jobs: int = 1) -> IngestReport:
    """The body of :func:`ingest`, running under the exclusive workspace run lock."""

    # `--jobs N` emits from WORKER threads (a source's start/done event fires where the work
    # happens), so the callback — which is whatever the caller passed — is serialized here. That
    # keeps "your progress callback is never invoked concurrently" a property of the API rather than
    # something each caller has to discover, and it costs nothing: emit fires a handful of times per
    # source, around sessions that take minutes. The console reporter is safe under it either way
    # (its writes are locked, and rich gives each in-flight source its own live row), but the
    # contract must not depend on that reasoning holding for every future callback.
    emit_lock = threading.Lock()

    def emit(event: str, **data) -> None:
        if progress is None:
            return
        with emit_lock:
            try:
                progress(event, data)
            except Exception:  # noqa: BLE001 - progress must never break ingest
                pass

    # ONE manifest parse: load() stashes the file's meta, and the mismatch probe reads that
    # stash — taken BEFORE anything saves (a save re-stamps meta with the CURRENT root, which
    # would blind the identity guard below to the mismatch it must catch).
    manifest_dict = manifest.load()
    workspace_mismatch = manifest.stamped_workspace_mismatch()
    # Persistent record of sources that could not be ingested (unreadable / errored / timed out).
    # Updated through the run and rewritten at the end, so it always reflects the CURRENT stuck set.
    failures_dict = failures.load()
    failures_before = {k: dict(v) if isinstance(v, dict) else v for k, v in failures_dict.items()}
    # Migration sweep: drop any entry a PREVIOUS run recorded for a source that must not be tracked
    # at all — a now-ignored junk file (Thumbs.db & friends, recorded before that feature existed)
    # or a path inside the WIKI (a page self-ingested by a layout whose raw root sits above the wiki,
    # before the discovery guard existed). Both still exist on disk, so a full run would never
    # re-detect them as deleted — clean them out of the manifest AND the failures catalog directly
    # so wiki/sources/index.md stops carrying the noise.
    pruned_ignored = False
    for key in [k for k in manifest_dict if _is_untrackable_key(k)]:
        del manifest_dict[key]
        pruned_ignored = True
    for key in [k for k in failures_dict if _is_untrackable_key(k)]:
        failures.clear(failures_dict, key)
        pruned_ignored = True
    if pruned_ignored:
        # Persist BOTH catalogs together, so an early exit (Ctrl+C / an unexpected error before
        # finalization) can't leave the manifest cleaned while the failures catalog still carries
        # the junk keys — the two would then disagree until the next run reconciled them.
        manifest.save(manifest_dict)
        failures.save(failures_dict)
    # The model/backend that will import this run's sources — recorded per-source in the manifest
    # so you can see which raw file was imported by which model. Resolved once (it does not change
    # mid-run) and read at call time so tests can monkeypatch the backend/model. Likewise the
    # content hash of the effective rules tree the sessions run under — stamped per source so a
    # later `curate --stale-rules` can find sources ingested under older rules; computed ONCE (the
    # rules do not change mid-run and hashing them per source would re-read the tree needlessly).
    model = config.ingest_model_label()
    rules_ver = config.rules_version()
    report = IngestReport([], [], [], [], model=model)

    # --- The workspace-identity HARD guard (key-space stability): the manifest was stamped by
    # a DIFFERENT workspace root AND most of its relative keys do not resolve here
    # (``manifest.workspace_rekeyed``) — a nested marker or a moved checkout re-keyed the world,
    # so the seen-set diff would read the entire old key space as deleted. Refuse the deletion
    # sweep (ingest of pending sources still proceeds); the dual-mount case (stamp differs but
    # keys resolve) stays a warning. ---
    workspace_shifted = bool(paths is None and workspace_mismatch and manifest.workspace_rekeyed(manifest_dict))
    if workspace_shifted:
        report.errors.append(
            f"workspace mismatch: the manifest was stamped by a workspace rooted at "
            f"{workspace_mismatch!r}, and most of its keys do not resolve under the current "
            f"root — refusing deletion detection so a re-keyed manifest is not read as mass "
            f"deletion. If the move is intentional, run `citadel ingest --full-rescan` once: the "
            f"sweep stays off for that run, but the manifest is re-stamped at its end so the "
            f"next run is clean (or re-init the workspace)."
        )

    if full_rescan and paths is None:
        # A full re-hash of a big corpus on a slow share takes a while — announce it so the run
        # does not look hung.
        print("NOTE: --full-rescan: re-hashing every tracked source (sha256 still decides).", file=sys.stderr)
    walk = _discover_walk(paths)
    # The ONE sweep decision: None = NO deletion sweep this run — a path-scoped run, a
    # degraded walk (any error anywhere has an unknown blast radius), or the workspace guard
    # above — else exactly the roots discovery ENTERED (an unreachable root contributes no
    # candidates). Passed to BOTH the file and the repo partition; every remaining guard
    # (root scoping, positive .exists() confirmation) lives in _sweep_gone.
    swept_roots: list[Path] | None = None
    if paths is None and not workspace_shifted and not walk.errors:
        swept_roots = list(walk.entered_roots)
    scan = _partition_sources(
        paths, manifest_dict, failures_dict, full_rescan, walk=walk, swept_roots=swept_roots, force=force
    )
    if scan.mutated:
        # The quick check refreshed/backfilled stat caches on unchanged entries: persist them now
        # so the very next run reads no content for these files, even if nothing else happens.
        manifest.save(manifest_dict)

    # Git repositories under raw/ are ingested as ONE source each (a digest), versioned by commit.
    # Discover + partition them alongside the file sources; a vanished repo folder is reconciled out
    # by the SAME deletion-cleanup path as a file (its citations point at the repo folder key), and
    # its deletion sweep is scoped by the same one swept_roots decision.
    repo_paths = _discover_repos(paths, walk)
    repo_pending, repo_moved, repo_deleted, repo_skipped, repo_out_of_root = _partition_repos(
        repo_paths, manifest_dict, swept_roots, force=force
    )
    report.skipped = scan.skipped + repo_skipped
    deleted_sources = scan.deleted + repo_deleted
    out_of_root = scan.out_of_root + repo_out_of_root

    # --- Deletion-sweep skip notes: whenever tracked sources were EXCLUDED from deletion
    # detection this run, say so loudly — silence here would look like "nothing was deleted"
    # when the truth is "deletion detection did not run for these". ---
    if paths is None:
        if walk.errors:
            print(
                "NOTE: the raw scan hit errors; deletion detection is skipped for this whole run "
                "(tracked sources are kept and re-checked next run):\n  " + "\n  ".join(walk.errors),
                file=sys.stderr,
            )
        for root in walk.unreachable:
            print(
                f"NOTE: raw root {root} is unreachable (not mounted?); its sources are kept — "
                "deletion detection for them is skipped this run.",
                file=sys.stderr,
            )
        if out_of_root:
            print(
                "NOTE: tracked source(s) under no configured raw root — never swept by deletion "
                "detection:\n  " + "\n  ".join(sorted(out_of_root)),
                file=sys.stderr,
            )
    if scan.unreadable_tracked:
        print(
            "NOTE: already-ingested source(s) could not be re-read this run (permissions / IO); "
            "kept as ingested and re-checked next run:\n  " + "\n  ".join(sorted(scan.unreadable_tracked)),
            file=sys.stderr,
        )
    # --- Discovery exclusions: both are deliberate skips, so say so rather than let the sources
    # simply not appear. The wiki note fires once per run (a raw root above the wiki prunes the
    # same tree at every level); the size note lists what the ceiling kept out. ---
    if walk.excluded_wiki:
        print(
            f"NOTE: the wiki directory ({config.WIKI_DIR}) is excluded from discovery - generated "
            "pages are never raw sources. If a raw root sits above the wiki, narrow "
            "CITADEL_RAW_DIRS (or move the wiki with CITADEL_WIKI_DIR) to silence this.",
            file=sys.stderr,
        )
    report.oversized = sorted((manifest.rel_key(p), size) for p, size in walk.oversized)
    if report.oversized:
        listed = [f"{key} ({_human_bytes(size)})" for key, size in report.oversized[:10]]
        if len(report.oversized) > len(listed):
            listed.append(f"... +{len(report.oversized) - len(listed)} more (all listed on the run report)")
        print(
            f"NOTE: {len(report.oversized)} file(s) skipped by CITADEL_MAX_SOURCE_BYTES "
            f"({_human_bytes(config.MAX_SOURCE_BYTES)}); raise it (or name a path explicitly) to "
            "ingest them:\n  " + "\n  ".join(listed),
            file=sys.stderr,
        )
    # A pending source whose key is ALREADY tracked is a re-ingest of changed bytes (reconcile);
    # one not yet tracked is brand new. Captured before the manifest is mutated below.
    pending_keys = {manifest.rel_key(p) for p in scan.pending}
    changed_keys = pending_keys & set(manifest_dict)

    # --- Reorganized sources: a file that only MOVED (or is a byte-for-byte duplicate) is
    # recognized and NOT re-ingested. For a real move (the old path is gone) repoint the wiki's
    # `resource` frontmatter and citation links to the new path so nothing breaks, then drop the
    # stale manifest key. Either way, record the new key so future runs skip it immediately. ---
    repointed = False
    for old_key, new_key, sha, old_gone in scan.moved:
        # A move/duplicate is NOT a re-ingest: carry over the model (and rules_version) that
        # originally imported this content (recorded under the old key) rather than stamping it
        # with this run's values. When the twin is itself pending in THIS run (two new copies
        # discovered together), the old key has no manifest entry yet — the twin will be stamped
        # with the run's values, so the duplicate carries the same ones instead of a permanent
        # None that `status` can't attribute and `--stale-rules` can never flag.
        carried_model = manifest.model_of(manifest_dict, old_key)
        carried_rules = manifest.entry_rules_version(manifest_dict.get(old_key))
        # ingested_at — and the cost/tokens usage stamp — are CARRIED only, never minted here:
        # unlike model/rules_version above, a fresh stamp would claim a session verified this
        # copy when none did (the pending twin's session may not even succeed). A duplicate left
        # stamp-less merely sorts to the front of `citadel refresh`'s queue — one re-verify
        # session later it is stamped honestly. (Read BEFORE the pop below.)
        carried_ingested = manifest.entry_ingested_at(manifest_dict.get(old_key))
        carried_usage = manifest.entry_usage(manifest_dict.get(old_key))
        if old_key not in manifest_dict and old_key in pending_keys:
            carried_model = carried_model or model
            carried_rules = carried_rules or rules_ver
        if old_gone and old_key != new_key:
            try:
                if store.rewrite_raw_references(old_key, new_key):
                    repointed = True
            except Exception as exc:  # noqa: BLE001 - collect, don't re-key, retry next run
                # Leave the manifest untouched so this move (and its repoint) is retried next
                # run rather than being silently recorded with stale references behind it.
                report.errors.append(f"{new_key}: repoint refs from {old_key}: {exc}")
                continue
            manifest_dict.pop(old_key, None)
            # The checkpoint store is keyed by source KEY, so a re-keyed source's slot can never be
            # adopted again (identity carries the key) — drop it here rather than leaving its page
            # text beside the wiki until the age sweep.
            resume.clear(old_key)
        moved_stat = scan.hashed[new_key][1] if new_key in scan.hashed else None
        manifest_dict[new_key] = manifest.make_entry(
            sha, carried_model, carried_rules, st=moved_stat, ingested_at=carried_ingested, **carried_usage
        )
        failures.clear(failures_dict, old_key)
        failures.clear(failures_dict, new_key)
        report.moved.append((old_key, new_key))
    # Repo moves: a repo whose folder was renamed (same base commit, old path gone). Repoint its
    # citations/`resource` to the new folder key and carry over its provenance — not a re-ingest.
    for old_key, new_key, ident in repo_moved:
        carried_model = manifest.model_of(manifest_dict, old_key)
        old_entry = manifest_dict.get(old_key)
        carried_remote = manifest.entry_remote(old_entry) if old_entry is not None else None
        carried_rules = manifest.entry_rules_version(old_entry)
        carried_ingested = manifest.entry_ingested_at(old_entry)
        carried_usage = manifest.entry_usage(old_entry)
        if old_key != new_key:
            try:
                if store.rewrite_raw_references(old_key, new_key):
                    repointed = True
            except Exception as exc:  # noqa: BLE001 - collect, don't re-key, retry next run
                report.errors.append(f"{new_key}: repoint refs from {old_key}: {exc}")
                continue
            manifest_dict.pop(old_key, None)
        manifest_dict[new_key] = manifest.make_repo_entry(
            ident, carried_model, carried_remote, carried_rules, ingested_at=carried_ingested, **carried_usage
        )
        report.moved.append((old_key, new_key))
    if report.moved:
        manifest.save(manifest_dict)

    # --- Unreadable sources: no extractable text (binary/unsupported). Mark them done (so they
    # are not re-checked and re-logged every run) and surface + log them — the file "did not
    # work", but it is not a hard error that should fail the whole run. ---
    for src in scan.unreadable:
        key = manifest.rel_key(src)
        if key not in scan.hashed:
            continue  # not even its hash could be read (OS error on a brand-new file): retry next run
        sha, src_stat = scan.hashed[key]
        report.unreadable.append(key)
        if _reads_as_cloud_placeholder(src):
            # A cloud-only placeholder: hydration restores the real content WITHOUT changing
            # size/mtime — and on Windows st_ctime is the stable creation time — so marking it
            # done would let the stat quick check skip the hydrated file forever. It lives only in
            # the failures catalog, and deliberately WITHOUT sha/stat: a cached sha that the quick
            # check trusts across a stat-stable hydration would thread the stale all-NUL sha into
            # mark_done. The cost is one re-hash of the still-stuck placeholder per run; the win is
            # that hydration always yields the real sha and the file ingests normally.
            report.cloud_placeholders.append(key)
            failures.record(
                failures_dict,
                key,
                failures.UNREADABLE,
                "reads as all NUL bytes - likely a cloud-only placeholder (Dropbox/OneDrive "
                "online-only file); make it available offline and re-run",
            )
            continue
        # No model imported it (it was only sniffed and skipped), so record the sha alone — with
        # the stat cache, so a later run skips the unchanged binary without a content read.
        manifest_dict[key] = manifest.make_entry(sha, None, st=src_stat)
        # Persist the failure so it survives the run (surfaced in wiki/sources/index.md; written by
        # the finalization step below, which an unreadable source always triggers). sha+stat let the
        # quick check recognize the unchanged file next run.
        failures.record(
            failures_dict, key, failures.UNREADABLE, "no extractable text (binary/unsupported)", sha=sha, st=src_stat
        )
    if scan.unreadable:
        manifest.save(manifest_dict)

    # --- Duplicate document sources: skipped in favor of another same-basename format (config
    # DEDUP_BY_BASENAME). Record them (report + persistent failures, with sha+stat so an unchanged
    # twin is never re-hashed) but do NOT mark them done, so a later run re-evaluates — deleting
    # the kept file promotes one of these. On a FORCED run nothing was dropped (the requested
    # file is ingested alongside its kept sibling), so the scan classified the pairs separately:
    # they reach the report purely as the divergence record naming that sibling — no DUPLICATE
    # failure is persisted (a stale one is cleared by the successful session below). ---
    for dropped_key, kept_key in scan.duplicates:
        report.duplicates.append((dropped_key, kept_key))
        dup_sha, dup_stat = scan.hashed.get(dropped_key, (None, None))
        failures.record(
            failures_dict,
            dropped_key,
            failures.DUPLICATE,
            f"same basename as {kept_key}, which was ingested instead",
            sha=dup_sha,
            st=dup_stat,
        )
    report.duplicates_forced.extend(scan.duplicates_forced)

    emit(
        "start",
        pending=len(scan.pending),
        skipped=len(report.skipped),
        moved=len(report.moved),
        unreadable=len(report.unreadable),
        deleted=len(deleted_sources),
        repos=len(repo_pending),
        jobs=jobs,
    )

    # --- The per-source jobs (the SourceJob loop): DELETION cleanups first, then files, then repos,
    # each group with its own index/total counters (frozen progress vocabulary). All three run
    # through the ONE shared loop (_run_source_jobs) + the ONE all-or-nothing session runner
    # (_run_agent_sessions); only session planning and post-success bookkeeping differ.
    # DELETIONS RUN BEFORE the pending sources (corpus-discovered fix, leuchtfeuer wave 3): a
    # delete cleanup strips a vanished source's stale provenance FIRST, so a later pending source
    # whose session touches a page that still cited the deleted source no longer fails validation
    # (bad_source) on that pre-existing stale citation and roll back fruitlessly — the pending
    # session now builds on a wiki the deletion already made consistent. Order is safe: every
    # group's members (incl. the deletion sweep) are computed by _partition_* BEFORE any session
    # runs, so no group's candidate set depends on another group having executed. ---

    def _file_job(src: Path) -> _SourceJob:
        rel_key = manifest.rel_key(src)
        is_image = src in scan.images
        is_audio = src in scan.audio
        # The (sha, stat) discovery already took — the source's ONE content read this run —
        # threaded to the failures catalog and, on success, to mark_done (never re-hashed).
        sha_stat = scan.hashed.get(rel_key, (None, None))
        # An already-tracked key is a re-ingest — new bytes, or a FORCED re-read of unchanged
        # ones: reconcile (update/remove stale facts) rather than only appending. A brand-new key
        # is a plain ingest. Image sources take the image propagation (the agent VIEWS them);
        # audio/video sources take the audio propagation (the agent reads the transcript).
        if is_image:
            kind = "image-reconcile" if rel_key in changed_keys else "image"
        elif is_audio:
            kind = "audio-reconcile" if rel_key in changed_keys else "audio"
        else:
            kind = "reconcile" if rel_key in changed_keys else "ingest"
        office = scan.office_text.get(src)

        def build() -> tuple[list, list[str], "_Resume | None"]:
            # Plan the pass(es): an Office source materializes its extracted text to a temp .md
            # the agent reads; an audio/video source is transcribed HERE through the whisper seam
            # (content-addressed cache; a raise is a retryable per-source prepare_error, and the
            # cache makes the retry free); a PDF's text layer is extracted HERE through the
            # (bundled) pypdf seam (same content-addressed cache idea; a None — no text layer,
            # unparsable, CITADEL_PDF_TEXT=0, or pypdf force-removed — quietly falls back to the
            # direct agent read, so the pre-pass can never cost a session); a source too large for
            # one context is SPLIT
            # into segments (promote-once per source — see _run_agent_sessions); anything else is
            # a single direct read.
            prepared = office
            run_kind = kind
            is_pdf = False
            if is_audio:
                prepared = transcribe.transcript_for(src, sha=sha_stat[0])
                # A transcription can take minutes: refresh the run lock afterwards so the
                # staleness window never has to absorb whisper time AND session time in one gap.
                runlock.heartbeat()
            elif prepared is None and pdftext.is_pdf_text_source(src):
                prepared = pdftext.text_for(src, sha=sha_stat[0])
                if prepared is not None:
                    # Only a source that ACTUALLY got an extraction takes the pdf propagation —
                    # the kind selects formats/pdf.md's prepared-extract rules (lines locators
                    # into the cached text); the fallback stays plain ingest/reconcile.
                    is_pdf = True
                    run_kind = "pdf-reconcile" if rel_key in changed_keys else "pdf"
            passes, tmpdirs = _prepare_passes(src, prepared, is_image, is_audio=is_audio, is_pdf=is_pdf)
            sessions = [
                (lambda rp=read_key, sg=segment, lw=window, k=run_kind: _pending_session(rel_key, k, rp, sg, lw))
                for read_key, segment, window in passes
            ]
            return sessions, tmpdirs, _resume_context(rel_key, run_kind, sha_stat[0], passes, model, rules_ver)

        def done(usage: llm.SessionUsage | None) -> None:
            # mark_done records exactly what discovery hashed (sha_stat above). On a forced
            # re-read this re-stamps the entry with the CURRENT model + rules_version. The
            # source's combined session usage (cost/tokens, when the backend reported any)
            # is stamped alongside — per-source cost observability.
            done_sha, done_stat = sha_stat
            # A re-recorded/re-exported source leaves its OLD bytes' transcript/extraction orphaned
            # in the content-addressed cache — plaintext source content (SECURITY.md). Prune it by
            # the OLD sha once the new content is safely in, regardless of the NEW file's type: a
            # PDF re-exported as plain text (or an audio file replaced by a document) still orphans
            # the old entry, and gating on the current type would miss it (mirrors the delete path).
            # Each prune is a safe no-op when there is no entry for that sha, so a plain-text change
            # touches nothing. Guarded so a byte-identical sibling keeps the cache it still verifies.
            old_entry = manifest_dict.get(rel_key)
            old_sha = manifest.entry_sha(old_entry) if old_entry is not None else None
            if old_sha and old_sha != done_sha and not _sha_shared_by_other_entry(manifest_dict, old_sha, rel_key):
                transcribe.prune_cached(old_sha)
                pdftext.prune_cached(old_sha)
            manifest.mark_done(
                manifest_dict,
                src,
                _stamp_model(usage, model),
                rules_ver,
                sha=done_sha,
                st=done_stat,
                **_usage_fields(usage),
            )
            # A source that had failed before (unreadable/errored/duplicate) now succeeded: drop
            # its persisted failure record — and any resume checkpoint (the session runner already
            # clears the one it consumed; this also catches a slot left by an earlier run whose
            # source has since stopped being chunked).
            failures.clear(failures_dict, rel_key)
            resume.clear(rel_key)
            # Persist progress immediately after each completed source: a later Ctrl+C (or a
            # crash) must not erase sources already finished this run.
            manifest.save(manifest_dict)
            report.processed.append(rel_key)

        return _SourceJob(
            key=rel_key,
            build_sessions=build,
            on_success=done,
            prepare_error="prepare audio transcript" if is_audio else "write source text",
            sha_stat=sha_stat,
            # A brand-new key (not a reconcile of changed/forced bytes) that produces zero page
            # changes is worth a warning — see _SourceJob.warn_no_pages.
            warn_no_pages=rel_key not in changed_keys,
        )

    # Repo sources: each git repository under raw/ is folded in by ONE session reading a
    # deterministic digest of its high-signal files. A re-ingest (a later commit) diffs against
    # the stored commit so only the changed files are inlined — except a FORCED re-read (the
    # run-level ``force``), which re-digests in FULL (see _partition_repos).
    def _repo_job(rjob: _RepoJob) -> _SourceJob:
        def build() -> tuple[list, list[str], "_Resume | None"]:
            only: list[str] | None = None
            change_summary: str | None = None
            if rjob.kind == "repo-reconcile" and rjob.old_commit and not force:
                changed = repo.changed_files(rjob.path, rjob.old_commit)
                if changed is not None:
                    only = changed
                    listing = "\n".join(changed) if changed else "(metadata only — no files)"
                    base = rjob.old_commit.split("+", 1)[0][:12]
                    change_summary = f"Changed files since {base}:\n{listing}"
            # Materialize the digest to a temp file the agent reads (citing the repo folder as
            # the source of record).
            digest = repo.build_digest(rjob.path, rjob.key, only=only, change_summary=change_summary)
            read_key, tmp = _office_write_temp(digest, rjob.path.name)
            sessions = [lambda rp=read_key: llm.run_ingest_session(rjob.key, kind=rjob.kind, read_path=rp)]
            return sessions, [tmp], None  # one session per repo digest: nothing to resume

        def done(usage: llm.SessionUsage | None) -> None:
            # On success the manifest records the repo's CURRENT commit identity, with a fresh
            # last-checked stamp (an agent session just verified this repo — the one event that
            # moves ingested_at) and the session's usage stamp when the backend reported one.
            manifest_dict[rjob.key] = manifest.make_repo_entry(
                repo.identity(rjob.path),
                _stamp_model(usage, model),
                repo.remote_url(rjob.path),
                rules_ver,
                ingested_at=manifest.now_iso(),
                **_usage_fields(usage),
            )
            failures.clear(failures_dict, rjob.key)
            manifest.save(manifest_dict)
            report.processed.append(rjob.key)

        return _SourceJob(
            key=rjob.key,
            build_sessions=build,
            on_success=done,
            prepare_error="build digest",
            warn_no_pages=rjob.kind == "repo",  # a fresh repo digest yielding nothing is suspicious
        )

    # Deleted sources: a tracked source vanished from disk (full run only). If any page still
    # cites it, run a `kind="delete"` cleanup session that strips that provenance, gated by a
    # post-condition that the wiki no longer references it (else the whole cleanup is rolled back
    # and retried next full run — the manifest key is dropped only on success). A deletion that
    # nothing cites plans NO session and just loses its manifest key.
    def _delete_job(key: str) -> _SourceJob:
        def build() -> tuple[list, list[str], "_Resume | None"]:
            if not store.find_raw_references(key):
                return [], [], None  # nothing cites it: no cleanup session, just forget it below
            return [lambda: llm.run_ingest_session(key, kind="delete")], [], None

        def done(_usage: llm.SessionUsage | None) -> None:
            # The cleanup session's usage lands only in the RUN total (report.usage) — the
            # source's manifest key is dropped, so there is no entry left to stamp.
            entry = manifest_dict.get(key)
            # The deleted source's cached transcript/extraction would sit orphaned forever — and
            # it holds the source's content in plaintext (SECURITY.md) — so prune it, but only
            # when NO other tracked source still shares those bytes (the cache is content-keyed;
            # a byte-identical sibling must keep the entry it verifies against). The file is gone,
            # so its bytes can't be re-sniffed: prune BOTH caches BY SHA — each is a safe no-op
            # when there is no entry for this sha (a plain-text delete touches nothing). Crucially
            # this must NOT gate on the extension: a PDF routes by %PDF- MAGIC (is_pdf_file), so it
            # can be cached under any name, and an ext gate would orphan its plaintext extraction.
            del_sha = manifest.entry_sha(entry) if entry is not None else None
            if entry is not None and not _sha_shared_by_other_entry(manifest_dict, del_sha, key):
                transcribe.prune_cached(del_sha)
                pdftext.prune_cached(del_sha)
            # A resume checkpoint is KEY-addressed (not content-addressed like those two caches),
            # so it belongs to this source alone and is dropped unconditionally — no shared-sha
            # guard applies, and leaving it would strand the source's page text beside the wiki.
            resume.clear(key)
            manifest_dict.pop(key, None)
            failures.clear(failures_dict, key)
            manifest.save(manifest_dict)
            report.sources_deleted.append(key)

        return _SourceJob(
            key=key,
            build_sessions=build,
            on_success=done,
            prepare_error="plan delete cleanup",
            extra_check=lambda: [f"{key}: still cited by {p} after cleanup" for p in store.find_raw_references(key)],
            # A delete cleanup MAY legitimately remove the last source's only page, leaving the
            # wiki empty — so the anti-emptying valve does not apply here.
            allow_emptying=True,
        )

    # A Ctrl+C (or other BaseException) raised mid-loop is captured (returned by
    # _run_source_jobs), not allowed to propagate immediately, so the remaining groups are
    # skipped and finalization still runs for the already-completed sources before it is
    # re-raised. Without this, the per-source-persisted manifest could outlive a stale index/log:
    # a later run with nothing pending would never rebuild the derived files.
    pending_interrupt: BaseException | None = None
    groups = (
        [_delete_job(key) for key in deleted_sources],
        [_file_job(src) for src in scan.pending],
        [_repo_job(r) for r in repo_pending],
    )
    for group in groups:
        if pending_interrupt is None:
            pending_interrupt = _run_source_jobs(group, emit, report, failures_dict, model, workers=jobs)

    if workspace_shifted and full_rescan:
        # The guard's advertised remedy must not loop: --full-rescan keeps the sweep refused
        # (safety frozen) but guarantees ONE end-of-run save, re-stamping the manifest meta with
        # the CURRENT workspace root — so the next run reads a matching stamp and the deletion
        # sweep is re-armed.
        manifest.save(manifest_dict)

    failures_changed = failures_dict != failures_before
    if (
        report.processed
        or report.pages_written
        or report.moved
        or report.unreadable
        or report.sources_deleted
        or repointed
        or failures_changed
        or pruned_ignored
    ):
        emit("finalize")
        # The manifest is already persisted incrementally (after each source, and right after the
        # move/unreadable bookkeeping) above, so a final save here would be redundant. Persist the
        # updated failures FIRST so the catalog rebuild below reflects this run's stuck set, then
        # rebuild the derived files (a move repoint can have changed page bodies/frontmatter).
        failures.save(failures_dict)
        store.rebuild_indexes()
        # Surface any cross-link left dangling by a restructure so it is never silent.
        report.broken_links = store.find_broken_links()
        if report.processed:
            store.append_log(
                f"ingest {report.processed} -> {len(report.pages_created)} created, "
                f"{len(report.pages_updated)} updated, {len(report.pages_deleted)} deleted "
                f"(model: {model})"
            )
        for key in report.no_pages:
            store.append_log(
                f"ingested {key} but the session produced no wiki changes (no page created, "
                f"updated, or deleted); retry with `citadel ingest --retry` or "
                f"`citadel ingest --force {key}`"
            )
        for old_key, new_key in report.moved:
            store.append_log(
                f"reorganized {new_key}: same content already ingested as {old_key}; "
                "recognized as moved, not re-ingested"
            )
        for key in report.unreadable:
            if key in report.cloud_placeholders:
                store.append_log(
                    f"could not ingest {key}: reads as all NUL bytes - likely a cloud-only "
                    "placeholder (online-only file); make it available offline"
                )
            else:
                store.append_log(f"could not ingest {key}: no readable text found (binary or unsupported); skipped")
        for key in report.sources_deleted:
            store.append_log(
                f"raw source {key} was deleted from disk; reconciled its citations out of the "
                "wiki and dropped it from the manifest"
            )
        # The wiki-history commit comes LAST, after the log/index/failures writes above, so one
        # commit captures the run's complete state. Best-effort by contract: the wiki is already
        # promoted, so a git problem is a report note, never a failed run.
        report.wiki_git = (
            wikigit.autocommit(
                f"citadel ingest: {len(report.processed)} processed, "
                f"{len(report.sources_deleted)} sources removed -> "
                f"{len(report.pages_created)} created, {len(report.pages_updated)} updated, "
                f"{len(report.pages_deleted)} deleted (model: {model})"
            )
            or ""
        )
        emit(
            "done",
            processed=len(report.processed),
            created=len(report.pages_created),
            updated=len(report.pages_updated),
            deleted=len(report.pages_deleted),
            broken=len(report.broken_links),
            moved=len(report.moved),
            unreadable=len(report.unreadable),
            sources_deleted=len(report.sources_deleted),
        )

    # Now that the completed sources have been finalized, re-raise a captured Ctrl+C so the
    # interrupt still aborts the run (the per-source `finally` already rolled back whichever
    # source was in flight when it landed).
    if pending_interrupt is not None:
        raise pending_interrupt

    return report
