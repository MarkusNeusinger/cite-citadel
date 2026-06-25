"""Tracks which raw files were already ingested so re-running is idempotent and cheap.

A tiny committed JSON file wiki/.okf_ingested.json maps the source's repo-relative
posix path -> sha256 of its content. A file is (re)ingested only if absent or its
hash changed. No DB.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import config


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


def load() -> dict[str, str]:
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


def save(manifest: dict[str, str]) -> None:
    """json.dump(manifest, sort_keys=True, indent=2) to MANIFEST_PATH (+ trailing
    newline)."""
    path = config.MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def is_pending(manifest: dict[str, str], src: Path) -> bool:
    """True if rel_key(src) absent OR its stored sha != file_sha256(src)."""
    key = rel_key(src)
    if key not in manifest:
        return True
    return manifest[key] != file_sha256(src)


def mark_done(manifest: dict[str, str], src: Path) -> None:
    """manifest[rel_key(src)] = file_sha256(src) (mutates in place; caller saves)."""
    manifest[rel_key(src)] = file_sha256(src)
