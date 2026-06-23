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

    def render(self) -> str:
        """Human-readable multi-line summary for CLI/MCP."""
        lines: list[str] = []
        lines.append(
            f"Ingest complete: {len(self.processed)} processed, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.pages_created)} created, "
            f"{len(self.pages_updated)} updated, "
            f"{len(self.pages_deleted)} deleted, "
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


def _candidates(paths: list[str] | None) -> list[Path]:
    """Resolve requested paths (or default to RAW_DIR/*.md) to a candidate list.

    A file is taken as-is; a directory contributes its top-level ``*.md`` files;
    with no paths, default to every ``*.md`` directly under ``config.RAW_DIR``.
    """
    candidates: list[Path] = []
    if paths:
        for raw in paths:
            p = Path(raw)
            if p.is_dir():
                candidates.extend(sorted(p.glob("*.md")))
            else:
                candidates.append(p)
    elif config.RAW_DIR.exists():
        candidates.extend(sorted(config.RAW_DIR.glob("*.md")))
    return candidates


def _partition_sources(paths: list[str] | None) -> tuple[list[Path], list[str]]:
    """Split candidates into ``(pending, skipped)`` in a single filesystem walk.

    ``pending`` are existing files the manifest reports as new/changed (sorted,
    de-duplicated by resolved path); ``skipped`` are the rel-keys of candidates
    whose sha already matches the manifest.
    """
    manifest_dict = manifest.load()
    pending: list[Path] = []
    skipped: list[str] = []
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
        if manifest.is_pending(manifest_dict, src):
            pending.append(src)
        else:
            skipped.append(manifest.rel_key(src))
    return sorted(pending), skipped


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

    Per source: back up the wiki, snapshot it, run the agent (which edits ``wiki/`` directly),
    snapshot again, diff to learn what changed, validate + re-stamp the changed pages, and
    repoint any renamed-page links. On a per-source exception (a missing/unusable CLI, a
    timeout, etc.) the wiki is rolled back to its pre-source state and the error is collected,
    so the source is retried next run. Finalization (manifest.save + rebuild_indexes +
    find_broken_links + append_log) happens once, only if any source was processed.

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

    pending, skipped = _partition_sources(paths)
    report.skipped = skipped
    emit("start", pending=len(pending), skipped=len(skipped))

    for index, src in enumerate(pending, 1):
        rel_key = manifest.rel_key(src)
        emit("source_start", index=index, total=len(pending), source=rel_key)
        started = time.monotonic()
        backup: str | None = None
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
                _restore_wiki(backup)
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
            report.processed.append(rel_key)
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
            _restore_wiki(backup)
            report.errors.append(f"{rel_key}: {exc}")
            emit(
                "source_error",
                index=index,
                total=len(pending),
                source=rel_key,
                error=str(exc),
                seconds=time.monotonic() - started,
            )
        finally:
            if backup:
                shutil.rmtree(backup, ignore_errors=True)

    if report.processed:
        emit("finalize")
        manifest.save(manifest_dict)
        store.rebuild_indexes()
        # Surface any cross-link left dangling by a restructure so it is never silent.
        report.broken_links = store.find_broken_links()
        store.append_log(
            f"ingest {report.processed} -> {len(report.pages_created)} created, "
            f"{len(report.pages_updated)} updated, {len(report.pages_deleted)} deleted"
        )
        emit(
            "done",
            processed=len(report.processed),
            created=len(report.pages_created),
            updated=len(report.pages_updated),
            deleted=len(report.pages_deleted),
            broken=len(report.broken_links),
        )

    return report
