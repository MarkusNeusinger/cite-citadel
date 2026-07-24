"""A self-contained, offline, zero-dependency local viewer for the OKF wiki.

``build_html`` serializes the wiki — the pages, the cross-link graph, the tags, AND the cited
raw sources (only the CITED EXCERPTS of each, not the whole file) — into ONE standalone HTML
document with the bundle embedded inline as JSON and a small hand-rolled markdown renderer + graph
in inlined vanilla JS. The link graph is stored ONCE, as each page's ``outbound``/``inbound`` lists;
the flat ``{source, target}`` edge array the graph code consumes is rebuilt from ``outbound`` in the
browser at boot (``BUNDLE.edges``), not shipped, so the same graph is not serialized three times.
It opens from ``file://`` with **no web server and no network**: nothing is
fetched from a CDN, so the wiki data never leaves the machine. No third-party code is vendored.

Sources are first-class: every ``[..](../../raw/x.md)`` citation and ``## Sources`` footnote is a
clickable link that opens the cited raw file — rendered, in the same reader — and a hover preview
peeks at it. Only the passages the wiki actually cites (plus a few lines of context) are embedded,
keyed by locator across every citing page — a ``lines A-B`` range, a ``§ Heading`` section, or a
head excerpt for an unlocated citation — merged into segments, with a "⋯ lines X–Y not embedded"
gap indicator and an "open the original file" affordance for the rest. A short file (or one whose
excerpts already cover most of it) still embeds whole. A "Sources" axis in the sidebar and an
optional source layer in the graph make provenance browsable.

Provenance is also legible at a glance: each page carries counts (``cites`` / ``llm`` /
``contradictions``) that the viewer renders as sidebar badges, quick-filter chips ("Contradictions",
"LLM notes"), and a reader summary with jump-to affordances. The sidebar search is a real
**full-text** search over every page/source body (ranked, with match snippets), and opening a
result highlights and scrolls to the hit.

Built to be browsed like a real wiki (Obsidian-style): the reader is a centered column with a
comfortable/wide/full width toggle; the interactive graph legend hides or shows any category (each
page type and the source layer) with live counts; the map can be collapsed, dragged to any height,
or expanded to full height for close inspection, and hovering a node dims all but its neighbours;
tags collapse into a compact counted dropdown; a page shows both its inbound ("Referenced by:") and
outbound ("Links to:") links; the open page is highlighted in the sidebar; and there is a random-page
button, a collapsible sidebar (backslash-key shortcut) for a focus/reading mode, and an auto/light/dark theme
toggle. All of this is client-side state persisted in ``localStorage``; the embedded data is untouched.

The only LLM-free, read-only consumer of the wiki besides search/lint. Reuses
``store.load`` / ``store.inbound_map`` / ``store.tag_catalog`` / ``store.find_raw_references``
and the shared citation/link/fence grammar (:mod:`citadel.grammar`) so the graph, tags, and
provenance always match the rest of the system.

The document shell, stylesheet, and viewer script are REAL files shipped as package data next to
this module (``template.html`` / ``app.css`` / ``app.js``) and read at build time via
``importlib.resources`` — editable as HTML/CSS/JS, not as Python string literals.

Public surface: ``build_bundle`` (pure data, the test seam), ``build_html`` (the document),
``write_viewer`` (writes ``wiki/.citadel_viewer.html``), and ``view`` (CLI entry — write, open,
print the path; on WSL it opens via ``wslview``/``explorer.exe`` and always prints a
Windows-pasteable path, and everywhere it degrades gracefully when no browser is available).
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import webbrowser
from importlib import resources
from pathlib import Path

from .. import config, extract, grammar, pdftext, store, transcribe
from .. import manifest as manifest_mod


# Default output: dot-prefixed so store.load() skips it (like .citadel_ingested.json) and it is
# gitignored; it is a regenerable artifact, never a source of truth.
VIEWER_FILENAME = ".citadel_viewer.html"

# A single embedded source is capped so a pathologically large raw file (a big PDF/CSV dump or a
# repo digest) can't bloat the standalone document without bound. This is the FINAL guard on the
# total embedded text per source (the whole body when a source embeds whole, or the sum of its
# excerpt segments): past it, the text is truncated with a marker and the viewer flags it. Only
# cited passages are embedded now, so this rarely bites.
_SOURCE_MAX_CHARS = 200_000

# Excerpt selection knobs (see :func:`_source_excerpts`). A ``lines A-B`` locator embeds the range
# padded by _LINE_CONTEXT lines on each side; an unlocated citation embeds a head excerpt of the
# first _HEAD_EXCERPT_LINES lines; a ``§ Heading`` section is capped at _HEADING_SECTION_CAP lines;
# ranges whose gap is <= _MERGE_GAP lines merge; and a file of <= _WHOLE_FILE_MAX_LINES lines (or
# one whose excerpts already cover >= 2/3 of it) embeds whole so small notes are never fragmented.
_LINE_CONTEXT = 3
_HEAD_EXCERPT_LINES = 30
_HEADING_SECTION_CAP = 80
_MERGE_GAP = 2
_WHOLE_FILE_MAX_LINES = 120

# First markdown ATX heading in a raw source — used as its human title when present.
_HEADING_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _page_stats(body: str) -> tuple[int, int, int]:
    """``(raw_citations, llm_facts, contradictions)`` for one page body — the counts the viewer
    shows as per-page sidebar badges and filters by. Counts only *prose* (the shared
    ``grammar.prose_lines`` view): it skips fenced code blocks and the trailing ``## Sources``
    section, so a marker or ``[!CONTRADICTION]`` written as a literal example — e.g. on a page
    documenting the citation format — is not miscounted, and a ``[^sN]`` mentioned inside another
    footnote's definition note is not mistaken for an inline use. An *inline* marker is one the
    guarded ``grammar.USED_MARKER_RE`` matches (a use, not a stray definition)."""
    cites = llm = contradictions = 0
    for line in grammar.prose_lines(body, skip_sources=True):
        if line.lstrip().startswith("#"):  # headings carry no citation markers to count
            continue
        for match in grammar.USED_MARKER_RE.finditer(line):
            if grammar.is_llm_marker(match.group(1)):
                llm += 1
            else:
                cites += 1
        if grammar.CONTRADICTION_LINE_RE.match(line):
            contradictions += 1
    return cites, llm, contradictions


def build_bundle(pages=None) -> dict:
    """Build the JSON-serializable bundle from the loaded wiki (pure data; no HTML, no I/O
    beyond ``store.load()`` and reading the cited raw sources). Deterministic — no timestamps —
    so a generated document round-trips back to this dict in tests."""
    if pages is None:
        pages = store.load()
    paths = {p.rel_path for p in pages}
    inbound = store.inbound_map(pages)

    pages_json: list[dict] = []
    types: dict[str, list[str]] = {}
    for page in pages:
        outbound = sorted(
            {resolved for _raw, resolved in grammar.resolved_md_links(page.rel_path, page.body) if resolved in paths}
        )
        types.setdefault(page.type or "Untyped", []).append(page.rel_path)
        cites, llm, contradictions = _page_stats(page.body)
        pages_json.append(
            {
                "rel_path": page.rel_path,
                "type": page.type or "Untyped",
                "title": page.title,
                "description": page.description,
                "tags": list(page.tags),
                "body": page.body,
                "outbound": outbound,
                "inbound": inbound.get(page.rel_path, []),
                # Per-page provenance counts for the sidebar badges + contradiction/LLM filters.
                "cites": cites,
                "llm": llm,
                "contradictions": contradictions,
            }
        )

    tags = {tag: [p.rel_path for p in tagged] for tag, tagged in store.tag_catalog(pages).items()}
    return {
        "wiki_name": config.WIKI_DIR.name,
        "pages": pages_json,
        "tags": tags,
        "types": {k: sorted(v) for k, v in types.items()},
        "sources": _build_sources(pages),
    }


# --------------------------------------------------------------------------------------
# Sources: discover every cited raw file, embed its content, and key it by the identity the
# in-browser link resolver produces so an inline citation can open it without any I/O.
# --------------------------------------------------------------------------------------


def _viewer_resolve(from_rel: str, target: str) -> str:
    """Python port of the viewer's in-browser ``resolveLink``: resolve a citation ``target`` written
    in page ``from_rel`` to a wiki-root-relative posix id, CLAMPING any ``..`` that would climb above
    the wiki root (a no-op pop on an empty stack, exactly like ``Array.pop`` in JS). This is the
    single identity under which an embedded source is keyed AND under which the browser looks it up,
    so a citation resolves to its source no matter how the wiki and raw trees are laid out (in-repo,
    a nested ``sub/wiki``, or a mounted network drive)."""
    target = target.split("#", 1)[0]
    base = from_rel.rsplit("/", 1)[0] if "/" in from_rel else ""
    parts = base.split("/") if base else []
    for seg in target.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def _source_view_id(abs_path: str | os.PathLike) -> str:
    """The identity the BROWSER link resolver yields for a source, so an inline ``../../raw/x.md``
    citation maps to it: the source's posix path relative to ``WIKI_DIR``'s parent (the repo root,
    or the shared root on a mounted drive). For an in-repo source this is just ``raw/x.md`` — which
    is exactly what the JS ``resolveLink`` returns for a citation that climbs out of ``wiki/``."""
    parent = config.WIKI_DIR.parent
    try:
        return os.path.relpath(str(abs_path), str(parent)).replace(os.sep, "/")
    except ValueError:  # different drive — no relative path exists
        return os.path.basename(str(abs_path))


def _collect_sources(pages) -> dict[str, str]:
    """Map each cited raw/docs source's VIEWER IDENTITY -> its source key, by scanning citation
    links (so a source is clickable even if it isn't in the manifest). What counts as a citation is
    the shared, config-aware :func:`grammar.is_source_citation` (a link into ``RAW_DIR``/``DOCS_DIR``).
    The identity is computed with :func:`_viewer_resolve` — the exact port of the browser's link
    resolver — so the source is keyed under the same id the inline citation looks it up by, in any
    layout. Fence-aware via ``grammar.prose_lines``, so a citation written as a literal inside a
    ``` code fence is not counted. First writer wins per identity, for determinism."""
    found: dict[str, str] = {}
    for page in pages:
        for line in grammar.prose_lines(page.body):
            for match in grammar.ANY_LINK_RE.finditer(line):
                path, _suffix = grammar.split_link_target(match.group(1))
                if not grammar.is_source_citation(page.rel_path, path):
                    continue
                link_abs = grammar.link_abs(page.rel_path, path)
                view_id = _viewer_resolve(page.rel_path, path)
                found.setdefault(view_id, config.rel_or_abs_posix(Path(link_abs)))
    return found


def _source_title(body: str, view_id: str) -> str:
    """A source's display title: its first markdown heading, else its file name."""
    match = _HEADING_RE.search(body)
    if match:
        return match.group(1).strip()
    return view_id.rsplit("/", 1)[-1]


def _source_snippet(body: str, limit: int = 240) -> str:
    """A short, whitespace-collapsed preview of a source's prose (headings dropped) for the hover
    popover. Only a bounded head of the body is scanned — the snippet needs ``limit`` chars, so
    collapsing a multi-hundred-KB source whole would be pure waste."""
    head = body[: limit * 40]
    prose = " ".join(line for line in head.splitlines() if not line.lstrip().startswith("#"))
    return " ".join(prose.split())[:limit]


def _source_href(abs_path: str | os.PathLike) -> str | None:
    """A relative link from the DEFAULT viewer location (``WIKI_DIR``) to the raw source on disk, so
    the reader can offer an "open the original file" affordance — the browser opens a PDF or other
    binary natively. None when no relative path exists (a different drive). The link assumes the
    viewer was written to its default ``wiki/`` location; the embedded text always works regardless."""
    try:
        return os.path.relpath(str(abs_path), str(config.WIKI_DIR)).replace(os.sep, "/")
    except ValueError:  # different drive — no relative path exists
        return None


def _read_source(path: Path) -> tuple[str, str]:
    """Read a raw source for embedding, returning ``(text, kind)``:

    - ``("...", "text")``  — a UTF-8 text file (markdown/code/notes), embedded verbatim;
    - ``("...", "office")`` — a ``.pptx``/``.docx`` whose text we extract with the stdlib (reusing
      the ingest extractor), so Office sources are readable inline too;
    - ``("...", "audio")`` — an audio/video recording whose cached whisper transcript exists
      (:func:`transcribe.cached_transcript` — the text the ingest agent actually read);
    - ``("...", "pdf")``   — a PDF whose cached pypdf text-layer extraction exists
      (:func:`pdftext.cached_text` — likewise the text the ingest agent actually read);
    - ``("", "binary")``   — anything we can't turn into text without a heavyweight dependency,
      e.g. a cache-less PDF. The viewer then offers an "open the original file" link instead of
      inline text.
    """
    if transcribe.is_audio_ext(path):
        # BEFORE the text attempt: an audio file must serve its transcript, never a lucky
        # UTF-8 decode of its container bytes. No cache -> fall through (a renamed text file
        # still renders as text; a real recording lands on "binary").
        cached = transcribe.cached_transcript(path)  # None when never transcribed here
        if cached:
            return cached, "audio"
    if pdftext.is_pdf_file(path):
        # Same for a genuine PDF: serve the cached extraction its `lines A-B` locators point
        # into. No cache -> "binary" (the open-the-original affordance) DIRECTLY: an ASCII-only
        # PDF would survive the UTF-8 read below and embed its raw object soup as "text".
        cached = pdftext.cached_text(path)
        return (cached, "pdf") if cached else ("", "binary")
    try:
        return path.read_text(encoding="utf-8"), "text"
    except (OSError, ValueError, UnicodeError):
        pass
    if extract.is_office_source(path):
        extracted = extract.extract_text(path)  # "" on a malformed/odd document
        if extracted:
            return extracted, "office"
    return "", "binary"


def _collect_source_locators(pages) -> dict[str, list[grammar.Locator | None]]:
    """Map each cited source's VIEWER IDENTITY -> the list of its citation locators across the whole
    wiki (``None`` for a citation with no locator). Walks every page's ``## Sources`` footnote
    definitions through :func:`grammar.source_definitions` (the one locator-bearing citation walk,
    shared with ``lint.check_locators``), keyed under the same :func:`_viewer_resolve` identity the
    embedded source records use — so :func:`_source_excerpts` can select exactly the cited passages.
    Model-supplied ``[^llm]`` definitions are skipped by ``source_definitions``."""
    locs: dict[str, list[grammar.Locator | None]] = {}
    for page in pages:
        for _marker_id, rest in grammar.source_definitions(page.body):
            target = grammar.def_link_target(rest)
            if target is None or grammar.is_external(target):
                continue
            view_id = _viewer_resolve(page.rel_path, target)
            tail = grammar.locator_tail(rest)
            locs.setdefault(view_id, []).append(grammar.parse_locator(tail) if tail else None)
    return locs


def _heading_lines(text: str) -> list[tuple[int, int, str]]:
    """Every section heading in ``text`` as ``(0-based line index, level, heading text)``, in
    document order — fence-aware via :func:`grammar.iter_lines`, using the shared
    :func:`grammar.parse_heading_line` (ATX ``#`` heading or whole-line ``**bold**``), so a
    ``§ Heading`` locator resolves against the same headings lint verifies against."""
    heads: list[tuple[int, int, str]] = []
    for idx, (line, in_code) in enumerate(grammar.iter_lines(text)):
        if in_code:
            continue
        parsed = grammar.parse_heading_line(line)
        if parsed is not None:
            heads.append((idx, parsed[0], parsed[1]))
    return heads


def _heading_range(heads: list[tuple[int, int, str]], heading: str, n: int) -> tuple[int, int] | None:
    """The 1-based inclusive line range of the section a ``§ Heading`` locator names, or None when
    no such heading exists. The section runs from the heading line to the line before the next
    heading of the SAME OR HIGHER level (else end of file), capped at :data:`_HEADING_SECTION_CAP`
    lines. Heading matching reuses :func:`grammar.heading_candidates` (case-folded), exactly as
    ``lint._locator_problem`` does, so a heading carrying a spaced-dash still matches."""
    cands = {c.lower() for c in grammar.heading_candidates(heading)}
    for pos, (idx, level, htext) in enumerate(heads):
        if htext.lower() not in cands:
            continue
        start = idx + 1  # 1-based heading line
        end = n
        for nidx, nlevel, _ in heads[pos + 1 :]:
            if nlevel <= level:
                end = nidx  # 0-based next-heading index == 1-based line before it
                break
        return start, min(end, start + _HEADING_SECTION_CAP - 1)
    return None


def _clamp_range(lo: int, hi: int, n: int) -> tuple[int, int]:
    """Clamp a 1-based inclusive line range to ``[1, n]``."""
    return max(1, min(lo, n)), max(1, min(hi, n))


def _line_range(start: int, end: int, n: int) -> tuple[int, int]:
    """The embed range for a ``lines A-B`` locator: the locator lines first normalized (an inverted
    ``lines 10-5`` — lint flags it, but the viewer must still build sanely — reads as ``5-10``) and
    clamped to EOF (a range past the file's end anchors at EOF, not off it), THEN padded by
    :data:`_LINE_CONTEXT` lines each side and clamped to ``[1, n]`` — so a past-EOF locator still
    shows a few lines of trailing context."""
    start, end = sorted((start, end))
    start, end = min(start, n), min(end, n)
    return _clamp_range(start - _LINE_CONTEXT, end + _LINE_CONTEXT, n)


def _source_excerpts(text: str, locators: list[grammar.Locator | None]) -> list[tuple[int, int]] | None:
    """Decide what to embed for one text source given all its citation ``locators``.

    Returns None to signal "embed the whole body" (a short file of <= :data:`_WHOLE_FILE_MAX_LINES`
    lines, or one whose merged excerpts already cover >= 2/3 of it — small notes must not be
    fragmented), or a list of merged 1-based inclusive ``(start, end)`` line ranges to embed as
    segments. Each locator contributes a range: a ``lines A-B`` range padded by :data:`_LINE_CONTEXT`
    lines each side; a ``§ Heading`` section (falling back to its combined ``, line N`` range, then to
    a head excerpt); and an unlocated / page-locator (``other``) citation a head excerpt of the first
    :data:`_HEAD_EXCERPT_LINES` lines. Overlapping AND near-adjacent ranges (gap <= :data:`_MERGE_GAP`)
    merge.

    The whole-body fallbacks fire ONLY when the whole body actually fits under
    :data:`_SOURCE_MAX_CHARS`. A file too big to embed whole (e.g. a whole book cited chapter by
    chapter) would otherwise fall through the coverage rule to a blindly truncated 200k prefix that
    drops its entire middle and end; emitting segments instead keeps the cited passages from
    throughout, with gap markers, so a large mostly-cited source is never silently front-truncated."""
    n = len(text.splitlines())
    whole_fits = len(text) <= _SOURCE_MAX_CHARS
    if n <= _WHOLE_FILE_MAX_LINES and whole_fits:
        return None
    head = _clamp_range(1, _HEAD_EXCERPT_LINES, n)
    ranges: list[tuple[int, int]] = []
    heads: list[tuple[int, int, str]] | None = None
    for loc in locators:
        if loc is None or loc.kind == "other":
            ranges.append(head)
        elif loc.kind == "lines":
            ranges.append(_line_range(loc.start, loc.end, n))
        elif loc.kind == "heading":
            if loc.start is not None:
                # Combined `§ Heading, lines A-B`: the ABSOLUTE line range is the precise anchor —
                # the same slice `citadel raw`/`wiki_raw` renders and lint verifies — with the
                # heading as context; embedding the whole section here instead showed a reader
                # different text than the CLI/MCP readers for the same citation.
                ranges.append(_line_range(loc.start, loc.end, n))
                continue
            if heads is None:
                heads = _heading_lines(text)
            hr = _heading_range(heads, loc.heading or "", n) if loc.heading else None
            ranges.append(hr if hr is not None else head)
    if not ranges:  # cited only via forms that yielded nothing — show a head excerpt
        ranges.append(head)
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for lo, hi in ranges:
        if merged and lo <= merged[-1][1] + _MERGE_GAP + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    covered = sum(hi - lo + 1 for lo, hi in merged)
    if covered * 3 >= n * 2 and whole_fits:
        return None
    return merged


def _embed_source(text: str, locators: list[grammar.Locator | None]) -> dict:
    """Build the per-source embed payload from its full ``text`` and citation ``locators``: either a
    whole-body record (``{"body": ..., "truncated": ...}``) or a segmented one (``{"segments": [...],
    "total_lines": n, "truncated": ...}``). :data:`_SOURCE_MAX_CHARS` is the final guard on the total
    embedded text (whole body, or the sum of segment texts).

    Segments are filled at SEGMENT granularity: whole segments are embedded greedily until the next
    one would exceed the budget, then the rest are dropped (``truncated`` set, the un-embedded tail
    shown as a gap with an "open the original" affordance) rather than slicing a passage off
    mid-line — so a hugely-cited source embeds only the segments that fit, not a 200k front-slice. If
    even the FIRST segment overflows an (unusually small) budget, a truncated head of just that
    segment is embedded so the record is never empty."""
    ranges = _source_excerpts(text, locators)
    if ranges is None:  # embed whole
        truncated = len(text) > _SOURCE_MAX_CHARS
        return {"body": text[:_SOURCE_MAX_CHARS] if truncated else text, "truncated": truncated}
    lines = text.splitlines()
    segments: list[dict] = []
    used = 0
    truncated = False
    for lo, hi in ranges:
        seg_text = "\n".join(lines[lo - 1 : hi])
        if used + len(seg_text) > _SOURCE_MAX_CHARS:
            truncated = True
            if not segments:  # never emit an empty record: keep a truncated head of the first
                seg_text = seg_text[: max(0, _SOURCE_MAX_CHARS - used)]
                segments.append({"start": lo, "end": hi, "text": seg_text})
            break
        used += len(seg_text)
        segments.append({"start": lo, "end": hi, "text": seg_text})
    return {"segments": segments, "total_lines": len(lines), "truncated": truncated}


def _build_sources(pages) -> dict:
    """Map each cited raw/docs source -> its embedded record. Cited sources are keyed by the exact
    browser identity (:func:`_collect_sources` via :func:`_viewer_resolve`) so an inline citation
    resolves straight to its record; tracked-but-uncited files fall back to :func:`_source_view_id`.
    Each record carries the CITED EXCERPTS of the file (via :func:`_embed_source` — a whole ``body``
    for a short/mostly-cited file, else ``segments`` + ``total_lines``), a title/snippet computed
    from the full text, the model that imported it (from the manifest), the wiki pages that cite it
    (the live link graph), a kind (text/office/audio/binary), an "open the original" href, and a missing
    flag when the file isn't on disk. Includes file
    sources tracked in the manifest even if currently uncited, so the Sources axis is complete;
    skips git-repository manifest entries (a folder, not a readable file). The manifest is read
    through ``manifest.load()`` — the one reader that understands both the stamped format-2 file
    and a legacy flat mapping — and provenance stays optional decoration: a missing/corrupt
    manifest simply reads as {}."""
    manifest = manifest_mod.load()
    manifest_files = {key for key, entry in manifest.items() if not manifest_mod.is_repo_entry(entry)}
    # Cited sources keyed by the browser identity, then tracked-but-uncited files under a fallback
    # id so the Sources axis is complete (a git-repository entry is a folder, not a file — skipped).
    id_to_key = _collect_sources(pages)
    seen_keys = set(id_to_key.values())
    for key in sorted(manifest_files):
        if key in seen_keys:
            continue
        id_to_key.setdefault(_source_view_id(config.source_path_for_key(key)), key)
        seen_keys.add(key)
    locators_by_id = _collect_source_locators(pages)
    sources: dict[str, dict] = {}
    for view_id, key in sorted(id_to_key.items()):
        abs_path = str(config.source_path_for_key(key))
        path = Path(abs_path)
        present = path.is_file()
        if present:
            text, kind = _read_source(path)
        else:
            text, kind = "", "binary"  # not on disk: render an "unavailable" notice, no body
        record = {
            "id": view_id,
            "key": key,
            # Title and snippet are computed from the FULL text (it is read anyway).
            "title": _source_title(text, view_id),
            "model": manifest_mod.entry_model(manifest[key]) if key in manifest else None,
            "cited_by": store.find_raw_references(key, pages),
            "missing": not present,
            "kind": kind,  # "text" | "office" | "audio" | "binary"
            "href": _source_href(abs_path) if present else None,
            "snippet": _source_snippet(text),
        }
        if kind == "binary" or not text:
            # Missing / binary / empty: no inline text, mirror the pre-excerpt whole-body shape.
            record.update(body="", truncated=False)
        else:
            # Embed only the cited passages (or the whole file when it is short / mostly cited).
            record.update(_embed_source(text, locators_by_id.get(view_id, [])))
        sources[view_id] = record
    return sources


def build_html(pages=None) -> str:
    """Return the complete self-contained HTML document as one string: shell + inlined CSS +
    inlined viewer JS + the bundle embedded as an inert ``application/json`` script."""
    bundle = build_bundle(pages)
    # Compact JSON; then escape '</' -> '<\/' so a literal '</script>' inside any page body
    # OR embedded source cannot close the data <script> early. (json.dumps does NOT do this.)
    blob = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    # Order matters: fill CSS and JS sentinels first, the data blob last, so a sentinel-like
    # substring inside page data is never re-interpreted.
    html = _asset("template.html").replace("/*__CSS__*/", _asset("app.css"))
    html = html.replace("/*__VIEWER_JS__*/", _asset("app.js"))
    html = html.replace("/*__BUNDLE__*/", blob)
    return html


def write_viewer(out_path=None, pages=None) -> Path:
    """Write the viewer document; default ``config.WIKI_DIR/.citadel_viewer.html``. Returns the
    absolute path written."""
    if out_path is None:
        out_path = config.WIKI_DIR / VIEWER_FILENAME
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(pages), encoding="utf-8")
    return out_path.resolve()


# Auto-open must never hang the command on a wedged opener — a few seconds is plenty for a
# fire-and-forget launcher to hand off.
_OPEN_TIMEOUT = 5


def _is_wsl() -> bool:
    """True when running under Windows Subsystem for Linux, where Python's ``webbrowser`` finds no
    Linux browser to launch and a ``file://`` Linux path is useless to paste into a Windows
    browser — so ``view`` reaches to the Windows side instead."""
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        return "microsoft" in platform.release().lower()
    except Exception:  # noqa: BLE001 - detection must never crash the command
        return False


def _wsl_windows_path(path: Path) -> str | None:
    """Best-effort ``wslpath -w`` — the Windows form (e.g.
    ``\\\\wsl.localhost\\Ubuntu\\home\\me\\wiki\\.citadel_viewer.html``) of a WSL Linux path, so a
    printed link is pasteable straight into a Windows browser. None on any failure."""
    wslpath = shutil.which("wslpath")
    if not wslpath:
        return None
    try:
        proc = subprocess.run(
            [wslpath, "-w", str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_OPEN_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _run_opener(cmd: list[str], *, require_zero: bool = True) -> bool:
    """Best-effort external opener. Returns True if it launched: with ``require_zero`` it demands a
    zero exit (``wslview`` reports real codes); without it a clean start counts (``explorer.exe``
    exits non-zero even on success). Never raises."""
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=_OPEN_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0 if require_zero else True


def open_in_browser(path: Path, win_path: str | None = None) -> bool:
    """Open ``path`` in the default browser; return True if a browser was launched. Never
    raises (a headless box with no browser returns False instead of crashing). On WSL, Python's
    ``webbrowser`` finds no Linux browser, so try the Windows side first — ``wslview`` (from wslu,
    purpose-built) then ``explorer.exe`` on the ``wslpath -w`` Windows path (opens the default
    Windows browser via file association) — before falling back to ``webbrowser``."""
    if _is_wsl():
        if shutil.which("wslview") and _run_opener(["wslview", str(path)]):
            return True
        if win_path and _run_opener(["explorer.exe", win_path], require_zero=False):
            return True
    try:
        return bool(webbrowser.open(path.as_uri()))
    except Exception:  # noqa: BLE001 - a missing browser must not crash the command
        return False


def _open_obsidian() -> int:
    """Best-effort: deep-link the wiki folder into Obsidian and always print the path."""
    import urllib.parse

    folder = config.WIKI_DIR.resolve()
    deep = "obsidian://open?path=" + urllib.parse.quote(str(folder))
    print(f"Open this folder as an Obsidian vault: {folder}")
    print("  tip: open the repository root instead to resolve raw/ citation links.")
    print(f"  deep link: {deep}")
    try:
        webbrowser.open(deep)
    except Exception:  # noqa: BLE001
        pass
    return 0


def view(out=None, open_browser: bool = True, obsidian: bool = False) -> int:
    """Generate the viewer, optionally open it, and print its path. Returns a CLI exit code
    (always 0 on a successful write, even if no browser could be launched)."""
    if obsidian:
        return _open_obsidian()
    path = write_viewer(out)
    print(f"wrote {path}")
    print(f"  {path.as_uri()}")
    # On WSL the file:// Linux path is useless to paste into a Windows browser, so always also
    # print the Windows form — a failed auto-open still leaves a working, pasteable link.
    win_path = _wsl_windows_path(path) if _is_wsl() else None
    if win_path:
        print(f"  {win_path}")
    if open_browser and not open_in_browser(path, win_path):
        print("  (could not launch a browser — open the file above manually)")
    return 0


def _asset(name: str) -> str:
    """Read one of the viewer's package-data files (``template.html``/``app.css``/``app.js``).
    Each asset file ends with a newline and its sentinel is replaced verbatim."""
    return (resources.files(__package__) / name).read_text(encoding="utf-8")
