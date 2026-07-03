"""``ingest --force`` (offline): deliberately re-read a source whose sha already matches the
manifest — docs/refactor-plan.md Z4, pinned tests-first. The decided semantics:

- a forced sha-matching FILE lands in pending and runs ``kind="reconcile"`` (never plain ingest —
  the reconcile brief carries the forced-re-read note), and the manifest is re-stamped with the
  CURRENT model label + rules_version;
- a forced REPO at the SAME commit runs ``kind="repo-reconcile"`` with a FULL re-digest
  (``only=None``) and NO change summary — never ``kind="repo"`` (a first-time brief would
  duplicate pages) and never a diff-restricted digest;
- ``--force`` clears a persisted UNREADABLE failure record and re-evaluates the source;
- ``--force`` on a dedup-dropped key ingests exactly the requested file (bypassing
  ``_dedup_rank``) and the report records the divergence;
- NO deletion sweep on a path-scoped force run;
- rollback-on-failure is untouched: a forced source whose session raises leaves the live wiki and
  its manifest stamp unchanged, and the failure is recorded;
- ``--force`` stays distinct from ``--full-rescan`` (PR4): full-rescan re-verifies hashes and
  never re-ingests a sha match; force runs the reconcile session.

``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

import pytest
from conftest import REAL_RULES_DIR

from citadel import config, failures, ingest, manifest, repo


# --------------------------------------------------------------------------------------------
# force on FILE sources
# --------------------------------------------------------------------------------------------


def test_forced_sha_match_runs_reconcile_never_plain_ingest(tmp_citadel, fake_agent, cite_page):
    """Z4: forcing an UNCHANGED, already-ingested source bypasses the sha short-circuit — it lands
    in pending and runs ``kind="reconcile"`` via the existing changed-keys logic (the key is
    tracked), NEVER a plain ``ingest`` that would duplicate its pages. Control on the same corpus:
    an UNFORCED path-scoped run still skips the sha match — force must not weaken the default
    (the full-run half of that control is tests/test_ingest_core.py's idempotency pin)."""
    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A fact."))

    ingest.ingest()
    assert agent.calls == [("raw/notes.md", "ingest")]  # brand new -> plain ingest

    agent.reset()
    assert ingest.ingest([str(raw / "notes.md")]).skipped == ["raw/notes.md"]
    assert agent.count == 0  # unforced path-scoped run: sha short-circuit stands

    report = ingest.ingest([str(raw / "notes.md")], force=True)
    assert agent.calls == [("raw/notes.md", "reconcile")]  # forced sha match -> reconcile, exactly once
    assert report.processed == ["raw/notes.md"]
    assert not report.errors


def test_force_without_paths_refused_at_the_api_layer(tmp_citadel, fake_agent):
    """Z4 guard, API twin of the CLI's exit-2 refusal: ``ingest(force=True)`` with no paths must
    raise ValueError BEFORE any work — one agent session per source must never hit the whole
    corpus by accident, no matter the caller. (The MCP server's ``wiki_ingest`` does not expose
    ``force`` at all.)"""
    agent = fake_agent()
    with pytest.raises(ValueError, match="--force requires explicit paths"):
        ingest.ingest(force=True)
    assert agent.count == 0  # refused before any session could run


def test_force_restamps_manifest_with_current_model_and_rules_version(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """Z4: a completed forced re-read re-stamps the manifest entry with the CURRENT model label +
    rules_version — that is the point of forcing after a model/rules upgrade."""
    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A fact."))

    monkeypatch.setattr(config, "ingest_model_label", lambda: "fake:model-a")
    monkeypatch.setattr(config, "rules_version", lambda: "rules-a")
    ingest.ingest()
    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    assert entry["model"] == "fake:model-a" and entry["rules_version"] == "rules-a"

    monkeypatch.setattr(config, "ingest_model_label", lambda: "fake:model-b")
    monkeypatch.setattr(config, "rules_version", lambda: "rules-b")
    report = ingest.ingest([str(raw / "notes.md")], force=True)

    assert report.processed == ["raw/notes.md"]
    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    assert entry["model"] == "fake:model-b"  # re-stamped with the CURRENT model
    assert entry["rules_version"] == "rules-b"  # ... and the CURRENT rules_version


def test_forced_source_failure_rolls_back_and_is_recorded(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """Rollback-on-failure is untouched by force: a forced source whose session raises leaves the
    live wiki byte-identical AND the manifest stamp exactly as it was (NOT re-stamped), records
    the failure, and retries next run — the frozen all-or-nothing machinery applies unchanged."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    monkeypatch.setattr(config, "ingest_model_label", lambda: "fake:model-a")
    fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A fact."))
    ingest.ingest()
    page = wiki / "misc" / "note.md"
    before_bytes = page.read_bytes()
    entry_before = dict(tmp_citadel.read_manifest()["raw/notes.md"])

    monkeypatch.setattr(config, "ingest_model_label", lambda: "fake:model-b")
    fake_agent(error=RuntimeError("forced boom"))
    report = ingest.ingest([str(raw / "notes.md")], force=True)

    assert "raw/notes.md" not in report.processed
    assert any("forced boom" in e for e in report.errors)
    assert page.read_bytes() == before_bytes  # live wiki untouched
    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    assert entry["sha256"] == entry_before["sha256"]
    assert entry.get("model") == "fake:model-a"  # NOT re-stamped on failure
    assert entry.get("rules_version") == entry_before.get("rules_version")
    recorded = failures.load()["raw/notes.md"]
    assert recorded["reason"] == failures.ERROR and "forced boom" in recorded["detail"]


def test_forced_path_run_never_sweeps_deletions(tmp_citadel, fake_agent, cite_page, seed_cited_deleted_source):
    """Z4: NO deletion sweep on a path-scoped force run — ``citadel ingest --force <path>`` must
    not read the rest of the manifest as candidates for deletion (``swept_roots=None`` already
    covers path-scoped runs; force must not re-arm it)."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A fact."))
    ingest.ingest()
    # A tracked source that vanished from disk, still cited by a live page.
    seed_cited_deleted_source()

    agent.reset()
    report = ingest.ingest([str(raw / "notes.md")], force=True)

    assert agent.calls == [("raw/notes.md", "reconcile")]  # only the forced target; no delete session
    assert report.sources_deleted == []
    assert (wiki / "concepts" / "topic.md").exists()  # the vanished source's page untouched
    assert "raw/gone.md" in tmp_citadel.read_manifest()  # still tracked; swept only by a full run


# --------------------------------------------------------------------------------------------
# force on REPO sources
# --------------------------------------------------------------------------------------------


def test_forced_repo_same_commit_runs_repo_reconcile_with_full_digest(
    repo_wiki, fake_agent, make_repo, cite_page, monkeypatch
):
    """Z4: forcing a repo at the SAME commit runs ``kind="repo-reconcile"`` with a FULL re-digest
    (``only=None``) and NO change summary — never ``kind="repo"`` (whose first-time brief would
    duplicate pages), and never the diff-restricted digest a normal reconcile builds."""
    raw = repo_wiki.raw
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/svc.md", rel_key, "A repo fact."))
    make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})
    ingest.ingest()
    assert agent.calls == [("raw/svc", "repo")]

    # Control (current behavior): an unforced re-run at the same commit is skipped, zero sessions.
    agent.reset()
    assert ingest.ingest().processed == []
    assert agent.count == 0

    captured: dict = {}
    real_build = repo.build_digest

    def capturing_build(path, key, *, only=None, change_summary=None, **kw):
        captured["only"] = only
        captured["change_summary"] = change_summary
        return real_build(path, key, only=only, change_summary=change_summary, **kw)

    monkeypatch.setattr(repo, "build_digest", capturing_build)
    # A WRONG implementation that consults the diff pathway would restrict the digest; make that
    # visible even for a marker (snap-identity) repo by having changed_files claim a diff exists.
    monkeypatch.setattr(repo, "changed_files", lambda *a, **k: ["README.md"])

    agent.reset()
    report = ingest.ingest([str(raw / "svc")], force=True)

    assert agent.calls == [("raw/svc", "repo-reconcile")]  # never plain "repo"
    assert report.processed == ["raw/svc"]
    assert captured == {"only": None, "change_summary": None}  # FULL re-digest, no change summary


# --------------------------------------------------------------------------------------------
# force on the edge states: persisted UNREADABLE, dedup-dropped
# --------------------------------------------------------------------------------------------


def test_forced_unreadable_source_is_reevaluated_and_failure_cleared(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """Z4: force clears a persisted UNREADABLE failure record and re-evaluates the source. Setup:
    an image recorded unreadable while image support was OFF is sha-tracked, so turning support ON
    is invisible to an unforced run (the short-circuit wins); the forced run re-classifies it,
    ingests it (reconcile-flavored — the key is tracked), and drops the failure record."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "IMAGE_SUPPORT", False, raising=False)
    (raw / "scan.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/scan.md", rel_key, "An image fact."))

    first = ingest.ingest()
    assert first.unreadable == ["raw/scan.png"] and agent.count == 0
    assert failures.load()["raw/scan.png"]["reason"] == failures.UNREADABLE

    monkeypatch.setattr(config, "IMAGE_SUPPORT", True, raising=False)
    second = ingest.ingest()  # unforced: the sha short-circuit still wins, the record stays
    assert second.processed == [] and agent.count == 0
    assert "raw/scan.png" in failures.load()

    third = ingest.ingest([str(raw / "scan.png")], force=True)
    assert agent.calls == [("raw/scan.png", "image-reconcile")]  # re-evaluated, retried
    assert third.processed == ["raw/scan.png"]
    assert "raw/scan.png" not in failures.load()  # the persisted failure record is cleared
    assert manifest.entry_model(tmp_citadel.read_manifest()["raw/scan.png"])  # a model imported it now


def test_forced_dedup_dropped_key_ingests_exactly_that_file(tmp_citadel, fake_agent, make_pptx, cite_page, monkeypatch):
    """Z4: force on a dedup-dropped key ingests EXACTLY the requested file — ``_dedup_rank`` is
    bypassed for it — and the report records the divergence (it names the kept sibling the wiki
    now deliberately holds alongside). The key was never ingested, so the existing changed-keys
    logic gives it a plain ``ingest`` (there are no stale facts of its own to reconcile)."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "DEDUP_BY_BASENAME", True, raising=False)
    (raw / "report.pdf").write_bytes(b"%PDF-1.7\ncontent")
    make_pptx(raw / "report.pptx", [["Slide fact."]])

    seen: list[tuple[str, str]] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.append((rel_key, kind))
        cite_page(f"misc/report-{rel_key.rsplit('.', 1)[-1]}.md", rel_key, "A report fact.")

    fake_agent(side_effect=fake)
    first = ingest.ingest()
    assert first.processed == ["raw/report.pdf"]
    assert first.duplicates == [("raw/report.pptx", "raw/report.pdf")]
    assert failures.load()["raw/report.pptx"]["reason"] == failures.DUPLICATE

    # Control (current behavior): an unforced path-scoped run still drops the twin.
    seen.clear()
    unforced = ingest.ingest([str(raw / "report.pptx")])
    assert unforced.processed == [] and seen == []

    forced = ingest.ingest([str(raw / "report.pptx")], force=True)

    assert seen == [("raw/report.pptx", "ingest")]  # exactly the requested file, dedup bypassed
    assert forced.processed == ["raw/report.pptx"]
    tracked = tmp_citadel.read_manifest()
    assert "raw/report.pptx" in tracked and "raw/report.pdf" in tracked  # both formats deliberately kept
    assert "raw/report.pptx" not in failures.load()  # the DUPLICATE record is cleared
    # The divergence is recorded in the report: the kept sibling is named even though this
    # path-scoped run never walked it (it can appear nowhere else in the render).
    assert "raw/report.pdf" in forced.render()


# --------------------------------------------------------------------------------------------
# --force vs --full-rescan distinctness
# --------------------------------------------------------------------------------------------


def test_full_rescan_refreshes_stats_only_where_force_reconciles(tmp_citadel, fake_agent, cite_page):
    """Z4 vs PR4: on the SAME unchanged sha-matching source, ``--full-rescan`` re-hashes and
    re-stamps stats with ZERO agent sessions, while ``--force`` runs exactly ONE reconcile
    session. The two flags must stay distinct."""
    raw = tmp_citadel.raw
    (raw / "a.md").write_text("alpha\n", encoding="utf-8")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/a.md", rel_key, "A fact."))
    ingest.ingest()

    agent.reset()
    rescan = ingest.ingest(full_rescan=True)
    assert rescan.skipped == ["raw/a.md"] and rescan.processed == []
    assert agent.count == 0  # full-rescan never re-ingests a sha match

    forced = ingest.ingest([str(raw / "a.md")], force=True)
    assert agent.calls == [("raw/a.md", "reconcile")]  # force runs the one reconcile session
    assert forced.processed == ["raw/a.md"]


# --------------------------------------------------------------------------------------------
# the rules layer: the reconcile brief must brief a FORCED session (verify, not rewrite)
# --------------------------------------------------------------------------------------------


def test_reconcile_brief_carries_forced_reread_note():
    """Z4: ``tasks/reconcile.md`` must tell a forced session that the source may be UNCHANGED —
    re-verify the wiki's facts against it under the current rules — otherwise the agent hunts for
    a source diff that does not exist. The note already ships; this pins it in place."""
    text = (REAL_RULES_DIR / "tasks" / "reconcile.md").read_text(encoding="utf-8").lower()
    assert "forced" in text
    assert "unchanged" in text
    assert "re-verify" in text
