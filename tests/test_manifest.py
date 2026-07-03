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


# --- PR4 (docs/refactor-plan.md Z3): the manifest is the scan cache ----------------------


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


# --- config.ingest_model_label resolution ----------------------------------------------


def test_label_claude_uses_ingest_model(monkeypatch):
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    assert config.ingest_model_label() == "claude:sonnet"

    monkeypatch.setattr(config, "INGEST_MODEL", "", raising=False)
    assert config.ingest_model_label() == "claude"


def test_label_copilot_prefers_native_env(monkeypatch):
    """A local/Ollama copilot sets COPILOT_MODEL — that is the model that really ran, so it wins
    over CITADEL_INGEST_MODEL and the CLI default."""
    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)  # claude default, ignored
    monkeypatch.setenv("COPILOT_MODEL", "qwen3.6:27b")
    assert config.ingest_model_label() == "copilot:qwen3.6:27b"


def test_label_copilot_explicit_okf_override(monkeypatch):
    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    monkeypatch.setenv("CITADEL_INGEST_MODEL", "gpt-5.4-mini")
    monkeypatch.setattr(config, "INGEST_MODEL", "gpt-5.4-mini", raising=False)
    assert config.ingest_model_label() == "copilot:gpt-5.4-mini"


def test_label_copilot_default_is_just_cli_name(monkeypatch):
    """With no native env and only the claude-oriented default model, a copilot run is NOT
    mislabeled 'copilot:sonnet' — it records just 'copilot'."""
    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.delenv("COPILOT_MODEL", raising=False)
    monkeypatch.delenv("CITADEL_INGEST_MODEL", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    assert config.ingest_model_label() == "copilot"


def test_label_gemini_native_env(monkeypatch):
    monkeypatch.setattr(config, "LLM_CLI", "gemini", raising=False)
    monkeypatch.delenv("CITADEL_INGEST_MODEL", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-pro")
    assert config.ingest_model_label() == "gemini:gemini-2.5-pro"
