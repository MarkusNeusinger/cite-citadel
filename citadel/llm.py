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
the workspace. The RESULT is whatever the agent wrote under ``wiki/``, which ``ingest``
discovers via a filesystem diff; the return value is only the session's best-effort
:class:`SessionUsage` (what the run cost, as the backend itself reports it — claude's
``--output-format json`` envelope, gemini's ``--session-summary`` stats file; None when the
backend reports nothing, e.g. copilot). It raises ``RuntimeError`` on a missing/
unusable CLI, a non-zero exit, a claude ``is_error`` envelope, or a timeout (the failure
surface ``ingest``'s per-source ``try/except`` already expects).
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import config


@dataclass(frozen=True)
class SessionUsage:
    """What ONE agent session cost, exactly as the backend CLI reports it — never estimated,
    never priced by us (the audit's cost-observability gap: the product argues in budgets while
    the CLIs' own cost envelopes were discarded).

    - ``cost_usd`` — the backend's own dollar figure (claude's ``total_cost_usd``); None for a
      backend that prices nothing (gemini/copilot).
    - ``input_tokens`` — the prompt-side total actually processed, INCLUDING cache writes/reads
      (the honest volume, not just the uncached slice).
    - ``output_tokens`` — the completion-side total.

    Every field is None when unknown; a whole-unknown session is represented as ``None`` rather
    than an empty instance (:func:`combine_usage` returns None when no part knew anything), so
    "no data" never renders as "$0.00"."""

    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def describe(self) -> str:
        """One ASCII report fragment: ``$0.42, tokens 1,234,567 in / 45,678 out`` — only the
        fields that are actually known (an unknown side is OMITTED, never rendered as a 0 that
        reads like a real count), "" when none are (so callers can skip the line)."""
        parts: list[str] = []
        if self.cost_usd is not None:
            parts.append(format_cost(self.cost_usd))
        tokens = [
            f"{count:,} {label}"
            for count, label in ((self.input_tokens, "in"), (self.output_tokens, "out"))
            if count is not None
        ]
        if tokens:
            parts.append("tokens " + " / ".join(tokens))
        return ", ".join(parts)


def combine_usage(parts) -> SessionUsage | None:
    """Sum an iterable of ``SessionUsage | None`` into one (a chunked source's segments, a run's
    sources). Each field sums over the parts that KNOW it and stays None when none did — so a
    claude+gemini mix keeps honest semantics (cost from the sessions that priced themselves,
    tokens from the ones that counted). Returns None when no part carried anything, and skips
    non-``SessionUsage`` values entirely (the test fakes return None)."""
    cost = tokens_in = tokens_out = None
    for part in parts:
        if not isinstance(part, SessionUsage):
            continue
        if part.cost_usd is not None:
            cost = (cost or 0.0) + part.cost_usd
        if part.input_tokens is not None:
            tokens_in = (tokens_in or 0) + part.input_tokens
        if part.output_tokens is not None:
            tokens_out = (tokens_out or 0) + part.output_tokens
    if cost is None and tokens_in is None and tokens_out is None:
        return None
    return SessionUsage(cost_usd=cost, input_tokens=tokens_in, output_tokens=tokens_out)


def format_cost(cost_usd: float) -> str:
    """``$0.053`` / ``$1.20`` / ``$1,234.50`` — four decimals so a sub-cent session never rounds
    to a lying ``$0.00``, trailing zeros trimmed but never below the conventional two decimals.
    Never raises: a non-finite value (a hand-edited manifest is external input) formats without
    the decimal-point trimming (``$nan``) instead of crashing a status/report render."""
    if not math.isfinite(cost_usd):
        return f"${cost_usd}"
    text = f"{cost_usd:,.4f}"
    while text.endswith("0") and len(text) - text.rindex(".") > 3:  # keep >= 2 decimals
        text = text[:-1]
    return f"${text}"


def _finite_cost(value) -> float | None:
    """``value`` as a finite float, or None — the ONE sanitizer for externally-supplied cost
    figures. Rejects non-numbers, bools (an int subclass), non-finite floats (json.loads accepts
    ``Infinity``/``NaN`` by default), and ints too large for a float (``float()`` would raise
    OverflowError — accounting must never be able to fail a session)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (OverflowError, ValueError):
        return None
    return out if math.isfinite(out) else None


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
    out-of-workspace members of {wiki dir (written), every raw source root
    (``config.source_roots()``), docs dir, every directory that can
    hold a referenced rules file (the packaged ``config.PACKAGED_RULES_DIR`` — under site-packages
    for a pip install, hence never inside a user workspace and ALWAYS granted there — plus the
    workspace ``rules/`` overlay, which lives under cwd and therefore filters out), the source
    file's own parent, and — for an Office source — the temp dir holding its extracted text}.
    Empty for the all-under-workspace dev-checkout layout (cwd already covers the rules), so that
    invocation is byte-for-byte unchanged."""
    candidates = [
        config.WIKI_DIR,
        *config.source_roots(),  # every raw source root (multi-root: an out-of-workspace root needs a grant)
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


@dataclass(frozen=True)
class _KindSpec:
    """The per-kind prompt-composition spec — the ONE table that replaces the scattered ``kind``
    checks. The EXTERNAL kind strings are the stable API (ingest.py, the manifest, and the tests
    keep them); only their mapping onto prompt SHAPE lives here. Columns:

    - ``task_file`` — the tree-relative ``tasks/*.md`` brief this kind reads.
    - ``reads_source`` — whether the session reads a raw SOURCE for content. It gates the two
      content-only frame parts: the genre enumeration (the agent judges genre FROM the source's
      text) and the fallback-date bullet (the source file's own date). ``delete`` (the file is
      gone) and ``curate`` (it improves EXISTING pages, not a source) read no source.
    - ``format_policy`` — how the format brief is chosen: ``"source"`` (an Office extract arrives
      via ``read_path`` → ``formats/office.md``; a large-source slice is covered by the task brief;
      else a PDF is magic-sniffed → ``formats/pdf.md`` — the ingest/reconcile axis), ``"repo"``,
      ``"image"``, ``"audio"`` (a whisper transcript arrives via ``read_path`` →
      ``formats/transcripts.md``, kept on EVERY segment — its cite-the-original and locator rules
      bind per slice), or ``"none"``. ``"none"`` attaches NO format brief EVEN when a ``read_path``
      is present — curate's findings file arrives via ``read_path`` and must never pull in
      ``formats/office.md``.
    - ``subject_prefix`` — the ``- <prefix>: <key>`` session bullet naming what the session acts on.
    """

    task_file: str
    reads_source: bool
    format_policy: str
    subject_prefix: str


# kind -> its composition spec. ingest/image/repo are all "fold a NEW source in" lifecycles (the
# format policy carries what differs); the *-reconcile kinds re-fold a changed/forced source;
# delete strips a removed source's provenance; curate (PR6) re-reads the run's findings file and
# improves EXISTING pages. An unknown kind is a FAIL-LOUD programming error (see _spec_for_kind).
_KIND_SPECS: dict[str, _KindSpec] = {
    "ingest": _KindSpec("tasks/ingest.md", True, "source", "Source (the source of record)"),
    "image": _KindSpec("tasks/ingest.md", True, "image", "Source (the source of record)"),
    "audio": _KindSpec("tasks/ingest.md", True, "audio", "Source (the source of record)"),
    "repo": _KindSpec("tasks/ingest.md", True, "repo", "Source (the source of record)"),
    "reconcile": _KindSpec("tasks/reconcile.md", True, "source", "Source (the source of record)"),
    "image-reconcile": _KindSpec("tasks/reconcile.md", True, "image", "Source (the source of record)"),
    "audio-reconcile": _KindSpec("tasks/reconcile.md", True, "audio", "Source (the source of record)"),
    "repo-reconcile": _KindSpec("tasks/reconcile.md", True, "repo", "Source (the source of record)"),
    "delete": _KindSpec("tasks/delete.md", False, "none", "Source (REMOVED from disk — do not open it)"),
    "curate": _KindSpec("tasks/curate.md", False, "none", "Page to curate (the cluster anchor)"),
}


def _spec_for_kind(kind: str) -> _KindSpec:
    """The composition spec for ``kind`` — FAIL LOUD (``ValueError``) on an unknown kind (a typo,
    or a new lifecycle that forgot to register here) instead of silently defaulting to an ingest
    brief and folding a source under the wrong task."""
    try:
        return _KIND_SPECS[kind]
    except KeyError:
        raise ValueError(f"unknown ingest kind {kind!r} (known: {', '.join(sorted(_KIND_SPECS))})") from None


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
    """The tree-relative FORMAT brief for this session, or None when no format applies — decided by
    the kind's ``format_policy`` (the ONE spec table). Formats are the structurally
    Python-detectable axis (repo markers, image magic, Office extraction, PDF magic); code selects
    the brief, genres stay the agent's content judgment.

    - ``repo``/``image``/``audio`` policies carry their format in the kind itself. ``audio`` keeps
      its brief on every SEGMENT too (unlike the Office exemption below): the transcript brief's
      cite-the-original-file and lines-locator rules bind for each slice of a long recording.
    - ``none`` (delete, curate) attaches NO brief — even with a ``read_path`` present (curate's
      findings file must not pull in ``formats/office.md``).
    - ``source`` (ingest/reconcile): a ``read_path`` WITHOUT a segment is a pre-extracted Office
      source (``formats/office.md``); WITH a segment it is a large-source slice covered by the task
      brief's Large-sources rules (a slice is not an Office extract, even when the source was one);
      otherwise a direct read, and a PDF (magic-sniffed) reads ``formats/pdf.md``."""
    policy = _spec_for_kind(kind).format_policy
    if policy == "repo":
        return "formats/repo.md"
    if policy == "image":
        return "formats/image.md"
    if policy == "audio":
        return "formats/transcripts.md"
    if policy == "none":
        return None
    if read_path:
        return None if segment is not None else "formats/office.md"
    if _is_pdf_source(rel_key):
        return "formats/pdf.md"
    return None


def _referenced_rules(
    rel_key: str, kind: str = "ingest", read_path: str | None = None, segment: tuple[int, int] | None = None
) -> list[tuple[str, Path]]:
    """Every RESOLVED rules file the prompt for this session references, as ``(role, path)``
    entries in the prompt's TRUE READ ORDER — the CANONICAL order, which
    :func:`_build_instruction` renders its rules lines from (single composition owner, so the
    two can never drift): ``schema`` and ``core`` (every session), the ``task`` brief for
    ``kind``, the ``format`` brief when one applies, the workspace ``local`` house rules when
    present, and finally one ``genre`` entry per effective genre brief (agent-judged; only when
    the kind READS a source — ``delete``/``curate`` have no source content to judge). The single
    source of truth the prompt-validation tests check against (every path must exist and be
    reachable)."""
    spec = _spec_for_kind(kind)
    files: list[tuple[str, Path]] = [
        ("schema", config.effective_rules_file("schema.md")),
        ("core", config.effective_rules_file("core.md")),
        ("task", config.effective_rules_file(spec.task_file)),
    ]
    fmt = _format_brief(rel_key, kind, read_path, segment)
    if fmt:
        files.append(("format", config.effective_rules_file(fmt)))
    local = config.local_rules_file()
    if local is not None:
        files.append(("local", local))
    if spec.reads_source:
        files.extend(("genre", g) for g in config.effective_genres())
    return files


# role -> prompt line for the non-genre rules entries; genres render as ONE enumerating line.
_RULES_LINE = {
    "schema": "- Format contract: {}",
    "core": "- How you work: {}",
    "task": "- Task brief (what THIS session does): {}",
    "format": "- Format brief (how to read THIS source): {}",
    "local": "- Workspace house rules: {}",
}


def _build_instruction(
    rel_key: str, kind: str = "ingest", read_path: str | None = None, segment: tuple[int, int] | None = None
) -> str:
    """The short, paths-only agent prompt: ONLY the code-invariant frame. Everything the agent
    must KNOW lives in the rules tree (``citadel/rules/``, see its README) and is referenced BY
    PATH — the prompt never embeds file content, so it stays at most a couple thousand chars
    regardless of raw-file size (the WinError 206 fix). The frame is:

    1. the rules read list — rendered from :func:`_referenced_rules` (the single composition
       owner) in its canonical order: schema.md + core.md (every session), the task brief
       ``kind`` maps to, the format brief when one applies, the workspace ``rules/local.md``
       when present, and ONE line enumerating the effective genre briefs for the agent to judge
       from the source's CONTENT (none for ``delete`` — it never reads the source);
    2. the session VARIABLES as bullets — the source key (verbatim), the configured wiki/raw
       directories, the prepared read path (an Office extract / segment slice / repo digest),
       the extracted-images ``media/`` folder with its file names (only an Office source that
       carried embedded images), the segment position, the source file's own date as the
       content-date fallback, the target wiki language (``CITADEL_WIKI_LANG``), the PDF mode
       (``CITADEL_PDF_MODE``, PDF sources only), and the style-profiling switch
       (``CITADEL_STYLE_PROFILES``, only when ON);
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
    # The raw-dir bullet names the root that COVERS this source (in a multi-root corpus a
    # second-root source must not be pointed at the primary); an out-of-root explicit path
    # falls back to the primary RAW_DIR. Lexical lookup — no disk access, delete-safe.
    raw_root = config.root_covering(config.source_path_for_key(rel_key)) or config.RAW_DIR
    raw_rel = _agent_path(raw_root)
    spec = _spec_for_kind(kind)  # the ONE table: subject bullet + whether a source is read
    fmt = _format_brief(rel_key, kind, read_path, segment)  # for the PDF-mode bullet below

    lines = [
        "You are the ingest engine for a self-structuring wiki in Google's Open Knowledge Format.",
        "Read these rules files FIRST and follow them exactly:",
    ]
    genres: list[Path] = []
    for role, path in _referenced_rules(rel_key, kind, read_path, segment):
        if role == "genre":
            genres.append(path)  # last in the canonical order — collected onto one line below
        else:
            lines.append(_RULES_LINE[role].format(_agent_path(path)))
    if genres:
        lines.append(
            "Judge the source's genre from its CONTENT; if it reads like one of these, ALSO read "
            "and follow the matching file: " + ", ".join(_agent_path(g) for g in genres) + "."
        )

    lines += ["", "Session variables (use these paths verbatim):"]
    lines.append(f"- {spec.subject_prefix}: {rel_key}")
    lines.append(f"- Wiki directory: {wiki_rel}/")
    lines.append(f"- Raw directory: {raw_rel}/")
    if read_path:
        lines.append(f"- Prepared file — read THIS for the source's content: {read_path}")
        # An Office source's embedded images (when it carried any) sit in a media/ folder beside
        # the extract. Name the folder AND its files: an agent told only by the format brief that
        # such a folder MAY exist has (measurably) concluded it doesn't and skipped the images.
        if fmt == "formats/office.md":
            media_dir = Path(read_path).parent / "media"
            images: list[str] = []
            with contextlib.suppress(OSError):
                if media_dir.is_dir():
                    images = sorted(entry.name for entry in media_dir.iterdir())
            if images:
                shown = ", ".join(images[:8]) + (", …" if len(images) > 8 else "")
                lines.append(
                    "- Extracted images — VIEW each of these with your file reader and ingest "
                    f"what they show (see the format brief): {media_dir.as_posix()}/ ({shown})"
                )
    if segment is not None:
        lines.append(f"- Segment: part {segment[0]} of {segment[1]}")
    # Fallback date for time-anchored sources: the raw file's own modification date, used only
    # when the source's CONTENT states no date (genres/meeting-minutes.md § Dates). Only for kinds
    # that READ a source (delete/curate have none), and guarded so a missing file (a repo folder,
    # a unit test's phantom key) yields no bullet.
    fallback_date = ""
    if spec.reads_source:
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
        f"Do what the task brief says by EDITING FILES DIRECTLY under {wiki_rel}/, using your "
        "built-in file tools (read/search/edit) — not shell commands — to read and search. "
        f"The source and {raw_rel}/ are READ-ONLY inputs: read them, but never write, create, "
        f"move, or delete anything there. Never create or edit {wiki_rel}/index.md, "
        f"{wiki_rel}/log.md, any */index.md, or any dotfile, and make no changes outside "
        f"{wiki_rel}/. When your edits are complete, run `citadel check` (or `uv run python -m "
        "citadel check`) ONCE; only if it reports errors, fix them and run it again to confirm.",
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
    copilot/gemini it is a ``-p`` argument — now safe because the prompt is tiny.

    All three CLIs run in their fully autonomous mode (each backend's headless YOLO equivalent);
    which files the agent may touch and which tools it should use is governed by the run
    instruction (:func:`_build_instruction`) — ``raw/`` is read-only, edits go only under the
    wiki, and the shell is reserved for the ``citadel check`` self-check and page deletes/renames —
    not by divergent per-CLI permission flags."""
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


def _usage_from_claude_envelope(env: dict | None) -> SessionUsage | None:
    """The session's cost/usage from claude's ``--output-format json`` result envelope:
    ``total_cost_usd`` plus the ``usage`` token counts. Input tokens include the cache
    creation/read counts — the prompt-side volume actually billed, not just the uncached slice.
    Defensive by design (an envelope is external input): non-numeric fields read as absent, and
    an envelope carrying nothing usable returns None."""
    if not isinstance(env, dict):
        return None
    # First FINITE-NUMERIC value wins (cost_usd is the pre-GA envelope name): a present-but-junk
    # total_cost_usd — a string, a bool, NaN/Infinity, an overflowing int — must not shadow a
    # valid legacy field, and must never raise (see _finite_cost).
    cost_usd = next(
        (cost for cost in map(_finite_cost, (env.get("total_cost_usd"), env.get("cost_usd"))) if cost is not None), None
    )
    usage = env.get("usage")
    usage = usage if isinstance(usage, dict) else {}

    def count(key: str) -> int:
        value = usage.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else 0

    tokens_in = count("input_tokens") + count("cache_creation_input_tokens") + count("cache_read_input_tokens")
    tokens_out = count("output_tokens")
    if cost_usd is None and not tokens_in and not tokens_out:
        return None
    return SessionUsage(cost_usd=cost_usd, input_tokens=tokens_in or None, output_tokens=tokens_out or None)


# --help output per resolved CLI binary, probed at most once per process (the gemini
# feature-detection below; a probe failure caches "" so a broken binary is not re-probed).
_HELP_TEXT_CACHE: dict[str, str] = {}


def _cli_help_text(cli_path: str) -> str:
    """The CLI's ``--help`` output (stdout+stderr merged), cached per binary path — the
    feature probe behind :func:`_gemini_summary_file`. Best-effort: any spawn failure or
    timeout degrades to "" (the probed feature simply reads as absent), because usage
    accounting must never be able to break an ingest."""
    if cli_path not in _HELP_TEXT_CACHE:
        try:
            proc = subprocess.run(
                [cli_path, "--help"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
                # DEVNULL, never the inherited stdin: a --help that blocks reading stdin (or the
                # MCP stdio pipe under `citadel serve`) gets immediate EOF instead of stalling
                # the probe against the 30s timeout.
                stdin=subprocess.DEVNULL,
            )
            _HELP_TEXT_CACHE[cli_path] = (proc.stdout or "") + (proc.stderr or "")
        except (OSError, subprocess.SubprocessError):
            _HELP_TEXT_CACHE[cli_path] = ""
    return _HELP_TEXT_CACHE[cli_path]


def _gemini_summary_file(cli: str, cli_path: str) -> Path | None:
    """A fresh temp file for gemini's ``--session-summary`` stats JSON, or None when the backend
    is not gemini or its binary does not ADVERTISE the flag in ``--help`` (probed once per
    binary) — an older gemini must never be handed an unknown flag that would fail the whole
    session over optional accounting. The advertisement check is an exact flag-token match
    (a longer option like ``--session-summary-file`` must not read as this flag; a false
    NEGATIVE is safe — it merely disables optional accounting). The temp-file creation is
    guarded like every other usage-path operation: an unwritable/full temp dir (a real
    Windows/AV/quota failure mode) reads as "no accounting this session", never as a failed
    source — the session must run exactly as it would have pre-accounting. The caller owns
    deleting the file."""
    if cli != "gemini" or not re.search(r"--session-summary(?![\w-])", _cli_help_text(cli_path)):
        return None
    try:
        fd, name = tempfile.mkstemp(prefix="citadel_gemini_stats_", suffix=".json")
        os.close(fd)
    except OSError:
        return None
    return Path(name)


def _usage_from_gemini_summary(path: Path) -> SessionUsage | None:
    """Token counts from the stats JSON gemini's ``--session-summary`` writes. Best-effort by
    design: the wrapper shape has shifted across gemini versions, so instead of pinning one
    schema this walks the JSON for the stable inner token dicts (integer ``prompt`` /
    ``candidates`` counts) and sums them across models; a missing/unreadable/foreign-shaped
    file records nothing (None). The parse AND the walk sit under one guard that includes
    ``RecursionError`` (a pathologically nested document blows the stack in either) — a stats
    file is external input and must never fail the session it accounts for. Gemini reports no
    dollar cost, so ``cost_usd`` stays None."""
    totals = {"in": 0, "out": 0}
    found = False

    def walk(node) -> None:
        nonlocal found
        if isinstance(node, dict):
            counted = False
            for key, bucket in (("prompt", "in"), ("candidates", "out")):
                value = node.get(key)
                # Positive real ints only (matching the claude-side count filter): a corrupted/
                # hand-edited stats file must not surface negative token counts on a report.
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    totals[bucket] += value
                    counted = True
            if counted:
                found = True
                return  # a tokens leaf — never descend into it (no double counting)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    try:
        walk(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, RecursionError):
        return None
    if not found:
        return None
    return SessionUsage(input_tokens=totals["in"], output_tokens=totals["out"])


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


def _run_session(
    cli: str, argv: list[str], stdin_text: str | None, *, log_label: str | None = None
) -> SessionUsage | None:
    """Run the agentic CLI once in ``config.WORKSPACE_ROOT``. Success = the session completed
    without error; the agent's edits are on disk. Returns the session's :class:`SessionUsage`
    when the backend reported one (claude's result envelope; None for copilot/gemini, whose
    stdout carries no cost data — gemini's stats file is read by ``run_ingest_session``).
    Raises ``RuntimeError`` on timeout, a spawn error, a non-zero exit, or (for claude) an
    ``is_error`` result envelope.

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
        # We read it to detect failure — and, on success, for its cost/usage fields; the
        # agent's WORK is on disk, not in `result`.
        env: dict | None = None
        if out:
            try:
                env = json.loads(out)
            except json.JSONDecodeError:
                env = _last_result_envelope(out)
        if isinstance(env, dict) and env.get("is_error"):
            status = env.get("api_error_status")
            error = RuntimeError(
                "claude CLI error"
                + (f" ({status})" if status else "")
                + f": {env.get('result') or err or 'unknown error'}"
            )
            # A failure envelope still reports what the session COST (error_max_turns, API
            # errors) — carry it on the exception so the run total counts the failed spend
            # (the documented "failed sessions included" contract; the manifest stamp stays
            # success-only regardless).
            error.session_usage = _usage_from_claude_envelope(env)
            raise error
        if returncode != 0:
            error = RuntimeError(f"the claude CLI failed (exit {returncode}): {(err or out)[:500]}")
            error.session_usage = _usage_from_claude_envelope(env)
            raise error
        return _usage_from_claude_envelope(env)

    # copilot / gemini (and any unknown CLI): the exit code is the success signal.
    if returncode != 0:
        raise RuntimeError(f"the {cli!r} CLI failed (exit {returncode}): {(err or out)[:500]}")
    return None


def run_ingest_session(
    rel_key: str, kind: str = "ingest", read_path: str | None = None, segment: tuple[int, int] | None = None
) -> SessionUsage | None:
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

    The agent's edits under ``config.WIKI_DIR`` are the real result — ``ingest`` discovers what
    changed via a filesystem diff. The return value is only the session's best-effort
    :class:`SessionUsage` (the backend's own cost/usage report: claude's result envelope,
    gemini's ``--session-summary`` stats file when its binary advertises the flag; None when
    nothing was reported — copilot, an older gemini, or any parse miss). Accounting is strictly
    passive: no usage path can fail the session. Raises ``RuntimeError`` (collected per-source
    by ingest) on a missing/failed CLI or a timeout."""
    cli = (config.LLM_CLI or "claude").strip().lower()
    cli_path = _resolve_cli(cli)
    prompt = _build_instruction(rel_key, kind, read_path, segment)
    argv, stdin_text = _build_invocation(cli, cli_path, prompt, _external_dirs(rel_key, read_path))
    summary_path = _gemini_summary_file(cli, cli_path)
    if summary_path is not None:
        argv = argv + ["--session-summary", str(summary_path)]
    try:
        usage = _run_session(cli, argv, stdin_text, log_label=f"{kind}.{rel_key}")
        if summary_path is not None:
            usage = combine_usage([usage, _usage_from_gemini_summary(summary_path)])
        return usage
    except RuntimeError as exc:
        # A FAILED gemini session may still have written its stats file before dying — attach
        # the tokens to the exception (mirroring the claude error-envelope carry) so ingest's
        # failure path can count the spend in the run total.
        if summary_path is not None and getattr(exc, "session_usage", None) is None:
            exc.session_usage = _usage_from_gemini_summary(summary_path)
        raise
    finally:
        if summary_path is not None:
            with contextlib.suppress(OSError):
                summary_path.unlink()
