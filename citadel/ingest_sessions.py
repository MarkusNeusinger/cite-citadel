"""The all-or-nothing agent-session runner and its supporting cast.

:func:`_run_agent_sessions` drives one source's session(s) — a single pass or every segment of
a chunked source — against ONE staging copy, with promote-once semantics (the full contract
lives on its docstring). Around it: the per-source outcome (:class:`_SourceOutcome`), the
resume-checkpoint glue for chunked sources (:class:`_Resume` and friends, over
:mod:`citadel.resume`), the session-usage accounting translations, and the pass planning that
prepares what each session reads (Office/transcript/PDF temp files, large-source chunking).

Split out of :mod:`citadel.ingest`, which re-exports these names — the module boundary is an
implementation detail; ``ingest._run_agent_sessions`` etc. remain the addressable seams
(``citadel curate`` rides :func:`_run_agent_sessions` through them).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config, extract, llm, manifest, okf, resume, store
from .ingest_staging import (
    _LIVE_WIKI_LOCK,
    _ConcurrentChange,
    _content_files,
    _content_hashes,
    _diff,
    _files_equal,
    _hash_pages,
    _make_staging,
    _promote,
    _redirect_wiki,
    _repair_renames,
    _robust_rmtree,
    _sha256,
    _sha256_or_none,
    _snapshot,
    _validate_and_restamp,
)


@dataclass
class _SourceOutcome:
    """Result of one agent-driven source (ingest / reconcile / delete). ``ok`` means the edit
    was validated and promoted onto the live wiki (the caller still updates the manifest + report);
    ``ok is False`` means nothing was promoted — the live wiki is unchanged — and ``errors`` says
    why. ``usage`` is what the source's session(s) reported costing (segments combined; also set
    on a FAILED outcome when earlier segments completed — that money was spent even though the
    work was rolled back), or None when no session reported anything."""

    ok: bool
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    seconds: float = 0.0
    usage: llm.SessionUsage | None = None
    # What EARLIER runs already paid for the segments a resume checkpoint restored. Kept apart from
    # ``usage`` on purpose: the run report must count only what THIS run spent (the earlier run
    # reported its own), while the manifest stamp must cover every session whose work is in the
    # wiki — "one combined usage, matching promote-once semantics" — across the runs that produced
    # it. Like every manifest stamp it is success-only: a FAILED attempt's spend stays on the run
    # report that paid it, exactly as for a single-session source.
    carried_usage: llm.SessionUsage | None = None
    # Human-readable note when this source continued from a checkpoint ("" when it did not).
    resumed_note: str = ""
    # `--jobs N` only: the session was clean, but a CONCURRENT source's promote had changed a page
    # this one would have written (:class:`_ConcurrentChange`), so nothing was promoted. Not a
    # failure — the caller re-runs the source serially before the run ends, and only if THAT fails
    # does it become one.
    conflict: bool = False
    # Validation errors a page this source touched ALREADY had before it did (see
    # ``_validate_and_restamp``'s ``inherited``). They did not fail the source — it did not cause
    # them — but they are true of the live wiki, so the caller surfaces them as a run warning
    # rather than letting the carve-out hide them.
    carried_issues: list[str] = field(default_factory=list)
    # False only for a source that needed NO agent session at all (a deleted source nothing cites):
    # "no changes" from such a source is the correct answer, not evidence that the agent is broken.
    ran_sessions: bool = True


@dataclass
class _Resume:
    """One chunked source's resume context (:mod:`citadel.resume`) — the identity of its
    multi-segment job plus the checkpoint an earlier run left, if any is still adoptable.

    Built by the pending-file job (only there: a repo digest, an image, a deletion cleanup and a
    curate cluster are all single-session, so there is nothing to resume), and consumed by
    :func:`_run_agent_sessions`. ``checkpoint`` is set to None the moment a guard refuses it, so
    the runner's own fallback path and the caller see the same "start at segment 1" state."""

    plan: resume.Plan
    checkpoint: resume.Checkpoint | None = None


def _plan_shape(passes) -> str:
    """Fingerprint a chunked source's pass plan by CONTENT — the chunking threshold, each pass's
    segment/line-window position, and the sha256 of the prepared text it hands the agent.

    Deliberately not the temp PATHS (``_office_write_temp`` mints a fresh random dir every run) and
    deliberately not just the segment count: an extraction change (a pypdf upgrade, a
    re-transcription, a re-tuned chunk budget) can keep the count while moving the boundaries, and
    "segment 3" would then name text its predecessor never saw. "" means the shape could not be
    determined — the caller then simply does not checkpoint.

    The budget hashed here is the EFFECTIVE one (:func:`config.source_chunk_chars`), never the raw
    ``CITADEL_MAX_SOURCE_CHARS``: a stated model context tightens the threshold, so hashing the raw
    value would let a checkpoint planned under one segment shape be replayed under another."""
    digest = hashlib.sha256(f"{config.source_chunk_chars()}".encode())
    for read_key, segment, window in passes:
        digest.update(f"\x1e{segment}|{window}|".encode())
        if read_key:
            try:
                # A read_key is workspace-RELATIVE when the temp landed inside the workspace and
                # absolute otherwise (config.rel_or_abs_posix) — resolve it the same way every
                # other consumer does, never as a bare Path against this process's CWD.
                digest.update(_sha256(config.source_path_for_key(read_key)).encode("ascii"))
            except (OSError, okf.OKFError, ValueError):
                return ""
    return digest.hexdigest()


def _resume_context(rel_key: str, kind: str, sha: str | None, passes, model: str, rules_ver: str) -> _Resume | None:
    """The :class:`_Resume` context for one pending source, or None when resume does not apply.

    It applies to CHUNKED sources only (a single-pass source has no earlier segment to save) and
    only when discovery actually hashed the file: a null sha would make the identity check compare
    ``None == None`` and could re-adopt a checkpoint after the source's bytes changed — sha256 is
    the sole arbiter of "changed" everywhere else, and it stays so here. An indeterminable pass
    shape (a temp read file that vanished) likewise opts the source out rather than guessing.

    Adopting a checkpoint COUNTS (``resume.note_attempt``): a segment that fails deterministically
    would otherwise re-fail cheaply and quietly forever, so after :data:`resume.ATTEMPT_CAP`
    fruitless resumes the checkpoint is dropped and the source is retried in full.

    A FORCED re-read (``--force``, and therefore ``citadel refresh``) deliberately still resumes:
    force means "read this source again now", and an interrupted forced re-read is exactly the
    expensive job worth continuing — a `refresh` slice that dies at segment 5 of 7 should not have
    to re-buy segments 1-4 on the next scheduled run. It cannot cross-adopt a normal run's work
    either way, since forcing changes the session ``kind`` (reconcile, not ingest) and the kind is
    part of the identity."""
    if not resume.enabled() or len(passes) < 2 or not sha:
        return None
    shape = _plan_shape(passes)
    if not shape:
        return None
    plan = resume.Plan(
        key=rel_key,
        sha=sha,
        kind=kind,
        model=model,
        rules_version=rules_ver,
        total=len(passes),
        shape=shape,
        knobs=resume.knob_stamp(),
    )
    checkpoint = resume.load(plan)
    if checkpoint is not None:
        resume.note_attempt(checkpoint)
    return _Resume(plan=plan, checkpoint=checkpoint)


def _usage_from_fields(fields: dict) -> llm.SessionUsage | None:
    """The inverse of :func:`_usage_fields`: a manifest-shaped usage dict (as carried in a resume
    checkpoint) back into a :class:`llm.SessionUsage`, or None when it says nothing."""
    if not fields:
        return None
    return llm.SessionUsage(
        cost_usd=fields.get("cost_usd"),
        input_tokens=fields.get("tokens_in"),
        output_tokens=fields.get("tokens_out"),
        aic=fields.get("aic"),
    )


def _usage_fields(usage: llm.SessionUsage | None) -> dict:
    """A source's combined session usage as ``manifest.make_entry`` / ``make_repo_entry`` kwargs
    (``cost_usd``/``tokens_in``/``tokens_out``/``aic``, only the known fields) — the
    one translation from the llm-layer shape to the manifest-layer stamp, so the done-hooks stay
    one-liners. ``model`` is deliberately NOT part of this: it is provenance, stamped through
    :func:`_stamp_model` into the entry's own ``model`` field, not usage."""
    if usage is None:
        return {}
    out: dict = {}
    for key, value in (
        ("cost_usd", usage.cost_usd),
        ("aic", usage.aic),
        ("tokens_in", usage.input_tokens),
        ("tokens_out", usage.output_tokens),
    ):
        if value is not None:
            out[key] = value
    return out


def _stamp_model(usage: llm.SessionUsage | None, fallback: str) -> str:
    """The model label to RECORD for a finished source: what the backend reported actually
    serving the session (``config.model_label_for``), else ``fallback`` — the run's configured
    label (``config.ingest_model_label``). The reported id is the only honest one: the configured
    model is a request the backend may not have honored (``auto``, a fallback, a stale ``.env``),
    and a wiki that claims an unused model misleads every later audit of its provenance."""
    reported = usage.model if isinstance(usage, llm.SessionUsage) else None
    return config.model_label_for(reported) if reported else fallback


def _sha_shared_by_other_entry(manifest_dict: dict, sha: str | None, exclude_key: str) -> bool:
    """True when a manifest entry OTHER than ``exclude_key`` still records content hash ``sha``.

    The transcript/PDF caches are CONTENT-addressed (keyed by sha256), so two byte-identical
    sources under different keys share ONE cache file. Pruning that file when one of them changes
    or is deleted would break offline verification (lint/``wiki_raw``/viewer) for the survivors
    until they re-extract. This guard gates every prune: only the LAST reference to a sha may
    drop its cache entry. Repo entries carry a commit identity, not a content sha, so they never
    hold a transcript/PDF cache entry and are skipped."""
    if not sha:
        return False
    for key, entry in manifest_dict.items():
        if key == exclude_key or manifest.is_repo_entry(entry):
            continue
        if manifest.entry_sha(entry) == sha:
            return True
    return False


def _checkpoint_delta(
    staging: Path, live: Path, base: dict[str, str] | None = None
) -> tuple[list[str], list[str]] | None:
    """``(changed, removed)`` — this source's own delta, exactly as :func:`_promote` computes it —
    or None when it must not be recorded at all.

    Computed with the PROMOTE's own file-level view (:func:`_content_files` + :func:`_files_equal`),
    never from the per-segment page diffs: those miss the link repairs ``_repair_renames`` writes
    into pages no session touched (and any non-``.md`` file), and their union across segments can
    even resurrect a page a later segment deliberately deleted. A checkpoint must describe exactly
    what would have shipped, so it is derived from exactly what ships.

    ``base`` — the clone snapshot, present only under ``--jobs N`` — is what keeps that true when
    the wiki is moving. Measured against the CURRENT live wiki, a page a CONCURRENT source created
    between this source's clone and this checkpoint reads as "in live, not in my staging", i.e. as a
    deletion THIS source made, and one it rewrote reads as a change of this source's with the clone's
    stale bytes. A checkpoint is durable, so such a delta outlives the parallel run: replayed by a
    later — even strictly serial — run, it deletes a fully-ingested source's page off the live wiki
    with no conflict, no error and no delete session. Measured against the base, the delta is this
    source's alone (the promote's exact rule), and the concurrent work is simply not in it.

    The refusal mirrors the promote's anti-emptying valve: a staging tree with no content page while
    the wiki this source started from had some is a wipe-the-wiki delta (a vanished/rm-tree'd staging
    reads exactly like this), and :func:`_promote` would refuse it — so it must never be persisted as
    a replayable one."""
    staged = _content_files(staging)
    started_from = _content_files(live) if base is None else base
    if not [rel for rel in staged if rel.endswith(".md")] and [rel for rel in started_from if rel.endswith(".md")]:
        return None
    if base is None:
        changed = sorted(rel for rel, src in staged.items() if not _files_equal(src, live / rel))
    else:
        changed = sorted(rel for rel, src in staged.items() if _sha256_or_none(src) != base.get(rel))
    removed = sorted(set(started_from) - set(staged))
    return changed, removed


def _adopt_checkpoint(
    ctx: _Resume, staging: Path, live: Path, rel_key: str, carried: list[str] | None = None
) -> tuple[list, list, list] | None:
    """Replay ``ctx``'s checkpoint into the fresh ``staging`` copy and return the
    ``(created, updated, deleted)`` it landed there, or None when it must not be used.

    Three gates, in cost order — all offline, all before a single agent token is spent:

    1. the base-state guard (:func:`resume.replay`): every page the delta touches must still be, in
       the live wiki, what it was when the checkpoint was written;
    2. re-validation of every replayed page — the same ``_validate_and_restamp`` every agent pass
       goes through, so a page whose cited raw source has since been deleted can never be promoted
       (it also re-stamps the timestamps, which would otherwise be the earlier run's);
    3. no cross-link may be broken that the live wiki did not already have broken — ``validate_page``
       has no cross-page view, and a link target removed between runs would otherwise land as a
       fresh dangling link on an already-promoted wiki.

    Returning None is NEVER a source failure: the caller drops the checkpoint and restarts the
    source at segment 1 in this same run, which is exactly the pre-resume behavior.

    ``carried`` collects the pre-existing page errors gate 2 forgave, so "forgive but still report"
    holds here too: a page this replay restored and no later segment touches again would otherwise
    have its inherited breakage validated once, waved through, and never surfaced. The caller merges
    it only when the adoption SUCCEEDS — a refused replay is discarded whole, and its findings with
    it."""
    with _redirect_wiki(staging):
        # Baseline the cross-links BEFORE the replay: staging is still a byte copy of live here, so
        # this is the set of breakages the wiki already lives with (which resume must not be blamed
        # for, and must not repair).
        before_pages = store.load()
        before_broken = set(store.find_broken_links(before_pages))
        written = resume.replay(ctx.checkpoint, staging, live)
        if written is None:
            return None
        # Validate exactly what the replay put on disk (its return value, not the record's own
        # list): a delta it could not apply in full has already refused above. The same
        # inherited-damage carve-out the agent passes get: a page the live wiki already holds
        # broken must not cost this source its checkpoint (and with it every paid segment) —
        # the replay is only ever refused for breakage the replay itself introduced.
        inherited = {page.rel_path: page for page in before_pages}
        if _validate_and_restamp(
            [rel for rel in written if rel.endswith(".md")], rel_key, inherited=inherited, carried=carried
        ):
            return None
        if set(store.find_broken_links(store.load())) - before_broken:
            return None
    # Classify by the recorded base state, so the run report/log/progress counts describe what the
    # promote will actually land — a resumed source that says "2 created" while 22 pages appear is
    # the exact converse of the report-claims-only-what-is-live rule. Only PAGES are reported: the
    # delta is the promote's file-level set (any non-reserved file), while the report's vocabulary
    # is the page diff's, so a stray non-`.md` file is replayed but never counted as a page.
    pages = [rel for rel in ctx.checkpoint.pages if rel.endswith(".md")]
    created = sorted(rel for rel in pages if ctx.checkpoint.bases.get(rel) is None)
    updated = sorted(rel for rel in pages if ctx.checkpoint.bases.get(rel) is not None)
    return created, updated, sorted(rel for rel in ctx.checkpoint.removed if rel.endswith(".md"))


def _write_checkpoint(
    ctx: _Resume, completed: int, staging: Path, live: Path, usage: dict, base: dict[str, str] | None = None
) -> None:
    """Record ``completed`` segments' work for this source. Best-effort by contract — any failure
    just means the next run starts at segment 1, so nothing here may raise into the session loop.

    Cost: one staging↔live comparison plus a copy of the (growing) delta per segment, i.e. O(wiki)
    per segment for a chunked source. Deliberately paid rather than optimized: deriving the delta
    from the promote's own view is what makes a replay equivalent to an unbroken run, and this is
    strictly cheaper than the per-source staging COPY the same run already makes — and invisible
    beside the agent session each segment costs."""
    try:
        delta = _checkpoint_delta(staging, live, base)
        if delta is not None:
            # `base` travels on to resume.save as the state the delta must be guarded against: the
            # wiki this source was CLONED from, not the (possibly moved-on) live wiki at save time.
            # Recording the latter would have the replay guard verify "live unchanged since I
            # saved" while the delta means "live as of my clone" — the wrong invariant, and one a
            # concurrent promote slips straight through.
            resume.save(ctx.plan, completed, staging, live, delta[0], delta[1], usage, bases=base)
    except Exception:  # noqa: BLE001 - a checkpoint may never cost a run its source
        pass


def _run_agent_sessions(
    session_fns,
    rel_key: str,
    extra_check=None,
    allow_emptying: bool = False,
    resume_ctx: _Resume | None = None,
    concurrent: bool = False,
    on_segment=None,
) -> _SourceOutcome:
    """Run one source's agent session(s) — a single pass, or every segment of a chunked source —
    against ONE staging copy, with full all-or-nothing safety. Shared by every job kind
    (ingest/reconcile, repo, deletion cleanup).

    Makes a STAGING copy of the live wiki (a sibling dir), redirects the agent + its ``citadel
    check`` there, then for EACH ``session_fn`` in order: snapshots staging, calls the session
    (the agent edits the STAGING copy — never the live wiki), diffs to learn what that pass
    changed, validates + re-stamps the changed pages (fail fast: an invalid segment stops the
    source right there — later segments never run), and repoints renamed-page links. A later
    segment therefore sees — and merges into — what the earlier segments wrote in the SAME
    staging copy. After the last session an optional ``extra_check()`` post-condition runs (used
    by deletion cleanup to assert no reference to the removed source survived).

    PROMOTION HAPPENS EXACTLY ONCE, after the last session passes (no silently partial imports): the non-destructive copy-over-then-prune that can never empty
    or half-write the live wiki, which thus only ever contains FULLY imported sources. A
    failure/timeout/interrupt at segment N still discards the whole staging copy and promotes
    NOTHING — that part of the trade-off is the guarantee itself and does not move.

    What ``resume_ctx`` changes is only who pays for it again. With a resume context (chunked
    sources only — :func:`_resume_context`), each completed segment records the delta it produced
    as a checkpoint beside the wiki, and a later run REPLAYS that delta into its fresh staging copy
    and continues at segment N instead of re-buying segments 1..N-1 (:mod:`citadel.resume`). The
    replay is gated offline — base state, re-validation, no new broken links — and any refusal
    falls back to a clean staging copy and segment 1 IN THIS RUN, so the pre-resume behavior is the
    floor, never the failure mode. ``CITADEL_RESUME=0`` (or any non-chunked source) skips the
    machinery entirely.

    On ANY failure — a validation error, a failed post-condition, or an exception from a session
    — the live wiki is left exactly as it was and ``ok`` is False; the caller leaves the source
    un-committed so it is retried next run. A propagating ``BaseException`` (Ctrl+C) during a
    session likewise leaves the live wiki untouched (nothing is promoted); during the brief
    promote it can leave that ONE source partially applied — a SUPERSET of valid pages, never an
    emptied wiki — which a later full run reconciles. Either way it re-raises for the caller's
    loop to capture. Staging is always discarded in ``finally``. The caller owns the manifest +
    report bookkeeping (different for a completed source vs. a removed one).

    ``concurrent`` (set only by the ``--jobs N`` driver) says another source may be staging or
    promoting at the same time. It changes nothing about a session — it makes the two moments that
    touch the LIVE wiki safe under that: the clone is taken under :data:`_LIVE_WIKI_LOCK` together
    with a hash snapshot of what was cloned, and the promote runs under the same lock against that
    base (see :func:`_promote`). A promote refused because a concurrent source got to one of these
    pages first comes back as ``conflict`` rather than an error — the driver re-runs the source
    serially, and the live wiki is untouched either way.

    ``on_segment(part, parts)`` — optional, best-effort — is called just BEFORE each session with
    its 1-based position among this source's passes. A chunked source is the one case where a
    single console row stands still for hours (one agent session per segment, each up to
    ``CITADEL_LLM_TIMEOUT``), so the caller uses it to say *which* pass is running rather than
    leaving a lone spinner to look hung; with a resume checkpoint the numbering continues at the
    segment the earlier run died on, since that is the pass actually being paid for. It is
    progress output — a raising callback must never cost a source its session, so it is guarded.

    An EMPTY ``session_fns`` (a deleted source nothing cites) succeeds immediately with zero page
    changes — before a staging copy is even made."""
    started = time.monotonic()
    if not session_fns:
        return _SourceOutcome(True, ran_sessions=False)
    live = config.wiki_dir()
    base: dict[str, str] | None = None
    staging: Path | None = None
    created: list[str] = []
    updated: list[str] = []
    deleted: list[str] = []
    # Each session's backend-reported usage (None from the test fakes / silent backends),
    # combined into the outcome on EVERY return path — a rolled-back source still spent money.
    usage_parts: list[llm.SessionUsage | None] = []
    # What earlier runs already paid for the segments a checkpoint restores (see _SourceOutcome).
    carried: dict = {}
    # Errors on pages this source touched that the wiki ALREADY had (see _SourceOutcome).
    carried_issues: list[str] = []
    resumed_note = ""

    def clone() -> tuple[Path, dict[str, str] | None]:
        """A staging copy of the live wiki plus (concurrent runs only) the base state it copied.

        The lock covers the COPY alone; the base is then hashed off the fresh staging tree, which
        is a byte-exact copy of exactly what was cloned — same hashes, half the disk I/O (the wiki
        is read once, not twice), and every other worker's clone/promote is unblocked that much
        sooner. It must still happen HERE, before anything mutates staging: a resume replay writes
        into it a few lines below, and those pages are not part of the wiki this source started
        from."""
        with _LIVE_WIKI_LOCK:
            staging = _make_staging(live)
        return staging, (_content_hashes(staging) if concurrent else None)

    try:
        staging, base = clone()
        # The content paths the live wiki held when this source cloned it (the fresh staging copy
        # IS that state, so walking it costs no second pass over live). Consulted only by the
        # vanished-staging check below, to name files that appeared in the LIVE wiki outside the
        # staging discipline.
        clone_paths = set(base) if base is not None else set(_content_files(staging))
        # RESUME: replay an earlier run's completed segments into this fresh staging copy, so only
        # the remaining ones have to be paid for again. Every guard failure falls back to a full
        # start on a clean staging copy IN THIS RUN — never a failed source, never a wasted session.
        start_at = 0
        if resume_ctx is not None and resume_ctx.checkpoint is not None:
            # Collected into a LOCAL list, merged only if the replay is adopted: a refused
            # checkpoint is discarded whole (staging included), so its findings describe a state
            # this run never went on to promote.
            replay_issues: list[str] = []
            seeded = _adopt_checkpoint(resume_ctx, staging, live, rel_key, carried=replay_issues)
            if seeded is None:
                resume.clear(rel_key)
                resume_ctx.checkpoint = None
                _robust_rmtree(staging)
                staging, base = clone()
                clone_paths = set(base) if base is not None else set(_content_files(staging))
            else:
                created, updated, deleted = list(seeded[0]), list(seeded[1]), list(seeded[2])
                start_at = resume_ctx.checkpoint.completed
                carried = dict(resume_ctx.checkpoint.usage)
                carried_issues.extend(replay_issues)
                resumed_note = f"{rel_key} (segments 1-{start_at} of {len(session_fns)} restored from checkpoint)"
        with _redirect_wiki(staging):
            prev_pages = store.load()
            prev = _hash_pages(prev_pages)
            # The wiki as this source FOUND it, kept across every segment (``prev_pages`` is
            # re-baselined per segment, so it stops answering "before this source" after the
            # first). This is what tells damage the source caused from damage it inherited —
            # a page created by segment 1 is absent here, so segment 2 owns it in full.
            inherited = {page.rel_path: page for page in prev_pages}
            for i in range(start_at, len(session_fns)):
                if on_segment is not None:
                    try:
                        on_segment(i + 1, len(session_fns))
                    except Exception:  # noqa: BLE001 - progress must never break a session
                        pass
                result = session_fns[i]()  # the agent edits the STAGING copy, never the live wiki
                usage_parts.append(result if isinstance(result, llm.SessionUsage) else None)

                if not Path(staging).is_dir():
                    # The staging copy ITSELF is gone: the agent (a weak model has been seen
                    # inventing a "publish" step — copying its pages into the live wiki and
                    # deleting staging as "done") or something else on the machine removed it.
                    # Without this check the empty snapshot reads as "the session changed
                    # nothing" and the failure surfaces — if at all — as an opaque
                    # refusing-to-promote error three steps later. Fail the source with the real
                    # story, and (serial runs only — under --jobs N a concurrent source's promote
                    # legitimately changes the live wiki) name any files that appeared in the
                    # LIVE wiki outside the staging discipline: they were never validated, and
                    # they are deliberately left in place for the user to inspect.
                    msg = (
                        f"{rel_key}: the staging wiki copy vanished mid-session (the agent or "
                        "another process moved or deleted it), so this session's work cannot be "
                        "verified or promoted"
                    )
                    if not concurrent:
                        stray = sorted(set(_content_files(live)) - clone_paths)
                        if stray:
                            shown = ", ".join(stray[:5]) + (f", ... +{len(stray) - 5} more" if len(stray) > 5 else "")
                            msg += (
                                "; these files appeared in the LIVE wiki outside the staging "
                                f"discipline (NOT validated by this run, left in place): {shown}"
                            )
                    return _SourceOutcome(
                        False,
                        errors=[msg],
                        seconds=time.monotonic() - started,
                        usage=llm.combine_usage(usage_parts),
                        carried_usage=_usage_from_fields(carried),
                        resumed_note=resumed_note,
                    )

                after = _snapshot()
                seg_created, seg_updated, seg_deleted = _diff(prev, after)

                val_errors = _validate_and_restamp(
                    seg_created + seg_updated, rel_key, inherited=inherited, carried=carried_issues
                )
                if val_errors:
                    return _SourceOutcome(
                        False,
                        errors=val_errors,
                        seconds=time.monotonic() - started,
                        usage=llm.combine_usage(usage_parts),
                        carried_usage=_usage_from_fields(carried),
                        resumed_note=resumed_note,
                    )

                _repair_renames(prev_pages, seg_created, seg_deleted)

                created.extend(seg_created)
                updated.extend(seg_updated)
                deleted.extend(seg_deleted)
                if resume_ctx is not None:
                    # AFTER the rename repairs (they are part of what would be promoted) and before
                    # the re-baseline. Written for the LAST segment too: a promote that then fails
                    # leaves the whole source replayable for free instead of re-buying every pass.
                    _write_checkpoint(
                        resume_ctx,
                        i + 1,
                        staging,
                        live,
                        _usage_fields(llm.combine_usage([*usage_parts, _usage_from_fields(carried)])),
                        base,
                    )
                if i + 1 < len(session_fns):
                    # Re-baseline on the validated/re-stamped state, so the next segment's diff
                    # (and its validation) covers exactly what THAT segment changes. Nothing
                    # consumes it after the LAST session, so it is skipped there.
                    prev_pages = store.load()
                    prev = _hash_pages(prev_pages)

            if extra_check is not None:
                post_errors = extra_check()
                if post_errors:
                    return _SourceOutcome(
                        False,
                        created,
                        updated,
                        deleted,
                        post_errors,
                        time.monotonic() - started,
                        usage=llm.combine_usage(usage_parts),
                        carried_usage=_usage_from_fields(carried),
                        resumed_note=resumed_note,
                    )

        # Every session was clean: commit the source onto the live wiki (config now points back
        # at live). This is the ONLY step that touches the live wiki, it happens ONCE per source,
        # and it is non-destructive — so an interrupt here still cannot empty it. Under `--jobs N`
        # it is also the only step that has to exclude its siblings (one promote at a time, checked
        # against the state this source was cloned from).
        with _LIVE_WIKI_LOCK:
            _promote(staging, live, allow_emptying=allow_emptying, base=base)
        if resume_ctx is not None:
            resume.clear(rel_key)  # the work is live now: the checkpoint has nothing left to save
        return _SourceOutcome(
            True,
            created,
            updated,
            deleted,
            [],
            time.monotonic() - started,
            usage=llm.combine_usage(usage_parts),
            carried_usage=_usage_from_fields(carried),
            resumed_note=resumed_note,
            # Only on the PROMOTED path: a rolled-back source left the live wiki untouched, so the
            # problems it saw in staging are somebody else's report to make.
            carried_issues=sorted(set(carried_issues)),
        )
    except _ConcurrentChange as exc:
        # Not a failure: the work was fine, the wiki simply moved under it (only reachable with
        # `--jobs N`). Nothing was promoted, so the live wiki still holds the OTHER source's
        # version; the driver re-runs this source serially against it. The spend is reported like
        # any other — that session was paid for.
        return _SourceOutcome(
            False,
            errors=[f"{rel_key}: {exc}"],
            seconds=time.monotonic() - started,
            usage=llm.combine_usage(usage_parts),
            carried_usage=_usage_from_fields(carried),
            resumed_note=resumed_note,
            conflict=True,
        )
    except Exception as exc:  # noqa: BLE001 - collect per-source, keep going; live wiki untouched
        # A raising session never returned its usage, but the backend may still have reported
        # what the FAILED attempt cost (claude's error envelope, copilot/agy's stdout stream) — llm
        # carries that on the exception, so the run total honors "failed sessions included".
        salvaged = getattr(exc, "session_usage", None)
        usage_parts.append(salvaged if isinstance(salvaged, llm.SessionUsage) else None)
        return _SourceOutcome(
            False,
            errors=[f"{rel_key}: {exc}"],
            seconds=time.monotonic() - started,
            usage=llm.combine_usage(usage_parts),
            carried_usage=_usage_from_fields(carried),
            resumed_note=resumed_note,
        )
    finally:
        # Discard staging on every exit (a clean source already promoted it; a failed or
        # interrupted one never touched the live wiki). A flaky share that refuses the delete only
        # leaves an inert sibling for the next run to clear — the live wiki is never at risk.
        if staging is not None:
            _robust_rmtree(staging)


def _office_write_temp(text: str, name: str, media: list[tuple[str, bytes]] | None = None) -> tuple[str, str]:
    """Materialize already-extracted Office ``text`` as a fresh temp ``.md`` (named after the
    source's ``name``) for the agent to READ, and return ``(read_key, tmpdir)``: ``read_key`` is the
    path the agent reads (it still cites the ORIGINAL source), and ``tmpdir`` is the temp directory
    the caller MUST remove after the session. Raises ``OSError`` only if the temp file cannot be
    written — handled per-source by the caller, never aborting the whole run.

    ``media`` is the source's embedded raster images (from :func:`extract.extract_media`): each is
    written into a ``media/`` subfolder beside the text file so the agent can VIEW the diagrams and
    charts the text extractor cannot capture. The extraction already happened once in
    :func:`_partition_sources` / here, so the ``.pptx``/``.docx`` is never parsed for text twice."""
    tmpdir = tempfile.mkdtemp(prefix="okf_extract_")
    try:
        out = Path(tmpdir) / (Path(name).stem + ".md")
        out.write_text(text, encoding="utf-8")
        if media:
            media_dir = Path(tmpdir) / "media"
            media_dir.mkdir(exist_ok=True)
            for fname, data in media:
                (media_dir / Path(fname).name).write_bytes(data)
    except OSError:
        # Don't leak the temp dir if the write fails — the caller never sees it to clean up.
        shutil.rmtree(tmpdir, ignore_errors=True)
        raise
    return config.rel_or_abs_posix(out), tmpdir


def _read_source_text(src: Path) -> str | None:
    """The decoded text of a plain-text source, for size-based chunking, or None when it should NOT
    be chunked here: a PDF (binary — its ``%PDF-`` magic; the agent's reader extracts the text) or a
    file we cannot read. Decoded with ``errors="replace"`` so an odd byte never raises. Only called
    for pending, non-Office, non-image sources (already sniffed as text by :func:`_is_ingestible`)."""
    try:
        with open(src, "rb") as fh:
            if fh.read(5) == b"%PDF-":
                return None
        return src.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _text_atoms(text: str, max_chars: int) -> list[str]:
    """Break ``text`` into atoms each at most ``max_chars`` long, preferring paragraph boundaries,
    then line boundaries, then hard character slices for a pathological single long line."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        if len(para) <= max_chars:
            out.append(para)
            continue
        for line in para.split("\n"):
            if len(line) <= max_chars:
                out.append(line)
            else:
                out.extend(line[i : i + max_chars] for i in range(0, len(line), max_chars))
    return [a for a in out if a.strip()]


def _split_text(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into ordered segments each at most ``max_chars`` long (packing whole
    paragraphs/lines together), or ``[text]`` when it already fits / chunking is off. Used to feed a
    large source to the agent in several sequential passes."""
    if max_chars <= 0 or len(text) <= max_chars:
        return [text]
    segments: list[str] = []
    cur = ""
    for atom in _text_atoms(text, max_chars):
        candidate = atom if not cur else cur + "\n\n" + atom
        if len(candidate) <= max_chars:
            cur = candidate
        else:
            if cur:
                segments.append(cur)
            cur = atom
    if cur:
        segments.append(cur)
    return segments or [text]


def _line_windows(text: str, max_chars: int) -> list[tuple[int, int]]:
    """Split ``text`` into contiguous 1-based inclusive LINE ranges, packing whole lines so each
    window stays at most ``max_chars`` characters (a single over-long line still gets its own
    window — lines are the atom here, never split). The windows cover every line in order, so a
    reader working window k of the SAME file sees the file's true line numbers — the point:
    unlike :func:`_split_text` slices, nothing ever rebases the numbering."""
    lines = text.splitlines()
    windows: list[tuple[int, int]] = []
    start, size = 1, 0
    for i, line in enumerate(lines, 1):
        cost = len(line) + 1
        if size and size + cost > max_chars:
            windows.append((start, i - 1))
            start, size = i, 0
        size += cost
    if start <= len(lines):
        windows.append((start, len(lines)))
    return windows or [(1, 1)]


def _prepare_passes(
    src: Path, office: str | None, is_image: bool, is_audio: bool = False, is_pdf: bool = False
) -> tuple[list[tuple[str | None, tuple[int, int] | None, tuple[int, int] | None]], list[str]]:
    """Plan the agent session(s) for one pending source and return ``(passes, tmpdirs)``.

    Each pass is ``(read_key, segment, line_range)``: ``read_key`` is the temp ``.md`` the agent
    reads (None = read the source file directly), ``segment`` is ``(part, total)`` for a chunked
    large source (None = single pass), and ``line_range`` — audio/PDF-extract only — is the
    1-based inclusive line window of the FULL prepared text this pass processes. ``tmpdirs`` are
    temp directories the caller MUST remove afterwards.

    - image: one pass, read the file directly (viewed visually).
    - a chunked AUDIO transcript or PDF text-layer extraction is NOT sliced into rebased temp
      files: every pass reads the SAME full prepared text (its line numbers are identical to the
      verification cache's) and carries the line window to process — so ``lines A-B`` locators
      stay correct by construction (a sliced temp restarts numbering at 1 and would silently
      mis-ground every chunked locator).
    - a source (pre-extracted Office text, or — when chunking is on — a readable non-PDF text
      file) whose content exceeds the effective chunk budget (``config.source_chunk_chars()`` —
      ``CITADEL_MAX_SOURCE_CHARS``, tightened by a stated ``CITADEL_MODEL_CONTEXT_TOKENS``) is
      SPLIT into segments, one pass each.
    - a small Office file / audio transcript / PDF extraction: one pass reading the prepared text.
    - anything else (small plain text, a PDF without a usable text layer, an image-less binary
      the agent reads): one pass reading the file directly (unchanged behavior).

    ``is_audio`` marks the ``office`` text as a whisper transcript, ``is_pdf`` as a pypdf
    text-layer extraction: same temp-file plumbing, but line-window chunking (above) and no media
    extraction (an ``.mp3``/``.pdf`` is not a ZIP to unzip).

    Raises ``OSError`` if a temp segment/extract file can't be written (handled per-source)."""
    if is_image:
        return [(None, None, None)], []
    max_chars = config.source_chunk_chars()
    # Content we could chunk: pre-extracted Office/transcript/PDF text, or (chunking on) a
    # readable text source.
    content = office
    if content is None and max_chars > 0:
        content = _read_source_text(src)
    if content is not None and max_chars > 0 and len(content) > max_chars:
        if is_audio or is_pdf:
            windows = _line_windows(content, max_chars)
            read_key, tmp = _office_write_temp(content, src.name, None)
            return [(read_key, (i, len(windows)), w) for i, w in enumerate(windows, 1)], [tmp]
        segments = _split_text(content, max_chars)
        # A chunked Office source keeps its embedded images: attached to the FIRST segment's temp,
        # exactly like the small-Office branch below — without this, a deck whose extracted text
        # crossed the chunking threshold silently lost its diagrams/charts.
        media = extract.extract_media(src) if office is not None and config.IMAGE_SUPPORT else []
        passes: list[tuple[str | None, tuple[int, int] | None, tuple[int, int] | None]] = []
        tmpdirs: list[str] = []
        try:
            for i, seg in enumerate(segments, 1):
                read_key, tmp = _office_write_temp(seg, src.name, media if i == 1 else None)
                passes.append((read_key, (i, len(segments)), None))
                tmpdirs.append(tmp)
        except OSError:
            for tmp in tmpdirs:
                shutil.rmtree(tmp, ignore_errors=True)
            raise
        return passes, tmpdirs
    if office is not None:
        # Small Office file: one pass reading the extracted text — plus its embedded images (decks
        # and docs often carry diagrams/charts/screenshots the text extractor can't see), written
        # beside the text for the agent to VIEW. Skipped when image support is off — and for an
        # audio transcript or PDF extraction, which have no OOXML media to extract.
        media = extract.extract_media(src) if config.IMAGE_SUPPORT and not (is_audio or is_pdf) else []
        read_key, tmp = _office_write_temp(office, src.name, media)
        return [(read_key, None, None)], [tmp]
    # Small plain text, a PDF without a usable text layer, or any other agent-readable source:
    # read the file directly.
    return [(None, None, None)], []


def _pending_session(
    rel_key: str,
    kind: str,
    read_key: str | None,
    segment: tuple[int, int] | None = None,
    line_range: tuple[int, int] | None = None,
) -> llm.SessionUsage | None:
    """Drive ONE ingest/reconcile agent session, passing through the backend's usage report
    (:class:`llm.SessionUsage` or None) for the outcome's accounting. When ``read_key`` is set
    (an Office source or a large-source segment whose text was extracted), point the agent at it
    via ``read_path``; otherwise call exactly as before so a non-Office source — and every
    existing test's faked session — is byte-for-byte unchanged. ``segment`` carries
    ``(part, total)`` for a chunked source, ``line_range`` the transcript window of a chunked
    AUDIO pass (the full-transcript lines this pass processes); each is passed to the backend
    ONLY when set, so every pre-existing call shape stays byte-for-byte unchanged."""
    if line_range is not None:
        return llm.run_ingest_session(rel_key, kind=kind, read_path=read_key, segment=segment, line_range=line_range)
    if read_key and segment is not None:
        return llm.run_ingest_session(rel_key, kind=kind, read_path=read_key, segment=segment)
    if read_key:
        return llm.run_ingest_session(rel_key, kind=kind, read_path=read_key)
    if segment is not None:
        return llm.run_ingest_session(rel_key, kind=kind, segment=segment)
    return llm.run_ingest_session(rel_key, kind=kind)
