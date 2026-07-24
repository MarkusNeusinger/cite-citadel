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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import (
    config,
    extract,
    failures,
    llm,
    manifest,
    okf,
    pdftext,
    repo,
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
    # The model/backend that imported this run's sources (config.ingest_model_label), recorded
    # per-source in the manifest and surfaced here so the report says WHICH model ran.
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
    # rel-keys of tracked sources that VANISHED from disk (a full run only): their provenance is
    # reconciled out of the wiki by a cleanup agent session, then the manifest key is dropped.
    sources_deleted: list[str] = field(default_factory=list)
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
        if self.unreadable:
            lines.append("Unreadable (no extractable text; not ingested):")
            for p in self.unreadable:
                if p in self.cloud_placeholders:
                    lines.append(
                        f"  - {p}  (reads as all NUL bytes - a cloud-only placeholder? make it available offline)"
                    )
                else:
                    lines.append(f"  - {p}")
        if self.duplicates:
            lines.append("Skipped as duplicate (same basename as another format that was ingested):")
            lines.extend(f"  - {dropped} (kept {kept})" for dropped, kept in self.duplicates)
        if self.duplicates_forced:
            lines.append("Duplicate formats deliberately ingested (forced):")
            lines.extend(f"  - {d} (ingested alongside {kept} — forced)" for d, kept in self.duplicates_forced)
        if self.skipped:
            lines.append("Skipped (already ingested):")
            lines.extend(f"  - {p}" for p in self.skipped)
        if self.broken_links:
            lines.append("WARNING — broken cross-links (run `citadel lint`):")
            lines.extend(f"  - {src} -> {tgt}" for src, tgt in self.broken_links)
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in self.errors)
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


def _scan_tree(root: Path, walk: _Walk) -> None:
    """ONE iterative ``os.scandir`` walk over ``root``, appending onto ``walk`` — this replaces
    the two ``os.walk`` passes (files + repos) with a single traversal whose ``DirEntry.stat``
    results are kept for the scan-cache quick check.

    Same skip rules as before: hidden names (leading ``.``), OS/junk ignore globs
    (:func:`_is_ignored_name`), and — with repo support on — no descending into a git repository
    (collected as one repo source instead). Any file type in any sub-folder is picked up;
    ``follow_symlinks=False`` throughout, so a symlinked directory is never recursed into (a
    cycle on a share must not hang discovery). Deterministic order (names sorted per directory,
    depth-first). NEVER raises: a top-level failure marks the root unreachable; a failure deeper
    in records a walk error (either one disarms the deletion sweep — see :func:`ingest`)."""
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
                    # Deliberately NOT _is_repo_source: its corpus-root guard resolve()s every root per call
                    # — too costly per-directory on a network share (a subdir is never a configured root here).
                    if config.REPO_SUPPORT and repo.is_repo_dir(path):
                        walk.repos.append(path)  # one repo source; the file walk stops here
                    else:
                        subdirs.append(path)
                elif entry.is_file(follow_symlinks=False):
                    walk.files.append((path, entry.stat(follow_symlinks=False)))
            except OSError as exc:
                walk.errors.append(f"{path}: {exc}")
        stack.extend(reversed(subdirs))  # LIFO -> depth-first in sorted order


def _discover_walk(paths: list[str] | None) -> _Walk:
    """Resolve requested paths (or default to every configured raw root, ``config.RAW_DIRS``)
    into one :class:`_Walk`. A requested file path is stat'ed and taken as-is (even a hidden or
    ignore-matched name — explicit wins, as before; one that is missing or not a regular file is
    silently dropped, replacing the old per-candidate ``is_file()``); a requested directory
    contributes its whole subtree — unless it is itself a repo source, which
    :func:`_discover_repos` handles. Roots are de-duplicated by resolved path."""
    walk = _Walk()
    if paths:
        for raw in paths:
            p = Path(raw)
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
    descended into repos file-by-file — the legacy behavior)."""
    if not config.REPO_SUPPORT:
        return []
    found: list[Path] = list(walk.repos)
    if paths:
        for raw in paths:
            p = Path(raw)
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
            target = okf.safe_join(config.WIKI_DIR, page.rel_path)
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
    """Best-effort recursive delete that tolerates the Windows read-only bit and the transient
    locks/latency common on network shares. Retries a few times and never raises — a tree that
    still will not delete is left for the caller (which overwrites it via ``dirs_exist_ok=True``),
    which beats aborting the whole run.

    Replaces a bare ``shutil.rmtree(..., ignore_errors=True)``: that swallowed the failure and left
    the directory in place, which then made a follow-up ``copytree`` crash with ``FileExistsError``."""

    def _clear_readonly(func, p, _exc):
        # Windows marks some files read-only; add the write bit (OR onto the existing mode so we
        # don't wipe read/execute — clearing a directory's execute bit on POSIX would block the
        # traversal the retried delete needs) and retry the one failed operation.
        try:
            os.chmod(p, os.stat(p).st_mode | stat.S_IWRITE)
            func(p)
        except OSError:
            pass

    for attempt in range(_RMTREE_ATTEMPTS):
        if not os.path.exists(path):
            return
        shutil.rmtree(path, onexc=_clear_readonly)
        if not os.path.exists(path):
            return
        time.sleep(0.2 * (attempt + 1))


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
    _STAGING_SEQ += 1
    staging = parent / f"{prefix}{os.getpid()}.{_STAGING_SEQ}"
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


@contextlib.contextmanager
def _redirect_wiki(staging: Path):
    """Point every wiki-derived config path — and ``CITADEL_WIKI_DIR`` for child processes (the agentic
    CLI and the ``citadel check`` it shells out to) — at ``staging`` for the duration of one
    session, so the agent reads/writes/validates the STAGING copy rather than the live wiki. The
    raw/docs dirs are left untouched. Everything is restored on exit (including an originally-unset
    ``CITADEL_WIKI_DIR``), so the redirect is invisible to the surrounding run."""
    staging = Path(staging)
    saved = (config.WIKI_DIR, config.INDEX_PATH, config.LOG_PATH, config.MANIFEST_PATH)
    env_had = "CITADEL_WIKI_DIR" in os.environ
    env_prev = os.environ.get("CITADEL_WIKI_DIR")
    config.WIKI_DIR = staging
    config.INDEX_PATH = staging / "index.md"
    config.LOG_PATH = staging / "log.md"
    config.MANIFEST_PATH = staging / ".citadel_ingested.json"
    os.environ["CITADEL_WIKI_DIR"] = str(staging)
    try:
        yield
    finally:
        config.WIKI_DIR, config.INDEX_PATH, config.LOG_PATH, config.MANIFEST_PATH = saved
        if env_had:
            os.environ["CITADEL_WIKI_DIR"] = env_prev  # type: ignore[assignment]
        else:
            os.environ.pop("CITADEL_WIKI_DIR", None)


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


def _promote(staging: Path, live: Path, allow_emptying: bool = False) -> None:
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
    only page legitimately leaves the wiki empty."""
    staging, live = Path(staging), Path(live)
    config.robust_mkdir(live)

    staging_content = _content_files(staging)
    live_content = _content_files(live)

    staging_pages = [r for r in staging_content if r.endswith(".md")]
    live_pages = [r for r in live_content if r.endswith(".md")]
    if not allow_emptying and not staging_pages and live_pages:
        raise okf.OKFError(
            "refusing to promote: the session left the wiki with no content pages "
            "(treated as a failed source so the live wiki is not emptied)"
        )

    # 1. Copy-over FIRST (atomic per page, only when the bytes differ).
    for rel, src in staging_content.items():
        dst = live / rel
        if not _files_equal(src, dst):
            config.robust_mkdir(dst.parent)
            _robust_copy_file(src, dst)

    # 2. Prune the content pages the agent deleted (reserved/generated files are left untouched).
    for rel in set(live_content) - set(staging_content):
        with contextlib.suppress(OSError):
            (live / rel).unlink()

    # 3. Best-effort sweep of any leftover *.citadeltmp from an earlier promote that was hard-killed
    #    between copyfile and os.replace. They are excluded from sync AND prune (reserved), so
    #    without this they could linger on the live wiki indefinitely.
    with contextlib.suppress(OSError):
        for tmp in live.rglob("*.citadeltmp"):
            with contextlib.suppress(OSError):
                tmp.unlink()

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


def _usage_fields(usage: llm.SessionUsage | None) -> dict:
    """A source's combined session usage as ``manifest.make_entry`` / ``make_repo_entry`` kwargs
    (``cost_usd``/``tokens_in``/``tokens_out``, only the known fields) — the one translation from
    the llm-layer shape to the manifest-layer stamp, so the done-hooks stay one-liners."""
    if usage is None:
        return {}
    out: dict = {}
    if usage.cost_usd is not None:
        out["cost_usd"] = usage.cost_usd
    if usage.input_tokens is not None:
        out["tokens_in"] = usage.input_tokens
    if usage.output_tokens is not None:
        out["tokens_out"] = usage.output_tokens
    return out


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


def _run_agent_sessions(session_fns, rel_key: str, extra_check=None, allow_emptying: bool = False) -> _SourceOutcome:
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
    or half-write the live wiki, which thus only ever contains FULLY imported sources. Trade-off
    accepted and documented: a failure/timeout/interrupt at segment N discards the whole
    staging copy — N-1 segments' agent work — and the source retries from segment 1 next run;
    the all-or-nothing guarantee is worth more than salvaged partial passes.

    On ANY failure — a validation error, a failed post-condition, or an exception from a session
    — the live wiki is left exactly as it was and ``ok`` is False; the caller leaves the source
    un-committed so it is retried next run. A propagating ``BaseException`` (Ctrl+C) during a
    session likewise leaves the live wiki untouched (nothing is promoted); during the brief
    promote it can leave that ONE source partially applied — a SUPERSET of valid pages, never an
    emptied wiki — which a later full run reconciles. Either way it re-raises for the caller's
    loop to capture. Staging is always discarded in ``finally``. The caller owns the manifest +
    report bookkeeping (different for a completed source vs. a removed one).

    An EMPTY ``session_fns`` (a deleted source nothing cites) succeeds immediately with zero page
    changes — before a staging copy is even made."""
    started = time.monotonic()
    if not session_fns:
        return _SourceOutcome(True)
    live = config.WIKI_DIR
    staging: Path | None = None
    created: list[str] = []
    updated: list[str] = []
    deleted: list[str] = []
    # Each session's backend-reported usage (None from the test fakes / silent backends),
    # combined into the outcome on EVERY return path — a rolled-back source still spent money.
    usage_parts: list[llm.SessionUsage | None] = []
    try:
        staging = _make_staging(live)
        with _redirect_wiki(staging):
            prev_pages = store.load()
            prev = _hash_pages(prev_pages)
            for i, session_fn in enumerate(session_fns):
                result = session_fn()  # the agent edits the STAGING copy, never the live wiki
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
                    )

                _repair_renames(prev_pages, seg_created, seg_deleted)

                created.extend(seg_created)
                updated.extend(seg_updated)
                deleted.extend(seg_deleted)
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
                    )

        # Every session was clean: commit the source onto the live wiki (config now points back
        # at live). This is the ONLY step that touches the live wiki, it happens ONCE per source,
        # and it is non-destructive — so an interrupt here still cannot empty it.
        _promote(staging, live, allow_emptying=allow_emptying)
        return _SourceOutcome(
            True, created, updated, deleted, [], time.monotonic() - started, usage=llm.combine_usage(usage_parts)
        )
    except Exception as exc:  # noqa: BLE001 - collect per-source, keep going; live wiki untouched
        # A raising session never returned its usage, but the backend may still have reported
        # what the FAILED attempt cost (claude's error envelope, gemini's stats file) — llm
        # carries that on the exception, so the run total honors "failed sessions included".
        salvaged = getattr(exc, "session_usage", None)
        usage_parts.append(salvaged if isinstance(salvaged, llm.SessionUsage) else None)
        return _SourceOutcome(
            False,
            errors=[f"{rel_key}: {exc}"],
            seconds=time.monotonic() - started,
            usage=llm.combine_usage(usage_parts),
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
    - ``build_sessions``: plans the source's agent session(s), returning ``(session_fns,
      tmpdirs)``: the callables run in order against ONE shared staging copy
      (:func:`_run_agent_sessions`), and the temp dirs the loop removes afterwards. It may raise
      — recorded as a per-source ``prepare_error`` failure, never aborting the run. An EMPTY
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
    """

    key: str
    build_sessions: Callable[[], tuple[list[Callable[[], llm.SessionUsage | None]], list[str]]]
    on_success: Callable[[llm.SessionUsage | None], None]
    prepare_error: str
    extra_check: Callable[[], list[str]] | None = None
    allow_emptying: bool = False
    sha_stat: tuple[str | None, os.stat_result | None] = (None, None)


def _run_source_jobs(jobs: list[_SourceJob], emit, report: IngestReport, failures_dict, model) -> BaseException | None:
    """Drive one GROUP of :class:`_SourceJob`s (deletion cleanups, files, or repos) through the
    ONE shared per-source loop: emit ``source_start``, plan the session(s), run them all-or-nothing
    against a single staging copy, then either record the failure (report + persistent failures
    catalog + ``source_error``) or run the job's success bookkeeping and emit ``source_done``.

    The progress vocabulary is frozen (pinned by tests): ``index``/``total`` count within THIS
    group, restarting at 1 per group, and the event payload keys are exactly what the three
    former loops emitted. Page changes reach the report only on success — a failed or interrupted
    source promotes nothing, so the report claims nothing for it.

    A ``BaseException`` (Ctrl+C) is RETURNED, not raised — the caller captures it, skips the
    remaining groups, finalizes the completed sources, and re-raises (the frozen
    capture-finalize-reraise pattern). The in-flight source was already rolled back by the
    session runner's ``finally``."""
    total = len(jobs)
    for index, job in enumerate(jobs, 1):
        # Keep the run lock's mtime fresh at every source boundary, so a long multi-source run
        # never crosses the staleness window another process could reclaim the lock through.
        runlock.heartbeat()
        emit("source_start", index=index, total=total, source=job.key)
        sha, st = job.sha_stat
        # Plan the session(s). A prepare failure (a temp write, a digest build) is a per-source
        # error, NOT a run-aborting one.
        try:
            sessions, tmpdirs = job.build_sessions()
        except Exception as exc:  # noqa: BLE001 - per-source, keep going
            detail = f"{job.key}: {job.prepare_error}: {exc}"
            report.errors.append(detail)
            failures.record(failures_dict, job.key, failures.ERROR, detail, model, sha=sha, st=st)
            emit("source_error", index=index, total=total, source=job.key, error=str(exc), seconds=0.0)
            continue
        try:
            outcome = _run_agent_sessions(
                sessions, job.key, extra_check=job.extra_check, allow_emptying=job.allow_emptying
            )
        except BaseException as exc:  # noqa: BLE001 - Ctrl+C etc.: runner rolled back; captured
            return exc
        finally:
            # Always remove every temp dir the plan produced (success, error, or interrupt).
            for tmp in tmpdirs:
                shutil.rmtree(tmp, ignore_errors=True)
        # The run's usage total counts every outcome — a failed source's sessions were paid for
        # too; only the per-source manifest stamp below is success-only. Deliberately NOT wired
        # through the BaseException path (the return above): an interrupted run re-raises and
        # its report is never rendered (_ingest_run's capture-finalize-reraise), so the in-flight
        # source's partial usage has no surface to appear on — the completed sources' manifest
        # stamps were already saved per-source with their usage intact.
        report.usage = llm.combine_usage([report.usage, outcome.usage])
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
            continue
        report.pages_created.extend(outcome.created)
        report.pages_updated.extend(outcome.updated)
        report.pages_written.extend(outcome.created + outcome.updated)
        report.pages_deleted.extend(outcome.deleted)
        job.on_success(outcome.usage)
        emit(
            "source_done",
            index=index,
            total=total,
            source=job.key,
            created=len(outcome.created),
            updated=len(outcome.updated),
            deleted=len(outcome.deleted),
            seconds=outcome.seconds,
        )
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


def ingest(
    paths: list[str] | None = None, progress=None, full_rescan: bool = False, force: bool = False
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
    forcing after a model/rules upgrade. ``force`` without explicit paths is refused HERE with a
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

    ``progress`` is an optional ``progress(event, data)`` callback (run start, before/after
    each source, before finalization); None for non-interactive callers. A failing callback
    never breaks ingest.
    """
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
        _sweep_stale_staging(config.WIKI_DIR)
        return _ingest_run(paths, progress, full_rescan=full_rescan, force=force)


def _ingest_run(paths: list[str] | None, progress, *, full_rescan: bool, force: bool) -> IngestReport:
    """The body of :func:`ingest`, running under the exclusive workspace run lock."""

    def emit(event: str, **data) -> None:
        if progress is not None:
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
    # Migration sweep: drop any entry a PREVIOUS run recorded for a file that is NOW ignored
    # (Thumbs.db & friends, before this feature existed). It still exists on disk, so a full run
    # would never re-detect it as deleted — clean it out of the manifest AND the failures catalog
    # directly so wiki/sources/index.md stops carrying the noise. Repo entries never match (their
    # key basename is a folder name), so this only touches junk-file keys.
    pruned_ignored = False
    for key in [k for k in manifest_dict if _is_ignored_name(PurePosixPath(k).name)]:
        del manifest_dict[key]
        pruned_ignored = True
    for key in [k for k in failures_dict if _is_ignored_name(PurePosixPath(k).name)]:
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

        def build() -> tuple[list, list[str]]:
            # Plan the pass(es): an Office source materializes its extracted text to a temp .md
            # the agent reads; an audio/video source is transcribed HERE through the whisper seam
            # (content-addressed cache; a raise is a retryable per-source prepare_error, and the
            # cache makes the retry free); a PDF's text layer is extracted HERE through the
            # optional pypdf seam (same content-addressed cache idea; a None — pypdf missing, no
            # text layer, unparsable — quietly falls back to the direct agent read, so the
            # pre-pass can never cost a session); a source too large for one context is SPLIT
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
            return sessions, tmpdirs

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
            manifest.mark_done(manifest_dict, src, model, rules_ver, sha=done_sha, st=done_stat, **_usage_fields(usage))
            # A source that had failed before (unreadable/errored/duplicate) now succeeded: drop
            # its persisted failure record.
            failures.clear(failures_dict, rel_key)
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
        )

    # Repo sources: each git repository under raw/ is folded in by ONE session reading a
    # deterministic digest of its high-signal files. A re-ingest (a later commit) diffs against
    # the stored commit so only the changed files are inlined — except a FORCED re-read (the
    # run-level ``force``), which re-digests in FULL (see _partition_repos).
    def _repo_job(rjob: _RepoJob) -> _SourceJob:
        def build() -> tuple[list, list[str]]:
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
            return sessions, [tmp]

        def done(usage: llm.SessionUsage | None) -> None:
            # On success the manifest records the repo's CURRENT commit identity, with a fresh
            # last-checked stamp (an agent session just verified this repo — the one event that
            # moves ingested_at) and the session's usage stamp when the backend reported one.
            manifest_dict[rjob.key] = manifest.make_repo_entry(
                repo.identity(rjob.path),
                model,
                repo.remote_url(rjob.path),
                rules_ver,
                ingested_at=manifest.now_iso(),
                **_usage_fields(usage),
            )
            failures.clear(failures_dict, rjob.key)
            manifest.save(manifest_dict)
            report.processed.append(rjob.key)

        return _SourceJob(key=rjob.key, build_sessions=build, on_success=done, prepare_error="build digest")

    # Deleted sources: a tracked source vanished from disk (full run only). If any page still
    # cites it, run a `kind="delete"` cleanup session that strips that provenance, gated by a
    # post-condition that the wiki no longer references it (else the whole cleanup is rolled back
    # and retried next full run — the manifest key is dropped only on success). A deletion that
    # nothing cites plans NO session and just loses its manifest key.
    def _delete_job(key: str) -> _SourceJob:
        def build() -> tuple[list, list[str]]:
            if not store.find_raw_references(key):
                return [], []  # nothing cites it: no cleanup session, just forget it below
            return [lambda: llm.run_ingest_session(key, kind="delete")], []

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
            pending_interrupt = _run_source_jobs(group, emit, report, failures_dict, model)

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
