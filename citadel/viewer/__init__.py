"""A self-contained, offline, zero-dependency local viewer for the OKF wiki.

``build_html`` serializes the wiki — the pages, the cross-link graph, the tags, AND the cited
raw sources (their content embedded inline) — into ONE standalone HTML document with the bundle
embedded inline as JSON and a small hand-rolled markdown renderer + graph in inlined vanilla JS.
It opens from ``file://`` with **no web server and no network**: nothing is fetched from a CDN,
so the wiki data never leaves the machine. No third-party code is vendored.

Sources are first-class: every ``[..](../../raw/x.md)`` citation and ``## Sources`` footnote is a
clickable link that opens the cited raw file — rendered, in the same reader — and a hover preview
peeks at it. The raw file content is embedded too, so opening a source stays fully offline. A
"Sources" axis in the sidebar and an optional source layer in the graph make provenance browsable.

Provenance is also legible at a glance: each page carries counts (``cites`` / ``llm`` /
``contradictions``) that the viewer renders as sidebar badges, quick-filter chips ("Contradictions",
"LLM notes"), and a reader summary with jump-to affordances. The sidebar search is a real
**full-text** search over every page/source body (ranked, with match snippets), and opening a
result highlights and scrolls to the hit.

Built to be browsed like a real wiki (Obsidian-style): the reader is a centered column with a
comfortable/wide/full width toggle; the interactive graph legend hides or shows any category (each
page type and the source layer) with live counts; the map can be collapsed, dragged to any height,
or expanded to full height for close inspection, and hovering a node dims all but its neighbours;
tags collapse into a compact counted dropdown; a page shows both its inbound ("Referenced by:") and
outbound ("Links to:") links; the open page is highlighted in the sidebar; and there is a random-page
button, a collapsible sidebar (backslash-key shortcut) for a focus/reading mode, and an auto/light/dark theme
toggle. All of this is client-side state persisted in ``localStorage``; the embedded data is untouched.

The only LLM-free, read-only consumer of the wiki besides search/lint. Reuses
``store.load`` / ``store.inbound_map`` / ``store.tag_catalog`` / ``store.find_raw_references``
and the shared citation/link/fence grammar (:mod:`citadel.grammar`) so the graph, tags, and
provenance always match the rest of the system.

The document shell, stylesheet, and viewer script are REAL files shipped as package data next to
this module (``template.html`` / ``app.css`` / ``app.js``) and read at build time via
``importlib.resources`` — editable as HTML/CSS/JS, not as Python string literals.

Public surface: ``build_bundle`` (pure data, the test seam), ``build_html`` (the document),
``write_viewer`` (writes ``wiki/.citadel_viewer.html``), and ``view`` (CLI entry — write, open,
print the path; degrades gracefully when no browser is available, e.g. under WSL).
"""

from __future__ import annotations

import json
import os
import re
import webbrowser
from importlib import resources
from pathlib import Path

from .. import config, extract, grammar, store
from .. import manifest as manifest_mod


# Default output: dot-prefixed so store.load() skips it (like .citadel_ingested.json) and it is
# gitignored; it is a regenerable artifact, never a source of truth.
VIEWER_FILENAME = ".citadel_viewer.html"

# A single embedded source is capped so a pathologically large raw file (a big PDF/CSV dump or a
# repo digest) can't bloat the standalone document without bound; the body is truncated with a
# marker and the viewer flags it. Generous enough that ordinary notes embed whole.
_SOURCE_MAX_CHARS = 200_000

# First markdown ATX heading in a raw source — used as its human title when present.
_HEADING_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def _page_stats(body: str) -> tuple[int, int, int]:
    """``(raw_citations, llm_facts, contradictions)`` for one page body — the counts the viewer
    shows as per-page sidebar badges and filters by. Counts only *prose* (the shared
    ``grammar.prose_lines`` view): it skips fenced code blocks and the trailing ``## Sources``
    section, so a marker or ``[!CONTRADICTION]`` written as a literal example — e.g. on a page
    documenting the citation format — is not miscounted, and a ``[^sN]`` mentioned inside another
    footnote's definition note is not mistaken for an inline use. An *inline* marker is one the
    guarded ``grammar.USED_MARKER_RE`` matches (a use, not a stray definition)."""
    cites = llm = contradictions = 0
    for line in grammar.prose_lines(body, skip_sources=True):
        if line.lstrip().startswith("#"):  # headings carry no citation markers to count
            continue
        for match in grammar.USED_MARKER_RE.finditer(line):
            if grammar.is_llm_marker(match.group(1)):
                llm += 1
            else:
                cites += 1
        if grammar.CONTRADICTION_LINE_RE.match(line):
            contradictions += 1
    return cites, llm, contradictions


def build_bundle(pages=None) -> dict:
    """Build the JSON-serializable bundle from the loaded wiki (pure data; no HTML, no I/O
    beyond ``store.load()`` and reading the cited raw sources). Deterministic — no timestamps —
    so a generated document round-trips back to this dict in tests."""
    if pages is None:
        pages = store.load()
    paths = {p.rel_path for p in pages}
    inbound = store.inbound_map(pages)

    pages_json: list[dict] = []
    edges: list[dict] = []
    types: dict[str, list[str]] = {}
    for page in pages:
        outbound = sorted(
            {resolved for _raw, resolved in grammar.resolved_md_links(page.rel_path, page.body) if resolved in paths}
        )
        for target in outbound:
            edges.append({"source": page.rel_path, "target": target})
        types.setdefault(page.type or "Untyped", []).append(page.rel_path)
        cites, llm, contradictions = _page_stats(page.body)
        pages_json.append(
            {
                "rel_path": page.rel_path,
                "type": page.type or "Untyped",
                "title": page.title,
                "description": page.description,
                "tags": list(page.tags),
                "body": page.body,
                "outbound": outbound,
                "inbound": inbound.get(page.rel_path, []),
                # Per-page provenance counts for the sidebar badges + contradiction/LLM filters.
                "cites": cites,
                "llm": llm,
                "contradictions": contradictions,
            }
        )

    tags = {tag: [p.rel_path for p in tagged] for tag, tagged in store.tag_catalog(pages).items()}
    return {
        "wiki_name": config.WIKI_DIR.name,
        "pages": pages_json,
        "edges": edges,
        "tags": tags,
        "types": {k: sorted(v) for k, v in types.items()},
        "sources": _build_sources(pages),
    }


# --------------------------------------------------------------------------------------
# Sources: discover every cited raw file, embed its content, and key it by the identity the
# in-browser link resolver produces so an inline citation can open it without any I/O.
# --------------------------------------------------------------------------------------


def _viewer_resolve(from_rel: str, target: str) -> str:
    """Python port of the viewer's in-browser ``resolveLink``: resolve a citation ``target`` written
    in page ``from_rel`` to a wiki-root-relative posix id, CLAMPING any ``..`` that would climb above
    the wiki root (a no-op pop on an empty stack, exactly like ``Array.pop`` in JS). This is the
    single identity under which an embedded source is keyed AND under which the browser looks it up,
    so a citation resolves to its source no matter how the wiki and raw trees are laid out (in-repo,
    a nested ``sub/wiki``, or a mounted network drive)."""
    target = target.split("#", 1)[0]
    base = from_rel.rsplit("/", 1)[0] if "/" in from_rel else ""
    parts = base.split("/") if base else []
    for seg in target.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def _source_view_id(abs_path: str | os.PathLike) -> str:
    """The identity the BROWSER link resolver yields for a source, so an inline ``../../raw/x.md``
    citation maps to it: the source's posix path relative to ``WIKI_DIR``'s parent (the repo root,
    or the shared root on a mounted drive). For an in-repo source this is just ``raw/x.md`` — which
    is exactly what the JS ``resolveLink`` returns for a citation that climbs out of ``wiki/``."""
    parent = config.WIKI_DIR.parent
    try:
        return os.path.relpath(str(abs_path), str(parent)).replace(os.sep, "/")
    except ValueError:  # different drive — no relative path exists
        return os.path.basename(str(abs_path))


def _collect_sources(pages) -> dict[str, str]:
    """Map each cited raw/docs source's VIEWER IDENTITY -> its source key, by scanning citation
    links (so a source is clickable even if it isn't in the manifest). What counts as a citation is
    the shared, config-aware :func:`grammar.is_source_citation` (a link into ``RAW_DIR``/``DOCS_DIR``).
    The identity is computed with :func:`_viewer_resolve` — the exact port of the browser's link
    resolver — so the source is keyed under the same id the inline citation looks it up by, in any
    layout. Fence-aware via ``grammar.prose_lines``, so a citation written as a literal inside a
    ``` code fence is not counted. First writer wins per identity, for determinism."""
    found: dict[str, str] = {}
    for page in pages:
        for line in grammar.prose_lines(page.body):
            for match in grammar.ANY_LINK_RE.finditer(line):
                path, _suffix = grammar.split_link_target(match.group(1))
                if not grammar.is_source_citation(page.rel_path, path):
                    continue
                link_abs = grammar.link_abs(page.rel_path, path)
                view_id = _viewer_resolve(page.rel_path, path)
                found.setdefault(view_id, config.rel_or_abs_posix(Path(link_abs)))
    return found


def _source_title(body: str, view_id: str) -> str:
    """A source's display title: its first markdown heading, else its file name."""
    match = _HEADING_RE.search(body)
    if match:
        return match.group(1).strip()
    return view_id.rsplit("/", 1)[-1]


def _source_snippet(body: str, limit: int = 240) -> str:
    """A short, whitespace-collapsed preview of a source's prose (headings dropped) for the hover
    popover."""
    prose = " ".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    return " ".join(prose.split())[:limit]


def _source_href(abs_path: str | os.PathLike) -> str | None:
    """A relative link from the DEFAULT viewer location (``WIKI_DIR``) to the raw source on disk, so
    the reader can offer an "open the original file" affordance — the browser opens a PDF or other
    binary natively. None when no relative path exists (a different drive). The link assumes the
    viewer was written to its default ``wiki/`` location; the embedded text always works regardless."""
    try:
        return os.path.relpath(str(abs_path), str(config.WIKI_DIR)).replace(os.sep, "/")
    except ValueError:  # different drive — no relative path exists
        return None


def _read_source(path: Path) -> tuple[str, str]:
    """Read a raw source for embedding, returning ``(text, kind)``:

    - ``("...", "text")``  — a UTF-8 text file (markdown/code/notes), embedded verbatim;
    - ``("...", "office")`` — a ``.pptx``/``.docx`` whose text we extract with the stdlib (reusing
      the ingest extractor), so Office sources are readable inline too;
    - ``("", "binary")``   — anything we can't turn into text without a heavyweight dependency,
      e.g. a PDF. The viewer then offers an "open the original file" link instead of inline text.
    """
    try:
        return path.read_text(encoding="utf-8"), "text"
    except (OSError, ValueError, UnicodeError):
        pass
    if extract.is_office_source(path):
        extracted = extract.extract_text(path)  # "" on a malformed/odd document
        if extracted:
            return extracted, "office"
    return "", "binary"


def _build_sources(pages) -> dict:
    """Map each cited raw/docs source -> its embedded record. Cited sources are keyed by the exact
    browser identity (:func:`_collect_sources` via :func:`_viewer_resolve`) so an inline citation
    resolves straight to its record; tracked-but-uncited files fall back to :func:`_source_view_id`.
    Each record carries the file content (capped/truncated), title, the model that imported it (from
    the manifest), the wiki pages that cite it (the live link graph), a kind (text/office/binary),
    an "open the original" href, and a missing flag when the file isn't on disk. Includes file
    sources tracked in the manifest even if currently uncited, so the Sources axis is complete;
    skips git-repository manifest entries (a folder, not a readable file). The manifest is read
    through ``manifest.load()`` — the one reader that understands both the stamped format-2 file
    and a legacy flat mapping — and provenance stays optional decoration: a missing/corrupt
    manifest simply reads as {}."""
    manifest = manifest_mod.load()
    manifest_files = {key for key, entry in manifest.items() if not manifest_mod.is_repo_entry(entry)}
    # Cited sources keyed by the browser identity, then tracked-but-uncited files under a fallback
    # id so the Sources axis is complete (a git-repository entry is a folder, not a file — skipped).
    id_to_key = _collect_sources(pages)
    seen_keys = set(id_to_key.values())
    for key in sorted(manifest_files):
        if key in seen_keys:
            continue
        id_to_key.setdefault(_source_view_id(config.source_path_for_key(key)), key)
        seen_keys.add(key)
    sources: dict[str, dict] = {}
    for view_id, key in sorted(id_to_key.items()):
        abs_path = str(config.source_path_for_key(key))
        path = Path(abs_path)
        present = path.is_file()
        if present:
            body, kind = _read_source(path)
        else:
            body, kind = "", "binary"  # not on disk: render an "unavailable" notice, no body
        truncated = len(body) > _SOURCE_MAX_CHARS
        if truncated:
            body = body[:_SOURCE_MAX_CHARS]
        sources[view_id] = {
            "id": view_id,
            "key": key,
            "title": _source_title(body, view_id),
            "model": manifest_mod.entry_model(manifest[key]) if key in manifest else None,
            "cited_by": store.find_raw_references(key, pages),
            "missing": not present,
            "kind": kind,  # "text" | "office" | "binary"
            "href": _source_href(abs_path) if present else None,
            "truncated": truncated,
            "snippet": _source_snippet(body),
            "body": body,
        }
    return sources


def build_html(pages=None) -> str:
    """Return the complete self-contained HTML document as one string: shell + inlined CSS +
    inlined viewer JS + the bundle embedded as an inert ``application/json`` script."""
    bundle = build_bundle(pages)
    # Compact JSON; then escape '</' -> '<\/' so a literal '</script>' inside any page body
    # OR embedded source cannot close the data <script> early. (json.dumps does NOT do this.)
    blob = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    # Order matters: fill CSS and JS sentinels first, the data blob last, so a sentinel-like
    # substring inside page data is never re-interpreted.
    html = _asset("template.html").replace("/*__CSS__*/", _asset("app.css"))
    html = html.replace("/*__VIEWER_JS__*/", _asset("app.js"))
    html = html.replace("/*__BUNDLE__*/", blob)
    return html


def write_viewer(out_path=None, pages=None) -> Path:
    """Write the viewer document; default ``config.WIKI_DIR/.citadel_viewer.html``. Returns the
    absolute path written."""
    if out_path is None:
        out_path = config.WIKI_DIR / VIEWER_FILENAME
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_html(pages), encoding="utf-8")
    return out_path.resolve()


def open_in_browser(path: Path) -> bool:
    """Open ``path`` in the default browser; return True if a browser was launched. Never
    raises (a headless/WSL box with no browser returns False instead of crashing)."""
    try:
        return bool(webbrowser.open(path.as_uri()))
    except Exception:  # noqa: BLE001 - a missing browser must not crash the command
        return False


def _open_obsidian() -> int:
    """Best-effort: deep-link the wiki folder into Obsidian and always print the path."""
    import urllib.parse

    folder = config.WIKI_DIR.resolve()
    deep = "obsidian://open?path=" + urllib.parse.quote(str(folder))
    print(f"Open this folder as an Obsidian vault: {folder}")
    print("  tip: open the repository root instead to resolve raw/ citation links.")
    print(f"  deep link: {deep}")
    try:
        webbrowser.open(deep)
    except Exception:  # noqa: BLE001
        pass
    return 0


def view(out=None, open_browser: bool = True, obsidian: bool = False) -> int:
    """Generate the viewer, optionally open it, and print its path. Returns a CLI exit code
    (always 0 on a successful write, even if no browser could be launched)."""
    if obsidian:
        return _open_obsidian()
    path = write_viewer(out)
    print(f"wrote {path}")
    print(f"  {path.as_uri()}")
    if open_browser and not open_in_browser(path):
        print("  (could not launch a browser — open the file above manually)")
    return 0


def _asset(name: str) -> str:
    """Read one of the viewer's package-data files (``template.html``/``app.css``/``app.js``).
    Each asset file ends with a newline and its sentinel is replaced verbatim."""
    return (resources.files(__package__) / name).read_text(encoding="utf-8")
