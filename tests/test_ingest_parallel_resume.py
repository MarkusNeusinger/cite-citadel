"""Where ``--jobs N`` meets the resume checkpoints of a CHUNKED source (offline).

A checkpoint is a promise about the live wiki: "these pages should hold these bytes, these should
be gone, and here is what they looked like when I banked it". Under concurrency that promise has a
second party — another source promoting between this one's clone and its checkpoint — so the delta
must be measured against the wiki THIS source was cloned from, never against a live wiki that has
since moved on. Both tests below fail (silently corrupting the wiki) when it is measured against
live: a checkpoint is durable, so the damage outlives the parallel run and lands in a later,
possibly serial, one.
"""

from __future__ import annotations

import threading

import pytest

from citadel import config, ingest, manifest


TIMEOUT = 10


def _paras(n: int) -> str:
    """n paragraphs, each individually identifiable — the chunking fixture (mirrors
    tests/test_ingest_resume.py)."""
    return "\n\n".join(f"Paragraph number {i} with some filler content about topic {i}." for i in range(n))


def _await_live(path, timeout: float = TIMEOUT) -> None:
    """Block until ``path`` exists in the LIVE wiki — i.e. until the other source's promote has
    landed. The one ordering the tests need: a promote is not observable through the agent seam,
    but its result is."""
    deadline = threading.Event()
    for _ in range(int(timeout * 100)):
        if path.exists():
            return
        deadline.wait(0.01)
    raise AssertionError(f"timed out waiting for {path} to be promoted")


@pytest.fixture
def chunked_and_plain(tmp_citadel, monkeypatch):
    """One CHUNKED source (3 segments) plus one ordinary source, so a run with ``--jobs 2`` has a
    checkpointing source and a concurrent promoter."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (tmp_citadel.raw / "big.txt").write_text(_paras(6), encoding="utf-8")
    (tmp_citadel.raw / "b.md").write_text("Content of b.\n", encoding="utf-8")
    return tmp_citadel


def test_checkpoint_never_banks_a_concurrent_source_page_as_deleted(chunked_and_plain, fake_agent, cite_page):
    """A page a CONCURRENT source created is not this source's deletion.

    Run 1 (``--jobs 2``): the chunked source clones the wiki, source ``b`` then promotes
    ``misc/b-md.md``, and only afterwards does segment 1 finish and bank its checkpoint. Measured
    against live, ``b``'s page is "in live, not in my staging" — a deletion. Run 2 replays that
    delta and prunes a fully-ingested source's page off the live wiki: no conflict, no error, no
    delete session, just a page gone."""
    cit = chunked_and_plain
    b_page = cit.wiki / "misc" / "b-md.md"

    cloned = threading.Event()

    def session(rel_key, kind="ingest", read_path=None, segment=None, **_kw):
        if rel_key == "raw/b.md":
            # Hold b back until the chunked source has cloned (its first session proves it), so the
            # ordering under test is the real one: clone, THEN a concurrent promote, THEN the
            # checkpoint.
            assert cloned.wait(timeout=TIMEOUT)
            cite_page("misc/b-md.md", rel_key, "A fact from b.")
            return
        if segment[0] == 1:
            cloned.set()
            _await_live(b_page)  # bank the checkpoint AFTER b's promote landed
            cite_page("misc/big.md", rel_key, "A fact from segment one.")
        if segment[0] == 2:
            raise RuntimeError("segment 2 boom")

    fake_agent(side_effect=session)
    first = ingest.ingest(jobs=2)
    assert first.processed == ["raw/b.md"]  # b is in; the chunked source failed at segment 2
    assert b_page.is_file()

    # Run 2 is serial and touches only the chunked source — it has no business deleting anything.
    def finish(rel_key, kind="ingest", read_path=None, segment=None, **_kw):
        cite_page("misc/big.md", rel_key, f"A fact from segment {segment[0]}.")

    fake_agent(side_effect=finish)
    second = ingest.ingest()

    assert second.errors == []
    assert "raw/b.md" in manifest.load()  # still recorded as ingested...
    assert b_page.is_file(), "a concurrent source's promoted page was pruned by a replayed checkpoint"


def test_a_raced_chunked_source_really_re_runs(chunked_and_plain, fake_agent, cite_page):
    """The ``raced`` contract must hold for chunked sources too: re-run serially, see the winner's
    page, merge into it.

    Both sources write ``concepts/shared.md``; the chunked one banks a checkpoint after its LAST
    segment (by design — a promote that then fails should replay for free), and its promote is then
    refused because ``b`` got there first. If that checkpoint survives into the serial re-run, the
    re-run opens at ``completed == total``, runs ZERO sessions, and promotes its stale copy over the
    winner's page — the exact opposite of the documented merge."""
    cit = chunked_and_plain
    shared = cit.wiki / "concepts" / "shared.md"
    sessions: list[tuple[str, int | None]] = []

    cloned = threading.Event()

    def session(rel_key, kind="ingest", read_path=None, segment=None, **_kw):
        sessions.append((rel_key, segment[0] if segment else None))
        if rel_key == "raw/b.md":
            assert cloned.wait(timeout=TIMEOUT)  # the chunked source clones first
            cite_page("concepts/shared.md", rel_key, "The fact b wrote.")
            return
        if segment[0] == 1:
            cloned.set()
            _await_live(shared)  # let b win the race for the shared page
        cite_page("concepts/shared.md", rel_key, f"The fact big wrote (segment {segment[0]}).")

    fake_agent(side_effect=session)
    report = ingest.ingest(jobs=2)

    assert report.raced == ["raw/big.txt"]
    re_run = [seg for key, seg in sessions if key == "raw/big.txt" and seg is not None]
    assert re_run.count(1) == 2, "the serial re-run must actually open a session, not replay a stale checkpoint"
    assert report.errors == []
