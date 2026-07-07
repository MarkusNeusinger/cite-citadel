"""Unit tests for store.define_text — the wiki_define / ``citadel define`` glossary lookup: an
Abbreviation-glossary hit, an exact-title/alias page, or the closest search hits as a fallback."""

from __future__ import annotations

from citadel import store


def test_abbreviation_glossary_hit_by_short_form(tmp_citadel, seed_page):
    seed_page(
        "abbreviations/tds.md",
        {"type": "Abbreviation", "title": "TDS — Total Dissolved Solids", "description": "Mineral content of water."},
    )
    out = store.define_text("TDS")

    assert out.startswith("# Definition: TDS")
    assert "## TDS — Total Dissolved Solids" in out
    assert "- Page: abbreviations/tds.md — TDS — Total Dissolved Solids" in out
    assert "- Mineral content of water." in out


def test_abbreviation_matches_expansion_and_is_case_insensitive(tmp_citadel, seed_page):
    seed_page(
        "abbreviations/api.md",
        {"type": "Abbreviation", "title": "API — Application Programming Interface", "description": "d"},
    )
    assert "## API — Application Programming Interface" in store.define_text("api")
    assert "## API — Application Programming Interface" in store.define_text("Application Programming Interface")


def test_abbreviation_matches_an_alias(tmp_citadel, seed_page):
    seed_page(
        "abbreviations/v60.md",
        {"type": "Abbreviation", "title": "V60 — Hario V60", "description": "A cone dripper.", "aliases": ["hario"]},
    )
    assert "## V60 — Hario V60" in store.define_text("hario")


def test_exact_title_page_of_any_type_when_no_abbreviation(tmp_citadel, seed_page):
    seed_page(
        "concepts/brewing.md",
        {"type": "Concept", "title": "Brewing", "description": "Extracting coffee with hot water."},
    )
    out = store.define_text("Brewing")

    assert "## Brewing (Concept)" in out
    assert "- Page: concepts/brewing.md" in out
    assert "- Extracting coffee with hot water." in out


def test_abbreviation_tier_wins_over_a_plain_page_of_the_same_name(tmp_citadel, seed_page):
    """A glossary Abbreviation page is more specific than an ordinary same-named page, so Tier 1
    wins: the exact-title concept is not what ``define`` returns when an abbreviation matches."""
    seed_page("abbreviations/tds.md", {"type": "Abbreviation", "title": "TDS — Total Dissolved Solids"})
    seed_page("concepts/tds.md", {"type": "Concept", "title": "TDS", "description": "A concept page."})

    out = store.define_text("TDS")
    assert "## TDS — Total Dissolved Solids" in out
    assert "(Concept)" not in out


def test_fallback_lists_closest_pages_when_nothing_matches_exactly(tmp_citadel, seed_page):
    seed_page("concepts/espresso.md", {"type": "Concept", "title": "Espresso"}, "A concentrated coffee shot.\n")
    out = store.define_text("espresso shot")

    assert "No glossary entry or exact-title page for 'espresso shot'." in out
    assert "Closest pages:" in out
    assert "- concepts/espresso.md — Espresso" in out


def test_no_match_at_all_omits_the_closest_pages_section(tmp_citadel, seed_page):
    seed_page("concepts/coffee.md", {"type": "Concept", "title": "Coffee"}, "Beans and water.\n")
    out = store.define_text("xylophone")

    assert "No glossary entry or exact-title page for 'xylophone'." in out
    assert "Closest pages:" not in out


def test_empty_term_returns_an_error_string(tmp_citadel):
    assert store.define_text("") == "error: empty term"
    assert store.define_text("   ") == "error: empty term"


def test_multiple_abbreviation_hits_are_ordered_by_short_then_rel_path(tmp_citadel, seed_page):
    """Two Abbreviation pages sharing an alias both surface, ordered deterministically."""
    seed_page("abbreviations/b.md", {"type": "Abbreviation", "title": "BBB — Big Brown Bear", "aliases": ["shared"]})
    seed_page("abbreviations/a.md", {"type": "Abbreviation", "title": "AAA — Ada Amber Ale", "aliases": ["shared"]})
    out = store.define_text("shared")

    assert out.index("## AAA — Ada Amber Ale") < out.index("## BBB — Big Brown Bear")
