"""Tracks which raw files were already ingested so re-running is idempotent and cheap.

A tiny committed JSON file wiki/.citadel_ingested.json:

    {
      "meta": {"format": 2, "workspace": "<abs posix workspace root>"},
      "sources": {
        "raw/notes.md": {"sha256": "<hex>", "model": "claude:sonnet", "rules_version": "<hex>"},
        ...
      }
    }

``sources`` maps the source's workspace-relative (or absolute, for an out-of-workspace source)
posix key to how it was last ingested: ``sha256`` is the hash of the source's content (a file is
(re)ingested only if absent or its hash changed); ``model`` is the model/backend that imported it
(``config.ingest_model_label``), so you can see WHICH raw file was imported by WHICH model;
``rules_version`` is the content hash of the effective rules tree the importing session ran under
(``config.rules_version``) — what a later ``curate --stale-rules`` compares to find sources
ingested under older rules. ``model``/``rules_version`` are omitted for a source that no model
imported (a binary/unreadable file that was only seen and skipped).

:func:`load` returns the FLAT sources dict — callers never see ``meta`` — and :func:`save` stamps
``meta`` with the CURRENT workspace root. A legacy flat manifest (pre-workspace, no meta) is read
as sources-only and upgraded to the stamped form on the next save; greenfield, no migration
tooling (docs/refactor-plan.md). A bare-sha-string entry value is likewise still read (it simply
carries no model). No DB.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from . import config


# The on-disk manifest format version stamped into ``meta`` by :func:`save`.
MANIFEST_FORMAT = 2


# A manifest value is either the current record ({"sha256": ..., "model": ...}) or, for an older
# manifest, a bare sha256 string. The helpers below accept both so a pre-existing manifest keeps
# working without a migration step.
Entry = dict | str


def file_sha256(path: Path) -> str:
    """hashlib.sha256 of the file bytes, hexdigest. Read in 1 MiB chunks rather than slurping the
    whole file, so hashing a large source (a big PDF/CSV/…) stays memory-bounded — ingest now
    accepts arbitrary file types, not just small markdown notes."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel_key(src: Path) -> str:
    """Stable identity key for a raw source: its posix path relative to config.WORKSPACE_ROOT
    when it lives under the workspace (e.g. 'raw/notes.md', 'docs/karpathy-llm-wiki.md'), else its
    ABSOLUTE posix path (e.g. 'T:/team-wiki/raw/notes.md') so a source on a mounted network drive
    gets a unique, resolvable key instead of colliding on basename. Thin wrapper over the single
    source of truth, config.rel_or_abs_posix."""
    return config.rel_or_abs_posix(src)


def make_entry(sha: str, model: str | None = None, rules_version: str | None = None) -> Entry:
    """Build a manifest value from a content hash, the importing model, and the rules-tree hash
    the importing session ran under (``config.rules_version``). ``model``/``rules_version`` are
    included only when set, so a source no model imported (binary/unreadable) records just its
    sha."""
    entry: dict = {"sha256": sha}
    if model:
        entry["model"] = model
    if rules_version:
        entry["rules_version"] = rules_version
    return entry


def entry_sha(entry: Entry) -> str:
    """The sha256 stored for a manifest value, accepting both the current record form
    ({"sha256": ...}) and the legacy bare-string form (the sha itself). Empty for a repo
    entry (which is versioned by commit, not a content sha)."""
    if isinstance(entry, dict):
        return str(entry.get("sha256") or "")
    return str(entry or "")


def make_repo_entry(
    commit: str, model: str | None = None, remote: str | None = None, rules_version: str | None = None
) -> dict:
    """Build a manifest value for a GIT-REPOSITORY source: ``{"kind": "git", "commit": ...}``
    plus the importing ``model``, the repo's ``remote`` URL when known, and the ``rules_version``
    hash the importing session ran under. ``commit`` is the repo's version identity (a HEAD
    commit, possibly with a ``+dirty.<hash>`` suffix, or a ``snap.<hash>`` aggregate for a
    git-less snapshot) — the source is re-ingested when it changes."""
    entry: dict = {"kind": "git", "commit": commit}
    if model:
        entry["model"] = model
    if remote:
        entry["remote"] = remote
    if rules_version:
        entry["rules_version"] = rules_version
    return entry


def is_repo_entry(entry: Entry) -> bool:
    """True if ``entry`` records a git-repository source (``kind == "git"``) rather than a single
    file. Repo sources are versioned by ``commit``, not ``sha256``."""
    return isinstance(entry, dict) and entry.get("kind") == "git"


def entry_commit(entry: Entry) -> str:
    """The commit/version identity stored for a repo entry, or "" for a non-repo/legacy value."""
    if isinstance(entry, dict):
        return str(entry.get("commit") or "")
    return ""


def entry_remote(entry: Entry) -> str | None:
    """The repo's remote URL recorded for a repo entry, or None when unknown."""
    if isinstance(entry, dict):
        remote = entry.get("remote")
        return str(remote) if remote else None
    return None


def entry_model(entry: Entry) -> str | None:
    """The model recorded for a manifest value, or None when unknown (a legacy bare-string entry,
    or a source that no model imported)."""
    if isinstance(entry, dict):
        model = entry.get("model")
        return str(model) if model else None
    return None


def entry_rules_version(entry: Entry | None) -> str | None:
    """The rules-tree content hash recorded for a manifest value, or None when unknown (a
    bare-string entry, a source no model imported, or a pre-rules-split entry)."""
    if isinstance(entry, dict):
        version = entry.get("rules_version")
        return str(version) if version else None
    return None


def model_of(manifest: dict[str, Entry], key: str) -> str | None:
    """The model that imported the source ``key``, or None if it is untracked / has no model."""
    if key not in manifest:
        return None
    return entry_model(manifest[key])


def _workspace_stamp() -> str:
    """The absolute posix identity of the current workspace root — the value :func:`save` stamps
    into ``meta.workspace``. Read at call time so tests can monkeypatch the layout."""
    return config._safe_resolve(Path(config.WORKSPACE_ROOT)).as_posix()


# Stamped roots already warned about, so one mismatching manifest warns ONCE per process instead
# of once per load() (rebuild_indexes and the viewer re-load the manifest during a single run).
_warned_workspaces: set[str] = set()


def _check_workspace(meta: dict) -> None:
    """Print ONE prominent stderr warning when the manifest was stamped by a workspace rooted
    somewhere else. A warning, NOT an error: the same share can legitimately be mounted at
    different paths (a Windows drive letter vs a WSL /mnt path), so a mismatch is suspicious but
    must not block. The HARD workspace-identity guard — refusing to run so a nested marker cannot
    silently re-key sources — is scheduled for PR4's deletion-sweep rework (docs/refactor-plan.md,
    Z1 "key-space stability" / roadmap row 4)."""
    stamped = str(meta.get("workspace") or "")
    current = _workspace_stamp()
    if not stamped or stamped == current or stamped in _warned_workspaces:
        return
    _warned_workspaces.add(stamped)
    print(
        f"WARNING: the ingest manifest ({config.MANIFEST_PATH}) was written by a workspace rooted at\n"
        f"    {stamped}\n"
        f"but the current workspace root is\n"
        f"    {current}\n"
        "Source keys may not line up (same share mounted at a different path?). Proceeding anyway;\n"
        "verify the workspace before trusting change/deletion detection.",
        file=sys.stderr,
    )


def load() -> dict[str, Entry]:
    """The flat ``{source key: entry}`` dict from MANIFEST_PATH, or {} if missing/empty/corrupt.

    Accepts both the stamped format-2 file (``{"meta": ..., "sources": {...}}`` — callers never
    see ``meta``) and a legacy flat mapping (read as sources-only; upgraded on the next save).
    A stamped workspace differing from the current one triggers one stderr warning."""
    path = config.MANIFEST_PATH
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        return {}
    if not text.strip():
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("sources"), dict):
        meta = data.get("meta")
        if isinstance(meta, dict):
            _check_workspace(meta)
        return data["sources"]
    return data  # legacy flat manifest: the whole mapping IS the sources dict


def save(manifest: dict[str, Entry]) -> None:
    """Write ``{"meta": {format, workspace}, "sources": manifest}`` to MANIFEST_PATH
    (sort_keys, indent=2, trailing newline). ``manifest`` is the flat sources dict the callers
    hold; the workspace stamp records WHICH workspace the keys are relative to."""
    path = config.MANIFEST_PATH
    config.robust_mkdir(path.parent)
    data = {"meta": {"format": MANIFEST_FORMAT, "workspace": _workspace_stamp()}, "sources": manifest}
    text = json.dumps(data, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def is_pending(manifest: dict[str, Entry], src: Path) -> bool:
    """True if rel_key(src) absent OR its stored sha != file_sha256(src)."""
    key = rel_key(src)
    if key not in manifest:
        return True
    return entry_sha(manifest[key]) != file_sha256(src)


def mark_done(
    manifest: dict[str, Entry], src: Path, model: str | None = None, rules_version: str | None = None
) -> None:
    """Record ``src`` as ingested: manifest[rel_key(src)] = {sha256, model, rules_version}
    (mutates in place; caller saves). ``model`` is the model/backend that imported it
    (config.ingest_model_label) and ``rules_version`` the effective-rules hash it ran under
    (config.rules_version — compute once per run, not per source); pass None for a source no
    model imported."""
    manifest[rel_key(src)] = make_entry(file_sha256(src), model, rules_version)
