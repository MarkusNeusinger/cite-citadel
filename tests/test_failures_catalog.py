"""Regression tests: failed REPO sessions and failed DELETE sessions must land in the persistent
failures catalog (``wiki/.citadel_failures.json``), exactly like failed FILE sources do.

The bug pinned here: ``ingest.ingest()``'s repo loop and delete-cleanup loop only did
``report.errors.extend(...)`` on a failed agent session — nothing ever called
``failures.record``, so once the console scrolled there was no lasting record that the repo or
the deletion cleanup was stuck (``sources/index.md``'s "Could not ingest" section silently
omitted them). Recording must NOT change retry semantics: the manifest is left exactly as a
failed file source leaves it, so the source is retried on the next run and a later success
drops the entry again.
"""

from __future__ import annotations

from conftest import delete_citing_pages

from citadel import failures, ingest, manifest, repo


# --------------------------------------------------------------------------------------------
# repo sessions
# --------------------------------------------------------------------------------------------


def test_failed_repo_session_recorded_and_retried(repo_wiki, fake_agent, make_repo):
    """Regression: a repo source whose agent session failed only reached ``report.errors`` —
    it was never recorded in the persistent failures catalog. It must land there with a reason,
    stay OUT of the manifest (so the next run retries it), and be dropped again on success."""
    agent = fake_agent(error=RuntimeError("boom"))
    make_repo(repo_wiki.raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})

    report = ingest.ingest()

    assert agent.calls == [("raw/svc", "repo")]
    assert "raw/svc" not in report.processed
    assert any("raw/svc" in e and "boom" in e for e in report.errors)
    # THE FIX: the failure is persisted, categorized as an error.
    recorded = failures.load()
    assert recorded["raw/svc"]["reason"] == failures.ERROR
    assert "boom" in recorded["raw/svc"]["detail"]
    # Retry semantics are unchanged: the repo was NOT marked done.
    assert "raw/svc" not in manifest.load()

    # Next run retries it (recording did not suppress the retry); success drops the entry.
    agent2 = fake_agent()  # clean no-op session
    second = ingest.ingest()
    assert ("raw/svc", "repo") in agent2.calls
    assert "raw/svc" in second.processed
    assert "raw/svc" in manifest.load()
    assert failures.load() == {}


def test_repo_session_timeout_categorized_as_timeout(repo_wiki, fake_agent, make_repo):
    """Regression companion: the recorded repo failure must reuse the file-source reason
    categories — a timeout message lands as ``timeout``, not a generic ``error``."""
    fake_agent(error=RuntimeError("agent timed out after 900s"))
    make_repo(repo_wiki.raw, "svc", {"README.md": "# Svc\n"})

    ingest.ingest()

    assert failures.load()["raw/svc"]["reason"] == failures.TIMEOUT


def test_failed_repo_digest_build_recorded_and_retried(repo_wiki, fake_agent, make_repo, monkeypatch):
    """Regression: a repo whose DIGEST BUILD raises (before any agent session ran) only reached
    ``report.errors`` — never the failures catalog. It must be recorded there with reason
    ``error`` and the manifest left untouched, so the repo is retried next run; a later
    successful build+session drops the entry again."""
    real_build_digest = repo.build_digest
    agent = fake_agent()  # must never run: the failure happens before the session
    make_repo(repo_wiki.raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})

    def boom(*_args, **_kwargs):
        raise RuntimeError("digest exploded")

    monkeypatch.setattr(repo, "build_digest", boom)
    report = ingest.ingest()

    assert agent.count == 0  # no session was attempted
    assert "raw/svc" not in report.processed
    assert any("raw/svc" in e and "digest exploded" in e for e in report.errors)
    # THE FIX: the digest-build failure is persisted, categorized as an error.
    recorded = failures.load()
    assert recorded["raw/svc"]["reason"] == failures.ERROR
    assert "digest exploded" in recorded["raw/svc"]["detail"]
    # Retry semantics are unchanged: the repo was NOT marked done.
    assert "raw/svc" not in manifest.load()

    # Next run (with the digest working again) retries it; success drops the entry.
    monkeypatch.setattr(repo, "build_digest", real_build_digest)
    agent2 = fake_agent()  # clean no-op session
    second = ingest.ingest()
    assert ("raw/svc", "repo") in agent2.calls
    assert "raw/svc" in second.processed
    assert "raw/svc" in manifest.load()
    assert failures.load() == {}


# --------------------------------------------------------------------------------------------
# delete-cleanup sessions
# --------------------------------------------------------------------------------------------


def test_mixed_run_failed_file_repo_and_delete_all_recorded_then_cleared(
    repo_wiki, seed_cited_deleted_source, fake_agent, make_repo
):
    """SourceJob unification pin (shape-neutral, docs/refactor-plan.md Z7): ONE run in which a
    FILE source, a REPO source, and a DELETE cleanup all fail must land all three in the failures
    catalog with reasons — through whatever shared per-source loop drives them — with retry
    semantics intact (file+repo not marked done; the deleted key kept); a later fully-successful
    run retries all three and clears the catalog."""
    raw = repo_wiki.raw
    (raw / "note.md").write_text("a note\n", encoding="utf-8")
    make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})
    seed_cited_deleted_source()  # raw/gone.md: tracked + cited, not on disk

    fake_agent(error=RuntimeError("boom"))
    report = ingest.ingest()

    assert report.processed == [] and report.sources_deleted == []
    recorded = failures.load()
    assert set(recorded) == {"raw/note.md", "raw/svc", "raw/gone.md"}
    assert all(entry["reason"] == failures.ERROR for entry in recorded.values())
    tracked = manifest.load()
    assert "raw/note.md" not in tracked and "raw/svc" not in tracked  # retried next run
    assert "raw/gone.md" in tracked  # deletion cleanup retried next full run

    # A later run where every session succeeds clears all three records again.
    def cleanup(rel_key, kind="ingest", **kwargs):
        if kind == "delete":
            delete_citing_pages(rel_key)

    fake_agent(side_effect=cleanup)
    second = ingest.ingest()

    assert set(second.processed) == {"raw/note.md", "raw/svc"}
    assert second.sources_deleted == ["raw/gone.md"]
    assert failures.load() == {}


def test_failed_delete_session_recorded_wiki_untouched_and_retried(tmp_citadel, seed_cited_deleted_source, fake_agent):
    """Regression: a delete-propagation session that failed only reached ``report.errors`` —
    never the failures catalog. It must be recorded, the live wiki must be left exactly as it
    was (rollback), and the manifest key KEPT so the cleanup is retried next full run."""
    seed_cited_deleted_source()
    page = tmp_citadel.wiki / "concepts" / "topic.md"
    before_text = page.read_text(encoding="utf-8")

    agent = fake_agent(error=RuntimeError("delete blew up"))
    report = ingest.ingest()

    assert agent.calls == [("raw/gone.md", "delete")]
    assert report.sources_deleted == []
    assert any("raw/gone.md" in e and "delete blew up" in e for e in report.errors)
    # THE FIX: the failed cleanup is persisted with a reason.
    recorded = failures.load()
    assert recorded["raw/gone.md"]["reason"] == failures.ERROR
    assert "delete blew up" in recorded["raw/gone.md"]["detail"]
    # The live wiki was rolled back byte-for-byte; the manifest key is kept for the retry.
    assert page.read_text(encoding="utf-8") == before_text
    assert "raw/gone.md" in manifest.load()

    # Next full run retries the cleanup; a session that strips the citations completes it and
    # the persisted failure is dropped.
    def cleanup(rel_key, kind="ingest", **kwargs):
        if kind == "delete":
            delete_citing_pages(rel_key)

    agent2 = fake_agent(side_effect=cleanup)
    second = ingest.ingest()
    assert ("raw/gone.md", "delete") in agent2.calls
    assert second.sources_deleted == ["raw/gone.md"]
    assert "raw/gone.md" not in manifest.load()
    assert failures.load() == {}
