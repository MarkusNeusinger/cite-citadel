"""The per-source staging machinery — everything that touches wiki files deterministically.

The staging-copy discipline (:func:`_make_staging` / :func:`_sweep_stale_staging` /
:func:`_redirect_wiki`), the content snapshot + diff-by-hash (:func:`_snapshot` /
:func:`_diff`), the validate-and-restamp pass every agent edit goes through
(:func:`_validate_and_restamp`), the deterministic rename-link repair
(:func:`_repair_renames`), the share-hardened file primitives (:func:`_robust_copy_file` /
:func:`_robust_rmtree`), and the one step that ever writes the live wiki: the non-destructive,
base-aware :func:`_promote` guarded by :data:`_LIVE_WIKI_LOCK`.

Split out of :mod:`citadel.ingest`, which re-exports these names — the module boundary is an
implementation detail; ``ingest._promote`` etc. remain the addressable seams. This machinery is
load-bearing (all-or-nothing promotes + network-share hardening) — don't simplify it away.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import threading
import time
from pathlib import Path

from . import config, okf, store, validate
from .okf import Page


def _hash_pages(pages: list[Page]) -> dict[str, str]:
    """``{rel_path: sha256(on-disk bytes)}`` for the given pages. Hash the bytes (not the
    parsed body) so a frontmatter-only change still registers; skip a page that vanished
    mid-read."""
    snap: dict[str, str] = {}
    for page in pages:
        try:
            target = okf.safe_join(config.wiki_dir(), page.rel_path)
            snap[page.rel_path] = hashlib.sha256(target.read_bytes()).hexdigest()
        except (okf.OKFError, OSError):
            continue
    return snap


def _snapshot() -> dict[str, str]:
    """Content-hash snapshot of every CURRENT non-reserved wiki page. Reuses ``store.load``
    so reserved files (index.md, log.md, ``*/index.md``, dotfiles) are excluded by the
    loader's own rule — one source of truth for 'what is a page'."""
    return _hash_pages(store.load())


def _diff(before: dict[str, str], after: dict[str, str]) -> tuple[list[str], list[str], list[str]]:
    """``(created, updated, deleted)``, each sorted. created = in after not before;
    deleted = in before not after; updated = in both with a changed hash."""
    created = sorted(k for k in after if k not in before)
    deleted = sorted(k for k in before if k not in after)
    updated = sorted(k for k in after if k in before and after[k] != before[k])
    return created, updated, deleted


def _canonical_resource_key(resource: str, rel_key: str) -> str | None:
    """Return the canonical source key to replace a changed page's ``resource`` with, or None to
    leave it untouched.

    The ingest agent occasionally records a SHORTENED ``resource`` for an out-of-repo source: for a
    file whose real key is an absolute path (``//host/share/raw/notes.pdf`` — what a source on a
    mounted network drive resolves to), it writes the conventional repo-relative ``raw/notes.pdf``
    that every schema example uses. That short form does not resolve to a real file (the file is on
    the drive, not under the repo), so it (a) fails ``bad_resource`` validation and rolls the whole
    source back — discarding a long, expensive session over a cosmetic path mismatch — and (b) would
    not equal the manifest key, so a later move/delete of the source could not find the page
    (``store.find_raw_references`` matches the ``resource`` frontmatter against the EXACT key).

    Repair ONLY the unambiguous case: the written value does not resolve to a file, it shares the
    source key's basename, and the source key itself resolves. Then the page plainly names THIS
    source — canonicalize it to ``rel_key``. A ``resource`` that already resolves (a valid source,
    possibly a DIFFERENT one on a page this session merged into) or whose basename differs is left
    alone, so a legitimately different ``resource`` is never clobbered. For an in-repo source the
    agent's ``raw/x.md`` already equals ``rel_key``, so this is a no-op — the in-repo path is
    unchanged."""
    written = (resource or "").strip().replace("\\", "/")
    canon = rel_key.replace("\\", "/")
    if not written or written == canon:
        return None
    if config.source_path_for_key(written).is_file():
        return None  # already points at a real file — don't second-guess it
    same_basename = written.rsplit("/", 1)[-1] == canon.rsplit("/", 1)[-1]
    if same_basename and config.source_path_for_key(canon).is_file():
        return canon
    return None


def _page_errors(rel_path: str, page: Page) -> set[tuple[str, str]]:
    """The error-severity issues a page ALREADY carries, as exact ``(category, detail)`` pairs.

    The unit of :func:`_validate_and_restamp`'s inherited-damage carve-out. Deliberately exact: a
    dangling ``[^s1]`` to one missing file does not excuse a second one to a different file, and a
    page that was missing ``tags`` before is not thereby allowed to lose its ``title`` too."""
    return {
        (issue.category, issue.detail)
        for issue in validate.validate_page(rel_path, page.frontmatter, page.body)
        if issue.severity == "error"
    }


def _validate_and_restamp(
    rel_paths: list[str], rel_key: str, inherited: dict[str, Page] | None = None, carried: list[str] | None = None
) -> list[str]:
    """Re-impose invariants on each changed page (``validate.validate_page``) and, if clean,
    canonicalize + re-stamp it through ``store.write_page`` (so the YAML is canonical, the
    ``type`` is enforced, and a fresh UTC ``timestamp`` is set even though the agent wrote the
    file). Before validating, a changed page whose ``resource`` is a shortened-but-broken reference
    to the source being ingested is canonicalized to its real key (:func:`_canonical_resource_key`),
    so an out-of-repo source the agent recorded as ``raw/<file>`` is repaired rather than failing the
    run. Returns one error string per error-severity validation issue; when any are returned the
    caller rolls the whole source back (all-or-nothing), so an invalid page never persists in the
    wiki — the issues are surfaced in the report instead.

    ``inherited`` (``{rel_path: page}`` as the wiki held it BEFORE this source's first session) is
    what keeps that all-or-nothing rule from turning one broken page into a corpus-wide outage. A
    page can already be invalid when a source touches it — a failed deletion cleanup leaves a
    dangling ``[^sN]`` behind, a raw file is moved out from under a ``resource``, a hand edit lands
    — and without this the NEXT source that merely appends a fact to that page inherits the blame,
    is rolled back in full, and fails again on every run: the money is spent, nothing is kept, and
    every source whose facts belong on that page is stuck until a human finds and fixes it.
    So an error whose exact ``(category, detail)`` the page already had is not this source's
    damage: it is reported through ``carried`` (an out-list the caller surfaces as a run warning,
    and which ``citadel lint`` names in full) instead of failing the source. Every OTHER error still
    fails it, so nothing this source actually broke can reach the live wiki — and the page is no
    worse off than the copy already promoted there."""
    errors: list[str] = []
    for rel_path in sorted(set(rel_paths)):
        try:
            page = store.read_page(rel_path)
        except (FileNotFoundError, okf.OKFError) as exc:
            errors.append(f"{rel_key}: re-read {rel_path}: {exc}")
            continue
        canonical = _canonical_resource_key(str(page.frontmatter.get("resource") or ""), rel_key)
        if canonical is not None:
            page.frontmatter["resource"] = canonical
        bad = [
            issue
            for issue in validate.validate_page(rel_path, page.frontmatter, page.body)
            if issue.severity == "error"
        ]
        prior = (inherited or {}).get(rel_path)
        if bad and prior is not None:
            already = _page_errors(rel_path, prior)
            if carried is not None:
                carried.extend(
                    f"{rel_path}: {issue.category}: {issue.detail}"
                    for issue in bad
                    if (issue.category, issue.detail) in already
                )
            bad = [issue for issue in bad if (issue.category, issue.detail) not in already]
        if bad:
            for issue in bad:
                errors.append(f"{rel_key}: invalid page {rel_path}: {issue.category}: {issue.detail}")
            continue
        try:
            store.write_page(rel_path, page.frontmatter, page.body)
        except okf.OKFError as exc:
            errors.append(f"{rel_key}: rewrite {rel_path}: {exc}")
    return errors


def _repair_renames(before_pages: list[Page], created: list[str], deleted: list[str]) -> None:
    """Deterministic safety net for inbound links the agent may not have fully repointed.

    A page that was DELETED while a page with the SAME title was CREATED this source is a
    rename/move; repoint every inbound cross-link from the old path to the new one via the
    tested ``store.rewrite_links``. A merge into a page whose title CHANGES (or a pre-existing
    survivor) is not auto-derivable here — the agent is asked to repoint those itself, and
    ``find_broken_links``/``lint`` surface anything missed."""
    if not deleted or not created:
        return
    created_by_title: dict[str, list[str]] = {}
    for rel_path in created:
        try:
            page = store.read_page(rel_path)
        except (FileNotFoundError, okf.OKFError):
            continue
        title = str(page.frontmatter.get("title") or "").strip().lower()
        if title:
            created_by_title.setdefault(title, []).append(rel_path)

    before_by_path = {p.rel_path: p for p in before_pages}
    rename_map: dict[str, str] = {}
    for old in deleted:
        page = before_by_path.get(old)
        if not page:
            continue
        title = str(page.frontmatter.get("title") or "").strip().lower()
        matches = created_by_title.get(title, [])
        if title and len(matches) == 1 and matches[0] != old:
            rename_map[old] = matches[0]
    if rename_map:
        store.rewrite_links(rename_map)


# Deleting a directory tree can transiently fail or lag when the wiki lives on a network share
# (``CITADEL_WIKI_DIR`` pointing at an SMB/UNC path): a file may be momentarily locked (antivirus,
# indexing, an open handle) or the share may still report the directory present right after its
# contents were removed. Retry a handful of times before giving up.
_RMTREE_ATTEMPTS = 5


def _robust_rmtree(path: str | os.PathLike) -> None:
    """Best-effort recursive delete of a staging tree — the share-hardened
    :func:`config.robust_rmtree` under ingest's own name (it lives in ``config`` because resume's
    checkpoint slots need exactly the same read-only-bit/retry handling)."""
    config.robust_rmtree(path, attempts=_RMTREE_ATTEMPTS)


def _sha256(path: Path) -> str:
    """sha256 hexdigest of a file's bytes, streamed so a large page stays memory-bounded."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _files_equal(a: Path, b: Path) -> bool:
    """True if ``b`` exists and is byte-identical to ``a`` (size short-circuit, then content hash).
    A transient read error counts as 'not equal' so the safer path (re-copy) is taken."""
    try:
        if not b.exists():
            return False
        if a.stat().st_size != b.stat().st_size:
            return False
        return _sha256(a) == _sha256(b)
    except OSError:
        return False


def _robust_copy_file(src: Path, dst: Path, attempts: int = _RMTREE_ATTEMPTS) -> None:
    """Copy ``src`` -> ``dst`` ATOMICALLY: write a temp sibling, then ``os.replace`` it into place
    (atomic on one volume), retrying the network-share hiccups that flake a single copy. If every
    attempt fails the temp is cleaned up and the error is raised with ``dst`` LEFT UNTOUCHED — so a
    live page is never observed truncated/half-written (the caller fails the source and retries next
    run, keeping the page's previous content)."""
    tmp = dst.with_name(dst.name + ".citadeltmp")
    for attempt in range(attempts):
        try:
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
            return
        except OSError:
            with contextlib.suppress(OSError):
                if tmp.exists():
                    tmp.unlink()
            if attempt == attempts - 1:
                raise  # leave dst as it was — never a half-written live page
            time.sleep(0.2 * (attempt + 1))


# The staging identity sentinel _make_staging drops into every fresh copy — see _staging_intact.
_STAGING_SENTINEL = ".citadel_staging"

# Monotonic per-process counter so each staging dir gets a UNIQUE name — see _make_staging.
_STAGING_SEQ = 0
# Guards the counter itself: with `--jobs N` several workers mint staging names at once, and two
# sources sharing a staging directory is exactly the merge-into-leftover-content failure the unique
# name exists to prevent.
_STAGING_SEQ_LOCK = threading.Lock()

# THE serialization point for every touch of the LIVE wiki: cloning it into a staging copy (plus
# recording that clone's base state) and promoting a finished source back onto it. Sessions — the
# minutes-long part — run fully in parallel OUTSIDE this lock; what it serializes is milliseconds of
# file copying, so it costs throughput nothing and buys the two properties `--jobs N` needs:
#   * a staging copy is a point-in-time image of the live wiki, never a half-promoted mixture;
#   * two promotes can never interleave their copy-over and prune phases.
# It is a plain lock, not the workspace run lock (:mod:`runlock`): that one keeps two PROCESSES off
# one workspace, this one keeps two threads of ONE run off one live wiki.
_LIVE_WIKI_LOCK = threading.Lock()


def _staging_prefix(live: Path) -> str:
    """The shared filename prefix of this wiki's staging siblings (``.<name>.staging.``)."""
    return f".{live.name}.staging."


def _sweep_stale_staging(live: Path) -> None:
    """Best-effort removal of EVERY staging sibling of ``live`` — called ONCE at run start,
    under the exclusive workspace run lock (:mod:`runlock`), where any staging dir on disk is
    by definition a leftover from a dead run (they are inert dotfiles, but we don't let them
    pile up). This used to run inside every :func:`_make_staging` call, which is exactly what
    made two concurrent runs destructive: the first run's next source rm-tree'd the second
    run's IN-FLIGHT staging copy mid-session."""
    with contextlib.suppress(OSError):
        for sibling in live.parent.iterdir():
            if sibling.name.startswith(_staging_prefix(live)):
                _robust_rmtree(sibling)


def _make_staging(live: Path) -> Path:
    """Create a fresh STAGING copy of the live wiki and return its path.

    Staging is a SIBLING of the live wiki (same parent, same depth) — never a system temp dir —
    so every relative citation/cross-link the agent writes (``../../raw/x.md`` and page-to-page
    links) resolves identically before and after the promote. The agent edits this copy, so the
    live wiki is never the scratch space.

    The staging name is UNIQUE per call (pid + a monotonic counter), so a copy can NEVER merge into
    leftover content from a crashed run and resurrect pages that were deleted — the live wiki is
    always copied into a brand-new directory. Stale siblings from earlier crashed runs are swept
    once at run start (:func:`_sweep_stale_staging`), never here — a per-call sweep would delete a
    concurrent run's in-flight staging. On a copy failure the
    partial staging is cleaned up before the error propagates (the caller reports it and the live
    wiki is untouched). When the live wiki does not exist yet (first run) staging starts empty."""
    global _STAGING_SEQ
    parent = live.parent
    prefix = _staging_prefix(live)
    with _STAGING_SEQ_LOCK:
        _STAGING_SEQ += 1
        seq = _STAGING_SEQ
    staging = parent / f"{prefix}{os.getpid()}.{seq}"
    _robust_rmtree(staging)  # paranoia: clear an identical-named leftover before a clean copy
    try:
        if live.is_dir():
            # Skip any half-written *.citadeltmp left in live by an interrupted promote, so a stray
            # temp never rides along into staging (and back out again). A wiki-history `.git`
            # (wikigit) stays out too: _promote never syncs hidden dirs anyway, and copying a
            # whole repository per source would only burn I/O.
            shutil.copytree(live, staging, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.citadeltmp", ".git"))
        else:
            config.robust_mkdir(staging)
        # Identity sentinel: proves at check time that THIS directory is still the tree this call
        # created. A bare `is_dir()` cannot tell "still my staging copy" from "deleted and
        # re-created empty" (or replaced by a symlinked directory) — and on a first ingest that
        # replacement would diff as an empty wiki and stamp the source as a silent zero-change
        # success. A dotfile, so it is invisible to the content walks, the promote, and the agent
        # (which is told never to touch dotfiles); the unique dir name is the token, tying the
        # file to this staging instance. See :func:`_staging_intact`.
        (staging / _STAGING_SENTINEL).write_text(staging.name, encoding="utf-8")
    except OSError:
        _robust_rmtree(staging)
        raise
    return staging


def _staging_intact(staging: Path) -> bool:
    """True while ``staging`` is still the directory :func:`_make_staging` created — its identity
    sentinel is present and names this exact staging dir. False when the tree was deleted,
    deleted-and-recreated, or replaced (a weak agent inventing a "publish"/cleanup step), where a
    plain existence check would read the impostor as an empty wiki. Read errors count as not
    intact — the conservative answer, since the caller fails the source rather than trusting an
    unverifiable tree."""
    try:
        return (Path(staging) / _STAGING_SENTINEL).read_text(encoding="utf-8") == Path(staging).name
    except OSError:
        return False


def _redirect_wiki(staging: Path):
    """Point every wiki-derived config path — and ``CITADEL_WIKI_DIR`` for the child processes the
    session spawns (the agentic CLI and the ``citadel check`` it shells out to) — at ``staging``
    for the duration of one session, so the agent reads/writes/validates the STAGING copy rather
    than the live wiki. The raw/docs dirs are left untouched.

    Thin alias for :func:`config.wiki_redirect`, kept under ingest's own name because this is where
    the staging discipline lives. The redirect is CONTEXT-local, not process-global: it never
    assigns ``config.WIKI_DIR`` or ``os.environ`` (the child's copy is built per spawn by
    ``config.child_env``), which is precisely what lets ``--jobs N`` keep several sources staged at
    once — each worker thread holds its own redirect, and the main thread still sees the live
    wiki."""
    return config.wiki_redirect(staging)


def _is_reserved_name(name: str) -> bool:
    """True for files the promote must NOT sync: the generated nav files (``index.md``/``log.md`` at
    any level), any dotfile (the ``.citadel_ingested.json`` manifest, etc.), and a half-written
    ``*.citadeltmp`` temp. Finalize regenerates the indexes and the ingest loop owns the manifest, so a
    per-source promote never lays a stale one down."""
    return name.startswith(".") or name in ("index.md", "log.md") or name.endswith(".citadeltmp")


def _content_files(root: Path) -> dict[str, Path]:
    """Map ``relposix -> abs path`` for every non-reserved file under ``root`` (skipping hidden
    dirs and :func:`_is_reserved_name` files) — the agent-authored content a promote syncs."""
    out: dict[str, Path] = {}
    if not Path(root).is_dir():
        return out
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in files:
            if _is_reserved_name(name):
                continue
            p = Path(dirpath) / name
            out[p.relative_to(root).as_posix()] = p
    return out


def _sha256_or_none(path: Path) -> str | None:
    """:func:`_sha256` that answers None instead of raising on an unreadable/vanished file — so a
    comparison against a recorded base hash treats it as "not what the base had" (the conservative
    answer) rather than blowing up a promote."""
    try:
        return _sha256(path)
    except OSError:
        return None


def _content_hashes(root: Path) -> dict[str, str]:
    """``{relposix: sha256}`` over :func:`_content_files` — a wiki's content state as bytes, not as
    timestamps. Taken of the fresh STAGING clone, which is byte-for-byte the live
    wiki this source started from: under ``--jobs N`` it feeds the base-aware promote (so it can
    tell "this page is exactly what I started from" from "another source changed it while I was
    working"), and in serial mode the live-drift note on a failed source
    (``ingest_sessions._live_drift_note``). A file that vanishes or cannot be
    read mid-walk is simply omitted, which reads as "absent" — the conservative answer, since it
    makes the promote treat it as changed rather than silently overwriting it."""
    out: dict[str, str] = {}
    for rel, path in _content_files(root).items():
        with contextlib.suppress(OSError):
            out[rel] = _sha256(path)
    return out


class _ConcurrentChange(Exception):
    """The live wiki moved under a staged source: a page this promote would write or prune is no
    longer what it was when the source was cloned, because a CONCURRENT source's promote (only
    possible under ``--jobs N``) landed there first.

    Never a data-loss path — it is raised BEFORE the promote writes anything, so the live wiki keeps
    the other source's work untouched. The caller re-runs this source SERIALLY, at the end of its
    group: the fresh session then sees the page the other source wrote and merges into it, which is
    exactly what a serial run would have done in the first place."""


def _assert_base_unchanged(live: Path, base: dict[str, str], rels: set[str]) -> None:
    """Raise :class:`_ConcurrentChange` if any of ``rels`` no longer matches ``base`` in the live
    wiki. Only the paths a promote is about to TOUCH are checked: a concurrent source that created
    or rewrote some unrelated page is no conflict at all — that is the whole point of running
    sources in parallel."""
    for rel in sorted(rels):
        target = live / rel
        current: str | None = None
        with contextlib.suppress(OSError):
            if target.is_file():
                current = _sha256(target)
        if current != base.get(rel):
            raise _ConcurrentChange(
                f"another source changed {rel} while this one was being folded in "
                "(re-running it serially so it merges into the current wiki)"
            )


def _promote(staging: Path, live: Path, allow_emptying: bool = False, base: dict[str, str] | None = None) -> None:
    """Copy a validated STAGING wiki's CONTENT onto the LIVE wiki WITHOUT ever emptying or
    half-writing it.

    Only the agent-authored content pages are synced — the generated ``index.md``/``log.md`` and the
    manifest are excluded (finalize regenerates the indexes; the loop owns the manifest), so a
    promote never lays a stale index down. Non-destructive order: every changed/new page is written
    into live FIRST (each atomically, via :func:`_robust_copy_file`), so at every instant the live
    wiki holds at least its previous content; only THEN are the pages the agent deleted pruned. A
    promote interrupted partway therefore leaves live a SUPERSET of valid pages — never an empty or
    corrupt tree — which a later full run reconciles. Directory creation tolerates the network
    share's WinError 183 race.

    Safety valve: an ingest/reconcile session must never reduce the live wiki to ZERO content pages.
    If staging carries no content page (a buggy/looping/adversarial session that deleted everything)
    while the live wiki has some, the promote is REFUSED — raising so the caller fails the source and
    retries it next run, with the live wiki left exactly as it was rather than emptied.
    ``allow_emptying`` lifts that guard for a ``delete`` cleanup, where removing the last source's
    only page legitimately leaves the wiki empty.

    ``base`` — the content hashes of the wiki this source was CLONED from (:func:`_content_hashes`
    over its staging copy, recorded only under ``--jobs N``) — makes the promote base-aware, which is what lets two sources
    promote onto one wiki without eating each other's work:

    * WHAT IS WRITTEN is this source's own delta — the staging files that differ from the BASE, not
      from the current live wiki. Staging also holds untouched copies of every page the source did
      not write, and judging those by "differs from live" would let this promote revert a page a
      concurrent source had just rewritten;
    * the PRUNE is likewise derived from the base, so a page a concurrent source created (absent
      from this source's base AND from its staging copy) is left alone instead of being deleted as
      "the agent removed it";
    * every path this promote would write or prune must still match the base, else
      :class:`_ConcurrentChange` is raised BEFORE anything is written and the source is re-run
      serially — the two sessions disagreed about one page, and a stale session must never win.

    ``base=None`` (the default, and the whole of the serial path) keeps the original semantics
    byte-for-byte: prune whatever live has and staging does not, no conflict check, no extra
    hashing."""
    staging, live = Path(staging), Path(live)
    config.robust_mkdir(live)

    staging_content = _content_files(staging)
    live_content = _content_files(live)

    staging_pages = [r for r in staging_content if r.endswith(".md")]
    # What "the wiki had pages" means for the anti-emptying valve: with a base, the wiki AS THIS
    # SOURCE FOUND IT — a page a concurrent source added in the meantime is not this session's to
    # answer for, in either direction.
    had_pages = [r for r in (live_content if base is None else base) if r.endswith(".md")]
    if not allow_emptying and not staging_pages and had_pages:
        raise okf.OKFError(
            "refusing to promote: the session left the wiki with no content pages "
            "(treated as a failed source so the live wiki is not emptied)"
        )

    if base is None:
        changed = {rel: src for rel, src in staging_content.items() if not _files_equal(src, live / rel)}
        pruned = set(live_content) - set(staging_content)
    else:
        # With a base, a promote applies THIS source's own delta and nothing else. Which pages the
        # source touched is decided against its base — not against the current live wiki — because
        # its staging copy also holds untouched copies of every page it did NOT write: judging by
        # "differs from live" would make a page a CONCURRENT source just rewrote look like this
        # source's change, and copying the staging copy over it would silently revert that work.
        changed = {rel: src for rel, src in staging_content.items() if _sha256_or_none(src) != base.get(rel)}
        pruned = (set(base) & set(live_content)) - set(staging_content)
        # NOTE for the reader: this is a per-FILE merge, not a per-line one. Two sources that wrote
        # the same page do not get merged here — that is what the conflict below is for.
        # Before the first byte is written: refuse a promote built on a wiki that has moved on.
        _assert_base_unchanged(live, base, set(changed) | pruned)
        # A page whose bytes already match live needs no write (a re-run that reproduced it exactly).
        changed = {rel: src for rel, src in changed.items() if not _files_equal(src, live / rel)}

    # 1. Copy-over FIRST (atomic per page, only when the bytes differ).
    for rel, src in changed.items():
        dst = live / rel
        config.robust_mkdir(dst.parent)
        _robust_copy_file(src, dst)

    # 2. Prune the content pages the agent deleted (reserved/generated files are left untouched).
    for rel in pruned:
        with contextlib.suppress(OSError):
            (live / rel).unlink()

    # 3. Best-effort sweep of any leftover *.citadeltmp from an earlier promote that was hard-killed
    #    between copyfile and os.replace. They are excluded from sync AND prune (reserved), so
    #    without this they could linger on the live wiki indefinitely.
    #    Only the CONTENT temps this step can actually have created are swept: a HIDDEN temp
    #    (`.citadel_ingested.json.<pid>.citadeltmp`) belongs to an in-flight atomic_write_text of the
    #    manifest/failures catalog — under `--jobs N` the main thread is saving one of those while a
    #    worker promotes, and deleting it out from under the writer turned a routine manifest save
    #    into a FileNotFoundError. Those temps are the writer's own to clean up.
    with contextlib.suppress(OSError):
        for dirpath, dirnames, filenames in os.walk(live):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for name in filenames:
                if name.startswith(".") or not name.endswith(".citadeltmp"):
                    continue
                with contextlib.suppress(OSError):
                    (Path(dirpath) / name).unlink()

    # 4. Drop directories left empty by the prune (bottom-up), but keep the live root itself.
    #    Hidden trees are exempt, exactly like the sync/prune above (_content_files skips them):
    #    a wiki-history `.git` legitimately holds empty dirs (a fresh repo's objects/ and refs/ —
    #    removing them corrupts the repository), and the same goes for e.g. an `.obsidian/`.
    for dirpath, _dirs, _files in os.walk(live, topdown=False):
        d = Path(dirpath)
        if d == live:
            continue
        if any(part.startswith(".") for part in d.relative_to(live).parts):
            continue
        with contextlib.suppress(OSError):
            if not any(d.iterdir()):
                d.rmdir()
