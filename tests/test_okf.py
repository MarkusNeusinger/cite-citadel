"""Offline unit tests for the format layer and the required path-safety guard.

No network, no API key. Only stdlib + pyyaml are needed.
"""

import pytest

from citadel import okf


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
    assert frontmatter == {"type": "Concept", "title": "Transformer", "tags": ["ml", "architecture"]}
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


def test_parse_tolerates_leading_bom_and_whitespace():
    """A leading UTF-8 BOM (common when a file is written on Windows) or a blank line
    above the opening fence must NOT hide the frontmatter. Either one used to make the page
    parse as having no frontmatter so every required field read as missing — the symptom
    behind a whole ingest run failing with 'missing required field' on every page."""
    expected = {"type": "Concept", "title": "Test", "description": "d", "tags": ["x"], "resource": "raw/notes.md"}
    base = "---\ntype: Concept\ntitle: Test\ndescription: d\ntags:\n- x\nresource: raw/notes.md\n---\nBody text.\n"
    # BOM, leading blank lines, leading spaces, CRLF newlines, and combinations all parse
    # to the same frontmatter, and the BOM/whitespace never leaks into the body.
    for label, text in {
        "bom": "\ufeff" + base,
        "blank_line": "\n" + base,
        "spaces": "   " + base,
        "crlf": base.replace("\n", "\r\n"),
        "bom_crlf": "\ufeff" + base.replace("\n", "\r\n"),
        "bom_then_blank": "\ufeff\n\n" + base,
    }.items():
        frontmatter, body = okf.parse(text)
        assert frontmatter == expected, label
        assert body.lstrip().startswith("Body text."), label
        assert "\ufeff" not in body, label


def test_parse_bom_page_roundtrips_clean():
    """Parsing a BOM-prefixed page then dumping it yields canonical OKF with NO BOM, so the
    re-stamp ingest performs after validation normalizes the file (a second parse is stable)."""
    frontmatter, body = okf.parse("\ufeff---\ntype: Concept\ntitle: T\n---\nBody.\n")
    rendered = okf.dump(frontmatter, body)
    assert not rendered.startswith("\ufeff")
    assert rendered.startswith("---\n")
    frontmatter2, body2 = okf.parse(rendered)
    assert frontmatter2 == frontmatter
    assert body2 == body


def test_parse_thematic_break_is_not_frontmatter():
    """A body whose content is a markdown thematic break (or starts with one) must still parse
    to an EMPTY dict — the embedded-frontmatter validator depends on this to avoid false
    positives, and the BOM/whitespace tolerance must not change it."""
    assert okf.parse("Some text.\n\n---\n\nMore text.\n")[0] == {}
    assert okf.parse("---\n\nJust a horizontal rule then prose.\n")[0] == {}
    assert okf.parse("\ufeffSome text.\n\n---\n\nMore.\n")[0] == {}


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
    """Each kind routes to its own folder; unknown types -> misc/. Case-insensitive."""
    assert okf.default_rel_path("Concept", "Transformer") == "concepts/transformer.md"
    # The kinds split out of the old overloaded Entity each get their own folder.
    assert okf.default_rel_path("Object", "Engine") == "objects/engine.md"
    assert okf.default_rel_path("Person", "Andrej Karpathy") == "persons/andrej-karpathy.md"
    assert okf.default_rel_path("Organization", "ACME Corp") == "organizations/acme-corp.md"
    assert okf.default_rel_path("Project", "Acme Migration") == "projects/acme-migration.md"
    assert okf.default_rel_path("System", "Postgres") == "systems/postgres.md"
    assert okf.default_rel_path("Metric", "Daily Active Users") == "misc/daily-active-users.md"
    # Abbreviation routes to its own folder; the "ABBR — Full Form" title slugifies cleanly.
    assert (
        okf.default_rel_path("Abbreviation", "TDS — Total Dissolved Solids")
        == "abbreviations/tds-total-dissolved-solids.md"
    )
    # Case-insensitive on the known types; British 'Organisation' aliases to organizations/.
    assert okf.default_rel_path("concept", "X") == "concepts/x.md"
    assert okf.default_rel_path("object", "Y") == "objects/y.md"
    assert okf.default_rel_path("organisation", "Z") == "organizations/z.md"
    assert okf.default_rel_path("abbreviation", "API") == "abbreviations/api.md"
    # Entity is kept as a tolerated legacy alias so old pages keep working.
    assert okf.default_rel_path("Entity", "Legacy Thing") == "entities/legacy-thing.md"
    assert okf.default_rel_path("ENTITY", "Y") == "entities/y.md"
    # Empty title -> 'untitled'.
    assert okf.default_rel_path("Note", "") == "misc/untitled.md"


def test_slugify_transliterates_accented_titles():
    """Accented Latin letters ASCII-fold instead of being dropped (they previously vanished, so a
    'Café' page slugged to 'caf' and mismatched the agent's 'cafe.md')."""
    assert okf.slugify("Caffè Aurora") == "caffe-aurora"
    assert okf.slugify("Café") == "cafe"
    assert okf.slugify("Zürcher") == "zurcher"
    assert okf.slugify("naïve") == "naive"
    assert okf.slugify("José María") == "jose-maria"
    # Letters with no NFKD ASCII decomposition get an explicit transliteration.
    assert okf.slugify("Straße") == "strasse"
    assert okf.slugify("Œuvre") == "oeuvre"
    assert okf.slugify("Æther") == "aether"
    assert okf.slugify("Þórr") == "thorr"
    # ASCII titles are unchanged; a title with nothing ASCII-foldable falls back to 'untitled'.
    assert okf.slugify("Plain Title 3") == "plain-title-3"
    assert okf.slugify("北京") == "untitled"
    assert okf.slugify("") == "untitled"


def test_abbrev_short_long():
    """abbrev_short_long splits 'SHORT — Expansion' titles (em/en-dash or spaced hyphen),
    falls back to the first two aliases, then to (title, description)."""

    def page(frontmatter):
        return okf.Page(rel_path="abbreviations/x.md", frontmatter=frontmatter, body="")

    # Em-dash, en-dash, spaced hyphen all split.
    assert okf.abbrev_short_long(page({"type": "Abbreviation", "title": "TDS — Total Dissolved Solids"})) == (
        "TDS",
        "Total Dissolved Solids",
    )
    assert okf.abbrev_short_long(
        page({"type": "Abbreviation", "title": "API – Application Programming Interface"})
    ) == ("API", "Application Programming Interface")
    assert okf.abbrev_short_long(page({"type": "Abbreviation", "title": "RO - Reverse Osmosis"})) == (
        "RO",
        "Reverse Osmosis",
    )
    # No separator in title -> fall back to the first two aliases.
    assert okf.abbrev_short_long(
        page({"type": "Abbreviation", "title": "Reverse Osmosis", "aliases": ["RO", "Reverse Osmosis"]})
    ) == ("RO", "Reverse Osmosis")
    # No separator, no aliases -> (title, description).
    assert okf.abbrev_short_long(page({"type": "Abbreviation", "title": "Foo", "description": "Bar baz"})) == (
        "Foo",
        "Bar baz",
    )
