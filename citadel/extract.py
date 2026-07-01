"""Zero-dependency text extraction for binary Office files (PowerPoint / Word / Excel).

A ``.pptx``/``.docx``/``.xlsx`` (and their macro-enabled ``.pptm``/``.docm``/``.xlsm`` siblings)
is an Office Open XML package — really a ZIP archive of XML parts — so the agentic CLI's file
reader cannot open it the way it opens a ``.md``/``.txt``/PDF. The **legacy** ``.doc``/``.ppt``/
``.xls`` are older OLE2 *compound files* (a FAT-like container of binary streams), which the CLI
likewise cannot read. Rather than add a heavy dependency (``python-pptx`` / ``python-docx`` /
``openpyxl`` / ``markitdown``), this module pulls the text out with the standard library only
(``zipfile`` + ``xml.etree.ElementTree`` for OOXML; a tiny CFBF reader in the
:mod:`citadel.extract_ole` sibling, imported lazily so the common OOXML path never pays for it),
matching the project's KISS, no-extra-deps ethos.

``ingest`` uses it in two places (see :mod:`citadel.ingest`):

- :func:`is_office_source` (cheap: extension + container magic) lets
  :func:`citadel.ingest._is_ingestible` treat an Office file as ingestible instead of rejecting it
  as a NUL-byte binary;
- :func:`extract_text` produces the plain text that ingest writes to a temp ``.md`` for the agent to
  read — while the wiki still cites the ORIGINAL Office file as its source.

Best-effort by design:

- **OOXML** (``.docx``/``.pptx``/``.xlsx`` …) captures slide/shape/table/notes text (pptx),
  paragraph/table text (docx), and per-sheet cell grids (xlsx) — enough for fact ingestion, but not
  drawing-canvas SmartArt, embedded charts/objects, or exact table geometry.
- **Legacy OLE** (``.doc``/``.ppt``/``.xls``) has no clean stdlib parser, so we open the OLE2
  container, isolate the document's main stream, and *salvage* its readable UTF-16LE / CP-1252 text
  runs (falling back to salvaging the whole file if the container can't be parsed). This recovers the
  prose/labels a fact-ingest needs, but is noisier than OOXML and drops formatting/geometry. The
  machinery lives in :mod:`citadel.extract_ole`.

Any parse/IO failure yields ``""`` (the caller then logs the file as unreadable), never an exception
that could break a run.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


# OOXML packages all start with the ZIP local-file-header magic; legacy OLE2 compound files start
# with their own 8-byte signature. We gate on BOTH the extension and the matching magic so a plain
# ``.zip`` (or a renamed text file) is never mistaken for an Office document.
_ZIP_MAGIC = b"PK\x03\x04"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_WORD_EXTS = {".docx", ".docm"}
_PPT_EXTS = {".pptx", ".pptm"}
_EXCEL_EXTS = {".xlsx", ".xlsm"}
_OOXML_EXTS = _WORD_EXTS | _PPT_EXTS | _EXCEL_EXTS
# Legacy binary OLE2 formats (Word 97-2003 / PowerPoint 97-2003 / Excel 97-2003).
_OLE_EXTS = {".doc", ".ppt", ".xls"}
# Every extension ingest hands to us (kept as one name so callers can ask "is this an Office file
# we extract text from?" without caring whether it is OOXML or legacy OLE).
_OFFICE_EXTS = _OOXML_EXTS | _OLE_EXTS

# Embedded raster images live under these ZIP paths in an OOXML package; these extensions are the
# ones a vision-capable agent reader can display (vector EMF/WMF are skipped — not renderable).
_MEDIA_DIRS = ("ppt/media/", "word/media/", "xl/media/")
_MEDIA_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}


def is_office_source(path: Path | str) -> bool:
    """True if ``path`` is a PowerPoint/Word/Excel file we can extract text from: a supported
    extension AND the matching container magic (ZIP for OOXML, OLE2 for legacy ``.doc``/``.ppt``/
    ``.xls``). Cheap (reads a few bytes) and never raises."""
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _OOXML_EXTS:
        return _has_magic(p, _ZIP_MAGIC)
    if ext in _OLE_EXTS:
        return _has_magic(p, _OLE_MAGIC)
    return False


def extract_text(path: Path | str) -> str:
    """Return the plain text of a supported Office file, or ``""`` for an unsupported type or on ANY
    read/parse failure (so the caller can treat empty == unreadable). Never raises."""
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext in _WORD_EXTS:
            return _normalize(_extract_docx(p))
        if ext in _PPT_EXTS:
            return _normalize(_extract_pptx(p))
        if ext in _EXCEL_EXTS:
            return _normalize(_extract_xlsx(p))
        if ext in _OLE_EXTS:
            # Lazy: the CFBF/salvage machinery is only imported when a legacy OLE file is actually
            # dispatched, so the common OOXML path never pays for it.
            from . import extract_ole

            return _normalize(extract_ole.extract_ole_text(p))
    except Exception:  # noqa: BLE001 - contract is "never raises": a malformed/encrypted/odd file
        # must degrade to "" so candidate partitioning (`_is_ingestible`) and ingest never crash on
        # ONE bad file. zipfile/ET/struct surface failures well beyond BadZipFile/ParseError — an
        # encrypted member raises RuntimeError, an unsupported compression method
        # NotImplementedError, a truncated OLE header struct.error, etc. — so we catch broadly here
        # (BaseException like Ctrl+C still propagates).
        return ""
    return ""


def extract_media(path: Path | str, min_bytes: int = 4096, max_count: int = 24) -> list[tuple[str, bytes]]:
    """Embedded raster images from an OOXML Office file (``ppt``/``word``/``xl`` ``media/``), as
    ``(filename, bytes)`` for the agent to VIEW — decks and docs often carry diagrams, charts, and
    screenshots as images the *text* extractor cannot see. Skips tiny assets (``< min_bytes``:
    bullets/icons/logos) and vector EMF/WMF the reader can't render, and caps at ``max_count``
    (largest first) to bound cost. Returns ``[]`` for a non-OOXML/legacy file or on ANY error —
    never raises (mirrors :func:`extract_text`)."""
    p = Path(path)
    if p.suffix.lower() not in _OOXML_EXTS:
        return []
    try:
        with zipfile.ZipFile(p) as z:
            picked = [
                info
                for info in z.infolist()
                if any(info.filename.startswith(d) for d in _MEDIA_DIRS)
                and Path(info.filename).suffix.lower() in _MEDIA_IMAGE_EXTS
                and info.file_size >= min_bytes
            ]
            picked.sort(key=lambda i: (-i.file_size, i.filename))  # keep the largest (most content)
            out = [(Path(info.filename).name, z.read(info.filename)) for info in picked[:max_count]]
        out.sort(key=lambda t: t[0])  # deterministic order for the agent
        return out
    except Exception:  # noqa: BLE001 - same "never raises" contract as extract_text
        return []


# --- internals: shared -------------------------------------------------------------------


def _has_magic(p: Path, magic: bytes) -> bool:
    """True if the first ``len(magic)`` bytes of ``p`` equal ``magic``. Never raises."""
    try:
        with open(p, "rb") as fh:
            return fh.read(len(magic)) == magic
    except OSError:
        return False


def _local(tag: str) -> str:
    """Strip the ``{namespace}`` prefix ElementTree puts on every tag, leaving the local name
    (``{...wordprocessingml...}p`` -> ``p``), so we can match across the w:/a:/p: namespaces
    without hard-coding their URIs."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _attr_by_local(el: ET.Element, local: str) -> str | None:
    """Value of the first attribute whose *local* name is ``local`` (namespace-agnostic), or None.
    Lets us read ``r:id`` / ``t`` / ``r`` without hard-coding the relationships-namespace URI."""
    for key, val in el.attrib.items():
        if _local(key) == local:
            return val
    return None


def _paragraph_texts(xml_bytes: bytes, para_local: str, text_local: str) -> list[str]:
    """One string per ``<*:{para_local}>`` element in document order, each the concatenation of its
    descendant ``<*:{text_local}>`` runs. Used for both Word (``w:p``/``w:t``) and PowerPoint
    (``a:p``/``a:t``); table cells contribute their inner paragraphs, so cell text is captured
    (linearly, one cell-paragraph per line)."""
    root = ET.fromstring(xml_bytes)
    out: list[str] = []
    for el in root.iter():
        if _local(el.tag) != para_local:
            continue
        runs = [t.text for t in el.iter() if _local(t.tag) == text_local and t.text]
        out.append("".join(runs))
    return out


def _slide_number(name: str) -> int:
    """The trailing integer of an OOXML part name (``ppt/slides/slide10.xml`` -> 10) so slides and
    notes sort numerically (slide2 before slide10), not lexically."""
    m = re.search(r"(\d+)\.xml$", name)
    return int(m.group(1)) if m else 0


def _normalize(text: str) -> str:
    """Trim trailing whitespace per line and collapse runs of 3+ blank lines to one, so the
    extracted markdown is tidy regardless of how the source spaced its paragraphs."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    joined = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


# --- internals: Word (.docx) -------------------------------------------------------------


def _extract_docx(path: Path) -> str:
    """Body + footnotes/endnotes text of a Word document, one paragraph per line. Table cells are
    included as their own lines (linear, no column geometry); headers/footers are skipped."""
    blocks: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        for part in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml"):
            if part not in names:
                continue
            paras = _paragraph_texts(z.read(part), "p", "t")
            text = "\n".join(paras).strip()
            if text:
                blocks.append(text)
    return "\n\n".join(blocks)


# --- internals: PowerPoint (.pptx) -------------------------------------------------------


def _extract_pptx(path: Path) -> str:
    """Per-slide text (shapes + table cells) under ``## Slide N`` headings, followed by a
    ``## Speaker notes`` section if any slide carries notes. Slides and notes are ordered
    numerically by their part name."""
    out: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        slides = sorted((n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=_slide_number)
        notes = sorted((n for n in names if re.fullmatch(r"ppt/notesSlides/notesSlide\d+\.xml", n)), key=_slide_number)
        for i, name in enumerate(slides, 1):
            paras = _paragraph_texts(z.read(name), "p", "t")
            body = "\n".join(p for p in paras if p.strip()).strip()
            if body:
                out.append(f"## Slide {i}\n\n{body}")
        notes_blocks: list[str] = []
        for name in notes:
            paras = _paragraph_texts(z.read(name), "p", "t")
            body = "\n".join(p for p in paras if p.strip()).strip()
            if body:
                notes_blocks.append(body)
        if notes_blocks:
            out.append("## Speaker notes\n\n" + "\n\n".join(notes_blocks))
    return "\n\n".join(out)


# --- internals: Excel (.xlsx) ------------------------------------------------------------


def _xlsx_shared_strings(z: zipfile.ZipFile, names: set[str]) -> list[str]:
    """The workbook's shared-string table (``xl/sharedStrings.xml``): one entry per ``<si>``, each
    the concatenation of its descendant ``<t>`` runs. Empty list when the part is absent."""
    if "xl/sharedStrings.xml" not in names:
        return []
    root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    out: list[str] = []
    for si in root:
        if _local(si.tag) != "si":
            continue
        out.append("".join(t.text for t in si.iter() if _local(t.tag) == "t" and t.text))
    return out


def _xlsx_sheet_order(z: zipfile.ZipFile, names: set[str]) -> list[tuple[str, str]]:
    """``[(sheet_name, part_path)]`` in workbook (tab) order, resolved via ``xl/workbook.xml`` +
    its ``.rels``. Falls back to the numerically-sorted ``xl/worksheets/sheet*.xml`` parts (named
    ``Sheet1``, ``Sheet2`` …) when the workbook/rels can't be read."""
    fallback = [
        (f"Sheet{_slide_number(n)}", n)
        for n in sorted((n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)), key=_slide_number)
    ]
    if "xl/workbook.xml" not in names or "xl/_rels/workbook.xml.rels" not in names:
        return fallback
    try:
        rid_to_target: dict[str, str] = {}
        for rel in ET.fromstring(z.read("xl/_rels/workbook.xml.rels")):
            rid = _attr_by_local(rel, "Id")
            target = _attr_by_local(rel, "Target")
            if rid and target:
                # Targets are relative to xl/ (e.g. "worksheets/sheet1.xml"); normalize a leading /.
                rid_to_target[rid] = "xl/" + target.lstrip("/") if not target.startswith("xl/") else target
        ordered: list[tuple[str, str]] = []
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        for el in wb.iter():
            if _local(el.tag) != "sheet":
                continue
            name = _attr_by_local(el, "name") or "Sheet"
            rid = _attr_by_local(el, "id")
            part = rid_to_target.get(rid or "")
            if part and part in names:
                ordered.append((name, part))
        return ordered or fallback
    except (ET.ParseError, KeyError):
        return fallback


def _col_index(cell_ref: str) -> int:
    """Zero-based column index of an A1-style cell reference (``B7`` -> 1, ``AA3`` -> 26). Returns
    the running position when the ref has no letters (so cells still land in appearance order)."""
    letters = re.match(r"[A-Za-z]+", cell_ref or "")
    if not letters:
        return -1
    idx = 0
    for ch in letters.group(0).upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _xlsx_cell_text(c: ET.Element, shared: list[str]) -> str:
    """The display text of one ``<c>`` cell: a shared-string lookup (``t="s"``), inline string
    (``t="inlineStr"``), or the literal ``<v>`` value (numbers/booleans/formula results)."""
    t = _attr_by_local(c, "t")
    if t == "inlineStr":
        return "".join(x.text for x in c.iter() if _local(x.tag) == "t" and x.text)
    v = next((x.text for x in c if _local(x.tag) == "v"), None)
    if v is None:
        return ""
    if t == "s":
        try:
            return shared[int(v)]
        except (ValueError, IndexError):
            return ""
    return v


def _xlsx_sheet_rows(xml_bytes: bytes, shared: list[str]) -> list[list[str]]:
    """The non-empty rows of one worksheet as lists of cell strings, cells placed by their column
    letter so sparse columns stay aligned (gaps become empty cells)."""
    root = ET.fromstring(xml_bytes)
    rows: list[list[str]] = []
    for row in root.iter():
        if _local(row.tag) != "row":
            continue
        cells: dict[int, str] = {}
        running = 0
        for c in row:
            if _local(c.tag) != "c":
                continue
            col = _col_index(_attr_by_local(c, "r") or "")
            if col < 0:
                col = running
            running = col + 1
            text = _xlsx_cell_text(c, shared)
            if text:
                cells[col] = text
        if not cells:
            continue
        width = max(cells) + 1
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def _extract_xlsx(path: Path) -> str:
    """Per-sheet cell text under ``## Sheet: <name>`` headings, each row rendered as pipe-joined
    cells (a plain, model-readable grid — no exact geometry). Sheets are in workbook tab order;
    empty rows/sheets are dropped."""
    out: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = _xlsx_shared_strings(z, names)
        for sheet_name, part in _xlsx_sheet_order(z, names):
            if part not in names:
                continue
            rows = _xlsx_sheet_rows(z.read(part), shared)
            body = "\n".join(" | ".join(r).rstrip(" |") for r in rows if any(cell.strip() for cell in r)).strip()
            if body:
                out.append(f"## Sheet: {sheet_name}\n\n{body}")
    return "\n\n".join(out)
