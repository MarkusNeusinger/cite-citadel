"""CITADEL_RULES_IN_SYSTEM_PROMPT (#164): schema.md + core.md delivered through claude's
``--append-system-prompt-file`` instead of as files the agent reads. Offline: every CLI is a
monkeypatched ``_run_session`` / ``--help`` fixture, nothing is spawned."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from citadel import config, doctor, ingest, llm, resume


_CLAUDE = "/bin/claude"
# What claude 2.1.x prints: the file flags appear only inside --bare's description.
_HELP_BRACKETED = (
    "--bare  Minimal mode. Explicitly provide context via: --system-prompt[-file], "
    "--append-system-prompt[-file], --add-dir\n"
    "--append-system-prompt <prompt>  Append a system prompt\n"
    "--exclude-dynamic-system-prompt-sections  Move per-machine sections into the first user message\n"
)
_HELP_TOKEN = "--append-system-prompt-file <path>\n"
_HELP_INLINE_ONLY = "--append-system-prompt <prompt>  Append a system prompt\n"


@pytest.fixture
def claude(tmp_citadel, monkeypatch):
    """claude on PATH with a configurable --help; returns the list of argv each session ran."""
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "HERMETIC", False, raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda cli: _CLAUDE)
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {_CLAUDE: _HELP_BRACKETED})
    seen: list[dict] = []

    def fake_run_session(cli, argv, stdin_text, *, log_label=None):
        entry = {"argv": list(argv), "prompt": stdin_text}
        if "--append-system-prompt-file" in argv:
            path = argv[argv.index("--append-system-prompt-file") + 1]
            entry["file"] = path
            entry["bytes"] = Path(path).read_bytes()
        seen.append(entry)
        return llm.SessionUsage(cost_usd=0.01)

    monkeypatch.setattr(llm, "_run_session", fake_run_session)
    return seen


def _set_level(monkeypatch, level: int) -> None:
    monkeypatch.setattr(config, "RULES_IN_SYSTEM_PROMPT", level, raising=False)


def _new_flags(argv: list[str], baseline: list[str]) -> list[str]:
    return [token for token in argv if token not in baseline]


# --- the knob --------------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), [("", 0), ("0", 0), ("1", 1), ("2", 2)])
def test_knob_parses_0_1_2_default_0(monkeypatch, raw, expected):
    monkeypatch.setenv("CITADEL_RULES_IN_SYSTEM_PROMPT", raw)
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    assert config._rules_in_system_prompt() == expected
    assert config.CONFIG_WARNINGS == []


@pytest.mark.parametrize("raw", ["3", "-1", "yes"])
def test_knob_rejects_anything_else_with_one_warning(monkeypatch, raw):
    monkeypatch.setenv("CITADEL_RULES_IN_SYSTEM_PROMPT", raw)
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    assert config._rules_in_system_prompt() == 0
    assert len(config.CONFIG_WARNINGS) == 1
    assert "CITADEL_RULES_IN_SYSTEM_PROMPT" in config.CONFIG_WARNINGS[0]


# --- knob 0: byte-for-byte today's behavior --------------------------------------------------


def test_knob_0_never_builds_the_file_and_adds_no_flag(claude, monkeypatch):
    _set_level(monkeypatch, 0)
    monkeypatch.setattr(llm, "_system_prompt_file", lambda: pytest.fail("built at knob 0"))
    llm.run_ingest_session("raw/notes.md")
    argv = claude[0]["argv"]
    assert "--append-system-prompt-file" not in argv
    assert "--exclude-dynamic-system-prompt-sections" not in argv
    assert claude[0]["prompt"] == llm._build_instruction("raw/notes.md")


# --- knob 1 / 2 on claude --------------------------------------------------------------------


@pytest.mark.parametrize("help_text", [_HELP_BRACKETED, _HELP_TOKEN])
def test_knob_1_delivers_schema_then_core_through_the_file(claude, monkeypatch, help_text):
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {_CLAUDE: help_text})
    _set_level(monkeypatch, 0)
    llm.run_ingest_session("raw/notes.md")
    _set_level(monkeypatch, 1)
    llm.run_ingest_session("raw/notes.md")
    base, armed = claude
    new = _new_flags(armed["argv"], base["argv"])
    assert new == ["--append-system-prompt-file", armed["file"]]
    assert armed["argv"].count("--append-system-prompt-file") == 1

    schema = config.effective_rules_file("schema.md")
    core = config.effective_rules_file("core.md")
    text = armed["bytes"].decode("utf-8")
    assert text.index(f"# Rules file: {llm._agent_path(schema)}") < text.index(f"# Rules file: {llm._agent_path(core)}")
    assert schema.read_text(encoding="utf-8") in text and core.read_text(encoding="utf-8") in text
    assert text.index(schema.read_text(encoding="utf-8")) < text.index(core.read_text(encoding="utf-8"))

    prompt = armed["prompt"].splitlines()
    assert any("ALREADY in your system prompt" in line for line in prompt)
    assert not any(line.startswith(("- Format contract:", "- How you work:")) for line in prompt)
    # Every OTHER line is the knob-0 prompt's.
    old = [
        line for line in base["prompt"].splitlines() if not line.startswith(("- Format contract:", "- How you work:"))
    ]
    assert [line for line in prompt if "ALREADY in your system prompt" not in line] == old
    # A session outside any run scope owns (and removed) its file.
    assert not os.path.exists(armed["file"])


def test_knob_2_adds_the_dynamic_sections_flag(claude, monkeypatch):
    _set_level(monkeypatch, 2)
    llm.run_ingest_session("raw/notes.md")
    argv = claude[0]["argv"]
    assert "--append-system-prompt-file" in argv
    assert argv.count("--exclude-dynamic-system-prompt-sections") == 1


def test_knob_2_falls_back_to_1_and_warns_once_per_run(claude, monkeypatch, capsys):
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {_CLAUDE: _HELP_TOKEN})
    _set_level(monkeypatch, 2)
    with llm.system_prompt_scope():
        llm.run_ingest_session("raw/notes.md")
        llm.run_ingest_session("raw/other.md")
    assert all("--append-system-prompt-file" in e["argv"] for e in claude)
    assert not any("--exclude-dynamic-system-prompt-sections" in e["argv"] for e in claude)
    assert capsys.readouterr().err.count("exclude-dynamic-system-prompt-sections") == 1


def test_probe_miss_passes_no_flag_and_warns_once_per_run(claude, monkeypatch, capsys):
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {_CLAUDE: _HELP_INLINE_ONLY})
    _set_level(monkeypatch, 1)
    with llm.system_prompt_scope():
        llm.run_ingest_session("raw/notes.md")
        llm.run_ingest_session("raw/other.md")
    for entry in claude:
        assert "--append-system-prompt-file" not in entry["argv"]
        assert "- Format contract:" in entry["prompt"]
    assert capsys.readouterr().err.count("does not advertise --append-system-prompt-file") == 1


def test_hermetic_auth_retry_keeps_the_system_prompt_flag(claude, monkeypatch):
    monkeypatch.setattr(config, "HERMETIC", True, raising=False)
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {_CLAUDE: _HELP_BRACKETED + "--bare\n"})
    _set_level(monkeypatch, 1)
    seen: list[list[str]] = []

    def fake_run_session(cli, argv, stdin_text, *, log_label=None):
        seen.append(list(argv))
        if "--bare" in argv:
            error = RuntimeError("claude CLI error: Not logged in")
            error.hermetic_auth_failure = True
            raise error
        return llm.SessionUsage(cost_usd=0.02)

    monkeypatch.setattr(llm, "_run_session", fake_run_session)
    llm.reset_hermetic_refusals()
    llm.run_ingest_session("raw/notes.md")
    assert len(seen) == 2
    assert "--bare" in seen[0] and "--bare" not in seen[1]
    assert all("--append-system-prompt-file" in argv for argv in seen)


@pytest.mark.parametrize("cli", ["copilot", "agy"])
@pytest.mark.parametrize("level", [1, 2])
def test_other_backends_ignore_the_knob(tmp_citadel, monkeypatch, cli, level):
    monkeypatch.setattr(config, "LLM_CLI", cli, raising=False)
    monkeypatch.setattr(config, "HERMETIC", False, raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda name: f"/bin/{name}")
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {f"/bin/{cli}": _HELP_BRACKETED})
    seen: list[tuple[list[str], str | None]] = []
    monkeypatch.setattr(llm, "_run_session", lambda c, argv, stdin, *, log_label=None: seen.append((list(argv), stdin)))
    _set_level(monkeypatch, 0)
    llm.run_ingest_session("raw/notes.md")
    _set_level(monkeypatch, level)
    llm.run_ingest_session("raw/notes.md")
    assert seen[0] == seen[1]


def test_workspace_ejected_schema_is_what_the_file_holds(tmp_citadel, monkeypatch):
    rules = Path(config.WORKSPACE_ROOT) / "rules"
    rules.mkdir(exist_ok=True)
    (rules / "schema.md").write_text("# my ejected schema\n", encoding="utf-8")
    monkeypatch.setattr(config, "WORKSPACE_FOUND", True, raising=False)
    text = llm._system_prompt_text()
    assert "# my ejected schema" in text
    assert f"# Rules file: {llm._agent_path(rules / 'schema.md')}" in text


# --- one file per run ------------------------------------------------------------------------


def _record_file(seen: list):
    lock = threading.Lock()

    def side_effect(*_args, **_kwargs):
        path, owned = llm._system_prompt_file()
        with lock:
            seen.append((path, owned, Path(path).read_bytes()))

    return side_effect


@pytest.mark.parametrize("jobs", [1, 2])
def test_ingest_builds_one_file_per_run_and_removes_it(tmp_citadel, fake_agent, monkeypatch, jobs):
    for name in ("a.md", "b.md", "c.md"):
        (tmp_citadel.raw / name).write_text(f"{name} body\n", encoding="utf-8")
    monkeypatch.setattr(config, "STALL_LIMIT", 0, raising=False)
    seen: list = []
    fake_agent(side_effect=_record_file(seen))
    ingest.ingest(jobs=jobs)
    assert len(seen) == 3
    assert len({path for path, _, _ in seen}) == 1
    assert len({data for _, _, data in seen}) == 1
    assert not any(owned for _, owned, _ in seen)
    path = seen[0][0]
    assert not os.path.exists(path) and not os.path.exists(os.path.dirname(path))


@pytest.mark.parametrize("error", [RuntimeError("boom"), KeyboardInterrupt()])
def test_the_file_is_removed_when_the_run_raises(tmp_citadel, monkeypatch, error):
    built: list[str] = []
    with pytest.raises(type(error)):
        with llm.system_prompt_scope():
            built.append(llm._system_prompt_file()[0])
            raise error
    assert not os.path.exists(built[0]) and not os.path.exists(os.path.dirname(built[0]))


def test_curate_shares_one_file_across_its_clusters(tmp_citadel, seed_page, fake_agent, monkeypatch):
    from citadel import curate

    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    for name in ("one", "two"):
        fm = {"type": "Concept", "title": name, "description": "d", "tags": ["t"], "resource": "raw/notes.md"}
        body = "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - s (ingested 2026-06-21)\n"
        seed_page(f"concepts/{name}.md", fm, body)
    monkeypatch.setattr(config, "CURATE_GUIDANCE", "retitle these", raising=False)
    seen: list = []
    fake_agent(side_effect=_record_file(seen))
    curate.curate(["concepts/one.md", "concepts/two.md"])
    assert len(seen) == 2 and seen[0][0] == seen[1][0] and not seen[0][1]
    assert not os.path.exists(seen[0][0])


# --- identity --------------------------------------------------------------------------------


def test_delivery_never_changes_rules_version_but_does_change_the_resume_stamp(tmp_citadel, monkeypatch):
    versions, stamps = set(), []
    for level in (0, 1, 2):
        _set_level(monkeypatch, level)
        versions.add(config.rules_version())
        stamps.append(resume.knob_stamp())
    assert len(versions) == 1
    assert stamps[0] != stamps[1] != stamps[2]


# --- doctor ----------------------------------------------------------------------------------


def test_doctor_is_silent_at_the_default(claude, monkeypatch):
    _set_level(monkeypatch, 0)
    assert doctor.check_rules_delivery() is None


def test_doctor_ok_on_a_probe_hit(claude, monkeypatch):
    _set_level(monkeypatch, 2)
    check = doctor.check_rules_delivery()
    assert check.status == doctor.OK and check.name == "rules delivery"


def test_doctor_warns_on_a_probe_miss(claude, monkeypatch):
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {_CLAUDE: _HELP_INLINE_ONLY})
    _set_level(monkeypatch, 1)
    check = doctor.check_rules_delivery()
    assert check.status == doctor.WARN and "0 in effect" in check.detail


@pytest.mark.parametrize("cli", ["copilot", "agy"])
def test_doctor_warns_claude_only_on_other_backends(tmp_citadel, monkeypatch, cli):
    monkeypatch.setattr(config, "LLM_CLI", cli, raising=False)
    _set_level(monkeypatch, 1)
    check = doctor.check_rules_delivery()
    assert check.status == doctor.WARN and "claude-only" in check.detail
