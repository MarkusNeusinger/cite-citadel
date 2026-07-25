"""The in-memory page-snapshot cache (:mod:`citadel.pagecache`) behind ``store.load()``.

Two things are under test, and the second matters more than the first: that a long-lived reader
stops re-parsing an unchanged wiki, and that it can NEVER serve something a fresh walk would not
have produced — a changed, added, deleted, renamed, or same-length-rewritten page, another wiki
directory, or anything at all during a mutating run.

Counting is done on ``store_core._load_pages`` (the uncached walk+parse): +1 means the wiki was
really re-read, +0 means the snapshot answered. The 2 s settle window is neutralized with
``_SETTLE_NS = 0`` wherever a test wants a warm cache from a just-written wiki (a freshly written
wiki is deliberately never cached); the window itself gets its own test.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from citadel import config, ingest, okf, pagecache, store, store_core


PAGE_FM = {"type": "concept", "title": "Coffee", "description": "A brewed drink.", "tags": ["beverage"], "sources": []}


@pytest.fixture
def counted(monkeypatch):
    """Count real walk+parse loads. Returns a zero-arg callable giving the current count."""
    calls = []
    real = store_core._load_pages

    def counting(wiki_dir):
        calls.append(wiki_dir)
        return real(wiki_dir)

    monkeypatch.setattr(store_core, "_load_pages", counting)
    return lambda: len(calls)


@pytest.fixture
def warm(monkeypatch):
    """Cache enabled and the settle window neutralized — the 'wiki has been quiet' state."""
    monkeypatch.setattr(pagecache, "_SETTLE_NS", 0)
    pagecache.enable()
    yield
    pagecache.reset()


def _seed_three(seed_page) -> None:
    seed_page("concepts/coffee.md", PAGE_FM, "Coffee is brewed from roasted beans.\n")
    seed_page("concepts/tea.md", {**PAGE_FM, "title": "Tea"}, "Tea is steeped.\n")
    seed_page("persons/ada.md", {**PAGE_FM, "type": "person", "title": "Ada"}, "Ada writes.\n")


# --- default behavior: off ---------------------------------------------------------------


def test_cache_is_off_by_default(tmp_citadel, seed_page, counted):
    """Nothing opts in, so every load() re-reads the wiki exactly as before the cache existed."""
    _seed_three(seed_page)
    assert len(store.load()) == 3
    assert len(store.load()) == 3
    assert counted() == 2


def test_env_knob_forces_the_cache_on_without_an_opt_in(tmp_citadel, seed_page, counted, monkeypatch):
    """CITADEL_PAGE_CACHE=1 caches in any process that consults it (no pagecache.enable() call)."""
    monkeypatch.setattr(pagecache, "_SETTLE_NS", 0)
    monkeypatch.setattr(config, "PAGE_CACHE", "on")
    _seed_three(seed_page)
    store.load()
    store.load()
    assert counted() == 1


def test_env_knob_forces_the_cache_off_over_an_opt_in(tmp_citadel, seed_page, counted, monkeypatch):
    """CITADEL_PAGE_CACHE=0 wins over enable() — the documented escape hatch."""
    monkeypatch.setattr(pagecache, "_SETTLE_NS", 0)
    monkeypatch.setattr(config, "PAGE_CACHE", "off")
    pagecache.enable()
    _seed_three(seed_page)
    store.load()
    store.load()
    assert counted() == 2


# --- the hit ------------------------------------------------------------------------------


def test_unchanged_wiki_is_served_from_the_snapshot(tmp_citadel, seed_page, counted, warm):
    """The point of the whole module: one parse, then stat-only validation."""
    _seed_three(seed_page)
    first = store.load()
    second = store.load()
    third = store.load()
    assert counted() == 1
    assert [p.rel_path for p in first] == [p.rel_path for p in second] == [p.rel_path for p in third]
    # Same Page objects (that identity is what makes the search memo hit), fresh list each call.
    assert first[0] is second[0]
    assert first is not second


def test_caller_may_mutate_the_returned_list(tmp_citadel, seed_page, counted, warm):
    """load() hands out a shallow copy: a caller sorting/clearing it cannot corrupt the snapshot."""
    _seed_three(seed_page)
    pages = store.load()
    pages.clear()
    pages.append("junk")
    assert len(store.load()) == 3
    assert counted() == 1


# --- the misses: every way the wiki can change --------------------------------------------


def test_edited_page_is_seen(tmp_citadel, seed_page, counted, warm):
    _seed_three(seed_page)
    store.load()
    seed_page("concepts/coffee.md", PAGE_FM, "Coffee is brewed from roasted beans. Also: crema.\n")
    bodies = {p.rel_path: p.body for p in store.load()}
    assert "crema" in bodies["concepts/coffee.md"]
    assert counted() == 2


def test_same_length_rewrite_is_seen(tmp_citadel, seed_page, counted, warm):
    """Size alone cannot catch a rewrite, so the fingerprint carries mtime/ctime too. The stamp is
    moved explicitly rather than relying on the clock, so the assertion holds on any filesystem
    timestamp resolution."""
    _seed_three(seed_page)
    store.load()
    target = Path(config.wiki_dir()) / "concepts/coffee.md"
    before = target.stat()
    target.write_text(okf.dump(PAGE_FM, "Coffee is brewed from ROASTED beans.\n"), encoding="utf-8")
    assert target.stat().st_size == before.st_size  # the case size cannot catch
    os.utime(target, ns=(before.st_atime_ns + 10**10, before.st_mtime_ns + 10**10))
    assert "ROASTED" in {p.rel_path: p.body for p in store.load()}["concepts/coffee.md"]
    assert counted() == 2


def test_new_page_is_seen(tmp_citadel, seed_page, counted, warm):
    _seed_three(seed_page)
    store.load()
    seed_page("concepts/cocoa.md", {**PAGE_FM, "title": "Cocoa"}, "Cocoa is pressed.\n")
    assert len(store.load()) == 4
    assert counted() == 2


def test_deleted_page_is_seen(tmp_citadel, seed_page, counted, warm):
    _seed_three(seed_page)
    store.load()
    (Path(config.wiki_dir()) / "concepts/tea.md").unlink()
    assert len(store.load()) == 2
    assert counted() == 2


def test_renamed_page_is_seen(tmp_citadel, seed_page, counted, warm):
    """A move keeps size and content; the fingerprint is keyed by rel_path, so it still misses."""
    _seed_three(seed_page)
    store.load()
    wiki = Path(config.wiki_dir())
    (wiki / "concepts/tea.md").rename(wiki / "concepts/black-tea.md")
    assert "concepts/black-tea.md" in [p.rel_path for p in store.load()]
    assert counted() == 2


def test_generated_files_do_not_invalidate(tmp_citadel, seed_page, counted, warm):
    """The fingerprint tracks exactly the files load() parses: index.md / log.md / dotfiles are
    regenerated on every run and are not pages, so rewriting them must not cost a re-parse."""
    _seed_three(seed_page)
    store.load()
    wiki = Path(config.wiki_dir())
    (wiki / "index.md").write_text("# Index\n\nregenerated\n", encoding="utf-8")
    (wiki / "concepts/index.md").write_text("# concepts\n\nregenerated\n", encoding="utf-8")
    (wiki / "log.md").write_text("# Log\n\n- entry\n", encoding="utf-8")
    (wiki / ".citadel_ingested.json").write_text("{}", encoding="utf-8")
    assert len(store.load()) == 3
    assert counted() == 1


def test_a_symlinked_page_is_stat_through_to_its_target(tmp_citadel, seed_page, counted, warm, tmp_path):
    """load() reads through a file symlink, so the fingerprint must stat through it too — else an
    edit to the target would be invisible."""
    _seed_three(seed_page)
    target = tmp_path / "external-page.md"
    target.write_text(okf.dump({**PAGE_FM, "title": "External"}, "External body.\n"), encoding="utf-8")
    link = Path(config.wiki_dir()) / "concepts/external.md"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):  # pragma: no cover - Windows without symlink privilege
        pytest.skip("symlinks not available")
    assert len(store.load()) == 4
    target.write_text(okf.dump({**PAGE_FM, "title": "External"}, "External body, revised.\n"), encoding="utf-8")
    bodies = {p.rel_path: p.body for p in store.load()}
    assert "revised" in bodies["concepts/external.md"]
    assert counted() == 2


def test_write_page_and_delete_page_invalidate(tmp_citadel, seed_page, counted, warm):
    """The in-process mutators drop the snapshot themselves — no stat walk needed to be right."""
    _seed_three(seed_page)
    store.load()
    store.write_page("concepts/cocoa.md", {**PAGE_FM, "title": "Cocoa"}, "Cocoa is pressed.\n")
    assert len(store.load()) == 4
    assert store.delete_page("concepts/cocoa.md") is True
    assert len(store.load()) == 3
    assert counted() == 3


# --- the guards ---------------------------------------------------------------------------


def test_a_freshly_written_wiki_is_not_cached(tmp_citadel, seed_page, counted, monkeypatch):
    """The settle window at its real value: while the wiki's newest stamp is younger than the
    window, every load re-reads — a coarse-timestamp filesystem could hide a same-tick rewrite
    behind an unchanged (size, mtime, ctime)."""
    pagecache.enable()
    _seed_three(seed_page)
    store.load()
    store.load()
    assert counted() == 2
    # Zeroing the window stands in for 'the wiki has been quiet longer than that': caching starts.
    monkeypatch.setattr(pagecache, "_SETTLE_NS", 0)
    store.load()
    store.load()
    assert counted() == 3


def test_snapshot_is_keyed_by_wiki_directory(tmp_citadel, seed_page, counted, warm, tmp_path):
    """Ingest redirects config.wiki_dir() at a staging copy; a snapshot of one directory must never
    answer for another (and the single slot means staging dirs cannot accumulate)."""
    _seed_three(seed_page)
    assert len(store.load()) == 3
    other = tmp_path / "other-wiki"
    (other / "concepts").mkdir(parents=True)
    (other / "concepts/solo.md").write_text(okf.dump(PAGE_FM, "Only page.\n"), encoding="utf-8")
    original = config.wiki_dir()
    try:
        config.WIKI_DIR = other
        assert [p.rel_path for p in store.load()] == ["concepts/solo.md"]
    finally:
        config.WIKI_DIR = original
    assert len(store.load()) == 3
    assert counted() == 3  # one per directory switch: nothing was served across wikis


def test_paused_never_serves_and_drops_the_snapshot(tmp_citadel, seed_page, counted, warm):
    _seed_three(seed_page)
    store.load()
    with pagecache.paused():
        store.load()
        store.load()
        assert counted() == 3
    store.load()  # the snapshot was dropped on exit too
    assert counted() == 4


def test_paused_is_reentrant(tmp_citadel, seed_page, counted, warm):
    _seed_three(seed_page)
    with pagecache.paused():
        with pagecache.paused():
            assert pagecache.enabled() is False
        assert pagecache.enabled() is False, "the inner exit must not re-enable the cache"
    assert pagecache.enabled() is True


def test_ingest_runs_with_the_cache_bypassed(tmp_citadel, seed_page, fake_agent, transformer_page, counted, warm):
    """ingest() wears @pagecache.bypass, so its diff-by-hash always reads the truth from disk —
    and the run's writes are visible to the very next read."""
    _seed_three(seed_page)
    store.load()
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    loads_before = counted()

    seen = {}
    fake_agent(transformer_page, side_effect=lambda *a, **kw: seen.setdefault("cached", pagecache.enabled()))
    report = ingest.ingest()

    assert not report.errors
    assert seen["cached"] is False, "an agent session must never run with the read cache live"
    assert counted() > loads_before, "the staged run really did re-read the wiki"
    assert "concepts/transformer.md" in [p.rel_path for p in store.load()]


def test_fingerprint_is_none_on_a_walk_error(tmp_citadel, seed_page, warm, monkeypatch):
    """A flaky share (or a directory that vanished mid-walk) yields no fingerprint at all."""
    _seed_three(seed_page)
    assert pagecache.fingerprint(config.wiki_dir(), store_core.is_skipped_name) is not None

    def boom(path):
        raise OSError("scandir failed")

    monkeypatch.setattr(os, "scandir", boom)
    assert pagecache.fingerprint(config.wiki_dir(), store_core.is_skipped_name) is None


def test_no_fingerprint_degrades_to_uncached(tmp_citadel, seed_page, counted, warm, monkeypatch):
    """'Cannot vouch for this' means an uncached load, never a guess — nothing is stored, and a
    snapshot cannot be served without re-verifying it either."""
    _seed_three(seed_page)
    monkeypatch.setattr(pagecache, "fingerprint", lambda *args, **kwargs: None)
    assert len(store.load()) == 3
    assert len(store.load()) == 3
    assert counted() == 2


def test_a_missing_wiki_directory_is_not_cached(tmp_citadel, counted, warm):
    """An empty (or not-yet-created) wiki dir: [] every time, from disk, never from a snapshot."""
    import shutil

    shutil.rmtree(config.wiki_dir())
    assert store.load() == []
    assert store.load() == []
    assert counted() == 2


def test_a_wiki_that_changes_during_the_load_is_not_cached(tmp_citadel, seed_page, counted, warm, monkeypatch):
    """The bracketed fingerprint: a page written WHILE the load runs must not be paired with the
    post-load stamp — that is the one race that could go stale forever."""
    _seed_three(seed_page)
    real = store_core._load_pages

    def load_then_change(wiki_dir):
        pages = real(wiki_dir)
        target = Path(config.wiki_dir()) / "concepts/late.md"
        target.write_text(okf.dump({**PAGE_FM, "title": "Late"}, "Written mid-load.\n"), encoding="utf-8")
        return pages

    monkeypatch.setattr(store_core, "_load_pages", load_then_change)
    assert len(store.load()) == 3  # the mid-load page is not in this result...
    monkeypatch.setattr(store_core, "_load_pages", real)
    assert len(store.load()) == 4  # ... and the next load sees it, because nothing was cached
    assert counted() == 2  # both loads were real: the racing one could not be vouched for


# --- the derived memo ---------------------------------------------------------------------


def test_search_results_are_identical_warm_and_cold(tmp_citadel, seed_page, warm, monkeypatch):
    """The memoized term-frequency tables must not change a single score or rank."""
    _seed_three(seed_page)
    seed_page(
        "concepts/espresso.md",
        {**PAGE_FM, "title": "Espresso", "tags": ["beverage", "coffee"]},
        "Espresso is brewed under pressure from roasted coffee beans.\n",
    )
    pagecache.reset()  # cold: no snapshot, no memo
    cold = [(p.rel_path, round(s, 6)) for p, s in store.search("brewed coffee beans", limit=10)]
    monkeypatch.setattr(pagecache, "_SETTLE_NS", 0)
    pagecache.enable()
    store.load()  # take a snapshot, so the second search runs off the memo
    warm_first = [(p.rel_path, round(s, 6)) for p, s in store.search("brewed coffee beans", limit=10)]
    warm_second = [(p.rel_path, round(s, 6)) for p, s in store.search("brewed coffee beans", limit=10)]
    assert cold == warm_first == warm_second
    assert cold  # the query really matched something
    # Operator queries and the tag= filter path go through the same snapshot.
    assert [p.rel_path for p, _ in store.search("type:person")] == ["persons/ada.md"]


def test_memo_dies_with_the_snapshot(tmp_citadel, seed_page, warm):
    """An edited page must be re-tokenized, not answered from the previous snapshot's tables."""
    _seed_three(seed_page)
    assert not store.search("chicory", limit=5)
    seed_page("concepts/coffee.md", PAGE_FM, "Coffee is sometimes cut with chicory.\n")
    assert [p.rel_path for p, _ in store.search("chicory", limit=5)] == ["concepts/coffee.md"]


def test_memo_ignores_pages_outside_the_snapshot(tmp_citadel, seed_page, warm):
    """A page the snapshot does not hold alive is computed fresh — id() is only unique among live
    objects, so a foreign page must never be memoized under a recyclable address."""
    _seed_three(seed_page)
    store.load()
    foreign = okf.Page(rel_path="concepts/ghost.md", frontmatter={**PAGE_FM, "title": "Ghost"}, body="Ghostly cocoa.\n")
    calls = []
    assert pagecache.memo(foreign, "field_counts", lambda: calls.append(1) or {"x": 1}) == {"x": 1}
    assert pagecache.memo(foreign, "field_counts", lambda: calls.append(1) or {"x": 1}) == {"x": 1}
    assert len(calls) == 2  # recomputed both times, never stored
    hits = store.search("ghostly cocoa", pages=[foreign], limit=5)
    assert [p.rel_path for p, _ in hits] == ["concepts/ghost.md"]
