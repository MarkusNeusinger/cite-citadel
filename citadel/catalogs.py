"""The generated OKF navigation catalogs, rebuilt mechanically from the loaded pages (no LLM).

:func:`rebuild_indexes` regenerates the reserved nav files from frontmatter + the ingest manifest
+ the live link graph: the top-level ``wiki/index.md`` (by type, with backlinks, Tags, Sources,
Open Points, Abbreviations sections), each per-folder ``index.md``, the provenance catalog
``wiki/sources/index.md``, and the derived ``wiki/open-points/index.md`` timeline. All are
frontmatter-free files that load() skips and delete_page/write_page refuse. Deterministic ordering
keeps diffs small. Sources/open-points bodies are removed when there is nothing to show so a stale
catalog never lingers.
"""

from __future__ import annotations

import re

from . import config, grammar, okf
from . import failures as failures_mod
from . import manifest as manifest_mod
from .linkgraph import _source_key_to_page_link, citing_pages_map, inbound_map
from .okf import Page
from .open_points import OpenPoint, collect_open_points
from .store_core import load, tag_catalog


def _md_cell(text: str) -> str:
    """Escape a markdown-table cell: pipes would otherwise be read as column separators, and a
    newline (possible in a failure detail message) would break the row — collapse both."""
    return re.sub(r"\s+", " ", str(text).replace("|", "\\|")).strip()


SOURCES_INDEX_REL = "sources/index.md"


def _render_sources_catalog(
    manifest_dict: dict,
    pages: list[Page],
    failures_dict: dict | None = None,
    refs_by_key: dict[str, list[str]] | None = None,
) -> str | None:
    """Render the body of ``wiki/sources/index.md`` — the provenance catalog.

    One row per tracked raw source (from the ingest manifest), showing the MODEL that imported it
    and the wiki pages that cite it. ``refs_by_key`` is the source-key → citing-pages map
    (:func:`citing_pages_map`) that :func:`rebuild_indexes` builds ONCE per rebuild and shares with
    the index.md ``## Sources`` section; when omitted it is computed here (standalone use). The
    source path links to the raw file and each citing page links to its page, both relative to
    ``sources/index.md`` (so the links work from that file's location, in-repo or on a network
    drive). A trailing ``## Could not ingest`` section lists the sources that FAILED (from
    ``failures_dict``: unreadable binaries, agent errors/timeouts) with their reason, so the
    files that never made it into the wiki are visible here too — not just in the run's console.
    Like ``index.md``/``log.md`` this is a generated, frontmatter-free OKF nav file — load() skips it
    and delete_page refuses it.

    Returns the markdown body, or None when there is nothing to show (no tracked source AND no
    failure) — the caller then removes any stale catalog."""
    failures_dict = failures_dict or {}
    if not manifest_dict and not failures_dict:
        return None
    if refs_by_key is None:
        refs_by_key = citing_pages_map(manifest_dict, pages)
    title_by_path = {p.rel_path: p.title for p in pages}
    lines: list[str] = [
        "# Sources",
        "",
        "Provenance for every ingested raw source: the model that imported it and the wiki "
        "pages that cite it. Generated — do not edit.",
        "",
    ]
    if manifest_dict:
        lines += ["| Source | Model | Referenced by |", "| --- | --- | --- |"]
        for key in sorted(manifest_dict):
            model = manifest_mod.entry_model(manifest_dict[key]) or "—"
            source_cell = f"[{_md_cell(key)}]({_source_key_to_page_link(SOURCES_INDEX_REL, key)})"
            refs = refs_by_key.get(key, [])
            if refs:
                ref_cell = ", ".join(
                    f"[{_md_cell(title_by_path.get(r, r))}]({okf.rel_path_between(SOURCES_INDEX_REL, r)})" for r in refs
                )
            else:
                ref_cell = "—"
            lines.append(f"| {source_cell} | {_md_cell(model)} | {ref_cell} |")
    if failures_dict:
        lines += [
            "",
            f"## Could not ingest ({len(failures_dict)})",
            "",
            "Raw sources that were NOT folded into the wiki — a binary/unsupported file, a source "
            "whose agent session errored or timed out, or one skipped as a same-basename `duplicate` "
            "of another format that was ingested instead. Fix/convert the file (or remove the kept "
            "duplicate) and re-run `citadel ingest`; a source that later succeeds drops off this "
            "list. Generated — do not edit.",
            "",
            "| Source | Reason | Detail |",
            "| --- | --- | --- |",
        ]
        for key in sorted(failures_dict):
            entry = failures_dict[key] if isinstance(failures_dict[key], dict) else {}
            reason = str(entry.get("reason") or "—")
            detail = str(entry.get("detail") or "—")
            source_cell = f"[{_md_cell(key)}]({_source_key_to_page_link(SOURCES_INDEX_REL, key)})"
            lines.append(f"| {source_cell} | {_md_cell(reason)} | {_md_cell(detail)} |")
    return "\n".join(lines).rstrip("\n") + "\n"


OPEN_POINTS_INDEX_REL = "open-points/index.md"

# Flatten a bullet for the catalog: inline links -> their text, footnote markers dropped
# (the shared marker grammar, with any leading whitespace swallowed along with the marker).
_OP_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_OP_FOOTNOTE_RE = re.compile(r"\s*" + grammar.FOOTNOTE_RE.pattern)


def _op_plain(text: str) -> str:
    """Flatten a bullet for the catalog: inline links -> their text, footnote markers dropped (the
    linked host page carries the live citations), whitespace collapsed."""
    text = _OP_MD_LINK_RE.sub(r"\1", text)
    text = _OP_FOOTNOTE_RE.sub("", text)
    return " ".join(text.split())


def _render_open_points_catalog(points: list[OpenPoint], title_by_path: dict[str, str]) -> str | None:
    """Render the body of ``wiki/open-points/index.md`` — the derived "what's still open /
    timeline per point" view, built mechanically from every ``## Open Points`` section (like the
    sources catalog). Points are grouped Open-first then Done; each links back to its host page,
    the source of truth for citations. Returns None when no point is tracked (the caller then
    removes any stale catalog), like ``index.md``/``log.md`` a generated, frontmatter-free nav
    file that load() skips and delete_page refuses."""
    if not points:
        return None
    open_pts = [p for p in points if p.status != "done"]
    done_pts = [p for p in points if p.status == "done"]
    lines: list[str] = [
        "# Open Points",
        "",
        "Tracked open points and their timelines, generated from every `## Open Points` section in "
        "the wiki. Grouped open-first; each links to the host page, which carries the citations. "
        "Generated — do not edit.",
        "",
    ]

    def emit(group: list[OpenPoint], heading: str) -> None:
        lines.append(f"## {heading} ({len(group)})")
        lines.append("")
        for pt in group:
            host_link = okf.rel_path_between(OPEN_POINTS_INDEX_REL, pt.page_rel)
            host_title = title_by_path.get(pt.page_rel, pt.page_rel)
            meta = [f"host: [{_md_cell(host_title)}]({host_link})"]
            if pt.last_date:
                meta.append(f"updated {pt.last_date}")
            if pt.point_id:
                meta.append(f"id: {pt.point_id}")
            lines.append(f"### {pt.title}")
            lines.append(" · ".join(meta))
            for date, text in pt.bullets:
                lines.append(f"- {date}: {_op_plain(text)}")
            lines.append("")

    if open_pts:
        emit(open_pts, "Open")
    if done_pts:
        emit(done_pts, "Done")
    return "\n".join(lines).rstrip("\n") + "\n"


def rebuild_indexes(pages: list[Page] | None = None) -> None:
    """Regenerate the OKF navigation files from the loaded pages (no LLM).

    Per OKF v0.1, ``index.md`` is the reserved progressive-disclosure file and **carries
    NO frontmatter** — so these are written as plain markdown. The top-level
    ``WIKI_DIR/index.md`` groups pages by type, adds a backlink ('↳ referenced by') line
    per page from the real link graph, and ends with a ``## Tags`` section that lists each
    OKF ``tags`` value and its pages (tags become a browse-by-topic navigation axis without
    inventing a non-reserved file). Each folder also gets a frontmatter-free ``index.md``.
    Deterministic ordering by rel_path keeps diffs small; index.md files are skipped by
    load()."""
    if pages is None:
        pages = load()
    pages = sorted(pages, key=lambda p: p.rel_path)
    title_by_path = {p.rel_path: p.title for p in pages}
    inbound = inbound_map(pages)

    # ----- sources/index.md: the provenance catalog (source -> model + citing pages) -----
    # Generated from the ingest manifest (the model lives there) + the live link graph, plus a
    # "Could not ingest" section from the failures record. Written before the top index so its
    # "See also" can link the catalog when it exists; removed when nothing is tracked or failed so a
    # stale catalog never lingers. The manifest is loaded once and reused below for the index.md
    # ## Sources section.
    manifest_dict = manifest_mod.load()
    failures_dict = failures_mod.load()
    # ONE wiki-body traversal builds the source-key → citing-pages map that BOTH provenance
    # consumers (the sources catalog and the index.md ## Sources section) read — replacing the two
    # separate O(sources × pages) scans the two consumers used to run independently (Z7).
    refs_by_key = citing_pages_map(manifest_dict, pages)
    sources_body = _render_sources_catalog(manifest_dict, pages, failures_dict, refs_by_key)
    sources_path = config.SOURCES_INDEX_PATH
    if sources_body is not None:
        config.robust_mkdir(sources_path.parent)
        sources_path.write_text(sources_body, encoding="utf-8")
    elif sources_path.exists():
        sources_path.unlink()

    # ----- open-points/index.md: the derived "what's still open / timeline per point" view -----
    # Built mechanically from every `## Open Points` section (no LLM, no second store) — like the
    # sources catalog it is written when there is at least one point and removed when there are none.
    open_points = collect_open_points(pages)
    open_points_body = _render_open_points_catalog(open_points, title_by_path)
    open_points_path = config.WIKI_DIR / OPEN_POINTS_INDEX_REL
    if open_points_body is not None:
        config.robust_mkdir(open_points_path.parent)
        open_points_path.write_text(open_points_body, encoding="utf-8")
    elif open_points_path.exists():
        open_points_path.unlink()

    # ----- top-level wiki/index.md (NO frontmatter — OKF reserved nav file) -----
    by_type: dict[str, list[Page]] = {}
    for page in pages:
        by_type.setdefault(page.type or "Untyped", []).append(page)

    folders: dict[str, list[Page]] = {}
    for page in pages:
        if "/" in page.rel_path:
            folders.setdefault(page.rel_path.split("/", 1)[0], []).append(page)

    lines: list[str] = [
        "# Wiki Index",
        "",
        "The wiki's home index: every page grouped by type (with backlinks), plus tags and the "
        "source/open-point catalogs. Generated — do not edit.",
        "",
    ]
    seealso_parts = [f"[{folder}]({folder}/index.md)" for folder in sorted(folders)]
    if sources_body is not None:
        seealso_parts.append(f"[sources]({SOURCES_INDEX_REL})")
    if open_points_body is not None:
        seealso_parts.append(f"[open points]({OPEN_POINTS_INDEX_REL})")
    if seealso_parts:
        lines.append(f"See also: {' · '.join(seealso_parts)}")
        lines.append("")
    for type_ in sorted(by_type):
        lines.append(f"## {type_}")
        for page in by_type[type_]:
            lines.append(f"- [{page.title}]({page.rel_path}) — {page.description}")
            refs = inbound.get(page.rel_path, [])
            if refs:
                reflinks = ", ".join(f"[{title_by_path.get(r, r)}]({r})" for r in refs)
                lines.append(f"  - ↳ referenced by: {reflinks}")
        lines.append("")

    by_tag = tag_catalog(pages)
    if by_tag:
        lines.append("## Tags")
        lines.append("")
        for tag in sorted(by_tag):
            tagged = by_tag[tag]
            lines.append(f"### {tag} ({len(tagged)})")
            for page in tagged:
                lines.append(f"- [{page.title}]({page.rel_path})")
            lines.append("")

    # ----- ## Sources: the by-source provenance axis, surfaced IN index.md (not just a See-also
    # link). An agent reading index.md (e.g. via the wiki_index MCP tool, which never reached the
    # skipped sources/index.md) can now discover what was ingested and from where. -----
    if manifest_dict:
        lines.append("## Sources")
        lines.append("")
        lines.append(
            f"{len(manifest_dict)} ingested raw source(s) — full catalog with the importing "
            f"model in [sources/index.md]({SOURCES_INDEX_REL})."
        )
        lines.append("")
        for key in sorted(manifest_dict):
            refs = refs_by_key.get(key, [])
            n = len(refs)
            cited = f"cited by {n} page{'s' if n != 1 else ''}" if n else "uncited"
            src_link = _source_key_to_page_link("index.md", key)
            lines.append(f"- [{_md_cell(key)}]({src_link}) — {cited}")
        lines.append("")

    # ----- ## Open Points: the by-point timeline axis, surfaced IN index.md so an agent reading
    # it (e.g. via the wiki_index MCP tool) can discover what is still open without reaching the
    # skipped open-points/index.md. -----
    if open_points:
        n_open = sum(1 for p in open_points if p.status != "done")
        lines.append("## Open Points")
        lines.append("")
        lines.append(
            f"{len(open_points)} tracked open point(s), {n_open} still open — full timeline in "
            f"[open-points/index.md]({OPEN_POINTS_INDEX_REL})."
        )
        lines.append("")

    # ----- ## Abbreviations: the glossary, generated from every type: Abbreviation page -----
    abbrev_pages = [p for p in pages if (p.type or "").strip().lower() == "abbreviation"]
    if abbrev_pages:

        def _cell(text: str) -> str:
            return text.replace("|", "\\|").strip()

        rows = [(okf.abbrev_short_long(p), p) for p in abbrev_pages]
        rows.sort(key=lambda r: (r[0][0].lower(), r[0][1].lower(), r[1].rel_path))
        lines.append("## Abbreviations")
        lines.append("")
        lines.append("| Abbreviation | Expansion | Page |")
        lines.append("| --- | --- | --- |")
        for (short, expansion), page in rows:
            lines.append(f"| {_cell(short)} | {_cell(expansion)} | [{_cell(page.title)}]({page.rel_path}) |")
        lines.append("")

    body = "\n".join(lines).rstrip("\n") + "\n"
    config.robust_mkdir(config.WIKI_DIR)
    (config.WIKI_DIR / "index.md").write_text(body, encoding="utf-8")

    # ----- per-directory index.md (also frontmatter-free) -----
    for folder in sorted(folders):
        folder_pages = sorted(folders[folder], key=lambda p: p.rel_path)
        flines: list[str] = [f"# {folder}", "", "The pages in this folder. Generated — do not edit.", ""]
        for page in folder_pages:
            rel_in_folder = page.rel_path[len(folder) + 1 :]
            flines.append(f"- [{page.title}]({rel_in_folder}) — {page.description}")
        flines.append("")
        fbody = "\n".join(flines).rstrip("\n") + "\n"
        folder_dir = config.WIKI_DIR / folder
        config.robust_mkdir(folder_dir)
        (folder_dir / "index.md").write_text(fbody, encoding="utf-8")
