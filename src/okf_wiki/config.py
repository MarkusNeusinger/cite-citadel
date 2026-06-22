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

WIKI_DIR: Path = Path(os.environ.get("OKF_WIKI_DIR", REPO_ROOT / "wiki")).resolve()
RAW_DIR: Path = Path(os.environ.get("OKF_RAW_DIR", REPO_ROOT / "raw")).resolve()
DOCS_DIR: Path = Path(os.environ.get("OKF_DOCS_DIR", REPO_ROOT / "docs")).resolve()

SCHEMA_PATH: Path = REPO_ROOT / "SCHEMA.md"
INDEX_PATH: Path = WIKI_DIR / "index.md"
LOG_PATH: Path = WIKI_DIR / "log.md"
MANIFEST_PATH: Path = WIKI_DIR / ".okf_ingested.json"

# Ingest backend: which coding-agent CLI to shell out to, and (for the claude
# CLI) which model alias/id to pass. No API key is used.
LLM_CLI: str = os.environ.get("OKF_LLM_CLI", "claude")
INGEST_MODEL: str = os.environ.get("OKF_INGEST_MODEL", "sonnet")
LLM_TIMEOUT: int = int(os.environ.get("OKF_LLM_TIMEOUT", "300"))

MAX_DIGEST_CHARS: int = 12000
DIGEST_TOP_N: int = 6
# How many keyword-matched pages to consider for the digest's full-body section. Their
# bodies are appended in score order only while the digest stays under MAX_DIGEST_CHARS,
# so a small wiki is shown in full and a large one fills the budget with the best matches
# — giving the model enough context to merge/split/restructure soundly.
DIGEST_CANDIDATE_N: int = 20
