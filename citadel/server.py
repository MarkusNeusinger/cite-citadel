"""MCP stdio server exposing the OKF wiki to AI clients.

A FastMCP instance over stdio with ten tools: nine read-only
(wiki_search / wiki_read / wiki_raw / wiki_neighbors / wiki_index / wiki_sources / wiki_tags /
wiki_validate / wiki_lint) and one mutating (wiki_ingest). Every tool returns a plain markdown/text
string, which an LLM consumes best, and NEVER raises out of the tool: not-found / unsafe-path /
missing-or-unusable-LLM-CLI conditions are returned as clear error strings
so the server stays up.

Each tool carries MCP **behavior annotations** (``readOnlyHint`` / ``destructiveHint`` /
``idempotentHint`` / ``openWorldHint``) so a client can reason about a tool before calling it: the
nine readers are read-only, and only ``wiki_ingest`` mutates (non-destructive, idempotent via the
sha manifest, and open-world because it spawns your external coding-agent CLI). If the installed
``mcp`` predates tool annotations, they are silently omitted — a client that ignores hints is
unaffected.

Run via ``citadel serve`` or ``python -m citadel.server``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP


try:  # tool behavior annotations are an optional MCP hint; older mcp releases lack the type
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover - depends on the installed mcp version
    ToolAnnotations = None


def _annotations(**hints):
    """A :class:`ToolAnnotations` carrying the given behavior hints, or None when the installed
    ``mcp`` predates them (the decorator then registers the tool without annotations)."""
    return ToolAnnotations(**hints) if ToolAnnotations is not None else None


# The nine readers share this profile; wiki_ingest overrides it at its decorator.
_READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}


mcp = FastMCP("citadel")

_SNIPPET_CHARS = 200


def _snippet(query: str, body: str, width: int = _SNIPPET_CHARS) -> str:
    """Return a ~``width``-char one-line snippet of ``body`` around the first
    matching query token (case-insensitive). Falls back to the body head."""
    flat = " ".join(body.split())
    if not flat:
        return ""
    lower = flat.lower()
    pos = -1
    for token in query.lower().split():
        if not token:
            continue
        found = lower.find(token)
        if found != -1 and (pos == -1 or found < pos):
            pos = found
    if pos == -1:
        snippet = flat[:width]
        return snippet + ("…" if len(flat) > width else "")
    start = max(0, pos - width // 2)
    end = min(len(flat), start + width)
    snippet = flat[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(flat):
        snippet = snippet + "…"
    return snippet


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_search(query: str, limit: int = 8, tag: str = "") -> str:
    """Keyword search across all OKF wiki pages (title/tags/description/body).

    Optionally restrict to pages carrying ``tag`` (case-insensitive). Returns a
    ranked markdown list; each entry gives the page rel_path, its score, the
    title, its tags, and a short body snippet around the first matching token.
    The primary 'make the wiki usable' tool: an AI searches the synthesized wiki
    instead of re-retrieving the raw sources.
    """
    from . import store

    try:
        pages = None
        if tag.strip():
            want = tag.strip().lower()
            pages = [p for p in store.load() if want in [str(t).lower() for t in p.tags]]
            if not pages:
                return f"No pages tagged {tag!r}."
        hits = store.search(query, pages=pages, limit=limit)
    except Exception as e:  # never raise out of the tool
        return f"error: search failed: {e}"
    if not hits:
        scope = f" (tag {tag!r})" if tag.strip() else ""
        return f"No matches for {query!r}{scope}."
    parts = [f"# Search results for {query!r} ({len(hits)})", ""]
    for page, score in hits:
        parts.append(f"## {page.rel_path} (score {score:.2f})")
        if page.title:
            parts.append(page.title)
        if page.tags:
            parts.append("tags: " + ", ".join(page.tags))
        snippet = _snippet(query, page.body)
        if snippet:
            parts.append(snippet)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_tags(tag: str = "") -> str:
    """Browse the wiki by topic. With no argument, list every tag and the pages
    under it; with a ``tag``, list just that tag's pages. Tags are the OKF-native
    ``tags`` frontmatter field — a second navigation axis alongside search and the
    cross-link graph. Computed live so it is always current.
    """
    from . import store

    try:
        catalog = store.tag_catalog()
    except Exception as e:  # never raise out of the tool
        return f"error: could not read tags: {e}"
    if not catalog:
        return "No tags yet."

    if tag.strip():
        want = tag.strip().lower()
        pages = catalog.get(want)
        if not pages:
            return f"No pages tagged {tag!r}."
        lines = [f"# {want} ({len(pages)})", ""]
        lines += [f"- [{p.title}]({p.rel_path}) — {p.description}" for p in pages]
        return "\n".join(lines) + "\n"

    lines = ["# Tags", ""]
    for t in sorted(catalog):
        pages = catalog[t]
        lines.append(f"## {t} ({len(pages)})")
        lines += [f"- [{p.title}]({p.rel_path}) — {p.description}" for p in pages]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_read(rel_path: str) -> str:
    """Return the full verbatim OKF page text for a rel_path like
    'concepts/transformer.md' (frontmatter + body, including all per-fact
    [^sN] citations and the trailing ## Sources section).

    Path-safety is enforced via okf.safe_join. Returns a clear error string
    on not-found / unsafe path rather than raising.
    """
    from . import okf, store

    try:
        return store.read_page_text(rel_path)
    except FileNotFoundError:
        return f"error: page not found: {rel_path!r}"
    except okf.OKFError as e:
        return f"error: unsafe path: {e}"
    except Exception as e:  # never raise out of the tool
        return f"error: could not read {rel_path!r}: {e}"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_raw(source_key: str, locator: str = "") -> str:
    """Read the raw SOURCE behind a citation — the spot-check that closes a [^sN] provenance loop.

    'source_key' is the key as it appears in a page's ## Sources citation (e.g. 'raw/notes.md');
    'locator' is that citation's locator tail verbatim ('lines 76-83', '§ Method', or a combined
    '§ Method, lines 5-9') — empty returns the whole source. Output is line-numbered and capped.

    Only sources the wiki actually cites are readable (the ingest manifest, or a docs/ file). This
    VERIFIES the synthesized wiki against its provenance; to ANSWER a question use wiki_search /
    wiki_read (the wiki is the cited layer — this is the trust-but-verify spot-check, not bulk
    re-retrieval). Returns a clear error string (not a cited source / missing on disk / no offline
    text / locator out of range) rather than raising.
    """
    from . import rawsource

    try:
        return rawsource.raw_text(source_key, locator)
    except rawsource.SourceError as e:
        return f"error: {e}"
    except Exception as e:  # never raise out of the tool
        return f"error: could not read source {source_key!r}: {e}"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_neighbors(rel_path: str) -> str:
    """The link neighborhood of a page — walk the graph without doing relative-path math yourself.

    For a rel_path like 'concepts/transformer.md', returns three sections: **Links out** (its wiki
    cross-links, resolved to rel_paths, each flagged '(missing)' if the target page does not exist),
    **Linked from** (the pages that link to it — the backlink graph), and **Cites sources** (the raw/
    docs source keys it cites, with a per-source count — the keys to hand to wiki_raw).

    Returns a clear error string on not-found / unsafe path rather than raising.
    """
    from . import okf, store

    try:
        return store.neighbors_text(rel_path)
    except FileNotFoundError:
        return f"error: page not found: {rel_path!r}"
    except okf.OKFError as e:
        return f"error: unsafe path: {e}"
    except Exception as e:  # never raise out of the tool
        return f"error: could not read {rel_path!r}: {e}"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_index() -> str:
    """Return the contents of wiki/index.md — the catalog of all pages with
    one-line descriptions, for progressive disclosure (the cheap first read
    an agent does to orient before searching).
    """
    from . import store

    try:
        return store.index_text()
    except FileNotFoundError:
        return "error: wiki index not found (run `citadel ingest` first)."
    except Exception as e:  # never raise out of the tool
        return f"error: could not read index: {e}"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_sources() -> str:
    """Return the contents of wiki/sources/index.md — the provenance catalog: one row per
    ingested raw source, the model that imported it, and the wiki pages that cite it.

    This is the browse-by-source axis — "what do I know, and from which source?" — complementary
    to wiki_search / wiki_index, which browse by topic. (The catalog file is skipped by the page
    loader, so wiki_search never returns it; this tool exposes it directly.) Returns a clear
    message when nothing has been ingested yet. Never raises out of the tool.
    """
    from . import store

    try:
        return store.sources_text()
    except FileNotFoundError:
        return "No sources catalog yet (run `citadel ingest` first)."
    except Exception as e:  # never raise out of the tool
        return f"error: could not read sources catalog: {e}"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_validate(rel_path: str = "") -> str:
    """Validate wiki pages for links, file format, and required fields (type/title/
    description/tags/resource, honest citations, relative non-broken links) — the same checks
    the ingest gate enforces. With no ``rel_path``, validate the whole wiki; with a rel_path
    like 'concepts/transformer.md', validate just that page. Returns a human-readable issue
    list. The ingest agent should call this on each page it created or changed before
    finishing, and fix every reported error. Never raises out of the tool.
    """
    from . import validate

    try:
        issues = validate.validate_all()
        if rel_path.strip():
            want = rel_path.strip().replace("\\", "/")
            issues = [i for i in issues if i.rel_path == want]
        return validate.render_issues(issues)
    except Exception as e:  # never raise out of the tool
        return f"error: validation failed: {e}"


@mcp.tool(annotations=_annotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def wiki_ingest(paths: list[str] | None = None) -> str:
    """Trigger ingest of new/changed raw files (default: all of raw/).

    Folds freshly-dropped sources into the wiki on demand; idempotent via the
    sha256 manifest. Returns the IngestReport.render() text. The ONLY mutating
    tool. If the configured LLM CLI is missing or not logged in, that surfaces
    as a per-source error inside the returned report (or a clear error string) —
    the tool never raises out.
    """
    from . import ingest

    try:
        report = ingest.ingest(paths)
    except RuntimeError as e:  # e.g. missing API key
        return f"error: {e}"
    except Exception as e:  # never raise out of the tool
        return f"error: ingest failed: {e}"
    return report.render()


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_lint() -> str:
    """Run the offline wiki health check and return its report — contradictions, orphans,
    missing citations, broken links, missing types, stale pages, fabricated sources, undefined
    abbreviations, and Z6 locator issues.

    This is the read-only companion to wiki_validate: ``wiki_validate`` is the strict per-page
    gate (required fields, honest citations, non-broken links), while ``wiki_lint`` is the
    whole-wiki advisory scan an AI can call to decide what to curate next. No LLM, no network —
    pure static analysis over the loaded wiki. Never raises out of the tool.
    """
    from . import lint

    try:
        return lint.lint().render()
    except Exception as e:  # never raise out of the tool
        return f"error: lint failed: {e}"


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
