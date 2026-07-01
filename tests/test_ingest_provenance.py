"""Provenance tracking (offline): the manifest keys sources by sha256 + importing model, a moved
or copied raw file is recognized (not re-ingested) with its references repointed, and the
sources catalog surfaces which model imported what. ``llm.run_ingest_session`` is replaced by
``fake_agent``.
"""

from __future__ import annotations

from citadel import config, ingest, lint, manifest, store


def test_moved_raw_file_is_recognized_not_reingested(tmp_citadel, fake_agent, transformer_page):
    """Reorganizing a raw file (same bytes, new path) is recognized: NOT re-ingested, the manifest
    is re-keyed, and the wiki's resource/citation references are repointed so lint stays clean."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    agent = fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    first = ingest.ingest()
    assert first.processed == ["raw/notes.md"] and agent.count == 1
    page = wiki / "concepts" / "transformer.md"
    assert "../../raw/notes.md" in page.read_text(encoding="utf-8")

    # Move the source into a sub-folder (byte-for-byte identical content).
    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "notes.md").unlink()

    second = ingest.ingest()
    assert agent.count == 1  # NOT re-ingested
    assert second.processed == []
    assert ("raw/notes.md", "raw/ml/notes.md") in second.moved
    assert not second.errors

    import json

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert "raw/ml/notes.md" in data and "raw/notes.md" not in data  # re-keyed

    text = page.read_text(encoding="utf-8")
    assert "resource: raw/ml/notes.md" in text
    assert "../../raw/ml/notes.md" in text
    assert "(../../raw/notes.md)" not in text
    rep = lint.lint()
    assert rep.ok() and rep.bad_sources == []

    log_text = tmp_citadel.log_path.read_text(encoding="utf-8")
    assert "raw/ml/notes.md" in log_text and "moved" in log_text


def test_duplicate_raw_file_not_reingested(tmp_citadel, fake_agent, transformer_page):
    """A byte-for-byte COPY at a new path (original still present) is recognized as already-known
    content and not re-ingested; the original's references are left intact (no repoint)."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    agent = fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()
    assert agent.count == 1

    (raw / "copy.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    report = ingest.ingest()
    assert agent.count == 1
    assert ("raw/notes.md", "raw/copy.md") in report.moved

    import json

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert "raw/notes.md" in data and "raw/copy.md" in data  # both tracked

    text = (wiki / "concepts" / "transformer.md").read_text(encoding="utf-8")
    assert "resource: raw/notes.md" in text  # original NOT repointed (still on disk)
    assert lint.lint().ok()


def test_rewrite_raw_references_repoints_resource_and_citation(tmp_citadel, seed_page):
    """store.rewrite_raw_references repoints the `resource` frontmatter and real citation links to
    a moved source, leaving a literal link inside a code fence untouched."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("x\n", encoding="utf-8")
    seed_page(
        "concepts/t.md",
        {"type": "Concept", "title": "T", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
        "A fact.[^s1]\n\n"
        "```\n"
        "example: [old](../../raw/notes.md)\n"  # fenced literal -> untouched
        "```\n\n"
        "## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
    )

    changed = store.rewrite_raw_references("raw/notes.md", "raw/ml/notes.md")
    assert changed == ["concepts/t.md"]
    text = (wiki / "concepts" / "t.md").read_text(encoding="utf-8")
    assert "resource: raw/ml/notes.md" in text
    assert "[^s1]: [raw/notes.md](../../raw/ml/notes.md)" in text  # real citation repointed
    assert "example: [old](../../raw/notes.md)" in text  # fenced literal left intact


def test_file_sha256_streams_and_matches_oneshot(tmp_path):
    """The chunk-streamed hash equals a one-shot hash of the whole bytes (memory-bounded, but
    identical digest), across multiple read chunks."""
    import hashlib

    data = bytes(range(256)) * 9000  # ~2.3 MiB -> several 1 MiB chunks
    p = tmp_path / "big.bin"
    p.write_bytes(data)
    assert manifest.file_sha256(p) == hashlib.sha256(data).hexdigest()


def test_unreadable_already_ingested_file_does_not_crash(tmp_citadel, fake_agent, transformer_page, monkeypatch):
    """An already-tracked raw file that becomes unreadable makes is_pending() (which hashes a
    tracked file) raise OSError — that must NOT crash the run: it stays classified as skipped,
    since it is already in the wiki."""
    raw = tmp_citadel.raw
    fake_agent(transformer_page)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    assert ingest.ingest().processed == ["raw/notes.md"]

    real = ingest.manifest.file_sha256

    def boom(path):
        if str(path).endswith("notes.md"):
            raise OSError("permission denied")
        return real(path)

    monkeypatch.setattr(ingest.manifest, "file_sha256", boom)

    report = ingest.ingest()  # must not raise
    assert "raw/notes.md" in report.skipped
    assert report.processed == []
    assert not report.errors


def test_ingest_records_importing_model_in_manifest(tmp_citadel, fake_agent, transformer_page, monkeypatch):
    """Each ingested source records WHICH model imported it; the report/log carry it too. A source
    no model imported (an unreadable binary) records its sha alone, with no model."""
    import json

    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "opus", raising=False)
    fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "blob.bin").write_bytes(b"\x00\x01BINARY\xff")

    report = ingest.ingest()
    assert report.model == "claude:opus"
    assert "Model: claude:opus" in report.render()

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert data["raw/notes.md"]["model"] == "claude:opus"
    assert "model" not in data["raw/blob.bin"]  # nothing imported it

    log_text = tmp_citadel.log_path.read_text(encoding="utf-8")
    assert "(model: claude:opus)" in log_text


def test_sources_catalog_lists_source_model_and_referencing_pages(
    tmp_citadel, fake_agent, transformer_page, monkeypatch
):
    """Ingest generates wiki/sources/index.md: a row per source with its model and links to the
    pages that cite it, and the top index links the catalog under 'See also'."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()

    catalog = (wiki / "sources" / "index.md").read_text(encoding="utf-8")
    assert catalog.startswith("# Sources") and not catalog.startswith("---")
    assert "| Source | Model | Referenced by |" in catalog
    # The source links to the raw file, shows the model, and links the page that cites it.
    assert "[raw/notes.md](../../raw/notes.md)" in catalog
    assert "claude:sonnet" in catalog
    assert "[Transformer](../concepts/transformer.md)" in catalog

    top = (wiki / "index.md").read_text(encoding="utf-8")
    assert "[sources](sources/index.md)" in top

    # The catalog is a reserved nav file: load() ignores it, so it is not a page / graph node.
    assert all(p.rel_path != "sources/index.md" for p in store.load())


def test_sources_catalog_removed_when_no_tracked_sources(tmp_citadel, seed_page):
    """With an empty manifest the catalog is not written, and a stale one is removed so it never
    lingers after the last source is gone."""
    wiki = tmp_citadel.wiki
    stale = wiki / "sources" / "index.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("# Sources\n\nstale\n", encoding="utf-8")
    seed_page(
        "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/a.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )

    store.rebuild_indexes()  # manifest is empty in this fixture

    assert not stale.exists()
    assert "[sources](sources/index.md)" not in (wiki / "index.md").read_text(encoding="utf-8")


def test_moved_source_carries_original_importing_model(tmp_citadel, fake_agent, transformer_page, monkeypatch):
    """Reorganizing a raw file is not a re-ingest, so the moved entry keeps the model that
    ORIGINALLY imported it — not the model configured for the run that detected the move."""
    import json

    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "opus", raising=False)
    fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()  # imported by claude:opus

    # A later run on a DIFFERENT model detects the move; the carried model must stay claude:opus.
    monkeypatch.setattr(config, "INGEST_MODEL", "haiku", raising=False)
    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "notes.md").unlink()

    report = ingest.ingest()
    assert ("raw/notes.md", "raw/ml/notes.md") in report.moved

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert "raw/notes.md" not in data
    assert data["raw/ml/notes.md"]["model"] == "claude:opus"  # original model carried, not haiku

    # The catalog reflects the moved key + the carried model.
    catalog = (wiki / "sources" / "index.md").read_text(encoding="utf-8")
    assert "[raw/ml/notes.md](../../raw/ml/notes.md)" in catalog
    assert "claude:opus" in catalog
