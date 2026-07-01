"""Tests for an out-of-repo wiki/raw layout — e.g. a mounted network drive (no CLI, no network).

The user case: ``CITADEL_WIKI_DIR=T:\\team-wiki\\wiki`` / ``CITADEL_RAW_DIR=T:\\team-wiki\\raw`` while the
code is a normal checkout on another volume. These cover the full chain that used to assume
everything lives under ``WORKSPACE_ROOT``:

  * config key<->path helpers (the single source of truth) + env-override resolution;
  * the agent bridge (absolute paths in the prompt + ``--add-dir`` for claude / ``--include-
    directories`` for gemini, while the in-repo invocation stays unchanged);
  * resource validation against an absolute out-of-repo path;
  * source-citation matching (find/rewrite) with absolute keys;
  * and an END-TO-END ingest whose wiki/raw sit OUTSIDE the repo.

All filesystem state is redirected to tmp_path (the shared ``tmp_citadel_external`` fixture
models the mounted drive) and ``llm.run_ingest_session`` is faked, so no real CLI is ever
spawned.
"""

from __future__ import annotations

import os
from pathlib import Path

from citadel import config, ingest, lint, llm, manifest, okf, store, validate


# --- config: the key<->path single source of truth -------------------------------------


def test_rel_or_abs_posix_relative_in_repo_absolute_outside(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "raw").mkdir(parents=True)
    monkeypatch.setattr(config, "WORKSPACE_ROOT", repo, raising=False)

    inside = repo / "raw" / "notes.md"
    outside = tmp_path / "net" / "raw" / "notes.md"
    outside.parent.mkdir(parents=True)

    assert config.rel_or_abs_posix(inside) == "raw/notes.md"  # repo-relative key
    assert config.rel_or_abs_posix(outside) == outside.resolve().as_posix()  # absolute key
    # No basename collapse: two out-of-repo files with the SAME name get DISTINCT keys.
    other = tmp_path / "net2" / "raw" / "notes.md"
    other.parent.mkdir(parents=True)
    assert config.rel_or_abs_posix(outside) != config.rel_or_abs_posix(other)


def test_source_path_for_key_inverts_rel_or_abs_posix(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(config, "WORKSPACE_ROOT", repo, raising=False)

    # workspace-relative key -> under WORKSPACE_ROOT
    assert config.source_path_for_key("raw/notes.md") == repo / "raw" / "notes.md"
    # absolute key -> used as-is
    abs_key = (tmp_path / "net" / "raw" / "notes.md").resolve().as_posix()
    assert config.source_path_for_key(abs_key) == Path(abs_key)
    # round-trip both ways
    for p in (repo / "raw" / "x.md", tmp_path / "net" / "raw" / "y.md"):
        assert config.source_path_for_key(config.rel_or_abs_posix(p)) == p.resolve()


def test_is_outside_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(config, "WORKSPACE_ROOT", ws, raising=False)
    assert config.is_outside_workspace(tmp_path / "net" / "wiki") is True
    assert config.is_outside_workspace(ws / "wiki") is False


def test_dir_setting_relative_against_repo_root_absolute_as_is(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(config, "WORKSPACE_ROOT", repo, raising=False)

    # A relative override resolves against the REPO ROOT, not the process CWD.
    monkeypatch.setenv("CITADEL_X_DIR", "wiki")
    assert config._dir_setting("CITADEL_X_DIR", repo / "default") == (repo / "wiki").resolve()

    # An absolute override is used as-is (so wiki/raw can live outside the repo).
    external = tmp_path / "net" / "wiki"
    monkeypatch.setenv("CITADEL_X_DIR", str(external))
    assert config._dir_setting("CITADEL_X_DIR", repo / "default") == external.resolve()

    # No override -> the default.
    monkeypatch.delenv("CITADEL_X_DIR", raising=False)
    assert config._dir_setting("CITADEL_X_DIR", repo / "default") == (repo / "default").resolve()


# --- the agent bridge: absolute paths + per-CLI external-dir access ---------------------


def test_build_instruction_uses_absolute_paths_when_wiki_outside_repo(tmp_path, tmp_citadel_external):
    """With the wiki/raw outside the repo, the agent prompt names them by ABSOLUTE path (not a
    bare 'wiki'/'raw' that the repo-root CWD can't find) and still stays tiny."""
    wiki, raw = tmp_citadel_external.wiki, tmp_citadel_external.raw
    abs_key = config.rel_or_abs_posix(raw / "notes.md")

    prompt = llm._build_instruction(abs_key)

    assert wiki.resolve().as_posix() in prompt  # absolute wiki path, not 'wiki/'
    assert raw.resolve().as_posix() in prompt  # absolute raw path
    assert abs_key in prompt  # the absolute source key
    assert abs_key.startswith(tmp_path.resolve().as_posix())  # it really is absolute
    assert len(prompt) < 3000  # paths + rule pointers, never file content (WinError 206 guard)


def test_external_dirs_lists_only_out_of_repo_dirs(tmp_citadel_external):
    cit = tmp_citadel_external  # docs is INSIDE the repo
    abs_key = config.rel_or_abs_posix(cit.raw / "notes.md")

    dirs = llm._external_dirs(abs_key)

    assert str(cit.wiki.resolve()) in dirs
    assert str(cit.raw.resolve()) in dirs
    assert str(cit.docs.resolve()) not in dirs  # in-repo docs needs no grant


def test_external_dirs_empty_for_in_repo_layout(tmp_path, make_citadel):
    """The default in-repo layout grants nothing extra (so the invocation is unchanged)."""
    make_citadel(root=tmp_path / "repo")

    assert llm._external_dirs("raw/notes.md") == []


def test_external_dirs_grants_office_extract_tmp_even_in_repo(tmp_path, make_citadel):
    """For an Office source the extracted-text temp dir lives OUTSIDE the repo, so it must be
    granted to the CLI even in the otherwise-unchanged default in-repo layout."""
    make_citadel(root=tmp_path / "repo")

    extract_dir = tmp_path / "okf_extract_zzz"  # sibling of the repo -> outside it
    dirs = llm._external_dirs("raw/deck.pptx", str(extract_dir / "deck.md"))
    assert str(extract_dir.resolve()) in dirs
    assert llm._external_dirs("raw/deck.pptx") == []  # no read_path -> still nothing extra


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
    assert "--add-dir" not in argv  # default layout: unchanged
    argv_default, _ = llm._build_invocation("claude", "/bin/claude", "P")
    assert "--add-dir" not in argv_default  # extra_dirs defaults to none


def test_build_invocation_gemini_includes_directories_only_when_external():
    argv, _ = llm._build_invocation("gemini", "/bin/gemini", "P", ["/net/wiki"])
    assert "--include-directories" in argv and "/net/wiki" in argv
    argv_in_repo, _ = llm._build_invocation("gemini", "/bin/gemini", "P", [])
    assert "--include-directories" not in argv_in_repo  # in-repo argv unchanged


# --- resource validation against an absolute out-of-repo path ---------------------------


def test_validate_resource_absolute_out_of_repo(tmp_citadel_external):
    raw = tmp_citadel_external.raw
    (raw / "notes.md").write_text("src\n", encoding="utf-8")
    abs_key = config.rel_or_abs_posix(raw / "notes.md")

    fm = {"type": "Concept", "title": "T", "description": "d", "tags": ["ml"], "resource": abs_key}
    body = f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{abs_key}](../../raw/notes.md) - n (ingested 2026-06-21)\n"
    issues = validate.validate_page("concepts/transformer.md", fm, body)
    assert [i for i in issues if i.category == "bad_resource"] == []  # absolute resource accepted

    # A missing absolute resource is still flagged.
    fm_missing = dict(fm, resource=config.rel_or_abs_posix(raw / "ghost.md"))
    issues2 = validate.validate_page("concepts/transformer.md", fm_missing, body)
    assert any(i.category == "bad_resource" for i in issues2)


# --- source-citation matching with absolute keys ----------------------------------------


def test_find_and_rewrite_raw_references_with_absolute_keys(tmp_citadel_external, seed_page):
    raw = tmp_citadel_external.raw
    (raw / "notes.md").write_text("x\n", encoding="utf-8")
    abs_key = config.rel_or_abs_posix(raw / "notes.md")

    page = seed_page(
        "concepts/t.md",
        {"type": "Concept", "title": "T", "description": "d", "tags": ["x"], "resource": abs_key},
        f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{abs_key}](../../raw/notes.md) - n\n",
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
    assert "(../../raw/ml/notes.md)" in text  # recomputed relative citation
    assert "(../../raw/notes.md)" not in text
    assert store.find_raw_references(abs_key) == []  # nothing points at the old key anymore


# --- END-TO-END: ingest with wiki/raw OUTSIDE the repo ----------------------------------


def _fake_session(rel_key, kind="ingest"):
    """Write one Concept page (as the agent would) into the configured WIKI_DIR, citing the raw
    file by its real RELATIVE path and recording the (possibly absolute) source key as resource."""
    target = config.WIKI_DIR / "concepts" / "transformer.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    rel_link = os.path.relpath(config.source_path_for_key(rel_key), config.WIKI_DIR / "concepts").replace(os.sep, "/")
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


def test_ingest_end_to_end_with_wiki_raw_outside_repo(tmp_citadel_external, fake_agent):
    repo, wiki, raw = tmp_citadel_external.root, tmp_citadel_external.wiki, tmp_citadel_external.raw
    fake_agent(side_effect=_fake_session)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    abs_key = config.rel_or_abs_posix(raw / "notes.md")
    assert report.processed == [abs_key]  # keyed by absolute path, no collision/basename
    assert not report.errors
    assert report.broken_links == []

    # The page was written to the NET wiki, not a repo/wiki.
    page = wiki / "concepts" / "transformer.md"
    assert page.exists()
    assert not (repo / "wiki").exists()
    text = page.read_text(encoding="utf-8")
    assert f"resource: {abs_key}" in text  # absolute resource survives validate+restamp
    assert "timestamp:" in text  # system re-stamped it
    assert "(../../raw/notes.md)" in text  # valid relative citation across the net dir

    # Derived files + manifest live next to the (out-of-repo) wiki.
    assert "transformer.md" in tmp_citadel_external.index_path.read_text(encoding="utf-8")
    data = tmp_citadel_external.read_manifest()
    assert abs_key in data

    # Whole-wiki health check is clean, and re-running is a no-op (idempotent on the abs key).
    rep = lint.lint()
    assert rep.ok() and rep.bad_sources == []
    assert ingest.ingest().processed == []


def test_ingest_deletes_out_of_repo_source(tmp_citadel_external, seed_page, fake_agent):
    """A tracked out-of-repo source that vanished from the drive is detected (existence check via
    source_path_for_key) and its provenance reconciled out — exercising find_raw_references on an
    absolute key for both the resource and the citation link."""
    wiki, raw = tmp_citadel_external.wiki, tmp_citadel_external.raw
    abs_key = config.rel_or_abs_posix(raw / "notes.md")  # never created -> "deleted" on disk

    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": abs_key},
        f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{abs_key}](../../raw/notes.md) - n\n",
    )
    manifest.save({abs_key: "deadbeef"})

    def unlink_topic(rel_key, kind="ingest"):
        (config.WIKI_DIR / "concepts" / "topic.md").unlink()

    agent = fake_agent(side_effect=unlink_topic)

    report = ingest.ingest()

    assert agent.calls == [(abs_key, "delete")]  # a delete-cleanup session for the abs key
    assert report.sources_deleted == [abs_key]
    assert not (wiki / "concepts" / "topic.md").exists()
    assert not report.errors
    data = tmp_citadel_external.read_manifest()
    assert abs_key not in data  # manifest key dropped


# --- canonicalizing a shortened `resource` for an out-of-repo source --------------------


def test_canonical_resource_key_repairs_only_shortened_current_source(tmp_path, make_citadel):
    """The unit guard behind the repair: a broken `resource` that names the source being ingested
    is canonicalized to its real key; anything else is left untouched."""
    cit = make_citadel(root=tmp_path / "repo")

    net = tmp_path / "net" / "raw"
    net.mkdir(parents=True)
    (net / "notes.pdf").write_text("x\n", encoding="utf-8")
    abs_key = config.rel_or_abs_posix(net / "notes.pdf")  # absolute, out-of-repo key

    # A shortened/broken reference to THIS source -> canonicalized to the real absolute key.
    assert ingest._canonical_resource_key("raw/notes.pdf", abs_key) == abs_key
    assert ingest._canonical_resource_key("notes.pdf", abs_key) == abs_key  # bare basename
    assert ingest._canonical_resource_key("raw\\notes.pdf", abs_key) == abs_key  # backslashes

    # Left untouched (return None):
    assert ingest._canonical_resource_key(abs_key, abs_key) is None  # already canonical
    assert ingest._canonical_resource_key("", abs_key) is None  # empty -> missing field
    assert ingest._canonical_resource_key("raw/other.md", abs_key) is None  # different basename
    ghost = config.rel_or_abs_posix(net / "ghost.pdf")  # source itself missing
    assert ingest._canonical_resource_key("raw/ghost.pdf", ghost) is None
    # A `resource` that already resolves to a real file is never second-guessed.
    (cit.raw / "notes.pdf").write_text("z\n", encoding="utf-8")
    assert ingest._canonical_resource_key("raw/notes.pdf", abs_key) is None


def test_ingest_canonicalizes_shortened_resource_for_out_of_repo_source(tmp_path, make_citadel, fake_agent):
    """The reported case: wiki/raw live IN the repo, but the SOURCE being ingested is on a mounted
    drive (an out-of-repo absolute key — e.g. a PDF under ``T:\\...\\raw``). The agent records the
    conventional short ``raw/<file>`` as the page's ``resource`` instead of the long absolute key,
    which used to fail every page with ``bad_resource`` and roll the whole (long) session back.
    Ingest must now canonicalize it to the real key and succeed."""
    cit = make_citadel(root=tmp_path / "repo")

    # The raw source (PDF stand-in) lives OUTSIDE the repo — a mounted-drive source.
    net_raw = tmp_path / "net" / "raw"
    net_raw.mkdir(parents=True)
    source = net_raw / "datenanalyse.md"
    source.write_text("Internal data analysis facts.\n", encoding="utf-8")
    abs_key = config.rel_or_abs_posix(source)
    assert abs_key == source.resolve().as_posix()  # really an absolute, out-of-repo key

    def shortened_session(rel_key, kind="ingest"):
        # The agent does the work but SHORTENS the long absolute key to the conventional form.
        page = config.WIKI_DIR / "concepts" / "internal-data-analysis.md"
        page.parent.mkdir(parents=True, exist_ok=True)
        rel_link = os.path.relpath(config.source_path_for_key(rel_key), page.parent).replace(os.sep, "/")
        page.write_text(
            okf.dump(
                {
                    "type": "Concept",
                    "title": "Internal Data Analysis",
                    "description": "internal data analysis",
                    "tags": ["data"],
                    "resource": "raw/" + rel_key.rsplit("/", 1)[-1],  # the shortened, broken form
                },
                f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}]({rel_link}) - n (ingested 2026-06-21)\n",
            ),
            encoding="utf-8",
        )

    fake_agent(side_effect=shortened_session)

    report = ingest.ingest([str(source)])

    assert report.processed == [abs_key]  # keyed by the absolute out-of-repo path
    assert not report.errors  # NOT rolled back over the short resource
    page = cit.wiki / "concepts" / "internal-data-analysis.md"
    text = page.read_text(encoding="utf-8")
    assert f"resource: {abs_key}" in text  # canonicalized to the real absolute key
    assert "resource: raw/datenanalyse.md" not in text  # the broken short form is gone
    # The canonical resource matches the manifest key, so later move/delete lookups find the page.
    assert store.find_raw_references(abs_key) == ["concepts/internal-data-analysis.md"]
    assert ingest.ingest([str(source)]).processed == []  # idempotent on the abs key
