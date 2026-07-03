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

**The manifest is also the scan cache** (docs/refactor-plan.md Z3 — no second cache file): an
entry additionally records the source's stat at hash time — ``size`` + ``mtime_ns`` (opaque
equality tokens, never ordered: an older-but-different mtime invalidates exactly like a newer
one), ``ctime_ns`` (one more opaque equality token — authoritative when recorded, see
:func:`entry_trusts_stat`), and ``hashed_at_ns`` (the newest reading of the SOURCE file's own
stat clock available at hash time — never the manifest write time or the local wall clock,
because the wiki and the raw share can sit on different servers with skewed clocks). These are a
SKIP HINT only: sha256 stays the sole arbiter of "changed"; a stat mismatch merely costs one
stream-hash. Entries without the stat fields (hand-seeded, pre-refactor) are rehashed once and
backfilled. No inode is recorded, and ctime is never a hard requirement — restic/borg made the
same call for SMB, where inode/ctime are not stable across mounts (a flaky ctime here degrades
to a harmless rehash, never to a missed change, because a recorded-but-mismatching ctime always
forces the rehash and the sha decides).

:func:`load` returns the FLAT sources dict — callers never see ``meta`` — and :func:`save` stamps
``meta`` with the CURRENT workspace root. A legacy flat manifest (pre-workspace, no meta) is read
as sources-only and upgraded to the stamped form on the next save; greenfield, no migration
tooling (docs/refactor-plan.md). A bare-sha-string entry value is likewise still read (it simply
carries no model). No DB.
"""

from __future__ import annotations

import hashlib
import json
import os
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


# The racy-timestamp window (ns): the git model, sized for SMB/FAT timestamp granularity. An
# entry whose recorded mtime_ns is at/after its hashed_at_ns minus this window COULD have been
# rewritten after it was hashed without moving its mtime — it is distrusted and rehashed.
RACY_WINDOW_NS = 3 * 10**9


def stat_fields(st: os.stat_result) -> dict:
    """The scan-cache stat fields recorded on an entry, from ONE ``os.stat`` of the source taken
    when it was hashed. ``hashed_at_ns`` is the newest reading of the source file's OWN stat
    clock in that stat (max of atime/mtime/ctime) — the cross-share-clock rule: comparing the
    source's mtime against the wiki server's (or the local) clock would be meaningless under
    clock skew, so the racy guard only ever compares source-clock readings with each other."""
    return {
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "ctime_ns": st.st_ctime_ns,
        "hashed_at_ns": max(st.st_atime_ns, st.st_mtime_ns, st.st_ctime_ns),
    }


def entry_trusts_stat(entry: Entry | None, st: os.stat_result) -> bool:
    """The quick check: True when ``entry``'s recorded stat proves the file unchanged since it
    was hashed, so the recorded sha can be reused WITHOUT reading the file.

    (size, mtime_ns) must match exactly — both opaque equality tokens, never ordered. That alone
    is not proof (a same-size rewrite whose mtime lands on the same token — coarse SMB/FAT
    granularity, or a backdating ``utime`` — is the classic racy-git case), so one of two
    guards must additionally hold:

    - ``ctime_ns`` equality — AUTHORITATIVE whenever the entry recorded one: POSIX bumps ctime
      on EVERY content/metadata change (a backdating ``utime`` included) and userspace cannot
      set it back, so a matching ctime proves nothing happened since the hash and a MISMATCH
      proves something did — it must distrust, never fall through to the window below (which a
      forged mtime could otherwise talk into trusting). An unstable SMB ctime therefore
      degrades to a harmless re-hash, never to a missed change. (On Windows ``st_ctime`` is the
      stable creation time: a match still rules out the file being REPLACED, but — like git on
      Windows — a deliberately backdated same-size in-place rewrite is invisible to stat and
      only ``--full-rescan`` or a real mtime change surfaces it. See the PR4 deviation note in
      docs/refactor-plan.md Z3.)
    - the racy-timestamp window (the git model, for entries carrying no ctime — hand-seeded or
      written by another tool): the file's mtime must lie comfortably BEFORE the recorded
      ``hashed_at_ns`` (both readings of the source's own clock), beyond
      :data:`RACY_WINDOW_NS` — i.e. the content provably predates the hash.

    Anything else — missing fields, mismatched tokens, a fresh-at-hash-time mtime with no ctime
    to vouch for it — fails the quick check and costs exactly one stream-hash (sha256 stays the
    sole arbiter of "changed")."""
    if not isinstance(entry, dict):
        return False
    if entry.get("size") != st.st_size or entry.get("mtime_ns") != st.st_mtime_ns:
        return False
    ctime = entry.get("ctime_ns")
    if isinstance(ctime, int):
        return ctime == st.st_ctime_ns
    hashed_at = entry.get("hashed_at_ns")
    return isinstance(hashed_at, int) and st.st_mtime_ns < hashed_at - RACY_WINDOW_NS


def make_entry(
    sha: str, model: str | None = None, rules_version: str | None = None, st: os.stat_result | None = None
) -> Entry:
    """Build a manifest value from a content hash, the importing model, and the rules-tree hash
    the importing session ran under (``config.rules_version``). ``model``/``rules_version`` are
    included only when set, so a source no model imported (binary/unreadable) records just its
    sha. ``st`` (the stat taken when the file was hashed) adds the scan-cache stat fields
    (:func:`stat_fields`) so later runs can skip rehashing the unchanged file."""
    entry: dict = {"sha256": sha}
    if model:
        entry["model"] = model
    if rules_version:
        entry["rules_version"] = rules_version
    if st is not None:
        entry.update(stat_fields(st))
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
    git-less snapshot) — the source is re-ingested when it changes. No scan-cache stat fields: a
    repo is a directory versioned by commit, not a stat-checkable file."""
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


# The ``meta`` section of the most recently load()ed manifest ({} when the file was missing,
# corrupt, or a legacy flat mapping). ONE json parse serves both the load itself and ingest's
# stamped-workspace probe (:func:`stamped_workspace_mismatch`), which must read the stamp as it
# was BEFORE this run's saves re-stamp the file.
_last_meta: dict = {}


def _stamped_workspace(meta: dict) -> str:
    """The workspace stamp recorded in a manifest ``meta`` section ("" when absent) — the one
    extraction both the load-time warning and the mismatch probe read."""
    return str(meta.get("workspace") or "")


# Stamped roots already warned about, so one mismatching manifest warns ONCE per process instead
# of once per load() (rebuild_indexes and the viewer re-load the manifest during a single run).
_warned_workspaces: set[str] = set()


def _check_workspace(meta: dict) -> None:
    """Print ONE prominent stderr warning when the manifest was stamped by a workspace rooted
    somewhere else. A warning, NOT an error: the same share can legitimately be mounted at
    different paths (a Windows drive letter vs a WSL /mnt path), so a mismatch is suspicious but
    must not block. The HARD workspace-identity guard lives in ingest (Z1 "key-space
    stability"): when the stamp mismatches AND the manifest's relative keys do not resolve on
    disk (a nested marker / moved checkout re-keyed the world, not just a dual mount), the
    deletion sweep is REFUSED with an actionable error — see
    :func:`stamped_workspace_mismatch` and the guard in :func:`citadel.ingest.ingest`."""
    stamped = _stamped_workspace(meta)
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
    see ``meta``, but it is stashed for :func:`stamped_workspace_mismatch`) and a legacy flat
    mapping (read as sources-only; upgraded on the next save). A stamped workspace differing
    from the current one triggers one stderr warning."""
    global _last_meta
    _last_meta = {}
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
            _last_meta = meta
            _check_workspace(meta)
        return data["sources"]
    return data  # legacy flat manifest: the whole mapping IS the sources dict


def stamped_workspace_mismatch() -> str | None:
    """The workspace root the manifest was stamped by, WHEN it differs from the current one —
    else None (no manifest, no stamp, or a matching stamp). Reads the ``meta`` the most recent
    :func:`load` stashed — ONE json parse per read, not a second parse of the same file — so
    call it right after ``load()`` and before anything ``save()``s (a save re-stamps the FILE
    with the CURRENT root, and a later load would then read the fresh stamp). Ingest's
    workspace-identity hard guard reads this to decide whether the manifest's key space can be
    trusted for a deletion sweep."""
    stamped = _stamped_workspace(_last_meta)
    if not stamped or stamped == _workspace_stamp():
        return None
    return stamped


def workspace_rekeyed(manifest: dict[str, Entry]) -> bool:
    """True when the manifest's RELATIVE key space does not belong to THIS workspace: the
    majority of its workspace-relative keys do not resolve on disk under the current root.

    The named discriminator behind ingest's workspace-identity HARD guard, applied when the
    stamped workspace differs from the current one (:func:`stamped_workspace_mismatch`). Two
    worlds produce that mismatch: a DUAL MOUNT (the same share mounted at a different path),
    where the keys still resolve — majority resolves → warn only, the run proceeds; and a
    nested marker / moved checkout that RE-KEYED the world, where they do not — majority
    missing → refuse the deletion sweep, because the seen-set diff would otherwise read the
    entire old key space as deleted. Absolute keys are excluded: they resolve independently of
    the workspace root, so they can vouch for neither world."""
    rel_keys = [k for k in manifest if not Path(k).is_absolute()]
    resolving = sum(1 for k in rel_keys if config.source_path_for_key(k).exists())
    return bool(rel_keys) and resolving * 2 < len(rel_keys)


def save(manifest: dict[str, Entry]) -> None:
    """Write ``{"meta": {format, workspace}, "sources": manifest}`` to MANIFEST_PATH
    (sort_keys, indent=2, trailing newline). ``manifest`` is the flat sources dict the callers
    hold; the workspace stamp records WHICH workspace the keys are relative to."""
    path = config.MANIFEST_PATH
    config.robust_mkdir(path.parent)
    data = {"meta": {"format": MANIFEST_FORMAT, "workspace": _workspace_stamp()}, "sources": manifest}
    text = json.dumps(data, sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def mark_done(
    manifest: dict[str, Entry],
    src: Path,
    model: str | None = None,
    rules_version: str | None = None,
    *,
    sha: str | None = None,
    st: os.stat_result | None = None,
) -> None:
    """Record ``src`` as ingested: manifest[rel_key(src)] = {sha256, model, rules_version} plus
    the scan-cache stat fields (mutates in place; caller saves). ``model`` is the model/backend
    that imported it (config.ingest_model_label) and ``rules_version`` the effective-rules hash
    it ran under (config.rules_version — compute once per run, not per source); pass None for a
    source no model imported. ``sha``/``st`` are the content hash and the stat discovery already
    took for this source — pass them through so the file is stream-hashed exactly ONCE per run
    (and so the recorded sha is the content that was actually ingested, not a post-session
    re-read); when omitted (direct callers), they are computed here."""
    if st is None:
        try:
            st = src.stat()
        except OSError:
            st = None
    if sha is None:
        sha = file_sha256(src)
    manifest[rel_key(src)] = make_entry(sha, model, rules_version, st=st)
