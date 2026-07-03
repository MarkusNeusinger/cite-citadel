"""Large-source chunking (offline): a source over CITADEL_MAX_SOURCE_CHARS is split into ordered
segments folded in over several passes; PDFs and disabled chunking stay single-pass; a failed
pass leaves the source pending.

PROMOTE-ONCE (docs/refactor-plan.md Z11, "no silently partial imports"): all segments of one
chunked source fold into a SINGLE staging copy; validation runs after EVERY segment (fail fast)
but PROMOTION happens exactly once, after the last segment passes — the live wiki only ever
contains fully-imported sources. Trade-off accepted: a failure at segment N discards the whole
staging copy (N-1 segments' agent work), and the source retries from segment 1 next run.
``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, failures, ingest


def _paras(n: int) -> str:
    """n paragraphs (~55 chars each) separated by blank lines, each individually identifiable."""
    return "\n\n".join(f"Paragraph number {i} with some filler content about topic {i}." for i in range(n))


def test_large_text_source_is_chunked_into_ordered_passes(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """A source larger than MAX_SOURCE_CHARS is split into ordered segments, each ingested in its
    own pass (segment tuple (i, n), read_path holds that segment's slice), covering all content;
    the source is processed once, tracked once, and all segment temp files are cleaned up."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "big.txt").write_text(_paras(6), encoding="utf-8")

    calls: list[dict] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        assert read_path is not None and segment is not None  # every chunked pass has both
        assert Path(read_path).exists()  # the segment file exists at call time
        calls.append({"segment": segment, "content": Path(read_path).read_text(encoding="utf-8")})
        if segment[0] == 1:  # first pass sets up the page; later passes merge (no-op here)
            cite_page("misc/big.md", rel_key, "A fact from the big source.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    n = len(calls)
    assert n >= 2  # actually split
    assert report.processed == ["raw/big.txt"]
    assert [c["segment"] for c in calls] == [(i, n) for i in range(1, n + 1)]  # ordered (i, n)
    assert all(len(c["content"]) <= 120 for c in calls)  # each within the cap
    joined = "\n".join(c["content"] for c in calls)
    for i in range(6):
        assert f"Paragraph number {i}" in joined  # all content covered across segments

    data = tmp_citadel.read_manifest()
    assert "raw/big.txt" in data  # tracked once
    assert ingest.ingest().processed == []  # idempotent


def test_chunking_disabled_is_single_direct_pass(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """With MAX_SOURCE_CHARS=0, even a large source is one pass and the agent reads it directly."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 0)
    (raw / "big.txt").write_text(_paras(50), encoding="utf-8")

    calls: list[tuple] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        calls.append((read_path, segment))
        assert read_path is None and segment is None  # not chunked -> read the file directly
        cite_page("misc/big.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    assert ingest.ingest().processed == ["raw/big.txt"]
    assert len(calls) == 1


def test_large_pdf_is_not_chunked(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """A large PDF is handed to the agent whole (its text isn't extracted here to split), so it is
    a single direct pass regardless of size."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 100)
    (raw / "big.pdf").write_bytes(b"%PDF-1.7\n" + b"a" * 5000)

    calls: list[tuple] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        calls.append((read_path, segment))
        assert read_path is None and segment is None  # PDF read directly, never chunked
        cite_page("misc/big.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    assert ingest.ingest().processed == ["raw/big.pdf"]
    assert len(calls) == 1


def test_segment_failure_discards_all_segments_nothing_live(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """DELIBERATE PIN FLIP (Z11, "no silently partial imports"): when segment 2 of a chunked
    source fails, the LIVE wiki holds NOTHING from the source — the whole single staging copy is
    discarded. (The previous pin here documented the opposite: segment 1's page was promoted and
    stayed live, a silently half-folded source. Z11 accepts the trade-off: a failure at segment N
    discards N-1 segments' agent work; the all-or-nothing guarantee is worth more.) The manifest
    is untouched, the failure is recorded, and the NEXT run retries from segment 1 in full."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "big.txt").write_text(_paras(6), encoding="utf-8")

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")
        elif segment[0] == 2:
            raise RuntimeError("segment two boom")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert "raw/big.txt" not in report.processed
    assert any("segment two boom" in e for e in report.errors)
    assert not (wiki / "misc" / "big.md").exists()  # FLIPPED: nothing from the source is live (Z11)
    assert "misc/big.md" not in report.pages_created  # the report claims no page that is not live
    assert "raw/big.txt" not in tmp_citadel.read_manifest()  # not marked done -> pending next run
    assert failures.load()["raw/big.txt"]["reason"] == failures.ERROR  # the failure is persisted

    # The next run retries the WHOLE source from segment 1 (nothing was salvaged to merge into).
    segments: list[tuple[int, int]] = []

    def fake_retry(rel_key, kind="ingest", read_path=None, segment=None):
        segments.append(segment)
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")

    fake_agent(side_effect=fake_retry)
    second = ingest.ingest()

    assert second.processed == ["raw/big.txt"]
    assert segments[0] == (1, segments[0][1]) and len(segments) == segments[0][1]  # full retry, 1..N
    assert (wiki / "misc" / "big.md").exists()
    assert "raw/big.txt" not in failures.load()  # success clears the record


def test_segments_fold_into_single_staging_and_promote_once(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """Z11: all segments of one chunked source run against the SAME staging copy (a later segment
    sees — and merges into — what the earlier segments wrote there, exactly as the ingest brief
    promises), the live wiki stays untouched until the LAST segment passes, and promotion happens
    exactly ONCE. The manifest marks the source once, at the end."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "big.txt").write_text(_paras(6), encoding="utf-8")

    promotes: list[Path] = []
    real_promote = ingest._promote

    def counting_promote(staging, live, **kwargs):
        promotes.append(Path(staging))
        return real_promote(staging, live, **kwargs)

    monkeypatch.setattr(ingest, "_promote", counting_promote)

    seen: list[dict] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.append(
            {
                "segment": segment,
                # Mid-source, the LIVE wiki must never hold this source's page yet.
                "live_clean": not (wiki / "misc" / "big.md").exists(),
                # Segments > 1 MERGE into what the earlier segments wrote in the shared staging.
                "staging_has_earlier": (config.WIKI_DIR / "misc" / "big.md").exists(),
            }
        )
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert len(seen) >= 3  # actually split into several segments
    assert report.processed == ["raw/big.txt"]
    assert len(promotes) == 1  # promotion happens exactly ONCE, after the last segment
    assert all(s["live_clean"] for s in seen)  # live untouched until the final promote
    assert all(s["staging_has_earlier"] for s in seen if s["segment"][0] > 1)  # one shared staging
    assert (wiki / "misc" / "big.md").exists()  # ... then the fully-folded source goes live
    assert "raw/big.txt" in tmp_citadel.read_manifest()  # marked done once, at the end


def test_invalid_segment_fails_fast_and_discards_whole_source(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """Z11: validation still runs after EVERY segment (fail fast) — an invalid page written by
    segment 2 stops the source right there (segment 3 never runs) — and promote-once means
    NOTHING, not even segment 1's clean work, reaches the live wiki."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "big.txt").write_text(_paras(6), encoding="utf-8")

    seen: list[int] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.append(segment[0])
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")
        elif segment[0] == 2:
            (Path(config.WIKI_DIR) / "misc" / "invalid.md").write_text("no frontmatter at all\n", encoding="utf-8")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert seen == [1, 2]  # fail fast: segment 3 never ran
    assert "raw/big.txt" not in report.processed and report.errors
    assert not (wiki / "misc" / "big.md").exists()  # segment 1's clean work discarded too (Z11)
    assert not (wiki / "misc" / "invalid.md").exists()  # the invalid page never reached live
    assert "raw/big.txt" not in tmp_citadel.read_manifest()  # retried in full next run
