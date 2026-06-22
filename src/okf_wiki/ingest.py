"""Orchestrate one ingest run with no cleverness.

For each pending source: build a compare-against-existing digest, call
``llm.plan_pages`` ONCE (which shells out to a coding-agent CLI), apply the
returned ops via ``store.write_page`` (defaulting ``rel_path`` via
``okf.default_rel_path``; non-Concept/Entity types route to ``misc/``), mark the
source done, then once per run rebuild all indexes and append a log line.

Idempotent: sources whose sha already matches the manifest are skipped. Exactly
one LLM call per source; no agent loop. The only outside call is
``llm.plan_pages`` (tests monkeypatch it).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import config, llm, manifest, okf, store
from .okf import Page


@dataclass
class IngestReport:
    processed: list[str]
    skipped: list[str]
    pages_written: list[str]
    errors: list[str]

    def render(self) -> str:
        """Human-readable multi-line summary for CLI/MCP."""
        lines: list[str] = []
        lines.append(
            f"Ingest complete: {len(self.processed)} processed, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.pages_written)} pages written, "
            f"{len(self.errors)} errors."
        )
        if self.processed:
            lines.append("Processed:")
            lines.extend(f"  - {p}" for p in self.processed)
        if self.pages_written:
            lines.append("Pages written:")
            lines.extend(f"  - {p}" for p in self.pages_written)
        if self.skipped:
            lines.append("Skipped (already ingested):")
            lines.extend(f"  - {p}" for p in self.skipped)
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


def _catalog(pages: list[Page]) -> str:
    """Render a cheap one-line-per-page catalog grouped by type (from the
    in-memory pages, so it stays consistent with the rest of the digest within a
    single run — never reads the on-disk index, which lags between sources)."""
    if not pages:
        return "(the wiki is currently empty)"
    by_type: dict[str, list[Page]] = {}
    for page in pages:
        by_type.setdefault(page.type or "Untyped", []).append(page)
    lines: list[str] = []
    for type_ in sorted(by_type):
        lines.append(f"## {type_}")
        for page in by_type[type_]:
            lines.append(f"- {page.rel_path} — {page.title}: {page.description}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _build_digest(raw_text: str, pages: list[Page]) -> str:
    """Build the compare-against-existing context for the ingest prompt.

    A catalog of every current page (so the model can see what already exists and
    avoid duplicating), then the FULL serialized body of the top keyword matches
    (so it can merge/patch them and spot contradictions). Both views derive from
    the same in-memory ``pages``. Truncated to ``config.MAX_DIGEST_CHARS``.
    """
    parts: list[str] = ["# CURRENT WIKI PAGES\n", _catalog(pages)]

    hits = store.search(raw_text, pages, limit=config.DIGEST_TOP_N)
    if hits:
        parts.append(
            "\n\n# TOP MATCHING PAGES (merge into / patch these; body shown WITHOUT "
            "its frontmatter — do not reproduce a `---` block in your body)\n"
        )
        for page, _score in hits:
            meta = (
                f"(type: {page.type} | title: {page.title} | "
                f"resource: {page.frontmatter.get('resource', '')})"
            )
            parts.append(f"\n## {page.rel_path}\n{meta}\n\n{page.body.rstrip()}\n")

    digest = "\n".join(parts)
    if len(digest) > config.MAX_DIGEST_CHARS:
        digest = digest[: config.MAX_DIGEST_CHARS]
    return digest


def _apply_op(op: dict, source_rel: str) -> str | None:
    """Apply one page op. ``op=="skip"`` -> None; else write the page and return rel_path.

    Frontmatter is ``{type, title, description, tags, resource}``. ``resource`` is the
    page-level pointer to the PRIMARY raw file this page was derived from: the model
    may override it via ``op['resource']``, otherwise it defaults to ``source_rel``
    (the raw file being ingested). ``rel_path`` defaults to
    ``okf.default_rel_path(op['type'], op['title'])`` when not given. ``store.write_page``
    enforces path-safety and stamps the timestamp.
    """
    if op.get("op") == "skip":
        return None

    type_ = op.get("type", "")
    title = op.get("title", "")

    frontmatter: dict = {
        "type": type_,
        "title": title,
        "description": op.get("description", ""),
        "tags": op.get("tags", []) or [],
        "resource": op.get("resource") or source_rel,
    }

    body = op.get("body", "")
    # Defensive: some models echo a YAML frontmatter block into the body (mimicking
    # the digest). Strip a leading "---...---" block so write_page's own frontmatter
    # is not duplicated.
    if body.lstrip().startswith("---"):
        body = okf.parse(body.lstrip("\n"))[1]

    rel_path = op.get("rel_path") or okf.default_rel_path(type_, title)
    store.write_page(rel_path, frontmatter, body)
    return rel_path


def ingest(paths: list[str] | None = None) -> IngestReport:
    """Run one ingest. Exactly one ``llm.plan_pages`` call per pending source.

    On a per-source exception (including a missing/unusable LLM CLI), the error is
    collected and the source is left un-recorded (so it is retried next run).
    Finalization (manifest.save + rebuild_indexes + append_log) happens once, only
    if any source was processed.
    """
    manifest_dict = manifest.load()
    pages = store.load()
    report = IngestReport([], [], [], [])

    pending, skipped = _partition_sources(paths)
    report.skipped = skipped

    for src in pending:
        rel_key = manifest.rel_key(src)
        try:
            raw_text = src.read_text(encoding="utf-8")
            digest = _build_digest(raw_text, pages)
            ops = llm.plan_pages(rel_key, raw_text, digest)
            for op in ops:
                rp = _apply_op(op, rel_key)
                if rp:
                    report.pages_written.append(rp)
            manifest.mark_done(manifest_dict, src)
            report.processed.append(rel_key)
            # Refresh so the NEXT source's digest sees the just-written pages.
            pages = store.load()
        except Exception as exc:  # noqa: BLE001 - collect per-source, keep going
            report.errors.append(f"{rel_key}: {exc}")

    if report.processed:
        manifest.save(manifest_dict)
        store.rebuild_indexes()
        store.append_log(
            f"ingest {report.processed} -> {len(report.pages_written)} pages written"
        )

    return report
