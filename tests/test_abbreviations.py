"""Offline tests for the abbreviation features: the generated ``## Abbreviations`` glossary
table in ``index.md`` (store) and the undefined-abbreviation nudge (lint).

No network, no LLM. The index test redirects ``config.*`` at a tmp wiki (same approach as
test_viewer); the lint tests build Page objects directly, since ``lint.lint`` accepts a page
list and needs no filesystem.
"""

from __future__ import annotations

from pathlib import Path

from okf_wiki import config, lint, okf, store


def _wire_tmp_wiki(tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path
    wiki, raw, docs = repo / "wiki", repo / "raw", repo / "docs"
    for d in (wiki, raw, docs):
        d.mkdir(parents=True, exist_ok=True)
    (repo / "SCHEMA.md").write_text("# SCHEMA\n", encoding="utf-8")
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", docs, raising=False)
    return wiki


def _seed(wiki: Path, rel_path: str, frontmatter: dict, body: str = "Body.\n") -> None:
    target = wiki / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def _page(rel_path: str, body: str, **frontmatter) -> okf.Page:
    fm = {"type": "Concept", "title": rel_path, "description": "d", "tags": ["t"]}
    fm.update(frontmatter)
    return okf.Page(rel_path=rel_path, frontmatter=fm, body=body)


# --------------------------------------------------------------------------- index table


def test_index_renders_abbreviations_table(tmp_path, monkeypatch):
    """rebuild_indexes emits a '## Abbreviations' table from every type: Abbreviation page,
    sorted by short form, with both forms and a link to the page."""
    wiki = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed(
        wiki, "abbreviations/tds.md",
        {"type": "Abbreviation", "title": "TDS — Total Dissolved Solids",
         "description": "Brew strength.", "aliases": ["TDS", "Total Dissolved Solids"],
         "tags": ["water"], "resource": "raw/a.md"},
    )
    _seed(
        wiki, "abbreviations/api.md",
        {"type": "Abbreviation", "title": "API — Application Programming Interface",
         "description": "A software interface.", "tags": ["software"], "resource": "raw/a.md"},
    )
    _seed(
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.",
         "tags": ["coffee"], "resource": "raw/a.md"},
    )

    store.rebuild_indexes()
    index = (wiki / "index.md").read_text(encoding="utf-8")

    assert "## Abbreviations" in index
    assert "| Abbreviation | Expansion | Page |" in index
    assert (
        "| TDS | Total Dissolved Solids | [TDS — Total Dissolved Solids](abbreviations/tds.md) |"
        in index
    )
    assert (
        "| API | Application Programming Interface | "
        "[API — Application Programming Interface](abbreviations/api.md) |"
        in index
    )
    # Sorted by short form: API before TDS.
    assert index.index("| API |") < index.index("| TDS |")


def test_index_has_no_abbreviations_table_without_entries(tmp_path, monkeypatch):
    """A wiki with no Abbreviation pages gets no '## Abbreviations' section at all."""
    wiki = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed(
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "description": "A brew.",
         "tags": ["coffee"], "resource": "raw/a.md"},
    )
    store.rebuild_indexes()
    index = (wiki / "index.md").read_text(encoding="utf-8")
    assert "## Abbreviations" not in index


# --------------------------------------------------------------------------- lint nudge


def test_lint_flags_recurring_undefined_abbreviation():
    """An abbreviation used on >=2 pages with no entry and no inline expansion is flagged;
    an inline-expanded one (TDS) and a chemistry formula (CO₂) are not."""
    pages = [
        _page("concepts/a.md", "The KPI dashboard is central. Reverse osmosis (RO) water."),
        _page("concepts/b.md", "Our KPI review matters. Strength is total dissolved solids (TDS)."),
        _page("concepts/c.md", "TDS rises with extraction. CO₂ degassing continues."),
        _page("concepts/d.md", "CO₂ levels fall over time."),
    ]
    report = lint.lint(pages)
    flagged = {abbr for abbr, _n in report.undefined_abbrevs}

    assert ("KPI", 2) in report.undefined_abbrevs   # used on a.md + b.md, never spelled out
    assert "TDS" not in flagged                      # expanded inline as "(TDS)" on b.md
    assert "RO" not in flagged                       # only one page (and expanded anyway)
    assert "CO" not in flagged                       # CO₂ is a formula, not an abbreviation
    # Advisory only — undefined abbreviations never fail the gate.
    assert report.ok()
    assert "KPI (on 2 pages)" in report.render()


def test_lint_abbreviation_entry_suppresses_nudge():
    """Once an abbreviation has an Abbreviation page (by dashed title or by aliases), it is no
    longer reported as undefined."""
    using = [
        _page("concepts/a.md", "The SLA target is high."),
        _page("concepts/b.md", "An SLA breach was logged."),
    ]
    # Without an entry: SLA recurs on 2 pages and is flagged.
    assert "SLA" in {a for a, _ in lint.lint(using).undefined_abbrevs}

    # With a dashed-title entry: suppressed.
    entry = okf.Page(
        rel_path="abbreviations/sla.md",
        frontmatter={"type": "Abbreviation", "title": "SLA — Service Level Agreement",
                     "description": "d", "tags": ["t"], "resource": "raw/a.md"},
        body="A service level agreement.\n",
    )
    assert "SLA" not in {a for a, _ in lint.lint(using + [entry]).undefined_abbrevs}

    # With an aliases-only entry (no dash in title): also suppressed.
    alias_entry = okf.Page(
        rel_path="abbreviations/sla.md",
        frontmatter={"type": "Abbreviation", "title": "Service Level Agreement",
                     "aliases": ["SLA", "Service Level Agreement"],
                     "description": "d", "tags": ["t"], "resource": "raw/a.md"},
        body="A service level agreement.\n",
    )
    assert "SLA" not in {a for a, _ in lint.lint(using + [alias_entry]).undefined_abbrevs}
