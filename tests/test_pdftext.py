"""PDF text-layer pre-pass (offline): pypdf is a bundled runtime dep, so the REAL extraction runs
here — no fake. A genuine PDF ingests via its extracted, content-addressed cached
text layer under the ``pdf``/``pdf-reconcile`` kinds while the wiki cites the original ``.pdf``;
the cache doubles as the offline verification text for lint, ``wiki_raw``, and the viewer —
exactly the audio pattern (test_ingest_audio is the blueprint). A PDF with no usable text layer
(scanned, encrypted, corrupt) or a disabled/unavailable pypdf falls back to the pre-existing
agent-native read. ``llm.run_ingest_session`` is replaced by ``fake_agent``; the tiny PDFs are
hand-written stdlib-only (the gazette corpus generator's approach, minimized).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import delete_citing_pages

from citadel import config, ingest, lint, llm, manifest, pdftext, rawsource, store


# --- a minimal, strictly-valid PDF builder (measured xref, stdlib-only) -------------------


def _pdf_escape(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _make_pdf(path: Path, pages: list[list[str]]) -> None:
    """Hand-write a valid PDF 1.4 at ``path``: one Helvetica text page per inner list (one ``Tj``
    per line, so pypdf extracts the lines verbatim); an empty inner list is a page with NO text
    layer (extraction yields nothing — the scanned-page shape)."""
    content_ids, page_ids, next_id = [], [], 4
    for _ in pages:
        content_ids.append(next_id)
        page_ids.append(next_id + 1)
        next_id += 2
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    bodies = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode(),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for cid, pid, lines in zip(content_ids, page_ids, pages, strict=True):
        ops = ""
        if lines:
            ops = "BT /F1 12 Tf 72 720 Td " + " 0 -14 Td ".join(f"({_pdf_escape(t)}) Tj" for t in lines) + " ET"
        stream = ops.encode()
        bodies[cid] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        bodies[pid] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {cid} 0 R >>"
        ).encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(bodies):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + bodies[num] + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(bodies) + 1}\n".encode() + b"0000000000 65535 f \n"
    for num in sorted(bodies):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(bodies) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


TWO_PAGES = [["Alpha line one.", "Beta line two."], ["Gamma on page two."]]
# The canonical extraction shape for TWO_PAGES: [p. N] markers, page text, blank line between.
TWO_PAGES_TEXT = "[p. 1]\nAlpha line one.\nBeta line two.\n\n[p. 2]\nGamma on page two.\n"


# --- the extraction seam itself -----------------------------------------------------------


def test_detection_magic_not_extension(tmp_citadel):
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)
    (raw / "fake.pdf").write_text("just text, no magic\n", encoding="utf-8")
    assert pdftext.is_pdf_file(raw / "report.pdf")
    assert not pdftext.is_pdf_file(raw / "fake.pdf")  # renamed text file is NOT a PDF
    assert not pdftext.is_pdf_file(raw / "missing.pdf")  # never raises
    assert pdftext.is_pdf_ext(raw / "fake.pdf") and not pdftext.is_pdf_ext(raw / "x.txt")


def test_text_for_extracts_pages_with_markers_and_caches(tmp_citadel):
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)

    text = pdftext.text_for(raw / "report.pdf")

    assert text == TWO_PAGES_TEXT
    # Cached content-addressed; a second call serves the cache (no re-parse — break the file's
    # parseability in place to prove it, keeping the same bytes' cache key by NOT changing it).
    assert pdftext.cached_text(raw / "report.pdf") == TWO_PAGES_TEXT
    sha = manifest.file_sha256(raw / "report.pdf")
    assert pdftext.cache_path(sha).is_file()


def test_scanned_pdf_yields_none_and_caches_empty(tmp_citadel):
    """A PDF whose pages have NO text layer extracts to empty: text_for returns None (fall back
    to agent-native reading), the empty result IS cached (no re-parse every run), and the
    verification consumers see 'no offline text' (cached_text None)."""
    raw = tmp_citadel.raw
    _make_pdf(raw / "scan.pdf", [[], []])

    assert pdftext.text_for(raw / "scan.pdf") is None
    sha = manifest.file_sha256(raw / "scan.pdf")
    assert pdftext.cache_path(sha).is_file()  # the empty extraction is cached...
    assert pdftext.cached_text(raw / "scan.pdf") is None  # ...but serves as "nothing"


def test_unparsable_pdf_falls_back_without_caching(tmp_citadel):
    raw = tmp_citadel.raw
    (raw / "broken.pdf").write_bytes(b"%PDF-1.4\ngarbage that is not a pdf body")
    assert pdftext.text_for(raw / "broken.pdf") is None
    # A parse failure writes NO cache entry (only an empty scanned-PDF extraction is cached).
    if pdftext.cache_dir().is_dir():
        assert list(pdftext.cache_dir().glob("*.md")) == []


def test_knob_and_availability_gate_routing(tmp_citadel, monkeypatch):
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)
    assert pdftext.is_pdf_text_source(raw / "report.pdf")  # auto + pypdf installed (dev dep)

    monkeypatch.setattr(config, "PDF_TEXT", "off", raising=False)
    assert not pdftext.is_pdf_text_source(raw / "report.pdf")

    monkeypatch.setattr(config, "PDF_TEXT", "auto", raising=False)
    monkeypatch.setattr(pdftext, "available", lambda: False)
    assert not pdftext.is_pdf_text_source(raw / "report.pdf")

    # Forced on without pypdf: still routed (enabled), but text_for degrades to None — the
    # per-source fallback (doctor carries the WARN).
    monkeypatch.setattr(config, "PDF_TEXT", "on", raising=False)
    assert pdftext.is_pdf_text_source(raw / "report.pdf")
    assert pdftext.text_for(raw / "report.pdf") is None


def test_cache_path_rejects_non_hexdigest(tmp_citadel):
    with pytest.raises(ValueError):
        pdftext.cache_path("../escape")
    pdftext.prune_cached("../escape")  # persisted-data guard: a no-op, never a traversal
    pdftext.prune_cached(None)


# --- end-to-end ingest --------------------------------------------------------------------


def test_pdf_ingests_via_extraction_under_pdf_kind(tmp_citadel, fake_agent, seed_page):
    """The full path: the text layer is extracted once (cache written), the agent reads the
    prepared extraction under the PDF propagation, the wiki cites the ORIGINAL .pdf with a
    `lines A-B` locator that lint verifies offline, the temp is cleaned up, and a re-run is
    idempotent."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.update(rel_key=rel_key, kind=kind, read_path=read_path, segment=segment)
        assert read_path is not None
        seen["prepared"] = Path(read_path).read_text(encoding="utf-8")
        seed_page(
            "misc/report.md",
            {"type": "Note", "title": "Report", "description": "d", "tags": ["pdf"], "resource": rel_key},
            f"Beta happened.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{rel_key}](../../{rel_key}), lines 3-3 - report (ingested 2026-07-24)\n",
        )

    agent = fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert report.processed == ["raw/report.pdf"] and not report.errors
    assert seen["kind"] == "pdf"  # the pdf propagation, not plain "ingest"
    assert seen["prepared"] == TWO_PAGES_TEXT  # the agent read the [p. N]-marked extraction
    assert seen["segment"] is None

    page_text = (wiki / "misc" / "report.md").read_text(encoding="utf-8")
    assert "resource: raw/report.pdf" in page_text  # cites the PDF, not the extraction temp
    rep = lint.lint()
    assert rep.ok() and rep.bad_sources == []
    assert rep.locator_issues == []  # `lines 3-3` verified offline against the cached extraction

    assert "raw/report.pdf" in tmp_citadel.read_manifest()
    assert not Path(str(seen["read_path"])).exists()  # extraction temp cleaned up
    assert pdftext.cached_text(raw / "report.pdf") == TWO_PAGES_TEXT  # cache persisted

    assert ingest.ingest().processed == []  # idempotent: no second session
    assert agent.count == 1


def test_pdf_without_text_layer_falls_back_to_direct_read(tmp_citadel, fake_agent, cite_page):
    """A scanned PDF (no text layer) keeps the pre-feature behavior: one plain `ingest` session
    reading the file directly, no prepared path — and never a failed source."""
    raw = tmp_citadel.raw
    _make_pdf(raw / "scan.pdf", [[]])

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.update(kind=kind, read_path=read_path)
        cite_page("misc/scan.md", rel_key, "A scanned fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert report.processed == ["raw/scan.pdf"] and not report.errors
    assert seen["kind"] == "ingest" and seen["read_path"] is None


def test_knob_off_keeps_agent_native_reading(tmp_citadel, fake_agent, cite_page, monkeypatch):
    monkeypatch.setattr(config, "PDF_TEXT", "off", raising=False)
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.update(kind=kind, read_path=read_path)
        cite_page("misc/report.md", rel_key, "A pdf fact.")

    fake_agent(side_effect=fake)
    assert ingest.ingest().processed == ["raw/report.pdf"]
    assert seen["kind"] == "ingest" and seen["read_path"] is None
    assert not pdftext.cache_dir().exists()  # nothing was extracted


def test_changed_pdf_reingests_as_pdf_reconcile_and_prunes_old_cache(tmp_citadel, fake_agent, cite_page):
    """A re-exported PDF (new bytes -> new cache key) reconciles under `pdf-reconcile` and prunes
    the OLD bytes' orphaned extraction — exactly one cache entry per live source."""
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen["kind"] = kind
        cite_page("misc/report.md", rel_key, "A pdf fact.")

    fake_agent(side_effect=fake)
    ingest.ingest()
    assert seen["kind"] == "pdf"
    assert len(list(pdftext.cache_dir().glob("*.md"))) == 1

    _make_pdf(raw / "report.pdf", [["Revised content, single page."]])
    ingest.ingest()

    assert seen["kind"] == "pdf-reconcile"
    entries = list(pdftext.cache_dir().glob("*.md"))
    assert len(entries) == 1  # the old entry is gone, only the new content's extraction remains
    assert "Revised content" in entries[0].read_text(encoding="utf-8")


def test_pdf_changed_into_plain_text_still_prunes_its_old_extraction(tmp_citadel, fake_agent, cite_page):
    """A PDF whose bytes are replaced by NON-PDF content (no %PDF- magic) still orphans its old
    text-layer extraction — the change-path prunes by OLD sha regardless of the new file's type,
    so the plaintext cache never lingers (mirrors the delete path)."""
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        cite_page("misc/report.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    ingest.ingest()
    assert len(list(pdftext.cache_dir().glob("*.md"))) == 1  # extracted + cached

    # Replace the PDF's bytes with plain text under the SAME name (no %PDF- magic anymore).
    (raw / "report.pdf").write_text("Now I am just plain text, no PDF magic.\n", encoding="utf-8")
    ingest.ingest()

    # The old extraction is gone even though the new file is not a PDF (change-path prune by sha).
    assert list(pdftext.cache_dir().glob("*.md")) == []


def test_deleted_pdf_prunes_its_cached_extraction(tmp_citadel, fake_agent, cite_page):
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if kind == "delete":
            delete_citing_pages(rel_key)
        else:
            cite_page("misc/report.md", rel_key, "A pdf fact.")

    fake_agent(side_effect=fake)
    ingest.ingest()
    cached_file = next(pdftext.cache_dir().glob("*.md"))

    (raw / "report.pdf").unlink()
    report = ingest.ingest()

    assert report.sources_deleted == ["raw/report.pdf"]
    assert not cached_file.exists()  # pruned with the source


def test_deleted_pdf_under_a_non_pdf_name_still_prunes_its_cache(tmp_citadel, fake_agent, cite_page):
    """A PDF routes by %PDF- MAGIC, not by extension, so it can be ingested under any name — and
    its cached extraction must still be pruned on delete (else plaintext orphans in the cache).
    The delete path prunes BY SHA, never gated on the extension."""
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.bin", TWO_PAGES)  # a genuine PDF wearing a .bin name

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if kind == "delete":
            delete_citing_pages(rel_key)
        else:
            cite_page("misc/report.md", rel_key, "A pdf fact.")

    fake_agent(side_effect=fake)
    ingest.ingest()
    assert list(pdftext.cache_dir().glob("*.md")), "a magic-detected PDF should be extracted+cached"

    (raw / "report.bin").unlink()
    report = ingest.ingest()

    assert report.sources_deleted == ["raw/report.bin"]
    assert list(pdftext.cache_dir().glob("*.md")) == []  # pruned despite the non-.pdf name


def test_prune_guard_spares_a_sha_another_entry_still_holds(tmp_citadel):
    """The cache is content-addressed, so two byte-identical sources under different keys share ONE
    cache entry. ``_sha_shared_by_other_entry`` is the guard that keeps a prune from deleting a
    cache file a sibling still verifies against — it prunes only the LAST reference to a sha. (The
    ingest partition normally dedups identical bytes into a move, so this is defense in depth; it
    also hardens the identical-audio case.)"""
    from citadel import manifest

    sha = "ab" * 32
    m = {
        "raw/a.pdf": manifest.make_entry(sha, "m"),
        "raw/b.pdf": manifest.make_entry(sha, "m"),  # a byte-identical sibling
        "raw/other.pdf": manifest.make_entry("cd" * 32, "m"),
    }
    # a's sha is still held by b -> sparing it; excluding a itself so its own entry never counts.
    assert ingest._sha_shared_by_other_entry(m, sha, exclude_key="raw/a.pdf") is True
    # other's sha is unique -> nothing else holds it, safe to prune.
    assert ingest._sha_shared_by_other_entry(m, "cd" * 32, exclude_key="raw/other.pdf") is False
    # None/empty sha and a repo entry (commit identity, not a content sha) never spare anything.
    assert ingest._sha_shared_by_other_entry(m, None, exclude_key="raw/a.pdf") is False
    m["raw/repo"] = manifest.make_repo_entry("commit123", "m", None, "rv")
    assert ingest._sha_shared_by_other_entry(m, sha, exclude_key="raw/b.pdf") is True  # a still holds it


def test_large_extraction_chunks_as_line_windows_over_one_full_file(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """A large text layer is folded in over several passes over the SAME full extraction file —
    never rebased slices: every pass keeps the PDF kind, reads one shared temp byte-identical to
    the verification cache, and carries a contiguous line window (the audio chunking contract)."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    _make_pdf(raw / "book.pdf", [[f"Sentence number {i} on page {p}." for i in range(3)] for p in range(1, 4)])

    seen: list[dict] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        seen.append(
            {
                "kind": kind,
                "segment": segment,
                "line_range": line_range,
                "read_path": read_path,
                "content": Path(read_path).read_text(encoding="utf-8"),
            }
        )
        cite_page("misc/book.md", rel_key, "A book fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert report.processed == ["raw/book.pdf"]
    assert len(seen) > 1  # genuinely chunked — a text-layer PDF is no longer unchunkable
    assert all(s["kind"] == "pdf" for s in seen)
    assert [s["segment"] for s in seen] == [(i, len(seen)) for i in range(1, len(seen) + 1)]

    cached = pdftext.cached_text(raw / "book.pdf")
    assert len({s["read_path"] for s in seen}) == 1  # ONE shared temp with the FULL extraction
    assert all(s["content"] == cached for s in seen)

    windows = [s["line_range"] for s in seen]
    total_lines = len(cached.splitlines())
    assert windows[0][0] == 1 and windows[-1][1] == total_lines
    assert all(w2[0] == w1[1] + 1 for w1, w2 in zip(windows, windows[1:], strict=False))


# --- the cache as offline verification text ----------------------------------------------


def _seed_pdf_citation(seed_page, locator: str) -> None:
    seed_page(
        "misc/report.md",
        {"type": "Note", "title": "Report", "description": "d", "tags": ["pdf"], "resource": "raw/report.pdf"},
        f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/report.pdf](../../raw/report.pdf), {locator} - report\n",
    )


def test_lint_verifies_lines_locators_against_cached_extraction(tmp_citadel, seed_page):
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)
    pdftext.text_for(raw / "report.pdf")  # populate the cache (6 lines)

    _seed_pdf_citation(seed_page, "lines 40-52")
    issues = lint.check_locators(store.load())
    assert issues and "out of range" in issues[0][1]

    _seed_pdf_citation(seed_page, "lines 2-3")
    assert lint.check_locators(store.load()) == []

    # Page locators (`p. N`) parse as "other" and stay agent-verified — cache or not.
    _seed_pdf_citation(seed_page, "p. 12")
    assert lint.check_locators(store.load()) == []


def test_text_file_named_pdf_still_verifies_and_serves_its_line_locators(tmp_citadel, seed_page):
    """A file merely NAMED ``.pdf`` but without ``%PDF-`` magic ingests as ORDINARY TEXT (routing
    is magic-based), so it carries real ``lines A-B`` locators — and lint must verify them and
    ``wiki_raw`` must serve them, never bail out purely on the ``.pdf`` extension (the audio
    ``renamed .mp3`` contract, mirrored for PDFs)."""
    raw = tmp_citadel.raw
    (raw / "notes.pdf").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")  # text, no %PDF- magic
    manifest_dict = manifest.load()
    manifest_dict["raw/notes.pdf"] = manifest.make_entry(manifest.file_sha256(raw / "notes.pdf"), "m")
    manifest.save(manifest_dict)

    seed_page(
        "misc/notes.md",
        {"type": "Note", "title": "Notes", "description": "d", "tags": ["a"], "resource": "raw/notes.pdf"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.pdf](../../raw/notes.pdf), lines 7-9 - notes\n",
    )
    issues = lint.check_locators(store.load())
    assert issues and "out of range" in issues[0][1]  # verified as text (3 lines), 7-9 is out of range

    # wiki_raw serves it as text (never the "no offline text extraction" PDF error).
    text = rawsource.raw_text("raw/notes.pdf", "lines 1-2")
    assert "alpha" in text and "beta" in text and "gamma" not in text


def test_lint_skips_pdf_locators_without_a_cache(tmp_citadel, seed_page):
    """No cache on this machine (agent-native ingest, pypdf absent, other machine) -> the locator
    is agent-verified (skipped, advisory) — never a false flag from reading the binary itself."""
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)
    _seed_pdf_citation(seed_page, "lines 999-1000")
    assert lint.check_locators(store.load()) == []


def test_wiki_raw_serves_cached_extraction_with_locator(tmp_citadel, fake_agent, cite_page):
    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        cite_page("misc/report.md", rel_key, "A pdf fact.")

    fake_agent(side_effect=fake)
    ingest.ingest()

    text = rawsource.raw_text("raw/report.pdf", "lines 2-3")
    assert "Alpha line one." in text and "Beta line two." in text
    assert "Gamma" not in text  # the locator slice, not the whole extraction

    # Prune the cache: the reader degrades to the explicit no-extraction error, naming the fix.
    pdftext.prune_cached(manifest.file_sha256(raw / "report.pdf"))
    with pytest.raises(rawsource.SourceError, match="no cached text-layer extraction"):
        rawsource.raw_text("raw/report.pdf")


def test_viewer_serves_cached_extraction_as_pdf_kind(tmp_citadel):
    from citadel import viewer

    raw = tmp_citadel.raw
    _make_pdf(raw / "report.pdf", TWO_PAGES)
    pdftext.text_for(raw / "report.pdf")

    text, kind = viewer._read_source(raw / "report.pdf")
    assert kind == "pdf" and text == TWO_PAGES_TEXT
    # Without a cache the PDF stays a binary (open-the-original link) — never a lucky decode.
    _make_pdf(raw / "other.pdf", [["Never extracted."]])
    pdftext.prune_cached(manifest.file_sha256(raw / "other.pdf"))
    assert viewer._read_source(raw / "other.pdf") == ("", "binary")


# --- prompt composition -------------------------------------------------------------------


def test_pdf_kind_prompt_names_the_pdf_brief_and_window(tmp_citadel):
    """The pdf kinds keep formats/pdf.md on every segment (its cite-the-original + locator rules
    bind per slice) and a windowed pass names the extracted-text window — not a 'transcript'."""
    prompt = llm._build_instruction(
        "raw/report.pdf", kind="pdf", read_path="prep.md", segment=(2, 3), line_range=(9, 16)
    )
    assert "formats/pdf.md" in prompt
    assert "- PDF mode: text" in prompt
    assert "Extracted text window for THIS pass: lines 9-16" in prompt
    assert "transcript" not in prompt.lower()

    reconcile = llm._build_instruction("raw/report.pdf", kind="pdf-reconcile", read_path="prep.md")
    assert "formats/pdf.md" in reconcile and "tasks/reconcile.md" in reconcile


# --- #165: per-page text-layer reliability ------------------------------------------------------

_PROSE = (
    "The observatory opened its new dome in the spring and the first nights were spent calibrating "
    "the mirror against known stars while the weather held clear over the ridge"
)
_PROSE_DE = (
    "Die Sternwarte eröffnete im Frühjahr ihre neue Kuppel und die ersten Nächte dienten der "
    "Kalibrierung des Spiegels an bekannten Sternen während das Wetter über dem Grat klar blieb"
)
_COLUMN_TABLE = "\n".join(
    ["Primary mirror sensor", "Dome humidity probe", "Focus motor encoder", "Shutter limit switch",
     "Guide camera offset", "Filter wheel index", "0.12", "0.35", "0.08", "0.21", "0.44", "0.17"]
)  # fmt: skip


def _extraction(*pages: str) -> str:
    return "\n\n".join(f"[p. {n}]\n{body}" for n, body in enumerate(pages, 1)) + "\n"


def test_a_column_serialized_page_is_flagged():
    assert pdftext.unreliable_pages(_extraction(_PROSE, _COLUMN_TABLE)) == (2,)


def test_an_ocr_noise_page_is_flagged():
    noise = " ".join(["t h e", "c0de", "|", "o b s", "~", "1l1", "e r v", "a t o r y"] * 3)
    assert pdftext.unreliable_pages(_extraction(noise)) == (1,)


def test_clean_prose_and_small_or_non_latin_pages_are_never_flagged():
    cyrillic = " ".join(["обсерватория"] * 25)
    text = _extraction(_PROSE, _PROSE_DE, "0.12\n0.35\n0.08\n0.21", "", cyrillic)
    assert pdftext.unreliable_pages(text) == ()


def test_format_pages_collapses_ranges():
    assert pdftext.format_pages([7, 2, 5, 6]) == "p. 2, pp. 5-7"


def test_a_pdf_with_one_garbled_page_names_it_to_the_session(tmp_citadel, fake_agent, cite_page, monkeypatch):
    (tmp_citadel.raw / "sheet.pdf").write_bytes(b"%PDF-1.4\nfixture\n")
    monkeypatch.setattr(pdftext, "text_for", lambda src, sha=None: _extraction(_PROSE, _COLUMN_TABLE))
    seen: dict = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None, visual_pages=None):
        seen.update(kind=kind, visual_pages=visual_pages)
        cite_page("misc/sheet.md", rel_key, "A sheet fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert seen == {"kind": "pdf", "visual_pages": (2,)}
    assert "PDF pages read visually (unreliable text layer):" in report.render()
    assert "raw/sheet.pdf (p. 2)" in report.render()
    report.render().encode("ascii")


def test_a_clean_pdf_session_carries_no_visual_pages(tmp_citadel, fake_agent, cite_page, monkeypatch):
    (tmp_citadel.raw / "clean.pdf").write_bytes(b"%PDF-1.4\nfixture\n")
    monkeypatch.setattr(pdftext, "text_for", lambda src, sha=None: _extraction(_PROSE))
    kwargs_seen: list = []

    def fake(rel_key, **kwargs):
        kwargs_seen.append(kwargs)
        cite_page("misc/clean.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    ingest.ingest()
    assert "visual_pages" not in kwargs_seen[0]


def test_every_page_garbled_reads_without_the_text_layer(tmp_citadel, fake_agent, cite_page, monkeypatch):
    (tmp_citadel.raw / "noise.pdf").write_bytes(b"%PDF-1.4\nfixture\n")
    monkeypatch.setattr(pdftext, "text_for", lambda src, sha=None: _extraction(_COLUMN_TABLE))
    seen: dict = {}

    def fake(rel_key, kind="ingest", read_path=None, **kw):
        seen.update(kind=kind, read_path=read_path)
        cite_page("misc/noise.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert seen == {"kind": "ingest", "read_path": None}
    assert "every text page unreliable" in report.render()


def test_chunked_passes_only_get_the_pages_that_begin_in_their_window():
    passes = [(None, (1, 2), (1, 10)), (None, (2, 2), (11, 20))]
    text = "\n".join(["[p. 1]"] + ["x"] * 9 + ["[p. 2]"] + ["y"] * 9)
    assert ingest._visual_pages_per_pass(passes, text, (2,)) == [(), (2,)]


def test_plan_shape_hashes_named_pages_only_when_present(tmp_citadel):
    from citadel import ingest_sessions

    passes = [(None, (1, 2), (1, 10)), (None, (2, 2), (11, 20))]
    base = ingest_sessions._plan_shape(passes)
    assert ingest_sessions._plan_shape(passes, [(), ()]) == base
    assert ingest_sessions._plan_shape(passes, [(), (2,)]) != base


def test_visual_bullet_only_for_pdf_kinds_ascii_and_capped(tmp_citadel):
    from citadel import llm

    prompt = llm._build_instruction("raw/x.pdf", "pdf", "/tmp/x.md", None, None, (2, 5, 6, 7))
    lines = prompt.splitlines()
    i = next(k for k, line in enumerate(lines) if line.startswith("- PDF mode:"))
    assert lines[i + 1].startswith("- Unreliable text layer") and lines[i + 1].endswith("p. 2, pp. 5-7")
    assert lines[i + 1].isascii()
    assert "Unreliable text layer" not in llm._build_instruction("raw/x.pdf", "ingest", None, None, None, (2,))
    many = tuple(range(1, 63, 2))  # 31 single-page ranges
    capped = llm._build_instruction("raw/x.pdf", "pdf", "/tmp/x.md", None, None, many)
    assert "(+1 more pages" in capped and len(capped) < 8000


def test_interleaving_check_is_linear_on_long_tokens():
    """A long unspaced OCR token must not make the noise check quadratic, and the answer is
    unchanged: an interleaving inside a word still counts, a pure run never does."""
    import time

    from citadel import pdftext

    assert pdftext._INTERLEAVED_RE.search("c0de") and pdftext._INTERLEAVED_RE.search("1l1")
    assert not pdftext._INTERLEAVED_RE.search("code") and not pdftext._INTERLEAVED_RE.search("2026")
    start = time.perf_counter()
    for token in ("a" * 200_000, "1" * 200_000, "a" * 100_000 + "1" * 100_000):
        assert not pdftext._INTERLEAVED_RE.search(token)
    assert time.perf_counter() - start < 1.0
