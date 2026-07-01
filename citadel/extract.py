"""Zero-dependency text extraction for binary Office files (PowerPoint / Word).

A ``.pptx``/``.docx`` (and their macro-enabled ``.pptm``/``.docm`` siblings) is an Office Open
XML package — really a ZIP archive of XML parts — so the agentic CLI's file reader cannot open it
the way it opens a ``.md``/``.txt``/PDF. Rather than add a heavy dependency (``python-pptx`` /
``python-docx`` / ``markitdown``), this module pulls the text out with the standard library only
(``zipfile`` + ``xml.etree.ElementTree``), matching the project's KISS, no-extra-deps ethos.

``ingest`` uses it in two places (see :mod:`citadel.ingest`):

- :func:`is_office_source` (cheap: extension + ZIP magic) lets :func:`citadel.ingest._is_ingestible`
  treat an Office file as ingestible instead of rejecting it as a NUL-byte binary;
- :func:`extract_text` produces the plain text that ingest writes to a temp ``.md`` for the agent to
  read — while the wiki still cites the ORIGINAL Office file as its source.

Best-effort by design: it captures slide/shape/table/notes text (pptx) and paragraph/table text
(docx) — enough for fact ingestion — but not drawing-canvas SmartArt, embedded charts/objects, or
exact table geometry. Any parse/IO failure yields ``""`` (the caller then logs the file as
unreadable), never an exception that could break a run. Legacy binary ``.ppt``/``.doc`` (OLE, not
ZIP) are NOT supported and stay unreadable.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


# OOXML packages all start with the ZIP local-file-header magic. We gate on BOTH the extension and
# this magic so a plain ``.zip`` (or a renamed text file) is never mistaken for an Office document.
_ZIP_MAGIC = b"PK\x03\x04"
_OFFICE_EXTS = {".docx", ".docm", ".pptx", ".pptm"}
_WORD_EXTS = {".docx", ".docm"}
_PPT_EXTS = {".pptx", ".pptm"}


def is_office_source(path: Path | str) -> bool:
    """True if ``path`` is a PowerPoint/Word OOXML file we can extract text from: a supported
    extension AND the ZIP magic header. Cheap (reads 4 bytes) and never raises."""
    p = Path(path)
    if p.suffix.lower() not in _OFFICE_EXTS:
        return False
    try:
        with open(p, "rb") as fh:
            return fh.read(len(_ZIP_MAGIC)) == _ZIP_MAGIC
    except OSError:
        return False


def extract_text(path: Path | str) -> str:
    """Return the plain text of a ``.pptx``/``.pptm`` or ``.docx``/``.docm`` file, or ``""`` for an
    unsupported type or on ANY read/parse failure (so the caller can treat empty == unreadable).
    Never raises."""
    p = Path(path)
    ext = p.suffix.lower()
    try:
        if ext in _WORD_EXTS:
            return _normalize(_extract_docx(p))
        if ext in _PPT_EXTS:
            return _normalize(_extract_pptx(p))
    except Exception:  # noqa: BLE001 - contract is "never raises": a malformed/encrypted/odd file
        # must degrade to "" so candidate partitioning (`_is_ingestible`) and ingest never crash on
        # ONE bad file. zipfile/ET surface failures well beyond BadZipFile/ParseError — an encrypted
        # member raises RuntimeError, an unsupported compression method NotImplementedError, etc. —
        # so we catch broadly here (BaseException like Ctrl+C still propagates).
        return ""
    return ""


# --- internals --------------------------------------------------------------------------


def _local(tag: str) -> str:
    """Strip the ``{namespace}`` prefix ElementTree puts on every tag, leaving the local name
    (``{...wordprocessingml...}p`` -> ``p``), so we can match across the w:/a:/p: namespaces
    without hard-coding their URIs."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


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


def _normalize(text: str) -> str:
    """Trim trailing whitespace per line and collapse runs of 3+ blank lines to one, so the
    extracted markdown is tidy regardless of how the source spaced its paragraphs."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    joined = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()
