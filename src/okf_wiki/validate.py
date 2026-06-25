"""Per-page validators for links, file format, and required fields (no LLM, no network).

Since ingest now lets a coding-agent CLI write the wiki page files **directly**, the
mechanical guarantees the old structured-output path enforced in Python (required fields,
honest citations, relative non-broken links) must be re-imposed by checking each page the
agent touched. This module is that checker, used in three places against ONE implementation:

  1. the ingest gate — ``ingest`` runs ``validate_page`` on every changed page and collects
     ``error``-severity issues into its report (so a forgotten field fails the run);
  2. the agent self-check — ``okf-wiki check`` / the MCP ``wiki_validate`` tool, which the
     ingest agent is told to run on its edits *before finishing* and fix what it forgot;
  3. ``lint`` — reuses :func:`source_issues` and :func:`wikilink_targets` for whole-wiki health.

``validate_page`` checks a single page in isolation (fields, format, citation provenance,
link FORM). Whether a cross-link RESOLVES to an existing page needs the whole page set, so
that lives in :func:`validate_all` (via ``store.find_broken_links``) and in ``lint``.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from . import config, okf, store
from .okf import Page

# STRICT — these frontmatter fields must be present and non-empty on every page.
REQUIRED_FIELDS = ("type", "title", "description", "tags", "resource")

# A [[wiki-style]] link — NOT allowed (the wiki uses relative markdown links).
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
# Tool-call / agent-transcript artifacts that must never leak into a wiki page body
# (an agentic CLI occasionally flushes these tokens at the end of a file it writes).
ARTIFACT_RE = re.compile(r"antml:|</?(?:invoke|function_calls|parameter|content)\b", re.IGNORECASE)
# A relative .md markdown link target (mirrors store._MD_LINK_RE / lint.LINK_RE).
_MD_LINK_RE = re.compile(r"\]\(([^)]+\.md)\)")

# --- citation/source parsing (moved here from lint so there is ONE implementation) ----
_DEF_LINE_RE = re.compile(r"^\s*\[\^([\w.-]+)\]:\s*(.*)$")
# First markdown link on a definition line; tolerates a <url> form and stops the URL at
# whitespace so a `(url "title")` link title is not swallowed into the path.
_DEF_LINK_RE = re.compile(r"\[[^\]]*\]\(\s*<?([^)\s>]+)>?")
# A footnote marker USED on a fact (not a definition — i.e. not followed by ':').
_USED_MARKER_RE = re.compile(r"\[\^([\w.-]+)\](?!:)")


@dataclass
class Issue:
    """One validation finding. ``severity`` is ``"error"`` (fails the gate) or
    ``"advisory"`` (surfaced, but does not fail)."""

    rel_path: str
    severity: str
    category: str
    detail: str


def source_issues(rel_path: str, body: str) -> list[str]:
    """Structural guard against fabricated/unverifiable provenance. Returns a detail string
    for each problem found:

      1. a raw-fact definition (``[^sN]``, not ``[^llmN]``) whose linked file does not exist;
      2. a raw-fact definition with no resolvable ``[..](path)`` link (bare/malformed line);
      3. a footnote marker used on a fact but never defined in ``## Sources``.

    Model-supplied (``[^llmN]``) facts are exempt — they cite "LLM", not a raw file. Purely
    STRUCTURAL: confirms a citation points at a real file and is defined; does NOT verify the
    cited file actually contains the fact. Definitions are read only inside the ``## Sources``
    section and code fences are skipped, so a page documenting the citation format is not
    falsely flagged. Resolution is by path math from the page's location under WIKI_DIR, so it
    works on synthetic (not-yet-written) pages too; only the cited SOURCE file must exist."""
    page_dir = os.path.dirname(str(config.WIKI_DIR / rel_path))
    in_fence = False
    in_sources = False
    defined: set[str] = set()
    used: set[str] = set()
    bad: list[str] = []

    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("#"):
            in_sources = bool(re.match(r"#+\s*sources\b", stripped, re.IGNORECASE))
            continue

        mdef = _DEF_LINE_RE.match(line)
        if mdef and in_sources:
            marker_id, rest = mdef.group(1), mdef.group(2)
            defined.add(marker_id)
            if marker_id.lower().startswith("llm"):
                continue  # model-supplied fact: cites "LLM", no raw file expected
            link = _DEF_LINK_RE.search(rest)
            if not link:
                bad.append(f"[^{marker_id}]: no resolvable source link")
                continue
            target = link.group(1).strip()
            if "://" in target or target.startswith("#"):
                continue
            resolved = os.path.normpath(os.path.join(page_dir, target))
            if not os.path.exists(resolved):
                bad.append(target)
            continue

        # Usage line: collect every marker that is not itself a definition.
        used.update(_USED_MARKER_RE.findall(line))

    # A fact tagged with a marker that is never defined is unverifiable provenance.
    for marker_id in sorted(used - defined):
        bad.append(f"[^{marker_id}] used but undefined")
    return bad


def wikilink_targets(body: str) -> list[str]:
    """Every ``[[wiki-style]]`` link in ``body`` (skipping fenced code blocks). These are
    NOT valid in this wiki — cross-links must be relative markdown links."""
    found: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        found.extend(m.strip() for m in WIKILINK_RE.findall(line))
    return found


def _backslash_links(body: str) -> list[str]:
    """Relative .md link targets written with backslashes (e.g. ``..\\raw\\x.md``) — these
    break cross-platform link resolution and must use forward slashes."""
    out: list[str] = []
    for match in _MD_LINK_RE.finditer(body):
        target = match.group(1).strip()
        if "\\" in target:
            out.append(target)
    return out


def validate_page(rel_path: str, frontmatter: dict, body: str) -> list[Issue]:
    """Validate one page in isolation. Returns a list of :class:`Issue`. ``error`` issues
    are: a missing/empty required field (type/title/description/tags/resource), a ``resource``
    that does not point at a real file, an embedded ``---`` frontmatter block in the body, a
    fabricated/undefined citation, a ``[[wiki-style]]`` link, or a backslash link path.
    ``advisory`` issues (folder routing, filename slug, tag case, See-also order) are surfaced
    but never fail the gate."""
    issues: list[Issue] = []

    def err(category: str, detail: str) -> None:
        issues.append(Issue(rel_path, "error", category, detail))

    def adv(category: str, detail: str) -> None:
        issues.append(Issue(rel_path, "advisory", category, detail))

    # --- required frontmatter fields (STRICT: all are errors) ---
    type_ = str(frontmatter.get("type") or "").strip()
    if not type_:
        err("missing_field", "missing required field: 'type'")
    if not str(frontmatter.get("title") or "").strip():
        err("missing_field", "missing required field: 'title'")
    if not str(frontmatter.get("description") or "").strip():
        err("missing_field", "missing required field: 'description'")

    tags = frontmatter.get("tags") or []
    tag_list = [t for t in tags if str(t).strip()] if isinstance(tags, list) else []
    if not tag_list:
        err("missing_field", "missing required field: 'tags' (need at least one)")
    else:
        for tag in tag_list:
            if str(tag) != str(tag).lower():
                adv("tag_case", f"tag is not lowercase: {tag!r}")

    resource = str(frontmatter.get("resource") or "").strip()
    if not resource:
        err("missing_field", "missing required field: 'resource'")
    elif ".." in resource.replace("\\", "/").split("/"):
        # A '..' traversal segment is never a valid source key (repo-relative or absolute).
        err("bad_resource", f"resource must not contain '..': {resource!r}")
    elif not config.source_path_for_key(resource).is_file():
        # source_path_for_key accepts BOTH a repo-relative key ('raw/notes.md') and an absolute
        # out-of-repo key ('T:/21_llmWiki/raw/notes.md' / '/mnt/share/raw/notes.md'), so a wiki
        # whose raw/ lives on a mounted network drive validates instead of being rejected.
        err("bad_resource", f"resource points at a missing file: {resource}")

    # --- file format ---
    # An embedded YAML frontmatter block in the body (the agent echoed it twice). After the
    # upstream okf.parse, a leading "---\nkey: val\n---" block in the BODY parses back to a
    # non-empty dict — a markdown thematic-break "---" does not, so no false positive.
    if okf.parse(body)[0]:
        err("embedded_frontmatter", "body contains a '---' YAML frontmatter block")

    artifact = ARTIFACT_RE.search(body)
    if artifact:
        err("artifact", "body contains a tool-call/transcript artifact: " + artifact.group(0))

    if type_:
        expected_folder = okf.folder_for_type(type_)
        folder = rel_path.split("/", 1)[0] if "/" in rel_path else ""
        if folder != expected_folder:
            adv(
                "routing",
                f"page is in {folder!r} but type {type_!r} routes to {expected_folder!r}",
            )
    title = str(frontmatter.get("title") or "").strip()
    if title:
        expected_name = okf.slugify(title) + ".md"
        name = rel_path.rsplit("/", 1)[-1]
        if name != expected_name:
            adv("filename", f"filename {name!r} does not match slug of title ({expected_name!r})")

    # --- citations / provenance ---
    for detail in source_issues(rel_path, body):
        err("bad_source", detail)

    # --- link form ---
    for wl in wikilink_targets(body):
        err("wikilink", f"[[wiki-style]] link is not allowed: [[{wl}]]")
    for bs in _backslash_links(body):
        err("backslash_link", f"link path uses backslashes (use '/'): {bs}")

    # See also must come before Sources (advisory).
    lower = body.lower()
    see = lower.find("## see also")
    src = lower.find("## sources")
    if see != -1 and src != -1 and see > src:
        adv("section_order", "'## See also' should come before '## Sources'")

    return issues


def validate_all(pages: list[Page] | None = None) -> list[Issue]:
    """Validate every page, then add broken-cross-link issues (which need the whole page set,
    so they can't be found per-page). Used by ``okf-wiki check`` and the ``wiki_validate``
    MCP tool."""
    if pages is None:
        pages = store.load()
    issues: list[Issue] = []
    for page in pages:
        issues.extend(validate_page(page.rel_path, page.frontmatter, page.body))
    for src, target in store.find_broken_links(pages):
        issues.append(Issue(src, "error", "broken_link", f"link target does not exist: {target}"))
    return issues


def has_errors(issues: list[Issue]) -> bool:
    """True if any issue is ``error`` severity."""
    return any(i.severity == "error" for i in issues)


def render_issues(issues: list[Issue]) -> str:
    """Human-readable report of issues, grouped by page, errors first. Deterministic."""
    if not issues:
        return "OK — no validation issues."
    ordered = sorted(
        issues, key=lambda i: (i.rel_path, 0 if i.severity == "error" else 1, i.category)
    )
    lines: list[str] = []
    current = None
    for issue in ordered:
        if issue.rel_path != current:
            current = issue.rel_path
            lines.append(f"{issue.rel_path}:")
        lines.append(f"  [{issue.severity}] {issue.category}: {issue.detail}")
    n_err = sum(1 for i in issues if i.severity == "error")
    n_adv = len(issues) - n_err
    lines.append("")
    lines.append(f"{n_err} error(s), {n_adv} advisory.")
    return "\n".join(lines)
