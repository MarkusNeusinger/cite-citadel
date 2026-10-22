"""#166 (offline): abbreviation and missing-citation noise cut, `[^llmN]` definitions enforced."""

from __future__ import annotations

import pytest

from citadel import config, curate, lint, validate
from citadel.okf import Page


def _page(body: str) -> Page:
    return Page(rel_path="concepts/x.md", frontmatter={"type": "Concept", "title": "X"}, body=body)


# --- (a) abbreviations -------------------------------------------------------------------------


def test_link_targets_are_not_scanned_but_link_text_is():
    assert lint._abbrev_token_uses("[docs](https://example.com/API/v2) and [mail](../../raw/AW-minutes.md)\n") == set()
    assert "KPI" in lint._abbrev_token_uses("[KPI report](kpi.md)\n")


@pytest.mark.parametrize("text", ["AW: Termin", "WG: Termin", "Muster AG baut", "16 GB frei", "EUR 500", "500 EUR"])
def test_context_gated_tokens_are_not_candidates(text):
    assert lint._abbrev_token_uses(text + "\n") == set()


@pytest.mark.parametrize("text", ["the WG met", "the AG decided"])
def test_the_same_tokens_out_of_context_still_count(text):
    assert lint._abbrev_token_uses(text + "\n")


def test_default_stoplist_keeps_the_graded_domain_terms_out():
    assert not {"KPI", "SLA", "ESB", "FAQ", "EY", "KSB", "TCO", "HX", "PV"} & set(config._DEFAULT_ABBREV_STOPLIST)


@pytest.mark.parametrize(
    ("value", "expect_in", "expect_out"),
    [
        ("", {"IT", "API"}, set()),
        ("FOO,BAR", {"FOO", "BAR"}, {"IT"}),
        ("+FOO", {"IT", "FOO"}, set()),
        ("+foo,+bar", {"IT", "FOO", "BAR"}, set()),
    ],
)
def test_abbrev_stoplist_knob(monkeypatch, value, expect_in, expect_out):
    monkeypatch.setenv("CITADEL_ABBREV_STOPLIST", value)
    resolved = set(config._resolve_abbrev_stoplist())
    assert expect_in <= resolved and not (expect_out & resolved)


def test_a_lowercase_stoplist_entry_still_matches(monkeypatch):
    monkeypatch.setattr(config, "ABBREV_STOPLIST", ["kpi"])
    assert "KPI" not in lint._abbrev_token_uses("the KPI moved\n")


# --- (b) missing citations ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "Die Anlage läuft seit dem 1. März 2019.\n",
        "Die Anlage braucht Pflege, z. B. die Wartung.\n",
        "Die Messung leitete Dr. Muster.\n",
        "J. Smith founded the guild.\n",
        "Das Projekt hat mehrere Phasen. Dazu gehören:\n\n- Phase eins.[^s1]\n- Phase zwei.[^s1]\n",
        "Details siehe [A](a.md). Weitere unter [B](b.md).\n",
        "This page collects the details of the 2019 survey. See the yearly pages below.\n",
    ],
)
def test_no_longer_flagged(body):
    assert lint._missing_cite_preview(_page(body)) is None


@pytest.mark.parametrize(
    "body",
    [
        "The kiln was built in 1990. It burned down in 1995.\n",
        "[Alice](a.md) founded [Acme](b.md). She ran it until 1998.\n",
        "See und Fluss liegen nah. Der See ist tief.\n",
        "Coffee is grown in the tropics. The plant is dominated by two species: Arabica and Robusta.\n\n- Arabica.[^s1]\n",
    ],
)
def test_still_flagged(body):
    assert lint._missing_cite_preview(_page(body)) is not None


# --- (c) [^llmN] -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("A model fact.[^llm1]\n\n## Sources\n\n", "[^llm1] used but undefined"),
        ("A model fact.[^llm1]\n\n## Sources\n\n[^llm1]:\n", "[^llm1]: empty note"),
        ("A model fact.[^llm1]\n\n## Sources\n\n[^llm1]: LLM\n", "[^llm1]: empty note"),
        ("A model fact.[^llm1]\n\n## Sources\n\n[^llm1]: LLM - (added 2026-06-21)\n", "[^llm1]: empty note"),
    ],
)
def test_llm_markers_must_be_defined_with_a_note(tmp_citadel, body, expected):
    assert validate.source_issues("concepts/x.md", body) == [expected]


def test_the_schema_template_passes(tmp_citadel):
    body = (
        "A model fact.[^llm1]\n\n## Sources\n\n[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-21)\n"
    )
    assert validate.source_issues("concepts/x.md", body) == []


def test_an_empty_llm_note_fails_check_lint_and_plans_curate(tmp_citadel, seed_page):
    seed_page(
        "concepts/x.md",
        {"type": "Concept", "title": "X", "description": "d", "tags": ["t"], "resource": "raw/x.md"},
        "A model fact.[^llm1]\n\n## Sources\n\n[^llm1]: LLM\n",
    )
    (tmp_citadel.raw / "x.md").write_text("x\n", encoding="utf-8")
    assert any(i.category == "bad_source" for i in validate.validate_all() if i.severity == "error")
    assert not lint.lint().ok()
    plan = curate.build_plan()
    assert curate.REASON_BAD_SOURCE in {r for item in plan.items for r in item.reasons}


def test_source_definitions_still_skip_llm_notes():
    from citadel import grammar

    assert list(grammar.source_definitions("## Sources\n\n[^llm1]: LLM - note\n")) == []


def test_a_session_adding_an_empty_llm_note_fails_the_source(tmp_citadel, fake_agent):
    from citadel import ingest

    (tmp_citadel.raw / "a.md").write_text("a\n", encoding="utf-8")

    def effect(rel_key, **kw):
        (config.wiki_dir() / "misc").mkdir(parents=True, exist_ok=True)
        (config.wiki_dir() / "misc" / "a.md").write_text(
            "---\ntype: Thing\ntitle: A\ndescription: d\ntags: [t]\nresource: raw/a.md\n---\n"
            "A fact.[^s1] A model aside.[^llm1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n[^llm1]: LLM\n",
            encoding="utf-8",
        )

    fake_agent(side_effect=effect)
    report = ingest.ingest()
    assert report.errors and not (tmp_citadel.wiki / "misc" / "a.md").exists()


def test_bad_source_guidance_mentions_llm_notes():
    assert "[^llmN]" in curate._REASON_GUIDANCE[curate.REASON_BAD_SOURCE]
