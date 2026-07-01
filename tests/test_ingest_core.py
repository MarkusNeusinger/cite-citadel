"""Core ingest flow (offline): the agent's file edits are discovered via the content-hash diff,
validated and re-stamped, indexed and logged; invalid pages roll the whole source back; renamed
pages get their inbound links repaired. ``llm.run_ingest_session`` is replaced by ``fake_agent``.
"""

from __future__ import annotations

from pathlib import Path

from citadel import config, ingest, lint, store, validate


def test_ingest_creates_pages(tmp_citadel, fake_agent, transformer_page):
    """The agent's edits are discovered via the diff, validated + re-stamped, indexed, logged."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    agent = fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    assert agent.count == 1
    assert "raw/notes.md" in report.processed
    assert not report.errors

    page = wiki / "concepts" / "transformer.md"
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "[^s1]" in text
    assert "## Sources" in text
    assert "../../raw/notes.md" in text
    # write_page (the re-stamp) stamps a timestamp into frontmatter.
    assert "timestamp:" in text
    assert "resource: raw/notes.md" in text

    assert "concepts/transformer.md" in report.pages_written
    assert "concepts/transformer.md" in report.pages_created
    assert report.pages_updated == []

    index_text = (wiki / "index.md").read_text(encoding="utf-8")
    assert "transformer.md" in index_text

    log_text = tmp_citadel.log_path.read_text(encoding="utf-8")
    assert "ingest" in log_text and "created" in log_text and "deleted" in log_text

    import json

    manifest_data = json.loads(tmp_citadel.manifest_path.read_text(encoding="utf-8"))["sources"]
    assert "raw/notes.md" in manifest_data


def test_ingest_accepts_bom_prefixed_page(tmp_citadel, fake_agent, transformer_page):
    """A page the agent writes with a leading UTF-8 BOM (the Windows failure mode) is parsed,
    validated, and re-stamped instead of failing the run with 'missing required field' on every
    field. The re-stamp writes the file back WITHOUT the BOM."""
    from citadel import okf

    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    frontmatter, body = transformer_page["concepts/transformer.md"]

    def fake(rel_key, kind="ingest"):
        # Write the page with a leading UTF-8 BOM, exactly as a tool in the chain does on
        # Windows. The frontmatter is well-formed; only the BOM precedes it. This reproduces
        # the run that failed with 'missing required field' on every field of every page —
        # the BOM hid the frontmatter from the parser so it looked empty.
        target = config.WIKI_DIR / "concepts" / "transformer.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\ufeff" + okf.dump(frontmatter, body), encoding="utf-8")

    fake_agent(side_effect=fake)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    assert report.errors == []
    assert "raw/notes.md" in report.processed
    assert "concepts/transformer.md" in report.pages_created

    page = wiki / "concepts" / "transformer.md"
    raw_text = page.read_text(encoding="utf-8")
    # The re-stamp normalized the encoding artifact away and stamped the timestamp.
    assert not raw_text.startswith("\ufeff")
    assert raw_text.startswith("---\n")
    assert "timestamp:" in raw_text
    # The frontmatter survived: it loads with every required field present.
    reread = store.read_page("concepts/transformer.md")
    assert reread.frontmatter["type"] == "Concept"
    assert reread.frontmatter["title"] == "Transformer"
    assert reread.frontmatter["resource"] == "raw/notes.md"
    assert not validate.has_errors(validate.validate_page(reread.rel_path, reread.frontmatter, reread.body))


def test_reingest_is_noop(tmp_citadel, fake_agent, transformer_page):
    """Running ingest twice on the same raw file is idempotent: 2nd processes nothing."""
    raw = tmp_citadel.raw
    agent = fake_agent(transformer_page)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    first = ingest.ingest()
    assert first.processed == ["raw/notes.md"]
    assert agent.count == 1

    second = ingest.ingest()
    assert second.processed == []
    assert "raw/notes.md" in second.skipped
    assert agent.count == 1  # the fake session was NOT run a second time


def test_ingest_distinguishes_created_vs_updated(tmp_citadel, fake_agent, transformer_page):
    """First ingest of a page is a create; re-ingesting (existing page) is an update."""
    raw = tmp_citadel.raw
    fake_agent(transformer_page)

    (raw / "notes.md").write_text("first\n", encoding="utf-8")
    r1 = ingest.ingest()
    assert "concepts/transformer.md" in r1.pages_created
    assert r1.pages_updated == []

    # Change the raw file so it re-ingests; the page now exists -> update, not create.
    (raw / "notes.md").write_text("second, changed\n", encoding="utf-8")
    r2 = ingest.ingest()
    assert "concepts/transformer.md" in r2.pages_updated
    assert r2.pages_created == []


def test_restamp_canonicalizes_and_stamps(tmp_citadel, fake_agent, transformer_page):
    """A page the agent wrote without a timestamp comes out with a system-set timestamp."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    fake_agent(transformer_page)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest()
    assert not report.errors
    text = (wiki / "concepts" / "transformer.md").read_text(encoding="utf-8")
    # Exactly one frontmatter block (open + close), and a stamped timestamp.
    assert text.split("\n").count("---") == 2
    assert text.startswith("---\n")
    assert "timestamp:" in text


def test_embedded_frontmatter_in_body_is_error(tmp_citadel, fake_agent, seed_page):
    """If the agent echoes a second '---' YAML block into the BODY, validation flags it."""
    raw = tmp_citadel.raw

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/echoed.md",
            {"type": "Concept", "title": "Echoed", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "---\ntype: Concept\ntitle: Echoed\n---\n\nA fact.[^s1]\n\n"
            "## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    fake_agent(side_effect=fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert any("embedded_frontmatter" in e for e in report.errors)


def test_ingest_missing_type_rolls_back(tmp_citadel, fake_agent, seed_page):
    """A page the agent wrote with no 'type' fails validation -> the WHOLE source is rolled
    back (all-or-nothing): error collected, source NOT processed, the invalid page is gone,
    and a pre-existing page is left intact."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    seed_page(
        "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/bad.md",
            {"title": "Bad", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    fake_agent(side_effect=fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert "raw/notes.md" not in report.processed  # rolled back -> not marked done
    assert any("invalid page concepts/bad.md" in e and "type" in e for e in report.errors)
    assert not (wiki / "concepts" / "bad.md").exists()  # rolled back, not left behind
    assert (wiki / "concepts" / "keep.md").exists()  # pre-existing page untouched


def test_missing_required_field_rolls_back(tmp_citadel, fake_agent, seed_page):
    """STRICT: a page missing 'tags' (or any required field) fails the gate and the source
    is rolled back (not marked done)."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/notags.md",
            {"type": "Concept", "title": "No Tags", "description": "d", "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    fake_agent(side_effect=fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert any("tags" in e for e in report.errors)
    assert "raw/notes.md" not in report.processed
    assert not (wiki / "concepts" / "notags.md").exists()


def test_ingest_no_changes_marks_done(tmp_citadel, fake_agent):
    """An agent that changes nothing is still 'processed' (and re-runs skip it)."""
    raw = tmp_citadel.raw
    agent = fake_agent()  # records the call, writes nothing
    (raw / "notes.md").write_text("nothing new\n", encoding="utf-8")

    report = ingest.ingest()
    assert "raw/notes.md" in report.processed
    assert report.pages_created == [] and report.pages_updated == [] and report.pages_deleted == []
    assert not report.errors

    second = ingest.ingest()
    assert "raw/notes.md" in second.skipped
    assert agent.count == 1


def test_diff_classifies_created_updated_deleted():
    """Unit test of the content-hash diff."""
    before = {"a.md": "h1", "b.md": "h2", "c.md": "h3"}
    after = {"a.md": "h1", "b.md": "CHANGED", "d.md": "h4"}
    created, updated, deleted = ingest._diff(before, after)
    assert created == ["d.md"]
    assert updated == ["b.md"]
    assert deleted == ["c.md"]


def test_reserved_files_excluded_from_diff(tmp_citadel, fake_agent, seed_page):
    """Even if the agent scribbles on a reserved file, it is excluded from the diff and
    regenerated; only real pages are reported."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/foo.md",
            {"type": "Concept", "title": "Foo", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        (config.WIKI_DIR / "index.md").write_text("GARBAGE the agent should not write\n", encoding="utf-8")

    fake_agent(side_effect=fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert "concepts/foo.md" in report.pages_created
    assert "index.md" not in report.pages_created and "index.md" not in report.pages_updated
    # index.md was regenerated by finalize, not left as the agent's garbage.
    assert (wiki / "index.md").read_text(encoding="utf-8").startswith("# Wiki Index")


def test_agent_merge_repoints_inbound_link(tmp_citadel, fake_agent, seed_page):
    """A merge: the agent writes the survivor, deletes the absorbed page, AND repoints the
    inbound link itself (its job). No broken link remains."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("Self-attention merges attention.\n", encoding="utf-8")

    seed_page(
        "concepts/attention.md",
        {"type": "Concept", "title": "Attention", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
        "Attention is a mechanism.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )
    seed_page(
        "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
        "See [Attention](./attention.md) for details.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )

    def fake(rel_key, kind="ingest"):
        seed_page(
            "concepts/self-attention.md",
            {
                "type": "Concept",
                "title": "Self-Attention",
                "description": "merged",
                "tags": ["ml"],
                "resource": "raw/notes.md",
            },
            "Self-attention subsumes attention.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-22)\n",
        )
        (config.WIKI_DIR / "concepts" / "attention.md").unlink()
        # The agent repoints the inbound link itself.
        seed_page(
            "concepts/linker.md",
            {"type": "Concept", "title": "Linker", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
            "See [Self-Attention](./self-attention.md) for details.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
        )

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert not report.errors
    assert "concepts/self-attention.md" in report.pages_written
    assert "concepts/attention.md" in report.pages_deleted
    assert not (wiki / "concepts" / "attention.md").exists()
    assert (wiki / "concepts" / "self-attention.md").exists()
    linker = (wiki / "concepts" / "linker.md").read_text(encoding="utf-8")
    assert "self-attention.md" in linker and "(./attention.md)" not in linker
    assert report.broken_links == []
    assert lint.lint().broken_links == []


def test_repair_renames_repoints_after_rename(tmp_citadel, fake_agent, seed_page):
    """A pure rename (delete old + create same-title new) where the agent forgot the inbound
    link: the deterministic Python safety net repoints it via store.rewrite_links."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("rename a\n", encoding="utf-8")

    seed_page(
        "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    seed_page(
        "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )

    def fake(rel_key, kind="ingest"):
        # Rename a.md -> aa.md (SAME title 'Alpha'); do NOT touch linker.
        (config.WIKI_DIR / "concepts" / "a.md").unlink()
        seed_page(
            "concepts/aa.md",
            {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
            "Alpha (renamed).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
        )

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "concepts/a.md" in report.pages_deleted
    assert "concepts/aa.md" in report.pages_created
    linker = (wiki / "concepts" / "linker.md").read_text(encoding="utf-8")
    assert "aa.md" in linker and "(./a.md)" not in linker
    assert report.broken_links == []


def test_agent_delete_leaves_broken_link_surfaced(tmp_citadel, fake_agent, seed_page):
    """If the agent deletes a page and forgets an inbound link (and it's not a rename the net
    can fix), the broken link is SURFACED in the report and fails lint."""
    raw = tmp_citadel.raw
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("delete a\n", encoding="utf-8")

    seed_page(
        "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    seed_page(
        "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )

    def fake(rel_key, kind="ingest"):
        (config.WIKI_DIR / "concepts" / "a.md").unlink()  # nothing created in its place

    fake_agent(side_effect=fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "concepts/a.md" in report.pages_deleted
    assert ("concepts/linker.md", "concepts/a.md") in report.broken_links
    assert lint.lint().broken_links != []


def test_contradiction_marker_preserved(tmp_citadel, fake_agent):
    """A contradiction marker the agent wrote survives the validate+restamp and lint flags it."""
    wiki, raw = tmp_citadel.wiki, tmp_citadel.raw
    fake_agent(
        {
            "misc/q3-revenue.md": (
                {
                    "type": "Note",
                    "title": "Q3 Revenue",
                    "description": "Conflicting revenue figures.",
                    "tags": ["finance"],
                    "resource": "raw/a.md",
                },
                "Revenue figures conflict across sources.[^s1][^s2]\n\n"
                "> [!CONTRADICTION]\n"
                "> raw/a.md says revenue grew 12% [^s1]; raw/b.md says it grew 9% [^s2].\n\n"
                "## Sources\n\n"
                "[^s1]: [raw/a.md](../../raw/a.md) - report a (ingested 2026-06-21)\n"
                "[^s2]: [raw/b.md](../../raw/b.md) - report b (ingested 2026-06-21)\n",
            )
        }
    )

    (raw / "a.md").write_text("Revenue grew 12%.\n", encoding="utf-8")
    (raw / "b.md").write_text("Revenue grew 9%.\n", encoding="utf-8")

    report = ingest.ingest()
    assert not report.errors
    assert report.pages_written

    written_rel = report.pages_written[0]
    page = wiki / Path(written_rel)
    assert page.exists()
    text = page.read_text(encoding="utf-8")
    assert "> [!CONTRADICTION]" in text

    lint_report = lint.lint()
    assert written_rel in lint_report.contradictions
