"""The ONLY place that talks to an LLM — through a coding-agent CLI, not an API key.

Ingest shells out to a CLI (``claude``, ``copilot``, or ``gemini``) in **agentic** mode:
the CLI is pointed at the workspace (``cwd`` = the workspace root) with autonomous file tools,
reads the raw source and the existing wiki itself, and **edits the wiki page files directly**. We
pass only a short instruction that references files BY PATH — never file content — so the argv
stays tiny (this is what kills the old Windows ``WinError 206`` argv-length limit) and the
agent can handle an arbitrarily large raw file. Everything the agent must KNOW lives in the
rules tree (``citadel/rules/``, overridable per file from the workspace ``rules/``): the prompt
is only the code-invariant frame — the rules read list ``kind`` maps onto, the session variables,
and the operational invariants (see :func:`_build_instruction`).

- Pick the backend with ``CITADEL_LLM_CLI`` (``claude`` | ``copilot`` | ``gemini``; default
  ``claude``), read via ``config.LLM_CLI``.
- Override the binary path with ``CLAUDE_CODE_PATH`` / ``COPILOT_CLI_PATH`` /
  ``GEMINI_CLI_PATH``.
- The model for the ``claude`` CLI comes from ``config.INGEST_MODEL``. copilot/gemini use
  their own default model.

One function does real work: ``run_ingest_session(rel_key)`` runs the chosen CLI once against
the workspace. It has no return value — the result is whatever the agent wrote under ``wiki/``,
which ``ingest`` discovers via a filesystem diff. It raises ``RuntimeError`` on a missing/
unusable CLI, a non-zero exit, a claude ``is_error`` envelope, or a timeout (the failure
surface ``ingest``'s per-source ``try/except`` already expects).
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import config


# CLI binary resolution (env override name -> default binary name).
_CLI_PATH_ENV = {"claude": "CLAUDE_CODE_PATH", "copilot": "COPILOT_CLI_PATH", "gemini": "GEMINI_CLI_PATH"}
_CLI_DEFAULT_BIN = {"claude": "claude", "copilot": "copilot", "gemini": "gemini"}


def _resolve_cli(cli: str) -> str:
    """Return an executable path for the chosen CLI or raise a clear RuntimeError."""
    override = os.environ.get(_CLI_PATH_ENV.get(cli, ""), "").strip()
    binary = override or _CLI_DEFAULT_BIN.get(cli, cli)
    path = shutil.which(binary)
    if path:
        return path
    if os.path.isabs(binary) and os.access(binary, os.X_OK):
        return binary
    raise RuntimeError(
        f"the {cli!r} CLI was not found on PATH. Install it and log in "
        f"(for claude: run `claude` once and `/login`), or set CITADEL_LLM_CLI to a "
        f"CLI you have, or point {_CLI_PATH_ENV.get(cli, 'the path env var')} at "
        f"the binary."
    )


def _agent_path(path: Path) -> str:
    """The path string to name a configured directory (wiki/raw) in the agent prompt. The agentic
    CLI runs with ``cwd`` = ``config.WORKSPACE_ROOT``, so a directory UNDER the workspace is named relative
    to it (short, cwd-relative), while one OUTSIDE the workspace — e.g. a wiki/raw tree on a mounted
    network drive — is named by its ABSOLUTE path so the agent (granted access via ``--add-dir``)
    can find it. Honors ``CITADEL_WIKI_DIR`` / ``CITADEL_RAW_DIR`` and never collapses an
    out-of-workspace dir to a bare name (the old bug that made the agent edit a non-existent
    ``./wiki``). Single source of truth: ``config.rel_or_abs_posix``."""
    return config.rel_or_abs_posix(path)


def _external_dirs(rel_key: str, read_path: str | None = None) -> list[str]:
    """OS-native paths of the directories the agent must read/write that live OUTSIDE the
    workspace, so the CLI can be granted access to them (claude ``--add-dir``, gemini
    ``--include-directories`` — both grant RECURSIVELY, so one grant of a rules root covers its
    tasks/formats/genres subdirs; copilot needs nothing — it runs with ``--allow-all-paths``). The
    agent's ``cwd`` is the workspace root, so this returns — de-duplicated and sorted — only the
    out-of-workspace members of {wiki dir (written), raw dir, docs dir, every directory that can
    hold a referenced rules file (the packaged ``config.PACKAGED_RULES_DIR`` — under site-packages
    for a pip install, hence never inside a user workspace and ALWAYS granted there — plus the
    workspace ``rules/`` overlay, which lives under cwd and therefore filters out), the source
    file's own parent, and — for an Office source — the temp dir holding its extracted text}.
    Empty for the all-under-workspace dev-checkout layout (cwd already covers the rules), so that
    invocation is byte-for-byte unchanged."""
    candidates = [
        config.WIKI_DIR,
        config.RAW_DIR,
        config.DOCS_DIR,
        config.PACKAGED_RULES_DIR,
        config.source_path_for_key(rel_key).parent,
    ]
    ws_rules = config.workspace_rules_dir()
    if ws_rules is not None:
        candidates.append(ws_rules)
    if read_path:
        # The extracted-text file lives in a system temp dir (outside the workspace); the agent
        # must be granted access so it can read what to ingest.
        candidates.append(Path(read_path).parent)
    out: dict[str, None] = {}
    for d in candidates:
        if config.is_outside_workspace(d):
            out[str(Path(d).resolve())] = None
    return sorted(out)


# kind -> lifecycle task brief (tree-relative rules name). The EXTERNAL kind strings are the
# stable API — ingest.py, the manifest, and the tests keep them; ONLY the mapping onto rules
# files lives here. ingest/image/repo are all "fold a new source in" lifecycles (the format
# brief carries what differs); the *-reconcile kinds re-fold a changed/forced source; delete
# strips a removed source's provenance.
_TASK_FOR_KIND = {
    "ingest": "tasks/ingest.md",
    "image": "tasks/ingest.md",
    "repo": "tasks/ingest.md",
    "reconcile": "tasks/reconcile.md",
    "image-reconcile": "tasks/reconcile.md",
    "repo-reconcile": "tasks/reconcile.md",
    "delete": "tasks/delete.md",
}


def _is_pdf_source(rel_key: str) -> bool:
    """True when the source is a PDF, flagged exactly like ingest flags them — by the ``%PDF-``
    magic header (``ingest._is_ingestible`` / ``_read_source_text``) — with the ``.pdf`` suffix as
    the fallback when the file cannot be read (a vanished file, a unit test's phantom key)."""
    try:
        with open(config.source_path_for_key(rel_key), "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return rel_key.lower().endswith(".pdf")


def _format_brief(rel_key: str, kind: str, read_path: str | None, segment: tuple[int, int] | None) -> str | None:
    """The tree-relative FORMAT brief for this session, or None when no format applies. Formats
    are the structurally Python-detectable axis (repo markers, image magic, Office extraction,
    PDF magic) — code selects the brief; genres stay the agent's content judgment.

    - repo/image kinds carry their format in the kind itself.
    - ``delete`` never reads the source, so it never gets a format brief.
    - a ``read_path`` WITHOUT a segment is a pre-extracted Office source (``formats/office.md``);
      WITH a segment it is a large-source slice, covered by the task brief's Large-sources rules
      (a segmented Office source's slice already IS extracted text — no separate brief).
    - otherwise, a direct read: a PDF (magic-sniffed) reads ``formats/pdf.md``."""
    if kind in ("repo", "repo-reconcile"):
        return "formats/repo.md"
    if kind in ("image", "image-reconcile"):
        return "formats/image.md"
    if kind == "delete":
        return None
    if read_path:
        return None if segment is not None else "formats/office.md"
    if _is_pdf_source(rel_key):
        return "formats/pdf.md"
    return None


def _referenced_rules(
    rel_key: str, kind: str = "ingest", read_path: str | None = None, segment: tuple[int, int] | None = None
) -> list[Path]:
    """Every RESOLVED rules file the prompt for this session references, in read order: schema.md
    and core.md (every session), the task brief for ``kind``, the format brief when one applies,
    the effective genre briefs (agent-judged; skipped for ``delete`` — there is no source content
    to judge), and the workspace ``rules/local.md`` when present. The single source of truth the
    prompt-validation tests check against (every path must exist and be reachable)."""
    files = [
        config.effective_rules_file("schema.md"),
        config.effective_rules_file("core.md"),
        config.effective_rules_file(_TASK_FOR_KIND.get(kind, "tasks/ingest.md")),
    ]
    fmt = _format_brief(rel_key, kind, read_path, segment)
    if fmt:
        files.append(config.effective_rules_file(fmt))
    if kind != "delete":
        files.extend(config.effective_genres())
    local = config.local_rules_file()
    if local is not None:
        files.append(local)
    return files


def _build_instruction(
    rel_key: str, kind: str = "ingest", read_path: str | None = None, segment: tuple[int, int] | None = None
) -> str:
    """The short, paths-only agent prompt: ONLY the code-invariant frame. Everything the agent
    must KNOW lives in the rules tree (``citadel/rules/``, see its README) and is referenced BY
    PATH — the prompt never embeds file content, so it stays at most a couple thousand chars
    regardless of raw-file size (the WinError 206 fix). The frame is:

    1. the rules read list — schema.md + core.md (every session), the task brief ``kind`` maps to
       (:data:`_TASK_FOR_KIND`), the format brief when one applies (:func:`_format_brief`), the
       workspace ``rules/local.md`` when present, and ONE line enumerating the effective genre
       briefs for the agent to judge from the source's CONTENT (none for ``delete`` — it never
       reads the source);
    2. the session VARIABLES as bullets — the source key (verbatim), the configured wiki/raw
       directories, the prepared read path (an Office extract / segment slice / repo digest),
       the segment position, the source file's own date as the content-date fallback, the target
       wiki language (``CITADEL_WIKI_LANG``), the PDF mode (``CITADEL_PDF_MODE``, PDF sources
       only), and the style-profiling switch (``CITADEL_STYLE_PROFILES``, only when ON);
    3. the operational invariants ingest enforces mechanically: the off-limits generated files,
       and the run-``citadel check``-before-finishing gate.

    Rules are named by their RESOLVED effective locations (workspace ``rules/`` overlay >
    packaged ``citadel/rules/``), rendered through the same :func:`config.rel_or_abs_posix`
    discipline as every other path: workspace-relative in the dev checkout, ABSOLUTE
    site-packages paths for a pip install (which :func:`_external_dirs` grants to the CLI).
    ``rel_key`` is the source key (workspace-relative posix for an in-workspace source, ABSOLUTE
    posix for one on a mounted drive); every directory name is read from config at CALL time so a
    custom layout (``CITADEL_WIKI_DIR=wikiET``, a ``T:\\team-wiki\\wiki`` network path) is named
    correctly instead of a hardcoded ``wiki/``.

    The external ``kind`` strings (``ingest`` / ``reconcile`` / ``delete`` / ``repo`` /
    ``repo-reconcile`` / ``image`` / ``image-reconcile``) are the stable API; they map internally
    onto (task brief, format brief). ``read_path`` is the prepared file for a pre-extracted
    Office source, one segment's slice of a large source (with ``segment=(part, total)``), or a
    repo digest — the agent reads it for content while citing ``rel_key`` as the source of
    record (per the task/format briefs)."""
    wiki_rel = _agent_path(config.WIKI_DIR)
    raw_rel = _agent_path(config.RAW_DIR)

    def ref(path: Path) -> str:
        return config.rel_or_abs_posix(path)

    task = _TASK_FOR_KIND.get(kind, "tasks/ingest.md")
    fmt = _format_brief(rel_key, kind, read_path, segment)

    lines = [
        "You are the ingest engine for a self-structuring wiki in Google's Open Knowledge Format.",
        "Read these rules files FIRST and follow them exactly:",
        f"- Format contract: {ref(config.effective_rules_file('schema.md'))}",
        f"- How you work: {ref(config.effective_rules_file('core.md'))}",
        f"- Task brief (what THIS session does): {ref(config.effective_rules_file(task))}",
    ]
    if fmt:
        lines.append(f"- Format brief (how to read THIS source): {ref(config.effective_rules_file(fmt))}")
    local = config.local_rules_file()
    if local is not None:
        lines.append(f"- Workspace house rules: {ref(local)}")
    if kind != "delete":
        genres = config.effective_genres()
        if genres:
            lines.append(
                "Judge the source's genre from its CONTENT; if it reads like one of these, ALSO read "
                "and follow the matching file: " + ", ".join(ref(g) for g in genres) + "."
            )

    lines += ["", "Session variables (use these paths verbatim):"]
    if kind == "delete":
        lines.append(f"- Source (REMOVED from disk — do not open it): {rel_key}")
    else:
        lines.append(f"- Source (the source of record): {rel_key}")
    lines.append(f"- Wiki directory: {wiki_rel}/")
    lines.append(f"- Raw directory: {raw_rel}/")
    if read_path:
        lines.append(f"- Prepared file — read THIS for the source's content: {read_path}")
    if segment is not None:
        lines.append(f"- Segment: part {segment[0]} of {segment[1]}")
    # Fallback date for time-anchored sources: the raw file's own modification date, used only
    # when the source's CONTENT states no date (genres/meeting-minutes.md § Dates). Guarded so a
    # missing file (a delete session, a repo folder, a unit test's phantom key) yields no bullet.
    fallback_date = ""
    with contextlib.suppress(OSError):
        src = config.source_path_for_key(rel_key)
        if src.is_file():
            fallback_date = time.strftime("%Y-%m-%d", time.gmtime(src.stat().st_mtime))
    if fallback_date:
        lines.append(
            "- Fallback date — the source file's own date, used only when the source's content "
            f"states no date: {fallback_date}"
        )
    lines.append(f"- Wiki language: {config.WIKI_LANG}")
    if fmt == "formats/pdf.md":
        lines.append(f"- PDF mode: {'images' if config.PDF_MODE == 'images' else 'text'}")
    if config.STYLE_PROFILES:
        lines.append("- Style profiling: ON")

    lines += [
        "",
        f"Do what the task brief says by EDITING FILES DIRECTLY under {wiki_rel}/. "
        f"Never create or edit {wiki_rel}/index.md, {wiki_rel}/log.md, any */index.md, or any "
        f"dotfile, and make no changes outside {wiki_rel}/. Before finishing, run `citadel check` "
        "(or `uv run python -m citadel check`) and fix every reported error.",
    ]
    return "\n".join(lines)


def _build_invocation(
    cli: str, cli_path: str, prompt: str, extra_dirs: list[str] | None = None
) -> tuple[list[str], str | None]:
    """Return ``(argv, stdin_text)`` for the chosen CLI in agentic, non-interactive mode.

    Each CLI runs with autonomous file tools and ``cwd`` = the workspace root (set by
    ``_run_session``). ``extra_dirs`` are directories the agent must reach that live OUTSIDE the
    workspace (an out-of-workspace wiki/raw on a mounted network drive, and the packaged rules dir
    for a pip install — computed by :func:`_external_dirs`) — empty for the all-under-workspace
    dev-checkout layout. For **claude** the prompt goes on STDIN (argv carries only flags); for
    copilot/gemini it is a ``-p`` argument — now safe because the prompt is tiny."""
    extra_dirs = extra_dirs or []
    if cli == "claude":
        # acceptEdits auto-applies file edits; the allowlist scopes tools (Read/Edit/Write to
        # author pages, Grep/Glob to search the wiki, Bash so the agent can run `citadel check`).
        # cwd=workspace root covers everything under it; --add-dir grants access to what is not —
        # an out-of-workspace wiki/raw (network drive) and the packaged rules under site-packages —
        # since claude's file tools are otherwise scoped to cwd. No extra_dirs in the
        # all-under-workspace dev layout, so the argv is then unchanged.
        argv = [
            cli_path,
            "-p",
            "--output-format",
            "json",
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Read Edit Write Grep Glob Bash",
        ]
        for d in extra_dirs:
            argv += ["--add-dir", d]
        if config.INGEST_MODEL:
            argv += ["--model", config.INGEST_MODEL]
        return argv, prompt
    if cli == "copilot":
        # --allow-all-tools is required for non-interactive editing; --allow-all-paths lets it
        # reach the wiki/raw AND the packaged rules whether they are under cwd, on a mounted drive,
        # or in site-packages (copilot has no per-directory grant mechanism, and needs none —
        # extra_dirs is deliberately unused here); --no-ask-user keeps it autonomous; -s trims stats.
        return [cli_path, "-p", prompt, "--allow-all-tools", "--allow-all-paths", "--no-ask-user", "-s"], None
    if cli == "gemini":
        # yolo auto-approves all tool calls (auto_edit still prompts for read/search tools,
        # which would hang with no TTY). --include-directories adds the out-of-workspace dirs — a
        # wiki/raw on a mounted drive, the packaged rules under site-packages — to the agent's
        # workspace (best-effort; only when needed, so the all-under-workspace argv is unchanged).
        argv = [cli_path, "-p", prompt, "--approval-mode", "yolo"]
        if extra_dirs:
            argv += ["--include-directories", ",".join(extra_dirs)]
        return argv, None
    # Unknown CLI: a plain headless prompt as an argument (best effort).
    return [cli_path, "-p", prompt], None


def _last_result_envelope(text: str) -> dict | None:
    """Fallback for claude: the last JSONL object whose ``type`` is ``result`` (in case the
    CLI streams instead of emitting one JSON object)."""
    found: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            found = obj
    return found


# Monotonic per-process counter so concurrent/same-second transcript files never collide.
_LOG_SEQ = 0


def _decode_partial(data) -> str:
    """Normalize the partial output a ``TimeoutExpired`` carries (``output``/``stderr``) to a string:
    None -> "", str -> itself, bytes -> UTF-8 with replacement (the captured path may hand back bytes
    if it timed out before decoding). Lets the timeout transcript include what was produced so far."""
    if data is None:
        return ""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return str(data)


def _echo_stderr(text: str) -> None:
    """Write diagnostic text to stderr, swallowing a broken/closed pipe. The verbose stream and the
    transcript-path notice are diagnostic ONLY, so a closed stderr (``2>|``, a downstream consumer
    that exited) must never abort the ingest."""
    with contextlib.suppress(OSError):
        sys.stderr.write(text)
        sys.stderr.flush()


def _stream_subprocess(cli: str, argv: list[str], stdin_text: str | None) -> tuple[int, str, str]:
    """Run the CLI while TEEING its output to the terminal live (verbose mode), returning
    ``(returncode, stdout, stderr)`` exactly like the captured path so the shared error-detection
    and transcript-logging below are unchanged.

    stderr is merged into stdout so the interleaved agent transcript is shown (and captured) in the
    real order it was produced; the returned ``stderr`` is therefore always empty. The tiny prompt
    is written to stdin and stdin is closed BEFORE reading any output, so there is no classic
    pipe-buffer deadlock (the prompt is at most a couple KB, well under the pipe buffer). A
    ``threading.Timer`` enforces ``config.LLM_TIMEOUT`` even if the child hangs producing no output
    — killing it raises ``TimeoutExpired`` to match the captured path."""
    proc = subprocess.Popen(  # noqa: S603 - argv is built internally, never from user input
        argv,
        stdin=subprocess.PIPE if stdin_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        cwd=str(config.WORKSPACE_ROOT),
    )
    if stdin_text is not None and proc.stdin is not None:
        try:
            proc.stdin.write(stdin_text)
        finally:
            proc.stdin.close()

    timed_out = {"v": False}

    def _kill() -> None:
        timed_out["v"] = True
        with contextlib.suppress(OSError):
            proc.kill()

    timer = threading.Timer(config.LLM_TIMEOUT, _kill)
    timer.start()
    chunks: list[str] = []
    # All terminal echo is diagnostic — a closed/broken stderr (e.g. `2>|`, or a downstream pipe
    # consumer that exited) must never abort the ingest, so every write goes through _echo_stderr.
    _echo_stderr(f"\n--- {cli} session (live) ---\n")
    try:
        if proc.stdout is not None:
            for line in proc.stdout:
                chunks.append(line)
                # Mirror the child's output to OUR stderr (stdout stays the final report), so a
                # piped `citadel ingest > report.txt` still shows the live transcript on screen.
                _echo_stderr(line)
        proc.wait()
    finally:
        timer.cancel()
    _echo_stderr(f"--- {cli} session end (exit {proc.returncode}) ---\n")
    if timed_out["v"]:
        # Carry whatever was streamed before the kill so _run_session can log a useful PARTIAL
        # transcript for the timed-out session instead of an empty one.
        raise subprocess.TimeoutExpired(argv, config.LLM_TIMEOUT, output="".join(chunks))
    return proc.returncode, "".join(chunks), ""


def _write_transcript(
    cli: str,
    argv: list[str],
    prompt: str | None,
    returncode: int | None,
    out: str,
    err: str,
    label: str | None,
    seconds: float,
    note: str = "",
) -> None:
    """Write ONE agent session's full record to ``config.LLM_LOG_DIR`` (no-op when unset) so there
    is an after-the-fact account of what the model saw and did — the prompt, the complete
    stdout/stderr, the exit code and duration. Best-effort: a logging failure must NEVER break
    ingest, so every error is swallowed. The path is announced on stderr so the user can find it."""
    log_dir = (config.LLM_LOG_DIR or "").strip()
    if not log_dir:
        return
    try:
        global _LOG_SEQ
        _LOG_SEQ += 1
        directory = Path(log_dir)
        if not directory.is_absolute():
            directory = config.WORKSPACE_ROOT / directory
        config.robust_mkdir(directory)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if (c.isalnum() or c in "-._") else "_" for c in (label or "session"))[:80]
        path = directory / f"{stamp}.{os.getpid()}.{_LOG_SEQ}.{safe}.log"
        body = [
            "# citadel ingest — LLM agent session transcript",
            f"time:        {stamp}",
            f"cli:         {cli}",
            f"model:       {config.ingest_model_label()}",
            f"label:       {label or ''}",
            f"returncode:  {returncode}",
            f"duration_s:  {seconds:.1f}",
            f"argv:        {argv}",
        ]
        if note:
            body.append(f"note:        {note}")
        body += ["", "## PROMPT", prompt or "(none)", "", "## STDOUT", out or "(empty)"]
        if err:
            body += ["", "## STDERR", err]
        path.write_text("\n".join(body) + "\n", encoding="utf-8")
        _echo_stderr(f"LLM transcript: {path}\n")
    except OSError:
        pass  # logging is diagnostic only — never let it abort an ingest


def _run_session(cli: str, argv: list[str], stdin_text: str | None, *, log_label: str | None = None) -> None:
    """Run the agentic CLI once in ``config.WORKSPACE_ROOT``. Success = the session completed
    without error; the agent's edits are on disk. Raises ``RuntimeError`` on timeout, a
    spawn error, a non-zero exit, or (for claude) an ``is_error`` result envelope.

    Output handling is observability-aware but otherwise unchanged: when ``config.LLM_VERBOSE`` is
    set the CLI's output is TEED to the terminal live (:func:`_stream_subprocess`); otherwise it is
    captured silently exactly as before. Either way, when ``config.LLM_LOG_DIR`` is set the full
    session (prompt + stdout/stderr + exit/duration) is written to a transcript file, labelled with
    ``log_label`` (the source key + kind). Both default OFF, so the captured, no-log path — and every
    test that monkeypatches ``subprocess.run`` — is byte-for-byte the original behavior.

    Note: empty stdout is NOT a failure — an agent that legitimately changed nothing prints
    nothing and exits 0 (ingest's snapshot diff then simply shows no changes)."""
    started = time.monotonic()
    try:
        if config.LLM_VERBOSE:
            returncode, out_raw, err_raw = _stream_subprocess(cli, argv, stdin_text)
        else:
            proc = subprocess.run(
                argv,
                input=stdin_text,
                capture_output=True,
                text=True,
                # Force UTF-8 on the piped prompt and the decoded stdout/stderr regardless of the
                # OS locale (e.g. cp1252 on German Windows); errors="replace" keeps a stray
                # undecodable byte from killing the run.
                encoding="utf-8",
                errors="replace",
                timeout=config.LLM_TIMEOUT,
                cwd=str(config.WORKSPACE_ROOT),
            )
            returncode, out_raw, err_raw = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        # TimeoutExpired carries whatever was captured before the kill — subprocess.run populates
        # .output/.stderr on the captured path, and _stream_subprocess attaches its streamed chunks
        # via output= — so the timeout transcript logs the PARTIAL session, not an empty one.
        partial_out = _decode_partial(exc.output)
        partial_err = _decode_partial(exc.stderr)
        _write_transcript(
            cli,
            argv,
            stdin_text,
            None,
            partial_out,
            partial_err,
            log_label,
            time.monotonic() - started,
            note=f"timed out after {config.LLM_TIMEOUT}s",
        )
        raise RuntimeError(f"the {cli!r} CLI timed out after {config.LLM_TIMEOUT}s") from exc
    except OSError as exc:
        raise RuntimeError(f"failed to run the {cli!r} CLI: {exc}") from exc

    out = (out_raw or "").strip()
    err = (err_raw or "").strip()
    _write_transcript(
        cli, argv, stdin_text, returncode, out_raw or "", err_raw or "", log_label, time.monotonic() - started
    )

    if cli == "claude":
        # `--output-format json` returns a single result envelope:
        # {"type":"result","is_error":bool,"api_error_status":int|null,"result":str,...}.
        # We read it ONLY to detect failure; the agent's work is on disk, not in `result`.
        env: dict | None = None
        if out:
            try:
                env = json.loads(out)
            except json.JSONDecodeError:
                env = _last_result_envelope(out)
        if isinstance(env, dict) and env.get("is_error"):
            status = env.get("api_error_status")
            raise RuntimeError(
                "claude CLI error"
                + (f" ({status})" if status else "")
                + f": {env.get('result') or err or 'unknown error'}"
            )
        if returncode != 0:
            raise RuntimeError(f"the claude CLI failed (exit {returncode}): {(err or out)[:500]}")
        return

    # copilot / gemini (and any unknown CLI): the exit code is the success signal.
    if returncode != 0:
        raise RuntimeError(f"the {cli!r} CLI failed (exit {returncode}): {(err or out)[:500]}")
    return


def run_ingest_session(
    rel_key: str, kind: str = "ingest", read_path: str | None = None, segment: tuple[int, int] | None = None
) -> None:
    """Run the configured agentic CLI once to propagate the raw source ``rel_key`` into the wiki.

    ``kind`` picks the propagation (see :func:`_build_instruction`): ``"ingest"`` folds in a new
    source, ``"reconcile"`` re-ingests a CHANGED source (updating/removing its stale facts),
    ``"image"``/``"image-reconcile"`` VIEW an image source, and ``"delete"`` strips the provenance
    of a source that was REMOVED from disk.

    ``read_path`` (ingest/reconcile only) is the path to the pre-extracted text of a binary Office
    source — or, when ``segment`` is set, this segment's slice of a large source: when set, the
    agent is told to READ it for content while still citing ``rel_key``, and its directory is
    granted to the CLI alongside any out-of-workspace wiki/raw. ``segment`` is ``(part, total)`` for a
    large source split across passes.

    Side-effecting only: the agent edits files under ``config.WIKI_DIR``. Returns None;
    ``ingest`` discovers what changed via a filesystem diff. Raises ``RuntimeError`` (collected
    per-source by ingest) on a missing/failed CLI or a timeout."""
    cli = (config.LLM_CLI or "claude").strip().lower()
    cli_path = _resolve_cli(cli)
    prompt = _build_instruction(rel_key, kind, read_path, segment)
    argv, stdin_text = _build_invocation(cli, cli_path, prompt, _external_dirs(rel_key, read_path))
    _run_session(cli, argv, stdin_text, log_label=f"{kind}.{rel_key}")
