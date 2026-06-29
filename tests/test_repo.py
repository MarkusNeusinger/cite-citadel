"""Tests for git-repository sources: detection, the digest builder, commit identity, and the
end-to-end ingest of a repo as ONE source (offline — ``llm.run_ingest_session`` is faked).

The hermetic tests use the opt-in ``.okfsource`` marker so they need no ``git`` binary; the
git-specific behavior (commit identity, ``.gitignore`` filtering, diff-based reconcile) is in a
small set of tests guarded by ``shutil.which("git")``.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from okf_wiki import config, ingest, lint, manifest, okf, repo, store


# --------------------------------------------------------------------------------------------
# wiring + fakes
# --------------------------------------------------------------------------------------------

_CALLS: dict[str, object] = {"n": 0, "kinds": []}


def _wire(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Redirect config paths at a fresh tmp wiki/raw and force repo support on. Return (wiki, raw)."""
    _CALLS["n"] = 0
    _CALLS["kinds"] = []
    repo_root = tmp_path
    wiki = repo_root / "wiki"
    raw = repo_root / "raw"
    docs = repo_root / "docs"
    for d in (wiki, raw, docs):
        d.mkdir(parents=True, exist_ok=True)
    (repo_root / "SCHEMA.md").write_text("# SCHEMA\n\ntest\n", encoding="utf-8")
    monkeypatch.setattr(config, "REPO_ROOT", repo_root, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", docs, raising=False)
    monkeypatch.setattr(config, "SCHEMA_PATH", repo_root / "SCHEMA.md", raising=False)
    monkeypatch.setattr(config, "AGENT_RULES_PATH", repo_root / "AGENT_INGEST.md", raising=False)
    monkeypatch.setattr(config, "INDEX_PATH", wiki / "index.md", raising=False)
    monkeypatch.setattr(config, "LOG_PATH", wiki / "log.md", raising=False)
    monkeypatch.setattr(config, "MANIFEST_PATH", wiki / ".okf_ingested.json", raising=False)
    monkeypatch.setattr(config, "REPO_SUPPORT", True, raising=False)
    return wiki, raw


def _write_page(rel_path: str, frontmatter: dict, body: str) -> None:
    target = config.WIKI_DIR / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def fake_session(rel_key, kind="ingest", read_path=None):
    """Stand-in for one agent session. For a normal/repo ingest it writes a page citing ``rel_key``
    (and, for a repo, a ``type: System`` page so the new category is exercised). For a ``delete``
    cleanup it removes every page that references ``rel_key`` — enough to satisfy the post-condition.
    The relative citation link reaches the source via ``../../`` + the source key (a repo key points
    at the folder)."""
    _CALLS["n"] = int(_CALLS["n"]) + 1
    _CALLS["kinds"].append((rel_key, kind))  # type: ignore[union-attr]

    if kind == "delete":
        for rel in store.find_raw_references(rel_key):
            (config.WIKI_DIR / rel).unlink(missing_ok=True)
        return

    slug = rel_key.replace("raw/", "").replace("/", "-").replace(".", "-") or "source"
    link = "../../" + rel_key
    _write_page(
        f"concepts/{slug}.md",
        {
            "type": "Concept",
            "title": slug.replace("-", " ").title(),
            "description": "a source",
            "tags": ["x"],
            "resource": rel_key,
        },
        f"It does a thing.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}]({link}) - note (ingested 2026-06-21)\n",
    )
    if kind in ("repo", "repo-reconcile"):
        _write_page(
            "systems/acme-db.md",
            {
                "type": "System",
                "title": "Acme DB",
                "description": "the database the repo writes to",
                "tags": ["database"],
                "resource": rel_key,
            },
            f"The repo loads data into Acme DB.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{rel_key}]({link}) - note (ingested 2026-06-21)\n",
        )


def _make_repo(raw: Path, name: str, files: dict[str, str], marker: bool = True) -> Path:
    """Create a folder under raw/ with the given files; add the ``.okfsource`` marker so it is
    treated as one repo source without needing git."""
    root = raw / name
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    if marker:
        (root / repo.MARKER).write_text("", encoding="utf-8")
    return root


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def _git_init(root: Path) -> None:
    _run_git(root, "init", "-q")
    _run_git(root, "config", "user.email", "t@t.t")
    _run_git(root, "config", "user.name", "t")
    _run_git(root, "config", "commit.gpgsign", "false")


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


# --------------------------------------------------------------------------------------------
# pure unit tests — detection, scoring, exclusion (no git, no ingest)
# --------------------------------------------------------------------------------------------


def test_is_repo_dir_detects_git_and_marker(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert not repo.is_repo_dir(plain)

    marked = tmp_path / "marked"
    marked.mkdir()
    (marked / repo.MARKER).write_text("", encoding="utf-8")
    assert repo.is_repo_dir(marked)
    assert not repo.is_git_repo(marked)

    gitdir = tmp_path / "g"
    (gitdir / ".git").mkdir(parents=True)
    assert repo.is_git_repo(gitdir)
    assert repo.is_repo_dir(gitdir)

    # a .git FILE (submodule / linked worktree) also counts
    gitfile = tmp_path / "gf"
    gitfile.mkdir()
    (gitfile / ".git").write_text("gitdir: ../x\n", encoding="utf-8")
    assert repo.is_git_repo(gitfile)


def test_score_ranks_transform_core_highest():
    assert repo._score("src/transform/mapping.py") == 5
    assert repo._score("db/migrations/001.sql") == 5
    assert repo._score("README.md") == 4
    assert repo._score("pyproject.toml") == 4
    assert repo._score("config.yaml") == 3
    assert repo._score("main.py") == 3
    assert repo._score("util.py") == 2
    assert repo._score("CHANGES.txt") == 1
    assert repo._score("logo.png") == 0


def test_is_excluded_drops_lockfiles_and_vendored():
    assert repo._is_excluded("package-lock.json")
    assert repo._is_excluded("app.min.js")
    assert repo._is_excluded("bundle.js.map")
    assert repo._is_excluded("node_modules/x/index.js")
    assert not repo._is_excluded("src/app.py")


def test_list_files_fallback_skips_junk(tmp_path):
    root = _make_repo(
        tmp_path,
        "r",
        {
            "app.py": "x\n",
            "node_modules/dep/index.js": "junk\n",
            "dist/bundle.js": "junk\n",
            "sub/util.py": "y\n",
        },
    )
    files = repo.list_files(root)
    assert "app.py" in files and "sub/util.py" in files
    assert not any(f.startswith("node_modules/") or f.startswith("dist/") for f in files)


# --------------------------------------------------------------------------------------------
# build_digest — budget, truncation, selection
# --------------------------------------------------------------------------------------------


def test_build_digest_includes_header_and_listing(tmp_path):
    root = _make_repo(tmp_path, "svc", {"README.md": "# Svc\n", "app.py": "print(1)\n"})
    digest = repo.build_digest(root, "raw/svc")
    assert "# Repository digest: raw/svc" in digest
    assert "commit/version: snap." in digest
    assert "## Files" in digest
    assert "### README.md" in digest
    assert "### app.py" in digest


def test_build_digest_truncates_long_file(tmp_path):
    root = _make_repo(tmp_path, "big", {"huge.py": "a" * 5000})
    digest = repo.build_digest(root, "raw/big", per_file_chars=100)
    assert "... [truncated]" in digest


def test_build_digest_respects_budget_and_prioritizes_signal(tmp_path):
    root = _make_repo(
        tmp_path,
        "p",
        {"transform.py": "T" * 400, "notes.txt": "N" * 400},
    )
    # Budget large enough for ~one inlined file: the high-signal transform wins, notes is omitted.
    digest = repo.build_digest(root, "raw/p", max_chars=900, per_file_chars=2000)
    assert "### transform.py" in digest
    assert "### notes.txt" not in digest
    assert "## Omitted" in digest and "notes.txt" in digest


def test_build_digest_never_exceeds_budget(tmp_path):
    # Several large, high-signal files plus a big change summary against a tight budget: the digest
    # must still honor max_chars exactly (header, listing, and every file block are all bounded).
    files = {f"transform_{i}.py": ("X" * 4000) for i in range(6)}
    files["README.md"] = "Y" * 4000
    root = _make_repo(tmp_path, "big", files)
    summary = "Changed files:\n" + "\n".join(f"transform_{i}.py" for i in range(6)) * 50
    digest = repo.build_digest(
        root, "raw/big", max_chars=3000, per_file_chars=2000, change_summary=summary
    )
    assert len(digest) <= 3000
    assert "# Repository digest: raw/big" in digest


def test_build_digest_first_file_block_is_bounded(tmp_path):
    # A single file far larger than the budget must not slip through whole — the cap holds.
    root = _make_repo(tmp_path, "one", {"transform.py": "Z" * 50000})
    digest = repo.build_digest(root, "raw/one", max_chars=1500, per_file_chars=40000)
    assert len(digest) <= 1500


def test_build_digest_only_restricts_to_changed(tmp_path):
    root = _make_repo(tmp_path, "c", {"a.py": "A\n", "b.py": "B\n"})
    digest = repo.build_digest(root, "raw/c", only=["a.py"], change_summary="Changed files:\na.py")
    assert "### a.py" in digest
    assert "### b.py" not in digest
    assert "What changed" in digest


def test_identity_snapshot_changes_with_content(tmp_path):
    root = _make_repo(tmp_path, "s", {"a.py": "one\n"})
    id1 = repo.identity(root)
    assert id1.startswith("snap.")
    (root / "a.py").write_text("two\n", encoding="utf-8")
    id2 = repo.identity(root)
    assert id2.startswith("snap.") and id1 != id2


# --------------------------------------------------------------------------------------------
# git-specific behavior (skipped when git is absent)
# --------------------------------------------------------------------------------------------


@needs_git
def test_identity_is_head_commit(tmp_path):
    root = tmp_path / "g"
    root.mkdir()
    _git_init(root)
    (root / "a.py").write_text("x\n", encoding="utf-8")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-qm", "init")
    head = repo.head_commit(root)
    assert head and len(head) == 40
    assert repo.identity(root) == head


@needs_git
def test_list_files_honors_gitignore(tmp_path):
    root = tmp_path / "g"
    root.mkdir()
    _git_init(root)
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / "kept.py").write_text("x\n", encoding="utf-8")
    (root / "ignored.txt").write_text("secret\n", encoding="utf-8")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-qm", "init")
    files = repo.list_files(root)
    assert "kept.py" in files
    assert "ignored.txt" not in files


@needs_git
def test_list_files_includes_untracked_non_ignored(tmp_path):
    root = tmp_path / "g"
    root.mkdir()
    _git_init(root)
    (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    (root / "committed.py").write_text("x\n", encoding="utf-8")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-qm", "init")
    # New, uncommitted, NOT ignored -> a dirty tree that re-ingest would trigger; must be in the list.
    (root / "new_pipeline.py").write_text("y\n", encoding="utf-8")
    (root / "ignored.txt").write_text("secret\n", encoding="utf-8")
    files = repo.list_files(root)
    assert "committed.py" in files
    assert "new_pipeline.py" in files
    assert "ignored.txt" not in files


@needs_git
def test_changed_files_diffs_commits(tmp_path):
    root = tmp_path / "g"
    root.mkdir()
    _git_init(root)
    (root / "a.py").write_text("x\n", encoding="utf-8")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-qm", "one")
    first = repo.head_commit(root)
    (root / "b.py").write_text("y\n", encoding="utf-8")
    _run_git(root, "add", "-A")
    _run_git(root, "commit", "-qm", "two")
    changed = repo.changed_files(root, first)
    assert changed == ["b.py"]


# --------------------------------------------------------------------------------------------
# ingest integration — a repo is ONE source (hermetic via .okfsource)
# --------------------------------------------------------------------------------------------


def test_repo_ingested_as_one_source_not_per_file(tmp_path, monkeypatch):
    wiki, raw = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session)
    _make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n", "etl/load.py": "y\n"})
    (raw / "loose.md").write_text("a loose note\n", encoding="utf-8")

    report = ingest.ingest()

    assert "raw/svc" in report.processed
    assert "raw/loose.md" in report.processed
    # The repo's individual files are NOT separate sources.
    assert "raw/svc/app.py" not in report.processed
    assert "raw/svc/etl/load.py" not in report.processed
    # One session for the repo + one for the loose file.
    assert int(_CALLS["n"]) == 2


def test_repo_manifest_entry_is_commit_keyed(tmp_path, monkeypatch):
    wiki, raw = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session)
    _make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})

    ingest.ingest()
    m = manifest.load()
    assert "raw/svc" in m
    assert manifest.is_repo_entry(m["raw/svc"])
    assert manifest.entry_commit(m["raw/svc"]).startswith("snap.")

    # Re-running with no change is a no-op (idempotent).
    _CALLS["n"] = 0
    second = ingest.ingest()
    assert second.processed == []
    assert int(_CALLS["n"]) == 0


def test_repo_creates_system_category_page(tmp_path, monkeypatch):
    wiki, raw = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session)
    _make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})

    ingest.ingest()
    assert (wiki / "systems" / "acme-db.md").exists()
    assert okf.folder_for_type("System") == "systems"
    # The wiki stays healthy (System page validates, citations resolve to the repo folder).
    assert lint.lint().ok()


def test_repo_reingested_on_change(tmp_path, monkeypatch):
    wiki, raw = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session)
    root = _make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})

    ingest.ingest()
    before = manifest.entry_commit(manifest.load()["raw/svc"])

    # Change a file -> the snapshot identity changes -> a repo-reconcile session runs.
    (root / "app.py").write_text("changed\n", encoding="utf-8")
    _CALLS["kinds"] = []
    report = ingest.ingest()

    assert "raw/svc" in report.processed
    assert ("raw/svc", "repo-reconcile") in _CALLS["kinds"]  # type: ignore[operator]
    after = manifest.entry_commit(manifest.load()["raw/svc"])
    assert before != after


def test_repo_deletion_reconciles_citations(tmp_path, monkeypatch):
    wiki, raw = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session)
    root = _make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"})

    ingest.ingest()
    assert "raw/svc" in manifest.load()

    # Remove the whole repo folder; a full run detects the vanished source and cleans it out.
    shutil.rmtree(root)
    report = ingest.ingest()

    assert "raw/svc" in report.sources_deleted
    assert "raw/svc" not in manifest.load()
    assert store.find_raw_references("raw/svc") == []


def test_repo_support_off_falls_back_to_per_file(tmp_path, monkeypatch):
    wiki, raw = _wire(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "REPO_SUPPORT", False, raising=False)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session)
    _make_repo(raw, "svc", {"README.md": "# Svc\n", "app.py": "x\n"}, marker=True)

    report = ingest.ingest()
    # With repo support off, the marker is meaningless: files are ingested individually.
    assert "raw/svc/README.md" in report.processed
    assert "raw/svc/app.py" in report.processed
    assert "raw/svc" not in report.processed
