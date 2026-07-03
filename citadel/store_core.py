"""Core of the wiki 'database': load / read / write / delete / search + the text providers.

Loads every .md under wiki/ (skipping index.md, log.md, per-directory index.md, dotfiles) into
Page objects; offers a dead-simple keyword scan (the ONE swappable search function);
writes/overwrites pages with path-safety and a reserved-name guard; deletes pages; the shared
page/index/sources text providers behind the CLI and MCP surfaces; and the append-only log.md
writer. No SQLite, no embeddings. The link graph, catalogs, and open-points live in sibling
modules (:mod:`citadel.linkgraph`, :mod:`citadel.catalogs`, :mod:`citadel.open_points`); the
:mod:`citadel.store` facade re-exports the whole surface.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from . import config, okf
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


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, drop tokens shorter than 2 chars."""
    return {tok for tok in _TOKEN_RE.findall(text.lower()) if len(tok) >= 2}


def _score(query_tokens: set[str], page: Page) -> float:
    """Token-overlap score. title 3.0, tags 2.0, description 1.5, body 1.0, plus a
    0.5 substring bonus if the raw lowercased query appears in title/body. 0.0 == no
    match. (Note: the raw-query substring bonus is applied in search(), which knows
    the original query string; this helper handles the token-overlap weights.)"""
    if not query_tokens:
        return 0.0
    score = 0.0
    title_tokens = _tokenize(page.title)
    tag_tokens = _tokenize(" ".join(page.tags))
    desc_tokens = _tokenize(page.description)
    body_tokens = _tokenize(page.body)
    score += 3.0 * len(query_tokens & title_tokens)
    score += 2.0 * len(query_tokens & tag_tokens)
    score += 1.5 * len(query_tokens & desc_tokens)
    score += 1.0 * len(query_tokens & body_tokens)
    return score


def search(query: str, pages: list[Page] | None = None, limit: int = 8) -> list[tuple[Page, float]]:
    """THE single swappable search seam. If pages is None, call load(). Score every
    page (token overlap with title*3/tags*2/description*1.5/body*1.0 plus a 0.5
    substring bonus when the lowercased query appears in the title or body), drop
    zeros, sort desc by score then rel_path, return the top `limit` as (page, score).
    (Future: replace this body with SQLite FTS5 bm25 — signature + MCP surface
    stay identical.)"""
    if pages is None:
        pages = load()
    query_tokens = _tokenize(query)
    raw_query = query.strip().lower()
    scored: list[tuple[Page, float]] = []
    for page in pages:
        score = _score(query_tokens, page)
        if raw_query and (raw_query in page.title.lower() or raw_query in page.body.lower()):
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


def read_page_text(rel_path: str) -> str:
    """The full verbatim OKF text of one wiki page (frontmatter + body). Raises FileNotFoundError
    (no such page), okf.OKFError (unsafe/traversal path), or an OS/decoding error (an undecodable
    file) — the callers translate those into a CLI exit code or an MCP error string."""
    page = read_page(rel_path)
    return okf.dump(page.frontmatter, page.body)


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
    index.md, any per-folder ``*/index.md``, log.md, dotfiles, and the empty path. Shared by both
    mutators so a restructure or a programmatic write can never clobber the catalog, the log, or
    the manifest."""
    name = rel_path.rsplit("/", 1)[-1] if rel_path else ""
    return not rel_path or rel_path in ("index.md", "log.md") or rel_path.endswith("/index.md") or name.startswith(".")


def write_page(rel_path: str, frontmatter: dict, body: str) -> Page:
    """okf.validate(frontmatter); target = okf.safe_join(WIKI_DIR, rel_path)
    (rejects '..'/absolute FIRST); mkdir -p; set frontmatter['timestamp']=utc_now_iso();
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
