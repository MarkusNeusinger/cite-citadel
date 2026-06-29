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

The only LLM-free, read-only consumer of the wiki besides search/lint. Reuses
``store.load`` / ``store._inbound_map`` / ``store._resolved_md_links`` / ``store.tag_catalog`` /
``store.find_raw_references`` so the graph, tags, and provenance always match the rest of the
system.

Public surface: ``build_bundle`` (pure data, the test seam), ``build_html`` (the document),
``write_viewer`` (writes ``wiki/.okf_viewer.html``), and ``view`` (CLI entry — write, open,
print the path; degrades gracefully when no browser is available, e.g. under WSL).
"""

from __future__ import annotations

import json
import os
import re
import webbrowser
from pathlib import Path

from . import config, extract, manifest as manifest_mod, store

# Default output: dot-prefixed so store.load() skips it (like .okf_ingested.json) and it is
# gitignored; it is a regenerable artifact, never a source of truth.
VIEWER_FILENAME = ".okf_viewer.html"

# A single embedded source is capped so a pathologically large raw file (a big PDF/CSV dump or a
# repo digest) can't bloat the standalone document without bound; the body is truncated with a
# marker and the viewer flags it. Generous enough that ordinary notes embed whole.
_SOURCE_MAX_CHARS = 200_000

# First markdown ATX heading in a raw source — used as its human title when present.
_HEADING_RE = re.compile(r"^#[ \t]+(.+?)[ \t]*$", re.MULTILINE)


def build_bundle(pages=None) -> dict:
    """Build the JSON-serializable bundle from the loaded wiki (pure data; no HTML, no I/O
    beyond ``store.load()`` and reading the cited raw sources). Deterministic — no timestamps —
    so a generated document round-trips back to this dict in tests."""
    if pages is None:
        pages = store.load()
    paths = {p.rel_path for p in pages}
    inbound = store._inbound_map(pages)

    pages_json: list[dict] = []
    edges: list[dict] = []
    types: dict[str, list[str]] = {}
    for page in pages:
        outbound = sorted(
            {
                resolved
                for _raw, resolved in store._resolved_md_links(page.rel_path, page.body)
                if resolved in paths
            }
        )
        for target in outbound:
            edges.append({"source": page.rel_path, "target": target})
        types.setdefault(page.type or "Untyped", []).append(page.rel_path)
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
            }
        )

    tags = {
        tag: [p.rel_path for p in tagged]
        for tag, tagged in store.tag_catalog(pages).items()
    }
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


def _load_manifest() -> dict:
    """The ingest manifest (source key -> {sha256, model, ...}) read from the LIVE wiki dir, so it
    follows a monkeypatched ``config.WIKI_DIR`` in tests rather than the import-time MANIFEST_PATH.
    Returns {} when absent/empty/corrupt — provenance is optional decoration, never required."""
    path = config.WIKI_DIR / ".okf_ingested.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _is_within(path_abs: str | os.PathLike, base) -> bool:
    """True if ``path_abs`` lies inside directory ``base`` (case-folded, purely LEXICAL — no
    symlink resolution). Used to tell a citation into the raw/ or docs/ source tree apart from a
    wiki cross-link or external URL. Stays lexical on purpose so it matches ``store._link_abs`` /
    ``store._link_points_at_key`` (which never call ``resolve()``); resolving only one side would
    diverge under a symlinked wiki/raw path and silently drop every cited source."""
    base_s = os.path.normcase(os.path.normpath(str(base)))
    p = os.path.normcase(os.path.normpath(str(path_abs)))
    return p == base_s or p.startswith(base_s + os.sep)


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
    links (so a source is clickable even if it isn't in the manifest). The identity is computed with
    :func:`_viewer_resolve` — the exact port of the browser's link resolver — so the source is keyed
    under the same id the inline citation looks it up by, in any layout. Fence-aware, mirroring the
    store's link scanners, so a citation written as a literal inside a ``` code fence is not counted.
    First writer wins per identity, for determinism."""
    found: dict[str, str] = {}
    for page in pages:
        in_fence = False
        for line in page.body.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            for match in store._ANY_LINK_RE.finditer(line):
                path, _suffix = store._split_link_target(match.group(1))
                link_abs = store._link_abs(page.rel_path, path)
                if link_abs is None:
                    continue
                if _is_within(link_abs, config.RAW_DIR) or _is_within(link_abs, config.DOCS_DIR):
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
    prose = " ".join(
        line for line in body.splitlines() if not line.lstrip().startswith("#")
    )
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
    skips git-repository manifest entries (a folder, not a readable file)."""
    manifest = _load_manifest()
    manifest_files = {
        key for key, entry in manifest.items() if not manifest_mod.is_repo_entry(entry)
    }
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
    blob = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).replace(
        "</", "<\\/"
    )
    # Order matters: fill CSS and JS sentinels first, the data blob last, so a sentinel-like
    # substring inside page data is never re-interpreted.
    html = _TEMPLATE.replace("/*__CSS__*/", _CSS)
    html = html.replace("/*__VIEWER_JS__*/", _VIEWER_JS)
    html = html.replace("/*__BUNDLE__*/", blob)
    return html


def write_viewer(out_path=None, pages=None) -> Path:
    """Write the viewer document; default ``config.WIKI_DIR/.okf_viewer.html``. Returns the
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


# --------------------------------------------------------------------------------------
# The single-file template. CSS/JS are inlined; the bundle goes in an inert JSON script.
# Filled via str.replace on sentinel comments (NOT str.format — the JS/CSS contain braces).
# --------------------------------------------------------------------------------------

_CSS = """
:root { --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#e2e2e2; --accent:#2563eb;
        --chip:#eef2ff; --card:#f8f9fb; --source:#b45309; --srcnode:#6b7280; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1115; --fg:#e6e6e6; --muted:#9aa0aa; --line:#2a2f3a; --accent:#6ea8fe;
          --chip:#1c2333; --card:#161a22; --source:#f0b366; --srcnode:#9aa0aa; } }
* { box-sizing:border-box; }
body { margin:0; font:15px/1.55 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
       color:var(--fg); background:var(--bg); }
#app { display:flex; height:100vh; }
#sidebar { width:300px; min-width:300px; border-right:1px solid var(--line); overflow:auto;
           padding:12px; }
#search { width:100%; padding:7px 9px; border:1px solid var(--line); border-radius:7px;
          background:var(--bg); color:var(--fg); margin-bottom:10px; }
#tag-filter { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:12px; }
.tag { background:var(--chip); color:var(--accent); border-radius:999px; padding:1px 9px;
       font-size:12px; cursor:pointer; user-select:none; }
.tag.active { background:var(--accent); color:#fff; }
#page-list details, #source-list details { margin-bottom:8px; }
#page-list summary, #source-list summary { cursor:pointer; color:var(--muted); font-size:12px;
                     text-transform:uppercase; letter-spacing:.04em; }
#source-list { border-top:1px solid var(--line); margin-top:6px; padding-top:8px; }
.navitem { display:block; padding:3px 6px; border-radius:6px; color:var(--fg);
           text-decoration:none; }
.navitem:hover { background:var(--card); }
.navitem .cite-count { color:var(--muted); font-size:11px; }
.navitem.src::before { content:"\\201C"; color:var(--source); margin-right:3px; font-weight:700; }
#content { flex:1; display:flex; flex-direction:column; overflow:hidden; }
#graph-pane { height:44vh; min-height:170px; border-bottom:1px solid var(--line);
              background:var(--card); display:flex; flex-direction:column; }
#graph-bar { display:flex; align-items:center; gap:6px; padding:4px 8px; flex:0 0 auto;
             border-bottom:1px solid var(--line); user-select:none; }
#graph-title { font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase;
               color:var(--muted); }
#graph-bar .spacer { flex:1; }
.gbtn { border:1px solid var(--line); background:var(--bg); color:var(--fg); border-radius:6px;
        min-width:24px; height:22px; line-height:20px; text-align:center; cursor:pointer;
        font-size:13px; padding:0 6px; }
.gbtn:hover { background:var(--card); border-color:var(--accent); color:var(--accent); }
.gbtn.active { background:var(--accent); border-color:var(--accent); color:#fff; }
#graph { flex:1; width:100%; min-height:0; cursor:grab; touch-action:none; user-select:none; }
#graph.grabbing { cursor:grabbing; }
#graph .node { cursor:pointer; }
#graph .node circle { stroke:var(--bg); stroke-width:1.5; }
#graph .node:hover circle { stroke:var(--accent); stroke-width:2.5; }
#graph .node.active circle { stroke:var(--accent); stroke-width:3.5; }
#graph .node.src rect { stroke:var(--bg); stroke-width:1.5; }
#graph .node.src:hover rect { stroke:var(--accent); stroke-width:2.5; }
#graph .node.active rect { stroke:var(--accent); stroke-width:3.5; }
#graph .node text { font-size:9px; fill:var(--fg); pointer-events:none; }
#graph line { stroke:var(--line); stroke-width:1; }
#graph line.src { stroke-dasharray:3 3; }
#graph-legend { display:flex; flex-wrap:wrap; gap:6px 12px; align-items:center; padding:4px 8px;
                flex:0 0 auto; border-top:1px solid var(--line); font-size:11px; color:var(--muted); }
#graph-legend .lg { display:inline-flex; align-items:center; gap:4px; }
#graph-legend .sw { width:9px; height:9px; border-radius:50%; display:inline-block; }
#graph-legend .sw.src { border-radius:2px; }
#content.map-collapsed #graph-pane { height:auto; min-height:0; }
#content.map-collapsed #graph, #content.map-collapsed #graph-legend { display:none; }
#reader { flex:1; overflow:auto; padding:20px 28px; max-width:920px; }
#reader h1 { margin:.2em 0 .1em; }
#reader .meta { color:var(--muted); font-size:13px; margin-bottom:6px; }
#reader .ptype { font-weight:600; color:var(--accent); }
#reader .ptype.src { color:var(--source); }
#reader .src-id { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }
#reader .src-model { color:var(--muted); }
#reader .desc { color:var(--muted); font-style:italic; }
#reader .backlinks { font-size:13px; color:var(--muted); margin:6px 0; }
#reader .toc { border:1px solid var(--line); background:var(--card); border-radius:8px;
               padding:6px 12px 8px; margin:10px 0; }
#reader .toc summary { cursor:pointer; color:var(--muted); font-size:11px; font-weight:600;
                       text-transform:uppercase; letter-spacing:.04em; }
#reader .toc a { display:block; text-decoration:none; color:var(--fg); padding:2px 0;
                 font-size:13px; }
#reader .toc a.lvl3 { padding-left:14px; color:var(--muted); }
#reader .toc a:hover { color:var(--accent); }
#reader table { border-collapse:collapse; margin:10px 0; }
#reader th, #reader td { border:1px solid var(--line); padding:5px 9px; }
#reader pre { background:var(--card); padding:10px; border-radius:7px; overflow:auto; }
#reader code { background:var(--card); padding:1px 4px; border-radius:4px; }
#reader pre code { background:none; padding:0; }
#reader blockquote { border-left:3px solid var(--line); margin:8px 0; padding:2px 12px;
                     color:var(--muted); }
.callout { border:1px solid var(--line); border-left:4px solid var(--accent);
           background:var(--card); border-radius:7px; padding:8px 12px; margin:10px 0; }
.callout-title { font-weight:700; font-size:12px; letter-spacing:.04em; color:var(--accent); }
.callout-contradiction { border-left-color:#dc2626; }
.callout-contradiction .callout-title { color:#dc2626; }
.fnref a { text-decoration:none; color:var(--accent); }
.fnref.has-src a { border-bottom:1px dotted var(--source); }
.fndef { font-size:13px; color:var(--muted); margin:3px 0; }
.fndef .fnid { font-weight:600; color:var(--fg); }
.fnback { text-decoration:none; }
.ext { color:var(--muted); border-bottom:1px dotted var(--muted); cursor:help; }
#reader a[data-page] { color:var(--accent); }
#reader a.srclink, a.srclink { color:var(--source); text-decoration:none;
           border-bottom:1px solid var(--line); cursor:pointer; }
#reader a.srclink:hover { border-bottom-color:var(--source); }
a.srclink::after { content:" \\2197"; font-size:.8em; opacity:.7; }
#reader a.rawfile { color:var(--accent); text-decoration:none; border:1px solid var(--line);
                    border-radius:6px; padding:1px 8px; font-size:12px; white-space:nowrap; }
#reader a.rawfile:hover { border-color:var(--accent); background:var(--card); }
#srcpop { position:fixed; z-index:50; max-width:360px; background:var(--bg);
          border:1px solid var(--line); border-radius:8px; box-shadow:0 6px 24px rgba(0,0,0,.18);
          padding:10px 12px; font-size:13px; display:none; pointer-events:none; }
#srcpop.show { display:block; }
#srcpop .sp-title { font-weight:700; margin-bottom:2px; }
#srcpop .sp-meta { color:var(--muted); font-size:11px; margin-bottom:6px;
                   font-family:ui-monospace,SFMono-Regular,Menlo,monospace; }
#srcpop .sp-snip { color:var(--fg); }
#srcpop .sp-hint { color:var(--source); font-size:11px; margin-top:6px; }
"""


_VIEWER_JS = r'''
(function () {
  "use strict";
  var BUNDLE = JSON.parse(document.getElementById("bundle").textContent);
  var PAGES = {};
  BUNDLE.pages.forEach(function (p) { PAGES[p.rel_path] = p; });
  var SOURCES = BUNDLE.sources || {};
  var TYPE_COLORS = ["#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2"];
  var SOURCE_COLOR = "#6b7280";
  var typeColor = {};
  Object.keys(BUNDLE.types).sort().forEach(function (t, i) {
    typeColor[t] = TYPE_COLORS[i % TYPE_COLORS.length];
  });
  var activeTag = "";

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Port of okf.resolve_link with the wiki root as a floor (a '..' that would climb above the
  // root is clamped), so a citation like '../../raw/x.md' resolves to 'raw/x.md' — exactly the
  // id under which build_sources keys an embedded source.
  function resolveLink(fromRel, target) {
    // Strip a markdown <...> link target so it resolves like store._split_link_target does. inlineFmt
    // runs on HTML-escaped text, so the brackets may already be &lt;...&gt;; the fnSrc parser passes
    // the raw <...>. Handle both forms.
    target = target.trim();
    if (target.charAt(0) === "<" && target.charAt(target.length - 1) === ">") {
      target = target.slice(1, -1);
    } else if (target.slice(0, 4) === "&lt;" && target.slice(-4) === "&gt;") {
      target = target.slice(4, -4);
    }
    target = target.split("#")[0];
    var base = fromRel.indexOf("/") >= 0 ? fromRel.replace(/\/[^\/]*$/, "") : "";
    var parts = base ? base.split("/") : [];
    target.split("/").forEach(function (seg) {
      if (seg === "" || seg === ".") return;
      if (seg === "..") parts.pop(); else parts.push(seg);
    });
    return parts.join("/");
  }

  // Inline formatting on already-HTML-escaped text. fnSrc maps a footnote id -> source view-id,
  // so an inline [^sN] gains a hover preview / open affordance for the source it cites.
  function inlineFmt(text, fromRel, fnSrc) {
    fnSrc = fnSrc || {};
    text = text.replace(/`([^`]+)`/g, function (_, c) { return "<code>" + c + "</code>"; });
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, function (_, t, url) {
      if (url.indexOf("://") >= 0) return "<span class='ext' title='" + url + "'>" + t + "</span>";
      var rel = resolveLink(fromRel, url);
      if (PAGES[rel]) {
        return "<a href='#" + encodeURIComponent(rel) + "' data-page='" + esc(rel) + "'>" + t + "</a>";
      }
      if (SOURCES[rel]) {
        return "<a href='#src:" + encodeURIComponent(rel) + "' class='srclink' data-source='" +
          esc(rel) + "' data-pop='" + esc(rel) + "'>" + t + "</a>";
      }
      return "<span class='ext' title='" + url + "'>" + t + "</span>";
    });
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/\[\^([^\]]+)\](?!:)/g, function (_, id) {
      var sid = fnSrc[id];
      var pop = sid ? " data-pop='" + esc(sid) + "'" : "";
      return "<sup class='fnref" + (sid ? " has-src" : "") + "'><a id='ref-" + esc(id) +
        "' href='#fn-" + esc(id) + "'" + pop + ">" + esc(id) + "</a></sup>";
    });
    return text;
  }

  function splitRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|")
      .map(function (c) { return c.trim(); });
  }

  // Hand-rolled markdown -> HTML. Generic over headings; special-cases only footnote
  // definitions and [!CALLOUT] blockquotes.
  function mdToHtml(src, fromRel, fnSrc) {
    var lines = src.split("\n"), out = [], i = 0, para = [];
    var inCode = false, codeBuf = [];
    function flush() {
      if (para.length) out.push("<p>" + inlineFmt(esc(para.join(" ")), fromRel, fnSrc) + "</p>");
      para = [];
    }
    while (i < lines.length) {
      var raw = lines[i], t = raw.replace(/\s+$/, "");
      if (/^\s*```/.test(t)) {
        flush();
        if (!inCode) { inCode = true; codeBuf = []; }
        else { inCode = false; out.push("<pre><code>" + esc(codeBuf.join("\n")) + "</code></pre>"); }
        i++; continue;
      }
      if (inCode) { codeBuf.push(raw); i++; continue; }
      var fd = /^\[\^([^\]]+)\]:\s*(.*)$/.exec(t);
      if (fd) {
        flush();
        out.push("<div class='fndef' id='fn-" + esc(fd[1]) + "'><span class='fnid'>" +
          esc(fd[1]) + ".</span> " + inlineFmt(esc(fd[2]), fromRel, fnSrc) +
          " <a class='fnback' href='#ref-" + esc(fd[1]) + "'>↩</a></div>");
        i++; continue;
      }
      var h = /^(#{1,6})\s+(.*)$/.exec(t);
      if (h) {
        flush();
        var lvl = h[1].length;
        out.push("<h" + lvl + ">" + inlineFmt(esc(h[2]), fromRel, fnSrc) + "</h" + lvl + ">");
        i++; continue;
      }
      if (t.indexOf("|") >= 0 && i + 1 < lines.length &&
          /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1]) && lines[i + 1].indexOf("-") >= 0) {
        flush();
        var header = splitRow(t); i += 2;
        var rows = [];
        while (i < lines.length && lines[i].indexOf("|") >= 0 && lines[i].trim() !== "") {
          rows.push(splitRow(lines[i])); i++;
        }
        var tb = "<table><thead><tr>" + header.map(function (c) {
          return "<th>" + inlineFmt(esc(c), fromRel, fnSrc) + "</th>";
        }).join("") + "</tr></thead><tbody>";
        rows.forEach(function (r) {
          tb += "<tr>" + r.map(function (c) {
            return "<td>" + inlineFmt(esc(c), fromRel, fnSrc) + "</td>";
          }).join("") + "</tr>";
        });
        out.push(tb + "</tbody></table>");
        continue;
      }
      if (/^\s*>/.test(t)) {
        flush();
        var q = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          q.push(lines[i].replace(/^\s*>\s?/, "")); i++;
        }
        var co = /^\s*\[!([A-Za-z]+)\]\s*(.*)$/.exec(q[0] || "");
        if (co) {
          var title = co[1].toUpperCase(), rest = q.slice(1);
          if (co[2]) rest.unshift(co[2]);
          out.push("<div class='callout callout-" + title.toLowerCase() +
            "'><div class='callout-title'>" + esc(title) + "</div><div class='callout-body'>" +
            inlineFmt(esc(rest.join(" ")), fromRel, fnSrc) + "</div></div>");
        } else {
          out.push("<blockquote>" + inlineFmt(esc(q.join(" ")), fromRel, fnSrc) + "</blockquote>");
        }
        continue;
      }
      if (/^\s*[-*]\s+/.test(t)) {
        flush();
        var items = [];
        while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
          items.push(lines[i].replace(/^\s*[-*]\s+/, "")); i++;
        }
        out.push("<ul>" + items.map(function (it) {
          return "<li>" + inlineFmt(esc(it), fromRel, fnSrc) + "</li>";
        }).join("") + "</ul>");
        continue;
      }
      if (t.trim() === "") { flush(); i++; continue; }
      para.push(t); i++;
    }
    flush();
    return out.join("\n");
  }

  function renderTags() {
    var box = document.getElementById("tag-filter");
    var html = "<span class='tag" + (activeTag ? "" : " active") + "' data-tag=''>all</span>";
    Object.keys(BUNDLE.tags).sort().forEach(function (tag) {
      html += "<span class='tag" + (tag === activeTag ? " active" : "") + "' data-tag='" +
        esc(tag) + "'>" + esc(tag) + " " + BUNDLE.tags[tag].length + "</span>";
    });
    box.innerHTML = html;
  }

  function renderSidebar() {
    var query = (document.getElementById("search").value || "").toLowerCase();
    var nav = document.getElementById("page-list"), html = "";
    Object.keys(BUNDLE.types).sort().forEach(function (type) {
      var rels = BUNDLE.types[type].filter(function (rel) {
        var p = PAGES[rel];
        if (activeTag && p.tags.indexOf(activeTag) < 0) return false;
        if (query) {
          var hay = (p.title + " " + p.rel_path + " " + p.tags.join(" ")).toLowerCase();
          if (hay.indexOf(query) < 0) return false;
        }
        return true;
      });
      if (!rels.length) return;
      html += "<details open><summary>" + esc(type) + " (" + rels.length + ")</summary>";
      rels.forEach(function (rel) {
        html += "<a class='navitem' href='#" + encodeURIComponent(rel) + "' data-page='" +
          esc(rel) + "'>" + esc(PAGES[rel].title) + "</a>";
      });
      html += "</details>";
    });
    nav.innerHTML = html || "<p class='ext'>No pages.</p>";
    renderSources(query);
  }

  // The Sources browse axis: a sidebar group listing every embedded source with its citation
  // count. Hidden while a tag filter is active (sources carry no tags). Text-filtered by the
  // shared search box (title + path).
  function renderSources(query) {
    var box = document.getElementById("source-list");
    if (!box) return;
    var ids = activeTag ? [] : Object.keys(SOURCES).sort().filter(function (id) {
      if (!query) return true;
      var s = SOURCES[id];
      return (s.title + " " + s.id).toLowerCase().indexOf(query) >= 0;
    });
    if (!ids.length) { box.innerHTML = ""; return; }
    var html = "<details open><summary>Sources (" + ids.length + ")</summary>";
    ids.forEach(function (id) {
      var s = SOURCES[id];
      html += "<a class='navitem src' href='#src:" + encodeURIComponent(id) +
        "' data-source='" + esc(id) + "' data-pop='" + esc(id) + "'>" + esc(s.title) +
        " <span class='cite-count'>" + s.cited_by.length + "</span></a>";
    });
    box.innerHTML = html + "</details>";
  }

  // Interactive force-directed graph: hand-rolled, dependency-free. Built as an SVG string via
  // innerHTML (so the SVG-namespace URL is never emitted — keeps the file fully offline).
  // Supports pan (drag the background), zoom (wheel / buttons), draggable nodes that pull their
  // neighbours via a live spring relaxation, and an optional source layer (square nodes linked to
  // the pages that cite them). A node click (no drag) opens the page or source.
  var Graph = (function () {
    var svg, gzoom;
    var nodes = [], edges = [], idx = {};
    var view = { x: 0, y: 0, k: 1 };
    var activeRel = "";
    var showSources = false;
    var raf = null, animating = false;
    var dragNode = null, panning = false, last = null, moved = false;
    var W = 600, H = 420;

    function r2(v) { return Math.round(v * 10) / 10; }

    function buildModel() {
      var pgs = BUNDLE.pages;
      var srcIds = showSources
        ? Object.keys(SOURCES).filter(function (id) { return SOURCES[id].cited_by.length; })
        : [];
      var n = (pgs.length + srcIds.length) || 1;
      nodes = pgs.map(function (p, i) {
        var a = 2 * Math.PI * i / n;
        return { id: p.rel_path, kind: "page", type: p.type, title: p.title,
                 x: W / 2 + Math.cos(a) * 150, y: H / 2 + Math.sin(a) * 150,
                 vx: 0, vy: 0, fx: null, fy: null };
      });
      srcIds.forEach(function (id, j) {
        var a = 2 * Math.PI * (pgs.length + j) / n;
        nodes.push({ id: "src:" + id, kind: "source", type: "__source__", title: SOURCES[id].title,
                     x: W / 2 + Math.cos(a) * 150, y: H / 2 + Math.sin(a) * 150,
                     vx: 0, vy: 0, fx: null, fy: null });
      });
      idx = {};
      nodes.forEach(function (nd, i) { idx[nd.id] = i; });
      edges = BUNDLE.edges.filter(function (e) {
        return idx[e.source] != null && idx[e.target] != null;
      }).map(function (e) { return { s: idx[e.source], t: idx[e.target] }; });
      srcIds.forEach(function (id) {
        var sNode = idx["src:" + id];
        SOURCES[id].cited_by.forEach(function (rel) {
          if (idx[rel] != null) edges.push({ s: idx[rel], t: sNode, src: true });
        });
      });
    }

    // Proven Fruchterman-Reingold settle for the INITIAL layout (clamped to the WxH box).
    function settle() {
      var n = nodes.length; if (!n) return;
      var k = Math.sqrt((W * H) / n) * 0.6;
      for (var it = 0; it < 130; it++) {
        var disp = nodes.map(function () { return { x: 0, y: 0 }; });
        for (var a = 0; a < n; a++) for (var b = a + 1; b < n; b++) {
          var dx = nodes[a].x - nodes[b].x, dy = nodes[a].y - nodes[b].y;
          var d = Math.sqrt(dx * dx + dy * dy) || 0.01, f = k * k / d;
          disp[a].x += dx / d * f; disp[a].y += dy / d * f;
          disp[b].x -= dx / d * f; disp[b].y -= dy / d * f;
        }
        edges.forEach(function (e) {
          var dx = nodes[e.s].x - nodes[e.t].x, dy = nodes[e.s].y - nodes[e.t].y;
          var d = Math.sqrt(dx * dx + dy * dy) || 0.01, f = d * d / k;
          disp[e.s].x -= dx / d * f; disp[e.s].y -= dy / d * f;
          disp[e.t].x += dx / d * f; disp[e.t].y += dy / d * f;
        });
        var temp = Math.max(2, 30 * (1 - it / 130));
        nodes.forEach(function (nd, kk) {
          var dl = Math.sqrt(disp[kk].x * disp[kk].x + disp[kk].y * disp[kk].y) || 0.01;
          nd.x += disp[kk].x / dl * Math.min(dl, temp);
          nd.y += disp[kk].y / dl * Math.min(dl, temp);
          nd.x = Math.max(18, Math.min(W - 18, nd.x));
          nd.y = Math.max(18, Math.min(H - 18, nd.y));
        });
      }
    }

    // Light live relaxation used while dragging, so neighbours follow: springs + capped
    // repulsion + a gentle pull toward the cluster centroid, damped. Returns the largest
    // per-node movement so the animation loop knows when to stop.
    function simStep() {
      var n = nodes.length; if (!n) return 0;
      var cx = 0, cy = 0, i, j;
      for (i = 0; i < n; i++) { cx += nodes[i].x; cy += nodes[i].y; }
      cx /= n; cy /= n;
      var L = 80, REP = 2400, SPR = 0.03, GRAV = 0.012, DAMP = 0.9, MAXV = 50;
      for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) {
        var dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
        var d2 = dx * dx + dy * dy + 0.01, d = Math.sqrt(d2);
        var f = Math.min(REP / d2, 40), ux = dx / d * f, uy = dy / d * f;
        nodes[i].vx += ux; nodes[i].vy += uy;
        nodes[j].vx -= ux; nodes[j].vy -= uy;
      }
      edges.forEach(function (e) {
        var a = nodes[e.s], b = nodes[e.t];
        var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        var f = (d - L) * SPR, ux = dx / d * f, uy = dy / d * f;
        a.vx += ux; a.vy += uy; b.vx -= ux; b.vy -= uy;
      });
      var maxd = 0;
      for (i = 0; i < n; i++) {
        var nd = nodes[i];
        if (nd.fx != null) { nd.x = nd.fx; nd.y = nd.fy; nd.vx = 0; nd.vy = 0; continue; }
        nd.vx = (nd.vx + (cx - nd.x) * GRAV) * DAMP;
        nd.vy = (nd.vy + (cy - nd.y) * GRAV) * DAMP;
        nd.vx = Math.max(-MAXV, Math.min(MAXV, nd.vx));
        nd.vy = Math.max(-MAXV, Math.min(MAXV, nd.vy));
        nd.x += nd.vx; nd.y += nd.vy;
        maxd = Math.max(maxd, Math.abs(nd.vx) + Math.abs(nd.vy));
      }
      return maxd;
    }

    function draw() {
      if (!gzoom) return;
      var s = "", i;
      for (i = 0; i < edges.length; i++) {
        var a = nodes[edges[i].s], b = nodes[edges[i].t];
        s += "<line class='" + (edges[i].src ? "src" : "") + "' x1='" + r2(a.x) + "' y1='" +
             r2(a.y) + "' x2='" + r2(b.x) + "' y2='" + r2(b.y) + "'/>";
      }
      for (i = 0; i < nodes.length; i++) {
        var nd = nodes[i];
        var label = nd.title.length > 18 ? nd.title.slice(0, 17) + "…" : nd.title;
        var act = nd.id === activeRel ? " active" : "";
        if (nd.kind === "source") {
          s += "<g class='node src" + act + "' data-page='" + esc(nd.id) + "'><rect x='" +
               r2(nd.x - 6) + "' y='" + r2(nd.y - 6) + "' width='12' height='12' rx='2' fill='" +
               SOURCE_COLOR + "'/><text x='" + r2(nd.x) + "' y='" + r2(nd.y - 11) +
               "' text-anchor='middle'>" + esc(label) + "</text></g>";
        } else {
          s += "<g class='node" + act + "' data-page='" + esc(nd.id) + "'><circle cx='" +
               r2(nd.x) + "' cy='" + r2(nd.y) + "' r='7' fill='" +
               (typeColor[nd.type] || "#888") + "'/><text x='" + r2(nd.x) + "' y='" +
               r2(nd.y - 11) + "' text-anchor='middle'>" + esc(label) + "</text></g>";
        }
      }
      gzoom.innerHTML = s;
      gzoom.setAttribute("transform", "translate(" + r2(view.x) + "," + r2(view.y) +
        ") scale(" + (Math.round(view.k * 1000) / 1000) + ")");
    }

    function frame() {
      var moving = simStep();
      draw();
      if (dragNode || moving > 0.4) { raf = requestAnimationFrame(frame); }
      else { animating = false; raf = null; }
    }
    function reheat() { if (!animating) { animating = true; raf = requestAnimationFrame(frame); } }

    function size() {
      var r = svg.getBoundingClientRect();
      return { w: r.width || 600, h: r.height || 360, left: r.left, top: r.top };
    }

    function refit() {
      if (!svg) return;
      if (!nodes.length) { draw(); return; }
      var sz = size(), minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
      nodes.forEach(function (n) {
        minx = Math.min(minx, n.x); miny = Math.min(miny, n.y);
        maxx = Math.max(maxx, n.x); maxy = Math.max(maxy, n.y);
      });
      var bw = (maxx - minx) || 1, bh = (maxy - miny) || 1, pad = 50;
      view.k = Math.max(0.2, Math.min(2, Math.min((sz.w - pad) / bw, (sz.h - pad) / bh)));
      view.x = sz.w / 2 - (minx + maxx) / 2 * view.k;
      view.y = sz.h / 2 - (miny + maxy) / 2 * view.k;
      draw();
    }

    function zoomAt(factor, px, py) {
      var nk = Math.max(0.2, Math.min(4, view.k * factor));
      var wx = (px - view.x) / view.k, wy = (py - view.y) / view.k;
      view.k = nk; view.x = px - wx * nk; view.y = py - wy * nk;
      draw();
    }
    function zoom(factor) { var sz = size(); zoomAt(factor, sz.w / 2, sz.h / 2); }

    function toWorld(ev) {
      var sz = size();
      return { x: (ev.clientX - sz.left - view.x) / view.k,
               y: (ev.clientY - sz.top - view.y) / view.k };
    }

    function onDown(ev) {
      var g = ev.target.closest ? ev.target.closest(".node") : null;
      last = { x: ev.clientX, y: ev.clientY }; moved = false;
      if (g) {
        dragNode = nodes[idx[g.getAttribute("data-page")]];
        dragNode.fx = dragNode.x; dragNode.fy = dragNode.y;  // pin in place until moved
      } else { panning = true; svg.classList.add("grabbing"); }
      ev.preventDefault();
    }
    function onMove(ev) {
      if (!dragNode && !panning) return;
      var dx = ev.clientX - last.x, dy = ev.clientY - last.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      if (dragNode) {
        var w = toWorld(ev);
        dragNode.fx = w.x; dragNode.fy = w.y; dragNode.x = w.x; dragNode.y = w.y;
        reheat();
      } else if (panning) { view.x += dx; view.y += dy; draw(); }
      last = { x: ev.clientX, y: ev.clientY };
    }
    function onUp() {
      if (dragNode) {
        var node = dragNode;
        dragNode.fx = null; dragNode.fy = null; dragNode = null;
        if (!moved) {  // a click (no drag) opens the page or source
          if (node.id.indexOf("src:") === 0) openSource(node.id.slice(4));
          else openPage(node.id);
        }
        reheat();
      }
      panning = false; if (svg) svg.classList.remove("grabbing");
    }

    function init() {
      svg = document.getElementById("graph");
      svg.innerHTML = "<g id='gzoom'></g>";
      gzoom = document.getElementById("gzoom");
      buildModel();
      settle();
      refit();
      svg.addEventListener("mousedown", onDown);
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
      svg.addEventListener("wheel", function (ev) {
        ev.preventDefault();
        var sz = size();
        zoomAt(ev.deltaY < 0 ? 1.12 : 1 / 1.12, ev.clientX - sz.left, ev.clientY - sz.top);
      }, { passive: false });
    }

    function setActive(rel) { activeRel = rel; draw(); }
    function setShowSources(on) { showSources = on; buildModel(); settle(); refit(); }

    return { init: init, zoom: zoom, refit: refit, setActive: setActive,
             setShowSources: setShowSources };
  })();

  // ---- The reader: render a page or a source into the article pane, then decorate it. ----

  function renderReader(html) {
    var reader = document.getElementById("reader");
    reader.innerHTML = html;
    reader.scrollTop = 0;
    decorateReader(reader);
  }

  // Add a collapsible table of contents for any page/source with enough headings, giving every
  // heading a stable id to jump to.
  function decorateReader(reader) {
    var hs = reader.querySelectorAll("h2, h3");
    if (hs.length < 3) return;
    var items = [];
    Array.prototype.forEach.call(hs, function (h, i) {
      var id = "h-" + i; h.id = id;
      var cls = h.tagName === "H3" ? "lvl3" : "";
      items.push("<a class='" + cls + "' data-h='" + id + "' href='#'>" + esc(h.textContent) +
        "</a>");
    });
    var toc = "<details class='toc' open><summary>On this page</summary>" + items.join("") +
      "</details>";
    var hr = reader.querySelector("hr");
    if (hr) hr.insertAdjacentHTML("afterend", toc);
    else reader.insertAdjacentHTML("afterbegin", toc);
  }

  function backlinkList(label, rels) {
    if (!rels.length) return "";
    return "<div class='backlinks'>" + label + " " + rels.map(function (r) {
      return "<a href='#" + encodeURIComponent(r) + "' data-page='" + esc(r) + "'>" +
        esc(PAGES[r] ? PAGES[r].title : r) + "</a>";
    }).join(", ") + "</div>";
  }

  function openPage(rel) {
    var p = PAGES[rel];
    if (!p) return;
    if (decodeURIComponent((location.hash || "").slice(1)) !== rel) {
      location.hash = encodeURIComponent(rel);
    }
    // Map each footnote id to the source it cites (parsed from the page's ## Sources defs), so
    // inline [^sN] markers become source-aware (hover preview + open).
    var fnSrc = {};
    p.body.split("\n").forEach(function (line) {
      var m = /^\s*\[\^([^\]]+)\]:\s*\[[^\]]*\]\(([^)\s]+)/.exec(line);
      if (m) { var r = resolveLink(rel, m[2]); if (SOURCES[r]) fnSrc[m[1]] = r; }
    });
    var meta = "<div class='meta'><span class='ptype'>" + esc(p.type) + "</span> " +
      p.tags.map(function (t) { return "<span class='tag'>" + esc(t) + "</span>"; }).join(" ") +
      "</div>";
    renderReader("<h1>" + esc(p.title) + "</h1>" + meta +
      (p.description ? "<p class='desc'>" + esc(p.description) + "</p>" : "") +
      backlinkList("Referenced by:", p.inbound) + "<hr>" + mdToHtml(p.body, p.rel_path, fnSrc));
    Graph.setActive(rel);
  }

  function rawFileLink(s, label) {
    if (!s.href || s.missing) return "";
    return "<a class='rawfile' href='" + esc(encodeURI(s.href)) +
      "' target='_blank' rel='noopener'>" + label + " ↗</a>";
  }

  function openSource(sid) {
    var s = SOURCES[sid];
    if (!s) return;
    var want = "src:" + encodeURIComponent(sid);
    if ((location.hash || "").slice(1) !== want) { location.hash = want; }
    var open = rawFileLink(s, "Open original file");
    var meta = "<div class='meta'><span class='ptype src'>Source</span> <span class='src-id'>" +
      esc(s.id) + "</span>" + (s.model ? " <span class='src-model'>via " + esc(s.model) +
      "</span>" : "") + (open ? " " + open : "") + "</div>";
    var body;
    if (s.missing) {
      body = "<div class='callout'><div class='callout-title'>SOURCE UNAVAILABLE</div>" +
        "<div class='callout-body'>The raw file <code>" + esc(s.id) +
        "</code> was not found when this viewer was generated. Re-run <code>okf-wiki view</code> " +
        "with the source present to embed its content.</div></div>";
    } else if (s.kind === "binary") {
      // A PDF or other binary: we can't render it inline without a heavy dependency, so open the
      // original file (the browser shows a PDF natively).
      body = "<div class='callout'><div class='callout-title'>BINARY SOURCE</div>" +
        "<div class='callout-body'>This source is a binary file (e.g. a PDF) and can't be " +
        "rendered inline. " + (s.href
          ? "Use <strong>Open original file</strong> above — a PDF opens directly in your browser."
          : "Open the raw file <code>" + esc(s.id) + "</code> directly to read it.") +
        "</div></div>";
    } else {
      body = (s.kind === "office"
        ? "<p class='desc'>Text extracted from the original document.</p>" : "") +
        mdToHtml(s.body, sid, {});
      if (s.truncated) {
        body += "<div class='callout'><div class='callout-title'>TRUNCATED</div>" +
          "<div class='callout-body'>This source was longer than the embed limit and was " +
          "truncated. Open the original file to read it in full.</div></div>";
      }
    }
    renderReader("<h1>" + esc(s.title) + "</h1>" + meta +
      backlinkList("Cited by:", s.cited_by) + "<hr>" + body);
    Graph.setActive("src:" + sid);
  }

  // ---- Source hover preview popover. ----

  var pop = null;
  function showPop(sid, anchor) {
    var s = SOURCES[sid]; if (!s) return;
    if (!pop) pop = document.getElementById("srcpop");
    var note = s.missing ? " · (file unavailable)"
      : (s.kind === "binary" ? " · (binary — opens original)" : "");
    pop.innerHTML = "<div class='sp-title'>" + esc(s.title) + "</div><div class='sp-meta'>" +
      esc(s.id) + (s.model ? " · " + esc(s.model) : "") + note + "</div>" +
      (s.snippet ? "<div class='sp-snip'>" + esc(s.snippet) + "…</div>" : "") +
      "<div class='sp-hint'>Click to open source</div>";
    pop.classList.add("show");
    var r = anchor.getBoundingClientRect();
    var x = Math.min(r.left, window.innerWidth - pop.offsetWidth - 8);
    var y = r.bottom + 6;
    if (y + pop.offsetHeight > window.innerHeight) y = r.top - pop.offsetHeight - 6;
    pop.style.left = Math.max(8, x) + "px";
    pop.style.top = Math.max(8, y) + "px";
  }
  function hidePop() { if (pop) pop.classList.remove("show"); }

  document.addEventListener("mouseover", function (ev) {
    var a = ev.target.closest && ev.target.closest("[data-pop]");
    if (a) showPop(a.getAttribute("data-pop"), a);
  });
  document.addEventListener("mouseout", function (ev) {
    var a = ev.target.closest && ev.target.closest("[data-pop]");
    if (a) hidePop();
  });
  document.addEventListener("click", function (ev) {
    // The graph pane (nodes + toolbar) handles its own pointer events.
    if (ev.target.closest && ev.target.closest("#graph-pane")) return;
    var s = ev.target.closest("[data-source]");
    if (s) { ev.preventDefault(); hidePop(); openSource(s.getAttribute("data-source")); return; }
    var a = ev.target.closest("[data-page]");
    if (a) { ev.preventDefault(); openPage(a.getAttribute("data-page")); return; }
    var tc = ev.target.closest(".toc a[data-h]");
    if (tc) {
      ev.preventDefault();
      var h = document.getElementById(tc.getAttribute("data-h"));
      if (h) h.scrollIntoView();
      return;
    }
    var tg = ev.target.closest("[data-tag]");
    if (tg) { activeTag = tg.getAttribute("data-tag"); renderTags(); renderSidebar(); }
  });
  document.getElementById("search").addEventListener("input", renderSidebar);
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "/" && document.activeElement.id !== "search") {
      ev.preventDefault(); document.getElementById("search").focus();
    } else if (ev.key === "Escape") {
      hidePop();
      if (document.activeElement.id === "search") document.activeElement.blur();
    }
  });

  function route() {
    var h = decodeURIComponent((location.hash || "").slice(1));
    if (h.indexOf("src:") === 0) { if (SOURCES[h.slice(4)]) openSource(h.slice(4)); }
    else if (h && PAGES[h]) openPage(h);
  }
  window.addEventListener("hashchange", route);

  renderTags();
  renderSidebar();
  Graph.init();
  renderLegend();

  function renderLegend() {
    var box = document.getElementById("graph-legend");
    if (!box) return;
    var html = Object.keys(BUNDLE.types).sort().map(function (t) {
      return "<span class='lg'><span class='sw' style='background:" + (typeColor[t] || "#888") +
        "'></span>" + esc(t) + "</span>";
    }).join("");
    if (Object.keys(SOURCES).length) {
      html += "<span class='lg'><span class='sw src' style='background:" + SOURCE_COLOR +
        "'></span>Source</span>";
    }
    box.innerHTML = html;
  }

  // Map toolbar: collapse (give the reader full height), zoom, fit, toggle the source layer.
  var content = document.getElementById("content");
  var collapseBtn = document.getElementById("g-collapse");
  function setCollapsed(c) {
    content.classList.toggle("map-collapsed", c);
    collapseBtn.textContent = c ? "▸" : "▾";
    collapseBtn.title = c ? "Show map" : "Collapse map";
    try { localStorage.setItem("okf_map_collapsed", c ? "1" : "0"); } catch (e) {}
    if (!c) Graph.refit();  // pane size changed — re-fit the layout
  }
  collapseBtn.addEventListener("click", function () {
    setCollapsed(!content.classList.contains("map-collapsed"));
  });
  document.getElementById("g-zoomin").addEventListener("click", function () { Graph.zoom(1.25); });
  document.getElementById("g-zoomout").addEventListener("click", function () { Graph.zoom(0.8); });
  document.getElementById("g-fit").addEventListener("click", function () { Graph.refit(); });

  var srcBtn = document.getElementById("g-sources");
  function setShowSources(on) {
    Graph.setShowSources(on);
    srcBtn.classList.toggle("active", on);
    srcBtn.title = on ? "Hide sources in the map" : "Show sources in the map";
    try { localStorage.setItem("okf_show_sources", on ? "1" : "0"); } catch (e) {}
  }
  srcBtn.addEventListener("click", function () {
    setShowSources(!srcBtn.classList.contains("active"));
  });
  try { if (localStorage.getItem("okf_show_sources") === "1") setShowSources(true); } catch (e) {}
  try { if (localStorage.getItem("okf_map_collapsed") === "1") setCollapsed(true); } catch (e) {}
  var rt;
  window.addEventListener("resize", function () {
    clearTimeout(rt); rt = setTimeout(function () { Graph.refit(); }, 150);
  });

  var initial = decodeURIComponent((location.hash || "").slice(1));
  if (initial.indexOf("src:") === 0 && SOURCES[initial.slice(4)]) openSource(initial.slice(4));
  else if (initial && PAGES[initial]) openPage(initial);
  else if (BUNDLE.pages.length) openPage(BUNDLE.pages[0].rel_path);
})();
'''


_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OKF Wiki Viewer</title>
<style>/*__CSS__*/</style>
</head>
<body>
<div id="app">
  <aside id="sidebar">
    <input id="search" type="search" placeholder="Filter pages…" autocomplete="off">
    <div id="tag-filter"></div>
    <nav id="page-list"></nav>
    <nav id="source-list"></nav>
  </aside>
  <main id="content">
    <section id="graph-pane">
      <div id="graph-bar">
        <span id="graph-title">Map</span>
        <span class="spacer"></span>
        <button class="gbtn" id="g-sources" title="Show sources in the map" type="button">&#9673;</button>
        <button class="gbtn" id="g-zoomout" title="Zoom out" type="button">&#8722;</button>
        <button class="gbtn" id="g-zoomin" title="Zoom in" type="button">+</button>
        <button class="gbtn" id="g-fit" title="Fit to view" type="button">&#10530;</button>
        <button class="gbtn" id="g-collapse" title="Collapse map" type="button">&#9662;</button>
      </div>
      <svg id="graph"></svg>
      <div id="graph-legend"></div>
    </section>
    <article id="reader"></article>
  </main>
</div>
<div id="srcpop"></div>
<script id="bundle" type="application/json">/*__BUNDLE__*/</script>
<script>/*__VIEWER_JS__*/</script>
</body>
</html>
"""
