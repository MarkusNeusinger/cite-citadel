"""``citadel status`` bucket classification (offline): every lifecycle bucket the per-source state
table renders — the ``(stale)`` rules marker, a DUPLICATE failure routed to *skipped* (not failed), a
CURATE record excluded (it is a page, not a source), an untracked raw file surfacing as *pending*, and
an OS/junk file matched by ``CITADEL_IGNORE_PATTERNS`` shown as *ignored* — plus the ``cli.main`` entry
point. Everything reads the manifest + failures catalog + one stat-only walk over a ``tmp_citadel``
layout; no CLI, no network.
"""

from __future__ import annotations

from pathlib import Path

from citadel import cli, config, failures, manifest, status


def _track(key: str, sha: str, rules_version: str | None, model: str = "claude:sonnet") -> None:
    """Record one manifest entry for raw source ``key`` (load-modify-save), stamping the importing
    model and the rules-tree hash the session ran under — what status' stale detector reads."""
    tracked = manifest.load()
    tracked[key] = manifest.make_entry(sha, model, rules_version)
    manifest.save(tracked)


def _fail(key: str, reason: str, detail: str = "", model: str | None = None) -> None:
    """Record one failures-catalog entry for ``key`` (load-modify-save)."""
    stuck = failures.load()
    failures.record(stuck, key, reason, detail, model)
    failures.save(stuck)


# --- ingested: the (stale) rules marker ----------------------------------------------------


def test_ingested_stale_rules_entry_renders_stale(tmp_citadel):
    """A source whose recorded rules-tree hash predates the CURRENT rulebook is flagged ``(stale)``
    — the ``curate --stale-rules`` signal — while one stamped with the current hash is not."""
    (tmp_citadel.raw / "old.md").write_text("body\n", encoding="utf-8")
    (tmp_citadel.raw / "fresh.md").write_text("body\n", encoding="utf-8")
    _track("raw/old.md", manifest.file_sha256(tmp_citadel.raw / "old.md"), "0000oldrules")
    _track("raw/fresh.md", manifest.file_sha256(tmp_citadel.raw / "fresh.md"), config.rules_version())

    report = status.build_status()
    by_key = {s.key: s for s in report.ingested}
    assert by_key["raw/old.md"].stale_rules is True
    assert by_key["raw/fresh.md"].stale_rules is False

    text = report.render()
    # The (stale) tag rides only the stale row.
    stale_line = next(line for line in text.splitlines() if "raw/old.md" in line)
    fresh_line = next(line for line in text.splitlines() if "raw/fresh.md" in line)
    assert "(stale)" in stale_line
    assert "(stale)" not in fresh_line


def test_stale_sources_close_with_the_refresh_hint_and_json_is_unchanged(tmp_citadel):
    """K (stale) sources close the table with the one command whose queue is exactly that set —
    the same K as ``refresh.stale_count()`` — while ``status --json`` keeps its shape."""
    from citadel import refresh

    (tmp_citadel.raw / "old.md").write_text("body\n", encoding="utf-8")
    (tmp_citadel.raw / "fresh.md").write_text("body\n", encoding="utf-8")
    _track("raw/fresh.md", manifest.file_sha256(tmp_citadel.raw / "fresh.md"), config.rules_version())
    fresh_only = status.build_status()
    assert "citadel refresh --stale-rules" not in fresh_only.render()
    keys_before = set(fresh_only.as_dict())

    _track("raw/old.md", manifest.file_sha256(tmp_citadel.raw / "old.md"), "0000oldrules")
    report = status.build_status()
    text = report.render()
    assert refresh.stale_count() == 1
    assert "1 (stale) source(s): re-verify with citadel refresh --stale-rules --limit 1" in text
    assert text.isascii()
    assert set(report.as_dict()) == keys_before


# --- failed vs skipped-duplicate: the bucket a row lands in IS its state --------------------


def test_duplicate_failure_lands_in_skipped_not_failed(tmp_citadel):
    """A same-basename ``duplicate`` is a deliberate SKIP, not a failure: it routes to
    ``skipped_duplicate`` and never to ``failed`` (and renders under that heading)."""
    _fail("raw/deck.pdf", failures.DUPLICATE, "same basename as raw/deck.pptx")
    _fail("raw/scan.tiff", failures.UNREADABLE, "no extractable text")

    report = status.build_status()
    assert [s.key for s in report.skipped_duplicate] == ["raw/deck.pdf"]
    assert [s.key for s in report.failed] == ["raw/scan.tiff"]

    text = report.render()
    assert "Skipped as duplicate (1)" in text
    assert "Failed (1)" in text
    assert "raw/deck.pdf" in text.split("Skipped as duplicate")[1]


def test_curate_failure_is_excluded_from_the_per_source_view(tmp_citadel):
    """A ``curate`` failure is keyed by a PAGE rel_path, not a source — status is a per-SOURCE view,
    so it appears in NO bucket (surfaced instead by ``citadel curate``)."""
    _fail("concepts/topic.md", failures.CURATE, "cluster session failed its gate")

    report = status.build_status()
    all_keys = (
        {s.key for s in report.ingested}
        | {s.key for s in report.failed}
        | {s.key for s in report.skipped_duplicate}
        | set(report.pending)
    )
    assert "concepts/topic.md" not in all_keys
    assert report.failed == [] and report.skipped_duplicate == []


# --- pending / ignored: from the stat-only discovery walk ----------------------------------


def test_untracked_raw_file_is_pending(tmp_citadel):
    """A file on disk under a raw root that is in neither the manifest nor the failures catalog is
    ``pending`` — waiting for its first ingest."""
    (tmp_citadel.raw / "todo.md").write_text("not yet ingested\n", encoding="utf-8")
    (tmp_citadel.raw / "done.md").write_text("already in\n", encoding="utf-8")
    _track("raw/done.md", manifest.file_sha256(tmp_citadel.raw / "done.md"), config.rules_version())

    report = status.build_status()
    assert "raw/todo.md" in report.pending
    assert "raw/done.md" not in report.pending  # tracked -> ingested, not pending


def test_os_junk_file_is_ignored_not_pending(tmp_citadel):
    """A ``Thumbs.db`` (a default ``CITADEL_IGNORE_PATTERNS`` glob) shows under ``ignored`` and is
    NOT mistaken for a pending source — discovery prunes it before the walk sees it."""
    (tmp_citadel.raw / "Thumbs.db").write_bytes(b"\x00junk")
    (tmp_citadel.raw / "real.md").write_text("real\n", encoding="utf-8")

    report = status.build_status()
    assert "Thumbs.db" in report.ignored
    assert "raw/Thumbs.db" not in report.pending  # ignored, never pending
    assert "raw/real.md" in report.pending  # the genuine untracked file still surfaces


def _ignore_index_and_private(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "INDEX.md", "private"])
    for sub in ("a", "b", "c"):
        (tmp_citadel.raw / sub).mkdir()
        (tmp_citadel.raw / sub / "INDEX.md").write_text("x\n", encoding="utf-8")
    private = tmp_citadel.raw / "private"
    (private / "sub").mkdir(parents=True)
    for name in ("1.txt", "2.txt", "3.txt"):
        (private / name).write_text("secret\n", encoding="utf-8")
    (private / "sub" / "4.txt").write_text("secret\n", encoding="utf-8")


def test_ignored_counts_files_per_name_not_distinct_names(tmp_citadel, monkeypatch):
    """F08: one row per distinct (name, is-dir) with real file counts — three INDEX.md files are
    three files, an ignored folder counts the files inside it (subfolders included)."""
    _ignore_index_and_private(tmp_citadel, monkeypatch)
    report = status.build_status()
    text = report.render()
    assert "Ignored (7 files, 2 names)" in text
    assert "  INDEX.md  (3 files)" in text
    assert "  private/  (1 folder, 4 files)" in text
    assert report.ignored == ["INDEX.md", "private"]
    assert report.as_dict()["ignored_detail"] == [
        {"name": "INDEX.md", "dir": False, "matches": 3, "files": 3, "capped": False},
        {"name": "private", "dir": True, "matches": 1, "files": 4, "capped": False},
    ]
    text.encode("ascii")


def test_discover_walk_records_ignored_entries_but_never_hidden_ones(tmp_citadel, monkeypatch):
    from citadel import ingest

    _ignore_index_and_private(tmp_citadel, monkeypatch)
    (tmp_citadel.raw / ".hidden.md").write_text("h\n", encoding="utf-8")
    (tmp_citadel.raw / "real.md").write_text("r\n", encoding="utf-8")
    walk = ingest._discover_walk(None)
    ignored = {(p.relative_to(tmp_citadel.raw).as_posix(), d) for p, d in walk.ignored}
    assert ignored == {("a/INDEX.md", False), ("b/INDEX.md", False), ("c/INDEX.md", False), ("private", True)}
    assert [p.name for p, _st in walk.files] == ["real.md"]

    # An explicitly named ignored file wins: it is a candidate, not an ignored entry.
    explicit = ingest._discover_walk([str(tmp_citadel.raw / "a" / "INDEX.md")])
    assert [p.name for p, _st in explicit.files] == ["INDEX.md"] and explicit.ignored == []


def test_ignored_folder_count_is_capped_and_never_raises(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "bulk", "locked"])
    bulk = tmp_citadel.raw / "bulk"
    bulk.mkdir()
    for i in range(1500):
        (bulk / f"{i}.bin").write_bytes(b"x")
    (tmp_citadel.raw / "locked").mkdir()
    real_scandir = status.os.scandir

    def scandir(path):
        if Path(path).name == "locked":
            raise PermissionError("denied")
        return real_scandir(path)

    monkeypatch.setattr(status.os, "scandir", scandir)
    report = status.build_status()
    text = report.render()
    assert "  bulk/  (1 folder, 1000+ files)" in text
    assert "  locked/  (1 folder, 0+ files)" in text
    assert "Ignored (1000+ files, 2 names)" in text
    detail = {g["name"]: g for g in report.as_dict()["ignored_detail"]}
    assert detail["bulk"]["capped"] is True and detail["bulk"]["files"] == 1000


def test_ignored_matches_discovery_roots_and_repo_pruning(tmp_citadel, monkeypatch, tmp_path):
    """The bucket comes from discovery's own walk: a junk file inside a repo source dir, or under a
    RAW_DIR outside RAW_DIRS, is not reported (discovery never walks either)."""
    repo_dir = tmp_citadel.raw / "proj"
    (repo_dir / ".git").mkdir(parents=True)
    (repo_dir / "Thumbs.db").write_bytes(b"x")
    monkeypatch.setattr(config, "REPO_SUPPORT", True)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "Thumbs.db").write_bytes(b"x")
    monkeypatch.setattr(config, "RAW_DIRS", [tmp_citadel.raw])
    monkeypatch.setattr(config, "RAW_DIR", outside)
    assert status.build_status().ignored == []


# --- the CLI entry point -------------------------------------------------------------------


def test_cli_status_exits_0_with_every_section_header(tmp_citadel, capsys):
    """``citadel status`` is read-only: it always exits 0 and prints every lifecycle section heading
    (even the empty buckets), so the table shape is stable for a script to parse."""
    (tmp_citadel.raw / "good.md").write_text("body\n", encoding="utf-8")
    _track("raw/good.md", manifest.file_sha256(tmp_citadel.raw / "good.md"), config.rules_version())
    _fail("raw/dup.pdf", failures.DUPLICATE, "same basename")
    (tmp_citadel.raw / "pending.md").write_text("later\n", encoding="utf-8")

    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "Corpus status" in out
    for heading in ("Ingested (", "Failed (", "Skipped as duplicate (", "Ignored (", "Oversized (", "Pending ("):
        assert heading in out
    assert "raw/good.md" in out and "raw/dup.pdf" in out and "raw/pending.md" in out


def test_cli_status_json_emits_machine_readable_buckets(tmp_citadel, capsys):
    """``status --json`` dumps the six buckets + rules_version as one JSON object, so a script
    gets 'which sources failed and why' without scraping the table."""
    import json

    (tmp_citadel.raw / "good.md").write_text("body\n", encoding="utf-8")
    _track("raw/good.md", manifest.file_sha256(tmp_citadel.raw / "good.md"), config.rules_version())
    _fail("raw/bad.bin", failures.UNREADABLE, "binary")
    (tmp_citadel.raw / "pending.md").write_text("later\n", encoding="utf-8")

    assert cli.main(["status", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["rules_version"] == config.rules_version()
    assert [s["key"] for s in data["ingested"]] == ["raw/good.md"]
    assert data["failed"][0]["key"] == "raw/bad.bin" and data["failed"][0]["reason"] == failures.UNREADABLE
    assert data["pending"] == ["raw/pending.md"]
    assert data["oversized"] == []


def test_cli_status_exit_code_gates_on_failed_or_pending(tmp_citadel, capsys):
    """``--exit-code`` returns 1 while anything is failed or pending (the CI gate) and 0 once the
    corpus is fully ingested; without the flag the exit stays 0 either way."""
    (tmp_citadel.raw / "pending.md").write_text("later\n", encoding="utf-8")
    assert cli.main(["status"]) == 0  # default contract unchanged
    assert cli.main(["status", "--exit-code"]) == 1

    _track("raw/pending.md", manifest.file_sha256(tmp_citadel.raw / "pending.md"), config.rules_version())
    assert cli.main(["status", "--exit-code"]) == 0
    capsys.readouterr()


def test_oversized_file_is_its_own_bucket_not_pending(tmp_citadel, monkeypatch):
    """A file past ``CITADEL_MAX_SOURCE_BYTES`` is neither pending (ingest will never pick it up)
    nor failed (nothing went wrong) — it gets its own bucket, with the size that explains it."""
    (tmp_citadel.raw / "dump.tdms").write_bytes(b"\x00" * 4096)
    (tmp_citadel.raw / "real.md").write_text("real\n", encoding="utf-8")
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", 1024)

    report = status.build_status()
    assert report.oversized == [("raw/dump.tdms", 4096)]
    assert "raw/dump.tdms" not in report.pending
    assert "raw/real.md" in report.pending
    assert "raw/dump.tdms  4.0 KB" in report.render()
    assert report.as_dict()["oversized"] == [{"key": "raw/dump.tdms", "size_bytes": 4096}]


def test_allowlist_filtered_file_is_its_own_bucket_not_pending(tmp_citadel, monkeypatch):
    """A file outside ``CITADEL_INCLUDE_PATTERNS`` is not pending (ingest will never pick it up)
    and not failed — it gets its own bucket, naming the allowlist that explains it. The bucket is
    hidden entirely when no allowlist is configured, so the default table is unchanged."""
    (tmp_citadel.raw / "sheet.xlsx").write_bytes(b"PK\x03\x04")
    (tmp_citadel.raw / "real.md").write_text("real\n", encoding="utf-8")

    assert "Not included" not in status.build_status().render()  # no allowlist -> no row at all

    monkeypatch.setattr(config, "INCLUDE_PATTERNS", ["*.md"], raising=False)
    report = status.build_status()
    assert report.not_included == ["raw/sheet.xlsx"]
    assert "raw/sheet.xlsx" not in report.pending
    assert "raw/real.md" in report.pending
    assert "Not included (1) - CITADEL_INCLUDE_PATTERNS = *.md" in report.render()
    assert report.as_dict()["not_included"] == ["raw/sheet.xlsx"]
