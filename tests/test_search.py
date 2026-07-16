"""Direct unit tests for ``store.search`` — the documented single swappable search seam.

These are CHARACTERIZATION tests: they pin the CURRENT observable contract (result shape,
field weights, the raw-substring bonus, tie-breaking, limit, the ``pages=`` restriction that
callers use for tag filtering, case handling, and robustness) so a future reimplementation
(e.g. SQLite FTS5 bm25) knows exactly which behavior it is replacing. All offline; pages are
seeded straight into the temp wiki via ``tmp_citadel`` + ``seed_page``.

Scoring model being pinned: token overlap (lowercased alphanumeric tokens, length >= 2)
weighted title 3.0 / aliases 2.5 / tags 2.0 / description 1.5 / body 1.0, each token scaled by its IDF
weight (a rare token outweighs one common to many pages; a token present in every page,
or in a single-page corpus, weighs exactly 1.0), plus a 0.5 bonus when the raw
stripped-lowercased query appears as a substring of the title or body. Zero scores are
dropped; results sort by score descending then rel_path ascending; top ``limit`` returned.
In most fixtures here a query token is either in one page or in every matching page (IDF
weight 1.0), so the expected scores stay multiples of 0.5 and exact ``==`` is safe; the two
tests that exercise a rarer token assert ordering and bounds instead.
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


def test_alias_hit_ranks_between_title_and_tags(tmp_citadel, seed_page):
    """A page's declared `aliases` are scored (weight 2.5), so a paraphrase that matches only an
    alias still reaches the page — above a tags hit (2.0), below a title hit (3.0). Search-lane
    harvest (#69): without this an alias-only term never ranked its page. 'cardamom' is in all 3
    pages so IDF ~1.0; the title page also gets the +0.5 substring bonus."""
    seed_page("concepts/title-hit.md", {"type": "concept", "title": "Cardamom"}, "Nothing.\n")
    seed_page(
        "concepts/alias-hit.md",
        {"type": "concept", "title": "Green Pod Spice", "aliases": ["cardamom"]},
        "Nothing here.\n",
    )
    seed_page("concepts/tag-hit.md", {"type": "concept", "title": "Beta", "tags": ["cardamom"]}, "Nothing.\n")

    hits = store.search("cardamom")

    assert [(p.rel_path, s) for p, s in hits] == [
        ("concepts/title-hit.md", 3.5),
        ("concepts/alias-hit.md", 2.5),
        ("concepts/tag-hit.md", 2.0),
    ]


def test_title_hit_outranks_body_hit(tmp_citadel, seed_page):
    """The core ranking promise: a query token in the title beats the same token in a body."""
    seed_page("concepts/in-title.md", {"type": "concept", "title": "Ferrite Basics"}, "Magnetic stuff.\n")
    seed_page("concepts/in-body.md", {"type": "concept", "title": "Magnets"}, "Uses ferrite cores.\n")

    hits = store.search("ferrite")

    assert [p.rel_path for p, _ in hits] == ["concepts/in-title.md", "concepts/in-body.md"]
    assert [s for _, s in hits] == [3.5, 1.5]


def test_multi_token_query_scores_accumulate(tmp_citadel, seed_page):
    """Each overlapping query token adds its field weight, scaled by IDF: the page with
    BOTH query tokens outranks the page with one. 'quantum' is on both pages (IDF 1.0) but
    'flux' is on only one, so IDF lifts both.md ABOVE the plain-overlap 2*3.0+0.5=6.5 it
    would score without rarity weighting; one.md keeps quantum's lone 3.0."""
    seed_page("concepts/both.md", {"type": "concept", "title": "Quantum Flux Theory"}, "Nothing else.\n")
    seed_page("concepts/one.md", {"type": "concept", "title": "Quantum Computing"}, "Nothing else.\n")

    hits = store.search("quantum flux")

    assert [p.rel_path for p, _ in hits] == ["concepts/both.md", "concepts/one.md"]
    both_score, one_score = hits[0][1], hits[1][1]
    assert one_score == 3.0  # a single common token, idf(quantum)=1.0 -> 3.0
    assert both_score > 6.5  # the rare 'flux' is IDF-boosted, lifting both.md past plain overlap


def test_idf_weights_a_rare_token_above_a_common_one(tmp_citadel, seed_page):
    """The IDF contract, and a regression lock (the golden-rank test): a rare query token
    must contribute strictly MORE than a corpus-common one. Ten pages carry 'common' in the
    body; only one also carries 'rare'. The rare token's IDF-weighted contribution exceeds
    the common token's whole score — which plain overlap counting (both weigh 1.0) cannot
    produce, so this test fails the instant the scorer drops IDF."""
    for i in range(9):
        seed_page(f"misc/p{i}.md", {"type": "misc", "title": f"P{i}"}, "the common word here\n")
    seed_page("misc/rare.md", {"type": "misc", "title": "Special"}, "the common word and the rare word\n")

    hits = {p.rel_path: s for p, s in store.search("common rare")}

    common_only = hits["misc/p0.md"]  # body 'common' only
    rare_page = hits["misc/rare.md"]  # body 'common' + 'rare'
    assert rare_page > common_only
    # the rare token's own contribution must exceed the entire common-only score:
    assert rare_page - common_only > common_only


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


def test_numeric_tag_is_coerced_not_a_crash(tmp_citadel, seed_page):
    """A bare year in the tag list (``tags: [finance, 2026]``) is YAML-parsed as an int.
    ``Page.tags`` coerces every entry to str, so search scores it like any tag token
    instead of raising TypeError in the ``" ".join(page.tags)`` IDF/scoring paths."""
    seed_page(
        "misc/budget.md", {"type": "misc", "title": "Budget", "tags": ["finance", 2026]}, "Totals by department.\n"
    )
    seed_page("misc/other.md", {"type": "misc", "title": "Other"}, "Nothing here.\n")

    budget = next(p for p in store.load() if p.rel_path == "misc/budget.md")
    assert budget.tags == ["finance", "2026"]

    hits = store.search("2026")

    assert [p.rel_path for p, _ in hits] == ["misc/budget.md"]


# --- light stemming (recall on paraphrased queries) ----------------------------------------


def test_stemming_matches_a_paraphrased_verb_form(tmp_citadel, seed_page):
    """The stemming contract: an inflected query form finds a page carrying a different
    inflection of the same word. 'brewing' (query) matches a body that only says 'brew',
    and 'founded' matches a title that says 'founding' — recall the un-stemmed tokenizer missed."""
    seed_page("concepts/coffee.md", {"type": "concept", "title": "Coffee"}, "You brew it slowly.\n")
    seed_page("concepts/company.md", {"type": "concept", "title": "Founding a Company"}, "History here.\n")

    assert [p.rel_path for p, _ in store.search("brewing")] == ["concepts/coffee.md"]
    assert [p.rel_path for p, _ in store.search("founded")] == ["concepts/company.md"]


def test_stemming_is_symmetric_so_plurals_and_singulars_agree(tmp_citadel, seed_page):
    """'magnets' (query) matches a body that says 'magnet', and vice versa — the stemmer is
    applied to both sides, so number/inflection no longer blocks a hit."""
    seed_page("concepts/m.md", {"type": "concept", "title": "Physics"}, "A single magnet attracts iron.\n")

    assert [p.rel_path for p, _ in store.search("magnets")] == ["concepts/m.md"]


def test_stemming_leaves_short_and_rootless_tokens_alone(tmp_citadel, seed_page):
    """Guard against over-stemming: a short token with no strippable suffix is unchanged, so an
    exact word still scores exactly as before (title 3.0 + substring bonus 0.5)."""
    seed_page("concepts/gas.md", {"type": "concept", "title": "Gas"}, "A state of matter.\n")

    hits = store.search("gas")
    assert [(p.rel_path, s) for p, s in hits] == [("concepts/gas.md", 3.5)]


def test_ly_needs_a_four_char_stem_so_early_does_not_match_ear(tmp_citadel, seed_page):
    """``-ly`` requires a 4-char stem: ``early`` stays whole (would otherwise collide with ``ear``),
    while ``nearly`` still stems to ``near`` and matches a page about ``near``."""
    seed_page("concepts/ear.md", {"type": "concept", "title": "Ear"}, "The ear hears sound.\n")
    seed_page("concepts/near.md", {"type": "concept", "title": "Near"}, "A near miss.\n")

    assert store.search("early") == []  # must NOT match the 'ear' page
    assert [p.rel_path for p, _ in store.search("nearly")] == ["concepts/near.md"]


def test_es_words_are_symmetric_with_their_singular(tmp_citadel, seed_page):
    """A consonant-ending ``-es`` plural strips a single char (via the ``-s`` rule), so ``tables``
    (query) matches a body that only says ``table`` — not the over-stripped ``tabl``."""
    seed_page("concepts/furniture.md", {"type": "concept", "title": "Furniture"}, "Put it on the table.\n")

    assert [p.rel_path for p, _ in store.search("tables")] == ["concepts/furniture.md"]


def test_single_pass_stemming_does_not_reach_the_bare_root(tmp_citadel, seed_page):
    """Boundary/characterization: the strip is ONE pass, so ``findings`` stems only to ``finding``,
    NOT to ``find`` — a page that only says ``find`` is not matched. Locks the intentional scope so a
    future move to two-pass stemming is a conscious change, not a silent regression."""
    seed_page("concepts/useful.md", {"type": "concept", "title": "Useful"}, "I find it useful.\n")

    assert store.search("findings") == []
