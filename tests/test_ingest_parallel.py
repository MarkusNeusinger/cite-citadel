"""Bounded parallel ingest (``citadel ingest --jobs N``) and the context-local wiki redirect it
rides on — all offline, no CLI, no network (the agent seam is the usual :class:`FakeAgent`).

The concurrency is proven, not assumed: the fake sessions synchronize on a ``threading.Barrier``,
so a test that requires two sources to be in flight AT ONCE simply cannot pass on a serial run (the
barrier times out and the sources fail). The safety properties get their own tests, each pinned to
the failure it prevents:

* a concurrent source's pages must survive another source's promote (the base-aware prune);
* two sessions that wrote the SAME page must not silently pick one — the loser is re-run serially,
  against the wiki the winner left behind;
* the manifest/report bookkeeping stays single-threaded, and an interrupt still keeps the work that
  was already promoted.
"""

from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import pytest

from citadel import cli, config, ingest, llm, manifest


BARRIER_TIMEOUT = 10  # generous: a loaded CI box must never flake, a serial run still fails fast


def _sources(cit, names: list[str]) -> None:
    """Write one trivial raw source per name (``raw/<name>.md``)."""
    for name in names:
        (cit.raw / f"{name}.md").write_text(f"Content of {name}.\n", encoding="utf-8")


def _page_writer(cite_page, barrier: threading.Barrier | None = None, page_for=None):
    """A fake-session body that (optionally) meets its siblings at ``barrier`` — proving the
    sessions overlap — and then writes ONE valid page for the source it was called with.

    ``page_for(rel_key, attempt)`` chooses the page path; the default gives every source its own
    page. The page is written into ``config.wiki_dir()`` at call time, i.e. into ingest's per-source
    staging copy, exactly like the real agent's edits."""
    attempts: dict[str, int] = {}
    lock = threading.Lock()

    def session(rel_key: str, kind: str = "ingest", *_args, **_kwargs) -> None:
        with lock:
            attempts[rel_key] = attempts.get(rel_key, 0) + 1
            attempt = attempts[rel_key]
        if barrier is not None and attempt == 1:
            barrier.wait(timeout=BARRIER_TIMEOUT)
        slug = rel_key.rsplit("/", 1)[-1].replace(".", "-")
        rel_path = page_for(rel_key, attempt) if page_for is not None else f"misc/{slug}.md"
        cite_page(rel_path, rel_key, f"A fact from {slug} (attempt {attempt}).")

    session.attempts = attempts  # type: ignore[attr-defined]
    return session


# --- the redirect that unblocked this: context-local, never process-global --------------------


def test_wiki_redirect_is_per_thread(tmp_citadel):
    """The staging redirect must be invisible to every OTHER thread — that is the whole reason
    parallel sources can each stage their own copy of the wiki."""
    staging = tmp_citadel.root / "staging"
    seen: dict[str, Path] = {}
    inside = threading.Event()
    release = threading.Event()

    def other() -> None:
        seen["other"] = config.wiki_dir()
        release.set()

    def holder() -> None:
        with config.wiki_redirect(staging):
            seen["holder"] = config.wiki_dir()
            seen["holder_manifest"] = config.manifest_path()
            seen["holder_env"] = Path(config.child_env()["CITADEL_WIKI_DIR"])
            inside.set()
            release.wait(timeout=BARRIER_TIMEOUT)
        seen["holder_after"] = config.wiki_dir()

    t = threading.Thread(target=holder)
    t.start()
    inside.wait(timeout=BARRIER_TIMEOUT)
    other()
    t.join(timeout=BARRIER_TIMEOUT)

    assert seen["holder"] == staging
    assert seen["holder_manifest"] == staging / ".citadel_ingested.json"
    assert seen["holder_env"] == staging  # the child process sees the redirect through its own env
    assert seen["other"] == tmp_citadel.wiki  # a sibling thread keeps the live wiki
    assert seen["holder_after"] == tmp_citadel.wiki  # and the redirect is restored on exit
    assert config.WIKI_DIR == tmp_citadel.wiki  # the module attribute is never assigned at all


# --- the concurrency itself -------------------------------------------------------------------


def test_jobs_runs_sources_concurrently(tmp_citadel, fake_agent, cite_page):
    """Three sources, ``--jobs 3``: all three sessions must be in flight at the same moment. The
    barrier is the proof — on a serial run it would time out and every source would fail."""
    _sources(tmp_citadel, ["a", "b", "c"])
    barrier = threading.Barrier(3)
    agent = fake_agent(side_effect=_page_writer(cite_page, barrier))

    report = ingest.ingest(jobs=3)

    assert agent.count == 3
    assert sorted(report.processed) == ["raw/a.md", "raw/b.md", "raw/c.md"]
    assert report.errors == []
    assert report.raced == []
    assert sorted(manifest.load()) == ["raw/a.md", "raw/b.md", "raw/c.md"]
    for name in ("a", "b", "c"):
        assert (tmp_citadel.wiki / "misc" / f"{name}-md.md").is_file()


def test_default_run_stays_strictly_serial(tmp_citadel, fake_agent, cite_page):
    """The default is unchanged behavior: never more than one session in flight."""
    _sources(tmp_citadel, ["a", "b", "c"])
    in_flight = 0
    peak = 0
    lock = threading.Lock()

    def session(rel_key: str, kind: str = "ingest", *_args, **_kwargs) -> None:
        nonlocal in_flight, peak
        with lock:
            in_flight += 1
            peak = max(peak, in_flight)
        try:
            slug = rel_key.rsplit("/", 1)[-1].replace(".", "-")
            cite_page(f"misc/{slug}.md", rel_key, "A fact.")
        finally:
            with lock:
                in_flight -= 1

    fake_agent(side_effect=session)
    report = ingest.ingest()  # no jobs= -> config.JOBS, which defaults to 1

    assert peak == 1
    assert sorted(report.processed) == ["raw/a.md", "raw/b.md", "raw/c.md"]


def test_concurrent_promote_keeps_the_other_source_pages(tmp_citadel, fake_agent, cite_page):
    """The base-aware prune. Both sources clone the wiki BEFORE either promotes, so each one's
    staging copy lacks the other's page. Pruning "everything live has and staging does not" would
    delete the source that promoted first — the page must survive."""
    _sources(tmp_citadel, ["a", "b"])
    fake_agent(side_effect=_page_writer(cite_page, threading.Barrier(2)))

    report = ingest.ingest(jobs=2)

    assert report.errors == []
    assert report.raced == []
    assert (tmp_citadel.wiki / "misc" / "a-md.md").is_file()
    assert (tmp_citadel.wiki / "misc" / "b-md.md").is_file()


def test_seeded_pages_survive_a_parallel_run(tmp_citadel, fake_agent, cite_page, seed_page):
    """A page NO source in this run touches is never collateral damage of a base-aware prune."""
    seed_page(
        "concepts/existing.md",
        {"type": "Concept", "title": "Existing", "description": "d", "tags": ["t"]},
        "Prior knowledge.[^llm1]\n\n## Sources\n\n[^llm1]: LLM - model knowledge\n",
    )
    _sources(tmp_citadel, ["a", "b"])
    fake_agent(side_effect=_page_writer(cite_page, threading.Barrier(2)))

    ingest.ingest(jobs=2)

    assert (tmp_citadel.wiki / "concepts" / "existing.md").is_file()


def test_a_promote_applies_only_its_own_delta(tmp_citadel, fake_agent, cite_page, seed_page):
    """A source's staging copy also holds untouched copies of every page it did NOT write. Judging
    "what changed" against the LIVE wiki instead of against the clone would make a page a concurrent
    source just rewrote look like this source's change — and copying the untouched staging copy over
    it would silently revert that work. Here source ``b`` touches only its own page while ``a``
    rewrites a pre-existing one: ``a``'s rewrite must survive, and nothing may count as a race."""
    seed_page(
        "concepts/shared.md",
        {"type": "Concept", "title": "Shared", "description": "d", "tags": ["t"]},
        "Original text.[^llm1]\n\n## Sources\n\n[^llm1]: LLM - model knowledge\n",
    )
    _sources(tmp_citadel, ["a", "b"])
    barrier = threading.Barrier(2)

    def session(rel_key: str, kind: str = "ingest", *_args, **_kwargs) -> None:
        barrier.wait(timeout=BARRIER_TIMEOUT)  # both clones are taken before either promote
        slug = rel_key.rsplit("/", 1)[-1].replace(".", "-")
        cite_page(f"misc/{slug}.md", rel_key, "A fact.")
        if rel_key == "raw/a.md":
            cite_page("concepts/shared.md", rel_key, "Rewritten by a.")

    fake_agent(side_effect=session)
    report = ingest.ingest(jobs=2)

    assert report.raced == []  # b never touched shared.md, so there is nothing to race over
    assert report.errors == []
    assert "Rewritten by a." in (tmp_citadel.wiki / "concepts" / "shared.md").read_text(encoding="utf-8")


def test_racing_sources_are_re_run_serially(tmp_citadel, fake_agent, cite_page):
    """Two sessions that both write the SAME page cannot both be right: the second promote is
    refused (its base no longer matches), and that source is re-run serially afterwards — where it
    sees the winner's page and merges into it. Nothing is reported as an error, and the extra
    session is surfaced as a race so a corpus that races a lot can be dialled back."""
    _sources(tmp_citadel, ["a", "b"])
    barrier = threading.Barrier(2)

    def merged_body(rel_key: str, attempt: int) -> str:
        # Both sources aim at ONE page; the re-run (attempt 2) writes it again, this time on top of
        # what the winner promoted.
        return "concepts/shared.md"

    session = _page_writer(cite_page, barrier, page_for=merged_body)
    agent = fake_agent(side_effect=session)

    report = ingest.ingest(jobs=2)

    assert len(report.raced) == 1  # exactly one source lost the race
    assert report.errors == []
    assert sorted(report.processed) == ["raw/a.md", "raw/b.md"]
    assert agent.count == 3  # two first attempts + the loser's serial re-run
    loser = report.raced[0]
    assert session.attempts[loser] == 2  # type: ignore[attr-defined]
    # Both sources are recorded as ingested, and the page holds the re-run's (merged) text.
    assert sorted(manifest.load()) == ["raw/a.md", "raw/b.md"]
    page = (tmp_citadel.wiki / "concepts" / "shared.md").read_text(encoding="utf-8")
    assert "attempt 2" in page


def test_race_re_run_failure_is_a_normal_source_failure(tmp_citadel, fake_agent, cite_page):
    """If the serial re-run itself fails, the source fails like any other: nothing promoted for it,
    an error on the report, and no manifest entry — so the next run retries it."""
    _sources(tmp_citadel, ["a", "b"])
    barrier = threading.Barrier(2)
    writer = _page_writer(cite_page, barrier, page_for=lambda rel_key, attempt: "concepts/shared.md")

    def session(rel_key: str, kind: str = "ingest", *args, **kwargs) -> None:
        writer(rel_key, kind, *args, **kwargs)
        if writer.attempts[rel_key] == 2:  # type: ignore[attr-defined]
            raise RuntimeError("the re-run session failed")

    fake_agent(side_effect=session)
    report = ingest.ingest(jobs=2)

    assert len(report.raced) == 1
    loser = report.raced[0]
    assert report.processed == [k for k in ("raw/a.md", "raw/b.md") if k != loser]
    assert any("the re-run session failed" in e for e in report.errors)
    assert loser not in manifest.load()


def test_interrupt_keeps_the_work_already_promoted(tmp_citadel, fake_agent, cite_page):
    """A Ctrl+C during a parallel run still re-raises — but a source that had already been promoted
    is recorded, so the run never pays twice for work that is on the live wiki."""
    _sources(tmp_citadel, ["a", "b"])
    done_a = threading.Event()

    def session(rel_key: str, kind: str = "ingest", *_args, **_kwargs) -> None:
        if rel_key == "raw/a.md":
            cite_page("misc/a-md.md", rel_key, "A fact.")
            done_a.set()
            return
        done_a.wait(timeout=BARRIER_TIMEOUT)  # let a finish and promote first
        raise KeyboardInterrupt

    fake_agent(side_effect=session)

    with pytest.raises(KeyboardInterrupt):
        ingest.ingest(jobs=2)

    tracked = manifest.load()
    assert "raw/a.md" in tracked  # promoted AND recorded
    assert "raw/b.md" not in tracked
    assert (tmp_citadel.wiki / "misc" / "a-md.md").is_file()


def test_a_clone_hashes_identically_to_what_it_copied(tmp_citadel, seed_page):
    """The base is hashed off the fresh staging clone rather than off the live wiki, so the lock
    covers the copy alone and the wiki is read once instead of twice. That is only sound while a
    clone is byte-for-byte what it copied — for exactly the file set `_content_files` considers,
    including the non-`.md` files and the nested folders a promote also syncs."""
    seed_page("concepts/a.md", {"type": "Concept", "title": "A", "description": "d", "tags": ["t"]}, "Body.\n")
    seed_page("persons/b.md", {"type": "Person", "title": "B", "description": "d", "tags": ["t"]}, "Body.\n")
    (tmp_citadel.wiki / "concepts" / "attachment.txt").write_text("not markdown\n", encoding="utf-8")
    (tmp_citadel.wiki / ".citadel_ingested.json").write_text("{}", encoding="utf-8")  # excluded either way

    staging = ingest._make_staging(tmp_citadel.wiki)
    try:
        assert ingest._content_hashes(staging) == ingest._content_hashes(tmp_citadel.wiki)
        assert set(ingest._content_hashes(staging)) == {"concepts/a.md", "concepts/attachment.txt", "persons/b.md"}
    finally:
        ingest._robust_rmtree(staging)


def test_promote_leaves_in_flight_state_temps_alone(tmp_citadel):
    """The promote's leftover-temp sweep must not touch a HIDDEN ``*.citadeltmp``: that is an
    in-flight ``config.atomic_write_text`` of the manifest or the failures catalog. Under
    ``--jobs N`` the main thread saves the manifest while a worker promotes, and sweeping its temp
    turned a routine save into a FileNotFoundError."""
    live = tmp_citadel.wiki
    (live / "concepts").mkdir(parents=True, exist_ok=True)
    (live / "concepts" / "page.md").write_text("live\n", encoding="utf-8")
    staging = tmp_citadel.root / "staging"
    (staging / "concepts").mkdir(parents=True)
    (staging / "concepts" / "page.md").write_text("live\n", encoding="utf-8")

    in_flight = live / ".citadel_ingested.json.4321.citadeltmp"
    in_flight.write_text("{}", encoding="utf-8")
    leftover = live / "concepts" / "page.md.citadeltmp"
    leftover.write_text("half-written\n", encoding="utf-8")

    ingest._promote(staging, live)

    assert in_flight.is_file()  # another writer owns it
    assert not leftover.exists()  # a hard-killed promote's own leftover is still swept


def test_progress_callback_is_never_invoked_concurrently(tmp_citadel, fake_agent, cite_page):
    """Progress events now fire from worker threads, so the callback — anything a caller passed —
    must still be handed one event at a time. A callback that is not itself thread-safe (the common
    case: a counter, a file handle, an accumulating list) would otherwise corrupt silently, since
    ingest swallows callback exceptions by design."""
    _sources(tmp_citadel, ["a", "b", "c"])
    overlaps: list[str] = []
    inside = 0
    barrier = threading.Barrier(3)

    def progress(event: str, data: dict) -> None:
        nonlocal inside
        inside += 1  # deliberately unguarded: this is the caller's naive callback
        if inside != 1:
            overlaps.append(event)
        time.sleep(0.001)  # widen the window a racing thread would slip into
        inside -= 1

    fake_agent(side_effect=_page_writer(cite_page, barrier))
    ingest.ingest(jobs=3, progress=progress)

    assert overlaps == []


def test_a_raced_source_still_reports_what_it_spent_and_reused(tmp_citadel, fake_agent, monkeypatch):
    """A conflict is not recorded as a source outcome — it is re-run serially — but the session it
    already paid for and any checkpoint it already replayed are facts of the run either way. The
    session runner is faked here: the point is the DRIVER's bookkeeping, not another real race."""
    _sources(tmp_citadel, ["a", "b"])
    fake_agent()
    attempts: dict[str, int] = {}

    def fake_sessions(session_fns, rel_key, *, concurrent=False, **_kw):
        attempts[rel_key] = attempts.get(rel_key, 0) + 1
        if rel_key == "raw/a.md" and attempts[rel_key] == 1:
            return ingest._SourceOutcome(
                False,
                conflict=True,
                usage=llm.SessionUsage(cost_usd=0.25),
                resumed_note="raw/a.md (segments 1-2 of 4 restored from checkpoint)",
            )
        return ingest._SourceOutcome(True, usage=llm.SessionUsage(cost_usd=0.25))

    monkeypatch.setattr(ingest, "_run_agent_sessions", fake_sessions)
    report = ingest.ingest(jobs=2)

    assert report.raced == ["raw/a.md"]
    assert attempts["raw/a.md"] == 2  # the conflict really was re-run
    assert report.resumed == ["raw/a.md (segments 1-2 of 4 restored from checkpoint)"]
    # Three sessions were paid for: b, a's raced attempt, and a's serial re-run.
    assert report.usage is not None and report.usage.cost_usd == pytest.approx(0.75)


# --- the knob ---------------------------------------------------------------------------------


def test_jobs_below_one_is_refused(tmp_citadel, fake_agent):
    fake_agent()
    with pytest.raises(ValueError, match="at least 1"):
        ingest.ingest(jobs=0)


def test_cli_jobs_is_threaded_through(tmp_citadel, monkeypatch, capsys):
    seen: dict = {}

    def fake_ingest(paths=None, progress=None, full_rescan=False, force=False, jobs=None):
        seen["jobs"] = jobs
        return ingest.IngestReport([], [], [], [])

    monkeypatch.setattr(ingest, "ingest", fake_ingest)
    assert cli.main(["ingest", "--jobs", "4", "--quiet"]) == 0
    assert seen["jobs"] == 4


def test_cli_rejects_a_zero_job_count(tmp_citadel, capsys):
    assert cli.main(["ingest", "--jobs", "0"]) == 2
    assert "at least 1" in capsys.readouterr().err


def test_config_clamps_a_bad_jobs_value(monkeypatch):
    monkeypatch.setenv("CITADEL_JOBS", "0")
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    assert config._jobs_setting() == 1
    assert any("CITADEL_JOBS" in w for w in config.CONFIG_WARNINGS)


def test_progress_drops_the_spinner_when_running_parallel():
    """With several sources in flight there is no single "current source" for the spinner to name,
    so the console falls back to a start line per source."""
    from citadel.progress import ConsoleProgress

    progress = ConsoleProgress(stream=io.StringIO())
    progress("start", {"pending": 3, "skipped": 0, "jobs": 3})
    assert progress.spinner is False
