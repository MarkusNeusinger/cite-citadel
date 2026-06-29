"""Tracks which raw files were already ingested so re-running is idempotent and cheap.

A tiny committed JSON file wiki/.citadel_ingested.json maps the source's repo-relative posix path
(e.g. 'raw/notes.md') to a small record of how it was last ingested:

    {"sha256": "<hex>", "model": "claude:sonnet"}

``sha256`` is the hash of the source's content (a file is (re)ingested only if absent or its
hash changed); ``model`` is the model/backend that imported it (``config.ingest_model_label``),
so you can see WHICH raw file was imported by WHICH model. ``model`` is omitted for a source
that no model imported (a binary/unreadable file that was only seen and skipped).

Backward compatible: an older manifest whose value is a bare sha STRING is still read — that
form simply carries no model. No DB.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import config

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
    """Stable identity key for a raw source: its posix path relative to config.REPO_ROOT when it
    lives under the repo (e.g. 'raw/notes.md', 'docs/karpathy-llm-wiki.md'), else its ABSOLUTE
    posix path (e.g. 'T:/team-wiki/raw/notes.md') so a source on a mounted network drive gets a
    unique, resolvable key instead of colliding on basename. Thin wrapper over the single
    source of truth, config.rel_or_abs_posix."""
    return config.rel_or_abs_posix(src)


def make_entry(sha: str, model: str | None = None) -> Entry:
    """Build a manifest value from a content hash and the importing model. ``model`` is included
    only when set, so a source no model imported (binary/unreadable) records just its sha."""
    entry: dict = {"sha256": sha}
    if model:
        entry["model"] = model
    return entry


def entry_sha(entry: Entry) -> str:
    """The sha256 stored for a manifest value, accepting both the current record form
    ({"sha256": ...}) and the legacy bare-string form (the sha itself). Empty for a repo
    entry (which is versioned by commit, not a content sha)."""
    if isinstance(entry, dict):
        return str(entry.get("sha256") or "")
    return str(entry or "")


def make_repo_entry(commit: str, model: str | None = None, remote: str | None = None) -> dict:
    """Build a manifest value for a GIT-REPOSITORY source: ``{"kind": "git", "commit": ...}``
    plus the importing ``model`` and the repo's ``remote`` URL when known. ``commit`` is the repo's
    version identity (a HEAD commit, possibly with a ``+dirty.<hash>`` suffix, or a ``snap.<hash>``
    aggregate for a git-less snapshot) — the source is re-ingested when it changes."""
    entry: dict = {"kind": "git", "commit": commit}
    if model:
        entry["model"] = model
    if remote:
        entry["remote"] = remote
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


def model_of(manifest: dict[str, Entry], key: str) -> str | None:
    """The model that imported the source ``key``, or None if it is untracked / has no model."""
    if key not in manifest:
        return None
    return entry_model(manifest[key])


def load() -> dict[str, Entry]:
    """json.loads(MANIFEST_PATH) or {} if missing/empty/corrupt."""
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
    return data


def save(manifest: dict[str, Entry]) -> None:
    """json.dump(manifest, sort_keys=True, indent=2) to MANIFEST_PATH (+ trailing
    newline)."""
    path = config.MANIFEST_PATH
    config.robust_mkdir(path.parent)
    text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def is_pending(manifest: dict[str, Entry], src: Path) -> bool:
    """True if rel_key(src) absent OR its stored sha != file_sha256(src)."""
    key = rel_key(src)
    if key not in manifest:
        return True
    return entry_sha(manifest[key]) != file_sha256(src)


def mark_done(manifest: dict[str, Entry], src: Path, model: str | None = None) -> None:
    """Record ``src`` as ingested: manifest[rel_key(src)] = {sha256, model} (mutates in place;
    caller saves). ``model`` is the model/backend that imported it (config.ingest_model_label);
    pass None for a source no model imported."""
    manifest[rel_key(src)] = make_entry(file_sha256(src), model)
