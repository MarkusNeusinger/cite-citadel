"""Unit tests for the zero-dependency Office text extractor (no deps, no network).

Real ``.docx``/``.pptx`` files are just ZIPs of XML, so we build minimal valid packages on the fly
(only the parts the extractor reads) and assert it pulls the text out — paragraphs/table cells for
Word, slides + speaker notes in numeric order for PowerPoint — and degrades to ``""`` (never an
exception) on an unsupported type or a corrupt file.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from citadel import extract


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
        {
            "word/document.xml": f'<?xml version="1.0"?><w:document xmlns:w="{_W}"><w:body>{body_xml}</w:body></w:document>'
        },
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
    assert "Second paragraph with two runs." in text  # two runs joined within the paragraph
    assert "Cell A" in text and "Cell B" in text  # table cell text captured
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
    assert "## Slide 1" in text and "## Slide 3" in text  # slide10 is the 3rd in order
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

    # A supported OOXML extension with no readable content -> "" (an empty workbook has no sheets).
    assert extract.extract_text(_zip(tmp_path / "s.xlsx", {"xl/workbook.xml": "<x/>"})) == ""

    # A wholly unsupported extension -> "" even if it is a zip.
    assert extract.extract_text(_zip(tmp_path / "s.zip", {"a.txt": "hi"})) == ""


def test_extract_text_swallows_unexpected_exceptions(tmp_path, monkeypatch):
    """The "never raises" contract holds beyond BadZipFile/ParseError: an encrypted/unsupported ZIP
    member raises RuntimeError/NotImplementedError from zipfile, which must still degrade to "" so
    candidate partitioning never crashes on one odd file."""
    doc = _zip(tmp_path / "weird.docx", {"word/document.xml": "<x/>"})

    def boom(_path):
        raise RuntimeError("File is encrypted, password required for extraction")

    monkeypatch.setattr(extract, "_extract_docx", boom)
    assert extract.extract_text(doc) == ""


# --- xlsx -------------------------------------------------------------------------------

_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _xlsx(path: Path, sheets: list[tuple[str, str]], shared: list[str]) -> Path:
    """Build a minimal ``.xlsx`` from ``sheets`` (name -> sheetData XML) and a shared-string list,
    wiring workbook.xml + its rels so sheet ORDER and shared-string lookups are exercised."""
    sst_items = "".join(f"<si><t>{s}</t></si>" for s in shared)
    entries: dict[str, str] = {"xl/sharedStrings.xml": f'<?xml version="1.0"?><sst xmlns="{_S}">{sst_items}</sst>'}
    sheet_tags, rel_tags = [], []
    for i, (name, sheet_data) in enumerate(sheets, 1):
        rid = f"rId{i}"
        entries[f"xl/worksheets/sheet{i}.xml"] = (
            f'<?xml version="1.0"?><worksheet xmlns="{_S}"><sheetData>{sheet_data}</sheetData></worksheet>'
        )
        sheet_tags.append(f'<sheet name="{name}" sheetId="{i}" r:id="{rid}"/>')
        rel_tags.append(f'<Relationship Id="{rid}" Target="worksheets/sheet{i}.xml"/>')
    entries["xl/workbook.xml"] = (
        f'<?xml version="1.0"?><workbook xmlns="{_S}" xmlns:r="{_R}"><sheets>{"".join(sheet_tags)}</sheets></workbook>'
    )
    entries["xl/_rels/workbook.xml.rels"] = f'<?xml version="1.0"?><Relationships>{"".join(rel_tags)}</Relationships>'
    return _zip(path, entries)


def test_extract_xlsx_shared_inline_and_numeric_cells(tmp_path):
    data = (
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2"><v>42</v></c><c r="B2" t="inlineStr"><is><t>inline note</t></is></c></row>'
    )
    text = extract.extract_text(_xlsx(tmp_path / "book.xlsx", [("Data", data)], ["Region", "Total"]))
    assert "## Sheet: Data" in text
    assert "Region | Total" in text  # shared-string header row, pipe-joined
    assert "42 | inline note" in text  # numeric literal + inline string on the next row


def test_extract_xlsx_sparse_columns_stay_aligned(tmp_path):
    # A cell in column C with A/B empty keeps its position: two empty leading cells -> two pipes
    # before the value (the row-leading space is trimmed, but the column count is preserved).
    data = '<row r="1"><c r="C1" t="s"><v>0</v></c></row>'
    text = extract.extract_text(_xlsx(tmp_path / "sparse.xlsx", [("S", data)], ["third"]))
    assert "|  | third" in text


def test_extract_xlsx_sheets_in_workbook_order(tmp_path):
    first = '<row r="1"><c r="A1" t="s"><v>0</v></c></row>'
    second = '<row r="1"><c r="A1" t="s"><v>1</v></c></row>'
    # Declared order in workbook.xml is Alpha then Beta; assert that order is honored.
    text = extract.extract_text(
        _xlsx(tmp_path / "multi.xlsx", [("Alpha", first), ("Beta", second)], ["a-cell", "b-cell"])
    )
    assert text.index("## Sheet: Alpha") < text.index("## Sheet: Beta")


def test_is_office_source_true_for_xlsx(tmp_path):
    assert extract.is_office_source(_zip(tmp_path / "b.xlsx", {"xl/workbook.xml": "<x/>"}))


# --- legacy OLE (.doc/.ppt/.xls) --------------------------------------------------------


def _minimal_cfbf(stream_name: str, payload: bytes) -> bytes:
    """Build a minimal-but-valid OLE2 compound file holding ONE stream (``stream_name`` -> payload),
    to round-trip the CFBF reader. 512-byte sectors; payload stored in the FAT (>= mini cutoff), so
    no mini-FAT is needed: sector 0 = FAT, sector 1 = directory, sectors 2.. = payload."""
    import struct as _struct

    SECTOR = 512
    FREESECT, ENDOFCHAIN, FATSECT = 0xFFFFFFFF, 0xFFFFFFFE, 0xFFFFFFFD
    n_data = (len(payload) + SECTOR - 1) // SECTOR or 1

    header = bytearray(SECTOR)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    _struct.pack_into("<H", header, 24, 0x003E)  # minor version
    _struct.pack_into("<H", header, 26, 0x0003)  # major version 3 (512-byte sectors)
    _struct.pack_into("<H", header, 28, 0xFFFE)  # byte order LE
    _struct.pack_into("<H", header, 30, 9)  # sector shift -> 512
    _struct.pack_into("<H", header, 32, 6)  # mini sector shift -> 64
    _struct.pack_into("<I", header, 44, 1)  # number of FAT sectors
    _struct.pack_into("<I", header, 48, 1)  # first directory sector
    _struct.pack_into("<I", header, 56, 4096)  # mini stream cutoff
    _struct.pack_into("<I", header, 60, ENDOFCHAIN)  # first mini-FAT sector
    _struct.pack_into("<I", header, 64, 0)  # number of mini-FAT sectors
    _struct.pack_into("<I", header, 68, ENDOFCHAIN)  # first DIFAT sector
    _struct.pack_into("<I", header, 72, 0)  # number of DIFAT sectors
    difat = [0] + [FREESECT] * 108  # FAT lives in sector 0
    _struct.pack_into("<109I", header, 76, *difat)

    fat = [FATSECT, ENDOFCHAIN]  # sector 0 = FAT itself, sector 1 = directory (single sector)
    for k in range(n_data):  # payload chain: sectors 2 .. 2+n_data-1
        fat.append(2 + k + 1 if k < n_data - 1 else ENDOFCHAIN)
    fat += [FREESECT] * (SECTOR // 4 - len(fat))
    fat_sector = _struct.pack(f"<{SECTOR // 4}I", *fat)

    def dir_entry(name: str, obj_type: int, start: int, size: int) -> bytes:
        e = bytearray(128)
        raw = name.encode("utf-16-le") + b"\x00\x00"
        e[0 : len(raw)] = raw
        _struct.pack_into("<H", e, 64, len(raw))
        e[66] = obj_type
        _struct.pack_into("<I", e, 116, start)
        _struct.pack_into("<I", e, 120, size)
        return bytes(e)

    directory = bytearray(SECTOR)
    directory[0:128] = dir_entry("Root Entry", 5, ENDOFCHAIN, 0)
    directory[128:256] = dir_entry(stream_name, 2, 2, len(payload))

    data_region = payload + b"\x00" * (n_data * SECTOR - len(payload))
    return bytes(header) + fat_sector + bytes(directory) + data_region


def test_cfbf_reader_round_trips_a_stream():
    text = "Compound file body text. " * 300  # >4096 bytes so it lives in the FAT, not the mini-FAT
    payload = text.encode("utf-16-le")
    streams = extract._cfbf_streams(_minimal_cfbf("WordDocument", payload))
    assert "WordDocument" in streams
    assert streams["WordDocument"] == payload


def test_extract_ole_doc_recovers_utf16_text_via_cfbf(tmp_path):
    body = "Quarterly revenue rose to 4.2 million euros in the northern region."
    payload = ("\x00\x00" + body + "\x00\x00").encode("utf-16-le")  # some binary padding around it
    p = tmp_path / "report.doc"
    p.write_bytes(_minimal_cfbf("WordDocument", payload + b"\x00" * 5000))
    text = extract.extract_text(p)
    assert "Quarterly revenue rose to 4.2 million euros" in text


def test_extract_ole_falls_back_to_whole_file_salvage(tmp_path):
    # OLE magic but a corrupt/short container: the CFBF parse fails, so we salvage the whole file.
    fact = "Legacy deck slide one heading text"
    blob = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00\x03\x91" + fact.encode("utf-16-le") + b"\x02\x00"
    p = tmp_path / "old.ppt"
    p.write_bytes(blob)
    assert fact in extract.extract_text(p)


def test_salvage_text_recovers_singlebyte_runs():
    # No UTF-16 (no interleaved NULs) -> the CP-1252 single-byte pass recovers the run.
    data = b"\x01\x02\x03Widget assembly torque spec is 12 Nm\xff\xfe"
    out = extract._salvage_text(data)
    assert "Widget assembly torque spec is 12 Nm" in out


def test_salvage_text_drops_wordless_noise():
    # A run with no alphanumerics is structural noise and must be dropped.
    assert extract._salvage_text(b"\x00\x00---!!!===\x00\x00") == ""


def test_is_office_source_true_for_legacy_ole(tmp_path):
    for ext in (".doc", ".ppt", ".xls"):
        p = tmp_path / f"legacy{ext}"
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 100)
        assert extract.is_office_source(p)
    # OLE magic but a non-legacy extension is not claimed as office.
    other = tmp_path / "thing.bin"
    other.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    assert not extract.is_office_source(other)
