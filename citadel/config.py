"""Single source of truth for filesystem layout and the ingest backend.

Resolves every path to an absolute Path under the WORKSPACE root. A workspace is any directory
holding a ``citadel.toml`` marker file (a PURE marker — a comment plus a format-version line,
never configuration; scaffold one with ``citadel init``). Discovery order at import time (must
never raise on import):

1. ``$CITADEL_WORKSPACE`` — the explicit override an MCP-host config sets so ``citadel serve``
   works from any CWD;
2. the nearest ``citadel.toml`` walking UP from the CWD (a nested marker shadows an outer one);
3. no marker, but BOTH ``CITADEL_WIKI_DIR`` and ``CITADEL_RAW_DIR`` are set: an env-dirs
   workspace — the CWD is only the nominal root (those dirs carry absolute keys anyway);
4. otherwise NO workspace resolved: ``WORKSPACE_FOUND`` is False and ``WORKSPACE_ROOT`` falls
   back to the bare CWD — ``cli.main`` fails loud on every workspace-needing subcommand instead
   of silently building a wiki in a random directory.

Reads env with sane defaults so a fresh workspace works out of the box. Includes a tiny optional
``.env`` loader (no dependency) that populates ``os.environ`` from ``WORKSPACE_ROOT/.env`` when a
workspace actually resolved (``WORKSPACE_FOUND``) and the var is unset.

Ingest runs through a coding-agent CLI (claude/copilot/gemini), so there is no
API key to manage — the CLI uses whatever subscription it is logged into.

No logic beyond path/setting resolution.

NOTE: other modules reference ``config.WIKI_DIR`` / ``config.INGEST_MODEL`` /
``config.LLM_CLI`` / etc. at call-time (``from . import config`` then
``config.WIKI_DIR``) so tests can monkeypatch these attributes.
"""

from __future__ import annotations

import os
import time
from pathlib import Path, PurePosixPath


def _safe_resolve(path: Path) -> Path:
    """``path.resolve()`` that never raises (falls back to an absolute, un-resolved path on a
    rare OS error), so path-identity math works even on a not-yet-existing target."""
    try:
        return path.resolve()
    except OSError:
        return path if path.is_absolute() else path.absolute()


WORKSPACE_MARKER: str = "citadel.toml"


def _find_marker_root(start: Path) -> Path | None:
    """The nearest directory at/above ``start`` holding a :data:`WORKSPACE_MARKER`, or None.
    Nearest wins: a nested workspace's marker shadows an outer one, so running from inside the
    inner workspace never touches the outer one's wiki/manifest."""
    cur = _safe_resolve(start)
    for candidate in (cur, *cur.parents):
        try:
            if (candidate / WORKSPACE_MARKER).is_file():
                return candidate
        except OSError:
            return None
    return None


def _resolve_workspace(cwd: Path | None = None) -> Path | None:
    """Resolve the workspace root per the module-docstring order (env override > nearest marker >
    env-dirs pair), or None when NO workspace resolved. Pure and never raises — callers (and
    tests) may pass an explicit ``cwd``; the import-time call uses the process CWD."""
    try:
        cwd = cwd if cwd is not None else Path.cwd()
        env = os.environ.get("CITADEL_WORKSPACE", "").strip()
        if env:
            return _safe_resolve(Path(env).expanduser())
        marker_root = _find_marker_root(cwd)
        if marker_root is not None:
            return marker_root
        if os.environ.get("CITADEL_WIKI_DIR", "").strip() and os.environ.get("CITADEL_RAW_DIR", "").strip():
            return _safe_resolve(cwd)
        return None
    except OSError:  # e.g. the CWD vanished — nothing can resolve; fail loud later, not here
        return None


def _load_dotenv(root: Path) -> None:
    """If ``root/.env`` exists, set any ``KEY=VALUE`` whose KEY is not already
    in ``os.environ``. Ignores blank / ``#`` lines, strips surrounding quotes.
    Best-effort; never raises."""
    env_path = root / ".env"
    try:
        text = env_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


def _cwd_fallback() -> Path:
    """The bare process CWD as the nominal (non-)workspace root; never raises on import."""
    try:
        return _safe_resolve(Path.cwd())
    except OSError:  # the CWD vanished — nothing can resolve; fail loud later, not here
        return Path(".")


_resolved_root = _resolve_workspace()
# Whether discovery actually found a workspace. False means WORKSPACE_ROOT is only the bare CWD
# fallback — cli.main fails loud on every workspace-needing subcommand.
WORKSPACE_FOUND: bool = _resolved_root is not None
WORKSPACE_ROOT: Path = _resolved_root if _resolved_root is not None else _cwd_fallback()
del _resolved_root

# Load the optional workspace .env BEFORE reading the env settings below, so a bare .env
# (no exported vars) also works. Only when a workspace actually resolved — the fallback
# CWD is NOT a workspace, so a stray .env in some random directory is never slurped.
if WORKSPACE_FOUND:
    _load_dotenv(WORKSPACE_ROOT)


def _dir_setting(env_key: str, default: Path) -> Path:
    """Resolve a configurable directory (wiki/raw/docs) to an absolute Path.

    With no override, use ``default``. With ``CITADEL_*_DIR`` set: expand a leading ``~``, take an
    ABSOLUTE override AS-IS — including a Windows mapped-drive path (``T:\\team-wiki\\wiki``) or a
    POSIX mount (``/mnt/share/wiki``) — so the wiki/raw can live OUTSIDE the workspace, e.g. on a
    mounted network drive; and resolve a RELATIVE override against the WORKSPACE ROOT (not the
    process CWD), so ``CITADEL_WIKI_DIR=wiki`` means ``WORKSPACE_ROOT/wiki`` regardless of where
    ``citadel`` is launched from. Always returns a ``resolve()``-d absolute path."""
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return default.resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    return _safe_resolve(path)


WIKI_DIR: Path = _dir_setting("CITADEL_WIKI_DIR", WORKSPACE_ROOT / "wiki")
RAW_DIR: Path = _dir_setting("CITADEL_RAW_DIR", WORKSPACE_ROOT / "raw")
DOCS_DIR: Path = _dir_setting("CITADEL_DOCS_DIR", WORKSPACE_ROOT / "docs")


def rel_or_abs_posix(path: Path | str) -> str:
    """The canonical identity key / agent-facing path for a raw source or a configured directory:
    its POSIX path **relative to** ``WORKSPACE_ROOT`` when it lives under the workspace (short, and
    resolvable from the agent's workspace-root CWD), or its **absolute** POSIX path when it does
    not — e.g. a wiki/raw tree on a mounted network drive (``T:/team-wiki/raw/notes.md``).

    This is the single source of truth for turning a path into a key, used by the manifest, the
    agent prompt, and the citation/resource bookkeeping. It replaces the old basename fallback,
    which collided distinct out-of-workspace files onto the same key and was unresolvable from the
    workspace root. Read ``WORKSPACE_ROOT`` at call time so tests can monkeypatch the layout."""
    rp = _safe_resolve(Path(path))
    try:
        return rp.relative_to(_safe_resolve(WORKSPACE_ROOT)).as_posix()
    except ValueError:
        return rp.as_posix()


def source_path_for_key(key: str) -> Path:
    """Inverse of :func:`rel_or_abs_posix`: the absolute filesystem Path a source key denotes. An
    absolute key (an out-of-workspace source, e.g. ``T:/team-wiki/raw/notes.md``) is used as-is; a
    workspace-relative key (``raw/notes.md``) is joined under ``WORKSPACE_ROOT``. Replaces the
    scattered root-relative joins that silently mis-resolved out-of-workspace keys."""
    p = Path(key)
    return p if p.is_absolute() else WORKSPACE_ROOT / key


def display_key(key: str) -> str:
    """A short, human-facing rendering of a source key for the ingest CONSOLE output.

    An out-of-repo source on a mounted network drive carries an ABSOLUTE key — e.g.
    ``//fileserver/share/dept/2026/reports/raw/sub/notes.pdf`` — whose long prefix before the raw
    folder is noise while a live multi-file ingest scrolls past (and it wrecks the one-line progress
    display). When the key lies under ``RAW_DIR`` (or ``DOCS_DIR``), collapse it to
    ``<folder-name>/<path-below>`` — dropping the WHOLE prefix before that folder, so
    ``//fileserver/.../raw/sub/notes.pdf`` shows as ``raw/sub/notes.pdf``. A repo-relative key
    (already short, e.g. ``raw/notes.md``) or any key not under those roots is returned unchanged
    apart from slash-normalization.

    Display-only: the CANONICAL key is still what the manifest, the report, and the citation
    bookkeeping use. Read ``RAW_DIR`` / ``DOCS_DIR`` at call time so tests can monkeypatch the layout.
    Always returns a ``str`` (the input normalized to forward slashes) and never raises — every
    fallback path returns the normalized string, so the ``-> str`` contract holds even for a non-str
    (e.g. ``Path``) input and the normalization is never dropped."""
    text = str(key).replace("\\", "/").strip()
    if not text:
        return text
    try:
        p = Path(text)
        # Resolve an ABSOLUTE key through the same normalization the roots use, so the two compare in
        # one space; leave a relative (in-repo) key alone — resolving it would bind it to the CWD.
        kp = PurePosixPath(_safe_resolve(p).as_posix()) if p.is_absolute() else PurePosixPath(text)
        for root in (RAW_DIR, DOCS_DIR):
            base = PurePosixPath(_safe_resolve(root).as_posix())
            try:
                rel = kp.relative_to(base)
            except ValueError:
                continue
            return base.name + "/" + "/".join(rel.parts) if rel.parts else base.name
    except (OSError, ValueError):
        return text
    return text


def is_outside_workspace(path: Path | str) -> bool:
    """True if ``path`` does NOT live under ``WORKSPACE_ROOT`` — so the agentic CLI must be
    granted explicit access to it (e.g. claude ``--add-dir``), since its file tools are otherwise
    scoped to the workspace-root working directory."""
    try:
        _safe_resolve(Path(path)).relative_to(_safe_resolve(WORKSPACE_ROOT))
        return False
    except ValueError:
        return True


def robust_mkdir(path: Path | str, attempts: int = 5) -> None:
    """``Path(path).mkdir(parents=True, exist_ok=True)`` hardened for a wiki on a network share.

    A UNC/SMB path can momentarily report an existing directory as *not* a directory (e.g. right
    after a sibling tree was deleted), so ``os.mkdir`` raises ``FileExistsError`` (Windows error
    183) and pathlib re-raises it even though ``exist_ok=True`` — because its ``self.is_dir()``
    re-check transiently returns False. That is the race that aborted a long ingest in
    ``rebuild_indexes`` mid-finalize.

    A ``FileExistsError`` is treated as success ONLY once the target is confirmed to BE a directory
    (retrying briefly to ride out the transient share state). If the path exists but never resolves
    to a directory — a genuine file collision — the error is re-raised rather than swallowed, so it
    surfaces here instead of as a confusing ``NotADirectoryError`` on the next write. Other
    transient ``OSError``s are likewise retried a few times before being re-raised."""
    p = Path(path)
    for attempt in range(attempts):
        try:
            p.mkdir(parents=True, exist_ok=True)
            return
        except OSError as exc:
            # FileExistsError on an existing DIRECTORY is the share's transient is_dir() race —
            # success once we can confirm it really is a directory. A real file collision (or any
            # other still-failing OSError) re-raises once the retries are exhausted.
            if isinstance(exc, FileExistsError) and p.is_dir():
                return
            if attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))


# The rules layer the agentic CLI reads (by path) each run — packaged with the wheel so a
# pip-installed citadel carries its own rules. Python does not read these files; they MUST be
# real files on disk (the agent opens them by path), so they resolve directly off this module's
# location — absolute, readable from ANY CWD, in a checkout and in site-packages alike.
PACKAGED_RULES_DIR: Path = Path(__file__).resolve().parent / "rules"
SCHEMA_PATH: Path = PACKAGED_RULES_DIR / "SCHEMA.md"
AGENT_RULES_PATH: Path = PACKAGED_RULES_DIR / "AGENT_INGEST.md"
INDEX_PATH: Path = WIKI_DIR / "index.md"
LOG_PATH: Path = WIKI_DIR / "log.md"
MANIFEST_PATH: Path = WIKI_DIR / ".citadel_ingested.json"
# Persistent record of raw sources that could NOT be ingested — a binary/unsupported file, or a
# source whose agent session errored/timed out — with the reason, so a failure survives the run
# instead of scrolling past in the console. Regenerated each run (a source that later succeeds is
# dropped) and surfaced in wiki/sources/index.md.
FAILURES_PATH: Path = WIKI_DIR / ".citadel_failures.json"

# Ingest backend: which coding-agent CLI to shell out to, and (for the claude
# CLI) which model alias/id to pass. No API key is used.
LLM_CLI: str = os.environ.get("CITADEL_LLM_CLI", "claude")
INGEST_MODEL: str = os.environ.get("CITADEL_INGEST_MODEL", "sonnet")
LLM_TIMEOUT: int = int(os.environ.get("CITADEL_LLM_TIMEOUT", "1200"))

# Observability for the otherwise-headless agent session — by default the CLI's stdout/stderr is
# captured only to detect failure and then DISCARDED, so there is no record of what the model
# actually did (the very thing you need when one backend/model produces no edits while another
# does). Two opt-in knobs, both read at call time (so tests/CLI flags can override them):
#
# - CITADEL_LLM_LOG_DIR: a directory to write ONE transcript file per agent session (prompt + full
#   stdout/stderr + exit code + duration). Relative paths resolve under WORKSPACE_ROOT. Empty = off.
# - CITADEL_LLM_VERBOSE: stream the CLI's output to the terminal live as the session runs, instead of
#   capturing it silently — so you can watch the model work ("see everything") without dropping
#   the non-interactive pipeline. copilot/gemini stream their full agentic transcript; the claude
#   CLI (run with --output-format json) only emits its final result envelope, so prefer a transcript
#   log there. Truthy: 1/true/yes/on.
LLM_LOG_DIR: str = os.environ.get("CITADEL_LLM_LOG_DIR", "").strip()
LLM_VERBOSE: bool = os.environ.get("CITADEL_LLM_VERBOSE", "").strip().lower() in ("1", "true", "yes", "on")

# Git-repository sources. A sub-folder under raw/ that is a git checkout (holds a ``.git``) — or
# carries an opt-in ``.citadelsource`` marker for a git-less snapshot — is ingested as ONE source: a
# size-capped DIGEST of its high-signal files (README, dependency manifests, the connection/config
# layer, the data-transform/pipeline core, entry points) is folded in by a SINGLE agent session,
# and the source is tracked by its HEAD commit so a later commit re-ingests only the diff. Set
# CITADEL_REPO_SUPPORT=0 to fall back to the old per-file walk (every file its own source).
REPO_SUPPORT: bool = os.environ.get("CITADEL_REPO_SUPPORT", "1").strip().lower() not in ("0", "false", "no", "off", "")
# Total character budget for one repo digest, and the per-file cap inside it (a long file is
# truncated with a marker). Generous defaults so the transform/pipeline core fits; raise for big
# repos, lower to keep sessions cheap.
REPO_DIGEST_MAX_CHARS: int = int(os.environ.get("CITADEL_REPO_DIGEST_MAX_CHARS", "120000"))
REPO_PER_FILE_MAX_CHARS: int = int(os.environ.get("CITADEL_REPO_PER_FILE_MAX_CHARS", "8000"))

# Image sources. When on (default), a raw file that is a recognized image (screenshot, scan,
# diagram, chart, photo) is handed to the agent to READ VISUALLY — the coding-agent CLI's file
# reader can display images — instead of being rejected as a NUL-byte binary. Set
# CITADEL_IMAGE_SUPPORT=0 to keep images out of the wiki (they then log as unreadable, as before).
IMAGE_SUPPORT: bool = os.environ.get("CITADEL_IMAGE_SUPPORT", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
    "",
)

# Same-basename document dedup. When on (default), if two or more raw files in the SAME folder
# share a basename and are all document-export formats (a deck saved as both report.pptx AND
# report.pdf, say — set below), only ONE is ingested and the rest are skipped as duplicates (the
# skip is recorded in the failures report, pointing at the file that was kept). Preference order is
# PDF first, then modern Office, then legacy. Re-evaluated every run, so deleting the kept file
# promotes another. Set CITADEL_DEDUP_BY_BASENAME=0 to ingest every format separately.
DEDUP_BY_BASENAME: bool = os.environ.get("CITADEL_DEDUP_BY_BASENAME", "1").strip().lower() not in (
    "0",
    "false",
    "no",
    "off",
    "",
)

# Large-source chunking. A single raw source whose extractable/readable text exceeds this many
# characters is ingested in several sequential agent passes (segments split on paragraph
# boundaries), so a file too big for one context window still folds in fully — each pass MERGES
# into the pages the earlier passes created. 0 disables chunking (every source is one pass, the old
# behavior). PDFs and images are never chunked (their text isn't extracted here — the agent reads
# them whole). The default (~75k tokens) is generous — modern models rarely have less context — so
# only genuinely large sources are split; lower it for a small-context backend, raise it (or set 0
# to disable) for a very large one.
MAX_SOURCE_CHARS: int = int(os.environ.get("CITADEL_MAX_SOURCE_CHARS", "300000"))

# OS/system junk files & folders to IGNORE entirely during a raw/ scan — never ingested, never
# recorded in the manifest or the failures catalog. These are noise a file manager or the OS drops
# into folders (Windows thumbnail caches / desktop.ini, macOS .DS_Store / resource forks, Office
# ~$ lock files, editor swap & backup files) that carry no wiki-worthy content — folding each into a
# "could not ingest" entry only clutters wiki/sources/index.md. Each pattern is a shell-style glob
# matched case-insensitively against a file OR directory BASENAME (fnmatch), so `*.tmp` and `~$*`
# work. Hidden dotfiles/dirs are already skipped separately, so these mainly cover the NON-hidden
# junk (a few common hidden ones are listed too, as documentation).
_DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = (
    # Windows Explorer / system noise
    "Thumbs.db",
    "Thumbs.db:encryptable",
    "ehthumbs.db",
    "ehthumbs_vista.db",
    "desktop.ini",
    "$RECYCLE.BIN",
    "System Volume Information",
    # macOS Finder noise
    ".DS_Store",
    "._*",
    ".Spotlight-V100",
    ".Trashes",
    ".TemporaryItems",
    ".fseventsd",
    ".apdisk",
    # Office / editor lock, swap & backup files
    "~$*",
    "*.tmp",
    "*.temp",
    "*.swp",
    "*.swo",
    "*~",
    ".~lock.*#",
)


def _parse_ignore_patterns(raw: str) -> list[str]:
    """Split a comma/newline-separated ignore-pattern string into a clean list (whitespace stripped,
    blank entries dropped)."""
    return [p.strip() for p in raw.replace("\n", ",").split(",") if p.strip()]


def _resolve_ignore_patterns() -> list[str]:
    """Build the effective ignore list from the built-in defaults and ``CITADEL_IGNORE_PATTERNS``:
    unset/blank keeps the defaults; a value with a leading ``+`` is ADDED to them (e.g.
    ``+*.bak,~backup*``); any other value REPLACES them (set it to a pattern that matches nothing to
    effectively disable — though ignoring these is almost always wanted)."""
    raw = os.environ.get("CITADEL_IGNORE_PATTERNS", "").strip()
    if not raw:
        return list(_DEFAULT_IGNORE_PATTERNS)
    if raw.startswith("+"):
        return list(_DEFAULT_IGNORE_PATTERNS) + _parse_ignore_patterns(raw[1:])
    return _parse_ignore_patterns(raw)


# Read at call time by ingest's discovery walk (tests monkeypatch this list directly).
IGNORE_PATTERNS: list[str] = _resolve_ignore_patterns()


# Where each non-claude backend keeps its OWN model id in the environment. A copilot user on a
# local/Ollama model sets COPILOT_MODEL (e.g. "qwen3.6:27b"); gemini uses GEMINI_MODEL. We read
# these so the recorded label reflects the model that ACTUALLY ran, not a guess. claude is absent
# because we pass it --model INGEST_MODEL ourselves (so INGEST_MODEL is authoritative there).
_CLI_MODEL_ENV = {"copilot": "COPILOT_MODEL", "gemini": "GEMINI_MODEL"}


def ingest_model_label() -> str:
    """A short, human-readable id of the model/backend that ingests a source — recorded per
    source in the manifest (``wiki/.citadel_ingested.json``) so you can see WHICH raw file was
    imported by WHICH model. Resolved at call time so tests can monkeypatch the inputs.

    - ``claude`` — the only backend we pass ``--model`` to, so :data:`INGEST_MODEL` is exactly the
      model that ran: ``"claude:sonnet"`` (or just ``"claude"`` if no model is configured).
    - ``copilot`` / ``gemini`` — run their own model, which we never pass. The label is resolved in
      priority order so it reflects what really ran:
        1. the CLI's OWN model env var (``COPILOT_MODEL`` / ``GEMINI_MODEL``) — this is what a
           local/Ollama copilot setup sets, e.g. ``"copilot:qwen3.6:27b"``;
        2. an explicitly-set ``CITADEL_INGEST_MODEL`` (the default ``"sonnet"`` is claude-only, so it
           counts only when the user actually exported the var) — e.g. ``"copilot:gpt-5.4-mini"``;
        3. otherwise just the CLI name (``"copilot"``).
    """
    cli = (LLM_CLI or "claude").strip().lower()
    if cli == "claude":
        model = (INGEST_MODEL or "").strip()
        return f"claude:{model}" if model else "claude"
    native = os.environ.get(_CLI_MODEL_ENV.get(cli, ""), "").strip()
    if native:
        return f"{cli}:{native}"
    if "CITADEL_INGEST_MODEL" in os.environ and (INGEST_MODEL or "").strip():
        return f"{cli}:{INGEST_MODEL.strip()}"
    return cli


MAX_DIGEST_CHARS: int = 12000
DIGEST_TOP_N: int = 6
# How many keyword-matched pages to consider for the digest's full-body section. Their
# bodies are appended in score order only while the digest stays under MAX_DIGEST_CHARS,
# so a small wiki is shown in full and a large one fills the budget with the best matches
# — giving the model enough context to merge/split/restructure soundly.
DIGEST_CANDIDATE_N: int = 20
