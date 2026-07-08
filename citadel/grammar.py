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
from dataclasses import dataclass

from . import config, okf


# --- link spans ---------------------------------------------------------------------------

# A markdown link span whose target ends in '.md' — the wiki cross-link / citation shape.
MD_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")
# A markdown link span ``](target)`` for ANY target (not only '.md'): citation links into the
# raw/ source tree point at arbitrary file types (.py/.txt/.pdf/...), so source-link handling
# cannot assume the '.md' suffix that wiki cross-link handling relies on.
ANY_LINK_RE = re.compile(r"\]\(([^)]+)\)")
# First full markdown link on a footnote-definition line. Two alternatives, mirroring
# split_link_target: the <angle> form captures everything up to the closing '>' (the ONE
# supported way to cite a source path containing spaces — see split_link_target), and the bare
# form stops the path at whitespace so a `(url "title")` link title is not swallowed into the
# path. Read the target through def_link_target(), which folds the two groups together.
DEF_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*(?:<([^>)]+)>|([^)\s>]+))")
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


def def_link_target(rest: str) -> str | None:
    """The target path of the first markdown link on a footnote-definition line's ``rest``, or
    None when there is no resolvable link. Folds :data:`DEF_LINK_RE`'s two alternatives (the
    ``<angle>`` form — which may contain spaces — and the whitespace-terminated bare form) into
    the one path string the strict gate resolves."""
    match = DEF_LINK_RE.search(rest)
    if not match:
        return None
    return match.group(1) if match.group(1) is not None else match.group(2)


def split_link_target(inner: str) -> tuple[str, str]:
    """Split a markdown link's parenthesized content into ``(path, suffix)``, where ``suffix`` is
    any trailing ``"title"`` (or empty for a ``<path>`` form) preserved verbatim on rewrite. e.g.
    ``'../../raw/x.md "note"'`` -> ``('../../raw/x.md', ' "note"')``; ``'<../../raw/x.md>'`` ->
    ``('../../raw/x.md', '')``.

    DECIDED (the standard-markdown rule this grammar supports): a target containing SPACES must
    be written in the angle form — ``[my report](<../../raw/my report.pdf>)`` — which this
    function reads whole; a bare spacey target lexically splits at the first whitespace (it is
    indistinguishable from a ``"title"`` boundary) and is NOT a supported citation. The
    emitters render through :func:`format_link_target` (the write-side twin), which angle-wraps
    whenever a target contains whitespace, so a rewrite round-trips."""
    inner = inner.strip()
    if inner.startswith("<"):
        end = inner.find(">")
        return (inner[1:end], "") if end != -1 else (inner, "")
    parts = inner.split(None, 1)
    return (parts[0], " " + parts[1]) if len(parts) == 2 else (inner, "")


def format_link_target(target: str) -> str:
    """Write-side twin of :func:`split_link_target`: render ``target`` for emission inside a
    markdown link's parentheses. A target containing whitespace is angle-wrapped (``<...>``) —
    the ONE parseable citation form for a spacey path (per the parse rule above, a bare spacey
    target lexically splits at the first whitespace and would never resolve again); any other
    target is returned unchanged."""
    return f"<{target}>" if re.search(r"\s", target) else target


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


def source_definitions(body: str) -> Iterator[tuple[str, str]]:
    """Yield ``(marker_id, rest)`` for every raw-source footnote DEFINITION line inside the page's
    ``## Sources`` section — THE single walk over a page's source citations. ``rest`` is everything
    after ``[^id]:`` (the source link plus any locator/description tail). Fence-aware and
    section-aware via :func:`iter_lines`: a heading toggles the Sources section and code fences are
    skipped, so a page documenting the citation format is never mis-read as citing.

    Model-supplied ``[^llm]`` definitions are SKIPPED — they cite "LLM", not a raw file, and every
    consumer (``validate``'s provenance check, ``lint``'s locator check, ``curate``'s cited-key
    collection) wants only the raw-file citations. Those consumers therefore agree by construction
    on what a source definition IS."""
    in_sources = False
    for line, in_code in iter_lines(body):
        if in_code:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            in_sources = bool(SOURCES_HEADING_RE.match(stripped))
            continue
        if not in_sources:
            continue
        match = DEF_LINE_RE.match(line)
        if not match or is_llm_marker(match.group(1)):
            continue
        yield match.group(1), match.group(2)


# --- source-citation locators (the `[^sN]` tail after the source link) -----------------------

# The full link span `](path)` / `](<path>)` on a definition line; what follows is the locator tail.
_LINK_SPAN_RE = re.compile(r"\]\((?:<[^>]*>|[^)]*)\)")
# A line-range locator matched as a PREFIX of the tail: `lines 40-52` (single or en/em-dash range).
_LOC_LINES_RE = re.compile(r"^lines?\s+(\d+)(?:\s*[-–—]\s*(\d+))?", re.IGNORECASE)
# The trailing `(ingested YYYY-MM-DD)` stamp the citation emitter always appends last — the one
# suffix strippable unambiguously before reading the locator.
_INGESTED_SUFFIX_RE = re.compile(r"\s*\(ingested[^)]*\)\s*$", re.IGNORECASE)
# A spaced dash (` - ` / ` – ` / ` — `): the description separator, ALSO legal inside a heading, so
# heading verification tries the full text then progressively drops a trailing `<spaced-dash> …`.
_SPACED_DASH_RE = re.compile(r"\s[-–—]\s")
# A `§ Heading` locator's `, line N` / `, lines N-M`: the COMBINED form the ingest agent emits
# (`§ Making a Matcha Latte, lines 55-59`). Split off so BOTH the heading and the line range verify,
# instead of the `, line N` tail defeating the heading match. The range ends at end-of-string OR a
# ` — description` separator, so a trailing description (`§ Heading, line 5 — the note`) still splits.
_HEADING_LINES_SUFFIX_RE = re.compile(r",\s*lines?\s+(\d+)(?:\s*[-–—]\s*(\d+))?(?=\s*$|\s[-–—]\s)", re.IGNORECASE)


@dataclass(frozen=True)
class Locator:
    """A parsed ``[^sN]`` citation locator tail (per ``schema.md`` § Locators). ``kind`` is
    ``"lines"`` (a ``lines A-B`` range), ``"heading"`` (a ``§ Heading``, optionally carrying a
    combined ``, line N`` range), or ``"other"`` (a ``p. 12`` page locator or any unrecognized form —
    agent-verified, not checkable offline). ``start``/``end`` carry a 1-based line range when one is
    present (on a ``"lines"`` locator or the combined ``"heading"`` form); ``heading`` carries the
    section name for a ``"heading"`` locator. ``text`` is the raw tail, kept for messages."""

    kind: str
    text: str
    start: int | None = None
    end: int | None = None
    heading: str | None = None


def locator_tail(rest: str) -> str | None:
    """The locator tail on a footnote-definition line's ``rest`` (everything after the source link),
    or None when there is none. A locator is comma-separated from the link (``…md), lines 40-52``,
    per ``schema.md`` § Locators); only the unambiguous trailing ``(ingested …)`` stamp is stripped —
    the ``- description`` separator is left in place because it is a spaced dash, indistinguishable
    from a dash inside a heading (:func:`parse_locator` and its consumers handle the description)."""
    span = _LINK_SPAN_RE.search(rest)
    if span is None:
        return None
    tail = rest[span.end() :].lstrip()
    if not tail.startswith(","):
        return None  # a bare ` - description` (no locator) or nothing
    tail = _INGESTED_SUFFIX_RE.sub("", tail[1:].strip()).strip()
    return tail or None


def parse_locator(tail: str) -> Locator:
    """Parse a locator ``tail`` (from :func:`locator_tail`) into a :class:`Locator`. A ``lines A-B``
    prefix is a line range; a ``§ Heading`` is a section, and a trailing ``, line N`` / ``, lines
    N-M`` on it is split off as a line range so BOTH halves can be verified — the combined form the
    ingest agent emits, whose ``, line N`` tail otherwise defeats the heading match. Anything else
    (``p. 12``, ``pp. 3-5``, unrecognized) is ``"other"`` — agent-verified, not offline-checkable."""
    lines_m = _LOC_LINES_RE.match(tail)
    if lines_m:
        start = int(lines_m.group(1))
        end = int(lines_m.group(2)) if lines_m.group(2) else start
        return Locator(kind="lines", text=tail, start=start, end=end)
    if tail.startswith("§"):
        heading = tail[1:].strip()
        start = end = None
        suffix = _HEADING_LINES_SUFFIX_RE.search(heading)
        if suffix:
            start = int(suffix.group(1))
            end = int(suffix.group(2)) if suffix.group(2) else start
            heading = heading[: suffix.start()].strip()
        return Locator(kind="heading", text=tail, start=start, end=end, heading=heading or None)
    return Locator(kind="other", text=tail)


def heading_candidates(text: str) -> Iterator[str]:
    """The heading strings to try for a ``§`` locator, most-specific first: the full text, then it
    with a trailing ``<spaced-dash> …`` segment dropped, and so on. So a heading that legitimately
    contains a spaced dash (``A word on the rivalry — yes, the coffee``) matches on the full text,
    while a real trailing description (``Nonexistent Heading - x``) is trimmed away and re-tried."""
    text = text.strip()
    yield text
    for match in reversed(list(_SPACED_DASH_RE.finditer(text))):
        candidate = text[: match.start()].strip()
        if candidate:
            yield candidate


def source_heading_texts(text: str) -> list[str]:
    """The markdown headings in a raw source ``text`` — each heading line's text with the leading
    ``#``/space stripped, ORIGINAL casing preserved, in document order, de-duplicated. Feeds
    human-facing hints (e.g. ``wiki_raw``'s "not a heading" error) that want the source's own casing;
    :func:`source_headings` is this same set case-folded for matching. Fence-aware via
    :func:`iter_lines`: a ``# comment`` inside a ``` code fence is prose, not a heading."""
    seen: dict[str, None] = {}  # dict keeps first-seen order while de-duplicating
    for line, in_code in iter_lines(text):
        if not in_code and line.lstrip().startswith("#"):
            seen.setdefault(line.lstrip().lstrip("#").strip(), None)
    return list(seen)


def source_headings(text: str) -> set[str]:
    """The set of markdown headings in a raw source ``text`` — each heading line's text with the
    leading ``#``/space stripped and case-folded — that a ``§ Heading`` locator may name. The
    case- and order-preserving variant is :func:`source_heading_texts`. Fence-aware via
    :func:`iter_lines`: a ``# comment`` inside a ``` code fence is prose, not a heading."""
    return {h.lower() for h in source_heading_texts(text)}


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


def is_within(path_abs: str | os.PathLike, base: str | os.PathLike, *, flavor=os.path) -> bool:
    """True if ``path_abs`` lies inside directory ``base`` (case-folded, purely LEXICAL — no
    symlink resolution, mirroring :func:`link_abs`; resolving only one side would diverge under
    a symlinked wiki/raw path). The ONE containment primitive: the citation predicate below and
    ``config.root_covering`` (the root-lookup behind the deletion sweep and the agent prompt's
    raw-dir bullet) both build on it.

    ``flavor`` (``os.path`` by default — production always uses the native flavor) is the pure
    lexical path module the containment math runs through. It exists so the Windows semantics —
    ``ntpath.normcase`` case-folds AND rewrites ``/`` to ``\\``, so a drive-letter/mixed-case/
    mixed-separator pair still nests — are unit-testable from any platform (the suite probes
    both ``ntpath`` and ``posixpath`` explicitly instead of trusting whichever OS CI runs on)."""
    base_s = flavor.normcase(flavor.normpath(str(base)))
    p = flavor.normcase(flavor.normpath(str(path_abs)))
    return p == base_s or p.startswith(base_s + flavor.sep)


def is_source_citation(page_rel: str, target: str) -> bool:
    """True when the link ``target`` written in wiki page ``page_rel`` is a citation into a
    SOURCE tree — every configured raw source root (``config.source_roots()``, the one deduped
    ``RAW_DIRS``+``RAW_DIR`` union) plus ``config.DOCS_DIR``, all read at call time so tests
    (and out-of-workspace layouts) can repoint them. Such a link is legal provenance, never a
    wiki cross-link (decided rule 1 in the module docstring). Filesystem-space twin of
    :func:`resolves_to_source` (see there for why both exist).

    Containment is lexical and existence is NOT required: whether the cited file is really on
    disk is the strict gate's job (``validate.source_issues``), not the grammar's."""
    abs_path = link_abs(page_rel, target)
    if abs_path is None:
        return False
    return any(is_within(abs_path, root) for root in (*config.source_roots(), config.DOCS_DIR))


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
    The shared upstream of ``store.find_broken_links`` / ``store.inbound_map`` /
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
