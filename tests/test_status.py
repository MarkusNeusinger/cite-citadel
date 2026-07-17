"""``citadel status`` bucket classification (offline): every lifecycle bucket the per-source state
table renders — the ``(stale)`` rules marker, a DUPLICATE failure routed to *skipped* (not failed), a
CURATE record excluded (it is a page, not a source), an untracked raw file surfacing as *pending*, and
an OS/junk file matched by ``CITADEL_IGNORE_PATTERNS`` shown as *ignored* — plus the ``cli.main`` entry
point. Everything reads the manifest + failures catalog + one stat-only walk over a ``tmp_citadel``
layout; no CLI, no network.
"""

from __future__ import annotations

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
    for heading in ("Ingested (", "Failed (", "Skipped as duplicate (", "Ignored (", "Pending ("):
        assert heading in out
    assert "raw/good.md" in out and "raw/dup.pdf" in out and "raw/pending.md" in out

def test_cli_status_json_emits_machine_readable_buckets(tmp_citadel, capsys):
    """``status --json`` dumps the five buckets + rules_version as one JSON object, so a script
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


def test_cli_status_exit_code_gates_on_failed_or_pending(tmp_citadel, capsys):
    """``--exit-code`` returns 1 while anything is failed or pending (the CI gate) and 0 once the
    corpus is fully ingested; without the flag the exit stays 0 either way."""
    (tmp_citadel.raw / "pending.md").write_text("later\n", encoding="utf-8")
    assert cli.main(["status"]) == 0  # default contract unchanged
    assert cli.main(["status", "--exit-code"]) == 1

    _track("raw/pending.md", manifest.file_sha256(tmp_citadel.raw / "pending.md"), config.rules_version())
    assert cli.main(["status", "--exit-code"]) == 0
    capsys.readouterr()
