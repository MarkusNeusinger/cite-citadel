"""Offline tests for the MCP server tool surface (``citadel/server.py``).

FastMCP's ``@mcp.tool()`` decorator registers each function on the server but returns the
ORIGINAL plain function, so the tools are called directly as ``server.wiki_search(...)`` etc. —
no ``.fn`` unwrapping is needed. Each of the ten tools is exercised for its happy path against
a small seeded wiki (``tmp_citadel`` + ``seed_page``) AND for its NEVER-RAISES contract: broken
inputs (missing page, path traversal, empty wiki, undecodable file, a crashing store) must come
back as clear error STRINGS, never as exceptions, so the MCP server stays up. ``wiki_ingest``
runs against the conftest ``fake_agent`` — no real CLI is ever spawned.
"""

from __future__ import annotations

import asyncio

import pytest

from citadel import server, store


# The page a "good" agent session would produce: every strict field present, resource and
# citation pointing at a real raw/ file. Shared by the seeded-wiki fixture and the fake agent.
TRANSFORMER_FM = {
    "type": "Concept",
    "title": "Transformer",
    "description": "Self-attention architecture.",
    "tags": ["ml", "nlp"],
    "resource": "raw/notes.md",
}
TRANSFORMER_BODY = (
    "Transformers use self-attention.[^s1]\n\n"
    "## Sources\n\n"
    "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n"
)

ATTENTION_FM = {
    "type": "Concept",
    "title": "Attention",
    "description": "Weighting mechanism over input tokens.",
    "tags": ["ml"],
    "resource": "raw/notes.md",
}
ATTENTION_BODY = "Attention weights the input tokens.\n"


@pytest.fixture
def seeded_wiki(tmp_citadel, seed_page):
    """A tiny two-page wiki plus the raw source both pages cite, wired into config."""
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    seed_page("concepts/transformer.md", TRANSFORMER_FM, TRANSFORMER_BODY)
    seed_page("concepts/attention.md", ATTENTION_FM, ATTENTION_BODY)
    return tmp_citadel


# --- registration ------------------------------------------------------------------------


def test_all_tools_registered():
    """The FastMCP instance exposes exactly the twelve documented tools (eleven read-only + the
    one mutating wiki_ingest) — a rename or a lost decorator would silently drop a tool from
    every MCP client."""
    tools = asyncio.run(server.mcp.list_tools())
    assert sorted(t.name for t in tools) == [
        "wiki_define",
        "wiki_index",
        "wiki_ingest",
        "wiki_lint",
        "wiki_neighbors",
        "wiki_raw",
        "wiki_read",
        "wiki_search",
        "wiki_sources",
        "wiki_status",
        "wiki_tags",
        "wiki_validate",
    ]


def test_read_only_tools_are_annotated_read_only():
    """Every reader carries the MCP ``readOnlyHint`` behavior annotation and only ``wiki_ingest``
    is left un-read-only — so a client can tell the mutating tool apart before calling it. Skipped
    gracefully if the installed mcp predates tool annotations."""
    if server.ToolAnnotations is None:  # older mcp without annotations -> nothing to assert
        return
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    readers = (
        "wiki_search",
        "wiki_define",
        "wiki_read",
        "wiki_raw",
        "wiki_neighbors",
        "wiki_index",
        "wiki_sources",
        "wiki_tags",
        "wiki_validate",
        "wiki_lint",
        "wiki_status",
    )
    for name in readers:
        assert tools[name].annotations is not None and tools[name].annotations.readOnlyHint is True
    assert tools["wiki_ingest"].annotations.readOnlyHint is False


def test_initialize_instructions_are_set():
    """The server hands orientation guidance up through ``initialize.instructions`` (previously
    null) — clients that surface it get the recommended tool flow for free."""
    assert server.mcp.instructions
    assert "wiki_index" in server.mcp.instructions
    assert "wiki_ingest" in server.mcp.instructions


# --- _snippet ----------------------------------------------------------------------------


def test_snippet_empty_body_is_empty():
    assert server._snippet("query", "") == ""
    assert server._snippet("query", "   \n\t ") == ""


def test_snippet_falls_back_to_head_when_no_token_matches():
    body = "word " * 100
    out = server._snippet("zzz-no-match", body)
    assert out.startswith("word word")
    assert out.endswith("…")  # truncated head
    assert len(out) <= server._SNIPPET_CHARS + 1


def test_snippet_centers_on_first_match_with_ellipses():
    body = ("x " * 200) + "NEEDLE lives here" + (" y" * 200)
    out = server._snippet("needle", body)
    assert "NEEDLE" in out
    assert out.startswith("…") and out.endswith("…")


# --- wiki_search -------------------------------------------------------------------------


def test_search_happy_path(seeded_wiki):
    out = server.wiki_search("transformer")
    assert out.startswith("# Search results for 'transformer'")
    assert "concepts/transformer.md (score" in out
    assert "Transformer" in out
    assert "tags: ml, nlp" in out
    assert "self-attention" in out  # body snippet around the match
    assert "concepts/attention.md" not in out  # unrelated page not returned


def test_search_tag_filter_restricts_scope(seeded_wiki):
    out = server.wiki_search("attention", tag="nlp")
    assert "concepts/transformer.md" in out
    assert "concepts/attention.md" not in out  # matches the query but not the tag


def test_search_unknown_tag_returns_message(seeded_wiki):
    assert server.wiki_search("anything", tag="nope") == "No pages tagged 'nope'."


def test_search_no_matches_returns_message(seeded_wiki):
    out = server.wiki_search("zzz-unfindable")
    assert out == "No matches for 'zzz-unfindable'."


def test_search_no_match_message_names_tag_scope(seeded_wiki):
    out = server.wiki_search("zzz-unfindable", tag="ml")
    assert out == "No matches for 'zzz-unfindable' (tag 'ml')."


def test_search_empty_wiki_returns_message(tmp_citadel):
    out = server.wiki_search("anything")
    assert out == "No matches for 'anything'."


@pytest.mark.parametrize("bad_limit", [0, -1])
def test_search_nonpositive_limit_falls_back_to_default(seeded_wiki, bad_limit):
    """A limit <= 0 (an LLM client miscomputing the argument) must fall back to the default,
    never slice the hit list empty and assert a confident, factually wrong "No matches"."""
    out = server.wiki_search("transformer", limit=bad_limit)
    assert "concepts/transformer.md (score" in out
    assert "No matches" not in out


def test_search_never_raises(tmp_citadel, monkeypatch):
    """NEVER-RAISES contract: a crashing store.search comes back as an error string."""

    def boom(*args, **kwargs):
        raise RuntimeError("index corrupted")

    monkeypatch.setattr(store, "search", boom)
    out = server.wiki_search("anything")
    assert out.startswith("error: search failed:")
    assert "index corrupted" in out


def test_search_tag_branch_never_raises(tmp_citadel, monkeypatch):
    """NEVER-RAISES contract: the tag pre-filter path (store.load) is inside the same guard."""

    def boom(*args, **kwargs):
        raise OSError("disk gone")

    monkeypatch.setattr(store, "load", boom)
    out = server.wiki_search("anything", tag="ml")
    assert out.startswith("error: search failed:")


# --- wiki_define -------------------------------------------------------------------------


def test_define_surfaces_abbreviation_glossary_entry(tmp_citadel, seed_page):
    seed_page(
        "abbreviations/tds.md",
        {"type": "Abbreviation", "title": "TDS — Total Dissolved Solids", "description": "Mineral content of water."},
        "Body.\n",
    )
    out = server.wiki_define("TDS")
    assert out.startswith("# Definition: TDS")
    assert "## TDS — Total Dissolved Solids" in out
    assert "- Page: abbreviations/tds.md — TDS — Total Dissolved Solids" in out
    assert "- Mineral content of water." in out


def test_define_is_case_insensitive_and_matches_expansion(tmp_citadel, seed_page):
    seed_page(
        "abbreviations/tds.md",
        {"type": "Abbreviation", "title": "TDS — Total Dissolved Solids", "description": "d"},
        "Body.\n",
    )
    assert "## TDS — Total Dissolved Solids" in server.wiki_define("tds")
    assert "## TDS — Total Dissolved Solids" in server.wiki_define("total dissolved solids")


def test_define_falls_back_to_exact_title_page(tmp_citadel, seed_page):
    seed_page(
        "concepts/brewing.md",
        {"type": "Concept", "title": "Brewing", "description": "Extracting coffee with hot water."},
        "Body.\n",
    )
    out = server.wiki_define("Brewing")
    assert "## Brewing (Concept)" in out
    assert "- Page: concepts/brewing.md" in out
    assert "- Extracting coffee with hot water." in out


def test_define_fallback_lists_closest_pages(tmp_citadel, seed_page):
    seed_page("concepts/espresso.md", {"type": "Concept", "title": "Espresso"}, "A concentrated coffee shot.\n")
    out = server.wiki_define("espresso shot")
    assert "No glossary entry or exact-title page for 'espresso shot'." in out
    assert "Closest pages:" in out
    assert "- concepts/espresso.md — Espresso" in out


def test_define_never_raises(tmp_citadel, monkeypatch):
    """NEVER-RAISES contract: a crashing store.define_text comes back as an error string."""

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(store, "define_text", boom)
    out = server.wiki_define("anything")
    assert out.startswith("error: could not define 'anything':")


# --- wiki_tags ---------------------------------------------------------------------------


def test_tags_lists_all_tags_and_pages(seeded_wiki):
    out = server.wiki_tags()
    assert out.startswith("# Tags")
    assert "## ml (2)" in out
    assert "## nlp (1)" in out
    assert "- [Transformer](concepts/transformer.md) — Self-attention architecture." in out
    assert "- [Attention](concepts/attention.md) — Weighting mechanism over input tokens." in out


def test_tags_single_tag_is_case_insensitive(seeded_wiki):
    out = server.wiki_tags("NLP")
    assert out.startswith("# nlp (1)")
    assert "concepts/transformer.md" in out
    assert "concepts/attention.md" not in out


def test_tags_unknown_tag_returns_message(seeded_wiki):
    assert server.wiki_tags("nope") == "No pages tagged 'nope'."


def test_tags_empty_wiki_returns_message(tmp_citadel):
    assert server.wiki_tags() == "No tags yet."


def test_tags_never_raises(tmp_citadel, monkeypatch):
    """NEVER-RAISES contract: a crashing tag_catalog comes back as an error string."""

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(store, "tag_catalog", boom)
    out = server.wiki_tags()
    assert out.startswith("error: could not read tags:")


# --- wiki_read ---------------------------------------------------------------------------


def test_read_returns_full_page_text(seeded_wiki):
    out = server.wiki_read("concepts/transformer.md")
    assert out.startswith("---\n")
    assert "type: Concept" in out
    assert "title: Transformer" in out
    assert "self-attention.[^s1]" in out
    assert "## Sources" in out


def test_read_not_found_returns_error_string(seeded_wiki):
    out = server.wiki_read("concepts/missing.md")
    assert out == "error: page not found: 'concepts/missing.md'"


@pytest.mark.parametrize("bad", ["../x.md", "concepts/../../x.md", "/etc/passwd", ""])
def test_read_rejects_path_traversal(seeded_wiki, bad):
    """Pins the okf.safe_join guard on wiki_read: a traversal/absolute/empty rel_path must come
    back as an 'unsafe path' error STRING — it must neither raise nor read outside the wiki. The
    prefix appears exactly once (the tool used to wrap the already-self-describing OKFError text
    into a doubled "unsafe path: unsafe path: …")."""
    out = server.wiki_read(bad)
    assert out.startswith("error: unsafe path:")
    assert out.count("unsafe path:") == 1


def test_read_normalizes_backslash_rel_path(seeded_wiki):
    """A Windows-style rel_path resolves like its POSIX twin — wiki_validate already normalized
    backslashes while wiki_read 404'd on the same page."""
    out = server.wiki_read("concepts\\transformer.md")
    assert "title: Transformer" in out


def test_read_generated_index_is_verbatim(seeded_wiki):
    """A generated, frontmatter-less file (index.md) comes back byte-for-byte — the okf.dump
    re-serialization used to prepend a spurious empty `---\\n{}\\n---` frontmatter block,
    contradicting the tool's "verbatim" contract."""
    store.rebuild_indexes()
    on_disk = seeded_wiki.index_path.read_text(encoding="utf-8")
    out = server.wiki_read("index.md")
    assert out == on_disk
    assert "{}" not in out


def test_read_strips_a_leading_bom(seeded_wiki):
    """A BOM'd page (common on Windows) must not leak a \\ufeff before its frontmatter into
    MCP/CLI output — read_page_text mirrors okf.parse's encoding-artifact stripping."""
    path = seeded_wiki.wiki / "misc" / "bommed.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf---\ntype: Note\ntitle: Bommed\n---\n\nBody.\n")
    out = server.wiki_read("misc/bommed.md")
    assert not out.startswith("\ufeff")
    assert out.startswith("---\n")


def test_read_undecodable_file_returns_error_string(seeded_wiki):
    """NEVER-RAISES contract: a non-UTF-8 file inside the wiki (e.g. dropped there by hand)
    surfaces as an error string, not a UnicodeDecodeError."""
    target = seeded_wiki.wiki / "concepts" / "binary.md"
    target.write_bytes(b"\xff\xfe\x00 not utf-8")
    out = server.wiki_read("concepts/binary.md")
    assert out.startswith("error: could not read 'concepts/binary.md':")


# --- wiki_raw ----------------------------------------------------------------------------


def test_raw_reads_a_cited_source_slice(tmp_citadel):
    """wiki_raw resolves a cited source and its locator: a line slice comes back line-numbered."""
    from citadel import config, manifest

    (tmp_citadel.raw / "notes.md").write_text("hello\nworld\n", encoding="utf-8")
    key = config.rel_or_abs_posix(tmp_citadel.raw / "notes.md")
    manifest.save({key: manifest.make_entry("aa" * 32)})

    out = server.wiki_raw(key, "lines 1-1")
    assert "1 | hello" in out
    assert "world" not in out


def test_raw_uncited_key_returns_error_string(tmp_citadel):
    """NEVER-RAISES contract: a key the wiki does not cite comes back as an error string (the
    provenance gate holds), not a SourceError out of the tool."""
    out = server.wiki_raw("raw/nope.md")
    assert out.startswith("error:") and "not a source the wiki cites" in out


def test_raw_unresolvable_locator_returns_error_string(tmp_citadel):
    """A locator that parses to nothing offline-resolvable is an ERROR STRING like every other bad
    locator — it used to silently dump the whole source with only a header note, which an MCP
    client checking the 'error:' prefix could not detect."""
    from citadel import config, manifest

    (tmp_citadel.raw / "notes.md").write_text("hello\nworld\n", encoding="utf-8")
    key = config.rel_or_abs_posix(tmp_citadel.raw / "notes.md")
    manifest.save({key: manifest.make_entry("aa" * 32)})

    out = server.wiki_raw(key, "gibberish locator")
    assert out.startswith("error:") and "not offline-resolvable" in out
    assert "hello" not in out  # no silent whole-source fallback


# --- wiki_neighbors ----------------------------------------------------------------------


def test_neighbors_lists_the_three_sections(seeded_wiki):
    out = server.wiki_neighbors("concepts/transformer.md")
    assert out.startswith("# Neighbors of concepts/transformer.md")
    assert "## Links out" in out and "## Linked from" in out and "## Cites sources" in out
    assert "- raw/notes.md — 1 citation" in out  # the source the page cites, keyed for wiki_raw


def test_neighbors_not_found_returns_error_string(seeded_wiki):
    """NEVER-RAISES contract: a missing page comes back as an error string."""
    assert server.wiki_neighbors("concepts/nope.md").startswith("error: page not found:")


def test_neighbors_unsafe_path_error_is_not_doubled(seeded_wiki):
    """A traversal rel_path errors with a single 'unsafe path:' prefix (same B11 fix as read)."""
    out = server.wiki_neighbors("../x.md")
    assert out.startswith("error: unsafe path:")
    assert out.count("unsafe path:") == 1


def test_neighbors_normalizes_backslash_rel_path(seeded_wiki):
    """A Windows-style rel_path resolves like its POSIX twin, matching wiki_read/wiki_validate."""
    out = server.wiki_neighbors("concepts\\transformer.md")
    assert out.startswith("# Neighbors of concepts/transformer.md")


# --- wiki_index --------------------------------------------------------------------------


def test_index_returns_generated_catalog(seeded_wiki):
    store.rebuild_indexes()
    out = server.wiki_index()
    assert "transformer.md" in out
    assert "attention.md" in out


def test_index_missing_returns_hint(tmp_citadel):
    assert server.wiki_index() == "error: wiki index not found (run `citadel ingest` first)."


def test_index_unreadable_returns_error_string(tmp_citadel):
    """NEVER-RAISES contract: an index path that exists but cannot be read as a file (here a
    directory) surfaces as an error string."""
    tmp_citadel.index_path.mkdir()
    out = server.wiki_index()
    assert out.startswith("error: could not read index:")


# --- wiki_sources ------------------------------------------------------------------------


def test_sources_returns_catalog_text(seeded_wiki):
    catalog = seeded_wiki.wiki / "sources" / "index.md"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    catalog.write_text("# Sources\n\n| raw/notes.md | model-x |\n", encoding="utf-8")
    out = server.wiki_sources()
    assert out.startswith("# Sources")
    assert "raw/notes.md" in out


def test_sources_missing_returns_hint(tmp_citadel):
    assert server.wiki_sources() == "No sources catalog yet (run `citadel ingest` first)."


def test_sources_unreadable_returns_error_string(tmp_citadel):
    """NEVER-RAISES contract: a sources/index.md that exists but cannot be read as a file
    (here a directory) surfaces as an error string."""
    (tmp_citadel.wiki / "sources" / "index.md").mkdir(parents=True)
    out = server.wiki_sources()
    assert out.startswith("error: could not read sources catalog:")


# --- wiki_validate -----------------------------------------------------------------------


def test_validate_clean_wiki_reports_ok(seeded_wiki):
    assert server.wiki_validate() == "OK — no validation issues."


def test_validate_reports_issues_as_text(seeded_wiki, seed_page):
    seed_page("misc/bad.md", {"type": "Note", "title": "Bad"}, "No fields.\n")
    out = server.wiki_validate()
    assert "misc/bad.md:" in out
    assert "[error] missing_field" in out
    assert "error(s)" in out


def test_validate_filters_to_one_page(seeded_wiki, seed_page):
    seed_page("misc/bad.md", {"type": "Note", "title": "Bad"}, "No fields.\n")
    # The clean page filters to zero issues even while the wiki as a whole has errors.
    assert server.wiki_validate("concepts/transformer.md") == "OK — no validation issues."
    out = server.wiki_validate("misc/bad.md")
    assert "misc/bad.md:" in out and "[error]" in out
    assert "concepts/" not in out


def test_validate_normalizes_backslash_rel_path(seeded_wiki, seed_page):
    """A Windows-style rel_path filter ('misc\\bad.md') matches the POSIX page identity."""
    seed_page("misc/bad.md", {"type": "Note", "title": "Bad"}, "No fields.\n")
    out = server.wiki_validate("misc\\bad.md")
    assert "misc/bad.md:" in out and "[error]" in out


def test_validate_unknown_page_is_an_error(seeded_wiki):
    """A rel_path that names no page must be an error string, never a clean "OK" — a page with
    zero issues and a typo'd path were previously indistinguishable (false green)."""
    assert server.wiki_validate("concepts/missing.md") == "error: no such page: concepts/missing.md"


def test_validate_generated_file_is_named_not_validated(seeded_wiki):
    # index.md exists on disk but is generated — excluded from validation, so name that.
    (seeded_wiki.wiki / "index.md").write_text("# Index\n", encoding="utf-8")
    out = server.wiki_validate("index.md")
    assert out.startswith("error: not a validated page: index.md")


def test_validate_traversal_path_reports_no_such_page(seeded_wiki):
    # An escaping path is never probed on disk (safe_join rejects it) — plain not-found error.
    assert server.wiki_validate("../../etc/passwd") == "error: no such page: ../../etc/passwd"


def test_validate_never_raises(tmp_citadel, monkeypatch):
    """NEVER-RAISES contract: a crashing validator comes back as an error string."""
    from citadel import validate

    def boom(*args, **kwargs):
        raise RuntimeError("validator exploded")

    monkeypatch.setattr(validate, "validate_all", boom)
    out = server.wiki_validate()
    assert out.startswith("error: validation failed:")
    assert "validator exploded" in out


# --- wiki_ingest -------------------------------------------------------------------------


def test_ingest_happy_path_with_fake_agent(tmp_citadel, fake_agent):
    """wiki_ingest runs a real ingest end-to-end (staging, diff, validate, promote) with the
    agent faked, and returns the rendered IngestReport text."""
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    agent = fake_agent({"concepts/transformer.md": (TRANSFORMER_FM, TRANSFORMER_BODY)})

    out = server.wiki_ingest()

    assert agent.calls == [("raw/notes.md", "ingest")]
    assert "Ingest complete: 1 processed" in out
    assert "0 errors." in out
    assert "raw/notes.md" in out
    assert "concepts/transformer.md" in out
    # The report reflects a real promotion onto the live wiki.
    assert (tmp_citadel.wiki / "concepts" / "transformer.md").exists()


def test_ingest_agent_failure_lands_in_report_not_exception(tmp_citadel, fake_agent):
    """NEVER-RAISES contract: a failing agent session (missing CLI, timeout, crash) surfaces
    as a per-source error INSIDE the returned report text, and nothing is promoted."""
    (tmp_citadel.raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    fake_agent(error=RuntimeError("agent exploded"))

    out = server.wiki_ingest()

    assert "1 errors." in out
    assert "Errors:" in out
    assert "agent exploded" in out
    # Rollback: the live wiki is untouched.
    assert not (tmp_citadel.wiki / "concepts" / "transformer.md").exists()


def test_ingest_runtime_error_becomes_error_string(tmp_citadel, monkeypatch):
    from citadel import ingest

    def boom(*args, **kwargs):
        raise RuntimeError("agent CLI 'claude' not found")

    monkeypatch.setattr(ingest, "ingest", boom)
    assert server.wiki_ingest() == "error: agent CLI 'claude' not found"


def test_ingest_generic_error_becomes_error_string(tmp_citadel, monkeypatch):
    from citadel import ingest

    def boom(*args, **kwargs):
        raise ValueError("kaboom")

    monkeypatch.setattr(ingest, "ingest", boom)
    out = server.wiki_ingest()
    assert out == "error: ingest failed: kaboom"


# --- wiki_lint ----------------------------------------------------------------------------


def test_lint_returns_report_text(seeded_wiki):
    out = server.wiki_lint()
    assert "Lint report" in out


def test_lint_stale_days_parameter_reaches_lint(tmp_citadel, monkeypatch):
    """``stale_days`` plumbs through to lint.lint — the knob CLI users had via --stale-days but
    MCP clients could never tune."""
    from citadel import lint as lint_mod

    seen = {}

    def fake_lint(pages=None, stale_days=365):
        seen["stale_days"] = stale_days
        return lint_mod.LintReport()

    monkeypatch.setattr(lint_mod, "lint", fake_lint)
    server.wiki_lint(stale_days=30)
    assert seen["stale_days"] == 30
    server.wiki_lint()
    assert seen["stale_days"] == 365  # documented default, matching the CLI's


def test_lint_never_raises(tmp_citadel, monkeypatch):
    """NEVER-RAISES contract: a crashing lint comes back as an error string."""
    from citadel import lint as lint_mod

    def boom(*args, **kwargs):
        raise RuntimeError("lint exploded")

    monkeypatch.setattr(lint_mod, "lint", boom)
    out = server.wiki_lint()
    assert out.startswith("error: lint failed:")


# --- wiki_status --------------------------------------------------------------------------


def test_status_reports_per_source_buckets(tmp_citadel):
    """wiki_status renders the same per-source state table as ``citadel status``: an ingested
    (manifested) source and a pending on-disk one each land in their bucket."""
    from citadel import config, manifest

    (tmp_citadel.raw / "done.md").write_text("done\n", encoding="utf-8")
    (tmp_citadel.raw / "todo.md").write_text("todo\n", encoding="utf-8")
    key = config.rel_or_abs_posix(tmp_citadel.raw / "done.md")
    manifest.save({key: manifest.make_entry("aa" * 32, model="claude:sonnet")})

    out = server.wiki_status()

    assert out.startswith("Corpus status")
    assert "Ingested (1)" in out and key in out
    assert "Pending (1)" in out and "raw/todo.md" in out


def test_status_never_raises(tmp_citadel, monkeypatch):
    """NEVER-RAISES contract: a crashing status build comes back as an error string."""
    from citadel import status

    def boom(*args, **kwargs):
        raise RuntimeError("status exploded")

    monkeypatch.setattr(status, "build_status", boom)
    out = server.wiki_status()
    assert out.startswith("error: could not read corpus status:")
    assert "status exploded" in out


def test_search_offset_pages_past_the_first_results(seeded_wiki):
    """offset skips the first N ranked hits, so results beyond one call's limit stay reachable."""
    first = server.wiki_search("attention", limit=1)
    second = server.wiki_search("attention", limit=1, offset=1)
    assert "offset 1" in second
    top_hit = next(line for line in first.splitlines() if line.startswith("## "))
    next_hit = next(line for line in second.splitlines() if line.startswith("## "))
    assert top_hit != next_hit  # genuinely the next ranked page, not a repeat
    assert server.wiki_search("attention", limit=1, offset=99) == "No more matches for 'attention' at offset 99."


def test_search_limit_is_clamped(seeded_wiki, monkeypatch):
    """A huge limit cannot dump the whole ranked corpus in one call."""
    seen: dict[str, int] = {}
    real_search = store.search

    def spy(query, pages=None, limit=8):
        seen["limit"] = limit
        return real_search(query, pages=pages, limit=limit)

    monkeypatch.setattr(store, "search", spy)
    server.wiki_search("attention", limit=100_000)
    assert seen["limit"] == server._SEARCH_LIMIT_MAX


def test_read_caps_a_pathological_page(tmp_citadel, seed_page):
    """wiki_read truncates a huge page at a line boundary with a re-call hint; max_chars=0 lifts
    the cap."""
    big_body = "\n".join(f"line {i} with some padding text" for i in range(2000))
    seed_page("concepts/huge.md", {"type": "Concept", "title": "Huge"}, big_body + "\n")
    out = server.wiki_read("concepts/huge.md")
    assert len(out) <= server._READ_MAX_CHARS + 120
    assert "truncated at 20000 chars" in out
    full = server.wiki_read("concepts/huge.md", max_chars=0)
    assert "truncated" not in full and full.rstrip().endswith("line 1999 with some padding text")
