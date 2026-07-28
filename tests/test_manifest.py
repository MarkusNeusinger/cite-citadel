"""Unit tests for the ingest manifest record (sha + importing model) and the model-label
resolution that feeds it. No CLI, no filesystem beyond tmp_path."""

from __future__ import annotations

import json

from citadel import config, manifest


# --- manifest entry helpers + backward compatibility ------------------------------------


def test_make_entry_includes_model_only_when_set():
    assert manifest.make_entry("abc") == {"sha256": "abc"}
    assert manifest.make_entry("abc", "claude:sonnet") == {"sha256": "abc", "model": "claude:sonnet"}
    # An empty/None model is omitted (a source no model imported records just its sha).
    assert manifest.make_entry("abc", "") == {"sha256": "abc"}
    assert manifest.make_entry("abc", None) == {"sha256": "abc"}


def test_entry_sha_and_model_accept_record_and_legacy_string():
    record = {"sha256": "deadbeef", "model": "copilot:qwen3.6:27b"}
    assert manifest.entry_sha(record) == "deadbeef"
    assert manifest.entry_model(record) == "copilot:qwen3.6:27b"

    # Legacy manifests stored a bare sha STRING — still read, with no model.
    assert manifest.entry_sha("deadbeef") == "deadbeef"
    assert manifest.entry_model("deadbeef") is None

    # A record with no model -> None.
    assert manifest.entry_model({"sha256": "x"}) is None


def test_model_of_lookups():
    m = {
        "raw/a.md": {"sha256": "h1", "model": "claude:sonnet"},
        "raw/b.md": "h2",  # legacy
    }
    assert manifest.model_of(m, "raw/a.md") == "claude:sonnet"
    assert manifest.model_of(m, "raw/b.md") is None  # legacy entry: unknown
    assert manifest.model_of(m, "raw/missing.md") is None


def test_mark_done_records_model_and_roundtrips(tmp_citadel):
    src = tmp_citadel.raw / "notes.md"
    src.write_text("hello\n", encoding="utf-8")

    m: dict = {}
    manifest.mark_done(m, src, "claude:opus")
    key = manifest.rel_key(src)
    assert m[key]["sha256"] == manifest.file_sha256(src)
    assert m[key]["model"] == "claude:opus"

    manifest.save(m)
    reread = manifest.load()
    assert reread[key]["model"] == "claude:opus"
    # save() writes the stamped format: the record sits under the top-level "sources" section.
    on_disk = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))["sources"]
    assert on_disk[key]["sha256"] == manifest.file_sha256(src)


# --- PR4: the manifest is the scan cache ----------------------


def test_mark_done_records_scan_cache_stat_fields(tmp_citadel):
    """``mark_done`` records the source's (size, mtime_ns) as the quick-check skip hint plus
    ``hashed_at_ns`` — the SOURCE file's clock at hash time, feeding the racy-timestamp guard —
    alongside sha/model/rules_version, and ``save``/``load`` round-trips the entry. mtime_ns is
    an opaque equality token: stored exactly as stat reports it, never truncated or ordered."""
    src = tmp_citadel.raw / "notes.md"
    src.write_text("hello\n", encoding="utf-8")

    m: dict = {}
    manifest.mark_done(m, src, "claude:opus", "rules123")
    st = src.stat()
    entry = m[manifest.rel_key(src)]
    assert entry["sha256"] == manifest.file_sha256(src)
    assert entry["model"] == "claude:opus"
    assert entry["size"] == st.st_size
    assert entry["mtime_ns"] == st.st_mtime_ns
    assert isinstance(entry["hashed_at_ns"], int)

    manifest.save(m)
    assert manifest.load()[manifest.rel_key(src)] == entry


def test_entry_helpers_accept_stat_extended_records():
    """The entry helpers keep working on a stat-extended record (forward compatibility: a PR4
    manifest read by code that only knows sha/model must not choke on the extra fields)."""
    record = {"sha256": "abc", "model": "m", "rules_version": "r", "size": 6, "mtime_ns": 1, "hashed_at_ns": 2}
    assert manifest.entry_sha(record) == "abc"
    assert manifest.entry_model(record) == "m"
    assert manifest.entry_rules_version(record) == "r"
    assert not manifest.is_repo_entry(record)


# --- config.ingest_model_label / model_label_for resolution ----------------------------


def test_label_claude_uses_ingest_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    assert config.ingest_model_label() == "claude:sonnet"

    monkeypatch.setattr(config, "INGEST_MODEL", "", raising=False)
    assert config.ingest_model_label() == "claude"


def test_label_is_backend_agnostic(monkeypatch):
    """Every backend honors --model, so the configured knob labels them all the same way — no
    per-backend guessing from COPILOT_MODEL/GEMINI_MODEL any more."""
    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "claude-sonnet-4.5", raising=False)
    assert config.ingest_model_label() == "copilot:claude-sonnet-4.5"

    monkeypatch.setattr(config, "LLM_CLI", "agy", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "gemini-3.1-pro-high", raising=False)
    assert config.ingest_model_label() == "agy:gemini-3.1-pro-high"


def test_label_unset_model_is_just_the_cli_name(monkeypatch):
    """No configured model = "the CLI's own default": the label must not invent one."""
    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "", raising=False)
    assert config.ingest_model_label() == "copilot"


def test_model_label_for_prefers_the_reported_model(monkeypatch):
    """What the backend SAYS it ran beats what we asked for — the whole point of reading the
    session envelope. The CLI prefix is kept, so the manifest still names the backend."""
    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "auto", raising=False)
    assert config.model_label_for("claude-sonnet-4.5") == "copilot:claude-sonnet-4.5"


def test_model_label_for_falls_back_when_nothing_was_reported(monkeypatch):
    monkeypatch.setattr(config, "LLM_CLI", "agy", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "gemini-3.1-pro-high", raising=False)
    for reported in (None, "", "   "):
        assert config.model_label_for(reported) == "agy:gemini-3.1-pro-high"
