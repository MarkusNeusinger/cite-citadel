"""The append-only run ledger — ``wiki/.citadel_runs.jsonl``, one line per mutating run.

``citadel status``' "Current corpus cost" is a SNAPSHOT: each source's manifest stamp carries only
its LAST verifying session, so curate clusters, forced reconciles / refreshes (which overwrite the
stamp), failed sources and delete cleanups are paid for and then invisible. The ledger is the
lifetime record: every ingest / refresh / curate run that attempted at least one agent session
appends ONE line with the run's already-summed usage — money and counts only, **never** a source
key, page path or guidance text (file names and steers can be private; per-source detail stays in
the manifest).

It lives INSIDE the wiki like the manifest and the failures catalog, because it cannot be derived
from anything else: wikigit's ``git add -A`` commits it with the wiki (a NOOP-only run's line rides
the next committing run), staging copies carry it but never promote it back (dotfile rule), and a
shared workspace mounted at several paths sees one ledger. A write is read + append + atomic
rewrite under the run lock the caller already holds — a plain append can tear on SMB — and any
``OSError`` becomes a report note: the ledger must never fail a run that already spent money.
"""

from __future__ import annotations

import json
import math

from . import config, manifest


VERSION = 1
LIFECYCLES = ("ingest", "refresh", "curate")


def _usage_fields(usage) -> dict:
    """The usage fields a backend reported, through the manifest's finite/non-negative filter —
    an unreported field is omitted, never written as 0."""
    if usage is None:
        return {}
    return manifest._usage_stamp_fields(
        getattr(usage, "cost_usd", None),
        getattr(usage, "input_tokens", None),
        getattr(usage, "output_tokens", None),
        getattr(usage, "aic", None),
    )


def make_line(
    lifecycle: str,
    *,
    started: str,
    model: str,
    usage,
    counts: dict[str, int],
    flags: dict[str, bool | int],
    interrupted: bool = False,
) -> dict:
    """One ledger record. ``counts``/``flags`` hold ints and booleans only (the caller names them
    after existing report fields); nothing path-shaped ever goes in."""
    line: dict = {
        "v": VERSION,
        "lifecycle": lifecycle,
        "started": started,
        "ended": manifest.now_iso(),
        "model": model,
        "rules_version": config.rules_version(),
        "interrupted": bool(interrupted),
        "flags": {k: v for k, v in flags.items() if isinstance(v, (bool, int))},
        "counts": {k: int(v) for k, v in counts.items()},
    }
    line.update(_usage_fields(usage))
    return line


def append(line: dict) -> str:
    """Append ``line`` (read + atomic rewrite). Returns "" on success, else a one-line note for the
    run report — never raises."""
    path = config.runs_ledger_path()
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        if existing and not existing.endswith("\n"):
            existing += "\n"
        config.atomic_write_text(path, existing + json.dumps(line, sort_keys=True, ensure_ascii=True) + "\n")
    except OSError as exc:
        return f"run ledger: not written ({exc}); this run's spend is on this report only"
    return ""


def _valid(record) -> bool:
    if not isinstance(record, dict) or record.get("v") != VERSION:
        return False
    if record.get("lifecycle") not in LIFECYCLES or not isinstance(record.get("started"), str):
        return False
    for key in ("cost_usd", "aic"):
        if key in record:
            value = record[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                return False
    for key in ("tokens_in", "tokens_out"):
        if key in record:
            value = record[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
    return True


def load() -> list[dict]:
    """Every valid ledger line, in file order. Malformed lines (truncated JSON, merge leftovers, an
    unknown version, junk or negative figures) are skipped; a missing/unreadable file is ``[]``."""
    try:
        text = config.runs_ledger_path().read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if _valid(record):
            out.append(record)
    return out


def exists() -> bool:
    return config.runs_ledger_path().exists()


def summarize(lines: list[dict]) -> dict | None:
    """Totals over ``lines`` — each field summed over the lines that KNOW it (None when none did),
    plus per lifecycle; None for no lines at all."""
    if not lines:
        return None

    def total(records: list[dict], key: str):
        known = [r[key] for r in records if key in r]
        return (round(sum(known), 6) if key in ("cost_usd", "aic") else sum(known)) if known else None

    by_lifecycle: dict[str, dict] = {}
    for lifecycle in LIFECYCLES:
        records = [r for r in lines if r.get("lifecycle") == lifecycle]
        if records:
            by_lifecycle[lifecycle] = {"cost_usd": total(records, "cost_usd"), "runs": len(records)}
    return {
        "cost_usd": total(lines, "cost_usd"),
        "aic": total(lines, "aic"),
        "tokens_in": total(lines, "tokens_in"),
        "tokens_out": total(lines, "tokens_out"),
        "runs": len(lines),
        "since": min(r["started"] for r in lines)[:10],
        "by_lifecycle": by_lifecycle,
    }
