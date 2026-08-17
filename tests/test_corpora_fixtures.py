"""Offline invariants for the generated test-corpus fixtures.

The corpora are graded by the `verify-corpus` skill against a hidden `ground-truth.md`, which is an
ANSWER KEY: it states, in prose, what a correct wiki must contain. That key can go quietly wrong in a
way no other test notices — a regenerated fixture, a pypdf upgrade that shifts the extraction, a
re-tuned chunk floor — and then the grader measures the pipeline against a document that no longer
describes the corpus. These tests pin the few fixture properties the key actually depends on, so such
a drift fails HERE, loudly and for free, instead of silently downgrading a paid corpus run.

Deliberately narrow: only the properties a ground-truth file asserts. Corpus prose is not pinned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from citadel import config, ingest_sessions, pdftext


GAZETTE_RAW = Path(__file__).resolve().parents[1] / "corpora" / "gazette" / "raw"
FIELD_SURVEY = GAZETTE_RAW / "field-survey.pdf"

# The window budget gazette/ground-truth.md §F names for its chunked run
# (CITADEL_MODEL_CONTEXT_TOKENS=20000 -> 20000 * 0.10 * 4).
GROUND_TRUTH_WINDOW_CHARS = 8000
STATIONS = 36


@pytest.fixture(scope="module")
def survey_text() -> str:
    if not FIELD_SURVEY.is_file():
        pytest.skip("gazette fixtures not generated (corpora/gazette/make_pdfs.py)")
    text = pdftext._extract(FIELD_SURVEY)
    if not text:
        pytest.skip("pypdf produced no text layer for the field-survey fixture")
    return text


def _station_spans(text: str) -> dict[int, tuple[int, int]]:
    """Each station's 1-based inclusive line span in the extraction."""
    starts: dict[int, int] = {}
    for n, line in enumerate(text.splitlines(), 1):
        m = re.search(r"Station T-(\d{2})", line)
        if m:
            starts.setdefault(int(m.group(1)), n)
    order = sorted(starts)
    total = len(text.splitlines())
    return {s: (starts[s], (starts[order[i + 1]] - 1) if i + 1 < len(order) else total) for i, s in enumerate(order)}


def test_field_survey_carries_every_station(survey_text):
    """The key grades "all 36 stations survive". They have to be IN the extraction first."""
    missing = [i for i in range(1, STATIONS + 1) if f"T-{i:02d}" not in survey_text]
    assert not missing, f"stations absent from the extraction: {missing}"


def test_field_survey_still_chunks_at_the_segment_floor(survey_text):
    """The fixture's whole purpose is to be long enough to split. If it ever stops splitting even at
    the smallest budget citadel will use, the §F grade silently becomes a no-op that always passes."""
    windows = ingest_sessions._line_windows(survey_text, config.MIN_CHUNK_CHARS)
    assert len(windows) >= 2, "field-survey.pdf no longer chunks — §F would grade nothing"


def test_field_survey_boundaries_still_cut_records_in_half(survey_text):
    """§F grades that a record CUT by a window edge survives whole. That only tests anything while
    some record is actually cut — an extraction shift could align every boundary with a record break
    and turn the sharpest check in this corpus into a tautology."""
    windows = ingest_sessions._line_windows(survey_text, GROUND_TRUTH_WINDOW_CHARS)
    spans = _station_spans(survey_text)
    straddling = sorted(
        s for s, (begin, end) in spans.items() for (w_start, w_end) in windows if w_start <= begin <= w_end < end
    )
    assert straddling, "no station straddles a window edge — §F's cut-record grade tests nothing"


def test_ground_truth_names_the_stations_it_grades(survey_text):
    """The answer key hard-codes WHICH stations straddle. Keep the key and the fixture in step: a
    named station that no longer straddles would have the grader hunting a defect that cannot exist."""
    key = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "verify-corpus" / "gazette" / "ground-truth.md"
    if not key.is_file():
        pytest.skip("ground-truth key not present in this checkout")
    named = {int(m) for m in re.findall(r"\*\*T-(\d{2})\*\*", key.read_text(encoding="utf-8"))}
    if not named:
        pytest.skip("the key names no straddling stations")

    windows = ingest_sessions._line_windows(survey_text, GROUND_TRUTH_WINDOW_CHARS)
    spans = _station_spans(survey_text)
    straddling = {
        s for s, (begin, end) in spans.items() for (w_start, w_end) in windows if w_start <= begin <= w_end < end
    }
    assert named == straddling, f"key names {sorted(named)}, fixture straddles {sorted(straddling)}"
