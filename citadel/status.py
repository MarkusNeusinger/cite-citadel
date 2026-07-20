"""``citadel status`` — a read-only snapshot of the corpus state.

One command answering "what state is my corpus in?": per raw source, which lifecycle bucket it
sits in —

- **ingested** — folded into the wiki (with the importing model + the rules-tree hash it ran
  under, a ``(stale)`` flag when that hash predates the current rulebook — the ``curate
  --stale-rules`` signal — and the ``checked`` date a model last verified it, the ``citadel
  refresh`` ordering);
- **failed** — unreadable / errored / timed-out, with the coarse reason and, for a stuck curate-
  style record, its attempt count;
- **skipped-duplicate** — a same-basename twin skipped in favor of another format;
- **ignored** — an OS/junk file matched by ``CITADEL_IGNORE_PATTERNS``;
- **pending** — on disk under a raw root, not yet in the manifest or the failures catalog.

Built from the manifest + the failures catalog + ONE stat-only discovery walk (reusing ingest's
own walk so repo sources, multi-root layouts, and dead mounts behave identically). It NEVER
re-hashes a byte — that is ingest's job — so it is cheap to run any time. The manifest/failures
files ARE the database; status only reads them. Read-only and defensive: a broken walk degrades to
empty pending/ignored rather than raising.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field

from . import config, failures, ingest, manifest


# How much of a (long) content hash / rules-version / commit id to show in the table.
_ID_WIDTH = 12


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


@dataclass
class StatusReport:
    """The per-source corpus state, split into its lifecycle buckets plus the current rules-tree
    hash (so the ``(stale)`` markers are self-explaining)."""

    ingested: list[SourceState] = field(default_factory=list)
    failed: list[SourceState] = field(default_factory=list)
    skipped_duplicate: list[SourceState] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    rules_version: str = ""

    def render(self) -> str:
        """A plain-text, ASCII-only per-source table — one bucket per section, counts in the
        headings. Deterministic (every bucket is sorted by key)."""
        lines = ["Corpus status", "=============", ""]
        lines.append(f"Rules version: {self.rules_version[:_ID_WIDTH] or '(none)'}")
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

        lines.append(f"Pending ({len(self.pending)})")
        for key in self.pending:
            lines.append(f"  {key}")

        return "\n".join(lines).rstrip() + "\n"

    def as_dict(self) -> dict:
        """The report as one JSON-ready dict (``citadel status --json``): the five buckets plus
        ``rules_version``, each source row a plain dict with only its None fields dropped —
        ``attempts: 0`` / ``stale_rules: false`` stay explicit, so scripts get a predictable
        shape for 'which sources failed and why' without scraping :meth:`render`'s table."""

        def row(s: SourceState) -> dict:
            return {k: v for k, v in asdict(s).items() if v is not None}

        return {
            "rules_version": self.rules_version,
            "ingested": [row(s) for s in self.ingested],
            "failed": [row(s) for s in self.failed],
            "skipped_duplicate": [row(s) for s in self.skipped_duplicate],
            "ignored": list(self.ignored),
            "pending": list(self.pending),
        }


def _is_stale_rules(entry, current_rules_version: str) -> bool:
    """True when an ingested source's recorded rules-tree hash predates the current one (an unknown
    /pre-rules-split stamp is not counted — it cannot be shown as stale honestly)."""
    recorded = manifest.entry_rules_version(entry)
    return recorded is not None and recorded != current_rules_version


def _present_source_keys() -> set[str]:
    """Every source key visible on disk under the raw roots RIGHT NOW — files plus repo dirs —
    via ingest's own stat-only walk (no hashing, repo-aware, dead-mount-safe). Defensive: any walk
    failure degrades to the empty set (pending simply shows nothing) rather than raising."""
    try:
        walk = ingest._discover_walk(None)
    except OSError:
        return set()
    keys = {manifest.rel_key(path) for path, _st in walk.files}
    keys |= {manifest.rel_key(path) for path in walk.repos}
    return keys


def _ignored_names() -> list[str]:
    """The OS/junk basenames under the raw roots that discovery skips (``CITADEL_IGNORE_PATTERNS``)
    — a light, stat-free ``os.walk`` that prunes ignored/hidden directories exactly as discovery
    does (the ONE ignore predicate, :func:`ingest._is_ignored_name`). Deduped + sorted; degrades to
    an empty list on any walk error."""
    found: set[str] = set()
    for root in config.source_roots():
        try:
            for _dirpath, dirnames, filenames in os.walk(root):
                kept = []
                for d in dirnames:
                    if d.startswith("."):
                        continue
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
            )
        )

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
    report.pending = sorted(key for key in _present_source_keys() if key not in tracked)
    report.ignored = _ignored_names()
    return report
