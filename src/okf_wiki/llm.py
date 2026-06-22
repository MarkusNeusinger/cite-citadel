"""The ONLY place that talks to an LLM — through a coding-agent CLI, not an API key.

Ingest shells out to a CLI (``claude``, ``copilot``, or ``gemini``) in headless
print mode, so calls run on whatever subscription that CLI is already logged into
(e.g. a Claude Max plan) and **no ANTHROPIC_API_KEY is needed**.

- Pick the backend with ``OKF_LLM_CLI`` (``claude`` | ``copilot`` | ``gemini``;
  default ``claude``), read via ``config.LLM_CLI``.
- Override the binary path with ``CLAUDE_CODE_PATH`` / ``COPILOT_CLI_PATH`` /
  ``GEMINI_CLI_PATH`` (matching the conventions of the user's other workflows).
- The model for the ``claude`` CLI comes from ``config.INGEST_MODEL`` (an alias
  like ``sonnet``/``opus``/``haiku`` or a full id). ``copilot``/``gemini`` use
  their own default model.

Exactly one function does real work: ``plan_pages(raw_name, raw_text, digest)``
builds the prompt (SCHEMA.md + standing rules + raw + digest), runs the CLI once,
and returns a validated list of page-op dicts parsed from the model's JSON. Since
a CLI can't enforce a JSON schema the way the API's ``output_config`` does, the
prompt demands a single bare JSON object and the parser extracts it robustly.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from . import config

# Standing rules appended to SCHEMA.md in the ingest prompt.
INGEST_RULES = (
    "Standing ingest rules:\n"
    "\n"
    "GROUNDING — raw files are the primary truth; any model-added fact must be labeled:\n"
    "- Build the page from the facts in the RAW FILE text given below. Rephrase into clean, "
    "well-formed sentences and reorganize freely, but NEVER change the meaning, the numbers, "
    "the names, or the claims of a raw fact.\n"
    "- You MAY add a fact from your own knowledge ONLY when ALL THREE hold: it is ESSENTIAL "
    "to understanding the topic, you are HIGHLY CONFIDENT it is correct, and it stays strictly "
    "on topic. Do not pad, speculate, or wander — when in doubt, leave it out.\n"
    "- Cite EVERY factual sentence with a footnote marker: use [^sN] (N = 1, 2, 3, ...) for a "
    "fact taken from a raw file, and [^llmN] (a SEPARATE numbering) for a fact you added from "
    "your own knowledge.\n"
    "- Define each marker once in a trailing \"## Sources\" section:\n"
    "    * raw fact:   `[^sN]: [raw/<file>](RELPATH_TO_RAW) - short note (ingested <date>)`, "
    "where RELPATH_TO_RAW is a RELATIVE path from the page to the raw file (a page in "
    "wiki/concepts/ reaches raw/ via ../../raw/<file>).\n"
    "    * model fact: `[^llmN]: LLM - model knowledge, not from a raw file (added <date>)` "
    "(NO file link).\n"
    "- A [^sN] marker MUST point to a real raw file — never invent provenance or attribute a "
    "fact to a raw file it did not come from. A fact you are not highly confident about is "
    "dropped, NOT guessed and labeled [^llmN].\n"
    "\n"
    "ROUTING & RESTRUCTURING — keep the wiki clean as it grows:\n"
    "- Route each piece of information to the page where it best FITS. Prefer extending "
    "or merging into an existing page from the digest over creating a new one; create a "
    "new page only when no existing page is a good home. Do NOT mechanically make one new "
    "page per raw file.\n"
    "- When you merge into an existing page, return its FULL merged body and keep ALL "
    "prior facts and their [^sN] markers intact (re-number/preserve the Sources section "
    "so every kept fact still resolves).\n"
    "- YOU MAY RESTRUCTURE THE WIKI. To SPLIT a page that has grown too large or mixes "
    "unrelated topics, emit one write op per focused new page (each carrying the moved "
    "facts WITH their [^sN] citations) plus one delete op for the original. To MERGE two "
    "pages on the same topic, emit one write op for the surviving page (full merged body, "
    "citations from BOTH pages preserved) plus one delete op for the absorbed page.\n"
    "- ALWAYS preserve every fact and its citation across a split or merge — never drop a "
    "cited fact. Use op=\"delete\" ONLY for a page you have just superseded by a write, or "
    "one that is now redundant/obsolete; never delete a page whose facts you have not "
    "preserved elsewhere. Never delete index.md or log.md (the system regenerates them).\n"
    "- NEVER emit a delete for a rel_path that one of your write ops also targets (a page "
    "you are writing this run is one you want to keep, not remove).\n"
    "- When you delete a page because its content moved into another page, set that op's "
    "\"redirect\" to the surviving page's rel_path. The system then repoints every "
    "cross-link that pointed at the deleted page to the survivor, so no link breaks.\n"
    "\n"
    "LINKS, TAGS & CONFLICTS:\n"
    "- Build a DENSELY connected graph. Link to other wiki pages with RELATIVE markdown "
    "links (e.g. ../concepts/foo.md), linking the FIRST mention of any concept that has "
    "(or clearly should have) its own page. Use the page catalog in the digest to find "
    "targets. Links are standard markdown — never [[wiki-style]] links.\n"
    "- End each page with a \"## See also\" section (AFTER the body, BEFORE \"## Sources\"): "
    "a short bulleted list of relative links to the most closely related pages. Omit it "
    "only when nothing is genuinely related.\n"
    "- Give each page 2-5 lowercase \"tags\" drawn from a shared vocabulary, REUSING "
    "existing tag names from the digest where they fit, so pages are searchable and "
    "browsable by topic.\n"
    "- The page body is GitHub-flavored markdown ONLY: NEVER put a YAML \"---\" "
    "frontmatter block inside the body — the system writes frontmatter from your op "
    "fields (type/title/description/tags). The digest shows existing pages with their "
    "frontmatter stripped for this reason.\n"
    "- On conflict, never silently overwrite: insert a \"> [!CONTRADICTION]\" callout that "
    "names both claims with both source markers.\n"
    "- Use op=\"skip\" if the raw file adds nothing new."
)

# How the model must shape its answer (the CLI can't enforce a json_schema).
OPS_FORMAT = (
    "OUTPUT FORMAT — this is strict:\n"
    "Reply with ONE JSON object and NOTHING else. No prose, no explanation, no "
    "markdown code fences. The object must be exactly:\n"
    '{"ops": [ {"op": "write" | "skip" | "delete", "type": "<OKF type, e.g. Concept, '
    'Entity, Note>", "title": "<human title>", "rel_path": "<wiki-relative path, or '
    'empty string to auto-route by type>", "description": "<one-line summary>", "tags": '
    '["lowercase", "tags"], "body": "<full markdown page body: each fact ends in a [^sN] '
    '(raw) or [^llmN] (model knowledge) footnote, then an optional ## See also section of '
    'relative links, then a trailing ## Sources section>"} ] }\n'
    'A "delete" op needs only rel_path (other fields may be omitted), plus an optional '
    '"redirect" naming the surviving page that absorbs its inbound links: '
    '{"op": "delete", "rel_path": "concepts/old.md", "redirect": "concepts/new.md"}.\n'
    "SPLIT example — break concepts/big.md into two focused pages:\n"
    '{"ops": [ {"op": "write", "type": "Concept", "title": "Topic A", "rel_path": "", '
    '"description": "...", "tags": [], "body": "...moved facts with their [^sN]..."}, '
    '{"op": "write", "type": "Concept", "title": "Topic B", "rel_path": "", '
    '"description": "...", "tags": [], "body": "...moved facts with their [^sN]..."}, '
    '{"op": "delete", "rel_path": "concepts/big.md", "redirect": "concepts/topic-a.md"} ] }\n'
    "MERGE example — fold concepts/attention.md into concepts/self-attention.md:\n"
    '{"ops": [ {"op": "write", "rel_path": "concepts/self-attention.md", "type": '
    '"Concept", "title": "Self-Attention", "description": "...", "tags": [], "body": '
    '"...full merged body keeping [^sN] from BOTH pages..."}, {"op": "delete", '
    '"rel_path": "concepts/attention.md", "redirect": "concepts/self-attention.md"} ] }\n'
    'For a source that adds nothing new, return {"ops": [{"op": "skip", "type": "", '
    '"title": "", "rel_path": "", "description": "", "tags": [], "body": ""}]}.'
)

_SCHEMA_TEXT: str | None = None

# CLI binary resolution (env override name -> default binary name).
_CLI_PATH_ENV = {
    "claude": "CLAUDE_CODE_PATH",
    "copilot": "COPILOT_CLI_PATH",
    "gemini": "GEMINI_CLI_PATH",
}
_CLI_DEFAULT_BIN = {"claude": "claude", "copilot": "copilot", "gemini": "gemini"}


def _schema_text() -> str:
    """Read SCHEMA.md (via ``config.SCHEMA_PATH``) once and cache it."""
    global _SCHEMA_TEXT
    if _SCHEMA_TEXT is None:
        try:
            _SCHEMA_TEXT = config.SCHEMA_PATH.read_text(encoding="utf-8")
        except OSError:
            _SCHEMA_TEXT = ""
    return _SCHEMA_TEXT


def build_prompt(schema_text: str, raw_name: str, raw_text: str, digest: str) -> str:
    """Assemble the full single-shot prompt for the CLI."""
    return "\n\n".join(
        [
            "You are the ingest engine for a self-structuring wiki in Google's Open "
            "Knowledge Format. Follow these house rules exactly:",
            schema_text,
            INGEST_RULES,
            OPS_FORMAT,
            f"RAW FILE: {raw_name}",
            f"<<<RAW>>>\n{raw_text}\n<<<END RAW>>>",
            "WIKI DIGEST (what already exists; merge into / patch these instead of "
            "duplicating):\n" + digest,
        ]
    )


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


def _build_invocation(cli: str, cli_path: str, prompt: str) -> tuple[list[str], str | None]:
    """Return ``(argv, stdin_text)`` for the chosen CLI in headless print mode.

    For the **claude** CLI the prompt is sent on STDIN (argv carries only flags). This
    avoids the Windows command-line length limit (CreateProcessW caps an argv at ~32 KB),
    which a large raw file or a budget-filled digest could otherwise exceed, and it sends
    the prompt as UTF-8 regardless of the OS code page. ``claude -p`` reads the prompt from
    stdin. copilot/gemini take the prompt as a ``-p`` argument (their documented form).
    """
    if cli == "claude":
        argv = [cli_path, "-p", "--output-format", "json"]
        if config.INGEST_MODEL:
            argv.extend(["--model", config.INGEST_MODEL])
        return argv, prompt
    # copilot / gemini (and any unknown CLI): a plain headless prompt as an argument.
    return [cli_path, "-p", prompt], None


def _run_cli(cli: str, argv: list[str], stdin_text: str | None = None) -> str:
    """Run the CLI once and return the assistant's text (raises on failure).

    ``stdin_text`` (the claude prompt) is fed on stdin; for copilot/gemini it is None and
    the prompt is already in ``argv``.
    """
    try:
        proc = subprocess.run(
            argv,
            input=stdin_text,
            capture_output=True,
            text=True,
            # Force UTF-8 on BOTH the piped prompt and the decoded stdout/stderr,
            # regardless of the OS locale. Without this, `text=True` uses the platform
            # default (e.g. cp1252 on German Windows) and a non-ASCII byte in the CLI's
            # UTF-8 output raises UnicodeDecodeError. errors="replace" keeps a stray
            # undecodable byte from killing the whole run.
            encoding="utf-8",
            errors="replace",
            timeout=config.LLM_TIMEOUT,
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
        # `--output-format json` returns a single envelope:
        # {"type":"result","is_error":bool,"api_error_status":int|null,"result":str,...}
        if not out:
            raise RuntimeError(
                f"the claude CLI returned no output (exit {proc.returncode}): "
                f"{err[:500]}"
            )
        try:
            env = json.loads(out)
        except json.JSONDecodeError:
            env = _last_json_result_line(out)
        if isinstance(env, dict):
            if env.get("is_error"):
                status = env.get("api_error_status")
                raise RuntimeError(
                    f"claude CLI error"
                    + (f" ({status})" if status else "")
                    + f": {env.get('result') or err or 'unknown error'}"
                )
            result = env.get("result")
            if isinstance(result, str):
                return result
        # Unexpected envelope shape: surface it rather than guessing.
        raise RuntimeError(f"unexpected claude CLI output: {out[:500]}")

    # copilot / gemini: plain text on stdout.
    if proc.returncode != 0:
        raise RuntimeError(
            f"the {cli!r} CLI failed (exit {proc.returncode}): {(err or out)[:500]}"
        )
    if not out:
        raise RuntimeError(f"the {cli!r} CLI returned no output: {err[:500]}")
    return out


def _last_json_result_line(text: str) -> dict | None:
    """Fallback parser for a stream-json transcript: last JSONL object whose
    ``type`` is ``result``."""
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


def _extract_ops(text: str) -> dict:
    """Robustly pull a ``{"ops": [...]}`` object out of the model's reply.

    Tries the whole string, any ```json fenced block, and the first balanced
    brace span — returns the first that parses to a dict containing ``ops``.
    """
    candidates: list[str] = [text.strip()]
    for m in re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL):
        candidates.append(m.strip())
    if "{" in text and "}" in text:
        candidates.append(text[text.find("{") : text.rfind("}") + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("ops"), list):
            return obj
    raise RuntimeError(
        f"could not parse a JSON {{'ops': [...]}} object from the CLI reply: "
        f"{text.strip()[:300]}"
    )


def plan_pages(raw_name: str, raw_text: str, digest: str) -> list[dict]:
    """Run the configured CLI once and return its list of page-op dicts.

    Raises RuntimeError (collected per-source by ingest) on a missing/failed CLI
    or an unparseable reply.
    """
    cli = (config.LLM_CLI or "claude").strip().lower()
    cli_path = _resolve_cli(cli)
    prompt = build_prompt(_schema_text(), raw_name, raw_text, digest)
    argv, stdin_text = _build_invocation(cli, cli_path, prompt)
    reply = _run_cli(cli, argv, stdin_text)
    return _extract_ops(reply)["ops"]
