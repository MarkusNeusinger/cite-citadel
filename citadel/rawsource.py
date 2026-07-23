"""Read the raw SOURCE behind a citation — the offline "trust but verify" reader.

Given a source key as it appears in a ``[^sN]`` citation (e.g. ``raw/notes.md``) and, optionally, the
citation's locator tail (``lines 76-83`` / ``§ Method`` / a combined ``§ Method, lines 5-9``), return
the cited source's text or exactly the slice the locator names. This VERIFIES the synthesized wiki: it
resolves a fact's provenance so a reader can spot-check the passage a citation rests on. It is NOT a
retrieval path — the wiki is the synthesized, cited layer, so to *answer* questions use ``wiki_search``
/ ``wiki_read``; this only lets you confirm what a page already told you.

Two guardrails keep that boundary from eroding into bulk re-retrieval:

  1. **Provenance gate** — a key is readable only when it is a source the wiki actually cites (present
     in the manifest, or a ``docs/`` file — legal provenance that is never manifested) AND lies within
     a configured raw root / ``docs/``. "Read my filesystem" becomes "show me what the wiki cites".
  2. **Size cap** — the returned text is capped (a whole-file read of a huge source would nuke the
     client context); over the cap the reader truncates with a hint to narrow via a locator.

Lives OUTSIDE :mod:`citadel.store_core` on purpose: that module is the wiki 'database', and raw
sources are explicitly not the wiki. Depends only on :mod:`citadel.config` (path/roots),
:mod:`citadel.grammar` (containment + the shared locator parser), :mod:`citadel.manifest` (what the
wiki tracks), and :mod:`citadel.extract` (Office text).
"""

from __future__ import annotations

from pathlib import Path

from . import config, extract, grammar, manifest, transcribe


# Hard cap on returned characters. A whole-file read of a large source (pemberley's raw is ~730k
# chars) would swamp the client context and turn a spot-check into bulk re-retrieval — the boundary
# this tool exists to hold. A constant, not an env knob (mirroring the curate page-length limits).
MAX_CHARS = 20_000

# Paginated / opaque-binary source types with no offline text extraction: the ingest agent reads
# these directly (PDFs visually per CITADEL_PDF_MODE, images via vision). We name the file, not dump
# it — Office files are handled separately via extract.extract_text.
_NO_TEXT_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff", ".heic"}


class SourceError(Exception):
    """A cited source could not be read, located, or verified. The CLI/MCP surfaces map it to an exit
    code / error string — distinct from the raw text so 'not a cited source' and 'gone from disk' stay
    reportable (the mismatch is itself a verification result)."""


def raw_text(source_key: str, locator: str = "") -> str:
    """The text of a raw source the wiki cites, or the slice a citation ``locator`` names. ``locator``
    is the citation tail verbatim (``lines 76-83`` / ``§ Method`` / ``§ Method, lines 5-9``); empty =
    the whole source. Raises :class:`SourceError` (not a cited source / missing on disk / no offline
    text / locator out of range, naming a missing heading, or not offline-resolvable). Output is
    line-numbered and capped."""
    path = _resolve_and_gate(source_key)
    if not path.is_file():
        raise SourceError(f"'{source_key}' is cited by the wiki but is missing on disk")
    text = _read_text(source_key, path)
    lines = text.splitlines()
    tail = locator.strip()
    if not tail:
        return _render(source_key, lines, 1, len(lines))

    loc = grammar.parse_locator(tail)
    if loc.kind == "other":
        # A `p. 12` page locator (Office) or a garbled form — not resolvable offline. An ERROR,
        # like every other locator problem: silently dumping the whole (capped) source with a
        # header note gave a typo'd locator exit 0, which no script or MCP client could detect.
        raise SourceError(
            f"locator '{tail}' is not offline-resolvable — use 'lines A-B', '§ Heading', or "
            f"'§ Heading, lines A-B', or omit the locator to read the whole source"
        )
    if loc.heading is not None:
        span = _heading_span(text, loc.heading)
        if span is None:
            available = ", ".join("§ " + h for h in grammar.source_heading_texts(text)) or "none"
            raise SourceError(f"'§ {loc.heading}' is not a heading in '{source_key}' (headings present: {available})")
        if loc.start is None:  # heading-only: show the whole section
            return _render(source_key, lines, span[0] + 1, span[1])
    if loc.start is not None:  # a line range (pure, or the combined form's — heading already verified)
        if loc.start < 1 or loc.start > loc.end or loc.end > len(lines):
            raise SourceError(
                f"locator 'lines {loc.start}-{loc.end}' is out of range — '{source_key}' has {len(lines)} lines"
            )
        return _render(source_key, lines, loc.start, loc.end)
    return _render(source_key, lines, 1, len(lines))


def _resolve_and_gate(source_key: str) -> Path:
    """The provenance gate: the absolute path a cited ``source_key`` denotes, or raise
    :class:`SourceError`. A key passes only when it (a) lies within a configured raw root or
    ``config.DOCS_DIR`` — lexical containment via :func:`grammar.is_within`, the correct guard here
    (an absolute mounted-drive key is legal, so ``okf.safe_join`` would wrongly reject it) — AND (b) is
    a source the wiki tracks: present in the manifest, or under ``docs/`` (docs files are legal
    provenance but never manifested)."""
    path = config.source_path_for_key(source_key)
    roots = [*config.source_roots(), config.DOCS_DIR]
    if not any(grammar.is_within(path, root) for root in roots):
        raise SourceError(f"'{source_key}' is not under a configured raw/ or docs/ source root")
    under_docs = grammar.is_within(path, config.DOCS_DIR)
    if not under_docs and source_key not in manifest.load():
        raise SourceError(f"'{source_key}' is not a source the wiki cites (not in the ingest manifest)")
    return path


def _read_text(source_key: str, path: Path) -> str:
    """The source's plain text, or raise :class:`SourceError` for a type with no offline text. Office
    files go through :func:`extract.extract_text`; PDFs/images have no offline reader (the ingest agent
    reads them directly), so we name the file rather than dump it; other files are read as UTF-8, with
    a NUL byte treated as "binary"."""
    if extract.is_office_source(path):
        text = extract.extract_text(path)
        if not text:
            raise SourceError(f"'{source_key}' is an Office file whose text could not be extracted offline")
        return text
    ext = path.suffix.lower()
    if transcribe.is_audio_ext(path):
        cached = transcribe.cached_transcript(path)
        if cached is None:
            raise SourceError(
                f"'{source_key}' ({ext}) has no cached transcript on this machine — ingest it with "
                f"CITADEL_AUDIO_SUPPORT=1 to transcribe it; the file is at {config.rel_or_abs_posix(path)}"
            )
        return cached
    if ext in _NO_TEXT_EXTS:
        raise SourceError(
            f"'{source_key}' ({ext}) has no offline text extraction — the ingest agent reads it "
            f"directly; the file is at {config.rel_or_abs_posix(path)}"
        )
    try:
        data = path.read_bytes()
    except OSError as e:
        raise SourceError(f"could not read '{source_key}': {e}") from e
    if b"\x00" in data:
        raise SourceError(f"'{source_key}' is binary, not offline-readable as text")
    return data.decode("utf-8", errors="replace")


def _heading_span(text: str, heading: str) -> tuple[int, int] | None:
    """The 0-based ``(start, end)`` half-open line span of the section a ``§ Heading`` names — the
    heading line through the line before the next heading of the same or shallower level — or None
    when no such heading exists. Recognizes both ATX ``#`` headings and whole-line ``**bold**``
    headings via the shared :func:`grammar.parse_heading_line`, so a ``§`` locator into a FAQ /
    exported-doc section resolves. Fence-aware and candidate-tolerant (a trailing ``- description``
    is trimmed) via :func:`grammar.iter_lines` / :func:`grammar.heading_candidates`."""
    wanted = {c.lower() for c in grammar.heading_candidates(heading)}
    rows = list(grammar.iter_lines(text))
    start = level = None
    for i, (line, in_code) in enumerate(rows):
        if in_code:
            continue
        parsed = grammar.parse_heading_line(line)
        if parsed is None:
            continue
        this_level, htext = parsed
        if start is None:
            if htext.lower() in wanted:
                start, level = i, this_level
            continue
        if this_level <= level:
            return (start, i)
    return (start, len(rows)) if start is not None else None


def _render(source_key: str, lines: list[str], start: int, end: int) -> str:
    """Render lines ``start..end`` (1-based, inclusive) of a source, each prefixed with its real line
    number, under a header naming the source and range; capped at :data:`MAX_CHARS` with a
    narrow-with-a-locator hint when the slice is too large."""
    picked = lines[start - 1 : end]
    if not picked:  # an empty source (0 lines) — a valid header, never a `lines 1-0 of 0` range
        return f"{source_key} — empty source (0 lines)"
    width = len(str(end))
    header = f"{source_key} — lines {start}-{end} of {len(lines)}"
    body = "\n".join(f"{start + i:>{width}} | {line}" for i, line in enumerate(picked))
    out = f"{header}\n\n{body}"
    if len(out) > MAX_CHARS:
        clipped = out[:MAX_CHARS].rsplit("\n", 1)[0]
        return f"{clipped}\n… [truncated at {MAX_CHARS} chars — narrow with a `lines A-B` or `§ Heading` locator]"
    return out
