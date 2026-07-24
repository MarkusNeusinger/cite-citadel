"""MCP stdio server exposing the OKF wiki to AI clients.

A FastMCP instance over stdio with thirteen tools: eleven read-only
(wiki_search / wiki_define / wiki_read / wiki_raw / wiki_neighbors / wiki_index / wiki_sources /
wiki_tags / wiki_validate / wiki_lint / wiki_status) and two mutating — wiki_capture (append ONE
attributed conversational note to the raw/ capture log; it never touches the wiki) and wiki_ingest
(the only tool that writes the WIKI, through the staged agent lifecycle). Every tool returns a
plain markdown/text string, which an LLM consumes best, and NEVER raises out of the tool:
not-found / unsafe-path / missing-or-unusable-LLM-CLI conditions are returned as clear error strings
so the server stays up.

Each tool carries MCP **behavior annotations** (``readOnlyHint`` / ``destructiveHint`` /
``idempotentHint`` / ``openWorldHint``) so a client can reason about a tool before calling it: the
eleven readers are read-only; ``wiki_capture`` mutates only the raw capture log (non-destructive —
append-only — and closed-world); ``wiki_ingest`` mutates the wiki (non-destructive, idempotent via
the sha manifest, and open-world because it spawns your external coding-agent CLI). If the installed
``mcp`` predates tool annotations, they are silently omitted — a client that ignores hints is
unaffected.

Beyond tools, the server publishes four workflow **prompts** (``wiki_answer`` / ``wiki_verify`` /
``wiki_capture_note`` / ``wiki_health`` — the recommended tool flows packaged as
slash-command-like entries) and the wiki's documents as ``wiki://`` **resources**
(``wiki://index`` / ``wiki://sources`` / ``wiki://tags`` plus the ``wiki://page/{folder}/{name}``
per-page template). Resources return the same text as their tool twins and share the tools'
never-raise contract.

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


# The eleven readers share this profile; wiki_capture and wiki_ingest override it at their
# decorators.
_READ_ONLY = {"readOnlyHint": True, "openWorldHint": False}


# Handed to clients in the ``initialize`` result (``instructions``) — the orientation an AI needs
# before its first tool call, kept to the flow the module docstring describes.
_INSTRUCTIONS = (
    "citadel serves an LLM-maintained, fully-cited wiki. Orient with wiki_index (the page catalog), "
    "find pages with wiki_search / wiki_define, and answer from wiki_read's full cited page text — "
    "the wiki is the synthesized, cited layer, so prefer it over re-reading raw files. wiki_raw "
    "verifies a single [^sN] citation against its raw source (a spot-check, not bulk retrieval); "
    "wiki_neighbors walks the link graph; wiki_status shows per-source corpus state. wiki_capture "
    "appends ONE attributed note from the conversation to the raw/ capture log (use it when the "
    "user states something durable worth keeping — it never touches the wiki). wiki_ingest is the "
    "only tool that writes the WIKI (it spawns the configured coding-agent CLI and may take "
    "minutes) — it also folds captured notes in; every other tool is read-only, and errors always "
    "come back as plain 'error: …' strings. The same flows are packaged as prompts "
    "(wiki_answer / wiki_verify / wiki_capture_note / wiki_health), and the catalogs and pages "
    "are also addressable as wiki:// resources (wiki://index, wiki://sources, wiki://tags, "
    "wiki://page/{folder}/{name})."
)

mcp = FastMCP("citadel", instructions=_INSTRUCTIONS)

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


_SEARCH_LIMIT_MAX = 50
# Deepest reachable pagination offset: bounds the limit+offset slice wiki_search asks store.search
# for, so a miscomputed huge offset cannot demand the whole ranked corpus in one call.
_SEARCH_OFFSET_MAX = 200


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_search(query: str, limit: int = 8, tag: str = "", offset: int = 0) -> str:
    """Ranked full-text search across all OKF wiki pages
    (title/aliases/tags/description/body).

    Bare query terms are matched AND (every content word must hit; English
    stopwords are not required, and a query no page fully matches is retried
    as OR) and scored by BM25 with title > aliases > tags > description > body
    field weighting plus an exact-phrase bonus. ``tag:x`` / ``type:y`` tokens
    inside the query filter instead of match (tag by prefix, type exactly) —
    ``type:person`` alone lists every person page. Optionally restrict to
    pages carrying ``tag`` (case-insensitive). Returns a ranked markdown list;
    each entry gives the page rel_path, its score (comparable within one
    result list only), the title, its tags, and a short body snippet around
    the first matching token. A ``limit`` <= 0 is treated as unset and falls
    back to the default (8) — a miscomputed limit must not read as a confident
    "No matches" — and is capped at 50 (one call must not dump the whole
    ranked corpus). ``offset`` skips the first N ranked hits, so results past
    the first page stay reachable (``offset=8`` continues where the default
    first call stopped); it is capped at 200. The primary 'make the wiki
    usable' tool: an AI searches the synthesized wiki instead of re-retrieving
    the raw sources.
    """
    from . import store

    if limit <= 0:
        limit = 8
    limit = min(limit, _SEARCH_LIMIT_MAX)
    offset = min(max(offset, 0), _SEARCH_OFFSET_MAX)
    try:
        pages = None
        if tag.strip():
            want = tag.strip().lower()
            pages = [p for p in store.load() if want in [str(t).lower() for t in p.tags]]
            if not pages:
                return f"No pages tagged {tag!r}."
        hits = store.search(query, pages=pages, limit=limit + offset)[offset:]
    except Exception as e:  # never raise out of the tool
        return f"error: search failed: {e}"
    if not hits:
        scope = f" (tag {tag!r})" if tag.strip() else ""
        if offset:
            return f"No more matches for {query!r}{scope} at offset {offset}."
        return f"No matches for {query!r}{scope}."
    header = f"# Search results for {query!r} ({len(hits)}" + (f", offset {offset})" if offset else ")")
    parts = [header, ""]
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
def wiki_define(term: str) -> str:
    """Glossary lookup — "what does X stand for / mean?" — surfacing the definition directly.

    A short definitional query is a LOOKUP, not full-text retrieval, so this answers it in three
    tiers, most specific first: an **Abbreviations glossary** hit (a ``type: Abbreviation`` page
    whose short form, expansion, title, or alias equals ``term``, rendered ``SHORT — Expansion``),
    then an **exact-title / alias** page of any type (the definitional page for that concept), then
    a **fallback** to the closest wiki_search hits when nothing matches exactly. Case-insensitive.

    Prefer this over wiki_search when you just need the meaning/expansion of a term; use wiki_search
    to explore a topic. Returns a clear message when nothing matches; never raises out of the tool.
    """
    from . import store

    try:
        return store.define_text(term)
    except Exception as e:  # never raise out of the tool
        return f"error: could not define {term!r}: {e}"


# Default output cap for wiki_read, mirroring rawsource.MAX_CHARS: one pathological page must not
# swamp the client context. Pages are normally far smaller (curate splits them well before this).
_READ_MAX_CHARS = 20_000


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_read(rel_path: str, max_chars: int = _READ_MAX_CHARS) -> str:
    """Return the full verbatim OKF page text for a rel_path like
    'concepts/transformer.md' (frontmatter + body, including all per-fact
    [^sN] citations and the trailing ## Sources section). A Windows-style
    rel_path (backslashes) is normalized, matching wiki_validate.

    Output is capped at ``max_chars`` (default 20000 — normal pages fit whole;
    the cap only guards against one pathological page swamping the context) and
    truncated at a line boundary with a marker; pass ``max_chars=0`` (exactly)
    for the uncapped text — a negative value is treated as invalid and falls
    back to the default cap. Path-safety is enforced via okf.safe_join. Returns
    a clear error string on not-found / unsafe path rather than raising.
    """
    from . import okf, store

    try:
        text = store.read_page_text(rel_path)
    except FileNotFoundError:
        return f"error: page not found: {rel_path!r}"
    except okf.OKFError as e:
        return f"error: {e}"  # the OKFError text already says "unsafe path: …"
    except Exception as e:  # never raise out of the tool
        return f"error: could not read {rel_path!r}: {e}"
    if max_chars < 0:  # a miscomputed client value must not silently lift the cap
        max_chars = _READ_MAX_CHARS
    if max_chars and len(text) > max_chars:
        clipped = text[:max_chars].rsplit("\n", 1)[0]
        return f"{clipped}\n… [truncated at {max_chars} chars — re-call with max_chars=0 for the full page]"
    return text


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
    text / locator out of range or not offline-resolvable) rather than raising.
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
    docs source keys it cites, with a per-source count — the keys to hand to wiki_raw). A
    Windows-style rel_path (backslashes) is normalized, matching wiki_validate.

    Returns a clear error string on not-found / unsafe path rather than raising.
    """
    from . import okf, store

    try:
        return store.neighbors_text(rel_path)
    except FileNotFoundError:
        return f"error: page not found: {rel_path!r}"
    except okf.OKFError as e:
        return f"error: {e}"  # the OKFError text already says "unsafe path: …"
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
    from . import config, okf, store, validate

    try:
        pages = store.load()
        issues = validate.validate_all(pages)
        if rel_path.strip():
            want = rel_path.strip().replace("\\", "/")
            # A named page that does not exist must be an error, not a clean "OK" — a page
            # with zero issues and a typo'd path would otherwise be indistinguishable.
            if want not in {p.rel_path for p in pages}:
                try:
                    on_disk = okf.safe_join(config.WIKI_DIR, want).is_file()
                except okf.OKFError:
                    on_disk = False
                if on_disk:
                    return f"error: not a validated page: {want} (generated/reserved files are not checked)"
                return f"error: no such page: {want}"
            issues = [i for i in issues if i.rel_path == want]
        return validate.render_issues(issues)
    except Exception as e:  # never raise out of the tool
        return f"error: validation failed: {e}"


@mcp.tool(
    annotations=_annotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)
)
def wiki_capture(text: str, source: str = "", topic: str = "") -> str:
    """Capture ONE attributed note from this conversation into the raw/ capture log — the
    conversational bridge into the wiki's provenance lifecycle.

    Appends (never edits or deletes) a dated entry to ``raw/captures/YYYY-MM.md`` under the
    primary raw root: ``text`` is the statement worth keeping (the user said something durable —
    a decision, a fact about their world, a "remember that …"), ``source`` attributes it (who
    said it / where it came from, e.g. ``"Kim, chat 2026-07-24"``), ``topic`` is an optional
    heading hint. The wiki itself is NOT touched: the log is an ordinary raw source, so the next
    wiki_ingest folds the entry in through the normal staged, validated lifecycle with real
    ``[^sN]`` line-locator citations into the log — captured statements enter the wiki as
    attributed claims ("X said Y"), never as bare facts. Returns the log's source key and the
    appended line range (the future citation locator), plus the ingest reminder; empty or
    oversized text (a whole transcript belongs in raw/ as its own file) comes back as a clear
    error string. Never raises out of the tool.
    """
    from . import capture as capture_mod

    try:
        return capture_mod.capture(text, source=source, topic=topic).render()
    except ValueError as e:  # empty / oversized text — the refusal is the answer
        return f"error: {e}"
    except Exception as e:  # never raise out of the tool
        return f"error: capture failed: {e}"


@mcp.tool(annotations=_annotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def wiki_ingest(paths: list[str] | None = None) -> str:
    """Trigger ingest of new/changed raw files (default: all of raw/).

    Folds freshly-dropped sources into the wiki on demand; idempotent via the
    sha256 manifest. Returns the IngestReport.render() text. The ONLY tool that
    writes the WIKI (wiki_capture only appends to the raw/ capture log). If the
    configured LLM CLI is missing or not logged in, that surfaces as a
    per-source error inside the returned report (or a clear error string) —
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
def wiki_lint(stale_days: int = 365) -> str:
    """Run the offline wiki health check and return its report — contradictions, orphans,
    missing citations, broken links, missing types, stale pages, fabricated sources, undefined
    abbreviations, and locator issues. Pages older than ``stale_days`` are flagged stale
    (default 365, matching ``citadel lint --stale-days``).

    This is the read-only companion to wiki_validate: ``wiki_validate`` is the strict per-page
    gate (required fields, honest citations, non-broken links), while ``wiki_lint`` is the
    whole-wiki advisory scan an AI can call to decide what to curate next. No LLM, no network —
    pure static analysis over the loaded wiki. Never raises out of the tool.
    """
    from . import lint

    try:
        return lint.lint(stale_days=stale_days).render()
    except Exception as e:  # never raise out of the tool
        return f"error: lint failed: {e}"


@mcp.tool(annotations=_annotations(**_READ_ONLY))
def wiki_status() -> str:
    """Per-source corpus state — the read-only twin of ``citadel status``.

    One bucket per lifecycle state: **ingested** (with the importing model + the rules version it
    ran under, flagged ``(stale)`` when that predates the current rulebook), **failed** (unreadable /
    errored / timed-out, with the reason and attempt count), **skipped-duplicate**, **ignored**
    (OS/junk files), and **pending** (on disk under a raw root but not yet ingested). Built from the
    manifest + failures catalog + one stat-only walk — it never re-hashes a byte and never mutates,
    so it is the cheap check to run before/after ``wiki_ingest`` to see what is pending, stale, or
    stuck. Never raises out of the tool.
    """
    from . import status

    try:
        return status.build_status().render()
    except Exception as e:  # never raise out of the tool
        return f"error: could not read corpus status: {e}"


# --- Prompts -----------------------------------------------------------------------------
# Packaged workflows exposed as MCP **prompts** (clients surface them as slash-command-like
# entries). Each renders to ONE user message that walks the model through the recommended
# tool flow — the prompt is orientation, the tools do the work. Names share the tools'
# ``wiki_`` prefix so the prompt and the tools it drives read as one surface.


@mcp.prompt(title="Answer from the wiki")
def wiki_answer(question: str) -> str:
    """Answer a question strictly from the cited wiki — the recommended read flow
    (orient → search → read → cite, with wiki_raw as the spot-check) packaged as one prompt."""
    return (
        f"Answer this question from the citadel wiki — the synthesized, fully-cited layer over "
        f"the user's raw sources:\n\n{question}\n\n"
        "Work like this:\n"
        "1. Orient: call wiki_index for the page catalog, or wiki_define first if the question "
        "is a what-does-X-mean lookup.\n"
        "2. Find: call wiki_search with the question's content words; refine the query (or page "
        "with offset) if the first hits miss.\n"
        "3. Read: call wiki_read on every promising rel_path and answer strictly from the page "
        "text — facts there carry [^sN] citations into immutable raw sources, while [^llmN] "
        "marks model-supplied knowledge with no raw source behind it (weigh it accordingly).\n"
        "4. Cite: name the wiki pages (rel_paths) the answer draws on. Spot-check any "
        "load-bearing claim with wiki_raw (source key + locator from the page's ## Sources) "
        "before asserting it.\n"
        "5. If the wiki does not cover the question, say so plainly instead of filling the gap "
        "from memory — new knowledge enters via files dropped into raw/ (folded in by "
        "wiki_ingest) or a wiki_capture note."
    )


@mcp.prompt(title="Verify a page's citations")
def wiki_verify(rel_path: str) -> str:
    """Spot-check one page against its provenance: read it, then resolve every [^sN]
    citation through wiki_raw and report supported / unsupported / unreadable per fact."""
    return (
        f"Verify the wiki page {rel_path} against its cited sources.\n\n"
        "1. Call wiki_read with rel_path=" + repr(rel_path) + " and max_chars=0 for the full "
        "text, and note each fact's footnote and the ## Sources entry it points to. Only [^sN] "
        "entries cite a raw source; [^llmN] entries are model-supplied (source: LLM) with "
        "nothing offline to verify — tally them, but skip wiki_raw for them.\n"
        "2. For every [^sN] citation, call wiki_raw with that entry's source key and its "
        "locator tail verbatim (e.g. 'lines 12-18' or '§ Heading') and check the returned "
        "lines actually support the fact as stated.\n"
        "3. Also run wiki_validate on the page for the structural gate.\n"
        "Report one line per [^sN] citation — supported / unsupported / source unreadable, with "
        "the mismatch quoted — plus the [^llmN] tally, and finish with an overall verdict. Do "
        "not try to fix anything: the wiki is only ever written by staged ingest/curate "
        "sessions."
    )


@mcp.prompt(title="Capture a note")
def wiki_capture_note(statement: str, source: str = "") -> str:
    """Record ONE durable statement from the conversation through wiki_capture — attributed,
    append-only, into the raw/ capture log the next ingest folds in."""
    if source.strip():
        attribution = f"source={source.strip()!r} as the attribution"
    else:
        attribution = (
            "a source you compose attributing it to the user in this conversation with "
            "today's actual date (in the shape 'the user, chat 2026-07-24')"
        )
    return (
        "Capture this durable statement into the citadel raw/ capture log:\n\n"
        f"{statement}\n\n"
        f"Call wiki_capture with that text, {attribution}, and a short topic hint. Keep it to "
        "ONE statement — a whole transcript belongs in raw/ as its own file — and leave out "
        "secrets or credentials. Then report the returned source key and line range (the "
        "future [^sN] locator) and remind the user that the next wiki_ingest folds the note "
        "into the wiki as an attributed claim."
    )


@mcp.prompt(title="Wiki health review")
def wiki_health() -> str:
    """Review corpus + wiki health (wiki_status, then wiki_lint) and recommend the single
    next maintenance action."""
    return (
        "Review the health of this citadel workspace.\n\n"
        "1. Call wiki_status for the per-source corpus state (pending / failed / stale "
        "sources).\n"
        "2. Call wiki_lint for the advisory wiki scan (contradictions, orphans, missing "
        "citations, broken links, locator issues).\n"
        "Summarize both briefly, then recommend the single most useful next action: wiki_ingest "
        "when sources are pending or failed-retryable, `citadel curate` for page-quality "
        "findings, `citadel refresh` for aging ingested sources (both CLI-only lifecycles). "
        "Keep the whole review short and actionable."
    )


# --- Resources ---------------------------------------------------------------------------
# The wiki's documents as addressable MCP **resources** under a ``wiki://`` scheme: the two
# catalogs and the tag overview as concrete resources, and every OKF page through one
# ``wiki://page/{folder}/{name}`` template (an OKF rel_path is always exactly
# ``folder/name.md`` — pages are routed one folder deep by okf.folder_for_type). Each
# resource returns the SAME text as its tool twin and shares the tools' never-raise
# contract: a missing page, an unsafe path, or a broken store reads back as a clear
# ``error: …`` body, so a resource-pulling client can never crash the server. Subscribe /
# ``listChanged`` notifications are deliberately not offered — FastMCP's registry is static,
# and the wiki only changes through staged ingest/curate runs anyway.


@mcp.resource(
    "wiki://index",
    name="wiki-index",
    title="Page catalog",
    mime_type="text/markdown",
    description="index.md — every wiki page with a one-line description (wiki_index's twin).",
)
def index_resource() -> str:
    return wiki_index()


@mcp.resource(
    "wiki://sources",
    name="wiki-sources",
    title="Provenance catalog",
    mime_type="text/markdown",
    description="sources/index.md — every ingested raw source and the pages citing it (wiki_sources's twin).",
)
def sources_resource() -> str:
    return wiki_sources()


@mcp.resource(
    "wiki://tags",
    name="wiki-tags",
    title="Tag overview",
    mime_type="text/markdown",
    description="Every tag and the pages under it (wiki_tags's twin).",
)
def tags_resource() -> str:
    return wiki_tags()


@mcp.resource(
    "wiki://page/{folder}/{name}",
    name="wiki-page",
    title="Wiki page",
    mime_type="text/markdown",
    description="One OKF page's full cited text by rel_path, e.g. wiki://page/concepts/transformer.md (wiki_read's twin, uncapped — a resource is a whole document).",
)
def page_resource(folder: str, name: str) -> str:
    return wiki_read(f"{folder}/{name}", max_chars=0)


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
