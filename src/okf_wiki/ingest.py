"""Orchestrate one ingest run: drive an agentic CLI, then re-impose the invariants.

For each pending source the agent (``llm.run_ingest_session``) reads the raw file, searches
the wiki, and **edits the wiki page files directly** — there is no ops JSON to apply. This
module does the deterministic work around that autonomy:

- run the agent against a **per-source staging copy** of the wiki (a sibling directory), so the
  **live wiki is never the agent's scratch space**: a clean session is promoted onto the live
  wiki, and a failed or aborted (Ctrl+C) one is discarded with the live wiki untouched. The
  promote is a non-destructive sync (copy-over then prune), so the live wiki can never be left
  empty or half-written — not even on a flaky network share, and not even if the promote is
  interrupted. Each source is all-or-nothing;
- snapshot the wiki BEFORE and AFTER the session and **diff by content hash** to learn what
  the agent created/updated/deleted (no return value needed);
- **validate + re-stamp** every changed page (``validate.validate_page`` re-imposes required
  fields / citations / link form; ``store.write_page`` canonicalizes YAML and stamps the
  ``timestamp`` the agent was told not to write); collect any validation errors;
- **repair renames** the agent may not have fully repointed (deterministic inbound-link fix
  via ``store.rewrite_links``, derived from the diff);
- once per run, rebuild indexes, surface broken links, and append a log line.

Idempotent: sources whose sha already matches the manifest are skipped, and a source is
marked done only on a clean session. ``llm.run_ingest_session`` is the single outside call
(tests monkeypatch it with a fake that writes files into the temp wiki).
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config, extract, llm, manifest, okf, repo, store, validate
from .okf import Page

# How many leading bytes to sniff when deciding whether a raw file holds text the agent can
# read. 64 KiB is plenty to classify text vs. binary without reading a huge file into memory.
_SNIFF_BYTES = 65536
# Bytes that count as "text" (the classic git binary heuristic): printable ASCII, the common
# whitespace/control bytes, plus EVERY high byte (0x80–0xFF) so UTF-8 / Latin-1 text is not
# misread as binary. A NUL byte — or a high proportion of other control bytes — marks a file
# binary. PDFs are detected separately by their magic header (the agent's reader extracts text
# from them), so they are not rejected here.
_TEXT_BYTES = bytes(
    {7, 8, 9, 10, 11, 12, 13, 27} | set(range(0x20, 0x7F)) | set(range(0x80, 0x100))
)


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
    # rel-keys of tracked sources that VANISHED from disk (a full run only): their provenance is
    # reconciled out of the wiki by a cleanup agent session, then the manifest key is dropped.
    sources_deleted: list[str] = field(default_factory=list)

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
            f"{len(self.errors)} errors."
        )
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
            lines.extend(f"  - {p}" for p in self.unreadable)
        if self.skipped:
            lines.append("Skipped (already ingested):")
            lines.extend(f"  - {p}" for p in self.skipped)
        if self.broken_links:
            lines.append("WARNING — broken cross-links (run `okf-wiki lint`):")
            lines.extend(f"  - {src} -> {tgt}" for src, tgt in self.broken_links)
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in self.errors)
        return "\n".join(lines)


def _same_path(a: Path, b: Path) -> bool:
    """True if ``a`` and ``b`` resolve to the same location (never raises)."""
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return a == b


def _is_repo_source(path: Path) -> bool:
    """True if ``path`` should be ingested as ONE repo source: repo support is on, it is a repo
    dir (``.git``/``.okfsource``), and it is NOT the corpus root ``RAW_DIR`` itself. The latter
    guard matters because a user may keep the whole ``raw/`` tree under git for backup — that must
    still be scanned file-by-file (its repo SUB-folders are the sources), not collapsed into one."""
    return (
        config.REPO_SUPPORT
        and repo.is_repo_dir(path)
        and not _same_path(path, config.RAW_DIR)
    )


def _prune_repo_dirs(parent: Path, dirnames: list[str]) -> list[str]:
    """Drop the sub-directories of ``parent`` that are repo roots (a ``.git`` or ``.okfsource``
    marker) when repo support is on, so the per-file walk does NOT descend into a repository — it
    is ingested as one source instead (see :mod:`okf_wiki.repo`). With repo support off, nothing is
    pruned and a repo's files are walked individually (the legacy behavior). Hidden dirs are always
    dropped, as before."""
    kept: list[str] = []
    for name in sorted(dirnames):
        if name.startswith("."):
            continue
        if _is_repo_source(parent / name):
            continue
        kept.append(name)
    return kept


def _walk_files(root: Path) -> list[Path]:
    """Every file under ``root``, recursively, in deterministic order — skipping hidden files
    and hidden directories (a leading ``.``: ``.gitkeep``, ``.git``, etc.) and NOT descending into
    git repositories (handled as one source each; see :func:`_prune_repo_dirs`).

    Unlike the old top-level ``*.md`` glob, this picks up ANY file type (``.txt``/``.py``/
    ``.sql``/``.pdf``/…) and descends into sub-folders, so a user can organize ``raw/`` however
    they like and drop in arbitrary sources. The agent decides what text it can extract; a
    binary with no readable text is filtered out later by :func:`_is_ingestible`."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = _prune_repo_dirs(Path(dirpath), dirnames)
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            out.append(Path(dirpath) / name)
    return out


def _candidates(paths: list[str] | None) -> list[Path]:
    """Resolve requested paths (or default to all of ``RAW_DIR``) to a candidate FILE list.

    A file path is taken as-is; a directory contributes ALL of its files, recursively (any
    extension, sub-folders included, hidden files/dirs skipped); with no paths, default to
    every file under ``config.RAW_DIR``. A directory that is itself a git repository is NOT
    expanded here — it is a repo source, returned by :func:`_discover_repos` instead."""
    candidates: list[Path] = []
    if paths:
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                if _is_repo_source(p):
                    continue
                candidates.extend(_walk_files(p))
            else:
                candidates.append(p)
    elif config.RAW_DIR.exists():
        candidates.extend(_walk_files(config.RAW_DIR))
    return candidates


def _repos_under(root: Path) -> list[Path]:
    """Every git repository (or ``.okfsource``-marked folder) under ``root``, not descending into a
    repo once found (a nested repo is part of its parent's tree). Deterministic order."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        parent = Path(dirpath)
        kept: list[str] = []
        for name in sorted(dirnames):
            if name.startswith("."):
                continue
            child = parent / name
            if repo.is_repo_dir(child):
                found.append(child)
            else:
                kept.append(name)
        dirnames[:] = kept
    return found


def _discover_repos(paths: list[str] | None) -> list[Path]:
    """The repo sources to ingest: directories under ``RAW_DIR`` (or under an explicitly requested
    directory) that are git repositories / ``.okfsource``-marked folders. An explicitly requested
    path that is itself a repo is taken directly. De-duplicated by resolved path, sorted. Empty when
    repo support is off."""
    if not config.REPO_SUPPORT:
        return []
    found: list[Path] = []
    if paths:
        for raw in paths:
            p = Path(raw)
            if not p.is_dir():
                continue
            if _is_repo_source(p):
                found.append(p)
            else:
                found.extend(_repos_under(p))
    elif config.RAW_DIR.exists():
        found.extend(_repos_under(config.RAW_DIR))
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
    so :func:`_partition_sources` routes them through :mod:`okf_wiki.extract` instead (a deck with
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


def _partition_sources(
    paths: list[str] | None, manifest_dict: dict[str, str]
) -> tuple[
    list[Path], list[str], list[tuple[str, str, str, bool]], list[Path], list[str], dict[Path, str]
]:
    """Split candidates into ``(pending, skipped, moved, unreadable, deleted, office_text)`` in one
    walk.

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
      session. Computed ONLY for a full run (``paths is None``); a path-scoped run never sweeps
      the whole manifest for deletions, so it can't surprise-prune sources it wasn't pointed at.
    - ``office_text``: ``{src_path: extracted_text}`` for the pending PowerPoint/Word sources whose
      text was extracted here to classify them — reused by the agent step so a ``.pptx``/``.docx``
      is parsed exactly once per run, not twice.

    Move/duplicate detection only fires for a genuinely NEW path (``key not in manifest_dict``):
    an in-place edit of an already-tracked file is always re-ingested, even if its new content
    happens to match another file.
    """
    by_sha: dict[str, list[str]] = {}
    for k, v in manifest_dict.items():
        if manifest.is_repo_entry(v):
            continue  # repo sources are versioned by commit, not sha — handled separately
        by_sha.setdefault(manifest.entry_sha(v), []).append(k)

    pending: list[Path] = []
    skipped: list[str] = []
    moved: list[tuple[str, str, str, bool]] = []
    unreadable: list[Path] = []
    # Office sources extracted here -> their text, so the agent step writes the temp .md without a
    # second ZIP/XML parse. Keyed by the same Path objects carried in `pending`.
    office_text: dict[Path, str] = {}
    seen: set[Path] = set()
    for src in _candidates(paths):
        try:
            resolved = src.resolve()
        except OSError:
            resolved = src
        if resolved in seen:
            continue
        seen.add(resolved)
        if not src.is_file():
            continue
        key = manifest.rel_key(src)
        try:
            changed = manifest.is_pending(manifest_dict, src)
        except OSError:
            # is_pending() hashes the file when it is already tracked; an already-ingested source
            # that became unreadable (permissions / transient IO) must NOT crash the whole run —
            # it is already in the wiki, so treat it as skipped rather than a fresh source.
            skipped.append(key)
            continue
        if not changed:
            skipped.append(key)
            continue
        # New/changed content. Hash once for move detection (and to fail closed on an OS read
        # error — a brand-new source we cannot read — by treating it as unreadable). The hash is
        # streamed (manifest.file_sha256), so even a large file stays memory-bounded.
        try:
            sha = manifest.file_sha256(src)
        except OSError:
            unreadable.append(src)
            continue
        if key not in manifest_dict:
            prior = sorted(k for k in by_sha.get(sha, []) if k != key)
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
        if not _is_ingestible(src):
            unreadable.append(src)
            continue
        pending.append(src)

    # Deleted sources: tracked keys whose file is gone (full run only). Exclude the source side
    # of a detected move — its old path is also gone, but that is a reorganize (references get
    # repointed), not a deletion to reconcile away.
    deleted: list[str] = []
    if paths is None:
        moved_old = {old_key for old_key, _new, _sha, old_gone in moved if old_gone}
        for key in sorted(manifest_dict):
            if key in moved_old:
                continue
            if manifest.is_repo_entry(manifest_dict[key]):
                continue  # repo deletions are detected by _partition_repos, not the file sweep
            if not config.source_path_for_key(key).exists():
                deleted.append(key)
    return sorted(pending), skipped, moved, unreadable, deleted, office_text


@dataclass
class _RepoJob:
    """One pending repo source: its on-disk ``path``, its source key (``raw/acme-service``), the
    session ``kind`` (``"repo"`` first time / ``"repo-reconcile"`` on a later commit), and the
    ``old_commit`` to diff against on a reconcile (None for a first ingest)."""

    path: Path
    key: str
    kind: str
    old_commit: str | None


def _partition_repos(
    repo_paths: list[Path], manifest_dict: dict[str, manifest.Entry], full_run: bool
) -> tuple[list[_RepoJob], list[tuple[str, str, str]], list[str], list[str]]:
    """Split discovered repos into ``(pending, moved, deleted, skipped)``.

    - ``pending``: repos that are new (``kind="repo"``) or whose commit changed since last ingest
      (``kind="repo-reconcile"``, carrying the old commit for the diff).
    - ``moved``: ``(old_key, new_key, identity)`` for a repo that appeared under a NEW path whose
      base commit matches a tracked repo whose old folder is gone — a rename; references get
      repointed, not re-ingested.
    - ``deleted``: tracked repo keys whose folder vanished (full run only) — their citations are
      reconciled out by the shared deletion-cleanup path.
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
        if manifest.is_repo_entry(stored) and manifest.entry_commit(stored) == ident:
            skipped.append(key)
            continue
        if key not in manifest_dict:
            base = ident.split("+", 1)[0]
            if base and not base.startswith("snap."):
                gone = sorted(
                    k for k in by_commit.get(base, [])
                    if k != key and not config.source_path_for_key(k).exists()
                )
                if gone:
                    moved.append((gone[0], key, ident))
                    continue
        old_commit = (
            manifest.entry_commit(stored) if manifest.is_repo_entry(stored) else None
        )
        kind = "repo-reconcile" if old_commit else "repo"
        pending.append(_RepoJob(path=path, key=key, kind=kind, old_commit=old_commit))

    deleted: list[str] = []
    if full_run:
        moved_old = {old for old, _new, _ident in moved}
        for key in sorted(repo_keys):
            if key in moved_old:
                continue
            if not config.source_path_for_key(key).exists():
                deleted.append(key)
    return pending, moved, deleted, skipped


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


def _diff(
    before: dict[str, str], after: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
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
        canonical = _canonical_resource_key(
            str(page.frontmatter.get("resource") or ""), rel_key
        )
        if canonical is not None:
            page.frontmatter["resource"] = canonical
        bad = [
            issue
            for issue in validate.validate_page(rel_path, page.frontmatter, page.body)
            if issue.severity == "error"
        ]
        if bad:
            for issue in bad:
                errors.append(
                    f"{rel_key}: invalid page {rel_path}: {issue.category}: {issue.detail}"
                )
            continue
        try:
            store.write_page(rel_path, page.frontmatter, page.body)
        except okf.OKFError as exc:
            errors.append(f"{rel_key}: rewrite {rel_path}: {exc}")
    return errors


def _repair_renames(
    before_pages: list[Page], created: list[str], deleted: list[str]
) -> None:
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
# (``OKF_WIKI_DIR`` pointing at an SMB/UNC path): a file may be momentarily locked (antivirus,
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
    """Copy ``src`` -> ``dst`` so the destination is never observed half-written: write a temp
    sibling then ``os.replace`` it into place (atomic on one volume), retrying the network-share
    hiccups that flake a single copy. Falls back to a direct copy if the atomic replace keeps
    failing, so a transient rename error never drops the update."""
    tmp = dst.with_name(dst.name + ".okftmp")
    for attempt in range(attempts):
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            return
        except OSError:
            with contextlib.suppress(OSError):
                if tmp.exists():
                    tmp.unlink()
            time.sleep(0.2 * (attempt + 1))
    shutil.copyfile(src, dst)  # last resort: direct, non-atomic copy (raises if it, too, fails)


def _make_staging(live: Path) -> Path:
    """Create a fresh STAGING copy of the live wiki and return its path.

    Staging is a SIBLING of the live wiki (same parent, same depth) — never a system temp dir —
    so every relative citation/cross-link the agent writes (``../../raw/x.md`` and page-to-page
    links) resolves identically before and after the promote. The agent edits this copy, so the
    live wiki is never the scratch space. Any leftover staging from a crashed run is removed first;
    if a flaky share refuses to delete it, a process-unique sibling is used instead so the agent
    never inherits stale pages. On a copy failure the partial staging is cleaned up before the
    error propagates (the caller reports it and the live wiki is untouched). When the live wiki does
    not exist yet (first run) staging starts empty."""
    base = live.parent / f".{live.name}.staging"
    staging = base
    _robust_rmtree(staging)
    if staging.exists():
        staging = live.parent / f".{live.name}.staging.{os.getpid()}"
        _robust_rmtree(staging)
    try:
        if live.is_dir():
            # Skip any half-written *.okftmp left in live by an interrupted promote, so a stray
            # temp never rides along into staging (and back out again).
            shutil.copytree(
                live, staging, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.okftmp")
            )
        else:
            config.robust_mkdir(staging)
    except OSError:
        _robust_rmtree(staging)
        raise
    return staging


@contextlib.contextmanager
def _redirect_wiki(staging: Path):
    """Point every wiki-derived config path — and ``OKF_WIKI_DIR`` for child processes (the agentic
    CLI and the ``okf-wiki check`` it shells out to) — at ``staging`` for the duration of one
    session, so the agent reads/writes/validates the STAGING copy rather than the live wiki. The
    raw/docs dirs are left untouched. Everything is restored on exit (including an originally-unset
    ``OKF_WIKI_DIR``), so the redirect is invisible to the surrounding run."""
    staging = Path(staging)
    saved = (config.WIKI_DIR, config.INDEX_PATH, config.LOG_PATH, config.MANIFEST_PATH)
    env_had = "OKF_WIKI_DIR" in os.environ
    env_prev = os.environ.get("OKF_WIKI_DIR")
    config.WIKI_DIR = staging
    config.INDEX_PATH = staging / "index.md"
    config.LOG_PATH = staging / "log.md"
    config.MANIFEST_PATH = staging / ".okf_ingested.json"
    os.environ["OKF_WIKI_DIR"] = str(staging)
    try:
        yield
    finally:
        config.WIKI_DIR, config.INDEX_PATH, config.LOG_PATH, config.MANIFEST_PATH = saved
        if env_had:
            os.environ["OKF_WIKI_DIR"] = env_prev  # type: ignore[assignment]
        else:
            os.environ.pop("OKF_WIKI_DIR", None)


def _promote(staging: Path, live: Path) -> None:
    """Copy a validated STAGING wiki onto the LIVE wiki WITHOUT ever emptying or half-writing it.

    Non-destructive sync: every staging file is written into live first (each page atomically, via
    :func:`_robust_copy_file`, and only when it actually differs), so at every instant the live wiki
    holds at least its previous content; only then are live files the staging copy no longer has
    pruned. A promote interrupted partway therefore leaves live a SUPERSET of valid pages — never an
    empty or corrupt tree — which the next run reconciles. Directory creation tolerates the network
    share's WinError 183 race. Promote runs ONLY after a session validated cleanly, so staging is
    known-good; as a final guard an unexpectedly-empty staging never prunes a non-empty live to
    nothing."""
    staging, live = Path(staging), Path(live)
    config.robust_mkdir(live)

    staging_rel: set[str] = set()
    for dirpath, _dirs, files in os.walk(staging):
        for name in files:
            src = Path(dirpath) / name
            rel = src.relative_to(staging)
            staging_rel.add(rel.as_posix())
            dst = live / rel
            if not _files_equal(src, dst):
                config.robust_mkdir(dst.parent)
                _robust_copy_file(src, dst)

    if not staging_rel:
        return  # safety valve: a broken/empty staging must not prune the live wiki to nothing

    for dirpath, _dirs, files in os.walk(live):
        for name in files:
            target = Path(dirpath) / name
            if target.relative_to(live).as_posix() not in staging_rel:
                with contextlib.suppress(OSError):
                    target.unlink()
    # Drop directories left empty by the prune (bottom-up), but keep the live root itself.
    for dirpath, _dirs, _files in os.walk(live, topdown=False):
        d = Path(dirpath)
        if d == live:
            continue
        with contextlib.suppress(OSError):
            if not any(d.iterdir()):
                d.rmdir()


@dataclass
class _SourceOutcome:
    """Result of one agent-driven source (ingest / reconcile / delete). ``ok`` means the edit
    was validated and promoted onto the live wiki (the caller still updates the manifest + report);
    ``ok is False`` means nothing was promoted — the live wiki is unchanged — and ``errors`` says
    why."""

    ok: bool
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0


def _run_one_agent_session(
    session_fn, rel_key: str, extra_check=None
) -> _SourceOutcome:
    """Run ONE agent session with full all-or-nothing safety, shared by the pending
    (ingest/reconcile) and deletion-cleanup loops.

    Makes a STAGING copy of the live wiki (a sibling dir), redirects the agent + its ``okf-wiki
    check`` there, snapshots staging, calls ``session_fn()`` (the agent edits the STAGING copy —
    never the live wiki), diffs to learn what changed, validates + re-stamps the changed pages,
    repoints renamed-page links, and runs an optional ``extra_check()`` post-condition (used by
    deletion cleanup to assert no reference to the removed source survived). Only on a CLEAN session
    is staging promoted onto the live wiki (a non-destructive copy-over-then-prune that can never
    empty or half-write it). On ANY failure — a validation error, a failed post-condition, or an
    exception from the session — the live wiki is left exactly as it was and ``ok`` is False; the
    caller leaves the source un-committed so it is retried next run. A propagating ``BaseException``
    (Ctrl+C) likewise leaves the live wiki untouched (nothing is promoted) and re-raises for the
    caller's loop to capture. Staging is always discarded in ``finally``. The caller owns the
    manifest + report bookkeeping (different for a completed source vs. a removed one)."""
    started = time.monotonic()
    live = config.WIKI_DIR
    staging: Path | None = None
    created: list[str] = []
    updated: list[str] = []
    deleted: list[str] = []
    try:
        staging = _make_staging(live)
        with _redirect_wiki(staging):
            before_pages = store.load()
            before = _hash_pages(before_pages)

            session_fn()  # the agent edits the STAGING copy, never the live wiki

            after = _snapshot()
            created, updated, deleted = _diff(before, after)

            val_errors = _validate_and_restamp(created + updated, rel_key)
            if val_errors:
                return _SourceOutcome(
                    False, errors=val_errors, seconds=time.monotonic() - started
                )

            _repair_renames(before_pages, created, deleted)

            if extra_check is not None:
                post_errors = extra_check()
                if post_errors:
                    return _SourceOutcome(
                        False, created, updated, deleted, post_errors, time.monotonic() - started
                    )

        # Clean session: commit it onto the live wiki (config now points back at live). This is the
        # ONLY step that touches the live wiki, and it is non-destructive — so an interrupt here
        # still cannot empty it.
        _promote(staging, live)
        return _SourceOutcome(
            True, created, updated, deleted, [], time.monotonic() - started
        )
    except Exception as exc:  # noqa: BLE001 - collect per-source, keep going; live wiki untouched
        return _SourceOutcome(
            False, errors=[f"{rel_key}: {exc}"], seconds=time.monotonic() - started
        )
    finally:
        # Discard staging on every exit (a clean session already promoted it; a failed or
        # interrupted one never touched the live wiki). A flaky share that refuses the delete only
        # leaves an inert sibling for the next run to clear — the live wiki is never at risk.
        if staging is not None:
            _robust_rmtree(staging)


def _office_write_temp(text: str, name: str) -> tuple[str, str]:
    """Materialize already-extracted Office ``text`` as a fresh temp ``.md`` (named after the
    source's ``name``) for the agent to READ, and return ``(read_key, tmpdir)``: ``read_key`` is the
    path the agent reads (it still cites the ORIGINAL source), and ``tmpdir`` is the temp directory
    the caller MUST remove after the session. Raises ``OSError`` only if the temp file cannot be
    written — handled per-source by the caller, never aborting the whole run.

    The extraction already happened once in :func:`_partition_sources` (which is how the source was
    classified pending); this only writes that text out, so the ``.pptx``/``.docx`` is never parsed
    a second time."""
    tmpdir = tempfile.mkdtemp(prefix="okf_extract_")
    try:
        out = Path(tmpdir) / (Path(name).stem + ".md")
        out.write_text(text, encoding="utf-8")
    except OSError:
        # Don't leak the temp dir if the write fails — the caller never sees it to clean up.
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    return config.rel_or_abs_posix(out), tmpdir


def _pending_session(rel_key: str, kind: str, read_key: str | None) -> None:
    """Drive ONE ingest/reconcile agent session. When ``read_key`` is set (an Office source whose
    text was extracted), point the agent at it via ``read_path``; otherwise call exactly as before
    so a non-Office source — and every existing test's faked session — is byte-for-byte unchanged."""
    if read_key:
        llm.run_ingest_session(rel_key, kind=kind, read_path=read_key)
    else:
        llm.run_ingest_session(rel_key, kind=kind)


def ingest(paths: list[str] | None = None, progress=None) -> IngestReport:
    """Run one ingest. Exactly one ``llm.run_ingest_session`` call per pending or deleted source.

    Before the per-source loop, candidates are partitioned (``_partition_sources``) into
    pending / already-ingested / **reorganized** (a file that only moved or is a byte-for-byte
    duplicate — recognized, not re-ingested; a real move repoints the wiki's resource/citation
    references and re-keys the manifest) / **unreadable** (no extractable text, e.g. a binary —
    logged and marked done, never fed to the agent) / **deleted** (a tracked source that
    vanished from disk — full runs only).

    Per pending source: run the agent against a per-source STAGING copy of the wiki (a sibling
    dir), snapshot it before/after, diff to learn what changed, validate + re-stamp the changed
    pages, repoint any renamed-page links, and — only on a clean session — promote staging onto the
    live wiki with a non-destructive sync. A source already tracked in the manifest but with new
    bytes is a re-ingest, run with ``kind="reconcile"`` so the agent UPDATES/REMOVES the stale
    facts it produced rather than only appending. On a per-source exception (a missing/unusable
    CLI, a timeout, etc.) — or a Ctrl+C — nothing is promoted, so the live wiki is left exactly as
    it was and the error is collected, so the source is retried next run.

    Per deleted source (full run only): if any wiki page still cites it, run a ``kind="delete"``
    cleanup session that strips those facts/citations, gated by a post-condition that the wiki no
    longer references it (else the whole cleanup is rolled back and retried); then drop its
    manifest key. A deleted source nothing cites is simply dropped from the manifest. Finalization
    (rebuild_indexes + find_broken_links + append_log) happens once, if any source was processed,
    reorganized, found unreadable, or removed.

    ``progress`` is an optional ``progress(event, data)`` callback (run start, before/after
    each source, before finalization); None for non-interactive callers. A failing callback
    never breaks ingest.
    """

    def emit(event: str, **data) -> None:
        if progress is not None:
            try:
                progress(event, data)
            except Exception:  # noqa: BLE001 - progress must never break ingest
                pass

    manifest_dict = manifest.load()
    # The model/backend that will import this run's sources — recorded per-source in the manifest
    # so you can see which raw file was imported by which model. Resolved once (it does not change
    # mid-run) and read at call time so tests can monkeypatch the backend/model.
    model = config.ingest_model_label()
    report = IngestReport([], [], [], [], model=model)

    pending, skipped, moved, unreadable, deleted_sources, office_text = _partition_sources(
        paths, manifest_dict
    )
    # Git repositories under raw/ are ingested as ONE source each (a digest), versioned by commit.
    # Discover + partition them alongside the file sources; a vanished repo folder is reconciled out
    # by the SAME deletion-cleanup path as a file (its citations point at the repo folder key).
    repo_paths = _discover_repos(paths)
    repo_pending, repo_moved, repo_deleted, repo_skipped = _partition_repos(
        repo_paths, manifest_dict, paths is None
    )
    report.skipped = skipped + repo_skipped
    deleted_sources = deleted_sources + repo_deleted
    # A pending source whose key is ALREADY tracked is a re-ingest of changed bytes (reconcile);
    # one not yet tracked is brand new. Captured before the manifest is mutated below.
    changed_keys = {manifest.rel_key(p) for p in pending} & set(manifest_dict)

    # --- Reorganized sources: a file that only MOVED (or is a byte-for-byte duplicate) is
    # recognized and NOT re-ingested. For a real move (the old path is gone) repoint the wiki's
    # `resource` frontmatter and citation links to the new path so nothing breaks, then drop the
    # stale manifest key. Either way, record the new key so future runs skip it immediately. ---
    repointed = False
    for old_key, new_key, sha, old_gone in moved:
        # A move/duplicate is NOT a re-ingest: carry over the model that originally imported this
        # content (recorded under the old key) rather than stamping it with this run's model.
        carried_model = manifest.model_of(manifest_dict, old_key)
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
        manifest_dict[new_key] = manifest.make_entry(sha, carried_model)
        report.moved.append((old_key, new_key))
    # Repo moves: a repo whose folder was renamed (same base commit, old path gone). Repoint its
    # citations/`resource` to the new folder key and carry over its provenance — not a re-ingest.
    for old_key, new_key, ident in repo_moved:
        carried_model = manifest.model_of(manifest_dict, old_key)
        old_entry = manifest_dict.get(old_key)
        carried_remote = manifest.entry_remote(old_entry) if old_entry is not None else None
        if old_key != new_key:
            try:
                if store.rewrite_raw_references(old_key, new_key):
                    repointed = True
            except Exception as exc:  # noqa: BLE001 - collect, don't re-key, retry next run
                report.errors.append(f"{new_key}: repoint refs from {old_key}: {exc}")
                continue
            manifest_dict.pop(old_key, None)
        manifest_dict[new_key] = manifest.make_repo_entry(ident, carried_model, carried_remote)
        report.moved.append((old_key, new_key))
    if report.moved:
        manifest.save(manifest_dict)

    # --- Unreadable sources: no extractable text (binary/unsupported). Mark them done (so they
    # are not re-checked and re-logged every run) and surface + log them — the file "did not
    # work", but it is not a hard error that should fail the whole run. ---
    for src in unreadable:
        key = manifest.rel_key(src)
        try:
            # No model imported it (it was only sniffed and skipped), so record the sha alone.
            manifest_dict[key] = manifest.make_entry(manifest.file_sha256(src), None)
        except OSError:
            continue
        report.unreadable.append(key)
    if unreadable:
        manifest.save(manifest_dict)

    emit(
        "start",
        pending=len(pending),
        skipped=len(report.skipped),
        moved=len(report.moved),
        unreadable=len(report.unreadable),
        deleted=len(deleted_sources),
        repos=len(repo_pending),
    )

    # A Ctrl+C (or other BaseException) raised mid-loop is captured here, not allowed to
    # propagate immediately, so finalization still runs for the already-completed sources
    # before it is re-raised. Without this, the per-source-persisted manifest could outlive a
    # stale index/log: a later run with nothing pending would never rebuild the derived files.
    pending_interrupt: BaseException | None = None
    for index, src in enumerate(pending, 1):
        rel_key = manifest.rel_key(src)
        # An already-tracked key with new bytes is a re-ingest: reconcile (update/remove stale
        # facts) rather than only appending. A brand-new key is a plain ingest.
        kind = "reconcile" if rel_key in changed_keys else "ingest"
        emit("source_start", index=index, total=len(pending), source=rel_key)

        # PowerPoint/Word were extracted once during partitioning; materialize that text to a temp
        # file the agent reads instead of the binary, while the wiki still cites the original `src`.
        # A non-Office source isn't in `office_text`, so read_key stays None (the agent reads it
        # directly, unchanged). A temp-write failure is a per-source error, NOT a run-aborting
        # interrupt, so it is collected and the loop continues.
        read_key: str | None = None
        extract_tmp: str | None = None
        office = office_text.get(src)
        if office is not None:
            try:
                read_key, extract_tmp = _office_write_temp(office, src.name)
            except OSError as exc:
                report.errors.append(f"{rel_key}: write extracted office text: {exc}")
                emit(
                    "source_error",
                    index=index,
                    total=len(pending),
                    source=rel_key,
                    error=str(exc),
                    seconds=0.0,
                )
                continue

        try:
            outcome = _run_one_agent_session(
                lambda rk=rel_key, k=kind, rp=read_key: _pending_session(rk, k, rp), rel_key
            )
        except BaseException as exc:  # noqa: BLE001 - Ctrl+C etc.: capture, finalize, re-raise
            # The in-flight source was already rolled back inside the helper's `finally`; capture
            # the interrupt, stop taking new sources, and re-raise it after finalization below.
            pending_interrupt = exc
            break
        finally:
            # Always remove the extracted-text temp dir (success, error, or interrupt-break).
            if extract_tmp:
                shutil.rmtree(extract_tmp, ignore_errors=True)

        if not outcome.ok:
            report.errors.extend(outcome.errors)
            emit(
                "source_error",
                index=index,
                total=len(pending),
                source=rel_key,
                error=outcome.errors[0] if outcome.errors else "",
                seconds=outcome.seconds,
            )
            continue

        report.pages_created.extend(outcome.created)
        report.pages_updated.extend(outcome.updated)
        report.pages_written.extend(outcome.created + outcome.updated)
        report.pages_deleted.extend(outcome.deleted)

        manifest.mark_done(manifest_dict, src, model)
        # Persist progress immediately after each completed source: a later Ctrl+C (or a crash)
        # must not erase sources already finished this run.
        manifest.save(manifest_dict)
        report.processed.append(rel_key)
        emit(
            "source_done",
            index=index,
            total=len(pending),
            source=rel_key,
            created=len(outcome.created),
            updated=len(outcome.updated),
            deleted=len(outcome.deleted),
            seconds=outcome.seconds,
        )

    # --- Repo sources: each git repository under raw/ is folded in by ONE session reading a
    # deterministic digest of its high-signal files. A re-ingest (a later commit) diffs against the
    # stored commit so only the changed files are inlined. The wiki edit goes through the same
    # all-or-nothing helper; on success the manifest records the new commit. Skipped after an
    # interrupt was captured. ---
    if pending_interrupt is None:
        total_repos = len(repo_pending)
        for index, job in enumerate(repo_pending, 1):
            repo_key = job.key
            emit("source_start", index=index, total=total_repos, source=repo_key)

            # On a reconcile, restrict the inlined contents to the files changed since the stored
            # commit (and tell the agent what changed); a snapshot/unknown base re-digests in full.
            only: list[str] | None = None
            change_summary: str | None = None
            if job.kind == "repo-reconcile" and job.old_commit:
                changed = repo.changed_files(job.path, job.old_commit)
                if changed is not None:
                    only = changed
                    listing = "\n".join(changed) if changed else "(metadata only — no files)"
                    base = job.old_commit.split("+", 1)[0][:12]
                    change_summary = f"Changed files since {base}:\n{listing}"

            # Build the digest and materialize it to a temp file the agent reads (citing the repo
            # folder as the source of record). A build/temp failure is a per-source error.
            try:
                digest = repo.build_digest(
                    job.path, repo_key, only=only, change_summary=change_summary
                )
                read_key, repo_tmp = _office_write_temp(digest, job.path.name)
            except Exception as exc:  # noqa: BLE001 - per-source, keep going
                report.errors.append(f"{repo_key}: build digest: {exc}")
                emit(
                    "source_error", index=index, total=total_repos, source=repo_key,
                    error=str(exc), seconds=0.0,
                )
                continue

            try:
                outcome = _run_one_agent_session(
                    lambda rk=repo_key, k=job.kind, rp=read_key: llm.run_ingest_session(
                        rk, kind=k, read_path=rp
                    ),
                    repo_key,
                )
            except BaseException as exc:  # noqa: BLE001 - Ctrl+C: helper rolled back; re-raise later
                pending_interrupt = exc
                break
            finally:
                shutil.rmtree(repo_tmp, ignore_errors=True)

            if not outcome.ok:
                report.errors.extend(outcome.errors)
                emit(
                    "source_error", index=index, total=total_repos, source=repo_key,
                    error=outcome.errors[0] if outcome.errors else "", seconds=outcome.seconds,
                )
                continue

            report.pages_created.extend(outcome.created)
            report.pages_updated.extend(outcome.updated)
            report.pages_written.extend(outcome.created + outcome.updated)
            report.pages_deleted.extend(outcome.deleted)
            manifest_dict[repo_key] = manifest.make_repo_entry(
                repo.identity(job.path), model, repo.remote_url(job.path)
            )
            manifest.save(manifest_dict)
            report.processed.append(repo_key)
            emit(
                "source_done", index=index, total=total_repos, source=repo_key,
                created=len(outcome.created), updated=len(outcome.updated),
                deleted=len(outcome.deleted), seconds=outcome.seconds,
            )

    # --- Deleted sources: a tracked source vanished from disk (full run only). If any page still
    # cites it, run a `kind="delete"` cleanup session that strips that provenance, gated by a
    # post-condition that the wiki no longer references it (else the whole cleanup is rolled back
    # and retried next run); then drop its manifest key. A deletion that nothing cites just loses
    # its manifest key. Skipped entirely once an interrupt was captured — we are aborting. ---
    if pending_interrupt is None:
        total_del = len(deleted_sources)
        for index, key in enumerate(deleted_sources, 1):
            emit("source_start", index=index, total=total_del, source=key)
            if not store.find_raw_references(key):
                # Nothing cites it (e.g. a source that added no facts, or was unreadable): just
                # forget it so a later run does not re-detect the same deletion.
                manifest_dict.pop(key, None)
                manifest.save(manifest_dict)
                report.sources_deleted.append(key)
                emit(
                    "source_done", index=index, total=total_del, source=key,
                    created=0, updated=0, deleted=0, seconds=0.0,
                )
                continue
            try:
                outcome = _run_one_agent_session(
                    lambda k=key: llm.run_ingest_session(k, kind="delete"),
                    key,
                    extra_check=lambda k=key: [
                        f"{k}: still cited by {p} after cleanup"
                        for p in store.find_raw_references(k)
                    ],
                )
            except BaseException as exc:  # noqa: BLE001 - Ctrl+C: helper rolled back; re-raise later
                pending_interrupt = exc
                break

            if not outcome.ok:
                report.errors.extend(outcome.errors)
                emit(
                    "source_error",
                    index=index,
                    total=total_del,
                    source=key,
                    error=outcome.errors[0] if outcome.errors else "",
                    seconds=outcome.seconds,
                )
                continue

            report.pages_created.extend(outcome.created)
            report.pages_updated.extend(outcome.updated)
            report.pages_written.extend(outcome.created + outcome.updated)
            report.pages_deleted.extend(outcome.deleted)
            manifest_dict.pop(key, None)
            manifest.save(manifest_dict)
            report.sources_deleted.append(key)
            emit(
                "source_done",
                index=index,
                total=total_del,
                source=key,
                created=len(outcome.created),
                updated=len(outcome.updated),
                deleted=len(outcome.deleted),
                seconds=outcome.seconds,
            )

    if (
        report.processed
        or report.moved
        or report.unreadable
        or report.sources_deleted
        or repointed
    ):
        emit("finalize")
        # The manifest is already persisted incrementally (after each source, and right after the
        # move/unreadable bookkeeping) above, so a final save here would be redundant — just
        # rebuild the derived files (a move repoint can have changed page bodies/frontmatter).
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
            store.append_log(
                f"could not ingest {key}: no readable text found (binary or unsupported); skipped"
            )
        for key in report.sources_deleted:
            store.append_log(
                f"raw source {key} was deleted from disk; reconciled its citations out of the "
                "wiki and dropped it from the manifest"
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
