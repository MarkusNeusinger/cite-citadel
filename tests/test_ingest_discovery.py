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


def test_cloud_placeholder_is_flagged_and_ingests_once_hydrated(tmp_citadel, fake_agent, transformer_page):
    """A file whose bytes read as 100% NUL — the signature of a Dropbox/OneDrive "online-only"
    placeholder seen through WSL/SMB — is surfaced with a targeted make-it-available-offline hint
    instead of the generic binary message, and is NOT marked done in the manifest: hydration
    restores the real content without changing size/mtime (and on Windows st_ctime is the stable
    creation time), so a stat-cached entry would skip the fixed file forever — which is also why
    the persisted failure deliberately caches no sha/stat: a trusted stale all-NUL sha would
    otherwise be stamped into the manifest on ingest. Until hydrated it stays visibly stuck; once
    hydrated it ingests normally and the manifest records the REAL content hash."""
    import json
    import os

    raw = tmp_citadel.raw
    agent = fake_agent(transformer_page)
    real = b"# Attention\n\nTransformers use self-attention.\n"
    (raw / "notes.md").write_bytes(b"\x00" * len(real))

    report = ingest.ingest()
    assert "raw/notes.md" in report.unreadable
    assert "raw/notes.md" in report.cloud_placeholders
    assert "cloud-only placeholder" in report.render()
    assert agent.count == 0
    assert "raw/notes.md" not in tmp_citadel.read_manifest()  # NOT stat-cached as done
    fdata = json.loads((tmp_citadel.wiki / ".citadel_failures.json").read_text(encoding="utf-8"))
    assert fdata["raw/notes.md"]["reason"] == "unreadable"
    assert "placeholder" in fdata["raw/notes.md"]["detail"]
    # No cached sha/stat: on a filesystem where hydration leaves the whole stat unchanged
    # (Windows ctime = creation time), a trusted cache would smuggle the NUL sha into mark_done.
    assert "sha256" not in fdata["raw/notes.md"]
    assert "mtime_ns" not in fdata["raw/notes.md"]

    # Still stuck: unlike a genuine binary it is re-surfaced, not silently skipped.
    second = ingest.ingest()
    assert "raw/notes.md" in second.unreadable
    assert agent.count == 0

    # "Hydration": the real bytes appear under the SAME size and mtime — only ctime may move.
    st = (raw / "notes.md").stat()
    (raw / "notes.md").write_bytes(real)
    os.utime(raw / "notes.md", ns=(st.st_atime_ns, st.st_mtime_ns))

    third = ingest.ingest()
    assert "raw/notes.md" in third.processed
    assert third.unreadable == []
    assert agent.count == 1
    entry = tmp_citadel.read_manifest()["raw/notes.md"]  # now genuinely ingested…
    assert entry["sha256"] == manifest.file_sha256(raw / "notes.md")  # …with the REAL content hash
    assert not (tmp_citadel.wiki / ".citadel_failures.json").exists()  # failure cleared


def test_all_nul_binary_vs_mixed_binary_detail(tmp_citadel, fake_agent):
    """Only the 100%-NUL read gets the placeholder hint — a normal binary (NUL bytes mixed with
    other content) keeps the generic no-extractable-text message and IS marked done."""
    import json

    raw = tmp_citadel.raw
    fake_agent()
    (raw / "blob.bin").write_bytes(b"\x00\x01\x02BINARY\xff\x00")

    report = ingest.ingest()
    assert "raw/blob.bin" in report.unreadable
    assert report.cloud_placeholders == []
    assert "placeholder" not in report.render()
    assert "raw/blob.bin" in tmp_citadel.read_manifest()  # marked done, quick-skipped next run
    fdata = json.loads((tmp_citadel.wiki / ".citadel_failures.json").read_text(encoding="utf-8"))
    assert fdata["raw/blob.bin"]["detail"] == "no extractable text (binary/unsupported)"


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


# --- the wiki is never its own raw source ---------------------------------------------------


@pytest.fixture
def wiki_under_raw(make_citadel, tmp_path):
    """The self-ingest layout: ONE raw root (a whole mounted drive, say) with the wiki INSIDE it —
    ``CITADEL_RAW_DIRS=T:\\`` and the wiki at ``T:\\llmWiki\\ds\\wiki``. Discovery must exclude the
    wiki from the walk; nothing but a hand-written ignore pattern used to."""
    drive = tmp_path / "drive"
    return make_citadel(root=tmp_path / "repo", raw=drive, wiki=drive / "llmWiki" / "ds" / "wiki")


def test_wiki_under_a_raw_root_is_never_discovered(wiki_under_raw, seed_page):
    """The wiki's own pages (and its generated index) are not candidates, while real sources in the
    same root are — the walk prunes the wiki directory whole."""
    seed_page("concepts/thing.md", {"type": "Concept", "title": "T", "description": "d", "tags": ["x"]})
    (wiki_under_raw.wiki / "index.md").write_text("# Index\n", encoding="utf-8")
    (wiki_under_raw.raw / "notes.md").write_text("real source\n", encoding="utf-8")
    (wiki_under_raw.raw / "llmWiki").mkdir(exist_ok=True)
    (wiki_under_raw.raw / "llmWiki" / "readme.md").write_text("also a real source\n", encoding="utf-8")

    got = {p.relative_to(wiki_under_raw.raw).as_posix() for p in ingest._candidates(None)}
    assert got == {"notes.md", "llmWiki/readme.md"}


def test_wiki_pages_are_not_ingested_and_the_exclusion_is_announced(
    wiki_under_raw, fake_agent, seed_page, cite_page, capsys
):
    """End to end: a wiki page sitting under the raw root is neither ingested nor tracked, and the
    run says out loud that the wiki was excluded (silence would read as "there was nothing there")."""
    seed_page("concepts/thing.md", {"type": "Concept", "title": "T", "description": "d", "tags": ["x"]})
    src = wiki_under_raw.raw / "notes.md"
    src.write_text("Transformers use self-attention.\n", encoding="utf-8")
    key = manifest.rel_key(src)
    agent = fake_agent(side_effect=lambda *a, **k: cite_page("concepts/transformer.md", key, "A fact."))

    report = ingest.ingest()
    assert [called for called, _kind in agent.calls] == [key]
    assert report.processed == [key]
    tracked = wiki_under_raw.read_manifest()
    assert not [k for k in tracked if "/wiki/" in k], tracked
    assert "excluded from discovery" in capsys.readouterr().err


def test_prior_self_ingested_wiki_entries_are_pruned(wiki_under_raw, fake_agent, seed_page):
    """A wiki page ingested by an EARLIER run (before the guard existed) is swept out of the
    manifest and the failures catalog — it still exists on disk, so deletion detection would never
    clean it up, and it would sit in wiki/sources/index.md forever."""
    seed_page("concepts/thing.md", {"type": "Concept", "title": "T", "description": "d", "tags": ["x"]})
    agent = fake_agent()
    page_key = manifest.rel_key(wiki_under_raw.wiki / "concepts" / "thing.md")
    seeded = manifest.load()
    seeded[page_key] = manifest.make_entry("aa" * 32, "claude:sonnet")
    manifest.save(seeded)
    fails = failures.load()
    failures.record(fails, page_key + ".bak", failures.UNREADABLE, "no extractable text")
    failures.save(fails)

    ingest.ingest()
    assert agent.count == 0
    assert page_key not in manifest.load()
    assert page_key + ".bak" not in failures.load()


def test_explicit_path_inside_the_wiki_is_still_refused(wiki_under_raw, seed_page, monkeypatch):
    """Explicit wins over hidden names, ignore globs and the size ceiling — but not over the wiki
    guard: a generated page cannot be turned into a source by naming it, absolutely OR relatively
    (the relative form is what a user actually types)."""
    page = seed_page("concepts/thing.md", {"type": "Concept", "title": "T", "description": "d", "tags": ["x"]})
    assert ingest._candidates([str(page)]) == []
    assert ingest._candidates([str(wiki_under_raw.wiki)]) == []

    monkeypatch.chdir(wiki_under_raw.wiki.parent)
    assert ingest._candidates(["wiki/concepts/thing.md"]) == []
    assert ingest._candidates(["wiki"]) == []


def test_a_git_backed_wiki_is_not_ingested_as_a_repo_source(wiki_under_raw, seed_page, monkeypatch):
    """CITADEL_WIKI_GIT makes the wiki dir its OWN git repo — i.e. a repo source by every other
    measure. Neither the walk nor an explicit path may digest it as one."""
    monkeypatch.setattr(config, "REPO_SUPPORT", True, raising=False)
    seed_page("concepts/thing.md", {"type": "Concept", "title": "T", "description": "d", "tags": ["x"]})
    (wiki_under_raw.wiki / ".git").mkdir()

    assert ingest._discover_repos(None, ingest._discover_walk(None)) == []
    explicit = [str(wiki_under_raw.wiki)]
    assert ingest._discover_repos(explicit, ingest._discover_walk(explicit)) == []


def test_raw_root_that_is_the_wiki_walks_nothing_and_arms_no_sweep(make_citadel, tmp_path, seed_page):
    """The degenerate config (a raw root that IS the wiki): the walk is refused outright, and the
    root is never counted as entered — so the deletion sweep stays disarmed rather than reading the
    whole corpus as vanished."""
    both = tmp_path / "both"
    make_citadel(root=tmp_path / "repo", raw=both, wiki=both)
    seed_page("concepts/thing.md", {"type": "Concept", "title": "T", "description": "d", "tags": ["x"]})

    walk = ingest._discover_walk(None)
    assert walk.files == [] and walk.entered_roots == []
    assert walk.excluded_wiki == [both]


# --- the discovery size ceiling (CITADEL_MAX_SOURCE_BYTES) -----------------------------------


def test_oversized_files_are_skipped_without_being_hashed(tmp_citadel, monkeypatch):
    """Over the ceiling: skipped at discovery from the walk's own stat — the file is never opened,
    so no sha256 is streamed over it (the whole point for a folder of multi-GB machine data)."""
    raw = tmp_citadel.raw
    (raw / "small.md").write_text("x" * 100, encoding="utf-8")
    (raw / "dump.tdms").write_bytes(b"\x00" * 5000)
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", 1000)
    monkeypatch.setattr(manifest, "file_sha256", lambda p: pytest.fail(f"hashed {p}"))

    walk = ingest._discover_walk(None)
    assert [p.name for p, _st in walk.files] == ["small.md"]
    assert [(p.name, size) for p, size in walk.oversized] == [("dump.tdms", 5000)]


def test_oversized_files_are_reported_and_never_tracked(tmp_citadel, fake_agent, transformer_page, monkeypatch, capsys):
    """A size skip is visible (run report + a stderr NOTE) but, like an ignore-pattern match, is
    never recorded in the manifest or the failures catalog — it is not a failure, just out of scope."""
    raw = tmp_citadel.raw
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "dump.tdms").write_bytes(b"\x00" * 4096)
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", 1024)
    fake_agent(transformer_page)

    report = ingest.ingest()
    assert report.processed == ["raw/notes.md"]
    assert report.oversized == [("raw/dump.tdms", 4096)]
    assert "raw/dump.tdms (4.0 KB)" in report.render()
    assert "CITADEL_MAX_SOURCE_BYTES" in capsys.readouterr().err
    assert "raw/dump.tdms" not in tmp_citadel.read_manifest()
    assert "raw/dump.tdms" not in failures.load()


def test_size_ceiling_is_off_by_default(tmp_citadel):
    """0 (the default) means no limit at all — the behavior citadel has always had."""
    (tmp_citadel.raw / "big.md").write_text("y" * 20000, encoding="utf-8")
    assert config.MAX_SOURCE_BYTES == 0
    assert [p.name for p in ingest._candidates(None)] == ["big.md"]


def test_explicitly_named_oversized_path_is_still_ingested(tmp_citadel, monkeypatch):
    """The ceiling is a scan-budget policy, not a ban: naming the file explicitly ingests it."""
    big = tmp_citadel.raw / "dump.tdms"
    big.write_bytes(b"x" * 5000)
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", 1000)
    assert ingest._candidates([str(big)]) == [big]


def test_a_tracked_source_growing_past_the_ceiling_is_not_swept_as_deleted(tmp_citadel, fake_agent, monkeypatch):
    """An already-ingested source that later crosses the ceiling drops out of the walk. It must NOT
    read as deleted (its provenance would be reconciled out of a wiki that is still correct): the
    sweep's positive .exists() confirmation is what saves it — it simply stops being re-checked."""
    raw = tmp_citadel.raw
    src = raw / "notes.md"
    src.write_text("z" * 5000, encoding="utf-8")
    tracked = manifest.load()
    tracked["raw/notes.md"] = manifest.make_entry(manifest.file_sha256(src), "claude:sonnet")
    manifest.save(tracked)
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", 1000)
    agent = fake_agent()

    report = ingest.ingest()
    assert report.sources_deleted == []
    assert agent.count == 0
    assert "raw/notes.md" in manifest.load()
