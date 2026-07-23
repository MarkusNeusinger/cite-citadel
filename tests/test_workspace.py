"""Tests for the workspace model: discovery order, `citadel init`, the fail-loud CLI guard,
the manifest workspace stamp, and workspace-root .env loading. All offline, all under tmp_path.

Discovery itself is exercised through ``config._resolve_workspace`` (pure — takes an explicit
``cwd`` and returns the resolved root, or None when no workspace resolved), because the
module-level ``WORKSPACE_ROOT``/``WORKSPACE_FOUND`` are import-time values the suite pins via
conftest's autouse fixture.
"""

from __future__ import annotations

import json
import os

import pytest

from citadel import cli, config, manifest, workspace


def _clear_workspace_env(monkeypatch) -> None:
    """Strip every env var that steers workspace discovery, so a developer's shell (or a loaded
    .env) cannot leak into the resolution tests."""
    for var in ("CITADEL_WORKSPACE", "CITADEL_WIKI_DIR", "CITADEL_RAW_DIR"):
        monkeypatch.delenv(var, raising=False)


def _marker(directory) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / config.WORKSPACE_MARKER).write_text(workspace.MARKER_CONTENT, encoding="utf-8")


# --- resolution order: env > marker > env-dirs > fallback --------------------------------


def test_env_override_wins_over_marker(tmp_path, monkeypatch):
    _clear_workspace_env(monkeypatch)
    marked = tmp_path / "marked"
    _marker(marked)
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    monkeypatch.setenv("CITADEL_WORKSPACE", str(explicit))

    # The env-var dir wins over the marker dir the CWD sits in.
    assert config._resolve_workspace(cwd=marked) == explicit.resolve()


def test_marker_found_by_upward_walk_from_nested_cwd(tmp_path, monkeypatch):
    _clear_workspace_env(monkeypatch)
    ws = tmp_path / "ws"
    _marker(ws)
    deep = ws / "sub" / "deep"
    deep.mkdir(parents=True)

    assert config._resolve_workspace(cwd=deep) == ws.resolve()


def test_resolution_defaults_to_process_cwd(tmp_path, monkeypatch):
    _clear_workspace_env(monkeypatch)
    ws = tmp_path / "ws"
    _marker(ws)
    monkeypatch.chdir(ws)

    assert config._resolve_workspace() == ws.resolve()


def test_env_dirs_pair_makes_cwd_a_nominal_workspace(tmp_path, monkeypatch):
    _clear_workspace_env(monkeypatch)
    monkeypatch.setenv("CITADEL_WIKI_DIR", str(tmp_path / "net" / "wiki"))
    monkeypatch.setenv("CITADEL_RAW_DIR", str(tmp_path / "net" / "raw"))
    anywhere = tmp_path / "anywhere"
    anywhere.mkdir()

    # The CWD itself becomes the (nominal) root of an env-dirs workspace.
    assert config._resolve_workspace(cwd=anywhere) == anywhere.resolve()
    # ONE env dir alone is NOT a workspace — both must be set.
    monkeypatch.delenv("CITADEL_RAW_DIR")
    assert config._resolve_workspace(cwd=anywhere) is None


def test_no_marker_no_env_resolves_nothing(tmp_path, monkeypatch):
    _clear_workspace_env(monkeypatch)
    bare = tmp_path / "bare"
    bare.mkdir()

    assert config._resolve_workspace(cwd=bare) is None  # -> WORKSPACE_FOUND False, root = bare CWD


# --- nested-marker shadowing --------------------------------------------------------------


def test_nested_marker_shadows_outer(tmp_path, monkeypatch):
    _clear_workspace_env(monkeypatch)
    outer = tmp_path / "outer"
    inner = outer / "inner"
    _marker(outer)
    _marker(inner)

    assert config._resolve_workspace(cwd=inner) == inner.resolve()  # nearest wins
    assert config._resolve_workspace(cwd=outer) == outer.resolve()


def test_inner_workspace_never_touches_outer_manifest(tmp_path, monkeypatch):
    """Running from the inner workspace keeps every derived file inside it — the outer
    workspace's wiki/manifest must not even come into existence."""
    _clear_workspace_env(monkeypatch)
    outer = tmp_path / "outer"
    inner = outer / "inner"
    _marker(outer)
    _marker(inner)

    root = config._resolve_workspace(cwd=inner)
    assert root == inner.resolve()
    # Wire config the way import-time derivation does: every default hangs off the workspace root.
    monkeypatch.setattr(config, "WORKSPACE_ROOT", root)
    monkeypatch.setattr(config, "WIKI_DIR", root / "wiki")
    monkeypatch.setattr(config, "MANIFEST_PATH", root / "wiki" / ".citadel_ingested.json")

    manifest.save({"raw/x.md": "h"})

    assert (inner / "wiki" / ".citadel_ingested.json").is_file()
    assert not (outer / "wiki").exists()  # the shadowed outer workspace stays untouched


# --- citadel init: scaffolding + idempotency ----------------------------------------------


def test_init_scaffolds_a_complete_workspace(tmp_path, capsys):
    ws = tmp_path / "ws"

    assert cli.main(["init", str(ws)]) == 0

    out = capsys.readouterr().out
    for name in ("citadel.toml", ".env", "raw/", "wiki/"):
        assert f"created {name}" in out
    assert (ws / "citadel.toml").read_text(encoding="utf-8") == workspace.MARKER_CONTENT
    assert "CITADEL_LLM_CLI" in (ws / ".env").read_text(encoding="utf-8")  # the packaged template
    assert (ws / "raw").is_dir() and (ws / "wiki").is_dir()
    # No rules/ overlay is scaffolded — house rules are opt-in (a hand-written rules/local.md or
    # `citadel rules eject`); a stub would only add a no-op file read to every agent session.
    assert not (ws / "rules").exists()
    # The scaffolded dir now discovers as a marker workspace.
    assert config._resolve_workspace(cwd=ws) == ws.resolve()


def test_init_is_idempotent_and_never_overwrites(tmp_path, capsys):
    ws = tmp_path / "ws"
    assert cli.main(["init", str(ws)]) == 0
    capsys.readouterr()
    (ws / ".env").write_text("CUSTOM=1\n", encoding="utf-8")  # the user's own edits

    assert cli.main(["init", str(ws)]) == 0  # re-running an initialized workspace is fine

    out = capsys.readouterr().out
    for name in ("citadel.toml", ".env", "raw/", "wiki/"):
        assert f"skipped {name}" in out
    assert "created" not in out
    assert "already initialized" in out
    assert (ws / ".env").read_text(encoding="utf-8") == "CUSTOM=1\n"  # never overwritten


def test_init_reports_created_and_skipped_mix(tmp_path, capsys):
    ws = tmp_path / "ws"
    (ws / "raw").mkdir(parents=True)  # pre-existing raw/ next to nothing else

    assert cli.main(["init", str(ws)]) == 0

    out = capsys.readouterr().out
    assert "skipped raw/" in out
    for name in ("citadel.toml", ".env", "wiki/"):
        assert f"created {name}" in out


# --- fail-loud: every subcommand except init needs a workspace ----------------------------


def test_workspace_needing_command_fails_loud_when_none_found(monkeypatch, capsys):
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)

    assert cli.main(["tags"]) == 2

    err = capsys.readouterr().err
    assert "no citadel workspace" in err
    assert "citadel init" in err  # the actionable fixes are named
    assert "CITADEL_WORKSPACE" in err


def test_init_refuses_a_file_where_a_directory_belongs(tmp_path):
    """Copilot review on PR #30: a FILE named raw/ or wiki/ used to fall through the is_dir()
    check into robust_mkdir's FileExistsError. init must fail loud with an actionable error."""
    (tmp_path / "raw").write_text("not a directory", encoding="utf-8")
    with pytest.raises(RuntimeError, match="'raw' exists but is not a directory"):
        workspace.init_workspace(tmp_path)


def test_init_refuses_a_directory_where_a_file_belongs(tmp_path):
    """A directory named .env (or citadel.toml) must raise a clear error, not be 'skipped'."""
    (tmp_path / ".env").mkdir()
    with pytest.raises(RuntimeError, match="'.env' exists but is a directory"):
        workspace.init_workspace(tmp_path)


def test_init_is_exempt_from_the_workspace_guard(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    assert cli.main(["init", str(tmp_path / "ws")]) == 0


def test_serve_dispatches_when_workspace_found(monkeypatch):
    """The MCP-host story: with a workspace resolved (e.g. CITADEL_WORKSPACE set), `citadel
    serve` passes the guard from ANY CWD and reaches the server entry point."""
    monkeypatch.setattr(config, "WORKSPACE_FOUND", True)
    called = {}

    def fake_serve(args):
        called["serve"] = True
        return 0

    monkeypatch.setattr(cli, "cmd_serve", fake_serve)
    assert cli.main(["serve"]) == 0
    assert called == {"serve": True}


def test_env_dirs_workspace_passes_the_guard(monkeypatch, tmp_citadel, capsys):
    monkeypatch.setattr(config, "WORKSPACE_FOUND", True)  # what an env-dirs pair resolves to
    assert cli.main(["tags"]) == 0  # a marker-less env-dirs workspace stays fully valid
    assert "No tags yet." in capsys.readouterr().out


# --- manifest workspace stamp --------------------------------------------------------------


def test_manifest_meta_round_trip(tmp_citadel):
    sources = {"raw/a.md": {"sha256": "h", "model": "claude:sonnet"}}
    manifest.save(sources)

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert data["meta"]["format"] == manifest.MANIFEST_FORMAT
    assert data["meta"]["workspace"] == tmp_citadel.root.resolve().as_posix()
    assert data["sources"] == sources

    assert manifest.load() == sources  # load() returns the FLAT dict; meta never leaks


def test_manifest_legacy_flat_read_and_upgrade_on_save(tmp_citadel):
    flat = {"raw/a.md": "deadbeef", "raw/b.md": {"sha256": "h2"}}
    tmp_citadel.manifest_path.write_text(json.dumps(flat), encoding="utf-8")

    assert manifest.load() == flat  # legacy flat manifest reads as sources-only

    manifest.save(manifest.load())  # ... and the next save upgrades it to the stamped form
    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert data["sources"] == flat
    assert data["meta"]["workspace"] == tmp_citadel.root.resolve().as_posix()


def test_manifest_workspace_mismatch_warns_once_but_loads(tmp_citadel, monkeypatch, capsys):
    monkeypatch.setattr(manifest, "_warned_workspaces", set())
    stamped = "/somewhere/else/entirely"
    payload = {"meta": {"format": 2, "workspace": stamped}, "sources": {"raw/a.md": "h"}}
    tmp_citadel.manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    assert manifest.load() == {"raw/a.md": "h"}  # a warning, never an error

    err = capsys.readouterr().err
    assert "WARNING" in err
    assert stamped in err and tmp_citadel.root.resolve().as_posix() in err

    manifest.load()
    assert capsys.readouterr().err == ""  # ONE prominent warning per process, not per load


def test_manifest_matching_workspace_stays_silent(tmp_citadel, monkeypatch, capsys):
    monkeypatch.setattr(manifest, "_warned_workspaces", set())
    manifest.save({"raw/a.md": "h"})
    assert manifest.load() == {"raw/a.md": "h"}
    assert capsys.readouterr().err == ""


# --- workspace-root .env loading -----------------------------------------------------------


def _reserve_env(monkeypatch, name: str) -> None:
    """Register ``name`` with monkeypatch so whatever ``_load_dotenv`` sets is rolled back."""
    monkeypatch.setenv(name, "sentinel")
    monkeypatch.delenv(name)


def test_dotenv_loads_from_workspace_root(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".env").write_text(
        '# comment\nCITADEL_WS_TEST="quoted value"\nexport CITADEL_WS_TEST2=two\n', encoding="utf-8"
    )
    _reserve_env(monkeypatch, "CITADEL_WS_TEST")
    _reserve_env(monkeypatch, "CITADEL_WS_TEST2")

    config._load_dotenv(ws)

    assert os.environ["CITADEL_WS_TEST"] == "quoted value"  # quotes stripped
    assert os.environ["CITADEL_WS_TEST2"] == "two"  # `export` prefix accepted


def test_dotenv_never_overrides_process_env(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".env").write_text("CITADEL_WS_TEST3=file\n", encoding="utf-8")
    monkeypatch.setenv("CITADEL_WS_TEST3", "process")

    config._load_dotenv(ws)

    assert os.environ["CITADEL_WS_TEST3"] == "process"  # process env > workspace .env


def test_dotenv_missing_file_is_a_noop(tmp_path):
    config._load_dotenv(tmp_path / "no-such-workspace")  # must not raise


# --- packaged rules resolve from any CWD ---------------------------------------------------


def test_packaged_rules_resolve_to_real_absolute_files():
    """The packaged rules TREE (citadel/rules/) resolves as absolute real files — readable from
    any CWD, in a checkout and in site-packages alike. Every file the prompt composition can
    reference must ship: schema.md + core.md (every session), one task brief per lifecycle, one
    format brief per Python-detectable format, and a non-empty genres/ starter set."""
    assert config.PACKAGED_RULES_DIR.is_absolute()
    for relname in (
        "README.md",
        "schema.md",
        "core.md",
        "tasks/ingest.md",
        "tasks/reconcile.md",
        "tasks/delete.md",
        "formats/repo.md",
        "formats/image.md",
        "formats/pdf.md",
        "formats/office.md",
        "formats/transcripts.md",
    ):
        path = config.PACKAGED_RULES_DIR / relname
        assert path.is_file(), f"missing packaged rules file: {relname}"
    assert list((config.PACKAGED_RULES_DIR / "genres").glob("*.md")), "the genres/ starter set must not be empty"
    # The old two-file rulebooks are GONE — greenfield, nothing may resurrect them. Checked
    # against the case-EXACT directory listing: on Windows/macOS a plain .exists() for
    # "SCHEMA.md" would match the new lowercase schema.md and false-fail.
    actual_names = {p.name for p in config.PACKAGED_RULES_DIR.iterdir()}
    assert "SCHEMA.md" not in actual_names
    assert "AGENT_INGEST.md" not in actual_names
