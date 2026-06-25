"""Unit tests for the zero-dependency Office text extractor (no deps, no network).

Real ``.docx``/``.pptx`` files are just ZIPs of XML, so we build minimal valid packages on the fly
(only the parts the extractor reads) and assert it pulls the text out — paragraphs/table cells for
Word, slides + speaker notes in numeric order for PowerPoint — and degrades to ``""`` (never an
exception) on an unsupported type or a corrupt file.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from okf_wiki import extract

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P = "http://schemas.openxmlformats.org/presentationml/2006/main"


def _zip(path: Path, entries: dict[str, str]) -> Path:
    """Write ``entries`` (arcname -> text) into a real ZIP at ``path`` (so it starts with the
    PK\\x03\\x04 magic ``is_office_source`` checks)."""
    with zipfile.ZipFile(path, "w") as z:
        for name, text in entries.items():
            z.writestr(name, text)
    return path


def _docx(path: Path, body_xml: str) -> Path:
    return _zip(
        path,
        {"word/document.xml": f'<?xml version="1.0"?><w:document xmlns:w="{_W}"><w:body>{body_xml}</w:body></w:document>'},
    )


def _slide(text_paras: list[str]) -> str:
    runs = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in text_paras)
    return f'<?xml version="1.0"?><p:sld xmlns:p="{_P}" xmlns:a="{_A}"><p:cSld><p:spTree><p:sp><p:txBody>{runs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>'


# --- is_office_source -------------------------------------------------------------------


def test_is_office_source_true_for_real_pptx_docx(tmp_path):
    assert extract.is_office_source(_zip(tmp_path / "d.docx", {"word/document.xml": "<x/>"}))
    assert extract.is_office_source(_zip(tmp_path / "p.pptx", {"ppt/slides/slide1.xml": "<x/>"}))
    assert extract.is_office_source(_zip(tmp_path / "m.docm", {"word/document.xml": "<x/>"}))


def test_is_office_source_false_for_non_office_and_non_zip(tmp_path):
    # Right magic, wrong extension -> not office (a plain .zip is left alone).
    assert not extract.is_office_source(_zip(tmp_path / "a.zip", {"x.txt": "hi"}))
    # Right extension, wrong magic (a renamed text file) -> not office.
    txt_as_pptx = tmp_path / "fake.pptx"
    txt_as_pptx.write_text("not a zip, just text\n", encoding="utf-8")
    assert not extract.is_office_source(txt_as_pptx)
    # A normal text file.
    plain = tmp_path / "notes.txt"
    plain.write_text("plain\n", encoding="utf-8")
    assert not extract.is_office_source(plain)


# --- docx -------------------------------------------------------------------------------


def test_extract_docx_paragraphs_runs_and_table_cells(tmp_path):
    body = (
        "<w:p><w:r><w:t>Hello world.</w:t></w:r></w:p>"
        "<w:p><w:r><w:t>Second paragraph with </w:t></w:r><w:r><w:t>two runs.</w:t></w:r></w:p>"
        "<w:tbl><w:tr>"
        "<w:tc><w:p><w:r><w:t>Cell A</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>Cell B</w:t></w:r></w:p></w:tc>"
        "</w:tr></w:tbl>"
    )
    text = extract.extract_text(_docx(tmp_path / "doc.docx", body))
    assert "Hello world." in text
    assert "Second paragraph with two runs." in text   # two runs joined within the paragraph
    assert "Cell A" in text and "Cell B" in text        # table cell text captured
    # Document order is preserved.
    assert text.index("Hello world.") < text.index("Second paragraph") < text.index("Cell A")


def test_extract_docx_includes_footnotes(tmp_path):
    path = _zip(
        tmp_path / "fn.docx",
        {
            "word/document.xml": f'<?xml version="1.0"?><w:document xmlns:w="{_W}"><w:body>'
            "<w:p><w:r><w:t>Body text.</w:t></w:r></w:p></w:body></w:document>",
            "word/footnotes.xml": f'<?xml version="1.0"?><w:footnotes xmlns:w="{_W}">'
            "<w:footnote><w:p><w:r><w:t>A footnote fact.</w:t></w:r></w:p></w:footnote></w:footnotes>",
        },
    )
    text = extract.extract_text(path)
    assert "Body text." in text and "A footnote fact." in text


# --- pptx -------------------------------------------------------------------------------


def test_extract_pptx_orders_slides_numerically_with_notes(tmp_path):
    path = _zip(
        tmp_path / "deck.pptx",
        {
            "ppt/slides/slide1.xml": _slide(["Alpha title", "Alpha bullet"]),
            "ppt/slides/slide2.xml": _slide(["Beta title"]),
            # slide10 must sort AFTER slide2 (numeric, not lexical).
            "ppt/slides/slide10.xml": _slide(["Gamma title"]),
            "ppt/notesSlides/notesSlide1.xml": _slide(["Speaker note for alpha"]),
        },
    )
    text = extract.extract_text(path)
    assert "Alpha title" in text and "Beta title" in text and "Gamma title" in text
    assert text.index("Alpha title") < text.index("Beta title") < text.index("Gamma title")
    assert "## Slide 1" in text and "## Slide 3" in text   # slide10 is the 3rd in order
    assert "## Speaker notes" in text and "Speaker note for alpha" in text


def test_extract_pptx_textless_deck_is_empty(tmp_path):
    # A slide with shapes but no <a:t> text (e.g. all images) extracts to nothing.
    empty_slide = f'<?xml version="1.0"?><p:sld xmlns:p="{_P}" xmlns:a="{_A}"><p:cSld><p:spTree><p:sp><p:txBody></p:txBody></p:sp></p:spTree></p:cSld></p:sld>'
    path = _zip(tmp_path / "images.pptx", {"ppt/slides/slide1.xml": empty_slide})
    assert extract.extract_text(path) == ""


# --- robustness -------------------------------------------------------------------------


def test_extract_text_empty_on_corrupt_or_unsupported(tmp_path):
    # A .docx that is not actually a ZIP -> "" (no exception).
    not_zip = tmp_path / "broken.docx"
    not_zip.write_text("definitely not a zip\n", encoding="utf-8")
    assert extract.extract_text(not_zip) == ""

    # Malformed XML inside a valid zip -> "" (ParseError swallowed).
    bad_xml = _zip(tmp_path / "badxml.docx", {"word/document.xml": "<w:document><unclosed>"})
    assert extract.extract_text(bad_xml) == ""

    # Unsupported extension -> "" even if it is a zip.
    assert extract.extract_text(_zip(tmp_path / "s.xlsx", {"xl/workbook.xml": "<x/>"})) == ""

    # Legacy binary .ppt/.doc (not OOXML) -> unsupported -> "".
    legacy = tmp_path / "old.ppt"
    legacy.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1binary")
    assert extract.extract_text(legacy) == ""
