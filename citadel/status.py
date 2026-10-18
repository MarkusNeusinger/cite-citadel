"""``citadel status`` — a read-only snapshot of the corpus state.

One command answering "what state is my corpus in?": per raw source, which lifecycle bucket it
sits in —

- **ingested** — folded into the wiki (with the importing model + the rules-tree hash it ran
  under, a ``(stale)`` flag when that hash predates the current rulebook — the ``curate
  --stale-rules`` plan signal, cleared only by re-verifying the source: ``citadel refresh
  --stale-rules`` — and the ``checked`` date a model last verified it, the ``citadel
  refresh`` ordering; a ``NO PAGES`` marker calls out a source that NO wiki page cites — it was
  ingested but produced zero entries, the ``citadel ingest --retry`` signal);
- **failed** — unreadable / errored / timed-out, with the coarse reason and, for a stuck curate-
  style record, its attempt count;
- **skipped-duplicate** — a same-basename twin skipped in favor of another format;
- **ignored** — files and folders matched by ``CITADEL_IGNORE_PATTERNS``, one row per distinct
  name with how many files it keeps out (a skipped folder's files are counted, bounded);
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

from . import config, failures, ingest, ledger, llm, manifest, refresh, store


# How much of a (long) content hash / rules-version / commit id to show in the table.
_ID_WIDTH = 12

# How many allowlist-filtered keys the table lists before collapsing the rest into a count (the
# excluded side of an allowlist is normally the big half of the tree — see ingest's twin).
_NOT_INCLUDED_SHOWN = 10

# Bounds of the per-ignored-directory file count: at most this many entries are examined per
# directory, and this many in total per ignored directory tree. `$RECYCLE.BIN` / `System Volume
# Information` (default ignore globs) on a drive-root raw dir are huge or unreadable, and status
# must stay cheap and never raise — a capped count renders as a lower bound (`N+`).
_IGNORED_DIR_ENTRY_CAP = 1000
_IGNORED_TREE_ENTRY_CAP = 10000


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
class IgnoredGroup:
    """One rendered ``Ignored`` row: every walked entry an ignore glob skipped under one basename,
    split by kind (a file name and a folder name never share a row). ``matches`` counts the
    entries, ``files`` the files they stand for — the entries themselves for a file row, the files
    inside the skipped folders for a folder row; ``capped`` marks ``files`` as a lower bound."""

    name: str
    dir: bool
    matches: int
    files: int
    capped: bool = False


def _plural(n: int, word: str, capped: bool = False) -> str:
    return f"{n}{'+' if capped else ''} {word}{'' if n == 1 and not capped else 's'}"


@dataclass
class StatusReport:
    """The per-source corpus state, split into its lifecycle buckets plus the current rules-tree
    hash (so the ``(stale)`` markers are self-explaining)."""

    ingested: list[SourceState] = field(default_factory=list)
    failed: list[SourceState] = field(default_factory=list)
    skipped_duplicate: list[SourceState] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)
    # One row per distinct (name, is-dir) the ignore globs skipped, with real file counts —
    # ``ignored`` above stays the plain sorted name list for existing JSON consumers.
    ignored_detail: list[IgnoredGroup] = field(default_factory=list)
    # (key, size_bytes) for files the CITADEL_MAX_SOURCE_BYTES ceiling keeps out of discovery.
    oversized: list[tuple[str, int]] = field(default_factory=list)
    # Keys the CITADEL_INCLUDE_PATTERNS allowlist keeps out of discovery ("read only .pdf/.txt").
    # Empty whenever no allowlist is configured, which is the default.
    not_included: list[str] = field(default_factory=list)
    pending: list[str] = field(default_factory=list)
    rules_version: str = ""
    # refresh.stale_count(): how many (stale) sources `citadel refresh --stale-rules` would
    # re-verify — the K of the closing hint. Render-only (status --json keeps its shape).
    stale_refreshable: int = 0
    # The run ledger's summary (ledger.summarize) — lifetime spend; None without a ledger.
    spend: dict | None = None

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
            lines.append(
                f"Current corpus cost: {total} over {len(costed)} source(s) "
                "(last verifying session each, not lifetime spend)"
            )
        credited = [s for s in self.ingested if s.aic is not None]
        if credited:
            # copilot's own billing unit, shown beside the dollars it was converted into — the
            # same "last session each" snapshot as the cost line.
            total_aic = llm.format_aic(sum(s.aic for s in credited))
            lines.append(
                f"Current corpus AI credits: {total_aic} AIC over {len(credited)} source(s) "
                "(last verifying session each, not lifetime spend)"
            )
        lines.extend(self._spend_lines())
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

        if self.ignored_detail:
            total = sum(g.files for g in self.ignored_detail)
            capped = any(g.capped for g in self.ignored_detail)
            rows = len(self.ignored_detail)
            lines.append(f"Ignored ({_plural(total, 'file', capped)}, {_plural(rows, 'name')})")
            for g in self.ignored_detail:
                if g.dir:
                    count = f"{_plural(g.matches, 'folder')}, {_plural(g.files, 'file', g.capped)}"
                    lines.append(f"  {g.name}/  ({count})")
                else:
                    lines.append(f"  {g.name}  ({_plural(g.files, 'file')})")
        else:
            lines.append("Ignored (0)")

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
        # The (stale) call to action: only the source lifecycle re-stamps a source, so name the
        # one command whose queue is exactly the stale set (curate re-checks pages and never
        # clears the marker).
        if self.stale_refreshable:
            if not (self.failed or uncited):
                lines.append("")
            k = self.stale_refreshable
            lines.append(f"{k} (stale) source(s): re-verify with {refresh.stale_command(k)}")

        return "\n".join(lines).rstrip() + "\n"

    def _spend_lines(self) -> list[str]:
        """The lifetime-spend line(s) from the run ledger (ASCII only)."""
        spend = self.spend
        if spend is None:
            return ["Spend to date: not recorded yet (the run ledger starts with the next ingest/curate/refresh run)"]
        since = f"since {spend['since']}"
        runs = f"{spend['runs']} run(s)"
        out: list[str] = []
        if spend["cost_usd"] is not None:
            parts = [
                f"{name} {llm.format_cost(entry['cost_usd'])}"
                for name, entry in spend["by_lifecycle"].items()
                if entry.get("cost_usd") is not None
            ]
            tail = f" ({', '.join(parts)})" if parts else ""
            out.append(f"Spend to date: {llm.format_cost(spend['cost_usd'])} over {runs} {since}{tail}")
        if spend["aic"] is not None:
            out.append(f"AI credits to date: {llm.format_aic(spend['aic'])} AIC over {runs} {since}")
        if not out:
            out.append(f"Spend to date: {runs} recorded, no cost reported by the backend")
        return out

    def as_dict(self) -> dict:
        """The report as one JSON-ready dict (``citadel status --json``): the seven buckets plus
        ``rules_version``, ``cost_usd_total`` and ``aic_total``, each source row a plain dict with only its None fields dropped —
        ``attempts: 0`` / ``stale_rules: false`` / ``uncited: false`` stay explicit, so scripts
        get a predictable shape for 'which sources failed and why' (and which produced no pages)
        without scraping :meth:`render`'s table.
        ``oversized`` carries ``{"key", "size_bytes"}`` objects rather than bare strings, since the
        size is the reason the row exists. ``ignored`` stays the sorted list of distinct ignored
        names; ``ignored_detail`` adds one ``{"name", "dir", "matches", "files", "capped"}`` object
        per rendered row (``files`` a lower bound when ``capped``)."""

        def row(s: SourceState) -> dict:
            return {k: v for k, v in asdict(s).items() if v is not None}

        costed = [s.cost_usd for s in self.ingested if s.cost_usd is not None]
        credits = [s.aic for s in self.ingested if s.aic is not None]
        return {
            "rules_version": self.rules_version,
            # The render()'s "Current corpus cost" total, machine-readably: the sum of each
            # source's last-session cost stamp (null when no entry carries one).
            "cost_usd_total": round(sum(costed), 4) if costed else None,
            # The same snapshot in copilot's billing unit (null when no entry carries one).
            "aic_total": round(sum(credits), 6) if credits else None,
            # Lifetime spend from the run ledger (null without one) — the snapshot totals above
            # stay exactly what they were.
            "spend": self.spend,
            "ingested": [row(s) for s in self.ingested],
            "failed": [row(s) for s in self.failed],
            "skipped_duplicate": [row(s) for s in self.skipped_duplicate],
            "ignored": list(self.ignored),
            "ignored_detail": [asdict(g) for g in self.ignored_detail],
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


def _walk_state() -> tuple[set[str], list[tuple[str, int]], list[str], list[tuple[Path, bool]]]:
    """ONE stat-only discovery walk (ingest's own — no hashing, repo-aware, dead-mount-safe), read
    for the four things status needs from disk: every source key visible under the raw roots RIGHT
    NOW (files plus repo dirs), the ``(key, size)`` pairs the ``CITADEL_MAX_SOURCE_BYTES``
    ceiling kept out of it, the keys the ``CITADEL_INCLUDE_PATTERNS`` allowlist kept out, and the
    ``(path, is_dir)`` entries the ``CITADEL_IGNORE_PATTERNS`` globs skipped — the same roots and
    repo pruning as discovery, by construction. Defensive: any walk failure degrades to empty
    (pending/oversized/not-included/ignored simply show nothing) rather than raising."""
    try:
        walk = ingest._discover_walk(None)
    except OSError:
        return set(), [], [], []
    keys = {manifest.rel_key(path) for path, _st in walk.files}
    keys |= {manifest.rel_key(path) for path in walk.repos}
    oversized = sorted((manifest.rel_key(path), size) for path, size in walk.oversized)
    not_included = sorted(manifest.rel_key(path) for path in walk.not_included)
    return keys, oversized, not_included, list(walk.ignored)


def _count_files(top: Path) -> tuple[int, bool]:
    """The files under an ignored directory — status-only (ingest never descends into one): a
    bounded iterative scandir (no symlinks followed, hidden names skipped, at most
    :data:`_IGNORED_DIR_ENTRY_CAP` entries per directory and :data:`_IGNORED_TREE_ENTRY_CAP` per
    tree). Returns ``(count, capped)``; a cap hit or any ``OSError`` makes the count a lower
    bound. Never raises."""
    count = 0
    examined = 0
    capped = False
    stack = [top]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for seen, entry in enumerate(it):
                    if seen >= _IGNORED_DIR_ENTRY_CAP or examined >= _IGNORED_TREE_ENTRY_CAP:
                        capped = True
                        break
                    examined += 1
                    if entry.name.startswith("."):
                        continue
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            count += 1
                    except OSError:
                        capped = True
        except OSError:
            capped = True
    return count, capped


def _ignored_groups(entries: list[tuple[Path, bool]]) -> list[IgnoredGroup]:
    """Group the walk's ignored entries into one row per distinct (name, is-dir) — by NAME, not by
    the pattern that matched, so a broad glob shows exactly which names it catches. Sorted by name
    (case-insensitively), file row before folder row on a tie."""
    groups: dict[tuple[str, bool], IgnoredGroup] = {}
    for path, is_dir in entries:
        g = groups.setdefault((path.name, is_dir), IgnoredGroup(name=path.name, dir=is_dir, matches=0, files=0))
        g.matches += 1
        if is_dir:
            n, capped = _count_files(path)
            g.files += n
            g.capped = g.capped or capped
        else:
            g.files += 1
    return [groups[k] for k in sorted(groups, key=lambda k: (k[0].lower(), k[0], k[1]))]


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
    present, oversized, not_included, ignored = _walk_state()
    report.pending = sorted(key for key in present if key not in tracked)
    report.oversized = oversized
    report.not_included = not_included
    try:
        report.spend = ledger.summarize(ledger.load())
    except Exception:  # noqa: BLE001 - status is read-only and must degrade, never raise
        report.spend = None
    report.ignored_detail = _ignored_groups(ignored)
    report.ignored = sorted({g.name for g in report.ignored_detail})
    if any(s.stale_rules for s in report.ingested):
        try:
            report.stale_refreshable = refresh.stale_count()
        except Exception:  # noqa: BLE001 - status is read-only and must degrade, never raise
            report.stale_refreshable = 0
    return report
