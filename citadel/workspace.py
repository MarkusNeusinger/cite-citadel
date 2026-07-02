"""Workspace scaffolding behind ``citadel init``.

A citadel workspace is any directory holding a ``citadel.toml`` marker file (see ``config``'s
workspace discovery). ``init_workspace`` creates the minimal skeleton — the marker (a PURE
marker, never configuration), a ``.env`` from the packaged template, and empty ``raw/`` +
``wiki/`` directories. No ``rules/`` overlay is scaffolded: house rules are opt-in — a user
creates ``rules/local.md`` (appended to every agent session once present) or forks a packaged
file with ``citadel rules eject <name>`` (a file dropped in ``rules/`` shadows the packaged
same-name rules file — see ``config.effective_rules_file`` and the rules README's *Workspace
overrides & local.md*). IDEMPOTENT: an existing file or directory is never overwritten, only
reported as skipped, so re-running init on a live workspace is always safe.
"""

from __future__ import annotations

from pathlib import Path

from . import config


# The pure-marker content: a comment plus a format-version line. Never configuration — all
# settings stay CITADEL_* env vars + the workspace .env.
MARKER_CONTENT: str = "# cite-citadel workspace marker\nformat = 1\n"

_ENV_FALLBACK: str = "# citadel workspace settings (CITADEL_* env vars; see the project README)\n"


def _env_template() -> str:
    """The packaged .env template (``citadel/templates/env.example`` — a real file next to this
    module, in a checkout and in site-packages alike). Best-effort: a missing template degrades
    to a one-line stub instead of failing init."""
    try:
        return (Path(__file__).resolve().parent / "templates" / "env.example").read_text(encoding="utf-8")
    except Exception:
        return _ENV_FALLBACK


def init_workspace(target: Path | str) -> tuple[Path, list[tuple[str, str]]]:
    """Scaffold a workspace at ``target`` (created if missing) and return
    ``(resolved root, [(status, name), ...])`` with status in ``{"created", "skipped"}`` —
    one entry per scaffolded item, in scaffold order. Existing files/dirs are NEVER overwritten
    (they report as ``skipped``), so the call is idempotent. A path that exists with the
    WRONG type (a file named ``raw``, a directory named ``.env``) raises a clear error
    instead of failing deep inside mkdir."""
    root = config._safe_resolve(Path(target).expanduser())
    config.robust_mkdir(root)

    results: list[tuple[str, str]] = []
    for name, content in ((config.WORKSPACE_MARKER, MARKER_CONTENT), (".env", _env_template())):
        path = root / Path(name)
        if path.is_dir():
            raise RuntimeError(f"cannot initialize workspace: '{name}' exists but is a directory - rename or remove it")
        if path.exists():
            results.append(("skipped", name))
        else:
            config.robust_mkdir(path.parent)
            path.write_text(content, encoding="utf-8")
            results.append(("created", name))
    for name in ("raw", "wiki"):
        path = root / name
        if path.exists() and not path.is_dir():
            raise RuntimeError(
                f"cannot initialize workspace: '{name}' exists but is not a directory - rename or remove it"
            )
        if path.is_dir():
            results.append(("skipped", name + "/"))
        else:
            config.robust_mkdir(path)
            results.append(("created", name + "/"))
    return root, results
