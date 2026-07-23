"""Whisper-CLI transcription for audio/video sources — the seam behind ``CITADEL_AUDIO_SUPPORT``.

An audio or video recording is the one large content class the coding-agent CLI cannot open, so
ingest shells out to a LOCAL whisper-class binary the user already has (exactly like the agent-CLI
seam in :mod:`citadel.llm` — no SDK, no API key): ``<file> --output_format srt --output_dir <tmp>``,
the openai-whisper flag convention that ``whisper-ctranslate2`` and ``mlx_whisper`` are drop-in
compatible with (whisper.cpp needs a one-line wrapper script). The resulting SRT is folded into
citadel's canonical transcript shape — one utterance per line, ``[HH:MM:SS] spoken text`` — and
cached CONTENT-ADDRESSED (by the source file's sha256) in a dotdir sibling of the wiki
(:func:`cache_dir`, next to the run lock and the staging copies, never inside the wiki where the
wikigit history layer would commit it). The cache is the point: transcription is minutes of CPU
per recording, so it runs at most once per content, survives failed/retried agent sessions, and —
because the agent session reads exactly this text while citing the ORIGINAL media file — it doubles
as the offline verification text: ``lint.check_locators`` and ``wiki_raw`` resolve a citation's
``lines A-B`` locator against the same cached transcript the facts were written from.

This module deliberately lives beside :mod:`citadel.extract` (Office text), not inside
:mod:`citadel.llm`: whisper is not an LLM, and ``llm.py`` stays the only place that talks to one.
Tests monkeypatch :func:`transcript_for` (the ingest seam) or ``subprocess.run`` (the shell-out);
no test spawns a real whisper binary.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from . import config, manifest


# Audio/video containers a whisper-class CLI (ffmpeg-backed) can transcribe. Recognized by
# extension AND magic bytes (mirroring ingest's image detector), so a renamed text file is never
# shelled out to whisper — it falls through to the normal text sniff instead.
AUDIO_EXTS = {
    ".mp3",
    ".wav",
    ".m4a",
    ".m4b",
    ".mp4",
    ".mov",
    ".mkv",
    ".webm",
    ".flac",
    ".ogg",
    ".oga",
    ".opus",
    ".aac",
    ".wma",
    ".mpga",
}

# The transcript cache: a dotdir SIBLING of the wiki (like the run lock and the staging copies) so
# it travels with the wiki — including a CITADEL_WIKI_DIR outside the workspace — but is never
# inside it (the wikigit history layer commits the wiki dir whole, and the per-source staging copy
# must not replicate a growing cache).
CACHE_DIR_NAME = ".citadel_transcripts"

# ISO-8601-ish SRT cue timing line: "00:01:02,500 --> 00:01:05,000" (comma or dot millis).
_SRT_TIMING_RE = re.compile(r"^(\d{1,2}:\d{2}:\d{2})[,.]\d{1,3}\s*-->")

# MP4-family container atom names accepted at byte offset 4 (m4a/m4b/mp4/mov start with a size-
# prefixed atom; `ftyp` leads almost always, the rest cover raw QuickTime captures).
_MP4_ATOMS = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip")


def is_audio_ext(path: Path) -> bool:
    """Pure extension membership in :data:`AUDIO_EXTS` — no config gate, no file IO. The check
    lint/``wiki_raw``/the viewer use to route a CITED source at its cached transcript (a citation
    stays servable even when ``CITADEL_AUDIO_SUPPORT`` was later turned off)."""
    return path.suffix.lower() in AUDIO_EXTS


def _looks_like_audio(head: bytes) -> bool:
    """True if ``head`` (the first bytes of a file) carries a common audio/video container magic:
    ID3/MPEG-sync (mp3/aac), RIFF/WAVE, fLaC, OggS, the MP4 atom family, EBML (mkv/webm), or ASF
    (wma). Cheap signature check so a text file renamed ``.mp3`` is not shelled out to whisper."""
    if head.startswith((b"ID3", b"fLaC", b"OggS", b"\x1a\x45\xdf\xa3")):
        return True
    if len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0:  # MPEG audio frame sync
        return True
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return True
    if head[4:8] in _MP4_ATOMS:
        return True
    return head.startswith(b"\x30\x26\xb2\x75\x8e\x66\xcf\x11")  # ASF (wma/wmv)


def is_audio_source(path: Path) -> bool:
    """True when audio ingestion is on (``config.AUDIO_SUPPORT``) and ``path`` is a recognized
    audio/video recording (extension AND matching magic). Such a source is transcribed through the
    whisper seam instead of being rejected by the binary sniff. Never raises."""
    if not config.AUDIO_SUPPORT or not is_audio_ext(path):
        return False
    try:
        with open(path, "rb") as fh:
            return _looks_like_audio(fh.read(16))
    except OSError:
        return False


def cache_dir() -> Path:
    """The transcript cache directory: a dotdir sibling of the wiki dir (read at call time so
    tests can monkeypatch the config layout — exactly like ``runlock.lock_path``)."""
    return Path(config.WIKI_DIR).parent / CACHE_DIR_NAME


def cache_path(sha: str) -> Path:
    """Where the transcript for a source with content hash ``sha`` lives — content-addressed, so
    a changed recording re-transcribes and an unchanged one never does."""
    return cache_dir() / f"{sha}.md"


def cached_transcript(path: Path, sha: str | None = None) -> str | None:
    """The cached transcript text for ``path``, or None when there is none to serve: never
    transcribed on this machine, the cache was deleted, the file itself is unreadable — or the
    cached transcript is EMPTY (whisper found no speech; there is nothing to verify against).
    ``sha`` skips the re-hash when the caller already knows the content hash. Never raises — the
    read-only consumers (lint, ``wiki_raw``, the viewer) degrade to "no offline text" instead."""
    if sha is None:
        try:
            sha = manifest.file_sha256(path)
        except OSError:
            return None
    try:
        text = cache_path(sha).read_text(encoding="utf-8")
    except OSError:
        return None
    return text if text.strip() else None


def resolve_whisper() -> str:
    """Return an executable path for the configured whisper-class CLI or raise a clear
    ``RuntimeError`` — the same PATH-name / absolute-path ladder as ``llm._resolve_cli``.
    ``CITADEL_WHISPER_CLI`` is both the selector and the override: a bare name is looked up on
    PATH, an absolute path is used directly."""
    binary = (config.WHISPER_CLI or "whisper").strip()
    path = shutil.which(binary)
    if path:
        return path
    if os.path.isabs(binary) and os.access(binary, os.X_OK):
        return binary
    raise RuntimeError(
        f"the whisper CLI {binary!r} was not found on PATH. Install one (openai-whisper, "
        f"whisper-ctranslate2, mlx_whisper - anything speaking the openai-whisper flags), or "
        f"point CITADEL_WHISPER_CLI at the binary, or set CITADEL_AUDIO_SUPPORT=0 to keep "
        f"audio/video files out of the wiki."
    )


def _parse_srt(srt: str) -> str:
    """Fold SRT cue blocks into citadel's canonical transcript shape: ONE utterance per line,
    ``[HH:MM:SS] spoken text`` (the cue's start time, milliseconds dropped; multi-line cue text
    joined with spaces). Index lines, timing lines, and empty/garbled blocks are consumed, never
    echoed — the result is exactly the text the agent reads and locators verify against."""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", srt.replace("\r\n", "\n").replace("\r", "\n")):
        lines = [ln.strip() for ln in block.strip().split("\n") if ln.strip()]
        if lines and lines[0].isdigit():
            lines = lines[1:]  # the SRT cue index
        if not lines:
            continue
        timing = _SRT_TIMING_RE.match(lines[0])
        if timing is None:
            continue
        text = " ".join(lines[1:]).strip()
        if text:
            out.append(f"[{timing.group(1)}] {text}")
    return "\n".join(out) + ("\n" if out else "")


def _run_whisper(src: Path) -> str:
    """Shell out to the whisper CLI for ``src`` and return the parsed transcript text (possibly
    empty — no speech). Raises ``RuntimeError`` with an actionable message on every failure mode
    (missing binary, non-zero exit, timeout, no output file) — the per-source ``prepare_error``
    surface ingest already records and retries."""
    cli_path = resolve_whisper()
    tmpdir = tempfile.mkdtemp(prefix="okf_whisper_")
    try:
        argv = [cli_path, str(src), "--output_format", "srt", "--output_dir", tmpdir]
        if config.WHISPER_MODEL:
            argv += ["--model", config.WHISPER_MODEL]
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                # Force UTF-8 regardless of the OS locale (cp1252 on German Windows);
                # errors="replace" keeps a stray undecodable byte from killing the run.
                encoding="utf-8",
                errors="replace",
                timeout=config.WHISPER_TIMEOUT,
                # DEVNULL, never the inherited stdin: a CLI that polls stdin (or the MCP stdio
                # pipe under `citadel serve`) gets immediate EOF instead of stalling.
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"the whisper CLI timed out after {config.WHISPER_TIMEOUT}s transcribing "
                f"{src.name} (raise CITADEL_WHISPER_TIMEOUT for long recordings)"
            ) from exc
        except OSError as exc:
            raise RuntimeError(f"failed to run the whisper CLI: {exc}") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()[:500]
            raise RuntimeError(f"the whisper CLI failed (exit {proc.returncode}): {detail}")
        srt = Path(tmpdir) / (src.stem + ".srt")
        if not srt.is_file():
            # openai-whisper names the output after the input stem; tolerate a CLI that mangles
            # the name as long as it wrote exactly one SRT where we asked.
            candidates = sorted(Path(tmpdir).glob("*.srt"))
            if len(candidates) != 1:
                raise RuntimeError(
                    f"the whisper CLI wrote no .srt into its --output_dir for {src.name} - "
                    f"it must speak the openai-whisper flag convention "
                    f"(`<file> --output_format srt --output_dir <dir>`)"
                )
            srt = candidates[0]
        try:
            return _parse_srt(srt.read_text(encoding="utf-8", errors="replace"))
        except OSError as exc:
            raise RuntimeError(f"could not read the whisper output for {src.name}: {exc}") from exc
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def transcript_for(src: Path, sha: str | None = None) -> str:
    """The transcript text for the audio/video source ``src`` — from the content-addressed cache
    when the same bytes were transcribed before, else by running the whisper CLI once and caching
    the result. THE ingest seam (monkeypatched by tests; the office analogue is
    ``extract.extract_text``). Raises ``RuntimeError`` when transcription fails OR yields no
    speech — ingest records it as a retryable per-source failure either way, and the cache makes
    the empty-transcript retry free (only a changed file re-runs whisper).

    The cache write is best-effort: a cache dir that cannot be written costs re-transcription next
    run and offline locator verification (lint/``wiki_raw`` read the cache), never the session."""
    if sha is None:
        sha = manifest.file_sha256(src)
    target = cache_path(sha)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        text = None
    if text is None:
        text = _run_whisper(src)
        try:
            config.robust_mkdir(cache_dir())
            config.atomic_write_text(target, text)
        except OSError:
            pass  # best-effort cache (see docstring); the session still gets the text in hand
    if not text.strip():
        raise RuntimeError(
            f"whisper produced an empty transcript for {src.name} (no recognizable speech?) - "
            f"delete {config.rel_or_abs_posix(cache_path(sha))} to force a re-transcription"
        )
    return text
