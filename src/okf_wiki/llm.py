"""The ONLY place that talks to an LLM — through a coding-agent CLI, not an API key.

Ingest shells out to a CLI (``claude``, ``copilot``, or ``gemini``) in **agentic** mode:
the CLI is pointed at the repo (``cwd`` = repo root) with autonomous file tools, reads the
raw source and the existing wiki itself, and **edits the wiki page files directly**. We pass
only a short instruction that references files BY PATH — never file content — so the argv
stays tiny (this is what kills the old Windows ``WinError 206`` argv-length limit) and the
agent can handle an arbitrarily large raw file.

- Pick the backend with ``OKF_LLM_CLI`` (``claude`` | ``copilot`` | ``gemini``; default
  ``claude``), read via ``config.LLM_CLI``.
- Override the binary path with ``CLAUDE_CODE_PATH`` / ``COPILOT_CLI_PATH`` /
  ``GEMINI_CLI_PATH``.
- The model for the ``claude`` CLI comes from ``config.INGEST_MODEL``. copilot/gemini use
  their own default model.

One function does real work: ``run_ingest_session(rel_key)`` runs the chosen CLI once against
the repo. It has no return value — the result is whatever the agent wrote under ``wiki/``,
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
_CLI_PATH_ENV = {
    "claude": "CLAUDE_CODE_PATH",
    "copilot": "COPILOT_CLI_PATH",
    "gemini": "GEMINI_CLI_PATH",
}
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
        f"(for claude: run `claude` once and `/login`), or set OKF_LLM_CLI to a "
        f"CLI you have, or point {_CLI_PATH_ENV.get(cli, 'the path env var')} at "
        f"the binary."
    )


def _agent_path(path: Path) -> str:
    """The path string to name a configured directory (wiki/raw) in the agent prompt. The agentic
    CLI runs with ``cwd`` = ``config.REPO_ROOT``, so a directory UNDER the repo is named relative
    to it (short, cwd-relative), while one OUTSIDE the repo — e.g. a wiki/raw tree on a mounted
    network drive — is named by its ABSOLUTE path so the agent (granted access via ``--add-dir``)
    can find it. Honors ``OKF_WIKI_DIR`` / ``OKF_RAW_DIR`` and never collapses an out-of-repo dir
    to a bare name (the old bug that made the agent edit a non-existent ``./wiki``). Single source
    of truth: ``config.rel_or_abs_posix``."""
    return config.rel_or_abs_posix(path)


def _external_dirs(rel_key: str, read_path: str | None = None) -> list[str]:
    """OS-native paths of the directories the agent must read/write that live OUTSIDE the repo, so
    the CLI can be granted access to them. The agent's ``cwd`` is the repo root (which already
    covers SCHEMA.md / AGENT_INGEST.md / the ``okf-wiki`` command), so this returns — de-duplicated
    and sorted — only the out-of-repo members of {wiki dir (written), raw dir, docs dir, the source
    file's own parent, and — for an Office source — the temp dir holding its extracted text}. Empty
    for the default in-repo layout, so the in-repo invocation is byte-for-byte unchanged."""
    candidates = [
        config.WIKI_DIR,
        config.RAW_DIR,
        config.DOCS_DIR,
        config.source_path_for_key(rel_key).parent,
    ]
    if read_path:
        # The extracted-text file lives in a system temp dir (outside the repo); the agent must be
        # granted access so it can read what to ingest.
        candidates.append(Path(read_path).parent)
    out: dict[str, None] = {}
    for d in candidates:
        if config.is_outside_repo(d):
            out[str(Path(d).resolve())] = None
    return sorted(out)


def _build_instruction(rel_key: str, kind: str = "ingest", read_path: str | None = None) -> str:
    """The short, paths-only agent prompt. References the rules and the raw source BY PATH
    (the agent opens them with its own tools), so it never embeds file content and stays paths-only
    — at most a couple thousand chars regardless of raw-file size, the WinError 206 fix. ``rel_key``
    is the source key (a repo-relative posix path like ``raw/notes.md`` for an in-repo source, or an
    ABSOLUTE posix path for an out-of-repo source on a mounted drive); ``cwd`` is the repo root, so
    an in-repo path is named relative to it and an out-of-repo path absolutely. The wiki/raw
    directory names are read from config (``OKF_WIKI_DIR`` / ``OKF_RAW_DIR``) at CALL time via
    :func:`_agent_path`, so a custom layout — a renamed in-repo dir (``OKF_WIKI_DIR=wikiET``) or a
    network-drive path (``OKF_WIKI_DIR=T:\\team-wiki\\wiki``) — is searched and written correctly
    instead of a hardcoded ``wiki/``.

    ``kind`` selects which propagation the agent performs:

    - ``"ingest"`` (default) — fold a NEW raw source into the wiki.
    - ``"reconcile"`` — the source CHANGED since it was last ingested; re-read it and UPDATE
      or REMOVE the now-stale facts it had produced, not merely append new ones.
    - ``"delete"`` — the source was REMOVED from disk; strip the facts/citations that came
      only from it (this is the only prompt that must NOT try to open ``rel_key``).

    ``read_path`` (ingest/reconcile only) is set when ``rel_key`` is a binary Office file the agent
    cannot open: ingest has extracted its text to that path, so the agent is told to READ
    ``read_path`` for content while still citing ``rel_key`` as the source of record.
    """
    wiki_rel = _agent_path(config.WIKI_DIR)
    raw_rel = _agent_path(config.RAW_DIR)
    header = (
        "You are the ingest engine for a self-structuring wiki in Google's Open Knowledge "
        "Format. Read the rules in SCHEMA.md and AGENT_INGEST.md (current directory) and "
        "follow them exactly.\n\n"
    )

    if kind == "delete":
        # The source no longer exists, so the agent must NOT open it — it greps the wiki for
        # the provenance that pointed at it and removes/repoints it. The post-run check in
        # ingest re-runs find_raw_references and rolls back unless every reference is gone.
        return (
            header
            + f"The raw source {rel_key} was DELETED and no longer exists on disk. Do NOT try "
            "to open it. Remove the provenance that depended on it by EDITING FILES DIRECTLY:\n"
            f"1. Search {wiki_rel}/ (Grep/Glob/Read) for every page that cites {rel_key}: a "
            f"`resource: {rel_key}` frontmatter field, or a `[^sN]` footnote whose `## Sources` "
            f"definition links to it (e.g. `](../../{rel_key})`).\n"
            "2. For each fact whose ONLY source was that file, delete the sentence, its `[^sN]` "
            "marker, and its `## Sources` definition. If the SAME fact also carries another "
            "`[^sN]` source, keep the fact and remove ONLY this file's marker and definition.\n"
            f"3. If a page's `resource:` named {rel_key}, repoint it to another raw file the "
            "page still cites; if no cited source remains, the page is unsupported — delete it "
            "and repoint or remove inbound relative links to it.\n"
            "4. Never invent replacement facts. Never edit index.md, log.md, any */index.md, or "
            f"any dotfile, and make no changes outside {wiki_rel}/.\n"
            "5. Before finishing, run `okf-wiki check` (or `uv run python -m okf_wiki check`) "
            f"and fix every error. When you are done, NO page may reference {rel_key}."
        )

    if kind in ("repo", "repo-reconcile"):
        # rel_key is a whole GIT REPOSITORY (a folder under raw/), not a single file. Its
        # high-signal files were pre-digested to read_path; the agent reads THAT and folds the repo
        # into a few pages + a `type: System` page per external system. ~99% of code is irrelevant,
        # so the brief is deliberately about USE/WHAT/HOW/OUTPUT, not a transcription.
        reconcile_note = ""
        if kind == "repo-reconcile":
            reconcile_note = (
                f"NOTE: {rel_key} is a repo that CHANGED since it was last ingested (new commits) "
                "— this is a RE-INGEST. The digest's 'What changed' section lists the changed "
                "files. UPDATE the facts those changes affect (a changed command, mapping, table, "
                "or output), remove facts the repo no longer supports, and leave unaffected facts "
                "and facts from OTHER sources intact. Do not merely append.\n\n"
            )
        return (
            header
            + reconcile_note
            + f"The raw source {rel_key} is a GIT REPOSITORY (a whole code repo), not a single "
            f"file. A DIGEST of its high-signal files has been prepared at {read_path} — read THAT "
            f"for the content. Treat {rel_key} (the repo folder) as the source of record: set "
            f"`resource: {rel_key}` and cite {rel_key} in `## Sources` (the relative link points at "
            "the repo folder). Fold it into the wiki by EDITING FILES DIRECTLY:\n"
            "1. Assume ~99% of the code is irrelevant to a knowledge wiki. For the repo, capture as "
            "cited facts only:\n"
            "   a. HOW TO USE IT — how to run/call it, how to connect to the API/service/DB, the "
            "key command(s) to transform the data, and the env vars / config it needs.\n"
            "   b. WHAT IT DOES — its purpose.\n"
            "   c. HOW IT DOES IT — the data flow / pipeline steps at a readable level (NOT line by "
            "line, NOT one note per function).\n"
            "   d. WHAT COMES OUT — the output / result form.\n"
            "   You MAY include a SHORT verbatim code excerpt (a few lines) when the code itself IS "
            "the fact — a connection/auth call, the key transform command, an env var, a SQL query; "
            "cite it like any fact. Do NOT paste large code blocks.\n"
            "2. For every EXTERNAL SYSTEM the repo touches — a database, API, service, queue, or "
            "tool (e.g. SAP, PLM, Postgres) — create or UPDATE a page with `type: System` (it routes "
            f"to {wiki_rel}/systems/), tags marking its kind (database/api/service/tool), describing "
            "the system and how this repo uses it (tables/endpoints, access method, auth). These "
            "pages ACCUMULATE across sources — search for an existing one and extend it before "
            "creating a new one. Link the repo's pages to the System pages.\n"
            f"3. Search {wiki_rel}/ (Grep/Glob/Read) before writing — prefer extending/merging over "
            "new pages. Set frontmatter type, title, description, tags (>=1 lowercase), and resource "
            "(verbatim); do NOT set timestamp. Cross-link densely with relative markdown links.\n"
            f"4. Never edit {wiki_rel}/index.md, {wiki_rel}/log.md, any */index.md, or any dotfile. "
            f"Make no changes outside {wiki_rel}/. When you delete/rename a page, repoint inbound "
            "links.\n"
            "5. Before finishing, run `okf-wiki check` (or `uv run python -m okf_wiki check`) and "
            f"fix every reported error.\nIf {rel_key} adds nothing new, make no edits and stop."
        )

    note = ""
    if kind == "reconcile":
        # Re-ingest of a CHANGED source: the wiki already holds facts it produced, so the agent
        # must reconcile (update/remove), not blindly append — otherwise a corrected number
        # leaves the stale one behind next to the new one.
        note = (
            f"NOTE: {rel_key} CHANGED since it was last ingested — this is a RE-INGEST, not a "
            "first ingest, and the wiki already cites it. As you fold in its CURRENT contents, "
            "UPDATE facts whose numbers/names/claims changed. For a fact the current file no "
            "longer supports, remove THIS source's `[^sN]` marker and its `## Sources` "
            "definition, and drop the whole sentence ONLY if no other `[^sN]` source remains on "
            "it (a co-cited fact stays — just remove this marker). Do not merely append, and "
            "leave facts from OTHER raw sources and their citations intact.\n\n"
        )

    if read_path:
        # rel_key is a binary Office file (pptx/docx); its text was pre-extracted to read_path. The
        # agent reads THAT for content but must cite the original rel_key as the source of record.
        read_step = (
            f"1. The raw source {rel_key} is a binary Office file (PowerPoint/Word) you cannot open "
            f"directly. Its text has been EXTRACTED to {read_path} — read THAT file for the content. "
            f"Treat {rel_key} as the source of record: set `resource: {rel_key}` and cite {rel_key} "
            "(NOT the extracted file) in `## Sources`. If it holds no usable text, make no edits.\n"
        )
    else:
        read_step = (
            f"1. Open and read the raw source file: {rel_key}. It may be ANY text-bearing file type "
            "(markdown, plain text, code such as .py/.sql, JSON/CSV, PDF, ...) — extract its text "
            "and ingest the facts. For CODE/config/data, capture its PURPOSE, BEHAVIOR and the "
            "external systems it touches (which database and HOW), NOT its structure — see 'Code & "
            "structured sources' in SCHEMA.md. If it holds no usable text, make no edits.\n"
        )

    return (
        header
        + note
        + "Fold ONE raw source into the wiki by EDITING FILES DIRECTLY:\n"
        + read_step
        + f"2. The wiki is under {wiki_rel}/ (raw sources under {raw_rel}/). Search and read "
        "existing pages (Grep/Glob/Read) before writing — prefer extending or merging into an "
        "existing page over creating a new one.\n"
        f"3. Create/update/merge/split page files under {wiki_rel}/ so every fact from {rel_key} "
        "is captured, cited ([^sN] for raw facts / [^llmN] for model facts, defined in a "
        "trailing ## Sources section), and densely cross-linked with relative markdown links. "
        "Set frontmatter type, title, description, tags (>=1 lowercase), and resource (verbatim); "
        "do NOT set timestamp.\n"
        f"4. Never edit {wiki_rel}/index.md, {wiki_rel}/log.md, any */index.md, or any dotfile. "
        f"Make no changes outside {wiki_rel}/.\n"
        "5. When you delete or rename a page, repoint inbound relative links to it.\n"
        "6. Before finishing, run `okf-wiki check` (or `uv run python -m okf_wiki check`) and "
        "fix every reported error.\n"
        f"If {rel_key} adds nothing new, make no edits and stop."
    )


def _build_invocation(
    cli: str, cli_path: str, prompt: str, extra_dirs: list[str] | None = None
) -> tuple[list[str], str | None]:
    """Return ``(argv, stdin_text)`` for the chosen CLI in agentic, non-interactive mode.

    Each CLI runs with autonomous file tools and ``cwd`` = the repo root (set by ``_run_session``).
    ``extra_dirs`` are directories the agent must reach that live OUTSIDE the repo (an out-of-repo
    wiki/raw on a mounted network drive, computed by :func:`_external_dirs`) — empty for the default
    in-repo layout. For **claude** the prompt goes on STDIN (argv carries only flags); for
    copilot/gemini it is a ``-p`` argument — now safe because the prompt is tiny."""
    extra_dirs = extra_dirs or []
    if cli == "claude":
        # acceptEdits auto-applies file edits; the allowlist scopes tools (Read/Edit/Write to
        # author pages, Grep/Glob to search the wiki, Bash so the agent can run `okf-wiki check`).
        # cwd=repo root covers SCHEMA.md/AGENT_INGEST.md/okf-wiki; --add-dir grants access to an
        # out-of-repo wiki/raw (network drive), since claude's file tools are otherwise scoped to
        # cwd. No extra_dirs in the default in-repo layout, so the argv is then unchanged.
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
        # reach the wiki/raw whether they are under cwd or on a mounted drive (so an out-of-repo
        # layout needs no extra flag); --no-ask-user keeps it autonomous; -s trims stats.
        return [
            cli_path,
            "-p",
            prompt,
            "--allow-all-tools",
            "--allow-all-paths",
            "--no-ask-user",
            "-s",
        ], None
    if cli == "gemini":
        # yolo auto-approves all tool calls (auto_edit still prompts for read/search tools,
        # which would hang with no TTY). --include-directories adds an out-of-repo wiki/raw to the
        # workspace (best-effort; only when needed, so the default in-repo argv is unchanged).
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


def _stream_subprocess(
    cli: str, argv: list[str], stdin_text: str | None
) -> tuple[int, str, str]:
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
        cwd=str(config.REPO_ROOT),
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
                # piped `okf-wiki ingest > report.txt` still shows the live transcript on screen.
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
            directory = config.REPO_ROOT / directory
        config.robust_mkdir(directory)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        safe = "".join(
            c if (c.isalnum() or c in "-._") else "_" for c in (label or "session")
        )[:80]
        path = directory / f"{stamp}.{os.getpid()}.{_LOG_SEQ}.{safe}.log"
        body = [
            "# okf-wiki ingest — LLM agent session transcript",
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


def _run_session(
    cli: str, argv: list[str], stdin_text: str | None, *, log_label: str | None = None
) -> None:
    """Run the agentic CLI once in ``config.REPO_ROOT``. Success = the session completed
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
                cwd=str(config.REPO_ROOT),
            )
            returncode, out_raw, err_raw = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        # TimeoutExpired carries whatever was captured before the kill — subprocess.run populates
        # .output/.stderr on the captured path, and _stream_subprocess attaches its streamed chunks
        # via output= — so the timeout transcript logs the PARTIAL session, not an empty one.
        partial_out = _decode_partial(exc.output)
        partial_err = _decode_partial(exc.stderr)
        _write_transcript(
            cli, argv, stdin_text, None, partial_out, partial_err, log_label,
            time.monotonic() - started, note=f"timed out after {config.LLM_TIMEOUT}s",
        )
        raise RuntimeError(
            f"the {cli!r} CLI timed out after {config.LLM_TIMEOUT}s"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"failed to run the {cli!r} CLI: {exc}") from exc

    out = (out_raw or "").strip()
    err = (err_raw or "").strip()
    _write_transcript(
        cli, argv, stdin_text, returncode, out_raw or "", err_raw or "",
        log_label, time.monotonic() - started,
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
            raise RuntimeError(
                f"the claude CLI failed (exit {returncode}): {(err or out)[:500]}"
            )
        return

    # copilot / gemini (and any unknown CLI): the exit code is the success signal.
    if returncode != 0:
        raise RuntimeError(
            f"the {cli!r} CLI failed (exit {returncode}): {(err or out)[:500]}"
        )
    return


def run_ingest_session(rel_key: str, kind: str = "ingest", read_path: str | None = None) -> None:
    """Run the configured agentic CLI once to propagate the raw source ``rel_key`` into the wiki.

    ``kind`` picks the propagation (see :func:`_build_instruction`): ``"ingest"`` folds in a new
    source, ``"reconcile"`` re-ingests a CHANGED source (updating/removing its stale facts), and
    ``"delete"`` strips the provenance of a source that was REMOVED from disk.

    ``read_path`` (ingest/reconcile only) is the path to the pre-extracted text of a binary Office
    source: when set, the agent is told to READ it for content while still citing ``rel_key``, and
    its directory is granted to the CLI alongside any out-of-repo wiki/raw.

    Side-effecting only: the agent edits files under ``config.WIKI_DIR``. Returns None;
    ``ingest`` discovers what changed via a filesystem diff. Raises ``RuntimeError`` (collected
    per-source by ingest) on a missing/failed CLI or a timeout."""
    cli = (config.LLM_CLI or "claude").strip().lower()
    cli_path = _resolve_cli(cli)
    prompt = _build_instruction(rel_key, kind, read_path)
    argv, stdin_text = _build_invocation(cli, cli_path, prompt, _external_dirs(rel_key, read_path))
    _run_session(cli, argv, stdin_text, log_label=f"{kind}.{rel_key}")
