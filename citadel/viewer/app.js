(function () {
  "use strict";
  var BUNDLE = JSON.parse(document.getElementById("bundle").textContent);
  var PAGES = {};
  BUNDLE.pages.forEach(function (p) { PAGES[p.rel_path] = p; });
  var SOURCES = BUNDLE.sources || {};
  // The full 8-hue colorblind-safe brand palette (green pinned first) — 8 hues so the topic
  // legend's top-8 clusters never share a color.
  var TYPE_COLORS = ["#009E73", "#C475FD", "#4467A3", "#BD8233", "#AE3030", "#2ABCCD", "#954477", "#99B314"];
  var SOURCE_COLOR = "#6B6A63";
  var OTHER_COLOR = "#8C8B82";  // muted warm gray for the grouped "other" topic bucket (singletons)
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
    // Default CLOSED (the source list is a long secondary axis), but honor a persisted user toggle.
    var open = false;
    try { open = localStorage.getItem("okf_sources_open") === "1"; } catch (e) {}
    var html = "<details class='src-axis'" + (open ? " open" : "") +
      "><summary>Sources (" + ids.length + ")</summary>";
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
    var nodes = [], edges = [], simEdges = [], idx = {}, adj = {};
    var view = { x: 0, y: 0, k: 1 };
    var activeRel = "";
    var showSources = false;
    var colorMode = "topic";       // "topic" (cluster color) | "type" (page-type color)
    var hiddenTypes = {};  // type name -> 1 when that category is toggled off in the legend
    var hiddenTopics = {}; // cluster key -> 1 when that topic cluster is toggled off (topic mode)
    var hoverIdx = null;   // index of the hovered node (dims non-neighbours), or null
    var degCut = 1;        // real-link-degree threshold above which a label always renders
    var raf = null, animating = false;
    var dragNode = null, panning = false, last = null, moved = false, activePointer = null;
    var W = 600, H = 420;

    function r2(v) { return Math.round(v * 10) / 10; }

    // Topic communities via DETERMINISTIC label propagation over the combined edge set (real link
    // edges weight 1.0 + tag-similarity edges weight = their similarity). Computed ONCE over EVERY
    // page — independent of any legend toggle — so colours/sizes/names never shift when a cluster is
    // hidden. There is NO Math.random: the assignment is byte-identical on every load.
    //   * combined weighted adjacency: real links weight 1.0, sim edges weight = similarity, summed
    //     where a pair carries both;
    //   * asynchronous sweeps in FIXED page-index order — each node adopts the neighbour label with
    //     the greatest summed incident edge weight (ties -> the SMALLER label id); an edgeless node
    //     keeps its own label; stop at a fixed point or after 20 sweeps;
    //   * communities of fewer than 2 members collapse into one muted "__other__" bucket;
    //   * each surviving community is NAMED by the tag with the highest summed IDF over its members
    //     (zero-IDF tags skipped), falling back to its dominant page type, then "cluster"; a name
    //     collision is broken deterministically (its next-best tag, else a numeric suffix).
    // Returns { of: rel_path -> cluster key, list: size-desc [{key,label,size,color}] (+ a muted
    // "__other__" bucket, then an empty "__sources__" bucket), index: key -> list position }.
    var _clusters = null;
    function clusters() {
      if (_clusters) return _clusters;
      var pages = BUNDLE.pages, P = pages.length;
      var pidx = {};
      pages.forEach(function (p, i) { pidx[p.rel_path] = i; });

      // Combined weighted adjacency over PAGE nodes (undirected, weights summed on overlap).
      var nbr = pages.map(function () { return {}; });
      function link(a, b, w) {
        if (a == null || b == null || a === b) return;
        nbr[a][b] = (nbr[a][b] || 0) + w;
        nbr[b][a] = (nbr[b][a] || 0) + w;
      }
      BUNDLE.edges.forEach(function (e) { link(pidx[e.source], pidx[e.target], 1.0); });
      simEdgesFor(pages).forEach(function (e) { link(e.s, e.t, e.w); });

      // Deterministic asynchronous label propagation (fixed index order, tie -> smaller label id).
      var label = pages.map(function (_p, i) { return i; });
      for (var sweep = 0; sweep < 20; sweep++) {
        var changed = false;
        for (var i = 0; i < P; i++) {
          var ns = nbr[i], keys = Object.keys(ns);
          if (!keys.length) continue;                    // edgeless node keeps its own label
          var wsum = {};
          for (var k = 0; k < keys.length; k++) {
            var lab = label[+keys[k]];
            wsum[lab] = (wsum[lab] || 0) + ns[keys[k]];
          }
          var best = label[i], bestW = -1;
          for (var l in wsum) {
            var lw = wsum[l], li = +l;
            if (lw > bestW || (lw === bestW && li < best)) { bestW = lw; best = li; }
          }
          if (best !== label[i]) { label[i] = best; changed = true; }
        }
        if (!changed) break;
      }

      // Group members by final label.
      var groups = {};
      for (var m = 0; m < P; m++) (groups[label[m]] = groups[label[m]] || []).push(m);

      // Corpus IDF (the same ubiquity machinery the sim edges use) for community naming.
      var ubiq = 0.67 * P, idf = {};
      Object.keys(BUNDLE.tags).forEach(function (t) {
        var df = BUNDLE.tags[t].length;
        idf[t] = (df <= 0 || df > ubiq) ? 0 : Math.log(P / df);
      });

      // Real communities (>= 2 members): rank their tags by summed IDF + find the dominant type.
      var comms = Object.keys(groups).filter(function (g) { return groups[g].length >= 2; })
        .map(function (g) {
          var mem = groups[g], tagW = {}, typeN = {};
          mem.forEach(function (pi) {
            var pg = pages[pi];
            (pg.tags || []).forEach(function (t) { if (idf[t]) tagW[t] = (tagW[t] || 0) + idf[t]; });
            var ty = pg.type || "Untyped"; typeN[ty] = (typeN[ty] || 0) + 1;
          });
          var tags = Object.keys(tagW).sort(function (a, b) {
            return tagW[b] - tagW[a] || (a < b ? -1 : a > b ? 1 : 0);
          });
          var domType = Object.keys(typeN).sort(function (a, b) {
            return typeN[b] - typeN[a] || (a < b ? -1 : a > b ? 1 : 0);
          })[0];
          return { members: mem, tags: tags, domType: domType, size: mem.length,
                   first: Math.min.apply(null, mem) };
        });
      // Rank size-desc (tie -> smallest member index) so the palette assignment is stable.
      comms.sort(function (a, b) { return b.size - a.size || a.first - b.first; });

      // Name each community; break collisions deterministically (next-best tag, then a suffix).
      var used = {};
      comms.forEach(function (c) {
        var name = c.tags.length ? c.tags[0] : (c.domType || "cluster");
        if (used[name]) {
          var alt = c.tags.length > 1 ? name + "/" + c.tags[1] : null;
          if (alt && !used[alt]) { name = alt; }
          else { var n = 2; while (used[name + " " + n]) n++; name = name + " " + n; }
        }
        used[name] = 1;
        c.label = name;
        c.key = "topic:" + name;
      });

      // Assemble the catalogue + the rel_path -> key map.
      var of = {}, list = [], index = {};
      comms.forEach(function (c, i) {
        index[c.key] = i;
        c.members.forEach(function (pi) { of[pages[pi].rel_path] = c.key; });
        list.push({ key: c.key, label: c.label, size: c.size,
                    color: TYPE_COLORS[i % TYPE_COLORS.length] });
      });
      // Singletons (edgeless / unmergeable pages) share one muted "other" bucket.
      var otherN = 0;
      Object.keys(groups).forEach(function (g) {
        if (groups[g].length < 2) {
          groups[g].forEach(function (pi) { of[pages[pi].rel_path] = "__other__"; otherN++; });
        }
      });
      if (otherN) {
        index["__other__"] = list.length;
        list.push({ key: "__other__", label: "other", size: otherN, color: OTHER_COLOR });
      }
      index["__sources__"] = list.length;
      list.push({ key: "__sources__", label: "Sources", size: 0, color: SOURCE_COLOR });

      _clusters = { of: of, list: list, index: index };
      return _clusters;
    }

    // A page's community (cluster) key — the label-propagation assignment computed in clusters().
    function clusterKey(p) { return clusters().of[p.rel_path] || "__other__"; }

    // Deterministic FNV-1a hash of a string -> two signed jitter offsets in [-70, 70], so a node's
    // seed position is reproducible (no Math.random) yet spread inside its cluster.
    function hashJitter(str) {
      var h = 2166136261;
      for (var i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; }
      return { x: (h % 141) - 70, y: ((h >>> 8) % 141) - 70 };
    }

    // Weighted-Jaccard similarity of two tag-weight maps: sum(min)/sum(max) over the key union.
    function wjaccard(A, B) {
      var num = 0, den = 0, k;
      for (k in A) { var b = B[k] || 0; num += Math.min(A[k], b); den += Math.max(A[k], b); }
      for (k in B) { if (!(k in A)) den += B[k]; }
      return den > 0 ? num / den : 0;
    }

    // Tag-similarity KNN edges (the anyplot mechanism): IDF-weighted tag vectors + a soft type
    // token, top-K neighbours per page kept as faint edges. Returns index-pair edges { s, t, w }
    // over `pgs` (w = weighted-Jaccard similarity). Pure + deterministic — no shared state — so both
    // the layout springs and the community detection can call it. One-time O(n^2) per call — fine at
    // wiki scale, so it is simply skipped past 1500 pages.
    function simEdgesFor(pgs) {
      var out = [], N = pgs.length;
      if (N > 1500 || N < 2) return out;
      var ubiq = 0.67 * N, idfw = {};
      Object.keys(BUNDLE.tags).forEach(function (t) {
        var df = BUNDLE.tags[t].length;
        idfw[t] = (df <= 0 || df > ubiq) ? 0 : Math.log(N / df);  // zero out ubiquitous tags
      });
      var maps = pgs.map(function (p) {
        var m = {};
        (p.tags || []).forEach(function (t) { if (idfw[t]) m["tag:" + t] = idfw[t]; });
        m["type:" + (p.type || "Untyped")] = 0.8;  // soft type token
        return m;
      });
      var K = 6, MINSIM = 0.12, seen = {};
      for (var i = 0; i < N; i++) {
        var cand = [];
        for (var j = 0; j < N; j++) {
          if (j === i) continue;
          var sim = wjaccard(maps[i], maps[j]);
          if (sim >= MINSIM) cand.push({ j: j, sim: sim });
        }
        cand.sort(function (a, b) { return b.sim - a.sim || a.j - b.j; });  // tie -> lower index (deterministic)
        for (var c = 0; c < cand.length && c < K; c++) {
          var b2 = cand[c].j, key = i < b2 ? i + "," + b2 : b2 + "," + i;
          if (seen[key]) continue;
          seen[key] = 1;
          out.push({ s: i, t: b2, sim: true, w: cand[c].sim });
        }
      }
      return out;
    }

    // The LAYOUT-ONLY tag-similarity springs over the currently visible `pgs` (indices match `pgs`).
    function buildSimEdges(pgs) { simEdges = simEdgesFor(pgs); }

    function buildModel() {
      var cl = clusters();
      var pgs = BUNDLE.pages.filter(function (p) {
        return colorMode === "topic" ? !hiddenTopics[clusterKey(p)]
                                     : !hiddenTypes[p.type || "Untyped"];
      });
      var srcIds = showSources
        ? Object.keys(SOURCES).filter(function (id) { return SOURCES[id].cited_by.length; })
        : [];
      var C = cl.list.length;
      function seed(cluster, id) {
        var ang = 2 * Math.PI * cluster / C, jt = hashJitter(id);
        return { x: W / 2 + Math.cos(ang) * 160 + jt.x, y: H / 2 + Math.sin(ang) * 160 + jt.y };
      }
      nodes = pgs.map(function (p) {
        var ci = cl.index[clusterKey(p)], s = seed(ci, p.rel_path);
        return { id: p.rel_path, kind: "page", type: p.type, title: p.title, cluster: ci,
                 x: s.x, y: s.y, vx: 0, vy: 0, fx: null, fy: null, deg: 0 };
      });
      srcIds.forEach(function (id) {
        // A source inherits its dominant citing-page cluster (max overlap), else the sources bucket.
        var tally = {}, bestKey = null, bestN = 0;
        SOURCES[id].cited_by.forEach(function (rel) {
          var pp = PAGES[rel]; if (!pp) return;
          var ck = clusterKey(pp), v = (tally[ck] = (tally[ck] || 0) + 1);
          if (v > bestN) { bestN = v; bestKey = ck; }
        });
        var ci = bestKey != null ? cl.index[bestKey] : cl.index["__sources__"];
        var s = seed(ci, "src:" + id);
        nodes.push({ id: "src:" + id, kind: "source", type: "__source__", title: SOURCES[id].title,
                     cluster: ci, x: s.x, y: s.y, vx: 0, vy: 0, fx: null, fy: null, deg: 0 });
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
      // Adjacency from link + citation edges (sim edges are layout aids, never neighbours); the
      // declutter degree counts PAGE-PAGE links only, so toggling the source layer never shifts
      // which labels show. Reset any stale hover on rebuild.
      adj = {}; hoverIdx = null;
      edges.forEach(function (e) {
        (adj[e.s] = adj[e.s] || {})[e.t] = 1;
        (adj[e.t] = adj[e.t] || {})[e.s] = 1;
        if (!e.src) { nodes[e.s].deg++; nodes[e.t].deg++; }
      });
      // Label declutter threshold: the ~60th-percentile degree, so only the top ~40% of connected
      // nodes label by default (floored at 1 so degree-0 nodes never label except on hover/zoom).
      var degs = nodes.map(function (nd) { return nd.deg; }).sort(function (a, b) { return a - b; });
      degCut = degs.length ? Math.max(1, degs[Math.floor(degs.length * 0.6)]) : 1;
      // Tag-similarity springs over the page nodes (indices 0..pgs.length-1, matching `pgs` order).
      buildSimEdges(pgs);
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
        simEdges.forEach(function (e) {  // tag-similarity springs pull half as hard as real links
          var dx = nodes[e.s].x - nodes[e.t].x, dy = nodes[e.s].y - nodes[e.t].y;
          var d = Math.sqrt(dx * dx + dy * dy) || 0.01, f = (d * d / k) * 0.5;
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
      var i, j;
      // Per-cluster centroids (O(n)) so gravity pulls each node toward ITS cluster, not one global
      // point — this is what makes the clusters actually separate on screen.
      var cen = {};
      for (i = 0; i < n; i++) {
        var c = nodes[i].cluster, acc = cen[c] || (cen[c] = { x: 0, y: 0, n: 0 });
        acc.x += nodes[i].x; acc.y += nodes[i].y; acc.n++;
      }
      for (var ck in cen) { cen[ck].x /= cen[ck].n; cen[ck].y /= cen[ck].n; }
      var REP = 2400, GRAV = 0.012, DAMP = 0.9, MAXV = 50, MIN = 22;
      for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) {
        var dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
        var d2 = dx * dx + dy * dy + 0.01, d = Math.sqrt(d2);
        var f = Math.min(REP / d2, 40);
        if (d < MIN) f += (MIN - d) * 0.5;  // hard collision separation for overlapping nodes
        var ux = dx / d * f, uy = dy / d * f;
        nodes[i].vx += ux; nodes[i].vy += uy;
        nodes[j].vx -= ux; nodes[j].vy -= uy;
      }
      edges.forEach(function (e) {  // real link springs: short + stiff
        var a = nodes[e.s], b = nodes[e.t];
        var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        var f = (d - 80) * 0.03, ux = dx / d * f, uy = dy / d * f;
        a.vx += ux; a.vy += uy; b.vx -= ux; b.vy -= uy;
      });
      simEdges.forEach(function (e) {  // tag-similarity springs: longer + soft, scaled by similarity
        var a = nodes[e.s], b = nodes[e.t];
        var dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        var f = (d - 120) * (0.012 * e.w), ux = dx / d * f, uy = dy / d * f;
        a.vx += ux; a.vy += uy; b.vx -= ux; b.vy -= uy;
      });
      var maxd = 0;
      for (i = 0; i < n; i++) {
        var nd = nodes[i];
        if (nd.fx != null) { nd.x = nd.fx; nd.y = nd.fy; nd.vx = 0; nd.vy = 0; continue; }
        var g = cen[nd.cluster];
        nd.vx = (nd.vx + (g.x - nd.x) * GRAV) * DAMP;
        nd.vy = (nd.vy + (g.y - nd.y) * GRAV) * DAMP;
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
      var hi = hoverIdx, cl = clusters().list, revealAll = view.k > 1.4;
      // Sim edges are barely-visible dashed layout aids, drawn behind the real link edges.
      for (i = 0; i < simEdges.length; i++) {
        var sa = nodes[simEdges[i].s], sb = nodes[simEdges[i].t];
        s += "<line class='sim' x1='" + r2(sa.x) + "' y1='" + r2(sa.y) + "' x2='" + r2(sb.x) +
             "' y2='" + r2(sb.y) + "'/>";
      }
      for (i = 0; i < edges.length; i++) {
        var a = nodes[edges[i].s], b = nodes[edges[i].t];
        var edim = hi != null && edges[i].s !== hi && edges[i].t !== hi ? " dim" : "";
        s += "<line class='" + (edges[i].src ? "src" : "") + edim + "' x1='" + r2(a.x) + "' y1='" +
             r2(a.y) + "' x2='" + r2(b.x) + "' y2='" + r2(b.y) + "'/>";
      }
      for (i = 0; i < nodes.length; i++) {
        var nd = nodes[i];
        var act = nd.id === activeRel ? " active" : "";
        var isNb = hi != null && (i === hi || (adj[hi] && adj[hi][i]));
        var ndim = hi != null && i !== hi && !(adj[hi] && adj[hi][i]) ? " dim" : "";
        // Declutter: a label renders only when the node is hovered/its neighbour, or it is a
        // top-degree hub, or the user has zoomed in (dimmed non-neighbours also hide text via CSS).
        var label = (isNb || revealAll || nd.deg >= degCut)
          ? "<text x='" + r2(nd.x) + "' y='" + r2(nd.y - 11) + "' text-anchor='middle'>" +
            esc(nd.title.length > 18 ? nd.title.slice(0, 17) + "…" : nd.title) + "</text>"
          : "";
        if (nd.kind === "source") {
          s += "<g class='node src" + act + ndim + "' data-page='" + esc(nd.id) + "'><rect x='" +
               r2(nd.x - 6) + "' y='" + r2(nd.y - 6) + "' width='12' height='12' rx='2' fill='" +
               SOURCE_COLOR + "'/>" + label + "</g>";
        } else {
          var fill = colorMode === "topic"
            ? (cl[nd.cluster] ? cl[nd.cluster].color : "#888") : (typeColor[nd.type] || "#888");
          s += "<g class='node" + act + ndim + "' data-page='" + esc(nd.id) + "'><circle cx='" +
               r2(nd.x) + "' cy='" + r2(nd.y) + "' r='7' fill='" + fill + "'/>" + label + "</g>";
        }
      }
      gzoom.innerHTML = s;
      gzoom.setAttribute("transform", "translate(" + r2(view.x) + "," + r2(view.y) +
        ") scale(" + (Math.round(view.k * 1000) / 1000) + ")");
    }

    // frame() runs the live model until motion dies down, but a hard per-reheat frame budget caps
    // it: a few dense layouts never fully quiesce below the motion threshold (collision + per-
    // cluster gravity keep a couple of nodes jittering), and without the cap the init reheat would
    // spin rAF forever. The budget is topped up while a node is being dragged (user-driven).
    var SETTLE_FRAMES = 400, frameBudget = 0;
    function frame() {
      var moving = simStep();
      draw();
      if (dragNode) { frameBudget = SETTLE_FRAMES; raf = requestAnimationFrame(frame); }
      else if (moving > 0.4 && frameBudget-- > 0) { raf = requestAnimationFrame(frame); }
      else { animating = false; raf = null; }
    }
    function reheat() {
      frameBudget = SETTLE_FRAMES;
      if (!animating) { animating = true; raf = requestAnimationFrame(frame); }
    }

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

    // Pointer Events (not mouse) so one-finger pan, node drag, and tap-to-open work on touch and
    // nothing regresses for mouse. setPointerCapture keeps move/up flowing to the SVG even if the
    // pointer leaves it mid-drag, so the window-level mouse listeners are no longer needed.
    function onDown(ev) {
      if (activePointer != null) return;  // ignore a second finger (single-pointer pan/drag)
      var g = ev.target.closest ? ev.target.closest(".node") : null;
      last = { x: ev.clientX, y: ev.clientY }; moved = false;
      if (g) {
        dragNode = nodes[idx[g.getAttribute("data-page")]];
        dragNode.fx = dragNode.x; dragNode.fy = dragNode.y;  // pin in place until moved
      } else { panning = true; svg.classList.add("grabbing"); }
      activePointer = ev.pointerId;
      try { svg.setPointerCapture(ev.pointerId); } catch (e) {}
      ev.preventDefault();
    }
    function onMove(ev) {
      if (!dragNode && !panning) return;
      if (activePointer != null && ev.pointerId !== activePointer) return;
      var dx = ev.clientX - last.x, dy = ev.clientY - last.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      if (dragNode) {
        var w = toWorld(ev);
        dragNode.fx = w.x; dragNode.fy = w.y; dragNode.x = w.x; dragNode.y = w.y;
        reheat();
      } else if (panning) { view.x += dx; view.y += dy; draw(); }
      last = { x: ev.clientX, y: ev.clientY };
    }
    function onUp(ev) {
      if (activePointer != null && ev && ev.pointerId !== activePointer) return;
      if (dragNode) {
        var node = dragNode;
        dragNode.fx = null; dragNode.fy = null; dragNode = null;
        if (!moved) {  // a click/tap (no drag) opens the page or source
          if (node.id.indexOf("src:") === 0) openSource(node.id.slice(4));
          else openPage(node.id);
        }
        reheat();
      }
      panning = false; if (svg) svg.classList.remove("grabbing");
      if (ev) { try { svg.releasePointerCapture(ev.pointerId); } catch (e) {} }
      activePointer = null;
    }

    function init() {
      svg = document.getElementById("graph");
      // Seed the layout box from the real pane size when it's laid out, so density scales with the
      // viewport (fall back to the 600x420 defaults when the pane isn't measurable yet).
      var r = svg.getBoundingClientRect ? svg.getBoundingClientRect() : null;
      if (r && r.width && r.height) { W = r.width; H = r.height; }
      svg.innerHTML = "<g id='gzoom'></g>";
      gzoom = document.getElementById("gzoom");
      buildModel();
      settle();
      refit();
      reheat();  // let the refined model (collision + cluster gravity + sim springs) settle the picture
      svg.addEventListener("pointerdown", onDown);
      svg.addEventListener("pointermove", onMove);
      svg.addEventListener("pointerup", onUp);
      svg.addEventListener("pointercancel", onUp);
      svg.addEventListener("wheel", function (ev) {
        ev.preventDefault();
        var sz = size();
        zoomAt(ev.deltaY < 0 ? 1.12 : 1 / 1.12, ev.clientX - sz.left, ev.clientY - sz.top);
      }, { passive: false });
      // Hover-highlight a node's neighbourhood (skip while dragging/panning; draw-only, no re-layout).
      svg.addEventListener("pointermove", function (ev) {
        if (dragNode || panning) return;
        var g = ev.target.closest ? ev.target.closest(".node") : null;
        var ni = g ? idx[g.getAttribute("data-page")] : null;
        if (ni == null) ni = null;
        if (ni !== hoverIdx) { hoverIdx = ni; draw(); }
      });
      svg.addEventListener("pointerleave", function () {
        if (hoverIdx !== null) { hoverIdx = null; draw(); }
      });
    }

    function setActive(rel) { activeRel = rel; draw(); }
    // A rebuild re-seeds the model, re-runs the FR settle, re-fits, then reheats so the refined
    // simStep model (collision + cluster gravity + sim springs) relaxes the final picture.
    function rebuild() { buildModel(); settle(); refit(); reheat(); }
    function setShowSources(on) { showSources = on; rebuild(); }

    // Topic-cluster legend data: the top clusters as individual toggles + one grouped "other"
    // bucket for the remainder (all with size over every page, so the list is stable).
    function topicLegend() {
      // Named communities only compete for the top slots; the muted "__other__" bucket is always
      // grouped into "other" (never colour-ranked), joined by any community beyond the top 8.
      var cl = clusters().list.filter(function (c) {
        return c.key !== "__sources__" && c.key !== "__other__" && c.size > 0;
      });
      var top = cl.slice(0, 8).map(function (c) {
        return { key: c.key, label: c.label, color: c.color, size: c.size,
                 hidden: !!hiddenTopics[c.key] };
      });
      var rest = cl.slice(8), keys = rest.map(function (c) { return c.key; });
      var oi = clusters().index["__other__"];
      var otherCluster = oi != null ? clusters().list[oi] : null;
      if (otherCluster) keys.push("__other__");
      var other = null;
      if (keys.length) {
        var sz = 0, allHidden = true;
        rest.forEach(function (c) { sz += c.size; if (!hiddenTopics[c.key]) allHidden = false; });
        if (otherCluster) {
          sz += otherCluster.size;
          if (!hiddenTopics["__other__"]) allHidden = false;
        }
        other = { size: sz, hidden: allHidden, keys: keys };
      }
      return { top: top, other: other };
    }

    return { init: init, zoom: zoom, refit: refit, setActive: setActive,
             setShowSources: setShowSources, showsSources: function () { return showSources; },
             colorMode: function () { return colorMode; },
             // How many REAL topic communities exist (excl. the "other"/Sources buckets) — lets the
             // boot code default a one-community wiki to type colours, where topic mode is monochrome.
             topicCount: function () {
               return clusters().list.filter(function (c) {
                 return c.key !== "__other__" && c.key !== "__sources__";
               }).length;
             },
             // Set the colour mode (before init, without a rebuild) / at runtime (rebuilds).
             setColorInit: function (m) { colorMode = m === "type" ? "type" : "topic"; },
             setColorMode: function (m) { colorMode = m === "type" ? "type" : "topic"; rebuild(); },
             isHidden: function (t) { return !!hiddenTypes[t]; },
             hiddenList: function () { return Object.keys(hiddenTypes); },
             // Restore the hidden-category set without rebuilding (call before init()).
             setHidden: function (arr) {
               hiddenTypes = {};
               (arr || []).forEach(function (t) { hiddenTypes[t] = 1; });
             },
             setHiddenType: function (t, hide) {
               if (hide) hiddenTypes[t] = 1; else delete hiddenTypes[t];
               rebuild();
             },
             topicLegend: topicLegend,
             isTopicHidden: function (k) { return !!hiddenTopics[k]; },
             hiddenTopicList: function () { return Object.keys(hiddenTopics); },
             setHiddenTopics: function (arr) {
               hiddenTopics = {};
               (arr || []).forEach(function (k) { hiddenTopics[k] = 1; });
             },
             setHiddenTopic: function (k, hide) {
               if (hide) hiddenTopics[k] = 1; else delete hiddenTopics[k];
               rebuild();
             },
             // Toggle the whole "other" bucket as a group: hide all when any is shown, else show all.
             toggleOther: function () {
               var o = topicLegend().other; if (!o) return;
               var hide = !o.hidden;
               o.keys.forEach(function (k) { if (hide) hiddenTopics[k] = 1; else delete hiddenTopics[k]; });
               rebuild();
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

  // ---- Compact "## Sources" rendering. ----
  // The trailing Sources section renders one .fndef per footnote — a same file repeated many times,
  // each with its own link, "(ingested ...)" date and back-arrow: a tall footnote wall. These helpers
  // rewrite it into a collapsed <details> that GROUPS citations by the source file they resolve to,
  // showing the file link + date once, then that file's citations as a compact run (or one line each
  // when they carry distinct notes). Every citation keeps its own id="fn-sN" so the inline [^sN] jump,
  // the fnref highlight, and the hover popovers still work per citation.

  // Peel a trailing "(ingested YYYY-MM-DD)" / "(added ...)" (or any year-bearing parenthesis, for a
  // translated wiki) off a footnote tail, returning the remaining text and the date text.
  function stripDate(s) {
    var m = s.match(/\(((?:ingested|added)[^)]*)\)\s*$/i);
    if (!m) m = s.match(/\(([^)]*\d{4}[^)]*)\)\s*$/);
    if (m) return { rest: s.slice(0, m.index).replace(/\s+$/, ""), date: m[1].trim() };
    return { rest: s, date: "" };
  }

  // Parse one rendered .fndef div into { fid, key, header, date, locator, note }. `key` groups
  // by the cited file (its data-source / link text) — or "__llm__" for a model-knowledge note.
  function parseDef(div) {
    var fid = (div.id || "").replace(/^fn-/, "");
    var isLlm = /^llm/i.test(fid);
    var linkEl = div.querySelector("a.srclink") || div.querySelector("a[data-source]") ||
                 div.querySelector("a") || div.querySelector(".ext");
    var clone = div.cloneNode(true), x;
    if ((x = clone.querySelector(".fnid"))) x.parentNode.removeChild(x);
    if ((x = clone.querySelector(".fnback"))) x.parentNode.removeChild(x);
    if (!isLlm && linkEl) {
      var lc = clone.querySelector("a.srclink") || clone.querySelector("a[data-source]") ||
               clone.querySelector("a") || clone.querySelector(".ext");
      if (lc) lc.parentNode.removeChild(lc);
    }
    var tail = (clone.textContent || "").replace(/\s+/g, " ").trim();
    var d = stripDate(tail); tail = d.rest.replace(/^[,;]\s*/, "");
    var locator = "", note = "";
    if (isLlm) {
      note = tail.replace(/^LLM\b\s*[-–—:,]?\s*/i, "").trim();
      if (/^model knowledge/i.test(note)) note = "";  // the generic boilerplate adds nothing
    } else {
      var dash = tail.indexOf(" — ");  // "locator — note"
      if (dash >= 0) { locator = tail.slice(0, dash).trim(); note = tail.slice(dash + 3).trim(); }
      else { locator = tail; }
    }
    var key = isLlm ? "__llm__"
      : (linkEl ? (linkEl.getAttribute("data-source") || linkEl.textContent) : "__" + fid);
    var header = isLlm ? "<span class='src-label'>Model knowledge (LLM)</span>"
      : (linkEl ? linkEl.outerHTML : esc(key));
    return { fid: fid, key: key, header: header, date: d.date, locator: locator, note: note };
  }

  // Replace the reader's "## Sources" heading + its .fndef run with a grouped, collapsed <details>.
  // The heading is matched with the grammar's laxness (SOURCES_HEADING_RE: case-insensitive
  // "sources" word) — the heading stays literal even in non-English wikis, it is a format invariant.
  function compactSources(reader) {
    var heads = reader.querySelectorAll("h2"), head = null, i;
    for (i = 0; i < heads.length; i++) {
      if (/^sources\b/i.test((heads[i].textContent || "").trim())) { head = heads[i]; break; }
    }
    if (!head) return;
    var defs = [], removable = [], sib = head.nextSibling;
    while (sib) {
      if (sib.nodeType === 1 && /^H[1-6]$/.test(sib.nodeName)) break;  // next section ends Sources
      removable.push(sib);
      if (sib.nodeType === 1 && sib.classList && sib.classList.contains("fndef")) defs.push(sib);
      sib = sib.nextSibling;
    }
    if (!defs.length) return;
    var order = [], groups = {};
    defs.forEach(function (div) {
      var info = parseDef(div), g = groups[info.key];
      if (!g) { g = groups[info.key] = { header: info.header, date: info.date, cites: [] }; order.push(info.key); }
      if (!g.date && info.date) g.date = info.date;
      g.cites.push(info);
    });
    var body = order.map(function (key) {
      var g = groups[key], noteless = [], noted = [];
      g.cites.forEach(function (c) { (c.note ? noted : noteless).push(c); });
      var run = noteless.length ? "<div class='src-cites'>" + noteless.map(function (c) {
        return "<span class='fncite' id='fn-" + esc(c.fid) + "'>" + esc(c.fid) +
          (c.locator ? " <span class='fnloc'>(" + esc(c.locator) + ")</span>" : "") + "</span>";
      }).join(", ") + "</div>" : "";
      var lines = noted.map(function (c) {
        return "<div class='src-cite' id='fn-" + esc(c.fid) + "'><span class='fncid'>" + esc(c.fid) +
          "</span>" + (c.locator ? " <span class='fnloc'>(" + esc(c.locator) + ")</span>" : "") +
          " <span class='src-note'>— " + esc(c.note) + "</span></div>";
      }).join("");
      return "<div class='src-group'><div class='src-group-head'>" + g.header +
        (g.date ? " <span class='src-date'>(" + esc(g.date) + ")</span>" : "") + "</div>" + run + lines + "</div>";
    }).join("");
    var details = document.createElement("details");
    details.className = "sources";
    details.innerHTML = "<summary>Sources (" + defs.length + ")</summary>" + body;
    head.parentNode.insertBefore(details, head);
    removable.forEach(function (n) { if (n.parentNode) n.parentNode.removeChild(n); });
    if (head.parentNode) head.parentNode.removeChild(head);
  }

  // Add a collapsible table of contents for any page/source with enough headings, giving every
  // heading a stable id to jump to.
  function decorateReader(reader) {
    compactSources(reader);
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
    // An inline [^sN] jump lands inside the collapsed Sources <details> — open it first so the
    // browser's native anchor scroll can reach the (now visible) definition.
    var fnj = ev.target.closest && ev.target.closest("a[href^='#fn-']");
    if (fnj) {
      var det = document.querySelector("#reader details.sources");
      if (det && !det.open) det.open = true;  // no return: let the native scroll proceed
    }
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
  // Persist the sidebar Sources <details> open/closed state (the `toggle` event does not bubble, so
  // capture it on the stable #source-list container that renderSources rewrites each render).
  document.getElementById("source-list").addEventListener("toggle", function (ev) {
    var d = ev.target;
    if (d && d.classList && d.classList.contains("src-axis")) {
      try { localStorage.setItem("okf_sources_open", d.open ? "1" : "0"); } catch (e) {}
    }
  }, true);
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
    // A footnote/marker anchor (#fn-sN / #ref-sN) opens the collapsed Sources section and scrolls to
    // the definition — covers hashchange/direct-URL navigation as well as an in-page marker click.
    if (h.indexOf("fn-") === 0 || h.indexOf("ref-") === 0) {
      var det = document.querySelector("#reader details.sources");
      if (det) det.open = true;
      var t = document.getElementById(h);
      if (t) t.scrollIntoView({ block: "center" });
      return;
    }
    if (h.indexOf("src:") === 0) { if (SOURCES[h.slice(4)]) openSource(h.slice(4)); }
    else if (h && PAGES[h]) openPage(h);
    else return;
    // Navigating to a page/source dismisses the mobile drawer, so the reader is visible at once.
    if (isSmall()) app.classList.remove("sb-open");
  }
  window.addEventListener("hashchange", route);

  document.getElementById("wiki-name").textContent = BUNDLE.wiki_name || "Wiki";
  renderTags();
  renderSidebar();
  // Restore the map's colour mode + both hidden sets BEFORE the first layout so the initial map
  // matches last session (topic mode is the default). Type and topic hidden sets use separate keys
  // so switching modes never corrupts either.
  try {
    var savedMode = localStorage.getItem("okf_color_mode");
    // No explicit choice yet: topic colours by default, EXCEPT when the whole wiki is a single
    // community (e.g. one dense narrative) — topic mode would be monochrome, so start on type.
    var defMode = Graph.topicCount() > 1 ? "topic" : "type";
    Graph.setColorInit(savedMode === "type" || savedMode === "topic" ? savedMode : defMode);
  } catch (e) {}
  try {
    var savedHidden = JSON.parse(localStorage.getItem("okf_hidden_types") || "[]");
    if (Array.isArray(savedHidden)) Graph.setHidden(savedHidden);
  } catch (e) {}
  try {
    var savedTopics = JSON.parse(localStorage.getItem("okf_hidden_topics") || "[]");
    if (Array.isArray(savedTopics)) Graph.setHiddenTopics(savedTopics);
  } catch (e) {}
  Graph.init();

  // Interactive legend: every category is a clickable chip that toggles its nodes in the map, with a
  // live count; a struck-through chip is hidden. In topic mode it lists the top clusters (+ an
  // "other" bucket); in type mode it lists the page types. The Source-layer chip stays in both.
  function chip(key, label, color, off, srcSwatch) {
    return "<span class='lg' data-legend='" + esc(key) + "'" + (off ? " data-off='1'" : "") +
      "><span class='sw" + (srcSwatch ? " src" : "") + "' style='background:" + color + "'></span>" +
      esc(label) + " <span class='cnt'>";
  }
  function renderLegend() {
    var box = document.getElementById("graph-legend");
    if (!box) return;
    var html = "";
    if (Graph.colorMode() === "topic") {
      var tl = Graph.topicLegend();
      html = tl.top.map(function (c) {
        return chip(c.key, c.label, c.color, c.hidden, false) + c.size + "</span></span>";
      }).join("");
      if (tl.other) {
        html += chip("__other__", "other", "var(--muted)", tl.other.hidden, false) +
          tl.other.size + "</span></span>";
      }
    } else {
      var counts = {};
      BUNDLE.pages.forEach(function (p) { var k = p.type || "Untyped"; counts[k] = (counts[k] || 0) + 1; });
      html = Object.keys(BUNDLE.types).sort().map(function (t) {
        return chip(t, t, typeColor[t] || "#888", Graph.isHidden(t), false) +
          (counts[t] || 0) + "</span></span>";
      }).join("");
    }
    if (Object.keys(SOURCES).length) {
      var nSrc = Object.keys(SOURCES).filter(function (id) { return SOURCES[id].cited_by.length; }).length;
      html += chip("__source__", "Source", SOURCE_COLOR, !Graph.showsSources(), true) +
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

  // Colour-by toggle: injected into the map bar (topic clusters vs page type). Created in JS so the
  // packaged template stays untouched. Default topic; the active (green) state means topic mode.
  var colorBtn = document.createElement("button");
  colorBtn.className = "gbtn";
  colorBtn.id = "g-color";
  colorBtn.type = "button";
  colorBtn.innerHTML = "&#9686;";  // half-shaded circle: "colour by"
  srcBtn.parentNode.insertBefore(colorBtn, srcBtn);
  function setColorMode(m, initial) {
    if (!initial) Graph.setColorMode(m);
    var topic = Graph.colorMode() === "topic";
    colorBtn.classList.toggle("active", topic);
    colorBtn.title = topic ? "Colour: topic (click for type)" : "Colour: type (click for topic)";
    try { localStorage.setItem("okf_color_mode", topic ? "topic" : "type"); } catch (e) {}
    renderLegend();
  }
  colorBtn.addEventListener("click", function () {
    setColorMode(Graph.colorMode() === "topic" ? "type" : "topic");
  });
  setColorMode(Graph.colorMode(), true);  // reflect the restored mode without a rebuild

  // The legend needs its own listener: the global document click handler early-returns inside
  // #graph-pane, so a data-legend branch there would never fire.
  document.getElementById("graph-legend").addEventListener("click", function (ev) {
    var el = ev.target.closest ? ev.target.closest("[data-legend]") : null;
    if (!el) return;
    var t = el.getAttribute("data-legend");
    if (t === "__source__") { setShowSources(!srcBtn.classList.contains("active")); return; }
    if (Graph.colorMode() === "topic") {
      if (t === "__other__") Graph.toggleOther();
      else Graph.setHiddenTopic(t, !Graph.isTopicHidden(t));
      try { localStorage.setItem("okf_hidden_topics", JSON.stringify(Graph.hiddenTopicList())); } catch (e) {}
    } else {
      Graph.setHiddenType(t, !Graph.isHidden(t));
      try { localStorage.setItem("okf_hidden_types", JSON.stringify(Graph.hiddenList())); } catch (e) {}
    }
    renderLegend();
  });

  // Sidebar collapse (focus/reading mode); the toggle lives in the map bar so it stays reachable.
  // On a small screen the sidebar is an off-canvas drawer: the same button/shortcut slides it in and
  // out via `sb-open` (default closed) instead of the desktop `sb-collapsed` (default open).
  function isSmall() { return window.matchMedia("(max-width: 720px)").matches; }
  function toggleSidebar() {
    if (isSmall()) { app.classList.toggle("sb-open"); return; }
    app.classList.remove("sb-open");
    app.classList.toggle("sb-collapsed");
    try { localStorage.setItem("okf_sb_collapsed", app.classList.contains("sb-collapsed") ? "1" : "0"); } catch (e) {}
    Graph.refit();
  }
  document.getElementById("g-sidebar").addEventListener("click", toggleSidebar);
  // A dim backdrop behind the open mobile drawer; tapping it closes the drawer. Inert (display:none)
  // on desktop, so the desktop layout is untouched.
  var backdrop = document.createElement("div");
  backdrop.id = "sb-backdrop";
  app.appendChild(backdrop);
  backdrop.addEventListener("click", function () { app.classList.remove("sb-open"); });

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

  // Draggable splitter to resize the map height (its own drag flag, independent of node drag/pan).
  // pointerdown starts the drag on the splitter; move/up/cancel are WINDOW listeners that
  // early-return unless the flag is set, so the drag ends reliably even when setPointerCapture is
  // unavailable and the pointer leaves the 6px splitter. Re-fit only on release.
  var gRez = document.getElementById("graph-resizer"), gPane = document.getElementById("graph-pane");
  var gDrag = false;
  gRez.addEventListener("pointerdown", function (ev) {
    gDrag = true; gRez.classList.add("drag"); document.body.style.userSelect = "none";
    try { gRez.setPointerCapture(ev.pointerId); } catch (e) {}
    ev.preventDefault();
  });
  window.addEventListener("pointermove", function (ev) {
    if (!gDrag) return;
    var top = content.getBoundingClientRect().top;
    gPane.style.height = Math.max(120, Math.min(content.clientHeight - 120, ev.clientY - top)) + "px";
  });
  function endResize() {
    if (!gDrag) return;
    gDrag = false; gRez.classList.remove("drag"); document.body.style.userSelect = "";
    try { localStorage.setItem("okf_map_h", gPane.style.height); } catch (e) {}
    Graph.refit();
  }
  window.addEventListener("pointerup", endResize);
  window.addEventListener("pointercancel", endResize);

  // Restore persisted view state, then re-fit once the pane geometry is final.
  try { var mh = localStorage.getItem("okf_map_h"); if (mh) gPane.style.height = mh; } catch (e) {}
  try { setWidth(+(localStorage.getItem("okf_reader_width") || 0)); } catch (e) { setWidth(0); }
  try { setTheme(localStorage.getItem("okf_theme") || "auto"); } catch (e) { setTheme("auto"); }
  try { if (localStorage.getItem("okf_show_sources") === "1") setShowSources(true); } catch (e) {}
  try { if (localStorage.getItem("okf_sb_collapsed") === "1") app.classList.add("sb-collapsed"); } catch (e) {}
  try { if (localStorage.getItem("okf_map_collapsed") === "1") setCollapsed(true); } catch (e) {}
  try { if (localStorage.getItem("okf_map_expanded") === "1") setExpanded(true); } catch (e) {}
  // On a small screen the map eats the viewport, so default it COLLAPSED on first load — but only
  // when the user has expressed no map preference yet (a persisted choice always wins).
  try {
    if (window.matchMedia("(max-width: 720px)").matches &&
        localStorage.getItem("okf_map_collapsed") === null &&
        localStorage.getItem("okf_map_expanded") === null) {
      setCollapsed(true);
    }
  } catch (e) {}
  renderLegend();
  Graph.refit();
  // Print: force the collapsed Sources section open so citations print, then restore afterwards.
  window.addEventListener("beforeprint", function () {
    var d = document.querySelector("#reader details.sources");
    if (d) { d._wasOpen = d.open; d.open = true; }
  });
  window.addEventListener("afterprint", function () {
    var d = document.querySelector("#reader details.sources");
    if (d && !d._wasOpen) d.open = false;
  });

  var rt;
  window.addEventListener("resize", function () {
    clearTimeout(rt); rt = setTimeout(function () { Graph.refit(); }, 150);
  });

  var initial = safeHash();
  if (initial.indexOf("src:") === 0 && SOURCES[initial.slice(4)]) openSource(initial.slice(4));
  else if (initial && PAGES[initial]) openPage(initial);
  else if (BUNDLE.pages.length) openPage(BUNDLE.pages[0].rel_path);
})();
