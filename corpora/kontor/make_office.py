#!/usr/bin/env python3
"""Deterministic, stdlib-only generator for the ``kontor`` Office test corpus.

This script hand-writes the binary Office fixtures for the ``kontor`` corpus into
``corpora/kontor/raw/`` using ONLY the Python standard library (``zlib``,
``zipfile``, ``struct``, ``pathlib``, ``sys``) -- no python-pptx / python-docx /
openpyxl / PIL / markitdown. Every fact embedded here is dictated by the corpus
fact-sheet (the single source of truth the ground-truth answer key also derives
from), so generator and grader agree by construction. The company (Aldervik
Kontor) and all its numbers are invented -- MIT-safe.

The corpus exercises citadel's zero-dependency Office extractors
(:mod:`citadel.extract` for OOXML, :mod:`citadel.extract_ole` for legacy OLE2)
plus the ingest traps layered on top of them:

  * q3-review.pptx    -- OOXML PowerPoint: 4 slides + a speaker-notes slide, and
                         an embedded chart PNG whose headline "GROSS MARGIN 34.2%"
                         lives ONLY in pixels (the image-delta / CITADEL_IMAGE
                         trap -- that string appears in no slide's text).
  * policy-handbook.docx -- OOXML Word: a heading, a support-hours paragraph, a
                         3-data-row role/leave/remote table (each cell its own
                         <w:p><w:t> so the extractor captures it), and a probation
                         paragraph.
  * budget-2026.xlsx  -- OOXML Excel: two sheets (Summary, Headcount) with a
                         shared-string table for text and literal <v> for numbers;
                         workbook.xml + its .rels pin the tab order Summary then
                         Headcount.
  * legacy-memo.doc / legacy-deck.ppt / legacy-ledger.xls -- legacy OLE2 compound
                         files (minimal valid CFBF v3), each holding its fact text
                         as a UTF-16LE main stream (WordDocument / PowerPoint
                         Document / Workbook) that extract_ole salvages cleanly.
  * report.docx + report.doc -- the dedup-by-basename pair: SAME content, one
                         OOXML and one legacy OLE (the .docx wins, .doc is skipped).
  * Thumbs.db / desktop.ini / ~$policy-handbook.docx -- junk that matches the
                         default CITADEL_IGNORE_PATTERNS and is never ingested.

Determinism guarantees (running this twice reproduces byte-identical files):
  * OOXML ZIPs use a FIXED ``date_time`` (1980-01-01 00:00:00) and sorted member
    order; ``zlib``/``zipfile`` deflate is deterministic for a fixed input.
  * The chart PNG's faint dither is a fixed-seed LCG (no ``random``); the 5x7
    bitmap font and bar geometry are constants. There is no ``datetime.now()``,
    no randomness, and no time-based input anywhere.
  * The legacy OLE containers are assembled from constant sector layouts.

Internal invariants are checked with ``if ...: raise`` rather than ``assert`` so
byte-exactness still holds under ``python -O`` (which strips ``assert``).

Run ``python corpora/kontor/make_office.py`` to (re)generate the fixtures, or add
``--check`` to additionally round-trip every file back through citadel's own
extractors and print PASS/FAIL per file (run from the repo root, or with
``PYTHONPATH`` pointing at it, so ``import citadel`` resolves).
"""

from __future__ import annotations

import struct
import sys
import zipfile
import zlib
from pathlib import Path


# ===========================================================================
# Canonical facts (verbatim from the fact-sheet; both builders and --check use
# these so the generator and the answer key can never drift).
# ===========================================================================

# q3-review.pptx
SLIDE1 = "Aldervik Kontor — Q3 2026 Business Review"
SLIDE2 = "Q3 2026 revenue was EUR 6.4 million, up from EUR 5.8 million in Q2 2026."
SLIDE3 = "The company employs 142 staff across four departments."
SLIDE4 = "Warehouses operate in Rotterdam, Hamburg, and Gdansk."
Q3_NOTES = (
    "The board has not approved the Lisbon warehouse. Treat the planned Q4 2026 "
    "opening as tentative and do not announce it externally."
)
GROSS_MARGIN = "GROSS MARGIN 34.2%"  # pixels-only headline on ppt/media/image1.png

# policy-handbook.docx
HANDBOOK_HEADING = "Aldervik Trading Kontor — Staff Handbook"
HANDBOOK_SUPPORT = "Standard customer support hours are Monday to Friday, 09:00 to 17:00 CET."
HANDBOOK_TABLE = [
    ["Role", "Annual leave (days)", "Remote days per week"],
    ["Warehouse staff", "25", "0"],
    ["Office staff", "28", "2"],
    ["Managers", "30", "3"],
]
HANDBOOK_PROBATION = "The probation period for new staff is six months."

# legacy OLE fact text (one clean UTF-16LE run each)
MEMO_TEXT = (
    "Internal memo, 12 March 2019. As of early 2019 Aldervik operated two "
    "warehouses, in Rotterdam and Hamburg. The team was about 40 people."
)
DECK_TEXT = (
    "Aldervik Kontor kickoff deck, 2018. The company was founded in 2011 in "
    "Aldervik harbour. Its original business was importing dried goods and textiles."
)
LEDGER_TEXT = "Aldervik 2019 year-end summary. Staff: 38. Revenue: EUR 4.1 million."

# report.docx + report.doc (dedup pair, same content)
REPORT_HEADING = "Aldervik 2026 sustainability report (summary)."
REPORT_BODY = "Warehouse energy use fell 12 percent year over year."

# budget-2026.xlsx -- (Department, value) rows per sheet; totals are literal.
BUDGET_SUMMARY = [
    ("Department", "Budget EUR 2026", None),  # header (both text)
    ("Marketing", 88000, "n"),
    ("Engineering", 150000, "n"),
    ("Warehousing & Logistics", 210000, "n"),
    ("Sales", 120000, "n"),
    ("Total", 568000, "n"),
]
BUDGET_HEADCOUNT = [
    ("Department", "FTE 2026", None),  # header (both text)
    ("Marketing", 22, "n"),
    ("Engineering", 40, "n"),
    ("Warehousing & Logistics", 51, "n"),
    ("Sales", 25, "n"),
    ("Total", 138, "n"),
]

# ===========================================================================
# 1. Shared low-level plumbing
# ===========================================================================

FIXED_DT = (1980, 1, 1, 0, 0, 0)  # deterministic ZIP timestamp for every member

# A token content-types part -- OOXML readers ignore our namespace choices, but a
# real package always carries this, so we include a minimal one for realism.
_CONTENT_TYPES = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    b'<Default Extension="xml" ContentType="application/xml"/>'
    b'<Default Extension="png" ContentType="image/png"/>'
    b"</Types>"
)
_ROOT_RELS = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
)


def _esc(text: str) -> str:
    """XML-escape the characters that are special inside element text (& < >).

    Only ``Warehousing & Logistics`` actually needs it, but escaping everywhere
    keeps the part builders trivially correct if the facts ever change."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _zip(path: Path, members: dict[str, bytes]) -> None:
    """Write a deterministic ZIP: fixed timestamps, sorted member order, DEFLATE."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(members):
            zi = zipfile.ZipInfo(name, date_time=FIXED_DT)
            zi.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(zi, members[name])


# ===========================================================================
# 2. Minimal PNG + 5x7 bitmap font (the chart whose headline is pixels-only)
# ===========================================================================


def _png(width: int, height: int, pixels: bytes) -> bytes:
    """An 8-bit grayscale PNG from a ``width*height`` gray buffer (top row first)."""
    if len(pixels) != width * height:  # explicit (not assert): guards the IDAT size
        raise ValueError(f"pixel buffer is {len(pixels)} bytes, expected {width * height}")

    def chunk(typ: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: None
        raw += pixels[y * width : (y + 1) * width]
    idat = zlib.compress(bytes(raw), 9)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# 5x7 bitmap font (complete A-Z / 0-9 / punctuation, lifted from gazette's
# make_pdfs.py). Each glyph is 7 rows; a row's low 5 bits are its pixels, MSB
# leftmost. The full set is used deliberately: the chart headline "GROSS MARGIN
# 34.2%" needs O and S, which the OOXML PoC's reduced set omitted.
_GLYPH_ROWS: dict[str, tuple[str, ...]] = {
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11100", "10010", "10001", "10001", "10001", "10010", "11100"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "10001", "11001", "10101", "10011", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "11011", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    ".": ("00000", "00000", "00000", "00000", "00000", "00110", "00110"),
    ",": ("00000", "00000", "00000", "00000", "00110", "00100", "01000"),
    ":": ("00000", "00110", "00110", "00000", "00110", "00110", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    "%": ("11001", "11010", "00010", "00100", "01000", "10011", "10011"),
}
_GLYPHS = {ch: [int(row, 2) for row in rows] for ch, rows in _GLYPH_ROWS.items()}


def _stamp(px: bytearray, w: int, x: int, y: int, s: str, scale: int = 3, ink: int = 30) -> None:
    """Stamp string ``s`` into gray buffer ``px`` (width ``w``) at top-left ``(x, y)``.

    Each source pixel becomes a ``scale x scale`` block; the pen advances
    ``6*scale`` px per character (fixed width). Unknown chars map to a space."""
    for ch in s.upper():
        glyph = _GLYPHS.get(ch, _GLYPHS[" "])
        for row in range(7):
            for col in range(5):
                if (glyph[row] >> (4 - col)) & 1:
                    for dy in range(scale):
                        for dx in range(scale):
                            px[(y + row * scale + dy) * w + (x + col * scale + dx)] = ink
        x += 6 * scale


def _chart_png(headline: str) -> bytes:
    """A bar chart whose ``headline`` number lives ONLY in pixels.

    A faint fixed-seed 4x4-block near-white dither adds just enough entropy to
    defeat flat-run compression, pushing the PNG past extract_media's 4096-byte
    floor while staying a modest ~9 KB committed fixture."""
    w, h = 480, 300
    block, lo, span, st = 4, 236, 20, 0x2545F491  # fixed LCG seed -> deterministic dither
    bw = (w + block - 1) // block
    bvals: list[int] = []
    for _ in range(bw * ((h + block - 1) // block)):
        st = (st * 1103515245 + 12345) & 0xFFFFFFFF
        bvals.append(lo + (((st >> 16) & 0xFF) % span))
    px = bytearray(bvals[(y // block) * bw + (x // block)] for y in range(h) for x in range(w))
    for gx in range(40, w, 40):  # vertical gridlines
        for y in range(20, h - 40):
            px[y * w + gx] = 210
    heights = [60, 120, 90, 200, 150, 240, 110]
    for i, bar_h in enumerate(heights):  # bars
        x0 = 40 + i * 58
        for x in range(x0, x0 + 42):
            for y in range(h - 40 - bar_h, h - 40):
                px[y * w + x] = 60
    _stamp(px, w, 40, 16, headline, scale=3)  # the pixels-only headline number
    return _png(w, h, bytes(px))


# ===========================================================================
# 3. Minimal valid CFBF (OLE2) for the legacy .doc/.ppt/.xls fixtures
# ===========================================================================

_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ENDOFCHAIN = 0xFFFFFFFE
_FREESECT = 0xFFFFFFFF
_FATSECT = 0xFFFFFFFD
_SECTOR = 512

# The main-stream name each legacy format's text lives in (matches
# citadel.extract_ole._OLE_MAIN_STREAMS).
_OLE_STREAM_NAME = {".doc": "WordDocument", ".ppt": "PowerPoint Document", ".xls": "Workbook"}


def _dir_entry(name: str, obj_type: int, start: int, size: int) -> bytes:
    """One 128-byte CFBF directory entry (type 5 = root storage, 2 = stream)."""
    e = bytearray(128)
    nb = name.encode("utf-16-le")
    e[0 : len(nb)] = nb
    struct.pack_into("<H", e, 64, len(nb) + 2)  # name length incl. null terminator
    e[66] = obj_type
    e[67] = 1  # color = black
    struct.pack_into("<I", e, 68, _FREESECT)  # left sibling
    struct.pack_into("<I", e, 72, _FREESECT)  # right sibling
    struct.pack_into("<I", e, 76, _FREESECT)  # child
    struct.pack_into("<I", e, 116, start)
    struct.pack_into("<I", e, 120, size)
    return bytes(e)


def make_ole(text: str, stream_name: str) -> bytes:
    """A minimal single-stream CFBF v3 container.

    Layout: sector 0 = FAT, sector 1 = directory, sectors 2.. = the text stream.
    The stream is the fact text as UTF-16LE, padded with NULs to at least 4096
    bytes so it lives in the big FAT (read via ``read_chain``, not the mini-FAT);
    the trailing NULs terminate extract_ole's salvage run cleanly."""
    payload = text.encode("utf-16-le")
    n_stream_sectors = max(8, (len(payload) + _SECTOR - 1) // _SECTOR)  # >= 4096 bytes
    stream_bytes = payload.ljust(n_stream_sectors * _SECTOR, b"\x00")

    stream_start = 2
    n_sectors = 2 + n_stream_sectors

    # FAT: one uint32 "next sector" per sector.
    fat = [_FREESECT] * (_SECTOR // 4)
    fat[0] = _FATSECT
    fat[1] = _ENDOFCHAIN  # directory: single sector
    for s in range(stream_start, stream_start + n_stream_sectors - 1):
        fat[s] = s + 1
    fat[stream_start + n_stream_sectors - 1] = _ENDOFCHAIN
    fat_sector = b"".join(struct.pack("<I", x) for x in fat)

    # Directory: root storage (no mini-stream) + the text stream + 2 unused slots.
    directory = (
        _dir_entry("Root Entry", 5, _ENDOFCHAIN, 0)
        + _dir_entry(stream_name, 2, stream_start, len(stream_bytes))
        + bytes(128) * 2
    )

    # Header (512 bytes).
    hdr = bytearray(_SECTOR)
    hdr[0:8] = _OLE_MAGIC
    struct.pack_into("<H", hdr, 24, 0x003E)  # minor version
    struct.pack_into("<H", hdr, 26, 3)  # major version (v3 -> 512-byte sectors)
    struct.pack_into("<H", hdr, 28, 0xFFFE)  # byte order
    struct.pack_into("<H", hdr, 30, 9)  # sector shift -> 512
    struct.pack_into("<H", hdr, 32, 6)  # mini sector shift -> 64
    struct.pack_into("<I", hdr, 44, 1)  # num FAT sectors
    struct.pack_into("<I", hdr, 48, 1)  # first directory sector
    struct.pack_into("<I", hdr, 56, 4096)  # mini stream cutoff
    struct.pack_into("<I", hdr, 60, _ENDOFCHAIN)  # first mini-FAT sector
    struct.pack_into("<I", hdr, 64, 0)  # num mini-FAT sectors
    struct.pack_into("<I", hdr, 68, _ENDOFCHAIN)  # first DIFAT sector
    struct.pack_into("<I", hdr, 72, 0)  # num DIFAT sectors
    difat = [0] + [_FREESECT] * 108  # FAT sector 0, rest free
    struct.pack_into("<109I", hdr, 76, *difat)

    body = fat_sector + directory + stream_bytes
    if len(body) != n_sectors * _SECTOR:  # explicit (not assert): sector alignment is load-bearing
        raise ValueError(f"CFBF body is {len(body)} bytes, expected {n_sectors * _SECTOR}")
    return bytes(hdr) + body


def _write_ole(path: Path, text: str) -> None:
    """Write a legacy OLE file, picking the main-stream name from the extension."""
    ext = path.suffix.lower()
    stream_name = _OLE_STREAM_NAME.get(ext)
    if stream_name is None:  # explicit (not assert): an unexpected ext is a generator bug
        raise ValueError(f"no OLE main-stream name for extension {ext!r}")
    path.write_bytes(make_ole(text, stream_name))


# ===========================================================================
# 4. OOXML builders (namespace-agnostic extractor: local names p/t/si/sheet/c/v)
# ===========================================================================


def _docx_paragraph(text: str) -> str:
    return f"<w:p><w:r><w:t>{_esc(text)}</w:t></w:r></w:p>"


def _docx_table(rows: list[list[str]]) -> str:
    """A Word table where each cell is its own <w:p><w:t> (so the extractor
    captures every cell on its own line, in row-major order)."""
    out = ["<w:tbl>"]
    for row in rows:
        out.append("<w:tr>")
        for cell in row:
            out.append(f"<w:tc>{_docx_paragraph(cell)}</w:tc>")
        out.append("</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


def _make_docx(path: Path, blocks: list[str]) -> None:
    """Write a .docx from a list of body-XML blocks (paragraphs and/or a table)."""
    body = "".join(blocks)
    doc = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    _zip(
        path,
        {"[Content_Types].xml": _CONTENT_TYPES, "_rels/.rels": _ROOT_RELS, "word/document.xml": doc.encode("utf-8")},
    )


def _make_pptx(path: Path, slides: list[str], notes: dict[int, str]) -> None:
    """Write a .pptx from slide texts (one paragraph each) and a {slide_no: note}
    map (each note becomes its own notesSlide part)."""
    members: dict[str, bytes] = {"[Content_Types].xml": _CONTENT_TYPES}
    for i, text in enumerate(slides, 1):
        sld = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
            ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f"<a:p><a:r><a:t>{_esc(text)}</a:t></a:r></a:p></p:sld>"
        )
        members[f"ppt/slides/slide{i}.xml"] = sld.encode("utf-8")
    for slide_no, note in notes.items():
        nts = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<p:notes xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
            ' xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
            f"<a:p><a:r><a:t>{_esc(note)}</a:t></a:r></a:p></p:notes>"
        )
        members[f"ppt/notesSlides/notesSlide{slide_no}.xml"] = nts.encode("utf-8")
    members["ppt/media/image1.png"] = _chart_png(GROSS_MARGIN)
    _zip(path, members)


def _col_letter(idx: int) -> str:
    """0-based column index -> A1-style letters (0 -> A, 1 -> B, 26 -> AA)."""
    letters = ""
    idx += 1
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


class _SharedStrings:
    """A workbook shared-string table: interns text, hands back stable indices."""

    def __init__(self) -> None:
        self._index: dict[str, int] = {}
        self.items: list[str] = []

    def intern(self, text: str) -> int:
        if text not in self._index:
            self._index[text] = len(self.items)
            self.items.append(text)
        return self._index[text]

    def xml(self) -> bytes:
        body = "".join(f"<si><t>{_esc(s)}</t></si>" for s in self.items)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="{len(self.items)}" uniqueCount="{len(self.items)}">{body}</sst>'
        ).encode("utf-8")


def _sheet_xml(rows: list[list[tuple[str, object]]]) -> bytes:
    """Worksheet XML from rows of ``(kind, value)`` cells (kind ``"s"`` = shared
    string index, ``"n"`` = literal number). Cell refs are A1-style by position."""
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    ]
    for r, row in enumerate(rows, 1):
        out.append(f'<row r="{r}">')
        for col, (kind, value) in enumerate(row):
            ref = f"{_col_letter(col)}{r}"
            if kind == "s":
                out.append(f'<c r="{ref}" t="s"><v>{value}</v></c>')
            elif kind == "n":
                out.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:  # explicit (not assert): only shared-string and number cells are used
                raise ValueError(f"unknown cell kind {kind!r}")
        out.append("</row>")
    out.append("</sheetData></worksheet>")
    return "".join(out).encode("utf-8")


def _budget_rows(spec: list[tuple[str, object, str | None]], sst: _SharedStrings) -> list[list[tuple[str, object]]]:
    """Turn a (label, value, value_kind) sheet spec into placed cells. A None
    value_kind marks the header (both columns are text)."""
    rows: list[list[tuple[str, object]]] = []
    for label, value, value_kind in spec:
        left = ("s", sst.intern(label))
        if value_kind is None:
            right = ("s", sst.intern(str(value)))
        elif value_kind == "n":
            right = ("n", value)
        else:  # explicit (not assert): guards the spec shape
            raise ValueError(f"unknown value kind {value_kind!r}")
        rows.append([left, right])
    return rows


def _make_xlsx(path: Path) -> None:
    """Write budget-2026.xlsx: sheets Summary then Headcount, shared-string text,
    literal numbers, tab order pinned by workbook.xml + its .rels."""
    sst = _SharedStrings()
    sheet1 = _sheet_xml(_budget_rows(BUDGET_SUMMARY, sst))
    sheet2 = _sheet_xml(_budget_rows(BUDGET_HEADCOUNT, sst))
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
        ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        '<sheet name="Summary" sheetId="1" r:id="rId1"/>'
        '<sheet name="Headcount" sheetId="2" r:id="rId2"/>'
        "</sheets></workbook>"
    ).encode("utf-8")
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        "</Relationships>"
    ).encode("utf-8")
    _zip(
        path,
        {
            "[Content_Types].xml": _CONTENT_TYPES,
            "_rels/.rels": _ROOT_RELS,
            "xl/workbook.xml": workbook,
            "xl/_rels/workbook.xml.rels": rels,
            "xl/sharedStrings.xml": sst.xml(),
            "xl/worksheets/sheet1.xml": sheet1,
            "xl/worksheets/sheet2.xml": sheet2,
        },
    )


# ===========================================================================
# 5. The documents
# ===========================================================================


def build_q3_review(path: Path) -> None:
    _make_pptx(path, [SLIDE1, SLIDE2, SLIDE3, SLIDE4], {4: Q3_NOTES})


def build_policy_handbook(path: Path) -> None:
    _make_docx(
        path,
        [
            _docx_paragraph(HANDBOOK_HEADING),
            _docx_paragraph(HANDBOOK_SUPPORT),
            _docx_table(HANDBOOK_TABLE),
            _docx_paragraph(HANDBOOK_PROBATION),
        ],
    )


def build_budget(path: Path) -> None:
    _make_xlsx(path)


def build_legacy_memo(path: Path) -> None:
    _write_ole(path, MEMO_TEXT)


def build_legacy_deck(path: Path) -> None:
    _write_ole(path, DECK_TEXT)


def build_legacy_ledger(path: Path) -> None:
    _write_ole(path, LEDGER_TEXT)


def build_report_docx(path: Path) -> None:
    _make_docx(path, [_docx_paragraph(REPORT_HEADING), _docx_paragraph(REPORT_BODY)])


def build_report_doc(path: Path) -> None:
    _write_ole(path, f"{REPORT_HEADING} {REPORT_BODY}")


def build_junk(raw_dir: Path) -> list[tuple[str, int]]:
    """Write the three ignore-pattern junk files. Returns (name, size) pairs."""
    written: list[tuple[str, int]] = []
    junk: dict[str, bytes] = {
        # A few non-zero bytes -- a real Thumbs.db is an OLE thumbnail cache, but
        # the corpus only needs something non-empty that discovery skips.
        "Thumbs.db": bytes((0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08)),
        "desktop.ini": b"[.ShellClassInfo]\n",
        # A short binary-ish Office lock stub (not a valid ZIP -- never opened).
        "~$policy-handbook.docx": b"KO" + bytes(range(16)),
    }
    for name, data in junk.items():
        out = raw_dir / name
        out.write_bytes(data)
        written.append((name, len(data)))
    return written


# ===========================================================================
# 6. --check: round-trip every file through citadel's own extractors
# ===========================================================================


def _run_check(raw_dir: Path) -> int:
    """Import citadel's extractors and assert every Office file round-trips.
    Prints PASS/FAIL per file; returns 0 iff all pass."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from citadel import extract, extract_ole  # noqa: PLC0415 - lazy: only --check needs citadel

    all_ok = True

    def report(name: str, ok: bool, detail: str) -> None:
        nonlocal all_ok
        all_ok = all_ok and ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    # OOXML text round-trips (key fact must survive extraction).
    ooxml_facts = {
        "q3-review.pptx": [SLIDE3, SLIDE4, Q3_NOTES],
        "policy-handbook.docx": [HANDBOOK_HEADING, HANDBOOK_PROBATION, "Warehouse staff", "25"],
        "budget-2026.xlsx": ["Warehousing & Logistics", "568000", "Headcount", "138"],
        "report.docx": [REPORT_BODY],
    }
    for name, facts in ooxml_facts.items():
        p = raw_dir / name
        dispatch = extract.is_office_source(p)
        text = extract.extract_text(p)
        missing = [f for f in facts if f not in text]
        report(name, dispatch and not missing, f"dispatch={dispatch} missing={missing}")

    # The gross-margin headline must be pixels-only (never in the pptx text).
    pptx_text = extract.extract_text(raw_dir / "q3-review.pptx")
    report("q3-review.pptx (image-delta)", GROSS_MARGIN not in pptx_text, f"'{GROSS_MARGIN}' absent from text")

    # extract_media must surface image1.png at >= 4096 bytes.
    media = dict(extract.extract_media(raw_dir / "q3-review.pptx"))
    img_ok = "image1.png" in media and len(media["image1.png"]) >= 4096
    size = len(media.get("image1.png", b""))
    report("q3-review.pptx (media)", img_ok, f"image1.png={size} bytes (>=4096)")

    # Legacy OLE salvage round-trips.
    ole_facts = {
        "legacy-memo.doc": ["two warehouses", "Rotterdam and Hamburg"],
        "legacy-deck.ppt": ["founded in 2011"],
        "legacy-ledger.xls": ["Staff: 38", "EUR 4.1 million"],
        "report.doc": [REPORT_BODY],
    }
    for name, facts in ole_facts.items():
        p = raw_dir / name
        dispatch = extract.is_office_source(p)
        text = extract_ole.extract_ole_text(p)
        missing = [f for f in facts if f not in text]
        report(name, dispatch and not missing, f"dispatch={dispatch} missing={missing}")

    print("\nALL PASS" if all_ok else "\nFAILED")
    return 0 if all_ok else 1


# ===========================================================================
# 7. Entry point
# ===========================================================================


def main(argv: list[str]) -> int:
    check = "--check" in argv[1:]
    unknown = [a for a in argv[1:] if a != "--check"]
    if unknown:
        print(f"usage: {Path(argv[0]).name} [--check]  (unexpected args: {unknown})", file=sys.stderr)
        return 2

    raw_dir = Path(__file__).resolve().parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    documents = [
        ("q3-review.pptx", build_q3_review),
        ("policy-handbook.docx", build_policy_handbook),
        ("budget-2026.xlsx", build_budget),
        ("legacy-memo.doc", build_legacy_memo),
        ("legacy-deck.ppt", build_legacy_deck),
        ("legacy-ledger.xls", build_legacy_ledger),
        ("report.docx", build_report_docx),
        ("report.doc", build_report_doc),
    ]
    for name, builder in documents:
        out = raw_dir / name
        builder(out)
        print(f"{out}  ({out.stat().st_size} bytes)")

    for name, size in build_junk(raw_dir):
        print(f"{raw_dir / name}  ({size} bytes)")

    if check:
        print("\n--check: round-tripping through citadel.extract / extract_ole")
        return _run_check(raw_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
