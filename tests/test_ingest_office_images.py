"""Office and image sources (offline): a .pptx is extracted to temp text (plus its embedded
media) for the agent to read while the wiki cites the original binary; a recognized image is fed
to the agent visually. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, ingest, lint, manifest


def _make_pptx_with_image(path: Path, paras: list[str], image_bytes: bytes) -> None:
    """A minimal .pptx with one text slide AND an embedded image under ppt/media/."""
    import zipfile

    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    runs = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in paras)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(
            "ppt/slides/slide1.xml",
            f'<?xml version="1.0"?><p:sld xmlns:p="{p}" xmlns:a="{a}"><p:cSld><p:spTree>'
            f"<p:sp><p:txBody>{runs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
        )
        z.writestr("ppt/media/image1.png", image_bytes)


def _make_png(path: Path) -> None:
    """Write a file that starts with the PNG signature (enough for _is_image_source's magic check)."""
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02\x03fake-image-bytes")


def test_partition_classifies_office_text_vs_textless_once(tmp_citadel, make_pptx):
    """Office routing lives in _partition_sources: a deck with extractable text is pending (and its
    text is cached for the agent step), a text-free deck is unreadable like any other binary — and
    the file is parsed exactly once (the cache is what avoids a second parse)."""
    raw = tmp_citadel.raw
    make_pptx(raw / "withtext.pptx", [["A real fact."]])
    make_pptx(raw / "notext.pptx", [[]])

    pending, skipped, moved, unreadable, deleted, office_text, images, duplicates = ingest._partition_sources(None, {})

    pending_keys = {manifest.rel_key(p) for p in pending}
    unreadable_keys = {manifest.rel_key(p) for p in unreadable}
    assert "raw/withtext.pptx" in pending_keys
    assert "raw/notext.pptx" in unreadable_keys
    # The extracted text is cached so the agent step reuses it (no second ZIP/XML parse).
    assert any("A real fact." in t for t in office_text.values())
    assert all(isinstance(p, Path) for p in office_text)  # keyed by the pending Path objects


def test_office_pptx_extracted_to_temp_and_ingested(tmp_citadel, fake_agent, seed_page, make_pptx):
    """A .pptx (binary the agent can't open) is extracted to a temp .md the agent READS, while the
    wiki cites the ORIGINAL .pptx as its source. The temp file is cleaned up after the session."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    make_pptx(raw / "deck.pptx", [["Transformers use self-attention.", "Key idea: attention."]])

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None):
        seen.update(rel_key=rel_key, kind=kind, read_path=read_path)
        # The agent is pointed at the EXTRACTED text, not the binary; it must exist right now.
        assert read_path is not None
        seen["extracted"] = Path(read_path).read_text(encoding="utf-8")
        seed_page(
            "concepts/transformer.md",
            {"type": "Concept", "title": "Transformer", "description": "d", "tags": ["ml"], "resource": rel_key},
            f"Transformers use self-attention.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{rel_key}](../../{rel_key}) - deck (ingested 2026-06-21)\n",
        )

    agent = fake_agent(side_effect=fake)

    report = ingest.ingest()

    assert report.processed == ["raw/deck.pptx"]  # keyed by the original Office file
    assert not report.errors
    assert seen["rel_key"] == "raw/deck.pptx" and seen["kind"] == "ingest"
    assert "self-attention" in str(seen["extracted"]).lower()
    assert "## Slide 1" in str(seen["extracted"])  # the extractor's structure reached the agent

    page = wiki / "concepts" / "transformer.md"
    assert page.exists()
    assert "resource: raw/deck.pptx" in page.read_text(encoding="utf-8")  # cites the .pptx
    rep = lint.lint()
    assert rep.ok() and rep.bad_sources == []

    import json

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))["sources"]
    assert "raw/deck.pptx" in data

    # The extracted-text temp dir/file is removed once the session is done (no litter).
    assert not Path(str(seen["read_path"])).exists()

    # Re-running is idempotent on the .pptx key (no second extraction/session).
    assert ingest.ingest().processed == []
    assert agent.count == 1


def test_office_embedded_images_are_extracted_for_the_agent(tmp_citadel, fake_agent, cite_page):
    """A deck's embedded images (which the text extractor can't see) are written to a media/ folder
    beside the extracted text so the agent can VIEW them."""
    raw = tmp_citadel.raw
    _make_pptx_with_image(raw / "deck.pptx", ["Deck text."], b"\x89PNG\r\n\x1a\n" + b"\x00" * 5000)

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        media_dir = Path(read_path).parent / "media"
        seen["images"] = sorted(m.name for m in media_dir.iterdir()) if media_dir.is_dir() else []
        cite_page("misc/deck.md", rel_key, "A deck fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert report.processed == ["raw/deck.pptx"]
    assert seen["images"] == ["image1.png"]  # the embedded image reached the agent


def test_office_embedded_images_skipped_when_image_support_off(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """With image support disabled, Office text is still ingested but no media/ folder is created."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "IMAGE_SUPPORT", False)
    _make_pptx_with_image(raw / "deck.pptx", ["Deck text."], b"\x89PNG\r\n\x1a\n" + b"\x00" * 5000)

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen["has_media"] = (Path(read_path).parent / "media").is_dir()
        cite_page("misc/deck.md", rel_key, "A deck fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert report.processed == ["raw/deck.pptx"] and seen["has_media"] is False


def test_office_deck_without_text_is_unreadable(tmp_citadel, fake_agent, make_pptx):
    """An all-images .pptx (no extractable text) is logged unreadable and never fed to the agent —
    no wasted session, marked done so a re-run does not re-check it."""
    raw = tmp_citadel.raw
    make_pptx(raw / "images.pptx", [[]])  # a slide with no text runs

    def fake(rel_key, kind="ingest", read_path=None):
        raise AssertionError(f"no session should run for a text-free deck (got {rel_key})")

    fake_agent(side_effect=fake)

    report = ingest.ingest()
    assert "raw/images.pptx" in report.unreadable
    assert report.processed == [] and not report.errors

    log_text = tmp_citadel.log_path.read_text(encoding="utf-8")
    assert "raw/images.pptx" in log_text and "no readable text" in log_text

    import json

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))["sources"]
    assert "raw/images.pptx" in data  # marked done


def test_image_source_is_read_visually_by_agent(tmp_citadel, fake_agent, cite_page):
    """A recognized image is fed to the agent with the IMAGE propagation (read visually, no text
    extraction / no read_path) and the wiki cites the image file as its source."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    _make_png(raw / "diagram.png")

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.update(rel_key=rel_key, kind=kind, read_path=read_path, segment=segment)
        cite_page("misc/diagram.md", rel_key, "The diagram shows a pump loop.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert report.processed == ["raw/diagram.png"]
    assert seen["kind"] == "image"  # image propagation, not plain "ingest"
    assert seen["read_path"] is None and seen["segment"] is None  # read the file directly, one pass
    assert "resource: raw/diagram.png" in (wiki / "misc" / "diagram.md").read_text(encoding="utf-8")

    # A CHANGED image re-ingests with the image-reconcile propagation.
    _make_png(raw / "diagram.png")  # same bytes -> not changed; write different bytes:
    (raw / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"different-bytes-now")
    ingest.ingest()
    assert seen["kind"] == "image-reconcile"


def test_image_support_off_marks_image_unreadable(tmp_citadel, fake_agent, monkeypatch):
    """With image support disabled, an image is logged unreadable (never fed to the agent)."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "IMAGE_SUPPORT", False)
    _make_png(raw / "diagram.png")

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        raise AssertionError("no session should run for an image when image support is off")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert "raw/diagram.png" in report.unreadable and report.processed == []


def test_text_file_with_image_extension_is_not_treated_as_image(tmp_citadel, fake_agent, cite_page):
    """A text file merely RENAMED to .png (no PNG magic) is not sent as an image — it falls through
    to the normal text sniff and ingests as a plain source (kind 'ingest', read directly)."""
    raw = tmp_citadel.raw
    (raw / "notreally.png").write_text("This is plain text, not a PNG at all.\n", encoding="utf-8")

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.update(kind=kind, read_path=read_path)
        cite_page("misc/notreally.md", rel_key, "A plain fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert report.processed == ["raw/notreally.png"]
    assert seen["kind"] == "ingest" and seen["read_path"] is None  # not an image
