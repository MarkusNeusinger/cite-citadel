"""Resume checkpoints for CHUNKED sources — the saved-spend half of ingest's all-or-nothing rule.

A source too large for one context window is folded in over several sequential agent sessions
(segments) against ONE staging copy, promoted exactly once at the end. Promote-once is
load-bearing (the live wiki only ever holds fully-imported sources), but it used to carry a blunt
cost: a failure/timeout/interrupt at segment N discarded the staging copy — and with it the N-1
EARLIER segments' paid agent work — so the next run restarted the source at segment 1.

This module removes the waste WITHOUT weakening the guarantee. After each segment passes
validation, ingest records a CHECKPOINT beside the wiki: the exact delta the completed segments
produced against the live wiki — *the promote that would have happened* — plus the identity of the
work it belongs to. A later run replays that delta into a FRESH staging copy of the CURRENT live
wiki, re-validates it, and runs only the remaining segments. Promotion still happens exactly once,
still only after the last segment, and a failure still leaves the live wiki untouched.

Deviation from the audit's scoped design (backlog #9 said "capture backend session IDs, retry from
segment N" via ``claude --resume``): checkpoints are BACKEND-AGNOSTIC. They work on every CLI
(copilot/gemini expose no session-resume flag), they *keep* the earlier segments' work instead of
re-running it, and they need no provider to hold a session open — which a resumed conversation
would anyway find gone, since the staging tree it edited is deleted on every failure path.

**Why the delta is the file-level staging↔live difference** and not the agent's per-segment page
diff: ingest promotes by comparing FILES (``_content_files`` + byte equality), while its diff is a
PAGE-level view (``store.load()``). Writes that land outside the page diff — the link repairs
``_repair_renames`` makes in pages no session touched, any non-``.md`` file — reach the live wiki
through the promote, so only the promote's own view describes what a run would have shipped. That
asymmetry is exactly where a "replay the agent's edits" design silently drifts.

**Every reuse is guarded, and every guard failure degrades to precisely today's behavior** — start
at segment 1, in the same run, with no session wasted and no source failed:

- *identity* — source key, content sha, session kind, ingest model, rules version, the segment
  plan's CONTENT, and the prompt-shaping knobs (wiki language, style profiles, PDF/image mode) must
  all match. A changed source, a model/rules upgrade, a re-tuned chunk size or a flipped language
  is a different job: merging run 2's German segments into run 1's English pages is exactly the
  kind of frankenstein output a naive identity check would ship.
- *integrity* — every recorded page blob must still hash to the sha the record names (a torn write,
  a hand-edited slot, a half-synced dotdir).
- *base state* — every page the delta touches (created, rewritten OR deleted) must still be, in the
  LIVE wiki, byte-for-byte what it was when the checkpoint was written. If another source promoted
  a change to one of those pages in between, replaying would silently clobber it — and replaying a
  recorded DELETION would silently destroy work a different source has since done under that path.
  This is a per-PAGE guard, not a whole-wiki one: unrelated sources promoting in between leave a
  checkpoint perfectly usable.
- *replayed state* — after the delta lands in staging it is re-validated like any agent output, and
  no cross-link may be broken that was not already broken in the live wiki. A raw file deleted
  under a checkpointed page, or a link target curate moved away, therefore drops the checkpoint
  instead of promoting an invalid page (validation runs BEFORE the first resumed session, so a
  checkpoint that can no longer validate costs zero agent tokens, ever).
- *attempts* — a checkpoint adopted ``ATTEMPT_CAP`` times without the source ever completing is
  dropped, so a deterministically poisonous segment N cannot wedge a source into failing cheaply
  forever; the next run pays for a full, honest retry.

The store is a dotdir SIBLING of the wiki (``.citadel_resume/``, the same convention as
``.citadel_transcripts``/``.citadel_pdftext``), one hash-named slot per source key. It holds wiki
page text in plaintext — see SECURITY.md — so a slot is deleted the moment its source completes,
when any guard refuses it, when the source is deleted, and by an age sweep at run start.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config, manifest, okf, runlock


# The dotdir sibling of the wiki that holds every checkpoint slot. Deliberately NOT prefixed like
# a staging sibling (`.<wiki>.staging.`), which the run-start sweep deletes unconditionally.
CACHE_DIR_NAME = ".citadel_resume"
# Inside one slot: the record and the page blobs. A slot is written to a `<slot>.new` sibling and
# swapped into place, so the record and the blobs it names can never describe different segments.
RECORD_NAME = "checkpoint.json"
PAGES_DIR_NAME = "pages"
NEW_SUFFIX = ".new"
# On-disk record format. A record stamped with anything else is ignored (and swept), so a future
# format change never has to migrate half-finished work — the source simply restarts at segment 1.
FORMAT = 1
# A checkpoint older than this is swept at run start: the source it belongs to was not retried in
# two weeks, so its (plaintext) pages should not sit beside the wiki indefinitely. Its guards would
# still protect a later reuse — this is hygiene, not correctness.
MAX_AGE_DAYS = 14
# How often one checkpoint may be adopted before it is dropped in favor of a full retry. Resume
# makes a DETERMINISTIC segment failure cheap and quiet (it re-fails at segment K+1 every run);
# without a cap that is a wedge, and the source would never be re-attempted from a clean slate.
ATTEMPT_CAP = 3


def enabled() -> bool:
    """True when resume checkpoints are on (``CITADEL_RESUME``, default on). Read at call time so
    tests and the workspace ``.env`` can flip it; off means neither written nor consumed — the
    pre-#9 discard-and-restart behavior, byte for byte."""
    return bool(config.RESUME)


def cache_dir() -> Path:
    """The checkpoint store: a dotdir sibling of the wiki dir. Read at call time — and deliberately
    derived from the wiki's PARENT, so it resolves to the same directory while ingest has
    ``config.WIKI_DIR`` redirected at a per-source staging copy (staging is a SIBLING of the live
    wiki — the same reason ``transcribe``/``pdftext``/``runlock`` resolve their siblings this way)."""
    return Path(config.WIKI_DIR).parent / CACHE_DIR_NAME


@dataclass(frozen=True)
class Plan:
    """The identity of one chunked source's multi-segment job — everything that must be unchanged
    for an earlier run's partial work to be reusable.

    - ``shape`` fingerprints the segment plan by CONTENT (each prepared segment's text), never by
      the temp paths it is materialized to: a re-tuned ``CITADEL_MAX_SOURCE_CHARS``, a different
      Office/PDF extraction or a re-transcription re-splits the source, so "segment 3" would no
      longer mean the same text.
    - ``knobs`` fingerprints the prompt-shaping settings ``rules_version`` does NOT cover (wiki
      language, style profiles, PDF mode, image support) — each one changes what the agent writes.
    """

    key: str
    sha: str | None
    kind: str
    model: str
    rules_version: str
    total: int
    shape: str
    knobs: str = ""

    def fingerprint(self) -> str:
        """A stable hash over every identity field — what a stored record is compared against."""
        parts = [
            self.key,
            self.sha or "",
            self.kind,
            self.model,
            self.rules_version,
            str(self.total),
            self.shape,
            self.knobs,
        ]
        return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Checkpoint:
    """A validated, replayable checkpoint: the delta ``completed`` segments produced, the live-wiki
    state it was computed against, what those segments cost, and how often it has been adopted."""

    key: str
    completed: int
    total: int
    # rel_path -> sha256 of the staged page's bytes (the blob under pages/).
    pages: dict[str, str] = field(default_factory=dict)
    # rel_paths the segments removed from the wiki (each carries a non-null base hash below).
    removed: list[str] = field(default_factory=list)
    # rel_path -> the sha256 that path had in the LIVE wiki when this was written (None = absent).
    bases: dict[str, str | None] = field(default_factory=dict)
    # The earlier segments' backend-reported spend, as manifest-shaped kwargs.
    usage: dict = field(default_factory=dict)
    attempts: int = 0
    slot: Path = Path()


# A slot name is a hash of the source key: keys are arbitrary paths (separators, drive letters,
# unicode, length), and nothing derived from one may become a path component unescaped — the same
# discipline as transcribe/pdftext's sha-only cache filenames.
_SLOT_RE = re.compile(r"[0-9a-f]{32}")


def slot_for(key: str) -> Path:
    """The slot directory for source ``key`` — a hash of the key, never the key itself."""
    return cache_dir() / hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def save(plan: Plan, completed: int, staging: Path, live: Path, changed, removed, usage: dict) -> bool:
    """Record ``completed`` segments' work as this source's checkpoint; True when one is on disk
    afterwards.

    ``changed`` are the rel_paths whose staged bytes differ from live (new or rewritten) and
    ``removed`` the ones the segments took away — i.e. exactly the promote that WOULD happen right
    now. The blobs are copied out of ``staging`` and the live wiki's current hash for every touched
    path is recorded as the base state a later replay must still find.

    Best-effort by contract: any problem returns False and leaves the source to restart at segment
    1. A checkpoint can never fail a run — the money is already spent either way.
    """
    if not enabled() or not plan.sha or not runlock.owned():
        return False
    # Never persist a delta computed against a vanished/emptied staging tree: `_content_files` on a
    # missing directory yields {}, which would read as "the segments deleted the whole wiki" — the
    # same catastrophic shape the promote's anti-emptying valve refuses.
    if not Path(staging).is_dir() or (removed and not changed and not _has_content(staging)):
        return False
    slot = slot_for(plan.key)
    staged_new = Path(f"{slot}{NEW_SUFFIX}")
    try:
        _rmtree(staged_new)
        pages_dir = staged_new / PAGES_DIR_NAME
        config.robust_mkdir(pages_dir)
        blobs: dict[str, str] = {}
        for rel in changed:
            src = _safe_rel(Path(staging), rel)
            dst = _safe_rel(pages_dir, rel)
            if src is None or dst is None:
                return _abort(staged_new)  # an unsafe path in the delta: record nothing at all
            if not src.is_file():
                continue
            config.robust_mkdir(dst.parent)
            shutil.copyfile(src, dst)
            sha = _sha256_file(dst)
            if sha is None:  # unreadable right after writing it: refuse rather than record a lie
                return _abort(staged_new)
            blobs[rel] = sha
        bases = _live_state(Path(live), list(blobs) + list(removed))
        # A recorded deletion whose base is unknown could not be guarded on replay — and an
        # unguarded deletion is the one operation that can destroy another source's work.
        if any(bases.get(rel) is None for rel in removed) or any(rel not in bases for rel in blobs):
            return _abort(staged_new)
        record = {
            "format": FORMAT,
            "fingerprint": plan.fingerprint(),
            "key": plan.key,
            "kind": plan.kind,
            "completed": int(completed),
            "total": int(plan.total),
            "attempts": 0,  # a fresh checkpoint means real progress: the attempt budget resets
            "saved_at": time.time(),
            "workspace": workspace_stamp(),
            "pages": blobs,
            "removed": list(removed),
            "bases": bases,
            "usage": _clean_usage(usage),
        }
        config.atomic_write_text(staged_new / RECORD_NAME, json.dumps(record, indent=2, sort_keys=True) + "\n")
        # Swap the whole slot into place. A multi-file checkpoint cannot be written atomically in
        # place (`atomic_write_text` is per FILE), and a record that outran its blobs would be a
        # SILENT partial import — so the new slot is built beside the old one and only then
        # replaces it. A crash mid-build leaves an inert `*.new` (swept); a crash mid-swap leaves
        # no slot, which simply means a full retry.
        _rmtree(slot)
        os.rename(staged_new, slot)
        return True
    except (OSError, ValueError, TypeError):
        _rmtree(staged_new)
        return False


def load(plan: Plan) -> Checkpoint | None:
    """This source's checkpoint when one exists and passes the IDENTITY + INTEGRITY guards, else
    None — a mismatched, damaged or attempt-capped slot is deleted on the way out, since it can
    never become valid again. The base-state guard runs later, in :func:`replay`."""
    if not enabled() or not plan.sha:
        return None
    slot = slot_for(plan.key)
    record = _read_record(slot)
    if record is None:
        return None
    if record.get("fingerprint") != plan.fingerprint():
        _drop(slot)  # a changed source / model / rules version / segment plan / knob: another job
        return None
    completed, total = record.get("completed"), record.get("total")
    if not isinstance(completed, int) or not 1 <= completed <= plan.total or total != plan.total:
        _drop(slot)
        return None
    pages, removed, bases = record.get("pages"), record.get("removed"), record.get("bases")
    if not isinstance(pages, dict) or not isinstance(removed, list) or not isinstance(bases, dict):
        _drop(slot)
        return None
    attempts = record.get("attempts")
    attempts = attempts if isinstance(attempts, int) and attempts >= 0 else 0
    if attempts >= ATTEMPT_CAP:
        _drop(slot)  # adopted this often without ever completing: buy a clean full retry instead
        return None
    blob_root = slot / PAGES_DIR_NAME
    for rel, sha in pages.items():
        blob = _safe_rel(blob_root, str(rel))
        if blob is None or _sha256_file(blob) != sha:
            _drop(slot)  # torn write / hand-edited slot: the recorded bytes are not on disk
            return None
    if any(not isinstance(rel, str) or not bases.get(rel) for rel in removed):
        _drop(slot)  # an unguardable deletion (see save) — never replay one
        return None
    return Checkpoint(
        key=plan.key,
        completed=completed,
        total=plan.total,
        pages={str(k): str(v) for k, v in pages.items()},
        removed=[str(r) for r in removed],
        bases={str(k): (str(v) if v is not None else None) for k, v in bases.items()},
        usage=_clean_usage(record.get("usage")),
        attempts=attempts,
        slot=slot,
    )


def note_attempt(cp: Checkpoint) -> None:
    """Count one adoption of ``cp`` (read-modify-write of the record's ``attempts``), so a
    checkpoint that keeps being adopted without its source ever completing eventually hits
    :data:`ATTEMPT_CAP` and is dropped. A successful segment writes a fresh checkpoint, which
    resets the counter — the budget bounds FRUITLESS resumes, not long sources. Never raises."""
    if not runlock.owned():
        return
    record = _read_record(cp.slot)
    if record is None:
        return
    record["attempts"] = cp.attempts + 1
    with contextlib.suppress(OSError, ValueError, TypeError):
        config.atomic_write_text(cp.slot / RECORD_NAME, json.dumps(record, indent=2, sort_keys=True) + "\n")


def replay(cp: Checkpoint, staging: Path, live: Path) -> list[str] | None:
    """Apply ``cp``'s delta into a FRESH ``staging`` copy of ``live`` and return the rel_paths it
    touched (for the caller to re-validate), or None when the BASE-STATE guard fails and the source
    must start at segment 1 instead.

    The guard: every page the delta created, rewrote or deleted must still hold, in the live wiki,
    exactly the bytes it held when the checkpoint was written (absent stays absent). A page another
    source has changed since would otherwise be silently overwritten with this checkpoint's older
    version — and a replayed deletion would silently destroy that other source's work.
    """
    for rel, base in cp.bases.items():
        target = _safe_rel(Path(live), rel)
        if target is None or _sha256_file(target) != base:
            return None
    touched: list[str] = []
    for rel in cp.pages:
        blob = _safe_rel(cp.slot / PAGES_DIR_NAME, rel)
        dst = _safe_rel(Path(staging), rel)
        if blob is None or dst is None:
            return None
        try:
            config.robust_mkdir(dst.parent)
            shutil.copyfile(blob, dst)
        except OSError:
            return None
        touched.append(rel)
    for rel in cp.removed:
        gone = _safe_rel(Path(staging), rel)
        if gone is None:
            return None
        with contextlib.suppress(OSError):
            gone.unlink(missing_ok=True)
        touched.append(rel)
    return touched


def clear(key: str) -> None:
    """Drop this source's checkpoint — on success (the work is live now), when the source is
    deleted or moved, or when a guard refused it. Never raises."""
    _drop(slot_for(key))


def sweep(max_age_days: int = MAX_AGE_DAYS) -> None:
    """Delete stale slots — unreadable/foreign-format records, ones stamped by another workspace,
    and anything older than ``max_age_days`` — plus abandoned ``*.new`` build dirs. Called ONCE at
    run start under the exclusive run lock (exactly like the stale-staging sweep), where no other
    run can be mid-write. Deliberately age-based only: gating on "the source still exists" would
    reintroduce the unmounted-root false-deletion shape discovery is hardened against. Never
    raises."""
    if not runlock.owned():
        return
    cutoff = time.time() - max_age_days * 86400
    stamp = workspace_stamp()
    with contextlib.suppress(OSError):
        for slot in cache_dir().iterdir():
            if not _SLOT_RE.fullmatch(slot.name):
                _drop(slot)  # a `*.new` build dir, or anything else that is not a slot
                continue
            record = _read_record(slot)
            if record is None:
                _drop(slot)
                continue
            saved_at = record.get("saved_at")
            stamped = str(record.get("workspace") or "")
            if not isinstance(saved_at, (int, float)) or saved_at < cutoff or (stamped and stamped != stamp):
                _drop(slot)


def pending() -> list[tuple[str, int, int]]:
    """``(source key, completed, total)`` for every readable checkpoint on disk, sorted by key —
    the read-only view ``citadel doctor`` reports. Identity is NOT re-checked here (that needs a
    run's model/rules context): a listed checkpoint is a candidate, not a promise. Never raises."""
    out: list[tuple[str, int, int]] = []
    with contextlib.suppress(OSError):
        for slot in cache_dir().iterdir():
            record = _read_record(slot) if _SLOT_RE.fullmatch(slot.name) else None
            if record is None:
                continue
            key, done, total = record.get("key"), record.get("completed"), record.get("total")
            if isinstance(key, str) and isinstance(done, int) and isinstance(total, int):
                out.append((key, done, total))
    return sorted(out)


def knob_stamp() -> str:
    """The prompt-shaping settings that ``rules_version`` does NOT cover, as one identity string.

    Each of these changes what the agent WRITES without touching the rules tree: the wiki's target
    language, persona/style capture, whether a PDF's figures are read, whether an Office source's
    embedded images came along. Flipping one between runs and then merging the new segments into
    the old ones would produce a page cluster no single run could — half English, half German —
    so a flip invalidates the checkpoint like any other identity change."""
    return "|".join(
        [
            config.WIKI_LANG,
            config.PDF_MODE,
            str(int(bool(config.STYLE_PROFILES))),
            str(int(bool(config.IMAGE_SUPPORT))),
            str(int(bool(config.AUDIO_SUPPORT))),
        ]
    )


def workspace_stamp() -> str:
    """The current workspace root as an absolute posix string — mirroring the manifest's
    ``meta.workspace`` stamp, so a checkpoint written by a DIFFERENT workspace that happens to
    share this wiki's parent directory is never replayed here (key-space stability is checked
    explicitly in this codebase, never assumed)."""
    with contextlib.suppress(OSError, ValueError):
        return Path(config.WORKSPACE_ROOT).resolve().as_posix()
    return str(config.WORKSPACE_ROOT)


# --- internals ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str | None:
    """The sha256 of ``path``, or None when it cannot be read (missing counts as absent)."""
    try:
        return manifest.file_sha256(path)
    except OSError:
        return None


def _safe_rel(root: Path, rel: str) -> Path | None:
    """``root/rel`` when ``rel`` is a safe wiki-relative path, else None. EVERY path out of a
    persisted record goes through this: a checkpoint is a file on disk, hence untrusted input."""
    try:
        return okf.safe_join(root, str(rel))
    except (okf.OKFError, ValueError):
        return None


def _live_state(live: Path, rels) -> dict[str, str | None]:
    """The current sha of each of ``rels`` in ``live`` (None = absent) — the base state a
    checkpoint records and a replay re-checks. An unsafe path yields None, which the deletion
    guard in :func:`save` then refuses."""
    out: dict[str, str | None] = {}
    for rel in rels:
        target = _safe_rel(live, rel)
        out[str(rel)] = _sha256_file(target) if target is not None else None
    return out


def _has_content(root: Path) -> bool:
    """True when ``root`` holds at least one ``.md`` file — the same "did the session leave a wiki
    at all" sanity check the promote's anti-emptying valve makes."""
    with contextlib.suppress(OSError):
        return any(root.rglob("*.md"))
    return False


def _clean_usage(usage) -> dict:
    """The usage kwargs, defensively filtered exactly like the manifest's stamp fields (finite
    non-bool cost, non-negative int tokens) — these round-trip through an on-disk sidecar and end
    up in the manifest, so a hand-edited value must never enter."""
    if not isinstance(usage, dict):
        return {}
    out: dict = {}
    cost = usage.get("cost_usd")
    if isinstance(cost, (int, float)) and not isinstance(cost, bool) and math.isfinite(float(cost)):
        out["cost_usd"] = round(float(cost), 4)
    for name in ("tokens_in", "tokens_out"):
        value = usage.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            out[name] = value
    return out


def _read_record(slot: Path) -> dict | None:
    """The slot's parsed record, or None when it is missing, unreadable, not JSON, not an object,
    or stamped with a format this version does not speak. Never raises — status/doctor read the
    store WITHOUT the run lock and may catch it mid-swap."""
    try:
        data = json.loads((slot / RECORD_NAME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return None
    return data


def _rmtree(path: Path) -> None:
    """Best-effort recursive delete (a slot is regenerable state; a share that refuses the delete
    only leaves an inert dotdir for the next sweep)."""
    shutil.rmtree(path, ignore_errors=True)


def _drop(slot: Path) -> None:
    _rmtree(slot)


def _abort(staged_new: Path) -> bool:
    """Discard a half-built slot and report "no checkpoint" — the one refusal path :func:`save`
    uses when the delta it was handed cannot be recorded faithfully."""
    _rmtree(staged_new)
    return False
