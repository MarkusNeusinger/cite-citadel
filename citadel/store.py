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
from . import manifest as manifest_mod
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


# A markdown link span ``](target)`` for ANY target (not only '.md'): citation links into the
# raw/ source tree now point at arbitrary file types (.py/.txt/.pdf/...), so repointing a moved
# source cannot assume the '.md' suffix that wiki cross-link rewriting relies on.
_ANY_LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _split_link_target(inner: str) -> tuple[str, str]:
    """Split a markdown link's parenthesized content into ``(path, suffix)``, where ``suffix`` is
    any trailing ``"title"`` (or empty for a ``<path>`` form) preserved verbatim on rewrite. e.g.
    ``'../../raw/x.md "note"'`` -> ``('../../raw/x.md', ' "note"')``; ``'<../../raw/x.md>'`` ->
    ``('../../raw/x.md', '')``."""
    inner = inner.strip()
    if inner.startswith("<"):
        end = inner.find(">")
        return (inner[1:end], "") if end != -1 else (inner, "")
    parts = inner.split(None, 1)
    return (parts[0], " " + parts[1]) if len(parts) == 2 else (inner, "")


def _link_abs(page_rel: str, target: str) -> str | None:
    """The absolute, lexically-normalized filesystem path a relative citation ``target`` in wiki
    page ``page_rel`` points at, or None for an external/anchor link. Lexical only (``normpath``,
    no symlink resolution) so it stays consistent with how source keys are formed and works on
    synthetic or not-yet-existing paths."""
    if "://" in target or target.startswith("#"):
        return None
    page_dir = os.path.dirname(str(config.WIKI_DIR / page_rel))
    return os.path.normpath(os.path.join(page_dir, target))


def _link_points_at_key(page_rel: str, target: str, key: str) -> bool:
    """True if the relative citation ``target`` written in wiki page ``page_rel`` resolves to the
    raw source identified by ``key`` — a repo-relative key (``raw/x.md``) OR an absolute
    out-of-repo key (``T:/team-wiki/raw/x.md``). Compares absolute paths with OS-appropriate case
    folding, so a ``../../raw/x.md`` citation matches its source whether the wiki and raw live in
    the repo or together on a mounted network drive. Replaces the old REPO_ROOT-relative resolver,
    which returned None for any citation that pointed outside the repo."""
    link_abs = _link_abs(page_rel, target)
    if link_abs is None:
        return False
    target_abs = str(config.source_path_for_key(key))
    return os.path.normcase(os.path.normpath(link_abs)) == os.path.normcase(
        os.path.normpath(target_abs)
    )


def _source_key_to_page_link(page_rel: str, key: str) -> str:
    """The relative markdown link FROM wiki page ``page_rel`` TO the raw source ``key`` (e.g. page
    ``concepts/a.md`` + key ``raw/sub/x.md`` -> ``../../raw/sub/x.md``). ``key`` may be absolute
    (out-of-repo): when the source and the wiki sit on the SAME volume — the network-drive case,
    e.g. both under ``T:/team-wiki`` — a normal relative link is produced; on the rare
    cross-volume layout where no relative path exists, fall back to the absolute POSIX path so the
    link still resolves rather than raising."""
    page_dir = os.path.dirname(str(config.WIKI_DIR / page_rel))
    target_abs = str(config.source_path_for_key(key))
    try:
        return os.path.relpath(target_abs, page_dir).replace(os.sep, "/")
    except ValueError:
        return target_abs.replace(os.sep, "/")


def _rewrite_raw_body_links(page_rel: str, body: str, old_rel: str, new_rel: str) -> str:
    """Return ``body`` with every citation link that resolves to the source key ``old_rel`` (a
    repo-relative or absolute out-of-repo key) repointed at ``new_rel`` (recomputed relative to
    ``page_rel``). Span-based and
    fence-aware, mirroring :func:`_rewrite_body_links`, so only genuine link spans are touched —
    never a literal ``](x)`` inside a code fence or a partial substring."""

    def repl(match: re.Match) -> str:
        path, suffix = _split_link_target(match.group(1))
        if not _link_points_at_key(page_rel, path, old_rel):
            return match.group(0)
        return f"]({_source_key_to_page_link(page_rel, new_rel)}{suffix})"

    out: list[str] = []
    in_fence = False
    for line in body.splitlines(keepends=True):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        out.append(line if in_fence else _ANY_LINK_RE.sub(repl, line))
    return "".join(out)


def rewrite_raw_references(
    old_rel: str, new_rel: str, pages: list[Page] | None = None
) -> list[str]:
    """Repoint every reference to a RAW SOURCE file after it was MOVED on disk, so the wiki keeps
    pointing at it. ``old_rel``/``new_rel`` are source keys — repo-relative posix paths (e.g.
    ``'raw/coffee.md'`` -> ``'raw/drinks/coffee.md'``) or, for an out-of-repo source on a mounted
    drive, absolute posix paths. For each page this updates the ``resource``
    frontmatter (when it named ``old_rel``) AND every ``[..](../../raw/old)`` citation link in the
    body. Only changed pages are written, mechanically (via okf.dump — no re-stamp, no re-validate),
    mirroring :func:`rewrite_links`. Returns the changed page rel_paths. This is the deterministic
    safety net that keeps `resource`/`[^sN]` provenance valid when raw sources are reorganized."""
    if old_rel == new_rel:
        return []
    if pages is None:
        pages = load()
    changed: list[str] = []
    for page in pages:
        frontmatter = page.frontmatter
        fm_changed = (
            str(frontmatter.get("resource") or "").strip().replace("\\", "/") == old_rel
        )
        if fm_changed:
            frontmatter = dict(frontmatter)
            frontmatter["resource"] = new_rel
        new_body = _rewrite_raw_body_links(page.rel_path, page.body, old_rel, new_rel)
        if fm_changed or new_body != page.body:
            target = okf.safe_join(config.WIKI_DIR, page.rel_path)
            target.write_text(okf.dump(frontmatter, new_body), encoding="utf-8")
            changed.append(page.rel_path)
    return changed


def find_raw_references(rel_key: str, pages: list[Page] | None = None) -> list[str]:
    """rel_paths of wiki pages that reference the raw source ``rel_key`` (a repo-relative key, or
    an absolute key for an out-of-repo source on a mounted drive) —
    either via the ``resource`` frontmatter or a citation link (``](../../raw/x.md)``) that
    resolves to it. Read-only companion to :func:`rewrite_raw_references`: ingest uses it to
    decide whether a DELETED source still has provenance worth a cleanup session, and to verify
    afterwards that the cleanup removed every reference (else it rolls the source back).

    Link detection is fence-aware (mirroring :func:`_rewrite_raw_body_links`), so a citation
    written as a literal inside a ``` code fence — e.g. a page documenting the citation format —
    is NOT counted, exactly as the rewriter would leave it untouched. Sorted for stable output."""
    target = rel_key.replace("\\", "/")
    if pages is None:
        pages = load()
    hits: list[str] = []
    for page in pages:
        if str(page.frontmatter.get("resource") or "").strip().replace("\\", "/") == target:
            hits.append(page.rel_path)
            continue
        in_fence = False
        for line in page.body.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            if any(
                _link_points_at_key(page.rel_path, _split_link_target(m.group(1))[0], target)
                for m in _ANY_LINK_RE.finditer(line)
            ):
                hits.append(page.rel_path)
                break
    return sorted(hits)


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


def _md_cell(text: str) -> str:
    """Escape a markdown-table cell: pipes would otherwise be read as column separators."""
    return str(text).replace("|", "\\|").strip()


SOURCES_INDEX_REL = "sources/index.md"


def _render_sources_catalog(
    manifest_dict: dict, pages: list[Page]
) -> str | None:
    """Render the body of ``wiki/sources/index.md`` — the provenance catalog.

    One row per tracked raw source (from the ingest manifest), showing the MODEL that imported it
    and the wiki pages that cite it (from the live link graph via :func:`find_raw_references`). The
    source path links to the raw file and each citing page links to its page, both relative to
    ``sources/index.md`` (so the links work from that file's location, in-repo or on a network
    drive). Like ``index.md``/``log.md`` this is a generated, frontmatter-free OKF nav file —
    load() skips it and delete_page refuses it.

    Returns the markdown body, or None when no source is tracked (the caller then removes any stale
    catalog) — so the catalog appears exactly when there is provenance to show."""
    if not manifest_dict:
        return None
    title_by_path = {p.rel_path: p.title for p in pages}
    lines: list[str] = [
        "# Sources",
        "",
        "Provenance for every ingested raw source: the model that imported it and the wiki "
        "pages that cite it. Generated — do not edit.",
        "",
        "| Source | Model | Referenced by |",
        "| --- | --- | --- |",
    ]
    for key in sorted(manifest_dict):
        model = manifest_mod.entry_model(manifest_dict[key]) or "—"
        source_cell = f"[{_md_cell(key)}]({_source_key_to_page_link(SOURCES_INDEX_REL, key)})"
        refs = find_raw_references(key, pages)
        if refs:
            ref_cell = ", ".join(
                f"[{_md_cell(title_by_path.get(r, r))}]"
                f"({okf.rel_path_between(SOURCES_INDEX_REL, r)})"
                for r in refs
            )
        else:
            ref_cell = "—"
        lines.append(f"| {source_cell} | {_md_cell(model)} | {ref_cell} |")
    return "\n".join(lines).rstrip("\n") + "\n"


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

    # ----- sources/index.md: the provenance catalog (source -> model + citing pages) -----
    # Generated from the ingest manifest (the model lives there) + the live link graph. Written
    # before the top index so its "See also" can link the catalog when it exists; removed when no
    # source is tracked so a stale catalog never lingers. The manifest is loaded once and reused
    # below for the index.md ## Sources section.
    manifest_dict = manifest_mod.load()
    sources_body = _render_sources_catalog(manifest_dict, pages)
    sources_path = config.WIKI_DIR / SOURCES_INDEX_REL
    if sources_body is not None:
        config.robust_mkdir(sources_path.parent)
        sources_path.write_text(sources_body, encoding="utf-8")
    elif sources_path.exists():
        sources_path.unlink()

    # ----- top-level wiki/index.md (NO frontmatter — OKF reserved nav file) -----
    by_type: dict[str, list[Page]] = {}
    for page in pages:
        by_type.setdefault(page.type or "Untyped", []).append(page)

    folders: dict[str, list[Page]] = {}
    for page in pages:
        if "/" in page.rel_path:
            folders.setdefault(page.rel_path.split("/", 1)[0], []).append(page)

    lines: list[str] = ["# Wiki Index", ""]
    seealso_parts = [f"[{folder}]({folder}/index.md)" for folder in sorted(folders)]
    if sources_body is not None:
        seealso_parts.append(f"[sources]({SOURCES_INDEX_REL})")
    if seealso_parts:
        lines.append(f"See also: {' · '.join(seealso_parts)}")
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

    # ----- ## Sources: the by-source provenance axis, surfaced IN index.md (not just a See-also
    # link). An agent reading index.md (e.g. via the wiki_index MCP tool, which never reached the
    # skipped sources/index.md) can now discover what was ingested and from where. -----
    if manifest_dict:
        lines.append("## Sources")
        lines.append("")
        lines.append(
            f"{len(manifest_dict)} ingested raw source(s) — full catalog with the importing "
            f"model in [sources/index.md]({SOURCES_INDEX_REL})."
        )
        lines.append("")
        for key in sorted(manifest_dict):
            refs = find_raw_references(key, pages)
            n = len(refs)
            cited = f"cited by {n} page{'s' if n != 1 else ''}" if n else "uncited"
            src_link = _source_key_to_page_link("index.md", key)
            lines.append(f"- [{_md_cell(key)}]({src_link}) — {cited}")
        lines.append("")

    # ----- ## Abbreviations: the glossary, generated from every type: Abbreviation page -----
    abbrev_pages = [p for p in pages if (p.type or "").strip().lower() == "abbreviation"]
    if abbrev_pages:
        def _cell(text: str) -> str:
            return text.replace("|", "\\|").strip()

        rows = [(okf.abbrev_short_long(p), p) for p in abbrev_pages]
        rows.sort(key=lambda r: (r[0][0].lower(), r[0][1].lower(), r[1].rel_path))
        lines.append("## Abbreviations")
        lines.append("")
        lines.append("| Abbreviation | Expansion | Page |")
        lines.append("| --- | --- | --- |")
        for (short, expansion), page in rows:
            lines.append(
                f"| {_cell(short)} | {_cell(expansion)} | "
                f"[{_cell(page.title)}]({page.rel_path}) |"
            )
        lines.append("")

    body = "\n".join(lines).rstrip("\n") + "\n"
    config.robust_mkdir(config.WIKI_DIR)
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
        config.robust_mkdir(folder_dir)
        (folder_dir / "index.md").write_text(fbody, encoding="utf-8")


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
