"""`citadel adopt` (#168), offline: record a moved workspace root without an ingest run."""

from __future__ import annotations

import json

import pytest

from citadel import cli, config, doctor, manifest, runlock, wikigit


OTHER = "/mnt/other-machine/team-wiki"


def _write(cit, sources: dict, stamp: str | None = OTHER) -> bytes:
    cit.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"meta": {"format": manifest.MANIFEST_FORMAT, "workspace": stamp}, "sources": sources} if stamp else sources
    cit.manifest_path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return cit.manifest_path.read_bytes()


def _sources(cit, present: int, missing: int = 0) -> dict:
    out = {}
    for i in range(present):
        (cit.raw / f"p{i}.md").write_text(f"p{i}\n", encoding="utf-8")
        out[f"raw/p{i}.md"] = {"sha256": "a" * 64}
    for i in range(missing):
        out[f"raw/gone{i}.md"] = {"sha256": "b" * 64}
    return out


@pytest.fixture(autouse=True)
def _fresh_warnings(monkeypatch):
    monkeypatch.setattr(manifest, "_warned_workspaces", set())


@pytest.fixture
def commits(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(wikigit, "autocommit", lambda message: calls.append(message) or "")
    return calls


def test_adopt_records_the_root_and_silences_the_warning(tmp_citadel, commits, capsys):
    sources = _sources(tmp_citadel, 3)
    _write(tmp_citadel, sources)
    assert cli.main(["adopt"]) == 0
    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert data["meta"]["workspace"] == manifest._workspace_stamp()
    assert OTHER in data["meta"]["workspaces"] and manifest._workspace_stamp() in data["meta"]["workspaces"]
    assert data["sources"] == sources
    assert commits == ["citadel adopt: record workspace root"]
    capsys.readouterr()
    manifest._warned_workspaces.clear()
    manifest.load()
    assert capsys.readouterr().err == ""


def test_adopt_refuses_a_rekeyed_key_space(tmp_citadel, commits, capsys):
    before = _write(tmp_citadel, _sources(tmp_citadel, 1, missing=4))
    assert cli.main(["adopt"]) == 1
    assert tmp_citadel.manifest_path.read_bytes() == before
    assert "citadel ingest --full-rescan" in capsys.readouterr().err
    assert commits == []


@pytest.mark.parametrize("case", ["missing", "empty", "legacy", "matching", "known"])
def test_adopt_nothing_to_do(tmp_citadel, commits, capsys, case):
    path = tmp_citadel.manifest_path
    if case == "empty":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    elif case == "legacy":
        _write(tmp_citadel, _sources(tmp_citadel, 1), stamp=None)
    elif case == "matching":
        _write(tmp_citadel, _sources(tmp_citadel, 1), stamp=manifest._workspace_stamp())
    elif case == "known":
        data = {
            "meta": {
                "format": manifest.MANIFEST_FORMAT,
                "workspace": OTHER,
                "workspaces": [manifest._workspace_stamp(), OTHER],
            },
            "sources": {},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    existed = path.exists()
    before = path.read_bytes() if existed else None
    assert cli.main(["adopt"]) == 0
    assert "nothing to do" in capsys.readouterr().out
    assert path.exists() == existed and (path.read_bytes() if existed else None) == before
    assert commits == []


def test_adopt_never_rewrites_a_corrupt_manifest(tmp_citadel, commits):
    tmp_citadel.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_citadel.manifest_path.write_text("{not json", encoding="utf-8")
    assert cli.main(["adopt"]) == 1
    assert tmp_citadel.manifest_path.read_text(encoding="utf-8") == "{not json"


def test_adopt_lists_a_minority_of_missing_keys(tmp_citadel, commits, capsys):
    _write(tmp_citadel, _sources(tmp_citadel, 4, missing=1))
    assert cli.main(["adopt"]) == 0
    out = capsys.readouterr().out
    assert "raw/gone0.md" in out and "will treat these as deleted" in out


def test_adopt_caps_the_missing_list_at_ten(tmp_citadel, commits, capsys):
    _write(tmp_citadel, _sources(tmp_citadel, 25, missing=15))
    assert cli.main(["adopt"]) == 0
    out = capsys.readouterr().out
    assert sum(1 for line in out.splitlines() if line.strip().startswith("raw/gone")) == 10
    assert "+5 more" in out


def test_adopt_respects_a_live_run_lock(tmp_citadel, commits, capsys, monkeypatch):
    before = _write(tmp_citadel, _sources(tmp_citadel, 2))

    def held(name):
        raise runlock.RunLockError("another citadel run holds the workspace")

    monkeypatch.setattr(runlock, "hold", held)
    assert cli.main(["adopt"]) == 1
    assert tmp_citadel.manifest_path.read_bytes() == before


def test_load_warn_false_is_silent(tmp_citadel, capsys):
    _write(tmp_citadel, _sources(tmp_citadel, 1))
    manifest.load(warn=False)
    assert capsys.readouterr().err == ""
    manifest.load()
    assert "citadel adopt" in capsys.readouterr().err


def test_doctor_names_the_matching_remedy(tmp_citadel):
    _write(tmp_citadel, _sources(tmp_citadel, 3))
    check = doctor.check_manifest()
    assert check.status == doctor.WARN and "citadel adopt" in check.detail
    _write(tmp_citadel, _sources(tmp_citadel, 0, missing=3))
    check = doctor.check_manifest()
    assert check.status == doctor.WARN and "--full-rescan" in check.detail
    _write(tmp_citadel, {}, stamp=manifest._workspace_stamp())
    assert doctor.check_manifest().status == doctor.OK


def test_adopt_needs_a_workspace(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    assert cli.main(["adopt"]) == 2
