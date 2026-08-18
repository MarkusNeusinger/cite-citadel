"""Resume checkpoints for chunked sources (offline): a run that dies at segment N no longer throws
away segments 1..N-1's paid agent work — the next run replays their delta into its fresh staging
copy and continues at segment N (citadel/resume.py, audit backlog #9).

What must NOT change is pinned just as hard as what does: promotion still happens exactly once,
nothing partial ever reaches the live wiki, and EVERY guard failure (changed source, changed
model/rules/knobs, damaged slot, a live page moved underneath, a replay that no longer validates,
too many fruitless adoptions) falls back to a full restart at segment 1 **in the same run** — never
a failed source, never a wasted session. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from citadel import config, failures, ingest, ingest_sessions, llm, manifest, okf, resume, runlock, store


def _paras(n: int) -> str:
    """n paragraphs (~55 chars each), each individually identifiable — the chunking fixture."""
    return "\n\n".join(f"Paragraph number {i} with some filler content about topic {i}." for i in range(n))


@pytest.fixture
def chunked_source(tmp_citadel, monkeypatch):
    """A raw source that splits into several segments (3 at this threshold)."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (tmp_citadel.raw / "big.txt").write_text(_paras(6), encoding="utf-8")
    return tmp_citadel


def _fail_at(segment_no: int, cite_page, page: str = "misc/big.md"):
    """A fake session that writes ``page`` on segment 1 and raises on ``segment_no``."""

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if segment[0] == 1:
            cite_page(page, rel_key, "A fact from segment one.")
        if segment[0] == segment_no:
            raise RuntimeError(f"segment {segment_no} boom")

    return fake


def _record_segments(calls: list):
    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        calls.append(segment)

    return fake


# --- the happy path --------------------------------------------------------------------------


def test_failed_segment_is_checkpointed_and_resumed(chunked_source, fake_agent, cite_page):
    """Run 1 dies at segment 2: nothing is promoted, but segment 1's work is on disk as a
    checkpoint. Run 2 replays it and opens at segment 2 — segment 1 is never paid for twice, and
    the page it wrote is promoted at the end without any session re-creating it."""
    wiki = chunked_source.wiki
    fake_agent(side_effect=_fail_at(2, cite_page))
    first = ingest.ingest()

    assert "raw/big.txt" not in first.processed
    assert not (wiki / "misc" / "big.md").exists()  # promote-once: nothing partial reaches live
    assert resume.pending() == [resume.Pending("raw/big.txt", 1, 3)]  # ... but segment 1's work is banked

    calls: list = []
    fake_agent(side_effect=_record_segments(calls))
    second = ingest.ingest()

    assert calls == [(2, 3), (3, 3)]  # continued at 2
    assert second.processed == ["raw/big.txt"]
    assert (wiki / "misc" / "big.md").exists()
    assert "segment one" in (wiki / "misc" / "big.md").read_text(encoding="utf-8")
    assert second.resumed == ["raw/big.txt (segments 1-1 of 3 restored from checkpoint)"]
    assert "Resumed (continued from an earlier run's checkpoint)" in second.render()
    assert resume.pending() == []  # the work is live: the checkpoint is dropped


def test_checkpoint_captures_edits_no_session_diff_reports(chunked_source, fake_agent, cite_page, monkeypatch):
    """The delta is the PROMOTE's file-level view, not the agent's page diff.

    Segment 2 renames a page, so ``_repair_renames`` repoints its inbound links — writing pages no
    session touched, after that segment's diff and before the next segment's re-baseline. A
    checkpoint built from the diff lists would silently drop those repairs and promote a wiki with
    dangling cross-links that an unbroken run never had."""
    wiki = chunked_source.wiki

    def page(rel_path: str, title: str, body: str) -> None:
        target = Path(config.wiki_dir()) / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            okf.dump(
                {"type": "Concept", "title": title, "description": "d", "tags": ["t"], "resource": "raw/big.txt"}, body
            ),
            encoding="utf-8",
        )

    sources = "\n\n## Sources\n\n[^s1]: [raw/big.txt](../../raw/big.txt) - src\n"

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if segment[0] == 1:
            page("concepts/kaffee.md", "Kaffee", "A fact.[^s1]" + sources)
            page("concepts/hub.md", "Hub", "See [Kaffee](kaffee.md).[^s1]" + sources)
        elif segment[0] == 2:  # rename: same title, new path -> _repair_renames repoints hub.md
            (Path(config.wiki_dir()) / "concepts" / "kaffee.md").unlink()
            page("concepts/coffee.md", "Kaffee", "A fact.[^s1]" + sources)
        elif segment[0] == 3:
            raise RuntimeError("segment three boom")

    fake_agent(side_effect=fake)
    ingest.ingest()

    fake_agent(side_effect=_record_segments([]))
    assert ingest.ingest().processed == ["raw/big.txt"]

    hub = (wiki / "concepts" / "hub.md").read_text(encoding="utf-8")
    assert "coffee.md" in hub and "kaffee.md" not in hub  # the repair survived the checkpoint
    assert not (wiki / "concepts" / "kaffee.md").exists()  # ... and so did the rename's deletion
    assert store.find_broken_links(store.load()) == []


def test_manifest_stamp_sums_both_runs_while_each_report_is_its_own(chunked_source, fake_agent, cite_page):
    """Money is reported twice in two different senses, and neither may double-count: each RUN
    reports what it spent, while the manifest stamps the whole cost of importing the source
    ("one combined usage, matching promote-once semantics") across the runs that paid it."""
    fake_agent(side_effect=_fail_at(2, cite_page), usage=llm.SessionUsage(cost_usd=0.25, input_tokens=100))
    first = ingest.ingest()
    assert first.usage.cost_usd == pytest.approx(0.25)  # segment 1 (the raising one reports nothing)

    fake_agent(side_effect=_record_segments([]), usage=llm.SessionUsage(cost_usd=0.25, input_tokens=100))
    second = ingest.ingest()

    assert second.usage.cost_usd == pytest.approx(0.50)  # segments 2 + 3: only THIS run's spend
    entry = chunked_source.read_manifest()["raw/big.txt"]
    assert entry["cost_usd"] == pytest.approx(0.75)  # the whole import: 0.25 carried + 0.50 now
    assert entry["tokens_in"] == 300


def test_promote_failure_after_the_last_segment_resumes_with_no_sessions(
    chunked_source, fake_agent, cite_page, monkeypatch
):
    """The most expensive failure of all — every segment paid for, then the promote itself fails —
    becomes a free retry: the next run replays the complete delta and promotes it without opening
    a single session."""

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")

    real_promote, failing = ingest._promote, [True]

    def boom(staging, live, **kwargs):
        if failing[0]:
            raise OSError("share went away mid-promote")
        return real_promote(staging, live, **kwargs)

    monkeypatch.setattr(ingest_sessions, "_promote", boom)
    fake_agent(side_effect=fake)
    assert ingest.ingest().processed == []
    assert resume.pending() == [resume.Pending("raw/big.txt", 3, 3)]  # all three segments banked

    failing[0] = False
    calls: list = []
    fake_agent(side_effect=_record_segments(calls))
    second = ingest.ingest()

    assert calls == []  # nothing left to run — and nothing left to pay for
    assert second.processed == ["raw/big.txt"]
    assert (chunked_source.wiki / "misc" / "big.md").exists()


# --- the guards: every one of these falls back to a full restart ------------------------------


def _assert_full_restart(report, calls, wiki) -> None:
    """The shared post-condition of every guard: the source ran from segment 1, succeeded, and
    nothing was recorded as a failure — i.e. exactly the pre-resume behavior."""
    assert calls and calls[0] == (1, 3) and len(calls) == 3
    assert report.processed == ["raw/big.txt"]
    assert report.resumed == []
    assert "raw/big.txt" not in failures.load()


def test_changed_source_discards_the_checkpoint(chunked_source, fake_agent, cite_page):
    """sha256 stays the sole arbiter of "changed": new bytes are a different job, so segment 3 of
    the old text may never be merged into pages built from it."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()
    (chunked_source.raw / "big.txt").write_text(_paras(6) + "\n\nA later addition entirely.", encoding="utf-8")

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    report = ingest.ingest()

    assert calls[0] == (1, calls[0][1])  # restarted at segment 1 against the new text
    assert report.resumed == [] and report.processed == ["raw/big.txt"]


def test_prompt_shaping_knob_flip_discards_the_checkpoint(chunked_source, fake_agent, cite_page, monkeypatch):
    """A knob the rules hash does not cover (here the wiki's target language) changes what the
    agent writes — resuming would merge German segments into English pages, a cluster no single
    run could produce."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()
    monkeypatch.setattr(config, "WIKI_LANG", "de")

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)


def test_guidance_flip_discards_the_checkpoint(chunked_source, fake_agent, cite_page, monkeypatch):
    """The operator steer (``ingest --guidance``) joins the prompt-knob identity: segments written
    under one steer must never be merged with segments written under another."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()
    monkeypatch.setattr(config, "INGEST_GUIDANCE", "create one machine registry", raising=False)

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)


def test_related_source_budget_flip_discards_the_checkpoint(chunked_source, fake_agent, cite_page, monkeypatch):
    """The related-source budget (``CITADEL_RELATED_SOURCES``) is a prompt knob like the rest:
    segments folded in with other sources consultable must never be merged with segments folded in
    without them — the two see a different corpus."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()
    monkeypatch.setattr(config, "RELATED_SOURCES", 0, raising=False)

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)


def test_model_change_discards_the_checkpoint(chunked_source, fake_agent, cite_page, monkeypatch):
    """Half a source imported by one model and half by another is exactly what a model upgrade
    must NOT silently produce."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()
    monkeypatch.setattr(config, "ingest_model_label", lambda: "some-other-model")

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)


def test_damaged_checkpoint_discards_itself(chunked_source, fake_agent, cite_page):
    """Integrity guard: a blob that no longer hashes to what the record names (a torn write, a
    half-synced dotdir, a hand-edited slot) is never replayed."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()
    slot = resume.slot_for("raw/big.txt")
    (slot / resume.PAGES_DIR_NAME / "misc" / "big.md").write_text("tampered\n", encoding="utf-8")

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)
    assert resume.pending() == []


def test_live_page_changed_underneath_discards_the_checkpoint(chunked_source, fake_agent, cite_page, seed_page):
    """Base-state guard: another source promoted a change to a page the delta also touches.
    Replaying would silently overwrite that newer work with this checkpoint's older version."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()
    # Stand in for another source's promote landing on the same page between the two runs.
    seed_page(
        "misc/big.md",
        {"type": "Note", "title": "Fact", "description": "d", "tags": ["t"], "resource": "raw/big.txt"},
        "Newer work from somewhere else.[^s1]\n\n## Sources\n\n[^s1]: [raw/big.txt](../../raw/big.txt) - src\n",
    )

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)


def test_replay_that_no_longer_validates_discards_the_checkpoint(chunked_source, fake_agent, cite_page):
    """A checkpointed page cites a second source that is deleted between the runs. Replaying it
    would promote a page whose ``[^sN]`` points at nothing — an error-severity `citadel check`
    failure on an already-promoted wiki. The gate runs BEFORE the first resumed session, so the
    discard costs nothing."""
    (chunked_source.docs / "spec.md").write_text("A spec.\n", encoding="utf-8")

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if segment[0] == 1:
            target = Path(config.wiki_dir()) / "misc" / "big.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                okf.dump(
                    {"type": "Note", "title": "F", "description": "d", "tags": ["t"], "resource": rel_key},
                    "A fact.[^s1] And another.[^s2]\n\n## Sources\n\n"
                    "[^s1]: [raw/big.txt](../../raw/big.txt) - src\n"
                    "[^s2]: [docs/spec.md](../../docs/spec.md) - spec\n",
                ),
                encoding="utf-8",
            )
        if segment[0] == 2:
            raise RuntimeError("segment two boom")

    fake_agent(side_effect=fake)
    ingest.ingest()
    assert resume.pending() == [resume.Pending("raw/big.txt", 1, 3)]
    (chunked_source.docs / "spec.md").unlink()

    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)


def test_repeated_fruitless_resumes_fall_back_to_a_full_retry(chunked_source, fake_agent, cite_page):
    """A deterministically poisonous segment must not wedge a source into failing cheaply forever:
    after ATTEMPT_CAP adoptions the checkpoint is dropped and the source is retried in full."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()  # writes the checkpoint (segment 1 done)

    seen: list[list] = []
    for _ in range(resume.ATTEMPT_CAP + 1):
        calls: list = []

        def fake(rel_key, kind="ingest", read_path=None, segment=None, _calls=calls):
            _calls.append(segment)
            if segment[0] == 1:
                cite_page("misc/big.md", rel_key, "A fact from segment one.")
            if segment[0] == 2:
                raise RuntimeError("segment two boom")

        fake_agent(side_effect=fake)
        ingest.ingest()
        seen.append(calls)

    assert [c[0] for c in seen[:-1]] == [(2, 3)] * resume.ATTEMPT_CAP  # cheap re-attempts
    assert seen[-1][0] == (1, 3)  # ... then one honest full retry


def test_disabled_knob_writes_and_reads_nothing(chunked_source, fake_agent, cite_page, monkeypatch):
    """CITADEL_RESUME=0 is the pre-#9 behavior byte for byte: no sidecar, full restart."""
    monkeypatch.setattr(config, "RESUME", False)
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()

    assert not resume.cache_dir().exists()
    calls: list = []
    fake_agent(side_effect=lambda *a, **k: (calls.append(k.get("segment")), cite_page("misc/big.md", a[0], "F."))[0])
    _assert_full_restart(ingest.ingest(), calls, chunked_source.wiki)


def test_single_pass_sources_never_checkpoint(tmp_citadel, fake_agent, cite_page):
    """Only a chunked source has an earlier segment worth saving; everything else is unchanged."""
    (tmp_citadel.raw / "small.md").write_text("a small source\n", encoding="utf-8")
    fake_agent(error=RuntimeError("session boom"))
    ingest.ingest()
    assert resume.pending() == []


# --- the store itself ------------------------------------------------------------------------


def test_replay_refuses_a_deletion_whose_page_moved_underneath(tmp_citadel, seed_page):
    """A recorded DELETION is the one replayed operation that can destroy another source's work,
    so it is guarded by the same base hash as a rewrite — and a slot that somehow lost that hash is
    refused outright rather than trusted."""
    for name in ("legacy", "keep"):
        seed_page(
            f"concepts/{name}.md",
            {"type": "Concept", "title": name, "description": "d", "tags": ["t"], "resource": "raw/a.md"},
            "Old.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n",
        )
    live = tmp_citadel.wiki
    # Staging as a real session would leave it: the live wiki minus the page this delta removes.
    staging = live.parent / "staging"
    (staging / "concepts").mkdir(parents=True)
    (staging / "concepts" / "keep.md").write_text(
        (live / "concepts" / "keep.md").read_text(encoding="utf-8"), encoding="utf-8"
    )
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=3, shape="s")

    with runlock.hold("test"):
        assert resume.save(plan, 1, staging, live, changed=[], removed=["concepts/legacy.md"], usage={})
        cp = resume.load(plan)
        assert cp is not None and cp.bases["concepts/legacy.md"]

        # Another source rewrites that page before the resumed run gets to it.
        (live / "concepts" / "legacy.md").write_text("rewritten by someone else\n", encoding="utf-8")
        assert resume.replay(cp, staging, live) is None  # refused, so the newer page survives


def test_a_wipe_the_wiki_delta_is_never_recorded(tmp_citadel, seed_page):
    """A staging tree with no content page while live has some is what a vanished/rm-tree'd staging
    looks like — the promote refuses it, so it must never be banked as a replayable delta either
    (the generated `index.md` a staging copy always carries must not count as content)."""
    seed_page(
        "concepts/a.md",
        {"type": "Concept", "title": "A", "description": "d", "tags": ["t"], "resource": "raw/a.md"},
        "F.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n",
    )
    (tmp_citadel.wiki / "index.md").write_text("# generated\n", encoding="utf-8")
    empty_staging = tmp_citadel.wiki.parent / "staging"
    empty_staging.mkdir()
    (empty_staging / "index.md").write_text("# generated\n", encoding="utf-8")

    assert ingest._checkpoint_delta(empty_staging, tmp_citadel.wiki) is None
    assert not resume._has_content(empty_staging)  # the generated index is not content


def test_an_unreadable_live_page_is_not_treated_as_absent(tmp_citadel, seed_page, monkeypatch):
    """ "Absent" and "there but unreadable" must never be conflated: a page the guard cannot read is
    a page the replay cannot prove it may overwrite."""
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    (staging / "concepts").mkdir(parents=True)
    (staging / "concepts" / "new.md").write_text("staged\n", encoding="utf-8")
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")

    with runlock.hold("test"):
        assert resume.save(plan, 1, staging, live, changed=["concepts/new.md"], removed=[], usage={})
        cp = resume.load(plan)
        assert cp is not None and cp.bases["concepts/new.md"] is None  # absent when banked

        # The page now EXISTS in live (another source created it) but cannot be hashed.
        (live / "concepts").mkdir(parents=True, exist_ok=True)
        (live / "concepts" / "new.md").write_text("someone else's work\n", encoding="utf-8")
        monkeypatch.setattr(resume, "_sha256_file", lambda path: None)
        assert resume.replay(cp, staging, live) is None

        # And such a page can't be banked as a base in the first place.
        monkeypatch.undo()
        real_sha = resume._sha256_file
        monkeypatch.setattr(resume, "_sha256_file", lambda path: None if live in path.parents else real_sha(path))
        assert resume.save(plan, 1, staging, live, changed=["concepts/new.md"], removed=[], usage={}) is False


def test_a_record_missing_a_base_is_refused(tmp_citadel):
    """replay guards on ``bases``, so a page absent from it would be written unguarded. The record
    is a file on disk — the invariant is re-checked on READ, never trusted from the write side."""
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    staging.mkdir()
    (staging / "page.md").write_text("staged\n", encoding="utf-8")
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    with runlock.hold("test"):
        assert resume.save(plan, 1, staging, live, changed=["page.md"], removed=[], usage={})
        record_path = resume.slot_for("raw/a.md") / resume.RECORD_NAME
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["bases"] = {}
        record_path.write_text(json.dumps(record), encoding="utf-8")
        assert resume.load(plan) is None


def test_a_foreign_workspace_slot_is_refused_on_load(tmp_citadel, monkeypatch):
    """The workspace stamp is enforced where it matters — at adoption — not only by the age sweep."""
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    staging.mkdir()
    (staging / "page.md").write_text("staged\n", encoding="utf-8")
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    with runlock.hold("test"):
        assert resume.save(plan, 1, staging, live, changed=["page.md"], removed=[], usage={})
        monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_citadel.root / "elsewhere")
        assert resume.load(plan) is None


def test_a_no_op_delta_is_never_banked(tmp_citadel):
    """A checkpoint whose delta is empty can only ever SKIP work — at completed == total it would
    let a later run promote nothing, report the source as processed, and never open a session. So
    a segment that changed nothing banks nothing."""
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    staging.mkdir()
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    with runlock.hold("test"):
        assert resume.save(plan, 2, staging, live, changed=[], removed=[], usage={}) is False
        assert resume.pending() == []


def test_a_deletion_that_did_not_apply_fails_the_replay(tmp_citadel, seed_page, monkeypatch):
    """A half-applied delta is worse than none: if a banked deletion cannot be carried out in the
    staging copy, promoting would resurrect a page the completed segments removed."""
    for name in ("legacy", "keep"):
        seed_page(
            f"concepts/{name}.md",
            {"type": "Concept", "title": name, "description": "d", "tags": ["t"], "resource": "raw/a.md"},
            "Old.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n",
        )
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    (staging / "concepts").mkdir(parents=True)
    for name in ("legacy", "keep"):
        (staging / "concepts" / f"{name}.md").write_text(
            (live / "concepts" / f"{name}.md").read_text(encoding="utf-8"), encoding="utf-8"
        )
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")

    with runlock.hold("test"):
        assert resume.save(plan, 1, staging, live, changed=[], removed=["concepts/legacy.md"], usage={})
        cp = resume.load(plan)
        # The unlink silently fails (a share lock / the Windows read-only bit).
        monkeypatch.setattr(Path, "unlink", lambda self, missing_ok=False: None)
        assert resume.replay(cp, staging, live) is None


def test_a_changed_path_that_is_not_a_file_refuses_the_checkpoint(tmp_citadel):
    """Same rule as a failed deletion: a delta the store cannot record in FULL is not the promote's
    delta, and a partial one replayed as truth is a silently wrong wiki."""
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    staging.mkdir()
    (staging / "real.md").write_text("staged\n", encoding="utf-8")
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    with runlock.hold("test"):
        # "gone.md" is in the delta but not on disk (it vanished between the walk and the copy).
        assert resume.save(plan, 1, staging, live, changed=["real.md", "gone.md"], removed=[], usage={}) is False
        assert resume.pending() == []  # nothing half-recorded is left behind either


def test_pending_never_raises_on_duplicate_keys(tmp_citadel):
    """`pending()` is called by read-only surfaces on the promise that it never raises. Two slots
    claiming the same key (a hand-copied dotdir) must not make the sort compare a None cost against
    a float."""
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    staging.mkdir()
    (staging / "page.md").write_text("staged\n", encoding="utf-8")
    with runlock.hold("test"):
        for key, usage in (("raw/a.md", {"cost_usd": 0.5}), ("raw/b.md", {})):
            plan = resume.Plan(key=key, sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
            assert resume.save(plan, 1, staging, live, changed=["page.md"], removed=[], usage=usage)
        # Make the second slot claim the FIRST slot's key, so only the later fields can break a tie.
        second = resume.slot_for("raw/b.md") / resume.RECORD_NAME
        record = json.loads(second.read_text(encoding="utf-8"))
        record["key"] = "raw/a.md"
        second.write_text(json.dumps(record), encoding="utf-8")

        listed = resume.pending()
        assert [p.key for p in listed] == ["raw/a.md", "raw/a.md"]


def test_robust_rmtree_never_raises(tmp_path):
    """It runs in `finally` blocks, so an escaping exception would mask the failure that got us
    there. A target rmtree refuses outright (here: a plain file) must still return quietly."""
    target = tmp_path / "not-a-directory"
    target.write_text("x\n", encoding="utf-8")
    config.robust_rmtree(target, attempts=1)  # must not raise
    config.robust_rmtree(tmp_path / "does-not-exist", attempts=1)


def test_clear_needs_the_run_lock(tmp_citadel):
    """Deleting a slot is a mutation like any other: a run that lost its lock owns nothing."""
    live = tmp_citadel.wiki
    staging = live.parent / "staging"
    staging.mkdir()
    (staging / "page.md").write_text("staged\n", encoding="utf-8")
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    with runlock.hold("test"):
        assert resume.save(plan, 1, staging, live, changed=["page.md"], removed=[], usage={})
    resume.clear("raw/a.md")  # no lock held any more
    assert resume.pending() == [resume.Pending("raw/a.md", 1, 2)]


def test_sweep_drops_old_and_foreign_slots(tmp_citadel, monkeypatch):
    """Hygiene at run start: age (a slot nobody came back for) and workspace identity (a slot
    written by a different workspace sharing this parent directory)."""
    staging = tmp_citadel.wiki.parent / "staging"
    staging.mkdir()
    (staging / "page.md").write_text("staged\n", encoding="utf-8")
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    with runlock.hold("test"):
        assert resume.save(plan, 1, staging, tmp_citadel.wiki, changed=["page.md"], removed=[], usage={})
        assert resume.pending() == [resume.Pending("raw/a.md", 1, 2)]

        resume.sweep(max_age_days=0)  # everything on disk is "old"
        assert resume.pending() == []

        assert resume.save(plan, 1, staging, tmp_citadel.wiki, changed=["page.md"], removed=[], usage={})
        monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_citadel.root / "elsewhere")
        resume.sweep()
        assert resume.pending() == []


def test_usage_is_filtered_like_a_manifest_stamp(tmp_citadel):
    """The carried cost round-trips through an on-disk sidecar into the manifest, so it passes the
    same defensive filter: no bools, no NaN/inf, no negative token counts."""
    staging = tmp_citadel.wiki.parent / "staging"
    staging.mkdir()
    (staging / "page.md").write_text("staged\n", encoding="utf-8")
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    with runlock.hold("test"):
        resume.save(
            plan,
            1,
            staging,
            tmp_citadel.wiki,
            changed=["page.md"],
            removed=[],
            usage={"cost_usd": float("inf"), "tokens_in": -5, "tokens_out": 12},
        )
        assert resume.load(plan).usage == {"tokens_out": 12}


def test_checkpoints_are_never_written_without_the_run_lock(tmp_citadel):
    """A stalled run whose lock another run reclaimed owns nothing any more — least of all durable
    state the new holder is already writing."""
    staging = tmp_citadel.wiki.parent / "staging"
    staging.mkdir()
    plan = resume.Plan(key="raw/a.md", sha="a" * 64, kind="ingest", model="m", rules_version="r", total=2, shape="s")
    assert not runlock.owned()
    assert resume.save(plan, 1, staging, tmp_citadel.wiki, changed=[], removed=[], usage={}) is False


def test_manifest_and_failure_state_are_untouched_by_a_checkpointed_failure(chunked_source, fake_agent, cite_page):
    """The checkpoint is the ONLY thing a failed chunked source leaves behind that is new: it is
    still not marked done, and it is still recorded as a failure for triage."""
    fake_agent(side_effect=_fail_at(2, cite_page))
    ingest.ingest()

    assert "raw/big.txt" not in chunked_source.read_manifest()
    assert failures.load()["raw/big.txt"]["reason"] == failures.ERROR
    assert manifest.load() == {}


# --- the chunk budget reaches the checkpoint -----------------------------------------------------


def test_stated_context_makes_a_would_be_single_pass_source_resumable(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """The other half of the local-model bug. A source UNDER MAX_SOURCE_CHARS plans one pass, and a
    single-pass source never checkpoints — so a session that dies half-way through it (exactly what a
    small context does) loses everything, every time. Stating the model's context splits the source,
    and chunked sources bank their completed segments."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 300000)  # alone: one pass, nothing bankable
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 50000)  # -> a 20000-char window
    body = _paras(1100)
    assert len(body) < config.MAX_SOURCE_CHARS  # the premise
    (tmp_citadel.raw / "big.txt").write_text(body, encoding="utf-8")

    fake_agent(side_effect=_fail_at(2, cite_page))
    first = ingest.ingest()

    assert "raw/big.txt" not in first.processed  # the source still failed ...
    assert not (tmp_citadel.wiki / "misc" / "big.md").exists()  # ... and promoted nothing
    waiting = resume.pending()
    assert [(p.key, p.completed) for p in waiting] == [("raw/big.txt", 1)]  # ... but segment 1 is banked
    assert waiting[0].total >= 3

    calls: list = []
    fake_agent(side_effect=_record_segments(calls))
    second = ingest.ingest()

    assert calls and calls[0][0] == 2  # continued at segment 2, never re-paying segment 1
    assert second.processed == ["raw/big.txt"]
    assert resume.pending() == []


def test_plan_shape_changes_when_the_stated_context_changes(monkeypatch):
    """The segment shape is fingerprinted from the EFFECTIVE budget, not the raw char threshold.
    Without this, changing only CITADEL_MODEL_CONTEXT_TOKENS would re-split a source while the
    checkpoint still claimed to describe it, and "segment 3" would name text its predecessor never
    saw."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 300000)
    passes = [(None, (1, 2), None), (None, (2, 2), None)]

    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 50000)
    narrow = ingest_sessions._plan_shape(passes)
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 100000)
    wide = ingest_sessions._plan_shape(passes)

    assert narrow and wide and narrow != wide
