"""The wiki link graph: cross-link resolvers/rewriters, raw-source reference finders, backlink map.

The deterministic 'links keep working' machinery layered on top of :mod:`citadel.store_core`. The
model proposes a restructure (rename / split / merge) or a raw source moves on disk; these
functions do the mechanical link bookkeeping so NO citation or cross-link ever breaks. All the
body rewriters are span-based and fence-aware (via :mod:`citadel.grammar`), so only genuine link
spans are touched — never a literal ``](x)`` written in prose or inside a code fence. Reuse
:func:`okf.safe_join` and the rel-or-abs source-key space (:mod:`citadel.config`) for every path.
"""

from __future__ import annotations

import os
import re

from . import config, grammar, okf
from .okf import Page
from .store_core import load


def _norm(p) -> str:
    """The leaf normal form for OS-case-folded absolute-path comparison:
    ``normcase(normpath(str(p)))``. The single normalizer used by :func:`_link_points_at_key` and
    :func:`citing_pages_map` so the single-key finder and the batch map compute the SAME normal form
    structurally, not by proof."""
    return os.path.normcase(os.path.normpath(str(p)))


def _resource_norm(value) -> str:
    """The normal form for matching a ``resource`` frontmatter value against a source key: a
    stripped, forward-slashed string. Shared by :func:`find_raw_references`' resource comparison and
    :func:`citing_pages_map`'s resource index so both match a ``resource`` field to a key identically."""
    return str(value or "").strip().replace("\\", "/")


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
    fenced code blocks (via :func:`grammar.iter_lines`, the shared fence implementation), so it
    touches ONLY genuine cross-links — never a literal ``](x.md)`` written in prose or a code
    example, and never a partial substring of a larger token. Whitespace inside the parens is
    handled because the whole matched span is replaced. Untouched links and all other text are
    left byte-for-byte intact."""

    def repl(match: re.Match) -> str:
        raw_target = match.group(1).strip()
        if grammar.is_external(raw_target):
            return match.group(0)
        resolved = okf.resolve_link(rel_path, raw_target)
        if grammar.resolves_to_source(resolved):
            return match.group(0)  # source citation, not a wiki cross-link
        dest = _follow_rename(resolved, rename_map)
        if dest == resolved:
            return match.group(0)
        return f"]({okf.rel_path_between(rel_path, dest)})"

    out: list[str] = []
    for line, in_code in grammar.iter_lines(body, keepends=True):
        out.append(line if in_code else grammar.MD_LINK_RE.sub(repl, line))
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


def _link_points_at_key(page_rel: str, target: str, key: str) -> bool:
    """True if the relative citation ``target`` written in wiki page ``page_rel`` resolves to the
    raw source identified by ``key`` — a workspace-relative key (``raw/x.md``) OR an absolute
    out-of-workspace key (``T:/team-wiki/raw/x.md``). Compares absolute paths with OS-appropriate case
    folding, so a ``../../raw/x.md`` citation matches its source whether the wiki and raw live in
    the workspace or together on a mounted network drive. Replaces the old resolver, which compared
    root-relative paths and so returned None for any citation that pointed outside the root."""
    link_abs = grammar.link_abs(page_rel, target)
    if link_abs is None:
        return False
    target_abs = str(config.source_path_for_key(key))
    return _norm(link_abs) == _norm(target_abs)


def source_key_to_page_link(page_rel: str, key: str) -> str:
    """The relative markdown link FROM wiki page ``page_rel`` TO the raw source ``key`` (e.g. page
    ``concepts/a.md`` + key ``raw/sub/x.md`` -> ``../../raw/sub/x.md``). ``key`` may be absolute
    (out-of-repo): when the source and the wiki sit on the SAME volume — the network-drive case,
    e.g. both under ``T:/team-wiki`` — a normal relative link is produced; on the rare
    cross-volume layout where no relative path exists, fall back to the absolute POSIX path so the
    link still resolves rather than raising. Emitted through ``grammar.format_link_target``, so a
    key containing spaces comes back angle-wrapped — the ONE parseable citation form — and every
    emitter (the citation rewriter, sources/index.md, the index reflinks) stays round-trippable."""
    page_dir = os.path.dirname(str(config.WIKI_DIR / page_rel))
    target_abs = str(config.source_path_for_key(key))
    try:
        link = os.path.relpath(target_abs, page_dir).replace(os.sep, "/")
    except ValueError:
        link = target_abs.replace(os.sep, "/")
    return grammar.format_link_target(link)


def _rewrite_raw_body_links(page_rel: str, body: str, old_rel: str, new_rel: str) -> str:
    """Return ``body`` with every citation link that resolves to the source key ``old_rel`` (a
    repo-relative or absolute out-of-repo key) repointed at ``new_rel`` (recomputed relative to
    ``page_rel``). Span-based and
    fence-aware, mirroring :func:`_rewrite_body_links`, so only genuine link spans are touched —
    never a literal ``](x)`` inside a code fence or a partial substring."""

    def repl(match: re.Match) -> str:
        path, suffix = grammar.split_link_target(match.group(1))
        if not _link_points_at_key(page_rel, path, old_rel):
            return match.group(0)
        # source_key_to_page_link already emits through grammar.format_link_target, so a spacey
        # repointed target comes back angle-wrapped and the rewritten span always parses back.
        return f"]({source_key_to_page_link(page_rel, new_rel)}{suffix})"

    out: list[str] = []
    for line, in_code in grammar.iter_lines(body, keepends=True):
        out.append(line if in_code else grammar.ANY_LINK_RE.sub(repl, line))
    return "".join(out)


def rewrite_raw_references(old_rel: str, new_rel: str, pages: list[Page] | None = None) -> list[str]:
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
        fm_changed = str(frontmatter.get("resource") or "").strip().replace("\\", "/") == old_rel
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
    target = _resource_norm(rel_key)
    if pages is None:
        pages = load()
    hits: list[str] = []
    for page in pages:
        if _resource_norm(page.frontmatter.get("resource")) == target:
            hits.append(page.rel_path)
            continue
        for line in grammar.prose_lines(page.body):
            if any(
                _link_points_at_key(page.rel_path, grammar.split_link_target(m.group(1))[0], target)
                for m in grammar.ANY_LINK_RE.finditer(line)
            ):
                hits.append(page.rel_path)
                break
    return sorted(hits)


def citing_pages_map(keys, pages: list[Page] | None = None) -> dict[str, list[str]]:
    """The BATCH inverse of :func:`find_raw_references`: for every source ``key`` in ``keys``, the
    sorted rel_paths of wiki pages that reference it — built in ONE wiki-body traversal instead of
    one scan per key. :func:`rebuild_indexes` feeds BOTH the sources catalog and the index.md
    ``## Sources`` section from a single call, replacing the old O(sources × pages) scan run twice
    (docs/refactor-plan.md Z7).

    Matching shares the normal form with :func:`_link_points_at_key` by construction: a page
    references a key via its ``resource`` frontmatter (exact key-string equality) OR a citation link
    that resolves to the key's source path (absolute-path equality, OS-case-folded). Reuses the SAME
    grammar parsers (:func:`grammar.prose_lines`, :data:`grammar.ANY_LINK_RE`,
    :func:`grammar.split_link_target`, :func:`grammar.link_abs`) as the single-key finder — no second
    regex copy — the same ``config.source_path_for_key`` key→path mapping AND the same :func:`_norm`
    leaf and :func:`_resource_norm` helper as :func:`_link_points_at_key` / :func:`find_raw_references`.
    Fence-aware, so a citation inside a ``` code fence is not counted, exactly as the rewriter would
    leave it."""
    if pages is None:
        pages = load()
    keys = list(keys)
    result: dict[str, list[str]] = {key: [] for key in keys}
    if not keys:
        return result
    # Two match indices, computed once (mirroring find_raw_references's two match modes): the
    # resource-frontmatter path matches the key STRING (via _resource_norm); the citation-link path
    # matches the key's normalized absolute source path (source_path_for_key via _norm), the exact
    # normal form _link_points_at_key computes. Several keys can share a normalized value (a rel and
    # an abs key for the same file), so both indices map to a LIST of keys.
    resource_to_keys: dict[str, list[str]] = {}
    abs_to_keys: dict[str, list[str]] = {}
    for key in keys:
        resource_to_keys.setdefault(_resource_norm(key), []).append(key)
        key_abs = _norm(config.source_path_for_key(key))
        abs_to_keys.setdefault(key_abs, []).append(key)
    for page in pages:
        matched: set[str] = set()
        resource = _resource_norm(page.frontmatter.get("resource"))
        if resource in resource_to_keys:
            matched.update(resource_to_keys[resource])
        for line in grammar.prose_lines(page.body):
            for m in grammar.ANY_LINK_RE.finditer(line):
                link_abs = grammar.link_abs(page.rel_path, grammar.split_link_target(m.group(1))[0])
                if link_abs is None:
                    continue
                link_norm = _norm(link_abs)
                if link_norm in abs_to_keys:
                    matched.update(abs_to_keys[link_norm])
        for key in matched:
            result[key].append(page.rel_path)
    for key in result:
        result[key].sort()
    return result


def find_broken_links(pages: list[Page] | None = None) -> list[tuple[str, str]]:
    """Every relative .md cross-link whose target page does not exist, as
    ``(source_rel_path, resolved_target)``. The 'links keep working' gate: ingest surfaces
    this in its report and lint flips its exit code on it. Delegates to the shared
    :func:`grammar.resolved_md_links` (see grammar.py for the decided rules). Sorted for
    stable output."""
    if pages is None:
        pages = load()
    paths = {p.rel_path for p in pages}
    broken: list[tuple[str, str]] = []
    for page in pages:
        for _raw_target, resolved in grammar.resolved_md_links(page.rel_path, page.body):
            if resolved not in paths:
                broken.append((page.rel_path, resolved))
    return sorted(broken)


def inbound_map(pages: list[Page]) -> dict[str, list[str]]:
    """For each page rel_path, the sorted list of OTHER pages that link to it (the
    backlink / 'referenced by' graph), built from the actual wiki cross-links. Consumed by
    rebuild_indexes (the index.md '↳ referenced by' lines) and the offline viewer."""
    paths = {p.rel_path for p in pages}
    inbound: dict[str, list[str]] = {p.rel_path: [] for p in pages}
    for page in pages:
        for _raw, resolved in grammar.resolved_md_links(page.rel_path, page.body):
            if resolved in paths and resolved != page.rel_path:
                inbound[resolved].append(page.rel_path)
    return {k: sorted(set(v)) for k, v in inbound.items()}
