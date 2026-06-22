"""The 'database' = the wiki/ directory loaded into memory.

Loads every .md under wiki/ (skipping index.md, log.md, per-directory index.md,
dotfiles) into Page objects; offers a dead-simple keyword scan (the ONE swappable
search function); writes/overwrites pages with path-safety; regenerates the
top-level index.md AND each per-directory index.md mechanically from frontmatter;
appends timestamped lines to log.md. No SQLite, no embeddings.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from . import config
from . import okf
from .okf import Page

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def utc_now_iso() -> str:
    """Return the current UTC time as 'YYYY-MM-DDTHH:MM:SSZ'."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_skipped_name(name: str) -> bool:
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
            if _is_skipped_name(name):
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


def search(
    query: str,
    pages: list[Page] | None = None,
    limit: int = 8,
) -> list[tuple[Page, float]]:
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
        if raw_query and (
            raw_query in page.title.lower() or raw_query in page.body.lower()
        ):
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


def write_page(rel_path: str, frontmatter: dict, body: str) -> Page:
    """okf.validate(frontmatter); target = okf.safe_join(WIKI_DIR, rel_path)
    (rejects '..'/absolute FIRST); mkdir -p; set frontmatter['timestamp']=utc_now_iso();
    write okf.dump(frontmatter, body). Return the Page. Overwrites if exists."""
    okf.validate(frontmatter)
    target = okf.safe_join(config.WIKI_DIR, rel_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = dict(frontmatter)
    frontmatter["timestamp"] = utc_now_iso()
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")
    return Page(rel_path=rel_path, frontmatter=frontmatter, body=body)


def rebuild_indexes(pages: list[Page] | None = None) -> None:
    """If pages is None, load(). (1) Write WIKI_DIR/index.md (type:Index, body groups
    pages by type with one bullet each '- [Title](RELPATH) — description', RELPATH
    relative to wiki root). (2) For each folder that contains pages, write
    folder/index.md (type:Index, bullets relative to that folder). Deterministic
    ordering by rel_path so diffs stay small. index.md files are skipped by load()."""
    if pages is None:
        pages = load()
    pages = sorted(pages, key=lambda p: p.rel_path)

    # ----- top-level wiki/index.md -----
    by_type: dict[str, list[Page]] = {}
    for page in pages:
        type_ = page.type or "Untyped"
        by_type.setdefault(type_, []).append(page)

    # Which folders contain pages (for the "See also" line + per-dir indexes).
    folders: dict[str, list[Page]] = {}
    for page in pages:
        if "/" in page.rel_path:
            folder = page.rel_path.split("/", 1)[0]
            folders.setdefault(folder, []).append(page)

    lines: list[str] = ["# Wiki Index", ""]
    if folders:
        seealso = " · ".join(
            f"[{folder}]({folder}/index.md)" for folder in sorted(folders)
        )
        lines.append(f"See also: {seealso}")
        lines.append("")
    for type_ in sorted(by_type):
        lines.append(f"## {type_}")
        for page in by_type[type_]:
            lines.append(
                f"- [{page.title}]({page.rel_path}) — {page.description}"
            )
        lines.append("")
    body = "\n".join(lines).rstrip("\n") + "\n"

    index_text = okf.dump({"type": "Index"}, body)
    config.WIKI_DIR.mkdir(parents=True, exist_ok=True)
    (config.WIKI_DIR / "index.md").write_text(index_text, encoding="utf-8")

    # ----- per-directory index.md -----
    for folder in sorted(folders):
        folder_pages = sorted(folders[folder], key=lambda p: p.rel_path)
        flines: list[str] = [f"# {folder}", ""]
        for page in folder_pages:
            # Link relative to the folder: strip the leading "<folder>/".
            rel_in_folder = page.rel_path[len(folder) + 1 :]
            flines.append(
                f"- [{page.title}]({rel_in_folder}) — {page.description}"
            )
        flines.append("")
        fbody = "\n".join(flines).rstrip("\n") + "\n"
        ftext = okf.dump({"type": "Index"}, fbody)
        folder_dir = config.WIKI_DIR / folder
        folder_dir.mkdir(parents=True, exist_ok=True)
        (folder_dir / "index.md").write_text(ftext, encoding="utf-8")


def append_log(line: str) -> None:
    """Append '- {utc_now_iso()} {line}\\n' to LOG_PATH (create with a type:Log
    header if missing). Never rewrites prior lines."""
    log_path = config.LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        header = okf.dump({"type": "Log"}, "# Log\n")
        log_path.write_text(header, encoding="utf-8")
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(f"- {utc_now_iso()} {line}\n")
