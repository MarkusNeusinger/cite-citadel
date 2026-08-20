"""``citadel status`` — a read-only snapshot of the corpus state.

One command answering "what state is my corpus in?": per raw source, which lifecycle bucket it
sits in —

- **ingested** — folded into the wiki (with the importing model + the rules-tree hash it ran
  under, a ``(stale)`` flag when that hash predates the current rulebook — the ``curate
  --stale-rules`` signal — and the ``checked`` date a model last verified it, the ``citadel
  refresh`` ordering; a ``NO PAGES`` marker calls out a source that NO wiki page cites — it was
  ingested but produced zero entries, the ``citadel ingest --retry`` signal);
- **failed** — unreadable / errored / timed-out, with the coarse reason and, for a stuck curate-
  style record, its attempt count;
- **skipped-duplicate** — a same-basename twin skipped in favor of another format;
- **ignored** — an OS/junk file matched by ``CITADEL_IGNORE_PATTERNS``;
- **oversized** — on disk under a raw root but past the ``CITADEL_MAX_SOURCE_BYTES`` ceiling, so
  discovery skips it (never hashed, never tracked);
- **not included** — on disk under a raw root but outside the ``CITADEL_INCLUDE_PATTERNS``
  allowlist ("read only ``.pdf``/``.txt``"), shown only when such an allowlist is configured;
- **pending** — on disk under a raw root, not yet in the manifest or the failures catalog.

Built from the manifest + the failures catalog + ONE stat-only discovery walk (reusing ingest's
own walk so repo sources, multi-root layouts, and dead mounts behave identically) + one wiki
traversal for the ``NO PAGES`` markers. It NEVER re-hashes a byte — that is ingest's job — so it
is cheap to run any time. The manifest/failures
files ARE the database; status only reads them. Read-only and defensive: a broken walk degrades to
empty pending/ignored rather than raising.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config, failures, ingest, llm, manifest, store


# How much of a (long) content hash / rules-version / commit id to show in the table.
_ID_WIDTH = 12

# How many allowlist-filtered keys the table lists before collapsing the rest into a count (the
# excluded side of an allowlist is normally the big half of the tree — see ingest's twin).
_NOT_INCLUDED_SHOWN = 10


def _format_duration(seconds: float) -> str:
    """Wall-clock seconds as a compact ASCII duration for the table: ``42s`` / ``4m 32s`` /
    ``5h 46m`` (the viewer's ``fmtDuration`` twin — keep the two in step)."""
    if seconds < 60:
        return f"{round(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {round(seconds % 60)}s"
    return f"{int(seconds // 3600)}h {round(seconds % 3600 // 60)}m"


@dataclass
class SourceState:
    """One raw source's lifecycle row. Which BUCKET a row lands in on :class:`StatusReport` IS its
    state — there is no separate stamped field. ``model``/``rules_version``/``commit`` describe an
    ingested source's provenance stamp; ``reason``/``detail``/``attempts`` describe a failed or
    skipped one."""

    key: str
    model: str | None = None
    rules_version: str | None = None
    commit: str | None = None
    stale_rules: bool = False
    ingested_at: str | None = None
    reason: str | None = None
    detail: str | None = None
    attempts: int = 0
    # What the last verifying session(s) cost, per the manifest's usage stamp — None when the
    # backend reported nothing (pre-cost-accounting entries). copilot quotes no dollars itself,
    # so its spend arrives as `aic` — AI credits, its own billing unit — and `cost_usd` is that
    # figure converted at GitHub's fixed published rate, which is what keeps a mixed-backend
    # corpus comparable in ONE total.
    cost_usd: float | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    aic: float | None = None
    # Citadel's own wall-clock measurement of the completing run's work on this source (the
    # manifest's `seconds` stamp) — on a local model, time is the cost, so it renders beside the
    # backend-reported figures. None for pre-duration-stamp entries.
    seconds: float | None = None
    # True for an INGESTED source that NO wiki page cites (the ``Referenced by`` column of
    # ``wiki/sources/index.md`` is empty for it): a session ran and was paid for, the source is
    # marked done, yet it contributed zero entries to the wiki. Rendered as a ``NO PAGES`` marker
    # and the `citadel ingest --retry` hint. Always False when the wiki could not be read (the
    # marker must never fire on a load error).
    uncited: bool = False


@dataclass
class StatusReport:
    """The per-source corpus state, split into its lifecycle buckets plus the current rules-tree
    hash (so the ``(stale)`` markers are self-explaining)."""

    ingested: list[SourceState] = field(default_factory=list)
    failed: list[SourceState] = field(default_factory=list)
    skipped_duplicate: list[SourceState] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    # (key, size_bytes) for files the CITADEL_MAX_SOURCE_BYTES ceiling keeps out of discovery.
    oversized: list[tuple[str, int]] = field(default_factory=list)
    # Keys the CITADEL_INCLUDE_PATTERNS allowlist keeps out of discovery ("read only .pdf/.txt").
    # Empty whenever no allowlist is configured, which is the default.
    not_included: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    rules_version: str = ""

    def render(self) -> str:
        """A plain-text, ASCII-only per-source table — one bucket per section, counts in the
        headings. Deterministic (every bucket is sorted by key)."""
        lines = ["Corpus status", "=============", ""]
        lines.append(f"Rules version: {self.rules_version[:_ID_WIDTH] or '(none)'}")
        costed = [s for s in self.ingested if s.cost_usd is not None]
        if costed:
            # The sum of each source's LAST verifying session — a maintenance-cost snapshot of
            # the current corpus, not lifetime spend (per-run spend is on each run's report).
            total = llm.format_cost(sum(s.cost_usd for s in costed))
            lines.append(f"Recorded LLM cost: {total} over {len(costed)} source(s) (last session each)")
        credited = [s for s in self.ingested if s.aic is not None]
        if credited:
            # copilot's own billing unit, shown beside the dollars it was converted into — the
            # same "last session each" snapshot as the cost line.
            total_aic = llm.format_aic(sum(s.aic for s in credited))
            lines.append(f"Recorded AI credits: {total_aic} AIC over {len(credited)} source(s) (last session each)")
        lines.append("")

        lines.append(f"Ingested ({len(self.ingested)})")
        for s in self.ingested:
            parts = [s.key]
            if s.model:
                parts.append(s.model)
            if s.commit:
                parts.append(f"commit {s.commit[:_ID_WIDTH]}")
            elif s.rules_version:
                tag = f"rules {s.rules_version[:_ID_WIDTH]}"
                if s.stale_rules:
                    tag += " (stale)"
                parts.append(tag)
            elif s.stale_rules:
                parts.append("rules (stale)")
            if s.ingested_at:
                # The date part is enough for "how long unchecked?" — `citadel refresh --dry-run`
                # shows the full queue ordering.
                parts.append(f"checked {s.ingested_at[:10]}")
            if s.cost_usd is not None:
                cost = llm.format_cost(s.cost_usd)
                # The credits are the figure copilot actually reported; the dollars are derived.
                parts.append(f"{cost} ({llm.format_aic(s.aic)} AIC)" if s.aic is not None else cost)
            elif s.aic is not None:
                # Stamped independently, so credits can outlive an unknown dollar figure — show
                # them rather than silently dropping spend the corpus total already counts.
                parts.append(f"{llm.format_aic(s.aic)} AIC")
            if s.seconds is not None:
                parts.append(_format_duration(s.seconds))
            if s.uncited:
                # Loud on purpose: "ingested" reads as success, but nothing in the wiki cites
                # this source — it produced zero entries.
                parts.append("NO PAGES (nothing cites this source)")
            lines.append("  " + "  ".join(parts))

        lines.append(f"Failed ({len(self.failed)})")
        for s in self.failed:
            row = f"  {s.key}  {s.reason}"
            if s.attempts:
                row += f"  attempts {s.attempts}"
            if s.detail:
                row += f"  {s.detail}"
            lines.append(row)

        lines.append(f"Skipped as duplicate ({len(self.skipped_duplicate)})")
        for s in self.skipped_duplicate:
            row = f"  {s.key}"
            if s.detail:
                row += f"  {s.detail}"
            lines.append(row)

        lines.append(f"Ignored ({len(self.ignored)})")
        for name in self.ignored:
            lines.append(f"  {name}")

        lines.append(f"Oversized ({len(self.oversized)})")
        for key, size in self.oversized:
            lines.append(f"  {key}  {ingest._human_bytes(size)}")

        # Only shown when an allowlist is configured: with none (the default) the bucket is empty
        # and a permanent "Not included (0)" row would be noise on every status call.
        if self.not_included:
            patterns = ", ".join(config.INCLUDE_PATTERNS) or "(none)"
            lines.append(f"Not included ({len(self.not_included)}) - CITADEL_INCLUDE_PATTERNS = {patterns}")
            for key in self.not_included[:_NOT_INCLUDED_SHOWN]:
                lines.append(f"  {key}")
            if len(self.not_included) > _NOT_INCLUDED_SHOWN:
                lines.append(f"  ... +{len(self.not_included) - _NOT_INCLUDED_SHOWN} more")

        lines.append(f"Pending ({len(self.pending)})")
        for key in self.pending:
            lines.append(f"  {key}")

        # The one-line call to action: everything stuck — failed sources and the NO PAGES ones —
        # is retryable with a single command, so say so instead of leaving the reader to collect
        # paths for `--force` by hand.
        uncited = sum(1 for s in self.ingested if s.uncited)
        if self.failed or uncited:
            bits = []
            if self.failed:
                bits.append(f"{len(self.failed)} failed source(s)")
            if uncited:
                bits.append(f"{uncited} NO PAGES source(s)")
            lines.append("")
            lines.append(f"Retry {' and '.join(bits)} with: citadel ingest --retry")

        return "\n".join(lines).rstrip() + "\n"

    def as_dict(self) -> dict:
        """The report as one JSON-ready dict (``citadel status --json``): the seven buckets plus
        ``rules_version``, ``cost_usd_total`` and ``aic_total``, each source row a plain dict with only its None fields dropped —
        ``attempts: 0`` / ``stale_rules: false`` / ``uncited: false`` stay explicit, so scripts
        get a predictable shape for 'which sources failed and why' (and which produced no pages)
        without scraping :meth:`render`'s table.
        ``oversized`` carries ``{"key", "size_bytes"}`` objects rather than bare strings, since the
        size is the reason the row exists."""

        def row(s: SourceState) -> dict:
            return {k: v for k, v in asdict(s).items() if v is not None}

        costed = [s.cost_usd for s in self.ingested if s.cost_usd is not None]
        credits = [s.aic for s in self.ingested if s.aic is not None]
        return {
            "rules_version": self.rules_version,
            # The render()'s "Recorded LLM cost" total, machine-readably: the sum of each
            # source's last-session cost stamp (null when no entry carries one).
            "cost_usd_total": round(sum(costed), 4) if costed else None,
            # The same snapshot in copilot's billing unit (null when no entry carries one).
            "aic_total": round(sum(credits), 6) if credits else None,
            "ingested": [row(s) for s in self.ingested],
            "failed": [row(s) for s in self.failed],
            "skipped_duplicate": [row(s) for s in self.skipped_duplicate],
            "ignored": list(self.ignored),
            "oversized": [{"key": key, "size_bytes": size} for key, size in self.oversized],
            # Always present (empty without an allowlist), so a script never has to branch on the
            # knob being configured; render() hides the empty case, JSON keeps the shape stable.
            "not_included": list(self.not_included),
            "pending": list(self.pending),
        }


def _is_stale_rules(entry, current_rules_version: str) -> bool:
    """True when an ingested source's recorded rules-tree hash predates the current one (an unknown
    /pre-rules-split stamp is not counted — it cannot be shown as stale honestly)."""
    recorded = manifest.entry_rules_version(entry)
    return recorded is not None and recorded != current_rules_version


def _walk_state() -> tuple[set[str], list[tuple[str, int]], list[str]]:
    """ONE stat-only discovery walk (ingest's own — no hashing, repo-aware, dead-mount-safe), read
    for the three things status needs from disk: every source key visible under the raw roots RIGHT
    NOW (files plus repo dirs), the ``(key, size)`` pairs the ``CITADEL_MAX_SOURCE_BYTES``
    ceiling kept out of it, and the keys the ``CITADEL_INCLUDE_PATTERNS`` allowlist kept out.
    Defensive: any walk failure degrades to empty (pending/oversized/not-included simply
    show nothing) rather than raising."""
    try:
        walk = ingest._discover_walk(None)
    except OSError:
        return set(), [], []
    keys = {manifest.rel_key(path) for path, _st in walk.files}
    keys |= {manifest.rel_key(path) for path in walk.repos}
    oversized = sorted((manifest.rel_key(path), size) for path, size in walk.oversized)
    not_included = sorted(manifest.rel_key(path) for path in walk.not_included)
    return keys, oversized, not_included


def _ignored_names() -> list[str]:
    """The OS/junk basenames under the raw roots that discovery skips (``CITADEL_IGNORE_PATTERNS``)
    — a light, stat-free ``os.walk`` that prunes ignored/hidden directories (and the wiki dir)
    exactly as discovery does, through discovery's OWN predicates
    (:func:`ingest._is_ignored_name` / :func:`ingest._is_wiki_internal`). Deduped + sorted; degrades
    to an empty list on any walk error."""
    found: set[str] = set()
    for root in config.source_roots():
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                kept = []
                for d in dirnames:
                    if d.startswith("."):
                        continue
                    if ingest._is_wiki_internal(Path(dirpath) / d):
                        continue  # generated output, not a source tree — never walked
                    if ingest._is_ignored_name(d):
                        found.add(d)
                    else:
                        kept.append(d)
                dirnames[:] = kept  # prune (don't descend into hidden/ignored dirs)
                for f in filenames:
                    if not f.startswith(".") and ingest._is_ignored_name(f):
                        found.add(f)
        except OSError:
            continue
    return sorted(found)


def build_status() -> StatusReport:
    """Compute the corpus state from the manifest + the failures catalog + one stat-only walk.
    Curate failure records (keyed by a PAGE rel_path, not a source) are excluded — this is a
    per-SOURCE view. Never re-hashes; read-only."""
    manifest_dict = manifest.load()
    failures_dict = failures.load()
    current = config.rules_version()
    report = StatusReport(rules_version=current)

    for key in sorted(manifest_dict):
        entry = manifest_dict[key]
        usage = manifest.entry_usage(entry)
        # One construction for both kinds: entry_commit is "" for a non-repo (file) source, so
        # `or None` leaves commit unset there and render falls back to the rules_version stamp.
        report.ingested.append(
            SourceState(
                key=key,
                model=manifest.entry_model(entry),
                commit=manifest.entry_commit(entry) or None,
                rules_version=manifest.entry_rules_version(entry),
                stale_rules=_is_stale_rules(entry, current),
                ingested_at=manifest.entry_ingested_at(entry),
                cost_usd=usage.get("cost_usd"),
                tokens_in=usage.get("tokens_in"),
                tokens_out=usage.get("tokens_out"),
                aic=usage.get("aic"),
                seconds=usage.get("seconds"),
            )
        )

    # Mark the ingested sources NO wiki page cites (the NO PAGES rows): one wiki traversal
    # (store.citing_pages_map — the exact verdict behind sources/index.md's "Referenced by"
    # column), best-effort like the walk: a wiki that cannot be read yields no markers rather
    # than a failed status.
    if report.ingested:
        try:
            refs = store.citing_pages_map([s.key for s in report.ingested])
        except Exception:  # noqa: BLE001 - status is read-only and must degrade, never raise
            refs = None
        if refs is not None:
            for row in report.ingested:
                row.uncited = not refs.get(row.key)

    for key in sorted(failures_dict):
        entry = failures_dict[key]
        if not isinstance(entry, dict):
            continue
        reason = str(entry.get("reason") or "")
        if reason == failures.CURATE:
            continue  # a curate cluster is a page, not a source — surfaced by `citadel curate`
        row = SourceState(
            key=key,
            model=entry.get("model"),
            reason=reason,
            detail=str(entry.get("detail") or "") or None,
            attempts=int(entry.get("attempts", 0) or 0),
        )
        # The bucket a row lands in IS its state: a same-basename `duplicate` is a skip, not a
        # failure; everything else is a genuine failure.
        if reason == failures.DUPLICATE:
            report.skipped_duplicate.append(row)
        else:
            report.failed.append(row)

    tracked = set(manifest_dict) | set(failures_dict)
    present, oversized, not_included = _walk_state()
    report.pending = sorted(key for key in present if key not in tracked)
    report.oversized = oversized
    report.not_included = not_included
    report.ignored = _ignored_names()
    return report
