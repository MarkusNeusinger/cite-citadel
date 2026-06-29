"""Unit tests for the ingest manifest record (sha + importing model) and the model-label
resolution that feeds it. No CLI, no filesystem beyond tmp_path."""

from __future__ import annotations

import json
from pathlib import Path

from citadel import config, manifest


# --- manifest entry helpers + backward compatibility ------------------------------------


def test_make_entry_includes_model_only_when_set():
    assert manifest.make_entry("abc") == {"sha256": "abc"}
    assert manifest.make_entry("abc", "claude:sonnet") == {
        "sha256": "abc",
        "model": "claude:sonnet",
    }
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


def test_is_pending_compares_sha_for_both_forms(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path, raising=False)
    src = tmp_path / "raw" / "notes.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("hello\n", encoding="utf-8")
    sha = manifest.file_sha256(src)
    key = manifest.rel_key(src)

    assert manifest.is_pending({}, src) is True  # untracked
    assert manifest.is_pending({key: {"sha256": sha, "model": "m"}}, src) is False
    assert manifest.is_pending({key: sha}, src) is False  # legacy bare-string still matches
    assert manifest.is_pending({key: {"sha256": "other"}}, src) is True  # changed bytes


def test_mark_done_records_model_and_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(config, "MANIFEST_PATH", tmp_path / "m.json", raising=False)
    src = tmp_path / "raw" / "notes.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text("hello\n", encoding="utf-8")

    m: dict = {}
    manifest.mark_done(m, src, "claude:opus")
    key = manifest.rel_key(src)
    assert m[key] == {"sha256": manifest.file_sha256(src), "model": "claude:opus"}

    manifest.save(m)
    reread = manifest.load()
    assert reread[key]["model"] == "claude:opus"
    # save() is plain JSON the value of which is the dict record.
    on_disk = json.loads(Path(config.MANIFEST_PATH).read_text(encoding="utf-8"))
    assert on_disk[key]["sha256"] == manifest.file_sha256(src)


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
