"""Blast radius (offline): one broken page, or one broken agent, must not cost the whole corpus.

Two independent failure modes from the same real incident, in which an agent CLI self-updated
mid-run into a build that could no longer launch its own tools. Every session then ran to
completion, spent its tokens, and changed nothing:

  1. the run's first job was a deletion cleanup. It changed nothing, so its post-condition failed
     and the vanished source's dangling ``[^sN]`` stayed on the page that cited it. From then on
     EVERY source whose session touched that page failed the all-or-nothing validation gate and was
     rolled back in full — sources that were themselves perfectly fine, failing forever, on a
     problem they did not cause and could not see;
  2. nothing noticed the agent was dead, so the run walked the remaining sources and billed a
     session for each one.

``llm.run_ingest_session`` is replaced by ``fake_agent`` throughout — no CLI is ever spawned.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, ingest, manifest, okf


# --- 1. inherited damage is not this source's fault ---------------------------------------


def _seed_page_with_dangling_citation(seed_page, name: str = "concepts/topic.md") -> None:
    """A page carrying a ``[^s2]`` to a raw file that does not exist — exactly what a deletion
    cleanup that failed to strip its provenance leaves behind. ``[^s1]`` stays honest, so the page
    is broken in one specific, nameable way."""
    seed_page(
        name,
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/kept.md"},
        "A true fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/kept.md](../../raw/kept.md) - kept\n"
        "[^s2]: [raw/vanished.md](../../raw/vanished.md) - vanished\n",
    )


def _append_fact(rel_path: str, marker: str, target: str) -> None:
    """A fake session's edit: add one more cited fact to an EXISTING page, reading the wiki through
    ``config.wiki_dir()`` so it lands in ingest's per-source staging copy like the real agent's."""
    page = Path(config.wiki_dir()) / rel_path
    frontmatter, body = okf.parse(page.read_text(encoding="utf-8"))
    body = body.replace("## Sources\n", f"Another fact.[^{marker}]\n\n## Sources\n").rstrip("\n")
    body += f"\n[^{marker}]: [{target}](../../{target}) - added\n"
    page.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def test_preexisting_breakage_does_not_fail_an_unrelated_source(tmp_citadel, fake_agent, seed_page):
    """THE REGRESSION. A page is already invalid (a dangling ``[^s2]``). A brand-new, unrelated
    source's session merely appends a fact to it. That source must be promoted and marked done —
    it did not cause the breakage, and blaming it means the source can never be ingested at all."""
    cit = tmp_citadel
    _seed_page_with_dangling_citation(seed_page)
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")
    (cit.raw / "fresh.md").write_text("a new source\n", encoding="utf-8")

    fake_agent(side_effect=lambda *a, **k: _append_fact("concepts/topic.md", "s3", "raw/fresh.md"))
    report = ingest.ingest([str(cit.raw / "fresh.md")])

    assert report.errors == []
    assert report.processed == ["raw/fresh.md"]
    assert "raw/fresh.md" in cit.read_manifest()
    # The edit really was promoted onto the LIVE wiki, not merely tolerated in staging.
    assert "Another fact.[^s3]" in (cit.wiki / "concepts/topic.md").read_text(encoding="utf-8")


def test_preexisting_breakage_is_reported_not_swallowed(tmp_citadel, fake_agent, seed_page):
    """The carve-out must not hide the problem: the pre-existing error is surfaced on the run
    report (and in its rendered text) as somebody's to fix, distinct from this run's errors."""
    cit = tmp_citadel
    _seed_page_with_dangling_citation(seed_page)
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")
    (cit.raw / "fresh.md").write_text("a new source\n", encoding="utf-8")

    fake_agent(side_effect=lambda *a, **k: _append_fact("concepts/topic.md", "s3", "raw/fresh.md"))
    report = ingest.ingest([str(cit.raw / "fresh.md")])

    assert any("concepts/topic.md" in i and "vanished.md" in i for i in report.inherited_issues)
    rendered = report.render()
    assert "pre-existing problems" in rendered
    assert "NOT caused by these sources" in rendered


def test_new_breakage_still_fails_the_source(tmp_citadel, fake_agent, seed_page):
    """The carve-out is exact, not a blanket amnesty. A session that adds a SECOND dangling
    citation — a different missing file — is still rolled back: that damage is its own."""
    cit = tmp_citadel
    _seed_page_with_dangling_citation(seed_page)
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")
    (cit.raw / "fresh.md").write_text("a new source\n", encoding="utf-8")

    before = (cit.wiki / "concepts/topic.md").read_text(encoding="utf-8")
    fake_agent(side_effect=lambda *a, **k: _append_fact("concepts/topic.md", "s3", "raw/also-missing.md"))
    report = ingest.ingest([str(cit.raw / "fresh.md")])

    assert any("also-missing.md" in e for e in report.errors)
    assert report.processed == []
    assert "raw/fresh.md" not in cit.read_manifest()
    assert (cit.wiki / "concepts/topic.md").read_text(encoding="utf-8") == before


def test_new_breakage_on_a_page_created_by_this_source_still_fails(tmp_citadel, fake_agent):
    """A page this source CREATED has no inherited state to forgive — it is the source's own work
    from the first byte, so an invalid new page fails exactly as it always did."""
    cit = tmp_citadel
    (cit.raw / "fresh.md").write_text("a new source\n", encoding="utf-8")

    fake_agent(
        pages={
            "concepts/new.md": (
                {"type": "Concept", "title": "New", "description": "d", "tags": ["x"], "resource": "raw/fresh.md"},
                "Fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/absent.md](../../raw/absent.md) - absent\n",
            )
        }
    )
    report = ingest.ingest([str(cit.raw / "fresh.md")])

    assert any("absent.md" in e for e in report.errors)
    assert report.processed == []


def test_failed_delete_cleanup_no_longer_blocks_the_rest_of_the_run(tmp_citadel, fake_agent, seed_page):
    """The incident end to end, minus the dead agent: a deletion cleanup that changes nothing fails
    its post-condition (as it must — the provenance is still there), and the pending source that
    follows it, whose session touches the very page the cleanup left broken, still lands."""
    cit = tmp_citadel
    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/kept.md"},
        "A true fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/kept.md](../../raw/kept.md) - kept\n"
        "[^s2]: [raw/vanished.md](../../raw/vanished.md) - vanished\n",
    )
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")
    (cit.raw / "fresh.md").write_text("a new source\n", encoding="utf-8")
    # raw/vanished.md is tracked but gone from disk -> a full run plans a delete cleanup for it.
    tracked = manifest.load()
    tracked["raw/vanished.md"] = manifest.make_entry("dd" * 32, None)
    manifest.save(tracked)

    def session(rel_key, kind="ingest", **kwargs):
        if kind == "delete":
            return None  # the dead agent: the cleanup session does nothing at all
        _append_fact("concepts/topic.md", "s3", "raw/fresh.md")

    fake_agent(side_effect=session)
    report = ingest.ingest()

    # The cleanup still fails loudly — the carve-out must not paper over a real post-condition.
    assert any("vanished.md" in e and "still cited" in e for e in report.errors)
    assert "raw/vanished.md" in cit.read_manifest()  # not forgotten: retried next full run
    # ...but it no longer takes the rest of the run down with it.
    assert "raw/fresh.md" in report.processed
    assert "Another fact.[^s3]" in (cit.wiki / "concepts/topic.md").read_text(encoding="utf-8")


def test_replayed_checkpoint_reports_its_inherited_issues(tmp_citadel, fake_agent, seed_page, monkeypatch):
    """ "Forgive but still report" has to hold on the resume path too. A page a checkpoint replays,
    and which no later segment touches again, is validated exactly once — inside the replay. If
    that one validation forgives an inherited error without recording it, the problem is waved
    through and never surfaced anywhere."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    cit = tmp_citadel
    (cit.raw / "kept.md").write_text("kept\n", encoding="utf-8")
    (cit.raw / "big.txt").write_text(
        "\n\n".join(f"Paragraph number {i} with some filler content about topic {i}." for i in range(6)),
        encoding="utf-8",
    )

    # The damage is ALREADY in the live wiki — the chunked source only appends to that page, so the
    # carve-out is what lets its segment 1 validate at all.
    _seed_page_with_dangling_citation(seed_page, "concepts/topic.md")

    # Run 1 appends on segment 1, then dies on segment 2 -> segment 1's delta is checkpointed.
    def fail_at_two(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        if segment[0] == 1:
            _append_fact("concepts/topic.md", "s3", rel_key)
        if segment[0] == 2:
            raise RuntimeError("segment 2 boom")

    fake_agent(side_effect=fail_at_two)
    ingest.ingest()

    # Run 2 replays segment 1 and its later segments never touch that page again.
    fake_agent()
    report = ingest.ingest()

    assert "raw/big.txt" in report.processed, "the replay must still be adopted, not refused"
    assert report.resumed, "the checkpoint must have been replayed, not restarted from segment 1"
    assert any("concepts/topic.md" in i and "vanished.md" in i for i in report.inherited_issues), (
        "an inherited error forgiven inside the replay must still reach the report"
    )


# --- 2. a dead agent stops the run instead of billing the corpus ---------------------------


def _pending_sources(cit, count: int) -> list[str]:
    """``count`` brand-new raw files, each with distinct content so none is a duplicate."""
    for i in range(count):
        (cit.raw / f"source-{i:02d}.md").write_text(f"source number {i}\n", encoding="utf-8")
    return sorted(str(p) for p in cit.raw.glob("source-*.md"))


def test_dead_agent_stops_the_run_at_the_stall_limit(tmp_citadel, fake_agent, monkeypatch):
    """An agent that runs, exits cleanly, and changes nothing must not be paid for the whole
    corpus. After CITADEL_STALL_LIMIT consecutive empty fresh sources the run stops dispatching."""
    monkeypatch.setattr(config, "STALL_LIMIT", 3)
    cit = tmp_citadel
    _pending_sources(cit, 10)

    agent = fake_agent()  # writes nothing, raises nothing, reports nothing: the dead-CLI signature
    report = ingest.ingest()

    assert agent.count == 3, "the run must stop after the limit, not walk the remaining sources"
    assert report.stalled
    assert "NO wiki changes" in report.stalled
    assert "STOPPED EARLY" in report.render()


def test_unattempted_sources_stay_pending(tmp_citadel, fake_agent, monkeypatch):
    """Stopping early costs nothing for the sources it skipped: they were never attempted, so they
    have no manifest entry and a plain re-run — with a healthy agent — folds them in. (The three
    empty sessions that tripped the guard WERE marked done, which is the pre-existing ``no_pages``
    contract; ``citadel ingest --retry`` is their recovery path, and the stall message says so.)"""
    monkeypatch.setattr(config, "STALL_LIMIT", 3)
    cit = tmp_citadel
    _pending_sources(cit, 10)

    fake_agent()
    stalled = ingest.ingest()
    assert len(cit.read_manifest()) == 3, "only the attempted sources are stamped"
    assert len(stalled.no_pages) == 3
    assert "--retry" in stalled.stalled

    def works(rel_key, kind="ingest", **kwargs):
        name = rel_key.rsplit("/", 1)[-1].removesuffix(".md")
        page = Path(config.wiki_dir()) / f"concepts/{name}.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            okf.dump(
                {"type": "Concept", "title": name, "description": "d", "tags": ["x"], "resource": rel_key},
                f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}](../../{rel_key}) - s\n",
            ),
            encoding="utf-8",
        )

    agent = fake_agent(side_effect=works)
    report = ingest.ingest()

    assert agent.count == 7, "the seven never attempted are still pending"
    assert not report.stalled
    assert len(cit.read_manifest()) == 10


def test_a_working_agent_resets_the_stall_count(tmp_citadel, fake_agent, monkeypatch):
    """The guard counts CONSECUTIVE empties. An agent that is merely selective — a couple of
    sources it finds nothing in, then one it does — is not a broken agent and must not be stopped
    (those empty sources are still flagged the way they always were, via ``no_pages``)."""
    monkeypatch.setattr(config, "STALL_LIMIT", 3)
    cit = tmp_citadel
    _pending_sources(cit, 9)

    seen: list[str] = []

    def every_third(rel_key, kind="ingest", **kwargs):
        seen.append(rel_key)
        if len(seen) % 3 != 0:
            return None
        name = rel_key.rsplit("/", 1)[-1].removesuffix(".md")
        page = Path(config.wiki_dir()) / f"concepts/{name}.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            okf.dump(
                {"type": "Concept", "title": name, "description": "d", "tags": ["x"], "resource": rel_key},
                f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}](../../{rel_key}) - s\n",
            ),
            encoding="utf-8",
        )

    agent = fake_agent(side_effect=every_third)
    report = ingest.ingest()

    assert agent.count == 9, "every source must be attempted"
    assert not report.stalled
    assert len(report.no_pages) == 6  # the empties are still surfaced, just not fatal


def test_a_reconcile_that_changed_pages_resets_the_count(tmp_citadel, fake_agent, seed_page, monkeypatch):
    """Counting and resetting are asymmetric about job kind, and this is the direction that is easy
    to get wrong. An empty reconcile is no evidence (never counted) — but a reconcile that CHANGED
    pages is proof the agent works, so it must reset the counter like any other source. Without
    that, a mixed run of fresh sources and reconciles — which is what scan order produces — can
    trip on an agent that has demonstrably just done work."""
    monkeypatch.setattr(config, "STALL_LIMIT", 3)
    cit = tmp_citadel
    # One already-ingested source whose bytes then change -> a reconcile in the next run...
    (cit.raw / "tracked.md").write_text("first version\n", encoding="utf-8")

    def write_tracked_page(rel_key, kind="ingest", **kwargs):
        page = Path(config.wiki_dir()) / "concepts/tracked.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            okf.dump(
                {"type": "Concept", "title": "Tracked", "description": "d", "tags": ["x"], "resource": rel_key},
                f"Version {len(page.read_text(encoding='utf-8')) if page.exists() else 0}.[^s1]\n\n"
                f"## Sources\n\n[^s1]: [{rel_key}](../../{rel_key}) - s\n",
            ),
            encoding="utf-8",
        )

    fake_agent(side_effect=write_tracked_page)
    ingest.ingest()
    (cit.raw / "tracked.md").write_text("second version, changed\n", encoding="utf-8")

    # ...interleaved with fresh sources the (broken-looking) agent leaves empty. Scan order is
    # alphabetical, so the reconcile of `tracked.md` lands between the empty fresh sources.
    for name in ("aaa.md", "bbb.md", "zzz.md"):
        (cit.raw / name).write_text(f"fresh {name}\n", encoding="utf-8")

    def empty_except_the_reconcile(rel_key, kind="ingest", **kwargs):
        if kind == "reconcile":
            write_tracked_page(rel_key, kind, **kwargs)  # this one really does change a page

    agent = fake_agent(side_effect=empty_except_the_reconcile)
    report = ingest.ingest()

    assert ("raw/tracked.md", "reconcile") in agent.calls, "the changed source must reconcile"
    assert not report.stalled, "a reconcile that changed pages is proof the agent works"
    assert agent.count == 4, "every source must still be attempted"


def test_reconcile_no_ops_never_trip_the_guard(tmp_citadel, fake_agent, monkeypatch):
    """A reconcile that changes nothing is a legitimate verdict ("I re-read it; it still says what
    the wiki says"), which is exactly what a healthy ``citadel refresh`` slice looks like. Those
    must never be counted as evidence of a dead agent."""
    monkeypatch.setattr(config, "STALL_LIMIT", 3)
    cit = tmp_citadel
    keys = _pending_sources(cit, 5)

    def works(rel_key, kind="ingest", **kwargs):
        name = rel_key.rsplit("/", 1)[-1].removesuffix(".md")
        page = Path(config.wiki_dir()) / f"concepts/{name}.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            okf.dump(
                {"type": "Concept", "title": name, "description": "d", "tags": ["x"], "resource": rel_key},
                f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}](../../{rel_key}) - s\n",
            ),
            encoding="utf-8",
        )

    fake_agent(side_effect=works)
    ingest.ingest()

    agent = fake_agent()  # every forced reconcile now changes nothing
    report = ingest.ingest(paths=keys, force=True)

    assert agent.count == 5, "a five-source reconcile that confirms the wiki must run in full"
    assert not report.stalled


def test_dead_agent_stops_a_parallel_run_too(tmp_citadel, fake_agent, monkeypatch):
    """``--jobs N`` must stop dispatching as well. Workers already in flight when the guard trips
    finish and are recorded normally (their sessions were already paid for), so the bound is the
    limit plus at most the in-flight ones — never the whole corpus."""
    monkeypatch.setattr(config, "STALL_LIMIT", 3)
    cit = tmp_citadel
    _pending_sources(cit, 24)

    agent = fake_agent()
    report = ingest.ingest(jobs=4)

    assert report.stalled
    # A deliberately loose bound, asserting the PROPERTY (the run stops dispatching) rather than an
    # exact count: the overshoot is however many workers picked up a source in the window between
    # the guard tripping and the main thread cancelling, which is scheduling-dependent. It is wider
    # here than it can ever be in practice, because these fake sessions return instantly while a
    # real one takes minutes — long enough for the cancel to land after at most `--jobs` more.
    assert agent.count <= 12, "the run must stop dispatching, not walk the corpus"
    assert len(cit.read_manifest()) == agent.count, "nothing was attempted after the stop"


def test_stall_guard_can_be_disabled(tmp_citadel, fake_agent, monkeypatch):
    """``CITADEL_STALL_LIMIT=0`` restores the pre-guard behavior exactly."""
    monkeypatch.setattr(config, "STALL_LIMIT", 0)
    cit = tmp_citadel
    _pending_sources(cit, 6)

    agent = fake_agent()
    report = ingest.ingest()

    assert agent.count == 6
    assert not report.stalled


def test_deletion_nothing_cites_is_not_a_stall(tmp_citadel, fake_agent, monkeypatch):
    """A tracked source that vanished and that NO page cites needs no session at all. Its "no
    changes" is the correct answer, not evidence — it must not count toward the limit."""
    monkeypatch.setattr(config, "STALL_LIMIT", 1)
    cit = tmp_citadel
    (cit.raw / "fresh.md").write_text("a new source\n", encoding="utf-8")
    tracked = manifest.load()
    for i in range(3):
        tracked[f"raw/orphan-{i}.md"] = manifest.make_entry(f"{i}{i}" * 32, None)
    manifest.save(tracked)

    def works(rel_key, kind="ingest", **kwargs):
        page = Path(config.wiki_dir()) / "concepts/fresh.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text(
            okf.dump(
                {"type": "Concept", "title": "Fresh", "description": "d", "tags": ["x"], "resource": rel_key},
                f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}](../../{rel_key}) - s\n",
            ),
            encoding="utf-8",
        )

    agent = fake_agent(side_effect=works)
    report = ingest.ingest()

    assert len(report.sources_deleted) == 3
    assert not report.stalled
    assert agent.count == 1, "only the pending file needed a session"
    assert report.processed == ["raw/fresh.md"]
