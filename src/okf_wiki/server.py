"""MCP stdio server exposing the OKF wiki to AI clients.

A FastMCP instance over stdio with five tools: four read-only
(wiki_search / wiki_read / wiki_index / wiki_tags) and one mutating (wiki_ingest).
Every tool returns a plain markdown/text string, which an LLM consumes
best, and NEVER raises out of the tool: not-found / unsafe-path /
missing-or-unusable-LLM-CLI conditions are returned as clear error strings
so the server stays up.

Run via ``okf-wiki serve`` or ``python -m okf_wiki.server``.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("okf-wiki")

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


@mcp.tool()
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
            pages = [
                p for p in store.load() if want in [str(t).lower() for t in p.tags]
            ]
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


@mcp.tool()
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


@mcp.tool()
def wiki_read(rel_path: str) -> str:
    """Return the full verbatim OKF page text for a rel_path like
    'concepts/transformer.md' (frontmatter + body, including all per-fact
    [^sN] citations and the trailing ## Sources section).

    Path-safety is enforced via okf.safe_join. Returns a clear error string
    on not-found / unsafe path rather than raising.
    """
    from . import okf, store

    try:
        page = store.read_page(rel_path)
    except FileNotFoundError:
        return f"error: page not found: {rel_path!r}"
    except okf.OKFError as e:
        return f"error: unsafe path: {e}"
    except Exception as e:  # never raise out of the tool
        return f"error: could not read {rel_path!r}: {e}"
    return okf.dump(page.frontmatter, page.body)


@mcp.tool()
def wiki_index() -> str:
    """Return the contents of wiki/index.md — the catalog of all pages with
    one-line descriptions, for progressive disclosure (the cheap first read
    an agent does to orient before searching).
    """
    from . import config

    try:
        return config.INDEX_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "error: wiki index not found (run `okf-wiki ingest` first)."
    except Exception as e:  # never raise out of the tool
        return f"error: could not read index: {e}"


@mcp.tool()
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


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
