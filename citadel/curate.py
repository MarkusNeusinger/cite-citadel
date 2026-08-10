"""``citadel curate`` — the second wiki lifecycle: re-verify, re-sort, split, and re-ground EXISTING
pages against a recomputed findings checklist, never ingesting anything
new.

Two layers, the Wikipedia-bot model, with **no persisted queue** — the wiki IS the database:

1. **Offline detectors** (this module, pure and offline): :func:`build_plan` recomputes the work
   list from the loaded wiki + the manifest at the START of every run (a persisted queue would be a
   second source of truth with staleness bugs). Each detector reuses :mod:`citadel.grammar` /
   :mod:`citadel.store` / :mod:`citadel.okf` — no new citation/link regexes. The reason codes:
   ``rules_version_drift`` (a page whose source was ingested under an older effective-rules hash),
   ``page_length_hard`` (over :data:`config.CURATE_PAGE_HARD_LINES` — lint only warns at the soft
   one), ``contradiction`` (an unresolved ``> [!CONTRADICTION]`` callout), ``orphan`` (an island),
   ``llm_drift`` (a page dominated by ``[^llm]`` facts with little ``[^sN]`` grounding),
   ``resort`` (a page whose ``type`` routes to a different folder than the one it sits in, via
   :func:`okf.folder_for_type`), ``operator_guidance`` (not a detection at all: the pages a human
   NAMED on the command line under a ``curate --guidance "…"`` steer — the one reason code a person
   supplies, so a structural ask lands even on pages every detector considers clean),
   ``bad_source`` (a ``[^sN]`` citation that does not verify —
   lint's "Fabricated/missing sources", e.g. the dangling citations a FAILED deletion cleanup
   leaves behind, via :func:`validate.source_issues`), and ``reverify`` (a sampled fact
   re-verification pass). Fact
   re-verification is pre-filtered offline through the manifest shas (:func:`reverify_candidates`):
   a CHANGED source is reconcile's job, a GONE source is delete's job — only sha-unchanged sources
   need the agent's entailment pass, and :func:`build_plan` samples just :data:`REVERIFY_SAMPLE_K`
   of the citing pages per run (the stalest × most-linked), so re-verification rolls over the
   corpus without a per-run token blow-up.

2. **Agent layer** (:func:`curate`): one staged session per page CLUSTER (the anchor page + its
   cited raw files + direct link neighbors), built on ingest's EXISTING all-or-nothing staging
   machinery (:func:`ingest._run_agent_sessions`). The cluster's findings are written to a temp file
   referenced BY PATH in the prompt (``tasks/curate.md`` + the paths-only frame). **The staging
   diff-by-hash is the single result arbiter**: an empty diff is a NOOP, a clean promoted diff is
   applied, an exception / failed ``citadel check`` is a failure — no machine tokens, no second
   result channel. A failed cluster lands in the failures catalog keyed by the PAGE rel_path with an
   additive ``attempts`` counter; it is never auto-retried and is skipped once ``attempts`` reaches
   :data:`ATTEMPT_CAP`. One edit-summary line per applied cluster goes into ``log.md``; ``--diff``
   writes a change report. Deterministic fixes (index rebuild) are applied directly by this layer,
   not queued.

The single LLM seam stays :func:`llm.run_ingest_session` (``kind="curate"``); curate sessions run
under :data:`config.CURATE_MODEL` (falling back to the ingest model).
"""

from __future__ import annotations

import contextlib
import difflib
import fnmatch
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import config, failures, grammar, ingest, lint, llm, manifest, okf, pagecache, runlock, store, validate, wikigit
from .okf import Page


# --- reason codes + ordering ----------------------------------------------------------------

REASON_OPERATOR = "operator_guidance"
REASON_PAGE_LENGTH = "page_length_hard"
REASON_RESORT = "resort"
REASON_BAD_SOURCE = "bad_source"
REASON_CONTRADICTION = "contradiction"
REASON_RULES_DRIFT = "rules_version_drift"
REASON_LLM_DRIFT = "llm_drift"
REASON_LOCATOR = "locator"
REASON_REVERIFY = "reverify"
REASON_ORPHAN = "orphan"

# Deterministic cluster ordering for --limit: what the HUMAN explicitly asked for first (a
# `--guidance` steer on named pages is an instruction, not a detection), then the structural fixes
# that change a page's identity/shape (split, re-sort), then the provenance repairs (a dangling
# citation is a lint FAIL — e.g. what a failed deletion cleanup leaves behind, which ingest's
# failure hint sends HERE to fix), then the contradiction/grounding repairs, then the advisory
# linking pass. A cluster's priority is the rank of its MOST urgent reason; ties break on the page
# rel_path.
_REASON_ORDER = [
    REASON_OPERATOR,
    REASON_PAGE_LENGTH,
    REASON_RESORT,
    REASON_BAD_SOURCE,
    REASON_CONTRADICTION,
    REASON_RULES_DRIFT,
    REASON_LLM_DRIFT,
    REASON_LOCATOR,
    REASON_REVERIFY,
    REASON_ORPHAN,
]

# How many times a failing curate cluster is attempted before it is skipped (never auto-retried).
# The failures-catalog ``attempts`` counter increments per run; once it reaches this cap the cluster
# is left alone until an explicit retry (``curate(force=True)`` / the CLI's ``citadel curate --retry``).
ATTEMPT_CAP = 2

# How many pages the rolling fact re-verification samples PER RUN. Kept
# small and deterministic: each run re-checks the K stalest, most-linked sha-unchanged-cited pages,
# so a large corpus re-verifies over many runs without a per-run token blow-up.
REVERIFY_SAMPLE_K = 3

# The `[^sN]`-drift outlier rule: a page counts as drifted when its model-supplied (``[^llm]``)
# facts both outnumber its raw-grounded (``[^sN]``) facts AND reach this floor (so a single stray
# ``[^llm]`` note on a well-cited page is not flagged).
_LLM_DRIFT_MIN = 2


def _detail_line(detail: str, limit: int = 240) -> str:
    """One console-safe line out of a recorded failure detail: whitespace/newlines collapsed,
    clipped at ``limit`` chars — a validation error can quote page content, and the report is a
    summary, not the catalog."""
    flat = " ".join(str(detail).split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."


# --- the plan -------------------------------------------------------------------------------


@dataclass
class PlanItem:
    """One page CLUSTER planned for a curate pass — the anchor page and the concrete reason codes
    the offline detectors flagged it under. Ordering for ``--limit`` is computed from the reasons
    at sort time (:func:`_priority`), never stored."""

    page: str  # the cluster anchor page rel_path
    reasons: list[str] = field(default_factory=list)  # reason codes, deduped + sorted


@dataclass
class Plan:
    """The recomputed-per-run curate work list: an ordered list of page-cluster :class:`PlanItem`s
    plus ``skipped`` — the anchor pages an attempt-capped failure record drops from the runnable
    plan (surfaced, but not re-run this pass). There is NO persisted queue: this is rebuilt from the
    detectors on every run, so ``--dry-run``/``--limit`` reflect exactly what would actually run."""

    items: list[PlanItem] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    def render(self) -> str:
        # Only the RUNNABLE items are listed here; attempt-capped clusters are surfaced by the
        # CurateReport's own "Skipped" section (they are in self.skipped), so no double-listing.
        if not self.items:
            if self.skipped:
                return "No runnable curate work (only attempt-capped clusters remain)."
            return "No curate work: every page is clean."
        lines = [f"Curate plan ({len(self.items)} cluster(s)):"]
        for item in self.items:
            lines.append(f"  - {item.page} [{', '.join(item.reasons)}]")
        return "\n".join(lines)


@dataclass
class CurateReport:
    """The outcome of a curate run — the recomputed plan plus, keyed by anchor page, which clusters
    the staging diff arbitrated as applied / NOOP / failed, and which were skipped (attempt-capped)."""

    plan: Plan
    applied: list[str] = field(default_factory=list)
    noop: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    # WHY each failed cluster failed, keyed by anchor page — the same detail the failures catalog
    # records, surfaced in render() so "Failed (rolled back): N" is never a dead end the user has
    # to go read wiki/.citadel_failures.json to explain.
    failed_details: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    # Path arguments that named no page (a typo, a folder with no pages, a glob that matched
    # nothing). Surfaced instead of dropped: under a `--guidance` steer a mistyped path would
    # otherwise read as "the wiki is clean", and the run the human asked for silently never ran.
    unmatched: list[str] = field(default_factory=list)
    # The wiki-history note from wikigit.autocommit — empty when the history layer had nothing to say.
    wiki_git: str = ""
    # What this run's cluster sessions cost, summed over every session that reported usage —
    # NOOP and failed clusters included (their sessions were paid for too). None when no
    # backend reported anything.
    usage: llm.SessionUsage | None = None

    def render(self) -> str:
        lines = ["Curate report", "=============", ""]
        if self.unmatched:
            lines.append(f"Matched no page (nothing was curated for these): {', '.join(self.unmatched)}")
            lines.append("")
        lines.append(self.plan.render())
        lines.append("")
        for label, group in (
            ("Applied", self.applied),
            ("NOOP (findings did not hold)", self.noop),
            ("Failed (rolled back)", self.failed),
            ("Skipped (attempt-capped)", self.skipped),
        ):
            lines.append(f"{label}: {len(group)}")
            for page in group:
                lines.append(f"  - {page}")
                detail = self.failed_details.get(page, "") if group is self.failed else ""
                if detail:
                    lines.append(f"      {_detail_line(detail)}")
        if self.failed:
            lines.append("")
            lines.append(
                "Failure reasons are also recorded in the failures catalog beside the wiki; "
                "a cluster that keeps failing is skipped after "
                f"{ATTEMPT_CAP} attempts until `citadel curate --retry`."
            )
        described = self.usage.describe() if self.usage is not None else ""
        if described:
            lines.append("")
            lines.append(f"LLM usage: {described}.")
        if self.wiki_git:
            lines.append("")
            lines.append(self.wiki_git)
        return "\n".join(lines)


# --- offline detectors ----------------------------------------------------------------------


def _stale_source_keys(manifest_dict: dict, current_rules_version: str) -> set[str]:
    """Tracked FILE source keys whose recorded ``rules_version`` differs from the current one — the
    sources whose citing pages a ``--stale-rules`` curate re-runs. Repo entries (versioned by commit)
    and entries with no recorded rules_version (pre-rules-split / model-less) are excluded."""
    stale: set[str] = set()
    for key, entry in manifest_dict.items():
        if manifest.is_repo_entry(entry):
            continue
        recorded = manifest.entry_rules_version(entry)
        if recorded is not None and recorded != current_rules_version:
            stale.add(key)
    return stale


def _in_degree(pages: list[Page]) -> dict[str, int]:
    """``{rel_path: number of pages that link TO it}`` — the in-degree map the reverify sampler
    weights staleness by. Reuses the shared wiki-link grammar (source citations don't count)."""
    indeg: dict[str, int] = {}
    for page in pages:
        for _raw, resolved in grammar.resolved_md_links(page.rel_path, page.body):
            indeg[resolved] = indeg.get(resolved, 0) + 1
    return indeg


def _staleness_seconds(page: Page, now: datetime) -> float:
    """How old the page's ``timestamp`` is in seconds (>= 0), or 0.0 when it is missing/unparseable
    — the staleness axis of the reverify sampler's ``staleness × in-degree`` weight."""
    ts = page.frontmatter.get("timestamp")
    if not isinstance(ts, str) or not ts:
        return 0.0
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return max(0.0, (now - dt).total_seconds())


def _reverify_sample(citing_pages: set[str], pages: list[Page]) -> list[str]:
    """The up-to-:data:`REVERIFY_SAMPLE_K` citing pages to re-verify this run, ranked by
    ``staleness × (in-degree + 1)`` so the stalest, most-linked pages are re-checked first while a
    stale island (in-degree 0) is never fully discounted. Deterministic:
    ties break on rel_path."""
    if not citing_pages:
        return []
    indeg = _in_degree(pages)
    now = datetime.now(timezone.utc)
    by_path = {p.rel_path: p for p in pages}

    def weight(rel_path: str) -> float:
        page = by_path.get(rel_path)
        return _staleness_seconds(page, now) * (indeg.get(rel_path, 0) + 1) if page is not None else 0.0

    ranked = sorted(citing_pages, key=lambda rel: (-weight(rel), rel))
    return ranked[:REVERIFY_SAMPLE_K]


def _page_line_count(page: Page) -> int:
    """The page's length in BODY lines — what the soft/hard page-length thresholds are measured in."""
    return len(page.body.splitlines())


def _has_unresolved_contradiction(body: str) -> bool:
    """True when the body carries a ``> [!CONTRADICTION]`` callout with NO resolution — i.e. a
    contradiction still awaiting a confident, labeled resolution line (``schema.md § Contradictions``:
    ``> Resolution: … [^llmN]``). A callout that already carries a ``Resolution`` line or an
    ``[^llm]`` marker is considered handled and is NOT re-planned."""
    lines = body.splitlines()
    i, n = 0, len(lines)
    while i < n:
        if grammar.CONTRADICTION_LINE_RE.match(lines[i]):
            block: list[str] = []
            j = i
            while j < n and lines[j].lstrip().startswith(">"):
                block.append(lines[j])
                j += 1
            block_text = "\n".join(block)
            resolved = "resolution" in block_text.lower() or grammar.LLM_MARKER_RE.search(block_text) is not None
            if not resolved:
                return True
            i = j
        else:
            i += 1
    return False


def _is_llm_drift(page: Page) -> bool:
    """True when the page is a per-page ``[^llm]``:``[^sN]`` drift outlier — model-supplied facts
    outnumber raw-grounded ones and reach :data:`_LLM_DRIFT_MIN`. Counts USED markers on facts (not
    the ``## Sources`` definitions), fence- and Sources-aware via shared grammar."""
    llm_used = src_used = 0
    for line in grammar.prose_lines(page.body, skip_sources=True):
        for match in grammar.USED_MARKER_RE.finditer(line):
            if grammar.is_llm_marker(match.group(1)):
                llm_used += 1
            else:
                src_used += 1
    return llm_used >= _LLM_DRIFT_MIN and llm_used > src_used


def _is_type_folder_mismatch(page: Page) -> bool:
    """True when the page's ``type`` routes (via :func:`okf.folder_for_type`) to a different folder
    than the one it sits in — the owner's 'Information umsortieren' made concrete. A page with no
    ``type`` is left to lint/check (missing type is a structural gate failure, not a re-sort)."""
    type_ = (page.type or "").strip()
    if not type_:
        return False
    expected = okf.folder_for_type(type_)
    folder = page.rel_path.split("/", 1)[0] if "/" in page.rel_path else ""
    return folder != expected


def reverify_candidates() -> set[str]:
    """The tracked source keys whose facts need the agent's entailment re-verification pass — the
    stale-fact re-check, PRE-FILTERED offline through the manifest shas:

    - a source whose bytes CHANGED (manifest sha != on-disk sha) is reconcile's job, not curate's;
    - a source that is GONE from disk is delete's job;
    - only a sha-UNCHANGED tracked file source is a re-verify candidate (its wiki facts might have
      drifted from what the still-identical file says, which needs the agent, not an offline check).

    Repo sources (versioned by commit) and entries with no recorded sha are excluded. Pure/offline:
    reads the manifest and stat/hashes the named files, nothing else."""
    manifest_dict = manifest.load()
    candidates: set[str] = set()
    for key, entry in manifest_dict.items():
        if manifest.is_repo_entry(entry):
            continue
        recorded = manifest.entry_sha(entry)
        if not recorded:
            continue
        path = config.source_path_for_key(key)
        try:
            if path.is_file() and manifest.file_sha256(path) == recorded:
                candidates.add(key)
        except OSError:
            continue
    return candidates


def _priority(reasons: set[str]) -> int:
    """A cluster's ordering rank = the rank of its MOST urgent reason (lowest index in
    :data:`_REASON_ORDER`); an unknown reason sorts last."""
    ranks = [_REASON_ORDER.index(r) for r in reasons if r in _REASON_ORDER]
    return min(ranks) if ranks else len(_REASON_ORDER)


def build_plan(
    pages: list[Page] | None = None,
    *,
    stale_rules: bool = False,
    limit: int | None = None,
    failures_dict: dict | None = None,
    force: bool = False,
    scope: set[str] | None = None,
    guided: bool = False,
) -> Plan:
    """Recompute the curate work list from the wiki + manifest (NO persisted queue). Every detector
    is offline and reuses shared grammar/store/okf. One :class:`PlanItem` per flagged page,
    aggregating all its reason codes, ordered deterministically (:func:`_priority`, then rel_path).

    ``scope`` (the resolved page set of the CLI's optional path arguments) restricts the plan to
    those anchors — applied BEFORE ``limit``, so ``--limit N`` means "the first N of what I asked
    for" rather than "N of the whole wiki, then filtered to nothing".

    ``guided`` marks those scoped pages as an explicit operator ask (``curate --guidance TEXT
    <paths>``): each gets :data:`REASON_OPERATOR` on top of whatever the detectors found, so a page
    no detector flagged is still planned — the human, not a detector, is the finding. It needs a
    ``scope``: a steer with no paths merely rides along on the detector plan (every findings file
    carries it), because fanning one out over a whole clean wiki would be one paid session per page.

    ``stale_rules`` narrows the plan to pages whose source was ingested under an OLDER effective-rules
    hash (the ``--stale-rules`` selector) — a page carrying only other reasons is dropped, except an
    explicitly guided one (a named page is an instruction, not a detection). ``limit``
    keeps the first N clusters of that ordered plan (``--limit``).

    ``failures_dict`` (loaded when omitted) supplies the per-cluster attempt counts: a cluster at or
    past :data:`ATTEMPT_CAP` is DROPPED from the runnable ``items`` into ``Plan.skipped`` — so
    ``--dry-run``/``--limit`` reflect only what would actually run — unless ``force`` bypasses the
    cap (an explicit retry of stuck clusters)."""
    if pages is None:
        pages = store.load()
    manifest_dict = manifest.load()
    if failures_dict is None:
        failures_dict = failures.load()
    current_rules_version = config.rules_version()

    reasons_by_page: dict[str, set[str]] = {}

    def add(rel_path: str, reason: str) -> None:
        reasons_by_page.setdefault(rel_path, set()).add(reason)

    # rules_version drift + fact re-verification both need "which pages cite key X" for a whole
    # set of source keys — resolved in ONE fence-aware wiki traversal via the batch
    # store.citing_pages_map (the O(sources × pages) per-key find_raw_references loop this
    # replaces dominated build_plan on a large wiki, --dry-run included).
    stale_keys = _stale_source_keys(manifest_dict, current_rules_version)
    reverify_keys = reverify_candidates()
    citing = store.citing_pages_map(set(stale_keys) | reverify_keys, pages)
    for key in stale_keys:
        for rel_path in citing.get(key, []):
            add(rel_path, REASON_RULES_DRIFT)

    for rel_path in lint.orphans(pages):
        add(rel_path, REASON_ORPHAN)

    # locator drift: a `lines A-B`/`§ Heading` citation that no longer resolves against its
    # still-unchanged text source. Reuses lint's one deterministic verifier (no second parser).
    for rel_path, _detail in lint.check_locators(pages):
        add(rel_path, REASON_LOCATOR)

    # fact re-verification: every page citing a sha-UNCHANGED tracked source is a candidate
    # (a changed source is reconcile's job, a gone one delete's) — sample K of them by staleness ×
    # in-degree for the agent's entailment re-check of each [^sN] claim against its still-identical
    # source.
    reverify_citing: set[str] = set()
    for key in reverify_keys:
        reverify_citing.update(citing.get(key, []))
    for rel_path in _reverify_sample(reverify_citing, pages):
        add(rel_path, REASON_REVERIFY)

    for page in pages:
        rel_path = page.rel_path
        if _page_line_count(page) > config.CURATE_PAGE_HARD_LINES:
            add(rel_path, REASON_PAGE_LENGTH)
        if _has_unresolved_contradiction(page.body):
            add(rel_path, REASON_CONTRADICTION)
        if _is_llm_drift(page):
            add(rel_path, REASON_LLM_DRIFT)
        if _is_type_folder_mismatch(page):
            add(rel_path, REASON_RESORT)
        # bad_source: a [^sN] citation that does not verify — a definition linking a raw file
        # that does not exist (lint's "Fabricated/missing sources", a structural FAIL), a bare
        # definition, or an undefined marker. The most common cause is a FAILED deletion
        # cleanup's dangling citations, whose ingest failure hint names curate as the repair
        # tool — this detector is what makes that promise true. Reuses validate.source_issues,
        # the same predicate lint and `citadel check` run, so all three agree by construction.
        if validate.source_issues(rel_path, page.body):
            add(rel_path, REASON_BAD_SOURCE)

    # The operator ask: pages named on the command line under a `--guidance` steer are planned
    # whether or not a detector flagged them — the steer IS their finding, rendered into the
    # cluster's checklist by _render_findings. Only for pages that actually exist (a path that
    # matches nothing is reported by the caller, never silently invented into the plan).
    if guided and scope:
        known = {page.rel_path for page in pages}
        for rel_path in scope & known:
            add(rel_path, REASON_OPERATOR)

    items: list[PlanItem] = []
    skipped: list[str] = []
    for rel_path, reasons in reasons_by_page.items():
        if scope is not None and rel_path not in scope:
            continue
        if stale_rules and REASON_RULES_DRIFT not in reasons and REASON_OPERATOR not in reasons:
            continue
        if not force and _cluster_attempts(failures_dict, rel_path) >= ATTEMPT_CAP:
            skipped.append(rel_path)
            continue
        items.append(PlanItem(page=rel_path, reasons=sorted(reasons)))
    items.sort(key=lambda item: (_priority(set(item.reasons)), item.page))
    skipped.sort()
    if limit is not None:
        items = items[:limit]
    return Plan(items=items, skipped=skipped)


# --- the agent layer (staged cluster sessions) ----------------------------------------------


@contextlib.contextmanager
def _curate_model_active():
    """Point ``config.INGEST_MODEL`` at the curate model (``CITADEL_CURATE_MODEL`` falling back to
    the ingest model) for the duration of the cluster sessions, so :func:`llm.run_ingest_session`
    (the single seam, which reads ``config.INGEST_MODEL`` at call time for the claude ``--model``
    flag and the recorded label) runs curate on the cheaper model. Restored on exit — mirrors how
    the CLI flips ``config.LLM_VERBOSE``/``LLM_LOG_DIR``."""
    curate_model = (config.CURATE_MODEL or config.INGEST_MODEL or "").strip()
    original = config.INGEST_MODEL
    config.INGEST_MODEL = curate_model
    try:
        yield
    finally:
        config.INGEST_MODEL = original


def _cited_source_keys(page: Page) -> list[str]:
    """The raw source keys the anchor page cites — its ``resource`` frontmatter plus every ``[^sN]``
    footnote-definition link resolved to a source key — for the findings 'cluster' section. Reuses
    the shared footnote/link grammar; deduped, order-preserving."""
    keys: list[str] = []
    seen: set[str] = set()

    def push(key: str) -> None:
        key = key.strip().replace("\\", "/")
        if key and key not in seen:
            seen.add(key)
            keys.append(key)

    push(str(page.frontmatter.get("resource") or ""))
    for _marker_id, rest in grammar.source_definitions(page.body):
        target = grammar.def_link_target(rest)
        if target is None or grammar.is_external(target):
            continue
        abs_path = grammar.link_abs(page.rel_path, target)
        if abs_path is not None:
            push(config.rel_or_abs_posix(Path(abs_path)))
    return keys


def _link_neighbors(page: Page, inbound: dict[str, list[str]]) -> list[str]:
    """The anchor's direct wiki-link neighbors (outbound targets + inbound backlinks) — the rest of
    the cluster the agent may touch. Deduped and sorted; excludes the anchor itself. ``inbound`` is
    the run's ONE precomputed ``store.inbound_map`` backlink graph — re-deriving it here per cluster
    re-parsed every page body once per PlanItem."""
    neighbors: set[str] = set()
    for _raw, resolved in grammar.resolved_md_links(page.rel_path, page.body):
        neighbors.add(resolved)
    neighbors.update(inbound.get(page.rel_path, ()))
    neighbors.discard(page.rel_path)
    return sorted(neighbors)


_REASON_GUIDANCE = {
    REASON_OPERATOR: (
        "The human running this pass asked for a specific change to this cluster — see the "
        "**Operator guidance for THIS run** section above and carry it out here where it applies. "
        "It is a STRUCTURAL "
        "steer: how pages are named, typed, routed, split, merged, and cross-linked. Re-read this "
        "cluster's cited raw sources first (a retitle follows the sources' own spelling, `core.md` "
        "§ Restructuring), and carry every fact across unchanged — same wording, same `[^sN]` "
        "marker, same `## Sources` definition. Where the steer does not fit this page, leave it "
        "untouched."
    ),
    REASON_PAGE_LENGTH: (
        "This page is over the hard length threshold. Split it along its topics into focused pages — "
        "every fact keeping its `[^sN]` marker AND its `## Sources` definition — then delete the "
        "original and repoint inbound links (see `core.md` § Restructuring)."
    ),
    REASON_RESORT: (
        "This page's `type` routes to a different folder than the one it sits in. Move it to the "
        "folder its `type` names (see `schema.md` § OKF types), carrying every citation."
    ),
    REASON_BAD_SOURCE: (
        "A `[^sN]` citation on this page does not verify: its `## Sources` definition links to a "
        "raw file that does not exist, or a marker/definition is malformed. If the raw file was "
        "renamed or moved, repoint the definition to where it lives now (check the cited raw "
        "folder first). If the source is genuinely gone, treat its facts exactly like a deleted "
        "source's (`tasks/delete.md`): drop a fact whose ONLY source it was — sentence, marker, "
        "and definition — keep a fact another `[^sN]` still grounds (removing only the dead "
        "marker + definition), and delete a page left with no cited source, repointing inbound "
        "links (`core.md` § Restructuring). Never invent a replacement source or fact."
    ),
    REASON_CONTRADICTION: (
        "This page carries a `> [!CONTRADICTION]` callout with no resolution. Add a labeled `[^llmN]` "
        "resolution line ONLY if you are highly confident which side is correct — never by dropping a "
        "side (see `schema.md` § Contradictions)."
    ),
    REASON_RULES_DRIFT: (
        "A source this page cites was ingested under an older rulebook. Re-check the page against the "
        "current rules and its still-unchanged raw source; fix drifted paraphrases, add nothing new."
    ),
    REASON_LLM_DRIFT: (
        "This page is dominated by model-supplied `[^llm]` facts with little `[^sN]` grounding. "
        "Re-ground each claim against its raw source where possible; never invent to fill a gap."
    ),
    REASON_LOCATOR: (
        "A `[^sN]` citation on this page has a locator (line range or `§ Heading`) that no longer "
        "matches its text source. Re-check each locator against the current raw file and fix it to "
        "the place the fact actually lives (see `schema.md` § Locators)."
    ),
    REASON_REVERIFY: (
        "Re-verify each `[^sN]` claim on this page against its still-unchanged raw source: read the "
        "cited file and confirm the paraphrase entails what it says. Correct any drifted wording to "
        "what the source actually states; add nothing new, and leave a claim that already holds "
        "untouched (a NOOP is correct)."
    ),
    REASON_ORPHAN: (
        "This page is an island (no inbound and no outbound wiki links). Add cross-links to and from "
        "genuinely related pages — only where a real relationship exists."
    ),
}

_REGISTRY_LENGTH_GUIDANCE = (
    "This Registry page is over the hard length threshold. Split it by entry range or subclass "
    "into sibling `Registry` pages, the original becoming a short hub page linking the parts — "
    "never a topic split, and never drop or compress entries: every row keeps its `[^sN]` marker "
    "AND its `## Sources` definition (see `genres/registry.md`)."
)


def _reason_guidance(reason: str, page: Page) -> str:
    """The per-reason instruction line for the findings checklist. A `Registry` page over the
    length threshold must split by entry range into sibling registries — the generic topic-split
    guidance would shred its rows across topic pages."""
    if reason == REASON_PAGE_LENGTH and (page.type or "").strip().lower() == "registry":
        return _REGISTRY_LENGTH_GUIDANCE
    return _REASON_GUIDANCE.get(reason, "Review and repair per the rules.")


_OPERATOR_GUIDANCE_FRAME = (
    "This steer comes from the human who started this curate run — it is part of the run "
    "instruction, not text from a source file, so following it is legitimate. It directs "
    "STRUCTURE: page names and titles, `type`/folder routing, splits, merges, section order, and "
    "cross-links. It can never change what the wiki SAYS: no fact is added, reworded away from "
    "what its source states, dropped, or re-attributed, and every fact keeps its `[^sN]` marker "
    "and its `## Sources` definition (`tasks/curate.md` § Hard invariants). Where it asks for "
    "something the rules or the cited sources do not support, follow the rules and the sources; "
    "where it does not fit this cluster, leave the pages untouched."
)


def _render_findings(item: PlanItem, page: Page, inbound: dict[str, list[str]]) -> str:
    """The per-cluster findings checklist the agent reads BY PATH (never embedded in the prompt).
    Names the anchor, its cited raw sources, its direct link neighbors, the run's operator guidance
    when one was given (``curate --guidance`` — curate's steer travels HERE rather than in the
    prompt frame, so the improve-or-NOOP rule reads it as a listed finding), and one concrete
    instruction per detected reason. The `tasks/curate.md` brief governs how to act on it."""
    cited = _cited_source_keys(page)
    neighbors = _link_neighbors(page, inbound)
    lines = [
        f"# Curate findings — {item.page}",
        "",
        "## Cluster",
        f"- Anchor page: {item.page}",
        f"- Cited raw sources: {', '.join(cited) if cited else '(none)'}",
        f"- Direct link neighbors: {', '.join(neighbors) if neighbors else '(none)'}",
        "",
    ]
    if config.CURATE_GUIDANCE:
        # The steer is QUOTED as a blockquote: it is one line by construction (whitespace is
        # collapsed at every entry point), so a `>` prefix is enough to keep whatever markdown a
        # human typed into it — a stray `##`, a list marker — from restructuring the checklist it
        # is quoted inside.
        steer = f"> {config.CURATE_GUIDANCE}"
        lines += ["## Operator guidance for THIS run", "", steer, "", _OPERATOR_GUIDANCE_FRAME, ""]
    lines.append("## Detected issues (act on each ONLY where it genuinely holds against the sources)")
    for reason in item.reasons:
        lines.append(f"- **{reason}** — {_reason_guidance(reason, page)}")
    lines += [
        "",
        "If the findings do not hold up against the pages and their cited raw files, make no edits "
        "and stop — a NOOP is a correct outcome.",
    ]
    return "\n".join(lines) + "\n"


def _write_findings(item: PlanItem, page: Page, inbound: dict[str, list[str]]) -> tuple[str, str]:
    """Materialize the cluster findings to a fresh temp ``.md`` for the agent to READ, returning
    ``(read_path, tmpdir)``; the caller removes ``tmpdir`` after the session. ``read_path`` is
    rendered through the same :func:`config.rel_or_abs_posix` discipline as every other prepared
    file, so ``llm._external_dirs`` grants its (out-of-workspace) temp dir to the CLI."""
    tmpdir = tempfile.mkdtemp(prefix="okf_curate_")
    out = Path(tmpdir) / "findings.md"
    try:
        out.write_text(_render_findings(item, page, inbound), encoding="utf-8")
    except OSError:
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    return config.rel_or_abs_posix(out), tmpdir


def _cluster_attempts(failures_dict: dict, page: str) -> int:
    """The recorded curate attempt count for a cluster's anchor page (0 when never failed)."""
    entry = failures_dict.get(page)
    return int(entry.get("attempts", 0)) if isinstance(entry, dict) else 0


def _record_cluster_failure(failures_dict: dict, page: str, outcome, model: str) -> str:
    """Persist a failed curate cluster in the failures catalog keyed by the PAGE rel_path, with an
    ADDITIVE ``attempts`` counter (increment-per-run). Never auto-retried; capped by
    :data:`ATTEMPT_CAP`. Returns the recorded detail so the run report can surface the SAME
    reason it persisted."""
    attempts = _cluster_attempts(failures_dict, page) + 1
    detail = outcome.errors[0] if outcome.errors else f"{page}: curate session failed"
    failures.record(failures_dict, page, failures.CURATE, detail, model)
    failures_dict[page]["attempts"] = attempts
    return detail


def _page_text(rel_path: str) -> str | None:
    """The on-disk text of one wiki page, or None when it cannot be read — the raw bytes the
    ``--diff`` snapshots compare (no okf parse)."""
    try:
        return okf.safe_join(config.wiki_dir(), rel_path).read_text(encoding="utf-8")
    except (OSError, okf.OKFError):
        return None


def _texts_for(pages: list[Page]) -> dict[str, str]:
    """Before-snapshot: ``{rel_path: on-disk text}`` for each ALREADY-LOADED page — reuses the run's
    ``store.load()`` list instead of parsing every page a second time just to re-read its bytes."""
    return {page.rel_path: text for page in pages if (text := _page_text(page.rel_path)) is not None}


def _texts_on_disk() -> dict[str, str]:
    """After-snapshot: ``{rel_path: on-disk text}`` from a plain ``.md`` file walk of the wiki (no
    okf parse) — curate may have added or deleted pages, so the set is re-discovered, but reuses
    ``store``'s 'what is a page' rule (index/log/sources-catalog/dotfiles skipped) so the diff
    ignores generated files."""
    out: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(config.wiki_dir()):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".md") or store.is_skipped_name(name):
                continue
            rel_path = os.path.relpath(os.path.join(dirpath, name), config.wiki_dir()).replace(os.sep, "/")
            text = _page_text(rel_path)
            if text is not None:
                out[rel_path] = text
    return out


def _write_diff_report(diff_path: str, before: dict[str, str], after: dict[str, str], report: CurateReport) -> None:
    """Write the ``--diff`` change report: a per-page unified diff over the before/after content
    snapshots (the idiolect steal). Reuses stdlib ``difflib``; a run that changed nothing says so."""
    lines = [
        "# Curate change report",
        "",
        f"Applied: {len(report.applied)}  NOOP: {len(report.noop)}  "
        f"Failed: {len(report.failed)}  Skipped: {len(report.skipped)}",
        "",
    ]
    any_change = False
    for rel_path in sorted(set(before) | set(after)):
        old, new = before.get(rel_path, ""), after.get(rel_path, "")
        if old == new:
            continue
        any_change = True
        lines += [f"## {rel_path}", "", "```diff"]
        lines += list(
            difflib.unified_diff(
                old.splitlines(), new.splitlines(), fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}", lineterm=""
            )
        )
        lines += ["```", ""]
    if not any_change:
        lines.append("_No page content changed._")
    Path(diff_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _select_pages(pages: list[Page], paths: list[str] | None) -> tuple[set[str] | None, list[str]]:
    """Normalize an optional ``paths`` scope to ``(the page rel_paths it names, the arguments that
    matched nothing)`` — ``(None, [])`` for the whole wiki. Each argument may be:

    - one page — a rel_path (``concepts/x.md``) or an absolute/OS path under the wiki;
    - a FOLDER — ``registries`` / ``registries/`` / an absolute wiki subdirectory: every page under
      it (recursively);
    - a GLOB over rel_paths — ``registries/machine-*.md``, ``**/fault*.md``.

    Folders and globs exist for the guided pass (``curate --guidance "…" registries/``): the pages a
    naming/structure steer applies to are usually a folder or a family, and naming each one by hand
    is exactly the work the steer is meant to save. Unmatched arguments are RETURNED, not dropped —
    a typo'd path under a steer would otherwise silently produce a clean "nothing to do" run."""
    if not paths:
        return None, []
    wiki_root = config.wiki_dir().resolve()
    known = {p.rel_path for p in pages}
    wanted: set[str] = set()
    unmatched: list[str] = []
    for arg in paths:
        rel = arg.replace("\\", "/")
        with contextlib.suppress(OSError, ValueError):
            resolved = Path(arg).resolve()
            if resolved.is_relative_to(wiki_root):
                rel = resolved.relative_to(wiki_root).as_posix() if resolved != wiki_root else ""
        rel = rel.strip("/")
        if rel in known:
            wanted.add(rel)
            continue
        # A folder prefix ("" = the whole wiki, for an explicit path to the wiki root itself), then
        # a glob. Both are matched against the loaded rel_paths, never the filesystem, so a page
        # store skips (index.md, dotfiles) can never be selected.
        prefix = f"{rel}/" if rel else ""  # "" only for the wiki root itself: every page is under it
        under = {rel_path for rel_path in known if rel_path.startswith(prefix)}
        if not under and any(ch in rel for ch in "*?["):
            under = {rel_path for rel_path in known if fnmatch.fnmatch(rel_path, rel)}
        if under:
            wanted |= under
        else:
            unmatched.append(arg)
    return wanted, unmatched


@pagecache.bypass
def curate(
    paths: list[str] | None = None,
    *,
    progress=None,
    dry_run: bool = False,
    limit: int | None = None,
    stale_rules: bool = False,
    diff: str | None = None,
    force: bool = False,
) -> CurateReport:
    """Run one curate pass. Recompute the plan (:func:`build_plan`), then — unless ``dry_run`` —
    run ONE staged agent session per planned cluster and let the staging diff arbitrate the outcome.

    - ``dry_run``: print/return the recomputed plan and run ZERO agent sessions, leaving the wiki
      byte-for-byte untouched (the wiki IS the database — nothing to persist).
    - ``limit`` / ``stale_rules``: passed to :func:`build_plan` (cap the plan / narrow it to
      stale-rules pages).
    - ``paths``: restrict the plan to the pages they name — a rel_path, a wiki-relative file path,
      a FOLDER, or a glob (:func:`_select_pages`); applied before ``limit``. Under a
      ``config.CURATE_GUIDANCE`` steer they are also the operator ask itself: each named page is
      planned even when no detector flagged it (:data:`REASON_OPERATOR`), and the steer is rendered
      into every cluster's findings file. A steer with NO paths only rides along on the detector
      plan — one paid session per page of a clean wiki is never implied.
    - ``diff``: write a per-page change report to this path (:func:`_write_diff_report`).
    - ``force``: bypass the per-cluster attempt cap (an explicit retry of stuck clusters).

    Each cluster's findings are written to a temp file referenced BY PATH; the session runs through
    ingest's all-or-nothing staging machinery (:func:`ingest._run_agent_sessions`). An empty staging
    diff is a NOOP, a clean promoted diff is applied (one ``log.md`` edit-summary line), and a failed
    ``citadel check`` / exception rolls the whole cluster back (revert-and-stop) and records an
    attempt-capped failure. Deterministic fixes (index rebuild) run once at the end when anything was
    applied. ``progress`` is an optional ``progress(event, data)`` callback; a failing callback never
    breaks the run."""

    def emit(event: str, **data) -> None:
        if progress is not None:
            with contextlib.suppress(Exception):
                progress(event, data)

    pages = store.load()
    failures_dict = failures.load()
    scope, unmatched = _select_pages(pages, paths)
    # build_plan already applies the scope, the operator ask and the attempt cap: capped clusters
    # land in plan.skipped, not items, so plan.items is exactly what will run (nothing to re-check
    # in the loop), and --limit counts the SCOPED plan.
    plan = build_plan(
        pages,
        stale_rules=stale_rules,
        limit=limit,
        failures_dict=failures_dict,
        force=force,
        scope=scope,
        guided=bool(config.CURATE_GUIDANCE),
    )

    report = CurateReport(plan=plan)
    report.skipped = list(plan.skipped)
    report.unmatched = unmatched
    if dry_run:
        emit("plan", clusters=len(plan.items))
        return report

    # ONE mutating run per workspace, shared with ingest: the staging machinery, promote, and the
    # failures save are all destructive under concurrency (see runlock's module docstring). The
    # dry-run path above stays lock-free — it is read-only by contract.
    with runlock.hold("curate"):
        ingest._sweep_stale_staging(config.wiki_dir())
        pages_by_path = {p.rel_path: p for p in pages}
        # One backlink-graph pass for the whole run; every cluster's findings slice it.
        inbound = store.inbound_map(pages)
        before_map = _texts_for(pages) if diff else {}
        emit("start", clusters=len(plan.items))
        for page_rel in plan.skipped:
            emit("cluster_skipped", page=page_rel)

        with _curate_model_active():
            model = config.ingest_model_label()
            for index, item in enumerate(plan.items, 1):
                runlock.heartbeat()
                page_rel = item.page
                page = pages_by_path.get(page_rel)
                if page is None:  # vanished since the plan was computed (nothing to curate)
                    continue
                emit("cluster_start", index=index, total=len(plan.items), page=page_rel)
                read_path, tmpdir = _write_findings(item, page, inbound)
                try:
                    session = [
                        lambda pr=page_rel, rp=read_path: llm.run_ingest_session(pr, kind="curate", read_path=rp)
                    ]
                    outcome = ingest._run_agent_sessions(session, page_rel)
                finally:
                    shutil.rmtree(tmpdir, ignore_errors=True)

                # The run total counts every cluster's sessions — a rolled-back or NOOP cluster
                # spent its session too.
                report.usage = llm.combine_usage([report.usage, outcome.usage])
                if not outcome.ok:
                    report.failed.append(page_rel)
                    report.failed_details[page_rel] = _record_cluster_failure(failures_dict, page_rel, outcome, model)
                    emit("cluster_failed", index=index, total=len(plan.items), page=page_rel)
                    continue

                # A clean session: clear any prior stuck record. The staging diff is the sole arbiter of
                # applied vs NOOP — a non-empty promoted diff is a real edit, an empty one is a NOOP.
                failures.clear(failures_dict, page_rel)
                if outcome.created or outcome.updated or outcome.deleted:
                    report.applied.append(page_rel)
                    store.append_log(
                        f"curate {page_rel}: {len(outcome.created)} created, {len(outcome.updated)} updated, "
                        f"{len(outcome.deleted)} deleted (model: {model})"
                    )
                    emit("cluster_applied", index=index, total=len(plan.items), page=page_rel)
                else:
                    report.noop.append(page_rel)
                    emit("cluster_noop", index=index, total=len(plan.items), page=page_rel)

        # Persist the failures catalog (attempt counters / cleared records) regardless of outcome, then —
        # only when the wiki actually changed — apply the deterministic index rebuild (the offline fix).
        failures.save(failures_dict)
        if report.applied:
            store.rebuild_indexes()
            # One wiki-history commit for the whole run, after the log/index writes so it captures the
            # complete state. Best-effort by contract — a git problem is a report note, never a failure.
            report.wiki_git = (
                wikigit.autocommit(f"citadel curate: {len(report.applied)} cluster(s) applied (model: {model})") or ""
            )

        if diff:
            _write_diff_report(diff, before_map, _texts_on_disk(), report)

    emit("done", applied=len(report.applied), noop=len(report.noop), failed=len(report.failed))
    return report
