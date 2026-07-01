"""Offline tests for the agentic CLI invocation + error handling (no CLI, no network).

The old structured-output path returned a ``{"ops": [...]}`` JSON that Python parsed; that is
gone. Ingest now runs the CLI agentically and the CLI edits the wiki itself. These tests cover
how ``llm`` builds the (tiny, paths-only) prompt and per-CLI argv, and how ``_run_session``
turns a CLI failure into a ``RuntimeError`` — all by monkeypatching ``subprocess.run`` so no
real CLI is ever spawned.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from citadel import config, llm


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _rules_tokens() -> tuple[str, str]:
    """The two rules-path tokens exactly as ``_build_instruction`` renders them into the prompt
    (the same ``config.rel_or_abs_posix`` discipline as every other prompt path)."""
    return config.rel_or_abs_posix(config.SCHEMA_PATH), config.rel_or_abs_posix(config.AGENT_RULES_PATH)


def test_build_instruction_references_paths_not_content():
    """The prompt references the rules + raw source BY PATH and never embeds content, so it
    stays tiny — the regression guard against the old WinError 206 (argv too long). The rules are
    named by their RESOLVED packaged locations (config.SCHEMA_PATH / config.AGENT_RULES_PATH),
    not assumed to sit in the current directory."""
    prompt = llm._build_instruction("raw/notes.md")
    schema_token, rules_token = _rules_tokens()
    assert schema_token in prompt
    assert rules_token in prompt
    assert "raw/notes.md" in prompt
    assert "wiki/" in prompt
    # Must never embed a large blob — paths only.
    assert len(prompt) < 3000


def test_build_instruction_uses_configured_wiki_dir(tmp_path, monkeypatch):
    """Regression for the hardcoded-'wiki/' bug: the prompt must name the CONFIGURED wiki
    directory (CITADEL_WIKI_DIR), so with CITADEL_WIKI_DIR=wikiET the agent searches and writes
    wikiET/ — otherwise it edits 'wiki/' while ingest's snapshot/diff watches wikiET/ and sees
    nothing."""
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wikiET", raising=False)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw", raising=False)
    # Keep the rules tokens free of the real checkout's absolute path (which could contain 'wiki/').
    monkeypatch.setattr(config, "SCHEMA_PATH", tmp_path / "rules" / "SCHEMA.md")
    monkeypatch.setattr(config, "AGENT_RULES_PATH", tmp_path / "rules" / "AGENT_INGEST.md")

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
    assert "media/" in prompt  # points the agent at the extracted embedded images
    # Still paths-only and tiny (WinError 206 guard). The bound matches the reconcile prompt's; an
    # out-of-repo wiki/raw resolves to ABSOLUTE paths that appear several times, so allow headroom.
    assert len(prompt) < 3000


def test_build_instruction_no_read_path_keeps_direct_read_step():
    """Without a read_path (the normal case) step 1 still tells the agent to open the source
    directly and mentions PDF — i.e. the Office branch does not leak into ordinary sources."""
    prompt = llm._build_instruction("raw/notes.md")
    assert "Open and read the raw source file: raw/notes.md" in prompt
    assert "extracted to" not in prompt.lower()


def test_build_instruction_image_tells_agent_to_view_and_cite():
    """An image source: the prompt tells the agent to VIEW/read the image and transcribe its facts,
    citing the image file — no read_path (the agent opens it directly)."""
    prompt = llm._build_instruction("raw/diagram.png", "image")
    low = prompt.lower()
    assert "raw/diagram.png" in prompt
    assert "image" in low and ("view" in low or "read" in low)
    assert "cite" in low  # the agent is told to cite the transcribed facts (to the image source)
    assert "resource" in low  # step 3 still requires setting the resource verbatim
    assert "extracted to" not in low  # not the office path


def test_build_instruction_segment_says_merge_not_duplicate():
    """A later segment of a large source reads the segment file but cites the whole source, and is
    told to MERGE into the pages earlier segments created (not duplicate)."""
    prompt = llm._build_instruction("raw/big.txt", "ingest", "/tmp/okf_extract_y/big.md", (2, 3))
    low = prompt.lower()
    assert "/tmp/okf_extract_y/big.md" in prompt  # this segment's slice to read
    assert "raw/big.txt" in prompt  # cite the whole source
    assert "segment 2 of 3" in low
    assert "merg" in low and "not duplicate" in low.replace("do not duplicate", "not duplicate")


def test_build_instruction_multisegment_reconcile_does_not_blanket_delete():
    """A CHANGED source split into segments must NOT get the blanket 'remove facts the file no
    longer supports' instruction (the agent sees only one segment) — it is told update-in-place and
    explicitly NOT to delete facts it cannot see in this segment."""
    prompt = llm._build_instruction("raw/big.txt", "reconcile", "/tmp/okf_extract_z/big.md", (2, 3))
    low = prompt.lower()
    assert "changed" in low and "update" in low
    assert "do not delete facts you cannot see" in low
    # The dangerous single-segment removal directive from the normal reconcile note is absent.
    assert "the current file no longer supports" not in low


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
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wikiET", raising=False)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw", raising=False)
    monkeypatch.setattr(config, "SCHEMA_PATH", tmp_path / "rules" / "SCHEMA.md")
    monkeypatch.setattr(config, "AGENT_RULES_PATH", tmp_path / "rules" / "AGENT_INGEST.md")

    prompt = llm._build_instruction("raw/gone.md", "delete")
    assert "wikiET/" in prompt
    assert "wiki/" not in prompt


# --- packaged rules: prompt repoint + access grants (PR2, refactor-plan Z1/Z8) ------------


@pytest.fixture
def pip_like_workspace(tmp_path, monkeypatch) -> Path:
    """A workspace whose packaged rules live OUTSIDE it — the pip-install reality (the rules sit
    in site-packages, never under a user workspace). Only the workspace moves to tmp; the REAL
    packaged ``config.SCHEMA_PATH`` / ``config.AGENT_RULES_PATH`` stay in effect, so their prompt
    tokens are ABSOLUTE paths here."""
    root = tmp_path / "ws"
    for d in ("wiki", "raw", "docs"):
        (root / d).mkdir(parents=True)
    monkeypatch.setattr(config, "WORKSPACE_ROOT", root)
    monkeypatch.setattr(config, "WIKI_DIR", root / "wiki")
    monkeypatch.setattr(config, "RAW_DIR", root / "raw")
    monkeypatch.setattr(config, "DOCS_DIR", root / "docs")
    return root


# Every (kind, read_path, segment) variant _build_instruction can emit today.
_KIND_VARIANTS = [
    ("ingest", None, None),
    ("reconcile", None, None),
    ("image", None, None),
    ("image-reconcile", None, None),
    ("delete", None, None),
    ("repo", "/tmp/okf_digest_x/repo.md", None),
    ("repo-reconcile", "/tmp/okf_digest_x/repo.md", None),
    ("ingest", "/tmp/okf_extract_x/deck.md", None),  # Office extract
    ("reconcile", "/tmp/okf_extract_x/deck.md", None),
    ("ingest", "/tmp/okf_extract_x/big.md", (1, 4)),  # large-source segments
    ("ingest", "/tmp/okf_extract_x/big.md", (3, 4)),
    ("reconcile", "/tmp/okf_extract_x/big.md", (2, 4)),
]


@pytest.mark.parametrize(("kind", "read_path", "segment"), _KIND_VARIANTS)
def test_prompt_rules_paths_point_at_existing_files(kind, read_path, segment):
    """Every rules path a built prompt references resolves — through the same key math the rest
    of the system uses (config.source_path_for_key) — to an EXISTING file: the packaged
    citadel/rules/ pair the wheel ships. A prompt pointing the agent at a missing rules file
    would silently ingest without the schema."""
    prompt = llm._build_instruction("raw/notes.md", kind, read_path, segment)
    for token in _rules_tokens():
        assert token in prompt
        assert config.source_path_for_key(token).is_file()


def test_external_dirs_always_grant_out_of_workspace_rules(pip_like_workspace):
    """With the packaged rules OUTSIDE the workspace (pip install), _external_dirs must include
    the resolved rules directory so the agent's file tools — otherwise scoped to cwd — can read
    the very rules the prompt tells it to follow."""
    dirs = llm._external_dirs("raw/notes.md")
    assert str(Path(config.SCHEMA_PATH).parent.resolve()) in dirs
    assert str(Path(config.AGENT_RULES_PATH).parent.resolve()) in dirs


def test_claude_and_gemini_grant_rules_dir_copilot_needs_nothing(pip_like_workspace, monkeypatch):
    """The rules-dir grant reaches each CLI's own mechanism: claude ``--add-dir``, gemini
    ``--include-directories``. copilot has NO per-directory grant mechanism and needs none —
    it always runs with ``--allow-all-paths`` (which covers site-packages)."""
    monkeypatch.setattr(config, "INGEST_MODEL", "", raising=False)
    dirs = llm._external_dirs("raw/notes.md")
    rules_dir = str(Path(config.SCHEMA_PATH).parent.resolve())

    argv, _ = llm._build_invocation("claude", "/bin/claude", "P", dirs)
    granted = [argv[i + 1] for i, flag in enumerate(argv) if flag == "--add-dir"]
    assert rules_dir in granted

    argv, _ = llm._build_invocation("gemini", "/bin/gemini", "P", dirs)
    included = argv[argv.index("--include-directories") + 1]
    assert rules_dir in included.split(",")

    argv, _ = llm._build_invocation("copilot", "/bin/copilot", "P", dirs)
    assert "--allow-all-paths" in argv
    assert rules_dir not in argv  # extra_dirs is deliberately unused for copilot


def test_prompt_rules_paths_inside_cwd_or_granted(pip_like_workspace):
    """The Z1 invariant: every rules path a built prompt references is readable by the agent —
    either under its cwd (the workspace root) or inside a directory _external_dirs granted."""
    prompt = llm._build_instruction("raw/notes.md")
    dirs = llm._external_dirs("raw/notes.md")
    for token in _rules_tokens():
        assert token in prompt
        resolved = config.source_path_for_key(token).resolve()
        assert (not config.is_outside_repo(resolved)) or str(resolved.parent) in dirs


def test_rules_inside_workspace_need_no_grant(tmp_path, make_citadel):
    """The dev-checkout shape (rules under the workspace root): the prompt names them by their
    short workspace-relative token and the cwd already covers them, so _external_dirs stays
    empty and the all-under-workspace argv is byte-for-byte unchanged."""
    make_citadel(root=tmp_path / "repo")
    prompt = llm._build_instruction("raw/notes.md")
    schema_token, rules_token = _rules_tokens()
    assert not Path(schema_token).is_absolute() and schema_token in prompt
    assert not Path(rules_token).is_absolute() and rules_token in prompt
    assert llm._external_dirs("raw/notes.md") == []


@pytest.mark.parametrize(("kind", "read_path", "segment"), _KIND_VARIANTS)
def test_prompt_size_guard_every_kind(pip_like_workspace, kind, read_path, segment):
    """The <3000-char argv guard (WinError 206) holds for EVERY prompt variant even in the
    worst realistic case: the rules referenced by their ABSOLUTE site-packages paths."""
    prompt = llm._build_instruction("raw/notes.md", kind, read_path, segment)
    assert len(prompt) < 3000


# The FULL pre-change kind=ingest prompt, rendered VERBATIM from `git show HEAD:citadel/llm.py`'s
# literals at the PR2 base (rel_key="raw/notes.md", wiki dir "wiki", raw dir "raw", source absent
# on disk -> no mtime date hint). Recorded so the PR2 repoint provably changes NOTHING but the two
# rules-path tokens. Do not hand-edit; regenerate the same way if the prompt legitimately changes
# (that is PR3's job — gutting _build_instruction — not PR2's).
_PRE_CHANGE_INGEST_PROMPT = (
    "You are the ingest engine for a self-structuring wiki in Google's Open Knowledge Format. Read "
    "the rules in SCHEMA.md and AGENT_INGEST.md (current directory) and follow them exactly.\n"
    "\n"
    "Fold ONE raw source into the wiki by EDITING FILES DIRECTLY:\n"
    "1. Open and read the raw source file: raw/notes.md. It may be ANY text-bearing file type "
    "(markdown, plain text, code such as .py/.sql, JSON/CSV, PDF, ...) — extract its text and ingest "
    "the facts. For a PDF, also LOOK AT the pages' figures, diagrams, and charts (not just the body "
    "text) and capture what they show. For CODE/config/data, capture its PURPOSE, BEHAVIOR and the "
    "external systems it touches (which database and HOW), NOT its structure — see 'Code & structured "
    "sources' in SCHEMA.md. If it holds no usable text, make no edits.\n"
    "2. The wiki is under wiki/ (raw sources under raw/). Search and read existing pages "
    "(Grep/Glob/Read) before writing — prefer extending or merging into an existing page over "
    "creating a new one.\n"
    "3. Create/update/merge/split page files under wiki/ so every fact from raw/notes.md is captured, "
    "cited ([^sN] for raw facts / [^llmN] for model facts, defined in a trailing ## Sources section), "
    "and densely cross-linked with relative markdown links. Set frontmatter type, title, description, "
    "tags (>=1 lowercase), and resource (verbatim); do NOT set timestamp.\n"
    "3b. If raw/notes.md is a TIME-ANCHORED tracking artifact (meeting minutes, status update, "
    "open-points/action list, changelog — judged from CONTENT, not name), ALSO maintain dated `## "
    "Open Points` threads (and `## Change Log`) per the 'Threaded sources' rules in AGENT_INGEST.md: "
    "fan facts out as normal, then append a dated `[^sN]` bullet to the matching `id: op-<slug>` "
    "(never rewriting a past bullet; status is derived, not stored). Date entries from the source.\n"
    "4. Never edit wiki/index.md, wiki/log.md, any */index.md, or any dotfile. Make no changes "
    "outside wiki/.\n"
    "5. When you delete or rename a page, repoint inbound relative links to it.\n"
    "6. Before finishing, run `citadel check` (or `uv run python -m citadel check`) and fix every "
    "reported error.\n"
    "If raw/notes.md adds nothing new, make no edits and stop."
)


def test_prompt_shape_unchanged_modulo_rules_paths(pip_like_workspace):
    """PR2's 'byte-identical modulo rules paths' gate: the assembled kind=ingest prompt equals the
    recorded pre-change prompt EXCEPT for the two rules-path substitutions in the header —
    ``SCHEMA.md`` -> the resolved config.SCHEMA_PATH token and ``AGENT_INGEST.md (current
    directory)`` -> the resolved config.AGENT_RULES_PATH token (the old parenthetical LOCATED the
    files, so it travels with the path it described). Undoing exactly those two substitutions must
    reproduce the pre-change text byte for byte."""
    prompt = llm._build_instruction("raw/notes.md")
    schema_token, rules_token = _rules_tokens()
    new_fragment = f"Read the rules in {schema_token} and {rules_token} and follow them exactly."
    assert new_fragment in prompt
    restored = prompt.replace(
        new_fragment, "Read the rules in SCHEMA.md and AGENT_INGEST.md (current directory) and follow them exactly.", 1
    )
    assert restored == _PRE_CHANGE_INGEST_PROMPT


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
