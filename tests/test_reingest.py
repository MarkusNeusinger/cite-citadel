"""``ingest --reingest`` (offline): strip a tracked source's previous facts, then re-import it
FRESH in the same run — the deliberate full re-think that ``--force``'s reconcile (which keeps the
existing treatment) cannot deliver. The decided semantics, pinned tests-first:

- a reingested tracked FILE runs exactly two jobs in order: a ``kind="delete"`` cleanup (its
  manifest key dropped on success) and then a plain ``kind="ingest"`` session — never a
  reconcile — with the manifest re-stamped fresh under the CURRENT model + rules_version;
- a reingested tracked source that NO page cites plans no cleanup session (the key is just
  forgotten) and goes straight to the fresh ingest;
- a FAILED cleanup blocks the fresh session for that source: nothing is written on top of the
  old facts, the live wiki and manifest entry stay as they were, and the failure is recorded;
- a reingested REPO runs the cleanup and then the FIRST-TIME ``kind="repo"`` brief over a FULL
  digest (safe exactly because the cleanup removed the pages a first-time brief would duplicate);
- ``reingest`` requires explicit paths (API ValueError; the CLI pre-empts with exit 2) and a
  path-scoped reingest run never sweeps deletions;
- the transcript/extraction caches are NOT pruned by a reingest cleanup (the source still exists
  with the same bytes, and the fresh session is about to re-read exactly that cached text).

``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

import pytest
from conftest import REAL_RULES_DIR, delete_citing_pages

from citadel import config, failures, ingest, manifest, pdftext, repo


def _reingest_side_effect(cite_page, rel_path="misc/note-v2.md", fact="A rethought fact."):
    """The canonical two-kind fake session: the ``delete`` pass strips every citing page from the
    staging copy, the fresh ``ingest`` pass writes the new page."""

    def _run(rel_key, kind="ingest", **kw):
        if kind == "delete":
            delete_citing_pages(rel_key)
        else:
            cite_page(rel_path, rel_key, fact)

    return _run


# --------------------------------------------------------------------------------------------
# reingest on FILE sources
# --------------------------------------------------------------------------------------------


def test_reingest_runs_cleanup_then_plain_ingest(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """The core semantics: cleanup first (``kind="delete"``), then a plain ``kind="ingest"`` —
    NEVER the ``reconcile`` a plain ``--force`` runs — and the manifest entry is a FRESH stamp
    under the current model. Control on the same corpus first: ``--force`` still reconciles."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    monkeypatch.setattr(config, "ingest_model_label", lambda: "fake:model-a")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A weak-model fact."))
    ingest.ingest()
    assert agent.calls == [("raw/notes.md", "ingest")]

    agent.reset()
    ingest.ingest([str(raw / "notes.md")], force=True)
    assert agent.calls == [("raw/notes.md", "reconcile")]  # control: force stays a reconcile

    monkeypatch.setattr(config, "ingest_model_label", lambda: "fake:model-b")
    agent = fake_agent(side_effect=_reingest_side_effect(cite_page))
    report = ingest.ingest([str(raw / "notes.md")], reingest=True)

    assert agent.calls == [("raw/notes.md", "delete"), ("raw/notes.md", "ingest")]
    assert report.reingest_cleaned == ["raw/notes.md"]
    assert report.sources_deleted == []  # a reingest is not a deletion
    assert report.processed == ["raw/notes.md"]
    assert not report.errors
    assert not (wiki / "misc" / "note.md").exists()  # the old treatment is gone...
    assert (wiki / "misc" / "note-v2.md").exists()  # ...replaced by the fresh import
    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    assert entry["model"] == "fake:model-b"  # a brand-new stamp, not a carried one


def test_reingest_without_paths_refused_at_the_api_layer(tmp_citadel, fake_agent):
    """Like force, but twice as expensive per source (cleanup + fresh ingest): ``reingest=True``
    with no paths raises ValueError before any work, no matter the caller."""
    agent = fake_agent()
    with pytest.raises(ValueError, match="--reingest requires explicit paths"):
        ingest.ingest(reingest=True)
    assert agent.count == 0


def test_reingest_uncited_source_skips_cleanup_session(tmp_citadel, fake_agent, cite_page):
    """A tracked source no page cites has nothing to strip: the cleanup job plans ZERO sessions
    (the key is just forgotten) and the fresh ingest runs directly — one paid session, not two."""
    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    agent = fake_agent()  # writes nothing: the source ends up ingested but uncited (no_pages)
    assert ingest.ingest().no_pages == ["raw/notes.md"]

    agent = fake_agent(side_effect=_reingest_side_effect(cite_page))
    report = ingest.ingest([str(raw / "notes.md")], reingest=True)

    assert agent.calls == [("raw/notes.md", "ingest")]  # no delete session was paid for
    assert report.reingest_cleaned == ["raw/notes.md"]  # the key was still dropped + re-imported
    assert report.processed == ["raw/notes.md"]
    assert not report.errors


def test_reingest_cleanup_failure_blocks_the_fresh_ingest(tmp_citadel, fake_agent, cite_page):
    """All-or-nothing per source, across BOTH jobs: a failed cleanup leaves the live wiki and the
    manifest entry untouched, and the fresh session is REFUSED (never run on top of the old
    facts) — recorded as a failure, so re-running ``--reingest`` retries the pair."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A fact."))
    ingest.ingest()
    page = wiki / "misc" / "note.md"
    before_bytes = page.read_bytes()
    entry_before = dict(tmp_citadel.read_manifest()["raw/notes.md"])

    def failing(rel_key, kind="ingest", **kw):
        if kind == "delete":
            raise RuntimeError("cleanup boom")
        cite_page("misc/note-v2.md", rel_key, "Must never land.")

    agent = fake_agent(side_effect=failing)
    report = ingest.ingest([str(raw / "notes.md")], reingest=True)

    assert agent.calls == [("raw/notes.md", "delete")]  # the fresh session never ran
    assert report.reingest_cleaned == []
    assert report.processed == []
    assert any("cleanup boom" in e for e in report.errors)
    assert any("reingest" in e for e in report.errors)  # the refusal names the why
    assert page.read_bytes() == before_bytes  # live wiki untouched
    assert not (wiki / "misc" / "note-v2.md").exists()
    assert tmp_citadel.read_manifest()["raw/notes.md"] == entry_before  # entry kept, not dropped
    assert "raw/notes.md" in failures.load()


def test_reingest_path_run_never_sweeps_deletions(tmp_citadel, fake_agent, cite_page, seed_cited_deleted_source):
    """A reingest run is path-scoped by construction — the rest of the manifest must never be
    read as deletion candidates (the same ``swept_roots=None`` rule as ``--force``)."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A fact."))
    ingest.ingest()
    seed_cited_deleted_source()

    agent = fake_agent(side_effect=_reingest_side_effect(cite_page))
    report = ingest.ingest([str(raw / "notes.md")], reingest=True)

    assert agent.calls == [("raw/notes.md", "delete"), ("raw/notes.md", "ingest")]
    assert report.sources_deleted == []
    assert (wiki / "concepts" / "topic.md").exists()  # the vanished source's page untouched
    assert "raw/gone.md" in tmp_citadel.read_manifest()  # still tracked; swept only by a full run


def test_reingest_cleanup_keeps_the_extraction_cache(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """The cleanup must NOT prune the content-addressed transcript/extraction caches: the source
    still exists with the same bytes, and the fresh session moments later re-reads exactly that
    cached text (contrast a real deletion, which prunes)."""
    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("stable content\n", encoding="utf-8")
    fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/note.md", rel_key, "A fact."))
    ingest.ingest()

    pruned: list[str] = []
    monkeypatch.setattr(pdftext, "prune_cached", lambda sha: pruned.append(sha))
    fake_agent(side_effect=_reingest_side_effect(cite_page))
    report = ingest.ingest([str(raw / "notes.md")], reingest=True)

    assert report.processed == ["raw/notes.md"]
    assert pruned == []  # the cache the fresh session would re-buy stays


# --------------------------------------------------------------------------------------------
# reingest on REPO sources
# --------------------------------------------------------------------------------------------


def test_reingest_repo_runs_cleanup_then_first_time_brief_over_full_digest(
    repo_wiki, fake_agent, make_repo, cite_page, monkeypatch
):
    """A reingested tracked repo runs the cleanup and then ``kind="repo"`` — the FIRST-TIME brief,
    which force deliberately never uses because it would duplicate pages; here the cleanup
    removed them first — over a FULL digest (``only=None``, no change summary)."""
    raw = repo_wiki.raw
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/svc.md", rel_key, "A repo fact."))
    make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})
    ingest.ingest()
    assert agent.calls == [("raw/svc", "repo")]

    captured: dict = {}
    real_build = repo.build_digest

    def capturing_build(path, key, *, only=None, change_summary=None, **kw):
        captured["only"] = only
        captured["change_summary"] = change_summary
        return real_build(path, key, only=only, change_summary=change_summary, **kw)

    monkeypatch.setattr(repo, "build_digest", capturing_build)
    monkeypatch.setattr(repo, "changed_files", lambda *a, **k: ["README.md"])  # a diff must not be consulted

    def rethink(rel_key, kind="repo", **kw):
        if kind == "delete":
            delete_citing_pages(rel_key)
        else:
            cite_page("misc/svc-v2.md", rel_key, "A rethought repo fact.")

    agent = fake_agent(side_effect=rethink)
    report = ingest.ingest([str(raw / "svc")], reingest=True)

    assert agent.calls == [("raw/svc", "delete"), ("raw/svc", "repo")]  # never repo-reconcile
    assert report.reingest_cleaned == ["raw/svc"]
    assert report.processed == ["raw/svc"]
    assert captured == {"only": None, "change_summary": None}  # full digest, no change summary
    assert manifest.is_repo_entry(repo_wiki.read_manifest()["raw/svc"])  # re-tracked as a repo


# --------------------------------------------------------------------------------------------
# the rules layer: the delete brief must cover the still-on-disk reingest cleanup
# --------------------------------------------------------------------------------------------


def test_delete_brief_carries_the_reingest_note():
    """``tasks/delete.md`` briefs the reingest cleanup too: the file may still exist on disk, and
    the agent must strip the provenance without opening it — otherwise a cleanup session that
    finds the file present second-guesses its task."""
    text = (REAL_RULES_DIR / "tasks" / "delete.md").read_text(encoding="utf-8").lower()
    assert "reingest" in text
    assert "still" in text and "disk" in text
