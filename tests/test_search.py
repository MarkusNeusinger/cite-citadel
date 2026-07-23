"""Direct unit tests for ``store.search`` — the documented single swappable search seam.

These are CHARACTERIZATION tests pinning the ranked-BM25 contract (the 2026-07 audit's backlog
#1, replacing the original token-overlap scorer): result shape, AND term semantics with the
stopword exemption and the one-shot OR recall fallback, the ``tag:``/``type:`` operator grammar
shared with the offline viewer, the BM25 field-weight ladder (title > aliases > tags >
description > body), the contiguous-phrase bonus, stemming, tie-breaking, limit, the ``pages=``
restriction callers use for tag filtering, case handling, and robustness. All offline; pages are
seeded straight into the temp wiki via ``tmp_citadel`` + ``seed_page``.

BM25 scores are corpus-relative floats (Lucene-smoothed IDF x saturated, length-normalized term
frequency x field weight), so most tests assert ORDER and reachability rather than exact values;
the only pinned magnitudes are the flat 1.0 of an operator-only listing and the 0.5
phrase/substring bonus of a page the tokenizer cannot reach.
"""

from __future__ import annotations

import pytest

from citadel import okf, store
from citadel.okf import Page


# --- result shape --------------------------------------------------------------------------


def test_search_returns_page_score_tuples(tmp_citadel, seed_page):
    """A hit is a (Page, float) tuple: the loaded page plus its positive score, in a plain list."""
    seed_page("concepts/quasar.md", {"type": "concept", "title": "Quasar"}, "A luminous core.\n")

    hits = store.search("quasar")

    assert isinstance(hits, list)
    assert len(hits) == 1
    page, score = hits[0]
    assert isinstance(page, Page)
    assert isinstance(score, float)
    assert page.rel_path == "concepts/quasar.md"
    assert page.title == "Quasar"
    assert score > 0.0


# --- ranking: field weights and the phrase bonus -------------------------------------------


def test_field_weight_ladder_title_alias_tag_description_body(tmp_citadel, seed_page):
    """One token in exactly one field per page pins the BM25 column-weight ladder: a title hit
    outranks an alias hit outranks a tag hit outranks a description hit outranks a body hit."""
    seed_page("concepts/title-hit.md", {"type": "concept", "title": "Zephyr"}, "Nothing to see.\n")
    seed_page(
        "concepts/alias-hit.md", {"type": "concept", "title": "West Wind", "aliases": ["zephyr"]}, "Nothing to see.\n"
    )
    seed_page("concepts/tag-hit.md", {"type": "concept", "title": "Alpha", "tags": ["zephyr"]}, "Nothing to see.\n")
    seed_page(
        "concepts/desc-hit.md",
        {"type": "concept", "title": "Beta", "description": "All about zephyr currents."},
        "Nothing to see.\n",
    )
    seed_page("concepts/body-hit.md", {"type": "concept", "title": "Gamma"}, "The zephyr blows west.\n")

    hits = store.search("zephyr")

    assert [p.rel_path for p, _ in hits] == [
        "concepts/title-hit.md",
        "concepts/alias-hit.md",
        "concepts/tag-hit.md",
        "concepts/desc-hit.md",
        "concepts/body-hit.md",
    ]
    assert all(score > 0.0 for _, score in hits)


def test_title_hit_outranks_body_hit(tmp_citadel, seed_page):
    """The core ranking promise: a query token in the title beats the same token in a body."""
    seed_page("concepts/in-title.md", {"type": "concept", "title": "Ferrite Basics"}, "Magnetic stuff.\n")
    seed_page("concepts/in-body.md", {"type": "concept", "title": "Magnets"}, "Uses ferrite cores.\n")

    hits = store.search("ferrite")

    assert [p.rel_path for p, _ in hits] == ["concepts/in-title.md", "concepts/in-body.md"]


def test_bm25_weighs_a_rare_token_above_a_common_one(tmp_citadel, seed_page):
    """The rarity contract BM25 carries over from the old IDF scorer: among pages matching a
    two-term OR-fallback query (no page holds both terms, so AND rescues to OR), the page
    carrying the corpus-rare term must rank first."""
    for i in range(9):
        seed_page(f"misc/p{i}.md", {"type": "misc", "title": f"P{i}"}, "the common word here\n")
    seed_page("misc/rare.md", {"type": "misc", "title": "Special"}, "holds the rare word only\n")

    hits = store.search("common rare", limit=50)

    assert hits[0][0].rel_path == "misc/rare.md"
    assert len(hits) == 10  # AND matched nothing -> OR fallback keeps every partial match reachable


def test_phrase_bonus_ranks_contiguous_phrase_first(tmp_citadel, seed_page):
    """Both pages match both tokens in the body, but only the page containing the contiguous
    lowercased phrase 'black hole' earns the 0.5 bonus and ranks first."""
    seed_page("concepts/adjacent.md", {"type": "concept", "title": "Spinner"}, "A black hole spins fast.\n")
    seed_page("concepts/scattered.md", {"type": "concept", "title": "Boxes"}, "The hole in the black box.\n")

    hits = store.search("black hole")

    assert [p.rel_path for p, _ in hits] == ["concepts/adjacent.md", "concepts/scattered.md"]
    assert hits[0][1] - hits[1][1] == pytest.approx(0.5, abs=0.2)


def test_single_char_query_matches_via_substring_bonus_only(tmp_citadel, seed_page):
    """Characterization quirk carried over from the old scorer: tokens shorter than 2 chars are
    dropped, so a 1-char query yields no term match — yet the phrase/substring net still fires,
    surfacing any page containing the character, scored exactly 0.5."""
    seed_page("concepts/hit.md", {"type": "concept", "title": "Drive"}, "A q-drive prototype.\n")
    seed_page("concepts/miss.md", {"type": "concept", "title": "Sail"}, "Solar wind only.\n")

    hits = store.search("q")

    assert [(p.rel_path, s) for p, s in hits] == [("concepts/hit.md", 0.5)]


def test_ties_break_by_rel_path_ascending(tmp_citadel, seed_page):
    """Equal scores order deterministically by rel_path (the sort key is (-score, rel_path))."""
    for name in ("cc", "aa", "bb"):
        seed_page(f"misc/{name}.md", {"type": "misc", "title": name.upper()}, "A meteor passed.\n")

    hits = store.search("meteor")

    assert len({s for _, s in hits}) == 1  # identical pages -> identical scores
    assert [p.rel_path for p, _ in hits] == ["misc/aa.md", "misc/bb.md", "misc/cc.md"]


# --- AND semantics and the OR recall fallback ----------------------------------------------


def test_terms_are_and_matched_when_a_full_match_exists(tmp_citadel, seed_page):
    """Viewer-convergent AND: when some page matches EVERY bare term, pages matching only a
    subset are excluded — 'quantum flux' returns the flux page only, not every quantum page."""
    seed_page("concepts/both.md", {"type": "concept", "title": "Quantum Flux Theory"}, "Nothing else.\n")
    seed_page("concepts/one.md", {"type": "concept", "title": "Quantum Computing"}, "Nothing else.\n")

    hits = store.search("quantum flux")

    assert [p.rel_path for p, _ in hits] == ["concepts/both.md"]


def test_stopwords_are_not_required_by_the_and_match(tmp_citadel, seed_page):
    """A natural-language question is AND-matched on its content words only: 'how do you brew
    coffee' reaches the brewing page even though it contains none of 'how'/'do'/'you' — and a
    page that happens to contain the stopwords but not both content words is excluded."""
    seed_page("concepts/brewing.md", {"type": "concept", "title": "Coffee Brewing"}, "Brew it slowly.\n")
    seed_page("concepts/chatty.md", {"type": "concept", "title": "Notes"}, "How do you like it? With coffee.\n")

    hits = store.search("how do you brew coffee")

    assert [p.rel_path for p, _ in hits] == ["concepts/brewing.md"]


def test_stopword_only_query_keeps_its_terms(tmp_citadel, seed_page):
    """A query consisting ONLY of stopwords is not filtered to nothing — the terms stay and
    match normally, so searching for 'the' still works."""
    seed_page("misc/p.md", {"type": "misc", "title": "Article"}, "The word appears here.\n")

    assert [p.rel_path for p, _ in store.search("the")] == ["misc/p.md"]


def test_or_fallback_rescues_a_query_no_page_fully_matches(tmp_citadel, seed_page):
    """When NO page matches every term, the query is retried as OR so the closest pages still
    surface instead of a flat 'no matches' — first-shot recall for partially-wrong phrasings."""
    seed_page("concepts/one.md", {"type": "concept", "title": "Quantum Computing"}, "Nothing else.\n")

    hits = store.search("quantum xylophone")

    assert [p.rel_path for p, _ in hits] == ["concepts/one.md"]


# --- tag:/type: operators (the viewer's query grammar) -------------------------------------


def test_type_operator_filters_exactly(tmp_citadel, seed_page):
    """type:concept keeps only pages of that type (case-insensitive, exact), composed with the
    bare terms — the person page matching the same term is filtered out."""
    seed_page("concepts/roast.md", {"type": "concept", "title": "Roast Levels"}, "About roasting.\n")
    seed_page("persons/roaster.md", {"type": "person", "title": "The Roaster"}, "About roasting.\n")

    hits = store.search("roasting type:concept")

    assert [p.rel_path for p, _ in hits] == ["concepts/roast.md"]


def test_tag_operator_prefix_matches_page_tags(tmp_citadel, seed_page):
    """tag:brew prefix-matches the tag 'brewing' (viewer semantics); a page without a matching
    tag is filtered out even though its text matches the bare term."""
    seed_page("concepts/pour.md", {"type": "concept", "title": "Pour Over", "tags": ["brewing"]}, "Slow water.\n")
    seed_page("concepts/bean.md", {"type": "concept", "title": "Beans"}, "Slow water too.\n")

    hits = store.search("water tag:brew")

    assert [p.rel_path for p, _ in hits] == ["concepts/pour.md"]


def test_operator_only_query_lists_the_filtered_pages(tmp_citadel, seed_page):
    """A query of only operators returns the filtered pages as a flat listing — score 1.0,
    rel_path order — so 'type:person' enumerates the persons folder over MCP/CLI."""
    seed_page("persons/ada.md", {"type": "person", "title": "Ada"}, "A person.\n")
    seed_page("persons/bob.md", {"type": "person", "title": "Bob"}, "A person.\n")
    seed_page("concepts/x.md", {"type": "concept", "title": "X"}, "A concept.\n")

    hits = store.search("type:person")

    assert [(p.rel_path, s) for p, s in hits] == [("persons/ada.md", 1.0), ("persons/bob.md", 1.0)]


def test_unknown_prefix_token_stays_a_literal_term(tmp_citadel, seed_page):
    """Only tag:/type: are operators; any other 'prefix:' token is matched as a literal bare
    term (viewer behavior), tokenized on the colon."""
    seed_page("misc/p.md", {"type": "misc", "title": "Note"}, "The ratio is water:coffee 16 to 1.\n")

    hits = store.search("water:coffee")

    assert [p.rel_path for p, _ in hits] == ["misc/p.md"]


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

    assert [p.rel_path for p, _ in hits] == ["misc/strong.md"]


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
    """A query token that only appears in a page's tags still ranks it — tag data is part of
    the default corpus, not just a filter key."""
    seed_page("misc/p.md", {"type": "misc", "title": "Plain", "tags": ["orbital", "debris"]}, "Nothing.\n")

    hits = store.search("orbital")

    assert [p.rel_path for p, _ in hits] == ["misc/p.md"]


def test_alias_only_term_reaches_the_page(tmp_citadel, seed_page):
    """A page's declared `aliases` are indexed, so a paraphrase that matches only an alias
    still reaches the page (search-lane harvest #69)."""
    seed_page(
        "concepts/alias-hit.md",
        {"type": "concept", "title": "Green Pod Spice", "aliases": ["cardamom"]},
        "Nothing here.\n",
    )

    hits = store.search("cardamom")

    assert [p.rel_path for p, _ in hits] == ["concepts/alias-hit.md"]


# --- case sensitivity ----------------------------------------------------------------------


def test_search_is_case_insensitive(tmp_citadel, seed_page):
    """Query and page text are both lowercased: 'ZEPHYR', 'Zephyr' and 'zephyr' all return the
    same hit with the same score against a capitalized body."""
    seed_page("misc/p.md", {"type": "misc", "title": "Wind"}, "The Zephyr blew.\n")

    scores = []
    for query in ("zephyr", "ZEPHYR", "Zephyr"):
        hits = store.search(query)
        assert [p.rel_path for p, _ in hits] == ["misc/p.md"], query
        scores.append(hits[0][1])
    assert len(set(scores)) == 1


# --- no-match and degenerate queries -------------------------------------------------------


def test_no_match_returns_empty_list(tmp_citadel, seed_page):
    """Zero-score pages are dropped, so a query hitting nothing yields []."""
    seed_page("misc/p.md", {"type": "misc", "title": "Coffee"}, "Beans and water.\n")

    assert store.search("xylophone") == []


def test_empty_and_whitespace_queries_match_nothing(tmp_citadel, seed_page):
    """'' and '   ' produce no terms and no operators, so no page can score."""
    seed_page("misc/p.md", {"type": "misc", "title": "Coffee"}, "Beans and water.\n")

    assert store.search("") == []
    assert store.search("   ") == []


def test_symbol_only_query_falls_back_to_substring(tmp_citadel, seed_page):
    """A term with no alphanumeric content is not FTS-matchable, but the phrase/substring net
    still surfaces a page containing it verbatim, at exactly the 0.5 bonus."""
    seed_page("misc/p.md", {"type": "misc", "title": "Ops"}, "Step A → Step B only.\n")

    hits = store.search("→")

    assert [(p.rel_path, s) for p, s in hits] == [("misc/p.md", 0.5)]


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
    assert score > 0.0


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
    ``Page.tags`` coerces every entry to str, so both indexing and the tag: operator handle it
    instead of raising TypeError."""
    seed_page(
        "misc/budget.md", {"type": "misc", "title": "Budget", "tags": ["finance", 2026]}, "Totals by department.\n"
    )
    seed_page("misc/other.md", {"type": "misc", "title": "Other"}, "Nothing here.\n")

    budget = next(p for p in store.load() if p.rel_path == "misc/budget.md")
    assert budget.tags == ["finance", "2026"]

    assert [p.rel_path for p, _ in store.search("2026")] == ["misc/budget.md"]
    assert [p.rel_path for p, _ in store.search("tag:2026")] == ["misc/budget.md"]


def test_quotes_and_boolean_syntax_are_inert(tmp_citadel, seed_page):
    """A pasted quoted-and-ANDed query is just words to the tokenizer — no query-syntax layer
    exists to break — so it searches its content words normally."""
    seed_page("misc/p.md", {"type": "misc", "title": "Coffee"}, "Beans and water.\n")

    hits = store.search('"beans" AND "water"')

    assert [p.rel_path for p, _ in hits] == ["misc/p.md"]


# --- stemming (recall on paraphrased queries) ----------------------------------------------


def test_stemming_matches_a_paraphrased_verb_form(tmp_citadel, seed_page):
    """The stemming contract: an inflected query form finds a page carrying a different
    inflection of the same word. 'brewing' (query) matches a body that only says 'brew',
    and 'founded' matches a title that says 'founding'."""
    seed_page("concepts/coffee.md", {"type": "concept", "title": "Coffee"}, "You brew it slowly.\n")
    seed_page("concepts/company.md", {"type": "concept", "title": "Founding a Company"}, "History here.\n")

    assert [p.rel_path for p, _ in store.search("brewing")] == ["concepts/coffee.md"]
    assert [p.rel_path for p, _ in store.search("founded")] == ["concepts/company.md"]


def test_stemming_is_symmetric_so_plurals_and_singulars_agree(tmp_citadel, seed_page):
    """'magnets' (query) matches a body that says 'magnet', and 'tables' matches 'table' — the
    same stemmer runs on both sides, so number/inflection no longer blocks a hit."""
    seed_page("concepts/m.md", {"type": "concept", "title": "Physics"}, "A single magnet attracts iron.\n")
    seed_page("concepts/furniture.md", {"type": "concept", "title": "Furniture"}, "Put it on the table.\n")

    assert [p.rel_path for p, _ in store.search("magnets")] == ["concepts/m.md"]
    assert [p.rel_path for p, _ in store.search("tables")] == ["concepts/furniture.md"]


def test_single_pass_stemming_does_not_reach_the_bare_root(tmp_citadel, seed_page):
    """Boundary/characterization: the strip is ONE pass, so ``findings`` stems only to
    ``finding``, NOT to ``find`` — a page that only says ``find`` is not matched. Locks the
    intentional scope so a future move to a deeper stemmer is a conscious change, not a silent
    regression."""
    seed_page("concepts/useful.md", {"type": "concept", "title": "Useful"}, "I find it useful.\n")

    assert store.search("findings") == []
