"""The Open Points feature: parse ``## Open Points`` threads and derive each point's status.

A page can carry an ``## Open Points`` section of ``### `` threads, each an append-only list of
dated ``- YYYY-MM-DD: ...`` bullets under an optional ``id: op-<slug>`` line. This module turns
that prose into :class:`OpenPoint` records and DERIVES a point's current status from its
latest-dated bullet (never stored — one source of truth). The catalog rendering lives in
:mod:`citadel.catalogs`; lint reuses these records for the duplicate-id check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import grammar
from .okf import Page


# A dated timeline bullet inside an `## Open Points` thread: "- 2026-06-10: text [^s2]".
_OP_BULLET_RE = re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*:\s*(.*)$")
# The stable identity line under a thread's `### ` heading: "id: op-checkout-latency".
_OP_ID_RE = re.compile(r"^id:\s*(\S+)\s*$", re.IGNORECASE)
# H2 headings whose section holds open-point threads (English + German).
_OP_SECTION_TITLES = ("open points", "offene punkte")
# Deriving a point's CURRENT status from its latest dated bullet (never stored): a reopen tell
# wins (still open), else a done tell closes it, else it is open.
_OP_DONE_RE = re.compile(
    r"\b(done|resolved|closed|fixed|shipped|completed|complete|erledigt|abgeschlossen|geschlossen|gel[oö]st)\b",
    re.IGNORECASE,
)
_OP_REOPEN_RE = re.compile(r"\b(reopened|reopen|regression|regressed|wieder\s+offen)\b", re.IGNORECASE)


@dataclass
class OpenPoint:
    """One `### ` thread parsed from a page's `## Open Points` section: its stable id, title,
    append-only dated bullets, and a status DERIVED from the latest bullet (never stored)."""

    page_rel: str
    point_id: str  # "op-..." slug, or "" when the id: line is missing (malformed)
    title: str
    bullets: list[tuple[str, str]]  # (YYYY-MM-DD, text) in document order
    status: str  # "done" | "open" — derived from the latest-dated bullet
    last_date: str  # the max bullet date, or "" when there is no dated bullet


def _op_derive_status(bullets: list[tuple[str, str]]) -> tuple[str, str]:
    """``(status, last_date)`` from the LATEST-dated bullet's text — one source of truth, no
    stored cursor. A reopen keyword forces open; else a done keyword closes it; else open."""
    if not bullets:
        return "open", ""
    date, text = max(bullets, key=lambda b: b[0])
    if _OP_REOPEN_RE.search(text):
        return "open", date
    if _OP_DONE_RE.search(text):
        return "done", date
    return "open", date


def parse_open_points(page: Page) -> list[OpenPoint]:
    """Extract every `### ` thread under a page's `## Open Points` section (code fences skipped).
    A thread is its heading title, an optional `id: op-<slug>` line, and append-only dated
    ``- YYYY-MM-DD: ...`` bullets. Returns ``[]`` for a page with no such section."""
    points: list[OpenPoint] = []
    in_section = False
    cur_title: str | None = None
    cur_id = ""
    cur_bullets: list[tuple[str, str]] = []

    def flush() -> None:
        nonlocal cur_title, cur_id, cur_bullets
        if cur_title is not None:
            status, last = _op_derive_status(cur_bullets)
            points.append(OpenPoint(page.rel_path, cur_id, cur_title, cur_bullets, status, last))
        cur_title, cur_id, cur_bullets = None, "", []

    for line, in_code in grammar.iter_lines(page.body):
        if in_code:
            continue
        stripped = line.strip()
        if stripped.startswith("### "):
            # An H3 thread heading (only meaningful inside the section).
            if in_section:
                flush()
                cur_title = stripped[4:].strip()
            continue
        if stripped.startswith("## "):
            # An H2 boundary: enter the Open-Points section, or leave it for any other H2.
            flush()
            in_section = stripped[3:].strip().lower() in _OP_SECTION_TITLES
            continue
        if not in_section or cur_title is None:
            continue
        m_id = _OP_ID_RE.match(stripped)
        if m_id and not cur_bullets:
            # Normalize to lowercase: ids follow the (lowercase) slugify rule, so a stray `OP-Foo`
            # must still match `op-foo` in the duplicate check and render consistently in the catalog.
            cur_id = m_id.group(1).lower()
            continue
        m_bullet = _OP_BULLET_RE.match(stripped)
        if m_bullet:
            cur_bullets.append((m_bullet.group(1), m_bullet.group(2).strip()))
    flush()
    return points


def collect_open_points(pages: list[Page]) -> list[OpenPoint]:
    """Every open-point thread across all pages, in page rel_path then document order."""
    out: list[OpenPoint] = []
    for page in sorted(pages, key=lambda p: p.rel_path):
        out.extend(parse_open_points(page))
    return out
