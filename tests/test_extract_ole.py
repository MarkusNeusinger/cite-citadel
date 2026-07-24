"""Offline tests for :mod:`citadel.extract_ole` — the lazy-import seam and the CFBF container.

Two concerns live here:

1. **The lazy-import seam** between :mod:`citadel.extract` and :mod:`citadel.extract_ole`: the
   OLE/CFBF salvage machinery is imported only when a legacy ``.doc``/``.ppt``/``.xls`` is
   actually dispatched — the common OOXML path (and a plain import of ``citadel.extract``) must
   never load it.

2. **The hand-rolled CFBF reader** (`_cfbf_streams` + the chain readers): the 2026-07 audit
   flagged this 222-line binary parser as the thinnest-covered risky surface in the repo — its
   only real exercise was the kontor corpus, which needs a live LLM run. The `_build_cfbf`
   fixture below is a spec-shaped MS-CFB *writer* (FAT, DIFAT chain, multi-sector directory,
   mini-FAT/mini-stream) so every container path — and the corruption guards — pin offline.

The plain salvage-text behavior (UTF-16/CP-1252 runs) stays covered by ``tests/test_extract.py``.
"""

from __future__ import annotations

import struct
import sys

import citadel
from citadel import extract, extract_ole


# --- lazy-import seam -------------------------------------------------------------------


def _forget_ole_module(monkeypatch) -> None:
    """Make the next ``from . import extract_ole`` a REAL import: scrub both places Python caches
    it — ``sys.modules`` and the attribute the first import bound on the ``citadel`` package (with
    the attribute in place, ``from . import`` resolves from it without touching ``sys.modules``)."""
    monkeypatch.delitem(sys.modules, "citadel.extract_ole", raising=False)
    monkeypatch.delattr(citadel, "extract_ole", raising=False)


def test_ooxml_path_never_imports_the_ole_module(tmp_path, monkeypatch, make_pptx):
    _forget_ole_module(monkeypatch)
    deck = tmp_path / "d.pptx"
    make_pptx(deck, [["Hello from OOXML"]])
    assert "Hello from OOXML" in extract.extract_text(deck)
    assert extract.is_office_source(deck)
    assert extract.extract_media(deck) == []
    assert "citadel.extract_ole" not in sys.modules


def test_legacy_ole_dispatch_imports_lazily_and_extracts(tmp_path, monkeypatch):
    _forget_ole_module(monkeypatch)
    fact = "Legacy body text from a Word 97 file"
    p = tmp_path / "old.doc"
    # OLE magic + a corrupt/short container: CFBF parse fails, whole-file salvage still recovers it.
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + fact.encode("utf-16-le") + b"\x00\x00")
    assert fact in extract.extract_text(p)
    assert "citadel.extract_ole" in sys.modules


# --- CFBF fixture writer ----------------------------------------------------------------

_SECTOR = 512
_MINI = 64
_ENDOFCHAIN = 0xFFFFFFFE
_FREESECT = 0xFFFFFFFF
_FATSECT = 0xFFFFFFFD
_DIFSECT = 0xFFFFFFFC
_MINI_CUTOFF = 4096


def _dir_entry(name: str, obj_type: int, start: int, size: int) -> bytes:
    e = bytearray(128)
    raw = name.encode("utf-16-le") + b"\x00\x00"
    e[0 : len(raw)] = raw
    struct.pack_into("<H", e, 64, len(raw))
    e[66] = obj_type
    struct.pack_into("<I", e, 116, start)
    struct.pack_into("<I", e, 120, size)
    return bytes(e)


def _build_cfbf(streams: dict[str, bytes], *, min_fat_sectors: int = 1, root: bool = True) -> bytes:
    """Build a spec-shaped CFBF v3 container (512-byte sectors) holding ``streams``.

    Streams smaller than the mini cutoff (4096) are stored through the mini-FAT/mini-stream
    machinery; larger ones through the main FAT. ``min_fat_sectors > 109`` forces the FAT sector
    list past the header's 109 DIFAT slots and into a DIFAT sector chain. ``root=False`` omits
    the root storage entry (a structurally broken but parseable container).

    Sector layout, in order: FAT sectors, DIFAT sectors, directory chain, mini-FAT sector,
    mini-stream chain, then each big stream's chain — all consecutively numbered, so callers can
    compute a sector's file offset for targeted corruption.
    """
    minis = {n: b for n, b in streams.items() if len(b) < _MINI_CUTOFF}
    bigs = {n: b for n, b in streams.items() if len(b) >= _MINI_CUTOFF}

    # Mini-stream: each mini stream padded to 64-byte mini sectors, concatenated.
    mini_bytes = bytearray()
    mini_starts: dict[str, int] = {}
    for name, payload in minis.items():
        if not payload:
            continue
        mini_starts[name] = len(mini_bytes) // _MINI
        n = (len(payload) + _MINI - 1) // _MINI
        mini_bytes += payload.ljust(n * _MINI, b"\x00")
    n_mini_container = (len(mini_bytes) + _SECTOR - 1) // _SECTOR
    n_minifat = 1 if mini_bytes else 0

    n_dir = ((1 + len(streams)) * 128 + _SECTOR - 1) // _SECTOR
    big_sectors = {n: (len(b) + _SECTOR - 1) // _SECTOR for n, b in bigs.items()}

    # Smallest FAT that indexes every sector in the file (fixed point over its own size).
    n_fat = max(1, min_fat_sectors)
    while True:
        n_difat = 0 if n_fat <= 109 else -(-(n_fat - 109) // (_SECTOR // 4 - 1))
        total = n_fat + n_difat + n_dir + n_minifat + n_mini_container + sum(big_sectors.values())
        if n_fat * (_SECTOR // 4) >= total:
            break
        n_fat += 1

    # Assign consecutive sector indices per the documented layout.
    cursor = n_fat + n_difat
    dir_start, cursor = cursor, cursor + n_dir
    minifat_start, cursor = (cursor, cursor + n_minifat) if n_minifat else (_ENDOFCHAIN, cursor)
    mini_start, cursor = (cursor, cursor + n_mini_container) if mini_bytes else (_ENDOFCHAIN, cursor)
    big_starts: dict[str, int] = {}
    for name, count in big_sectors.items():
        big_starts[name], cursor = cursor, cursor + count
    n_sectors = cursor

    fat = [_FREESECT] * (n_fat * (_SECTOR // 4))
    fat[0:n_fat] = [_FATSECT] * n_fat
    fat[n_fat : n_fat + n_difat] = [_DIFSECT] * n_difat

    def chain(start: int, count: int) -> None:
        for i in range(count):
            fat[start + i] = start + i + 1 if i < count - 1 else _ENDOFCHAIN

    chain(dir_start, n_dir)
    if n_minifat:
        chain(minifat_start, n_minifat)
    if mini_bytes:
        chain(mini_start, n_mini_container)
    for name, count in big_sectors.items():
        chain(big_starts[name], count)

    minifat = [_FREESECT] * (_SECTOR // 4)
    for name, payload in minis.items():
        if not payload:
            continue
        start = mini_starts[name]
        count = (len(payload) + _MINI - 1) // _MINI
        for i in range(count):
            minifat[start + i] = start + i + 1 if i < count - 1 else _ENDOFCHAIN

    directory = bytearray()
    if root:
        directory += _dir_entry("Root Entry", 5, mini_start, len(mini_bytes))
    for name, payload in streams.items():
        start = big_starts[name] if name in bigs else mini_starts.get(name, _ENDOFCHAIN)
        directory += _dir_entry(name, 2, start, len(payload))
    directory = directory.ljust(n_dir * _SECTOR, b"\x00")

    header = bytearray(_SECTOR)
    header[0:8] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
    struct.pack_into("<H", header, 24, 0x003E)  # minor version
    struct.pack_into("<H", header, 26, 3)  # major version 3 -> 512-byte sectors
    struct.pack_into("<H", header, 28, 0xFFFE)  # little-endian byte order
    struct.pack_into("<H", header, 30, 9)  # sector shift
    struct.pack_into("<H", header, 32, 6)  # mini sector shift
    struct.pack_into("<I", header, 44, n_fat)
    struct.pack_into("<I", header, 48, dir_start)
    struct.pack_into("<I", header, 56, _MINI_CUTOFF)
    struct.pack_into("<I", header, 60, minifat_start)
    struct.pack_into("<I", header, 64, n_minifat)
    struct.pack_into("<I", header, 68, n_fat if n_difat else _ENDOFCHAIN)
    struct.pack_into("<I", header, 72, n_difat)
    struct.pack_into("<109I", header, 76, *(list(range(min(109, n_fat))) + [_FREESECT] * max(0, 109 - n_fat)))

    difat_sectors = bytearray()
    if n_difat:
        per = _SECTOR // 4 - 1
        overflow = list(range(109, n_fat))
        for i in range(n_difat):
            block = overflow[i * per : (i + 1) * per]
            block += [_FREESECT] * (per - len(block))
            block.append(n_fat + i + 1 if i < n_difat - 1 else _ENDOFCHAIN)
            difat_sectors += struct.pack(f"<{per + 1}I", *block)

    body = bytearray(n_sectors * _SECTOR)
    fat_bytes = struct.pack(f"<{len(fat)}I", *fat)
    body[0 : len(fat_bytes)] = fat_bytes
    body[n_fat * _SECTOR : n_fat * _SECTOR + len(difat_sectors)] = difat_sectors
    body[dir_start * _SECTOR : dir_start * _SECTOR + len(directory)] = directory
    if n_minifat:
        mf = struct.pack(f"<{len(minifat)}I", *minifat)
        body[minifat_start * _SECTOR : minifat_start * _SECTOR + len(mf)] = mf
    if mini_bytes:
        body[mini_start * _SECTOR : mini_start * _SECTOR + len(mini_bytes)] = bytes(mini_bytes)
    for name, payload in bigs.items():
        off = big_starts[name] * _SECTOR
        body[off : off + len(payload)] = payload

    return bytes(header) + bytes(body)


_BINARY = bytes(range(256)) * 2  # 512 bytes of every value — proves chains never mangle bytes


# --- container round-trips --------------------------------------------------------------


def test_mini_stream_round_trips_exactly():
    payload = _BINARY + b"mini tail"  # < 4096 -> stored via mini-FAT + mini-stream
    streams = extract_ole._cfbf_streams(_build_cfbf({"WordDocument": payload}))
    assert streams["WordDocument"] == payload


def test_multi_sector_big_stream_round_trips_exactly():
    payload = (_BINARY * 12)[:5000]  # >= 4096 -> main FAT, spanning several 512-byte sectors
    streams = extract_ole._cfbf_streams(_build_cfbf({"Workbook": payload}))
    assert streams["Workbook"] == payload


def test_mixed_streams_and_multi_sector_directory():
    # 8 streams + root = 9 directory entries -> a 3-sector directory chain; mini and big mixed.
    wanted = {f"Stream{i}": (f"payload {i} " * 40).encode() for i in range(6)}
    wanted["Big"] = b"B" * 6000
    wanted["WordDocument"] = b"the actual document text " * 10
    streams = extract_ole._cfbf_streams(_build_cfbf(wanted))
    assert streams == wanted


def test_difat_chain_reaches_fat_sectors_past_the_header():
    # 110 FAT sectors: id #109 only exists in the DIFAT sector chain, never in the header's
    # 109 slots — a reader that ignores DIFAT sectors would lose part of the FAT.
    payload = b"difat-addressed document body " * 200  # big stream, lives late in the file
    data = _build_cfbf({"WordDocument": payload}, min_fat_sectors=110)
    streams = extract_ole._cfbf_streams(data)
    assert streams["WordDocument"] == payload


def test_zero_length_stream_is_skipped():
    streams = extract_ole._cfbf_streams(_build_cfbf({"Empty": b"", "WordDocument": b"text " * 20}))
    assert "Empty" not in streams
    assert "WordDocument" in streams


# --- extension -> main-stream dispatch --------------------------------------------------


def test_xls_prefers_workbook_but_accepts_biff5_book(tmp_path):
    both = tmp_path / "both.xls"
    both.write_bytes(_build_cfbf({"Book": b"OLD BIFF5 LEDGER ROWS", "Workbook": b"BIFF8 LEDGER ROWS"}))
    assert "BIFF8 LEDGER ROWS" in extract_ole.extract_ole_text(both)
    assert "OLD BIFF5" not in extract_ole.extract_ole_text(both)

    old = tmp_path / "old.xls"
    old.write_bytes(_build_cfbf({"Book": b"OLD BIFF5 LEDGER ROWS"}))
    assert "OLD BIFF5 LEDGER ROWS" in extract_ole.extract_ole_text(old)


def test_ppt_reads_the_powerpoint_document_stream(tmp_path):
    p = tmp_path / "deck.ppt"
    body = "Slide one: shipping plan".encode("utf-16-le")
    p.write_bytes(_build_cfbf({"PowerPoint Document": body, "Noise": b"IGNORED SIDE STREAM"}))
    text = extract_ole.extract_ole_text(p)
    assert "Slide one: shipping plan" in text
    assert "IGNORED SIDE STREAM" not in text


def test_parseable_container_without_the_main_stream_salvages_whole_file(tmp_path):
    # A valid container whose streams don't include the extension's main stream: the reader finds
    # nothing to isolate, so extraction degrades to whole-file salvage — the side stream's text is
    # still recovered rather than lost.
    p = tmp_path / "odd.doc"
    p.write_bytes(_build_cfbf({"SummaryInformation": b"salvaged side text anyway"}))
    assert "salvaged side text anyway" in extract_ole.extract_ole_text(p)


# --- corruption guards ------------------------------------------------------------------


def _patch_fat(data: bytes, sector: int, value: int) -> bytes:
    """Rewrite one FAT entry of a `_build_cfbf` container (FAT starts at sector 0 = offset 512)."""
    buf = bytearray(data)
    struct.pack_into("<I", buf, _SECTOR + sector * 4, value)
    return bytes(buf)


def _stream_start(data: bytes) -> int:
    """The start sector of the first type-2 stream, read from the directory like the parser does."""
    dir_start = struct.unpack_from("<I", data, 48)[0]
    off = _SECTOR + dir_start * _SECTOR
    for entry in range(4):
        base = off + entry * 128
        if data[base + 66] == 2:
            return struct.unpack_from("<I", data, base + 116)[0]
    raise AssertionError("no stream entry in the first directory sector")


def test_fat_cycle_terminates_instead_of_hanging():
    payload = b"cycle-start marker text " * 300  # several sectors
    data = _build_cfbf({"WordDocument": payload})
    start = _stream_start(data)
    data = _patch_fat(data, start + 1, start)  # second sector points back at the first
    streams = extract_ole._cfbf_streams(data)  # must return, not loop forever
    # The visited-guard truncates the chain; whatever was read is a clean prefix of the payload.
    assert streams["WordDocument"] == payload[: len(streams["WordDocument"])]
    assert streams["WordDocument"].startswith(b"cycle-start marker text ")


def test_mini_fat_cycle_terminates_instead_of_hanging():
    payload = b"mini cycle payload " * 30  # < 4096, several 64-byte mini sectors
    data = _build_cfbf({"WordDocument": payload})
    # Patch the first mini-FAT entry into a self-loop (mini-FAT sector offset from the header).
    minifat_start = struct.unpack_from("<I", data, 60)[0]
    buf = bytearray(data)
    struct.pack_into("<I", buf, _SECTOR + minifat_start * _SECTOR, 0)
    streams = extract_ole._cfbf_streams(bytes(buf))
    assert streams["WordDocument"] == payload[: len(streams["WordDocument"])]


def test_chain_pointing_past_the_file_falls_back_to_whole_file_salvage(tmp_path):
    # A FAT entry naming a sector the file doesn't contain makes the container parse raise
    # ("sector out of range"), so extraction degrades to whole-file salvage — never a crash.
    fact = "chain-end marker sentence"
    payload = (fact + " ").encode("utf-16-le") * 100
    data = _build_cfbf({"WordDocument": payload})
    data = _patch_fat(data, _stream_start(data) + 1, 10_000_000)
    p = tmp_path / "wild.doc"
    p.write_bytes(data)
    assert fact in extract_ole.extract_ole_text(p)


def test_truncated_container_falls_back_to_whole_file_salvage(tmp_path):
    fact = "Survivor sentence near the front of the stream"
    payload = (fact + " ").encode("utf-16-le") * 40
    whole = _build_cfbf({"WordDocument": payload})
    p = tmp_path / "cut.doc"
    p.write_bytes(whole[: len(whole) - _SECTOR])  # last stream sector gone -> "sector out of range"
    assert fact in extract_ole.extract_ole_text(p)  # container parse fails, salvage still delivers


def test_bad_sector_shift_falls_back_to_whole_file_salvage(tmp_path):
    fact = "Readable despite the broken header"
    data = bytearray(_build_cfbf({"WordDocument": fact.encode("utf-16-le")}))
    struct.pack_into("<H", data, 30, 0)  # sector shift 0 -> sector size 1 -> reader refuses
    p = tmp_path / "bad.doc"
    p.write_bytes(bytes(data))
    assert fact in extract_ole.extract_ole_text(p)


def test_rootless_container_yields_empty_not_crash(tmp_path):
    # A mini-sized stream needs the root storage's mini-stream; without a root entry the reader
    # has nothing to read from — best-effort means empty text, never an exception.
    p = tmp_path / "noroot.doc"
    p.write_bytes(_build_cfbf({"WordDocument": b"unreachable mini text"}, root=False))
    assert extract_ole.extract_ole_text(p) == ""
