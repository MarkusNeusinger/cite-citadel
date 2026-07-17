"""Target-behavior suite for PR4 — incremental discovery + multi-root.

Covers the manifest-as-scan-cache (stat quick check, zero content reads on an unchanged corpus),
the racy-timestamp guard (source clock, 3 s window, mtime as an OPAQUE EQUALITY token), the
failures-catalog quick check for duplicate/unreadable sources, the candidates-then-confirm
deletion sweep with its operational-safety guards (walk-error abort, unreachable roots,
out-of-root keys, workspace-identity hard guard), ``CITADEL_RAW_DIRS`` multi-root discovery,
``--full-rescan``, and the space-containing-source-path citation form.

DECIDED (the PR3.5 follow-up): the supported markdown form for a source path containing spaces is
the angle-bracket target ``[text](<../../raw/my report.pdf>)`` — standard markdown, already parsed
by ``grammar.split_link_target``. The bare form splits at the first whitespace (a ``"title"``
suffix would be indistinguishable) and stays unsupported; the rewriters must EMIT the angle form
whenever a repointed target contains whitespace, so a rewrite round-trips.

All of the incremental-discovery rework is implemented; every test here is a live behavior pin. All offline:
``llm.run_ingest_session`` is always the ``fake_agent`` stand-in.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from conftest import _cite_page, delete_citing_pages, errors_of

from citadel import config, failures, grammar, ingest, linkgraph, lint, manifest, okf, store, validate


# --- shared helpers ------------------------------------------------------------------------


def _write_page_citing(rel_key: str) -> None:
    """Write one valid page citing ``rel_key`` into the CONFIGURED wiki (ingest's staging copy at
    session time) — conftest's ``cite_page``, slug-pathed per key so a whole corpus of sources
    yields distinct pages (the relative-vs-absolute citation branch lives in the shared helper)."""
    _cite_page(f"concepts/{okf.slugify(rel_key)}.md", rel_key, "A fact.")


def _fake_session(rel_key: str, kind: str = "ingest", **_kw) -> None:
    """Deterministic agent stand-in for a whole corpus: an ingest/reconcile session writes one
    valid page citing ``rel_key``; a delete session removes every page citing it. Reads/writes the
    staging wiki through ``config`` at call time, exactly like the real agent's file edits."""
    if kind == "delete":
        delete_citing_pages(rel_key)
        return
    _write_page_citing(rel_key)


@dataclass
class HashCounter:
    """Counts every raw-source content read routed through ``manifest.file_sha256`` — the single
    content-hash seam for sources (the quick-check-miss rehash, move detection, and ``mark_done``
    all go through it). The 'zero reads on an unchanged corpus' contract is asserted on this
    counter."""

    calls: list[Path] = field(default_factory=list)

    def of(self, path: Path | str) -> int:
        target = Path(path)
        return sum(1 for p in self.calls if p == target)

    @property
    def total(self) -> int:
        return len(self.calls)

    def reset(self) -> None:
        self.calls.clear()


@pytest.fixture
def count_hashes(monkeypatch) -> HashCounter:
    """Install a counting wrapper over ``manifest.file_sha256`` (the module attribute every
    caller — ingest included — resolves at call time) and return the counter."""
    counter = HashCounter()
    real = manifest.file_sha256

    def counting(path):
        counter.calls.append(Path(path))
        return real(path)

    monkeypatch.setattr(manifest, "file_sha256", counting)
    return counter


class _FilteredScandir:
    """An ``os.scandir`` result that hides entries named ``hide`` — simulates a walk that RACED a
    file (listed a directory the instant the file was invisible) while the file exists on disk.
    Supports the context-manager + iterator protocol ``os.walk`` (and any scandir walk) uses."""

    def __init__(self, inner, hide: str):
        self._inner = inner
        self._hide = hide

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self._inner.close()
        return False

    def __iter__(self):
        return self

    def __next__(self):
        while True:
            entry = next(self._inner)
            if entry.name != self._hide:
                return entry

    def close(self):
        self._inner.close()


def _patch_scandir(monkeypatch, *, hide_in: Path | None = None, hide_name: str = "", fail_dir: Path | None = None):
    """Monkeypatch ``os.scandir`` so listing ``hide_in`` omits ``hide_name`` and listing
    ``fail_dir`` raises ``OSError`` (a flaky SMB subdirectory). All other directories list
    normally, so the wiki/staging machinery is untouched."""
    real = os.scandir

    def _same(path, target: Path) -> bool:
        try:
            return Path(os.fspath(path)).resolve() == target.resolve()
        except (OSError, TypeError):
            return False

    def fake(path=".", *args, **kwargs):
        if fail_dir is not None and _same(path, fail_dir):
            raise OSError(5, "simulated I/O error on a flaky share")
        it = real(path, *args, **kwargs)
        if hide_in is not None and _same(path, hide_in):
            return _FilteredScandir(it, hide_name)
        return it

    monkeypatch.setattr(os, "scandir", fake)


def _seed_tracked(path: Path, model: str | None = "claude:sonnet") -> None:
    """Record ``path`` in the on-disk manifest exactly as a pre-PR4 run would have (sha only,
    no stat fields)."""
    m = manifest.load()
    m[manifest.rel_key(path)] = manifest.make_entry(manifest.file_sha256(path), model)
    manifest.save(m)


# --- 1. the manifest is the scan cache -----------------------------------------------------


def test_unchanged_corpus_second_run_reads_no_content(tmp_citadel, fake_agent, count_hashes):
    """An unchanged corpus whose sources are all ingested (stat fields present from run 1) is
    fully skipped on the next run with ZERO content reads: the exact (size, mtime_ns) match IS the
    skip decision; no file is opened, let alone hashed."""
    raw = tmp_citadel.raw
    (raw / "a.md").write_text("alpha\n", encoding="utf-8")
    (raw / "sub").mkdir()
    (raw / "sub" / "b.txt").write_text("beta\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)

    first = ingest.ingest()
    assert set(first.processed) == {"raw/a.md", "raw/sub/b.txt"}

    count_hashes.reset()
    agent.reset()
    second = ingest.ingest()
    assert set(second.skipped) == {"raw/a.md", "raw/sub/b.txt"}
    assert agent.count == 0
    assert count_hashes.total == 0  # not one single content read on the unchanged corpus


def test_touched_but_identical_file_rehashes_once_and_refreshes_cache(tmp_citadel, fake_agent, count_hashes):
    """A file whose mtime changed but whose bytes did not (touched/re-saved identically) is
    rehashed exactly once, NOT re-ingested (sha is the sole arbiter of 'changed'), and the manifest
    entry's stat cache is refreshed and SAVED so the next run quick-skips it again. The new mtime
    is set in the PAST: mtime_ns is an opaque equality token, never ordered, so an older-but-
    different token must equally invalidate the quick check."""
    src = tmp_citadel.raw / "a.md"
    src.write_text("alpha\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    past_ns = src.stat().st_mtime_ns - 50 * 10**9
    os.utime(src, ns=(past_ns, past_ns))
    count_hashes.reset()
    agent.reset()
    report = ingest.ingest()
    assert "raw/a.md" in report.skipped
    assert agent.count == 0  # sha matched: recognized as unchanged, no session
    assert count_hashes.of(src) == 1  # quick-check miss -> exactly one rehash
    assert tmp_citadel.read_manifest()["raw/a.md"]["mtime_ns"] == past_ns  # cache refreshed on disk


def test_changed_file_is_reconciled_after_exactly_one_content_hash(tmp_citadel, fake_agent, count_hashes):
    """A file with new bytes lands in pending and takes kind=reconcile (pinned elsewhere too) —
    and the whole run reads its content exactly ONCE: the quick-check-miss hash serves move
    detection AND is passed through to ``mark_done`` instead of being recomputed there."""
    src = tmp_citadel.raw / "a.md"
    src.write_text("alpha\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    src.write_text("alpha, revised\n", encoding="utf-8")
    count_hashes.reset()
    agent.reset()
    report = ingest.ingest()
    assert agent.calls == [("raw/a.md", "reconcile")]
    assert report.processed == ["raw/a.md"]
    assert count_hashes.of(src) == 1


def test_entry_without_stat_fields_is_rehashed_once_and_backfilled(tmp_citadel, fake_agent, count_hashes):
    """A pre-PR4 manifest entry (sha only, no stat fields) is rehashed exactly once on first
    contact and the entry is backfilled with (size, mtime_ns) and saved — so the very next run
    joins the zero-read quick check without needing --full-rescan."""
    src = tmp_citadel.raw / "old.md"
    src.write_text("pre-PR4 tracked content\n", encoding="utf-8")
    _seed_tracked(src)
    agent = fake_agent(side_effect=_fake_session)

    count_hashes.reset()
    report = ingest.ingest()
    assert "raw/old.md" in report.skipped
    assert agent.count == 0
    assert count_hashes.of(src) == 1

    st = src.stat()
    entry = tmp_citadel.read_manifest()["raw/old.md"]
    assert entry["size"] == st.st_size
    assert entry["mtime_ns"] == st.st_mtime_ns


# --- 2. the racy-timestamp guard ------------------------------------------------------------


def test_racy_timestamp_entries_are_rehashed_despite_matching_stat(tmp_citadel, fake_agent, count_hashes):
    """The git model: an entry whose recorded mtime_ns is at/after its hashed_at_ns (the SOURCE
    file's clock at hash time) minus the 3 s SMB/FAT window is distrusted and rehashed even though
    (size, mtime_ns) match exactly; an entry hashed comfortably after its last modification is
    trusted and never opened."""
    raw = tmp_citadel.raw
    entries: dict[str, dict] = {}
    offsets = {"safe.md": 60 * 10**9, "racy.md": 0, "boundary.md": manifest.RACY_WINDOW_NS}
    for name, offset in offsets.items():
        src = raw / name
        src.write_text(f"content of {name}\n", encoding="utf-8")
        st = src.stat()
        entries[manifest.rel_key(src)] = {
            "sha256": manifest.file_sha256(src),
            "model": "claude:sonnet",
            "size": st.st_size,
            "mtime_ns": st.st_mtime_ns,
            "hashed_at_ns": st.st_mtime_ns + offset,
        }
    manifest.save(entries)
    agent = fake_agent(side_effect=_fake_session)

    count_hashes.reset()
    report = ingest.ingest()
    assert set(report.skipped) == set(entries)  # shas all match: nothing re-ingested
    assert agent.count == 0
    assert count_hashes.of(raw / "safe.md") == 0  # hashed 60s after mtime: trusted
    assert count_hashes.of(raw / "racy.md") == 1  # hashed the instant it was written: distrusted
    assert count_hashes.of(raw / "boundary.md") == 1  # exactly at the 3s window edge: distrusted


def test_same_stat_edit_within_racy_window_is_still_detected(tmp_citadel, fake_agent):
    """The end-to-end property the racy-window guard exists for: a
    source rewritten with the SAME byte length and the SAME mtime_ns (mtime granularity / clock
    skew / a backdating ``utime`` can produce exactly this) is still detected as changed when the
    entry is inside the racy window — its recorded mtime is not comfortably before its recorded
    ``hashed_at_ns``, so the quick check distrusts it and the rehash catches the new bytes.

    Pinned on a PURE-WINDOW entry (ctime token stripped, ``hashed_at_ns`` set to the recorded
    mtime — the hand-seeded/other-tool entry class) because that is the guarantee that holds on
    EVERY platform. This is the accepted limitation, same as git: OUTSIDE the window the quick
    check needs the ctime token, and on Windows ``st_ctime`` is the stable creation time, so a
    deliberately backdated same-size in-place rewrite there is invisible to stat until
    ``--full-rescan`` or a real mtime change (an accepted deviation, and
    ``manifest.entry_trusts_stat``). The ctime-mismatch catch is pinned separately below."""
    src = tmp_citadel.raw / "a.md"
    src.write_text("alpha version one\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    # Rewrite the manifest entry as a pure-window one: no ctime token to vouch, hashed_at equal
    # to the recorded mtime — i.e. hashed the instant it was last written, the racy case, made
    # deterministic and platform-independent instead of relying on real stat-clock timing.
    m = manifest.load()
    entry = dict(m["raw/a.md"])
    entry.pop("ctime_ns", None)
    entry["hashed_at_ns"] = entry["mtime_ns"]
    m["raw/a.md"] = entry
    manifest.save(m)

    st = src.stat()
    src.write_text("alpha version two\n", encoding="utf-8")  # same length, new bytes
    os.utime(src, ns=(st.st_mtime_ns, st.st_mtime_ns))  # same mtime token
    assert src.stat().st_size == st.st_size

    agent.reset()
    report = ingest.ingest()
    assert agent.calls == [("raw/a.md", "reconcile")]
    assert report.processed == ["raw/a.md"]


def test_ctime_token_mismatch_forces_rehash_even_when_window_looks_safe(tmp_citadel, fake_agent):
    """The ctime token is AUTHORITATIVE end-to-end: an entry whose recorded ``ctime_ns`` does not
    match the file's current one is distrusted and rehashed EVEN when its ``hashed_at_ns`` is
    forged to look comfortably safe — the case a backdated mtime could otherwise talk the pure
    window into trusting. On POSIX this is exactly the same-size same-mtime rewrite (the kernel
    bumps ctime on every change and userspace cannot set it back); on Windows it is a REPLACED
    file (a new file gets a new creation time). The mismatch is planted on the recorded token
    (one tick before the real ctime) rather than produced by a live rewrite, because on a fast
    filesystem write->ingest->rewrite can land inside ONE coarse-clock tick and leave the real
    ctime unchanged — the planted form pins the identical code path deterministically on every
    platform."""
    src = tmp_citadel.raw / "a.md"
    src.write_text("alpha version one\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    m = manifest.load()
    entry = dict(m["raw/a.md"])
    assert isinstance(entry.get("ctime_ns"), int)  # the token really is recorded end-to-end
    entry["ctime_ns"] -= 1  # the file's ctime moved since the hash (rewrite / replacement)
    entry["hashed_at_ns"] = entry["mtime_ns"] + 60 * 10**9  # window alone would say "safe"
    m["raw/a.md"] = entry
    manifest.save(m)

    st = src.stat()
    src.write_text("alpha version two\n", encoding="utf-8")  # same length, new bytes
    os.utime(src, ns=(st.st_mtime_ns, st.st_mtime_ns))  # same mtime token
    assert src.stat().st_size == st.st_size

    agent.reset()
    report = ingest.ingest()
    assert agent.calls == [("raw/a.md", "reconcile")]
    assert report.processed == ["raw/a.md"]


def test_recorded_ctime_token_is_authoritative_in_the_quick_check(tmp_citadel):
    """Unit pin on :func:`manifest.entry_trusts_stat`, platform-independent by construction (the
    entry dict is manipulated, never the file): with (size, mtime_ns) matching, a recorded
    ``ctime_ns`` decides ALONE — equal -> trusted, different -> distrusted even when
    ``hashed_at_ns`` sits comfortably past the window (a mismatching ctime proves change; falling
    through to the window would let a forged mtime win). Only an entry with NO ctime token falls
    back to the pure racy-window rule."""
    src = tmp_citadel.raw / "a.md"
    src.write_text("alpha\n", encoding="utf-8")
    st = src.stat()
    safe_hashed_at = st.st_mtime_ns + 60 * 10**9
    base = {"sha256": "aa" * 32, "size": st.st_size, "mtime_ns": st.st_mtime_ns}

    assert manifest.entry_trusts_stat({**base, "ctime_ns": st.st_ctime_ns}, st)
    assert not manifest.entry_trusts_stat({**base, "ctime_ns": st.st_ctime_ns + 1, "hashed_at_ns": safe_hashed_at}, st)
    assert manifest.entry_trusts_stat({**base, "hashed_at_ns": safe_hashed_at}, st)
    assert not manifest.entry_trusts_stat({**base, "hashed_at_ns": st.st_mtime_ns}, st)


# --- 3. duplicate/unreadable sources join the quick check via the failures catalog -----------


def _dedup_corpus(cit, make_pptx) -> tuple[Path, Path, Path]:
    """A kept .pdf + its same-basename .pptx twin (dedup-dropped) + an unreadable binary."""
    pdf = cit.raw / "report.pdf"
    pdf.write_bytes(b"%PDF-1.7\nfake quarterly deck export\n")
    pptx = cit.raw / "report.pptx"
    make_pptx(pptx, [["Quarterly numbers improved."]])
    blob = cit.raw / "blob.bin"
    blob.write_bytes(b"text\x00more\x00binary")
    return pdf, pptx, blob


def test_duplicate_and_unreadable_record_stat_and_sha_in_failures_catalog(
    tmp_citadel, fake_agent, make_pptx, monkeypatch
):
    """A dedup-dropped same-basename twin and an unreadable binary get sha256 + (size, mtime_ns)
    recorded on their failures-catalog entries, so they can join the stat quick check — otherwise
    every dropped .pptx twin would be re-hashed forever."""
    monkeypatch.setattr(config, "DEDUP_BY_BASENAME", True, raising=False)
    pdf, pptx, blob = _dedup_corpus(tmp_citadel, make_pptx)
    fake_agent(side_effect=_fake_session)

    report = ingest.ingest()
    assert report.duplicates == [("raw/report.pptx", "raw/report.pdf")]
    assert report.unreadable == ["raw/blob.bin"]
    assert "raw/report.pdf" in report.processed

    catalog = failures.load()
    for key, path in (("raw/report.pptx", pptx), ("raw/blob.bin", blob)):
        entry, st = catalog[key], path.stat()
        assert entry["sha256"] == manifest.file_sha256(path)
        assert entry["size"] == st.st_size
        assert entry["mtime_ns"] == st.st_mtime_ns


def test_unchanged_duplicate_and_unreadable_are_not_rehashed_on_later_runs(
    tmp_citadel, fake_agent, make_pptx, monkeypatch, count_hashes
):
    """On the run AFTER a duplicate/unreadable source was cataloged, an unchanged twin/binary is
    quick-checked against its failures-catalog stat+sha — zero content reads, no agent session —
    and stays cataloged (a later run must still re-evaluate it if the kept file disappears)."""
    monkeypatch.setattr(config, "DEDUP_BY_BASENAME", True, raising=False)
    pdf, pptx, blob = _dedup_corpus(tmp_citadel, make_pptx)
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    count_hashes.reset()
    agent.reset()
    ingest.ingest()
    assert agent.count == 0
    assert count_hashes.of(pptx) == 0
    assert count_hashes.of(blob) == 0
    assert count_hashes.of(pdf) == 0
    catalog = failures.load()
    assert "raw/report.pptx" in catalog and "raw/blob.bin" in catalog


# --- 4. deletion safety: candidates, then positive confirmation ------------------------------


def test_deleted_file_is_confirmed_gone_then_swept_on_full_run(tmp_citadel, fake_agent):
    """The happy path stays: a tracked, cited source that really vanished from disk is a deletion
    candidate, is positively confirmed gone, gets its kind=delete cleanup session, and is dropped
    from the manifest — on a FULL run."""
    raw = tmp_citadel.raw
    (raw / "keep.md").write_text("keep\n", encoding="utf-8")
    gone = raw / "gone.md"
    gone.write_text("gone\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    gone.unlink()
    agent.reset()
    report = ingest.ingest()
    assert report.sources_deleted == ["raw/gone.md"]
    assert ("raw/gone.md", "delete") in agent.calls
    data = tmp_citadel.read_manifest()
    assert "raw/gone.md" not in data
    assert "raw/keep.md" in data


def test_path_scoped_run_never_sweeps_deletions(tmp_citadel, fake_agent):
    """A path-scoped run (explicit paths) runs NO deletion sweep at all — it cannot surprise-prune
    sources it was not pointed at (existing behavior, kept pinned through the discovery rework)."""
    raw = tmp_citadel.raw
    gone = raw / "gone.md"
    gone.write_text("gone\n", encoding="utf-8")
    _seed_tracked(gone)
    gone.unlink()
    (raw / "new.md").write_text("new source\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)

    report = ingest.ingest([str(raw / "new.md")])
    assert report.processed == ["raw/new.md"]
    assert report.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    assert "raw/gone.md" in tmp_citadel.read_manifest()


def test_candidate_that_exists_at_confirm_time_is_not_swept(tmp_citadel, fake_agent, monkeypatch):
    """A file the walk MISSED (raced/flaky listing) while it exists on disk is never swept: the
    seen-set diff only nominates candidates; each one must be positively confirmed gone with
    .exists() before any delete session."""
    raw = tmp_citadel.raw
    present = raw / "present.md"
    present.write_text("still here\n", encoding="utf-8")
    _seed_tracked(present)
    agent = fake_agent(side_effect=_fake_session)

    _patch_scandir(monkeypatch, hide_in=raw, hide_name="present.md")
    report = ingest.ingest()
    assert "raw/present.md" not in report.skipped  # self-check: the walk really did not see it
    assert report.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    assert "raw/present.md" in tmp_citadel.read_manifest()


def test_walk_error_in_one_subdir_aborts_entire_deletion_sweep(tmp_citadel, fake_agent, monkeypatch, capsys):
    """A scandir error ANYWHERE in the walk (one flaky SMB subdirectory) aborts the deletion sweep
    for the whole run — even a candidate that is genuinely gone elsewhere is not swept — while
    pending sources are still processed, and a loud note says deletion detection was skipped."""
    raw = tmp_citadel.raw
    flaky = raw / "flaky-sub"
    flaky.mkdir()
    inside = flaky / "inside.md"
    inside.write_text("inside the flaky dir\n", encoding="utf-8")
    _seed_tracked(inside)
    gone = raw / "gone.md"
    gone.write_text("gone\n", encoding="utf-8")
    _seed_tracked(gone)
    gone.unlink()  # genuinely deleted -- but the sweep must still refuse to act this run
    (raw / "new.md").write_text("new source\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)

    _patch_scandir(monkeypatch, fail_dir=flaky)
    report = ingest.ingest()
    assert "raw/new.md" in report.processed  # ingest itself is not blocked
    assert report.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    data = tmp_citadel.read_manifest()
    assert "raw/gone.md" in data  # retried next run instead of swept on a flaky walk
    assert "raw/flaky-sub/inside.md" in data
    assert "deletion" in capsys.readouterr().err.lower()


def test_unreachable_raw_root_never_reads_as_mass_deletion(tmp_citadel, fake_agent, capsys):
    """An unmounted/vanished raw root (the whole directory unreachable) produces ZERO deletions
    for its keys plus a skip note — 5000 sources on a share that did not mount must never read as
    '5000 sources deleted'."""
    raw = tmp_citadel.raw
    for name in ("a.md", "b.md"):
        src = raw / name
        src.write_text(f"{name} content\n", encoding="utf-8")
        _seed_tracked(src)
    agent = fake_agent(side_effect=_fake_session)

    shutil.rmtree(raw)
    report = ingest.ingest()
    assert report.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    data = tmp_citadel.read_manifest()
    assert "raw/a.md" in data and "raw/b.md" in data
    assert "deletion" in capsys.readouterr().err.lower()


def test_manifest_key_under_no_configured_root_is_never_swept(make_citadel, fake_agent, tmp_path, capsys):
    """A source ingested via an explicit path from OUTSIDE every configured root (an absolute,
    out-of-workspace key) is never nominated for deletion by a full run — even after the file
    vanishes — because no walked root covers it; it is logged instead."""
    cit = make_citadel(root=tmp_path / "repo")
    outside = tmp_path / "elsewhere" / "notes.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("out-of-root source\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest([str(outside)])
    key = outside.resolve().as_posix()
    assert key in cit.read_manifest()

    outside.unlink()
    agent.reset()
    report = ingest.ingest()  # full run
    assert report.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    assert key in cit.read_manifest()
    assert key in capsys.readouterr().err


def test_out_of_root_source_still_on_disk_survives_full_run(make_citadel, fake_agent, tmp_path):
    """The pinning case: path-scoped ingest of an out-of-root (out-of-workspace) file, then a
    FULL run — the absolute key stays tracked and nothing tries to delete it while the file is on
    disk."""
    cit = make_citadel(root=tmp_path / "repo")
    outside = tmp_path / "elsewhere" / "notes.txt"
    outside.parent.mkdir(parents=True)
    outside.write_text("out-of-root source\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest([str(outside)])
    key = outside.resolve().as_posix()
    assert key in cit.read_manifest()

    agent.reset()
    report = ingest.ingest()  # full run
    assert report.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    assert key in cit.read_manifest()


# --- 5. multi-root discovery (CITADEL_RAW_DIRS) ----------------------------------------------


def test_raw_dirs_env_resolution(tmp_citadel, tmp_path, monkeypatch):
    """CITADEL_RAW_DIRS is a comma/newline-separated list (the shared config._split_list_env):
    a relative entry resolves against WORKSPACE_ROOT, an absolute entry is taken as-is; unset
    falls back to the single RAW_DIR."""
    other = tmp_path / "share" / "raw2"
    monkeypatch.setenv("CITADEL_RAW_DIRS", f"raw, {other}")
    assert config._resolve_raw_dirs() == [Path(config.WORKSPACE_ROOT) / "raw", other]

    monkeypatch.delenv("CITADEL_RAW_DIRS", raising=False)
    assert config._resolve_raw_dirs() == [Path(config.RAW_DIR)]


def test_multi_root_discovery_walks_both_roots_with_rel_and_abs_keys(make_citadel, fake_agent, tmp_path, monkeypatch):
    """With two roots — the workspace-sibling raw/ and an elsewhere-absolute directory — discovery
    walks both; keys keep the rel-or-abs discipline: workspace-relative for the sibling root,
    absolute posix for the out-of-workspace root."""
    cit = make_citadel(root=tmp_path / "repo")
    root_b = tmp_path / "share" / "more-raw"
    root_b.mkdir(parents=True)
    (cit.raw / "a.md").write_text("alpha\n", encoding="utf-8")
    (root_b / "b.md").write_text("beta\n", encoding="utf-8")
    monkeypatch.setattr(config, "RAW_DIRS", [cit.raw, root_b], raising=False)
    fake_agent(side_effect=_fake_session)

    report = ingest.ingest()
    key_b = (root_b / "b.md").resolve().as_posix()
    assert set(report.processed) == {"raw/a.md", key_b}
    data = cit.read_manifest()
    assert "raw/a.md" in data and key_b in data


def test_adding_and_removing_a_root_never_rekeys_or_deletes_other_roots(
    make_citadel, fake_agent, tmp_path, monkeypatch
):
    """Adding root B neither re-keys nor re-ingests nor deletes root A's sources; removing root B
    again leaves B's keys tracked (they are under no configured root — logged, never swept)."""
    cit = make_citadel(root=tmp_path / "repo")
    root_b = tmp_path / "share" / "more-raw"
    root_b.mkdir(parents=True)
    (cit.raw / "a.md").write_text("alpha\n", encoding="utf-8")
    (root_b / "b.md").write_text("beta\n", encoding="utf-8")
    key_b = (root_b / "b.md").resolve().as_posix()
    agent = fake_agent(side_effect=_fake_session)

    monkeypatch.setattr(config, "RAW_DIRS", [cit.raw], raising=False)
    ingest.ingest()
    entry_a = cit.read_manifest()["raw/a.md"]

    monkeypatch.setattr(config, "RAW_DIRS", [cit.raw, root_b], raising=False)
    agent.reset()
    second = ingest.ingest()
    assert second.processed == [key_b]  # only root B's source is new
    assert "raw/a.md" in second.skipped
    assert second.sources_deleted == []
    assert cit.read_manifest()["raw/a.md"] == entry_a  # byte-identical entry: never re-keyed

    monkeypatch.setattr(config, "RAW_DIRS", [cit.raw], raising=False)
    agent.reset()
    third = ingest.ingest()
    assert third.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    data = cit.read_manifest()
    assert "raw/a.md" in data and key_b in data


def test_same_content_in_two_roots_stays_two_distinct_sources(make_citadel, fake_agent, tmp_path, monkeypatch):
    """A byte-identical file present in BOTH roots keeps two distinct manifest keys — no cross-root
    collapse onto one key. Consistent with the single-root duplicate semantics (pinned here for the
    cross-root case): the second copy is RECOGNIZED as a byte-for-byte duplicate and not re-ingested
    (one agent session, ``report.moved`` records the recognition, both keys tracked). Same-basename
    document dedup is untouched: it only collapses same-FOLDER document-format groups."""
    cit = make_citadel(root=tmp_path / "repo")
    root_b = tmp_path / "share" / "more-raw"
    root_b.mkdir(parents=True)
    (cit.raw / "x.md").write_text("the same bytes\n", encoding="utf-8")
    (root_b / "x.md").write_text("the same bytes\n", encoding="utf-8")
    key_b = (root_b / "x.md").resolve().as_posix()
    monkeypatch.setattr(config, "RAW_DIRS", [cit.raw, root_b], raising=False)
    agent = fake_agent(side_effect=_fake_session)

    report = ingest.ingest()
    assert agent.count == 1  # the content is folded in exactly once
    assert report.moved == [("raw/x.md", key_b)]
    data = cit.read_manifest()
    assert "raw/x.md" in data and key_b in data  # two distinct sources, no re-keying
    assert manifest.entry_sha(data["raw/x.md"]) == manifest.entry_sha(data[key_b])


def test_deletion_sweep_scoped_per_root_with_unreachable_second_root(
    make_citadel, fake_agent, tmp_path, monkeypatch, capsys
):
    """With root A walked cleanly and root B unmounted, A's genuinely-deleted source is swept while
    every key under the unreachable B survives untouched (plus a skip note) — per-root scoping is
    what keeps one dead mount from poisoning the whole sweep."""
    cit = make_citadel(root=tmp_path / "repo")
    root_b = tmp_path / "share" / "more-raw"
    root_b.mkdir(parents=True)
    (cit.raw / "keep.md").write_text("keep\n", encoding="utf-8")
    gone = cit.raw / "gone.md"
    gone.write_text("gone\n", encoding="utf-8")
    (root_b / "b.md").write_text("beta\n", encoding="utf-8")
    key_b = (root_b / "b.md").resolve().as_posix()
    monkeypatch.setattr(config, "RAW_DIRS", [cit.raw, root_b], raising=False)
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    gone.unlink()
    shutil.rmtree(root_b)  # the share did not mount this morning
    agent.reset()
    report = ingest.ingest()
    assert report.sources_deleted == ["raw/gone.md"]  # root A's sweep still works
    data = cit.read_manifest()
    assert key_b in data  # unreachable root: zero deletions for its keys
    assert "raw/keep.md" in data
    assert "deletion" in capsys.readouterr().err.lower()


def test_page_citing_second_root_by_absolute_path_passes_check_lint_and_rebuild(make_citadel, seed_page, tmp_path):
    """The cross-root citation form: a page citing a non-sibling root's source by ABSOLUTE posix
    path passes the strict gate and lint, is untouched by an unrelated raw-reference rewrite, and
    survives an index rebuild (grammar pre-paved: resolves_to_source accepts absolutes)."""
    cit = make_citadel(root=tmp_path / "repo")
    root_b = tmp_path / "share" / "more-raw"
    root_b.mkdir(parents=True)
    src = root_b / "notes.md"
    src.write_text("a cross-root fact\n", encoding="utf-8")
    key = src.resolve().as_posix()
    seed_page(
        "concepts/crossroot.md",
        {"type": "Concept", "title": "Crossroot", "description": "d", "tags": ["t"], "resource": key},
        f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [notes]({key}) - n (ingested 2026-06-21)\n",
    )
    manifest.save({key: manifest.make_entry("cafe" * 16, "claude:sonnet")})

    page = store.load()[0]
    assert errors_of(validate.validate_page(page.rel_path, page.frontmatter, page.body)) == []
    assert lint.lint().ok()
    assert store.find_broken_links() == []
    assert store.find_raw_references(key) == ["concepts/crossroot.md"]
    assert store.rewrite_raw_references("raw/unrelated.md", "raw/moved.md") == []  # byte-stable

    store.rebuild_indexes()
    assert key in (cit.wiki / "sources" / "index.md").read_text(encoding="utf-8")
    assert store.find_broken_links() == []


# --- 6. the workspace-identity HARD guard (deferred to the sweep rework) ---------


def _write_stamped_manifest(cit, sources: dict, stamp: str) -> None:
    """Write a format-2 manifest stamped as if a workspace rooted at ``stamp`` had produced it."""
    cit.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"meta": {"format": manifest.MANIFEST_FORMAT, "workspace": stamp}, "sources": sources}
    cit.manifest_path.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def test_workspace_mismatch_with_unresolvable_keys_refuses_deletion_sweep(tmp_citadel, fake_agent, monkeypatch):
    """A manifest stamped by workspace X, running under workspace Y, with under half of its
    relative keys resolving on disk (a nested marker / moved checkout re-keyed the world) REFUSES
    the deletion sweep with an actionable error suggesting --full-rescan — ingest of pending
    sources still proceeds, but nothing is swept off a shifted key space."""
    monkeypatch.setattr(manifest, "_warned_workspaces", set())
    raw = tmp_citadel.raw
    here = raw / "here.md"
    here.write_text("resolvable\n", encoding="utf-8")
    sources = {
        "raw/here.md": manifest.make_entry(manifest.file_sha256(here), "claude:sonnet"),
        "raw/gone-one.md": manifest.make_entry("aa" * 32, "claude:sonnet"),
        "raw/gone-two.md": manifest.make_entry("bb" * 32, "claude:sonnet"),
    }
    _write_stamped_manifest(tmp_citadel, sources, "/mnt/other-mount/team-wiki")
    (raw / "new.md").write_text("new source\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)

    report = ingest.ingest()
    assert "raw/new.md" in report.processed  # pending sources may proceed
    assert report.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    data = tmp_citadel.read_manifest()
    assert "raw/gone-one.md" in data and "raw/gone-two.md" in data
    assert any("workspace" in e.lower() and "--full-rescan" in e for e in report.errors)


def test_workspace_mismatch_with_resolvable_keys_warns_and_proceeds(tmp_citadel, fake_agent, monkeypatch, capsys):
    """The dual-mount case stays a WARNING: the stamp mismatches but the keys resolve (same share
    mounted at a different path), so the run — including a legitimate deletion sweep — proceeds
    (current behavior, kept pinned)."""
    monkeypatch.setattr(manifest, "_warned_workspaces", set())
    raw = tmp_citadel.raw
    sources: dict = {}
    for name in ("a.md", "b.md"):
        src = raw / name
        src.write_text(f"{name} content\n", encoding="utf-8")
        sources[f"raw/{name}"] = manifest.make_entry(manifest.file_sha256(src), "claude:sonnet")
    sources["raw/gone.md"] = manifest.make_entry("cc" * 32, "claude:sonnet")  # 2 of 3 resolve
    stamp = "/mnt/dual-mount/team-wiki-b"
    _write_stamped_manifest(tmp_citadel, sources, stamp)
    fake_agent(side_effect=_fake_session)

    report = ingest.ingest()
    err = capsys.readouterr().err
    assert "WARNING" in err and stamp in err
    assert report.errors == []
    assert report.sources_deleted == ["raw/gone.md"]  # the sweep itself is NOT refused
    data = tmp_citadel.read_manifest()
    assert "raw/a.md" in data and "raw/b.md" in data


# --- 7. --full-rescan -------------------------------------------------------------------------


def test_full_rescan_rehashes_everything_without_reingesting(tmp_citadel, fake_agent, count_hashes):
    """``ingest(full_rescan=True)`` distrusts the quick check and rehashes every tracked file —
    but sha stays the sole arbiter, so unchanged sources are still skipped, not re-ingested."""
    raw = tmp_citadel.raw
    (raw / "a.md").write_text("alpha\n", encoding="utf-8")
    (raw / "sub").mkdir()
    (raw / "sub" / "b.txt").write_text("beta\n", encoding="utf-8")
    agent = fake_agent(side_effect=_fake_session)
    ingest.ingest()

    count_hashes.reset()
    agent.reset()
    report = ingest.ingest(full_rescan=True)
    assert set(report.skipped) == {"raw/a.md", "raw/sub/b.txt"}
    assert agent.count == 0
    assert count_hashes.of(raw / "a.md") == 1
    assert count_hashes.of(raw / "sub" / "b.txt") == 1


def test_full_rescan_after_workspace_guard_restamps_manifest(tmp_citadel, fake_agent, monkeypatch):
    """The guard's advertised remedy must not loop: with the workspace guard fired and NOTHING
    else persisting a save, ``--full-rescan`` still refuses the sweep (safety frozen) but saves
    the manifest at end-of-run — re-stamping meta with the CURRENT root — so the NEXT run reads a
    matching stamp and the deletion sweep re-arms."""
    monkeypatch.setattr(manifest, "_warned_workspaces", set())
    sources = {
        "raw/gone-one.md": manifest.make_entry("aa" * 32, "claude:sonnet"),
        "raw/gone-two.md": manifest.make_entry("bb" * 32, "claude:sonnet"),
        "raw/gone-three.md": manifest.make_entry("dd" * 32, "claude:sonnet"),
    }
    _write_stamped_manifest(tmp_citadel, sources, "/mnt/other-mount/team-wiki")
    agent = fake_agent(side_effect=_fake_session)

    first = ingest.ingest(full_rescan=True)
    assert any("workspace" in e.lower() for e in first.errors)  # the sweep stays refused THIS run
    assert first.sources_deleted == []
    assert not any(kind == "delete" for _key, kind in agent.calls)
    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))
    assert data["meta"]["workspace"] == Path(config.WORKSPACE_ROOT).resolve().as_posix()  # re-stamped

    agent.reset()
    second = ingest.ingest()  # next run: matching stamp, no guard — the sweep is re-armed
    assert not any("workspace" in e.lower() for e in second.errors)
    assert set(second.sources_deleted) == set(sources)


# --- 8. source paths containing spaces (the PR3.5 follow-up) ----------------------------------


def test_split_link_target_angle_form_is_the_supported_space_path_form():
    """DECIDED form: a space-containing target is written ``(<...>)`` (standard markdown), which
    ``split_link_target`` already parses whole; the bare form lexically splits at the first
    whitespace (it is a ``"title"`` boundary) and stays unsupported — pinned here as the
    documented contract."""
    assert grammar.split_link_target("<../../raw/my report.pdf>") == ("../../raw/my report.pdf", "")
    assert grammar.split_link_target("../../raw/my report.pdf") == ("../../raw/my", " report.pdf")


def test_spacey_source_key_round_trips_through_page_link(tmp_citadel):
    """The emit side (grammar.format_link_target): the link the sources catalog / index reflinks
    emit for a spacey key is angle-wrapped, so it parses back through split_link_target and still
    resolves to the key — a spacey key round-trips through every emitter."""
    key = "raw/my report.pdf"
    link = store.source_key_to_page_link(store.SOURCES_INDEX_REL, key)
    assert link.startswith("<") and link.endswith(">")
    path, suffix = grammar.split_link_target(link)
    assert suffix == ""
    assert linkgraph._link_points_at_key(store.SOURCES_INDEX_REL, path, key)
    # A space-free key stays a bare target (identity), byte-for-byte as before.
    assert grammar.format_link_target("../../raw/plain.md") == "../../raw/plain.md"


def test_angle_form_citation_with_spaces_matches_source_key(tmp_citadel, seed_page):
    """An angle-form citation to a raw path containing spaces resolves: ``_link_points_at_key``
    matches the spacey key, so ``find_raw_references`` finds the citing page (via the body link,
    not the ``resource`` field)."""
    raw = tmp_citadel.raw
    (raw / "other.md").write_text("x\n", encoding="utf-8")
    (raw / "my report.pdf").write_bytes(b"%PDF-1.7 fake")
    seed_page(
        "concepts/spacey.md",
        {"type": "Concept", "title": "Spacey", "description": "d", "tags": ["t"], "resource": "raw/other.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [my report](<../../raw/my report.pdf>) - r (ingested 2026-06-21)\n",
    )
    assert store.find_raw_references("raw/my report.pdf") == ["concepts/spacey.md"]


def test_rewrite_raw_references_keeps_spacey_citation_resolvable(tmp_citadel, seed_page):
    """Repointing a citation onto a key containing spaces must ROUND-TRIP: the rewriter emits the
    angle form, so the rewritten link still resolves to the new key (today it emits a bare spacey
    target that nothing can parse back)."""
    raw = tmp_citadel.raw
    (raw / "other.md").write_text("x\n", encoding="utf-8")
    (raw / "my report.pdf").write_bytes(b"%PDF-1.7 fake")
    seed_page(
        "concepts/spacey.md",
        {"type": "Concept", "title": "Spacey", "description": "d", "tags": ["t"], "resource": "raw/other.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [my report](<../../raw/my report.pdf>) - r (ingested 2026-06-21)\n",
    )
    (raw / "archive").mkdir()
    (raw / "my report.pdf").rename(raw / "archive" / "my report.pdf")

    changed = store.rewrite_raw_references("raw/my report.pdf", "raw/archive/my report.pdf")
    assert changed == ["concepts/spacey.md"]
    assert store.find_raw_references("raw/archive/my report.pdf") == ["concepts/spacey.md"]
    assert store.find_raw_references("raw/my report.pdf") == []
    body = (tmp_citadel.wiki / "concepts" / "spacey.md").read_text(encoding="utf-8")
    assert "(<../../raw/archive/my report.pdf>)" in body  # the documented angle form is emitted


def test_check_accepts_angle_form_citation_with_spaces(tmp_citadel, seed_page):
    """The strict gate accepts a footnote definition whose link uses the angle form with spaces —
    the definition parser must read the whole ``<...>`` target instead of stopping at the first
    whitespace and reporting a fabricated source."""
    raw = tmp_citadel.raw
    (raw / "my report.pdf").write_bytes(b"%PDF-1.7 fake")
    seed_page(
        "concepts/spacey.md",
        {"type": "Concept", "title": "Spacey", "description": "d", "tags": ["t"], "resource": "raw/my report.pdf"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [my report](<../../raw/my report.pdf>) - r (ingested 2026-06-21)\n",
    )
    page = store.load()[0]
    assert validate.source_issues(page.rel_path, page.body) == []
    assert errors_of(validate.validate_page(page.rel_path, page.frontmatter, page.body)) == []

def test_same_run_duplicate_carries_the_run_model_and_rules_stamp(make_citadel, fake_agent, tmp_path, monkeypatch):
    """A byte-identical copy recognized as a duplicate of a twin ingested in the SAME run carries
    that run's model + rules_version (the twin has no manifest entry yet at recognition time —
    carrying None left the copy unattributable in `status` and invisible to `--stale-rules`)."""
    cit = make_citadel(root=tmp_path / "repo")
    root_b = tmp_path / "share" / "more-raw"
    root_b.mkdir(parents=True)
    (cit.raw / "x.md").write_text("the same bytes\n", encoding="utf-8")
    (root_b / "x.md").write_text("the same bytes\n", encoding="utf-8")
    key_b = (root_b / "x.md").resolve().as_posix()
    monkeypatch.setattr(config, "RAW_DIRS", [cit.raw, root_b], raising=False)
    fake_agent(side_effect=_fake_session)

    ingest.ingest()
    data = cit.read_manifest()
    twin_model = manifest.entry_model(data["raw/x.md"])
    assert twin_model  # the ingested twin is attributed to the run's model
    assert manifest.entry_model(data[key_b]) == twin_model
    assert manifest.entry_rules_version(data[key_b]) == config.rules_version()

def test_tracked_source_that_became_unreadable_is_skipped_with_a_note(tmp_citadel, fake_agent, monkeypatch, capsys):
    """An already-ingested source whose re-hash fails (permissions / transient IO) stays skipped —
    never a fresh session, never a deletion — but the run says so on stderr instead of silently
    reading as 'ingested, nothing to do' forever."""
    fake_agent(side_effect=_fake_session)
    src = tmp_citadel.raw / "a.md"
    src.write_text("hello\n", encoding="utf-8")
    ingest.ingest()

    # Make the next run re-hash (stat no longer trusted) and fail that read.
    real_sha = manifest.file_sha256
    monkeypatch.setattr(
        manifest,
        "file_sha256",
        lambda p: (_ for _ in ()).throw(OSError("io error")) if p.name == "a.md" else real_sha(p),
    )
    report = ingest.ingest(full_rescan=True)
    err = capsys.readouterr().err
    assert report.errors == [] and report.processed == []
    assert "could not be re-read" in err and "raw/a.md" in err
    assert "raw/a.md" in tmp_citadel.read_manifest()  # still tracked, retried next run
