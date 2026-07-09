"""Optional wiki HISTORY layer: auto-commit the wiki directory after every mutating run.

The wiki is plain markdown files, so git is the natural long-term changelog: after each ingest or
curate run that changed pages, :func:`autocommit` stages and commits EVERYTHING under
``config.WIKI_DIR`` (pages, the regenerated indexes, ``log.md``, the manifest) so every run is one
reviewable diff — what changed, in which page, attributable to the run that did it. An optional
remote (``CITADEL_WIKI_GIT_REMOTE`` — a name or URL, GitHub/GitLab/anything) is pushed to after
each commit.

Design rules (all load-bearing):

- **Never raises, never fails the run.** By the time autocommit runs the wiki is already promoted;
  a git problem (no binary, no identity, a rejected push) becomes a one-line note on the report.
- **Never creates a repository behind the user's back.** The default mode (``auto``) only commits
  when the wiki dir is already ITS OWN repo (holds a ``.git``). ``CITADEL_WIKI_GIT=1`` opts into a
  first-use ``git init`` — but even then a wiki dir sitting INSIDE another git working tree is
  refused (an embedded repo would confuse the outer checkout: the dev workspace, a corpus wiki
  committed to this repo, a wiki inside a project repo). ``git init`` it yourself to overrule.
- **Bounded git calls** (like :mod:`citadel.repo`): a hung git must never hang an ingest run.

Config is read at call time (``config.WIKI_GIT`` / ``config.WIKI_GIT_REMOTE`` / ``config.WIKI_DIR``)
so tests monkeypatch it like everything else.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from . import config


# Bounded git calls. Local operations are near-instant; the push talks to a network and gets the
# same generous-but-finite budget the LLM-adjacent network operations use.
_GIT_TIMEOUT_S = 60
_PUSH_TIMEOUT_S = 300

# Commit identity fallback when the machine has none configured (a fresh container/CI box):
# `git commit` refuses to guess, which would silently disable the whole history layer.
_FALLBACK_NAME = "cite-citadel"
_FALLBACK_EMAIL = "citadel@localhost"

# Scaffolded into a freshly-initialized wiki repo: the offline viewer artifact is generated,
# large, and rebuilt wholesale — history noise, never worth versioning.
_GITIGNORE_BODY = ".citadel_viewer.html\n"

REPO = "repo"  # the wiki dir is its own git repository (holds a .git)
NESTED = "nested"  # no own .git, but sits inside another git working tree
ABSENT = "absent"  # no git repository anywhere up the tree


def _git(cwd: Path, *args: str, timeout: int = _GIT_TIMEOUT_S) -> tuple[int, str] | None:
    """Run ``git -C <cwd> <args>``; return ``(returncode, combined output)`` or None when git is
    missing or the call itself failed to run (OSError/timeout). Never raises."""
    git = shutil.which("git")
    if not git:
        return None
    try:
        proc = subprocess.run(
            [git, "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()


def _brief(output: str) -> str:
    """The last non-empty line of a git error, bounded — enough to say WHY without dumping a page."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    tail = lines[-1] if lines else "unknown error"
    return tail if len(tail) <= 200 else tail[:197] + "..."


def repo_state(wiki_dir: Path) -> str:
    """Classify ``wiki_dir``: :data:`REPO` (its own repo — a ``.git`` dir, or a ``.git`` file for a
    linked worktree/submodule), :data:`NESTED` (inside another git working tree), or
    :data:`ABSENT`. NESTED vs ABSENT needs the git binary; without one everything non-REPO reads
    as ABSENT, which is safe — no mode ever inits or commits without the binary."""
    wiki_dir = Path(wiki_dir)
    if (wiki_dir / ".git").exists():
        return REPO
    res = _git(wiki_dir, "rev-parse", "--show-toplevel")
    if res is not None and res[0] == 0 and res[1]:
        return NESTED
    return ABSENT


def _identity_args(wiki_dir: Path) -> list[str]:
    """``-c user.name/user.email`` fallbacks when no commit identity is configured, else []."""
    res = _git(wiki_dir, "config", "user.email")
    if res is not None and res[0] == 0 and res[1]:
        return []
    return ["-c", f"user.name={_FALLBACK_NAME}", "-c", f"user.email={_FALLBACK_EMAIL}"]


def autocommit(message: str) -> str | None:
    """Commit every change under ``config.WIKI_DIR`` as one commit with ``message``; push to
    ``config.WIKI_GIT_REMOTE`` when set. Returns a one-line human note for the run report
    ("wiki git: committed <sha>", or a warning describing what was skipped and why) — or None when
    there is nothing to say (mode off, no repo in auto mode, or a clean tree). NEVER raises: the
    wiki is already promoted when this runs, so a git problem must never fail the run."""
    mode = config.WIKI_GIT
    if mode == "off":
        return None
    wiki_dir = Path(config.WIKI_DIR)
    if not wiki_dir.is_dir():
        return None
    if shutil.which("git") is None:
        # Only worth a note when the user explicitly opted in; auto mode stays silent.
        return "wiki git: git not found on PATH; wiki history skipped" if mode == "init" else None

    state = repo_state(wiki_dir)
    if state != REPO:
        if mode != "init":
            return None  # auto mode: history is opt-in until the wiki dir is its own repo
        if state == NESTED:
            return (
                f"wiki git: {wiki_dir} sits inside another git working tree; refusing to init an "
                "embedded repo (run `git init` there yourself to overrule)"
            )
        res = _git(wiki_dir, "init", "-q")
        if res is None or res[0] != 0:
            return f"wiki git: `git init` failed; wiki history skipped ({_brief(res[1]) if res else 'git error'})"
        gitignore = wiki_dir / ".gitignore"
        if not gitignore.exists():
            try:
                gitignore.write_text(_GITIGNORE_BODY, encoding="utf-8")
            except OSError:
                pass  # cosmetic — the viewer artifact merely becomes a tracked file

    res = _git(wiki_dir, "add", "-A")
    if res is None or res[0] != 0:
        return f"wiki git: `git add` failed; commit skipped ({_brief(res[1]) if res else 'git error'})"
    res = _git(wiki_dir, "status", "--porcelain")
    if res is None or res[0] != 0:
        return f"wiki git: `git status` failed; commit skipped ({_brief(res[1]) if res else 'git error'})"
    if not res[1]:
        return None  # clean tree — this run changed nothing git doesn't already have

    res = _git(wiki_dir, *_identity_args(wiki_dir), "commit", "-q", "-m", message)
    if res is None or res[0] != 0:
        return f"wiki git: commit failed ({_brief(res[1]) if res else 'git error'})"
    sha = _git(wiki_dir, "rev-parse", "--short", "HEAD")
    note = f"wiki git: committed {sha[1]}" if sha is not None and sha[0] == 0 and sha[1] else "wiki git: committed"

    remote = config.WIKI_GIT_REMOTE
    if remote:
        res = _git(wiki_dir, "push", "--quiet", remote, "HEAD", timeout=_PUSH_TIMEOUT_S)
        if res is not None and res[0] == 0:
            note += f", pushed to {remote}"
        else:
            note += f"; push to {remote} failed ({_brief(res[1]) if res else 'git error'})"
    return note
