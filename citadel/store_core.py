"""Core of the wiki 'database': load / read / write / delete / search + the text providers.

Loads every .md under wiki/ (skipping index.md, log.md, per-directory index.md, dotfiles) into
Page objects; offers ranked full-text search (the ONE swappable search function — BM25 computed
in memory per call, so nothing is persisted and the wiki stays the database); writes/overwrites
pages with path-safety and a reserved-name guard; deletes pages; the shared page/index/sources
text providers behind the CLI and MCP surfaces; and the append-only log.md writer. No on-disk
index, no embeddings. The link graph, catalogs, and open-points live in sibling modules
(:mod:`citadel.linkgraph`, :mod:`citadel.catalogs`, :mod:`citadel.open_points`); the
:mod:`citadel.store` facade re-exports the whole surface.
"""

from __future__ import annotations

import math
import os
import re
from datetime import datetime, timezone

from . import __version__, config, okf
from .okf import Page


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def utc_now_iso() -> str:
    """Return the current UTC time as 'YYYY-MM-DDTHH:MM:SSZ'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_skipped_name(name: str) -> bool:
    """True for files load() must skip: index.md, log.md, and any dotfile."""
    if name.startswith("."):
        return True
    return name in ("index.md", "log.md")


def load() -> list[Page]:
    """Walk config.WIKI_DIR; parse each *.md (not index.md/log.md, not a dotfile)
    into a Page whose rel_path is its posix path relative to WIKI_DIR. Missing
    'type' is surfaced by lint, not load, so failing pages are still included.
    Return the list sorted by rel_path."""
    wiki_dir = config.WIKI_DIR
    pages: list[Page] = []
    if not os.path.isdir(wiki_dir):
        return pages
    for dirpath, dirnames, filenames in os.walk(wiki_dir):
        # Skip hidden directories.
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".md"):
                continue
            if is_skipped_name(name):
                continue
            abs_path = os.path.join(dirpath, name)
            rel_path = os.path.relpath(abs_path, wiki_dir).replace(os.sep, "/")
            try:
                with open(abs_path, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                continue
            frontmatter, body = okf.parse(text)
            pages.append(Page(rel_path=rel_path, frontmatter=frontmatter, body=body))
    pages.sort(key=lambda p: p.rel_path)
    return pages


_VOWELS = frozenset("aeiouy")


def _stem(token: str) -> str:
    """A light, deterministic, dependency-free suffix strip so paraphrased query words match:
    ``brewing``/``brew``, ``founded``/``founding``/``found``, ``blows``/``blow`` all collapse to a
    common root. NOT a full Porter stemmer — one pass, checking a fixed, hand-ordered suffix list
    (``ing``, ``edly``, ``ed``, ``ly``, ``ies``, ``es``, ``s``) and taking the first that matches,
    only when a vowel survives in the stem (so short/odd tokens like ``ss`` are left alone) and the
    remaining stem is long enough. ``-ies`` becomes ``-y`` (``ponies`` -> ``pony``). Applied
    symmetrically to both the query and the page text by :func:`_tokenize`, so matching stays
    consistent and the field-weight/IDF contract is unchanged (a token is stemmed the same way
    wherever it appears).

    Two targeted guards keep the strip from over-collapsing:

    * ``-ly`` requires a **4-char** stem (all other suffixes require 3), so ``nearly`` -> ``near``
      but ``early``/``curly``/``burly`` are left whole rather than colliding with ``ear``/``cur``/``bur``.
    * ``-es`` is only taken when the stem ends in a vowel (``potatoes`` -> ``potato``); for a
      consonant-ending stem it is skipped so the plain ``-s`` rule strips a single char instead,
      keeping ``-e`` words symmetric (``tables`` -> ``table`` matches ``table``, ``houses`` ->
      ``house``) rather than over-stripping to ``tabl``/``hous``.

    This is a single pass, so it unifies only one inflection layer: ``findings`` -> ``finding`` (not
    ``find``), and irregular pairs (e.g. ``caffeinated``/``caffeine``) simply fall back to plain
    overlap — light recall gain, never a regression."""
    if len(token) <= 3:
        return token
    for suffix in ("ing", "edly", "ed", "ly", "ies", "es", "s"):
        if not token.endswith(suffix):
            continue
        stem = token[: len(token) - len(suffix)]
        min_stem = 4 if suffix == "ly" else 3
        if len(stem) < min_stem:
            continue
        if suffix == "ies":
            return stem + "y"
        # A consonant-ending "-es" (tables, houses) is really "-e" + "s": defer to the "-s" rule
        # below so it strips a single char and stays symmetric with the singular.
        if suffix == "es" and stem[-1] not in _VOWELS:
            continue
        if any(ch in _VOWELS for ch in stem):
            return stem
    return token


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, drop tokens shorter than 2 chars, then light-stem
    (:func:`_stem`) so paraphrased forms of the same word share a token."""
    return {_stem(tok) for tok in _TOKEN_RE.findall(text.lower()) if len(tok) >= 2}


# The per-field BM25 weights, in _field_counts order: title, aliases, tags, description, body.
# Aliases are a page's declared alternate names/synonyms (an abbreviation's spelled-out form, a
# lay term for the concept), so weighting them lets a paraphrased query reach the page by a word
# the title lacks — purely lexical, no synonym map.
_FIELD_WEIGHTS = (3.0, 2.5, 2.0, 1.5, 1.0)

# The standard BM25 constants: _K1 saturates repeated occurrences of a term (the 10th mention
# adds far less than the 2nd); _FIELD_B scales the per-field length normalization (a term hit
# lost in a long text says less than one in a short text). Only the prose fields (description,
# body) are length-normalized: title/aliases/tags are short structured fields where document
# length carries no relevance signal — and normalizing them against a corpus where most pages
# leave the field empty would punish exactly the pages that use it.
_K1 = 1.2
_FIELD_B = (0.0, 0.0, 0.0, 0.75, 0.75)

# English function words dropped from the MATCHED terms (never from the phrase bonus) so a
# natural-language query — the MCP consumer asks questions, not keywords — is AND-matched on its
# content words only: "how do you brew coffee" must reach the brewing pages, not just whichever
# page happens to contain "how", "do", and "you". A query of ONLY stopwords keeps its terms.
_STOPWORDS = frozenset(
    """a an and are as at be but by can could did do does for from had has have how i if in is it
    its no not of on or should that the their them then there these they this those to was were
    what when where which who why will with would you your""".split()
)


def _field_counts(page: Page) -> list[dict[str, int]]:
    """Stemmed token counts (term frequencies) for a page's five scored fields — title, aliases,
    tags, description, body, in :data:`_FIELD_WEIGHTS` order. Computed ONCE per page per search
    and shared by the document-frequency pass and the scoring pass."""
    counted: list[dict[str, int]] = []
    for text in (
        page.title,
        " ".join(sorted(_aliases_of(page))),
        " ".join(str(t) for t in page.tags),
        page.description,
        page.body,
    ):
        counts: dict[str, int] = {}
        for tok in _TOKEN_RE.findall(text.lower()):
            if len(tok) >= 2:
                stemmed = _stem(tok)
                counts[stemmed] = counts.get(stemmed, 0) + 1
        counted.append(counts)
    return counted


def _bm25_scores(terms: list[str], pages: list[Page]) -> dict[int, float]:
    """BM25 relevance per candidate page, computed in memory from `pages` on every call —
    holding to 'the wiki IS the database' (no persisted index, nothing to go stale). Fields are
    weighted in the classic ladder (title 3.0, aliases 2.5, tags 2.0, description 1.5, body 1.0,
    a simplified BM25F); term and page text share one stemmer (:func:`_stem`) so inflected forms
    match. IDF uses the Lucene smoothing ``log(1 + (N - df + 0.5) / (df + 0.5))``, which is
    strictly positive — deliberately NOT SQLite FTS5's ``bm25()``, whose unsmoothed Robertson
    IDF clamps any term appearing in more than half the corpus to ~0, gutting the field ladder
    for exactly the most common query shape in a topical wiki (the corpus's own topic word).
    Terms are matched AND (every term must appear in some field, like the viewer); when a
    multi-term AND matches nothing the query is retried once as OR, so a partially-wrong
    phrasing still surfaces the closest pages instead of a flat miss. Returns
    ``{page index: score}``, higher = better; ``{}`` when nothing tokenizes or matches."""
    query_tokens = _tokenize(" ".join(terms))
    n = len(pages)
    if not query_tokens or n == 0:
        return {}
    docs = [_field_counts(page) for page in pages]
    lengths = [[sum(field.values()) for field in fields] for fields in docs]
    df = dict.fromkeys(query_tokens, 0)
    for fields in docs:
        for tok in query_tokens:
            if any(tok in field for field in fields):
                df[tok] += 1
    idf = {tok: math.log(1.0 + (n - d + 0.5) / (d + 0.5)) for tok, d in df.items()}
    # Average field length over the pages that USE the field (a mostly-empty corpus field must
    # not punish the pages that fill it), for the length-normalized prose fields.
    avglen = []
    for f in range(len(_FIELD_WEIGHTS)):
        filled = [lens[f] for lens in lengths if lens[f]]
        avglen.append(sum(filled) / len(filled) if filled else 0.0)
    for require_all in (True, False):
        scores: dict[int, float] = {}
        for i, fields in enumerate(docs):
            present = {tok for tok in query_tokens if any(tok in field for field in fields)}
            if require_all and present != query_tokens:
                continue
            score = 0.0
            for tok in present:
                weighted = 0.0
                for f, (weight, field) in enumerate(zip(_FIELD_WEIGHTS, fields, strict=True)):
                    tf = field.get(tok, 0)
                    if not tf:
                        continue
                    b = _FIELD_B[f]
                    norm = 1.0 - b + b * (lengths[i][f] / avglen[f]) if b and avglen[f] else 1.0
                    weighted += weight * tf * (_K1 + 1.0) / (tf + _K1 * norm)
                score += idf[tok] * weighted
            if score > 0.0:
                scores[i] = score
        if scores or len(query_tokens) < 2:
            return scores
    return scores


def _parse_query(query: str) -> tuple[list[str], list[str], list[str]]:
    """Split a query into lowercased bare terms plus ``tag:``/``type:`` operator filters —
    the SAME grammar the offline viewer's search box parses, so the two search surfaces accept
    one query language. Any other ``prefix:`` token stays a literal bare term. Returns
    ``(terms, tag_filters, type_filters)``."""
    terms: list[str] = []
    tag_filters: list[str] = []
    type_filters: list[str] = []
    for tok in (query or "").strip().lower().split():
        if tok.startswith("tag:") and len(tok) > 4:
            tag_filters.append(tok[4:])
        elif tok.startswith("type:") and len(tok) > 5:
            type_filters.append(tok[5:])
        else:
            terms.append(tok)
    return terms, tag_filters, type_filters


def _passes_operators(page: Page, tag_filters: list[str], type_filters: list[str]) -> bool:
    """Viewer-convergent operator semantics: every ``tag:`` filter must PREFIX-match one of the
    page's tags (``tag:brew`` hits ``brewing``), and the page's type must equal one of the
    ``type:`` filters exactly (case-insensitive). No filters -> passes."""
    if type_filters and (page.type or "").strip().lower() not in type_filters:
        return False
    for tf in tag_filters:
        if not any(str(t).strip().lower().startswith(tf) for t in page.tags):
            return False
    return True


def search(query: str, pages: list[Page] | None = None, limit: int = 8) -> list[tuple[Page, float]]:
    """THE single swappable search seam. If pages is None, call load(). Ranked full-text search
    over the candidate pages: bare terms are matched AND (every term must hit — English
    stopwords are excluded from the requirement so a natural-language question matches on its
    content words, and the query is retried once as OR when it would otherwise miss entirely)
    and scored by BM25 (:func:`_bm25_scores` — in-memory, Lucene-smoothed IDF, term-frequency
    saturation, length normalization) with the title 3.0 / aliases 2.5 / tags 2.0 /
    description 1.5 / body 1.0 field weights, both sides stemmed by :func:`_stem`, plus a 0.5
    bonus when the contiguous lowercased phrase appears in any indexed field — so an exact
    phrase outranks the same words scattered. ``tag:x`` / ``type:y`` operator tokens filter
    instead of match (tag by prefix, type exactly), the same query grammar as the offline
    viewer's search box — the two search surfaces converge. An operator-only query returns the
    filtered pages as a flat listing (score 1.0, rel_path order). Zero scores are dropped;
    results sort desc by score then rel_path; the top `limit` is returned as (page, score).
    Scores are comparable within one result list only (BM25 is corpus-relative)."""
    if limit <= 0:
        return []
    if pages is None:
        pages = load()
    terms, tag_filters, type_filters = _parse_query(query)
    if not terms and not tag_filters and not type_filters:
        return []
    candidates = [page for page in pages if _passes_operators(page, tag_filters, type_filters)]
    if not terms:  # operator-only: a flat filter listing, like the viewer's
        candidates.sort(key=lambda p: p.rel_path)
        return [(page, 1.0) for page in candidates[:limit]]
    content_terms = [t for t in terms if t not in _STOPWORDS] or terms
    scores = _bm25_scores(content_terms, candidates)
    phrase = " ".join(terms)
    scored: list[tuple[Page, float]] = []
    for i, page in enumerate(candidates):
        score = scores.get(i, 0.0)
        # The contiguous-phrase bonus, checked over the same five fields BM25 indexes. It doubles
        # as a substring net (a page the tokenizer cannot reach — a symbol-only query, an embedded
        # hyphenated form — still surfaces at 0.5), and because it is flat across fields, ties
        # among equally-bonused pages fall back to BM25's column weights — including the case of a
        # term present in EVERY candidate, where BM25's clamped idf alone degenerates to ~0.
        haystack = "\n".join(
            (
                page.title,
                " ".join(sorted(_aliases_of(page))),
                " ".join(str(t) for t in page.tags),
                page.description,
                page.body,
            )
        ).lower()
        if phrase in haystack:
            score += 0.5
        if score > 0.0:
            scored.append((page, score))
    scored.sort(key=lambda item: (-item[1], item[0].rel_path))
    return scored[:limit]


def read_page(rel_path: str) -> Page:
    """okf.safe_join(WIKI_DIR, rel_path); read text; okf.parse; return Page.
    Raise FileNotFoundError if absent."""
    target = okf.safe_join(config.WIKI_DIR, rel_path)
    if not target.is_file():
        raise FileNotFoundError(rel_path)
    text = target.read_text(encoding="utf-8")
    frontmatter, body = okf.parse(text)
    return Page(rel_path=rel_path, frontmatter=frontmatter, body=body)


# --- shared page/catalog text providers ------------------------------------------------------
# The ONE implementation behind each of the read/index/sources behaviors, consumed by BOTH the
# CLI subcommands (cli.cmd_read/index/sources — print + exit codes) and the MCP tools
# (server.wiki_read/index/sources — never-raise error strings). Each returns the text or raises a
# typed error the caller maps to its own contract, so the behavior lives exactly once.


def _normalize_rel_path(rel_path: str) -> str:
    """Normalize a caller-supplied page rel_path: whitespace stripped, backslashes (Windows input)
    to forward slashes — the SAME normalization ``wiki_validate`` applies, so every rel_path-taking
    surface (MCP tool or its CLI twin) accepts a Windows-style path identically."""
    return rel_path.strip().replace("\\", "/")


def read_page_text(rel_path: str) -> str:
    """The full text of one wiki page as written on disk — never re-serialized (re-dumping
    through ``okf.dump`` gave a frontmatter-less generated file like ``index.md`` a spurious
    empty ``{}`` frontmatter block; canonical pages round-trip identically either way). Two
    encoding-artifact normalizations only, so the page's CONTENT is untouched: a leading UTF-8
    BOM is stripped (``utf-8-sig``, mirroring ``okf.parse`` — a BOM'd page must not leak a
    ``\\ufeff`` before its frontmatter into MCP/CLI output) and text mode applies universal
    newlines. Raises FileNotFoundError (no such page), okf.OKFError (unsafe/traversal path), or
    an OS/decoding error (an undecodable file) — the callers translate those into a CLI exit
    code or an MCP error string."""
    rel_path = _normalize_rel_path(rel_path)
    target = okf.safe_join(config.WIKI_DIR, rel_path)
    if not target.is_file():
        raise FileNotFoundError(rel_path)
    return target.read_text(encoding="utf-8-sig")


def neighbors_text(rel_path: str) -> str:
    """The link neighborhood of one wiki page — the text behind ``wiki_neighbors`` / ``citadel
    neighbors``, so an AI can walk the graph without doing relative-path math itself. Three sections:
    **Links out** (this page's resolved wiki cross-links, each flagged ``(missing)`` when it names no
    existing page), **Linked from** (the pages that link to this one — the backlink graph), and
    **Cites sources** (the distinct raw/docs source keys in its ``## Sources``, with how many
    footnotes cite each — the handoff key for ``wiki_raw``). The rel_path is normalized like
    ``read_page_text``'s (backslashes to slashes). Raises FileNotFoundError (no such page) /
    okf.OKFError (unsafe path), which the CLI/MCP surfaces map to an exit code / error string. ONE
    ``load()`` powers the target page, the backlink graph, and the link titles — the file is parsed
    once, not re-read on top of the corpus scan."""
    from . import grammar, linkgraph

    rel_path = _normalize_rel_path(rel_path)
    okf.safe_join(config.WIKI_DIR, rel_path)  # validate the path (raises okf.OKFError on traversal/escape)
    pages = load()
    by_path = {p.rel_path: p for p in pages}
    page = by_path.get(rel_path)
    if page is None:  # safe but absent (or a skipped index.md/log.md) — same not-found contract as read_page
        raise FileNotFoundError(rel_path)
    titles = {rp: p.title for rp, p in by_path.items()}

    seen: set[str] = set()
    out_links: list[tuple[str, str | None]] = []
    for _raw, resolved in grammar.resolved_md_links(rel_path, page.body):
        if resolved == rel_path or resolved in seen:
            continue
        seen.add(resolved)
        out_links.append((resolved, titles.get(resolved)))

    inbound = linkgraph.inbound_map(pages).get(rel_path, [])

    cites: dict[str, int] = {}
    for _marker, rest in grammar.source_definitions(page.body):
        target = grammar.def_link_target(rest)
        if target is None or grammar.is_external(target):
            continue
        abs_path = grammar.link_abs(rel_path, target)
        key = config.rel_or_abs_posix(abs_path) if abs_path else target
        cites[key] = cites.get(key, 0) + 1

    lines = [f"# Neighbors of {rel_path} — {page.title}", ""]
    lines.append(f"## Links out ({len(out_links)})")
    lines += [f"- {resolved} — {title if title is not None else '(missing)'}" for resolved, title in out_links] or [
        "- (none)"
    ]
    lines.append("")
    lines.append(f"## Linked from ({len(inbound)})")
    lines += [f"- {src} — {titles.get(src, '')}" for src in inbound] or ["- (none)"]
    lines.append("")
    lines.append(f"## Cites sources ({len(cites)})")
    lines += [f"- {key} — {cites[key]} citation{'s' if cites[key] != 1 else ''}" for key in sorted(cites)] or [
        "- (none)"
    ]
    return "\n".join(lines) + "\n"


def _aliases_of(page: Page) -> set[str]:
    """Lowercased, stripped ``aliases`` frontmatter of a page (empty set when absent/malformed).
    Aliases are alternate lookup keys — an abbreviation's spelled-out form, a synonym title — so
    :func:`define_text` can match either the short or the long form."""
    aliases = page.frontmatter.get("aliases") or []
    if not isinstance(aliases, list):
        return set()
    return {str(a).strip().lower() for a in aliases if str(a).strip()}


def define_text(term: str, pages: list[Page] | None = None) -> str:
    """Glossary lookup — the text behind ``wiki_define`` / ``citadel define``. A short "what does X
    stand for / mean" is a LOOKUP, not full-text retrieval, so this surfaces the definition directly
    instead of a ranked page list.

    Three tiers, most specific first: (1) the **Abbreviations glossary** — every ``type:
    Abbreviation`` page whose short form, expansion, title, or an alias equals ``term`` (rendered
    ``SHORT — Expansion`` via :func:`okf.abbrev_short_long`); (2) an **exact-title / alias boost** —
    any page (any type) whose title or an alias equals ``term``, the definitional page for that
    concept; (3) a **fallback** to the closest :func:`search` hits, so the lookup still points
    somewhere when nothing matches exactly. Case-insensitive throughout; results are ordered
    deterministically by rel_path. Never raises."""
    query = (term or "").strip()
    if not query:
        return "error: empty term"
    needle = query.lower()
    if pages is None:
        pages = load()

    # Tier 1: the Abbreviations glossary the index already builds — exact short/expansion/title/alias.
    abbrev_hits: list[tuple[str, str, Page]] = []
    for page in pages:
        if (page.type or "").strip().lower() != "abbreviation":
            continue
        short, expansion = okf.abbrev_short_long(page)
        forms = {short.strip().lower(), expansion.strip().lower(), page.title.strip().lower()}
        forms |= _aliases_of(page)
        forms.discard("")
        if needle in forms:
            abbrev_hits.append((short, expansion, page))
    abbrev_hits.sort(key=lambda h: (h[0].lower(), h[2].rel_path))
    if abbrev_hits:
        lines = [f"# Definition: {query}", ""]
        for short, expansion, page in abbrev_hits:
            lines.append(f"## {short} — {expansion}")
            lines.append(f"- Page: {page.rel_path} — {page.title}")
            if page.description.strip():
                lines.append(f"- {page.description.strip()}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    # Tier 2: exact-title / alias boost — the definitional page for a concept, any type.
    exact = [p for p in pages if needle == p.title.strip().lower() or needle in _aliases_of(p)]
    exact.sort(key=lambda p: p.rel_path)
    if exact:
        lines = [f"# Definition: {query}", ""]
        for page in exact:
            kind = (page.type or "").strip() or "page"
            lines.append(f"## {page.title} ({kind})")
            lines.append(f"- Page: {page.rel_path}")
            if page.description.strip():
                lines.append(f"- {page.description.strip()}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    # Tier 3: no exact definition — point at the closest full-text hits so the lookup still helps.
    hits = search(query, pages=pages, limit=5)
    lines = [f"# Definition: {query}", "", f"No glossary entry or exact-title page for {query!r}."]
    if hits:
        lines.append("")
        lines.append("Closest pages:")
        lines += [f"- {p.rel_path} — {p.title}" for p, _ in hits]
    return "\n".join(lines) + "\n"


def index_text() -> str:
    """The generated ``wiki/index.md`` catalog text. Raises FileNotFoundError when no index exists
    yet (nothing ingested), or an OS error when the path is unreadable."""
    return config.INDEX_PATH.read_text(encoding="utf-8")


def sources_text() -> str:
    """The generated ``wiki/sources/index.md`` provenance catalog text. Raises FileNotFoundError
    when nothing has been ingested yet, or an OS error when the path is unreadable."""
    return config.SOURCES_INDEX_PATH.read_text(encoding="utf-8")


def _is_reserved_name(rel_path: str) -> bool:
    """True for the generated/reserved files that write_page and delete_page must refuse:
    any ``index.md``/``log.md`` basename (at ANY depth — exactly the set :func:`is_skipped_name`
    hides from ``load()``, so a writable-but-never-loaded ghost page like ``foo/log.md`` cannot
    exist), dotfiles, and the empty path. Shared by both mutators so a restructure or a
    programmatic write can never clobber the catalog, the log, or the manifest."""
    rel = rel_path.replace("\\", "/")  # okf.safe_join treats backslash as a separator on Windows
    name = rel.rsplit("/", 1)[-1] if rel else ""
    return not rel or is_skipped_name(name)


def write_page(rel_path: str, frontmatter: dict, body: str) -> Page:
    """okf.validate(frontmatter); target = okf.safe_join(WIKI_DIR, rel_path)
    (rejects '..'/absolute FIRST); mkdir -p; set frontmatter['timestamp']=utc_now_iso() and
    frontmatter['citadel_version']=__version__ (which cite-citadel release last wrote the page —
    provenance a reader/curate can compare against the installed version, stamped like the
    timestamp so it can never go stale or be authored by hand);
    write okf.dump(frontmatter, body). Return the Page. Overwrites if exists.

    Refuses the generated/reserved files (index.md, any per-folder ``*/index.md``, log.md,
    dotfiles) with the SAME guard as delete_page, so a programmatic write (e.g. curate) can never
    clobber the catalog, the log, or the manifest."""
    if _is_reserved_name(rel_path):
        raise okf.OKFError(f"refusing to write protected file: {rel_path!r}")
    okf.validate(frontmatter)
    target = okf.safe_join(config.WIKI_DIR, rel_path)
    config.robust_mkdir(target.parent)
    frontmatter = dict(frontmatter)
    frontmatter["timestamp"] = utc_now_iso()
    frontmatter["citadel_version"] = __version__
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")
    return Page(rel_path=rel_path, frontmatter=frontmatter, body=body)


def delete_page(rel_path: str) -> bool:
    """Delete a wiki page, path-safely. Refuses the generated/reserved files
    (index.md, any per-folder */index.md, log.md, dotfiles) so a restructure can never
    remove the catalog, the log, or the manifest. Returns True if a file was removed,
    False if it did not exist (idempotent — a delete of an already-gone page is a no-op,
    not an error). Path-safety reuses the exact okf.safe_join guard that write_page uses.
    Leaves a now-empty parent folder on disk; rebuild_indexes only emits a per-folder
    index for folders that still hold pages and load() ignores index.md, so an empty
    folder is inert and drops out of the catalog on the next rebuild."""
    if _is_reserved_name(rel_path):
        raise okf.OKFError(f"refusing to delete protected file: {rel_path!r}")
    target = okf.safe_join(config.WIKI_DIR, rel_path)  # rejects ''/absolute/'..'
    if target.is_file():
        target.unlink()
        return True
    return False


def tag_catalog(pages: list[Page] | None = None) -> dict[str, list[Page]]:
    """Map each lowercased tag -> the pages carrying it (the OKF-native ``tags``
    frontmatter field). The basis for the index.md Tags section and the CLI/MCP
    tag browse surfaces. Pages within a tag are sorted by rel_path."""
    if pages is None:
        pages = load()
    by_tag: dict[str, list[Page]] = {}
    for page in pages:
        for tag in page.tags:
            key = str(tag).strip().lower()
            if key:
                by_tag.setdefault(key, []).append(page)
    for key in by_tag:
        by_tag[key].sort(key=lambda p: p.rel_path)
    return by_tag


def append_log(line: str) -> None:
    """Append an entry to LOG_PATH in OKF style: a frontmatter-free ``log.md`` whose
    entries are grouped under ``## YYYY-MM-DD`` date headings (per the OKF reserved-file
    convention). A new date heading is opened the first time a given UTC day is logged;
    prior lines are never rewritten (append-only audit trail)."""
    log_path = config.LOG_PATH
    config.robust_mkdir(log_path.parent)
    now = datetime.now(timezone.utc)
    day, stamp = now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%SZ")
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    if not existing:
        existing = "# Log\n"
        log_path.write_text(existing, encoding="utf-8")
    with open(log_path, "a", encoding="utf-8") as fh:
        if f"## {day}" not in existing:
            fh.write(f"\n## {day}\n")
        fh.write(f"- {stamp} {line}\n")
