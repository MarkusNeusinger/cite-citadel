"""Unit tests for the cross-process workspace run lock (``runlock.py``) and the atomic
manifest/failures saves it protects — the audit's B1: two concurrent ``citadel ingest`` runs
were silently destructive (staging sweep, promote prune, last-write-wins saves)."""

from __future__ import annotations

import json
import os
import socket
import time

import pytest

from citadel import config, ingest, runlock


def _foreign_lock(payload: dict) -> None:
    runlock.lock_path().write_text(json.dumps(payload), encoding="utf-8")


# --- hold(): acquire / release ---------------------------------------------------------------


def test_hold_creates_and_removes_the_lockfile(tmp_citadel):
    path = runlock.lock_path()
    with runlock.hold("ingest"):
        assert path.is_file()
        holder = json.loads(path.read_text(encoding="utf-8"))
        assert holder["pid"] == os.getpid()
        assert holder["kind"] == "ingest"
    assert not path.exists()


def test_hold_releases_on_exception(tmp_citadel):
    with pytest.raises(RuntimeError, match="boom"):
        with runlock.hold("ingest"):
            raise RuntimeError("boom")
    assert not runlock.lock_path().exists()


def test_second_hold_fails_loud_naming_the_holder(tmp_citadel):
    with runlock.hold("ingest"):
        with pytest.raises(runlock.RunLockError, match="already running"):
            with runlock.hold("curate"):
                pass  # pragma: no cover - never reached
        # the failed acquire must not have removed the live run's lock
        assert runlock.lock_path().is_file()
    assert not runlock.lock_path().exists()


def test_runlock_error_is_a_runtime_error():
    # cli.main's top-level handler and the MCP never-raise wrappers both catch RuntimeError,
    # so the lock failure renders as a friendly one-liner everywhere.
    assert issubclass(runlock.RunLockError, RuntimeError)


# --- staleness reclaim ------------------------------------------------------------------------


def test_dead_pid_on_this_host_is_reclaimed(tmp_citadel, monkeypatch):
    _foreign_lock({"pid": 12345, "host": socket.gethostname(), "kind": "ingest", "started": "x"})
    monkeypatch.setattr(runlock, "_pid_alive", lambda pid: False)
    with runlock.hold("ingest"):
        assert json.loads(runlock.lock_path().read_text(encoding="utf-8"))["pid"] == os.getpid()
    assert not runlock.lock_path().exists()


def test_old_mtime_is_reclaimed_even_from_another_host(tmp_citadel):
    _foreign_lock({"pid": 999999, "host": "elsewhere", "kind": "ingest", "started": "x"})
    old = time.time() - (runlock._stale_after_s() + 60)
    os.utime(runlock.lock_path(), (old, old))
    with runlock.hold("curate"):
        assert json.loads(runlock.lock_path().read_text(encoding="utf-8"))["host"] == socket.gethostname()


def test_fresh_foreign_lock_blocks_with_holder_in_the_message(tmp_citadel):
    _foreign_lock({"pid": 999999, "host": "elsewhere", "kind": "ingest", "started": "2026-07-10 09:00:00"})
    with pytest.raises(runlock.RunLockError, match="elsewhere"):
        with runlock.hold("ingest"):
            pass  # pragma: no cover - never reached
    # the blocked acquire leaves the foreign lock alone
    assert json.loads(runlock.lock_path().read_text(encoding="utf-8"))["host"] == "elsewhere"


def test_pid_alive_probes_self_on_posix():
    if os.name != "posix":
        pytest.skip("pid probing is POSIX-only; Windows staleness rides on mtime")
    assert runlock._pid_alive(os.getpid()) is True


def test_heartbeat_refreshes_the_lock_mtime(tmp_citadel):
    with runlock.hold("ingest"):
        path = runlock.lock_path()
        old = time.time() - 10_000
        os.utime(path, (old, old))
        runlock.heartbeat()
        assert time.time() - path.stat().st_mtime < 60


def test_heartbeat_leaves_a_foreign_lock_alone(tmp_citadel):
    """A lock another (reclaiming) run owns is never refreshed: bumping its mtime would mask the
    NEW holder's staleness. Same pid+host guard as the release path."""
    path = runlock.lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    old = time.time() - 10_000
    path.write_text(json.dumps({"pid": os.getpid() + 1, "host": "other-host", "kind": "ingest"}), encoding="utf-8")
    os.utime(path, (old, old))
    runlock.heartbeat()
    assert abs(path.stat().st_mtime - old) < 1  # untouched
    path.unlink()


# --- integration: ingest/staging under the lock ----------------------------------------------


def test_ingest_fails_loud_while_another_run_holds_the_lock(tmp_citadel, fake_agent):
    fake_agent({})
    (tmp_citadel.raw / "a.md").write_text("hello\n", encoding="utf-8")
    with runlock.hold("ingest"):
        with pytest.raises(runlock.RunLockError):
            ingest.ingest()
    # lock released -> the same call goes through, and cleans up after itself
    ingest.ingest()
    assert not runlock.lock_path().exists()


def test_make_staging_no_longer_sweeps_siblings_but_run_start_does(tmp_citadel):
    live = config.WIKI_DIR
    config.robust_mkdir(live)
    stale = live.parent / f"{ingest._staging_prefix(live)}999.1"
    stale.mkdir()
    fresh = ingest._make_staging(live)
    # the per-call sweep is GONE - it used to rm-tree a concurrent run's in-flight staging
    assert stale.is_dir()
    ingest._sweep_stale_staging(live)
    assert not stale.exists()
    assert not fresh.exists()


# --- atomic saves ------------------------------------------------------------------------------


def test_atomic_write_replaces_and_leaves_no_tmp(tmp_path):
    target = tmp_path / "m.json"
    target.write_text("old", encoding="utf-8")
    config.atomic_write_text(target, "new")
    assert target.read_text(encoding="utf-8") == "new"
    assert list(tmp_path.glob("*.citadeltmp")) == []


def test_atomic_write_retries_transient_replace_failures(tmp_path, monkeypatch):
    target = tmp_path / "m.json"
    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError("sharing violation")
        return real_replace(src, dst)

    monkeypatch.setattr(config.os, "replace", flaky)
    config.atomic_write_text(target, "content")
    assert target.read_text(encoding="utf-8") == "content"
    assert calls["n"] == 3


def test_atomic_write_failure_leaves_the_original_intact(tmp_path, monkeypatch):
    target = tmp_path / "m.json"
    target.write_text("old", encoding="utf-8")

    def always_fail(src, dst):
        raise OSError("locked")

    monkeypatch.setattr(config.os, "replace", always_fail)
    with pytest.raises(OSError):
        config.atomic_write_text(target, "new", attempts=2)
    assert target.read_text(encoding="utf-8") == "old"
    assert list(tmp_path.glob("*.citadeltmp")) == []
