#!/usr/bin/env python3
"""Deterministic, stdlib-only generator for the `gazette` PDF test corpus.

This script hand-writes four small, strictly-valid PDF 1.4 files into
``corpora/gazette/raw/`` for use as cite-citadel ingest fixtures. It uses ONLY
the Python standard library (``zlib`` for image compression, ``pathlib``/``sys``)
-- no reportlab, PIL, or fpdf. Output is fully deterministic: no timestamps, no
randomness, no ``datetime.now()``. Running it again reproduces the same bytes.

The files exercise different PDF-extraction behaviours:

  1. feature-article.pdf  -- 2 pages, text-only (Helvetica text layer).
  2. figure-brief.pdf     -- 1 page, text body + an embedded chart raster whose
                             numeric value ("0.42 (Nov 14)") lives ONLY in pixels.
  3. preprint.pdf         -- 2 pages, text-only, shaped like an academic preprint.
  4. scanned-notice.pdf   -- 1 page that is a single full-page image, NO text
                             layer at all (text extraction yields nothing).

PDF byte-plumbing notes (why the xref is byte-exact):
  * The file is assembled as a single growing ``bytearray``. Every object's
    start offset is recorded as ``len(out)`` at the instant just before its
    ``N 0 obj`` header is appended -- offsets are MEASURED, never estimated.
  * Each cross-reference entry is emitted as exactly 20 bytes
    (``"%010d 00000 n \n"``), matching the spec so pypdf can seek by offset.
  * Every stream stores its true byte ``/Length`` (``len(data)``), so the
    dictionary and the payload never disagree.
"""

from __future__ import annotations

import sys
import zlib
from pathlib import Path


# ---------------------------------------------------------------------------
# US-Letter geometry (PDF points, origin bottom-left)
# ---------------------------------------------------------------------------
PAGE_W = 612
PAGE_H = 792
MARGIN = 72

# ===========================================================================
# 1. Low-level PDF object plumbing
# ===========================================================================


class PDFBuilder:
    """Collects numbered objects and serialises them with a byte-exact xref.

    Objects are numbered 1..N contiguously (``alloc`` hands out the next id).
    ``build`` walks them in order, records each object's byte offset as it is
    written, then emits the xref table and trailer from those measured offsets.
    """

    def __init__(self) -> None:
        self._objects: dict[int, bytes] = {}
        self._next = 1
        self.root: int | None = None

    def alloc(self) -> int:
        """Reserve the next object number (body filled in later via ``put``)."""
        n = self._next
        self._next += 1
        return n

    def put(self, num: int, body: bytes) -> None:
        """Assign the body for a previously ``alloc``-ed object number."""
        self._objects[num] = body

    def add(self, body: bytes) -> int:
        """Allocate a fresh object number and set its body in one step."""
        num = self.alloc()
        self._objects[num] = body
        return num

    def build(self) -> bytes:
        if self.root is None:  # explicit (not assert): must hold even under python -O
            raise ValueError("root (catalog) object not set")
        n_objects = self._next - 1
        # All allocated numbers must have a body.
        for i in range(1, n_objects + 1):
            if i not in self._objects:
                raise ValueError(f"object {i} was allocated but never filled")

        out = bytearray()
        # Header: version + a binary-marker comment line (>=4 high bytes) so
        # naive tools treat the file as binary. Its length is part of every
        # offset below because we always measure len(out).
        out += b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"

        offsets: dict[int, int] = {}
        for i in range(1, n_objects + 1):
            body = self._objects[i]
            offsets[i] = len(out)  # start of "i 0 obj" -- measured, not guessed
            out += f"{i} 0 obj\n".encode("latin-1")
            out += body
            if not body.endswith(b"\n"):
                out += b"\n"
            out += b"endobj\n"

        # Cross-reference table. Object 0 is the mandatory free head entry.
        xref_offset = len(out)
        out += f"xref\n0 {n_objects + 1}\n".encode("latin-1")
        out += b"0000000000 65535 f \n"  # 20 bytes exactly
        for i in range(1, n_objects + 1):
            # 10-digit offset + space + 5-digit gen + space + 'n' + space + LF
            # == 20 bytes; the fixed width is what makes xref seeking work.
            entry = f"{offsets[i]:010d} 00000 n \n".encode("latin-1")
            if len(entry) != 20:  # explicit (not assert): the 20-byte width is load-bearing
                raise ValueError(f"xref entry must be 20 bytes, got {len(entry)}")
            out += entry

        out += b"trailer\n"
        out += f"<< /Size {n_objects + 1} /Root {self.root} 0 R >>\n".encode("latin-1")
        out += b"startxref\n"
        out += f"{xref_offset}\n".encode("latin-1")
        out += b"%%EOF\n"
        return bytes(out)


def stream_object(dict_extra: str, data: bytes) -> bytes:
    """Build a stream object body with a truthful ``/Length``.

    ``dict_extra`` is the dictionary content (without ``/Length``); ``data`` is
    the raw stream payload. ``/Length`` is the real byte length so the dict and
    the payload can never disagree.
    """
    prefix = f"{dict_extra} " if dict_extra else ""
    header = f"<< {prefix}/Length {len(data)} >>\nstream\n".encode("latin-1")
    return header + data + b"\nendstream"


def font_object() -> bytes:
    """The single base-14 Helvetica font shared by all text-layer pages."""
    return b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"


def catalog_object(pages_ref: int) -> bytes:
    return f"<< /Type /Catalog /Pages {pages_ref} 0 R >>".encode("latin-1")


def pages_object(kid_refs: list[int]) -> bytes:
    kids = " ".join(f"{r} 0 R" for r in kid_refs)
    return f"<< /Type /Pages /Kids [ {kids} ] /Count {len(kid_refs)} >>".encode("latin-1")


def page_object(parent_ref: int, content_ref: int, font_ref: int | None = None, image_ref: int | None = None) -> bytes:
    """A single page. Resources hold the font and/or the image XObject used."""
    res_parts: list[str] = []
    if font_ref is not None:
        res_parts.append(f"/Font << /F1 {font_ref} 0 R >>")
    if image_ref is not None:
        res_parts.append(f"/XObject << /Im0 {image_ref} 0 R >>")
    resources = " ".join(res_parts)
    return (
        f"<< /Type /Page /Parent {parent_ref} 0 R "
        f"/MediaBox [0 0 {PAGE_W} {PAGE_H}] "
        f"/Resources << {resources} >> "
        f"/Contents {content_ref} 0 R >>"
    ).encode("latin-1")


def image_object(width: int, height: int, gray: bytes) -> bytes:
    """A DeviceGray, 8-bit, Flate-compressed image XObject.

    ``gray`` is ``width*height`` bytes, one gray value per pixel, row-major with
    the TOP row first (PDF images are top-down). Compression is deterministic
    for a given input at a fixed level.
    """
    if len(gray) != width * height:  # explicit (not assert): guards the image stream size
        raise ValueError(f"gray buffer is {len(gray)} bytes, expected {width * height}")
    compressed = zlib.compress(gray, 9)
    extra = (
        f"/Type /XObject /Subtype /Image /Width {width} /Height {height} "
        f"/ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode"
    )
    return stream_object(extra, compressed)


# ===========================================================================
# 2. Text-layer content streams
# ===========================================================================


def _escape(text: str) -> str:
    """Escape the three characters special inside a PDF ``(...)`` string."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_block(x: float, y: float, size: float, leading: float, lines: list[str]) -> str:
    """One BT..ET text block: set font/leading, position, draw each line.

    The first line is drawn at ``(x, y)``; ``T*`` advances by ``leading`` before
    each subsequent line. An empty string in ``lines`` yields a blank line
    (useful as paragraph spacing).
    """
    parts = ["BT", f"/F1 {size} Tf", f"{leading} TL", f"{x} {y} Td"]
    for ln in lines:
        parts.append(f"({_escape(ln)}) Tj")
        parts.append("T*")
    parts.append("ET")
    return "\n".join(parts) + "\n"


def wrap(text: str, width: int = 90) -> list[str]:
    """Greedy word-wrap to at most ``width`` characters per line."""
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ===========================================================================
# 3. 5x7 bitmap font + raster helpers (for pixels-only text inside images)
# ===========================================================================
#
# Each glyph is 7 rows; each row's low 5 bits are the pixels, MSB = leftmost.
# Rows are written as binary strings for readability, then packed into ints.

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

# Pack each glyph into 7 ints (low 5 bits per row, MSB leftmost).
GLYPHS: dict[str, list[int]] = {ch: [int(row, 2) for row in rows] for ch, rows in _GLYPH_ROWS.items()}


def draw_text(
    pixels: bytearray,
    W: int,
    H: int,
    x: int,
    y: int,
    string: str,
    scale: int,
    ink: int = 0,
    bg: int = 255,  # noqa: ARG001 -- kept for signature parity; buffer is pre-filled
) -> None:
    """Stamp ``string`` into a gray pixel buffer at top-left ``(x, y)``.

    The input is upper-cased (the font is uppercase-only); unknown characters
    map to a space. Each source pixel becomes a ``scale x scale`` block, and the
    pen advances ``6*scale`` pixels per character (fixed width, no kerning).
    ``(x, y)`` is the top-left of the first glyph; rows run top-down.
    """
    string = string.upper()
    cx = x
    for ch in string:
        glyph = GLYPHS.get(ch, GLYPHS[" "])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if (bits >> (4 - col)) & 1:
                    px0 = cx + col * scale
                    py0 = y + row * scale
                    for dy in range(scale):
                        py = py0 + dy
                        if py < 0 or py >= H:
                            continue
                        base = py * W
                        for dx in range(scale):
                            px = px0 + dx
                            if 0 <= px < W:
                                pixels[base + px] = ink
        cx += 6 * scale


def fill_rect(pixels: bytearray, W: int, H: int, x0: int, y0: int, x1: int, y1: int, val: int) -> None:
    """Fill the pixel rectangle [x0,x1) x [y0,y1) (top-down rows) with ``val``."""
    for py in range(max(0, y0), min(H, y1)):
        base = py * W
        for px in range(max(0, x0), min(W, x1)):
            pixels[base + px] = val


def draw_line(pixels: bytearray, W: int, H: int, x0: int, y0: int, x1: int, y1: int, ink: int = 0) -> None:
    """Draw a 1px straight line between two points (simple linear interpolation)."""
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    steps = max(dx, dy, 1)
    for i in range(steps + 1):
        x = round(x0 + (x1 - x0) * i / steps)
        y = round(y0 + (y1 - y0) * i / steps)
        if 0 <= x < W and 0 <= y < H:
            pixels[y * W + x] = ink


def centered_x(W: int, text: str, scale: int) -> int:
    """Left x that horizontally centres ``text`` (6*scale px per char)."""
    return max(0, (W - len(text) * 6 * scale) // 2)


# ===========================================================================
# 4. Raster builders
# ===========================================================================


def make_chart_raster() -> tuple[int, int, bytes]:
    """Build the figure-brief bar chart. Returns (W, H, gray-bytes).

    The 12 monthly medians are hand-picked; the 11th bar (November) is the
    shortest -> best (sharpest) seeing. The numeric callout "best: 0.42 (Nov 14)"
    is rasterised here and NOWHERE in any text layer, which is the whole point.
    """
    W, H = 380, 220
    px = bytearray(b"\xff" * (W * H))  # white background

    baseline = 190  # pixel row of the x-axis (bars grow upward = smaller rows)
    left_axis = 44
    bar_w = 18
    gap = 9
    start_x = left_axis + 4

    # Monthly bar heights in px. Index 10 (November) is the shortest = best.
    heights = [90, 100, 85, 95, 80, 110, 105, 88, 60, 70, 40, 92]
    month_letters = "JFMAMJJASOND"

    # Axes.
    fill_rect(px, W, H, left_axis, 20, left_axis + 1, baseline + 1, 0)  # y-axis
    fill_rect(px, W, H, left_axis, baseline, W - 10, baseline + 1, 0)  # x-axis

    # Bars + month initials.
    for i, h in enumerate(heights):
        x0 = start_x + i * (bar_w + gap)
        top = baseline - h
        fill_rect(px, W, H, x0, top, x0 + bar_w, baseline, 0)
        draw_text(px, W, H, x0 + (bar_w - 6) // 2, baseline + 4, month_letters[i], 1)

    # Y-axis label (rendered horizontally near the top-left).
    draw_text(px, W, H, 4, 6, "arcsec", 1)

    # Callout -- numbers live ONLY in these pixels. A short pointer connects the
    # text to the shortest (November) bar.
    nov_x0 = start_x + 10 * (bar_w + gap)
    nov_center = nov_x0 + bar_w // 2
    nov_top = baseline - heights[10]
    draw_text(px, W, H, 236, 30, "best: 0.42 (Nov 14)", 1)
    draw_line(px, W, H, nov_center, 40, nov_center, nov_top, 0)

    return W, H, bytes(px)


def make_notice_raster() -> tuple[int, int, bytes]:
    """Build the full-page scanned-notice raster (portrait, white background).

    Every line of the public notice is stamped as pixels; there is no text layer
    on the page that shows it, so text extraction yields nothing.
    """
    W, H = 600, 780
    px = bytearray(b"\xff" * (W * H))

    # A simple inset border to look like a printed notice.
    fill_rect(px, W, H, 20, 20, W - 20, 24, 0)  # top
    fill_rect(px, W, H, 20, H - 24, W - 20, H - 20, 0)  # bottom
    fill_rect(px, W, H, 20, 20, 24, H - 20, 0)  # left
    fill_rect(px, W, H, W - 24, 20, W - 20, H - 20, 0)  # right

    # (text, scale). Empty text == a blank spacing row.
    lines: list[tuple[str, int]] = [
        ("CINDER PEAK OBSERVATORY", 3),
        ("PUBLIC NOTICE", 3),
        ("", 2),
        ("PUBLIC VIEWING NIGHTS ARE SUSPENDED", 2),
        ("FOR DOME RESURFACING FROM", 2),
        ("3 TO 17 APRIL 2026.", 2),
        ("", 2),
        ("THE OBSERVATORY REOPENS TO VISITORS", 2),
        ("ON 18 APRIL 2026.", 2),
        ("", 2),
        ("FOR UPDATES SEE THE MERIDIAN GAZETTE.", 2),
    ]

    y = 90
    for text, scale in lines:
        if text:
            draw_text(px, W, H, centered_x(W, text, scale), y, text, scale)
        y += 7 * scale + 22  # glyph height + generous line spacing

    return W, H, bytes(px)


# ===========================================================================
# 5. The four documents
# ===========================================================================


def build_feature_article() -> bytes:
    """2 pages, text only: the tardigrade science feature."""
    b1 = (
        "Tardigrades, the microscopic invertebrates commonly called water bears, "
        "endure near-total desiccation by entering a dormant state called "
        "cryptobiosis; when the loss of water drives it, biologists specifically "
        "call it anhydrobiosis."
    )
    b2 = (
        "As a water bear dries, it loses roughly 97 percent of its body water and "
        'pulls its legs in to form a shrunken, barrel-shaped "tun".'
    )
    b3 = (
        "To survive, it floods its cells with the sugar trehalose and with "
        "tardigrade-specific intrinsically disordered proteins (TDPs), which "
        "vitrify - turn glassy - as the animal dries, cradling proteins and "
        "membranes so they do not shatter."
    )
    b4 = (
        "In 2007, in an experiment known as TARDIS aboard the European FOTON-M3 "
        "satellite, tardigrades were carried into low Earth orbit and exposed "
        "directly to the vacuum of space and the Sun's unfiltered ultraviolet "
        "radiation; some survived the vacuum, and a number of those also survived "
        "the radiation and went on to reproduce after returning to Earth."
    )
    b5 = "A dried tun can wait for years, and rehydration revives it within minutes to hours."
    closing = "-- Continued reporting in the Meridian Gazette science desk."

    # --- Page 1 content ---
    p1 = ""
    p1 += text_block(MARGIN, 730, 18, 18, ["How Water Bears Survive the Void"])
    p1 += text_block(MARGIN, 708, 10, 12, ["The Meridian Gazette  |  Science"])
    page1_lines = wrap(b1) + [""] + wrap(b2) + [""] + wrap(b3)
    p1 += text_block(MARGIN, 675, 11, 15, page1_lines)

    # --- Page 2 content ---
    p2 = ""
    page2_lines = wrap(b4) + [""] + wrap(b5)
    p2 += text_block(MARGIN, 730, 11, 15, page2_lines)
    p2 += text_block(MARGIN, 560, 11, 15, [closing])

    pdf = PDFBuilder()
    catalog = pdf.alloc()
    pages = pdf.alloc()
    font = pdf.add(font_object())
    c1 = pdf.add(stream_object("", p1.encode("latin-1")))
    c2 = pdf.add(stream_object("", p2.encode("latin-1")))
    page1 = pdf.add(page_object(pages, c1, font_ref=font))
    page2 = pdf.add(page_object(pages, c2, font_ref=font))
    pdf.put(catalog, catalog_object(pages))
    pdf.put(pages, pages_object([page1, page2]))
    pdf.root = catalog
    return pdf.build()


def build_figure_brief() -> bytes:
    """1 page: text body + one embedded chart image (numbers pixels-only)."""
    body = (
        "This brief summarises the median nightly seeing measured at Cinder Peak "
        "Observatory, which opened in 1998, through 2025. Seeing - the blurring of "
        "stars by atmospheric turbulence - is reported in arcseconds, and lower is "
        "sharper. The monthly medians are shown in Figure 1. The autumn nights were "
        "consistently the sharpest of the year."
    )
    outlook = (
        "The survey will continue with the observatory's new instrument, which "
        "offers about three times the light-gathering area of the retired 0.6-metre "
        "telescope. Raw nightly logs are archived internally and are not reproduced "
        "here; this brief reports medians only."
    )
    caption = "Figure 1. Median nightly seeing by month, 2025."

    W, H, gray = make_chart_raster()
    img_w, img_h = 380, 220  # display size in points (1:1 with the raster px)
    img_x, img_y = MARGIN, 300  # lower-left placement (below the expanded text body)

    content = ""
    content += text_block(MARGIN, 730, 16, 16, ["Atmospheric Seeing Brief - 2025"])
    content += text_block(MARGIN, 710, 10, 12, ["Cinder Peak Observatory"])
    content += text_block(MARGIN, 685, 11, 15, wrap(body) + [""] + wrap(outlook))
    # Caption sits UNDER where the image is drawn.
    content += text_block(MARGIN, img_y - 18, 9, 11, [caption])
    # Draw the chart: q sw 0 0 sh tx ty cm /Im0 Do Q
    content += f"q {img_w} 0 0 {img_h} {img_x} {img_y} cm /Im0 Do Q\n"

    pdf = PDFBuilder()
    catalog = pdf.alloc()
    pages = pdf.alloc()
    font = pdf.add(font_object())
    img = pdf.add(image_object(W, H, gray))
    c1 = pdf.add(stream_object("", content.encode("latin-1")))
    page1 = pdf.add(page_object(pages, c1, font_ref=font, image_ref=img))
    pdf.put(catalog, catalog_object(pages))
    pdf.put(pages, pages_object([page1]))
    pdf.root = catalog
    return pdf.build()


def build_preprint() -> bytes:
    """2 pages, text only, shaped like an academic preprint."""
    abstract = (
        "We surveyed microplastic concentrations in three high-altitude tarns over "
        "a single melt season. The most affected site, Black Tarn, held up to "
        "1,180 microplastic particles per litre - roughly six times the "
        "concentration at the least affected site. We discuss likely "
        "atmospheric-deposition pathways."
    )
    methods = (
        "Triplicate 5-litre samples were drawn from each tarn at two-week "
        "intervals, vacuum-filtered onto 0.45-micrometre membranes, and counted "
        "by fluorescence microscopy after Nile Red staining."
    )
    results = (
        "Particle counts rose through the season at all sites and peaked in late "
        "summer. Black Tarn's 1,180 particles per litre was the season maximum; "
        "Glass Tarn recorded the lowest counts."
    )
    references = [
        "[1] A. Nowak et al. (2019). Freshwater microplastics: a review. Journal of Alpine Science 12(3), 210-229.",
        "[2] P. Reyes and K. Duman (2020). Atmospheric transport of fibres to "
        "remote lakes. Mountain Hydrology Letters 4, 55-61.",
        "[3] S. Okafor (2018). Nile Red staining protocols for microplastic counts. Methods in Limnology 7, 88-97.",
        "[4] J. Vance et al. (2021). Deposition gradients above the treeline. Alpine Environments 33, 1201-1215.",
        "[5] L. Feretti and R. Halvorsen (2022). Tarn sampling design. "
        "Institute for Mountain Hydrology Technical Note 9.",
    ]

    # --- Page 1 ---
    p1 = ""
    p1 += text_block(MARGIN, 730, 15, 15, ["Microplastic accumulation in three alpine tarns"])
    p1 += text_block(MARGIN, 710, 10, 12, ["R. Halvorsen, M. Okonkwo, and L. Feretti"])
    p1 += text_block(MARGIN, 696, 9, 11, ["Institute for Mountain Hydrology (preprint, not peer reviewed)"])
    p1 += text_block(MARGIN, 672, 11, 13, ["Abstract"])
    p1 += text_block(MARGIN, 655, 10, 13, wrap(abstract, 95))
    p1 += text_block(MARGIN, 575, 11, 13, ["Methods"])
    p1 += text_block(MARGIN, 558, 10, 13, wrap(methods, 95))

    # --- Page 2 ---
    p2 = ""
    p2 += text_block(MARGIN, 730, 11, 13, ["Results"])
    p2 += text_block(MARGIN, 713, 10, 13, wrap(results, 95))
    p2 += text_block(MARGIN, 650, 11, 13, ["References"])
    # Each reference on its own line (unwrapped -- they fit within the margins).
    p2 += text_block(MARGIN, 628, 9, 13, references)

    pdf = PDFBuilder()
    catalog = pdf.alloc()
    pages = pdf.alloc()
    font = pdf.add(font_object())
    c1 = pdf.add(stream_object("", p1.encode("latin-1")))
    c2 = pdf.add(stream_object("", p2.encode("latin-1")))
    page1 = pdf.add(page_object(pages, c1, font_ref=font))
    page2 = pdf.add(page_object(pages, c2, font_ref=font))
    pdf.put(catalog, catalog_object(pages))
    pdf.put(pages, pages_object([page1, page2]))
    pdf.root = catalog
    return pdf.build()


def build_scanned_notice() -> bytes:
    """1 page that is a single full-page image with NO text layer at all."""
    W, H, gray = make_notice_raster()

    # Display the raster to fill the page (small even margin keeps aspect close).
    disp_w, disp_h = 600, 780
    tx = (PAGE_W - disp_w) // 2
    ty = (PAGE_H - disp_h) // 2
    content = f"q {disp_w} 0 0 {disp_h} {tx} {ty} cm /Im0 Do Q\n"

    pdf = PDFBuilder()
    catalog = pdf.alloc()
    pages = pdf.alloc()
    img = pdf.add(image_object(W, H, gray))
    c1 = pdf.add(stream_object("", content.encode("latin-1")))
    # No /Font in resources -- there is deliberately no text on this page.
    page1 = pdf.add(page_object(pages, c1, image_ref=img))
    pdf.put(catalog, catalog_object(pages))
    pdf.put(pages, pages_object([page1]))
    pdf.root = catalog
    return pdf.build()


# ===========================================================================
# 6. Entry point
# ===========================================================================


def main() -> int:
    raw_dir = Path(__file__).parent / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    documents = [
        ("feature-article.pdf", build_feature_article),
        ("figure-brief.pdf", build_figure_brief),
        ("preprint.pdf", build_preprint),
        ("scanned-notice.pdf", build_scanned_notice),
    ]

    for name, builder in documents:
        data = builder()
        out_path = raw_dir / name
        out_path.write_bytes(data)
        print(f"{out_path}  ({len(data)} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
