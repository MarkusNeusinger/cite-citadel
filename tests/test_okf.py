"""Offline unit tests for the format layer and the required path-safety guard.

No network, no API key. Only stdlib + pyyaml are needed.
"""

import pytest

from okf_wiki import okf


def test_roundtrip():
    """dump(parse(text)) round-trips frontmatter dict + body for a doc with
    code fences, links, tags list."""
    text = (
        "---\n"
        "type: Concept\n"
        "title: Transformer\n"
        "tags:\n"
        "- ml\n"
        "- architecture\n"
        "---\n"
        "# Transformer\n"
        "\n"
        "Uses self-attention.[^s1] See [Karpathy](../entities/andrej-karpathy.md).\n"
        "\n"
        "```python\n"
        "x = attention(q, k, v)\n"
        "```\n"
        "\n"
        "## Sources\n"
        "\n"
        "[^s1]: [raw/attention.md](../../raw/attention.md) — notes\n"
    )
    frontmatter, body = okf.parse(text)
    assert frontmatter == {
        "type": "Concept",
        "title": "Transformer",
        "tags": ["ml", "architecture"],
    }
    assert body.startswith("# Transformer")
    assert "```python" in body
    assert "[Karpathy](../entities/andrej-karpathy.md)" in body
    assert "[^s1]:" in body

    rendered = okf.dump(frontmatter, body)
    frontmatter2, body2 = okf.parse(rendered)
    assert frontmatter2 == frontmatter
    assert body2 == body
    # Body ends with exactly one trailing newline.
    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")


def test_requires_type():
    """okf.validate({}) and okf.validate({'title':'x'}) raise OKFError;
    okf.validate({'type':'Concept'}) does not."""
    with pytest.raises(okf.OKFError):
        okf.validate({})
    with pytest.raises(okf.OKFError):
        okf.validate({"title": "x"})
    with pytest.raises(okf.OKFError):
        okf.validate({"type": ""})
    # Does not raise.
    okf.validate({"type": "Concept"})


def test_preserves_unknown_fields():
    """A frontmatter with an extra field survives parse->dump->parse
    unchanged."""
    text = (
        "---\n"
        "type: Entity\n"
        "title: Acme\n"
        "resource: raw/acme.md\n"
        "custom_field: kept\n"
        "nested:\n"
        "  a: 1\n"
        "  b: 2\n"
        "---\n"
        "Body text.\n"
    )
    frontmatter, body = okf.parse(text)
    assert frontmatter["custom_field"] == "kept"
    assert frontmatter["nested"] == {"a": 1, "b": 2}

    frontmatter2, body2 = okf.parse(okf.dump(frontmatter, body))
    assert frontmatter2 == frontmatter
    assert body2 == body


def test_parse_malformed_frontmatter_is_tolerant():
    """A page with broken YAML frontmatter parses as no-frontmatter instead of
    raising, so one bad hand-edited page can't DoS the whole wiki load."""
    text = "---\ntype: Concept\ntitle: [unclosed\n---\nBody text.\n"
    frontmatter, body = okf.parse(text)
    assert frontmatter == {}
    assert "Body text." in body


def test_safe_join_rejects_traversal(tmp_path):
    """okf.safe_join rejects '..' traversal in any form."""
    with pytest.raises(okf.OKFError):
        okf.safe_join(tmp_path, "../evil.md")
    with pytest.raises(okf.OKFError):
        okf.safe_join(tmp_path, "a/../../b.md")
    with pytest.raises(okf.OKFError):
        okf.safe_join(tmp_path, "")


def test_safe_join_rejects_absolute(tmp_path):
    """okf.safe_join rejects an absolute path."""
    with pytest.raises(okf.OKFError):
        okf.safe_join(tmp_path, "/etc/passwd")


def test_safe_join_accepts_safe_relative(tmp_path):
    """A normal relative path resolves under base."""
    target = okf.safe_join(tmp_path, "concepts/transformer.md")
    assert target == (tmp_path.resolve() / "concepts" / "transformer.md")
    assert target.is_relative_to(tmp_path.resolve())


def test_default_rel_path_routing():
    """Concept->concepts/, Entity->entities/, Abbreviation->abbreviations/, Metric->misc/.
    Case-insensitive on the known types."""
    assert okf.default_rel_path("Concept", "Transformer") == "concepts/transformer.md"
    assert okf.default_rel_path("Entity", "Andrej Karpathy") == "entities/andrej-karpathy.md"
    assert okf.default_rel_path("Metric", "Daily Active Users") == "misc/daily-active-users.md"
    # Abbreviation routes to its own folder; the "ABBR — Full Form" title slugifies cleanly.
    assert (
        okf.default_rel_path("Abbreviation", "TDS — Total Dissolved Solids")
        == "abbreviations/tds-total-dissolved-solids.md"
    )
    # Case-insensitive on the known types.
    assert okf.default_rel_path("concept", "X") == "concepts/x.md"
    assert okf.default_rel_path("ENTITY", "Y") == "entities/y.md"
    assert okf.default_rel_path("abbreviation", "API") == "abbreviations/api.md"
    # Empty title -> 'untitled'.
    assert okf.default_rel_path("Note", "") == "misc/untitled.md"


def test_abbrev_short_long():
    """abbrev_short_long splits 'SHORT — Expansion' titles (em/en-dash or spaced hyphen),
    falls back to the first two aliases, then to (title, description)."""

    def page(frontmatter):
        return okf.Page(rel_path="abbreviations/x.md", frontmatter=frontmatter, body="")

    # Em-dash, en-dash, spaced hyphen all split.
    assert okf.abbrev_short_long(
        page({"type": "Abbreviation", "title": "TDS — Total Dissolved Solids"})
    ) == ("TDS", "Total Dissolved Solids")
    assert okf.abbrev_short_long(
        page({"type": "Abbreviation", "title": "API – Application Programming Interface"})
    ) == ("API", "Application Programming Interface")
    assert okf.abbrev_short_long(
        page({"type": "Abbreviation", "title": "RO - Reverse Osmosis"})
    ) == ("RO", "Reverse Osmosis")
    # No separator in title -> fall back to the first two aliases.
    assert okf.abbrev_short_long(
        page({"type": "Abbreviation", "title": "Reverse Osmosis", "aliases": ["RO", "Reverse Osmosis"]})
    ) == ("RO", "Reverse Osmosis")
    # No separator, no aliases -> (title, description).
    assert okf.abbrev_short_long(
        page({"type": "Abbreviation", "title": "Foo", "description": "Bar baz"})
    ) == ("Foo", "Bar baz")
