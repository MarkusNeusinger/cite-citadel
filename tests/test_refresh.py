"""``citadel refresh`` (offline): budget-controlled re-verification of the least-recently-checked
sources. The decided semantics, pinned tests-first:

- the manifest's ``ingested_at`` stamp moves ONLY when an agent session actually verified the
  source (``mark_done`` / the repo done-hook) — a cache re-stamp of unchanged content carries the
  old stamp, so "last checked" never lies;
- ``refresh.plan`` orders oldest-checked first, a missing stamp (pre-refresh manifest) counting
  as oldest, and only over sources a model imported that still exist on disk;
- ``--min-age-days`` drops fresh sources from the plan entirely (the self-limiting knob for
  scheduled runs) but never drops a stamp-less entry;
- ``refresh.refresh`` hands exactly the ``limit`` head of the queue to a FORCED path-scoped
  ingest (each source one ``kind="reconcile"`` session) and the re-stamp rotates it to the back
  of the queue; ``dry_run`` runs zero sessions;
- the budget is always explicit: ``limit < 1`` is refused (ValueError; exit 2 at the CLI).

``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from pathlib import PurePosixPath

import pytest

from citadel import cli, config, ingest, manifest, refresh


OLD = "2020-01-01T00:00:00Z"


def _track(cit, name: str, content: str, *, model: str | None = "claude:old", ingested_at: str | None = None) -> str:
    """Write raw/<name> and hand-seed its manifest entry (sha-matching, so only a FORCED run
    re-reads it). Returns the manifest key."""
    src = cit.raw / name
    src.write_text(content, encoding="utf-8")
    m = manifest.load()
    key = manifest.rel_key(src)
    m[key] = manifest.make_entry(manifest.file_sha256(src), model, "old-rules", st=src.stat(), ingested_at=ingested_at)
    manifest.save(m)
    return key


def _pager(cite_page):
    """A fake-agent side effect writing one distinct valid page per source."""
    return lambda rel_key, **kw: cite_page(f"misc/{PurePosixPath(rel_key).stem}.md", rel_key, "A fact.")


# --------------------------------------------------------------------------------------------
# the ingested_at stamp
# --------------------------------------------------------------------------------------------


def test_mark_done_stamps_ingested_at_only_for_model_imports(tmp_citadel):
    """``mark_done`` with a model records a fresh ISO-UTC ``ingested_at``; without a model (a
    binary only seen and skipped) it records none — there is nothing "checked" to date."""
    src = tmp_citadel.raw / "notes.md"
    src.write_text("hello\n", encoding="utf-8")
    m: dict = {}
    manifest.mark_done(m, src, "claude:opus", "rules123")
    stamp = manifest.entry_ingested_at(m[manifest.rel_key(src)])
    assert stamp is not None and stamp.endswith("Z") and len(stamp) == len("2026-01-01T00:00:00Z")

    manifest.mark_done(m, src, None)
    assert manifest.entry_ingested_at(m[manifest.rel_key(src)]) is None


def test_cache_restamp_carries_ingested_at_unchanged(tmp_citadel, fake_agent, cite_page):
    """A ``--full-rescan`` over an UNCHANGED source refreshes the scan-cache fields but must
    CARRY the old last-checked stamp — no session ran, so "last checked" must not move (else
    refresh's ordering would rot on every rescan)."""
    key = _track(tmp_citadel, "a.md", "stable\n", ingested_at=OLD)
    agent = fake_agent()
    ingest.ingest(full_rescan=True)
    assert agent.count == 0  # sha still decides: no session
    assert manifest.entry_ingested_at(manifest.load()[key]) == OLD


# --------------------------------------------------------------------------------------------
# planning
# --------------------------------------------------------------------------------------------


def test_plan_orders_oldest_first_and_missing_stamp_oldest(tmp_citadel):
    _track(tmp_citadel, "mar.md", "m\n", ingested_at="2026-03-04T00:00:00Z")
    _track(tmp_citadel, "jan.md", "j\n", ingested_at="2026-01-02T00:00:00Z")
    _track(tmp_citadel, "unstamped.md", "u\n", ingested_at=None)
    queue = refresh.plan()
    assert [c.key for c in queue] == ["raw/unstamped.md", "raw/jan.md", "raw/mar.md"]
    # Every entry was stamped under "old-rules" != the current tree hash: flagged stale.
    assert all(c.stale_rules for c in queue)


def test_plan_excludes_unimported_gone_and_fresh_sources(tmp_citadel):
    _track(tmp_citadel, "old.md", "o\n", ingested_at=OLD)
    _track(tmp_citadel, "binary.bin", "b\n", model=None)  # no model imported it: nothing to re-verify
    gone_key = _track(tmp_citadel, "gone.md", "g\n", ingested_at=OLD)
    (tmp_citadel.raw / "gone.md").unlink()  # vanished: the deletion sweep's job, not refresh's
    _track(tmp_citadel, "fresh.md", "f\n", ingested_at=manifest.now_iso())
    _track(tmp_citadel, "unstamped.md", "u\n", ingested_at=None)

    assert [c.key for c in refresh.plan()] == ["raw/unstamped.md", "raw/old.md", "raw/fresh.md"]
    # The age floor drops the fresh source but NEVER a stamp-less one (age unknown = oldest).
    assert [c.key for c in refresh.plan(min_age_days=30)] == ["raw/unstamped.md", "raw/old.md"]
    assert gone_key not in [c.key for c in refresh.plan()]


# --------------------------------------------------------------------------------------------
# running
# --------------------------------------------------------------------------------------------


def test_refresh_reconciles_the_oldest_and_rotates_it_to_the_back(tmp_citadel, fake_agent, cite_page):
    old_key = _track(tmp_citadel, "a.md", "a\n", ingested_at=OLD)
    _track(tmp_citadel, "b.md", "b\n", ingested_at="2026-06-01T00:00:00Z")
    agent = fake_agent(side_effect=_pager(cite_page))

    report = refresh.refresh(limit=1)
    assert agent.calls == [(old_key, "reconcile")]  # forced sha match: reconcile, never plain ingest
    assert report.candidates == 2 and [c.key for c in report.selected] == [old_key]
    assert not report.ingest_report.errors

    m = manifest.load()
    new_stamp = manifest.entry_ingested_at(m[old_key])
    assert new_stamp is not None and new_stamp > "2026-06-01T00:00:00Z"  # fresh: rotated to the back
    assert manifest.entry_ingested_at(m["raw/b.md"]) == "2026-06-01T00:00:00Z"  # untouched
    assert manifest.entry_model(m[old_key]) == config.ingest_model_label()  # re-stamped to current


def test_refresh_dry_run_plans_only(tmp_citadel, fake_agent):
    _track(tmp_citadel, "a.md", "a\n", ingested_at=OLD)
    agent = fake_agent()
    report = refresh.refresh(limit=5, dry_run=True)
    assert agent.count == 0
    assert [c.key for c in report.selected] == ["raw/a.md"]
    assert report.ingest_report is None
    assert "Would refresh" in report.render()


def test_refresh_empty_plan_is_a_cheap_noop(tmp_citadel, fake_agent):
    agent = fake_agent()
    report = refresh.refresh(limit=3)
    assert agent.count == 0 and report.ingest_report is None
    assert "Nothing to refresh: no re-verifiable sources" in report.render()


def test_refresh_empty_plan_messages_tell_none_from_fresh(tmp_citadel, fake_agent):
    """The two empty-plan worlds render honestly: with NO re-verifiable sources the report must
    not claim everything was 'checked recently'; with sources that are merely fresh under the
    age floor, it says exactly that."""
    fake_agent()
    assert "no re-verifiable sources" in refresh.refresh(limit=1, min_age_days=30).render()

    _track(tmp_citadel, "fresh.md", "f\n", ingested_at=manifest.now_iso())
    report = refresh.refresh(limit=1, min_age_days=30)
    assert report.eligible == 1 and report.candidates == 0
    assert "all 1 re-verifiable source(s) were checked within the last 30 days" in report.render()


def test_same_run_duplicate_never_mints_a_stamp(tmp_citadel, fake_agent, cite_page):
    """Two byte-identical files discovered together: one runs the session (and is stamped), the
    duplicate's manifest record carries the run's model/rules but NO minted ``ingested_at`` — no
    session verified that copy, so it must sort to the FRONT of the refresh queue, not hide at
    the back behind a stamp nothing backs."""
    (tmp_citadel.raw / "a.md").write_text("same bytes\n", encoding="utf-8")
    (tmp_citadel.raw / "b.md").write_text("same bytes\n", encoding="utf-8")
    fake_agent(side_effect=_pager(cite_page))
    ingest.ingest()

    m = manifest.load()
    stamped = [k for k in ("raw/a.md", "raw/b.md") if manifest.entry_ingested_at(m[k])]
    unstamped = [k for k in ("raw/a.md", "raw/b.md") if not manifest.entry_ingested_at(m[k])]
    assert len(stamped) == 1 and len(unstamped) == 1  # exactly the session-run twin is stamped
    assert manifest.entry_model(m[unstamped[0]]) is not None  # provenance still attributed
    assert refresh.plan()[0].key == unstamped[0]  # the unverified copy is first in line


def test_refresh_limit_must_be_explicit_and_positive(tmp_citadel):
    with pytest.raises(ValueError):
        refresh.refresh(limit=0)


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def test_cli_refresh_dry_run_and_limit_guard(tmp_citadel, fake_agent, capsys):
    _track(tmp_citadel, "a.md", "a\n", ingested_at=OLD)
    agent = fake_agent()
    assert cli.main(["refresh", "--dry-run", "--quiet"]) == 0
    assert agent.count == 0
    assert "raw/a.md" in capsys.readouterr().out

    assert cli.main(["refresh", "--limit", "0"]) == 2
    assert "--limit must be >= 1" in capsys.readouterr().err


def test_cli_refresh_runs_the_budgeted_sessions(tmp_citadel, fake_agent, cite_page, capsys):
    _track(tmp_citadel, "a.md", "a\n", ingested_at=OLD)
    _track(tmp_citadel, "b.md", "b\n", ingested_at="2026-06-01T00:00:00Z")
    agent = fake_agent(side_effect=_pager(cite_page))
    assert cli.main(["refresh", "--limit", "2", "--quiet"]) == 0
    assert agent.calls == [("raw/a.md", "reconcile"), ("raw/b.md", "reconcile")]
    out = capsys.readouterr().out
    assert "Refreshing 2 of 2" in out
