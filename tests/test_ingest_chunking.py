"""Large-source chunking (offline): a source over CITADEL_MAX_SOURCE_CHARS is split into ordered
segments folded in over several passes; PDFs and disabled chunking stay single-pass; a failed
pass leaves the source pending.

PROMOTE-ONCE ("no silently partial imports"): all segments of one
chunked source fold into a SINGLE staging copy; validation runs after EVERY segment (fail fast)
but PROMOTION happens exactly once, after the last segment passes — the live wiki only ever
contains fully-imported sources. A failure at segment N still discards the whole staging copy and
promotes nothing. What it no longer discards is the MONEY: segment N-1's work was checkpointed, so
the next run replays it and continues at segment N (citadel/resume.py — the resume behavior itself
is pinned in tests/test_ingest_resume.py). ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, failures, ingest, ingest_sessions


def _paras(n: int) -> str:
    """n paragraphs (~55 chars each) separated by blank lines, each individually identifiable."""
    return "\n\n".join(f"Paragraph number {i} with some filler content about topic {i}." for i in range(n))


def _window_text(lines: list[str], window: tuple[int, int]) -> str:
    """The text of a 1-based inclusive line window — what the agent's ranged read of the file sees."""
    return "\n".join(lines[window[0] - 1 : window[1]])


def test_large_text_source_is_chunked_into_ordered_passes(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """A source larger than MAX_SOURCE_CHARS is folded in over ordered passes, each a contiguous
    LINE WINDOW of the ORIGINAL file (segment tuple (i, n), line_range (a, b), read_path None —
    the agent reads the source itself, ranged); the windows cover every line exactly once, the
    source is processed once and tracked once, and no temp file is ever written for it."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    body = _paras(6)
    (raw / "big.txt").write_text(body, encoding="utf-8")
    lines = body.splitlines()

    calls: list[dict] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        assert read_path is None  # no slice: the source file IS what the agent reads
        assert segment is not None and line_range is not None  # every chunked pass has both
        calls.append({"segment": segment, "window": line_range, "content": _window_text(lines, line_range)})
        if segment[0] == 1:  # first pass sets up the page; later passes merge (no-op here)
            cite_page("misc/big.md", rel_key, "A fact from the big source.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    n = len(calls)
    assert n >= 2  # actually split
    assert report.processed == ["raw/big.txt"]
    assert [c["segment"] for c in calls] == [(i, n) for i in range(1, n + 1)]  # ordered (i, n)
    assert all(len(c["content"]) <= 120 for c in calls)  # each within the cap
    windows = [c["window"] for c in calls]
    assert windows[0][0] == 1 and windows[-1][1] == len(lines)  # first line to last line
    assert all(b + 1 == a2 for (_a, b), (a2, _b2) in zip(windows, windows[1:], strict=False))  # contiguous, no overlap
    joined = "\n".join(c["content"] for c in calls)
    for i in range(6):
        assert f"Paragraph number {i}" in joined  # all content covered across segments

    data = tmp_citadel.read_manifest()
    assert "raw/big.txt" in data  # tracked once
    assert ingest.ingest().processed == []  # idempotent


def test_chunked_text_windows_keep_the_original_line_numbers(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """The locator guarantee for chunked plain text. The previous slicer split on blank-line RUNS
    and re-joined with one blank line, then wrote each segment to a temp restarting at line 1 — so
    a segment-1 agent that trusted the slice's numbering cited `lines A-B` that drifted early by
    one line per squeezed run (observed on the pemberley showcase: 17-258 lines off). Now every
    pass is a window of the original file: a fact's line number inside the window IS its line
    number in the source, however many blank lines precede it."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    # Blank-line RUNS of growing length between paragraphs: exactly what the slicer collapsed.
    body = "".join(
        f"Paragraph number {i} with some filler content about topic {i}.\n" + "\n" * (i + 1) for i in range(6)
    )
    (raw / "big.txt").write_text(body, encoding="utf-8")
    lines = body.splitlines()
    assert (
        lines.index("Paragraph number 5 with some filler content about topic 5.") + 1 == 21
    )  # 5 paras + 1+2+3+4+5 blanks

    windows: list[tuple[int, int]] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        windows.append(line_range)
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from the big source.")

    fake_agent(side_effect=fake)
    assert ingest.ingest().processed == ["raw/big.txt"]
    assert len(windows) >= 2
    # Every paragraph is found at its TRUE line number inside exactly one window.
    for i in range(6):
        true_line = lines.index(f"Paragraph number {i} with some filler content about topic {i}.") + 1
        owners = [w for w in windows if w[0] <= true_line <= w[1]]
        assert len(owners) == 1, (i, true_line, windows)
        assert lines[true_line - 1].startswith(f"Paragraph number {i} ")  # the number indexes the source


def test_chunking_disabled_is_single_direct_pass(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """With MAX_SOURCE_CHARS=0, even a large source is one pass and the agent reads it directly."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 0)
    (raw / "big.txt").write_text(_paras(50), encoding="utf-8")

    calls: list[tuple] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
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

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        calls.append((read_path, segment))
        assert read_path is None and segment is None  # PDF read directly, never chunked
        cite_page("misc/big.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    assert ingest.ingest().processed == ["raw/big.pdf"]
    assert len(calls) == 1


def test_segment_failure_discards_all_segments_nothing_live(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """DELIBERATE PIN FLIP #2 ("no silently partial imports", now without the wasted spend): when
    segment 2 of a chunked source fails, the LIVE wiki still holds NOTHING from the source — the
    whole single staging copy is discarded — the manifest is untouched and the failure is recorded.

    Pin history, because the trade-off moved twice:
      1. originally segment 1's page was PROMOTED and stayed live — a silently half-folded source;
      2. promote-once flipped that: nothing reaches live, but the NEXT RUN RE-RAN SEGMENT 1,
         discarding N-1 segments' paid agent work;
      3. now (resume checkpoints, citadel/resume.py) the next run CONTINUES AT SEGMENT 2, replaying
         segment 1's checkpointed work into the fresh staging copy. What reaches the live wiki is
         unchanged in every case — only the bill is."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "big.txt").write_text(_paras(6), encoding="utf-8")

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")
        elif segment[0] == 2:
            raise RuntimeError("segment two boom")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert "raw/big.txt" not in report.processed
    assert any("segment two boom" in e for e in report.errors)
    assert not (wiki / "misc" / "big.md").exists()  # FLIPPED: nothing from the source is live
    assert "misc/big.md" not in report.pages_created  # the report claims no page that is not live
    assert "raw/big.txt" not in tmp_citadel.read_manifest()  # not marked done -> pending next run
    assert failures.load()["raw/big.txt"]["reason"] == failures.ERROR  # the failure is persisted

    # The next run picks the source back up at segment 2 — segment 1 is never re-run, and its page
    # is restored from the checkpoint (this fake deliberately writes NOTHING, so a page that exists
    # afterwards can only have come from the replay).
    segments: list[tuple[int, int]] = []

    def fake_retry(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        segments.append(segment)
        # Segment 1's page is already in the staging copy when the resumed segment opens.
        assert (Path(config.wiki_dir()) / "misc" / "big.md").exists()

    fake_agent(side_effect=fake_retry)
    second = ingest.ingest()

    total = segments[0][1]
    assert second.processed == ["raw/big.txt"]
    assert segments == [(i, total) for i in range(2, total + 1)]  # continued at 2, 1 never re-run
    assert (wiki / "misc" / "big.md").exists()  # segment 1's work: replayed, then promoted
    assert "segment one" in (wiki / "misc" / "big.md").read_text(encoding="utf-8")
    assert second.resumed and "segments 1-1" in second.resumed[0]  # and the report says so
    assert "raw/big.txt" not in failures.load()  # success clears the record


def test_segments_fold_into_single_staging_and_promote_once(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """All segments of one chunked source run against the SAME staging copy (a later segment
    sees — and merges into — what the earlier segments wrote there, exactly as the ingest brief
    promises), the live wiki stays untouched until the LAST segment passes, and promotion happens
    exactly ONCE. The manifest marks the source once, at the end."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "big.txt").write_text(_paras(6), encoding="utf-8")

    promotes: list[Path] = []
    real_promote = ingest_sessions._promote

    def counting_promote(staging, live, **kwargs):
        promotes.append(Path(staging))
        return real_promote(staging, live, **kwargs)

    monkeypatch.setattr(ingest_sessions, "_promote", counting_promote)

    seen: list[dict] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        seen.append(
            {
                "segment": segment,
                # Mid-source, the LIVE wiki must never hold this source's page yet.
                "live_clean": not (wiki / "misc" / "big.md").exists(),
                # Segments > 1 MERGE into what the earlier segments wrote in the shared staging.
                "staging_has_earlier": (config.wiki_dir() / "misc" / "big.md").exists(),
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
    """Validation still runs after EVERY segment (fail fast) — an invalid page written by
    segment 2 stops the source right there (segment 3 never runs) — and promote-once means
    NOTHING, not even segment 1's clean work, reaches the live wiki."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (raw / "big.txt").write_text(_paras(6), encoding="utf-8")

    seen: list[int] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        seen.append(segment[0])
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from segment one.")
        elif segment[0] == 2:
            (Path(config.wiki_dir()) / "misc" / "invalid.md").write_text("no frontmatter at all\n", encoding="utf-8")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert seen == [1, 2]  # fail fast: segment 3 never ran
    assert "raw/big.txt" not in report.processed and report.errors
    assert not (wiki / "misc" / "big.md").exists()  # segment 1's clean work discarded too
    assert not (wiki / "misc" / "invalid.md").exists()  # the invalid page never reached live
    assert "raw/big.txt" not in tmp_citadel.read_manifest()  # retried in full next run


# --- The chunk budget: CITADEL_MAX_SOURCE_CHARS as ceiling, a stated model context as budget ---
#
# `config.source_chunk_chars()` is the ONE value ingest splits on (`_prepare_passes`) and the one
# hashed into a resume checkpoint's segment shape (`_plan_shape`). These pin its composition, which
# is deliberately asymmetric: the char threshold is an absolute ceiling, a stated model context only
# ever tightens it, and neither can talk the other into chunking a source that was told not to.


def test_stated_context_derives_a_finer_chunk_budget(monkeypatch):
    """A stated model context caps the per-pass source window at 10% of it (~4 chars/token), well
    under the generous char default — this is the whole point of the knob."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 300000)
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 100000)
    assert config.context_budget_chars() == 40000
    assert config.source_chunk_chars() == 40000


def test_unset_context_leaves_the_char_threshold_alone(monkeypatch):
    """The default. An existing workspace that never heard of the new knob must chunk exactly where
    it always did — this is the pin against a silent behavior change for every current user."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 300000)
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 0)
    assert config.context_budget_chars() == 0
    assert config.source_chunk_chars() == 300000


def test_max_source_chars_still_wins_when_lower(monkeypatch):
    """The two compose by min(): the char threshold stays the hard ceiling, so an operator who wants
    a window tighter than the derived one keeps the direct override they always had."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 25000)
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 100000)
    assert config.source_chunk_chars() == 25000


def test_chunking_off_beats_a_stated_context(monkeypatch):
    """CITADEL_MAX_SOURCE_CHARS=0 is an explicit "never chunk". A stated context is a BUDGET, not an
    override, so it must not switch chunking back on behind the operator's back."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 0)
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 100000)
    assert config.source_chunk_chars() == 0


def test_tiny_stated_context_clamps_to_the_segment_floor(monkeypatch):
    """Every segment is a full session that re-pays the rulebook read, so the budget is floored: no
    stated context, however small, can produce an unbounded number of tiny passes."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 300000)
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 4000)
    assert config.context_budget_chars() < config.MIN_CHUNK_CHARS  # what doctor WARNs about
    assert config.source_chunk_chars() == config.MIN_CHUNK_CHARS


def test_stated_context_segments_a_source_the_char_threshold_would_not(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """End-to-end: the reported bug. A source comfortably UNDER MAX_SOURCE_CHARS — one that plans a
    single pass today and blows a small model's context — is split once the model's context is
    stated, with no change to the char threshold."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 300000)  # untouched: alone it would NOT split
    monkeypatch.setattr(config, "MODEL_CONTEXT_TOKENS", 50000)  # -> a 20000-char window
    body = _paras(1100)
    assert len(body) < config.MAX_SOURCE_CHARS  # the premise: not "large" by the char threshold
    (raw / "big.txt").write_text(body, encoding="utf-8")

    calls: list[dict] = []

    lines = body.splitlines()

    def fake(rel_key, kind="ingest", read_path=None, segment=None, line_range=None):
        assert read_path is None and segment is not None and line_range is not None
        calls.append({"segment": segment, "content": _window_text(lines, line_range)})
        if segment[0] == 1:
            cite_page("misc/big.md", rel_key, "A fact from the big source.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    n = len(calls)
    assert n >= 3  # actually split, several times over
    assert report.processed == ["raw/big.txt"]
    assert [c["segment"] for c in calls] == [(i, n) for i in range(1, n + 1)]
    assert all(len(c["content"]) <= 20000 for c in calls)  # each within the derived window
    joined = "\n".join(c["content"] for c in calls)
    for i in (0, 550, 1099):
        assert f"Paragraph number {i} " in joined  # start, middle and end all covered
