"""Unit tests for the persistent could-not-ingest record (citadel.failures)."""

from __future__ import annotations

import json

from citadel import config, failures


def _wire(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FAILURES_PATH", tmp_path / ".citadel_failures.json", raising=False)


def test_record_clear_roundtrip(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    d: dict[str, dict] = {}
    failures.record(d, "raw/a.bin", failures.UNREADABLE, "no extractable text")
    failures.record(d, "raw/b.log", failures.ERROR, "raw/b.log: boom", model="claude:sonnet")
    failures.save(d)

    on_disk = json.loads((tmp_path / ".citadel_failures.json").read_text(encoding="utf-8"))
    assert on_disk["raw/a.bin"] == {"reason": "unreadable", "detail": "no extractable text"}
    assert on_disk["raw/b.log"]["model"] == "claude:sonnet"
    assert failures.load() == on_disk

    failures.clear(d, "raw/a.bin")
    failures.clear(d, "raw/missing")  # no-op
    assert "raw/a.bin" not in d and "raw/b.log" in d


def test_save_removes_file_when_empty(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    path = tmp_path / ".citadel_failures.json"
    failures.save({"raw/a.bin": {"reason": "unreadable", "detail": "x"}})
    assert path.exists()
    failures.save({})  # empties -> file removed, so a clean wiki carries no stale sidecar
    assert not path.exists()
    assert failures.load() == {}  # missing file loads as empty


def test_reason_for_categorizes_timeout_vs_error():
    assert failures.reason_for("raw/x: agent timed out after 1200s") == failures.TIMEOUT
    assert failures.reason_for("Command TIMEOUT reached") == failures.TIMEOUT
    assert failures.reason_for("raw/x: validation failed") == failures.ERROR
    assert failures.reason_for("") == failures.ERROR


def test_load_tolerates_corrupt_file(tmp_path, monkeypatch):
    _wire(tmp_path, monkeypatch)
    (tmp_path / ".citadel_failures.json").write_text("{not json", encoding="utf-8")
    assert failures.load() == {}
