"""Visibility + one-command retry for stuck sources (offline).

Two ways a source can silently contribute nothing to the wiki:

- it FAILED (errored / timed-out / unreadable) — persisted in the failures catalog, retried on
  the next run;
- it "succeeded" with ZERO page changes — marked done in the manifest, so without help it is
  never revisited and no wiki page ever cites it.

These tests pin the visibility layer (``IngestReport.no_pages`` + its WARNING section, the
``NO PAGES`` marker and retry hint in ``citadel status``) and the retry lane
(``ingest.retry_candidates()`` + ``citadel ingest --retry``). Everything runs on ``tmp_citadel``
with the shared ``fake_agent``/``seed_page`` fixtures; no CLI, no network.
"""

from __future__ import annotations

import pytest

from citadel import cli, config, failures, ingest, manifest, status


def _track(key: str, sha: str) -> None:
    """Record one ingested manifest entry for ``key`` (load-modify-save)."""
    tracked = manifest.load()
    tracked[key] = manifest.make_entry(sha, "claude:sonnet", config.rules_version())
    manifest.save(tracked)


def _fail(key: str, reason: str, detail: str = "") -> None:
    """Record one failures-catalog entry for ``key`` (load-modify-save)."""
    stuck = failures.load()
    failures.record(stuck, key, reason, detail)
    failures.save(stuck)


def _cited_source(cit, seed_page, name: str = "cited") -> str:
    """A raw source on disk, tracked in the manifest, WITH a wiki page whose ``resource``
    frontmatter cites it — the healthy baseline the uncited detection must not flag."""
    key = f"raw/{name}.md"
    src = cit.raw / f"{name}.md"
    src.write_text("body\n", encoding="utf-8")
    _track(key, manifest.file_sha256(src))
    seed_page(
        f"concepts/{name}.md",
        {"type": "Concept", "title": name, "description": "d", "tags": ["t"], "resource": key},
        f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{key}](../../{key}) - src\n",
    )
    return key


# --- the run report: IngestReport.no_pages -------------------------------------------------


def test_fresh_ingest_with_no_page_changes_is_flagged(tmp_citadel, fake_agent):
    """A brand-new source whose session changes NOTHING lands on ``report.no_pages`` and the
    report renders a WARNING with the retry hint — it is marked done, so this warning is the
    only trace that the source contributed zero entries."""
    (tmp_citadel.raw / "notes.md").write_text("nothing came of this\n", encoding="utf-8")
    fake_agent()  # a successful session that writes no pages

    report = ingest.ingest()
    assert report.no_pages == ["raw/notes.md"]
    assert "raw/notes.md" in report.processed  # still marked done — the point of the warning
    text = report.render()
    assert "produced NO wiki changes" in text
    assert "citadel ingest --retry" in text
    # The permanent trace survives the console: log.md records the zero-page verdict.
    assert "produced no wiki changes" in tmp_citadel.log_path.read_text(encoding="utf-8")


def test_reconcile_with_no_changes_is_not_flagged(tmp_citadel, fake_agent, transformer_page):
    """A RECONCILE (changed bytes of an already-tracked source) that decides nothing needs to
    change is a legitimate verdict — never flagged (else ``citadel refresh`` would warn on its
    whole slice)."""
    (tmp_citadel.raw / "notes.md").write_text("v1\n", encoding="utf-8")
    fake_agent(transformer_page)
    assert ingest.ingest().no_pages == []  # created a page: nothing to flag

    (tmp_citadel.raw / "notes.md").write_text("v2 (changed)\n", encoding="utf-8")
    agent = fake_agent()  # reconcile session: writes nothing
    report = ingest.ingest()
    assert agent.calls == [("raw/notes.md", "reconcile")]
    assert report.no_pages == []


def test_error_report_renders_retry_hint():
    """The Errors section points at the retry lane, so a failed run tells the reader how to try
    again instead of leaving the failure to scroll away."""
    report = ingest.IngestReport(processed=[], skipped=[], pages_written=[], errors=["raw/x.md: boom"])
    assert "citadel ingest --retry" in report.render()


# --- retry_candidates(): the computed retry set --------------------------------------------


def test_retry_candidates_failed_and_uncited_buckets(tmp_citadel, seed_page):
    """``retry_candidates()`` = (failed sources still on disk, ingested sources no page cites).
    Excluded: a vanished failure (nothing left to read), a deliberate ``duplicate`` skip, a
    curate record (a page, not a source), and every cited healthy source."""
    (tmp_citadel.raw / "bad.md").write_text("errored last run\n", encoding="utf-8")
    _fail("raw/bad.md", failures.ERROR, "agent session failed")
    _fail("raw/gone.md", failures.ERROR, "vanished since")  # no file on disk
    (tmp_citadel.raw / "dup.pdf").write_bytes(b"%PDF-fake")
    _fail("raw/dup.pdf", failures.DUPLICATE, "same basename as raw/dup.pptx")
    _fail("concepts/topic.md", failures.CURATE, "cluster failed")
    _cited_source(tmp_citadel, seed_page, "cited")
    (tmp_citadel.raw / "empty.md").write_text("ingested to zero entries\n", encoding="utf-8")
    _track("raw/empty.md", manifest.file_sha256(tmp_citadel.raw / "empty.md"))

    failed, uncited = ingest.retry_candidates()
    assert failed == ["raw/bad.md"]
    assert uncited == ["raw/empty.md"]


def test_retry_candidates_empty_when_healthy(tmp_citadel, seed_page):
    """A corpus with no failures and every source cited has nothing to retry."""
    _cited_source(tmp_citadel, seed_page)
    assert ingest.retry_candidates() == ([], [])


# --- citadel ingest --retry ----------------------------------------------------------------


@pytest.mark.parametrize("argv", [["raw/x.md"], ["--force"], ["--force", "raw/x.md"]])
def test_cli_retry_refuses_paths_and_force(tmp_citadel, capsys, argv):
    """``--retry`` computes its own set: explicit paths or ``--force`` alongside it are a usage
    error (exit 2), before ``ingest.ingest`` is ever reached."""
    assert cli.main(["ingest", "--quiet", "--retry", *argv]) == 2
    assert "--retry" in capsys.readouterr().err


def test_cli_retry_with_nothing_stuck_is_a_clean_noop(tmp_citadel, capsys, monkeypatch):
    """No failed and no uncited sources: ``--retry`` says so and exits 0 without a run."""

    def never(*a, **k):  # pragma: no cover - the assertion is that this is never reached
        raise AssertionError("ingest.ingest must not run when there is nothing to retry")

    monkeypatch.setattr(ingest, "ingest", never)
    assert cli.main(["ingest", "--quiet", "--retry"]) == 0
    assert "Nothing to retry" in capsys.readouterr().out


def test_cli_retry_runs_computed_set_as_forced_read(tmp_citadel, seed_page, capsys, monkeypatch):
    """``--retry`` prints the retry set and hands exactly those paths to ``ingest.ingest`` with
    ``force=True`` — the failed source re-runs, the uncited one re-reads as a forced reconcile."""
    (tmp_citadel.raw / "bad.md").write_text("errored last run\n", encoding="utf-8")
    _fail("raw/bad.md", failures.ERROR, "agent session failed")
    (tmp_citadel.raw / "empty.md").write_text("ingested to zero entries\n", encoding="utf-8")
    _track("raw/empty.md", manifest.file_sha256(tmp_citadel.raw / "empty.md"))
    _cited_source(tmp_citadel, seed_page, "cited")  # healthy: must NOT be re-read

    captured: dict = {}

    def spy(paths=None, progress=None, **kwargs):
        captured["paths"] = paths
        captured["kwargs"] = kwargs
        return ingest.IngestReport(processed=[], skipped=[], pages_written=[], errors=[])

    monkeypatch.setattr(ingest, "ingest", spy)
    assert cli.main(["ingest", "--quiet", "--retry"]) == 0
    expected = [str(config.source_path_for_key(k)) for k in ("raw/bad.md", "raw/empty.md")]
    assert captured["paths"] == expected
    assert captured["kwargs"]["force"] is True
    out = capsys.readouterr().out
    assert "Retrying 1 failed source(s)" in out
    assert "Force-reconciling 1 ingested source(s)" in out


def test_cli_retry_end_to_end_clears_the_stuck_source(tmp_citadel, fake_agent, transformer_page):
    """The whole lane, no spies: a fresh ingest flags the zero-page source, ``--retry`` re-runs
    it as a forced reconcile, and once the session produces a citing page the source stops being
    a candidate."""
    (tmp_citadel.raw / "notes.md").write_text("worth a page\n", encoding="utf-8")
    fake_agent()  # first pass under-delivers: no pages
    assert ingest.ingest().no_pages == ["raw/notes.md"]
    assert ingest.retry_candidates() == ([], ["raw/notes.md"])

    agent = fake_agent(transformer_page)  # the retry writes the page
    assert cli.main(["ingest", "--quiet", "--retry"]) == 0
    assert agent.calls == [("raw/notes.md", "reconcile")]
    assert ingest.retry_candidates() == ([], [])


# --- citadel status: the NO PAGES marker ---------------------------------------------------


def test_status_marks_uncited_sources(tmp_citadel, seed_page):
    """An ingested source no wiki page cites carries ``uncited`` (rendered as ``NO PAGES`` with
    the retry hint, explicit in ``--json``); a cited one does not."""
    _cited_source(tmp_citadel, seed_page, "cited")
    (tmp_citadel.raw / "empty.md").write_text("zero entries\n", encoding="utf-8")
    _track("raw/empty.md", manifest.file_sha256(tmp_citadel.raw / "empty.md"))

    report = status.build_status()
    by_key = {s.key: s for s in report.ingested}
    assert by_key["raw/empty.md"].uncited is True
    assert by_key["raw/cited.md"].uncited is False

    text = report.render()
    empty_line = next(line for line in text.splitlines() if "raw/empty.md" in line)
    cited_line = next(line for line in text.splitlines() if "raw/cited.md" in line)
    assert "NO PAGES" in empty_line and "NO PAGES" not in cited_line
    assert "citadel ingest --retry" in text

    rows = {r["key"]: r for r in report.as_dict()["ingested"]}
    assert rows["raw/empty.md"]["uncited"] is True and rows["raw/cited.md"]["uncited"] is False


def test_status_healthy_corpus_has_no_retry_hint(tmp_citadel, seed_page):
    """Nothing failed and everything cited: no marker, no hint — the table stays quiet."""
    _cited_source(tmp_citadel, seed_page)
    text = status.build_status().render()
    assert "NO PAGES" not in text
    assert "citadel ingest --retry" not in text


def test_status_failed_sources_alone_trigger_the_hint(tmp_citadel):
    """The retry hint also rides on failures alone (the catalog's sources are retryable too)."""
    _fail("raw/bad.md", failures.ERROR, "agent session failed")
    text = status.build_status().render()
    assert "1 failed source(s)" in text
    assert "citadel ingest --retry" in text
