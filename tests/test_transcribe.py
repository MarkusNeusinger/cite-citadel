"""Unit tests for citadel.transcribe — the whisper-CLI seam behind CITADEL_AUDIO_SUPPORT.

All offline: the whisper shell-out is exercised under a monkeypatched ``subprocess.run`` (the
test_llm _FakeProc pattern) and binary resolution under a monkeypatched ``shutil.which`` — no test
spawns a real whisper. The content-addressed cache lands under the ``tmp_citadel`` layout
(a dotdir sibling of the wiki, ``<root>/.citadel_transcripts``).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from citadel import config, transcribe


def _make_mp3(path: Path, tail: bytes = b"\x00\x01\xff\xfbfake-mp3-frames") -> None:
    """A file that passes the audio magic sniff (ID3 header) and — like a real MP3 — is not
    valid UTF-8 (the 0xFF byte), so no consumer can mistake it for text."""
    path.write_bytes(b"ID3\x03\x00" + tail)


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- detection: extension + magic, gated by the knob -------------------------------------


def test_is_audio_ext_is_pure_extension_membership(tmp_path):
    assert transcribe.is_audio_ext(Path("a/memo.MP3"))
    assert transcribe.is_audio_ext(Path("clip.webm"))
    assert not transcribe.is_audio_ext(Path("notes.md"))
    assert not transcribe.is_audio_ext(Path("deck.pptx"))


@pytest.mark.parametrize(
    ("name", "head"),
    [
        ("a.mp3", b"ID3\x04\x00rest"),
        ("a.mp3", b"\xff\xfb\x90\x00frames"),  # raw MPEG frame sync
        ("a.wav", b"RIFF\x24\x08\x00\x00WAVEfmt "),
        ("a.flac", b"fLaC\x00\x00\x00\x22"),
        ("a.ogg", b"OggS\x00\x02junk"),
        ("a.opus", b"OggS\x00\x02junk"),
        ("a.m4a", b"\x00\x00\x00\x20ftypM4A "),
        ("a.mp4", b"\x00\x00\x00\x18ftypisom"),
        ("a.mkv", b"\x1a\x45\xdf\xa3junk"),
        ("a.wma", b"\x30\x26\xb2\x75\x8e\x66\xcf\x11rest"),
    ],
)
def test_is_audio_source_recognizes_common_containers(tmp_path, monkeypatch, name, head):
    monkeypatch.setattr(config, "AUDIO_SUPPORT", True)
    f = tmp_path / name
    f.write_bytes(head + b"\x00" * 32)
    assert transcribe.is_audio_source(f)


def test_is_audio_source_gate_and_magic(tmp_path, monkeypatch):
    f = tmp_path / "memo.mp3"
    _make_mp3(f)
    # Knob off -> never audio, regardless of content.
    monkeypatch.setattr(config, "AUDIO_SUPPORT", False)
    assert not transcribe.is_audio_source(f)
    # Knob on -> recognized.
    monkeypatch.setattr(config, "AUDIO_SUPPORT", True)
    assert transcribe.is_audio_source(f)
    # A text file renamed .mp3 fails the magic sniff (falls through to the normal text path).
    renamed = tmp_path / "notes.mp3"
    renamed.write_text("just text\n", encoding="utf-8")
    assert not transcribe.is_audio_source(renamed)
    # A missing file never raises.
    assert not transcribe.is_audio_source(tmp_path / "gone.mp3")


# --- binary resolution -------------------------------------------------------------------


def test_resolve_whisper_via_path_lookup(monkeypatch):
    monkeypatch.setattr(config, "WHISPER_CLI", "whisper")
    monkeypatch.setattr(transcribe.shutil, "which", lambda b: "/opt/bin/whisper" if b == "whisper" else None)
    assert transcribe.resolve_whisper() == "/opt/bin/whisper"


def test_resolve_whisper_accepts_absolute_executable(monkeypatch, tmp_path):
    binary = tmp_path / "my-whisper"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)
    monkeypatch.setattr(config, "WHISPER_CLI", str(binary))
    monkeypatch.setattr(transcribe.shutil, "which", lambda b: None)
    assert transcribe.resolve_whisper() == str(binary)


def test_resolve_whisper_missing_names_the_fixes(monkeypatch):
    monkeypatch.setattr(config, "WHISPER_CLI", "whisper")
    monkeypatch.setattr(transcribe.shutil, "which", lambda b: None)
    with pytest.raises(RuntimeError, match="CITADEL_WHISPER_CLI"):
        transcribe.resolve_whisper()


# --- SRT parsing -------------------------------------------------------------------------


def test_parse_srt_folds_cues_to_stamped_lines():
    srt = (
        "1\n00:00:01,000 --> 00:00:04,000\nHello there.\n\n"
        "2\n00:00:05.500 --> 00:00:09.000\nSecond cue,\nwrapped over two lines.\n\n"
        "not-a-cue garbage block\n\n"
        "3\n00:12:34,000 --> 00:12:35,000\n\n"  # empty text -> dropped
    )
    out = transcribe._parse_srt(srt)
    assert out == "[00:00:01] Hello there.\n[00:00:05] Second cue, wrapped over two lines.\n"


def test_parse_srt_handles_crlf_and_empty():
    assert transcribe._parse_srt("") == ""
    out = transcribe._parse_srt("1\r\n00:00:01,000 --> 00:00:02,000\r\nCRLF text.\r\n\r\n")
    assert out == "[00:00:01] CRLF text.\n"


# --- the shell-out -----------------------------------------------------------------------


def _install_fake_run(monkeypatch, seen, srt_text="1\n00:00:01,000 --> 00:00:02,000\nHi.\n\n", *, stem=None):
    """Fake subprocess.run that records argv and writes the SRT where --output_dir points."""
    monkeypatch.setattr(transcribe, "resolve_whisper", lambda: "/opt/bin/whisper")

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        outdir = Path(argv[argv.index("--output_dir") + 1])
        name = (stem if stem is not None else Path(argv[1]).stem) + ".srt"
        (outdir / name).write_text(srt_text, encoding="utf-8")
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)


def test_run_whisper_builds_openai_whisper_argv(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    seen: dict = {}
    _install_fake_run(monkeypatch, seen)
    monkeypatch.setattr(config, "WHISPER_MODEL", "")

    text = transcribe._run_whisper(src)

    assert text == "[00:00:01] Hi.\n"
    argv = seen["argv"]
    assert argv[0] == "/opt/bin/whisper" and argv[1] == str(src)
    assert argv[2:] == ["--output_format", "srt", "--output_dir", argv[argv.index("--output_dir") + 1]]
    assert "--model" not in argv  # empty knob -> the CLI's own default
    assert seen["kwargs"]["timeout"] == config.WHISPER_TIMEOUT
    assert seen["kwargs"]["stdin"] is subprocess.DEVNULL
    # The whisper temp output dir is cleaned up.
    assert not Path(argv[argv.index("--output_dir") + 1]).exists()


def test_run_whisper_passes_configured_model(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    seen: dict = {}
    _install_fake_run(monkeypatch, seen)
    monkeypatch.setattr(config, "WHISPER_MODEL", "turbo")
    transcribe._run_whisper(src)
    argv = seen["argv"]
    assert argv[argv.index("--model") + 1] == "turbo"


def test_run_whisper_tolerates_a_mangled_output_name(tmp_citadel, monkeypatch):
    """A CLI that renames the output is tolerated as long as exactly ONE .srt landed in the dir."""
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    seen: dict = {}
    _install_fake_run(monkeypatch, seen, stem="weird-name")
    assert transcribe._run_whisper(src) == "[00:00:01] Hi.\n"


def test_run_whisper_nonzero_exit_raises(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    monkeypatch.setattr(transcribe, "resolve_whisper", lambda: "/opt/bin/whisper")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(returncode=2, stderr="model not found"))
    with pytest.raises(RuntimeError, match="exit 2.*model not found"):
        transcribe._run_whisper(src)


def test_run_whisper_timeout_raises_actionable(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    monkeypatch.setattr(transcribe, "resolve_whisper", lambda: "/opt/bin/whisper")

    def fake_run(argv, **kwargs):
        raise subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="timed out.*CITADEL_WHISPER_TIMEOUT"):
        transcribe._run_whisper(src)


def test_run_whisper_oserror_raises_runtimeerror(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    monkeypatch.setattr(transcribe, "resolve_whisper", lambda: "/opt/bin/whisper")

    def fake_run(argv, **kwargs):
        raise OSError("exec format error")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="failed to run the whisper CLI"):
        transcribe._run_whisper(src)


def test_run_whisper_missing_output_raises(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    monkeypatch.setattr(transcribe, "resolve_whisper", lambda: "/opt/bin/whisper")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc())  # exits 0, writes nothing
    with pytest.raises(RuntimeError, match="no \\.srt"):
        transcribe._run_whisper(src)


# --- the content-addressed cache ---------------------------------------------------------


def test_transcript_for_caches_by_content_and_never_reruns(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    calls = {"n": 0}

    def fake_whisper(path):
        calls["n"] += 1
        return "[00:00:01] Cached hello.\n"

    monkeypatch.setattr(transcribe, "_run_whisper", fake_whisper)

    text = transcribe.transcript_for(src)
    assert text == "[00:00:01] Cached hello.\n"
    assert calls["n"] == 1
    cache_files = list(transcribe.cache_dir().glob("*.md"))
    assert len(cache_files) == 1  # content-addressed cache entry written

    # Second call: served from cache — whisper never runs again for the same bytes.
    assert transcribe.transcript_for(src) == text
    assert calls["n"] == 1
    # cached_transcript (the lint/wiki_raw entry point) serves the same text.
    assert transcribe.cached_transcript(src) == text


def test_transcript_for_empty_result_is_cached_and_raises(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "silent.mp3"
    _make_mp3(src)
    calls = {"n": 0}

    def fake_whisper(path):
        calls["n"] += 1
        return ""

    monkeypatch.setattr(transcribe, "_run_whisper", fake_whisper)

    with pytest.raises(RuntimeError, match="empty transcript"):
        transcribe.transcript_for(src)
    # The empty result IS cached, so the retry fails fast without re-running whisper …
    with pytest.raises(RuntimeError, match="empty transcript"):
        transcribe.transcript_for(src)
    assert calls["n"] == 1
    # … and there is nothing to verify against for lint/wiki_raw.
    assert transcribe.cached_transcript(src) is None


def test_transcript_for_cache_write_failure_is_best_effort(tmp_citadel, monkeypatch):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    monkeypatch.setattr(transcribe, "_run_whisper", lambda p: "[00:00:01] Still delivered.\n")

    def broken_write(path, text, attempts=4):
        raise OSError("read-only cache dir")

    monkeypatch.setattr(config, "atomic_write_text", broken_write)
    # The session still gets the transcript in hand; only the cache is lost.
    assert transcribe.transcript_for(src) == "[00:00:01] Still delivered.\n"
    assert transcribe.cached_transcript(src) is None


def test_cached_transcript_none_without_cache_or_file(tmp_citadel):
    src = tmp_citadel.raw / "memo.mp3"
    _make_mp3(src)
    assert transcribe.cached_transcript(src) is None  # never transcribed
    assert transcribe.cached_transcript(tmp_citadel.raw / "gone.mp3") is None  # unreadable file
