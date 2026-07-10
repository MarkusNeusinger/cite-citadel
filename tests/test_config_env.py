"""Unit tests for config's tolerant env parsing (``_int_env`` / ``_bool_env`` /
``_wiki_git_mode`` + ``CONFIG_WARNINGS``).

A malformed knob must degrade to its default with a recorded warning (surfaced by
``citadel doctor``'s config check), never crash at import or silently coerce — config is imported
before every subcommand runs, including doctor, the one tool built to diagnose exactly this
mistake. Blank means "unset" (yields the default without a warning) for EVERY knob family, so an
uncommented-but-emptied ``.env`` line can no longer silently disable a default-on feature.
"""

from __future__ import annotations

import pytest

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


# --- _bool_env -----------------------------------------------------------------------------


@pytest.mark.parametrize("default", [True, False])
def test_bool_env_missing_yields_default(monkeypatch, default):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.delenv("CITADEL_TEST_BOOL", raising=False)
    assert config._bool_env("CITADEL_TEST_BOOL", default) is default
    assert config.CONFIG_WARNINGS == []


@pytest.mark.parametrize("default", [True, False])
def test_bool_env_blank_means_unset_not_an_opt_out(monkeypatch, default):
    # The B6 fix: a bare `CITADEL_IMAGE_SUPPORT=` (uncommented-but-emptied .env line) used to
    # silently DISABLE default-on features via the "" entry in the old falsy tuples; blank now
    # means "unset" for booleans exactly as it does for every other knob family.
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_TEST_BOOL", "   ")
    assert config._bool_env("CITADEL_TEST_BOOL", default) is default
    assert config.CONFIG_WARNINGS == []


@pytest.mark.parametrize("raw", ["1", "true", "YES", " On "])
def test_bool_env_truthy_tokens(monkeypatch, raw):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_TEST_BOOL", raw)
    assert config._bool_env("CITADEL_TEST_BOOL", False) is True
    assert config.CONFIG_WARNINGS == []


@pytest.mark.parametrize("raw", ["0", "false", "NO", " Off "])
def test_bool_env_falsy_tokens(monkeypatch, raw):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_TEST_BOOL", raw)
    assert config._bool_env("CITADEL_TEST_BOOL", True) is False
    assert config.CONFIG_WARNINGS == []


@pytest.mark.parametrize("default", [True, False])
def test_bool_env_unrecognized_value_falls_back_and_warns(monkeypatch, default):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_TEST_BOOL", "banana")
    assert config._bool_env("CITADEL_TEST_BOOL", default) is default
    assert len(config.CONFIG_WARNINGS) == 1
    assert "CITADEL_TEST_BOOL" in config.CONFIG_WARNINGS[0]
    assert "banana" in config.CONFIG_WARNINGS[0]


# --- _wiki_git_mode ------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "mode"), [("0", "off"), ("off", "off"), ("1", "init"), ("init", "init")])
def test_wiki_git_recognized_tokens(monkeypatch, raw, mode):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_WIKI_GIT", raw)
    assert config._wiki_git_mode() == mode
    assert config.CONFIG_WARNINGS == []


@pytest.mark.parametrize("raw", ["", "   ", "auto", "AUTO"])
def test_wiki_git_blank_or_auto_is_auto_without_warning(monkeypatch, raw):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_WIKI_GIT", raw)
    assert config._wiki_git_mode() == "auto"
    assert config.CONFIG_WARNINGS == []


@pytest.mark.parametrize("raw", ["garbage", "of", "fasle", "disable"])
def test_wiki_git_unrecognized_value_warns_and_falls_back_to_auto(monkeypatch, raw):
    """The B7 fix: a typo of "off" used to resolve to auto with no signal anywhere, so the wiki
    kept auto-committing (and pushing). The fallback stays auto (the safe default), but doctor's
    config check now surfaces the typo via CONFIG_WARNINGS."""
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    monkeypatch.setenv("CITADEL_WIKI_GIT", raw)
    assert config._wiki_git_mode() == "auto"
    assert len(config.CONFIG_WARNINGS) == 1
    assert "CITADEL_WIKI_GIT" in config.CONFIG_WARNINGS[0]
    assert raw in config.CONFIG_WARNINGS[0]
    assert "auto" in config.CONFIG_WARNINGS[0]
