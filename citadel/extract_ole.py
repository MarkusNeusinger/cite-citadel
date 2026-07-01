"""Best-effort text salvage for legacy OLE2 Office files (``.doc``/``.ppt``/``.xls``, Office 97-2003).

A ``.doc``/``.ppt``/``.xls`` from Office 97-2003 is a "compound file" — a mini-filesystem of named
binary streams inside one file. There is no stdlib parser, and a faithful per-format decoder
(Word piece tables, Excel BIFF records, PowerPoint atoms) is a large, fragile surface we cannot
validate offline. Instead we do the pragmatic, robust thing: parse the container enough to isolate
the document's MAIN stream, then salvage the readable UTF-16LE / CP-1252 text runs from it. If the
container can't be parsed we salvage the whole file. Best-effort by design.

This module is imported LAZILY by :mod:`citadel.extract` — only when a legacy OLE file is actually
dispatched — so the common OOXML path never pays for the CFBF machinery. The ``extract_text``
never-raises contract is upheld by that caller: :func:`extract_ole_text` runs inside its broad
``except Exception`` (so an unreadable file still degrades to ``""``), while within this module a
malformed *container* already degrades to whole-file salvage rather than an error.
"""

from __future__ import annotations

import re
import struct
from pathlib import Path

from .extract import _OLE_MAGIC


# The named stream that holds each legacy format's document text.
_OLE_MAIN_STREAMS = {
    ".doc": ("WordDocument",),
    ".ppt": ("PowerPoint Document",),
    ".xls": ("Workbook", "Book"),  # BIFF8 uses "Workbook"; BIFF5/7 used "Book"
}

# CFBF sector-chain sentinels.
_END_OF_CHAIN = 0xFFFFFFFE
_FREE_SECT = 0xFFFFFFFF

# Byte values that count as readable text when salvaging (printable ASCII + common whitespace +
# the Latin-1 supplement, skipping the C1 control range 0x7F-0xA0).
_SALVAGE_OK = frozenset({0x09, 0x0A, 0x0D} | set(range(0x20, 0x7F)) | set(range(0xA1, 0x100)))


def extract_ole_text(path: Path) -> str:
    """Best-effort text of a legacy ``.doc``/``.ppt``/``.xls``: salvage the readable runs from the
    document's main OLE stream (or the whole file if the container won't parse)."""
    data = path.read_bytes()
    stream = _ole_main_stream(data, path.suffix.lower())
    return _salvage_text(stream if stream is not None else data)


def _ole_main_stream(data: bytes, ext: str) -> bytes | None:
    """The bytes of the document's main stream (WordDocument / PowerPoint Document / Workbook), read
    out of the OLE2 container, or None if the container can't be parsed or the stream isn't found."""
    try:
        streams = _cfbf_streams(data)
    except Exception:  # noqa: BLE001 - a malformed container degrades to whole-file salvage.
        return None
    for name in _OLE_MAIN_STREAMS.get(ext, ()):
        if name in streams:
            return streams[name]
    return None


def _cfbf_streams(data: bytes) -> dict[str, bytes]:
    """Parse a Compound File Binary Format (OLE2) container and return ``{stream_name: bytes}`` for
    its non-empty streams. Implements just enough of MS-CFB — DIFAT/FAT/mini-FAT chains and the
    directory — to read stream contents; raises on any structural problem (caller falls back)."""
    if data[:8] != _OLE_MAGIC:
        raise ValueError("not an OLE2 compound file")
    sector_size = 1 << struct.unpack_from("<H", data, 30)[0]
    mini_sector_size = 1 << struct.unpack_from("<H", data, 32)[0]
    num_fat_sectors = struct.unpack_from("<I", data, 44)[0]
    first_dir_sector = struct.unpack_from("<I", data, 48)[0]
    mini_cutoff = struct.unpack_from("<I", data, 56)[0]
    first_minifat_sector = struct.unpack_from("<I", data, 60)[0]
    num_minifat_sectors = struct.unpack_from("<I", data, 64)[0]
    first_difat_sector = struct.unpack_from("<I", data, 68)[0]
    num_difat_sectors = struct.unpack_from("<I", data, 72)[0]
    if sector_size < 512 or mini_sector_size < 1:
        raise ValueError("bad sector size")

    def sector_bytes(idx: int) -> bytes:
        start = 512 + idx * sector_size
        chunk = data[start : start + sector_size]
        if len(chunk) < sector_size:
            raise ValueError("sector out of range")
        return chunk

    # DIFAT: 109 entries in the header, then a chain of DIFAT sectors (last uint32 = next sector).
    difat: list[int] = list(struct.unpack_from("<109I", data, 76))
    sec = first_difat_sector
    per_difat = sector_size // 4 - 1
    for _ in range(num_difat_sectors):
        if sec in (_END_OF_CHAIN, _FREE_SECT):
            break
        raw = sector_bytes(sec)
        difat.extend(struct.unpack_from(f"<{per_difat}I", raw, 0))
        sec = struct.unpack_from("<I", raw, per_difat * 4)[0]
    fat_sectors = [s for s in difat[:num_fat_sectors] if s not in (_END_OF_CHAIN, _FREE_SECT)]

    # FAT: the concatenation of the FAT sectors, one uint32 "next sector" per entry.
    fat: list[int] = []
    for s in fat_sectors:
        fat.extend(struct.unpack_from(f"<{sector_size // 4}I", sector_bytes(s), 0))

    def read_chain(start: int, size: int | None = None) -> bytes:
        out = bytearray()
        sec = start
        visited: set[int] = set()  # follow the chain, stopping on end/free OR a cycle (corrupt file)
        while sec not in (_END_OF_CHAIN, _FREE_SECT) and sec not in visited:
            visited.add(sec)
            out += sector_bytes(sec)
            sec = fat[sec] if sec < len(fat) else _END_OF_CHAIN
        return bytes(out[:size]) if size is not None else bytes(out)

    # Directory chain -> entries. Entry: name (64B UTF-16LE), name len (u16@64), type (byte@66),
    # start sector (u32@116), stream size (u32@120, low dword is enough for v3/v4 real files).
    dir_bytes = read_chain(first_dir_sector)
    entries: list[tuple[str, int, int, int]] = []  # (name, type, start, size)
    for off in range(0, len(dir_bytes) - 127, 128):
        name_len = struct.unpack_from("<H", dir_bytes, off + 64)[0]
        obj_type = dir_bytes[off + 66]
        if obj_type == 0 or name_len < 2:
            continue
        name = dir_bytes[off : off + max(0, name_len - 2)].decode("utf-16-le", "replace")
        start = struct.unpack_from("<I", dir_bytes, off + 116)[0]
        size = struct.unpack_from("<I", dir_bytes, off + 120)[0]
        entries.append((name, obj_type, start, size))

    # The root storage entry (type 5) holds the mini-stream (all streams smaller than mini_cutoff).
    root = next((e for e in entries if e[1] == 5), None)
    mini_stream = read_chain(root[2], root[3]) if root else b""

    # Mini-FAT: like the FAT but for the mini-stream's small sectors.
    minifat: list[int] = []
    sec = first_minifat_sector
    for _ in range(num_minifat_sectors):
        if sec in (_END_OF_CHAIN, _FREE_SECT):
            break
        minifat.extend(struct.unpack_from(f"<{sector_size // 4}I", sector_bytes(sec), 0))
        sec = fat[sec] if sec < len(fat) else _END_OF_CHAIN

    def read_mini_chain(start: int, size: int) -> bytes:
        out = bytearray()
        sec = start
        visited: set[int] = set()  # stop on end/free OR a cycle, so a corrupt mini-FAT can't loop
        while sec not in (_END_OF_CHAIN, _FREE_SECT) and sec not in visited:
            visited.add(sec)
            begin = sec * mini_sector_size
            out += mini_stream[begin : begin + mini_sector_size]
            sec = minifat[sec] if sec < len(minifat) else _END_OF_CHAIN
        return bytes(out[:size])

    streams: dict[str, bytes] = {}
    for name, obj_type, start, size in entries:
        if obj_type != 2 or size == 0:  # streams only
            continue
        streams[name] = read_mini_chain(start, size) if size < mini_cutoff else read_chain(start, size)
    return streams


def _salvage_text(data: bytes) -> str:
    """Recover readable text from binary ``data``: first the UTF-16LE printable runs (Word/most
    modern OLE text is UTF-16), then the single-byte (CP-1252) runs in the bytes not already claimed
    by a UTF-16 run. Runs are kept only when reasonably word-like, then joined one per line."""
    consumed = bytearray(len(data))
    runs = _utf16le_runs(data, consumed) + _singlebyte_runs(data, consumed)
    kept = [r for r in (_clean_run(r) for r in runs) if r]
    return "\n".join(kept)


def _is_salvage_char(b: int) -> bool:
    return b in _SALVAGE_OK


def _utf16le_runs(data: bytes, consumed: bytearray, min_chars: int = 3) -> list[str]:
    """Even-aligned UTF-16LE runs of printable BMP-Latin characters (low byte printable, high byte
    0). Marks the bytes it consumes so the single-byte pass won't double-count them."""
    out: list[str] = []
    i = 0
    n = len(data)
    while i < n - 1:
        if data[i + 1] == 0 and _is_salvage_char(data[i]):
            j = i
            chars: list[str] = []
            while j < n - 1 and data[j + 1] == 0 and _is_salvage_char(data[j]):
                chars.append(chr(data[j]))
                j += 2
            if len(chars) >= min_chars:
                out.append("".join(chars))
                for k in range(i, j):
                    consumed[k] = 1
            i = j if j > i else i + 2
        else:
            i += 1
    return out


def _singlebyte_runs(data: bytes, consumed: bytearray, min_chars: int = 4) -> list[str]:
    """CP-1252 runs of printable bytes, skipping bytes already claimed by a UTF-16LE run. A slightly
    longer minimum than the UTF-16 pass, since single-byte binary noise is more likely to be
    coincidentally printable."""
    out: list[str] = []
    cur = bytearray()
    for i, b in enumerate(data):
        if not consumed[i] and _is_salvage_char(b):
            cur.append(b)
        else:
            if len(cur) >= min_chars:
                out.append(cur.decode("cp1252", "replace"))
            cur = bytearray()
    if len(cur) >= min_chars:
        out.append(cur.decode("cp1252", "replace"))
    return out


def _clean_run(run: str) -> str:
    """Tidy one salvaged run and drop it (return "") when it carries no word-like content — a run
    with no alphanumeric character is structural noise, not text."""
    text = re.sub(r"[ \t\r\n]+", " ", run).strip()
    if not any(ch.isalnum() for ch in text):
        return ""
    return text
