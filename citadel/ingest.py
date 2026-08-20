"""Orchestrate one ingest run: drive an agentic CLI, then re-impose the invariants.

For each pending source the agent (``llm.run_ingest_session``) reads the raw file, searches
the wiki, and **edits the wiki page files directly** — there is no ops JSON to apply. The
deterministic work around that autonomy is split by responsibility across four modules (this
one is the orchestrator and the facade; like :mod:`citadel.store`, the sibling modules are an
implementation detail and every seam stays addressable as ``ingest._x``):

- :mod:`citadel.ingest_scan` — discovery + partitioning: the incremental ``os.scandir`` walk,
  the guarded deletion sweep, source classification (Office/image/audio/PDF routing,
  same-basename dedup), and the file/repo partitions;
- :mod:`citadel.ingest_staging` — the per-source staging copies, the before/after
  **diff by content hash** that learns what the agent created/updated/deleted, the
  **validate + re-stamp** pass, deterministic rename-link repair, and the non-destructive
  promote-once-per-source onto the live wiki;
- :mod:`citadel.ingest_sessions` — the all-or-nothing session runner every job kind drives,
  the resume-checkpoint glue for chunked sources, and large-source pass planning;
- this module — :class:`IngestReport`, the ONE shared per-source job loop
  (:class:`_SourceJob` / :func:`_run_source_jobs`, serial and ``--jobs N`` parallel), and
  :func:`ingest` itself: partition, run deletion cleanups then files then repos, finalize
  (rebuild indexes, surface broken links, append the log) once per run.

Idempotent: sources whose sha already matches the manifest are skipped (unless deliberately
re-read with ``--force``), and a source is marked done only on a clean session.
``llm.run_ingest_session`` is the single outside call (tests monkeypatch it with a fake that
writes files into the temp wiki).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sys
import threading
from collections.abc import Callable
from concurrent import futures
from dataclasses import dataclass, field
from pathlib import Path

from . import config, failures, llm, manifest, pagecache, pdftext, repo, resume, runlock, store, transcribe, wikigit
from .ingest_scan import _candidates as _candidates
from .ingest_scan import _dedup_by_basename as _dedup_by_basename

# --- Facade re-exports -------------------------------------------------------------------------
# The underscore names below are deliberate seams: tests, `citadel status` and `citadel curate`
# address them as `ingest._x` (see each module's docstring). Names this module itself consumes are
# imported plainly; the pure re-exports use the redundant-alias form so the linter keeps them.
from .ingest_scan import (
    _discover_repos,
    _discover_walk,
    _human_bytes,
    _is_untrackable_key,
    _partition_repos,
    _partition_sources,
    _reads_as_cloud_placeholder,
    _RepoJob,
)
from .ingest_scan import _is_ignored_name as _is_ignored_name
from .ingest_scan import _is_included_name as _is_included_name
from .ingest_scan import _is_ingestible as _is_ingestible
from .ingest_scan import _is_repo_source as _is_repo_source
from .ingest_scan import _is_wiki_internal as _is_wiki_internal
from .ingest_sessions import _checkpoint_delta as _checkpoint_delta
from .ingest_sessions import (
    _office_write_temp,
    _pending_session,
    _prepare_passes,
    _Resume,
    _resume_context,
    _run_agent_sessions,
    _sha_shared_by_other_entry,
    _SourceOutcome,
    _stamp_model,
    _usage_fields,
)
from .ingest_staging import _canonical_resource_key as _canonical_resource_key
from .ingest_staging import _content_hashes as _content_hashes
from .ingest_staging import _diff as _diff
from .ingest_staging import _make_staging as _make_staging
from .ingest_staging import _promote as _promote
from .ingest_staging import _robust_copy_file as _robust_copy_file
from .ingest_staging import _robust_rmtree as _robust_rmtree
from .ingest_staging import _staging_prefix as _staging_prefix
from .ingest_staging import _sweep_stale_staging


# How many allowlist-filtered files the run report lists by name before collapsing the rest into a
# count. An allowlist is normally the SMALL half of a raw tree, so the excluded side can be tens of
# thousands of files — a full dump would bury the report it is a footnote of.
_NOT_INCLUDED_SHOWN = 10


@dataclass
class IngestReport:
    processed: list[str]
    skipped: list[str]
    pages_written: list[str]  # = pages_created + pages_updated (union, in write order)
    errors: list[str]
    # The model/backend that imported this run's sources, surfaced so the report says WHICH model
    # ran. Starts as the CONFIGURED label (config.ingest_model_label) and is upgraded in place to
    # the model the backend REPORTED serving as soon as a session names one (_record_spend) — the
    # same id the per-source manifest entries are stamped with.
    model: str = ""
    pages_deleted: list[str] = field(default_factory=list)
    # (source_rel_path, target) cross-links left dangling after this run — should be empty.
    broken_links: list[tuple[str, str]] = field(default_factory=list)
    pages_created: list[str] = field(default_factory=list)  # pages that did not exist before
    pages_updated: list[str] = field(default_factory=list)  # existing pages that were rewritten
    # (old_rel_key, new_rel_key) for sources recognized as only MOVED/reorganized (same bytes
    # under a new path) — not re-ingested; their wiki references are repointed deterministically.
    moved: list[tuple[str, str]] = field(default_factory=list)
    # rel-keys of sources with no extractable text (binary/unsupported) — NOT ingested, logged.
    unreadable: list[str] = field(default_factory=list)
    # Subset of ``unreadable`` whose bytes read as 100% NUL — cloud-only placeholders (Dropbox/
    # OneDrive online-only files seen through WSL/SMB), surfaced with a make-it-available-offline
    # hint instead of the generic binary message.
    cloud_placeholders: list[str] = field(default_factory=list)
    # (dropped_key, kept_key) for same-basename document files skipped in favor of another format.
    duplicates: list[tuple[str, str]] = field(default_factory=list)
    # (forced_key, kept_key) for same-basename pairs a FORCED run ingested ALONGSIDE the kept
    # sibling (a forced run bypasses the dedup drop — nothing was skipped, both formats are in the wiki).
    duplicates_forced: list[tuple[str, str]] = field(default_factory=list)
    # (rel_key, size_bytes) for sources skipped at discovery because they exceed
    # CITADEL_MAX_SOURCE_BYTES — never hashed, never ingested, and (like an ignore-pattern match)
    # never recorded in the manifest or the failures catalog. Reported so a size skip is visible.
    oversized: list[tuple[str, int]] = field(default_factory=list)
    # rel-keys of files the CITADEL_INCLUDE_PATTERNS allowlist kept out of discovery ("read only
    # .pdf and .txt"). Like an ignore match: never hashed, never ingested, never recorded in the
    # manifest or the failures catalog — but reported, because an allowlist filtering the whole
    # tree away must be legible as a filter rather than as an empty raw/.
    not_included: list[str] = field(default_factory=list)
    # rel-keys of tracked sources that VANISHED from disk (a full run only): their provenance is
    # reconciled out of the wiki by a cleanup agent session, then the manifest key is dropped.
    sources_deleted: list[str] = field(default_factory=list)
    # `--reingest` only: tracked sources whose previous facts were STRIPPED by a cleanup session
    # (manifest key dropped) ahead of the fresh plain-ingest session the same run then ran for
    # them — the deliberate re-think of an already-ingested source. The fresh session's own
    # outcome lands in `processed`/`errors` like any other source's.
    reingest_cleaned: list[str] = field(default_factory=list)
    # `--jobs N` only: sources whose session raced a CONCURRENT source's promote over the same page
    # and were therefore re-run serially afterwards (the re-run's own success/failure is reported
    # like any other source's). Surfaced because it is the one place parallel ingest costs money a
    # serial run would not have spent — a corpus that races often wants a lower --jobs.
    raced: list[str] = field(default_factory=list)
    # Chunked sources that CONTINUED from an earlier run's checkpoint instead of restarting at
    # segment 1 ("raw/book.txt (segments 1-3 of 7 restored)") — see citadel/resume.py. Recorded
    # whether or not the resumed source then succeeded: the earlier work was reused either way.
    resumed: list[str] = field(default_factory=list)
    # rel-keys of FRESH sources (a plain ingest — not a reconcile, not a delete cleanup) whose
    # session succeeded but changed NOTHING: no page created, updated, or deleted. Suspicious by
    # construction — a brand-new source that contributes zero facts is usually a session that
    # under-delivered, yet it is marked done and never revisited on its own. Surfaced as a WARNING
    # so it is easy to spot and retry (`citadel ingest --retry`, or `--force <path>`).
    no_pages: list[str] = field(default_factory=list)
    # Validation errors that were ALREADY on a page when a source touched it — a dangling `[^sN]`
    # a failed deletion cleanup left behind, a `resource` whose raw file moved, a hand edit. They
    # did not fail the source that found them (it did not cause them — see
    # ``_validate_and_restamp``'s ``inherited``), but they are real problems in the live wiki, so
    # they are surfaced here rather than silently carried forward.
    inherited_issues: list[str] = field(default_factory=list)
    # Per-failure guidance for the failures where "it will be retried next run" is not the whole
    # story, because the failed source left something behind in the live wiki (see
    # ``_SourceJob.failure_hint``). Deduped, in first-seen order.
    failure_hints: list[str] = field(default_factory=list)
    # Set when the run STOPPED EARLY because consecutive sources came back from the agent having
    # changed nothing at all — the signature of a broken agent CLI, not of a corpus with nothing to
    # say. Holds the human-readable reason; empty on every normal run.
    stalled: str = ""
    # The wiki-history note from wikigit.autocommit ("wiki git: committed <sha>", or a warning
    # naming what was skipped and why) — empty when the history layer had nothing to say.
    wiki_git: str = ""
    # What this run's agent sessions cost, summed over EVERY session that reported usage —
    # failed sources included (their money was spent too; only the manifest stamp is
    # success-only). None when no backend reported anything (copilot, the test fakes).
    usage: llm.SessionUsage | None = None

    def render(self) -> str:
        """Human-readable multi-line summary for CLI/MCP."""
        lines: list[str] = []
        if self.model:
            lines.append(f"Model: {self.model}")
        lines.append(
            f"Ingest complete: {len(self.processed)} processed, "
            f"{len(self.skipped)} skipped, "
            f"{len(self.pages_created)} created, "
            f"{len(self.pages_updated)} updated, "
            f"{len(self.pages_deleted)} deleted, "
            f"{len(self.moved)} reorganized, "
            f"{len(self.sources_deleted)} sources removed, "
            f"{len(self.unreadable)} unreadable, "
            f"{len(self.duplicates)} duplicate(s) skipped, "
            f"{len(self.errors)} errors."
        )
        described = self.usage.describe() if self.usage is not None else ""
        if described:
            lines.append(f"LLM usage: {described}.")
        if self.processed:
            lines.append("Processed:")
            lines.extend(f"  - {p}" for p in self.processed)
        if self.pages_created:
            lines.append("Pages created:")
            lines.extend(f"  - {p}" for p in self.pages_created)
        if self.pages_updated:
            lines.append("Pages updated:")
            lines.extend(f"  - {p}" for p in self.pages_updated)
        if self.pages_deleted:
            lines.append("Pages deleted (restructured):")
            lines.extend(f"  - {p}" for p in self.pages_deleted)
        if self.moved:
            lines.append("Reorganized (recognized as moved; not re-ingested):")
            lines.extend(f"  - {old} -> {new}" for old, new in self.moved)
        if self.sources_deleted:
            lines.append("Sources removed (deleted from disk; citations reconciled out):")
            lines.extend(f"  - {s}" for s in self.sources_deleted)
        if self.reingest_cleaned:
            lines.append("Re-ingested fresh (previous facts stripped first, then imported as new):")
            lines.extend(f"  - {s}" for s in self.reingest_cleaned)
        if self.resumed:
            lines.append("Resumed (continued from an earlier run's checkpoint):")
            lines.extend(f"  - {r}" for r in self.resumed)
        if self.raced:
            lines.append("Re-run serially (raced another source's promote over the same page):")
            lines.extend(f"  - {r}" for r in self.raced)
        if self.unreadable:
            lines.append("Unreadable (no extractable text; not ingested):")
            for p in self.unreadable:
                if p in self.cloud_placeholders:
                    lines.append(
                        f"  - {p}  (reads as all NUL bytes - a cloud-only placeholder? make it available offline)"
                    )
                else:
                    lines.append(f"  - {p}")
        if self.oversized:
            lines.append(f"Oversized (over CITADEL_MAX_SOURCE_BYTES = {_human_bytes(config.MAX_SOURCE_BYTES)}):")
            lines.extend(f"  - {key} ({_human_bytes(size)})" for key, size in self.oversized)
        if self.not_included:
            # An allowlist can filter out a whole drive, so the report shows a sample, not a dump.
            lines.append(
                f"Not included ({len(self.not_included)} file(s) outside CITADEL_INCLUDE_PATTERNS = "
                f"{', '.join(config.INCLUDE_PATTERNS) or '(none)'}):"
            )
            lines.extend(f"  - {key}" for key in self.not_included[:_NOT_INCLUDED_SHOWN])
            if len(self.not_included) > _NOT_INCLUDED_SHOWN:
                lines.append(f"  - ... +{len(self.not_included) - _NOT_INCLUDED_SHOWN} more")
        if self.duplicates:
            lines.append("Skipped as duplicate (same basename as another format that was ingested):")
            lines.extend(f"  - {dropped} (kept {kept})" for dropped, kept in self.duplicates)
        if self.duplicates_forced:
            lines.append("Duplicate formats deliberately ingested (forced):")
            lines.extend(f"  - {d} (ingested alongside {kept} — forced)" for d, kept in self.duplicates_forced)
        if self.skipped:
            lines.append("Skipped (already ingested):")
            lines.extend(f"  - {p}" for p in self.skipped)
        if self.no_pages:
            lines.append("WARNING — ingested but produced NO wiki changes (no page created, updated, or deleted):")
            lines.extend(f"  - {p}" for p in self.no_pages)
            lines.append(
                "  These sources are marked done and will not be revisited automatically. "
                "Retry them with `citadel ingest --retry` (or `citadel ingest --force <path>`)."
            )
        if self.inherited_issues:
            lines.append("WARNING — pre-existing problems on pages this run touched (NOT caused by these sources):")
            lines.extend(f"  - {i}" for i in self.inherited_issues)
            lines.append(
                "  These did not fail the sources that found them. Run `citadel lint` for the full "
                "picture, and `citadel curate` to have them repaired."
            )
        if self.broken_links:
            lines.append("WARNING — broken cross-links (run `citadel lint`):")
            lines.extend(f"  - {src} -> {tgt}" for src, tgt in self.broken_links)
        if self.stalled:
            lines.append(f"STOPPED EARLY — {self.stalled}")
        if self.errors:
            lines.append("Errors:")
            lines.extend(f"  - {e}" for e in self.errors)
            lines.append(
                "  Failed sources stay in the failures catalog (`citadel status` lists them) and are "
                "retried on the next run — or right away with `citadel ingest --retry`."
            )
            # ...but a retry is not the whole story when the failure left damage in the wiki.
            for hint in self.failure_hints:
                lines.append(f"  {hint}")
        if self.wiki_git:
            lines.append(self.wiki_git)
        return "\n".join(lines)


@dataclass
class _SourceJob:
    """ONE per-source unit of agent-driven work — the shared shape behind :func:`ingest`'s single
    per-source loop (the three near-duplicate loops — pending files,
    repos, deletion cleanups — collapse behind this; :func:`_run_source_jobs` owns the
    emit/report/failures vocabulary once).

    - ``key``: the source key — the report/failures/progress identity.
    - ``build_sessions``: plans the source's agent session(s), returning ``(session_fns, tmpdirs,
      resume_ctx)``: the callables run in order against ONE shared staging copy
      (:func:`_run_agent_sessions`), the temp dirs the loop removes afterwards, and — for a CHUNKED
      source only — the :class:`_Resume` context that lets the runner continue from an earlier
      run's checkpoint (None everywhere else: every other job kind is a single session). It may
      raise — recorded as a per-source ``prepare_error`` failure, never aborting the run. An EMPTY
      session list means there is nothing for an agent to do (a deleted source nothing cites):
      the job succeeds immediately with zero page changes.
    - ``on_success``: the post-success bookkeeping that differs per kind — the manifest stamp
      (``mark_done`` / repo entry / key drop), clearing the failure record, the per-source
      manifest save, and which report list the source lands in. Takes the outcome's combined
      session usage (``llm.SessionUsage | None``) plus the source's wall-clock seconds, so the
      manifest stamp can record what the verification cost in the backend's units AND in time
      (the only cost a local model has); the page changes already went into the report before it
      runs, so a job needs no view of the diff.
      (``citadel curate`` deliberately BYPASSES ``_SourceJob`` — its per-cluster report, different
      vocabulary, and NOOP outcome do not fit here — and rides :func:`_run_agent_sessions`
      directly, so nothing consumes a per-source outcome through this seam.)
    - ``extra_check``/``allow_emptying``: passed through to the session runner (deletion cleanup
      asserts no reference survived and may legitimately empty the wiki).
    - ``sha_stat``: the (sha256, stat) discovery already took for the source, threaded into the
      failures catalog so an unchanged stuck source joins the stat quick check.
    - ``warn_no_pages``: True for a FRESH source (a plain ingest of a new key, file or repo) —
      a successful session that then changed NOTHING lands on ``report.no_pages`` as a warning.
      Deliberately False for reconciles (an unchanged verdict is a legitimate outcome of
      re-reading a source, and ``citadel refresh`` would otherwise flag its whole slice) and for
      delete cleanups (empty means nothing cited the source — the expected case).
    - ``expects_changes``: True when a session that changes NOTHING is evidence the agent is not
      working, rather than a legitimate verdict — a fresh source (which has no facts in the wiki
      yet) or a deletion cleanup that was only planned BECAUSE something still cites the source.
      Feeds :class:`_StallGuard`. Reconciles are excluded for the same reason they are excluded
      from ``warn_no_pages``: "nothing changed" is a real answer there.
    - ``failure_hint``: what the user should DO when THIS job fails, when the generic
      "it will be retried" advice is not the whole story. Set only where a failed source leaves
      something behind in the live wiki that a retry alone does not address — today just the
      deletion cleanup. Surfaced once per run on ``report.failure_hints``.
    """

    key: str
    build_sessions: Callable[[], tuple[list[Callable[[], llm.SessionUsage | None]], list[str], "_Resume | None"]]
    on_success: Callable[[llm.SessionUsage | None, float | None], None]
    prepare_error: str
    extra_check: Callable[[], list[str]] | None = None
    allow_emptying: bool = False
    sha_stat: tuple[str | None, os.stat_result | None] = (None, None)
    warn_no_pages: bool = False
    expects_changes: bool = False
    failure_hint: str = ""


@dataclass
class _StallGuard:
    """Stops a run whose AGENT has stopped working, before it bills the whole corpus for nothing.

    A source whose session runs to completion and changes not one page is normally just a warning
    (``report.no_pages``). But when it happens to fresh source after fresh source, it is not a
    corpus with nothing to say — it is the agent CLI failing in a way that does not look like
    failure: a self-update mid-run that leaves the new binary unable to launch its own tools, a
    revoked file-write permission, a sandbox that denies every subprocess. The session still exits
    0, still reports tokens spent, and still returns an empty diff, so every existing guard passes
    and the run marches through every remaining source at full price.

    So: count CONSECUTIVE sources that were expected to change something (:attr:`_SourceJob
    .expects_changes` — a fresh source or a deletion cleanup that was planned because something
    still cites the source) and did not, and trip once that reaches ``limit``. Any source whose
    session CHANGED something resets the count — including a reconcile's — because that is proof the
    agent works. Only the empty outcomes are read by job kind: an empty reconcile ("I re-read it; it
    still says what the wiki says") is a legitimate verdict and no evidence in either direction, as
    is a deletion nothing cited or a source that failed before its session ran.

    Tripping stops the run cleanly: nothing is rolled back (everything promoted stays promoted),
    untouched sources are simply never attempted, so they stay pending and the next run picks them
    up with no manifest entry to undo.
    """

    limit: int
    consecutive: int = 0
    tripped: bool = False
    first_key: str = ""
    # note() is called from WORKER threads under ``--jobs N`` (see below), so the counters get
    # their own lock — the one shared-state exception to the main-thread-writes rule, taken
    # deliberately: the guard must trip AT COMPLETION TIME, or it cannot stop dispatch in time.
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def note(self, job: "_SourceJob", outcome: "_SourceOutcome") -> None:
        """Fold one completed outcome into the count. Thread-safe: the serial driver feeds it
        from :func:`_record_source_run`, but the parallel driver feeds it from the WORKER the
        moment its attempt completes — noting only when the main thread gets around to recording
        would let a fast-failing (broken) agent drain the whole queue before the third empty
        outcome is ever seen, which is precisely the corpus-wide bill the guard exists to stop.

        Counting and resetting are deliberately ASYMMETRIC about ``expects_changes``, because the
        two directions need different evidence. An empty session only means "the agent is broken"
        for a source that had work to do, so a reconcile's empty verdict is not counted. But a
        session that CHANGED something is proof the agent works whatever the job kind was — so a
        reconcile that did change pages resets the counter like any other source. Treating that
        proof as no evidence would false-trip a mixed run, where a run's fresh sources and its
        reconciles are interleaved in scan order."""
        with self._lock:
            if self.limit <= 0 or self.tripped or not outcome.ran_sessions:
                return
            if outcome.created or outcome.updated or outcome.deleted:
                self.consecutive = 0
                self.first_key = ""
                return
            if not job.expects_changes:
                return  # an empty reconcile is a legitimate verdict: no evidence in either direction
            self.consecutive += 1
            if self.consecutive == 1:
                self.first_key = job.key
            if self.consecutive >= self.limit:
                self.tripped = True

    @property
    def reason(self) -> str:
        """The run report's ``stalled`` line — what tripped, and what to do about it."""
        if not self.tripped:
            return ""
        return (
            f"{self.consecutive} sources in a row came back from the agent with NO wiki changes "
            f"(starting at {config.display_key(self.first_key)}). That is the signature of an agent "
            "CLI that runs but cannot do its work — check `citadel doctor`, then run the CLI by hand "
            "once to confirm it can still write files and launch tools (a self-update can silently "
            "take that away mid-run). Remaining sources were NOT attempted, so no further sessions "
            "were billed: they stay pending and a plain re-run picks them up. The empty ones above "
            "were marked done and need `citadel ingest --retry`. Set CITADEL_STALL_LIMIT=0 to "
            "disable this check."
        )


@dataclass
class _JobRun:
    """One ATTEMPT at one source, as the driver sees it — the value a worker hands back.

    Exactly one of the three outcome fields is set: ``prepare_exc`` (planning raised — a per-source
    failure, never a run-aborting one), ``interrupt`` (a ``BaseException`` such as Ctrl+C escaped the
    session runner, which already rolled the source back), or ``outcome`` (the session runner's
    verdict, including a ``conflict`` that asks for a serial re-run). ``index``/``total`` are the
    source's position in its group — carried on the run so a re-run keeps the number the progress
    output already showed."""

    job: _SourceJob
    index: int
    total: int
    outcome: _SourceOutcome | None = None
    prepare_exc: Exception | None = None
    interrupt: BaseException | None = None


def _attempt_source(job: _SourceJob, index: int, total: int, emit, concurrent: bool) -> _JobRun:
    """Plan and run ONE source's session(s) — the whole minutes-long part — and return what
    happened, touching NO shared bookkeeping. That is what makes it safe to call from a worker
    thread under ``--jobs N``: the report, the manifest and the failures catalog are the main
    thread's alone (:func:`_record_source_run`), so nothing here needs a lock beyond the live-wiki
    one the session runner takes around its clone and promote."""
    # Keep the run lock's mtime fresh at every source boundary, so a long multi-source run never
    # crosses the staleness window another process could reclaim the lock through.
    runlock.heartbeat()
    emit("source_start", index=index, total=total, source=job.key)
    run = _JobRun(job=job, index=index, total=total)
    # Plan the session(s). A prepare failure (a temp write, a digest build) is a per-source error,
    # NOT a run-aborting one.
    try:
        sessions, tmpdirs, resume_ctx = job.build_sessions()
    except Exception as exc:  # noqa: BLE001 - per-source, keep going
        run.prepare_exc = exc
        return run

    def on_segment(part: int, parts: int) -> None:
        """Announce which PASS of a chunked source is starting.

        Only for a source that actually has several (``parts > 1``): a single-pass source's
        ``source_start`` already said everything there is to say, and an unconditional
        ``1/1`` would be noise on every ordinary source. A chunked one is the opposite case —
        one agent session per segment, each of which can run for hours — so without this its
        console row shows the same file and a spinner from the first pass to the last."""
        if parts > 1:
            emit("source_segment", index=index, total=total, source=job.key, part=part, parts=parts)

    try:
        run.outcome = _run_agent_sessions(
            sessions,
            job.key,
            extra_check=job.extra_check,
            allow_emptying=job.allow_emptying,
            resume_ctx=resume_ctx,
            concurrent=concurrent,
            on_segment=on_segment,
        )
    except BaseException as exc:  # noqa: BLE001 - Ctrl+C etc.: runner rolled back; captured
        run.interrupt = exc
    finally:
        # Always remove every temp dir the plan produced (success, error, or interrupt).
        for tmp in tmpdirs:
            shutil.rmtree(tmp, ignore_errors=True)
    return run


def _record_spend(outcome: _SourceOutcome, report: IngestReport) -> None:
    """Book what one attempt COST and what it REUSED — the two facts that hold whatever its verdict
    was, so they have exactly one owner instead of one per branch.

    The run's usage total counts every outcome: a failed (or raced) source's sessions were paid for
    too; only the per-source manifest stamp is success-only. A restored checkpoint is recorded the
    same way — the earlier segments were reused whether or not this attempt went on to promote.

    Called from :func:`_record_source_run` and, separately, from the ``--jobs N`` conflict path,
    whose source is re-run serially instead of being recorded: it still spent a session and may
    still have replayed a checkpoint, and a report that hid that would be understating the run.
    Deliberately NOT wired through the interrupt path: an interrupted run re-raises and its report
    is never rendered (_ingest_run's capture-finalize-reraise), so the in-flight source's partial
    usage has no surface to appear on — the completed sources' manifest stamps were already saved
    per-source with their usage intact."""
    report.usage = llm.combine_usage([report.usage, outcome.usage])
    # The first session that NAMES its model upgrades the report's label from "what we asked for"
    # to "what actually ran" (the manifest entries are stamped with the same id per source).
    if isinstance(outcome.usage, llm.SessionUsage) and outcome.usage.model:
        report.model = config.model_label_for(outcome.usage.model)
    if outcome.resumed_note:
        report.resumed.append(outcome.resumed_note)


def _record_source_run(run: _JobRun, emit, report: IngestReport, failures_dict, model, stall=None) -> None:
    """Book ONE finished attempt into the run's shared state — report lists, the persistent
    failures catalog, the job's success hook (manifest stamp + save), and the closing progress
    event. MAIN THREAD ONLY, so the manifest/failures/report writes stay single-threaded exactly as
    they were before ``--jobs N``; the concurrency lives entirely in :func:`_attempt_source`.

    Page changes reach the report only on success — a failed or interrupted source promotes
    nothing, so the report claims nothing for it. A ``conflict`` outcome never reaches here: the
    driver re-runs that source serially first.

    ``stall`` (the run's :class:`_StallGuard`) is fed every recorded SUCCESSFUL outcome here by
    the serial driver; the parallel driver passes ``stall=None`` and instead feeds the guard from
    the WORKER the moment an attempt completes (see :func:`_run_source_jobs_parallel`) — recording
    lags completion there, and a guard that trips only when the main thread catches up cannot stop
    dispatch in time. The DRIVERS then check ``stall.tripped`` to stop dispatching."""
    job, index, total = run.job, run.index, run.total
    sha, st = job.sha_stat
    if run.prepare_exc is not None:
        detail = f"{job.key}: {job.prepare_error}: {run.prepare_exc}"
        report.errors.append(detail)
        failures.record(failures_dict, job.key, failures.ERROR, detail, model, sha=sha, st=st)
        emit("source_error", index=index, total=total, source=job.key, error=str(run.prepare_exc), seconds=0.0)
        return
    outcome = run.outcome
    if outcome is None:  # an interrupted attempt: the caller re-raises, nothing to book
        return
    _record_spend(outcome, report)  # cost + any restored checkpoint, before the ok/failed branch
    if not outcome.ok:
        # Nothing was promoted (the live wiki is untouched) and the source is NOT marked
        # done, so it is retried next run. Persist the failure for triage.
        report.errors.extend(outcome.errors)
        if job.failure_hint and job.failure_hint not in report.failure_hints:
            report.failure_hints.append(job.failure_hint)
        detail = outcome.errors[0] if outcome.errors else f"{job.key}: agent session failed"
        failures.record(failures_dict, job.key, failures.reason_for(detail), detail, model, sha=sha, st=st)
        emit(
            "source_error",
            index=index,
            total=total,
            source=job.key,
            error=outcome.errors[0] if outcome.errors else "",
            seconds=outcome.seconds,
        )
        return
    if stall is not None:
        stall.note(job, outcome)
    report.pages_created.extend(outcome.created)
    report.pages_updated.extend(outcome.updated)
    report.pages_written.extend(outcome.created + outcome.updated)
    report.pages_deleted.extend(outcome.deleted)
    for issue in outcome.carried_issues:
        if issue not in report.inherited_issues:
            report.inherited_issues.append(issue)
    if job.warn_no_pages and not (outcome.created or outcome.updated or outcome.deleted):
        # A fresh source folded in with zero page changes: marked done below, so without this
        # warning it would silently never contribute anything (see IngestReport.no_pages).
        report.no_pages.append(job.key)
    # The manifest stamp covers every session whose work this promote landed — this run's plus
    # whatever an earlier run already paid for the segments a checkpoint restored — while
    # ``report.usage`` above stays strictly this run's spend, so nothing is double-counted
    # across runs and `citadel status` never under-reports a resumed source.
    stamped = llm.combine_usage([outcome.usage, outcome.carried_usage])
    job.on_success(stamped, outcome.seconds)
    emit(
        "source_done",
        index=index,
        total=total,
        source=job.key,
        created=len(outcome.created),
        updated=len(outcome.updated),
        deleted=len(outcome.deleted),
        seconds=outcome.seconds,
        # The console reports what THIS run spent (matching the run report's total), but names the
        # model from the full stamp — a resumed source's model is known even when every segment
        # this run ran came back from a checkpoint.
        usage=outcome.usage,
        model=getattr(stamped, "model", None),
    )


def _run_source_jobs(
    jobs: list[_SourceJob], emit, report: IngestReport, failures_dict, model, workers: int = 1, stall=None
) -> BaseException | None:
    """Drive one GROUP of :class:`_SourceJob`s (deletion cleanups, files, or repos) through the
    ONE shared per-source loop: emit ``source_start``, plan the session(s), run them all-or-nothing
    against a single staging copy, then either record the failure (report + persistent failures
    catalog + ``source_error``) or run the job's success bookkeeping and emit ``source_done``.

    The progress vocabulary is frozen (pinned by tests): ``index``/``total`` count within THIS
    group, restarting at 1 per group, and the event payload keys are exactly what the three
    former loops emitted. The one addition is ``source_segment`` (``part``/``parts`` on top of
    those keys), fired between a chunked source's ``source_start`` and its verdict — a purely
    additive event a consumer that does not know it simply ignores. Page changes reach the report only on success — a failed or interrupted
    source promotes nothing, so the report claims nothing for it.

    ``workers`` > 1 (``citadel ingest --jobs N``) runs that many sources CONCURRENTLY — see
    :func:`_run_source_jobs_parallel`. ``workers`` of 1, and any group of a single source, take the
    serial path, which is the original loop line for line.

    A ``BaseException`` (Ctrl+C) is RETURNED, not raised — the caller captures it, skips the
    remaining groups, finalizes the completed sources, and re-raises (the frozen
    capture-finalize-reraise pattern). The in-flight source was already rolled back by the
    session runner's ``finally``.

    ``stall`` (:class:`_StallGuard`) stops dispatching entirely once the agent has proven it is not
    doing its work; the un-attempted sources stay pending for the next run."""
    if workers <= 1 or len(jobs) <= 1:
        return _run_serially(list(enumerate(jobs, 1)), len(jobs), emit, report, failures_dict, model, stall)
    return _run_source_jobs_parallel(jobs, emit, report, failures_dict, model, workers, stall)


def _run_serially(
    numbered: list[tuple[int, _SourceJob]], total: int, emit, report: IngestReport, failures_dict, model, stall=None
) -> BaseException | None:
    """Run ``(index, job)`` pairs one after another — the whole serial path, and the tail of the
    parallel one (a source whose promote raced another is re-run here, keeping its original
    index/total so the progress numbering stays honest)."""
    for index, job in numbered:
        if stall is not None and stall.tripped:
            # The agent is not doing its work: every further source would only buy another empty
            # session. Stop BEFORE spawning it — the caller reports why and leaves the rest pending.
            return None
        run = _attempt_source(job, index, total, emit, concurrent=False)
        if run.interrupt is not None:
            return run.interrupt
        _record_source_run(run, emit, report, failures_dict, model, stall)
    return None


def _run_source_jobs_parallel(
    jobs: list[_SourceJob], emit, report: IngestReport, failures_dict, model, workers: int, stall=None
) -> BaseException | None:
    """Run one group's sources through a bounded thread pool, then re-run serially whichever of
    them raced another source's promote.

    What each worker does is exactly what the serial loop does — plan, stage, run the session(s),
    validate, promote — with two differences, both inside :func:`_run_agent_sessions`: the clone and
    the promote take :data:`_LIVE_WIKI_LOCK`, and the promote is checked against the state its clone
    was taken from. Everything a run SHARES (report lists, the manifest, the failures catalog) is
    written here on the main thread as results arrive, so those writes stay serial and the manifest
    is still saved per completed source.

    Sources are folded in in COMPLETION order, which is not submission order — the wiki is a set of
    pages, not a log, so nothing depends on it; the report's lists simply read in the order sources
    finished.

    Interrupts: a Ctrl+C reaches the main thread (and, being in the same process group, the agent
    subprocesses too). The first ``BaseException`` from either side wins — queued sources are
    cancelled and their workers told to stop before starting anything new, in-flight ones roll
    themselves back — and it is returned for the caller's capture-finalize-reraise. Sources that had
    already finished cleanly are still recorded, so an interrupt never throws away work the run
    already paid for and promoted."""
    total = len(jobs)
    abort = threading.Event()
    interrupt: BaseException | None = None
    conflicted: list[tuple[int, _SourceJob]] = []
    recorded: set[int] = set()

    def attempt(index: int, job: _SourceJob) -> _JobRun | None:
        # A cancelled-too-late worker must not start a session: once the run is aborting, the only
        # correct thing a queued source can do is nothing at all. The stall guard is read here as
        # well as in the recording loop, and for the same reason it is read at all: a worker that
        # picks up the next source in the window between the guard tripping and the main thread
        # cancelling would otherwise buy one more session from an agent already known to be broken.
        if abort.is_set() or (stall is not None and stall.tripped):
            return None
        run = _attempt_source(job, index, total, emit, concurrent=True)
        # Feed the guard HERE, at completion time, not when the main thread records the result:
        # with instant-failing sessions (the exact broken-agent signature the guard exists for)
        # the workers would otherwise drain the whole queue before the main thread has recorded
        # the third empty outcome — billing the corpus the guard was built to protect. Only the
        # outcomes the recording path would note qualify: a successful, non-conflict attempt
        # (a conflict is re-run serially and noted there; a failed source is no evidence).
        if stall is not None and run.outcome is not None and run.outcome.ok and not run.outcome.conflict:
            stall.note(job, run.outcome)
        return run

    with futures.ThreadPoolExecutor(max_workers=min(workers, total), thread_name_prefix="citadel-ingest") as pool:
        submitted = [pool.submit(attempt, index, job) for index, job in enumerate(jobs, 1)]
        try:
            for future in futures.as_completed(submitted):
                if future.cancelled():
                    # A cancelled future is only ever produced by the abort below, so its
                    # `CancelledError` would be caught there and discarded in favour of the
                    # interrupt that caused it — correct, but only by that reasoning. Skipping it
                    # here (as the drain loop already does) keeps the property local: `result()` is
                    # called on completed work only.
                    continue
                run = future.result()
                if run is None:
                    continue
                if run.interrupt is not None:
                    interrupt = interrupt if interrupt is not None else run.interrupt
                    abort.set()
                    for pending in submitted:
                        pending.cancel()
                    continue
                if run.outcome is not None and run.outcome.conflict:
                    # Nothing was promoted, so this attempt is NOT recorded as a source outcome —
                    # but what it spent and what it replayed are facts of this run either way, and
                    # the source goes into the serial tail below (where it can no longer race
                    # anybody).
                    _record_spend(run.outcome, report)
                    report.raced.append(run.job.key)
                    conflicted.append((run.index, run.job))
                    emit("source_retry", index=run.index, total=total, source=run.job.key, seconds=run.outcome.seconds)
                    continue
                # stall=None: the worker already noted this outcome at completion time (above) —
                # noting again here would double-count it.
                _record_source_run(run, emit, report, failures_dict, model)
                recorded.add(run.index)
                if stall is not None and stall.tripped:
                    # Same shape as the interrupt path, and for the same reason — there is no point
                    # spending on work that cannot succeed — but it is NOT an interrupt: queued
                    # sources are cancelled (their `attempt` returns before starting a session),
                    # in-flight ones finish and are recorded normally, and the run ends cleanly with
                    # everything already promoted intact.
                    abort.set()
                    for pending in submitted:
                        pending.cancel()
        except BaseException as exc:  # noqa: BLE001 - Ctrl+C while waiting: stop dispatching
            interrupt = interrupt if interrupt is not None else exc
            abort.set()
            for pending in submitted:
                pending.cancel()
        # Leaving the `with` joins whatever is still running (their sessions roll back on the same
        # interrupt); their results are drained below rather than dropped.
    if interrupt is not None:
        for future in submitted:
            if not future.done() or future.cancelled():
                continue
            with contextlib.suppress(Exception):
                run = future.result()
                # Only completed, PROMOTED work is booked during an abort: it is already on the live
                # wiki, so leaving it out of the manifest would just make the next run pay again.
                if run is not None and run.outcome is not None and run.outcome.ok and run.index not in recorded:
                    _record_source_run(run, emit, report, failures_dict, model)
                    recorded.add(run.index)
        return interrupt
    if conflicted:
        # The serial tail: no other source can be promoting now, so these re-runs see the wiki the
        # winner left behind and merge into it — the result a serial run would have produced.
        return _run_serially(
            sorted(conflicted, key=lambda pair: pair[0]), total, emit, report, failures_dict, model, stall
        )
    return None


def retry_candidates() -> tuple[list[str], list[str]]:
    """The source keys ``citadel ingest --retry`` re-runs, as ``(failed, uncited)``.

    - ``failed``: every source in the failures catalog that is still on disk — errored / timed-out
      / unreadable records alike (an unchanged unreadable file is re-evaluated for free, and a
      fixed one — hydrated placeholder, re-exported document — now ingests). Deliberate skips
      stay skipped: a same-basename ``duplicate`` record is a decision, not a failure, and a
      ``curate`` record is keyed by a PAGE, not a source (``citadel curate --retry`` owns those).
    - ``uncited``: every INGESTED source that no wiki page cites (the same
      ``store.citing_pages_map`` verdict as the ``Referenced by`` column of
      ``wiki/sources/index.md``, and ``citadel status``'s ``NO PAGES`` marker) — a session was
      paid for, the source is marked done, and yet nothing in the wiki carries its facts. These
      are re-run as FORCED reconciles.

    Both lists are sorted and disjoint (a key can only be in one catalog); vanished files are
    excluded — a retry cannot read what is not there (a vanished INGESTED source is the deletion
    sweep's job, not a retry's). Read-only: computing candidates changes nothing. Best-effort
    like ``status``'s marker: a wiki that cannot be traversed degrades to an empty ``uncited``
    list instead of taking the recovery command down — the failed sources are still retried,
    which is exactly the situation ``--retry`` exists for."""
    failed: list[str] = []
    for key, entry in sorted(failures.load().items()):
        if not isinstance(entry, dict):
            continue
        if entry.get("reason") in (failures.DUPLICATE, failures.CURATE):
            continue
        if config.source_path_for_key(key).exists():
            failed.append(key)
    manifest_dict = manifest.load()
    uncited: list[str] = []
    if manifest_dict:
        try:
            refs = store.citing_pages_map(list(manifest_dict))
        except Exception:  # noqa: BLE001 - recovery must degrade, never crash on a broken wiki
            refs = None
        if refs is not None:
            uncited = [
                key for key in sorted(manifest_dict) if not refs.get(key) and config.source_path_for_key(key).exists()
            ]
    return failed, uncited


@pagecache.bypass
def ingest(
    paths: list[str] | None = None,
    progress=None,
    full_rescan: bool = False,
    force: bool = False,
    jobs: int | None = None,
    reingest: bool = False,
) -> IngestReport:
    """Run one ingest. Exactly one source = one all-or-nothing agent job (a chunked source runs
    several ``llm.run_ingest_session`` passes inside that one job).

    Before the per-source loop, candidates are partitioned (``_partition_sources``) into
    pending / already-ingested / **reorganized** (a file that only moved or is a byte-for-byte
    duplicate — recognized, not re-ingested; a real move repoints the wiki's resource/citation
    references and re-keys the manifest) / **unreadable** (no extractable text, e.g. a binary —
    logged and marked done, never fed to the agent; an all-NUL cloud-only placeholder is instead
    kept re-evaluated so it ingests once hydrated) / **deleted** (a tracked source that
    vanished from disk — full runs only). Discovery is incremental: the manifest doubles as the
    scan cache, so an unchanged corpus is skipped on stat alone (``full_rescan=True`` — the
    ``--full-rescan`` flag — distrusts that cache and re-hashes everything; sha stays the sole
    arbiter, so unchanged sources are re-stamped, not re-ingested).

    ``force`` (the ``--force`` flag) deliberately re-reads the
    requested sources even when nothing changed: the quick check AND the sha short-circuit are
    bypassed, so a sha-matching tracked source lands in pending and runs ``kind="reconcile"``,
    a tracked repo at its stored commit runs ``kind="repo-reconcile"`` over a FULL re-digest
    (never a first-time brief — the rationale lives on :func:`_partition_repos`), a persisted
    UNREADABLE/ERROR failure record is re-evaluated (and cleared on success), and a
    dedup-dropped key is ingested exactly as requested (the report records the divergence).
    On success the manifest is re-stamped with the CURRENT model + rules_version — the point of
    forcing after a model/rules upgrade. One short-circuit force deliberately does NOT bypass: a
    chunked source's resume checkpoint (:func:`_resume_context`). Forcing is what ``citadel
    refresh`` drives, and an interrupted forced re-read is exactly the expensive job worth
    continuing rather than re-buying; a checkpoint from a NON-forced run can't be adopted anyway,
    since forcing changes the session kind. ``force`` without explicit paths is refused HERE with a
    ValueError (one agent session per source must never hit the whole corpus by accident; the
    CLI pre-empts it with the same message and a friendly exit 2), and a path-scoped run never
    sweeps deletions (``swept_roots=None`` below).

    ``reingest`` (the ``--reingest`` flag) goes one deliberate step past ``force``: instead of
    reconciling the named tracked sources around their existing treatment, each is re-imported
    FRESH — first a ``kind="delete"`` cleanup session strips its previous facts from the wiki and
    its manifest key is dropped, then (same run, deletions always run first) the source lands in
    pending as a brand-new key and runs a plain ``kind="ingest"`` session (``kind="repo"`` for a
    tracked repo — the cleanup already removed the pages a first-time brief would otherwise
    duplicate). That is the escape hatch from reconcile's keep-the-existing-genre-treatment rule:
    the source is re-thought from scratch against the CURRENT wiki and rules (e.g. after a model
    upgrade or a new genre), at the cost of a cleanup session plus a full ingest session per
    source. Like ``force`` it requires explicit paths (same ValueError here, same CLI exit 2) and
    implies force's partitioning (sha short-circuit and dedup drop bypassed). If the cleanup
    session fails, the fresh ingest for that source is refused (a per-source failure, retried by
    re-running ``--reingest``) — new pages are never written on top of the old facts.

    Deletion detection is guarded (operational safety over
    thoroughness): candidates come from the walked-seen-set diff, each positively confirmed with
    ``.exists()``; any walk error aborts the entire sweep for the run; an unreachable root
    contributes no candidates; keys under no configured root are logged, never swept; and a
    workspace-identity mismatch whose keys do not resolve refuses the sweep outright.

    Per pending source: the agent's pass(es) run all-or-nothing against a per-source STAGING
    copy, promoted once per source — the full story lives on :func:`_run_agent_sessions`.
    A source already tracked in the manifest but with new bytes is a re-ingest, run with
    ``kind="reconcile"`` so the agent UPDATES/REMOVES the stale facts it produced rather than
    only appending. On a per-source exception (a missing/unusable CLI, a timeout, etc.) — or a
    Ctrl+C — nothing is promoted, the error is collected, and the source is retried next run.

    Per deleted source (full run only, run BEFORE the pending sources): if any wiki page still
    cites it, run a ``kind="delete"`` cleanup session that strips those facts/citations, gated by
    a post-condition that the wiki no longer references it (else the whole cleanup is rolled back
    and retried); then drop its manifest key. A deleted source nothing cites is simply dropped
    from the manifest. Running deletions first is load-bearing (the per-source-job group-order
    comment in the body carries the full why). Finalization
    (rebuild_indexes + find_broken_links + append_log) happens once, if any source was processed,
    reorganized, found unreadable, or removed.

    The per-source loop itself is ONE shared implementation (:class:`_SourceJob` +
    :func:`_run_source_jobs`): deletion cleanups, files, and repos differ only in how their
    sessions are planned and in their post-success bookkeeping.

    ``jobs`` (``citadel ingest --jobs N``; None takes :data:`config.JOBS`, default 1) is how many
    sources may be folded in CONCURRENTLY. 1 is the strictly serial behavior citadel has always
    had. Above 1, each source still gets its own staging copy and its own all-or-nothing promote —
    what changes is that N of them are in flight at once, promoting one at a time against the wiki
    state they were cloned from; a source whose promote raced another one over the same page is
    re-run serially before the run ends (``report.raced``). Every guarantee is unmoved: one promote
    per source, nothing partial on the live wiki, the manifest still saved per completed source. The
    real cost is cross-linking — concurrent sessions cannot see each other's new pages — which is
    why the default stays 1 and the knob is documented as a throughput trade, not a free win.

    ``progress`` is an optional ``progress(event, data)`` callback (run start, before/after
    each source, before finalization); None for non-interactive callers. A failing callback
    never breaks ingest.
    """
    workers = config.JOBS if jobs is None else jobs
    if workers < 1:
        raise ValueError(f"--jobs must be at least 1 (got {workers}); 1 means the serial default.")
    if force and not paths:
        # The API-layer twin of the CLI's exit-2 refusal (which pre-empts this with the same
        # message), so a programmatic caller cannot force the whole corpus by accident either.
        # The MCP server's wiki_ingest does not expose force at all.
        raise ValueError(
            "--force requires explicit paths (a forced re-read runs one agent session per "
            "source; name the files or directories to force, e.g. `citadel ingest --force raw/notes.md`)."
        )
    if reingest and not paths:
        # Same guard, sharper teeth: a reingest costs a cleanup session PLUS a full ingest
        # session per source, so a whole-corpus reingest by accident is twice as expensive.
        raise ValueError(
            "--reingest requires explicit paths (each source runs a delete cleanup session plus "
            "a fresh ingest session; name the files or directories to re-import, e.g. "
            "`citadel ingest --reingest raw/notes.md`)."
        )

    # ONE mutating run per workspace: the staging sweep, promote's prune, and the manifest/
    # failures saves are all destructive under concurrency (see runlock's module docstring).
    # A second run fails loud here instead of silently eating the first one's work.
    with runlock.hold("ingest"):
        _sweep_stale_staging(config.wiki_dir())
        # Same place, same reason: under the exclusive lock, leftovers on disk belong to dead runs.
        # Age-based only — a checkpoint's own guards decide whether it is USABLE (see resume.sweep).
        resume.sweep()
        return _ingest_run(paths, progress, full_rescan=full_rescan, force=force, jobs=workers, reingest=reingest)


def _ingest_run(
    paths: list[str] | None, progress, *, full_rescan: bool, force: bool, jobs: int = 1, reingest: bool = False
) -> IngestReport:
    """The body of :func:`ingest`, running under the exclusive workspace run lock."""

    # A reingest rides force's partitioning wholesale (sha short-circuit and dedup drop bypassed,
    # stat cache distrusted for the named paths); what it changes beyond force — the cleanup jobs
    # and the fresh session kinds — is keyed off `reingest`/`reingest_keys` below.
    force = force or reingest

    # `--jobs N` emits from WORKER threads (a source's start/done event fires where the work
    # happens), so the callback — which is whatever the caller passed — is serialized here. That
    # keeps "your progress callback is never invoked concurrently" a property of the API rather than
    # something each caller has to discover, and it costs nothing: emit fires a handful of times per
    # source, around sessions that take minutes. The console reporter is safe under it either way
    # (its writes are locked, and rich gives each in-flight source its own live row), but the
    # contract must not depend on that reasoning holding for every future callback.
    emit_lock = threading.Lock()

    def emit(event: str, **data) -> None:
        if progress is None:
            return
        with emit_lock:
            try:
                progress(event, data)
            except Exception:  # noqa: BLE001 - progress must never break ingest
                pass

    # ONE manifest parse: load() stashes the file's meta, and the mismatch probe reads that
    # stash — taken BEFORE anything saves (a save re-stamps meta with the CURRENT root, which
    # would blind the identity guard below to the mismatch it must catch).
    manifest_dict = manifest.load()
    workspace_mismatch = manifest.stamped_workspace_mismatch()
    # Persistent record of sources that could not be ingested (unreadable / errored / timed out).
    # Updated through the run and rewritten at the end, so it always reflects the CURRENT stuck set.
    failures_dict = failures.load()
    failures_before = {k: dict(v) if isinstance(v, dict) else v for k, v in failures_dict.items()}
    # Migration sweep: drop any entry a PREVIOUS run recorded for a source that must not be tracked
    # at all — a now-ignored junk file (Thumbs.db & friends, recorded before that feature existed)
    # or a path inside the WIKI (a page self-ingested by a layout whose raw root sits above the wiki,
    # before the discovery guard existed). Both still exist on disk, so a full run would never
    # re-detect them as deleted — clean them out of the manifest AND the failures catalog directly
    # so wiki/sources/index.md stops carrying the noise.
    pruned_ignored = False
    for key in [k for k in manifest_dict if _is_untrackable_key(k)]:
        del manifest_dict[key]
        pruned_ignored = True
    for key in [k for k in failures_dict if _is_untrackable_key(k)]:
        failures.clear(failures_dict, key)
        pruned_ignored = True
    if pruned_ignored:
        # Persist BOTH catalogs together, so an early exit (Ctrl+C / an unexpected error before
        # finalization) can't leave the manifest cleaned while the failures catalog still carries
        # the junk keys — the two would then disagree until the next run reconciled them.
        manifest.save(manifest_dict)
        failures.save(failures_dict)
    # The model/backend that will import this run's sources — recorded per-source in the manifest
    # so you can see which raw file was imported by which model. Resolved once (it does not change
    # mid-run) and read at call time so tests can monkeypatch the backend/model. Likewise the
    # content hash of the effective rules tree the sessions run under — stamped per source so a
    # later `curate --stale-rules` can find sources ingested under older rules; computed ONCE (the
    # rules do not change mid-run and hashing them per source would re-read the tree needlessly).
    model = config.ingest_model_label()
    rules_ver = config.rules_version()
    report = IngestReport([], [], [], [], model=model)

    # --- The workspace-identity HARD guard (key-space stability): the manifest was stamped by
    # a DIFFERENT workspace root AND most of its relative keys do not resolve here
    # (``manifest.workspace_rekeyed``) — a nested marker or a moved checkout re-keyed the world,
    # so the seen-set diff would read the entire old key space as deleted. Refuse the deletion
    # sweep (ingest of pending sources still proceeds); the dual-mount case (stamp differs but
    # keys resolve) stays a warning. ---
    workspace_shifted = bool(paths is None and workspace_mismatch and manifest.workspace_rekeyed(manifest_dict))
    if workspace_shifted:
        report.errors.append(
            f"workspace mismatch: the manifest was stamped by a workspace rooted at "
            f"{workspace_mismatch!r}, and most of its keys do not resolve under the current "
            f"root — refusing deletion detection so a re-keyed manifest is not read as mass "
            f"deletion. If the move is intentional, run `citadel ingest --full-rescan` once: the "
            f"sweep stays off for that run, but the manifest is re-stamped at its end so the "
            f"next run is clean (or re-init the workspace)."
        )

    if full_rescan and paths is None:
        # A full re-hash of a big corpus on a slow share takes a while — announce it so the run
        # does not look hung.
        print("NOTE: --full-rescan: re-hashing every tracked source (sha256 still decides).", file=sys.stderr)
    walk = _discover_walk(paths)
    # The ONE sweep decision: None = NO deletion sweep this run — a path-scoped run, a
    # degraded walk (any error anywhere has an unknown blast radius), or the workspace guard
    # above — else exactly the roots discovery ENTERED (an unreachable root contributes no
    # candidates). Passed to BOTH the file and the repo partition; every remaining guard
    # (root scoping, positive .exists() confirmation) lives in _sweep_gone.
    swept_roots: list[Path] | None = None
    if paths is None and not workspace_shifted and not walk.errors:
        swept_roots = list(walk.entered_roots)
    scan = _partition_sources(
        paths, manifest_dict, failures_dict, full_rescan, walk=walk, swept_roots=swept_roots, force=force
    )
    if scan.mutated:
        # The quick check refreshed/backfilled stat caches on unchanged entries: persist them now
        # so the very next run reads no content for these files, even if nothing else happens.
        manifest.save(manifest_dict)

    # Git repositories under raw/ are ingested as ONE source each (a digest), versioned by commit.
    # Discover + partition them alongside the file sources; a vanished repo folder is reconciled out
    # by the SAME deletion-cleanup path as a file (its citations point at the repo folder key), and
    # its deletion sweep is scoped by the same one swept_roots decision.
    repo_paths = _discover_repos(paths, walk)
    repo_pending, repo_moved, repo_deleted, repo_skipped, repo_out_of_root = _partition_repos(
        repo_paths, manifest_dict, swept_roots, force=force
    )
    report.skipped = scan.skipped + repo_skipped
    deleted_sources = scan.deleted + repo_deleted
    out_of_root = scan.out_of_root + repo_out_of_root

    # --- Deletion-sweep skip notes: whenever tracked sources were EXCLUDED from deletion
    # detection this run, say so loudly — silence here would look like "nothing was deleted"
    # when the truth is "deletion detection did not run for these". ---
    if paths is None:
        if walk.errors:
            print(
                "NOTE: the raw scan hit errors; deletion detection is skipped for this whole run "
                "(tracked sources are kept and re-checked next run):\n  " + "\n  ".join(walk.errors),
                file=sys.stderr,
            )
        for root in walk.unreachable:
            print(
                f"NOTE: raw root {root} is unreachable (not mounted?); its sources are kept — "
                "deletion detection for them is skipped this run.",
                file=sys.stderr,
            )
        if out_of_root:
            print(
                "NOTE: tracked source(s) under no configured raw root — never swept by deletion "
                "detection:\n  " + "\n  ".join(sorted(out_of_root)),
                file=sys.stderr,
            )
    if scan.unreadable_tracked:
        print(
            "NOTE: already-ingested source(s) could not be re-read this run (permissions / IO); "
            "kept as ingested and re-checked next run:\n  " + "\n  ".join(sorted(scan.unreadable_tracked)),
            file=sys.stderr,
        )
    # --- Discovery exclusions: both are deliberate skips, so say so rather than let the sources
    # simply not appear. The wiki note fires once per run (a raw root above the wiki prunes the
    # same tree at every level); the size note lists what the ceiling kept out. ---
    if walk.excluded_wiki:
        print(
            f"NOTE: the wiki directory ({config.WIKI_DIR}) is excluded from discovery - generated "
            "pages are never raw sources. If a raw root sits above the wiki, narrow "
            "CITADEL_RAW_DIRS (or move the wiki with CITADEL_WIKI_DIR) to silence this.",
            file=sys.stderr,
        )
    report.oversized = sorted((manifest.rel_key(p), size) for p, size in walk.oversized)
    if report.oversized:
        listed = [f"{key} ({_human_bytes(size)})" for key, size in report.oversized[:10]]
        if len(report.oversized) > len(listed):
            listed.append(f"... +{len(report.oversized) - len(listed)} more (all listed on the run report)")
        print(
            f"NOTE: {len(report.oversized)} file(s) skipped by CITADEL_MAX_SOURCE_BYTES "
            f"({_human_bytes(config.MAX_SOURCE_BYTES)}); raise it (or name a path explicitly) to "
            "ingest them:\n  " + "\n  ".join(listed),
            file=sys.stderr,
        )
    # The allowlist's own note. It fires on every run it filters anything, deliberately: unlike the
    # other exclusions this one is easy to get wrong in a way that looks like nothing to do (a typo
    # in CITADEL_INCLUDE_PATTERNS silently empties the corpus), so the count and the effective
    # patterns are always in front of the user.
    report.not_included = sorted(manifest.rel_key(p) for p in walk.not_included)
    if report.not_included:
        listed = report.not_included[:_NOT_INCLUDED_SHOWN]
        if len(report.not_included) > len(listed):
            listed = listed + [f"... +{len(report.not_included) - len(listed)} more"]
        print(
            f"NOTE: {len(report.not_included)} file(s) skipped by CITADEL_INCLUDE_PATTERNS "
            f"({', '.join(config.INCLUDE_PATTERNS) or '(none)'}) - only matching file names are "
            "read; widen it (or name a path explicitly) to ingest them:\n  " + "\n  ".join(listed),
            file=sys.stderr,
        )
    # A pending source whose key is ALREADY tracked is a re-ingest of changed bytes (reconcile);
    # one not yet tracked is brand new. Captured before the manifest is mutated below.
    pending_keys = {manifest.rel_key(p) for p in scan.pending}
    changed_keys = pending_keys & set(manifest_dict)
    # --reingest: every named TRACKED source is re-imported fresh instead of reconciled — a
    # delete-cleanup job (group 1, always before pending) strips its previous facts and drops its
    # manifest key, and emptying changed_keys here makes its pending session plan the plain
    # ingest/image/audio/pdf kind of a brand-new key. Tracked repos join reingest_keys below.
    reingest_keys: set[str] = set()
    if reingest:
        reingest_keys = set(changed_keys)
        changed_keys = set()
        # A tracked repo (force gave it kind="repo-reconcile") is re-imported fresh the same way:
        # cleanup first, then the FIRST-TIME brief over a full digest. kind="repo" is safe here
        # precisely because the cleanup precedes it — the pages a first-time brief would
        # otherwise duplicate are already stripped (contrast _partition_repos' force rule).
        repo_pending = [
            _RepoJob(path=r.path, key=r.key, kind="repo", old_commit=None) if r.old_commit else r for r in repo_pending
        ]
        reingest_keys.update(r.key for r in repo_pending if r.key in manifest_dict)

    # --- Reorganized sources: a file that only MOVED (or is a byte-for-byte duplicate) is
    # recognized and NOT re-ingested. For a real move (the old path is gone) repoint the wiki's
    # `resource` frontmatter and citation links to the new path so nothing breaks, then drop the
    # stale manifest key. Either way, record the new key so future runs skip it immediately. ---
    repointed = False
    for old_key, new_key, sha, old_gone in scan.moved:
        # A move/duplicate is NOT a re-ingest: carry over the model (and rules_version) that
        # originally imported this content (recorded under the old key) rather than stamping it
        # with this run's values. When the twin is itself pending in THIS run (two new copies
        # discovered together), the old key has no manifest entry yet — the twin will be stamped
        # with the run's values, so the duplicate carries the same ones instead of a permanent
        # None that `status` can't attribute and `--stale-rules` can never flag.
        carried_model = manifest.model_of(manifest_dict, old_key)
        carried_rules = manifest.entry_rules_version(manifest_dict.get(old_key))
        # ingested_at — and the cost/tokens usage stamp — are CARRIED only, never minted here:
        # unlike model/rules_version above, a fresh stamp would claim a session verified this
        # copy when none did (the pending twin's session may not even succeed). A duplicate left
        # stamp-less merely sorts to the front of `citadel refresh`'s queue — one re-verify
        # session later it is stamped honestly. (Read BEFORE the pop below.)
        carried_ingested = manifest.entry_ingested_at(manifest_dict.get(old_key))
        carried_usage = manifest.entry_usage(manifest_dict.get(old_key))
        if old_key not in manifest_dict and old_key in pending_keys:
            carried_model = carried_model or model
            carried_rules = carried_rules or rules_ver
        if old_gone and old_key != new_key:
            try:
                if store.rewrite_raw_references(old_key, new_key):
                    repointed = True
            except Exception as exc:  # noqa: BLE001 - collect, don't re-key, retry next run
                # Leave the manifest untouched so this move (and its repoint) is retried next
                # run rather than being silently recorded with stale references behind it.
                report.errors.append(f"{new_key}: repoint refs from {old_key}: {exc}")
                continue
            manifest_dict.pop(old_key, None)
            # The checkpoint store is keyed by source KEY, so a re-keyed source's slot can never be
            # adopted again (identity carries the key) — drop it here rather than leaving its page
            # text beside the wiki until the age sweep.
            resume.clear(old_key)
        moved_stat = scan.hashed[new_key][1] if new_key in scan.hashed else None
        manifest_dict[new_key] = manifest.make_entry(
            sha, carried_model, carried_rules, st=moved_stat, ingested_at=carried_ingested, **carried_usage
        )
        failures.clear(failures_dict, old_key)
        failures.clear(failures_dict, new_key)
        report.moved.append((old_key, new_key))
    # Repo moves: a repo whose folder was renamed (same base commit, old path gone). Repoint its
    # citations/`resource` to the new folder key and carry over its provenance — not a re-ingest.
    for old_key, new_key, ident in repo_moved:
        carried_model = manifest.model_of(manifest_dict, old_key)
        old_entry = manifest_dict.get(old_key)
        carried_remote = manifest.entry_remote(old_entry) if old_entry is not None else None
        carried_rules = manifest.entry_rules_version(old_entry)
        carried_ingested = manifest.entry_ingested_at(old_entry)
        carried_usage = manifest.entry_usage(old_entry)
        if old_key != new_key:
            try:
                if store.rewrite_raw_references(old_key, new_key):
                    repointed = True
            except Exception as exc:  # noqa: BLE001 - collect, don't re-key, retry next run
                report.errors.append(f"{new_key}: repoint refs from {old_key}: {exc}")
                continue
            manifest_dict.pop(old_key, None)
        manifest_dict[new_key] = manifest.make_repo_entry(
            ident, carried_model, carried_remote, carried_rules, ingested_at=carried_ingested, **carried_usage
        )
        report.moved.append((old_key, new_key))
    if report.moved:
        manifest.save(manifest_dict)

    # --- Unreadable sources: no extractable text (binary/unsupported). Mark them done (so they
    # are not re-checked and re-logged every run) and surface + log them — the file "did not
    # work", but it is not a hard error that should fail the whole run. ---
    for src in scan.unreadable:
        key = manifest.rel_key(src)
        if key not in scan.hashed:
            continue  # not even its hash could be read (OS error on a brand-new file): retry next run
        sha, src_stat = scan.hashed[key]
        report.unreadable.append(key)
        if _reads_as_cloud_placeholder(src):
            # A cloud-only placeholder: hydration restores the real content WITHOUT changing
            # size/mtime — and on Windows st_ctime is the stable creation time — so marking it
            # done would let the stat quick check skip the hydrated file forever. It lives only in
            # the failures catalog, and deliberately WITHOUT sha/stat: a cached sha that the quick
            # check trusts across a stat-stable hydration would thread the stale all-NUL sha into
            # mark_done. The cost is one re-hash of the still-stuck placeholder per run; the win is
            # that hydration always yields the real sha and the file ingests normally.
            report.cloud_placeholders.append(key)
            failures.record(
                failures_dict,
                key,
                failures.UNREADABLE,
                "reads as all NUL bytes - likely a cloud-only placeholder (Dropbox/OneDrive "
                "online-only file); make it available offline and re-run",
            )
            continue
        # No model imported it (it was only sniffed and skipped), so record the sha alone — with
        # the stat cache, so a later run skips the unchanged binary without a content read.
        manifest_dict[key] = manifest.make_entry(sha, None, st=src_stat)
        # Persist the failure so it survives the run (surfaced in wiki/sources/index.md; written by
        # the finalization step below, which an unreadable source always triggers). sha+stat let the
        # quick check recognize the unchanged file next run.
        failures.record(
            failures_dict, key, failures.UNREADABLE, "no extractable text (binary/unsupported)", sha=sha, st=src_stat
        )
    if scan.unreadable:
        manifest.save(manifest_dict)

    # --- Duplicate document sources: skipped in favor of another same-basename format (config
    # DEDUP_BY_BASENAME). Record them (report + persistent failures, with sha+stat so an unchanged
    # twin is never re-hashed) but do NOT mark them done, so a later run re-evaluates — deleting
    # the kept file promotes one of these. On a FORCED run nothing was dropped (the requested
    # file is ingested alongside its kept sibling), so the scan classified the pairs separately:
    # they reach the report purely as the divergence record naming that sibling — no DUPLICATE
    # failure is persisted (a stale one is cleared by the successful session below). ---
    for dropped_key, kept_key in scan.duplicates:
        report.duplicates.append((dropped_key, kept_key))
        dup_sha, dup_stat = scan.hashed.get(dropped_key, (None, None))
        failures.record(
            failures_dict,
            dropped_key,
            failures.DUPLICATE,
            f"same basename as {kept_key}, which was ingested instead",
            sha=dup_sha,
            st=dup_stat,
        )
    report.duplicates_forced.extend(scan.duplicates_forced)

    emit(
        "start",
        pending=len(scan.pending),
        skipped=len(report.skipped),
        moved=len(report.moved),
        unreadable=len(report.unreadable),
        deleted=len(deleted_sources),
        repos=len(repo_pending),
        jobs=jobs,
        # Each reingest source runs a cleanup JOB on top of its pending session — counted so the
        # overall progress total matches the jobs that will actually run.
        reingest=len(reingest_keys),
    )

    # --- The per-source jobs (the SourceJob loop): DELETION cleanups first, then files, then repos,
    # each group with its own index/total counters (frozen progress vocabulary). All three run
    # through the ONE shared loop (_run_source_jobs) + the ONE all-or-nothing session runner
    # (_run_agent_sessions); only session planning and post-success bookkeeping differ.
    # DELETIONS RUN BEFORE the pending sources (corpus-discovered fix, leuchtfeuer wave 3): a
    # delete cleanup strips a vanished source's stale provenance FIRST, so a later pending source
    # whose session touches a page that still cited the deleted source no longer fails validation
    # (bad_source) on that pre-existing stale citation and roll back fruitlessly — the pending
    # session now builds on a wiki the deletion already made consistent. Order is safe: every
    # group's members (incl. the deletion sweep) are computed by _partition_* BEFORE any session
    # runs, so no group's candidate set depends on another group having executed. ---

    def _file_job(src: Path) -> _SourceJob:
        rel_key = manifest.rel_key(src)
        is_image = src in scan.images
        is_audio = src in scan.audio
        # The (sha, stat) discovery already took — the source's ONE content read this run —
        # threaded to the failures catalog and, on success, to mark_done (never re-hashed).
        sha_stat = scan.hashed.get(rel_key, (None, None))
        # An already-tracked key is a re-ingest — new bytes, or a FORCED re-read of unchanged
        # ones: reconcile (update/remove stale facts) rather than only appending. A brand-new key
        # is a plain ingest. Image sources take the image propagation (the agent VIEWS them);
        # audio/video sources take the audio propagation (the agent reads the transcript).
        if is_image:
            kind = "image-reconcile" if rel_key in changed_keys else "image"
        elif is_audio:
            kind = "audio-reconcile" if rel_key in changed_keys else "audio"
        else:
            kind = "reconcile" if rel_key in changed_keys else "ingest"
        office = scan.office_text.get(src)

        def build() -> tuple[list, list[str], "_Resume | None"]:
            # A reingest source may only run its fresh session on a wiki its cleanup actually
            # cleaned: the cleanup job (group 1) pops the manifest key on success, so a key still
            # tracked here means that cleanup failed — refuse rather than write new pages on top
            # of the old facts (a per-source prepare failure; re-running --reingest retries both).
            if rel_key in reingest_keys and rel_key in manifest_dict:
                raise RuntimeError(
                    "the delete cleanup for this reingest failed, so its previous facts are "
                    "still in the wiki; fix that failure and re-run `citadel ingest --reingest`"
                )
            # Plan the pass(es): an Office source materializes its extracted text to a temp .md
            # the agent reads; an audio/video source is transcribed HERE through the whisper seam
            # (content-addressed cache; a raise is a retryable per-source prepare_error, and the
            # cache makes the retry free); a PDF's text layer is extracted HERE through the
            # (bundled) pypdf seam (same content-addressed cache idea; a None — no text layer,
            # unparsable, CITADEL_PDF_TEXT=0, or pypdf force-removed — quietly falls back to the
            # direct agent read, so the pre-pass can never cost a session); a source too large for
            # one context is SPLIT
            # into segments (promote-once per source — see _run_agent_sessions); anything else is
            # a single direct read.
            prepared = office
            run_kind = kind
            is_pdf = False
            if is_audio:
                prepared = transcribe.transcript_for(src, sha=sha_stat[0])
                # A transcription can take minutes: refresh the run lock afterwards so the
                # staleness window never has to absorb whisper time AND session time in one gap.
                runlock.heartbeat()
            elif prepared is None and pdftext.is_pdf_text_source(src):
                prepared = pdftext.text_for(src, sha=sha_stat[0])
                if prepared is not None:
                    # Only a source that ACTUALLY got an extraction takes the pdf propagation —
                    # the kind selects formats/pdf.md's prepared-extract rules (lines locators
                    # into the cached text); the fallback stays plain ingest/reconcile.
                    is_pdf = True
                    run_kind = "pdf-reconcile" if rel_key in changed_keys else "pdf"
            passes, tmpdirs = _prepare_passes(src, prepared, is_image, is_audio=is_audio, is_pdf=is_pdf)
            sessions = [
                (lambda rp=read_key, sg=segment, lw=window, k=run_kind: _pending_session(rel_key, k, rp, sg, lw))
                for read_key, segment, window in passes
            ]
            return sessions, tmpdirs, _resume_context(rel_key, run_kind, sha_stat[0], passes, model, rules_ver)

        def done(usage: llm.SessionUsage | None, seconds: float | None = None) -> None:
            # mark_done records exactly what discovery hashed (sha_stat above). On a forced
            # re-read this re-stamps the entry with the CURRENT model + rules_version. The
            # source's combined session usage (cost/tokens, when the backend reported any)
            # is stamped alongside — per-source cost observability — plus the wall-clock
            # seconds the run spent on this source (the only cost a local model has).
            done_sha, done_stat = sha_stat
            # A re-recorded/re-exported source leaves its OLD bytes' transcript/extraction orphaned
            # in the content-addressed cache — plaintext source content (SECURITY.md). Prune it by
            # the OLD sha once the new content is safely in, regardless of the NEW file's type: a
            # PDF re-exported as plain text (or an audio file replaced by a document) still orphans
            # the old entry, and gating on the current type would miss it (mirrors the delete path).
            # Each prune is a safe no-op when there is no entry for that sha, so a plain-text change
            # touches nothing. Guarded so a byte-identical sibling keeps the cache it still verifies.
            old_entry = manifest_dict.get(rel_key)
            old_sha = manifest.entry_sha(old_entry) if old_entry is not None else None
            if old_sha and old_sha != done_sha and not _sha_shared_by_other_entry(manifest_dict, old_sha, rel_key):
                transcribe.prune_cached(old_sha)
                pdftext.prune_cached(old_sha)
            manifest.mark_done(
                manifest_dict,
                src,
                _stamp_model(usage, model),
                rules_ver,
                sha=done_sha,
                st=done_stat,
                seconds=seconds,
                **_usage_fields(usage),
            )
            # A source that had failed before (unreadable/errored/duplicate) now succeeded: drop
            # its persisted failure record — and any resume checkpoint (the session runner already
            # clears the one it consumed; this also catches a slot left by an earlier run whose
            # source has since stopped being chunked).
            failures.clear(failures_dict, rel_key)
            resume.clear(rel_key)
            # Persist progress immediately after each completed source: a later Ctrl+C (or a
            # crash) must not erase sources already finished this run.
            manifest.save(manifest_dict)
            report.processed.append(rel_key)

        return _SourceJob(
            key=rel_key,
            build_sessions=build,
            on_success=done,
            prepare_error="prepare audio transcript" if is_audio else "write source text",
            sha_stat=sha_stat,
            # A brand-new key (not a reconcile of changed/forced bytes) that produces zero page
            # changes is worth a warning — see _SourceJob.warn_no_pages. It is also the evidence
            # the stall guard counts: a fresh source has no facts in the wiki yet, so an empty
            # session means the agent did not work, not that there was nothing to do.
            warn_no_pages=rel_key not in changed_keys,
            expects_changes=rel_key not in changed_keys,
        )

    # Repo sources: each git repository under raw/ is folded in by ONE session reading a
    # deterministic digest of its high-signal files. A re-ingest (a later commit) diffs against
    # the stored commit so only the changed files are inlined — except a FORCED re-read (the
    # run-level ``force``), which re-digests in FULL (see _partition_repos).
    def _repo_job(rjob: _RepoJob) -> _SourceJob:
        def build() -> tuple[list, list[str], "_Resume | None"]:
            # Same cleanup post-condition as _file_job's: a reingested repo whose cleanup failed
            # (key still tracked) must not run the first-time brief on top of its old pages.
            if rjob.key in reingest_keys and rjob.key in manifest_dict:
                raise RuntimeError(
                    "the delete cleanup for this reingest failed, so its previous facts are "
                    "still in the wiki; fix that failure and re-run `citadel ingest --reingest`"
                )
            only: list[str] | None = None
            change_summary: str | None = None
            if rjob.kind == "repo-reconcile" and rjob.old_commit and not force:
                changed = repo.changed_files(rjob.path, rjob.old_commit)
                if changed is not None:
                    only = changed
                    listing = "\n".join(changed) if changed else "(metadata only — no files)"
                    base = rjob.old_commit.split("+", 1)[0][:12]
                    change_summary = f"Changed files since {base}:\n{listing}"
            # Materialize the digest to a temp file the agent reads (citing the repo folder as
            # the source of record).
            digest = repo.build_digest(rjob.path, rjob.key, only=only, change_summary=change_summary)
            read_key, tmp = _office_write_temp(digest, rjob.path.name)
            sessions = [lambda rp=read_key: llm.run_ingest_session(rjob.key, kind=rjob.kind, read_path=rp)]
            return sessions, [tmp], None  # one session per repo digest: nothing to resume

        def done(usage: llm.SessionUsage | None, seconds: float | None = None) -> None:
            # On success the manifest records the repo's CURRENT commit identity, with a fresh
            # last-checked stamp (an agent session just verified this repo — the one event that
            # moves ingested_at), the session's usage stamp when the backend reported one, and
            # the wall-clock seconds the run spent on this repo.
            manifest_dict[rjob.key] = manifest.make_repo_entry(
                repo.identity(rjob.path),
                _stamp_model(usage, model),
                repo.remote_url(rjob.path),
                rules_ver,
                ingested_at=manifest.now_iso(),
                seconds=seconds,
                **_usage_fields(usage),
            )
            failures.clear(failures_dict, rjob.key)
            manifest.save(manifest_dict)
            report.processed.append(rjob.key)

        return _SourceJob(
            key=rjob.key,
            build_sessions=build,
            on_success=done,
            prepare_error="build digest",
            warn_no_pages=rjob.kind == "repo",  # a fresh repo digest yielding nothing is suspicious
            expects_changes=rjob.kind == "repo",
        )

    # Deleted sources: a tracked source vanished from disk (full run only). If any page still
    # cites it, run a `kind="delete"` cleanup session that strips that provenance, gated by a
    # post-condition that the wiki no longer references it (else the whole cleanup is rolled back
    # and retried next full run — the manifest key is dropped only on success). A deletion that
    # nothing cites plans NO session and just loses its manifest key. With ``reingest_cleanup``
    # the SAME job strips a still-on-disk source ahead of its fresh re-import (`--reingest`); the
    # bookkeeping differs only where the "source is gone" premise does not hold.
    def _delete_job(key: str, reingest_cleanup: bool = False) -> _SourceJob:
        def build() -> tuple[list, list[str], "_Resume | None"]:
            if not store.find_raw_references(key):
                return [], [], None  # nothing cites it: no cleanup session, just forget it below
            return [lambda: llm.run_ingest_session(key, kind="delete")], [], None

        def done(_usage: llm.SessionUsage | None, _seconds: float | None = None) -> None:
            # The cleanup session's usage lands only in the RUN total (report.usage) — the
            # source's manifest key is dropped, so there is no entry left to stamp.
            entry = manifest_dict.get(key)
            # The deleted source's cached transcript/extraction would sit orphaned forever — and
            # it holds the source's content in plaintext (SECURITY.md) — so prune it, but only
            # when NO other tracked source still shares those bytes (the cache is content-keyed;
            # a byte-identical sibling must keep the entry it verifies against). The file is gone,
            # so its bytes can't be re-sniffed: prune BOTH caches BY SHA — each is a safe no-op
            # when there is no entry for this sha (a plain-text delete touches nothing). Crucially
            # this must NOT gate on the extension: a PDF routes by %PDF- MAGIC (is_pdf_file), so it
            # can be cached under any name, and an ext gate would orphan its plaintext extraction.
            del_sha = manifest.entry_sha(entry) if entry is not None else None
            # ... except on a reingest cleanup: the source still exists with the SAME bytes, and
            # the fresh session moments away re-reads exactly the cached transcript/extraction —
            # pruning here would throw away work the run is about to re-buy.
            if (
                not reingest_cleanup
                and entry is not None
                and not _sha_shared_by_other_entry(manifest_dict, del_sha, key)
            ):
                transcribe.prune_cached(del_sha)
                pdftext.prune_cached(del_sha)
            # A resume checkpoint is KEY-addressed (not content-addressed like those two caches),
            # so it belongs to this source alone and is dropped unconditionally — no shared-sha
            # guard applies, and leaving it would strand the source's page text beside the wiki.
            resume.clear(key)
            manifest_dict.pop(key, None)
            failures.clear(failures_dict, key)
            manifest.save(manifest_dict)
            if reingest_cleanup:
                report.reingest_cleaned.append(key)
            else:
                report.sources_deleted.append(key)

        return _SourceJob(
            key=key,
            build_sessions=build,
            on_success=done,
            prepare_error="plan delete cleanup",
            extra_check=lambda: [f"{key}: still cited by {p} after cleanup" for p in store.find_raw_references(key)],
            # A delete cleanup MAY legitimately remove the last source's only page, leaving the
            # wiki empty — so the anti-emptying valve does not apply here.
            allow_emptying=True,
            # A cleanup session is planned ONLY when something still cites the source, so it has
            # work to do by construction: an empty diff means the agent did nothing (and the
            # post-condition below is about to fail it). The empty-session case — a deletion
            # nothing cited — carries ``ran_sessions=False`` and is never counted.
            expects_changes=True,
            # A failed cleanup is the ONE failure that leaves a defect in the live wiki rather than
            # just leaving work undone: the pages named above keep citing a source file that no
            # longer exists. The generic "it will be retried" advice does not cover that, and a
            # retry only helps once the agent can actually do the work — so name the offline tools
            # that see and fix the leftover, or the user is left with a dangling `[^sN]` and no
            # idea it is there.
            failure_hint=(
                "A deletion cleanup failed, so the pages it names still cite a source file that no "
                "longer exists. Other sources are no longer blocked by this, but it IS a defect in "
                "the wiki: `citadel lint` lists it under 'Fabricated/missing sources' (exit 3) and "
                "`citadel curate` repairs it."
            ),
        )

    # A Ctrl+C (or other BaseException) raised mid-loop is captured (returned by
    # _run_source_jobs), not allowed to propagate immediately, so the remaining groups are
    # skipped and finalization still runs for the already-completed sources before it is
    # re-raised. Without this, the per-source-persisted manifest could outlive a stale index/log:
    # a later run with nothing pending would never rebuild the derived files.
    pending_interrupt: BaseException | None = None
    stall = _StallGuard(limit=config.STALL_LIMIT)
    groups = (
        # Reingest cleanups ride the deletion group, so the always-first ordering above holds for
        # them too: a source's old facts are stripped before ANY pending session runs.
        [_delete_job(key) for key in deleted_sources]
        + [_delete_job(key, reingest_cleanup=True) for key in sorted(reingest_keys)],
        [_file_job(src) for src in scan.pending],
        [_repo_job(r) for r in repo_pending],
    )
    for group in groups:
        # A tripped stall guard skips the REMAINING groups too: the agent is what is broken, and it
        # is no more able to fold in a repo than it was the last three files.
        if pending_interrupt is None and not stall.tripped:
            pending_interrupt = _run_source_jobs(group, emit, report, failures_dict, model, workers=jobs, stall=stall)
    report.stalled = stall.reason

    if workspace_shifted and full_rescan:
        # The guard's advertised remedy must not loop: --full-rescan keeps the sweep refused
        # (safety frozen) but guarantees ONE end-of-run save, re-stamping the manifest meta with
        # the CURRENT workspace root — so the next run reads a matching stamp and the deletion
        # sweep is re-armed.
        manifest.save(manifest_dict)
    elif workspace_mismatch and not workspace_shifted and paths is None:
        # The dual-mount counterpart: the stamp named another root but the key space held up
        # (the sweep stayed armed), so this root legitimately worked the manifest. Guarantee ONE
        # end-of-run save even when nothing else saved — meta.workspaces records the current
        # root and the load-time warning keeps its promise that one completed `citadel ingest`
        # run makes it stop, a no-op run included.
        manifest.save(manifest_dict)

    failures_changed = failures_dict != failures_before
    if (
        report.processed
        or report.pages_written
        or report.moved
        or report.unreadable
        or report.sources_deleted
        or report.reingest_cleaned
        or repointed
        or failures_changed
        or pruned_ignored
    ):
        emit("finalize")
        # The manifest is already persisted incrementally (after each source, and right after the
        # move/unreadable bookkeeping) above, so a final save here would be redundant. Persist the
        # updated failures FIRST so the catalog rebuild below reflects this run's stuck set, then
        # rebuild the derived files (a move repoint can have changed page bodies/frontmatter).
        failures.save(failures_dict)
        store.rebuild_indexes()
        # Surface any cross-link left dangling by a restructure so it is never silent.
        report.broken_links = store.find_broken_links()
        if report.processed:
            store.append_log(
                f"ingest {report.processed} -> {len(report.pages_created)} created, "
                f"{len(report.pages_updated)} updated, {len(report.pages_deleted)} deleted "
                f"(model: {model})"
            )
        for key in report.no_pages:
            store.append_log(
                f"ingested {key} but the session produced no wiki changes (no page created, "
                f"updated, or deleted); retry with `citadel ingest --retry` or "
                f"`citadel ingest --force {key}`"
            )
        for old_key, new_key in report.moved:
            store.append_log(
                f"reorganized {new_key}: same content already ingested as {old_key}; "
                "recognized as moved, not re-ingested"
            )
        for key in report.unreadable:
            if key in report.cloud_placeholders:
                store.append_log(
                    f"could not ingest {key}: reads as all NUL bytes - likely a cloud-only "
                    "placeholder (online-only file); make it available offline"
                )
            else:
                store.append_log(f"could not ingest {key}: no readable text found (binary or unsupported); skipped")
        for key in report.sources_deleted:
            store.append_log(
                f"raw source {key} was deleted from disk; reconciled its citations out of the "
                "wiki and dropped it from the manifest"
            )
        for key in report.reingest_cleaned:
            store.append_log(
                f"reingest {key}: stripped its previous facts ahead of the fresh import "
                "(deliberate re-read as a new source)"
            )
        # The wiki-history commit comes LAST, after the log/index/failures writes above, so one
        # commit captures the run's complete state. Best-effort by contract: the wiki is already
        # promoted, so a git problem is a report note, never a failed run.
        report.wiki_git = (
            wikigit.autocommit(
                f"citadel ingest: {len(report.processed)} processed, "
                f"{len(report.sources_deleted)} sources removed -> "
                f"{len(report.pages_created)} created, {len(report.pages_updated)} updated, "
                f"{len(report.pages_deleted)} deleted (model: {model})"
            )
            or ""
        )
        emit(
            "done",
            processed=len(report.processed),
            created=len(report.pages_created),
            updated=len(report.pages_updated),
            deleted=len(report.pages_deleted),
            broken=len(report.broken_links),
            moved=len(report.moved),
            unreadable=len(report.unreadable),
            sources_deleted=len(report.sources_deleted),
        )

    # Now that the completed sources have been finalized, re-raise a captured Ctrl+C so the
    # interrupt still aborts the run (the per-source `finally` already rolled back whichever
    # source was in flight when it landed).
    if pending_interrupt is not None:
        raise pending_interrupt

    return report
