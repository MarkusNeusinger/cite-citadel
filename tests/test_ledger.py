"""The append-only run ledger (#163), offline: one line per mutating run that ran a session."""

from __future__ import annotations

import json

import pytest

from citadel import config, curate, ingest, ledger, llm, manifest, refresh, server, status


def _lines() -> list[dict]:
    path = config.runs_ledger_path()
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def _write(tmp_citadel, name: str, text: str | None = None):
    # Distinct bytes per file: byte-identical sources are deduped by sha.
    (tmp_citadel.raw / name).write_text(text or f"body of {name}\n", encoding="utf-8")


def test_ingest_appends_one_line_with_the_run_totals(tmp_citadel, fake_agent, cite_page):
    _write(tmp_citadel, "good.md")
    _write(tmp_citadel, "bad.md")

    def effect(rel_key, **kw):
        if rel_key.endswith("good.md"):
            cite_page("misc/good.md", rel_key, "A fact.")
        else:
            (config.wiki_dir() / "misc").mkdir(parents=True, exist_ok=True)
            (config.wiki_dir() / "misc" / "bad.md").write_text("no frontmatter\n", encoding="utf-8")

    fake_agent(side_effect=effect, usage=llm.SessionUsage(cost_usd=0.5, input_tokens=100, output_tokens=10))
    report = ingest.ingest()
    (line,) = _lines()
    assert line["lifecycle"] == "ingest" and line["v"] == 1 and line["interrupted"] is False
    assert line["cost_usd"] == pytest.approx(report.usage.cost_usd)
    assert line["tokens_in"] == report.usage.input_tokens and line["tokens_out"] == report.usage.output_tokens
    assert line["counts"] == {
        "processed": len(report.processed),
        "sources_deleted": 0,
        "reingest_cleaned": 0,
        "errors": len(report.errors),
    }


def test_forced_rerun_overwrites_the_manifest_but_the_ledger_keeps_both(tmp_citadel, fake_agent, cite_page):
    _write(tmp_citadel, "a.md")
    fake_agent(
        side_effect=lambda rel_key, **kw: cite_page("misc/a.md", rel_key, "A fact."),
        usage=llm.SessionUsage(cost_usd=0.4),
    )
    ingest.ingest()
    ingest.ingest([str(tmp_citadel.raw / "a.md")], force=True)
    assert manifest.entry_usage(manifest.load()["raw/a.md"])["cost_usd"] == 0.4
    assert len(_lines()) == 2
    text = status.build_status().render()
    assert "Spend to date: $0.80 over 2 run(s) since" in text and "(ingest $0.80)" in text
    text.encode("ascii")


def test_curate_line_counts_applied_and_noop(tmp_citadel, seed_page, fake_agent, cite_page):
    for name in ("a", "b"):
        seed_page(
            f"concepts/{name}.md",
            {"type": "Thing", "title": name, "description": "d", "tags": ["t"], "resource": "raw/x.md"},
            "x\n",
        )
    _write(tmp_citadel, "x.md")
    calls = []

    def effect(rel_key, **kw):
        calls.append(rel_key)
        if len(calls) == 1:
            cite_page(rel_key, "raw/x.md", "Edited fact.")

    fake_agent(side_effect=effect, usage=llm.SessionUsage(cost_usd=1.0))
    report = curate.curate()
    (line,) = _lines()
    assert line["lifecycle"] == "curate"
    assert line["counts"] == {"applied": len(report.applied), "noop": len(report.noop), "failed": len(report.failed)}
    assert line["cost_usd"] == pytest.approx(report.usage.cost_usd)


def test_refresh_line_is_labelled_refresh(tmp_citadel, fake_agent, cite_page):
    _write(tmp_citadel, "a.md")
    m = manifest.load()
    m["raw/a.md"] = manifest.make_entry(manifest.file_sha256(tmp_citadel.raw / "a.md"), "claude:x", "r")
    manifest.save(m)
    fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/a.md", rel_key, "A fact."))
    refresh.refresh(limit=1)
    assert [line["lifecycle"] for line in _lines()] == ["refresh"]


def test_no_line_for_runs_that_paid_for_nothing(tmp_citadel, fake_agent, seed_page):
    fake_agent()
    ingest.ingest()  # nothing pending
    curate.curate(dry_run=True)
    refresh.refresh(limit=1, dry_run=True)
    refresh.refresh(limit=1)  # empty slice
    # A deletion nothing cites runs no session.
    m = manifest.load()
    m["raw/gone.md"] = manifest.make_entry("aa" * 32, "claude:x", "r")
    manifest.save(m)
    ingest.ingest()
    assert _lines() == []


def test_interrupt_records_the_completed_sources_once(tmp_citadel, fake_agent, cite_page):
    _write(tmp_citadel, "a.md")
    _write(tmp_citadel, "b.md")

    def effect(rel_key, **kw):
        if rel_key.endswith("b.md"):
            raise KeyboardInterrupt
        cite_page("misc/a.md", rel_key, "A fact.")

    fake_agent(side_effect=effect, usage=llm.SessionUsage(cost_usd=0.3))
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest()
    (line,) = _lines()
    assert line["interrupted"] is True and line["cost_usd"] == 0.3


def test_an_exception_after_the_in_run_write_leaves_exactly_one_line(tmp_citadel, fake_agent, cite_page, monkeypatch):
    from citadel import store

    _write(tmp_citadel, "a.md")
    fake_agent(
        side_effect=lambda rel_key, **kw: cite_page("misc/a.md", rel_key, "A fact."),
        usage=llm.SessionUsage(cost_usd=0.2),
    )

    def boom():
        raise RuntimeError("index rebuild failed")

    monkeypatch.setattr(store, "rebuild_indexes", boom)
    with pytest.raises(RuntimeError):
        ingest.ingest()
    assert len(_lines()) == 1


def test_a_failed_ledger_write_is_a_note_never_a_failure(tmp_citadel, fake_agent, cite_page, monkeypatch):
    _write(tmp_citadel, "a.md")
    fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/a.md", rel_key, "A fact."))

    def boom(*a, **k):
        raise OSError("disk full")

    real = config.atomic_write_text

    def guarded(path, text):
        if str(path).endswith(".citadel_runs.jsonl"):
            boom()
        return real(path, text)

    monkeypatch.setattr(config, "atomic_write_text", guarded)
    report = ingest.ingest()
    assert not report.errors and "raw/a.md" in manifest.load()
    assert "run ledger: not written" in report.render()


def test_the_ledger_never_carries_paths_or_guidance(tmp_citadel, fake_agent, cite_page, monkeypatch):
    _write(tmp_citadel, "secret-salary-review.md")
    monkeypatch.setattr(config, "INGEST_GUIDANCE", "very private steer text")
    fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/salary.md", rel_key, "A fact."))
    ingest.ingest()
    raw = config.runs_ledger_path().read_text(encoding="utf-8")
    assert "secret-salary-review" not in raw and "very private steer" not in raw and "misc/salary" not in raw
    assert json.loads(raw)["flags"]["guided"] is True


def test_load_skips_malformed_lines(tmp_citadel):
    good = {"v": 1, "lifecycle": "ingest", "started": "2026-01-01T00:00:00Z", "cost_usd": 1.0}
    lines = [
        json.dumps(good),
        '{"v": 1, "lifecycle": "ingest", "started": "2026',
        json.dumps({**good, "cost_usd": float("nan")}).replace("NaN", "NaN"),
        json.dumps({**good, "cost_usd": "1.0"}),
        json.dumps({**good, "tokens_in": -5}),
        json.dumps({**good, "v": 99}),
    ]
    config.runs_ledger_path().write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert ledger.load() == [good]
    status.build_status().render()


def test_status_without_a_ledger_and_json_shape(tmp_citadel):
    report = status.build_status()
    assert "Spend to date: not recorded yet" in report.render()
    data = report.as_dict()
    assert data["spend"] is None and "cost_usd_total" in data
    assert server.wiki_status() == report.render()


def test_a_session_writing_a_ledger_into_staging_does_not_reach_live(tmp_citadel, fake_agent, cite_page):
    _write(tmp_citadel, "a.md")

    def effect(rel_key, **kw):
        cite_page("misc/a.md", rel_key, "A fact.")
        (config.wiki_dir() / ".citadel_runs.jsonl").write_text('{"forged": true}\n', encoding="utf-8")

    fake_agent(side_effect=effect)
    ingest.ingest()
    assert all("forged" not in line for line in _lines())
    assert len(_lines()) == 1


def test_a_non_utf8_ledger_is_left_alone_with_a_note(tmp_citadel):
    path = config.runs_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    good = json.dumps({"v": ledger.VERSION, "lifecycle": "ingest", "started": "2026-01-01T00:00:00Z"})
    raw = b"\xff\xfe junk\n" + good.encode("ascii") + b"\n"
    path.write_bytes(raw)
    note = ledger.append({"v": ledger.VERSION, "lifecycle": "ingest", "started": "2026-02-01T00:00:00Z"})
    assert "not written" in note and "UTF-8" in note
    assert path.read_bytes() == raw  # untouched
    assert [r["started"] for r in ledger.load()] == ["2026-01-01T00:00:00Z"]  # load survives too
