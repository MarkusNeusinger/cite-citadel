"""pypdf text-layer pre-pass for PDF sources — the seam behind ``CITADEL_PDF_TEXT``.

A PDF used to be the one text-bearing class whose locators were never offline-verifiable: the
agent read it directly and cited ``p. N`` page locators nobody but another agent could check.
This module closes that hole the way :mod:`citadel.transcribe` closed it for audio. ``pypdf`` is a
BUNDLED runtime dependency (PDFs are a common ``raw/`` class, so the offline-verifiable path is on
by default — pure-Python, BSD, no transitive deps; ``pip install cite-citadel[pdf]`` is a no-op
compat alias): ingest extracts the PDF's embedded text layer ONCE per content and the agent reads
that extraction — a ``[p. N]``-marked, line-stable text file — while citing the ORIGINAL ``.pdf``
as the source of record with ordinary ``lines A-B`` locators. The extraction is cached
CONTENT-ADDRESSED (by the source file's sha256) in a dotdir sibling of the wiki
(:func:`cache_dir`, next to ``.citadel_transcripts/``), so it doubles as the offline
verification text: ``lint.check_locators``, ``wiki_raw``, and the viewer resolve a citation's
``lines A-B`` against the same cached text the facts were written from.

Everything here is BEST-EFFORT by design — the pre-pass is an upgrade, never a gate:

- ``CITADEL_PDF_TEXT=0``, an encrypted/corrupt PDF, a scanned PDF with no text layer, or the
  unusual case of pypdf force-removed from the environment all yield ``None`` from
  :func:`text_for`, and ingest falls back to the pre-existing behavior (the agent opens the PDF
  itself; ``p. N`` locators, agent-verified).
- ``p. N`` page locators remain legal and agent-verified for the fallback path and for
  figure-only facts in ``CITADEL_PDF_MODE=images`` (a figure lives in pixels, not in the text
  layer).

Lives beside :mod:`citadel.extract` (Office text) and :mod:`citadel.transcribe` (whisper), not in
:mod:`citadel.llm`: pypdf is not an LLM, and ``llm.py`` stays the only place that talks to one.
Tests monkeypatch :func:`text_for` (the ingest seam) or seed the cache directly; the real pypdf
extraction is exercised offline against tiny hand-written PDFs (no network, no LLM).
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

from . import config, manifest


# The extraction cache: a dotdir SIBLING of the wiki (like ``.citadel_transcripts/`` and the run
# lock) so it travels with the wiki — including a CITADEL_WIKI_DIR outside the workspace — but is
# never inside it (the wikigit history layer commits the wiki dir whole, and the per-source
# staging copy must not replicate a growing cache).
CACHE_DIR_NAME = ".citadel_pdftext"

# Every page starts with this marker line in the extraction, so the page number a fact came from
# is readable IN the cited lines themselves (exactly like a transcript's [HH:MM:SS] stamps) —
# locators stay plain `lines A-B`, no new locator form.
PAGE_MARKER = "[p. {n}]"


def is_pdf_ext(path: Path) -> bool:
    """Pure ``.pdf`` extension check — no file IO. The cheap pre-filter for consumers that walk
    many paths; :func:`is_pdf_file` is the authoritative (magic) check."""
    return path.suffix.lower() == ".pdf"


def is_pdf_file(path: Path) -> bool:
    """True when ``path`` starts with the ``%PDF-`` magic — the SAME detection ingest uses
    (``_is_ingestible``), extension-independent, so a PDF renamed ``.txt`` routes identically
    everywhere and a text file renamed ``.pdf`` never does. Never raises."""
    try:
        with open(path, "rb") as fh:
            return fh.read(5) == b"%PDF-"
    except OSError:
        return False


def available() -> bool:
    """True when the (bundled) ``pypdf`` dependency is importable — normally always. Checked
    lazily and cheaply (``find_spec``, no import) so the seam degrades gracefully in the unusual
    case that pypdf was force-removed from the environment, rather than crashing on import."""
    try:
        return importlib.util.find_spec("pypdf") is not None
    except (ImportError, ValueError):  # a broken/half-uninstalled package must read as absent
        return False


def enabled() -> bool:
    """Whether the text-layer pre-pass is ON: ``CITADEL_PDF_TEXT=auto`` (the default) follows
    pypdf availability, ``1`` forces on (a missing pypdf then falls back per source, with a
    ``doctor`` warning), ``0`` forces off (agent-native PDF reading, the pre-pre-pass behavior)."""
    mode = config.PDF_TEXT
    if mode == "off":
        return False
    if mode == "on":
        return True
    return available()


def is_pdf_text_source(path: Path) -> bool:
    """True when the pre-pass is enabled and ``path`` is a genuine PDF — ingest's routing check
    (mirroring ``transcribe.is_audio_source``). Never raises."""
    return enabled() and is_pdf_file(path)


def cache_dir() -> Path:
    """The extraction cache directory: a dotdir sibling of the wiki dir (read at call time so
    tests can monkeypatch the config layout — exactly like ``transcribe.cache_dir``)."""
    return Path(config.WIKI_DIR).parent / CACHE_DIR_NAME


# A sha256 hexdigest and nothing else — the ONLY string shape allowed to become a cache filename
# (the same guard as transcribe's: a sha from PERSISTED data could have been hand-corrupted).
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def _valid_sha(sha: str | None) -> str | None:
    """``sha`` normalized to a lowercase sha256 hexdigest, or None when it is not one — a value
    carrying path separators must never reach :func:`cache_path`."""
    sha = (sha or "").strip().lower()
    return sha if _SHA256_RE.fullmatch(sha) else None


def cache_path(sha: str) -> Path:
    """Where the extraction for a source with content hash ``sha`` lives — content-addressed, so
    a changed PDF re-extracts and an unchanged one never does. Raises ``ValueError`` on anything
    that is not a sha256 hexdigest (defense in depth behind :func:`_valid_sha`)."""
    checked = _valid_sha(sha)
    if checked is None:
        raise ValueError(f"not a sha256 hexdigest: {sha!r}")
    return cache_dir() / f"{checked}.md"


def cached_text(path: Path, sha: str | None = None) -> str | None:
    """The cached text-layer extraction for ``path``, or None when there is none to serve: never
    extracted on this machine, the cache was deleted, the file itself is unreadable — or the
    cached extraction is EMPTY (a scanned PDF with no text layer; nothing to verify against).
    ``sha`` skips the re-hash when the caller already knows the content hash; a value that is not
    a sha256 hexdigest falls back to the safe re-hash. Never raises — the read-only consumers
    (lint, ``wiki_raw``, the viewer) degrade to "no offline text" instead."""
    sha = _valid_sha(sha)
    if sha is None:
        try:
            sha = manifest.file_sha256(path)
        except OSError:
            return None
    try:
        text = cache_path(sha).read_text(encoding="utf-8")
    except (OSError, UnicodeError):  # missing OR corrupted cache entry — nothing to serve
        return None
    return text if text.strip() else None


def prune_cached(sha: str | None) -> None:
    """Best-effort removal of the cache entry for ``sha`` — called by ingest when a PDF is
    DELETED from raw/ or its bytes CHANGED: the old extraction would otherwise sit orphaned
    forever, and it holds the document's content in plaintext (SECURITY.md). Never raises; a
    None/empty/non-hexdigest ``sha`` is a no-op."""
    sha = _valid_sha(sha)
    if sha is None:
        return
    try:
        cache_path(sha).unlink(missing_ok=True)
    except OSError:
        pass


def _extract(src: Path) -> str | None:
    """Extract ``src``'s embedded text layer with pypdf, in citadel's canonical shape — every
    page opens with its ``[p. N]`` marker line, followed by that page's text (lines
    trailing-stripped, newlines normalized), pages separated by one blank line. As long as ANY
    page has text, every page keeps its marker even when empty — so page numbering stays complete
    and an image-only page is visibly blank in the extraction (the gazette corpus grades this).

    Returns the extraction, or ``""`` when NO page yielded text at all (a fully scanned/image-only
    PDF — the cached file is then empty, no markers, and ``cached_text`` serves it as "nothing"),
    or None when pypdf is unavailable or the document cannot be parsed (encrypted without an empty
    password, corrupt). Both ``""`` and None mean "fall back to agent-native reading" for
    :func:`text_for`; the distinction is only that ``""`` is cached (a scanned PDF is not
    re-parsed every run) while None is not (a transient failure retries for free)."""
    if not available():
        return None
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(src))
        if reader.is_encrypted:
            # An empty user password is common (owner-locked PDFs); anything stronger → fallback.
            if not reader.decrypt(""):
                return None
        chunks: list[str] = []
        any_text = False
        for n, page in enumerate(reader.pages, 1):
            try:
                raw = page.extract_text() or ""
            except Exception:  # noqa: BLE001 - one malformed page must not sink the document
                raw = ""
            lines = [ln.rstrip() for ln in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
            while lines and not lines[-1]:
                lines.pop()
            while lines and not lines[0]:
                lines.pop(0)
            if lines:
                any_text = True
            chunks.append("\n".join([PAGE_MARKER.format(n=n), *lines]))
        if not chunks:
            return None  # a PDF with zero pages parses as nothing to read — fall back
        return ("\n\n".join(chunks) + "\n") if any_text else ""
    except Exception:  # noqa: BLE001 - pypdf raises a zoo of parse errors; all mean "fall back"
        return None


def text_for(src: Path, sha: str | None = None) -> str | None:
    """The text-layer extraction for the PDF source ``src`` — from the content-addressed cache
    when the same bytes were extracted before, else by running pypdf once and caching the result.
    THE ingest seam (monkeypatched by tests; the audio analogue is ``transcribe.transcript_for``).

    Returns None whenever there is no usable text layer to hand the agent — the document
    unparsable, the extraction empty (scanned pages), or the unusual case of pypdf force-removed
    from the environment — and ingest then falls back to the agent-native direct read. Unlike the audio seam this NEVER raises: a PDF is always
    agent-readable without us, so no failure here may cost a session. An empty extraction IS
    cached (so a scanned PDF is not re-parsed every run), but a parse failure is not (a
    transiently unreadable file retries for free next run). The cache write is best-effort: a
    cache dir that cannot be written costs re-extraction next run and offline locator
    verification (lint/``wiki_raw`` read the cache), never the session."""
    sha = _valid_sha(sha)
    if sha is None:
        try:
            sha = manifest.file_sha256(src)
        except OSError:
            return None
    target = cache_path(sha)
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError):  # missing OR corrupted cache entry: re-extract (overwrites)
        text = None
    if text is None:
        text = _extract(src)
        if text is None:
            return None
        try:
            config.robust_mkdir(cache_dir())
            config.atomic_write_text(target, text)
        except OSError:
            pass  # best-effort cache (see docstring); the session still gets the text in hand
    return text if text.strip() else None
