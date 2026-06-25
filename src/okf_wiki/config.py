"""Single source of truth for filesystem layout and the ingest backend.

Resolves every path to an absolute Path relative to the repo root (found by
walking up from this file until a dir containing both ``pyproject.toml`` and
``SCHEMA.md``, falling back to three parents up). Reads env with sane defaults
so a fresh clone works out of the box. Includes a tiny optional ``.env`` loader
(no dependency) that populates ``os.environ`` from a repo-root ``.env`` if
present and the var is unset.

Ingest runs through a coding-agent CLI (claude/copilot/gemini), so there is no
API key to manage — the CLI uses whatever subscription it is logged into.

No logic beyond path/setting resolution.

NOTE: other modules reference ``config.WIKI_DIR`` / ``config.INGEST_MODEL`` /
``config.LLM_CLI`` / etc. at call-time (``from . import config`` then
``config.WIKI_DIR``) so tests can monkeypatch these attributes.
"""

from __future__ import annotations

import os
from pathlib import Path


def _resolve_repo_root() -> Path:
    """Walk up from this file until a dir containing BOTH pyproject.toml and
    SCHEMA.md. Fall back to ``parents[2]`` (the src-layout repo root) if no such
    dir is found."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "SCHEMA.md").is_file():
            return parent
    return here.parents[2]


def _load_dotenv() -> None:
    """If REPO_ROOT/.env exists, set any ``KEY=VALUE`` whose KEY is not already
    in ``os.environ``. Ignores blank / ``#`` lines, strips surrounding quotes.
    Best-effort; never raises."""
    env_path = REPO_ROOT / ".env"
    try:
        text = env_path.read_text(encoding="utf-8")
    except (OSError, ValueError):
        return
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
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


REPO_ROOT: Path = _resolve_repo_root()

# Load the optional .env BEFORE reading the env settings below, so a bare .env
# (no exported vars) also works.
_load_dotenv()

def _safe_resolve(path: Path) -> Path:
    """``path.resolve()`` that never raises (falls back to an absolute, un-resolved path on a
    rare OS error), so path-identity math works even on a not-yet-existing target."""
    try:
        return path.resolve()
    except OSError:
        return path if path.is_absolute() else path.absolute()


def _dir_setting(env_key: str, default: Path) -> Path:
    """Resolve a configurable directory (wiki/raw/docs) to an absolute Path.

    With no override, use ``default``. With ``OKF_*_DIR`` set: expand a leading ``~``, take an
    ABSOLUTE override AS-IS — including a Windows mapped-drive path (``T:\\team-wiki\\wiki``) or a
    POSIX mount (``/mnt/share/wiki``) — so the wiki/raw can live OUTSIDE the repo, e.g. on a
    mounted network drive; and resolve a RELATIVE override against the REPO ROOT (not the process
    CWD), so ``OKF_WIKI_DIR=wiki`` means ``REPO_ROOT/wiki`` regardless of where ``okf-wiki`` is
    launched from. Always returns a ``resolve()``-d absolute path."""
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return default.resolve()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return _safe_resolve(path)


WIKI_DIR: Path = _dir_setting("OKF_WIKI_DIR", REPO_ROOT / "wiki")
RAW_DIR: Path = _dir_setting("OKF_RAW_DIR", REPO_ROOT / "raw")
DOCS_DIR: Path = _dir_setting("OKF_DOCS_DIR", REPO_ROOT / "docs")


def rel_or_abs_posix(path: Path | str) -> str:
    """The canonical identity key / agent-facing path for a raw source or a configured directory:
    its POSIX path **relative to** ``REPO_ROOT`` when it lives under the repo (short, and
    resolvable from the agent's repo-root CWD), or its **absolute** POSIX path when it does not —
    e.g. a wiki/raw tree on a mounted network drive (``T:/team-wiki/raw/notes.md``).

    This is the single source of truth for turning a path into a key, used by the manifest, the
    agent prompt, and the citation/resource bookkeeping. It replaces the old basename fallback,
    which collided distinct out-of-repo files onto the same key and was unresolvable from the repo
    root. Read ``REPO_ROOT`` at call time so tests can monkeypatch the layout."""
    rp = _safe_resolve(Path(path))
    try:
        return rp.relative_to(_safe_resolve(REPO_ROOT)).as_posix()
    except ValueError:
        return rp.as_posix()


def source_path_for_key(key: str) -> Path:
    """Inverse of :func:`rel_or_abs_posix`: the absolute filesystem Path a source key denotes. An
    absolute key (an out-of-repo source, e.g. ``T:/team-wiki/raw/notes.md``) is used as-is; a
    repo-relative key (``raw/notes.md``) is joined under ``REPO_ROOT``. Replaces the scattered
    ``REPO_ROOT / key`` joins that silently mis-resolved out-of-repo keys."""
    p = Path(key)
    return p if p.is_absolute() else REPO_ROOT / key


def is_outside_repo(path: Path | str) -> bool:
    """True if ``path`` does NOT live under ``REPO_ROOT`` — so the agentic CLI must be granted
    explicit access to it (e.g. claude ``--add-dir``), since its file tools are otherwise scoped
    to the repo-root working directory."""
    try:
        _safe_resolve(Path(path)).relative_to(_safe_resolve(REPO_ROOT))
        return False
    except ValueError:
        return True

SCHEMA_PATH: Path = REPO_ROOT / "SCHEMA.md"
# The direct-edit ingest rules the agentic CLI reads (by path) each run. Referenced in
# the short ingest prompt; Python does not read it.
AGENT_RULES_PATH: Path = REPO_ROOT / "AGENT_INGEST.md"
INDEX_PATH: Path = WIKI_DIR / "index.md"
LOG_PATH: Path = WIKI_DIR / "log.md"
MANIFEST_PATH: Path = WIKI_DIR / ".okf_ingested.json"

# Ingest backend: which coding-agent CLI to shell out to, and (for the claude
# CLI) which model alias/id to pass. No API key is used.
LLM_CLI: str = os.environ.get("OKF_LLM_CLI", "claude")
INGEST_MODEL: str = os.environ.get("OKF_INGEST_MODEL", "sonnet")
LLM_TIMEOUT: int = int(os.environ.get("OKF_LLM_TIMEOUT", "1200"))

MAX_DIGEST_CHARS: int = 12000
DIGEST_TOP_N: int = 6
# How many keyword-matched pages to consider for the digest's full-body section. Their
# bodies are appended in score order only while the digest stays under MAX_DIGEST_CHARS,
# so a small wiki is shown in full and a large one fills the budget with the best matches
# — giving the model enough context to merge/split/restructure soundly.
DIGEST_CANDIDATE_N: int = 20
