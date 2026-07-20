"""``citadel refresh`` — budget-controlled re-verification of the least-recently-checked sources.

The third wiki lifecycle beside ingest (new/changed sources) and curate (improve existing PAGES):
refresh re-verifies existing SOURCES. The motivating scenario is a wiki that outlives its models —
a source imported a year ago by a weaker model, whose pages nobody has re-checked since. Rather
than ever regenerating the whole wiki after a model upgrade (unaffordable at corpus scale), you
spend a SELF-CHOSEN budget regularly — e.g. monthly, when the token allowance renews —
and refresh burns exactly that budget on the sources that need it most: the ones that have gone
longest unchecked.

Mechanically refresh plans, then delegates: it orders the manifest by the ``ingested_at``
last-checked stamp (oldest first; a pre-refresh entry with no stamp counts as oldest — it has
provably never been re-checked since the stamp existed) and hands the first ``--limit`` sources to
:func:`citadel.ingest.ingest` as a FORCED path-scoped run. Everything downstream is ingest's
existing, hardened machinery: each source runs one ``kind="reconcile"`` session (a repo a full
``repo-reconcile`` re-digest) against a staging copy, all-or-nothing, promoted only when clean,
and on success ``mark_done`` re-stamps the entry with the CURRENT model + rules_version + a fresh
``ingested_at`` — which is what rotates the source to the back of the queue, so repeated refresh
runs walk the whole corpus round-robin without any persisted queue (the manifest IS the queue
state; ``--dry-run`` shows the current head of it).

The budget unit is SOURCES, not tokens: citadel shells out to an agent CLI and never sees token
counts, but one source is exactly one agent session (a chunked large source: a few), so
``--limit N`` is an honest, predictable proxy — the same knob curate uses. ``--min-age-days``
makes a scheduled run self-limiting: sources checked more recently than that are not candidates
at all, so a cron'd ``citadel refresh --limit 20 --min-age-days 30`` becomes a cheap no-op once
the corpus is fresh instead of pointlessly re-burning budget on it.

Only sources a model actually imported are candidates (an unreadable binary that was merely seen
has nothing to re-verify — retrying those is ``ingest --force``'s job), and a source missing from
disk is never a candidate (deletion is the full ingest run's guarded sweep, not refresh's). Like
every mutating lifecycle, the delegated run holds the exclusive workspace run lock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from . import config, ingest, manifest


@dataclass
class RefreshCandidate:
    """One refreshable source: its manifest key, when a model last verified it (``ingested_at``,
    None = never re-stamped since the feature existed → treated as oldest), and the provenance it
    currently carries (which model imported it, whether under a now-stale rulebook)."""

    key: str
    ingested_at: str | None
    model: str | None
    stale_rules: bool


@dataclass
class RefreshReport:
    """What one refresh run planned and (unless ``--dry-run``) did. ``selected`` is the head of
    the oldest-first queue this run took on, ``candidates`` the full queue length it was cut
    from, ``eligible`` the re-verifiable sources BEFORE the age floor (so an empty queue can say
    honestly whether nothing exists or everything is merely fresh); ``ingest_report`` is the
    delegated forced run's own report (None on a dry run or an empty plan)."""

    selected: list[RefreshCandidate] = field(default_factory=list)
    candidates: int = 0
    eligible: int = 0
    min_age_days: int = 0
    dry_run: bool = False
    ingest_report: ingest.IngestReport | None = None

    def render(self) -> str:
        """The refresh plan (and, after a real run, the delegated ingest report below it)."""
        lines = ["Refresh report", "==============", ""]
        if not self.selected:
            if self.eligible == 0:
                lines.append("Nothing to refresh: no re-verifiable sources in the manifest.")
            else:
                lines.append(
                    f"Nothing to refresh: all {self.eligible} re-verifiable source(s) were "
                    f"checked within the last {self.min_age_days} days."
                )
            return "\n".join(lines) + "\n"
        verb = "Would refresh" if self.dry_run else "Refreshing"
        lines.append(f"{verb} {len(self.selected)} of {self.candidates} candidate source(s), oldest-checked first:")
        for c in self.selected:
            parts = [c.key, f"last checked {c.ingested_at or 'unknown (never re-stamped)'}"]
            if c.model:
                parts.append(f"by {c.model}")
            if c.stale_rules:
                parts.append("(stale rules)")
            lines.append("  " + "  ".join(parts))
        if self.dry_run:
            lines.append("")
            lines.append("Dry run: no agent sessions were started.")
        elif self.ingest_report is not None:
            lines.append("")
            lines.append(self.ingest_report.render())
        return "\n".join(lines).rstrip() + "\n"


def _age_floor(queue: list[RefreshCandidate], min_age_days: int) -> list[RefreshCandidate]:
    """Drop candidates whose ``ingested_at`` is younger than ``min_age_days`` — the self-limiting
    knob for scheduled runs. An entry with NO stamp always stays (age unknown = provably never
    re-checked, i.e. oldest); ``min_age_days <= 0`` is a no-op."""
    if min_age_days <= 0:
        return list(queue)
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [c for c in queue if c.ingested_at is None or c.ingested_at < cutoff]


def plan(min_age_days: int = 0) -> list[RefreshCandidate]:
    """The full refresh queue: every re-verifiable source, ordered least-recently-checked first.

    A source qualifies when a model actually imported it (``entry_model`` set — an unreadable
    binary that was only sniffed has nothing to re-verify) and it still exists on disk (a gone
    source is the deletion sweep's job). ``min_age_days > 0`` additionally applies
    :func:`_age_floor`. Ordering is the stamp as a plain string (fixed-width ISO UTC sorts
    chronologically), missing stamps first, key as the deterministic tie-break."""
    out: list[RefreshCandidate] = []
    current_rules = config.rules_version()
    for key, entry in manifest.load().items():
        model = manifest.entry_model(entry)
        if not model:
            continue
        if not config.source_path_for_key(key).exists():
            continue
        recorded_rules = manifest.entry_rules_version(entry)
        out.append(
            RefreshCandidate(
                key=key,
                ingested_at=manifest.entry_ingested_at(entry),
                model=model,
                stale_rules=recorded_rules is not None and recorded_rules != current_rules,
            )
        )
    out.sort(key=lambda c: (c.ingested_at or "", c.key))
    return _age_floor(out, min_age_days)


def refresh(limit: int = 1, min_age_days: int = 0, dry_run: bool = False, progress=None) -> RefreshReport:
    """Run one refresh: take the ``limit`` least-recently-checked sources off the queue and
    re-verify each through a forced ingest run (``kind="reconcile"`` per source, all-or-nothing
    staging, manifest re-stamped on success). ``limit`` must be >= 1 — the budget is always
    explicit, an unbounded refresh (one agent session per source, corpus-wide) can never happen
    by accident, mirroring ``--force``'s refusal without paths. ``dry_run`` computes and returns
    the plan with zero sessions. ``progress`` is threaded through to ingest untouched."""
    if limit < 1:
        raise ValueError("refresh limit must be >= 1 (each refreshed source runs one agent session).")
    eligible = plan()
    queue = _age_floor(eligible, min_age_days)
    selected = queue[:limit]
    report = RefreshReport(
        selected=selected, candidates=len(queue), eligible=len(eligible), min_age_days=min_age_days, dry_run=dry_run
    )
    if dry_run or not selected:
        return report
    # Hand ingest ABSOLUTE paths: manifest keys are workspace-relative, but ingest resolves
    # requested path strings against the CWD — which need not be the workspace root.
    paths = [str(config.source_path_for_key(c.key)) for c in selected]
    report.ingest_report = ingest.ingest(paths, progress=progress, force=True)
    return report
