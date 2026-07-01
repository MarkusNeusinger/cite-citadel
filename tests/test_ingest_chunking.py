"""Large-source chunking (offline): a source over CITADEL_MAX_SOURCE_CHARS is split into ordered
segments folded in over several passes; PDFs and disabled chunking stay single-pass; a failed
pass leaves the source pending. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, ingest


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

    import json

    data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))["sources"]
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


def test_chunk_pass_failure_leaves_source_pending(tmp_citadel, fake_agent, cite_page, monkeypatch):
    """If a later segment's session fails, the source is NOT marked done (so it re-ingests next run),
    the failure is recorded, and the earlier promoted segment's page is still reported/indexed."""
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
    assert report.errors  # the failure surfaced
    assert (wiki / "misc" / "big.md").exists()  # segment one's page is live (documented partial)

    import json

    manifest_path = tmp_citadel.manifest_path
    tracked = json.loads(manifest_path.read_text(encoding="utf-8"))["sources"] if manifest_path.exists() else {}
    assert "raw/big.txt" not in tracked  # not marked done -> pending again next run
