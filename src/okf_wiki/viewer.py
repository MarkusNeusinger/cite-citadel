"""A self-contained, offline, zero-dependency local viewer for the OKF wiki.

``build_html`` serializes the wiki — the pages, the cross-link graph, and the tags we
already compute in :mod:`store` — into ONE standalone HTML document with the bundle embedded
inline as JSON and a small hand-rolled markdown renderer + graph in inlined vanilla JS. It
opens from ``file://`` with **no web server and no network**: nothing is fetched from a CDN,
so the wiki data never leaves the machine. No third-party code is vendored.

The only LLM-free, read-only consumer of the wiki besides search/lint. Reuses
``store.load`` / ``store._inbound_map`` / ``store._resolved_md_links`` / ``store.tag_catalog``
so the graph and tags always match the rest of the system.

Public surface: ``build_bundle`` (pure data, the test seam), ``build_html`` (the document),
``write_viewer`` (writes ``wiki/.okf_viewer.html``), and ``view`` (CLI entry — write, open,
print the path; degrades gracefully when no browser is available, e.g. under WSL).
"""

from __future__ import annotations

import json
import webbrowser
from pathlib import Path

from . import config, store

# Default output: dot-prefixed so store.load() skips it (like .okf_ingested.json) and it is
# gitignored; it is a regenerable artifact, never a source of truth.
VIEWER_FILENAME = ".okf_viewer.html"


def build_bundle(pages=None) -> dict:
    """Build the JSON-serializable bundle from the loaded wiki (pure data; no HTML, no I/O
    beyond ``store.load()``). Deterministic — no timestamps — so a generated document
    round-trips back to this dict in tests."""
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
    }


def build_html(pages=None) -> str:
    """Return the complete self-contained HTML document as one string: shell + inlined CSS +
    inlined viewer JS + the bundle embedded as an inert ``application/json`` script."""
    bundle = build_bundle(pages)
    # Compact JSON; then escape '</' -> '<\/' so a literal '</script>' inside any page body
    # cannot close the data <script> early. (json.dumps does NOT do this.)
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
        --chip:#eef2ff; --card:#f8f9fb; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1115; --fg:#e6e6e6; --muted:#9aa0aa; --line:#2a2f3a; --accent:#6ea8fe;
          --chip:#1c2333; --card:#161a22; } }
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
#page-list details { margin-bottom:8px; }
#page-list summary { cursor:pointer; color:var(--muted); font-size:12px;
                     text-transform:uppercase; letter-spacing:.04em; }
.navitem { display:block; padding:3px 6px; border-radius:6px; color:var(--fg);
           text-decoration:none; }
.navitem:hover { background:var(--card); }
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
#graph { flex:1; width:100%; min-height:0; cursor:grab; touch-action:none; user-select:none; }
#graph.grabbing { cursor:grabbing; }
#graph .node { cursor:pointer; }
#graph .node circle { stroke:var(--bg); stroke-width:1.5; }
#graph .node:hover circle { stroke:var(--accent); stroke-width:2.5; }
#graph .node.active circle { stroke:var(--accent); stroke-width:3.5; }
#graph .node text { font-size:9px; fill:var(--fg); pointer-events:none; }
#graph line { stroke:var(--line); stroke-width:1; }
#content.map-collapsed #graph-pane { height:auto; min-height:0; }
#content.map-collapsed #graph { display:none; }
#reader { flex:1; overflow:auto; padding:20px 28px; max-width:920px; }
#reader h1 { margin:.2em 0 .1em; }
#reader .meta { color:var(--muted); font-size:13px; margin-bottom:6px; }
#reader .ptype { font-weight:600; color:var(--accent); }
#reader .desc { color:var(--muted); font-style:italic; }
#reader .backlinks { font-size:13px; color:var(--muted); margin:6px 0; }
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
.fndef { font-size:13px; color:var(--muted); margin:3px 0; }
.fndef .fnid { font-weight:600; color:var(--fg); }
.fnback { text-decoration:none; }
.ext { color:var(--muted); border-bottom:1px dotted var(--muted); cursor:help; }
#reader a[data-page] { color:var(--accent); }
"""


_VIEWER_JS = r'''
(function () {
  "use strict";
  var BUNDLE = JSON.parse(document.getElementById("bundle").textContent);
  var PAGES = {};
  BUNDLE.pages.forEach(function (p) { PAGES[p.rel_path] = p; });
  var TYPE_COLORS = ["#2563eb", "#16a34a", "#d97706", "#9333ea", "#dc2626", "#0891b2"];
  var typeColor = {};
  Object.keys(BUNDLE.types).sort().forEach(function (t, i) {
    typeColor[t] = TYPE_COLORS[i % TYPE_COLORS.length];
  });
  var activeTag = "";

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // Port of okf.resolve_link: normalize dirname(fromRel)/target to a posix path.
  function resolveLink(fromRel, target) {
    target = target.split("#")[0];
    var base = fromRel.indexOf("/") >= 0 ? fromRel.replace(/\/[^\/]*$/, "") : "";
    var parts = base ? base.split("/") : [];
    target.split("/").forEach(function (seg) {
      if (seg === "" || seg === ".") return;
      if (seg === "..") parts.pop(); else parts.push(seg);
    });
    return parts.join("/");
  }

  // Inline formatting on already-HTML-escaped text.
  function inlineFmt(text, fromRel) {
    text = text.replace(/`([^`]+)`/g, function (_, c) { return "<code>" + c + "</code>"; });
    text = text.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g, function (_, t, url) {
      if (url.indexOf("://") >= 0) return "<span class='ext' title='" + url + "'>" + t + "</span>";
      var rel = resolveLink(fromRel, url);
      if (PAGES[rel]) {
        return "<a href='#" + encodeURIComponent(rel) + "' data-page='" + esc(rel) + "'>" + t + "</a>";
      }
      return "<span class='ext' title='" + url + "'>" + t + "</span>";
    });
    text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    text = text.replace(/\[\^([^\]]+)\](?!:)/g, function (_, id) {
      return "<sup class='fnref'><a id='ref-" + esc(id) + "' href='#fn-" + esc(id) + "'>" +
        esc(id) + "</a></sup>";
    });
    return text;
  }

  function splitRow(line) {
    return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|")
      .map(function (c) { return c.trim(); });
  }

  // Hand-rolled markdown -> HTML. Generic over headings; special-cases only footnote
  // definitions and [!CALLOUT] blockquotes.
  function mdToHtml(src, fromRel) {
    var lines = src.split("\n"), out = [], i = 0, para = [];
    var inCode = false, codeBuf = [];
    function flush() {
      if (para.length) out.push("<p>" + inlineFmt(esc(para.join(" ")), fromRel) + "</p>");
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
          esc(fd[1]) + ".</span> " + inlineFmt(esc(fd[2]), fromRel) +
          " <a class='fnback' href='#ref-" + esc(fd[1]) + "'>↩</a></div>");
        i++; continue;
      }
      var h = /^(#{1,6})\s+(.*)$/.exec(t);
      if (h) {
        flush();
        var lvl = h[1].length;
        out.push("<h" + lvl + ">" + inlineFmt(esc(h[2]), fromRel) + "</h" + lvl + ">");
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
          return "<th>" + inlineFmt(esc(c), fromRel) + "</th>";
        }).join("") + "</tr></thead><tbody>";
        rows.forEach(function (r) {
          tb += "<tr>" + r.map(function (c) {
            return "<td>" + inlineFmt(esc(c), fromRel) + "</td>";
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
            inlineFmt(esc(rest.join(" ")), fromRel) + "</div></div>");
        } else {
          out.push("<blockquote>" + inlineFmt(esc(q.join(" ")), fromRel) + "</blockquote>");
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
          return "<li>" + inlineFmt(esc(it), fromRel) + "</li>";
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
  }

  // Interactive force-directed graph: hand-rolled, dependency-free. Built as an SVG string via
  // innerHTML (so the SVG-namespace URL is never emitted — keeps the file fully offline).
  // Supports pan (drag the background), zoom (wheel / buttons), and draggable nodes that pull
  // their neighbours via a live spring relaxation. A node click (no drag) opens the page.
  var Graph = (function () {
    var svg, gzoom;
    var nodes = [], edges = [], idx = {};
    var view = { x: 0, y: 0, k: 1 };
    var activeRel = "";
    var raf = null, animating = false;
    var dragNode = null, panning = false, last = null, moved = false;
    var W = 600, H = 420;

    function r2(v) { return Math.round(v * 10) / 10; }

    function buildModel() {
      var n = BUNDLE.pages.length || 1;
      nodes = BUNDLE.pages.map(function (p, i) {
        var a = 2 * Math.PI * i / n;
        return { id: p.rel_path, type: p.type, title: p.title,
                 x: W / 2 + Math.cos(a) * 150, y: H / 2 + Math.sin(a) * 150,
                 vx: 0, vy: 0, fx: null, fy: null };
      });
      idx = {};
      nodes.forEach(function (nd, i) { idx[nd.id] = i; });
      edges = BUNDLE.edges.filter(function (e) {
        return idx[e.source] != null && idx[e.target] != null;
      }).map(function (e) { return { s: idx[e.source], t: idx[e.target] }; });
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
        s += "<line x1='" + r2(a.x) + "' y1='" + r2(a.y) + "' x2='" + r2(b.x) +
             "' y2='" + r2(b.y) + "'/>";
      }
      for (i = 0; i < nodes.length; i++) {
        var nd = nodes[i];
        var label = nd.title.length > 18 ? nd.title.slice(0, 17) + "…" : nd.title;
        s += "<g class='node" + (nd.id === activeRel ? " active" : "") + "' data-page='" +
             esc(nd.id) + "'><circle cx='" + r2(nd.x) + "' cy='" + r2(nd.y) + "' r='7' fill='" +
             (typeColor[nd.type] || "#888") + "'/><text x='" + r2(nd.x) + "' y='" +
             r2(nd.y - 11) + "' text-anchor='middle'>" + esc(label) + "</text></g>";
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
        if (!moved) { openPage(node.id); }  // a click (no drag) opens the page
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

    return { init: init, zoom: zoom, refit: refit, setActive: setActive };
  })();

  function openPage(rel) {
    var p = PAGES[rel];
    if (!p) return;
    if (decodeURIComponent((location.hash || "").slice(1)) !== rel) {
      location.hash = encodeURIComponent(rel);
    }
    var meta = "<div class='meta'><span class='ptype'>" + esc(p.type) + "</span> " +
      p.tags.map(function (t) { return "<span class='tag'>" + esc(t) + "</span>"; }).join(" ") +
      "</div>";
    var back = p.inbound.length ? "<div class='backlinks'>Referenced by: " +
      p.inbound.map(function (r) {
        return "<a href='#" + encodeURIComponent(r) + "' data-page='" + esc(r) + "'>" +
          esc(PAGES[r] ? PAGES[r].title : r) + "</a>";
      }).join(", ") + "</div>" : "";
    document.getElementById("reader").innerHTML = "<h1>" + esc(p.title) + "</h1>" + meta +
      (p.description ? "<p class='desc'>" + esc(p.description) + "</p>" : "") + back + "<hr>" +
      mdToHtml(p.body, p.rel_path);
    document.getElementById("reader").scrollTop = 0;
    Graph.setActive(rel);
  }

  document.addEventListener("click", function (ev) {
    // The graph pane (nodes + toolbar) handles its own pointer events.
    if (ev.target.closest && ev.target.closest("#graph-pane")) return;
    var a = ev.target.closest("[data-page]");
    if (a) { ev.preventDefault(); openPage(a.getAttribute("data-page")); return; }
    var tg = ev.target.closest("[data-tag]");
    if (tg) { activeTag = tg.getAttribute("data-tag"); renderTags(); renderSidebar(); }
  });
  document.getElementById("search").addEventListener("input", renderSidebar);
  window.addEventListener("hashchange", function () {
    var rel = decodeURIComponent((location.hash || "").slice(1));
    if (rel && PAGES[rel]) openPage(rel);
  });

  renderTags();
  renderSidebar();
  Graph.init();

  // Map toolbar: collapse (give the reader full height), zoom, fit.
  var content = document.getElementById("content");
  var collapseBtn = document.getElementById("g-collapse");
  function setCollapsed(c) {
    content.classList.toggle("map-collapsed", c);
    collapseBtn.textContent = c ? "▸" : "▾";  // ▸ / ▾
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
  try { if (localStorage.getItem("okf_map_collapsed") === "1") setCollapsed(true); } catch (e) {}
  var rt;
  window.addEventListener("resize", function () {
    clearTimeout(rt); rt = setTimeout(function () { Graph.refit(); }, 150);
  });

  var initial = decodeURIComponent((location.hash || "").slice(1));
  if (initial && PAGES[initial]) openPage(initial);
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
  </aside>
  <main id="content">
    <section id="graph-pane">
      <div id="graph-bar">
        <span id="graph-title">Map</span>
        <span class="spacer"></span>
        <button class="gbtn" id="g-zoomout" title="Zoom out" type="button">&#8722;</button>
        <button class="gbtn" id="g-zoomin" title="Zoom in" type="button">+</button>
        <button class="gbtn" id="g-fit" title="Fit to view" type="button">&#10530;</button>
        <button class="gbtn" id="g-collapse" title="Collapse map" type="button">&#9662;</button>
      </div>
      <svg id="graph"></svg>
    </section>
    <article id="reader"></article>
  </main>
</div>
<script id="bundle" type="application/json">/*__BUNDLE__*/</script>
<script>/*__VIEWER_JS__*/</script>
</body>
</html>
"""
