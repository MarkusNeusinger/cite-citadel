"""Tests for an out-of-repo wiki/raw layout — e.g. a mounted network drive (no CLI, no network).

The user case: ``OKF_WIKI_DIR=T:\\21_llmWiki\\wiki`` / ``OKF_RAW_DIR=T:\\21_llmWiki\\raw`` while the
code is a normal checkout on another volume. These cover the full chain that used to assume
everything lives under ``REPO_ROOT``:

  * config key<->path helpers (the single source of truth) + env-override resolution;
  * the agent bridge (absolute paths in the prompt + ``--add-dir`` for claude / ``--include-
    directories`` for gemini, while the in-repo invocation stays unchanged);
  * resource validation against an absolute out-of-repo path;
  * source-citation matching (find/rewrite) with absolute keys;
  * and an END-TO-END ingest whose wiki/raw sit OUTSIDE the repo.

All filesystem state is redirected to tmp_path and ``llm.run_ingest_session`` is faked, so no real
CLI is ever spawned.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from okf_wiki import config, ingest, lint, llm, manifest, okf, store, validate


# --- config: the key<->path single source of truth -------------------------------------


def test_rel_or_abs_posix_relative_in_repo_absolute_outside(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "raw").mkdir(parents=True)
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)

    inside = repo / "raw" / "notes.md"
    outside = tmp_path / "net" / "raw" / "notes.md"
    outside.parent.mkdir(parents=True)

    assert config.rel_or_abs_posix(inside) == "raw/notes.md"            # repo-relative key
    assert config.rel_or_abs_posix(outside) == outside.resolve().as_posix()  # absolute key
    # No basename collapse: two out-of-repo files with the SAME name get DISTINCT keys.
    other = tmp_path / "net2" / "raw" / "notes.md"
    other.parent.mkdir(parents=True)
    assert config.rel_or_abs_posix(outside) != config.rel_or_abs_posix(other)


def test_source_path_for_key_inverts_rel_or_abs_posix(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)

    # repo-relative key -> under REPO_ROOT
    assert config.source_path_for_key("raw/notes.md") == repo / "raw" / "notes.md"
    # absolute key -> used as-is
    abs_key = (tmp_path / "net" / "raw" / "notes.md").resolve().as_posix()
    assert config.source_path_for_key(abs_key) == Path(abs_key)
    # round-trip both ways
    for p in (repo / "raw" / "x.md", tmp_path / "net" / "raw" / "y.md"):
        assert config.source_path_for_key(config.rel_or_abs_posix(p)) == p.resolve()


def test_is_outside_repo(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    assert config.is_outside_repo(tmp_path / "net" / "wiki") is True
    assert config.is_outside_repo(repo / "wiki") is False


def test_dir_setting_relative_against_repo_root_absolute_as_is(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)

    # A relative override resolves against the REPO ROOT, not the process CWD.
    monkeypatch.setenv("OKF_X_DIR", "wiki")
    assert config._dir_setting("OKF_X_DIR", repo / "default") == (repo / "wiki").resolve()

    # An absolute override is used as-is (so wiki/raw can live outside the repo).
    external = tmp_path / "net" / "wiki"
    monkeypatch.setenv("OKF_X_DIR", str(external))
    assert config._dir_setting("OKF_X_DIR", repo / "default") == external.resolve()

    # No override -> the default.
    monkeypatch.delenv("OKF_X_DIR", raising=False)
    assert config._dir_setting("OKF_X_DIR", repo / "default") == (repo / "default").resolve()


# --- the agent bridge: absolute paths + per-CLI external-dir access ---------------------


def _wire_external(tmp_path, monkeypatch):
    """REPO_ROOT on one subtree; wiki/raw on a SEPARATE 'net' subtree (a shared parent, as a
    mounted drive would have). Returns (repo, wiki, raw)."""
    repo = tmp_path / "repo"
    net = tmp_path / "net"          # stands in for T:\21_llmWiki
    wiki, raw, docs = net / "wiki", net / "raw", repo / "docs"
    for d in (repo, wiki, raw, docs):
        d.mkdir(parents=True, exist_ok=True)
    (repo / "SCHEMA.md").write_text("# SCHEMA\n", encoding="utf-8")

    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", docs, raising=False)
    monkeypatch.setattr(config, "SCHEMA_PATH", repo / "SCHEMA.md", raising=False)
    monkeypatch.setattr(config, "AGENT_RULES_PATH", repo / "AGENT_INGEST.md", raising=False)
    monkeypatch.setattr(config, "INDEX_PATH", wiki / "index.md", raising=False)
    monkeypatch.setattr(config, "LOG_PATH", wiki / "log.md", raising=False)
    monkeypatch.setattr(config, "MANIFEST_PATH", wiki / ".okf_ingested.json", raising=False)
    return repo, wiki, raw


def test_build_instruction_uses_absolute_paths_when_wiki_outside_repo(tmp_path, monkeypatch):
    """With the wiki/raw outside the repo, the agent prompt names them by ABSOLUTE path (not a
    bare 'wiki'/'raw' that the repo-root CWD can't find) and still stays tiny."""
    repo, wiki, raw = _wire_external(tmp_path, monkeypatch)
    abs_key = config.rel_or_abs_posix(raw / "notes.md")

    prompt = llm._build_instruction(abs_key)

    assert wiki.resolve().as_posix() in prompt   # absolute wiki path, not 'wiki/'
    assert raw.resolve().as_posix() in prompt    # absolute raw path
    assert abs_key in prompt                      # the absolute source key
    assert abs_key.startswith(tmp_path.resolve().as_posix())  # it really is absolute
    assert len(prompt) < 3000                     # paths + rule pointers, never file content (WinError 206 guard)


def test_external_dirs_lists_only_out_of_repo_dirs(tmp_path, monkeypatch):
    repo, wiki, raw = _wire_external(tmp_path, monkeypatch)   # docs is INSIDE the repo
    abs_key = config.rel_or_abs_posix(raw / "notes.md")

    dirs = llm._external_dirs(abs_key)

    assert str(wiki.resolve()) in dirs
    assert str(raw.resolve()) in dirs
    assert str((repo / "docs").resolve()) not in dirs   # in-repo docs needs no grant


def test_external_dirs_empty_for_in_repo_layout(tmp_path, monkeypatch):
    """The default in-repo layout grants nothing extra (so the invocation is unchanged)."""
    repo = tmp_path / "repo"
    for sub in ("wiki", "raw", "docs"):
        (repo / sub).mkdir(parents=True)
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", repo / "wiki", raising=False)
    monkeypatch.setattr(config, "RAW_DIR", repo / "raw", raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", repo / "docs", raising=False)

    assert llm._external_dirs("raw/notes.md") == []


def test_build_invocation_claude_adds_add_dir_for_external(monkeypatch):
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    dirs = ["/net/wiki", "/net/raw"]
    argv, stdin_text = llm._build_invocation("claude", "/bin/claude", "P", dirs)
    assert stdin_text == "P"
    joined = " ".join(argv)
    assert argv.count("--add-dir") == 2
    assert "--add-dir /net/wiki" in joined and "--add-dir /net/raw" in joined


def test_build_invocation_claude_no_add_dir_when_in_repo(monkeypatch):
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    argv, _ = llm._build_invocation("claude", "/bin/claude", "P", [])
    assert "--add-dir" not in argv                       # default layout: unchanged
    argv_default, _ = llm._build_invocation("claude", "/bin/claude", "P")
    assert "--add-dir" not in argv_default               # extra_dirs defaults to none


def test_build_invocation_gemini_includes_directories_only_when_external():
    argv, _ = llm._build_invocation("gemini", "/bin/gemini", "P", ["/net/wiki"])
    assert "--include-directories" in argv and "/net/wiki" in argv
    argv_in_repo, _ = llm._build_invocation("gemini", "/bin/gemini", "P", [])
    assert "--include-directories" not in argv_in_repo   # in-repo argv unchanged


# --- resource validation against an absolute out-of-repo path ---------------------------


def test_validate_resource_absolute_out_of_repo(tmp_path, monkeypatch):
    repo, wiki, raw = _wire_external(tmp_path, monkeypatch)
    (raw / "notes.md").write_text("src\n", encoding="utf-8")
    abs_key = config.rel_or_abs_posix(raw / "notes.md")

    fm = {"type": "Concept", "title": "T", "description": "d", "tags": ["ml"], "resource": abs_key}
    body = (
        "A fact.[^s1]\n\n## Sources\n\n"
        f"[^s1]: [{abs_key}](../../raw/notes.md) - n (ingested 2026-06-21)\n"
    )
    issues = validate.validate_page("concepts/transformer.md", fm, body)
    assert [i for i in issues if i.category == "bad_resource"] == []   # absolute resource accepted

    # A missing absolute resource is still flagged.
    fm_missing = dict(fm, resource=config.rel_or_abs_posix(raw / "ghost.md"))
    issues2 = validate.validate_page("concepts/transformer.md", fm_missing, body)
    assert any(i.category == "bad_resource" for i in issues2)


# --- source-citation matching with absolute keys ----------------------------------------


def test_find_and_rewrite_raw_references_with_absolute_keys(tmp_path, monkeypatch):
    repo, wiki, raw = _wire_external(tmp_path, monkeypatch)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")
    abs_key = config.rel_or_abs_posix(raw / "notes.md")

    page = wiki / "concepts" / "t.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        okf.dump(
            {"type": "Concept", "title": "T", "description": "d", "tags": ["x"], "resource": abs_key},
            "A fact.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{abs_key}](../../raw/notes.md) - n\n",
        ),
        encoding="utf-8",
    )

    # find: matches via BOTH the absolute resource frontmatter and the relative citation link.
    assert store.find_raw_references(abs_key) == ["concepts/t.md"]

    # rewrite: a move to a new absolute key repoints resource + citation to a valid relative link.
    (raw / "ml").mkdir()
    new_key = config.rel_or_abs_posix(raw / "ml" / "notes.md")
    changed = store.rewrite_raw_references(abs_key, new_key)
    assert changed == ["concepts/t.md"]
    text = page.read_text(encoding="utf-8")
    assert f"resource: {new_key}" in text
    assert "(../../raw/ml/notes.md)" in text          # recomputed relative citation
    assert "(../../raw/notes.md)" not in text
    assert store.find_raw_references(abs_key) == []   # nothing points at the old key anymore


# --- END-TO-END: ingest with wiki/raw OUTSIDE the repo ----------------------------------


def _fake_session(rel_key, kind="ingest"):
    """Write one Concept page (as the agent would) into the configured WIKI_DIR, citing the raw
    file by its real RELATIVE path and recording the (possibly absolute) source key as resource."""
    target = config.WIKI_DIR / "concepts" / "transformer.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    rel_link = os.path.relpath(
        config.source_path_for_key(rel_key), config.WIKI_DIR / "concepts"
    ).replace(os.sep, "/")
    target.write_text(
        okf.dump(
            {
                "type": "Concept",
                "title": "Transformer",
                "description": "self-attention model",
                "tags": ["ml"],
                "resource": rel_key,
            },
            "Transformers use self-attention.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{rel_key}]({rel_link}) - notes (ingested 2026-06-21)\n",
        ),
        encoding="utf-8",
    )


def test_ingest_end_to_end_with_wiki_raw_outside_repo(tmp_path, monkeypatch):
    repo, wiki, raw = _wire_external(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", _fake_session)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    abs_key = config.rel_or_abs_posix(raw / "notes.md")
    assert report.processed == [abs_key]            # keyed by absolute path, no collision/basename
    assert not report.errors
    assert report.broken_links == []

    # The page was written to the NET wiki, not a repo/wiki.
    page = wiki / "concepts" / "transformer.md"
    assert page.exists()
    assert not (repo / "wiki").exists()
    text = page.read_text(encoding="utf-8")
    assert f"resource: {abs_key}" in text           # absolute resource survives validate+restamp
    assert "timestamp:" in text                      # system re-stamped it
    assert "(../../raw/notes.md)" in text            # valid relative citation across the net dir

    # Derived files + manifest live next to the (out-of-repo) wiki.
    assert "transformer.md" in (wiki / "index.md").read_text(encoding="utf-8")
    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert abs_key in data

    # Whole-wiki health check is clean, and re-running is a no-op (idempotent on the abs key).
    assert lint.lint().ok() and lint.lint().bad_sources == []
    assert ingest.ingest().processed == []


def test_ingest_deletes_out_of_repo_source(tmp_path, monkeypatch):
    """A tracked out-of-repo source that vanished from the drive is detected (existence check via
    source_path_for_key) and its provenance reconciled out — exercising find_raw_references on an
    absolute key for both the resource and the citation link."""
    repo, wiki, raw = _wire_external(tmp_path, monkeypatch)
    abs_key = config.rel_or_abs_posix(raw / "notes.md")   # never created -> "deleted" on disk

    page = wiki / "concepts" / "topic.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(
        okf.dump(
            {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": abs_key},
            "A fact.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{abs_key}](../../raw/notes.md) - n\n",
        ),
        encoding="utf-8",
    )
    manifest.save({abs_key: "deadbeef"})

    calls: list[tuple[str, str]] = []

    def fake_delete(rel_key, kind="ingest"):
        calls.append((rel_key, kind))
        (config.WIKI_DIR / "concepts" / "topic.md").unlink()

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_delete)

    report = ingest.ingest()

    assert calls == [(abs_key, "delete")]             # a delete-cleanup session for the abs key
    assert report.sources_deleted == [abs_key]
    assert not (wiki / "concepts" / "topic.md").exists()
    assert not report.errors
    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert abs_key not in data                         # manifest key dropped
