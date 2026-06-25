"""Orchestrate one ingest run: drive an agentic CLI, then re-impose the invariants.

For each pending source the agent (``llm.run_ingest_session``) reads the raw file, searches
the wiki, and **edits the wiki page files directly** — there is no ops JSON to apply. This
module does the deterministic work around that autonomy:

- **back up** ``wiki/`` first, so a failed/half-finished session is rolled back (each source
  is all-or-nothing);
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

import hashlib
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config, llm, manifest, okf, store, validate
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

    def render(self) -> str:
        """Human-readable multi-line summary for CLI/MCP."""
        lines: list[str] = []
        lines.append(
            f"Ingest complete: {len(self.processed)} processed, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.pages_created)} created, "
            f"{len(self.pages_updated)} updated, "
            f"{len(self.pages_deleted)} deleted, "
            f"{len(self.moved)} reorganized, "
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


def _walk_files(root: Path) -> list[Path]:
    """Every file under ``root``, recursively, in deterministic order — skipping hidden files
    and hidden directories (a leading ``.``: ``.gitkeep``, ``.git``, etc.).

    Unlike the old top-level ``*.md`` glob, this picks up ANY file type (``.txt``/``.py``/
    ``.sql``/``.pdf``/…) and descends into sub-folders, so a user can organize ``raw/`` however
    they like and drop in arbitrary sources. The agent decides what text it can extract; a
    binary with no readable text is filtered out later by :func:`_is_ingestible`."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith("."):
                continue
            out.append(Path(dirpath) / name)
    return out


def _candidates(paths: list[str] | None) -> list[Path]:
    """Resolve requested paths (or default to all of ``RAW_DIR``) to a candidate list.

    A file path is taken as-is; a directory contributes ALL of its files, recursively (any
    extension, sub-folders included, hidden files/dirs skipped); with no paths, default to
    every file under ``config.RAW_DIR``."""
    candidates: list[Path] = []
    if paths:
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                candidates.extend(_walk_files(p))
            else:
                candidates.append(p)
    elif config.RAW_DIR.exists():
        candidates.extend(_walk_files(config.RAW_DIR))
    return candidates


def _is_ingestible(path: Path) -> bool:
    """True if the agent has a realistic chance of extracting text from this raw file.

    We try to OPEN everything rather than allow-listing extensions: plain text and code
    (``.txt``/``.py``/``.sql``/``.json``/…) read directly, and a PDF (detected by its ``%PDF-``
    magic) is handed to the agent because its reader can pull text out. Only a "weird binary" —
    a NUL byte, or a high proportion of non-text bytes in the sniffed prefix — is rejected; the
    caller logs those as unreadable instead of spending an LLM session on a blob. An empty file
    is ingestible (the agent simply finds nothing to add), not a binary failure."""
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
) -> tuple[list[Path], list[str], list[tuple[str, str, str, bool]], list[Path]]:
    """Split candidates into ``(pending, skipped, moved, unreadable)`` in one filesystem walk.

    - ``pending``: new/changed files with novel, readable content — fed to the agent (sorted,
      de-duplicated by resolved path).
    - ``skipped``: rel-keys whose sha already matches the manifest (already ingested).
    - ``moved``: ``(old_key, new_key, sha, old_gone)`` for a file that appeared under a NEW path
      whose bytes were already ingested under another key — a reorganize (rename/move) or a
      duplicate. Recognized, NOT re-ingested. ``old_gone`` is True when the prior path no longer
      exists on disk (a real move, so its wiki references get repointed).
    - ``unreadable``: files with no extractable text (binary/unsupported) — logged, not ingested.

    Move/duplicate detection only fires for a genuinely NEW path (``key not in manifest_dict``):
    an in-place edit of an already-tracked file is always re-ingested, even if its new content
    happens to match another file.
    """
    by_sha: dict[str, list[str]] = {}
    for k, v in manifest_dict.items():
        by_sha.setdefault(v, []).append(k)

    pending: list[Path] = []
    skipped: list[str] = []
    moved: list[tuple[str, str, str, bool]] = []
    unreadable: list[Path] = []
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
                gone = sorted(k for k in prior if not (config.REPO_ROOT / k).exists())
                old_key = gone[0] if gone else prior[0]
                moved.append((old_key, key, sha, bool(gone)))
                continue
        if not _is_ingestible(src):
            unreadable.append(src)
            continue
        pending.append(src)
    return sorted(pending), skipped, moved, unreadable


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


def _validate_and_restamp(rel_paths: list[str], rel_key: str) -> list[str]:
    """Re-impose invariants on each changed page (``validate.validate_page``) and, if clean,
    canonicalize + re-stamp it through ``store.write_page`` (so the YAML is canonical, the
    ``type`` is enforced, and a fresh UTC ``timestamp`` is set even though the agent wrote the
    file). Returns one error string per error-severity validation issue; when any are returned
    the caller rolls the whole source back (all-or-nothing), so an invalid page never persists
    in the wiki — the issues are surfaced in the report instead."""
    errors: list[str] = []
    for rel_path in sorted(set(rel_paths)):
        try:
            page = store.read_page(rel_path)
        except (FileNotFoundError, okf.OKFError) as exc:
            errors.append(f"{rel_key}: re-read {rel_path}: {exc}")
            continue
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


def _backup_wiki() -> str | None:
    """Copy ``wiki/`` to a fresh temp dir and return that dir (the rollback point), or None
    if the wiki does not exist yet (first run)."""
    src = config.WIKI_DIR
    if not src.is_dir():
        return None
    tmp = tempfile.mkdtemp(prefix="okf_wiki_bak_")
    shutil.copytree(src, os.path.join(tmp, "wiki"))
    return tmp


def _restore_wiki(backup_tmp: str | None) -> None:
    """Restore ``wiki/`` from a backup made by :func:`_backup_wiki`. If there was no backup
    (the wiki did not exist before this source), remove whatever the agent created."""
    dst = config.WIKI_DIR
    if backup_tmp is None:
        if dst.exists():
            shutil.rmtree(dst, ignore_errors=True)
        return
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(os.path.join(backup_tmp, "wiki"), dst)


def ingest(paths: list[str] | None = None, progress=None) -> IngestReport:
    """Run one ingest. Exactly one ``llm.run_ingest_session`` call per pending source.

    Before the per-source loop, candidates are partitioned (``_partition_sources``) into
    pending / already-ingested / **reorganized** (a file that only moved or is a byte-for-byte
    duplicate — recognized, not re-ingested; a real move repoints the wiki's resource/citation
    references and re-keys the manifest) / **unreadable** (no extractable text, e.g. a binary —
    logged and marked done, never fed to the agent).

    Per pending source: back up the wiki, snapshot it, run the agent (which edits ``wiki/``
    directly), snapshot again, diff to learn what changed, validate + re-stamp the changed pages,
    and repoint any renamed-page links. On a per-source exception (a missing/unusable CLI, a
    timeout, etc.) the wiki is rolled back to its pre-source state and the error is collected,
    so the source is retried next run. Finalization (rebuild_indexes + find_broken_links +
    append_log) happens once, if any source was processed, reorganized, or found unreadable.

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
    report = IngestReport([], [], [], [])

    pending, skipped, moved, unreadable = _partition_sources(paths, manifest_dict)
    report.skipped = skipped

    # --- Reorganized sources: a file that only MOVED (or is a byte-for-byte duplicate) is
    # recognized and NOT re-ingested. For a real move (the old path is gone) repoint the wiki's
    # `resource` frontmatter and citation links to the new path so nothing breaks, then drop the
    # stale manifest key. Either way, record the new key so future runs skip it immediately. ---
    repointed = False
    for old_key, new_key, sha, old_gone in moved:
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
        manifest_dict[new_key] = sha
        report.moved.append((old_key, new_key))
    if report.moved:
        manifest.save(manifest_dict)

    # --- Unreadable sources: no extractable text (binary/unsupported). Mark them done (so they
    # are not re-checked and re-logged every run) and surface + log them — the file "did not
    # work", but it is not a hard error that should fail the whole run. ---
    for src in unreadable:
        key = manifest.rel_key(src)
        try:
            manifest_dict[key] = manifest.file_sha256(src)
        except OSError:
            continue
        report.unreadable.append(key)
    if unreadable:
        manifest.save(manifest_dict)

    emit(
        "start",
        pending=len(pending),
        skipped=len(skipped),
        moved=len(report.moved),
        unreadable=len(report.unreadable),
    )

    # A Ctrl+C (or other BaseException) raised mid-loop is captured here, not allowed to
    # propagate immediately, so finalization still runs for the already-completed sources
    # before it is re-raised. Without this, the per-source-persisted manifest could outlive a
    # stale index/log: a later run with nothing pending would never rebuild the derived files.
    pending_interrupt: BaseException | None = None
    for index, src in enumerate(pending, 1):
        rel_key = manifest.rel_key(src)
        emit("source_start", index=index, total=len(pending), source=rel_key)
        started = time.monotonic()
        backup: str | None = None
        succeeded = False
        try:
            backup = _backup_wiki()
            before_pages = store.load()
            before = _hash_pages(before_pages)

            llm.run_ingest_session(rel_key)  # the agent edits wiki/ directly

            after = _snapshot()
            created, updated, deleted = _diff(before, after)

            # Re-impose invariants on (and re-stamp) every changed page. A validation error
            # means the agent produced an invalid page (missing field, fabricated citation,
            # leaked artifact, ...): roll the WHOLE source back (all-or-nothing) and leave it
            # un-done so it is retried next run, rather than committing an invalid wiki state.
            val_errors = _validate_and_restamp(created + updated, rel_key)
            if val_errors:
                # Invalid page(s): leave the source un-done and let `finally` roll the wiki
                # back (succeeded is still False) — all-or-nothing, retried next run.
                report.errors.extend(val_errors)
                emit(
                    "source_error",
                    index=index,
                    total=len(pending),
                    source=rel_key,
                    error=val_errors[0],
                    seconds=time.monotonic() - started,
                )
                continue

            # Repoint inbound links for any rename the agent did not fully fix.
            _repair_renames(before_pages, created, deleted)

            report.pages_created.extend(created)
            report.pages_updated.extend(updated)
            report.pages_written.extend(created + updated)
            report.pages_deleted.extend(deleted)

            manifest.mark_done(manifest_dict, src)
            # Persist progress immediately after each completed source: a later Ctrl+C (or a
            # crash) must not erase sources already finished this run. (The old code saved the
            # manifest only once, in finalization, which a propagating interrupt skipped.)
            manifest.save(manifest_dict)
            report.processed.append(rel_key)
            succeeded = True
            emit(
                "source_done",
                index=index,
                total=len(pending),
                source=rel_key,
                created=len(created),
                updated=len(updated),
                deleted=len(deleted),
                seconds=time.monotonic() - started,
            )
        except Exception as exc:  # noqa: BLE001 - collect per-source, roll back, keep going
            report.errors.append(f"{rel_key}: {exc}")
            emit(
                "source_error",
                index=index,
                total=len(pending),
                source=rel_key,
                error=str(exc),
                seconds=time.monotonic() - started,
            )
        except BaseException as exc:  # noqa: BLE001 - Ctrl+C etc.: capture, finalize, re-raise
            # A KeyboardInterrupt/SystemExit is not a per-source error to collect — capture it,
            # let `finally` roll this in-flight source back, then stop the loop and re-raise it
            # AFTER finalization (below) so the completed sources don't keep stale indexes.
            pending_interrupt = exc
        finally:
            # Roll back unless the source fully succeeded. This `finally` is the single rollback
            # point for every non-success exit — the validation-error `continue`, an ordinary
            # Exception, and a captured BaseException — so none of them can leave a half-edit.
            if not succeeded:
                _restore_wiki(backup)
            if backup:
                shutil.rmtree(backup, ignore_errors=True)

        # Stop taking new sources once an interrupt was captured, but fall through to
        # finalization for the sources already completed this run.
        if pending_interrupt is not None:
            break

    if report.processed or report.moved or report.unreadable or repointed:
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
                f"{len(report.pages_updated)} updated, {len(report.pages_deleted)} deleted"
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
        emit(
            "done",
            processed=len(report.processed),
            created=len(report.pages_created),
            updated=len(report.pages_updated),
            deleted=len(report.pages_deleted),
            broken=len(report.broken_links),
            moved=len(report.moved),
            unreadable=len(report.unreadable),
        )

    # Now that the completed sources have been finalized, re-raise a captured Ctrl+C so the
    # interrupt still aborts the run (the per-source `finally` already rolled back whichever
    # source was in flight when it landed).
    if pending_interrupt is not None:
        raise pending_interrupt

    return report
