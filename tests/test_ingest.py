"""Offline integration tests for the agentic ingest (no CLI, no network).

``llm.run_ingest_session`` is monkeypatched to a deterministic fake that WRITES FILES into the
temp wiki (simulating the agent editing the wiki directly). This exercises the real
snapshot/diff/validate-and-restamp/rename-repair/rollback path against ``tmp_path`` — a stronger
integration test than stubbing a return value. All filesystem state is redirected to ``tmp_path``
by monkeypatching ``config.*`` (including ``REPO_ROOT``, which is exactly what the agentic
session's ``cwd`` reads), so no real CLI is ever spawned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from okf_wiki import config, ingest, lint, manifest, okf, store, validate


# A counter so tests can assert the fake session runs exactly once per source.
_CALLS: dict[str, int] = {"n": 0}


def _agent_write(rel_path: str, frontmatter: dict, body: str) -> None:
    """Simulate the agent writing a wiki page file directly (no timestamp — the system
    stamps it). Writes canonical OKF via okf.dump into the temp WIKI_DIR."""
    target = config.WIKI_DIR / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


def fake_session_transformer(rel_key, kind="ingest"):
    """Deterministic stand-in for one agentic ingest session: writes a single Concept page
    with a per-fact GFM footnote linking relatively to the raw file + a ## Sources section."""
    _CALLS["n"] += 1
    _agent_write(
        "concepts/transformer.md",
        {
            "type": "Concept",
            "title": "Transformer",
            "description": "self-attention model",
            "tags": ["ml"],
            "resource": "raw/notes.md",
        },
        "Transformers use self-attention.[^s1]\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n",
    )


def fake_session_bom(rel_key, kind="ingest"):
    """A session that writes its page with a leading UTF-8 BOM, exactly as a tool in the
    chain does on Windows. The frontmatter is well-formed; only the BOM precedes it. This
    reproduces the run that failed with 'missing required field' on every field of every
    page — the BOM hid the frontmatter from the parser so it looked empty."""
    _CALLS["n"] += 1
    target = config.WIKI_DIR / "concepts" / "transformer.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    canonical = okf.dump(
        {
            "type": "Concept",
            "title": "Transformer",
            "description": "self-attention model",
            "tags": ["ml"],
            "resource": "raw/notes.md",
        },
        "Transformers use self-attention.[^s1]\n\n"
        "## Sources\n\n"
        "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-21)\n",
    )
    target.write_text("\ufeff" + canonical, encoding="utf-8")


def fake_session_contradiction(rel_key, kind="ingest"):
    """A session that writes a page containing a '> [!CONTRADICTION]' callout (type Note -> misc)."""
    _CALLS["n"] += 1
    _agent_write(
        "misc/q3-revenue.md",
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


def _wire_tmp_wiki(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Redirect all config paths at a fresh tmp wiki/raw layout. Return (wiki, raw)."""
    _CALLS["n"] = 0

    repo = tmp_path
    wiki = repo / "wiki"
    raw = repo / "raw"
    docs = repo / "docs"
    for d in (wiki, raw, docs):
        d.mkdir(parents=True, exist_ok=True)

    # A SCHEMA.md so anything reading config.SCHEMA_PATH works (llm is faked, but be safe).
    schema_path = repo / "SCHEMA.md"
    schema_path.write_text("# SCHEMA\n\ntest schema\n", encoding="utf-8")

    monkeypatch.setattr(config, "REPO_ROOT", repo, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", wiki, raising=False)
    monkeypatch.setattr(config, "RAW_DIR", raw, raising=False)
    monkeypatch.setattr(config, "DOCS_DIR", docs, raising=False)
    monkeypatch.setattr(config, "SCHEMA_PATH", schema_path, raising=False)
    monkeypatch.setattr(config, "AGENT_RULES_PATH", repo / "AGENT_INGEST.md", raising=False)
    monkeypatch.setattr(config, "INDEX_PATH", wiki / "index.md", raising=False)
    monkeypatch.setattr(config, "LOG_PATH", wiki / "log.md", raising=False)
    monkeypatch.setattr(
        config, "MANIFEST_PATH", wiki / ".okf_ingested.json", raising=False
    )
    return wiki, raw


def _seed_page(wiki: Path, rel_path: str, frontmatter: dict, body: str) -> None:
    """Write an OKF page directly under the temp wiki (bypassing ingest)."""
    target = wiki / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(okf.dump(frontmatter, body), encoding="utf-8")


# --- core ingest flow -------------------------------------------------------------------


def test_ingest_creates_pages(tmp_path, monkeypatch):
    """The agent's edits are discovered via the diff, validated + re-stamped, indexed, logged."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()

    assert _CALLS["n"] == 1
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

    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "ingest" in log_text and "created" in log_text and "deleted" in log_text

    import json

    manifest_data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/notes.md" in manifest_data


def test_ingest_accepts_bom_prefixed_page(tmp_path, monkeypatch):
    """A page the agent writes with a leading UTF-8 BOM (the Windows failure mode) is parsed,
    validated, and re-stamped instead of failing the run with 'missing required field' on every
    field. The re-stamp writes the file back WITHOUT the BOM."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_bom)

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
    assert not validate.has_errors(
        validate.validate_page(reread.rel_path, reread.frontmatter, reread.body)
    )


def test_reingest_is_noop(tmp_path, monkeypatch):
    """Running ingest twice on the same raw file is idempotent: 2nd processes nothing."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    first = ingest.ingest()
    assert first.processed == ["raw/notes.md"]
    assert _CALLS["n"] == 1

    second = ingest.ingest()
    assert second.processed == []
    assert "raw/notes.md" in second.skipped
    assert _CALLS["n"] == 1  # the fake session was NOT run a second time


def test_ingest_distinguishes_created_vs_updated(tmp_path, monkeypatch):
    """First ingest of a page is a create; re-ingesting (existing page) is an update."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("first\n", encoding="utf-8")
    r1 = ingest.ingest()
    assert "concepts/transformer.md" in r1.pages_created
    assert r1.pages_updated == []

    # Change the raw file so it re-ingests; the page now exists -> update, not create.
    (raw / "notes.md").write_text("second, changed\n", encoding="utf-8")
    r2 = ingest.ingest()
    assert "concepts/transformer.md" in r2.pages_updated
    assert r2.pages_created == []


def test_restamp_canonicalizes_and_stamps(tmp_path, monkeypatch):
    """A page the agent wrote without a timestamp comes out with a system-set timestamp."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest()
    assert not report.errors
    text = (wiki / "concepts" / "transformer.md").read_text(encoding="utf-8")
    # Exactly one frontmatter block (open + close), and a stamped timestamp.
    assert text.split("\n").count("---") == 2
    assert text.startswith("---\n")
    assert "timestamp:" in text


def test_embedded_frontmatter_in_body_is_error(tmp_path, monkeypatch):
    """If the agent echoes a second '---' YAML block into the BODY, validation flags it."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key, kind="ingest"):
        _agent_write(
            "concepts/echoed.md",
            {
                "type": "Concept",
                "title": "Echoed",
                "description": "d",
                "tags": ["x"],
                "resource": "raw/notes.md",
            },
            "---\ntype: Concept\ntitle: Echoed\n---\n\nA fact.[^s1]\n\n"
            "## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert any("embedded_frontmatter" in e for e in report.errors)


def test_ingest_missing_type_rolls_back(tmp_path, monkeypatch):
    """A page the agent wrote with no 'type' fails validation -> the WHOLE source is rolled
    back (all-or-nothing): error collected, source NOT processed, the invalid page is gone,
    and a pre-existing page is left intact."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        _agent_write(
            "concepts/bad.md",
            {"title": "Bad", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert "raw/notes.md" not in report.processed  # rolled back -> not marked done
    assert any("invalid page concepts/bad.md" in e and "type" in e for e in report.errors)
    assert not (wiki / "concepts" / "bad.md").exists()  # rolled back, not left behind
    assert (wiki / "concepts" / "keep.md").exists()  # pre-existing page untouched


def test_missing_required_field_rolls_back(tmp_path, monkeypatch):
    """STRICT: a page missing 'tags' (or any required field) fails the gate and the source
    is rolled back (not marked done)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key, kind="ingest"):
        _agent_write(
            "concepts/notags.md",
            {"type": "Concept", "title": "No Tags", "description": "d", "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert any("tags" in e for e in report.errors)
    assert "raw/notes.md" not in report.processed
    assert not (wiki / "concepts" / "notags.md").exists()


def test_ingest_no_changes_marks_done(tmp_path, monkeypatch):
    """An agent that changes nothing is still 'processed' (and re-runs skip it)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key, kind="ingest"):
        _CALLS["n"] += 1  # writes nothing

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("nothing new\n", encoding="utf-8")

    report = ingest.ingest()
    assert "raw/notes.md" in report.processed
    assert report.pages_created == [] and report.pages_updated == [] and report.pages_deleted == []
    assert not report.errors

    second = ingest.ingest()
    assert "raw/notes.md" in second.skipped
    assert _CALLS["n"] == 1


# --- arbitrary file types, sub-folders, moves, and binaries -----------------------------


def _make_fake(written: list[str]):
    """A session fake that writes one valid Concept page per source, citing the raw file (which
    may be any type/sub-folder), and records which rel_keys it was driven with."""

    def fake(rel_key: str, kind: str = "ingest") -> None:
        _CALLS["n"] += 1
        written.append(rel_key)
        slug = okf.slugify(rel_key)
        _agent_write(
            f"concepts/{slug}.md",
            {
                "type": "Concept",
                "title": slug,
                "description": "d",
                "tags": ["x"],
                "resource": rel_key,
            },
            f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{rel_key}](../../{rel_key}) - n\n",
        )

    return fake


def _make_pptx(path: Path, slides: list[list[str]]) -> None:
    """Write a minimal real ``.pptx`` (a ZIP of slide XML) at ``path``; ``slides`` is a list of
    slides, each a list of paragraph strings. An empty slide ([]) carries no text."""
    import zipfile

    a = "http://schemas.openxmlformats.org/drawingml/2006/main"
    p = "http://schemas.openxmlformats.org/presentationml/2006/main"
    with zipfile.ZipFile(path, "w") as z:
        for i, paras in enumerate(slides, 1):
            runs = "".join(f"<a:p><a:r><a:t>{t}</a:t></a:r></a:p>" for t in paras)
            z.writestr(
                f"ppt/slides/slide{i}.xml",
                f'<?xml version="1.0"?><p:sld xmlns:p="{p}" xmlns:a="{a}"><p:cSld><p:spTree>'
                f"<p:sp><p:txBody>{runs}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>",
            )


def test_candidates_walks_recursively_and_skips_hidden(tmp_path, monkeypatch):
    """Discovery picks up ANY file type in ANY sub-folder, skipping hidden files/dirs — both for
    the default (whole-raw/) scan and for an explicit directory argument."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("a\n", encoding="utf-8")
    (raw / "sub").mkdir()
    (raw / "sub" / "b.txt").write_text("b\n", encoding="utf-8")
    (raw / "sub" / "c.py").write_text("c\n", encoding="utf-8")
    (raw / ".hidden.md").write_text("h\n", encoding="utf-8")  # hidden file -> skipped
    (raw / ".git").mkdir()
    (raw / ".git" / "config").write_text("x\n", encoding="utf-8")  # hidden dir -> skipped

    expected = {"a.md", "sub/b.txt", "sub/c.py"}
    default = {str(p.relative_to(raw)).replace("\\", "/") for p in ingest._candidates(None)}
    explicit = {str(p.relative_to(raw)).replace("\\", "/") for p in ingest._candidates([str(raw)])}
    assert default == expected
    assert explicit == expected


def test_ingest_discovers_subfolders_and_nonmd(tmp_path, monkeypatch):
    """A .txt at top level and .sql/.py in a sub-folder are all ingested; a hidden file is not."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    written: list[str] = []
    monkeypatch.setattr(ingest.llm, "run_ingest_session", _make_fake(written))

    (raw / "top.txt").write_text("top level text source\n", encoding="utf-8")
    (raw / "code").mkdir()
    (raw / "code" / "query.sql").write_text("SELECT 1; -- a fact\n", encoding="utf-8")
    (raw / "code" / "script.py").write_text("# a python fact\nprint('hi')\n", encoding="utf-8")
    (raw / ".gitkeep").write_text("", encoding="utf-8")

    report = ingest.ingest()
    assert set(report.processed) == {"raw/top.txt", "raw/code/query.sql", "raw/code/script.py"}
    assert "raw/.gitkeep" not in report.processed
    assert len(report.pages_created) == 3
    assert not report.errors
    assert lint.lint().ok()


def test_is_ingestible_classifies_text_pdf_binary(tmp_path, monkeypatch):
    """Text/code/UTF-8/empty/PDF are ingestible; a NUL byte or a high non-text ratio is not."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def mk(name, data):
        p = raw / name
        p.write_bytes(data)
        return p

    assert ingest._is_ingestible(mk("a.txt", b"plain text\n"))
    assert ingest._is_ingestible(mk("a.py", b"print('hi')\n"))
    assert ingest._is_ingestible(mk("u.md", "Café — résumé ☕\n".encode("utf-8")))
    assert ingest._is_ingestible(mk("a.pdf", b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\nstuff"))
    assert ingest._is_ingestible(mk("empty", b""))
    assert not ingest._is_ingestible(mk("nul.bin", b"text\x00more\x00data"))
    assert not ingest._is_ingestible(mk("ctrl.bin", bytes([1, 2, 3, 4, 5, 6, 16, 17, 18, 19]) * 50))


def test_binary_raw_file_is_logged_unreadable_not_ingested(tmp_path, monkeypatch):
    """A binary blob is filtered out before the agent, surfaced as unreadable, logged in log.md,
    and marked done so a re-run neither re-checks nor re-logs it — without failing the run."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "blob.bin").write_bytes(b"\x00\x01\x02\x03BINARY\xff\xfe\x00")
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    report = ingest.ingest()
    assert _CALLS["n"] == 1  # only the readable text file ran a session
    assert "raw/notes.md" in report.processed
    assert "raw/blob.bin" in report.unreadable
    assert "raw/blob.bin" not in report.processed
    assert not report.errors  # unreadable is logged, NOT a hard error

    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "raw/blob.bin" in log_text and "no readable text" in log_text

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/blob.bin" in data  # marked done

    second = ingest.ingest()
    assert "raw/blob.bin" in second.skipped
    assert second.unreadable == []
    assert _CALLS["n"] == 1  # not re-run


def test_partition_classifies_office_text_vs_textless_once(tmp_path, monkeypatch):
    """Office routing lives in _partition_sources: a deck with extractable text is pending (and its
    text is cached for the agent step), a text-free deck is unreadable like any other binary — and
    the file is parsed exactly once (the cache is what avoids a second parse)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _make_pptx(raw / "withtext.pptx", [["A real fact."]])
    _make_pptx(raw / "notext.pptx", [[]])

    pending, skipped, moved, unreadable, deleted, office_text = ingest._partition_sources(None, {})

    pending_keys = {manifest.rel_key(p) for p in pending}
    unreadable_keys = {manifest.rel_key(p) for p in unreadable}
    assert "raw/withtext.pptx" in pending_keys
    assert "raw/notext.pptx" in unreadable_keys
    # The extracted text is cached so the agent step reuses it (no second ZIP/XML parse).
    assert any("A real fact." in t for t in office_text.values())
    assert all(isinstance(p, Path) for p in office_text)   # keyed by the pending Path objects


def test_office_pptx_extracted_to_temp_and_ingested(tmp_path, monkeypatch):
    """A .pptx (binary the agent can't open) is extracted to a temp .md the agent READS, while the
    wiki cites the ORIGINAL .pptx as its source. The temp file is cleaned up after the session."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _make_pptx(raw / "deck.pptx", [["Transformers use self-attention.", "Key idea: attention."]])

    seen: dict[str, object] = {}

    def fake(rel_key, kind="ingest", read_path=None):
        _CALLS["n"] += 1
        seen.update(rel_key=rel_key, kind=kind, read_path=read_path)
        # The agent is pointed at the EXTRACTED text, not the binary; it must exist right now.
        assert read_path is not None
        seen["extracted"] = Path(read_path).read_text(encoding="utf-8")
        _agent_write(
            "concepts/transformer.md",
            {"type": "Concept", "title": "Transformer", "description": "d", "tags": ["ml"],
             "resource": rel_key},
            f"Transformers use self-attention.[^s1]\n\n## Sources\n\n"
            f"[^s1]: [{rel_key}](../../{rel_key}) - deck (ingested 2026-06-21)\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    report = ingest.ingest()

    assert report.processed == ["raw/deck.pptx"]   # keyed by the original Office file
    assert not report.errors
    assert seen["rel_key"] == "raw/deck.pptx" and seen["kind"] == "ingest"
    assert "self-attention" in str(seen["extracted"]).lower()
    assert "## Slide 1" in str(seen["extracted"])   # the extractor's structure reached the agent

    page = wiki / "concepts" / "transformer.md"
    assert page.exists()
    assert "resource: raw/deck.pptx" in page.read_text(encoding="utf-8")  # cites the .pptx
    assert lint.lint().ok() and lint.lint().bad_sources == []

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/deck.pptx" in data

    # The extracted-text temp dir/file is removed once the session is done (no litter).
    assert not Path(str(seen["read_path"])).exists()

    # Re-running is idempotent on the .pptx key (no second extraction/session).
    assert ingest.ingest().processed == []
    assert _CALLS["n"] == 1


def test_office_deck_without_text_is_unreadable(tmp_path, monkeypatch):
    """An all-images .pptx (no extractable text) is logged unreadable and never fed to the agent —
    no wasted session, marked done so a re-run does not re-check it."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _make_pptx(raw / "images.pptx", [[]])  # a slide with no text runs

    def fake(rel_key, kind="ingest", read_path=None):
        raise AssertionError(f"no session should run for a text-free deck (got {rel_key})")

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    report = ingest.ingest()
    assert "raw/images.pptx" in report.unreadable
    assert report.processed == [] and not report.errors

    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "raw/images.pptx" in log_text and "no readable text" in log_text

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/images.pptx" in data  # marked done


def test_moved_raw_file_is_recognized_not_reingested(tmp_path, monkeypatch):
    """Reorganizing a raw file (same bytes, new path) is recognized: NOT re-ingested, the manifest
    is re-keyed, and the wiki's resource/citation references are repointed so lint stays clean."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    first = ingest.ingest()
    assert first.processed == ["raw/notes.md"] and _CALLS["n"] == 1
    page = wiki / "concepts" / "transformer.md"
    assert "../../raw/notes.md" in page.read_text(encoding="utf-8")

    # Move the source into a sub-folder (byte-for-byte identical content).
    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "notes.md").unlink()

    second = ingest.ingest()
    assert _CALLS["n"] == 1  # NOT re-ingested
    assert second.processed == []
    assert ("raw/notes.md", "raw/ml/notes.md") in second.moved
    assert not second.errors

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/ml/notes.md" in data and "raw/notes.md" not in data  # re-keyed

    text = page.read_text(encoding="utf-8")
    assert "resource: raw/ml/notes.md" in text
    assert "../../raw/ml/notes.md" in text
    assert "(../../raw/notes.md)" not in text
    assert lint.lint().ok() and lint.lint().bad_sources == []

    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "raw/ml/notes.md" in log_text and "moved" in log_text


def test_duplicate_raw_file_not_reingested(tmp_path, monkeypatch):
    """A byte-for-byte COPY at a new path (original still present) is recognized as already-known
    content and not re-ingested; the original's references are left intact (no repoint)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()
    assert _CALLS["n"] == 1

    (raw / "copy.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    report = ingest.ingest()
    assert _CALLS["n"] == 1
    assert ("raw/notes.md", "raw/copy.md") in report.moved

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/notes.md" in data and "raw/copy.md" in data  # both tracked

    text = (wiki / "concepts" / "transformer.md").read_text(encoding="utf-8")
    assert "resource: raw/notes.md" in text  # original NOT repointed (still on disk)
    assert lint.lint().ok()


def test_rewrite_raw_references_repoints_resource_and_citation(tmp_path, monkeypatch):
    """store.rewrite_raw_references repoints the `resource` frontmatter and real citation links to
    a moved source, leaving a literal link inside a code fence untouched."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("x\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/t.md",
        {"type": "Concept", "title": "T", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
        "A fact.[^s1]\n\n"
        "```\n"
        "example: [old](../../raw/notes.md)\n"  # fenced literal -> untouched
        "```\n\n"
        "## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
    )

    changed = store.rewrite_raw_references("raw/notes.md", "raw/ml/notes.md")
    assert changed == ["concepts/t.md"]
    text = (wiki / "concepts" / "t.md").read_text(encoding="utf-8")
    assert "resource: raw/ml/notes.md" in text
    assert "[^s1]: [raw/notes.md](../../raw/ml/notes.md)" in text  # real citation repointed
    assert "example: [old](../../raw/notes.md)" in text  # fenced literal left intact


def test_file_sha256_streams_and_matches_oneshot(tmp_path):
    """The chunk-streamed hash equals a one-shot hash of the whole bytes (memory-bounded, but
    identical digest), across multiple read chunks."""
    import hashlib

    data = bytes(range(256)) * 9000  # ~2.3 MiB -> several 1 MiB chunks
    p = tmp_path / "big.bin"
    p.write_bytes(data)
    assert manifest.file_sha256(p) == hashlib.sha256(data).hexdigest()


def test_unreadable_already_ingested_file_does_not_crash(tmp_path, monkeypatch):
    """An already-tracked raw file that becomes unreadable makes is_pending() (which hashes a
    tracked file) raise OSError — that must NOT crash the run: it stays classified as skipped,
    since it is already in the wiki."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    assert ingest.ingest().processed == ["raw/notes.md"]

    real = ingest.manifest.file_sha256

    def boom(path):
        if str(path).endswith("notes.md"):
            raise OSError("permission denied")
        return real(path)

    monkeypatch.setattr(ingest.manifest, "file_sha256", boom)

    report = ingest.ingest()  # must not raise
    assert "raw/notes.md" in report.skipped
    assert report.processed == []
    assert not report.errors


def test_diff_classifies_created_updated_deleted():
    """Unit test of the content-hash diff."""
    before = {"a.md": "h1", "b.md": "h2", "c.md": "h3"}
    after = {"a.md": "h1", "b.md": "CHANGED", "d.md": "h4"}
    created, updated, deleted = ingest._diff(before, after)
    assert created == ["d.md"]
    assert updated == ["b.md"]
    assert deleted == ["c.md"]


def test_reserved_files_excluded_from_diff(tmp_path, monkeypatch):
    """Even if the agent scribbles on a reserved file, it is excluded from the diff and
    regenerated; only real pages are reported."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)

    def fake(rel_key, kind="ingest"):
        _agent_write(
            "concepts/foo.md",
            {"type": "Concept", "title": "Foo", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        (config.WIKI_DIR / "index.md").write_text("GARBAGE the agent should not write\n", encoding="utf-8")

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    report = ingest.ingest([str(raw / "notes.md")])
    assert "concepts/foo.md" in report.pages_created
    assert "index.md" not in report.pages_created and "index.md" not in report.pages_updated
    # index.md was regenerated by finalize, not left as the agent's garbage.
    assert (wiki / "index.md").read_text(encoding="utf-8").startswith("# Wiki Index")


def test_agent_merge_repoints_inbound_link(tmp_path, monkeypatch):
    """A merge: the agent writes the survivor, deletes the absorbed page, AND repoints the
    inbound link itself (its job). No broken link remains."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("Self-attention merges attention.\n", encoding="utf-8")

    _seed_page(
        wiki, "concepts/attention.md",
        {"type": "Concept", "title": "Attention", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
        "Attention is a mechanism.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )
    _seed_page(
        wiki, "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
        "See [Attention](./attention.md) for details.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
    )

    def fake(rel_key, kind="ingest"):
        _agent_write(
            "concepts/self-attention.md",
            {"type": "Concept", "title": "Self-Attention", "description": "merged", "tags": ["ml"], "resource": "raw/notes.md"},
            "Self-attention subsumes attention.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/notes.md](../../raw/notes.md) - notes (ingested 2026-06-22)\n",
        )
        (config.WIKI_DIR / "concepts" / "attention.md").unlink()
        # The agent repoints the inbound link itself.
        _agent_write(
            "concepts/linker.md",
            {"type": "Concept", "title": "Linker", "description": "d", "tags": ["ml"], "resource": "raw/old.md"},
            "See [Self-Attention](./self-attention.md) for details.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/old.md](../../raw/old.md) - old (ingested 2026-06-21)\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
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


def test_repair_renames_repoints_after_rename(tmp_path, monkeypatch):
    """A pure rename (delete old + create same-title new) where the agent forgot the inbound
    link: the deterministic Python safety net repoints it via store.rewrite_links."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("rename a\n", encoding="utf-8")

    _seed_page(
        wiki, "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    _seed_page(
        wiki, "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )

    def fake(rel_key, kind="ingest"):
        # Rename a.md -> aa.md (SAME title 'Alpha'); do NOT touch linker.
        (config.WIKI_DIR / "concepts" / "a.md").unlink()
        _agent_write(
            "concepts/aa.md",
            {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
            "Alpha (renamed).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "concepts/a.md" in report.pages_deleted
    assert "concepts/aa.md" in report.pages_created
    linker = (wiki / "concepts" / "linker.md").read_text(encoding="utf-8")
    assert "aa.md" in linker and "(./a.md)" not in linker
    assert report.broken_links == []


def test_agent_delete_leaves_broken_link_surfaced(tmp_path, monkeypatch):
    """If the agent deletes a page and forgets an inbound link (and it's not a rename the net
    can fix), the broken link is SURFACED in the report and fails lint."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("delete a\n", encoding="utf-8")

    _seed_page(
        wiki, "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    _seed_page(
        wiki, "concepts/linker.md",
        {"type": "Concept", "title": "Linker", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )

    def fake(rel_key, kind="ingest"):
        (config.WIKI_DIR / "concepts" / "a.md").unlink()  # nothing created in its place

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "concepts/a.md" in report.pages_deleted
    assert ("concepts/linker.md", "concepts/a.md") in report.broken_links
    assert lint.lint().broken_links != []


def test_failed_session_rolls_back(tmp_path, monkeypatch):
    """A session that raises after a partial write is rolled back: the wiki returns to its
    pre-source state, the source is NOT marked done, and the error is collected."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        _agent_write(
            "concepts/partial.md",
            {"type": "Concept", "title": "Partial", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "Half-written.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        raise RuntimeError("boom mid-session")

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    report = ingest.ingest([str(raw / "notes.md")])

    assert "raw/notes.md" not in report.processed
    assert any("boom mid-session" in e for e in report.errors)
    assert not (wiki / "concepts" / "partial.md").exists()  # rolled back
    assert (wiki / "concepts" / "keep.md").exists()  # untouched

    # Source is retried next run (not in the manifest).
    import json

    manifest_path = wiki / ".okf_ingested.json"
    if manifest_path.exists():
        assert "raw/notes.md" not in json.loads(manifest_path.read_text(encoding="utf-8"))


def test_keyboardinterrupt_rolls_back_current_source(tmp_path, monkeypatch):
    """A Ctrl+C (KeyboardInterrupt) raised mid-session must roll the wiki back to its
    pre-source state, then propagate. KeyboardInterrupt is a BaseException, so the per-source
    `except Exception` does NOT catch it — the rollback lives in `finally` (guarded by a
    success flag), which a BaseException still runs on its way out."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/old.md"},
        "Keep me.[^s1]\n\n## Sources\n\n[^s1]: [raw/old.md](../../raw/old.md) - o\n",
    )
    (raw / "old.md").write_text("x\n", encoding="utf-8")
    (raw / "notes.md").write_text("x\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        _agent_write(
            "concepts/partial.md",
            {"type": "Concept", "title": "Partial", "description": "d", "tags": ["x"], "resource": "raw/notes.md"},
            "Half-written.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )
        raise KeyboardInterrupt()

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest([str(raw / "notes.md")])

    assert not (wiki / "concepts" / "partial.md").exists()  # rolled back on the interrupt
    assert (wiki / "concepts" / "keep.md").exists()         # pre-existing page untouched


def test_completed_sources_persisted_before_interrupt(tmp_path, monkeypatch):
    """Progress is written to the manifest right after each source completes, so a Ctrl+C
    during a LATER source can't erase already-finished work. (The old code saved the manifest
    only in finalization, which a propagating KeyboardInterrupt skipped entirely.)"""
    import json

    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("first\n", encoding="utf-8")
    (raw / "b.md").write_text("second\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        if rel_key == "raw/a.md":
            _agent_write(
                "concepts/from-a.md",
                {"type": "Concept", "title": "From A", "description": "d", "tags": ["x"], "resource": "raw/a.md"},
                "Fact A.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n",
            )
        else:  # raw/b.md — interrupt mid-session, after a.md already finished
            raise KeyboardInterrupt()

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest()  # processes raw/a.md then raw/b.md (sorted order)

    manifest_path = wiki / ".okf_ingested.json"
    assert manifest_path.exists()  # saved incrementally, not only at finalization
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "raw/a.md" in data       # a finished -> persisted before the interrupt
    assert "raw/b.md" not in data   # b interrupted -> not marked done
    assert (wiki / "concepts" / "from-a.md").exists()  # a's page survived b's rollback


def test_finalization_runs_for_completed_sources_on_interrupt(tmp_path, monkeypatch):
    """If a Ctrl+C interrupts the run after some sources already completed, the derived files
    (indexes + log) for that completed work are still rebuilt before the interrupt propagates.
    Otherwise — since the manifest is now persisted per-source — a later run could find nothing
    pending, skip finalization entirely, and leave the wiki's indexes/log permanently stale."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("first\n", encoding="utf-8")
    (raw / "b.md").write_text("second\n", encoding="utf-8")

    def fake(rel_key, kind="ingest"):
        if rel_key == "raw/a.md":
            _agent_write(
                "concepts/from-a.md",
                {"type": "Concept", "title": "From A", "description": "d", "tags": ["x"], "resource": "raw/a.md"},
                "Fact A.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - a\n",
            )
        else:  # raw/b.md interrupts after a is already done
            raise KeyboardInterrupt()

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)
    with pytest.raises(KeyboardInterrupt):
        ingest.ingest()

    # a's page is committed AND the indexes/log were rebuilt despite the interrupt — so the
    # wiki is not stranded with content the navigation files don't reflect.
    assert (wiki / "concepts" / "from-a.md").exists()
    assert "from-a.md" in (wiki / "index.md").read_text(encoding="utf-8")
    assert (wiki / "log.md").exists()


def test_contradiction_marker_preserved(tmp_path, monkeypatch):
    """A contradiction marker the agent wrote survives the validate+restamp and lint flags it."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_contradiction)

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


# --- changed + deleted raw-source propagation -------------------------------------------


def test_changed_source_runs_reconcile_not_plain_ingest(tmp_path, monkeypatch):
    """A NEW source runs with kind='ingest'; re-ingesting it after its bytes change runs with
    kind='reconcile' (so the agent updates/removes stale facts instead of only appending)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    seen: list[tuple[str, str]] = []

    def fake(rel_key, kind="ingest"):
        seen.append((rel_key, kind))
        _agent_write(
            "concepts/transformer.md",
            {"type": "Concept", "title": "Transformer", "description": "d", "tags": ["ml"], "resource": "raw/notes.md"},
            "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    (raw / "notes.md").write_text("first\n", encoding="utf-8")
    ingest.ingest()
    assert seen == [("raw/notes.md", "ingest")]  # brand new -> plain ingest

    (raw / "notes.md").write_text("second, corrected\n", encoding="utf-8")
    ingest.ingest()
    assert seen[-1] == ("raw/notes.md", "reconcile")  # changed bytes -> reconcile


def test_deleted_source_citations_reconciled_out(tmp_path, monkeypatch):
    """A tracked raw file that vanished from disk triggers a kind='delete' cleanup session: the
    page it solely sourced is removed, its manifest key is dropped, and lint stays clean."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/gone.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    manifest.save({"raw/gone.md": "deadbeef"})  # tracked, but the file is NOT on disk

    calls: list[tuple[str, str]] = []

    def fake(rel_key, kind="ingest"):
        calls.append((rel_key, kind))
        # The deleted source was this page's only provenance -> remove the page entirely.
        (config.WIKI_DIR / "concepts" / "topic.md").unlink()

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    report = ingest.ingest()

    assert calls == [("raw/gone.md", "delete")]  # exactly one delete-cleanup session
    assert report.sources_deleted == ["raw/gone.md"]
    assert "concepts/topic.md" in report.pages_deleted
    assert not (wiki / "concepts" / "topic.md").exists()
    assert not report.errors

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/gone.md" not in data  # manifest key dropped
    assert lint.lint().ok() and lint.lint().bad_sources == []

    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "raw/gone.md" in log_text and "deleted" in log_text


def test_deleted_source_drops_one_citation_keeps_corroborated_fact(tmp_path, monkeypatch):
    """When a deleted source co-cited a fact that ANOTHER source also supports, the cleanup
    drops only the deleted source's marker/definition and keeps the fact + the survivor cite."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "keep.md").write_text("keep\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/dual.md",
        {"type": "Concept", "title": "Dual", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
        "A corroborated fact.[^s1][^s2]\n\n## Sources\n\n"
        "[^s1]: [raw/keep.md](../../raw/keep.md) - k\n"
        "[^s2]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    manifest.save({"raw/keep.md": manifest.file_sha256(raw / "keep.md"), "raw/gone.md": "deadbeef"})

    def fake(rel_key, kind="ingest"):
        assert (rel_key, kind) == ("raw/gone.md", "delete")
        # Keep the fact + [^s1]/keep.md; remove only [^s2] and its gone.md definition.
        _agent_write(
            "concepts/dual.md",
            {"type": "Concept", "title": "Dual", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
            "A corroborated fact.[^s1]\n\n## Sources\n\n"
            "[^s1]: [raw/keep.md](../../raw/keep.md) - k\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    report = ingest.ingest()

    assert report.sources_deleted == ["raw/gone.md"]
    assert "concepts/dual.md" in report.pages_updated
    text = (wiki / "concepts" / "dual.md").read_text(encoding="utf-8")
    assert "corroborated fact" in text and "[^s1]" in text  # fact + survivor cite kept
    assert "gone.md" not in text and "[^s2]" not in text    # deleted source's cite removed
    assert lint.lint().ok()
    assert store.find_raw_references("raw/gone.md") == []


def test_deleted_source_with_no_references_just_dropped(tmp_path, monkeypatch):
    """A deleted source nothing cites needs no agent session — its manifest key is simply
    dropped, and an unrelated page citing a still-present source is left untouched."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "keep.md").write_text("keep\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/keep.md",
        {"type": "Concept", "title": "Keep", "description": "d", "tags": ["x"], "resource": "raw/keep.md"},
        "Kept.[^s1]\n\n## Sources\n\n[^s1]: [raw/keep.md](../../raw/keep.md) - k\n",
    )
    manifest.save({"raw/keep.md": manifest.file_sha256(raw / "keep.md"), "raw/gone.md": "deadbeef"})

    def fake(rel_key, kind="ingest"):
        raise AssertionError(f"no session should run (got {rel_key}, {kind})")

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    report = ingest.ingest()

    assert report.sources_deleted == ["raw/gone.md"]
    assert report.processed == [] and not report.errors
    assert (wiki / "concepts" / "keep.md").exists()  # unrelated page untouched

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/gone.md" not in data and "raw/keep.md" in data


def test_deleted_cleanup_incomplete_rolls_back_and_retries(tmp_path, monkeypatch):
    """If the cleanup session fails to remove every reference to the deleted source, the
    post-condition fails: the whole source is rolled back, an error is collected, and the
    manifest key is KEPT so it is retried next run (no half-cleaned wiki)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/gone.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    manifest.save({"raw/gone.md": "deadbeef"})

    def fake(rel_key, kind="ingest"):
        pass  # agent does nothing -> the gone.md citation survives

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    report = ingest.ingest()

    assert report.sources_deleted == []  # not completed
    assert any("still cited" in e for e in report.errors)
    assert (wiki / "concepts" / "topic.md").exists()  # rolled back, page intact

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/gone.md" in data  # key kept -> retried next run


def test_deletion_swept_only_on_full_run_not_path_scoped(tmp_path, monkeypatch):
    """A path-scoped ingest must NOT sweep the whole manifest for deletions — only a full run
    (no paths) reconciles a vanished source, so `ingest <one-file>` can't surprise-prune."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["x"], "resource": "raw/gone.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/gone.md](../../raw/gone.md) - g\n",
    )
    (raw / "new.md").write_text("new source\n", encoding="utf-8")
    manifest.save({"raw/gone.md": "deadbeef"})

    seen: list[tuple[str, str]] = []

    def fake(rel_key, kind="ingest"):
        seen.append((rel_key, kind))
        _agent_write(
            "concepts/new.md",
            {"type": "Concept", "title": "New", "description": "d", "tags": ["x"], "resource": "raw/new.md"},
            "New.[^s1]\n\n## Sources\n\n[^s1]: [raw/new.md](../../raw/new.md) - n\n",
        )

    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake)

    report = ingest.ingest([str(raw / "new.md")])  # scoped to one file

    assert seen == [("raw/new.md", "ingest")]  # only the targeted file ran; no delete session
    assert report.sources_deleted == []
    assert (wiki / "concepts" / "topic.md").exists()  # the deleted source's page is untouched

    import json

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/gone.md" in data  # still tracked; not pruned by a scoped run


def test_moved_source_not_treated_as_deletion(tmp_path, monkeypatch):
    """A reorganized file (old path gone, same bytes at a new path) is a MOVE, not a deletion:
    its references are repointed, no delete-cleanup session runs, and the page survives."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()
    assert _CALLS["n"] == 1

    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "notes.md").unlink()

    report = ingest.ingest()
    assert _CALLS["n"] == 1  # no session at all — neither re-ingest nor delete-cleanup
    assert report.sources_deleted == []  # the gone old path is a move, not a deletion
    assert ("raw/notes.md", "raw/ml/notes.md") in report.moved
    assert (wiki / "concepts" / "transformer.md").exists()
    assert lint.lint().ok()


def test_find_raw_references_matches_resource_and_citation_skips_fence(tmp_path, monkeypatch):
    """store.find_raw_references finds pages via `resource` frontmatter OR a real citation link,
    and ignores a citation written as a literal inside a code fence (a format-doc example)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/by-resource.md",
        {"type": "Concept", "title": "By Resource", "description": "d", "tags": ["x"], "resource": "raw/target.md"},
        "Body.[^s1]\n\n## Sources\n\n[^s1]: [raw/target.md](../../raw/target.md) - t\n",
    )
    _seed_page(
        wiki, "concepts/by-citation.md",
        {"type": "Concept", "title": "By Citation", "description": "d", "tags": ["x"], "resource": "raw/other.md"},
        "Body.[^s1]\n\n## Sources\n\n[^s1]: [raw/target.md](../../raw/target.md) - t\n",
    )
    _seed_page(
        wiki, "concepts/fence-only.md",
        {"type": "Concept", "title": "Fence Only", "description": "d", "tags": ["x"], "resource": "raw/other.md"},
        "Example:\n\n```\n[^s1]: [raw/target.md](../../raw/target.md)\n```\n\n"
        "Body.[^s1]\n\n## Sources\n\n[^s1]: [raw/other.md](../../raw/other.md) - o\n",
    )

    hits = store.find_raw_references("raw/target.md")
    assert hits == ["concepts/by-citation.md", "concepts/by-resource.md"]
    assert "concepts/fence-only.md" not in hits  # fenced literal not counted


# --- progress reporting -----------------------------------------------------------------


def test_ingest_emits_progress_events(tmp_path, monkeypatch):
    """ingest() drives a progress callback: start -> source_start/done -> finalize -> done."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)
    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")

    events = []
    ingest.ingest(progress=lambda ev, data: events.append((ev, data)))

    names = [e for e, _ in events]
    assert names[0] == "start"
    for expected in ("source_start", "source_done", "finalize", "done"):
        assert expected in names, f"missing event: {expected}"
    start = next(d for e, d in events if e == "start")
    assert start == {"pending": 1, "skipped": 0, "moved": 0, "unreadable": 0, "deleted": 0}
    done = next(d for e, d in events if e == "source_done")
    assert done["source"] == "raw/notes.md"
    assert done["index"] == 1 and done["total"] == 1
    assert done["created"] == 1 and done["updated"] == 0
    assert "seconds" in done


def test_ingest_progress_default_is_silent(tmp_path, monkeypatch):
    """No progress arg -> no callback invoked (MCP/non-interactive path stays quiet)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)
    (raw / "notes.md").write_text("x\n", encoding="utf-8")
    report = ingest.ingest()  # must not raise without a progress callback
    assert "raw/notes.md" in report.processed


def test_console_progress_renders_ascii_without_tty():
    """ConsoleProgress on a non-TTY stream prints one plain line per file, ASCII-only."""
    import io
    from okf_wiki.progress import ConsoleProgress

    buf = io.StringIO()  # isatty() -> False, so no spinner thread
    p = ConsoleProgress(stream=buf)
    p("start", {"pending": 2, "skipped": 1})
    p("source_start", {"index": 1, "total": 2, "source": "raw/a.md"})
    p("source_done", {"index": 1, "total": 2, "source": "raw/a.md",
                      "created": 2, "updated": 1, "deleted": 1, "seconds": 12.4})
    p("source_error", {"index": 2, "total": 2, "source": "raw/b.md",
                       "error": "boom", "seconds": 1.0})
    p("finalize", {})
    out = buf.getvalue()

    assert "Ingesting 2 file(s) (1 already up to date)" in out
    assert "[1/2] OK  raw/a.md" in out and "2 created, 1 updated, 1 deleted" in out
    assert "[2/2] ERR raw/b.md" in out and "boom" in out
    assert "Rebuilding indexes" in out
    out.encode("ascii")  # must be ASCII-only (safe on any Windows code page)


# --- lint / store / okf-compliance (independent of the ingest mechanism) ----------------


def test_lint_flags_fabricated_source(tmp_path, monkeypatch):
    """A page citing a raw file that does not exist is flagged and flips lint.ok()."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki,
        "concepts/made-up.md",
        {"type": "Concept", "title": "Made Up", "resource": "raw/ghost.md"},
        "An uncited-source fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/ghost.md](../../raw/ghost.md) - ghost (ingested 2026-06-22)\n",
    )
    report = lint.lint()
    assert ("concepts/made-up.md", "../../raw/ghost.md") in report.bad_sources
    assert not report.ok()


def test_lint_clean_when_source_exists(tmp_path, monkeypatch):
    """The same page passes once its cited raw file actually exists."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "real.md").write_text("real source\n", encoding="utf-8")
    _seed_page(
        wiki,
        "concepts/grounded.md",
        {"type": "Concept", "title": "Grounded", "resource": "raw/real.md"},
        "A grounded fact.[^s1]\n\n## Sources\n\n"
        "[^s1]: [raw/real.md](../../raw/real.md) - real (ingested 2026-06-22)\n",
    )
    report = lint.lint()
    assert report.bad_sources == []


def test_lint_flags_wikilink(tmp_path, monkeypatch):
    """A [[wiki-style]] link is flagged and flips lint.ok()."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("src\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/wikilinked.md",
        {"type": "Concept", "title": "Wikilinked", "resource": "raw/a.md"},
        "See [[Some Page]] for more.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    report = lint.lint()
    assert ("concepts/wikilinked.md", "Some Page") in report.wikilinks
    assert not report.ok()


def test_rewrite_links_skips_code_fences_and_substrings():
    """The link rewrite touches only genuine link spans: a literal ](old) inside a fenced
    code block is left intact, and only the real cross-link is repointed."""
    body = (
        "See [Old](./old.md) for details.\n\n"
        "```\n"
        "documented syntax: [X](./old.md)\n"
        "```\n\n"
        "End.\n"
    )
    out = store._rewrite_body_links(
        "concepts/page.md", body, {"concepts/old.md": "concepts/new.md"}
    )
    assert "[Old](new.md)" in out          # real link repointed
    assert "[X](./old.md)" in out          # fenced literal left intact
    assert out.count("(new.md)") == 1


def test_lint_allows_and_surfaces_llm_sourced_fact(tmp_path, monkeypatch):
    """A model-supplied [^llmN] fact is NOT flagged as fabricated, but IS surfaced under
    llm_facts for transparency; the page still passes lint."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/with-llm.md",
        {"type": "Concept", "title": "With LLM", "resource": "raw/real.md"},
        "An essential, high-confidence model fact.[^llm1]\n\n## Sources\n\n"
        "[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-22)\n",
    )
    report = lint.lint()
    assert report.bad_sources == []
    assert "concepts/with-llm.md" in report.llm_facts
    assert report.ok()


def test_lint_flags_bare_and_undefined_sources(tmp_path, monkeypatch):
    """A bare-path (un-linked) source def and a used-but-undefined marker are both flagged."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/sloppy.md",
        {"type": "Concept", "title": "Sloppy", "resource": "raw/x.md"},
        "Fact one.[^s1] Fact two.[^s2]\n\n## Sources\n\n"
        "[^s1]: raw/x.md (ingested 2026-06-22)\n",  # bare path, no markdown link; s2 undefined
    )
    report = lint.lint()
    details = [t for r, t in report.bad_sources if r == "concepts/sloppy.md"]
    assert any("no resolvable source link" in d for d in details)
    assert any("[^s2] used but undefined" in d for d in details)
    assert not report.ok()


def test_lint_tolerates_link_title_and_code_fences(tmp_path, monkeypatch):
    """A link title in a Sources def, and an example def inside a code fence, do not cause
    false-positive fabricated-source failures."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "x.md").write_text("src\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/titled.md",
        {"type": "Concept", "title": "Titled", "resource": "raw/x.md"},
        'A fact.[^s1]\n\n'
        '```\n'
        '[^sN]: [raw/example.md](../../raw/example.md) - how to cite\n'
        '```\n\n'
        '## Sources\n\n'
        '[^s1]: [raw/x.md](../../raw/x.md "the title") - note (ingested 2026-06-22)\n',
    )
    report = lint.lint()
    assert report.bad_sources == []
    assert report.ok()


def test_indexes_have_no_frontmatter(tmp_path, monkeypatch):
    """OKF: index.md (top + per-folder) must NOT carry YAML frontmatter."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"]},
        "Alpha body.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    store.rebuild_indexes()
    top = (wiki / "index.md").read_text(encoding="utf-8")
    folder = (wiki / "concepts" / "index.md").read_text(encoding="utf-8")
    assert top.startswith("# Wiki Index") and not top.startswith("---")
    assert "type: Index" not in top
    assert folder.startswith("# concepts") and not folder.startswith("---")
    assert "## Tags" in top and "### x (1)" in top
    assert not (wiki / "tags.md").exists()


def test_index_shows_backlinks(tmp_path, monkeypatch):
    """The top index lists who references each page (the backlink graph)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/a.md", {"type": "Concept", "title": "Alpha", "resource": "raw/a.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    _seed_page(
        wiki, "concepts/b.md", {"type": "Concept", "title": "Beta", "resource": "raw/a.md"},
        "See [Alpha](./a.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    store.rebuild_indexes()
    top = (wiki / "index.md").read_text(encoding="utf-8")
    assert "referenced by:" in top
    assert "[Beta](concepts/b.md)" in top


def test_log_is_frontmatter_free_with_date_headings(tmp_path, monkeypatch):
    """OKF: log.md has no frontmatter and groups entries under ## YYYY-MM-DD headings."""
    import re as _re

    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    store.append_log("did a thing")
    log = (wiki / "log.md").read_text(encoding="utf-8")
    assert log.startswith("# Log") and not log.startswith("---")
    assert "type: Log" not in log
    assert _re.search(r"(?m)^## \d{4}-\d{2}-\d{2}$", log)
    assert "did a thing" in log


def test_tag_catalog_and_suggested_links(tmp_path, monkeypatch):
    """tag_catalog groups pages by tag; lint suggests an un-linked mention (advisory)."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    (raw / "a.md").write_text("src\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/espresso.md",
        {"type": "Concept", "title": "Espresso", "tags": ["brewing", "coffee"], "resource": "raw/a.md"},
        "Espresso is pressure brewing.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    _seed_page(
        wiki, "concepts/caffeine.md",
        {"type": "Concept", "title": "Caffeine", "tags": ["coffee"], "resource": "raw/a.md"},
        "Espresso carries caffeine.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    catalog = store.tag_catalog()
    assert set(catalog) == {"brewing", "coffee"}
    assert {p.rel_path for p in catalog["coffee"]} == {
        "concepts/espresso.md", "concepts/caffeine.md"
    }

    report = lint.lint()
    assert (
        "concepts/caffeine.md",
        "concepts/espresso.md (mentions 'Espresso')",
    ) in report.suggested_links
    assert report.ok()  # advisory only


def test_suggested_links_skips_already_linked(tmp_path, monkeypatch):
    """A page that already links a concept is not nagged to link it again."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    _seed_page(
        wiki, "concepts/espresso.md", {"type": "Concept", "title": "Espresso", "resource": "raw/a.md"},
        "Espresso.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    _seed_page(
        wiki, "concepts/caffeine.md", {"type": "Concept", "title": "Caffeine", "resource": "raw/a.md"},
        "See [Espresso](./espresso.md).[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )
    report = lint.lint()
    caffeine_suggestions = [t for r, t in report.suggested_links if r == "concepts/caffeine.md"]
    assert not any("espresso.md" in s for s in caffeine_suggestions)


# --- per-source model provenance (manifest + sources catalog) ---------------------------


def test_ingest_records_importing_model_in_manifest(tmp_path, monkeypatch):
    """Each ingested source records WHICH model imported it; the report/log carry it too. A source
    no model imported (an unreadable binary) records its sha alone, with no model."""
    import json

    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "opus", raising=False)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "blob.bin").write_bytes(b"\x00\x01BINARY\xff")

    report = ingest.ingest()
    assert report.model == "claude:opus"
    assert "Model: claude:opus" in report.render()

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert data["raw/notes.md"]["model"] == "claude:opus"
    assert "model" not in data["raw/blob.bin"]  # nothing imported it

    log_text = (wiki / "log.md").read_text(encoding="utf-8")
    assert "(model: claude:opus)" in log_text


def test_sources_catalog_lists_source_model_and_referencing_pages(tmp_path, monkeypatch):
    """Ingest generates wiki/sources/index.md: a row per source with its model and links to the
    pages that cite it, and the top index links the catalog under 'See also'."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()

    catalog = (wiki / "sources" / "index.md").read_text(encoding="utf-8")
    assert catalog.startswith("# Sources") and not catalog.startswith("---")
    assert "| Source | Model | Referenced by |" in catalog
    # The source links to the raw file, shows the model, and links the page that cites it.
    assert "[raw/notes.md](../../raw/notes.md)" in catalog
    assert "claude:sonnet" in catalog
    assert "[Transformer](../concepts/transformer.md)" in catalog

    top = (wiki / "index.md").read_text(encoding="utf-8")
    assert "[sources](sources/index.md)" in top

    # The catalog is a reserved nav file: load() ignores it, so it is not a page / graph node.
    assert all(p.rel_path != "sources/index.md" for p in store.load())


def test_sources_catalog_removed_when_no_tracked_sources(tmp_path, monkeypatch):
    """With an empty manifest the catalog is not written, and a stale one is removed so it never
    lingers after the last source is gone."""
    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    stale = wiki / "sources" / "index.md"
    stale.parent.mkdir(parents=True, exist_ok=True)
    stale.write_text("# Sources\n\nstale\n", encoding="utf-8")
    _seed_page(
        wiki, "concepts/a.md",
        {"type": "Concept", "title": "Alpha", "description": "d", "tags": ["x"], "resource": "raw/a.md"},
        "Alpha.[^s1]\n\n## Sources\n\n[^s1]: [raw/a.md](../../raw/a.md) - n\n",
    )

    store.rebuild_indexes()  # manifest is empty in this fixture

    assert not stale.exists()
    assert "[sources](sources/index.md)" not in (wiki / "index.md").read_text(encoding="utf-8")


def test_moved_source_carries_original_importing_model(tmp_path, monkeypatch):
    """Reorganizing a raw file is not a re-ingest, so the moved entry keeps the model that
    ORIGINALLY imported it — not the model configured for the run that detected the move."""
    import json

    wiki, raw = _wire_tmp_wiki(tmp_path, monkeypatch)
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "opus", raising=False)
    monkeypatch.setattr(ingest.llm, "run_ingest_session", fake_session_transformer)

    (raw / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    ingest.ingest()  # imported by claude:opus

    # A later run on a DIFFERENT model detects the move; the carried model must stay claude:opus.
    monkeypatch.setattr(config, "INGEST_MODEL", "haiku", raising=False)
    (raw / "ml").mkdir()
    (raw / "ml" / "notes.md").write_text("Transformers use self-attention.\n", encoding="utf-8")
    (raw / "notes.md").unlink()

    report = ingest.ingest()
    assert ("raw/notes.md", "raw/ml/notes.md") in report.moved

    data = json.loads((wiki / ".okf_ingested.json").read_text(encoding="utf-8"))
    assert "raw/notes.md" not in data
    assert data["raw/ml/notes.md"]["model"] == "claude:opus"  # original model carried, not haiku

    # The catalog reflects the moved key + the carried model.
    catalog = (wiki / "sources" / "index.md").read_text(encoding="utf-8")
    assert "[raw/ml/notes.md](../../raw/ml/notes.md)" in catalog
    assert "claude:opus" in catalog
