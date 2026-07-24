"""The Lint operation as a REAL, code-level health check (no LLM, no network).

Pure static analysis over the loaded wiki:
  (1) contradictions = pages containing the '> [!CONTRADICTION]' marker
  (2) orphans        = pages no other page links to AND that link to nothing
  (3) missing_cites  = factual-looking paragraphs with no [^sN] footnote marker
  (4) broken_links   = relative .md cross-links whose target page does not exist
  (5) missing_type   = frontmatter without a 'type'
  (6) stale          = timestamp older than stale_days
  (7) undefined_abbrevs = abbreviations used across pages but never defined (no entry, no
                          inline expansion) — the glossary's to-do list

REFINEMENT: ok() returns True unless there are STRUCTURAL problems — missing_type,
broken_links, bad_sources (a fact citing a missing raw/ file), or wikilinks (a
``[[wiki-style]]`` link). contradictions/orphans/missing_cites/stale/llm_facts/
suggested_links/undefined_abbrevs are ADVISORY — render() lists every category with counts,
but they do NOT flip ok(). The per-page citation (source) and wikilink checks are shared with the
ingest gate via :mod:`citadel.validate`, and the link/fence grammar (what counts as a wiki
cross-link vs a source citation into raw/ or docs/, and that fenced links are literal text) is
shared via :mod:`citadel.grammar` — so lint and `citadel check` agree by construction. This
keeps `citadel lint` green on an empty seeded wiki and avoids failing on the advisory
missing-cites heuristic.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config, grammar, okf, pdftext, store, transcribe, validate
from .okf import Page


# An abbreviation/acronym candidate: 2–6 chars, all caps, starting with a letter (TCO, API,
# SLA, KPI, V60, B2B). Used to surface domain abbreviations that recur across the wiki but are
# never defined — neither given an `Abbreviation` page nor spelled out in parentheses anywhere.
# A high-precision, capped *nudge* (like suggested_links), never a structural failure.
ABBREV_RE = re.compile(r"\b[A-Z][A-Z0-9]{1,5}\b")
# A parenthetical pairing that counts as an inline definition: `... solids (TDS)` or
# `WDT (Weiss Distribution Technique)`. Either side of the parens names the short form.
_ABBR_IN_PARENS_RE = re.compile(r"\(\s*([A-Z][A-Z0-9]{1,5})\b")
_ABBR_THEN_PARENS_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,5})\s*\(")
# Unicode sub/superscript digits: a token trailed by one is a chemistry formula (CO₂, H₂O),
# not an abbreviation — skip it so the glossary nudge doesn't flag molecules.
_SCRIPT_DIGITS = "₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹"
# An abbreviation must recur on at least this many distinct pages before the nudge fires —
# cross-page recurrence is the low-noise signal of shared jargon worth a glossary entry (a
# one-off is more likely a typo or a throwaway mention).
_ABBREV_MIN_PAGES = 2
# Cap on the undefined-abbreviation list so a jargon-dense wiki can't drown the report.
_ABBREV_REPORT_CAP = 25
# Two open-point identities this similar (SequenceMatcher ratio) are flagged as a possible
# duplicate/typo. This is a TYPO guard only — it cannot catch two different noun phrases for the
# same point (which share no characters); the generated open-points catalog is the real review
# surface for that. Capped so a busy wiki can't drown the report.
_OP_DUP_RATIO = 0.85
_OP_DUP_CAP = 50

# A markdown list bullet made ONLY of links (a `## See also`-style navigation line), not factual
# prose. Skipped by the missing-citation heuristic: a link *title* containing sentence punctuation
# (`Immersion vs. Percolation Brewing`) otherwise fakes a multi-sentence paragraph and mis-flags the
# whole nav list as an uncited fact. Handles one-link-per-bullet and several ` - `-joined on a line.
_LIST_BULLET_RE = re.compile(r"^[-*+]\s")
_MD_FULL_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")

# Roman numerals and fiscal-period labels are not glossary abbreviations. A roman numeral is excluded
# only in an ordinal context (`Chapter IV`), so a real abbreviation that merely parses as a numeral
# (DC, MC, CI) is still surfaced; `Q1..Q4` / `H1`/`H2` are excluded outright.
_ROMAN_RE = re.compile(r"^(?=[MDCLXVI])M{0,4}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})$")
_FISCAL_RE = re.compile(r"^(?:Q[1-4]|H[12])$")
_ORDINAL_CONTEXT = frozenset(
    {
        "chapter",
        "part",
        "section",
        "sec",
        "vol",
        "volume",
        "book",
        "act",
        "scene",
        "appendix",
        "figure",
        "fig",
        "table",
        "canto",
        "phase",
        "step",
        "tier",
        "note",
    }
)

# --- Locator verification (deterministic, for text-bearing raw sources) ------------------
# The locator grammar — the link span, `lines A-B` / `§ Heading` / combined `§ Heading, line N`
# parsing, and the source-heading set — lives in grammar.py (the single home of the citation
# grammar) as grammar.locator_tail / parse_locator / heading_candidates / source_headings. What
# stays here is the IO + policy: which source extensions are non-text, and the advisory framing.
# Paginated / binary source extensions whose locators (`p. 12`) are agent-verified, not read here.
# `.pdf` is deliberately ABSENT: a genuine PDF (`%PDF-` magic) is handled entirely by the
# `pdftext.is_pdf_file` branch above (served from its cached extraction, or skipped when none
# exists), while a text file merely NAMED `.pdf` (no magic — it ingested as ordinary text, and can
# carry real `lines A-B` locators) must fall through to the text read below and be verified. This
# mirrors how the audio extensions are handled purely by the `transcribe.is_audio_ext` branch.
_NON_TEXT_EXTS = {
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".odt",
    ".odp",
    ".ods",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".webp",
    ".tif",
    ".tiff",
    ".heic",
}


@dataclass
class LintReport:
    contradictions: list[str] = field(default_factory=list)  # rel_paths
    orphans: list[str] = field(default_factory=list)  # rel_paths
    missing_cites: list[tuple[str, str]] = field(default_factory=list)  # (rel_path, preview)
    broken_links: list[tuple[str, str]] = field(default_factory=list)  # (rel_path, target)
    missing_type: list[str] = field(default_factory=list)  # rel_paths
    stale: list[str] = field(default_factory=list)  # rel_paths
    bad_sources: list[tuple[str, str]] = field(default_factory=list)  # (rel_path, target)
    llm_facts: list[str] = field(default_factory=list)  # rel_paths (advisory)
    # (rel_path, "links to add"): page mentions another page's title but doesn't link it.
    suggested_links: list[tuple[str, str]] = field(default_factory=list)  # advisory
    wikilinks: list[tuple[str, str]] = field(default_factory=list)  # (rel_path, [[target]])
    # (abbr, #pages): an abbreviation used on >=2 pages with no Abbreviation entry and no
    # inline parenthetical expansion anywhere — a candidate for the glossary. Advisory.
    undefined_abbrevs: list[tuple[str, int]] = field(default_factory=list)
    # ("rel#title", "rel#title"): two open-point threads with near-identical identities — a
    # TYPO/near-duplicate guard (it cannot catch two different noun phrases for one point). Advisory.
    duplicate_open_points: list[tuple[str, str]] = field(default_factory=list)
    # (rel_path, title): an open-point thread missing its `id:` line or any dated bullet. Advisory.
    malformed_open_points: list[tuple[str, str]] = field(default_factory=list)
    # (rel_path, detail): a `lines A-B` locator past the end of its text source, or a `§ Heading`
    # locator naming a heading the source does not contain. Advisory — a locator being off does
    # not break navigation, so it does NOT flip ok(); it is also fed to `citadel curate` as a finding.
    locator_issues: list[tuple[str, str]] = field(default_factory=list)
    # rel_paths over the SOFT page-length threshold (config.CURATE_PAGE_SOFT_LINES, ~400 body lines):
    # long enough to be worth an eventual topic split. Advisory — "lint warns at soft, curate acts at
    # hard": this does NOT flip ok(); `citadel curate` only plans a split
    # once a page crosses the HARD threshold.
    long_pages: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        """True unless there are structural-integrity problems: missing_type, broken_links,
        bad_sources (a RAW fact citing a raw/ file that does not exist — fabricated or
        mistyped provenance), OR wikilinks (a ``[[wiki-style]]`` link, which this wiki does not
        use — it silently breaks navigation). The other categories — including llm_facts (pages
        carrying model-supplied facts, surfaced for transparency) — are advisory and do NOT flip
        ok()."""
        return not (self.missing_type or self.broken_links or self.bad_sources or self.wikilinks)

    def render(self) -> str:
        """Human-readable report; lists every category with counts."""
        lines: list[str] = []
        lines.append("Lint report")
        lines.append("===========")

        lines.append(f"Contradictions: {len(self.contradictions)}")
        for rel in self.contradictions:
            lines.append(f"  - {rel}")

        lines.append(f"Orphans: {len(self.orphans)}")
        for rel in self.orphans:
            lines.append(f"  - {rel}")

        lines.append(f"Missing citations: {len(self.missing_cites)}")
        for rel, preview in self.missing_cites:
            lines.append(f"  - {rel}: {preview}")

        lines.append(f"Broken links: {len(self.broken_links)}")
        for rel, target in self.broken_links:
            lines.append(f"  - {rel} -> {target}")

        lines.append(f"Missing type: {len(self.missing_type)}")
        for rel in self.missing_type:
            lines.append(f"  - {rel}")

        lines.append(f"Stale: {len(self.stale)}")
        for rel in self.stale:
            lines.append(f"  - {rel}")

        lines.append(f"Long pages (over soft length, consider a split): {len(self.long_pages)}")
        for rel in self.long_pages:
            lines.append(f"  - {rel}")

        lines.append(f"Fabricated/missing sources: {len(self.bad_sources)}")
        for rel, target in self.bad_sources:
            lines.append(f"  - {rel} -> {target}")

        lines.append(f"Pages with model-supplied (LLM) facts: {len(self.llm_facts)}")
        for rel in self.llm_facts:
            lines.append(f"  - {rel}")

        lines.append(f"Suggested links (un-linked mentions): {len(self.suggested_links)}")
        for rel, target in self.suggested_links:
            lines.append(f"  - {rel} -> {target}")

        lines.append(f"Undefined abbreviations (used, never defined): {len(self.undefined_abbrevs)}")
        for abbr, n_pages in self.undefined_abbrevs:
            lines.append(f"  - {abbr} (on {n_pages} pages)")

        lines.append(f"Wiki-style [[links]] (not allowed): {len(self.wikilinks)}")
        for rel, target in self.wikilinks:
            lines.append(f"  - {rel} -> [[{target}]]")

        lines.append(f"Near-duplicate open points (review for a fork): {len(self.duplicate_open_points)}")
        for a, b in self.duplicate_open_points:
            lines.append(f"  - {a} ~ {b}")

        lines.append(f"Malformed open points (no id/date): {len(self.malformed_open_points)}")
        for rel, title in self.malformed_open_points:
            lines.append(f"  - {rel}: {title}")

        lines.append(f"Locator issues (out-of-range lines / missing headings): {len(self.locator_issues)}")
        for rel, detail in self.locator_issues:
            lines.append(f"  - {rel}: {detail}")

        lines.append("")
        lines.append("OK" if self.ok() else "FAIL (missing type, broken links, fabricated sources, or [[wiki-links]])")
        return "\n".join(lines)


def _outbound_links(page: Page) -> list[str]:
    """Wiki cross-link targets for orphan/broken-link detection — delegates to the shared
    :func:`grammar.resolved_md_links`; see grammar.py for the decided rules."""
    return [resolved for _raw, resolved in grammar.resolved_md_links(page.rel_path, page.body)]


def orphans(pages: list[Page], outbound: dict[str, list[str]] | None = None) -> list[str]:
    """Island pages — no page links TO them AND they link to nothing (only source citations, which
    resolve into raw/ and are never wiki cross-links). THE single orphan definition: :func:`lint`'s
    own check and ``citadel curate``'s plan both consume this (the :func:`check_locators` precedent),
    so they agree by construction. Sorted. ``outbound`` accepts a caller's already-built
    ``{rel_path: [targets]}`` link graph (:func:`lint` computes one anyway for broken_links) so the
    whole-corpus link parse runs once, not twice."""
    if outbound is None:
        outbound = {page.rel_path: _outbound_links(page) for page in pages}
    inbound: set[str] = set()
    for links in outbound.values():
        inbound.update(links)
    return sorted(p.rel_path for p in pages if p.rel_path not in inbound and not outbound[p.rel_path])


def _has_footnote(paragraph: str) -> bool:
    """True if a [^sN]-style footnote marker is present."""
    return grammar.FOOTNOTE_RE.search(paragraph) is not None


def _is_stale(page: Page, stale_days: int) -> bool:
    """True if the page's timestamp is older than stale_days. A missing/unparseable
    timestamp is NOT counted as stale (it is simply unknown)."""
    ts = page.frontmatter.get("timestamp")
    if not ts or not isinstance(ts, str):
        return False
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    age_days = (datetime.now(timezone.utc) - dt).days
    return age_days > stale_days


def _is_link_list_line(stripped: str) -> bool:
    """True for a markdown list bullet whose content is only links + separators — a `## See also`
    navigation line, not a factual sentence. Removing every ``[text](url)`` link must leave no
    letter/digit behind (``- [Coffee](coffee.md)`` / ``- [A](a) - [B](b)`` -> only bullet + dashes)."""
    if not _LIST_BULLET_RE.match(stripped):
        return False
    residue = _MD_FULL_LINK_RE.sub("", stripped)
    return not re.search(r"[0-9A-Za-z]", residue)


def _missing_cite_preview(page: Page) -> str | None:
    """Return a short preview of the first factual-looking paragraph in the page
    body that lacks a footnote marker, or None if every such paragraph is cited.

    A "factual-looking paragraph" is a block of >1 sentence that is not a heading,
    not inside a code fence, and not part of the trailing ## Sources section."""
    in_sources = False
    paragraph_lines: list[str] = []

    def flush(buf: list[str]) -> str | None:
        text = " ".join(buf).strip()
        if not text:
            return None
        # Sentence count heuristic: count terminal punctuation.
        sentences = [s for s in re.split(r"[.!?]+\s+|[.!?]+$", text) if s.strip()]
        if len(sentences) <= 1:
            return None
        if _has_footnote(text):
            return None
        return text[:80]

    for line, in_code in grammar.iter_lines(page.body):
        if in_code:
            continue
        stripped = line.strip()
        if stripped.startswith("#"):
            # Heading: paragraph boundary; detect the Sources section.
            preview = flush(paragraph_lines)
            paragraph_lines = []
            if preview is not None:
                return preview
            if grammar.SOURCES_HEADING_RE.match(stripped):
                in_sources = True
            continue
        if in_sources:
            continue
        if stripped.startswith(">"):
            # Callout (e.g. contradiction) — not a plain factual paragraph.
            continue
        if _is_link_list_line(stripped):
            # A `## See also`-style link list — navigation, not an uncited factual paragraph.
            continue
        if not stripped:
            preview = flush(paragraph_lines)
            paragraph_lines = []
            if preview is not None:
                return preview
            continue
        paragraph_lines.append(stripped)

    # Trailing paragraph (only if not inside the Sources section).
    if not in_sources:
        preview = flush(paragraph_lines)
        if preview is not None:
            return preview
    return None


def _unlinked_mentions(
    page: Page, title_index: list[tuple[str, re.Pattern[str], str]], linked: set[str], cap: int = 8
) -> list[str]:
    """Other pages whose title appears (whole-word, case-insensitive) in this page's body
    but which this page does not already link to — candidate cross-links to add. Advisory:
    a high-precision nudge toward a denser knowledge graph, capped to avoid noise.
    ``title_index`` carries each title's pattern PRE-compiled by :func:`lint` — building a fresh
    regex per (page, title) pair made this the most expensive lint step on a large wiki."""
    body_lower = page.body.lower()
    found: list[str] = []
    for rel_path, title_pattern, title in title_index:
        if rel_path == page.rel_path or rel_path in linked:
            continue
        if title_pattern.search(body_lower):
            found.append(f"{rel_path} (mentions '{title}')")
            if len(found) >= cap:
                break
    return found


def _preceding_word(line: str, index: int) -> str:
    """The lower-cased word immediately before ``index`` in ``line`` (trailing punctuation stripped),
    or ``''`` — used to tell a roman numeral in an ordinal context (``Chapter IV``) from a real
    abbreviation that merely parses as a numeral (``DC``, ``MC``)."""
    before = line[:index].rstrip()
    if not before:
        return ""
    return before.rsplit(maxsplit=1)[-1].strip(".,;:—–-").lower()


def _abbrev_token_uses(body: str) -> set[str]:
    """Abbreviation-shaped tokens (see ABBREV_RE) used in the prose of ``body`` (see
    :func:`grammar.prose_lines` — headings count, code fences and ``## Sources`` do not), skipping
    chemistry formulae (a token trailed by a subscript digit, e.g. CO₂), fiscal-period labels
    (``Q1``..``Q4`` / ``H1``/``H2``), and roman numerals in an ordinal context (``Chapter IV``)."""
    found: set[str] = set()
    for line in grammar.prose_lines(body, skip_sources=True):
        for m in ABBREV_RE.finditer(line):
            if m.end() < len(line) and line[m.end()] in _SCRIPT_DIGITS:
                continue
            token = m.group(0)
            if _FISCAL_RE.match(token):
                continue
            if _ROMAN_RE.match(token) and _preceding_word(line, m.start()) in _ORDINAL_CONTEXT:
                continue
            found.add(token)
    return found


def _abbrev_expansions(body: str) -> set[str]:
    """Abbreviation tokens written next to a parenthetical expansion in the prose of ``body``
    (``solids (TDS)`` or ``WDT (Weiss …)``) — i.e. defined inline, so not a glossary gap. Only
    prose counts (see :func:`grammar.prose_lines`): an expansion that appears solely inside a code
    fence or the ``## Sources`` section must not suppress the nudge for real uses elsewhere."""
    out: set[str] = set()
    for line in grammar.prose_lines(body, skip_sources=True):
        out.update(_ABBR_IN_PARENS_RE.findall(line))
        out.update(_ABBR_THEN_PARENS_RE.findall(line))
    return out


def _defined_abbrevs(pages: list[Page]) -> set[str]:
    """Short forms already covered by an ``Abbreviation`` page — its title's short side plus
    any abbreviation-shaped ``aliases`` — upper-cased for case-insensitive matching."""
    defined: set[str] = set()
    for page in pages:
        if (page.type or "").strip().lower() != "abbreviation":
            continue
        short, _expansion = okf.abbrev_short_long(page)
        if short:
            defined.add(short.upper())
        aliases = page.frontmatter.get("aliases") or []
        if isinstance(aliases, list):
            for alias in aliases:
                text = str(alias).strip()
                if ABBREV_RE.fullmatch(text):
                    defined.add(text.upper())
    return defined


def _undefined_abbrevs(pages: list[Page]) -> list[tuple[str, int]]:
    """Abbreviations used on >= 2 distinct pages that have neither an ``Abbreviation`` entry nor
    an inline parenthetical expansion anywhere — the glossary's to-do list. Sorted by page count
    (desc) then token, capped. Advisory: a heuristic nudge, not a structural failure."""
    defined = _defined_abbrevs(pages)
    expanded: set[str] = set()
    pages_by_token: dict[str, set[str]] = {}
    for page in pages:
        expanded |= _abbrev_expansions(page.body)
        for token in _abbrev_token_uses(page.body):
            pages_by_token.setdefault(token, set()).add(page.rel_path)
    candidates = [
        (token, len(where))
        for token, where in pages_by_token.items()
        if len(where) >= _ABBREV_MIN_PAGES and token.upper() not in defined and token not in expanded
    ]
    candidates.sort(key=lambda t: (-t[1], t[0]))
    return candidates[:_ABBREV_REPORT_CAP]


def _open_point_key(pt: store.OpenPoint) -> str:
    """The identity to compare threads on: the explicit ``op-<slug>`` id, or the slugified title
    when the ``id:`` line is missing."""
    return pt.point_id or okf.slugify(pt.title)


def _duplicate_open_points(points: list[store.OpenPoint]) -> list[tuple[str, str]]:
    """Pairs of open-point threads whose identities are near-identical (>= _OP_DUP_RATIO) — a typo
    /near-duplicate nudge, NOT a merge oracle (two different noun phrases for one point share no
    characters and are invisible here; the generated catalog is the real review surface). Sorted,
    de-duplicated, capped."""
    labeled = [(_open_point_key(pt), f"{pt.page_rel}#{pt.title}") for pt in points]
    labeled = [(k, label) for k, label in labeled if k]
    pairs: set[tuple[str, str]] = set()
    for i, (key_a, label_a) in enumerate(labeled):
        # Reuse one matcher per outer key so its second-sequence index is computed once, and gate
        # the O(len) ratio() behind the two cheap upper-bound ratios so obvious mismatches are
        # skipped. Short-circuit once _OP_DUP_CAP pairs are found — deterministic given the stable
        # rel_path/title ordering — so this never scans the full O(n^2) space on a large wiki.
        matcher = difflib.SequenceMatcher(None, b=key_a)
        for key_b, label_b in labeled[i + 1 :]:
            if label_a == label_b:
                continue
            matcher.set_seq1(key_b)
            if (
                matcher.real_quick_ratio() >= _OP_DUP_RATIO
                and matcher.quick_ratio() >= _OP_DUP_RATIO
                and matcher.ratio() >= _OP_DUP_RATIO
            ):
                pairs.add(tuple(sorted((label_a, label_b))))
                if len(pairs) >= _OP_DUP_CAP:
                    return sorted(pairs)
    return sorted(pairs)


def _read_source_text(page_rel: str, target: str, cache: dict[str, str | None]) -> str | None:
    """The text of the raw source a citation ``target`` (written in ``page_rel``) points at, or
    None when it is not a locator-checkable text file: not a source citation, missing, a paginated/
    binary format (PDF/Office/image — those carry agent-verified page locators), or undecodable. A
    NUL byte or a decode failure means "binary" — the locator is left for the agent, not flagged.

    ``cache`` memoizes the result per resolved absolute path for the lifetime of one
    :func:`check_locators` call, so a page whose many ``[^sN]`` locators cite the SAME source file
    reads that file once (O(files), not O(citations))."""
    if not grammar.is_source_citation(page_rel, target):
        return None
    abs_path = grammar.link_abs(page_rel, target)
    if abs_path is None:
        return None
    if abs_path in cache:
        return cache[abs_path]
    text = _load_source_text(abs_path)
    cache[abs_path] = text
    return text


def _load_source_text(abs_path: str) -> str | None:
    """Read one resolved source path as locator-checkable text, or None when it is missing, a
    paginated/binary format, or undecodable (the uncached inner read behind :func:`_read_source_text`).
    An audio/video source is checkable through its CACHED whisper transcript — the very text the
    ingest agent read and cited — and skipped (None) when no cache exists on this machine. A text
    file merely RENAMED ``.mp3`` (no audio magic — it ingested as ordinary text) falls through to
    the normal decode below, so its line locators keep being verified. A genuine PDF (``%PDF-``
    magic) is checkable the same way through its CACHED pypdf text-layer extraction — the text a
    ``pdf``-kind session read and cited — and skipped when none exists (agent-native ingest,
    a different machine, or pypdf absent): its ``p. N`` page locators stay agent-verified."""
    path = Path(abs_path)
    if transcribe.is_audio_ext(path):
        cached = transcribe.cached_transcript(path)
        if cached is not None or transcribe.is_audio_file(path):
            return cached
    if pdftext.is_pdf_file(path):
        return pdftext.cached_text(path)
    if path.suffix.lower() in _NON_TEXT_EXTS:
        return None
    try:
        if not path.is_file():
            return None  # a missing source is bad_sources' job, not the locator check's
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _locator_problem(page_rel: str, target: str, tail: str, cache: dict[str, str | None]) -> str | None:
    """Verify ONE locator ``tail`` against its text source, returning a human-readable problem or
    None. Parsed by :func:`grammar.parse_locator`: a ``lines A-B`` range is checked against the file's
    line count, a ``§ Heading`` against the source's headings (:func:`grammar.source_headings`), and
    the combined ``§ Heading, line N`` form verifies BOTH halves. ``p. 12`` page locators and any
    unrecognized form are agent-verified — skipped. ``cache`` is the per-run source-text memo threaded
    through :func:`_read_source_text`."""
    loc = grammar.parse_locator(tail)
    if loc.kind == "other":
        return None
    text = _read_source_text(page_rel, target, cache)
    if text is None:
        return None
    if loc.start is not None:
        n = len(text.splitlines())
        if loc.start < 1 or loc.start > loc.end or loc.end > n:
            span = f"line {loc.start}" if loc.start == loc.end else f"lines {loc.start}-{loc.end}"
            return f"locator '{span}' out of range (source has {n} lines)"
    if loc.heading is not None:
        headings = grammar.source_headings(text)
        if not any(cand.lower() in headings for cand in grammar.heading_candidates(loc.heading)):
            return f"locator '§ {loc.heading}' names a heading not in the source"
    return None


def check_locators(pages: list[Page]) -> list[tuple[str, str]]:
    """Deterministically verify every ``[^sN]`` citation locator against its text-bearing raw source: a ``lines A-B`` range past the file's end, or a ``§ Heading`` naming
    a heading the source lacks, is a ``(rel_path, detail)`` warning. Office ``p. N`` page
    locators stay agent-verified; a PDF's ``lines A-B`` locators verify against its cached pypdf
    text-layer extraction when one exists (:mod:`citadel.pdftext`), its page locators stay
    agent-verified. Shared by :func:`lint` and ``citadel curate``;
    reuses the one citation/link/fence grammar (:func:`grammar.source_definitions`), so it agrees
    with the strict gate by construction."""
    issues: list[tuple[str, str]] = []
    # ONE source-text memo for the whole call: raw files don't change mid-lint, and N pages citing
    # the same source must read it once — not once per page (for an audio source that read is a
    # full content hash to find its cached transcript, so per-page misses were O(pages × file size)).
    cache: dict[str, str | None] = {}
    for page in pages:
        for _marker_id, rest in grammar.source_definitions(page.body):
            target = grammar.def_link_target(rest)
            if target is None or grammar.is_external(target):
                continue
            tail = grammar.locator_tail(rest)
            if tail is None:
                continue
            problem = _locator_problem(page.rel_path, target, tail, cache)
            if problem:
                issues.append((page.rel_path, problem))
    return sorted(issues)


def lint(pages: list[Page] | None = None, stale_days: int = 365) -> LintReport:
    """If pages is None, store.load(). Build the link graph; flag orphans (no inbound
    and no outbound non-raw links), contradictions (marker present), missing_type
    (okf.validate fails), broken_links (target rel_path not in the page set),
    missing_cites (a multi-sentence paragraph with no [^...] marker, not a
    heading/code-fence/Sources), stale (timestamp older than stale_days), bad_sources
    (fabricated provenance), llm_facts and suggested_links (advisory)."""
    if pages is None:
        pages = store.load()

    report = LintReport()
    page_paths = {p.rel_path for p in pages}

    # Build the outbound-link graph once; broken_links AND orphans consume the same map.
    outbound: dict[str, list[str]] = {page.rel_path: _outbound_links(page) for page in pages}
    report.orphans = orphans(pages, outbound)

    # Page titles long enough to match on (for the un-linked-mention suggestion), each with its
    # whole-word pattern compiled ONCE for the run.
    title_index = [
        (p.rel_path, re.compile(rf"\b{re.escape(title.lower())}\b"), title)
        for p in pages
        if len(title := p.title.strip()) >= 3
    ]

    for page in pages:
        # missing_type
        try:
            okf.validate(page.frontmatter)
        except okf.OKFError:
            report.missing_type.append(page.rel_path)

        # contradictions — matched line-anchored through the shared tolerant pattern (indentation,
        # spacing, case), the SAME one curate's planner and the viewer use, so the three consumers
        # agree by construction (an exact-substring test here missed callouts they both counted).
        if any(grammar.CONTRADICTION_LINE_RE.match(line) for line in page.body.splitlines()):
            report.contradictions.append(page.rel_path)

        # broken_links
        for target in outbound[page.rel_path]:
            if target not in page_paths:
                report.broken_links.append((page.rel_path, target))

        # long_pages (advisory): over the SOFT length threshold — lint warns, curate acts at hard.
        if len(page.body.splitlines()) > config.CURATE_PAGE_SOFT_LINES:
            report.long_pages.append(page.rel_path)

        # missing_cites
        preview = _missing_cite_preview(page)
        if preview is not None:
            report.missing_cites.append((page.rel_path, preview))

        # stale
        if _is_stale(page, stale_days):
            report.stale.append(page.rel_path)

        # bad_sources: a RAW fact cites a raw/ source file that does not exist.
        for target in validate.source_issues(page.rel_path, page.body):
            report.bad_sources.append((page.rel_path, target))

        # wikilinks (structural): [[wiki-style]] links are not allowed.
        for target in validate.wikilink_targets(page.body):
            report.wikilinks.append((page.rel_path, target))

        # llm_facts (advisory): page carries one or more model-supplied facts. Deliberately
        # searched over the WHOLE body (fences and Sources definitions included): the badge
        # answers "does model knowledge appear anywhere on this page", not "how many prose uses".
        if grammar.LLM_MARKER_RE.search(page.body):
            report.llm_facts.append(page.rel_path)

        # suggested_links (advisory): un-linked mentions of other pages' titles.
        for sug in _unlinked_mentions(page, title_index, set(outbound[page.rel_path])):
            report.suggested_links.append((page.rel_path, sug))

    # undefined_abbrevs (advisory): a whole-corpus pass — an abbreviation is "defined" if any
    # page gives it an entry or an inline expansion, so this can't be decided per-page.
    report.undefined_abbrevs = _undefined_abbrevs(pages)

    # open points (advisory): near-duplicate identities (a typo guard) + malformed blocks (a
    # thread with no id: line or no dated bullet). Neither flips ok() — both are review nudges.
    op_points = store.collect_open_points(pages)
    report.malformed_open_points = sorted(
        (pt.page_rel, pt.title) for pt in op_points if not pt.point_id or not pt.bullets
    )
    report.duplicate_open_points = _duplicate_open_points(op_points)

    # locator issues (advisory): line ranges past a text source's end / missing §-headings.
    report.locator_issues = check_locators(pages)

    # Deterministic ordering.
    report.contradictions.sort()
    report.orphans.sort()
    report.missing_cites.sort()
    report.broken_links.sort()
    report.missing_type.sort()
    report.stale.sort()
    report.bad_sources.sort()
    report.llm_facts.sort()
    report.suggested_links.sort()
    report.wikilinks.sort()
    report.long_pages.sort()
    return report
