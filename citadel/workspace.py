"""Workspace scaffolding behind ``citadel init``.

A citadel workspace is any directory holding a ``citadel.toml`` marker file (see ``config``'s
workspace discovery). ``init_workspace`` creates the minimal skeleton — the marker (a PURE
marker, never configuration), a ``.env`` from the packaged template, empty ``raw/`` + ``wiki/``
directories, and the editable ``rules/`` overlay with a commented ``rules/local.md`` stub (house
rules appended to every agent session once it says anything; a file dropped in ``rules/`` shadows
the packaged same-name rules file — see ``config.effective_rules_file``). IDEMPOTENT: an existing
file or directory is never overwritten, only reported as skipped, so re-running init on a live
workspace is always safe.
"""

from __future__ import annotations

from pathlib import Path

from . import config


# The pure-marker content: a comment plus a format-version line. Never configuration — all
# settings stay CITADEL_* env vars + the workspace .env.
MARKER_CONTENT: str = "# cite-citadel workspace marker\nformat = 1\n"

_ENV_FALLBACK: str = "# citadel workspace settings (CITADEL_* env vars; see the project README)\n"

# The rules/local.md stub: all comments (renders as nothing, teaches the extension point). It IS
# referenced by every agent session once present — which is exactly the additive, upgrade-safe
# customization channel; a fresh stub simply tells the agent nothing.
LOCAL_RULES_STUB: str = (
    "<!--\n"
    "rules/local.md - workspace house rules (optional, upgrade-safe).\n"
    "\n"
    "Every ingest agent session reads this file IN ADDITION to the packaged rulebook, so put\n"
    "additive house conventions here: preferred tags, naming, project context, extra do/don't\n"
    "rules. To FORK a packaged rules file instead, copy it into this directory with\n"
    "`citadel rules eject <name>` - a file here shadows the packaged same-name file\n"
    "(`citadel rules list` shows what is in effect).\n"
    "-->\n"
)


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
    for name, content in (
        (config.WORKSPACE_MARKER, MARKER_CONTENT),
        (".env", _env_template()),
        ("rules/local.md", LOCAL_RULES_STUB),
    ):
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
