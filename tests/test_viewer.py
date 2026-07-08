"""Offline tests for the self-contained HTML viewer.

No browser, no network: every test only calls build_bundle/build_html/write_viewer/view and
asserts on strings (webbrowser.open is monkeypatched). Filesystem state is redirected to
tmp_path by the shared ``tmp_citadel`` fixture (see conftest.py).
"""

from __future__ import annotations

import json
import re

from citadel import manifest, store, viewer


def _two_page_wiki(seed_page) -> None:
    seed_page(
        "concepts/espresso.md",
        {
            "type": "Concept",
            "title": "Espresso",
            "description": "A brew method.",
            "tags": ["brewing", "coffee"],
            "resource": "raw/a.md",
        },
        "Espresso uses pressure.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n (ingested 2026-06-22)\n",
    )
    seed_page(
        "concepts/caffeine.md",
        {
            "type": "Concept",
            "title": "Caffeine",
            "description": "The stimulant.",
            "tags": ["coffee"],
            "resource": "raw/a.md",
        },
        "See [Espresso](./espresso.md) for the shot.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - n (ingested 2026-06-22)\n",
    )


def _embedded_bundle(html: str) -> tuple[str, dict]:
    """Pull the embedded JSON bundle out of a built viewer document: returns ``(blob, bundle)``
    where ``blob`` is the raw (still ``<\\/``-escaped) script payload and ``bundle`` is the dict
    parsed after the documented unescape."""
    m = re.search(r'<script id="bundle" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert m, "embedded bundle script not found"
    blob = m.group(1)
    return blob, json.loads(blob.replace("<\\/", "</"))


def test_bundle_embeds_cited_sources(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text(
        "# Coffee Overview\n\nCoffee is a brewed drink made from roasted beans.\n", encoding="utf-8"
    )
    _two_page_wiki(seed_page)
    sources = viewer.build_bundle()["sources"]

    assert "raw/a.md" in sources
    s = sources["raw/a.md"]
    assert s["missing"] is False
    assert s["title"] == "Coffee Overview"
    assert "brewed drink" in s["body"]
    assert "brewed drink" in s["snippet"]
    # Both pages cite raw/a.md (resource frontmatter + a ## Sources footnote link).
    assert set(s["cited_by"]) == {"concepts/espresso.md", "concepts/caffeine.md"}


def test_binary_pdf_source_is_openable_not_unavailable(tmp_citadel, seed_page):
    # A real PDF is binary (not UTF-8). It must not be reported as missing — instead it carries an
    # "open the original file" href so the browser can show it natively.
    (tmp_citadel.raw / "a.pdf").write_bytes(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n")
    seed_page(
        "concepts/x.md",
        {"type": "Concept", "title": "X"},
        "Body cites a pdf.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.pdf](../../raw/a.pdf) - n\n",
    )
    s = viewer.build_bundle()["sources"]["raw/a.pdf"]
    assert s["missing"] is False
    assert s["kind"] == "binary"
    assert s["body"] == ""
    assert s["href"] == "../raw/a.pdf"
    assert s["cited_by"] == ["concepts/x.md"]


def test_missing_source_is_flagged_not_fatal(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)  # cites raw/a.md, but the raw file is absent
    s = viewer.build_bundle()["sources"]["raw/a.md"]
    assert s["missing"] is True
    assert s["body"] == ""
    assert set(s["cited_by"]) == {"concepts/espresso.md", "concepts/caffeine.md"}


def test_build_html_makes_sources_clickable(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text("# A\n\nbody text\n", encoding="utf-8")
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    # The inlined viewer renders raw citations as clickable source links and can open them.
    assert "data-source" in html
    assert "srclink" in html
    assert "openSource" in html
    # Still fully offline with an embedded source present.
    for bad in ("http://", "https://", "cdn", " src=", "fetch("):
        assert bad not in html, f"network reference present: {bad!r}"


def test_sources_keyed_by_browser_identity_in_nested_layout(tmp_path, make_citadel, seed_page):
    # When wiki/ is NOT a direct child of the repo root (e.g. CITADEL_WIKI_DIR=sub/wiki), the citation
    # climbs further but the in-browser resolver clamps '..' at the wiki root. The embedded source
    # must be keyed under that SAME clamped id, else the citation can't find it.
    cit = make_citadel(wiki=tmp_path / "sub" / "wiki")
    (cit.raw / "x.md").write_text("# X source\n\ndetail\n", encoding="utf-8")
    # From repo/sub/wiki/concepts/p.md to repo/raw/x.md is '../../../raw/x.md'.
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites x.[^s1]\n\n## Sources\n\n[^s1]: [raw/x.md](../../../raw/x.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    # Keyed by the clamped identity the browser produces, not the WIKI_DIR.parent-relative '../raw/x.md'.
    assert "raw/x.md" in sources
    assert "../raw/x.md" not in sources
    assert sources["raw/x.md"]["cited_by"] == ["concepts/p.md"]


def test_sources_truncated_when_oversized(tmp_citadel, seed_page):
    # A source too big to embed whole is excerpted, not embedded as a truncated whole body: the
    # total embedded text is capped at _SOURCE_MAX_CHARS and the record is flagged truncated.
    big = "x" * (viewer._SOURCE_MAX_CHARS + 50)
    (tmp_citadel.raw / "a.md").write_text(big, encoding="utf-8")
    _two_page_wiki(seed_page)
    s = viewer.build_bundle()["sources"]["raw/a.md"]
    assert "body" not in s
    assert s["truncated"] is True
    assert sum(len(g["text"]) for g in s["segments"]) == viewer._SOURCE_MAX_CHARS


# --------------------------------------------------------------------------------------
# Cited-excerpt embedding: a large source embeds only the passages the wiki cites (plus a few
# lines of context), keyed by locator, rather than its whole body. Short/mostly-cited files still
# embed whole (body key). See viewer._source_excerpts / _embed_source.
# --------------------------------------------------------------------------------------


def _numbered_source(n: int) -> str:
    """A source whose i-th line is literally ``line i`` (1-based), for locator assertions."""
    return "\n".join(f"line {i}" for i in range(1, n + 1))


def _cite(seed_page, defs: str, *, rel: str = "concepts/p.md", body: str = "Fact.[^s1]") -> None:
    """Seed one page whose ``## Sources`` section is exactly ``defs`` (the footnote def lines)."""
    seed_page(rel, {"type": "Concept", "title": "P"}, f"{body}\n\n## Sources\n\n{defs}\n")


def test_large_source_embeds_only_cited_line_ranges_with_context(tmp_citadel, seed_page):
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(200), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), lines 40-52 (ingested 2026-06-22)")
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert "body" not in s  # excerpted, not whole
    assert s["total_lines"] == 200
    assert s["truncated"] is False
    assert [(g["start"], g["end"]) for g in s["segments"]] == [(37, 55)]  # 40-52 padded by 3
    seg = s["segments"][0]
    assert seg["text"].startswith("line 37")
    assert seg["text"].endswith("line 55")


def test_overlapping_and_near_adjacent_ranges_merge(tmp_citadel, seed_page):
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(200), encoding="utf-8")
    # 40-52 -> [37,55] and 50-60 -> [47,63] overlap -> merge to [37,63];
    # 100-100 -> [97,103] and 108-108 -> [105,111] have a 1-line gap -> merge to [97,111].
    _cite(
        seed_page,
        "[^s1]: [big](../../raw/big.md), lines 40-52\n"
        "[^s2]: [big](../../raw/big.md), lines 50-60\n"
        "[^s3]: [big](../../raw/big.md), lines 100-100\n"
        "[^s4]: [big](../../raw/big.md), lines 108-108",
        body="A.[^s1] B.[^s2] C.[^s3] D.[^s4]",
    )
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert [(g["start"], g["end"]) for g in s["segments"]] == [(37, 63), (97, 111)]


def test_line_locator_past_eof_clamps_to_eof(tmp_citadel, seed_page):
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(200), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), lines 500-510")
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert [(g["start"], g["end"]) for g in s["segments"]] == [(197, 200)]
    assert s["segments"][0]["text"].endswith("line 200")


def test_heading_locator_resolves_the_section(tmp_citadel, seed_page):
    lines = ["# Intro"] + [f"line {i}" for i in range(2, 41)]
    lines += ["## Section A"] + [f"line {i}" for i in range(42, 59)] + ["## Section B"]
    lines += [f"line {i}" for i in range(60, 201)]
    (tmp_citadel.raw / "big.md").write_text("\n".join(lines), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), § Section A")
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    # Section A spans its heading line (41) up to the line before ## Section B (59) -> [41, 58].
    assert [(g["start"], g["end"]) for g in s["segments"]] == [(41, 58)]
    assert s["segments"][0]["text"].startswith("## Section A")


def test_heading_locator_section_capped(tmp_citadel, seed_page):
    lines = ["# Intro"] + [f"line {i}" for i in range(2, 59)] + ["## Section B"]
    lines += [f"line {i}" for i in range(60, 201)]  # Section B runs 59..200, no further heading
    (tmp_citadel.raw / "big.md").write_text("\n".join(lines), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), § Section B")
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    # 59..200 is 142 lines; the section embed is capped at 80 -> [59, 138].
    assert [(g["start"], g["end"]) for g in s["segments"]] == [(59, 138)]


def test_unlocated_citation_gets_head_excerpt(tmp_citadel, seed_page):
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(200), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md) - just a note (ingested 2026-06-22)")
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert [(g["start"], g["end"]) for g in s["segments"]] == [(1, 30)]  # head excerpt
    assert s["segments"][0]["text"].startswith("line 1")


def test_short_source_embeds_whole(tmp_citadel, seed_page):
    src = _numbered_source(100)  # <= 120 lines: never fragmented
    (tmp_citadel.raw / "big.md").write_text(src, encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), lines 10-12")
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert "segments" not in s
    assert s["body"] == src


def test_mostly_cited_source_embeds_whole(tmp_citadel, seed_page):
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(150), encoding="utf-8")
    # lines 1-98 -> [1,101]: 101 of 150 lines >= 2/3, so embed the whole file, not segments.
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), lines 1-98")
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert "segments" not in s
    assert s["body"].endswith("line 150")


def test_source_max_chars_guards_total_excerpt(tmp_citadel, seed_page, monkeypatch):
    monkeypatch.setattr(viewer, "_SOURCE_MAX_CHARS", 40)
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(200), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), lines 40-52")  # [37,55], well over 40 chars
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert s["truncated"] is True
    assert sum(len(g["text"]) for g in s["segments"]) <= 40


def test_budget_drops_whole_trailing_segments_not_mid_passage(tmp_citadel, seed_page, monkeypatch):
    # When the budget is exhausted between segments, the remaining WHOLE segments are dropped (and
    # the record flagged truncated) rather than slicing one off mid-passage — so a hugely-cited
    # source embeds only the segments that fit, keeping the standalone document small.
    monkeypatch.setattr(viewer, "_SOURCE_MAX_CHARS", 100)
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(200), encoding="utf-8")
    # 10-12 -> [7,15] (~68 chars) fits; 150-152 -> [147,155] (~80 chars) would overflow -> dropped.
    _cite(
        seed_page,
        "[^s1]: [big](../../raw/big.md), lines 10-12\n[^s2]: [big](../../raw/big.md), lines 150-152",
        body="A.[^s1] B.[^s2]",
    )
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert [(g["start"], g["end"]) for g in s["segments"]] == [(7, 15)]  # the overflowing 2nd dropped
    # The kept segment is whole (its full [7,15] text), not a mid-passage slice.
    assert s["segments"][0]["text"] == "\n".join(f"line {i}" for i in range(7, 16))
    assert s["truncated"] is True
    assert s["total_lines"] == 200  # so the viewer shows the un-embedded tail as a gap


def test_oversized_but_mostly_cited_source_still_segments(tmp_citadel, seed_page, monkeypatch):
    # The >= 2/3 coverage whole-embed fallback must NOT fire when the whole body is too big to embed:
    # a blindly truncated 200k prefix would drop the file's entire middle and end, so it emits
    # segments (the cited passages) instead. Regression for the pemberley showcase (a book cited
    # chapter by chapter to ~95% coverage).
    monkeypatch.setattr(viewer, "_SOURCE_MAX_CHARS", 200)
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(300), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), lines 1-290")  # covers >= 2/3 of the file
    s = viewer.build_bundle()["sources"]["raw/big.md"]
    assert "body" not in s  # too big to embed whole despite high coverage
    assert "segments" in s
    assert s["truncated"] is True


def test_excerpt_bundle_round_trips_and_renders(tmp_citadel, seed_page):
    (tmp_citadel.raw / "big.md").write_text(_numbered_source(200), encoding="utf-8")
    _cite(seed_page, "[^s1]: [big](../../raw/big.md), lines 40-52")
    html = viewer.build_html()
    _blob, bundle = _embedded_bundle(html)
    assert bundle == viewer.build_bundle()  # deterministic, JSON round-trips the segments
    # The viewer script knows how to render segmented sources and their gap indicators.
    assert "renderSegments" in html
    assert "seg-gap" in html


def test_manifest_model_and_repo_and_uncited(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text("# A\n\ncited\n", encoding="utf-8")
    (tmp_citadel.raw / "lonely.md").write_text("# Lonely\n\nuncited\n", encoding="utf-8")
    tmp_citadel.manifest_path.write_text(
        json.dumps(
            {
                "raw/a.md": {"sha256": "h1", "model": "claude:sonnet"},
                "raw/lonely.md": {"sha256": "h2", "model": "copilot:gpt"},
                "raw/somerepo": {"kind": "git", "commit": "abc", "model": "claude:sonnet"},
            }
        ),
        encoding="utf-8",
    )
    _two_page_wiki(seed_page)
    sources = viewer.build_bundle()["sources"]
    # Model attribution flows from the manifest onto the cited source.
    assert sources["raw/a.md"]["model"] == "claude:sonnet"
    # A tracked-but-uncited file still appears, with an empty cited_by.
    assert "raw/lonely.md" in sources
    assert sources["raw/lonely.md"]["cited_by"] == []
    assert sources["raw/lonely.md"]["model"] == "copilot:gpt"
    # A git-repository entry is a folder, not a file — it is never embedded as a source.
    assert "raw/somerepo" not in sources
    assert all(s["key"] != "raw/somerepo" for s in sources.values())


def test_format2_manifest_provenance_decorates_sources(tmp_citadel, seed_page):
    """Regression: the bundle reads the manifest through ``manifest.load()``, which unwraps the
    stamped format-2 file (``{"meta", "sources"}``) that ``manifest.save`` writes. The old
    private viewer reader returned that RAW dict, so on a format-2 manifest the model
    attribution silently vanished and the tracked-but-uncited source never surfaced."""
    (tmp_citadel.raw / "a.md").write_text("# A\n\ncited\n", encoding="utf-8")
    (tmp_citadel.raw / "lonely.md").write_text("# Lonely\n\nuncited\n", encoding="utf-8")
    manifest.save(
        {
            "raw/a.md": {"sha256": "h1", "model": "claude:sonnet"},
            "raw/lonely.md": {"sha256": "h2", "model": "copilot:gpt"},
        }
    )
    _two_page_wiki(seed_page)
    sources = viewer.build_bundle()["sources"]
    assert sources["raw/a.md"]["model"] == "claude:sonnet"  # provenance decoration from the wrapped file
    assert "raw/lonely.md" in sources  # tracked-but-uncited still surfaces
    assert sources["raw/lonely.md"]["model"] == "copilot:gpt"
    # The envelope keys themselves must never leak in as phantom sources.
    assert all(s["key"] not in ("meta", "sources") for s in sources.values())


def test_citation_inside_code_fence_is_not_a_source(tmp_citadel, seed_page):
    (tmp_citadel.raw / "real.md").write_text("# Real\n\nx\n", encoding="utf-8")
    (tmp_citadel.raw / "fenced.md").write_text("# Fenced\n\ny\n", encoding="utf-8")
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Real cite.[^s1]\n\n```\n[raw/fenced.md](../../raw/fenced.md)\n```\n\n"
        "## Sources\n\n[^s1]: [raw/real.md](../../raw/real.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "raw/real.md" in sources
    assert "raw/fenced.md" not in sources  # the fenced citation is a literal, not provenance


def test_angle_bracket_citation_is_discovered(tmp_citadel, seed_page):
    # A citation written in markdown's <...> target form must still be discovered and embedded
    # (grammar.split_link_target strips the brackets); the in-browser resolveLink strips them too.
    (tmp_citadel.raw / "x.md").write_text("# X\n\nbody\n", encoding="utf-8")
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites x.[^s1]\n\n## Sources\n\n[^s1]: [raw/x.md](<../../raw/x.md>) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "raw/x.md" in sources
    assert sources["raw/x.md"]["cited_by"] == ["concepts/p.md"]


def test_docs_citation_is_a_source(tmp_citadel, seed_page):
    (tmp_citadel.docs / "ref.md").write_text("# Reference\n\nspec\n", encoding="utf-8")
    seed_page(
        "concepts/p.md",
        {"type": "Concept", "title": "P"},
        "Cites a doc.[^s1]\n\n## Sources\n\n[^s1]: [docs/ref.md](../../docs/ref.md) - n\n",
    )
    sources = viewer.build_bundle()["sources"]
    assert "docs/ref.md" in sources
    assert sources["docs/ref.md"]["title"] == "Reference"


def test_bundle_contains_pages_links_tags(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    b = viewer.build_bundle()

    by_path = {p["rel_path"]: p for p in b["pages"]}
    assert set(by_path) == {"concepts/espresso.md", "concepts/caffeine.md"}
    assert by_path["concepts/espresso.md"]["title"] == "Espresso"
    assert by_path["concepts/espresso.md"]["tags"] == ["brewing", "coffee"]
    # caffeine -> espresso edge; espresso has caffeine as a backlink.
    assert by_path["concepts/caffeine.md"]["outbound"] == ["concepts/espresso.md"]
    assert by_path["concepts/espresso.md"]["inbound"] == ["concepts/caffeine.md"]
    assert {"source": "concepts/caffeine.md", "target": "concepts/espresso.md"} in b["edges"]
    # tags / types match the store helpers.
    assert set(b["tags"]["coffee"]) == {"concepts/espresso.md", "concepts/caffeine.md"}
    assert b["types"]["Concept"] == ["concepts/caffeine.md", "concepts/espresso.md"]


def test_build_html_embeds_and_round_trips(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    assert "Espresso" in html and "concepts/caffeine.md" in html
    _, parsed = _embedded_bundle(html)
    assert parsed == viewer.build_bundle()


def test_build_html_is_offline(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    for bad in ("http://", "https://", "cdn", " src=", "fetch("):
        assert bad not in html, f"network reference present: {bad!r}"


def test_build_html_escapes_script_close(tmp_citadel, seed_page):
    seed_page(
        "concepts/x.md",
        {"type": "Concept", "title": "X"},
        "danger </script><b>x</b> end.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    html = viewer.build_html()
    assert "<\\/script>" in html  # the body's </script> was escaped
    assert "danger </script>" not in html  # ...and not left raw inside the data blob
    # exactly one real closing </script> per real <script> tag (bundle + viewer js)
    assert html.count("<script") == html.count("</script>")


def test_write_viewer_creates_file_and_load_skips(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)
    path = viewer.write_viewer()
    assert path.exists() and path.suffix == ".html" and path.name.startswith(".")
    assert path.read_text(encoding="utf-8") == viewer.build_html()
    # The generated artifact must not be loaded as a wiki page.
    assert not any(p.rel_path.endswith(".citadel_viewer.html") for p in store.load())


def test_view_no_open_returns_zero(tmp_citadel, seed_page, monkeypatch):
    _two_page_wiki(seed_page)
    monkeypatch.setattr(viewer, "_is_wsl", lambda: False)  # hermetic on a WSL dev box
    calls = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda *a, **k: calls.append(a))
    rc = viewer.view(open_browser=False)
    assert rc == 0
    assert calls == []  # browser not launched
    assert (tmp_citadel.wiki / ".citadel_viewer.html").exists()


def test_view_handles_no_browser(tmp_citadel, seed_page, monkeypatch):
    _two_page_wiki(seed_page)
    monkeypatch.setattr(viewer, "_is_wsl", lambda: False)  # hermetic on a WSL dev box

    def boom(*a, **k):
        raise viewer.webbrowser.Error("no browser")

    monkeypatch.setattr(viewer.webbrowser, "open", boom)
    rc = viewer.view(open_browser=True)  # must not crash
    assert rc == 0
    assert (tmp_citadel.wiki / ".citadel_viewer.html").exists()


# --- WSL: open via wslview/explorer.exe and always print a Windows-pasteable path ------------
# Every seam (WSL detection, wslpath, wslview, explorer.exe, webbrowser) is monkeypatched, so
# these never spawn a real process even when the suite runs on an actual WSL box.

_WIN_PATH = r"\\wsl.localhost\Ubuntu\home\me\wiki\.citadel_viewer.html"


class _FakeProc:
    def __init__(self, returncode=0, stdout=""):
        self.returncode = returncode
        self.stdout = stdout


def test_is_wsl_detects_env_and_release(monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(viewer.platform, "release", lambda: "5.15.0-generic")
    assert viewer._is_wsl() is False
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert viewer._is_wsl() is True
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(viewer.platform, "release", lambda: "5.15.90.1-microsoft-standard-WSL2")
    assert viewer._is_wsl() is True


def test_wsl_windows_path_uses_wslpath(monkeypatch, tmp_path):
    monkeypatch.setattr(viewer.shutil, "which", lambda name: "/usr/bin/wslpath")
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return _FakeProc(returncode=0, stdout=_WIN_PATH + "\n")

    monkeypatch.setattr(viewer.subprocess, "run", fake_run)
    p = tmp_path / "v.html"
    assert viewer._wsl_windows_path(p) == _WIN_PATH
    assert seen["cmd"] == ["/usr/bin/wslpath", "-w", str(p)]


def test_wsl_windows_path_none_when_wslpath_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(viewer.shutil, "which", lambda name: None)
    assert viewer._wsl_windows_path(tmp_path / "v.html") is None


def test_open_in_browser_wsl_prefers_wslview(monkeypatch, tmp_path):
    monkeypatch.setattr(viewer, "_is_wsl", lambda: True)
    monkeypatch.setattr(viewer.shutil, "which", lambda name: "/usr/bin/wslview" if name == "wslview" else None)
    calls = []
    monkeypatch.setattr(viewer.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _FakeProc(returncode=0))
    wb = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda *a, **k: wb.append(a) or True)
    p = tmp_path / "v.html"
    p.write_text("x")
    assert viewer.open_in_browser(p, _WIN_PATH) is True
    assert calls == [["wslview", str(p)]]  # wslview first, nothing else tried
    assert wb == []  # webbrowser never reached


def test_open_in_browser_wsl_falls_to_explorer(monkeypatch, tmp_path):
    monkeypatch.setattr(viewer, "_is_wsl", lambda: True)
    monkeypatch.setattr(viewer.shutil, "which", lambda name: None)  # no wslview on PATH
    calls = []
    # explorer.exe exits non-zero even on success — a clean launch must still count.
    monkeypatch.setattr(viewer.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _FakeProc(returncode=1))
    wb = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda *a, **k: wb.append(a) or True)
    p = tmp_path / "v.html"
    p.write_text("x")
    assert viewer.open_in_browser(p, _WIN_PATH) is True
    assert calls == [["explorer.exe", _WIN_PATH]]
    assert wb == []


def test_open_in_browser_wsl_falls_through_to_webbrowser(monkeypatch, tmp_path):
    monkeypatch.setattr(viewer, "_is_wsl", lambda: True)
    monkeypatch.setattr(viewer.shutil, "which", lambda name: None)  # no wslview

    def boom(cmd, **kw):
        raise OSError("explorer.exe unavailable")

    monkeypatch.setattr(viewer.subprocess, "run", boom)
    wb = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda uri, *a, **k: wb.append(uri) or True)
    p = tmp_path / "v.html"
    p.write_text("x")
    assert viewer.open_in_browser(p, _WIN_PATH) is True  # explorer raised → webbrowser fallback
    assert wb == [p.as_uri()]


def test_view_prints_windows_path_on_wsl(tmp_citadel, seed_page, monkeypatch, capsys):
    _two_page_wiki(seed_page)
    monkeypatch.setattr(viewer, "_is_wsl", lambda: True)
    monkeypatch.setattr(viewer, "_wsl_windows_path", lambda path: _WIN_PATH)
    seen = {}

    def fake_open(path, win_path=None):
        seen["win"] = win_path
        return True

    monkeypatch.setattr(viewer, "open_in_browser", fake_open)
    rc = viewer.view(open_browser=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert _WIN_PATH in out  # pasteable Windows path printed alongside the file:// URI
    assert seen["win"] == _WIN_PATH  # and threaded into the opener for explorer.exe
    assert "could not launch a browser" not in out


def test_view_non_wsl_never_prints_windows_path_or_calls_wslpath(tmp_citadel, seed_page, monkeypatch, capsys):
    _two_page_wiki(seed_page)
    monkeypatch.setattr(viewer, "_is_wsl", lambda: False)

    def fail(*a, **k):
        raise AssertionError("wslpath must not be probed off WSL")

    monkeypatch.setattr(viewer, "_wsl_windows_path", fail)
    opened = []
    monkeypatch.setattr(viewer.webbrowser, "open", lambda uri, *a, **k: opened.append(uri) or True)
    rc = viewer.view(open_browser=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert "wsl.localhost" not in out
    assert opened  # plain webbrowser path, untouched


def test_empty_wiki(tmp_citadel):
    html = viewer.build_html()
    assert '"pages":[]' in html.replace(" ", "")
    assert "<!doctype html>" in html


def test_bundle_page_stats_counts_cites_llm_contradictions(tmp_citadel, seed_page):
    body = (
        "Espresso uses pressure.[^s1] It is strong.[^s2]\n\n"
        "A model-supplied note.[^llm1]\n\n"
        "> [!CONTRADICTION]\n"
        "> raw/a.md says 9 bar [^s1]; raw/b.md says 8 bar [^s2].\n\n"
        "```\n[^s9]\n```\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - n\n"
        "[^s2]: [raw/b.md](../../raw/b.md) - n\n"
        "[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-22)\n"
    )
    seed_page("concepts/espresso.md", {"type": "Concept", "title": "Espresso"}, body)
    page = next(p for p in viewer.build_bundle()["pages"] if p["rel_path"] == "concepts/espresso.md")
    # 2 raw cites in prose + 2 inside the contradiction callout; the fenced [^s9] and the
    # trailing ## Sources definitions ([^sN]:) are not counted.
    assert page["cites"] == 4
    # Inline [^llm1]; the ## Sources definition is not counted as a use.
    assert page["llm"] == 1
    assert page["contradictions"] == 1


def test_bundle_page_stats_zero_when_clean(tmp_citadel, seed_page):
    _two_page_wiki(seed_page)  # one [^s1] each, no llm, no contradiction
    by_path = {p["rel_path"]: p for p in viewer.build_bundle()["pages"]}
    assert by_path["concepts/espresso.md"]["cites"] == 1
    assert by_path["concepts/espresso.md"]["llm"] == 0
    assert by_path["concepts/espresso.md"]["contradictions"] == 0


def test_bundle_page_stats_ignores_fenced_and_sources_examples(tmp_citadel, seed_page):
    # A page that DOCUMENTS the citation/contradiction format must not have its example markers
    # counted: a callout inside a code fence is not a real contradiction, and a footnote marker
    # mentioned inside another footnote's ## Sources definition note is not an inline use.
    body = (
        "Real fact.[^s1]\n\n"
        "Here is how the contradiction format looks:\n\n"
        "```\n"
        "> [!CONTRADICTION]\n"
        "> raw/a.md says X [^s7]; raw/b.md says Y [^s8].\n"
        "```\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/a.md](../../raw/a.md) - derived alongside [^s2], see [^llm9] (ingested 2026-06-22)\n"
        "[^s2]: [raw/b.md](../../raw/b.md) - n\n"
    )
    seed_page("concepts/format.md", {"type": "Concept", "title": "Format"}, body)
    page = next(p for p in viewer.build_bundle()["pages"] if p["rel_path"] == "concepts/format.md")
    assert page["contradictions"] == 0  # the fenced callout is documentation, not a real one
    assert page["cites"] == 1  # only the inline [^s1]; fenced [^s7]/[^s8] and the def-note [^s2] excluded
    assert page["llm"] == 0  # the [^llm9] mentioned in the def note is not an inline use


def test_build_html_has_fulltext_search_badges_and_facets(tmp_citadel, seed_page):
    (tmp_citadel.raw / "a.md").write_text("# A\n\nbody text\n", encoding="utf-8")
    _two_page_wiki(seed_page)
    html = viewer.build_html()
    # Full-text search over bodies + result highlighting, the sidebar badge/facet machinery, and
    # the reader jump-to-contradiction/LLM affordance are all present in the inlined viewer.
    for marker in (
        "searchResults",
        "applyHighlight",
        "renderResults",
        "badgesHtml",
        "renderFacets",
        "data-facet",
        "data-jump",
        "<mark>",
        'id="facets"',
    ):
        assert marker in html, f"missing viewer feature marker: {marker!r}"
    # (The offline guarantee is asserted by test_build_html_is_offline /
    # test_build_html_makes_sources_clickable — not re-scanned here, since those substrings can
    # legitimately occur inside embedded source/page text on a real wiki.)


def test_golden_bundle_structural_invariants(tmp_citadel, seed_page):
    """Golden test on the BUILT document over a seeded 3-page wiki, pinning exactly three
    invariants of the Python-side embedding rules on the real artifact: the embedded page map
    contains the seeded rel_paths, cross-page links resolve to wiki-root-relative ids, and a
    literal ``</script>`` in a body escape-round-trips through the data blob (in place of any
    Python-vs-JS runtime parity test — no JS runtime in the suite)."""
    seed_page("concepts/alpha.md", {"type": "Concept", "title": "Alpha"}, "Links to [Beta](./beta.md).\n")
    seed_page("concepts/beta.md", {"type": "Concept", "title": "Beta"}, "Links to [Gamma](../misc/gamma.md).\n")
    seed_page("misc/gamma.md", {"type": "Note", "title": "Gamma"}, "Contains a literal </script> tag in prose.\n")
    blob, bundle = _embedded_bundle(viewer.build_html())

    # The '</' escape: gamma's literal '</script>' must not close the data <script> early in the
    # raw blob, and must round-trip back to '</script>' after the documented unescape.
    assert "<\\/script> tag in prose" in blob
    assert "</script> tag in prose" not in blob
    by_path = {p["rel_path"]: p for p in bundle["pages"]}
    assert "</script> tag in prose" in by_path["misc/gamma.md"]["body"]

    # The embedded page map contains exactly the seeded rel_paths.
    assert set(by_path) == {"concepts/alpha.md", "concepts/beta.md", "misc/gamma.md"}

    # Resolved hrefs between the pages: relative links resolve to wiki-root-relative ids in
    # outbound/inbound (edges are derived from outbound).
    assert by_path["concepts/alpha.md"]["outbound"] == ["concepts/beta.md"]
    assert by_path["concepts/beta.md"]["outbound"] == ["misc/gamma.md"]
    assert by_path["misc/gamma.md"]["inbound"] == ["concepts/beta.md"]


def test_cli_view_wires_up():
    from citadel import cli

    args = cli.build_parser().parse_args(["view", "--no-open"])
    assert args.func is cli.cmd_view
    assert args.open_browser is False
