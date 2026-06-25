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

import json
import os
import shutil
import subprocess
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


def _repo_rel(path: Path) -> str:
    """Repo-relative POSIX path for a configured directory. The agentic CLI runs with
    ``cwd`` = ``config.REPO_ROOT``, so the prompt must name the wiki/raw directories relative
    to the repo root — and honor ``OKF_WIKI_DIR`` / ``OKF_RAW_DIR`` overrides rather than a
    hardcoded ``wiki/``. Falls back to the directory's own name if it is not under the repo
    root (mirrors ``manifest.rel_key``)."""
    try:
        return path.resolve().relative_to(config.REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _build_instruction(rel_key: str, kind: str = "ingest") -> str:
    """The short, paths-only agent prompt. References the rules and the raw source BY PATH
    (the agent opens them with its own tools), so it never embeds file content and stays a
    few hundred chars regardless of raw-file size — the WinError 206 fix. ``rel_key`` is the
    repo-relative posix path of the raw source (e.g. ``raw/notes.md``); ``cwd`` is the repo
    root, so all paths here are repo-relative. The wiki/raw directory names are read from
    config (``OKF_WIKI_DIR`` / ``OKF_RAW_DIR``) at CALL time, so a custom layout (e.g.
    ``OKF_WIKI_DIR=wikiET``) is searched and written correctly instead of a hardcoded
    ``wiki/``.

    ``kind`` selects which propagation the agent performs:

    - ``"ingest"`` (default) — fold a NEW raw source into the wiki.
    - ``"reconcile"`` — the source CHANGED since it was last ingested; re-read it and UPDATE
      or REMOVE the now-stale facts it had produced, not merely append new ones.
    - ``"delete"`` — the source was REMOVED from disk; strip the facts/citations that came
      only from it (this is the only prompt that must NOT try to open ``rel_key``).
    """
    wiki_rel = _repo_rel(config.WIKI_DIR)
    raw_rel = _repo_rel(config.RAW_DIR)
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

    note = ""
    if kind == "reconcile":
        # Re-ingest of a CHANGED source: the wiki already holds facts it produced, so the agent
        # must reconcile (update/remove), not blindly append — otherwise a corrected number
        # leaves the stale one behind next to the new one.
        note = (
            f"NOTE: {rel_key} CHANGED since it was last ingested — this is a RE-INGEST, not a "
            "first ingest, and the wiki already cites it. As you fold in its CURRENT contents, "
            "UPDATE facts whose numbers/names/claims changed, and REMOVE facts the current file "
            "no longer supports (drop the sentence, its `[^sN]` marker, and its `## Sources` "
            "definition) — do not merely append. Leave facts from OTHER raw sources and their "
            "citations intact.\n\n"
        )

    return (
        header
        + note
        + "Fold ONE raw source into the wiki by EDITING FILES DIRECTLY:\n"
        f"1. Open and read the raw source file: {rel_key}. It may be ANY text-bearing file type "
        "(markdown, plain text, code such as .py/.sql, JSON/CSV, PDF, ...) — extract whatever "
        "text it contains and ingest the facts. If it holds no usable text, make no edits.\n"
        f"2. The wiki is under {wiki_rel}/ (raw sources under {raw_rel}/). Search and read "
        "existing pages (Grep/Glob/Read) before writing — prefer extending or merging into an "
        "existing page over creating a new one.\n"
        f"3. Create/update/merge/split page files under {wiki_rel}/ so every fact from {rel_key} "
        "is captured, cited ([^sN] for raw facts / [^llmN] for model facts, defined in a "
        "trailing ## Sources section), and densely cross-linked with relative markdown links. "
        "Set frontmatter type, title, description, tags (>=1 lowercase), and resource; do NOT "
        "set timestamp.\n"
        f"4. Never edit {wiki_rel}/index.md, {wiki_rel}/log.md, any */index.md, or any dotfile. "
        f"Make no changes outside {wiki_rel}/.\n"
        "5. When you delete or rename a page, repoint inbound relative links to it.\n"
        "6. Before finishing, run `okf-wiki check` (or `uv run python -m okf_wiki check`) and "
        "fix every reported error.\n"
        f"If {rel_key} adds nothing new, make no edits and stop."
    )


def _build_invocation(
    cli: str, cli_path: str, prompt: str
) -> tuple[list[str], str | None]:
    """Return ``(argv, stdin_text)`` for the chosen CLI in agentic, non-interactive mode.

    Each CLI runs with autonomous file tools scoped to ``cwd`` (the repo root, set by
    ``_run_session``). For **claude** the prompt goes on STDIN (argv carries only flags); for
    copilot/gemini it is a ``-p`` argument — now safe because the prompt is tiny."""
    if cli == "claude":
        # acceptEdits auto-applies file edits; the allowlist scopes tools (Read/Edit/Write to
        # author pages, Grep/Glob to search the wiki, Bash so the agent can run `okf-wiki
        # check`). cwd=repo root already contains raw/ and wiki/, so no --add-dir is needed.
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
        if config.INGEST_MODEL:
            argv += ["--model", config.INGEST_MODEL]
        return argv, prompt
    if cli == "copilot":
        # --allow-all-tools is required for non-interactive editing; --allow-all-paths lets it
        # reach raw/ and wiki/ under cwd; --no-ask-user keeps it autonomous; -s trims stats.
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
        # which would hang with no TTY).
        return [cli_path, "-p", prompt, "--approval-mode", "yolo"], None
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


def _run_session(cli: str, argv: list[str], stdin_text: str | None) -> None:
    """Run the agentic CLI once in ``config.REPO_ROOT``. Success = the session completed
    without error; the agent's edits are on disk. Raises ``RuntimeError`` on timeout, a
    spawn error, a non-zero exit, or (for claude) an ``is_error`` result envelope.

    Note: empty stdout is NOT a failure — an agent that legitimately changed nothing prints
    nothing and exits 0 (ingest's snapshot diff then simply shows no changes)."""
    try:
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
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"the {cli!r} CLI timed out after {config.LLM_TIMEOUT}s"
        ) from exc
    except OSError as exc:
        raise RuntimeError(f"failed to run the {cli!r} CLI: {exc}") from exc

    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

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
        if proc.returncode != 0:
            raise RuntimeError(
                f"the claude CLI failed (exit {proc.returncode}): {(err or out)[:500]}"
            )
        return

    # copilot / gemini (and any unknown CLI): the exit code is the success signal.
    if proc.returncode != 0:
        raise RuntimeError(
            f"the {cli!r} CLI failed (exit {proc.returncode}): {(err or out)[:500]}"
        )
    return


def run_ingest_session(rel_key: str, kind: str = "ingest") -> None:
    """Run the configured agentic CLI once to propagate the raw source ``rel_key`` into the wiki.

    ``kind`` picks the propagation (see :func:`_build_instruction`): ``"ingest"`` folds in a new
    source, ``"reconcile"`` re-ingests a CHANGED source (updating/removing its stale facts), and
    ``"delete"`` strips the provenance of a source that was REMOVED from disk.

    Side-effecting only: the agent edits files under ``config.WIKI_DIR``. Returns None;
    ``ingest`` discovers what changed via a filesystem diff. Raises ``RuntimeError`` (collected
    per-source by ingest) on a missing/failed CLI or a timeout."""
    cli = (config.LLM_CLI or "claude").strip().lower()
    cli_path = _resolve_cli(cli)
    prompt = _build_instruction(rel_key, kind)
    argv, stdin_text = _build_invocation(cli, cli_path, prompt)
    _run_session(cli, argv, stdin_text)
