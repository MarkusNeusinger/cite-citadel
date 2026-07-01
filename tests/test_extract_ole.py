"""Pins the lazy-import seam between :mod:`citadel.extract` and :mod:`citadel.extract_ole`.

The OLE/CFBF salvage machinery lives in its own module and is imported only when a legacy
``.doc``/``.ppt``/``.xls`` is actually dispatched — the common OOXML path (and a plain import of
``citadel.extract``) must never load it. The salvage behavior itself is covered by
``tests/test_extract.py``, which imports :mod:`citadel.extract_ole` directly.
"""

from __future__ import annotations

import sys

import citadel
from citadel import extract


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
