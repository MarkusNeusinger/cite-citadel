"""Direct unit tests for ``store.search`` — the documented single swappable search seam.

These are CHARACTERIZATION tests: they pin the CURRENT observable contract (result shape,
field weights, the raw-substring bonus, tie-breaking, limit, the ``pages=`` restriction that
callers use for tag filtering, case handling, and robustness) so a future reimplementation
(e.g. SQLite FTS5 bm25) knows exactly which behavior it is replacing. All offline; pages are
seeded straight into the temp wiki via ``tmp_citadel`` + ``seed_page``.

Scoring model being pinned: token overlap (lowercased alphanumeric tokens, length >= 2)
weighted title 3.0 / tags 2.0 / description 1.5 / body 1.0, plus a 0.5 bonus when the raw
stripped-lowercased query appears as a substring of the title or body. Zero scores are
dropped; results sort by score descending then rel_path ascending; top ``limit`` returned.
All expected scores are multiples of 0.5, so exact ``==`` float comparisons are safe.
"""

from __future__ import annotations

from citadel import okf, store
from citadel.okf import Page


# --- result shape --------------------------------------------------------------------------


def test_search_returns_page_score_tuples(tmp_citadel, seed_page):
    """A hit is a (Page, float) tuple: the loaded page plus its score, in a plain list."""
    seed_page("concepts/quasar.md", {"type": "concept", "title": "Quasar"}, "A luminous core.\n")

    hits = store.search("quasar")

    assert isinstance(hits, list)
    assert len(hits) == 1
    page, score = hits[0]
    assert isinstance(page, Page)
    assert isinstance(score, float)
    assert page.rel_path == "concepts/quasar.md"
    assert page.title == "Quasar"
    # title token overlap (3.0) + raw-substring bonus in the title (0.5).
    assert score == 3.5


# --- ranking: field weights and the substring bonus ----------------------------------------


def test_field_weight_ladder_title_tags_description_body(tmp_citadel, seed_page):
    """One token in exactly one field per page pins the weights: title 3.0(+0.5 bonus),
    tags 2.0, description 1.5, body 1.0(+0.5 bonus). The bonus only inspects title/body,
    so a description-only hit (1.5) TIES with a body-only hit (1.0+0.5) and the tie is
    broken by rel_path ascending — body-hit.md sorts before desc-hit.md."""
    seed_page("concepts/title-hit.md", {"type": "concept", "title": "Zephyr"}, "Nothing to see.\n")
    seed_page("concepts/tag-hit.md", {"type": "concept", "title": "Alpha", "tags": ["zephyr"]}, "Nothing to see.\n")
    seed_page(
        "concepts/desc-hit.md",
        {"type": "concept", "title": "Beta", "description": "All about zephyr currents."},
        "Nothing to see.\n",
    )
    seed_page("concepts/body-hit.md", {"type": "concept", "title": "Gamma"}, "The zephyr blows west.\n")

    hits = store.search("zephyr")

    assert [(p.rel_path, s) for p, s in hits] == [
        ("concepts/title-hit.md", 3.5),
        ("concepts/tag-hit.md", 2.0),
        ("concepts/body-hit.md", 1.5),
        ("concepts/desc-hit.md", 1.5),
    ]


def test_title_hit_outranks_body_hit(tmp_citadel, seed_page):
    """The core ranking promise: a query token in the title beats the same token in a body."""
    seed_page("concepts/in-title.md", {"type": "concept", "title": "Ferrite Basics"}, "Magnetic stuff.\n")
    seed_page("concepts/in-body.md", {"type": "concept", "title": "Magnets"}, "Uses ferrite cores.\n")

    hits = store.search("ferrite")

    assert [p.rel_path for p, _ in hits] == ["concepts/in-title.md", "concepts/in-body.md"]
    assert [s for _, s in hits] == [3.5, 1.5]


def test_multi_token_query_scores_accumulate(tmp_citadel, seed_page):
    """Each overlapping query token adds its field weight; the substring bonus needs the
    exact raw phrase: 'Quantum Flux Theory' gets 2*3.0+0.5=6.5, 'Quantum Computing' gets 3.0."""
    seed_page("concepts/both.md", {"type": "concept", "title": "Quantum Flux Theory"}, "Nothing else.\n")
    seed_page("concepts/one.md", {"type": "concept", "title": "Quantum Computing"}, "Nothing else.\n")

    hits = store.search("quantum flux")

    assert [(p.rel_path, s) for p, s in hits] == [("concepts/both.md", 6.5), ("concepts/one.md", 3.0)]


def test_substring_bonus_requires_contiguous_phrase(tmp_citadel, seed_page):
    """Both pages match both tokens in the body (2.0), but only the page containing the
    contiguous lowercased phrase 'black hole' earns the extra 0.5."""
    seed_page("concepts/adjacent.md", {"type": "concept", "title": "Spinner"}, "A black hole spins fast.\n")
    seed_page("concepts/scattered.md", {"type": "concept", "title": "Boxes"}, "The hole in the black box.\n")

    hits = store.search("black hole")

    assert [(p.rel_path, s) for p, s in hits] == [("concepts/adjacent.md", 2.5), ("concepts/scattered.md", 2.0)]


def test_single_char_query_matches_via_substring_bonus_only(tmp_citadel, seed_page):
    """Characterization quirk: tokens shorter than 2 chars are dropped, so a 1-char query
    yields no token overlap — yet the raw-substring bonus still fires, surfacing any page
    whose title or body contains the character, scored exactly 0.5."""
    seed_page("concepts/hit.md", {"type": "concept", "title": "Drive"}, "A q-drive prototype.\n")
    seed_page("concepts/miss.md", {"type": "concept", "title": "Sail"}, "Solar wind only.\n")

    hits = store.search("q")

    assert [(p.rel_path, s) for p, s in hits] == [("concepts/hit.md", 0.5)]


def test_ties_break_by_rel_path_ascending(tmp_citadel, seed_page):
    """Equal scores order deterministically by rel_path (the sort key is (-score, rel_path))."""
    for name in ("cc", "aa", "bb"):
        seed_page(f"misc/{name}.md", {"type": "misc", "title": name.upper()}, "A meteor passed.\n")

    hits = store.search("meteor")

    assert [s for _, s in hits] == [1.5, 1.5, 1.5]
    assert [p.rel_path for p, _ in hits] == ["misc/aa.md", "misc/bb.md", "misc/cc.md"]


# --- limit ---------------------------------------------------------------------------------


def test_default_limit_is_eight(tmp_citadel, seed_page):
    """Ten equal matches, default call -> exactly the first 8 by rel_path."""
    for i in range(10):
        seed_page(f"misc/p{i:02d}.md", {"type": "misc", "title": f"Page {i}"}, "A meteor passed.\n")

    hits = store.search("meteor")

    assert [p.rel_path for p, _ in hits] == [f"misc/p{i:02d}.md" for i in range(8)]


def test_explicit_limit_truncates_after_ranking(tmp_citadel, seed_page):
    """limit=N returns the top N of the FULL ranking (not the first N pages scanned)."""
    seed_page("misc/weak.md", {"type": "misc", "title": "Weak"}, "A meteor passed.\n")
    seed_page("misc/strong.md", {"type": "misc", "title": "Meteor"}, "Nothing here.\n")

    hits = store.search("meteor", limit=1)

    assert [(p.rel_path, s) for p, s in hits] == [("misc/strong.md", 3.5)]


def test_limit_zero_returns_empty(tmp_citadel, seed_page):
    """limit=0 slices everything away, even with matches present."""
    seed_page("misc/p.md", {"type": "misc", "title": "Meteor"}, "Body.\n")

    assert store.search("meteor", limit=0) == []


# --- the pages= seam (how callers implement tag filtering) ---------------------------------


def test_explicit_pages_restricts_the_searched_set(tmp_citadel, seed_page):
    """Passing pages= searches ONLY that list — the seam cli/server use for --tag filtering:
    pre-filter load() by tag, then hand the survivors to search()."""
    seed_page("misc/tagged.md", {"type": "misc", "title": "One", "tags": ["space"]}, "A meteor passed.\n")
    seed_page("misc/untagged.md", {"type": "misc", "title": "Two"}, "A meteor passed.\n")

    want = "space"
    filtered = [p for p in store.load() if want in [str(t).lower() for t in p.tags]]
    hits = store.search("meteor", pages=filtered)

    assert [p.rel_path for p, _ in hits] == ["misc/tagged.md"]


def test_empty_pages_list_is_not_replaced_by_load(tmp_citadel, seed_page):
    """pages=[] means 'search nothing' (only pages=None falls back to load())."""
    seed_page("misc/p.md", {"type": "misc", "title": "Meteor"}, "Body.\n")

    assert store.search("meteor", pages=[]) == []
    assert store.search("meteor", pages=None) != []


def test_tag_tokens_score_without_any_filtering(tmp_citadel, seed_page):
    """A query token that only appears in a page's tags still ranks it (weight 2.0) —
    tag data is part of the default corpus, not just a filter key."""
    seed_page("misc/p.md", {"type": "misc", "title": "Plain", "tags": ["orbital", "debris"]}, "Nothing.\n")

    hits = store.search("orbital")

    assert [(p.rel_path, s) for p, s in hits] == [("misc/p.md", 2.0)]


# --- case sensitivity ----------------------------------------------------------------------


def test_search_is_case_insensitive_including_the_bonus(tmp_citadel, seed_page):
    """Query and page text are both lowercased: 'ZEPHYR', 'Zephyr' and 'zephyr' all score
    identically against a capitalized body, substring bonus included."""
    seed_page("misc/p.md", {"type": "misc", "title": "Wind"}, "The Zephyr blew.\n")

    for query in ("zephyr", "ZEPHYR", "Zephyr"):
        hits = store.search(query)
        assert [(p.rel_path, s) for p, s in hits] == [("misc/p.md", 1.5)], query


# --- no-match and degenerate queries -------------------------------------------------------


def test_no_match_returns_empty_list(tmp_citadel, seed_page):
    """Zero-score pages are dropped, so a query hitting nothing yields []."""
    seed_page("misc/p.md", {"type": "misc", "title": "Coffee"}, "Beans and water.\n")

    assert store.search("xylophone") == []


def test_empty_and_whitespace_queries_match_nothing(tmp_citadel, seed_page):
    """'' and '   ' produce no tokens AND an empty raw query, so no page can score."""
    seed_page("misc/p.md", {"type": "misc", "title": "Coffee"}, "Beans and water.\n")

    assert store.search("") == []
    assert store.search("   ") == []


# --- robustness ----------------------------------------------------------------------------


def test_search_on_empty_wiki_returns_empty(tmp_citadel):
    """A wiki with no pages at all is a valid corpus: search returns [] without raising."""
    assert store.search("anything") == []


def test_search_tolerates_broken_frontmatter(tmp_citadel):
    """okf.parse returns ({}, full_text) for malformed YAML, so a hand-mangled page still
    loads (title falls back to rel_path) and its text remains searchable as body."""
    broken = tmp_citadel.wiki / "misc" / "broken.md"
    broken.parent.mkdir(parents=True, exist_ok=True)
    broken.write_text("---\ntitle: [unclosed\n---\nThe zephyr appears here.\n", encoding="utf-8")
    frontmatter, _body = okf.parse(broken.read_text(encoding="utf-8"))
    assert frontmatter == {}  # precondition: this really is the malformed-YAML fallback

    hits = store.search("zephyr")

    assert len(hits) == 1
    page, score = hits[0]
    assert page.rel_path == "misc/broken.md"
    assert page.title == "misc/broken.md"  # Page.title falls back to rel_path
    assert score == 1.5  # body token (1.0) + substring bonus (0.5)


def test_default_corpus_excludes_generated_files(tmp_citadel, seed_page):
    """With pages=None, search runs over load(), which skips index.md, log.md, per-folder
    index.md and dotfiles — a query token planted in generated files never surfaces."""
    (tmp_citadel.wiki / "index.md").write_text("meteor meteor meteor\n", encoding="utf-8")
    tmp_citadel.log_path.write_text("meteor\n", encoding="utf-8")
    seed_page("misc/index.md", {"type": "misc", "title": "Meteor Index"}, "meteor\n")
    seed_page("misc/real.md", {"type": "misc", "title": "Real"}, "A meteor passed.\n")

    hits = store.search("meteor")

    assert [p.rel_path for p, _ in hits] == ["misc/real.md"]
