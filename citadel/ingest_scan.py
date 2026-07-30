"""Source discovery and partitioning for ingest — the read-only front half of a run.

One iterative ``os.scandir`` walk over every configured raw root (:class:`_Walk` /
:func:`_scan_tree`), the guarded deletion sweep (:func:`_sweep_gone`), source classification
(text sniff, Office/image/audio/PDF routing, same-basename dedup), and the partitions the
orchestrator consumes: :func:`_partition_sources` (files) and :func:`_partition_repos` (git
repos). Everything here is offline and side-effect-free apart from refreshing manifest stat
caches in place (``_Scan.mutated`` tells the caller to save).

Split out of :mod:`citadel.ingest`, which re-exports these names — the module boundary is an
implementation detail; ``ingest._candidates`` etc. remain the addressable seams.
"""

from __future__ import annotations

import fnmatch
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import config, extract, grammar, manifest, repo, transcribe


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
