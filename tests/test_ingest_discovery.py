"""Source discovery (offline): recursive raw/ walking, hidden-file skipping, OS-junk ignore
patterns, binary sniffing, and the persistent failures catalog for sources that could not be
ingested. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

import pytest

from citadel import config, failures, ingest, lint, manifest, okf


def test_candidates_walks_recursively_and_skips_hidden(tmp_citadel):
    """Discovery picks up ANY file type in ANY sub-folder, skipping hidden files/dirs — both for
    the default (whole-raw/) scan and for an explicit directory argument."""
    raw = tmp_citadel.raw
    (raw / "a.md").write_text("a\n", encoding="utf-8")
    (raw / "sub").mkdir()
    (raw / "sub" / "b.txt").write_text("b\n", encoding="utf-8")
    (raw / "sub" / "c.py").write_text("c\n", encoding="utf-8")
    (raw / ".hidden.md").write_text("h\n", encoding="utf-8")  # hidden file -> skipped
    (raw / ".git").mkdir()
    (raw / ".git" / "config").write_text("x\n", encoding="utf-8")  # hidden dir -> skipped

    expected = {"a.md", "sub/b.txt", "sub/c.py"}
    default = {str(p.relative_to(raw)).replace("\\", "/") for p in ingest._candidates(None)}
    explicit = {str(p.relative_to(raw)).replace("\\", "/") for p in ingest._candidates([str(raw)])}
    assert default == expected
    assert explicit == expected


def test_discovery_skips_os_junk_files_and_dirs(tmp_citadel):
    """OS/system junk (Thumbs.db, desktop.ini, ~$ Office locks, *.tmp, editor backups) and junk
    folders ($RECYCLE.BIN) are skipped during discovery — never fed to the agent — while real
    sources in the same folders are kept."""
    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("real content\n", encoding="utf-8")
    (raw / "Thumbs.db").write_bytes(b"\x00\x01thumbnail cache\x00")
    (raw / "desktop.ini").write_text("[.ShellClassInfo]\n", encoding="utf-8")
    (raw / "~$report.docx").write_bytes(b"\x00office lock\x00")
    (raw / "scratch.tmp").write_text("temp\n", encoding="utf-8")
    (raw / "notes.md~").write_text("editor backup\n", encoding="utf-8")
    (raw / "sub").mkdir()
    (raw / "sub" / "b.txt").write_text("b\n", encoding="utf-8")
    (raw / "sub" / "Thumbs.db").write_bytes(b"\x00more\x00")
    (raw / "$RECYCLE.BIN").mkdir()
    (raw / "$RECYCLE.BIN" / "deleted.md").write_text("in recycle bin\n", encoding="utf-8")

    got = {str(p.relative_to(raw)).replace("\\", "/") for p in ingest._candidates(None)}
    assert got == {"notes.md", "sub/b.txt"}


def test_discovery_skips_wsl_zone_identifier_ads_files(tmp_citadel, fake_agent, transformer_page):
    """WSL surfaces NTFS Alternate-Data-Stream sidecars as their own files: copying a file in from
    Windows leaves a `<name>:Zone.Identifier` mark-of-the-web stream (content `[ZoneTransfer]`),
    which WSL exposes as a real file. It is junk, so discovery skips it entirely while the actual
    source beside it is ingested — and it never lands in the manifest or the failures catalog."""
    raw = tmp_citadel.raw
    fake_agent(transformer_page)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "notes.md:Zone.Identifier").write_text("[ZoneTransfer]\nZoneId=3\n", encoding="utf-8")

    got = {str(p.relative_to(raw)).replace("\\", "/") for p in ingest._candidates(None)}
    assert got == {"notes.md"}  # the ADS sidecar is skipped, the real source kept

    report = ingest.ingest()
    assert "raw/notes.md" in report.processed
    assert "raw/notes.md:Zone.Identifier" not in manifest.load()
    assert "raw/notes.md:Zone.Identifier" not in failures.load()


def test_os_junk_not_recorded_in_manifest_or_failures(tmp_citadel, fake_agent, transformer_page):
    """A junk file next to a real source is ignored entirely: NOT ingested, NOT surfaced as
    unreadable, and NOT written into the manifest or the failures catalog (the user's complaint)."""
    raw = tmp_citadel.raw
    fake_agent(transformer_page)

    (raw / "Thumbs.db").write_bytes(b"\x00\x01\x02thumbnail\x00")
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()
    assert "raw/notes.md" in report.processed
    assert "raw/Thumbs.db" not in report.unreadable
    assert not any("Thumbs.db" in e for e in report.errors)
    assert "raw/Thumbs.db" not in manifest.load()
    assert "raw/Thumbs.db" not in failures.load()


def test_prior_junk_entries_are_pruned_on_next_run(tmp_citadel, fake_agent, transformer_page):
    """A junk file recorded by a PREVIOUS run (before it was ignored) is swept out of the manifest
    and the failures catalog on the next run, even though the file still sits on disk."""
    raw = tmp_citadel.raw
    agent = fake_agent(transformer_page)

    junk = raw / "Thumbs.db"
    junk.write_bytes(b"\x00\x01thumbnail\x00")
    notes = raw / "notes.md"
    notes.write_text("Transformers use self-attention.\n", encoding="utf-8")
    # Seed prior state: notes.md already ingested (so it is skipped, not re-run), and Thumbs.db
    # recorded exactly as the old code left it — a manifest entry plus an unreadable failure.
    seeded = manifest.load()
    seeded["raw/notes.md"] = manifest.make_entry(manifest.file_sha256(notes), "claude:sonnet")
    seeded["raw/Thumbs.db"] = manifest.make_entry(manifest.file_sha256(junk), None)
    manifest.save(seeded)
    fails = failures.load()
    failures.record(fails, "raw/Thumbs.db", failures.UNREADABLE, "no extractable text")
    failures.save(fails)

    report = ingest.ingest()
    assert agent.count == 0  # notes.md unchanged -> skipped; junk pruned without a session
    after = manifest.load()
    assert "raw/notes.md" in after  # the real source is left tracked
    assert "raw/Thumbs.db" not in after
    assert "raw/Thumbs.db" not in failures.load()
    assert "raw/Thumbs.db" not in report.unreadable


def test_migration_sweep_persists_both_catalogs_even_on_early_abort(tmp_citadel, monkeypatch):
    """The junk-entry sweep persists the manifest AND the failures catalog together: if the run
    aborts right after the sweep (before finalization), neither still carries the pruned junk key —
    they never disagree. Simulated by making the partition step (which runs AFTER the sweep) raise."""
    raw = tmp_citadel.raw

    junk = raw / "Thumbs.db"
    junk.write_bytes(b"\x00\x01thumbnail\x00")
    seeded = manifest.load()
    seeded["raw/Thumbs.db"] = manifest.make_entry(manifest.file_sha256(junk), None)
    manifest.save(seeded)
    fails = failures.load()
    failures.record(fails, "raw/Thumbs.db", failures.UNREADABLE, "no extractable text")
    failures.save(fails)

    # Abort AFTER the sweep: _partition_sources is called once the manifest/failures were pruned.
    def boom(*_a, **_k):
        raise RuntimeError("early abort after the migration sweep")

    monkeypatch.setattr(ingest, "_partition_sources", boom)

    with pytest.raises(RuntimeError):
        ingest.ingest()

    # Both sidecars were flushed in the sweep, so on disk they agree — the junk is gone from each.
    assert "raw/Thumbs.db" not in manifest.load()
    assert "raw/Thumbs.db" not in failures.load()


def test_ignore_patterns_config_resolution(monkeypatch):
    """CITADEL_IGNORE_PATTERNS: unset keeps defaults, a leading `+` extends them, any other value
    replaces them; parsing splits on commas and newlines and trims blanks."""
    monkeypatch.delenv("CITADEL_IGNORE_PATTERNS", raising=False)
    assert config._resolve_ignore_patterns() == list(config._DEFAULT_IGNORE_PATTERNS)

    monkeypatch.setenv("CITADEL_IGNORE_PATTERNS", "+*.bak, ~backup* \n")
    extended = config._resolve_ignore_patterns()
    assert extended[: len(config._DEFAULT_IGNORE_PATTERNS)] == list(config._DEFAULT_IGNORE_PATTERNS)
    assert extended[len(config._DEFAULT_IGNORE_PATTERNS) :] == ["*.bak", "~backup*"]

    monkeypatch.setenv("CITADEL_IGNORE_PATTERNS", "only.this,*.foo")
    assert config._resolve_ignore_patterns() == ["only.this", "*.foo"]


def test_is_ignored_name_is_case_insensitive(monkeypatch):
    """Matching a basename against the ignore globs is case-insensitive (Windows filenames vary),
    and only fires for configured patterns."""
    monkeypatch.setattr(config, "IGNORE_PATTERNS", ["Thumbs.db", "*.tmp", "~$*"], raising=False)
    assert ingest._is_ignored_name("Thumbs.db")
    assert ingest._is_ignored_name("thumbs.DB")
    assert ingest._is_ignored_name("SCRATCH.TMP")
    assert ingest._is_ignored_name("~$Report.docx")
    assert not ingest._is_ignored_name("notes.md")
    assert not ingest._is_ignored_name("thumbnails.md")


def test_ingest_discovers_subfolders_and_nonmd(tmp_citadel, fake_agent, seed_page):
    """A .txt at top level and .sql/.py in a sub-folder are all ingested; a hidden file is not."""
    raw = tmp_citadel.raw

    def fake(rel_key: str, kind: str = "ingest") -> None:
        # One valid Concept page per source, citing the raw file (any type/sub-folder).
        slug = okf.slugify(rel_key)
        seed_page(
            f"concepts/{slug}.md",
            {"type": "Concept", "title": slug, "description": "d", "tags": ["x"], "resource": rel_key},
            f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}](../../{rel_key}) - n\n",
        )

    fake_agent(side_effect=fake)

    (raw / "top.txt").write_text("top level text source\n", encoding="utf-8")
    (raw / "code").mkdir()
    (raw / "code" / "query.sql").write_text("SELECT 1; -- a fact\n", encoding="utf-8")
    (raw / "code" / "script.py").write_text("# a python fact\nprint('hi')\n", encoding="utf-8")
    (raw / ".gitkeep").write_text("", encoding="utf-8")

    report = ingest.ingest()
    assert set(report.processed) == {"raw/top.txt", "raw/code/query.sql", "raw/code/script.py"}
    assert "raw/.gitkeep" not in report.processed
    assert len(report.pages_created) == 3
    assert not report.errors
    assert lint.lint().ok()


def test_is_ingestible_classifies_text_pdf_binary(tmp_citadel):
    """Text/code/UTF-8/empty/PDF are ingestible; a NUL byte or a high non-text ratio is not."""
    raw = tmp_citadel.raw

    def mk(name, data):
        p = raw / name
        p.write_bytes(data)
        return p

    assert ingest._is_ingestible(mk("a.txt", b"plain text\n"))
    assert ingest._is_ingestible(mk("a.py", b"print('hi')\n"))
    assert ingest._is_ingestible(mk("u.md", "Café — résumé ☕\n".encode("utf-8")))
    assert ingest._is_ingestible(mk("a.pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\nstuff"))
    assert ingest._is_ingestible(mk("empty", b""))
    assert not ingest._is_ingestible(mk("nul.bin", b"text\x00more\x00data"))
    assert not ingest._is_ingestible(mk("ctrl.bin", bytes([1, 2, 3, 4, 5, 6, 16, 17, 18, 19]) * 50))


def test_binary_raw_file_is_logged_unreadable_not_ingested(tmp_citadel, fake_agent, transformer_page):
    """A binary blob is filtered out before the agent, surfaced as unreadable, logged in log.md,
    and marked done so a re-run neither re-checks nor re-logs it — without failing the run."""
    raw = tmp_citadel.raw
    agent = fake_agent(transformer_page)

    (raw / "blob.bin").write_bytes(b"\x00\x01\x02\x03BINARY\xff\xfe\x00")
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()
    assert agent.count == 1  # only the readable text file ran a session
    assert "raw/notes.md" in report.processed
    assert "raw/blob.bin" in report.unreadable
    assert "raw/blob.bin" not in report.processed
    assert not report.errors  # unreadable is logged, NOT a hard error

    log_text = tmp_citadel.log_path.read_text(encoding="utf-8")
    assert "raw/blob.bin" in log_text and "no readable text" in log_text

    data = tmp_citadel.read_manifest()
    assert "raw/blob.bin" in data  # marked done

    second = ingest.ingest()
    assert "raw/blob.bin" in second.skipped
    assert second.unreadable == []
    assert agent.count == 1  # not re-run


def test_failures_are_persisted_surfaced_and_cleared(tmp_citadel, fake_agent, transformer_page):
    """Unreadable AND errored/failed sources are written to a persistent .citadel_failures.json with
    a reason and surfaced in wiki/sources/index.md — and a source that later succeeds drops off,
    while an unreadable file (still stuck) stays listed across runs."""
    import json

    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "blob.bin").write_bytes(b"text\x00more\x00binary")  # unreadable
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")  # will error

    fake_agent(error=RuntimeError("agent exploded"))
    report = ingest.ingest()
    assert "raw/notes.md" in report.errors[0] and report.processed == []

    fpath = wiki / ".citadel_failures.json"
    data = json.loads(fpath.read_text(encoding="utf-8"))
    assert data["raw/blob.bin"]["reason"] == "unreadable"
    assert data["raw/notes.md"]["reason"] == "error"

    catalog = (wiki / "sources" / "index.md").read_text(encoding="utf-8")
    assert "## Could not ingest" in catalog
    assert "raw/blob.bin" in catalog and "raw/notes.md" in catalog

    # Fix the session so notes.md now succeeds: its failure clears; the unreadable blob stays stuck.
    fake_agent(transformer_page)
    ingest.ingest()
    data2 = json.loads(fpath.read_text(encoding="utf-8"))
    assert "raw/notes.md" not in data2  # succeeded -> dropped
    assert data2["raw/blob.bin"]["reason"] == "unreadable"  # still stuck -> stays across runs
