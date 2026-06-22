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

from dataclasses import dataclass, field
from pathlib import Path

from . import config, llm, manifest, okf, store
from .okf import Page


@dataclass
class IngestReport:
    processed: list[str]
    skipped: list[str]
    pages_written: list[str]
    errors: list[str]
    pages_deleted: list[str] = field(default_factory=list)
    # (source_rel_path, target) cross-links left dangling after this run — should be empty.
    broken_links: list[tuple[str, str]] = field(default_factory=list)

    def render(self) -> str:
        """Human-readable multi-line summary for CLI/MCP."""
        lines: list[str] = []
        lines.append(
            f"Ingest complete: {len(self.processed)} processed, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.pages_written)} pages written, "
            f"{len(self.pages_deleted)} pages deleted, "
            f"{len(self.errors)} errors."
        )
        if self.processed:
            lines.append("Processed:")
            lines.extend(f"  - {p}" for p in self.processed)
        if self.pages_written:
            lines.append("Pages written:")
            lines.extend(f"  - {p}" for p in self.pages_written)
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
            # The size hint lets the model judge when a page has grown "too big" and
            # should be split.
            lines.append(
                f"- {page.rel_path} (~{len(page.body)} chars) — "
                f"{page.title}: {page.description}"
            )
        lines.append("")
    return "\n".join(lines).rstrip()


def _build_digest(raw_text: str, pages: list[Page]) -> str:
    """Build the compare-against-existing context for the ingest prompt.

    A catalog of every current page (with a size hint so the model can spot pages that
    grew too big), then the FULL serialized body of as many keyword-matched pages as fit
    the ``config.MAX_DIGEST_CHARS`` budget (best matches first) — so the model can merge
    into, patch, split, or delete them and spot contradictions. A small wiki is shown in
    full; a large one fills the budget with the most relevant pages. Both views derive
    from the same in-memory ``pages``.
    """
    parts: list[str] = [
        "# CURRENT WIKI PAGES (you MAY rewrite, split, merge, or delete any of these)\n",
        _catalog(pages),
    ]

    hits = store.search(raw_text, pages, limit=config.DIGEST_CANDIDATE_N)
    if hits:
        parts.append(
            "\n\n# TOP MATCHING PAGES (merge into / patch / split / delete these; body "
            "shown WITHOUT its frontmatter — do not reproduce a `---` block in your body; "
            "you MAY rewrite, split, or delete any page shown here)\n"
        )
        running = len("\n".join(parts))
        for page, _score in hits:
            meta = (
                f"(type: {page.type} | title: {page.title} | "
                f"resource: {page.frontmatter.get('resource', '')} | "
                f"size: {len(page.body)} chars)"
            )
            block = f"\n## {page.rel_path}\n{meta}\n\n{page.body.rstrip()}\n"
            # Stop once the next full body would overflow the budget (but always include
            # at least the catalog + header that are already in `parts`).
            if running + len(block) > config.MAX_DIGEST_CHARS:
                break
            parts.append(block)
            running += len(block)

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

    # OLD rel_path -> surviving rel_path, accumulated across the run from delete ops that
    # carry a "redirect". Applied once at the end so every inbound cross-link to a
    # merged/renamed page is repointed at the survivor (links keep working).
    rename_map: dict[str, str] = {}

    for src in pending:
        rel_key = manifest.rel_key(src)
        try:
            raw_text = src.read_text(encoding="utf-8")
            digest = _build_digest(raw_text, pages)
            ops = llm.plan_pages(rel_key, raw_text, digest)

            # The set of pages that exist as we apply this source's ops, so a delete can
            # be validated and a redirect target confirmed.
            existing = {p.rel_path for p in pages}
            # Pages this source WRITES — a delete of one of these is a contradiction and
            # would destroy a page we just (re)created, so it is refused below.
            written_this_src: set[str] = set()

            # Pass 1: writes first. A split/merge writes the survivor(s) BEFORE any
            # delete runs, so a delete can never remove the only copy of a fact.
            for op in ops:
                if op.get("op") == "delete":
                    continue
                rp = _apply_op(op, rel_key)
                if rp:
                    report.pages_written.append(rp)
                    existing.add(rp)
                    written_this_src.add(rp)
                    # If a slug deleted-with-redirect earlier in the run is now rewritten
                    # with fresh content, it is no longer "renamed away" — drop the stale
                    # mapping so inbound links are not repointed off the live page.
                    rename_map.pop(rp, None)

            # Pass 2: deletes, collecting redirects for the end-of-run link rewrite.
            for op in ops:
                if op.get("op") != "delete":
                    continue
                rel = (op.get("rel_path") or "").strip()
                if rel in written_this_src:
                    report.errors.append(
                        f"{rel_key}: delete refused, {rel!r} was just written this run"
                    )
                    continue
                if not rel or rel not in existing:
                    report.errors.append(
                        f"{rel_key}: delete skipped, no such page: {rel!r}"
                    )
                    continue
                try:
                    store.delete_page(rel)
                except okf.OKFError as exc:
                    report.errors.append(f"{rel_key}: delete {rel}: {exc}")
                    continue
                report.pages_deleted.append(rel)
                existing.discard(rel)
                redirect = (op.get("redirect") or op.get("into") or "").strip()
                if redirect and redirect in existing:
                    rename_map[rel] = redirect

            manifest.mark_done(manifest_dict, src)
            report.processed.append(rel_key)
            # Refresh so the NEXT source's digest sees the just-written pages.
            pages = store.load()
        except Exception as exc:  # noqa: BLE001 - collect per-source, keep going
            report.errors.append(f"{rel_key}: {exc}")

    if report.processed:
        manifest.save(manifest_dict)
        # Repoint inbound cross-links to any merged/renamed pages BEFORE rebuilding the
        # indexes, so the regenerated catalog and the link graph agree.
        if rename_map:
            store.rewrite_links(rename_map)
        store.rebuild_indexes()
        # Surface any cross-link left dangling by a restructure so it is never silent.
        report.broken_links = store.find_broken_links()
        store.append_log(
            f"ingest {report.processed} -> {len(report.pages_written)} written, "
            f"{len(report.pages_deleted)} deleted"
        )

    return report
