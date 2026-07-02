"""THE single source of the citation grammar (links, footnotes, fences, source citations).

Every regex and parsing rule for the wiki's markdown grammar lives HERE, exactly once:
the ``](x.md)`` / ``](anything)`` link spans, the ``[^sN]`` / ``[^llmN]`` footnote markers
and their ``[^id]: ...`` definition lines, the ``## Sources`` heading, the contradiction
callout, the fence-aware line iterator, and the "is this link a source citation?" predicates.
``store``, ``validate``, ``lint``, and the viewer all parse through this module, so the strict
gate (``citadel check``), the health check (``citadel lint``), the link rewriters, and the
viewer agree by construction on what a link, a citation, and code ARE.

Two decided grammar rules are canonical here:

  1. A citation link into a source tree (the sibling ``raw/`` or ``docs/`` roots) is a LEGAL
     source citation, never a broken wiki cross-link (``citadel check`` was authoritative).
  2. A link inside a ``` code fence is literal text: rewriters never touch it and detectors
     never count it (fences come from :func:`iter_lines`, the ONE fence implementation).

Fence semantics (shared by every consumer): a line whose stripped form starts with ``` toggles
code state, and the delimiter line itself counts as code. ``~~~`` fences and indented code
blocks are NOT recognized — the ingest rules only ever produce ``` fences.

Depends only on :mod:`citadel.okf` (link math) and :mod:`citadel.config` (source roots, read
at call time so tests can monkeypatch the layout). Knows nothing about pages, the store, or
the LLM.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator

from . import config, okf


# --- link spans ---------------------------------------------------------------------------

# A markdown link span whose target ends in '.md' — the wiki cross-link / citation shape.
MD_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")
# A markdown link span ``](target)`` for ANY target (not only '.md'): citation links into the
# raw/ source tree point at arbitrary file types (.py/.txt/.pdf/...), so source-link handling
# cannot assume the '.md' suffix that wiki cross-link handling relies on.
ANY_LINK_RE = re.compile(r"\]\(([^)]+)\)")
# First full markdown link on a footnote-definition line; tolerates a <url> form and stops the
# path at whitespace so a `(url "title")` link title is not swallowed into the path.
DEF_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?")
# A [[wiki-style]] link — NOT allowed (the wiki uses relative markdown links).
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# --- footnote markers / definitions --------------------------------------------------------

# A footnote marker, use OR definition: [^s1] / [^llm2] / [^note.a].
FOOTNOTE_RE = re.compile(r"\[\^[\w.-]+\]")
# A footnote marker USED on a fact (not a definition — i.e. not followed by ':'), id captured.
USED_MARKER_RE = re.compile(r"\[\^([\w.-]+)\](?!:)")
# A model-supplied ("source: LLM") footnote marker, e.g. [^llm1]. These facts are added from
# the model's own knowledge rather than a raw file, and are deliberately NOT required to cite
# a raw/ file. For a captured marker id, use :func:`is_llm_marker` instead.
LLM_MARKER_RE = re.compile(r"\[\^llm[\w.-]*\]", re.IGNORECASE)
# A footnote definition line: `[^id]: rest` (leading indentation tolerated). Only meaningful
# inside the ## Sources section and outside code fences — the caller enforces that context.
DEF_LINE_RE = re.compile(r"^\s*\[\^([\w.-]+)\]:\s*(.*)$")

# --- section / callout markers --------------------------------------------------------------

# The ## Sources heading (any level, case-insensitive) that opens the footnote-definition
# section; any other heading closes it. Match against the stripped line.
SOURCES_HEADING_RE = re.compile(r"#+\s*sources\b", re.IGNORECASE)
# The contradiction callout: the exact marker the ingest rules prescribe, plus a per-line
# regex tolerant of indentation and `>` spacing for detectors that scan prose lines.
CONTRADICTION_MARKER = "> [!CONTRADICTION]"
_DRIVE_RE = re.compile(r"^[A-Za-z]:")  # windows drive prefix in a posix-styled citation
CONTRADICTION_LINE_RE = re.compile(r"^\s*>\s*\[!CONTRADICTION\]", re.IGNORECASE)


def is_llm_marker(marker_id: str) -> bool:
    """True when a captured footnote marker id denotes a model-supplied fact (``llm`` prefix,
    case-insensitive) — cited as "LLM", exempt from the raw-file provenance requirements."""
    return marker_id.lower().startswith("llm")


def is_external(target: str) -> bool:
    """True for a link target that is an external URL or an in-page anchor — never a wiki
    cross-link and never a source citation."""
    return "://" in target or target.startswith("#")


def split_link_target(inner: str) -> tuple[str, str]:
    """Split a markdown link's parenthesized content into ``(path, suffix)``, where ``suffix`` is
    any trailing ``"title"`` (or empty for a ``<path>`` form) preserved verbatim on rewrite. e.g.
    ``'../../raw/x.md "note"'`` -> ``('../../raw/x.md', ' "note"')``; ``'<../../raw/x.md>'`` ->
    ``('../../raw/x.md', '')``."""
    inner = inner.strip()
    if inner.startswith("<"):
        end = inner.find(">")
        return (inner[1:end], "") if end != -1 else (inner, "")
    parts = inner.split(None, 1)
    return (parts[0], " " + parts[1]) if len(parts) == 2 else (inner, "")


# --- the ONE fence-aware line iterator -------------------------------------------------------


def iter_lines(body: str, *, keepends: bool = False) -> Iterator[tuple[str, bool]]:
    """Yield ``(line, in_code)`` for every line of ``body`` — THE single fence-state
    implementation. A line whose stripped form starts with ``` toggles the fence state and
    itself yields ``in_code=True``, so detectors skip it and rewriters emit it verbatim: the
    delimiter is code, matching both philosophies. ``keepends=True`` preserves line endings
    for the span-based rewriters, whose output must be byte-identical outside rewritten spans."""
    in_fence = False
    for line in body.splitlines(keepends=keepends):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            yield line, True
        else:
            yield line, in_fence


def prose_lines(body: str, *, skip_sources: bool = False) -> Iterator[str]:
    """The fence-aware prose-line view over :func:`iter_lines`: yield every line of ``body``
    outside ``` code fences. With ``skip_sources=True`` the ``## Sources`` heading and its
    section (up to the next heading of any level) are dropped too — its raw filenames, dates,
    and footnote links are not prose. Headings other than ``## Sources`` ARE prose
    (an abbreviation in a heading is a real use); consumers that handle headings themselves
    filter them at the call site."""
    in_sources = False
    for line, in_code in iter_lines(body):
        if in_code:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            if skip_sources:
                in_sources = bool(SOURCES_HEADING_RE.match(stripped))
                if in_sources:
                    continue
            yield line
            continue
        if in_sources:
            continue
        yield line


# --- source-citation predicates --------------------------------------------------------------


def link_abs(page_rel: str, target: str) -> str | None:
    """The absolute, lexically-normalized filesystem path a relative link ``target`` written in
    wiki page ``page_rel`` points at, or None for an external/anchor link. Lexical only
    (``normpath``, no symlink resolution) so it stays consistent with how source keys are formed
    and works on synthetic or not-yet-existing paths."""
    if is_external(target):
        return None
    page_dir = os.path.dirname(str(config.WIKI_DIR / page_rel))
    return os.path.normpath(os.path.join(page_dir, target))


def _is_within(path_abs: str | os.PathLike, base: str | os.PathLike) -> bool:
    """True if ``path_abs`` lies inside directory ``base`` (case-folded, purely LEXICAL — no
    symlink resolution, mirroring :func:`link_abs`; resolving only one side would diverge under
    a symlinked wiki/raw path)."""
    base_s = os.path.normcase(os.path.normpath(str(base)))
    p = os.path.normcase(os.path.normpath(str(path_abs)))
    return p == base_s or p.startswith(base_s + os.sep)


def is_source_citation(page_rel: str, target: str) -> bool:
    """True when the link ``target`` written in wiki page ``page_rel`` is a citation into a
    SOURCE tree — by default the configured ``config.RAW_DIR`` / ``config.DOCS_DIR`` roots,
    read at call time so tests (and out-of-workspace layouts) can repoint them. Such a link
    is legal provenance, never a wiki cross-link (decided rule 1 in the module docstring).
    Filesystem-space twin of :func:`resolves_to_source` (see there for why both exist).

    Containment is lexical and existence is NOT required: whether the cited file is really on
    disk is the strict gate's job (``validate.source_issues``), not the grammar's. Multi-root
    discovery (PR4) lands by extending the call-time default below, not the signature."""
    abs_path = link_abs(page_rel, target)
    if abs_path is None:
        return False
    return any(_is_within(abs_path, root) for root in (config.RAW_DIR, config.DOCS_DIR))


def resolves_to_source(resolved: str) -> bool:
    """Source-or-cross-link over a RESOLVED wiki link identity (``okf.resolve_link`` output) —
    the rewriters'/detectors' universe, deliberately distinct from :func:`is_source_citation`,
    which answers the same question in FILESYSTEM space against the configured roots. The two
    predicates stay separate because their domains differ: a citation into a since-removed
    root must remain a skipped source link here even though no configured root contains it.
    A resolved path is a source citation when it escapes the wiki root (``..``-escape), names
    a top-level ``raw``/``docs`` segment, or is ABSOLUTE (the multi-root citation form for
    non-sibling roots — see docs/refactor-plan.md Z3)."""
    if resolved.startswith(("/", "\\")) or os.path.isabs(resolved) or _DRIVE_RE.match(resolved):
        return True
    return resolved.startswith("..") or resolved.split("/", 1)[0] in ("raw", "docs")


def resolved_md_links(page_rel: str, body: str) -> list[tuple[str, str]]:
    """Every relative ``.md`` WIKI CROSS-LINK in ``body`` as ``(raw_target, resolved)``.

    ``raw_target`` is the link text as written (e.g. ``'./b.md'``); ``resolved`` is its
    wiki-root-relative identity via ``okf.resolve_link``. Skips external links, anchors, and
    source citations (:func:`resolves_to_source` — the ``## Sources`` footnotes). Fence-aware
    (decided rule 2): a literal ``](x.md)`` inside a ``` code fence is text, exactly as the
    rewriters treat it, so detectors (broken links, backlinks, graph edges) and rewriters agree.
    The shared upstream of ``store.find_broken_links`` / ``store._inbound_map`` /
    ``lint``'s link graph / the viewer's edges."""
    out: list[tuple[str, str]] = []
    for line in prose_lines(body):
        for match in MD_LINK_RE.finditer(line):
            raw_target = match.group(1).strip()
            if is_external(raw_target):
                continue
            resolved = okf.resolve_link(page_rel, raw_target)
            if resolves_to_source(resolved):
                continue
            out.append((raw_target, resolved))
    return out
