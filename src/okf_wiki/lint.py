"""The Lint operation as a REAL, code-level health check (no LLM, no network).

Pure static analysis over the loaded wiki:
  (1) contradictions = pages containing the '> [!CONTRADICTION]' marker
  (2) orphans        = pages no other page links to AND that link to nothing
  (3) missing_cites  = factual-looking paragraphs with no [^sN] footnote marker
  (4) broken_links   = relative .md cross-links whose target page does not exist
  (5) missing_type   = frontmatter without a 'type'
  (6) stale          = timestamp older than stale_days

REFINEMENT: ok() returns True unless there are STRUCTURAL problems — missing_type,
broken_links, bad_sources (a fact citing a missing raw/ file), or wikilinks (a
``[[wiki-style]]`` link). contradictions/orphans/missing_cites/stale/llm_facts/
suggested_links are ADVISORY — render() lists every category with counts, but they do
NOT flip ok(). The per-page citation (source) and wikilink checks are shared with the
ingest gate via :mod:`okf_wiki.validate`. This keeps `okf-wiki lint` green on an empty
seeded wiki and avoids failing on the advisory missing-cites heuristic.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from . import okf
from . import store
from . import validate
from .okf import Page

CONTRADICTION_MARKER = "> [!CONTRADICTION]"
LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")
FOOTNOTE_RE = re.compile(r"\[\^[\w.-]+\]")
# A model-supplied ("source: LLM") footnote marker, e.g. [^llm1]. These facts are added
# from the model's own knowledge (essential, high-confidence, on-topic) rather than a raw
# file, and are deliberately NOT required to cite a raw/ file.
LLM_MARKER_RE = re.compile(r"\[\^llm[\w.-]*\]", re.IGNORECASE)


@dataclass
class LintReport:
    contradictions: list[str] = field(default_factory=list)        # rel_paths
    orphans: list[str] = field(default_factory=list)               # rel_paths
    missing_cites: list[tuple[str, str]] = field(default_factory=list)  # (rel_path, preview)
    broken_links: list[tuple[str, str]] = field(default_factory=list)   # (rel_path, target)
    missing_type: list[str] = field(default_factory=list)          # rel_paths
    stale: list[str] = field(default_factory=list)                 # rel_paths
    bad_sources: list[tuple[str, str]] = field(default_factory=list)    # (rel_path, target)
    llm_facts: list[str] = field(default_factory=list)             # rel_paths (advisory)
    # (rel_path, "links to add"): page mentions another page's title but doesn't link it.
    suggested_links: list[tuple[str, str]] = field(default_factory=list)  # advisory
    wikilinks: list[tuple[str, str]] = field(default_factory=list)  # (rel_path, [[target]])

    def ok(self) -> bool:
        """True unless there are structural-integrity problems: missing_type, broken_links,
        bad_sources (a RAW fact citing a raw/ file that does not exist — fabricated or
        mistyped provenance), OR wikilinks (a ``[[wiki-style]]`` link, which this wiki does not
        use — it silently breaks navigation). The other categories — including llm_facts (pages
        carrying model-supplied facts, surfaced for transparency) — are advisory and do NOT flip
        ok()."""
        return not (
            self.missing_type or self.broken_links or self.bad_sources or self.wikilinks
        )

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

        lines.append(f"Fabricated/missing sources: {len(self.bad_sources)}")
        for rel, target in self.bad_sources:
            lines.append(f"  - {rel} -> {target}")

        lines.append(f"Pages with model-supplied (LLM) facts: {len(self.llm_facts)}")
        for rel in self.llm_facts:
            lines.append(f"  - {rel}")

        lines.append(f"Suggested links (un-linked mentions): {len(self.suggested_links)}")
        for rel, target in self.suggested_links:
            lines.append(f"  - {rel} -> {target}")

        lines.append(f"Wiki-style [[links]] (not allowed): {len(self.wikilinks)}")
        for rel, target in self.wikilinks:
            lines.append(f"  - {rel} -> [[{target}]]")

        lines.append("")
        lines.append(
            "OK"
            if self.ok()
            else "FAIL (missing type, broken links, fabricated sources, or [[wiki-links]])"
        )
        return "\n".join(lines)


def _outbound_links(page: Page) -> list[str]:
    """All .md link targets in the body, resolved to wiki-root-relative posix
    rel_paths (skipping Sources-section raw/ links). Used for orphan +
    broken-link detection."""
    base_dir = os.path.dirname(page.rel_path)
    targets: list[str] = []
    for match in LINK_RE.finditer(page.body):
        raw_target = match.group(1).strip()
        # Skip external links and anchors.
        if "://" in raw_target or raw_target.startswith("#"):
            continue
        # Skip links into the raw/ source tree (these are the ## Sources footnotes).
        # They may appear as ../../raw/foo.md relative to the page.
        norm = os.path.normpath(os.path.join(base_dir, raw_target))
        norm = norm.replace(os.sep, "/")
        first = norm.split("/", 1)[0]
        if first == "raw" or "/raw/" in ("/" + norm):
            continue
        # Resolve to a wiki-root-relative posix path.
        targets.append(norm)
    return targets


def _has_footnote(paragraph: str) -> bool:
    """True if a [^sN]-style footnote marker is present."""
    return FOOTNOTE_RE.search(paragraph) is not None


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


def _missing_cite_preview(page: Page) -> str | None:
    """Return a short preview of the first factual-looking paragraph in the page
    body that lacks a footnote marker, or None if every such paragraph is cited.

    A "factual-looking paragraph" is a block of >1 sentence that is not a heading,
    not inside a code fence, and not part of the trailing ## Sources section."""
    in_code_fence = False
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

    for line in page.body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        if stripped.startswith("#"):
            # Heading: paragraph boundary; detect the Sources section.
            preview = flush(paragraph_lines)
            paragraph_lines = []
            if preview is not None:
                return preview
            if re.match(r"#+\s*sources\b", stripped, re.IGNORECASE):
                in_sources = True
            continue
        if in_sources:
            continue
        if stripped.startswith(">"):
            # Callout (e.g. contradiction) — not a plain factual paragraph.
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
    page: Page, title_index: list[tuple[str, str, str]], linked: set[str], cap: int = 8
) -> list[str]:
    """Other pages whose title appears (whole-word, case-insensitive) in this page's body
    but which this page does not already link to — candidate cross-links to add. Advisory:
    a high-precision nudge toward a denser knowledge graph, capped to avoid noise."""
    body_lower = page.body.lower()
    found: list[str] = []
    for rel_path, title_lower, title in title_index:
        if rel_path == page.rel_path or rel_path in linked:
            continue
        if re.search(rf"\b{re.escape(title_lower)}\b", body_lower):
            found.append(f"{rel_path} (mentions '{title}')")
            if len(found) >= cap:
                break
    return found


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

    # Build the outbound-link graph once.
    outbound: dict[str, list[str]] = {}
    inbound_targets: set[str] = set()
    for page in pages:
        links = _outbound_links(page)
        outbound[page.rel_path] = links
        for target in links:
            inbound_targets.add(target)

    # Page titles long enough to match on (for the un-linked-mention suggestion).
    title_index = [
        (p.rel_path, p.title.strip().lower(), p.title.strip())
        for p in pages
        if len(p.title.strip()) >= 3
    ]

    for page in pages:
        # missing_type
        try:
            okf.validate(page.frontmatter)
        except okf.OKFError:
            report.missing_type.append(page.rel_path)

        # contradictions
        if CONTRADICTION_MARKER in page.body:
            report.contradictions.append(page.rel_path)

        # broken_links
        for target in outbound[page.rel_path]:
            if target not in page_paths:
                report.broken_links.append((page.rel_path, target))

        # orphans: no inbound links AND no outbound (non-raw) links.
        has_inbound = page.rel_path in inbound_targets
        has_outbound = bool(outbound[page.rel_path])
        if not has_inbound and not has_outbound:
            report.orphans.append(page.rel_path)

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

        # llm_facts (advisory): page carries one or more model-supplied facts.
        if LLM_MARKER_RE.search(page.body):
            report.llm_facts.append(page.rel_path)

        # suggested_links (advisory): un-linked mentions of other pages' titles.
        for sug in _unlinked_mentions(page, title_index, set(outbound[page.rel_path])):
            report.suggested_links.append((page.rel_path, sug))

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
    return report
