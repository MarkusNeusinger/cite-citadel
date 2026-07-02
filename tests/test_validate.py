"""Unit tests for citadel.validate — the per-page link/format/required-field checker."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import errors_of

from citadel import config, okf, validate


@pytest.fixture
def wiki(tmp_path, monkeypatch):
    """A temp repo with wiki/ + raw/ wired into config; returns the wiki dir."""
    repo = tmp_path
    wiki_dir = repo / "wiki"
    raw_dir = repo / "raw"
    for d in (wiki_dir, raw_dir):
        d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki_dir, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw_dir, raising=False)
    (raw_dir / "notes.md").write_text("source\n", encoding="utf-8")
    return wiki_dir


def _seed(wiki_dir: Path, rel_path: str, frontmatter: dict, body: str) -> None:
    target = wiki_dir / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


_GOOD_FM = {
    "type": "Concept",
    "title": "Transformer",
    "description": "self-attention model",
    "tags": ["ml"],
    "resource": "raw/notes.md",
}
_GOOD_BODY = (
    "Transformers use self-attention.[^s1]\n\n"
    "## Sources\n\n"
    "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n"
)


def test_clean_page_has_noerrors_of(wiki):
    issues = validate.validate_page("concepts/transformer.md", dict(_GOOD_FM), _GOOD_BODY)
    assert errors_of(issues) == []


@pytest.mark.parametrize("field", ["type", "title", "description", "tags", "resource"])
def test_missing_required_field_is_error(wiki, field):
    fm = dict(_GOOD_FM)
    del fm[field]
    issues = validate.validate_page("concepts/transformer.md", fm, _GOOD_BODY)
    cats = {i.category for i in errors_of(issues)}
    assert "missing_field" in cats


def test_empty_tags_is_error(wiki):
    fm = dict(_GOOD_FM, tags=[])
    issues = validate.validate_page("concepts/transformer.md", fm, _GOOD_BODY)
    assert any(i.category == "missing_field" and "tags" in i.detail for i in errors_of(issues))


def test_resource_must_point_at_real_file(wiki):
    fm = dict(_GOOD_FM, resource="raw/ghost.md")
    issues = validate.validate_page("concepts/transformer.md", fm, _GOOD_BODY)
    assert any(i.category == "bad_resource" for i in errors_of(issues))


def test_fabricated_citation_is_error(wiki):
    body = "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/ghost.md](../../raw/ghost.md) - missing\n"
    issues = validate.validate_page("concepts/transformer.md", dict(_GOOD_FM), body)
    assert any(i.category == "bad_source" for i in errors_of(issues))


def test_wikilink_is_error(wiki):
    body = _GOOD_BODY.replace("Transformers use self-attention.[^s1]", "See [[Some Page]].[^s1]")
    issues = validate.validate_page("concepts/transformer.md", dict(_GOOD_FM), body)
    assert any(i.category == "wikilink" for i in errors_of(issues))


def test_backslash_link_is_error(wiki):
    body = "See [Other](..\\concepts\\other.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n"
    issues = validate.validate_page("concepts/transformer.md", dict(_GOOD_FM), body)
    assert any(i.category == "backslash_link" for i in errors_of(issues))


def test_embedded_frontmatter_is_error(wiki):
    body = "---\ntype: Concept\ntitle: X\n---\n\n" + _GOOD_BODY
    issues = validate.validate_page("concepts/transformer.md", dict(_GOOD_FM), body)
    assert any(i.category == "embedded_frontmatter" for i in errors_of(issues))


def test_thematic_break_is_not_embedded_frontmatter(wiki):
    """A markdown '---' horizontal rule (not a YAML block) must not be flagged."""
    body = "First section.[^s1]\n\n---\n\nSecond section.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n"
    issues = validate.validate_page("concepts/transformer.md", dict(_GOOD_FM), body)
    assert not any(i.category == "embedded_frontmatter" for i in errors_of(issues))


def test_tool_artifact_in_body_is_error(wiki):
    """Leaked tool-call / transcript tokens in a page body are flagged as an error."""
    body = _GOOD_BODY + "\n</content>\n</invoke>\n"
    issues = validate.validate_page("concepts/transformer.md", dict(_GOOD_FM), body)
    assert any(i.category == "artifact" for i in errors_of(issues))


def test_routing_and_filename_are_advisory(wiki):
    """A page in the wrong folder / with a non-slug filename is advisory, not an error."""
    issues = validate.validate_page("misc/Weird Name.md", dict(_GOOD_FM), _GOOD_BODY)
    assert errors_of(issues) == []
    cats = {i.category for i in issues}
    assert "routing" in cats and "filename" in cats


def test_validate_all_flags_broken_cross_link(wiki):
    _seed(
        wiki,
        "concepts/a.md",
        dict(_GOOD_FM, title="Alpha"),
        "See [Ghost](./ghost.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
    )
    issues = validate.validate_all()
    assert any(i.category == "broken_link" for i in errors_of(issues))
    assert validate.has_errors(issues)


def test_render_issues_is_readable():
    issues = [
        validate.Issue("concepts/a.md", "error", "missing_field", "missing required field: 'tags'"),
        validate.Issue("concepts/a.md", "advisory", "routing", "wrong folder"),
    ]
    out = validate.render_issues(issues)
    assert "concepts/a.md" in out
    assert "[error]" in out and "[advisory]" in out
    assert "1 error(s)" in out
