"""Audio/video sources (offline): with CITADEL_AUDIO_SUPPORT on, a recognized recording is
transcribed through the whisper seam (faked here — no test spawns a real whisper) and the agent
reads the ``[HH:MM:SS]``-stamped transcript while the wiki cites the original media file; the
content-addressed cache doubles as the offline verification text for lint and ``wiki_raw``.
``llm.run_ingest_session`` is replaced by ``fake_agent``, mirroring test_ingest_office_images.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from citadel import config, ingest, lint, manifest, store, transcribe


TRANSCRIPT = "[00:00:01] Hello from the memo.\n[00:00:05] The budget was approved.\n"


def _make_mp3(path: Path, tail: bytes = b"\x00\x01\xff\xfbfake-mp3-frames") -> None:
    """A file that passes the audio magic sniff (ID3 header) and — like a real MP3 — is not
    valid UTF-8 (the 0xFF byte), so no consumer can mistake it for text."""
    path.write_bytes(b"ID3\x03\x00" + tail)


@pytest.fixture
def audio_on(monkeypatch):
    monkeypatch.setattr(config, "AUDIO_SUPPORT", True)


@pytest.fixture
def fake_whisper(monkeypatch):
    """Fake the SHELL-OUT (transcribe._run_whisper) but keep the real transcript_for, so the
    content-addressed cache machinery runs for real in these end-to-end tests."""
    calls = {"n": 0, "text": TRANSCRIPT}

    def fake(path):
        calls["n"] += 1
        return calls["text"]

    monkeypatch.setattr(transcribe, "_run_whisper", fake)
    return calls


# --- partition classification ------------------------------------------------------------


def test_partition_routes_audio_to_pending_when_knob_on(tmp_citadel, audio_on):
    raw = tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")

    scan = ingest._partition_sources(None, {})

    assert {manifest.rel_key(p) for p in scan.pending} == {"raw/memo.mp3"}
    assert {manifest.rel_key(p) for p in scan.audio} == {"raw/memo.mp3"}
    assert scan.unreadable == []


def test_partition_knob_off_marks_audio_unreadable(tmp_citadel, fake_agent):
    """Without the knob (the default), an audio file is a NUL-byte binary: logged unreadable and
    marked done — exactly the pre-feature behavior."""
    raw = tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")

    report = ingest.ingest()

    assert "raw/memo.mp3" in report.unreadable and report.processed == []
    assert "raw/memo.mp3" in tmp_citadel.read_manifest()  # marked done, not re-checked


def test_text_file_renamed_mp3_is_not_audio(tmp_citadel, audio_on, fake_agent, cite_page):
    """A text file merely RENAMED .mp3 fails the magic sniff and ingests as plain text (kind
    'ingest', read directly) — never shelled out to whisper."""
    raw = tmp_citadel.raw
    (raw / "notreally.mp3").write_text("Plain text, no ID3 header.\n", encoding="utf-8")

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.update(kind=kind, read_path=read_path)
        cite_page("misc/notreally.md", rel_key, "A plain fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert report.processed == ["raw/notreally.mp3"]
    assert seen["kind"] == "ingest" and seen["read_path"] is None


# --- end-to-end ingest -------------------------------------------------------------------


def test_audio_source_transcribed_and_ingested(tmp_citadel, audio_on, fake_whisper, fake_agent, seed_page):
    """The full path: the recording is transcribed once (cache written), the agent reads the
    transcript temp under the AUDIO propagation, the wiki cites the ORIGINAL .mp3, the temp is
    cleaned up, and a re-run is idempotent — no second whisper run, no second session."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.update(rel_key=rel_key, kind=kind, read_path=read_path, segment=segment)
        assert read_path is not None
        seen["prepared"] = Path(read_path).read_text(encoding="utf-8")
        seed_page(
            "misc/memo.md",
            {"type": "Note", "title": "Memo", "description": "d", "tags": ["audio"], "resource": rel_key},
            f"The budget was approved.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{rel_key}](../../{rel_key}), lines 2-2 - voice memo (ingested 2026-07-23)\n",
        )

    agent = fake_agent(side_effect=fake)

    report = ingest.ingest()

    assert report.processed == ["raw/memo.mp3"] and not report.errors
    assert seen["kind"] == "audio"  # the audio propagation, not plain "ingest"
    assert seen["rel_key"] == "raw/memo.mp3"
    assert seen["prepared"] == TRANSCRIPT  # the agent read the [HH:MM:SS] transcript
    assert seen["segment"] is None
    assert fake_whisper["n"] == 1

    page_text = (wiki / "misc" / "memo.md").read_text(encoding="utf-8")
    assert "resource: raw/memo.mp3" in page_text  # cites the recording, not the transcript temp
    rep = lint.lint()
    assert rep.ok() and rep.bad_sources == []
    assert rep.locator_issues == []  # `lines 2-2` verified offline against the cached transcript

    assert "raw/memo.mp3" in tmp_citadel.read_manifest()
    assert not Path(str(seen["read_path"])).exists()  # transcript temp cleaned up
    assert transcribe.cached_transcript(raw / "memo.mp3") == TRANSCRIPT  # cache persisted

    # Idempotent: no second whisper run, no second session.
    assert ingest.ingest().processed == []
    assert agent.count == 1 and fake_whisper["n"] == 1


def test_changed_audio_reingests_as_audio_reconcile(tmp_citadel, audio_on, fake_whisper, fake_agent, cite_page):
    raw = tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen["kind"] = kind
        cite_page("misc/memo.md", rel_key, "A memo fact.")

    fake_agent(side_effect=fake)
    ingest.ingest()
    assert seen["kind"] == "audio"

    _make_mp3(raw / "memo.mp3", tail=b"\x00re-recorded-different-bytes")
    fake_whisper["text"] = "[00:00:01] A newer take.\n"
    ingest.ingest()
    assert seen["kind"] == "audio-reconcile"
    assert fake_whisper["n"] == 2  # new bytes -> new cache key -> transcribed again


def test_whisper_failure_is_a_retryable_source_error(tmp_citadel, audio_on, fake_agent, monkeypatch):
    """A missing/failing whisper CLI fails the SOURCE (prepare_error), not the run: the error is
    recorded in the failures catalog, nothing is promoted or marked done, no agent session is
    spent — and the next run retries."""
    raw = tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")
    attempts = {"n": 0}

    def failing(src, sha=None):
        attempts["n"] += 1
        raise RuntimeError("the whisper CLI 'whisper' was not found on PATH")

    monkeypatch.setattr(transcribe, "transcript_for", failing)
    agent = fake_agent()

    report = ingest.ingest()

    assert report.processed == []
    assert any("whisper" in e for e in report.errors)
    assert agent.count == 0  # no LLM session was wasted on a source with no transcript
    assert "raw/memo.mp3" not in tmp_citadel.read_manifest()  # NOT marked done
    failures_data = json.loads(tmp_citadel.failures_path.read_text(encoding="utf-8"))
    assert any("memo.mp3" in key for key in failures_data.get("sources", failures_data))

    ingest.ingest()
    assert attempts["n"] == 2  # retried next run


def test_long_transcript_chunks_with_brief_on_every_segment(
    tmp_citadel, audio_on, fake_whisper, fake_agent, cite_page, monkeypatch
):
    """A long recording's transcript rides the existing multi-pass chunking: every pass keeps the
    AUDIO kind (so formats/transcripts.md binds per slice) and merges into one promote."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 80)
    fake_whisper["text"] = (
        "\n".join(f"[00:0{i}:00] Utterance number {i}, long enough to split." for i in range(6)) + "\n"
    )
    _make_mp3(raw / "podcast.mp3")

    seen: list[tuple[str, tuple[int, int] | None]] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.append((kind, segment))
        cite_page("misc/podcast.md", rel_key, "A podcast fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert report.processed == ["raw/podcast.mp3"]
    assert len(seen) > 1  # genuinely chunked
    assert all(kind == "audio" for kind, _seg in seen)
    assert [seg for _kind, seg in seen] == [(i, len(seen)) for i in range(1, len(seen) + 1)]
    assert fake_whisper["n"] == 1  # one transcription feeds all segments


# --- the cache as offline verification text ----------------------------------------------


def test_lint_flags_out_of_range_locator_against_cached_transcript(tmp_citadel, audio_on, fake_whisper, seed_page):
    raw = tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")
    transcribe.transcript_for(raw / "memo.mp3")  # populate the cache (2 lines)

    seed_page(
        "misc/memo.md",
        {"type": "Note", "title": "Memo", "description": "d", "tags": ["a"], "resource": "raw/memo.mp3"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/memo.mp3](../../raw/memo.mp3), lines 7-9 - memo\n",
    )
    issues = lint.check_locators(store.load())
    assert issues and "out of range" in issues[0][1]

    # An in-range locator into the same cache verifies clean.
    seed_page(
        "misc/memo.md",
        {"type": "Note", "title": "Memo", "description": "d", "tags": ["a"], "resource": "raw/memo.mp3"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/memo.mp3](../../raw/memo.mp3), lines 1-2 - memo\n",
    )
    assert lint.check_locators(store.load()) == []


def test_lint_skips_audio_locators_without_a_cache(tmp_citadel, audio_on, seed_page):
    """No cache on this machine -> the locator is agent-verified (skipped, advisory) — never a
    false flag from reading the binary itself."""
    raw = tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")
    seed_page(
        "misc/memo.md",
        {"type": "Note", "title": "Memo", "description": "d", "tags": ["a"], "resource": "raw/memo.mp3"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/memo.mp3](../../raw/memo.mp3), lines 999-1000 - memo\n",
    )
    assert lint.check_locators(store.load()) == []


def test_viewer_serves_cached_transcript_as_audio_kind(tmp_citadel, audio_on, fake_whisper):
    from citadel import viewer

    raw = tmp_citadel.raw
    _make_mp3(raw / "memo.mp3")
    transcribe.transcript_for(raw / "memo.mp3")

    text, kind = viewer._read_source(raw / "memo.mp3")
    assert kind == "audio" and text == TRANSCRIPT
    # Without a cache (different bytes -> different content hash) the recording stays a binary
    # (open-the-original link).
    _make_mp3(raw / "other.mp3", tail=b"\x00\xff\xfbnever-transcribed-bytes")
    assert viewer._read_source(raw / "other.mp3") == ("", "binary")
