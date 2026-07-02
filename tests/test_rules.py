"""The rules tree as configuration: resolution layers, the rules_version stamp, and the
``citadel rules`` CLI (list / show / eject).

Resolution is two layers, first-hit-wins PER FILENAME: workspace ``rules/<relname>`` shadows the
packaged ``citadel/rules/<relname>``; ``rules/genres/`` is enumerated as a UNION (the starter-set
model); ``rules/local.md`` is additive. ``config.rules_version()`` content-hashes the effective
tree and is stamped per source into the manifest at mark-done time — what a later
``curate --stale-rules`` compares. All offline; the agent is faked where an ingest runs.
"""

from __future__ import annotations

import pytest
from conftest import REAL_RULES_DIR

from citadel import cli, config, ingest, manifest, okf


# --- resolution: workspace > packaged, per filename ----------------------------------------


def test_effective_rules_file_falls_back_to_packaged(tmp_citadel):
    resolved = config.effective_rules_file("core.md")
    assert resolved == tmp_citadel.packaged_rules / "core.md"
    assert resolved.is_file()


def test_workspace_file_shadows_packaged_same_name(tmp_citadel):
    override = tmp_citadel.root / "rules" / "tasks" / "ingest.md"
    override.parent.mkdir(parents=True)
    override.write_text("# forked ingest brief\n", encoding="utf-8")

    assert config.effective_rules_file("tasks/ingest.md") == override.resolve()
    # Per FILENAME: the sibling brief still resolves to the packaged layer.
    assert config.effective_rules_file("tasks/reconcile.md") == tmp_citadel.packaged_rules / "tasks/reconcile.md"


def test_effective_genres_is_the_sorted_union_of_both_layers(tmp_citadel):
    ws_genres = tmp_citadel.root / "rules" / "genres"
    ws_genres.mkdir(parents=True)
    (ws_genres / "lab-notebook.md").write_text("# lab-notebook\n", encoding="utf-8")
    (ws_genres / "prose.md").write_text("# prose — forked\n", encoding="utf-8")  # shadows packaged

    genres = config.effective_genres()
    names = [p.name for p in genres]
    assert names == sorted(names)
    assert "lab-notebook.md" in names  # workspace-only genre participates
    assert names.count("prose.md") == 1  # union, not concatenation
    assert (ws_genres / "prose.md").resolve() in genres  # ...and the workspace copy won


def test_local_rules_file_only_when_present(tmp_citadel):
    assert config.local_rules_file() is None
    local = tmp_citadel.root / "rules" / "local.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("house rules\n", encoding="utf-8")
    assert config.local_rules_file() == local.resolve()


def test_no_workspace_means_no_workspace_overlay(tmp_citadel, monkeypatch):
    """The bare-CWD fallback is NOT a workspace: without one, only the packaged layer is
    consulted — a stray ./rules in some random directory must never leak into resolution."""
    override = tmp_citadel.root / "rules" / "core.md"
    override.parent.mkdir(parents=True)
    override.write_text("# stray\n", encoding="utf-8")
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)

    assert config.workspace_rules_dir() is None
    assert config.effective_rules_file("core.md") == tmp_citadel.packaged_rules / "core.md"
    assert config.local_rules_file() is None


# --- rules_version: a content hash of the effective tree -----------------------------------


def test_rules_version_is_stable_and_short(tmp_citadel):
    first = config.rules_version()
    assert first == config.rules_version()  # deterministic
    assert len(first) == 12 and int(first, 16) >= 0  # short hex digest


def test_rules_version_changes_when_a_rules_file_changes(tmp_citadel):
    before = config.rules_version()
    core = tmp_citadel.packaged_rules / "core.md"
    core.write_text(core.read_text(encoding="utf-8") + "\nnew rule\n", encoding="utf-8")
    assert config.rules_version() != before


def test_rules_version_changes_when_a_workspace_override_appears(tmp_citadel):
    before = config.rules_version()
    override = tmp_citadel.root / "rules" / "core.md"
    override.parent.mkdir(parents=True)
    override.write_text("# forked core\n", encoding="utf-8")
    assert config.rules_version() != before  # the override IS the effective content now


def test_rules_version_lands_in_manifest_entries(tmp_citadel, fake_agent, transformer_page):
    """Ingest stamps the run's rules_version into each successfully imported source's manifest
    entry (mark_done time) — the hook curate's --stale-rules will compare against."""
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    fake_agent(transformer_page)

    report = ingest.ingest()

    assert report.errors == []
    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    assert entry["rules_version"] == config.rules_version()


def test_unreadable_source_entry_carries_no_rules_version(tmp_citadel, fake_agent):
    """A binary/unreadable source is only sniffed and skipped — no session ran, so no model and
    no rules_version are stamped (mirrors the model field's contract)."""
    (tmp_citadel.raw / "blob.bin").write_bytes(b"\x00\x01\x02\x03")
    fake_agent({})

    ingest.ingest()

    entry = tmp_citadel.read_manifest()["raw/blob.bin"]
    assert "rules_version" not in entry and "model" not in entry


def test_manifest_helpers_roundtrip_rules_version():
    entry = manifest.make_entry("abc", "claude:sonnet", "cafe01234567")
    assert entry == {"sha256": "abc", "model": "claude:sonnet", "rules_version": "cafe01234567"}
    assert manifest.entry_rules_version(entry) == "cafe01234567"
    assert manifest.entry_rules_version(manifest.make_entry("abc")) is None
    assert manifest.entry_rules_version("barehash") is None
    assert manifest.entry_rules_version(None) is None
    repo_entry = manifest.make_repo_entry("deadbeef", "m", "git@x:y.git", "cafe01234567")
    assert repo_entry["rules_version"] == "cafe01234567"


# --- citadel rules list / show / eject ------------------------------------------------------


def test_rules_list_names_layer_and_description(tmp_citadel, capsys):
    (tmp_citadel.root / "rules").mkdir(exist_ok=True)
    (tmp_citadel.root / "rules" / "core.md").write_text("# core — forked for this workspace\n", encoding="utf-8")

    assert cli.main(["rules", "list"]) == 0

    out = capsys.readouterr().out
    lines = {line.split("\t")[0]: line for line in out.strip().splitlines()}
    assert "core.md\tworkspace\tcore — forked for this workspace" in lines["core.md"]
    assert "\tpackaged\t" in lines["schema.md"]
    assert "tasks/ingest.md" in lines  # the tree is listed by tree-relative name


def test_rules_show_prints_the_effective_content(tmp_citadel, capsys):
    assert cli.main(["rules", "show", "core.md"]) == 0
    assert "core.md (test stub)" in capsys.readouterr().out

    override = tmp_citadel.root / "rules" / "core.md"
    override.parent.mkdir(exist_ok=True)
    override.write_text("# core — forked\n", encoding="utf-8")
    assert cli.main(["rules", "show", "core.md"]) == 0
    assert "forked" in capsys.readouterr().out


def test_rules_show_unknown_name_fails_actionably(tmp_citadel, capsys):
    assert cli.main(["rules", "show", "nope.md"]) == 1
    assert "no rules file named" in capsys.readouterr().err


def test_rules_show_rejects_path_escapes(tmp_citadel, capsys):
    for evil in ("../secrets.md", "/etc/passwd", "tasks/../../x.md"):
        assert cli.main(["rules", "show", evil]) == 1
        assert "invalid rules file name" in capsys.readouterr().err


def test_rules_eject_rejects_drive_letter_and_escapes(tmp_citadel, capsys):
    """The eject join points are guarded too (okf.safe_join via config.rules_join): a Windows
    drive-letter path — even on POSIX, where plain path math reads it as a relative segment —
    and any traversal name are rejected before anything touches the filesystem."""
    for evil in ("C:\\evil.md", "C:/evil.md", "../escape.md"):
        assert cli.main(["rules", "eject", evil]) == 1
        assert "invalid rules file name" in capsys.readouterr().err
    assert not (tmp_citadel.root / "rules").exists()  # nothing was created


def test_effective_rules_file_rejects_traversal(tmp_citadel):
    """The resolver itself is guarded at the join points — a traversal name raises instead of
    resolving outside the rules trees (the packaged fallback join included)."""
    with pytest.raises(okf.OKFError):
        config.effective_rules_file("../../etc/passwd")
    with pytest.raises(okf.OKFError):
        config.effective_rules_file("C:\\evil.md")  # drive letter, backslash-normalized then rejected


def test_rules_eject_copies_once_then_refuses(tmp_citadel, capsys):
    assert cli.main(["rules", "eject", "genres/prose.md"]) == 0
    out = capsys.readouterr().out
    dest = tmp_citadel.root / "rules" / "genres" / "prose.md"
    assert str(dest) in out
    assert dest.read_text(encoding="utf-8") == (tmp_citadel.packaged_rules / "genres/prose.md").read_text(
        encoding="utf-8"
    )
    # The ejected copy is now the effective file (fork-one-file, everything else updates with pip).
    assert config.effective_rules_file("genres/prose.md") == dest.resolve()

    dest.write_text("user edits\n", encoding="utf-8")
    assert cli.main(["rules", "eject", "genres/prose.md"]) == 1  # refuses to overwrite
    assert "refusing to overwrite" in capsys.readouterr().err
    assert dest.read_text(encoding="utf-8") == "user edits\n"  # the user's fork is untouched


def test_rules_eject_unknown_packaged_name_fails(tmp_citadel, capsys):
    assert cli.main(["rules", "eject", "genres/nope.md"]) == 1
    assert "no packaged rules file" in capsys.readouterr().err


def test_rules_list_and_show_work_without_a_workspace(monkeypatch, capsys):
    """A pip user BEFORE `citadel init` can still browse the packaged defaults: rules list/show
    opt out of the fail-loud workspace guard and fall back to the packaged layer."""
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)

    assert cli.main(["rules", "list"]) == 0
    out = capsys.readouterr().out
    assert "core.md\tpackaged" in out

    assert cli.main(["rules", "show", "core.md"]) == 0
    assert "core.md" in capsys.readouterr().out


def test_rules_eject_without_a_workspace_fails_actionably(monkeypatch, capsys):
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    assert cli.main(["rules", "eject", "core.md"]) == 1
    err = capsys.readouterr().err
    assert "needs a workspace" in err and "citadel init" in err


def test_packaged_rules_readme_indexes_every_file():
    """The anyplot-style README index: every packaged rules file (except the README itself) is
    named in the index table, so the map never silently drifts from the tree."""
    readme = (REAL_RULES_DIR / "README.md").read_text(encoding="utf-8")
    for path in sorted(REAL_RULES_DIR.rglob("*.md")):
        rel = path.relative_to(REAL_RULES_DIR).as_posix()
        if rel == "README.md":
            continue
        assert f"`{rel}`" in readme, f"rules README must index {rel}"


@pytest.mark.parametrize("relname", ["schema.md", "core.md"])
def test_always_read_rules_carry_the_wiki_language_rule(relname):
    """Z2: the target-language contract lives in the always-read layer — named in the run
    instruction, verbatim quotes stay original."""
    text = (REAL_RULES_DIR / relname).read_text(encoding="utf-8").lower()
    assert "language" in text
    assert "run instruction" in text
