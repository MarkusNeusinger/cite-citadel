"""Offline tests for the agentic CLI invocation + error handling (no CLI, no network).

The old structured-output path returned a ``{"ops": [...]}`` JSON that Python parsed; that is
gone. Ingest now runs the CLI agentically and the CLI edits the wiki itself. These tests cover
how ``llm`` builds the (tiny, paths-only) prompt and per-CLI argv, and how ``_run_session``
turns a CLI failure into a ``RuntimeError`` — all by monkeypatching ``subprocess.run`` so no
real CLI is ever spawned.
"""

from __future__ import annotations

import subprocess

import pytest

from citadel import config, llm


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_build_instruction_references_paths_not_content():
    """The prompt references the rules + raw source BY PATH and never embeds content, so it
    stays tiny — the regression guard against the old WinError 206 (argv too long)."""
    prompt = llm._build_instruction("raw/notes.md")
    assert "SCHEMA.md" in prompt
    assert "AGENT_INGEST.md" in prompt
    assert "raw/notes.md" in prompt
    assert "wiki/" in prompt
    # Must never embed a large blob — paths only.
    assert len(prompt) < 3000


def test_build_instruction_uses_configured_wiki_dir(tmp_path, monkeypatch):
    """Regression for the hardcoded-'wiki/' bug: the prompt must name the CONFIGURED wiki
    directory (CITADEL_WIKI_DIR), so with CITADEL_WIKI_DIR=wikiET the agent searches and writes
    wikiET/ — otherwise it edits 'wiki/' while ingest's snapshot/diff watches wikiET/ and sees
    nothing."""
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wikiET", raising=False)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw", raising=False)

    prompt = llm._build_instruction("raw/notes.md")

    assert "wikiET/" in prompt  # the configured wiki dir is used throughout...
    assert "wiki/" not in prompt  # ...and no hardcoded bare 'wiki/' survives
    assert "raw/notes.md" in prompt  # the raw source path is still referenced verbatim
    assert len(prompt) < 3000  # still tiny (paths-only) — WinError 206 guard


def test_rule_files_teach_path_and_filename_as_routing_context():
    """A source's path within raw/ and its filename often encode the project/topic the facts
    belong to. The tiny argv prompt only POINTS the agent at the rule files (and must stay under
    the WinError-206 size guard), so — exactly like provenance and restructuring — this guidance
    lives in the rule layer the agent is told to read and follow: SCHEMA.md and AGENT_INGEST.md.
    Guard that it is not silently dropped, since the agent's awareness of path/filename as a
    routing key depends on it. Keyed on stable anchors so prose tweaks don't break the test."""
    schema = config.SCHEMA_PATH.read_text(encoding="utf-8").lower()
    rules = config.AGENT_RULES_PATH.read_text(encoding="utf-8").lower()
    for doc in (schema, rules):
        assert "routing context" in doc or "routing signal" in doc
        assert "path" in doc and "filename" in doc
        assert "project" in doc and "topic" in doc
        # specific to the new guidance: a path-derived project/topic makes a "natural tag".
        # (Plain "tag" would pass on the unrelated frontmatter-`tags` prose and guard nothing.)
        assert "natural tag" in doc
        # load-bearing guardrail: the path ROUTES facts, it is never itself a cited fact
        assert "never cite the path" in doc


def test_build_instruction_reconcile_says_update_and_remove():
    """The reconcile prompt (changed source) tells the agent to UPDATE/REMOVE stale facts, not
    just append — and still references the source by path and stays tiny."""
    prompt = llm._build_instruction("raw/notes.md", "reconcile")
    assert "raw/notes.md" in prompt
    low = prompt.lower()
    assert "changed" in low
    assert "update" in low and "remove" in low
    assert "re-ingest" in low or "reingest" in low
    # A co-cited fact must NOT be dropped whole — only this source's marker is removed unless it
    # was the last citation (mirrors the delete prompt; guards the Copilot-review fix).
    assert "co-cited" in low and "only if" in low
    assert len(prompt) < 3000  # paths + rules + a code-handling pointer, never file content (WinError 206 guard)


def test_build_instruction_office_read_path_points_to_extract_cites_original():
    """For a binary Office source, the prompt sends the agent to READ the pre-extracted text file
    while still citing the ORIGINAL source as `resource`/in `## Sources` — and stays tiny."""
    prompt = llm._build_instruction("raw/deck.pptx", "ingest", "/tmp/okf_extract_x/deck.md")
    low = prompt.lower()
    assert "/tmp/okf_extract_x/deck.md" in prompt  # the extracted-text file to read
    assert "raw/deck.pptx" in prompt  # the original source of record
    assert "resource: raw/deck.pptx" in prompt  # cite the original, not the extract
    assert "office" in low and "extracted" in low
    assert "read that" in low  # explicit: read the extracted file
    assert len(prompt) < 2000  # still paths-only — WinError 206 guard


def test_build_instruction_no_read_path_keeps_direct_read_step():
    """Without a read_path (the normal case) step 1 still tells the agent to open the source
    directly and mentions PDF — i.e. the Office branch does not leak into ordinary sources."""
    prompt = llm._build_instruction("raw/notes.md")
    assert "Open and read the raw source file: raw/notes.md" in prompt
    assert "extracted to" not in prompt.lower()


def test_build_instruction_delete_strips_provenance_without_opening():
    """The delete prompt (removed source) tells the agent NOT to open the file and to remove the
    facts/citations that depended on it; it names the path so the agent can grep for it."""
    prompt = llm._build_instruction("raw/gone.md", "delete")
    assert "raw/gone.md" in prompt
    low = prompt.lower()
    assert "delete" in low and "no longer exists" in low
    assert "do not try" in low and "open it" in low  # must not re-read a missing file
    assert "resource" in low and "[^s" in prompt  # points at both provenance forms
    assert len(prompt) < 3000


def test_build_instruction_delete_honors_configured_wiki_dir(tmp_path, monkeypatch):
    """The delete prompt names the CONFIGURED wiki dir (CITADEL_WIKI_DIR), never a hardcoded
    'wiki/', so a custom layout is searched/edited correctly."""
    monkeypatch.setattr(config, "REPO_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wikiET", raising=False)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw", raising=False)

    prompt = llm._build_instruction("raw/gone.md", "delete")
    assert "wikiET/" in prompt
    assert "wiki/" not in prompt


def test_build_invocation_claude_uses_stdin_and_acceptedits(monkeypatch):
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    argv, stdin_text = llm._build_invocation("claude", "/bin/claude", "PROMPT")
    assert "-p" in argv
    assert "--permission-mode" in argv and "acceptEdits" in argv
    assert "--allowedTools" in argv
    assert "--model" in argv and "sonnet" in argv
    # claude takes the prompt on STDIN (argv carries only flags).
    assert stdin_text == "PROMPT"
    assert "PROMPT" not in argv


def test_build_invocation_copilot_prompt_in_argv(monkeypatch):
    argv, stdin_text = llm._build_invocation("copilot", "/bin/copilot", "SHORT PROMPT")
    assert stdin_text is None
    assert "SHORT PROMPT" in argv
    assert "--allow-all-tools" in argv
    assert "--no-ask-user" in argv


def test_build_invocation_gemini_yolo():
    argv, stdin_text = llm._build_invocation("gemini", "/bin/gemini", "SHORT PROMPT")
    assert stdin_text is None
    assert "SHORT PROMPT" in argv
    assert "--approval-mode" in argv and "yolo" in argv


def test_run_session_claude_is_error_raises(monkeypatch):
    """A claude result envelope with is_error=true raises (e.g. quota/auth)."""

    def fake_run(*a, **k):
        return _FakeProc(
            returncode=0, stdout='{"type":"result","is_error":true,"api_error_status":429,"result":"quota"}'
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("claude", ["claude", "-p"], "PROMPT")
    assert "quota" in str(exc.value) or "429" in str(exc.value)


def test_run_session_claude_success(monkeypatch):
    """A clean claude envelope (is_error false, exit 0) does not raise."""

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout='{"type":"result","is_error":false,"result":"done"}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("claude", ["claude", "-p"], "PROMPT")  # no raise


def test_run_session_nonzero_exit_raises(monkeypatch):
    def fake_run(*a, **k):
        return _FakeProc(returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("copilot", ["copilot", "-p", "x"], None)
    assert "copilot" in str(exc.value)


def test_run_session_empty_output_is_success_for_copilot(monkeypatch):
    """An agentic session that legitimately changed nothing prints nothing and exits 0 —
    that must NOT be treated as a failure (this is the old 'no ops JSON' parse-bug fix)."""

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None)  # no raise
    llm._run_session("gemini", ["gemini", "-p", "x"], None)  # no raise


def test_run_session_timeout_raises(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=config.LLM_TIMEOUT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("claude", ["claude", "-p"], "PROMPT")
    assert "timed out" in str(exc.value)


def test_run_ingest_session_wires_resolve_build_run(monkeypatch):
    """run_ingest_session resolves the CLI, builds the invocation, and runs the session once."""
    calls = {"resolve": 0, "run": 0}

    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.setattr(
        llm, "_resolve_cli", lambda cli: calls.__setitem__("resolve", calls["resolve"] + 1) or "/bin/copilot"
    )

    def fake_run_session(cli, argv, stdin_text, *, log_label=None):
        calls["run"] += 1
        assert cli == "copilot"
        assert "/bin/copilot" in argv[0]
        # The session is labelled with the kind + source key so a transcript log can name it.
        assert log_label == "ingest.raw/notes.md"

    monkeypatch.setattr(llm, "_run_session", fake_run_session)
    llm.run_ingest_session("raw/notes.md")
    assert calls == {"resolve": 1, "run": 1}


def test_run_session_writes_transcript_when_log_dir_set(tmp_path, monkeypatch):
    """With CITADEL_LLM_LOG_DIR set, _run_session records the prompt + full CLI output to a transcript
    file — the visibility fix for an agent run that otherwise leaves no record of what it did."""
    monkeypatch.setattr(config, "LLM_LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout="the model said hello", stderr="a warning")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None, log_label="ingest.raw/notes.md")

    logs = list(tmp_path.glob("*.log"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "the model said hello" in text  # stdout captured
    assert "a warning" in text  # stderr captured
    assert "ingest.raw_notes.md" in logs[0].name  # label sanitized into the filename


def test_run_session_no_transcript_when_log_dir_unset(tmp_path, monkeypatch):
    """The transcript is strictly opt-in: with no log dir configured, nothing is written (the
    captured, no-log path is the unchanged default)."""
    monkeypatch.setattr(config, "LLM_LOG_DIR", "", raising=False)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout="x")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None)
    assert list(tmp_path.glob("*.log")) == []


def test_run_session_timeout_logs_partial_transcript(tmp_path, monkeypatch):
    """On a timeout, the transcript captures the PARTIAL output the TimeoutExpired carries (what the
    model produced before the kill) instead of an empty body — and notes that it timed out."""
    monkeypatch.setattr(config, "LLM_LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="copilot", timeout=config.LLM_TIMEOUT, output="partial work so far")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("copilot", ["copilot", "-p", "x"], None, log_label="ingest.raw/x.md")
    assert "timed out" in str(exc.value)

    logs = list(tmp_path.glob("*.log"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "partial work so far" in text  # the partial output is preserved, not dropped
    assert "timed out" in text  # and the transcript is annotated as a timeout


def test_run_session_verbose_uses_streaming_not_capture(monkeypatch):
    """With config.LLM_VERBOSE set, _run_session tees output via _stream_subprocess instead of the
    silent capture path — and still applies the same exit-code error detection to its result."""
    monkeypatch.setattr(config, "LLM_VERBOSE", True, raising=False)
    monkeypatch.setattr(config, "LLM_LOG_DIR", "", raising=False)

    used = {"stream": 0, "run": 0}

    def fake_stream(cli, argv, stdin_text):
        used["stream"] += 1
        return 0, "streamed transcript", ""

    def fake_run(*a, **k):  # must NOT be called in verbose mode
        used["run"] += 1
        return _FakeProc(returncode=0, stdout="")

    monkeypatch.setattr(llm, "_stream_subprocess", fake_stream)
    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None)  # no raise
    assert used == {"stream": 1, "run": 0}
