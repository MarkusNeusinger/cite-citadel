"""Unit tests for citadel.rawsource — the wiki_raw / ``citadel raw`` provider.

The offline "trust but verify" reader: resolve a ``[^sN]`` citation's raw source (whole, or the slice
a locator names), gated to sources the wiki actually cites. All offline; a raw file is written under
the ``tmp_citadel`` RAW_DIR and recorded in the manifest so the provenance gate lets it through.
"""

from __future__ import annotations

import pytest

from citadel import config, manifest, rawsource


def _cite(cit, name: str, text: str) -> str:
    """Write a raw source under RAW_DIR and record it in the manifest (so the provenance gate admits
    it), returning its source key."""
    (cit.raw / name).write_text(text, encoding="utf-8")
    key = config.rel_or_abs_posix(cit.raw / name)
    tracked = manifest.load()
    tracked[key] = manifest.make_entry("aa" * 32, model="sonnet")
    manifest.save(tracked)
    return key


def test_whole_source_is_returned_line_numbered(tmp_citadel):
    key = _cite(tmp_citadel, "notes.md", "alpha\nbeta\ngamma\n")

    out = rawsource.raw_text(key)

    assert "lines 1-3 of 3" in out
    assert "1 | alpha" in out and "3 | gamma" in out


def test_line_locator_slices_to_the_range(tmp_citadel):
    key = _cite(tmp_citadel, "notes.md", "l1\nl2\nl3\nl4\nl5\n")

    out = rawsource.raw_text(key, "lines 2-3")

    assert "2 | l2" in out and "3 | l3" in out
    assert " l1" not in out and " l4" not in out


def test_heading_locator_returns_only_that_section(tmp_citadel):
    text = "# Intro\n\nhi\n\n## Method\n\nstep one\nstep two\n\n## Results\n\ndone\n"
    key = _cite(tmp_citadel, "spec.md", text)

    out = rawsource.raw_text(key, "§ Method")

    assert "## Method" in out and "step one" in out and "step two" in out
    assert "Results" not in out and "Intro" not in out


def test_combined_locator_verifies_heading_and_returns_the_line_range(tmp_citadel):
    # lines: 1 '# Intro', 2 '', 3 '## Method', 4 '', 5 'step one', 6 'step two', 7 'step three'
    key = _cite(tmp_citadel, "spec.md", "# Intro\n\n## Method\n\nstep one\nstep two\nstep three\n")

    out = rawsource.raw_text(key, "§ Method, lines 5-6")
    assert "5 | step one" in out and "6 | step two" in out
    assert "step three" not in out

    # a combined locator whose heading does not exist is refused even when the lines are valid:
    with pytest.raises(rawsource.SourceError, match="not a heading"):
        rawsource.raw_text(key, "§ Nonexistent, lines 5-6")


def test_uncited_key_is_refused(tmp_citadel):
    (tmp_citadel.raw / "loose.md").write_text("secret\n", encoding="utf-8")  # on disk but never ingested
    key = config.rel_or_abs_posix(tmp_citadel.raw / "loose.md")

    with pytest.raises(rawsource.SourceError, match="not a source the wiki cites"):
        rawsource.raw_text(key)


def test_key_outside_every_source_root_is_refused(tmp_citadel, tmp_path):
    outside = tmp_path / "elsewhere.md"
    outside.write_text("x\n", encoding="utf-8")

    with pytest.raises(rawsource.SourceError, match="not under a configured"):
        rawsource.raw_text(str(outside))


def test_docs_file_is_readable_without_a_manifest_entry(tmp_citadel):
    (tmp_citadel.docs / "okf.md").write_text("# Spec\n\nrule\n", encoding="utf-8")
    key = config.rel_or_abs_posix(tmp_citadel.docs / "okf.md")

    out = rawsource.raw_text(key)  # docs/ is legal provenance, never manifested

    assert "rule" in out


def test_cited_but_missing_on_disk_is_reported(tmp_citadel):
    key = _cite(tmp_citadel, "gone.md", "x\n")
    (tmp_citadel.raw / "gone.md").unlink()

    with pytest.raises(rawsource.SourceError, match="missing on disk"):
        rawsource.raw_text(key)


def test_out_of_range_line_locator_is_reported(tmp_citadel):
    key = _cite(tmp_citadel, "notes.md", "one\ntwo\n")

    with pytest.raises(rawsource.SourceError, match="out of range"):
        rawsource.raw_text(key, "lines 40-52")


def test_missing_heading_lists_the_available_ones_with_original_casing(tmp_citadel):
    # Issue #58: the hint must echo the source's OWN casing, not grammar.source_headings' case-fold.
    key = _cite(tmp_citadel, "spec.md", "# The One Rule About Temperature\n\nprose\n")

    with pytest.raises(rawsource.SourceError) as exc:
        rawsource.raw_text(key, "§ No Such Heading")

    msg = str(exc.value)
    assert "§ The One Rule About Temperature" in msg  # the available heading, in the source's casing
    assert "the one rule about temperature" not in msg  # never the case-folded form


def test_bold_line_heading_locator_resolves_the_section(tmp_citadel):
    # Issue #62: a FAQ source structured with whole-line **bold** headers (not `#`) — a `§ Heading`
    # locator into a bold section must resolve, not raise "headings present: none".
    text = "**Q: How does caffeine work?**\n\nIt blocks adenosine.\n\n**Q: What about tea?**\n\nLess.\n"
    key = _cite(tmp_citadel, "faq.md", text)

    out = rawsource.raw_text(key, "§ Q: How does caffeine work?")

    assert "It blocks adenosine" in out
    assert "What about tea" not in out and "Less" not in out


def test_large_source_is_capped_with_a_narrowing_hint(tmp_citadel):
    key = _cite(tmp_citadel, "big.md", "".join(f"line {i}\n" for i in range(20000)))

    out = rawsource.raw_text(key)

    assert len(out) <= rawsource.MAX_CHARS + 200
    assert "truncated" in out and "locator" in out


def test_pdf_source_has_no_offline_text(tmp_citadel):
    key = _cite(tmp_citadel, "report.pdf", "%PDF-1.4 not really\n")

    with pytest.raises(rawsource.SourceError, match="no offline text"):
        rawsource.raw_text(key)


def test_binary_source_is_reported_not_dumped(tmp_citadel):
    (tmp_citadel.raw / "blob.dat").write_bytes(b"text\x00more")
    key = config.rel_or_abs_posix(tmp_citadel.raw / "blob.dat")
    tracked = manifest.load()
    tracked[key] = manifest.make_entry("bb" * 32)
    manifest.save(tracked)

    with pytest.raises(rawsource.SourceError, match="binary"):
        rawsource.raw_text(key)


def test_empty_source_renders_a_valid_header(tmp_citadel):
    """An empty cited source renders a clean 'empty source' header, never a `lines 1-0 of 0` range."""
    key = _cite(tmp_citadel, "empty.md", "")

    out = rawsource.raw_text(key)

    assert "empty source (0 lines)" in out
    assert "1-0" not in out


@pytest.mark.parametrize("locator", ["p. 3", "gibberish locator"])
def test_unresolvable_locator_is_an_error_not_a_silent_fallback(tmp_citadel, locator):
    """A locator that parses to nothing offline-resolvable (an Office page locator, a garbled
    form) raises like every other bad locator — it used to silently return the whole source with
    a header note and exit 0, so a typo'd locator was undetectable. The error names the
    recognized forms and the omit-the-locator escape hatch."""
    key = _cite(tmp_citadel, "notes.md", "a\nb\nc\n")

    with pytest.raises(rawsource.SourceError, match="not offline-resolvable") as exc:
        rawsource.raw_text(key, locator)

    msg = str(exc.value)
    assert "lines A-B" in msg and "§ Heading" in msg and "omit the locator" in msg


# --- audio sources: served through the cached whisper transcript -------------------------


def _cite_audio(cit, name: str, transcript: str | None) -> str:
    """Write a fake .mp3 under RAW_DIR, record it in the manifest, and (optionally) plant its
    content-addressed transcript cache — returning its source key."""
    from citadel import transcribe

    path = cit.raw / name
    path.write_bytes(b"ID3\x03\x00" + b"\x00\x01fake-frames-" + name.encode())
    key = config.rel_or_abs_posix(path)
    tracked = manifest.load()
    tracked[key] = manifest.make_entry(manifest.file_sha256(path), model="sonnet")
    manifest.save(tracked)
    if transcript is not None:
        config.robust_mkdir(transcribe.cache_dir())
        transcribe.cache_path(manifest.file_sha256(path)).write_text(transcript, encoding="utf-8")
    return key


def test_audio_source_served_from_cached_transcript(tmp_citadel):
    key = _cite_audio(tmp_citadel, "memo.mp3", "[00:00:01] Hello.\n[00:00:05] Budget approved.\n")

    out = rawsource.raw_text(key)
    assert "[00:00:01] Hello." in out and "[00:00:05] Budget approved." in out

    sliced = rawsource.raw_text(key, "lines 2-2")
    assert "Budget approved" in sliced and "Hello." not in sliced


def test_audio_source_without_cache_names_the_knob(tmp_citadel):
    key = _cite_audio(tmp_citadel, "memo.mp3", None)

    with pytest.raises(rawsource.SourceError, match="CITADEL_AUDIO_SUPPORT"):
        rawsource.raw_text(key)


def test_text_file_renamed_mp3_is_served_as_text(tmp_citadel):
    """A UTF-8 text file merely RENAMED .mp3 (no audio magic) ingested as ordinary text — wiki_raw
    must serve it through the normal text path, not demand a transcript cache."""
    key = _cite(tmp_citadel, "notes.mp3", "alpha\nbeta\ngamma\n")

    out = rawsource.raw_text(key, "lines 2-3")
    assert "beta" in out and "gamma" in out
