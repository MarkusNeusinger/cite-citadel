"""Same-basename document dedup (offline): a folder holding the same document in several formats
(report.pdf + report.pptx) collapses to one preferred file; the rest are recorded as duplicates.
``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from citadel import config, ingest


def test_dedup_by_basename_keeps_pdf_over_pptx(tmp_citadel, make_pptx):
    """A same-folder, same-basename group of document formats collapses to one kept file (PDF
    preferred), the rest reported as duplicates."""
    raw = tmp_citadel.raw
    (raw / "deck.pdf").write_bytes(b"%PDF-1.7\n")
    make_pptx(raw / "deck.pptx", [["x"]])
    kept, dups, dropped = ingest._dedup_by_basename([raw / "deck.pdf", raw / "deck.pptx"], {})
    assert [p.name for p in kept] == ["deck.pdf"]
    assert dups == [("raw/deck.pptx", "raw/deck.pdf")]
    assert (raw / "deck.pptx") in dropped


def test_dedup_leaves_group_with_nondoc_sibling_alone(tmp_citadel):
    """A group is only collapsed when ALL members are document formats — a hand-authored notes.md
    sharing a stem with notes.pdf is never dropped."""
    raw = tmp_citadel.raw
    (raw / "notes.pdf").write_bytes(b"%PDF-1.7\n")
    (raw / "notes.md").write_text("real notes\n", encoding="utf-8")
    kept, dups, dropped = ingest._dedup_by_basename([raw / "notes.pdf", raw / "notes.md"], {})
    assert {p.name for p in kept} == {"notes.pdf", "notes.md"}
    assert dups == [] and dropped == set()


def test_dedup_staggered_skips_new_format_when_sibling_already_ingested(tmp_citadel, make_pptx):
    """If a same-basename document is ALREADY in the wiki (another format on disk), a newly-added
    format is skipped as a duplicate rather than ingested as a second copy."""
    raw = tmp_citadel.raw
    make_pptx(raw / "deck.pptx", [["x"]])  # already ingested (below), still on disk
    (raw / "deck.pdf").write_bytes(b"%PDF-1.7\n")  # newly added
    manifest_dict = {"raw/deck.pptx": {"sha256": "abc", "model": "m"}}
    kept, dups, dropped = ingest._dedup_by_basename([raw / "deck.pdf"], manifest_dict)
    assert kept == []  # the new pdf is skipped
    assert dups == [("raw/deck.pdf", "raw/deck.pptx")]  # points at the already-ingested sibling


def test_dedup_does_not_drop_a_changed_document_as_its_own_duplicate(tmp_citadel, make_pptx):
    """A CHANGED document source is both pending AND in the manifest; it must NOT be treated as an
    already-ingested sibling of itself and dropped — with no other same-basename format present it
    is kept and re-ingested."""
    raw = tmp_citadel.raw
    make_pptx(raw / "deck.pptx", [["x"]])
    manifest_dict = {"raw/deck.pptx": {"sha256": "oldsha", "model": "m"}}  # tracked (changed bytes)
    kept, dups, dropped = ingest._dedup_by_basename([raw / "deck.pptx"], manifest_dict)
    assert [p.name for p in kept] == ["deck.pptx"]
    assert dups == [] and dropped == set()


def test_same_basename_document_duplicate_is_skipped_and_recorded(tmp_citadel, fake_agent, make_pptx, cite_page):
    """End to end: report.pdf + report.pptx -> only the pdf runs a session; the pptx is skipped and
    recorded as a duplicate in the run report AND the persistent failures/sources catalog."""
    import json

    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "report.pdf").write_bytes(b"%PDF-1.7\ncontent")
    make_pptx(raw / "report.pptx", [["Slide fact."]])

    seen: list[str] = []

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        seen.append(rel_key)
        cite_page("misc/report.md", rel_key, "A report fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()

    assert report.processed == ["raw/report.pdf"] and seen == ["raw/report.pdf"]  # pptx never ran
    assert report.duplicates == [("raw/report.pptx", "raw/report.pdf")]

    data = json.loads((wiki / ".citadel_failures.json").read_text(encoding="utf-8"))
    assert data["raw/report.pptx"]["reason"] == "duplicate"
    assert "raw/report.pdf" in data["raw/report.pptx"]["detail"]
    catalog = (wiki / "sources" / "index.md").read_text(encoding="utf-8")
    assert "raw/report.pptx" in catalog and "duplicate" in catalog


def test_dedup_disabled_ingests_every_format(tmp_citadel, fake_agent, make_pptx, cite_page, monkeypatch):
    """With CITADEL_DEDUP_BY_BASENAME off, both same-basename formats are ingested separately."""
    raw = tmp_citadel.raw
    monkeypatch.setattr(config, "DEDUP_BY_BASENAME", False)
    (raw / "report.pdf").write_bytes(b"%PDF-1.7\ncontent")
    make_pptx(raw / "report.pptx", [["Slide fact."]])

    def fake(rel_key, kind="ingest", read_path=None, segment=None):
        from pathlib import Path as _P

        cite_page(f"misc/report-{_P(rel_key).suffix[1:]}.md", rel_key, "A fact.")

    fake_agent(side_effect=fake)
    report = ingest.ingest()
    assert set(report.processed) == {"raw/report.pdf", "raw/report.pptx"}
    assert report.duplicates == []


# --- #169: tracked members are never dropped; .ics ranks after every document ---------------


def _track_file(path, sha: str | None = None) -> None:
    from citadel import manifest

    m = manifest.load()
    m[manifest.rel_key(path)] = manifest.make_entry(
        sha or manifest.file_sha256(path), "claude:x", config.rules_version()
    )
    manifest.save(m)


def test_dedup_keeps_a_changed_tracked_twin_and_drops_the_new_one(tmp_citadel):
    raw = tmp_citadel.raw
    (raw / "x.docx").write_bytes(b"PK")
    (raw / "x.pdf").write_bytes(b"%PDF-1.7\n")
    kept, dups, _ = ingest._dedup_by_basename([raw / "x.docx", raw / "x.pdf"], {"raw/x.docx": {"sha256": "old"}})
    assert kept == [raw / "x.docx"]
    assert dups == [("raw/x.pdf", "raw/x.docx")]


def test_dedup_both_tracked_one_changed_keeps_it(tmp_citadel):
    raw = tmp_citadel.raw
    (raw / "deck.pdf").write_bytes(b"%PDF-1.7\n")
    (raw / "deck.docx").write_bytes(b"PK")
    kept, dups, _ = ingest._dedup_by_basename(
        [raw / "deck.pdf"], {"raw/deck.pdf": {"sha256": "old"}, "raw/deck.docx": {"sha256": "s"}}
    )
    assert kept == [raw / "deck.pdf"] and dups == []


def test_mixed_tracked_and_new_end_to_end_reconciles_the_tracked_twin(tmp_citadel, fake_agent, cite_page):
    from citadel import failures, status

    raw = tmp_citadel.raw
    (raw / "x.md").write_text("placeholder\n", encoding="utf-8")
    (raw / "x.ics").write_text("BEGIN:VCALENDAR\nSUMMARY:old\nEND:VCALENDAR\n", encoding="utf-8")
    _track_file(raw / "x.ics", sha="00" * 32)  # tracked, and its bytes have changed since
    (raw / "x.md").unlink()
    (raw / "x.pdf").write_text("BEGIN:VCALENDAR\nnot really a pdf\n", encoding="utf-8")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/x.md", rel_key, "A fact."))
    ingest.ingest()
    assert agent.calls == [("raw/x.ics", "reconcile")]
    assert failures.load()["raw/x.pdf"]["reason"] == failures.DUPLICATE
    report = status.build_status()
    assert [s.key for s in report.ingested] == ["raw/x.ics"]
    assert [s.key for s in report.skipped_duplicate] == ["raw/x.pdf"]


def test_a_stale_duplicate_record_on_a_tracked_twin_heals(tmp_citadel, fake_agent, cite_page):
    from citadel import failures

    raw = tmp_citadel.raw
    (raw / "x.ics").write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
    _track_file(raw / "x.ics", sha="00" * 32)
    stuck = failures.load()
    failures.record(stuck, "raw/x.ics", failures.DUPLICATE, "same basename as raw/x.pdf", None)
    failures.save(stuck)
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/x.md", rel_key, "A fact."))
    ingest.ingest()
    assert agent.calls == [("raw/x.ics", "reconcile")]
    assert "raw/x.ics" not in failures.load()


def test_dedup_priority_ends_with_ics_and_ranks_no_vcf_eml_msg():
    from citadel import ingest_scan

    assert ingest_scan._DEDUP_PRIORITY[-2:] == [".xls", ".ics"]
    assert not {".vcf", ".eml", ".msg"} & set(ingest_scan._DEDUP_PRIORITY)


def test_new_pdf_plus_ics_keeps_the_pdf(tmp_citadel):
    raw = tmp_citadel.raw
    (raw / "x.pdf").write_bytes(b"%PDF-1.7\n")
    (raw / "x.ics").write_text("BEGIN:VCALENDAR\n", encoding="utf-8")
    kept, dups, _ = ingest._dedup_by_basename([raw / "x.ics", raw / "x.pdf"], {})
    assert kept == [raw / "x.pdf"] and dups == [("raw/x.ics", "raw/x.pdf")]


def test_new_docx_plus_ics_keeps_the_docx(tmp_citadel):
    raw = tmp_citadel.raw
    (raw / "x.docx").write_bytes(b"PK")
    (raw / "x.ics").write_text("BEGIN:VCALENDAR\n", encoding="utf-8")
    kept, dups, _ = ingest._dedup_by_basename([raw / "x.ics", raw / "x.docx"], {})
    assert kept == [raw / "x.docx"] and dups == [("raw/x.ics", "raw/x.docx")]


def test_ics_with_md_or_vcf_with_pdf_are_not_collapsed(tmp_citadel):
    raw = tmp_citadel.raw
    for name in ("a.ics", "a.md", "b.vcf", "b.pdf"):
        (raw / name).write_text("x\n", encoding="utf-8")
    paths = [raw / n for n in ("a.ics", "a.md", "b.vcf", "b.pdf")]
    kept, dups, _ = ingest._dedup_by_basename(paths, {})
    assert set(kept) == set(paths) and dups == []


def test_staggered_new_pdf_behind_a_tracked_ics(tmp_citadel):
    raw = tmp_citadel.raw
    (raw / "x.ics").write_text("BEGIN:VCALENDAR\n", encoding="utf-8")
    (raw / "x.pdf").write_bytes(b"%PDF-1.7\n")
    kept, dups, _ = ingest._dedup_by_basename([raw / "x.pdf"], {"raw/x.ics": {"sha256": "s"}})
    assert kept == [] and dups == [("raw/x.pdf", "raw/x.ics")]


def test_both_tracked_ics_pdf_no_retroactive_effect(tmp_citadel, fake_agent, cite_page):
    raw = tmp_citadel.raw
    (raw / "x.ics").write_text("BEGIN:VCALENDAR\n", encoding="utf-8")
    (raw / "x.pdf").write_bytes(b"%PDF-1.7\n")
    _track_file(raw / "x.ics")
    _track_file(raw / "x.pdf")
    agent = fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/x.md", rel_key, "A fact."))
    report = ingest.ingest()
    assert agent.count == 0 and report.duplicates == []
    (raw / "x.ics").write_text("BEGIN:VCALENDAR\nCHANGED\n", encoding="utf-8")
    report = ingest.ingest()
    assert agent.calls == [("raw/x.ics", "reconcile")] and report.duplicates == []
