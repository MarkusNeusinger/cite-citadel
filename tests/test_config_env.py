"""Unit tests for config's tolerant env parsing (``_int_env`` + ``CONFIG_WARNINGS``).

A malformed numeric knob must degrade to its default with a recorded warning (surfaced by
``citadel doctor``'s config check), never crash at import — config is imported before every
subcommand runs, including doctor, the one tool built to diagnose exactly this mistake.
"""

from __future__ import annotations

from citadel import config


def test_int_env_missing_yields_default(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.delenv("CITADEL_TEST_INT", raising=False)
    assert config._int_env("CITADEL_TEST_INT", 42) == 42
    assert config.CONFIG_WARNINGS == []


def test_int_env_blank_means_unset_not_a_mistake(monkeypatch):
    # An uncommented-but-emptied .env line (`CITADEL_LLM_TIMEOUT=`) is a realistic edit: it means
    # "unset", so it yields the default without a warning — and must never crash.
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_TEST_INT", "   ")
    assert config._int_env("CITADEL_TEST_INT", 42) == 42
    assert config.CONFIG_WARNINGS == []


def test_int_env_valid_value_parses(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_TEST_INT", " 250 ")
    assert config._int_env("CITADEL_TEST_INT", 42) == 250
    assert config.CONFIG_WARNINGS == []


def test_int_env_malformed_value_falls_back_and_warns(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_TEST_INT", "300k")
    assert config._int_env("CITADEL_TEST_INT", 42) == 42
    assert len(config.CONFIG_WARNINGS) == 1
    assert "CITADEL_TEST_INT" in config.CONFIG_WARNINGS[0]
    assert "300k" in config.CONFIG_WARNINGS[0]
    assert "42" in config.CONFIG_WARNINGS[0]
