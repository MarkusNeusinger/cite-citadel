"""#158 (offline): doctor's free `agent instructions` line, the opt-in paid `--probe`, and copilot's
`--no-custom-instructions` isolation flag that never triggers the credential retry."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from citadel import cli, config, doctor, llm


def _help(monkeypatch, path: str, text: str) -> None:
    cache = dict(llm._HELP_TEXT_CACHE)
    cache[path] = text
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", cache)


def _backend(monkeypatch, cli_name: str, help_text: str, hermetic: bool = True):
    monkeypatch.setattr(config, "LLM_CLI", cli_name)
    monkeypatch.setattr(config, "HERMETIC", hermetic, raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda c: f"/bin/{c}")
    _help(monkeypatch, f"/bin/{cli_name}", help_text)


@pytest.fixture(autouse=True)
def _no_sessions(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("plain doctor must never start an agent session")

    monkeypatch.setattr(llm, "_run_session", boom)
    monkeypatch.setattr(llm, "_HERMETIC_REFUSED", set())


# --- (a) agent instructions ------------------------------------------------------------------


@pytest.mark.parametrize(
    "name", ["CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md", ".claude/rules/x.md", "AGENTS.md"]
)
def test_claude_non_hermetic_warns_for_each_instruction_file(tmp_citadel, monkeypatch, name):
    _backend(monkeypatch, "claude", "--bare", hermetic=False)
    target = tmp_citadel.root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("project rules\n", encoding="utf-8")
    check = doctor.check_agent_instructions()
    assert check.status == doctor.WARN and "NOT isolated" in check.detail


def test_a_claude_md_in_a_parent_dir_counts(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "", hermetic=True)  # no --bare advertised
    (tmp_citadel.root.parent / "CLAUDE.md").write_text("x\n", encoding="utf-8")
    try:
        assert doctor.check_agent_instructions().status == doctor.WARN
    finally:
        (tmp_citadel.root.parent / "CLAUDE.md").unlink()


def test_claude_hermetic_is_ok_with_the_probe_caveat(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "--bare", hermetic=True)
    (tmp_citadel.root / "CLAUDE.md").write_text("x\n", encoding="utf-8")
    check = doctor.check_agent_instructions()
    assert check.status == doctor.OK and "doctor --probe" in check.detail


@pytest.mark.parametrize("name", [".github/copilot-instructions.md", "AGENTS.md", "CLAUDE.md"])
def test_copilot_warns_unless_isolated(tmp_citadel, monkeypatch, name):
    target = tmp_citadel.root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x\n", encoding="utf-8")
    _backend(monkeypatch, "copilot", "", hermetic=True)
    assert doctor.check_agent_instructions().status == doctor.WARN
    _backend(monkeypatch, "copilot", "--no-custom-instructions", hermetic=False)
    assert doctor.check_agent_instructions().status == doctor.WARN
    _backend(monkeypatch, "copilot", "--no-custom-instructions", hermetic=True)
    check = doctor.check_agent_instructions()
    assert check.status == doctor.OK and "--probe" not in check.detail


def test_agy_always_warns(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "agy", "", hermetic=True)
    (tmp_citadel.root / "AGENTS.md").write_text("x\n", encoding="utf-8")
    assert doctor.check_agent_instructions().status == doctor.WARN


def test_ok_when_nothing_found_home_config_ignored_and_no_workspace(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "", hermetic=False)
    assert doctor.check_agent_instructions().status == doctor.OK
    home_cfg = tmp_citadel.root.parent / ".claude"
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_citadel.root.parent))
    home_cfg.mkdir(exist_ok=True)
    (home_cfg / "CLAUDE.md").write_text("x\n", encoding="utf-8")
    try:
        assert doctor.check_agent_instructions().status == doctor.OK
    finally:
        (home_cfg / "CLAUDE.md").unlink()
        home_cfg.rmdir()
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    assert "skipped" in doctor.check_agent_instructions().detail


def test_a_stat_that_raises_counts_as_absent(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "", hermetic=False)

    def raising(self, *a, **k):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "exists", raising)
    assert doctor.check_agent_instructions().status == doctor.OK


def test_more_than_three_files_are_elided(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "", hermetic=False)
    for name in ("CLAUDE.md", "CLAUDE.local.md", "AGENTS.md"):
        (tmp_citadel.root / name).write_text("x\n", encoding="utf-8")
    (tmp_citadel.root / ".claude").mkdir()
    (tmp_citadel.root / ".claude" / "CLAUDE.md").write_text("x\n", encoding="utf-8")
    assert "+1 more" in doctor.check_agent_instructions().detail


def test_plain_doctor_runs_no_session(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "--bare", hermetic=True)
    report = doctor.run()
    assert all(c.name != "probe" for c in report.checks)


# --- (b) --probe ------------------------------------------------------------------------------


def _fake_sessions(monkeypatch, *results):
    calls: list[dict] = []
    queue = list(results)

    def fake(cli_name, argv, stdin, *, log_label=None, cwd=None, timeout=None):
        calls.append({"argv": list(argv), "cwd": cwd, "timeout": timeout})
        assert cwd and Path(cwd).is_dir() and cwd != str(config.child_cwd())
        result = queue.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(llm, "_run_session", fake)
    return calls


def _auth_error(hermetic: bool, usage=None) -> RuntimeError:
    exc = RuntimeError("claude CLI error (401): Authentication error · please log in\nsecond line")
    exc.hermetic_auth_failure = hermetic
    exc.session_usage = usage
    return exc


def test_probe_ok_reports_served_model_and_cost(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "--bare --tools --max-budget-usd --no-session-persistence --permission-prompts")
    calls = _fake_sessions(monkeypatch, llm.SessionUsage(cost_usd=0.02, model="claude-sonnet-x"))
    result = llm.probe_session()
    assert result.status == "ok" and "hermetic (--bare)" in result.detail and "claude-sonnet-x" in result.detail
    assert "$0.02" in result.detail
    argv = calls[0]["argv"]
    assert argv[argv.index("--tools") + 1] == "" and "--max-budget-usd" in argv and "--no-session-persistence" in argv
    assert calls[0]["timeout"] <= 120 and not Path(calls[0]["cwd"]).exists()


def test_probe_caps_are_omitted_when_not_advertised(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "")
    calls = _fake_sessions(monkeypatch, None)
    llm.probe_session()
    argv = calls[0]["argv"]
    assert "--tools" not in argv and "--max-budget-usd" not in argv and "--bare" not in argv


def test_probe_warns_when_bare_strips_credentials_and_counts_the_failed_leg(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "--bare")
    _fake_sessions(monkeypatch, _auth_error(True, llm.SessionUsage(cost_usd=0.01)), llm.SessionUsage(cost_usd=0.02))
    result = llm.probe_session()
    assert result.status == "warn" and "CITADEL_HERMETIC=0" in result.detail
    assert result.usage.cost_usd == pytest.approx(0.03) and result.sessions == 2


def test_probe_fails_when_both_legs_fail_auth(tmp_citadel, monkeypatch, capsys):
    _backend(monkeypatch, "claude", "--bare")
    _fake_sessions(monkeypatch, _auth_error(True), _auth_error(False))
    result = llm.probe_session()
    assert result.status == "fail" and "not logged in" in result.detail
    assert result.detail.isascii() and "\n" not in result.detail
    monkeypatch.setattr(llm, "probe_session", lambda: result)
    assert cli.main(["doctor", "--probe"]) == 1


def test_probe_names_a_rejected_model(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "")
    monkeypatch.setattr(config, "INGEST_MODEL", "sonet-typo")
    _fake_sessions(monkeypatch, RuntimeError("model 'sonet-typo' not found"))
    result = llm.probe_session()
    assert result.status == "fail" and "CITADEL_INGEST_MODEL=sonet-typo" in result.detail


def test_probe_unlaunchable_cli_runs_no_session(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "LLM_CLI", "claude")

    def missing(cli_name):
        raise RuntimeError("claude is not installed")

    monkeypatch.setattr(llm, "_resolve_cli", missing)
    result = llm.probe_session()
    assert result.status == "fail" and result.sessions == 0


def test_probe_runs_again_for_a_differing_curate_model(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "")
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet")
    monkeypatch.setattr(config, "CURATE_MODEL", "haiku")
    calls = _fake_sessions(monkeypatch, None, None)
    checks = doctor._probe_checks()
    assert [c.name for c in checks] == ["probe", "probe (curate model)"]
    assert calls[1]["argv"][calls[1]["argv"].index("--model") + 1] == "haiku"


def test_copilot_auth_failure_is_a_login_problem_with_no_retry(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "copilot", "--no-custom-instructions")
    calls = _fake_sessions(monkeypatch, _auth_error(False))
    result = llm.probe_session()
    assert result.status == "fail" and len(calls) == 1 and "not logged in" in result.detail


def test_probe_writes_nothing_into_the_workspace(tmp_citadel, monkeypatch):
    _backend(monkeypatch, "claude", "")
    _fake_sessions(monkeypatch, None)
    before = sorted(str(p) for p in tmp_citadel.root.rglob("*"))
    llm.probe_session()
    assert sorted(str(p) for p in tmp_citadel.root.rglob("*")) == before


def test_probe_without_a_workspace_says_so(monkeypatch, tmp_path):
    _backend(monkeypatch, "claude", "")
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    monkeypatch.setattr(llm, "probe_session", lambda: llm.ProbeResult("ok", "session ran"))
    (check,) = doctor._probe_checks()
    assert "no workspace" in check.detail


# --- (d) copilot isolation ---------------------------------------------------------------------


def test_copilot_gets_its_isolation_flag_only_when_advertised(monkeypatch):
    _help(monkeypatch, "/bin/copilot", "--no-custom-instructions")
    monkeypatch.setattr(config, "HERMETIC", True, raising=False)
    assert llm._hermetic_flags("copilot", "/bin/copilot") == ["--no-custom-instructions"]
    _help(monkeypatch, "/bin/copilot", "")
    assert llm._hermetic_flags("copilot", "/bin/copilot") == []


def test_copilot_flag_never_triggers_the_auth_hint_or_retry(monkeypatch):
    assert llm._hermetic_auth_hint("copilot", ["copilot", "--no-custom-instructions"], "Authentication error") == ""
    monkeypatch.setattr(config, "LLM_CLI", "copilot")
    monkeypatch.setattr(llm, "_resolve_cli", lambda c: "/bin/copilot")
    monkeypatch.setattr(config, "HERMETIC", True, raising=False)
    _help(monkeypatch, "/bin/copilot", "--no-custom-instructions")
    launches: list = []

    def fake_run(argv, **kw):
        launches.append(argv)
        return subprocess.CompletedProcess(argv, 1, stdout="", stderr="Authentication error: not logged in")

    monkeypatch.undo()  # restore the real _run_session (the autouse fake raises)
    monkeypatch.setattr(config, "LLM_CLI", "copilot")
    monkeypatch.setattr(llm, "_resolve_cli", lambda c: "/bin/copilot")
    monkeypatch.setattr(config, "HERMETIC", True, raising=False)
    _help(monkeypatch, "/bin/copilot", "--no-custom-instructions")
    monkeypatch.setattr(llm, "_HERMETIC_REFUSED", set())
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(llm, "_build_instruction", lambda *a, **k: "p")
    with pytest.raises(RuntimeError):
        llm.run_ingest_session("raw/x.md")
    assert len(launches) == 1 and "--no-custom-instructions" in launches[0]
    assert llm._HERMETIC_REFUSED == set()
    assert os.environ is not None
