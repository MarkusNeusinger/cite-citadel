"""Changed + deleted raw-source propagation (offline): a changed source runs a reconcile session,
a vanished source runs a delete-cleanup session (full runs only), and moves are never mistaken
for deletions. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from citadel import config, ingest, lint, manifest, store


def test_changed_source_runs_reconcile_not_plain_ingest(tmp_citadel, fake_agent, seed_page):
    """A NEW source runs with kind='ingest'; re-ingesting it after its bytes change runs with
    kind='reconcile' (so the agent updates/removes stale facts instead of only appending)."""
    raw = tmp_citadel.raw

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/transformer.md",
            {"type": "Concept", "title": "Transformer", "description": "d", "tags": ["ml"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    agent = fake_agent(side_effect=fake)

    (raw / "notes.md").write_text("first\n", encoding="utf-8")
    ingest.ingest()
    assert agent.calls == [("raw/notes.md", "ingest")]  # brand new -> plain ingest

    (raw / "notes.md").write_text("second, corrected\n", encoding="utf-8")
    ingest.ingest()
    assert agent.calls[-1] == ("raw/notes.md", "reconcile")  # changed bytes -> reconcile


def test_deleted_source_citations_reconciled_out(tmp_citadel, fake_agent, seed_cited_deleted_source):
    """A tracked raw file that vanished from disk triggers a kind='delete' cleanup session: the
    page it solely sourced is removed, its manifest key is dropped, and lint stays clean."""
    wiki = tmp_citadel.wiki
    seed_cited_deleted_source()  # raw/gone.md: tracked + cited, but the file is NOT on disk

    def fake(rel_key, kind="ingest"):
        # The deleted source was this page's only provenance -> remove the page entirely.
        (config.WIKI_DIR / "concepts" / "topic.md").unlink()

    agent = fake_agent(side_effect=fake)

    report = ingest.ingest()

    assert agent.calls == [("raw/gone.md", "delete")]  # exactly one delete-cleanup session
    assert report.sources_deleted == ["raw/gone.md"]
    assert "concepts/topic.md" in report.pages_deleted
    assert not (wiki / "concepts" / "topic.md").exists()
    assert not report.errors

    data = tmp_citadel.read_manifest()
    assert "raw/gone.md" not in data  # manifest key dropped
    rep = lint.lint()
    assert rep.ok() and rep.bad_sources == []

    log_text = tmp_citadel.log_path.read_text(encoding="utf-8")
    assert "raw/gone.md" in log_text and "deleted" in log_text


def test_deleted_source_drops_one_citation_keeps_corroborated_fact(tmp_citadel, fake_agent, seed_page):
    """When a deleted source co-cited a fact that ANOTHER source also supports, the cleanup
    drops only the deleted source's marker/definition and keeps the fact + the survivor cite."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "keep.md").write_text("keep\n", encoding="utf-8")
    seed_page(
        "concepts/dual.md",
        {"type": "Concept", "title": "Dual", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
        "A corroborated fact.[^s1][^s2]\n\n## Sources\n\n"
        "[^s1]: [raw/keep.md](../../raw/keep.md) - k\n"
        "[^s2]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    manifest.save({"raw/keep.md": manifest.file_sha256(raw / "keep.md"), "raw/gone.md": "deadbeef"})

    def fake(rel_key, kind="ingest"):
        assert (rel_key, kind) == ("raw/gone.md", "delete")
        # Keep the fact + [^s1]/keep.md; remove only [^s2] and its gone.md definition.
        seed_page(
            "concepts/dual.md",
            {"type": "Concept", "title": "Dual", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
            "A corroborated fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/keep.md](../../raw/keep.md) - k\n",
        )

    fake_agent(side_effect=fake)

    report = ingest.ingest()

    assert report.sources_deleted == ["raw/gone.md"]
    assert "concepts/dual.md" in report.pages_updated
    text = (wiki / "concepts" / "dual.md").read_text(encoding="utf-8")
    assert "corroborated fact" in text and "[^s1]" in text  # fact + survivor cite kept
    assert "gone.md" not in text and "[^s2]" not in text  # deleted source's cite removed
    assert lint.lint().ok()
    assert store.find_raw_references("raw/gone.md") == []


def test_deletion_runs_before_pending_source_touching_stale_page(tmp_citadel, fake_agent, seed_page):
    """Ordering regression (corpus-discovered, project-history wave 3): within ONE full run the
    deletion cleanup must run BEFORE the pending sources, so a NEW source whose session edits a
    page that still cites the just-deleted source does not fail validation on that PRE-EXISTING
    stale citation. Here systems/komet.md cites both the present raw/keep.md and the vanished
    raw/gone.md; the delete job strips gone.md's citation FIRST, then raw/portal.md's session
    appends its own cited fact to the now-consistent page and succeeds — zero errors, both jobs
    applied. Reverse the group order (pending before delete) and this test FAILS: portal's session
    touches komet.md while it still cites the missing gone.md -> bad_source -> the whole source
    rolls back, portal is never applied and report.errors is non-empty. The order pin below (delete
    call before ingest call) is what makes this the regression's guard."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    # A still-present corroborating source, and the NEW pending source B.
    (raw / "keep.md").write_text("keep\n", encoding="utf-8")
    (raw / "portal.md").write_text("portal kickoff\n", encoding="utf-8")
    # The page that cites BOTH the present keep.md and the vanished gone.md (its resource stays on
    # the present source, so only the footnote to gone.md is the stale, validation-tripping cite).
    seed_page(
        "systems/komet.md",
        {"type": "System", "title": "Komet", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
        "Komet ships.[^s1][^s2]\n\n## Sources\n\n"
        "[^s1]: [raw/keep.md](../../raw/keep.md) - k\n"
        "[^s2]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    # keep.md tracked+unchanged (skipped); gone.md tracked but off disk (a deletion); portal.md new.
    manifest.save({"raw/keep.md": manifest.file_sha256(raw / "keep.md"), "raw/gone.md": "deadbeef"})

    def fake(rel_key, kind="ingest"):
        if kind == "delete":
            assert (rel_key, kind) == ("raw/gone.md", "delete")
            # Cleanup: drop ONLY gone.md's citation, keep the fact + the keep.md cite.
            seed_page(
                "systems/komet.md",
                {"type": "System", "title": "Komet", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
                "Komet ships.[^s1]\n\n## Sources\n\n[^s1]: [raw/keep.md](../../raw/keep.md) - k\n",
            )
            return
        # The new source B (raw/portal.md) edits the SAME page, appending its own cited fact.
        assert (rel_key, kind) == ("raw/portal.md", "ingest")
        seed_page(
            "systems/komet.md",
            {"type": "System", "title": "Komet", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
            "Komet ships.[^s1]\n\nPortal kickoff scheduled.[^s2]\n\n## Sources\n\n"
            "[^s1]: [raw/keep.md](../../raw/keep.md) - k\n"
            "[^s2]: [raw/portal.md](../../raw/portal.md) - p\n",
        )

    agent = fake_agent(side_effect=fake)

    report = ingest.ingest()

    # THE PIN: the deletion cleanup ran FIRST, then the pending file — both applied, zero errors.
    assert agent.calls == [("raw/gone.md", "delete"), ("raw/portal.md", "ingest")]
    assert report.errors == []
    assert report.sources_deleted == ["raw/gone.md"]
    assert "raw/portal.md" in report.processed
    assert "systems/komet.md" in report.pages_updated

    text = (wiki / "systems" / "komet.md").read_text(encoding="utf-8")
    assert "Portal kickoff scheduled." in text and "[^s2]: [raw/portal.md]" in text  # B's fact landed
    assert "gone.md" not in text  # the deleted source's stale citation is gone
    assert lint.lint().ok()
    assert store.find_raw_references("raw/gone.md") == []
    assert "raw/gone.md" not in tmp_citadel.read_manifest()  # deletion's manifest key dropped


def test_deleted_source_with_no_references_just_dropped(tmp_citadel, fake_agent, seed_page):
    """A deleted source nothing cites needs no agent session — its manifest key is simply
    dropped, and an unrelated page citing a still-present source is left untouched."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "keep.md").write_text("keep\n", encoding="utf-8")
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
        "Kept.[^s1]\n\n## Sources\n\n[^s1]: [raw/keep.md](../../raw/keep.md) - k\n",
    )
    manifest.save({"raw/keep.md": manifest.file_sha256(raw / "keep.md"), "raw/gone.md": "deadbeef"})

    def fake(rel_key, kind="ingest"):
        raise AssertionError(f"no session should run (got {rel_key}, {kind})")

    fake_agent(side_effect=fake)

    report = ingest.ingest()

    assert report.sources_deleted == ["raw/gone.md"]
    assert report.processed == [] and not report.errors
    assert (wiki / "concepts" / "keep.md").exists()  # unrelated page untouched

    data = tmp_citadel.read_manifest()
    assert "raw/gone.md" not in data and "raw/keep.md" in data


def test_deleted_cleanup_incomplete_rolls_back_and_retries(tmp_citadel, fake_agent, seed_page):
    """If the cleanup session fails to remove every reference to the deleted source, the
    post-condition fails: the whole source is rolled back, an error is collected, and the
    manifest key is KEPT so it is retried next run (no half-cleaned wiki)."""
    wiki = tmp_citadel.wiki
    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/gone.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    manifest.save({"raw/gone.md": "deadbeef"})

    fake_agent()  # agent does nothing -> the gone.md citation survives

    report = ingest.ingest()

    assert report.sources_deleted == []  # not completed
    assert any("still cited" in e for e in report.errors)
    assert (wiki / "concepts" / "topic.md").exists()  # rolled back, page intact

    data = tmp_citadel.read_manifest()
    assert "raw/gone.md" in data  # key kept -> retried next run


def test_deletion_swept_only_on_full_run_not_path_scoped(tmp_citadel, fake_agent, seed_page):
    """A path-scoped ingest must NOT sweep the whole manifest for deletions — only a full run
    (no paths) reconciles a vanished source, so `ingest <one-file>` can't surprise-prune."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/gone.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    (raw / "new.md").write_text("new source\n", encoding="utf-8")
    manifest.save({"raw/gone.md": "deadbeef"})

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/new.md",
            {"type": "Concept", "title": "New", "description": "d", "tags": ["x"], "resource": "raw/new.md"},
            "New.[^s1]\n\n## Sources\n\n[^s1]: [raw/new.md](../../raw/new.md) - n\n",
        )

    agent = fake_agent(side_effect=fake)

    report = ingest.ingest([str(raw / "new.md")])  # scoped to one file

    assert agent.calls == [("raw/new.md", "ingest")]  # only the targeted file ran; no delete session
    assert report.sources_deleted == []
    assert (wiki / "concepts" / "topic.md").exists()  # the deleted source's page is untouched

    data = tmp_citadel.read_manifest()
    assert "raw/gone.md" in data  # still tracked; not pruned by a scoped run


def test_moved_source_not_treated_as_deletion(tmp_citadel, fake_agent, transformer_page):
    """A reorganized file (old path gone, same bytes at a new path) is a MOVE, not a deletion:
    its references are repointed, no delete-cleanup session runs, and the page survives."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    agent = fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()
    assert agent.count == 1

    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "notes.md").unlink()

    report = ingest.ingest()
    assert agent.count == 1  # no session at all — neither re-ingest nor delete-cleanup
    assert report.sources_deleted == []  # the gone old path is a move, not a deletion
    assert ("raw/notes.md", "raw/ml/notes.md") in report.moved
    assert (wiki / "concepts" / "transformer.md").exists()
    assert lint.lint().ok()


def test_find_raw_references_matches_resource_and_citation_skips_fence(tmp_citadel, seed_page):
    """store.find_raw_references finds pages via `resource` frontmatter OR a real citation link,
    and ignores a citation written as a literal inside a code fence (a format-doc example)."""
    seed_page(
        "concepts/by-resource.md",
        {"type": "Concept", "title": "By Resource", "description": "d", "tags": ["x"], "resource": "raw/target.md"},
        "Body.[^s1]\n\n## Sources\n\n[^s1]: [raw/target.md](../../raw/target.md) - t\n",
    )
    seed_page(
        "concepts/by-citation.md",
        {"type": "Concept", "title": "By Citation", "description": "d", "tags": ["x"], "resource": "raw/other.md"},
        "Body.[^s1]\n\n## Sources\n\n[^s1]: [raw/target.md](../../raw/target.md) - t\n",
    )
    seed_page(
        "concepts/fence-only.md",
        {"type": "Concept", "title": "Fence Only", "description": "d", "tags": ["x"], "resource": "raw/other.md"},
        "Example:\n\n```\n[^s1]: [raw/target.md](../../raw/target.md)\n```\n\n"
        "Body.[^s1]\n\n## Sources\n\n[^s1]: [raw/other.md](../../raw/other.md) - o\n",
    )

    hits = store.find_raw_references("raw/target.md")
    assert hits == ["concepts/by-citation.md", "concepts/by-resource.md"]
    assert "concepts/fence-only.md" not in hits  # fenced literal not counted
