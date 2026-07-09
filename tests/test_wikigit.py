"""The wiki-history layer (:mod:`citadel.wikigit`): auto-commit the wiki after mutating runs.

Pure-logic paths (mode off, missing binary, note plumbing) run hermetically; everything that
exercises real git is guarded by ``needs_git`` (the :mod:`tests.test_repo` pattern) and stays
offline — the only "remote" ever pushed to is a local bare repository.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from citadel import config, ingest, wikigit


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _run_git(cwd: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)
    return proc.stdout.strip()


def _init_repo(root: Path) -> None:
    _run_git(root, "init", "-q")
    _run_git(root, "config", "user.email", "t@t.t")
    _run_git(root, "config", "user.name", "t")
    _run_git(root, "config", "commit.gpgsign", "false")


def _commit_count(root: Path) -> int:
    return int(_run_git(root, "rev-list", "--count", "HEAD"))


@pytest.fixture
def wiki_git_mode(monkeypatch):
    """Set the layer's mode/remote (config is read at call time, like every other knob)."""

    def _set(mode: str, remote: str = "") -> None:
        monkeypatch.setattr(config, "WIKI_GIT", mode, raising=False)
        monkeypatch.setattr(config, "WIKI_GIT_REMOTE", remote, raising=False)

    return _set


# --- mode gating (hermetic — no git needed) ---------------------------------------------------


def test_off_mode_never_touches_git(tmp_citadel, wiki_git_mode):
    wiki_git_mode("off")
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")
    assert wikigit.autocommit("msg") is None
    assert not (tmp_citadel.wiki / ".git").exists()


def test_missing_wiki_dir_is_a_silent_noop(tmp_citadel, wiki_git_mode, monkeypatch):
    wiki_git_mode("init")
    monkeypatch.setattr(config, "WIKI_DIR", tmp_citadel.root / "nope", raising=False)
    assert wikigit.autocommit("msg") is None


def test_missing_git_binary(tmp_citadel, wiki_git_mode, monkeypatch):
    """auto stays silent without a git binary; an explicit opt-in earns a skip note."""
    monkeypatch.setattr(wikigit.shutil, "which", lambda name: None)
    wiki_git_mode("auto")
    assert wikigit.autocommit("msg") is None
    wiki_git_mode("init")
    note = wikigit.autocommit("msg")
    assert note is not None and "git not found" in note


# --- auto mode: opt-in via an existing repo ---------------------------------------------------


@needs_git
def test_auto_mode_noop_when_wiki_is_not_its_own_repo(tmp_citadel, wiki_git_mode):
    wiki_git_mode("auto")
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")
    assert wikigit.autocommit("msg") is None
    assert not (tmp_citadel.wiki / ".git").exists()  # auto NEVER creates a repo


@needs_git
def test_auto_mode_commits_in_an_own_repo(tmp_citadel, wiki_git_mode):
    wiki_git_mode("auto")
    _init_repo(tmp_citadel.wiki)
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")

    note = wikigit.autocommit("citadel ingest: test run")

    assert note is not None and note.startswith("wiki git: committed")
    assert _commit_count(tmp_citadel.wiki) == 1
    assert _run_git(tmp_citadel.wiki, "log", "-1", "--format=%s") == "citadel ingest: test run"
    assert _run_git(tmp_citadel.wiki, "status", "--porcelain") == ""


@needs_git
def test_clean_tree_is_a_silent_noop(tmp_citadel, wiki_git_mode):
    wiki_git_mode("auto")
    _init_repo(tmp_citadel.wiki)
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")
    assert wikigit.autocommit("first") is not None
    assert wikigit.autocommit("second") is None  # nothing changed since the first commit
    assert _commit_count(tmp_citadel.wiki) == 1


@needs_git
def test_commit_identity_falls_back_when_none_is_configured(tmp_citadel, wiki_git_mode, monkeypatch):
    """A fresh container/CI box has no git identity; the commit must still land (with the
    cite-citadel fallback identity) instead of silently disabling the history layer."""
    # Hide any real global/system config so `git config user.email` genuinely resolves to nothing.
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_citadel.root / "no-such-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_citadel.root / "no-such-system"))
    wiki_git_mode("auto")
    _run_git(tmp_citadel.wiki, "init", "-q")
    _run_git(tmp_citadel.wiki, "config", "commit.gpgsign", "false")
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")

    note = wikigit.autocommit("msg")

    assert note is not None and note.startswith("wiki git: committed")
    assert _run_git(tmp_citadel.wiki, "log", "-1", "--format=%ae") == "citadel@localhost"


@needs_git
def test_commit_identity_fallback_fills_only_the_missing_half(tmp_citadel, wiki_git_mode, monkeypatch):
    """A partially-configured identity (email set, name missing) must also commit — git requires
    BOTH halves — and the configured half wins over the fallback."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_citadel.root / "no-such-gitconfig"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_citadel.root / "no-such-system"))
    wiki_git_mode("auto")
    _run_git(tmp_citadel.wiki, "init", "-q")
    _run_git(tmp_citadel.wiki, "config", "commit.gpgsign", "false")
    _run_git(tmp_citadel.wiki, "config", "user.email", "me@example.com")  # email set, name missing
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")

    note = wikigit.autocommit("msg")

    assert note is not None and note.startswith("wiki git: committed")
    assert _run_git(tmp_citadel.wiki, "log", "-1", "--format=%an") == "cite-citadel"  # fallback name
    assert _run_git(tmp_citadel.wiki, "log", "-1", "--format=%ae") == "me@example.com"  # configured email kept


# --- init mode: first-use `git init`, embedded-repo refusal -----------------------------------


@needs_git
def test_init_mode_creates_the_repo_and_gitignore(tmp_citadel, wiki_git_mode):
    wiki_git_mode("init")
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")

    note = wikigit.autocommit("msg")

    assert note is not None and note.startswith("wiki git: committed")
    assert (tmp_citadel.wiki / ".git").is_dir()
    assert ".citadel_viewer.html" in (tmp_citadel.wiki / ".gitignore").read_text(encoding="utf-8")
    assert _commit_count(tmp_citadel.wiki) == 1


@needs_git
def test_init_mode_refuses_an_embedded_repo(tmp_citadel, wiki_git_mode):
    """A wiki dir INSIDE another git working tree (the dev checkout, a project repo, a committed
    corpus wiki) must never grow a nested .git behind the user's back."""
    wiki_git_mode("init")
    _init_repo(tmp_citadel.root)  # the WORKSPACE is a git repo; wiki/ sits inside it
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")

    note = wikigit.autocommit("msg")

    assert note is not None and "refusing" in note
    assert not (tmp_citadel.wiki / ".git").exists()


@needs_git
def test_repo_state_classification(tmp_citadel):
    assert wikigit.repo_state(tmp_citadel.wiki) == wikigit.ABSENT
    _init_repo(tmp_citadel.root)
    assert wikigit.repo_state(tmp_citadel.wiki) == wikigit.NESTED
    _init_repo(tmp_citadel.wiki)
    assert wikigit.repo_state(tmp_citadel.wiki) == wikigit.REPO


# --- push (offline: a local bare repository stands in for GitHub/GitLab) ----------------------


@needs_git
def test_push_to_a_configured_remote(tmp_citadel, wiki_git_mode, tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    wiki_git_mode("init", remote=str(bare))
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")

    note = wikigit.autocommit("msg")

    assert note is not None and f"pushed to {bare}" in note
    assert int(_run_git(bare, "rev-list", "--count", "--all")) == 1


@needs_git
def test_push_failure_is_a_note_never_an_error(tmp_citadel, wiki_git_mode, tmp_path):
    wiki_git_mode("init", remote=str(tmp_path / "no-such-remote.git"))
    (tmp_citadel.wiki / "page.md").write_text("x\n", encoding="utf-8")

    note = wikigit.autocommit("msg")

    assert note is not None and note.startswith("wiki git: committed")
    assert "push" in note and "failed" in note
    assert _commit_count(tmp_citadel.wiki) == 1  # the local commit still landed


# --- wiring: ingest commits the run as ONE diff -----------------------------------------------


@needs_git
def test_ingest_autocommits_the_run(tmp_citadel, fake_agent, transformer_page, wiki_git_mode):
    wiki_git_mode("init")
    fake_agent(transformer_page)
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    assert not report.errors
    assert report.wiki_git.startswith("wiki git: committed")
    assert report.wiki_git in report.render()
    # ONE commit captures the complete run state: the page AND the regenerated log/index.
    files = _run_git(tmp_citadel.wiki, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert "concepts/transformer.md" in files
    assert "log.md" in files
    assert "index.md" in files


@needs_git
def test_promote_preserves_a_fresh_wiki_repo(tmp_citadel, fake_agent, transformer_page, wiki_git_mode):
    """Regression: _promote's empty-directory sweep must exempt hidden trees. A FRESH `git init`ed
    wiki repo holds empty dirs (`.git/objects`, `.git/refs/heads`) — pruning them corrupts the
    repository, so the very first auto-mode ingest after opting in would find a broken repo."""
    wiki_git_mode("auto")
    _init_repo(tmp_citadel.wiki)  # brand-new repo, no commits yet
    fake_agent(transformer_page)
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    assert not report.errors
    assert report.wiki_git.startswith("wiki git: committed")
    assert _commit_count(tmp_citadel.wiki) == 1


@needs_git
def test_curate_autocommits_applied_clusters(tmp_citadel, seed_page, fake_agent, wiki_git_mode):
    from citadel import curate

    wiki_git_mode("init")
    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    fm = {"type": "Person", "title": "Alice", "description": "d", "tags": ["t"], "resource": "raw/notes.md"}
    body = "Fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - s\n"
    seed_page("concepts/alice.md", fm, body)  # a Person mis-filed under concepts/ -> a resort cluster
    fake_agent(pages={"concepts/alice.md": (fm, body.replace("Fact.", "Improved fact."))})

    report = curate.curate()

    assert report.applied
    assert report.wiki_git.startswith("wiki git: committed")
    assert report.wiki_git in report.render()
    assert (tmp_citadel.wiki / ".git").is_dir()


def test_ingest_report_omits_the_note_when_layer_is_off(tmp_citadel, fake_agent, transformer_page, wiki_git_mode):
    wiki_git_mode("off")
    fake_agent(transformer_page)
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    assert not report.errors
    assert report.wiki_git == ""
    assert "wiki git" not in report.render()
