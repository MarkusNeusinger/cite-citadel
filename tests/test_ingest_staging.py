"""Staging / promote / rollback / interrupt (offline): the agent only ever edits a per-source
staging sibling of the live wiki; a clean session is promoted non-destructively, any failure,
timeout, or Ctrl+C leaves the live wiki byte-identical, and the network-share-hardened
``_robust_*`` / ``robust_mkdir`` machinery survives flaky deletes and mkdir races.
``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from citadel import config, ingest, ingest_staging, store


def test_failed_session_rolls_back(tmp_citadel, fake_agent, seed_page):
    """A session that raises after a partial write is rolled back: the wiki returns to its
    pre-source state, the source is NOT marked done, and the error is collected."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/partial.md",
            {"type": "Concept", "title": "Partial", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "Half-written.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        raise RuntimeError("boom mid-session")

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("boom mid-session" in e for e in report.errors)
    assert not (wiki / "concepts" / "partial.md").exists()  # rolled back
    assert (wiki / "concepts" / "keep.md").exists()  # untouched

    # Source is retried next run (not in the manifest).

    assert "raw/notes.md" not in tmp_citadel.read_manifest()  # {} when the manifest never got written


def test_robust_rmtree_retries_then_succeeds(tmp_path, monkeypatch):
    """``_robust_rmtree`` retries a transiently-undeletable tree (a lock that clears, as on a
    network share) and removes it once the delete goes through, rather than giving up after the
    first failure the way ``rmtree(ignore_errors=True)`` silently did."""
    victim = tmp_path / "victim"
    (victim / "sub").mkdir(parents=True)
    (victim / "sub" / "f.txt").write_text("x", encoding="utf-8")

    real_rmtree = ingest_staging.shutil.rmtree
    state = {"n": 0}

    def flaky_rmtree(path, *args, **kwargs):
        state["n"] += 1
        if state["n"] < 3:
            return  # first two attempts "fail" silently, leaving the tree in place
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(ingest_staging.shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr(ingest_staging.time, "sleep", lambda *_: None)  # keep the retry loop instant

    ingest._robust_rmtree(victim)

    assert state["n"] == 3  # retried until the delete went through
    assert not victim.exists()  # tree is gone


def test_robust_copy_file_retries_then_succeeds(tmp_path, monkeypatch):
    """``_robust_copy_file`` retries the transient ``os.replace`` hiccup a network share flakes on
    (a momentary lock/latency) and lands the copy once it clears — writing a temp sibling then
    atomically replacing, so ``dst`` is never observed half-written."""
    src = tmp_path / "src.md"
    src.write_text("fresh content\n", encoding="utf-8")
    dst = tmp_path / "dst.md"

    real_replace = ingest_staging.os.replace
    state = {"n": 0}

    def flaky_replace(a, b, *args, **kwargs):
        state["n"] += 1
        if state["n"] < 3:
            raise OSError("share momentarily locked")  # first two attempts fail
        return real_replace(a, b, *args, **kwargs)

    monkeypatch.setattr(ingest_staging.os, "replace", flaky_replace)
    monkeypatch.setattr(ingest_staging.time, "sleep", lambda *_: None)  # keep the retry loop instant

    ingest._robust_copy_file(src, dst, attempts=5)

    assert state["n"] == 3  # retried until the replace went through
    assert dst.read_text(encoding="utf-8") == "fresh content\n"  # final content is the source
    assert not (tmp_path / "dst.md.citadeltmp").exists()  # the temp sibling is cleaned up


def test_robust_copy_file_leaves_dst_untouched_on_permanent_failure(tmp_path, monkeypatch):
    """The load-bearing atomicity invariant: when every attempt fails, ``_robust_copy_file`` raises
    with ``dst`` LEFT EXACTLY AS IT WAS (its previous content, never a truncated half-write) and no
    temp sibling left behind — so ingest can fail the source and retry next run with the live page
    intact."""
    src = tmp_path / "src.md"
    src.write_text("new content that must not leak\n", encoding="utf-8")
    dst = tmp_path / "dst.md"
    dst.write_text("PRE-EXISTING\n", encoding="utf-8")  # the live page's current content

    def always_fail(a, b, *args, **kwargs):
        raise OSError("share offline")

    monkeypatch.setattr(ingest_staging.os, "replace", always_fail)
    monkeypatch.setattr(ingest_staging.time, "sleep", lambda *_: None)

    with pytest.raises(OSError):
        ingest._robust_copy_file(src, dst, attempts=3)

    assert dst.read_text(encoding="utf-8") == "PRE-EXISTING\n"  # never a half-written live page
    assert not (tmp_path / "dst.md.citadeltmp").exists()  # temp sibling cleaned up even on give-up


def test_rollback_survives_undeletable_wiki_on_network_share(tmp_citadel, fake_agent, seed_page, monkeypatch):
    """Regression for the WinError 183 crash that emptied a wiki on a network share. The agent now
    edits a STAGING sibling, so a failed session never touches the live wiki — and even when the
    share refuses to delete a directory (here: the live wiki dir), the run reports the real session
    error rather than crashing, and the pre-existing page is left intact."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    # Simulate the worst case the old ignore_errors=True hid: the share never actually deletes
    # wiki/. Local temp dirs (the backup) still delete normally, so they pass through.
    real_rmtree = ingest_staging.shutil.rmtree
    wiki_resolved = wiki.resolve()

    def undeletable_share(path, *args, **kwargs):
        if Path(path).resolve() == wiki_resolved:
            return  # the share "fails" to delete and reports nothing
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(ingest_staging.shutil, "rmtree", undeletable_share)
    monkeypatch.setattr(ingest_staging.time, "sleep", lambda *_: None)

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/partial.md",
            {"type": "Concept", "title": "Partial", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "Half-written.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        raise RuntimeError("boom mid-session")

    fake_agent(side_effect=fake)

    # Used to die with FileExistsError out of the rollback; now the real error is reported instead.
    report = ingest.ingest([str(raw / "notes.md")])

    assert any("boom mid-session" in e for e in report.errors)
    assert "raw/notes.md" not in report.processed
    assert (wiki / "concepts" / "keep.md").exists()  # backup laid back down over the surviving dir


def test_keyboardinterrupt_rolls_back_current_source(tmp_citadel, fake_agent, seed_page):
    """A Ctrl+C (KeyboardInterrupt) raised mid-session must roll the wiki back to its
    pre-source state, then propagate. KeyboardInterrupt is a BaseException, so the per-source
    `except Exception` does NOT catch it — the rollback lives in `finally` (guarded by a
    success flag), which a BaseException still runs on its way out."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/partial.md",
            {"type": "Concept", "title": "Partial", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "Half-written.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        raise KeyboardInterrupt()

    fake_agent(side_effect=fake)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest([str(raw / "notes.md")])

    assert not (wiki / "concepts" / "partial.md").exists()  # rolled back on the interrupt
    assert (wiki / "concepts" / "keep.md").exists()  # pre-existing page untouched


def test_keyboardinterrupt_mid_segment_discards_whole_source(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """Promote-once under Ctrl+C: a KeyboardInterrupt at segment 2 of a chunked source keeps
    the capture-finalize-reraise semantics — the interrupt still propagates AFTER finalization ran
    for the previously completed source — and leaves the live wiki with NOTHING from the segmented
    source (previously segment 1's page was already promoted; that partial is flipped away by
    the single staging copy). The source stays PENDING, so the next run re-imports it — continuing
    at segment 2 from the resume checkpoint segment 1 wrote (tests/test_ingest_resume.py), which
    changes nothing about what is on the live wiki right now: still nothing."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "a.md").write_text("a small source that fits one pass\n", encoding="utf-8")
    (raw / "big.txt").write_text(
        "\n\n".join(f"Paragraph number {i} with some filler content about topic {i}." for i in range(6)),
        encoding="utf-8",
    )

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        if rel_key == "raw/a.md":
            cite_page("misc/from-a.md", rel_key, "Fact A.")
            return
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")
        elif segment[0] == 2:
            raise KeyboardInterrupt()

    fake_agent(side_effect=fake)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest()  # a.md completes first (sorted order), big.txt interrupts at segment 2

    assert not (wiki / "misc" / "big.md").exists()  # the whole segmented source discarded
    data = tmp_citadel.read_manifest()
    assert "raw/big.txt" not in data  # retried in full next run
    assert "raw/a.md" in data  # the completed source was persisted before the interrupt
    assert "from-a.md" in (wiki / "index.md").read_text(encoding="utf-8")  # finalize ran before re-raise
    # No staging sibling left behind by the interrupted multi-segment source.
    assert not any(p.name.startswith(".wiki.staging") for p in wiki.parent.iterdir())


def test_completed_sources_persisted_before_interrupt(tmp_citadel, fake_agent, seed_page):
    """Progress is written to the manifest right after each source completes, so a Ctrl+C
    during a LATER source can't erase already-finished work. (The old code saved the manifest
    only in finalization, which a propagating KeyboardInterrupt skipped entirely.)"""

    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "a.md").write_text("first\n", encoding="utf-8")
    (raw / "b.md").write_text("second\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        if rel_key == "raw/a.md":
            seed_page(
                "concepts/from-a.md",
                {"type": "Concept", "title": "From A", "description": "d", "tags": ["x"], "resource": "raw/a.md"},
                "Fact A.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n",
            )
        else:  # raw/b.md — interrupt mid-session, after a.md already finished
            raise KeyboardInterrupt()

    fake_agent(side_effect=fake)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest()  # processes raw/a.md then raw/b.md (sorted order)

    assert tmp_citadel.manifest_path.exists()  # saved incrementally, not only at finalization
    data = tmp_citadel.read_manifest()
    assert "raw/a.md" in data  # a finished -> persisted before the interrupt
    assert "raw/b.md" not in data  # b interrupted -> not marked done
    assert (wiki / "concepts" / "from-a.md").exists()  # a's page survived b's rollback


def test_finalization_runs_for_completed_sources_on_interrupt(tmp_citadel, fake_agent, seed_page):
    """If a Ctrl+C interrupts the run after some sources already completed, the derived files
    (indexes + log) for that completed work are still rebuilt before the interrupt propagates.
    Otherwise — since the manifest is now persisted per-source — a later run could find nothing
    pending, skip finalization entirely, and leave the wiki's indexes/log permanently stale."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "a.md").write_text("first\n", encoding="utf-8")
    (raw / "b.md").write_text("second\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        if rel_key == "raw/a.md":
            seed_page(
                "concepts/from-a.md",
                {"type": "Concept", "title": "From A", "description": "d", "tags": ["x"], "resource": "raw/a.md"},
                "Fact A.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n",
            )
        else:  # raw/b.md interrupts after a is already done
            raise KeyboardInterrupt()

    fake_agent(side_effect=fake)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest()

    # a's page is committed AND the indexes/log were rebuilt despite the interrupt — so the
    # wiki is not stranded with content the navigation files don't reflect.
    assert (wiki / "concepts" / "from-a.md").exists()
    assert "from-a.md" in (wiki / "index.md").read_text(encoding="utf-8")
    assert tmp_citadel.log_path.exists()


def test_robust_mkdir_swallows_fileexists_race(tmp_path, monkeypatch):
    """``config.robust_mkdir`` treats a ``FileExistsError`` as success: a network share can report
    an existing directory as not-a-dir for a moment, so ``mkdir(exist_ok=True)`` still raises
    WinError 183 even though the directory is present. That race aborted a long ingest in
    ``rebuild_indexes``; it must now be a no-op."""
    target = tmp_path / "wiki"
    target.mkdir()

    real_mkdir = Path.mkdir

    def flaky_mkdir(self, *args, **kwargs):
        if self == target:
            raise FileExistsError(183, "Cannot create a file when that file already exists")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", flaky_mkdir)
    config.robust_mkdir(target)  # must NOT raise
    assert target.is_dir()


def test_robust_mkdir_reraises_on_real_file_collision(tmp_path, monkeypatch):
    """``robust_mkdir`` must NOT swallow a FileExistsError when the path is a real FILE (not a
    transient share race): it surfaces the error here instead of masking it into a confusing
    NotADirectoryError on the next write."""
    clash = tmp_path / "notadir"
    clash.write_text("i am a file", encoding="utf-8")  # the path exists, but as a file
    monkeypatch.setattr(config.time, "sleep", lambda *_: None)

    with pytest.raises(OSError):
        config.robust_mkdir(clash, attempts=2)
    assert clash.is_file()  # left as it was


def test_rebuild_indexes_survives_fileexists_on_share(tmp_citadel, seed_page, monkeypatch):
    """The exact reported crash: ``rebuild_indexes`` did ``WIKI_DIR.mkdir(...)`` which threw
    WinError 183 on the share and aborted the whole run. With the robust mkdir it finishes and the
    index is written; the wiki content is never lost."""
    wiki = tmp_citadel.wiki
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/o.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/o.md](../../raw/o.md) - o\n",
    )

    real_mkdir = Path.mkdir

    def flaky_mkdir(self, *args, **kwargs):
        if self.resolve() == wiki.resolve():
            raise FileExistsError(183, "Cannot create a file when that file already exists")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", flaky_mkdir)

    store.rebuild_indexes()  # used to raise FileExistsError out of finalize
    assert "keep.md" in (wiki / "index.md").read_text(encoding="utf-8")
    assert (wiki / "concepts" / "keep.md").exists()


def test_agent_edits_staging_sibling_not_live(tmp_citadel, fake_agent, seed_page):
    """During a session the agent writes to a STAGING copy that is a SIBLING of the live wiki (same
    parent, same depth — so its relative citation links stay valid), and the live wiki is untouched
    until the clean session is promoted."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")
    seen = {}

    def fake(rel_key, kind="ingest"):
        staging = config.wiki_dir()
        seen["staging"] = staging
        seen["is_sibling"] = staging != wiki and staging.parent == wiki.parent
        # The live wiki must not yet hold this page while the agent is mid-session.
        seen["live_clean_midsession"] = not (wiki / "concepts" / "transformer.md").exists()
        seed_page(
            "concepts/transformer.md",
            {"type": "Concept", "title": "T", "description": "d", "tags": ["ml"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert not report.errors
    assert seen["is_sibling"]  # staging is a sibling of live, not a temp dir
    assert seen["live_clean_midsession"]  # live untouched while the agent worked
    assert (wiki / "concepts" / "transformer.md").exists()  # promoted after a clean session
    assert config.wiki_dir() == wiki  # redirect restored
    import os as _os

    assert "CITADEL_WIKI_DIR" not in _os.environ  # env restored (was unset)
    # No staging sibling left behind.
    assert not any(p.name.startswith(".wiki.staging") for p in wiki.parent.iterdir())


def test_failed_session_leaves_live_wiki_byte_identical(tmp_citadel, fake_agent, seed_page, monkeypatch):
    """A session that fails mid-way must leave the live wiki EXACTLY as it was — even when the share
    refuses to delete a directory (the case that used to empty the wiki). The agent's partial page
    lands only in staging and is discarded; nothing the agent did reaches the live wiki."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/o.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/o.md](../../raw/o.md) - o\n",
    )
    (raw / "o.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")
    keep = wiki / "concepts" / "keep.md"
    before_bytes = keep.read_bytes()
    before_mtime = keep.stat().st_mtime_ns

    # The share "fails" to delete any directory under the live wiki's parent (staging cleanup),
    # exactly the flakiness that broke the old rollback. Local temp dirs still delete normally.
    real_rmtree = ingest_staging.shutil.rmtree

    def flaky_rmtree(path, *args, **kwargs):
        if str(Path(path).resolve()).startswith(str(wiki.parent.resolve())):
            return  # share refuses the delete and reports nothing
        return real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(ingest_staging.shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr(ingest_staging.time, "sleep", lambda *_: None)

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/partial.md",
            {"type": "Concept", "title": "Partial", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "Half.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        raise RuntimeError("boom mid-session")

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert any("boom mid-session" in e for e in report.errors)
    assert "raw/notes.md" not in report.processed
    assert keep.read_bytes() == before_bytes  # untouched, byte for byte
    assert keep.stat().st_mtime_ns == before_mtime  # not even rewritten
    assert not (wiki / "concepts" / "partial.md").exists()  # agent's partial never reached live


def test_promote_syncs_changed_and_pruned(tmp_path):
    """``_promote`` brings live to match staging: new + changed files are copied, removed files are
    pruned, and empty directories are dropped — while files already identical are left alone."""
    live = tmp_path / "wiki"
    staging = tmp_path / ".wiki.staging"
    for d in (live / "concepts", staging / "concepts"):
        d.mkdir(parents=True)
    (live / "concepts" / "a.md").write_text("A1", encoding="utf-8")  # will change
    (live / "concepts" / "same.md").write_text("S", encoding="utf-8")  # identical -> untouched
    (live / "gone").mkdir()
    (live / "gone" / "x.md").write_text("X", encoding="utf-8")  # pruned
    (staging / "concepts" / "a.md").write_text("A2", encoding="utf-8")
    (staging / "concepts" / "same.md").write_text("S", encoding="utf-8")
    (staging / "concepts" / "new.md").write_text("N", encoding="utf-8")  # created

    ingest._promote(staging, live)

    assert (live / "concepts" / "a.md").read_text(encoding="utf-8") == "A2"
    assert (live / "concepts" / "new.md").read_text(encoding="utf-8") == "N"
    assert (live / "concepts" / "same.md").read_text(encoding="utf-8") == "S"
    assert not (live / "gone" / "x.md").exists()  # pruned
    assert not (live / "gone").exists()  # emptied dir dropped


def test_promote_is_non_destructive_on_copy_failure(tmp_path, monkeypatch):
    """If a copy fails partway through a promote, the live wiki keeps its previous pages — the
    copy-over runs before any prune, so live is never emptied even on a mid-promote error."""
    live = tmp_path / "wiki"
    staging = tmp_path / ".wiki.staging"
    for d in (live, staging):
        d.mkdir(parents=True)
    (live / "keep.md").write_text("KEEP", encoding="utf-8")
    (staging / "keep.md").write_text("KEEP2", encoding="utf-8")  # a change the agent made
    (staging / "more.md").write_text("MORE", encoding="utf-8")

    def boom(src, dst, *a, **k):
        raise OSError("share dropped mid-copy")

    monkeypatch.setattr(ingest_staging, "_robust_copy_file", boom)

    with pytest.raises(OSError):
        ingest._promote(staging, live)

    # The original page is still there: the prune phase never ran, so nothing was lost.
    assert (live / "keep.md").read_text(encoding="utf-8") == "KEEP"
    assert any(live.iterdir())  # live is NOT empty


def test_session_that_deletes_all_pages_is_refused_not_promoted(tmp_citadel, fake_agent, seed_page):
    """A clean-validating session that nonetheless leaves the wiki with ZERO content pages (a
    buggy/looping/adversarial agent that deleted everything) must NOT be promoted — the live wiki
    keeps its pages and the source is reported as a failure, never emptied."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/o.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/o.md](../../raw/o.md) - o\n",
    )
    (raw / "o.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        # The agent wipes every content page from its staging copy (adds nothing back).
        for p in config.wiki_dir().rglob("*.md"):
            if p.name not in ("index.md", "log.md"):
                p.unlink()

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed  # not committed
    assert any("no content pages" in e for e in report.errors)
    assert (wiki / "concepts" / "keep.md").exists()  # the live wiki kept its page


def test_vanished_staging_fails_with_clear_reason(tmp_citadel, fake_agent, seed_page):
    """A session that deletes its own staging copy (a weak model inventing a "publish"/cleanup
    step) fails the source with a reason that says so — not with an opaque promote refusal or,
    worse, a silent zero-change success. The live wiki is untouched and the source is retried."""
    import shutil

    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/o.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/o.md](../../raw/o.md) - o\n",
    )
    (raw / "o.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        shutil.rmtree(config.wiki_dir())  # the redirected wiki IS the staging copy

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("staging wiki copy vanished" in e for e in report.errors)
    assert (wiki / "concepts" / "keep.md").exists()  # live wiki untouched
    assert "raw/notes.md" not in tmp_citadel.read_manifest()  # retried next run


def test_vanished_staging_names_pages_written_to_live_wiki(tmp_citadel, fake_agent, seed_page):
    """The incident this guards against: the agent copies its pages into the LIVE wiki directly,
    then deletes the staging copy as "published". The failure reason must name the files that
    appeared outside the staging discipline — they were never validated — and leave them in
    place for the user to inspect rather than silently deleting paid-for work."""
    import shutil

    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        stray = wiki / "concepts" / "stray.md"
        stray.parent.mkdir(parents=True, exist_ok=True)
        stray.write_text("published directly, bypassing staging\n", encoding="utf-8")
        shutil.rmtree(config.wiki_dir())

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("staging wiki copy vanished" in e for e in report.errors)
    # The serial-mode live-drift note (appended to the failure) names the out-of-band write ...
    note = next(e for e in report.errors if "changed while this source's session ran" in e)
    assert "concepts/stray.md" in note
    assert (wiki / "concepts" / "stray.md").exists()  # ... and left in place, never auto-deleted


def test_vanished_staging_on_empty_wiki_is_not_a_silent_success(tmp_citadel, fake_agent):
    """The variant with nothing to trip the anti-emptying guard: the live wiki has NO content
    pages yet (a first ingest), the agent deletes its staging copy and touches nothing else.
    Empty-before vs empty-after used to diff as "the session changed nothing" and stamp the
    source done — a silent zero-change success. The identity check must fail the source."""
    import shutil

    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        shutil.rmtree(config.wiki_dir())

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed  # never stamped as ingested
    assert any("staging wiki copy vanished" in e for e in report.errors)
    assert "raw/notes.md" not in tmp_citadel.read_manifest()  # retried next run


def test_recreated_staging_directory_is_detected_as_replaced(tmp_citadel, fake_agent):
    """A deleted-then-recreated staging directory (the "publish then tidy up" shape) passes a bare
    existence check but not the identity sentinel: the impostor tree was never the copy this run
    made, so nothing in it can be trusted or diffed. The source must fail, not read as empty."""
    import shutil

    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        staging = config.wiki_dir()
        shutil.rmtree(staging)
        staging.mkdir()  # same path, brand-new (empty) directory — is_dir() alone would pass

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("staging wiki copy vanished or was replaced" in e for e in report.errors)
    assert "raw/notes.md" not in tmp_citadel.read_manifest()


def test_forged_sentinel_in_recreated_staging_is_detected(tmp_citadel, fake_agent):
    """The sentinel's token is random and process-local, so even an impostor tree that re-creates
    `.citadel_staging` (the filename and the directory name are both predictable) cannot forge the
    identity: the content never matches the registered token and the source fails."""
    import shutil

    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        staging = config.wiki_dir()
        shutil.rmtree(staging)
        staging.mkdir()
        # Forge the sentinel with the only value an outsider could predict: the dir's own name.
        (staging / ingest_staging._STAGING_SENTINEL).write_text(staging.name, encoding="utf-8")

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("staging wiki copy vanished or was replaced" in e for e in report.errors)
    assert "raw/notes.md" not in tmp_citadel.read_manifest()


def test_corrupt_sentinel_reads_as_not_intact(tmp_path):
    """A sentinel holding undecodable bytes must answer False, never raise — `_staging_intact` is
    also called while another failure is being handled, where an escaping UnicodeDecodeError would
    abort the whole run instead of reporting the vanished/replaced staging copy."""
    staging = ingest_staging._make_staging(tmp_path / "wiki")
    assert ingest_staging._staging_intact(staging)
    (staging / ingest_staging._STAGING_SENTINEL).write_bytes(b"\xff\xfe garbage")
    assert ingest_staging._staging_intact(staging) is False


def test_raising_session_still_reports_vanished_staging(tmp_citadel, fake_agent):
    """A session can destroy its staging copy AND then die (timeout, non-zero exit). The vanished
    -staging diagnosis must not be lost behind the session's own error: both stories surface."""
    import shutil

    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        shutil.rmtree(config.wiki_dir())
        raise RuntimeError("agent timed out")

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("agent timed out" in e for e in report.errors)  # the session's own failure ...
    assert any("also vanished or was replaced" in e for e in report.errors)  # ... and the story


def test_failed_source_names_out_of_staging_live_writes(tmp_citadel, fake_agent):
    """The observed weak-model failure mode: the agent "publishes" its pages into the LIVE wiki
    itself instead of leaving them in its staging copy. The emptied staging trips the promote
    guard exactly as before — and the failure must also NAME the out-of-band live writes, because
    those pages bypassed validation and the plain rollback message would read as "live wiki
    untouched" while unvalidated pages actually stand in it. Detection only: nothing is swept (a
    page a human added mid-run must never be deleted on the agent's account)."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def rogue(*args, **kwargs):
        # Writes around the staging copy, straight into the live wiki; staging stays empty.
        target = wiki / "concepts" / "rogue.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("a page written around the staging machinery\n", encoding="utf-8")

    fake_agent(side_effect=rogue)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed  # the source still fails (guard unchanged)
    assert any("no content pages" in e for e in report.errors)
    note = next(e for e in report.errors if "changed while this source's session ran" in e)
    assert "concepts/rogue.md" in note  # the drift note names the unvalidated page
    assert (wiki / "concepts" / "rogue.md").exists()  # detection only — nothing is swept


def test_promote_excludes_generated_and_manifest_files(tmp_path):
    """``_promote`` syncs only content pages: it never copies a staging ``index.md``/``log.md`` or
    the manifest onto live (finalize regenerates indexes, the loop owns the manifest), and it does
    not prune live's own generated files."""
    live = tmp_path / "wiki"
    staging = tmp_path / ".wiki.staging.x"
    for d in (live, staging):
        d.mkdir(parents=True)
    (live / "index.md").write_text("LIVE INDEX", encoding="utf-8")  # must be left alone
    (live / ".citadel_ingested.json").write_text("{}", encoding="utf-8")  # must be left alone
    (live / "a.md").write_text("A", encoding="utf-8")
    (staging / "index.md").write_text("STALE INDEX", encoding="utf-8")  # must NOT overwrite live
    (staging / "log.md").write_text("STALE LOG", encoding="utf-8")  # must NOT be copied
    (staging / ".citadel_ingested.json").write_text('{"stale":1}', encoding="utf-8")
    (staging / "a.md").write_text("A2", encoding="utf-8")  # a real content change

    ingest._promote(staging, live)

    assert (live / "a.md").read_text(encoding="utf-8") == "A2"  # content synced
    assert (live / "index.md").read_text(encoding="utf-8") == "LIVE INDEX"  # generated file untouched
    assert (live / ".citadel_ingested.json").read_text(encoding="utf-8") == "{}"  # manifest untouched
    assert not (live / "log.md").exists()  # stale log not copied in
