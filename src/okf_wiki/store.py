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
# A relative markdown link whose target ends in '.md' (mirrors lint.LINK_RE). Used to
# find cross-links for broken-link detection and link rewriting after a restructure.
_MD_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")


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


def delete_page(rel_path: str) -> bool:
    """Delete a wiki page, path-safely. Refuses the generated/reserved files
    (index.md, any per-folder */index.md, log.md, dotfiles) so a restructure can never
    remove the catalog, the log, or the manifest. Returns True if a file was removed,
    False if it did not exist (idempotent — a delete of an already-gone page is a no-op,
    not an error). Path-safety reuses the exact okf.safe_join guard that write_page uses.
    Leaves a now-empty parent folder on disk; rebuild_indexes only emits a per-folder
    index for folders that still hold pages and load() ignores index.md, so an empty
    folder is inert and drops out of the catalog on the next rebuild."""
    name = rel_path.rsplit("/", 1)[-1] if rel_path else ""
    if (
        not rel_path
        or rel_path in ("index.md", "log.md")
        or rel_path.endswith("/index.md")
        or name.startswith(".")
    ):
        raise okf.OKFError(f"refusing to delete protected file: {rel_path!r}")
    target = okf.safe_join(config.WIKI_DIR, rel_path)  # rejects ''/absolute/'..'
    if target.is_file():
        target.unlink()
        return True
    return False


def _resolved_md_links(rel_path: str, body: str) -> list[tuple[str, str]]:
    """Every relative .md cross-link in ``body`` as ``(raw_target, resolved_rel_path)``.

    ``raw_target`` is the link text as written (e.g. ``'./b.md'``); ``resolved_rel_path``
    is its wiki-root-relative identity via okf.resolve_link. Skips external links,
    anchors, and links into the raw/ source tree (the ## Sources footnotes)."""
    out: list[tuple[str, str]] = []
    for match in _MD_LINK_RE.finditer(body):
        raw_target = match.group(1).strip()
        if "://" in raw_target or raw_target.startswith("#"):
            continue
        resolved = okf.resolve_link(rel_path, raw_target)
        # A resolved path that escapes the wiki root (starts with '..') is a source
        # citation into the sibling raw/ or docs/ tree (e.g. '../../raw/x.md' from a
        # concepts/ page resolves to '../raw/x.md'), NOT a wiki cross-link — skip it.
        if resolved.startswith("..") or resolved.split("/", 1)[0] in ("raw", "docs"):
            continue
        out.append((raw_target, resolved))
    return out


def _follow_rename(resolved: str, rename_map: dict[str, str]) -> str:
    """Follow a (possibly multi-hop) chain of renames to a stable destination,
    guarding against cycles."""
    dest = resolved
    seen: set[str] = set()
    while dest in rename_map and dest not in seen:
        seen.add(dest)
        dest = rename_map[dest]
    return dest


def _rewrite_body_links(rel_path: str, body: str, rename_map: dict[str, str]) -> str:
    """Return ``body`` with every cross-link that resolves to a key of ``rename_map``
    repointed at the mapped survivor, as a fresh relative link from ``rel_path``.

    The rewrite is span-based (``re.sub`` over only the ``](...md)`` link spans) and skips
    fenced code blocks, so it touches ONLY genuine cross-links — never a literal ``](x.md)``
    written in prose or a code example, and never a partial substring of a larger token.
    Whitespace inside the parens is handled because the whole matched span is replaced.
    Untouched links and all other text are left byte-for-byte intact."""

    def repl(match: re.Match) -> str:
        raw_target = match.group(1).strip()
        if "://" in raw_target or raw_target.startswith("#"):
            return match.group(0)
        resolved = okf.resolve_link(rel_path, raw_target)
        if resolved.startswith("..") or resolved.split("/", 1)[0] in ("raw", "docs"):
            return match.group(0)  # source citation, not a wiki cross-link
        dest = _follow_rename(resolved, rename_map)
        if dest == resolved:
            return match.group(0)
        return f"]({okf.rel_path_between(rel_path, dest)})"

    out: list[str] = []
    in_fence = False
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append(line if in_fence else _MD_LINK_RE.sub(repl, line))
    return "".join(out)


def rewrite_links(rename_map: dict[str, str], pages: list[Page] | None = None) -> list[str]:
    """Repoint every inbound cross-link after a rename / split / merge so NO link breaks.

    ``rename_map`` maps an OLD page rel_path -> the NEW rel_path that absorbs its inbound
    links. For each wiki page, any relative .md link resolving to an OLD key is rewritten
    to point at the survivor. This is the deterministic guarantee that restructuring keeps
    links working — the model proposes the restructure, the store does the link
    bookkeeping. Only pages whose body actually changes are written back, and they are
    written with okf.dump (preserving frontmatter, NOT re-stamping the timestamp or
    re-validating), since a mechanical link fix is not a content edit. Returns the
    rel_paths that were changed."""
    if not rename_map:
        return []
    if pages is None:
        pages = load()
    changed: list[str] = []
    for page in pages:
        new_body = _rewrite_body_links(page.rel_path, page.body, rename_map)
        if new_body != page.body:
            target = okf.safe_join(config.WIKI_DIR, page.rel_path)
            target.write_text(okf.dump(page.frontmatter, new_body), encoding="utf-8")
            changed.append(page.rel_path)
    return changed


def find_broken_links(pages: list[Page] | None = None) -> list[tuple[str, str]]:
    """Every relative .md cross-link whose target page does not exist, as
    ``(source_rel_path, resolved_target)``. The 'links keep working' gate: ingest surfaces
    this in its report and lint flips its exit code on it. Sorted for stable output."""
    if pages is None:
        pages = load()
    paths = {p.rel_path for p in pages}
    broken: list[tuple[str, str]] = []
    for page in pages:
        for _raw_target, resolved in _resolved_md_links(page.rel_path, page.body):
            if resolved not in paths:
                broken.append((page.rel_path, resolved))
    return sorted(broken)


def _inbound_map(pages: list[Page]) -> dict[str, list[str]]:
    """For each page rel_path, the sorted list of OTHER pages that link to it (the
    backlink / 'referenced by' graph), built from the actual wiki cross-links."""
    paths = {p.rel_path for p in pages}
    inbound: dict[str, list[str]] = {p.rel_path: [] for p in pages}
    for page in pages:
        for _raw, resolved in _resolved_md_links(page.rel_path, page.body):
            if resolved in paths and resolved != page.rel_path:
                inbound[resolved].append(page.rel_path)
    return {k: sorted(set(v)) for k, v in inbound.items()}


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


def rebuild_indexes(pages: list[Page] | None = None) -> None:
    """Regenerate the OKF navigation files from the loaded pages (no LLM).

    Per OKF v0.1, ``index.md`` is the reserved progressive-disclosure file and **carries
    NO frontmatter** — so these are written as plain markdown. The top-level
    ``WIKI_DIR/index.md`` groups pages by type, adds a backlink ('↳ referenced by') line
    per page from the real link graph, and ends with a ``## Tags`` section that lists each
    OKF ``tags`` value and its pages (tags become a browse-by-topic navigation axis without
    inventing a non-reserved file). Each folder also gets a frontmatter-free ``index.md``.
    Deterministic ordering by rel_path keeps diffs small; index.md files are skipped by
    load()."""
    if pages is None:
        pages = load()
    pages = sorted(pages, key=lambda p: p.rel_path)
    title_by_path = {p.rel_path: p.title for p in pages}
    inbound = _inbound_map(pages)

    # ----- top-level wiki/index.md (NO frontmatter — OKF reserved nav file) -----
    by_type: dict[str, list[Page]] = {}
    for page in pages:
        by_type.setdefault(page.type or "Untyped", []).append(page)

    folders: dict[str, list[Page]] = {}
    for page in pages:
        if "/" in page.rel_path:
            folders.setdefault(page.rel_path.split("/", 1)[0], []).append(page)

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
            lines.append(f"- [{page.title}]({page.rel_path}) — {page.description}")
            refs = inbound.get(page.rel_path, [])
            if refs:
                reflinks = ", ".join(
                    f"[{title_by_path.get(r, r)}]({r})" for r in refs
                )
                lines.append(f"  - ↳ referenced by: {reflinks}")
        lines.append("")

    by_tag = tag_catalog(pages)
    if by_tag:
        lines.append("## Tags")
        lines.append("")
        for tag in sorted(by_tag):
            tagged = by_tag[tag]
            lines.append(f"### {tag} ({len(tagged)})")
            for page in tagged:
                lines.append(f"- [{page.title}]({page.rel_path})")
            lines.append("")

    body = "\n".join(lines).rstrip("\n") + "\n"
    config.WIKI_DIR.mkdir(parents=True, exist_ok=True)
    (config.WIKI_DIR / "index.md").write_text(body, encoding="utf-8")

    # ----- per-directory index.md (also frontmatter-free) -----
    for folder in sorted(folders):
        folder_pages = sorted(folders[folder], key=lambda p: p.rel_path)
        flines: list[str] = [f"# {folder}", ""]
        for page in folder_pages:
            rel_in_folder = page.rel_path[len(folder) + 1 :]
            flines.append(f"- [{page.title}]({rel_in_folder}) — {page.description}")
        flines.append("")
        fbody = "\n".join(flines).rstrip("\n") + "\n"
        folder_dir = config.WIKI_DIR / folder
        folder_dir.mkdir(parents=True, exist_ok=True)
        (folder_dir / "index.md").write_text(fbody, encoding="utf-8")


def append_log(line: str) -> None:
    """Append an entry to LOG_PATH in OKF style: a frontmatter-free ``log.md`` whose
    entries are grouped under ``## YYYY-MM-DD`` date headings (per the OKF reserved-file
    convention). A new date heading is opened the first time a given UTC day is logged;
    prior lines are never rewritten (append-only audit trail)."""
    log_path = config.LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
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
