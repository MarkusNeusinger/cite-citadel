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
  var activeFacet = "";  // "" | "contradiction" | "llm" — the sidebar quick filter
  var query = "";        // current full-text query, lowercased/trimmed

  // Precompute the searchable/snippet forms once: a whitespace-collapsed body ("flat") and a
  // lowercased mirror of each searched field. Full-text search then scans these in memory — no
  // index, no network, and snippet offsets line up with the flat text.
  BUNDLE.pages.forEach(function (p) {
    p.flat = (p.body || "").replace(/\s+/g, " ").trim();
    p.lowBody = p.flat.toLowerCase();
    p.lowTitle = (p.title || "").toLowerCase();
    p.lowTags = (p.tags || []).join(" ").toLowerCase();
    p.lowPath = p.rel_path.toLowerCase();
  });
  Object.keys(SOURCES).forEach(function (id) {
    var s = SOURCES[id];
    // Full-text search runs over whatever text is embedded: the whole body, or — when only cited
    // excerpts are embedded — the concatenation of the segment texts.
    var embedded = s.body != null ? s.body
      : (s.segments || []).map(function (g) { return g.text; }).join("\n");
    s.flat = embedded.replace(/\s+/g, " ").trim();
    s.lowBody = s.flat.toLowerCase();
    s.lowTitle = (s.title || "").toLowerCase();
    s.lowId = id.toLowerCase();
  });

  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  // The current location hash as a decoded id, never throwing on a malformed/hand-edited hash
  // (decodeURIComponent raises URIError on bad percent-encoding) — a bad hash must not break the app.
  function safeHash() {
    try { return decodeURIComponent((location.hash || "").slice(1)); } catch (e) { return ""; }
  }

  // Port of okf.resolve_link with the wiki root as a floor (a '..' that would climb above the
  // root is clamped), so a citation like '../../raw/x.md' resolves to 'raw/x.md' — exactly the
  // id under which build_sources keys an embedded source.
  function resolveLink(fromRel, target) {
    // Strip a markdown <...> link target so it resolves like grammar.split_link_target does. inlineFmt
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

  // A compact native <select> of tags with per-tag counts (was a chip cloud that ate vertical
  // space). The stable #tag-filter container holds it; a delegated change listener does the filter.
  function renderTags() {
    var box = document.getElementById("tag-filter");
    var html = "<select id='tag-select'><option value=''>All tags (" + BUNDLE.pages.length +
      ")</option>";
    Object.keys(BUNDLE.tags).sort().forEach(function (tag) {
      html += "<option value='" + esc(tag) + "'" + (tag === activeTag ? " selected" : "") + ">" +
        esc(tag) + " (" + BUNDLE.tags[tag].length + ")</option>";
    });
    box.innerHTML = html + "</select>";
  }

  // Per-page provenance badges: raw citations (amber), model-supplied facts (purple), and
  // contradiction callouts (red). Only non-zero counts are shown, so a page's shape is legible at
  // a glance from the sidebar.
  function badgesHtml(p) {
    var out = "";
    if (p.cites) out += "<span class='badge badge-cite' title='" + p.cites +
      " citation(s) to raw sources'>&#8220;" + p.cites + "</span>";
    if (p.llm) out += "<span class='badge badge-llm' title='" + p.llm +
      " model-supplied (LLM) fact(s)'>LLM " + p.llm + "</span>";
    if (p.contradictions) out += "<span class='badge badge-contra' title='" + p.contradictions +
      " contradiction(s)'>&#9888; " + p.contradictions + "</span>";
    return out ? "<span class='badges'>" + out + "</span>" : "";
  }

  // A page passes the sidebar filters when it matches the active tag AND the active quick facet
  // (contradictions / LLM notes). Shared by browse mode and search mode.
  function passesFilters(p) {
    if (activeTag && p.tags.indexOf(activeTag) < 0) return false;
    if (activeFacet === "contradiction" && !p.contradictions) return false;
    if (activeFacet === "llm" && !p.llm) return false;
    return true;
  }

  // A whitespace-collapsed excerpt of `flat` centered on the first occurrence of `q` (already
  // lowercased) in `low`, with the hit wrapped in <mark> and ellipses where clipped. Falls back to
  // the head of the text when the match is only in the title/path/tags (not the body).
  function snippetHtml(flat, low, q) {
    var radius = 64, i = low.indexOf(q);
    if (i < 0) return esc(flat.slice(0, 2 * radius)) + (flat.length > 2 * radius ? "…" : "");
    var start = Math.max(0, i - radius), end = Math.min(flat.length, i + q.length + radius);
    return (start > 0 ? "…" : "") + esc(flat.slice(start, i)) + "<mark>" +
      esc(flat.slice(i, i + q.length)) + "</mark>" + esc(flat.slice(i + q.length, end)) +
      (end < flat.length ? "…" : "");
  }

  // Full-text ranking: title > tags > path > body, so a title hit sorts above a body-only hit.
  // Sources join the results only when neither a tag nor a facet is active (they carry no tags and
  // no contradiction/LLM markers, so a facet/tag filter is page-only).
  function searchResults(q) {
    var res = [];
    BUNDLE.pages.forEach(function (p) {
      if (!passesFilters(p)) return;
      var score = 0;
      if (p.lowTitle.indexOf(q) >= 0) score += 100;
      if (p.lowTags.indexOf(q) >= 0) score += 20;
      if (p.lowPath.indexOf(q) >= 0) score += 10;
      if (p.lowBody.indexOf(q) >= 0) score += 1;
      if (score) res.push({ kind: "page", id: p.rel_path, title: p.title, p: p, score: score });
    });
    if (!activeTag && !activeFacet) {
      Object.keys(SOURCES).forEach(function (id) {
        var s = SOURCES[id], score = 0;
        if (s.lowTitle.indexOf(q) >= 0) score += 80;
        if (s.lowId.indexOf(q) >= 0) score += 10;
        if (s.lowBody.indexOf(q) >= 0) score += 1;
        if (score) res.push({ kind: "source", id: id, title: s.title, s: s, score: score });
      });
    }
    res.sort(function (a, b) { return b.score - a.score || a.title.localeCompare(b.title); });
    return res;
  }

  function renderResults(q) {
    var res = searchResults(q), nav = document.getElementById("page-list");
    document.getElementById("source-list").innerHTML = "";  // sources appear inline in results
    if (!res.length) {
      nav.innerHTML = "<p class='ext'>No matches for “" + esc(q) + "”.</p>";
      return;
    }
    var html = "<div class='result-head'>" + res.length + " result" +
      (res.length === 1 ? "" : "s") + "</div>";
    res.forEach(function (r) {
      if (r.kind === "page") {
        var p = r.p;
        html += "<a class='result' href='#" + encodeURIComponent(p.rel_path) + "' data-page='" +
          esc(p.rel_path) + "'><span class='result-title'>" + esc(p.title) + "</span>" +
          badgesHtml(p) + "<span class='result-snip'>" +
          snippetHtml(p.flat, p.lowBody, q) + "</span></a>";
      } else {
        var s = r.s;
        html += "<a class='result src' href='#src:" + encodeURIComponent(r.id) +
          "' data-source='" + esc(r.id) + "' data-pop='" + esc(r.id) +
          "'><span class='result-title'>" + esc(s.title) + "</span><span class='result-snip'>" +
          snippetHtml(s.flat, s.lowBody, q) + "</span></a>";
      }
    });
    nav.innerHTML = html;
    markActiveNav();
  }

  function renderSidebar() {
    query = (document.getElementById("search").value || "").trim().toLowerCase();
    renderFacets();
    if (query) { renderResults(query); return; }  // full-text mode
    var nav = document.getElementById("page-list"), html = "";
    Object.keys(BUNDLE.types).sort().forEach(function (type) {
      var rels = BUNDLE.types[type].filter(function (rel) { return passesFilters(PAGES[rel]); });
      if (!rels.length) return;
      html += "<details open><summary>" + esc(type) + " (" + rels.length + ")</summary>";
      rels.forEach(function (rel) {
        var p = PAGES[rel];
        html += "<a class='navitem' href='#" + encodeURIComponent(rel) + "' data-page='" +
          esc(rel) + "'>" + esc(p.title) + badgesHtml(p) + "</a>";
      });
      html += "</details>";
    });
    nav.innerHTML = html || "<p class='ext'>No pages.</p>";
    renderSources();
    markActiveNav();
  }

  // The contradiction / LLM quick-filter chips, each with a live corpus count. Clicking a chip
  // toggles the facet; only chips with a non-zero count are shown.
  function renderFacets() {
    var box = document.getElementById("facets");
    if (!box) return;
    var nContra = 0, nLlm = 0;
    BUNDLE.pages.forEach(function (p) { if (p.contradictions) nContra++; if (p.llm) nLlm++; });
    var html = "";
    if (nContra) html += "<span class='facet contra" +
      (activeFacet === "contradiction" ? " active" : "") +
      "' data-facet='contradiction'>&#9888; Contradictions " + nContra + "</span>";
    if (nLlm) html += "<span class='facet llm" + (activeFacet === "llm" ? " active" : "") +
      "' data-facet='llm'>LLM notes " + nLlm + "</span>";
    box.innerHTML = html;
  }

  // The Sources browse axis: a sidebar group listing every embedded source with its citation
  // count. Shown only in browse mode with no tag/facet active (sources carry neither); in search
  // mode they surface inline in the ranked results instead.
  function renderSources() {
    var box = document.getElementById("source-list");
    if (!box) return;
    if (activeTag || activeFacet) { box.innerHTML = ""; return; }
    var ids = Object.keys(SOURCES).sort();
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
    var nodes = [], edges = [], idx = {}, adj = {};
    var view = { x: 0, y: 0, k: 1 };
    var activeRel = "";
    var showSources = false;
    var hiddenTypes = {};  // type name -> 1 when that category is toggled off in the legend
    var hoverIdx = null;   // index of the hovered node (dims non-neighbours), or null
    var raf = null, animating = false;
    var dragNode = null, panning = false, last = null, moved = false;
    var W = 600, H = 420;

    function r2(v) { return Math.round(v * 10) / 10; }

    function buildModel() {
      var pgs = BUNDLE.pages.filter(function (p) { return !hiddenTypes[p.type || "Untyped"]; });
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
      // Adjacency (by node index) for the hover-highlight; reset any stale hover on rebuild.
      adj = {}; hoverIdx = null;
      edges.forEach(function (e) {
        (adj[e.s] = adj[e.s] || {})[e.t] = 1;
        (adj[e.t] = adj[e.t] || {})[e.s] = 1;
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
      var hi = hoverIdx;
      for (i = 0; i < edges.length; i++) {
        var a = nodes[edges[i].s], b = nodes[edges[i].t];
        var edim = hi != null && edges[i].s !== hi && edges[i].t !== hi ? " dim" : "";
        s += "<line class='" + (edges[i].src ? "src" : "") + edim + "' x1='" + r2(a.x) + "' y1='" +
             r2(a.y) + "' x2='" + r2(b.x) + "' y2='" + r2(b.y) + "'/>";
      }
      for (i = 0; i < nodes.length; i++) {
        var nd = nodes[i];
        var label = nd.title.length > 18 ? nd.title.slice(0, 17) + "…" : nd.title;
        var act = nd.id === activeRel ? " active" : "";
        var ndim = hi != null && i !== hi && !(adj[hi] && adj[hi][i]) ? " dim" : "";
        if (nd.kind === "source") {
          s += "<g class='node src" + act + ndim + "' data-page='" + esc(nd.id) + "'><rect x='" +
               r2(nd.x - 6) + "' y='" + r2(nd.y - 6) + "' width='12' height='12' rx='2' fill='" +
               SOURCE_COLOR + "'/><text x='" + r2(nd.x) + "' y='" + r2(nd.y - 11) +
               "' text-anchor='middle'>" + esc(label) + "</text></g>";
        } else {
          s += "<g class='node" + act + ndim + "' data-page='" + esc(nd.id) + "'><circle cx='" +
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
      // Hover-highlight a node's neighbourhood (skip while dragging/panning; draw-only, no re-layout).
      svg.addEventListener("mousemove", function (ev) {
        if (dragNode || panning) return;
        var g = ev.target.closest ? ev.target.closest(".node") : null;
        var ni = g ? idx[g.getAttribute("data-page")] : null;
        if (ni == null) ni = null;
        if (ni !== hoverIdx) { hoverIdx = ni; draw(); }
      });
      svg.addEventListener("mouseleave", function () {
        if (hoverIdx !== null) { hoverIdx = null; draw(); }
      });
    }

    function setActive(rel) { activeRel = rel; draw(); }
    function setShowSources(on) { showSources = on; buildModel(); settle(); refit(); }

    return { init: init, zoom: zoom, refit: refit, setActive: setActive,
             setShowSources: setShowSources, showsSources: function () { return showSources; },
             isHidden: function (t) { return !!hiddenTypes[t]; },
             hiddenList: function () { return Object.keys(hiddenTypes); },
             // Restore the hidden-category set without rebuilding (call before init()).
             setHidden: function (arr) {
               hiddenTypes = {};
               (arr || []).forEach(function (t) { hiddenTypes[t] = 1; });
             },
             setHiddenType: function (t, hide) {
               if (hide) hiddenTypes[t] = 1; else delete hiddenTypes[t];
               buildModel(); settle(); refit();
             } };
  })();

  // ---- The reader: render a page or a source into the article pane, then decorate it. ----

  function renderReader(html) {
    var reader = document.getElementById("reader");
    reader.innerHTML = html;
    reader.scrollTop = 0;
    decorateReader(reader);
    applyHighlight(reader, true);  // opening a doc scrolls to the first hit
  }

  // Unwrap any existing <mark> spans so the reader can be re-highlighted for a new query without a
  // full re-render (which would lose the scroll position while typing).
  function clearMarks(reader) {
    var marks = reader.querySelectorAll("mark");
    Array.prototype.forEach.call(marks, function (m) {
      m.parentNode.replaceChild(document.createTextNode(m.textContent), m);
    });
    if (marks.length) reader.normalize();  // merge split text nodes so future matches span
  }

  // Reader provenance summary: citations (static), plus jump-to chips for the first model-supplied
  // fact and the first contradiction — so "find the contradictions in this page" is one click.
  function statsHtml(p) {
    var out = "";
    if (p.cites) out += "<span class='stat stat-cite' title='citations to raw sources'>&#8220;" +
      p.cites + " citation" + (p.cites === 1 ? "" : "s") + "</span>";
    if (p.llm) out += "<a class='stat stat-llm' href='#' data-jump='llm' " +
      "title='jump to the first model-supplied fact'>LLM " + p.llm + " note" +
      (p.llm === 1 ? "" : "s") + "</a>";
    if (p.contradictions) out += "<a class='stat stat-contra' href='#' data-jump='contra' " +
      "title='jump to the first contradiction'>&#9888; " + p.contradictions + " contradiction" +
      (p.contradictions === 1 ? "" : "s") + "</a>";
    return out ? "<div class='stats'>" + out + "</div>" : "";
  }

  // Wrap every occurrence of `needle` (already lowercased) in matching reader text nodes with a
  // <mark>, returning the first mark (or null). DOM-safe — it only ever splits text nodes, never
  // touches tags/attributes. Skips the table-of-contents so its nav copy isn't marked.
  function markAll(reader, needle) {
    var walker = document.createTreeWalker(reader, NodeFilter.SHOW_TEXT, null);
    var targets = [], node;
    while ((node = walker.nextNode())) {
      var par = node.parentNode;
      if (!par || /^(SCRIPT|STYLE|MARK)$/.test(par.nodeName)) continue;
      if (par.closest && par.closest(".toc")) continue;
      if (node.nodeValue.toLowerCase().indexOf(needle) >= 0) targets.push(node);
    }
    var first = null;
    targets.forEach(function (n) {
      var text = n.nodeValue, low = text.toLowerCase(), frag = document.createDocumentFragment();
      var last = 0, i;
      while ((i = low.indexOf(needle, last)) >= 0) {
        if (i > last) frag.appendChild(document.createTextNode(text.slice(last, i)));
        var mk = document.createElement("mark");
        mk.textContent = text.slice(i, i + needle.length);
        frag.appendChild(mk);
        if (!first) first = mk;
        last = i + needle.length;
      }
      if (last < text.length) frag.appendChild(document.createTextNode(text.slice(last)));
      n.parentNode.replaceChild(frag, n);
    });
    return first;
  }

  // Highlight the active query in the reader and (with `scroll`) bring the first hit into view (on
  // navigation; live typing passes false so the page doesn't jump). Tries the whole phrase first;
  // if it matches nothing — the search index collapses newlines but the reader keeps block
  // structure, so a multi-word phrase can straddle a heading/paragraph boundary — it falls back to
  // highlighting each term, so a clicked result never lands on a page with no visible hit. No-op
  // when there is no query.
  function applyHighlight(reader, scroll) {
    if (!query) return;
    var first = markAll(reader, query);
    if (!first && query.indexOf(" ") >= 0) {
      var seen = {};
      query.split(/\s+/).forEach(function (term) {
        if (!term || seen[term]) return;
        seen[term] = 1;
        var f = markAll(reader, term);
        if (!first) first = f;
      });
    }
    if (scroll && first) first.scrollIntoView({ block: "center" });
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
    if (safeHash() !== rel) {
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
    renderReader("<h1>" + esc(p.title) + "</h1>" + meta + statsHtml(p) +
      (p.description ? "<p class='desc'>" + esc(p.description) + "</p>" : "") +
      backlinkList("Referenced by:", p.inbound) + backlinkList("Links to:", p.outbound) +
      "<hr>" + mdToHtml(p.body, p.rel_path, fnSrc));
    Graph.setActive(rel);
    markActiveNav();
  }

  function rawFileLink(s, label) {
    if (!s.href || s.missing) return "";
    return "<a class='rawfile' href='" + esc(encodeURI(s.href)) +
      "' target='_blank' rel='noopener'>" + label + " ↗</a>";
  }

  function lineSpan(a, b) { return a === b ? ("line " + a) : ("lines " + a + "–" + b); }

  // A muted "⋯ lines X–Y not embedded" row between/around embedded segments, with an
  // open-the-original affordance (reusing the source's href) for the elided passage.
  function segGap(s, from, to) {
    var link = rawFileLink(s, "open the original file");
    return "<div class='seg-gap'>⋯ " + lineSpan(from, to) + " not embedded" +
      (link ? " — " + link : "") + "</div>";
  }

  // Render a source that embedded only its cited excerpts: each segment headed by a small "lines
  // A–B" label, with gap rows for the un-embedded stretches before/between/after them.
  function renderSegments(s, sid) {
    var out = [], prev = 0, total = s.total_lines || 0;
    (s.segments || []).forEach(function (g) {
      if (g.start > prev + 1) out.push(segGap(s, prev + 1, g.start - 1));
      out.push("<div class='seg' data-seg-start='" + g.start + "' data-seg-end='" + g.end +
        "'><div class='seg-label'>" + lineSpan(g.start, g.end) + "</div>" +
        mdToHtml(g.text, sid, {}) + "</div>");
      prev = g.end;
    });
    if (total > prev) out.push(segGap(s, prev + 1, total));
    return out.join("\n");
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
        "</code> was not found when this viewer was generated. Re-run <code>citadel view</code> " +
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
        (s.segments ? renderSegments(s, sid) : mdToHtml(s.body, sid, {}));
      if (s.truncated) {
        body += "<div class='callout'><div class='callout-title'>TRUNCATED</div>" +
          "<div class='callout-body'>This source was longer than the embed limit and was " +
          "truncated. Open the original file to read it in full.</div></div>";
      }
    }
    renderReader("<h1>" + esc(s.title) + "</h1>" + meta +
      backlinkList("Cited by:", s.cited_by) + "<hr>" + body);
    Graph.setActive("src:" + sid);
    markActiveNav();
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
    var jm = ev.target.closest("[data-jump]");
    if (jm) {
      ev.preventDefault();
      var rdr = document.getElementById("reader");
      var tgt = jm.getAttribute("data-jump") === "contra"
        ? rdr.querySelector(".callout-contradiction")
        : rdr.querySelector("[id^='ref-llm'], [id^='fn-llm']");
      if (tgt) tgt.scrollIntoView({ block: "center" });
      return;
    }
    var fc = ev.target.closest("[data-facet]");
    if (fc) {
      var f = fc.getAttribute("data-facet");
      activeFacet = activeFacet === f ? "" : f;  // toggle
      renderSidebar();
      return;
    }
    var tg = ev.target.closest("[data-tag]");
    if (tg) { activeTag = tg.getAttribute("data-tag"); renderTags(); renderSidebar(); }
  });
  // Typing updates the sidebar AND re-highlights the open reader in place (no scroll yank), so the
  // reader's highlight never goes stale relative to the query.
  document.getElementById("search").addEventListener("input", function () {
    renderSidebar();
    var reader = document.getElementById("reader");
    clearMarks(reader);
    applyHighlight(reader, false);
  });
  // Delegated on the stable #tag-filter container (renderTags rewrites its innerHTML each call).
  document.getElementById("tag-filter").addEventListener("change", function (ev) {
    if (ev.target.id === "tag-select") { activeTag = ev.target.value; renderSidebar(); }
  });
  // Enter in the search box jumps straight to the top-ranked full-text result.
  document.getElementById("search").addEventListener("keydown", function (ev) {
    if (ev.key !== "Enter") return;
    var q = (this.value || "").trim().toLowerCase();
    if (!q) return;
    var res = searchResults(q);
    if (!res.length) return;
    ev.preventDefault();
    if (res[0].kind === "source") openSource(res[0].id); else openPage(res[0].id);
  });
  document.addEventListener("keydown", function (ev) {
    if (ev.key === "/" && document.activeElement.id !== "search") {
      ev.preventDefault(); document.getElementById("search").focus();
    } else if (ev.key === "\\" && document.activeElement.id !== "search") {
      ev.preventDefault(); toggleSidebar();
    } else if (ev.key === "Escape") {
      hidePop();
      if (document.activeElement.id === "search") document.activeElement.blur();
    }
  });

  function route() {
    var h = safeHash();
    if (h.indexOf("src:") === 0) { if (SOURCES[h.slice(4)]) openSource(h.slice(4)); }
    else if (h && PAGES[h]) openPage(h);
  }
  window.addEventListener("hashchange", route);

  document.getElementById("wiki-name").textContent = BUNDLE.wiki_name || "Wiki";
  renderTags();
  renderSidebar();
  // Restore the hidden-category filter BEFORE the first layout so the initial map matches last session.
  try {
    var savedHidden = JSON.parse(localStorage.getItem("okf_hidden_types") || "[]");
    if (Array.isArray(savedHidden)) Graph.setHidden(savedHidden);
  } catch (e) {}
  Graph.init();

  // Interactive legend: every category (each page type + the Source layer) is a clickable chip
  // that toggles its nodes in the map, with a live count; a struck-through chip is hidden.
  function renderLegend() {
    var box = document.getElementById("graph-legend");
    if (!box) return;
    var counts = {};
    BUNDLE.pages.forEach(function (p) { var k = p.type || "Untyped"; counts[k] = (counts[k] || 0) + 1; });
    var html = Object.keys(BUNDLE.types).sort().map(function (t) {
      return "<span class='lg' data-legend='" + esc(t) + "'" + (Graph.isHidden(t) ? " data-off='1'" : "") +
        "><span class='sw' style='background:" + (typeColor[t] || "#888") + "'></span>" + esc(t) +
        " <span class='cnt'>" + (counts[t] || 0) + "</span></span>";
    }).join("");
    if (Object.keys(SOURCES).length) {
      var nSrc = Object.keys(SOURCES).filter(function (id) { return SOURCES[id].cited_by.length; }).length;
      html += "<span class='lg' data-legend='__source__'" + (Graph.showsSources() ? "" : " data-off='1'") +
        "><span class='sw src' style='background:" + SOURCE_COLOR + "'></span>Source <span class='cnt'>" +
        nSrc + "</span></span>";
    }
    box.innerHTML = html;
  }

  // Highlight the open page/source in the sidebar so the map, list, and reader read as one surface.
  // Safe in search mode and when the item is filtered out (querySelector simply finds nothing).
  function markActiveNav() {
    ["page-list", "source-list"].forEach(function (id) {
      var l = document.getElementById(id);
      if (!l) return;
      Array.prototype.forEach.call(l.querySelectorAll(".active"), function (n) {
        n.classList.remove("active");
      });
    });
    var h = safeHash();
    if (!h) return;
    var isSrc = h.indexOf("src:") === 0;
    var val = (isSrc ? h.slice(4) : h).replace(/(['\\])/g, "\\$1");
    var attr = isSrc ? "data-source" : "data-page";
    var el = document.querySelector("#page-list [" + attr + "='" + val + "'], #source-list [" +
      attr + "='" + val + "']");
    if (el) { el.classList.add("active"); el.scrollIntoView({ block: "nearest" }); }
  }

  // --- Map + reading toolbar wiring (everything below needs `content`/`app` in scope). ---
  var content = document.getElementById("content");
  var app = document.getElementById("app");
  var collapseBtn = document.getElementById("g-collapse");
  var expandBtn = document.getElementById("g-expand");
  var srcBtn = document.getElementById("g-sources");

  function setCollapsed(c) {
    content.classList.toggle("map-collapsed", c);
    if (c) { content.classList.remove("map-expanded"); expandBtn.classList.remove("active"); }
    collapseBtn.textContent = c ? "▸" : "▾";
    collapseBtn.title = c ? "Show map" : "Collapse map";
    try {
      localStorage.setItem("okf_map_collapsed", c ? "1" : "0");
      // Collapse and expand are mutually exclusive: persist the cleared state too, so collapsing an
      // expanded map doesn't restore as expanded on the next load (the restore applies expand last).
      if (c) localStorage.setItem("okf_map_expanded", "0");
    } catch (e) {}
    if (!c) Graph.refit();  // pane size changed — re-fit the layout
  }
  // Expand the map to full height (mutually exclusive with collapse); restoring re-fits the layout.
  function setExpanded(x) {
    if (x) setCollapsed(false);
    content.classList.toggle("map-expanded", x);
    expandBtn.classList.toggle("active", x);
    expandBtn.title = x ? "Restore map height" : "Expand map to full height";
    try { localStorage.setItem("okf_map_expanded", x ? "1" : "0"); } catch (e) {}
    Graph.refit();
  }
  collapseBtn.addEventListener("click", function () {
    setCollapsed(!content.classList.contains("map-collapsed"));
  });
  expandBtn.addEventListener("click", function () {
    setExpanded(!content.classList.contains("map-expanded"));
  });
  document.getElementById("g-zoomin").addEventListener("click", function () { Graph.zoom(1.25); });
  document.getElementById("g-zoomout").addEventListener("click", function () { Graph.zoom(0.8); });
  document.getElementById("g-fit").addEventListener("click", function () { Graph.refit(); });
  document.getElementById("g-random").addEventListener("click", function () {
    var ps = BUNDLE.pages;
    if (ps.length) openPage(ps[Math.floor(Math.random() * ps.length)].rel_path);
  });

  function setShowSources(on) {
    Graph.setShowSources(on);
    srcBtn.classList.toggle("active", on);
    srcBtn.title = on ? "Hide sources in the map" : "Show sources in the map";
    try { localStorage.setItem("okf_show_sources", on ? "1" : "0"); } catch (e) {}
    renderLegend();  // keep the Source legend chip in sync with the toolbar button
  }
  srcBtn.addEventListener("click", function () {
    setShowSources(!srcBtn.classList.contains("active"));
  });

  // The legend needs its own listener: the global document click handler early-returns inside
  // #graph-pane, so a data-legend branch there would never fire.
  document.getElementById("graph-legend").addEventListener("click", function (ev) {
    var el = ev.target.closest ? ev.target.closest("[data-legend]") : null;
    if (!el) return;
    var t = el.getAttribute("data-legend");
    if (t === "__source__") { setShowSources(!srcBtn.classList.contains("active")); }
    else {
      Graph.setHiddenType(t, !Graph.isHidden(t));
      try { localStorage.setItem("okf_hidden_types", JSON.stringify(Graph.hiddenList())); } catch (e) {}
      renderLegend();
    }
  });

  // Sidebar collapse (focus/reading mode); the toggle lives in the map bar so it stays reachable.
  function toggleSidebar() {
    app.classList.toggle("sb-collapsed");
    try { localStorage.setItem("okf_sb_collapsed", app.classList.contains("sb-collapsed") ? "1" : "0"); } catch (e) {}
    Graph.refit();
  }
  document.getElementById("g-sidebar").addEventListener("click", toggleSidebar);

  // Reading-width cycle (comfortable -> wide -> full), persisted; only the reader column changes.
  var RW = ["rw-comfortable", "rw-wide", "rw-full"], rwi = 0;
  function setWidth(i) {
    rwi = (((i | 0) % 3) + 3) % 3;  // `| 0` coerces NaN/fractional/corrupt values to a valid slot
    content.classList.remove("rw-comfortable", "rw-wide", "rw-full");
    content.classList.add(RW[rwi]);
    try { localStorage.setItem("okf_reader_width", String(rwi)); } catch (e) {}
  }
  document.getElementById("g-width").addEventListener("click", function () { setWidth(rwi + 1); });

  // Theme cycle (auto -> light -> dark), persisted; "auto" defers to the OS via prefers-color-scheme.
  var THEMES = ["auto", "light", "dark"], themeBtn = document.getElementById("g-theme");
  function setTheme(t) {
    if (t !== "light" && t !== "dark") t = "auto";  // coerce unknown/corrupt stored values back to auto
    if (t === "auto") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", t);
    themeBtn.textContent = t === "light" ? "☀" : (t === "dark" ? "☾" : "◐");
    themeBtn.title = "Theme: " + t + " (click to change)";
    try { localStorage.setItem("okf_theme", t); } catch (e) {}
  }
  themeBtn.addEventListener("click", function () {
    var cur = document.documentElement.getAttribute("data-theme") || "auto";
    setTheme(THEMES[(THEMES.indexOf(cur) + 1) % THEMES.length]);
  });

  // Draggable splitter to resize the map height (its own drag flag, independent of node drag/pan;
  // both window handlers early-return unless their own flag is set). Re-fit only on release.
  var gRez = document.getElementById("graph-resizer"), gPane = document.getElementById("graph-pane");
  var gDrag = false;
  gRez.addEventListener("mousedown", function (ev) {
    gDrag = true; gRez.classList.add("drag"); document.body.style.userSelect = "none"; ev.preventDefault();
  });
  window.addEventListener("mousemove", function (ev) {
    if (!gDrag) return;
    var top = content.getBoundingClientRect().top;
    gPane.style.height = Math.max(120, Math.min(content.clientHeight - 120, ev.clientY - top)) + "px";
  });
  window.addEventListener("mouseup", function () {
    if (!gDrag) return;
    gDrag = false; gRez.classList.remove("drag"); document.body.style.userSelect = "";
    try { localStorage.setItem("okf_map_h", gPane.style.height); } catch (e) {}
    Graph.refit();
  });

  // Restore persisted view state, then re-fit once the pane geometry is final.
  try { var mh = localStorage.getItem("okf_map_h"); if (mh) gPane.style.height = mh; } catch (e) {}
  try { setWidth(+(localStorage.getItem("okf_reader_width") || 0)); } catch (e) { setWidth(0); }
  try { setTheme(localStorage.getItem("okf_theme") || "auto"); } catch (e) { setTheme("auto"); }
  try { if (localStorage.getItem("okf_show_sources") === "1") setShowSources(true); } catch (e) {}
  try { if (localStorage.getItem("okf_sb_collapsed") === "1") app.classList.add("sb-collapsed"); } catch (e) {}
  try { if (localStorage.getItem("okf_map_collapsed") === "1") setCollapsed(true); } catch (e) {}
  try { if (localStorage.getItem("okf_map_expanded") === "1") setExpanded(true); } catch (e) {}
  renderLegend();
  Graph.refit();

  var rt;
  window.addEventListener("resize", function () {
    clearTimeout(rt); rt = setTimeout(function () { Graph.refit(); }, 150);
  });

  var initial = safeHash();
  if (initial.indexOf("src:") === 0 && SOURCES[initial.slice(4)]) openSource(initial.slice(4));
  else if (initial && PAGES[initial]) openPage(initial);
  else if (BUNDLE.pages.length) openPage(BUNDLE.pages[0].rel_path);
})();
