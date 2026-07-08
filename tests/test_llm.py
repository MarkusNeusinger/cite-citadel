"""Offline tests for the agentic CLI invocation + error handling (no CLI, no network).

The old structured-output path returned a ``{"ops": [...]}`` JSON that Python parsed; that is
gone. Ingest now runs the CLI agentically and the CLI edits the wiki itself. These tests cover
how ``llm`` builds the (tiny, paths-only) prompt and per-CLI argv, and how ``_run_session``
turns a CLI failure into a ``RuntimeError`` — all by monkeypatching ``subprocess.run`` so no
real CLI is ever spawned.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from conftest import PROMPT_CHAR_BUDGET, REAL_RULES_DIR

from citadel import config, llm


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _ref(relname: str) -> str:
    """The prompt token for one EFFECTIVE rules file — the same resolution + rel_or_abs_posix
    discipline ``_build_instruction`` renders every rules path through."""
    return config.rel_or_abs_posix(config.effective_rules_file(relname))


def _assert_referenced_rules_reachable(
    prompt: str, rel_key: str, kind: str = "ingest", read_path: str | None = None, segment=None
) -> None:
    """The shared prompt-validation core: every rules path ``_referenced_rules`` lists (a)
    appears in the prompt, (b) resolves — through the same key math the rest of the system
    uses — to an EXISTING file, and (c) is readable by the agent: under its cwd (the workspace
    root) or inside a directory ``_external_dirs`` granted (grants are recursive)."""
    granted = [Path(d) for d in llm._external_dirs(rel_key, read_path)]
    referenced = llm._referenced_rules(rel_key, kind, read_path, segment)
    assert referenced  # never an empty rules read list
    for _role, path in referenced:
        token = config.rel_or_abs_posix(path)
        assert token in prompt
        assert config.source_path_for_key(token).is_file()
        resolved = Path(path).resolve()
        assert (not config.is_outside_workspace(resolved)) or any(resolved.is_relative_to(d) for d in granted)


def test_build_instruction_references_paths_not_content():
    """The prompt references the rules + raw source BY PATH and never embeds content, so it
    stays tiny — the regression guard against the old WinError 206 (argv too long). Every session
    reads schema.md + core.md + exactly one task brief, named by their RESOLVED effective
    locations, not assumed to sit in the current directory."""
    prompt = llm._build_instruction("raw/notes.md")
    for relname in ("schema.md", "core.md", "tasks/ingest.md"):
        assert _ref(relname) in prompt
    assert "raw/notes.md" in prompt
    assert "wiki/" in prompt
    # Must never embed a large blob — paths only.
    assert len(prompt) < PROMPT_CHAR_BUDGET


def test_build_instruction_uses_configured_wiki_dir(tmp_path, monkeypatch):
    """Regression for the hardcoded-'wiki/' bug: the prompt must name the CONFIGURED wiki
    directory (CITADEL_WIKI_DIR), so with CITADEL_WIKI_DIR=wikiET the agent searches and writes
    wikiET/ — otherwise it edits 'wiki/' while ingest's snapshot/diff watches wikiET/ and sees
    nothing."""
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wikiET", raising=False)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw", raising=False)
    # Keep the rules tokens free of the real checkout's absolute path (which could contain 'wiki/').
    monkeypatch.setattr(config, "PACKAGED_RULES_DIR", tmp_path / "citadel-rules")

    prompt = llm._build_instruction("raw/notes.md")

    assert "wikiET/" in prompt  # the configured wiki dir is used throughout...
    assert "wiki/" not in prompt  # ...and no hardcoded bare 'wiki/' survives
    assert "raw/notes.md" in prompt  # the raw source path is still referenced verbatim
    assert len(prompt) < PROMPT_CHAR_BUDGET  # still tiny (paths-only) — WinError 206 guard


def test_raw_directory_bullet_names_the_covering_root(tmp_citadel, tmp_path, monkeypatch):
    """Multi-root corpora: the prompt's 'Raw directory' bullet names the root that COVERS the
    current source (config.root_covering), not blindly the primary — a root-2 source must not be
    pointed at root 1. An out-of-root explicit path falls back to the primary RAW_DIR."""
    root_b = tmp_path / "share" / "more-raw"
    root_b.mkdir(parents=True)
    (root_b / "b.md").write_text("beta\n", encoding="utf-8")
    monkeypatch.setattr(config, "RAW_DIRS", [tmp_citadel.raw, root_b], raising=False)

    key_b = (root_b / "b.md").resolve().as_posix()
    assert f"- Raw directory: {config.rel_or_abs_posix(root_b)}/" in llm._build_instruction(key_b)
    # A primary-root source still names the primary root, byte-for-byte as before.
    assert "- Raw directory: raw/" in llm._build_instruction("raw/notes.md")
    # An explicit out-of-root path: no covering root — fall back to the primary.
    outside = (tmp_path / "elsewhere.md").resolve().as_posix()
    assert "- Raw directory: raw/" in llm._build_instruction(outside)


# --- the rules tree keeps teaching what the prompt no longer says --------------------------
#
# The tiny argv prompt only POINTS the agent at the rules files, so — exactly like provenance
# and restructuring — the behavioral guidance lives in the rules layer. These content pins key
# on stable anchors (not exact prose) so wording tweaks don't break them, but a silently DROPPED
# rule fails loud.


def test_core_rules_teach_path_and_filename_as_routing_context():
    """A source's path within raw/ and its filename often encode the project/topic the facts
    belong to. After the rules split this guidance lives ONLY in core.md § 'Path & filename are
    context' — guard that it is not silently dropped."""
    core = (REAL_RULES_DIR / "core.md").read_text(encoding="utf-8").lower()
    assert "routing context" in core or "routing signal" in core
    assert "path" in core and "filename" in core
    assert "project" in core and "topic" in core
    # Coarse keyword pins (one distinctive token per concept, so a meaning-preserving rewording
    # survives): the path-derived project/topic feeds the page's tags...
    assert "tag" in core
    # ...and the load-bearing guardrail: the path ROUTES facts, it is never itself a cited fact.
    assert "never cite" in core


def test_core_rules_teach_raw_read_only_and_tool_discipline():
    """core.md must keep telling the agent that raw sources are READ-ONLY (never written) and that
    reading/searching go through the built-in file tools, with the shell reserved for the
    self-check and page deletes/renames — the guidance that keeps a session's footprint small and
    the raw tree untouched. Coarse keyword pins so a rewording survives but a dropped rule fails."""
    core = (REAL_RULES_DIR / "core.md").read_text(encoding="utf-8").lower()
    assert "read-only" in core  # raw sources are read-only inputs
    assert "built-in" in core and "shell" in core  # prefer built-in tools over the shell
    # The self-check runs ONCE, not repeatedly, to avoid a spawn per iteration.
    assert "once" in core


def test_curate_brief_runs_check_once():
    """tasks/curate.md keeps the run-once self-check discipline (re-run only to confirm fixes)."""
    brief = (REAL_RULES_DIR / "tasks/curate.md").read_text(encoding="utf-8").lower()
    assert "once" in brief and "citadel check" in brief


def test_prompt_frame_pins_raw_read_only_and_run_once_check():
    """The code-invariant closing frame must name the raw tree as READ-ONLY, steer reading/search
    to the built-in file tools, and run `citadel check` ONCE (re-running only on errors) — the
    behaviors that keep the agent from writing outside the wiki and spawning a shell per step."""
    prompt = llm._build_instruction("raw/notes.md")
    assert "READ-ONLY" in prompt  # raw/source is read-only
    assert "built-in file tools" in prompt
    assert "ONCE" in prompt  # the self-check runs once
    assert "citadel check" in prompt


def test_reconcile_brief_says_update_remove_and_keeps_cocited_facts():
    """tasks/reconcile.md (the changed-source brief) must keep telling the agent to UPDATE/REMOVE
    stale facts rather than append — and that a co-cited fact loses only THIS source's marker
    (the Copilot-review fix), plus the locator re-check and the keep-genre-treatment rule (the
    no-churn stand-in for the unshipped manifest genre stamp)."""
    brief = (REAL_RULES_DIR / "tasks/reconcile.md").read_text(encoding="utf-8").lower()
    assert "update" in brief and "remove" in brief
    assert "append" in brief  # coarse pin: reconcile means update/remove, not append
    assert "co-cited" in brief and "only if" in brief
    assert "locator" in brief
    assert "genre treatment" in brief
    # The segmented-reconcile guard: never blanket-delete facts outside the visible segment.
    assert "cannot see" in brief


def test_office_brief_covers_extract_media_and_source_of_record():
    """formats/office.md must keep the load-bearing Office rules: read the pre-extracted text,
    VIEW the embedded media/ images, and cite the ORIGINAL file as the source of record."""
    brief = (REAL_RULES_DIR / "formats/office.md").read_text(encoding="utf-8").lower()
    assert "extracted" in brief and "media/" in brief
    assert "source of record" in brief and "resource" in brief
    assert "locator" in brief  # office citations require locators (Z6)


def test_delete_brief_strips_provenance_without_opening():
    """tasks/delete.md must keep: never open the removed file, remove only THIS source's
    provenance (a co-cited fact keeps its other markers), and the no-references post-condition
    ingest re-checks."""
    brief = (REAL_RULES_DIR / "tasks/delete.md").read_text(encoding="utf-8").lower()
    assert "removed" in brief and "not" in brief and "open" in brief
    assert "resource" in brief and "[^s" in brief  # both provenance forms are named
    assert "never invent" in brief
    assert "reference" in brief  # coarse pin: the no-references post-condition


def test_ingest_brief_segments_merge_not_duplicate():
    """tasks/ingest.md § Large sources: read the slice, cite the WHOLE source, and MERGE later
    segments into the pages earlier passes created instead of duplicating them."""
    brief = " ".join((REAL_RULES_DIR / "tasks/ingest.md").read_text(encoding="utf-8").lower().split())
    # Coarse keyword pins, one per concept: cite the WHOLE source (never the slice), merge into
    # earlier passes' pages without duplicating, and never invent continuations of the slice.
    assert "whole source" in brief
    assert "merging" in brief and "duplicate" in brief
    assert "continuations" in brief


def test_pdf_brief_names_both_modes_and_page_locators():
    """formats/pdf.md carries the CITADEL_PDF_MODE semantics (text vs images) and the mandatory
    page locators; the knob in Python only names the active mode."""
    brief = (REAL_RULES_DIR / "formats/pdf.md").read_text(encoding="utf-8").lower()
    assert "text" in brief and "images" in brief
    assert "page locator" in brief


def test_first_person_genre_gates_style_profiling_on_run_instruction():
    """genres/first-person.md: attributed positions ALWAYS; style profiling ONLY when the run
    instruction turns it on (CITADEL_STYLE_PROFILES) — the opt-in idiolect vision."""
    brief = (REAL_RULES_DIR / "genres/first-person.md").read_text(encoding="utf-8").lower()
    assert "attributed" in brief
    assert "style profil" in brief
    assert "run instruction" in brief and "on" in brief


def test_every_genre_brief_opens_with_an_applies_when_line():
    """The starter-set contract (rules README): each genre file starts by saying when it applies,
    because the agent picks briefs from an enumerated list by content."""
    genre_files = sorted((REAL_RULES_DIR / "genres").glob("*.md"))
    assert len(genre_files) >= 4  # prose, meeting-minutes, email, first-person ship as the set
    for path in genre_files:
        head = path.read_text(encoding="utf-8").lower()[:400]
        assert "applies" in head, f"{path.name} must open with when it applies"


# --- prompt composition: kind -> (task, format) mapping ------------------------------------


def test_reconcile_kind_reads_reconcile_brief():
    prompt = llm._build_instruction("raw/notes.md", "reconcile")
    assert _ref("tasks/reconcile.md") in prompt
    assert _ref("tasks/ingest.md") not in prompt
    assert len(prompt) < PROMPT_CHAR_BUDGET


def test_office_read_path_maps_to_office_brief_and_prepared_file_bullet():
    """A pre-extracted Office source: the prompt points the agent at formats/office.md and names
    the extract as the prepared file — the source of record stays the original rel_key."""
    prompt = llm._build_instruction("raw/deck.pptx", "ingest", "/tmp/okf_extract_x/deck.md")
    assert _ref("formats/office.md") in prompt
    assert "/tmp/okf_extract_x/deck.md" in prompt  # the extracted-text file to read
    assert "raw/deck.pptx" in prompt  # the original source of record
    assert len(prompt) < PROMPT_CHAR_BUDGET


def test_plain_source_gets_no_format_brief_and_no_prepared_file():
    """A normal text source maps to NO format brief, and no prepared-file bullet leaks in."""
    prompt = llm._build_instruction("raw/notes.md")
    assert "Prepared file" not in prompt
    for fmt in ("formats/office.md", "formats/image.md", "formats/repo.md", "formats/pdf.md"):
        assert _ref(fmt) not in prompt


def test_image_kinds_map_to_image_brief():
    for kind in ("image", "image-reconcile"):
        prompt = llm._build_instruction("raw/diagram.png", kind)
        assert _ref("formats/image.md") in prompt
        assert "raw/diagram.png" in prompt
        assert "Prepared file" not in prompt  # the agent opens the image directly


def test_repo_kinds_map_to_repo_brief_with_digest_as_prepared_file():
    for kind, task in (("repo", "tasks/ingest.md"), ("repo-reconcile", "tasks/reconcile.md")):
        prompt = llm._build_instruction("raw/acme-etl", kind, "/tmp/okf_digest_x/repo.md")
        assert _ref("formats/repo.md") in prompt
        assert _ref(task) in prompt
        assert "/tmp/okf_digest_x/repo.md" in prompt  # the digest the agent reads
        assert "raw/acme-etl" in prompt  # the repo folder stays the source of record


def test_pdf_source_magic_sniffed_maps_to_pdf_brief(tmp_citadel):
    """A real %PDF- file (magic-sniffed exactly like ingest does) maps to formats/pdf.md and gets
    the PDF-mode bullet; a text file that merely ENDS in .pdf does not."""
    (tmp_citadel.raw / "report.pdf").write_bytes(b"%PDF-1.7\nfake body\n")
    prompt = llm._build_instruction("raw/report.pdf")
    assert _ref("formats/pdf.md") in prompt
    assert "PDF mode: text" in prompt  # the default CITADEL_PDF_MODE

    (tmp_citadel.raw / "notes.pdf").write_text("just text, not a real pdf\n", encoding="utf-8")
    prompt = llm._build_instruction("raw/notes.pdf")
    assert _ref("formats/pdf.md") not in prompt
    assert "PDF mode" not in prompt


def test_pdf_suffix_is_the_fallback_when_the_file_is_unreadable():
    """A phantom .pdf key (no file on disk — e.g. mid-run vanish) still maps to the PDF brief via
    the suffix fallback."""
    assert llm._is_pdf_source("raw/gone.pdf") is True
    assert llm._is_pdf_source("raw/gone.md") is False


def test_segment_bullet_and_no_office_brief_for_slices():
    """A large-source slice names the segment position and the slice as the prepared file; the
    task brief's Large-sources rules cover it (NOT formats/office.md — a slice is not an Office
    extract, even when the source was one)."""
    prompt = llm._build_instruction("raw/big.txt", "ingest", "/tmp/okf_extract_y/big.md", (2, 3))
    assert "Segment: part 2 of 3" in prompt
    assert "/tmp/okf_extract_y/big.md" in prompt
    assert "raw/big.txt" in prompt
    assert _ref("formats/office.md") not in prompt
    assert _ref("tasks/ingest.md") in prompt


def test_multisegment_reconcile_reads_reconcile_brief_with_segment_bullet():
    prompt = llm._build_instruction("raw/big.txt", "reconcile", "/tmp/okf_extract_z/big.md", (2, 3))
    assert _ref("tasks/reconcile.md") in prompt
    assert "Segment: part 2 of 3" in prompt


def test_delete_kind_reads_delete_brief_no_format_no_genres():
    """The delete prompt maps to tasks/delete.md alone: no format brief (it never reads the
    source) and no genre enumeration (there is no content to judge). The source bullet says the
    file is gone."""
    prompt = llm._build_instruction("raw/gone.md", "delete")
    assert _ref("tasks/delete.md") in prompt
    assert "raw/gone.md" in prompt
    assert "REMOVED from disk" in prompt and "do not open" in prompt
    assert "Judge the source's genre" not in prompt
    for fmt in ("formats/office.md", "formats/image.md", "formats/repo.md", "formats/pdf.md"):
        assert _ref(fmt) not in prompt
    assert len(prompt) < PROMPT_CHAR_BUDGET


def test_build_instruction_delete_honors_configured_wiki_dir(tmp_path, monkeypatch):
    """The delete prompt names the CONFIGURED wiki dir (CITADEL_WIKI_DIR), never a hardcoded
    'wiki/', so a custom layout is searched/edited correctly."""
    monkeypatch.setattr(config, "WORKSPACE_ROOT", tmp_path, raising=False)
    monkeypatch.setattr(config, "WIKI_DIR", tmp_path / "wikiET", raising=False)
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw", raising=False)
    monkeypatch.setattr(config, "PACKAGED_RULES_DIR", tmp_path / "citadel-rules")

    prompt = llm._build_instruction("raw/gone.md", "delete")
    assert "wikiET/" in prompt
    assert "wiki/" not in prompt


def test_curate_kind_reads_curate_brief_via_findings_no_office_no_genres():
    """PR6 curate: the kind maps to tasks/curate.md, names the anchor PAGE as its subject and the
    findings file as the prepared file — but attaches NO format brief (format_policy 'none') even
    though a read_path is present (curate's findings file must NOT pull in formats/office.md), and
    enumerates NO genres (it edits existing pages, not source content). Paths-only, tiny."""
    findings = "/tmp/okf_findings_x/concepts_topic.md"
    prompt = llm._build_instruction("concepts/topic.md", "curate", findings)
    assert _ref("tasks/curate.md") in prompt
    assert _ref("schema.md") in prompt and _ref("core.md") in prompt
    assert _ref("tasks/ingest.md") not in prompt and _ref("tasks/reconcile.md") not in prompt
    assert "concepts/topic.md" in prompt  # the cluster anchor page
    assert findings in prompt  # the findings checklist, referenced BY PATH (not embedded)
    assert "cluster anchor" in prompt
    assert "Judge the source's genre" not in prompt  # no genre enumeration for curate
    for fmt in ("formats/office.md", "formats/image.md", "formats/repo.md", "formats/pdf.md"):
        assert _ref(fmt) not in prompt
    assert len(prompt) < PROMPT_CHAR_BUDGET


def test_unknown_kind_fails_loud():
    """The per-kind spec table has no silent ingest-brief default: an unregistered kind (a typo, a
    new lifecycle that forgot to register) raises loudly rather than folding a source under the
    wrong task. Guards _spec_for_kind and every builder that goes through it."""
    with pytest.raises(ValueError, match="unknown ingest kind"):
        llm._spec_for_kind("bogus-kind")
    with pytest.raises(ValueError, match="unknown ingest kind"):
        llm._build_instruction("raw/notes.md", "bogus-kind")
    with pytest.raises(ValueError, match="unknown ingest kind"):
        llm._referenced_rules("raw/notes.md", "bogus-kind")


def test_curate_brief_teaches_improve_or_noop_and_provenance_invariants():
    """tasks/curate.md (the curate brief) must keep its load-bearing invariants: consume the
    findings checklist, improve-or-NOOP ('make no edits and stop'), never invent, never break
    [^sN] provenance, preserve counterfactuals, re-sort/split keeping every fact + citation, and
    run citadel check before finishing. Coarse keyword pins so a rewording survives but a DROPPED
    rule fails loud."""
    brief = (REAL_RULES_DIR / "tasks/curate.md").read_text(encoding="utf-8").lower()
    assert "findings" in brief  # consumes the findings file
    assert "make no edits and stop" in brief  # improve-or-NOOP is mandatory
    assert "never invent" in brief
    assert "[^s" in brief and "provenance" in brief  # never break provenance
    assert "counterfactual" in brief  # preserved as stated
    assert "folder" in brief and "split" in brief  # re-sort + split-overlong
    assert "citation" in brief  # every fact keeps its citation across a move/split
    assert "citadel check" in brief  # the pre-finish gate


# --- variables-as-bullets: the config knobs the rules expect -------------------------------


def test_wiki_language_bullet_default_and_override(tmp_citadel, monkeypatch):
    """core.md/schema.md § Wiki language read the target language from the run instruction: the
    bullet carries CITADEL_WIKI_LANG (default en) for every kind, including delete."""
    assert "Wiki language: en" in llm._build_instruction("raw/notes.md")
    assert "Wiki language: en" in llm._build_instruction("raw/gone.md", "delete")
    monkeypatch.setattr(config, "WIKI_LANG", "de")
    assert "Wiki language: de" in llm._build_instruction("raw/notes.md")


def test_pdf_mode_bullet_switches_with_the_knob(tmp_citadel, monkeypatch):
    (tmp_citadel.raw / "report.pdf").write_bytes(b"%PDF-1.7\nx\n")
    assert "PDF mode: text" in llm._build_instruction("raw/report.pdf")
    monkeypatch.setattr(config, "PDF_MODE", "images")
    assert "PDF mode: images" in llm._build_instruction("raw/report.pdf")
    # The bullet is PDF-only: a plain source never names a PDF mode, whatever the knob says.
    assert "PDF mode" not in llm._build_instruction("raw/notes.md")


def test_style_profiles_knob_gates_the_style_line(tmp_citadel, monkeypatch):
    """CITADEL_STYLE_PROFILES (default 0) gates the style-profiling line: absent by default —
    genres/first-person.md § Style profile activates ONLY when the run instruction says ON."""
    assert "Style profiling" not in llm._build_instruction("raw/notes.md")
    monkeypatch.setattr(config, "STYLE_PROFILES", True)
    assert "Style profiling: ON" in llm._build_instruction("raw/notes.md")


def test_fallback_date_bullet_uses_the_source_files_own_date(tmp_citadel):
    """genres/meeting-minutes.md § Dates: the run instruction gives the source file's own date as
    the fallback when the content states no date. A phantom key yields no bullet."""
    import calendar
    import os

    src = tmp_citadel.raw / "minutes.md"
    src.write_text("weekly sync\n", encoding="utf-8")
    stamp = calendar.timegm((2026, 3, 2, 12, 0, 0, 0, 0, 0))  # UTC — matches the prompt's gmtime
    os.utime(src, (stamp, stamp))
    prompt = llm._build_instruction("raw/minutes.md")
    assert "Fallback date" in prompt and "2026-03-02" in prompt

    assert "Fallback date" not in llm._build_instruction("raw/phantom.md")


# --- genres: enumerated dynamically from the EFFECTIVE genres dir --------------------------


def test_prompt_enumerates_every_effective_genre_brief(tmp_citadel):
    prompt = llm._build_instruction("raw/notes.md")
    assert "Judge the source's genre from its CONTENT" in prompt
    genres = config.effective_genres()
    assert genres  # the stub tree ships at least one genre
    for path in genres:
        assert config.rel_or_abs_posix(path) in prompt


def test_workspace_genre_participates_without_code_change(tmp_citadel):
    """The starter-set clarification: a genre file dropped into the workspace rules/genres/ is
    enumerated into the prompt automatically."""
    genre = tmp_citadel.root / "rules" / "genres" / "lab-notebook.md"
    genre.parent.mkdir(parents=True)
    genre.write_text("# lab-notebook — applies when the source reads like a lab notebook\n", encoding="utf-8")
    prompt = llm._build_instruction("raw/notes.md")
    assert "rules/genres/lab-notebook.md" in prompt


def test_workspace_genre_shadows_packaged_same_name(tmp_citadel):
    """A workspace rules/genres/<name> overrides the packaged same-name brief: the prompt names
    the workspace copy and drops the packaged one."""
    override = tmp_citadel.root / "rules" / "genres" / "prose.md"
    override.parent.mkdir(parents=True)
    override.write_text("# prose — forked\n", encoding="utf-8")
    prompt = llm._build_instruction("raw/notes.md")
    assert "rules/genres/prose.md" in prompt
    assert config.rel_or_abs_posix(tmp_citadel.packaged_rules / "genres/prose.md") not in prompt


def test_local_md_is_appended_when_present(tmp_citadel):
    prompt = llm._build_instruction("raw/notes.md")
    assert "local.md" not in prompt  # absent -> not referenced
    local = tmp_citadel.root / "rules" / "local.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("house rules\n", encoding="utf-8")
    prompt = llm._build_instruction("raw/notes.md")
    assert "rules/local.md" in prompt


def test_workspace_override_shadows_packaged_core(tmp_citadel):
    """First-hit-wins per filename: a workspace rules/core.md replaces the packaged core.md in
    the prompt (the fork-one-file story behind `citadel rules eject`)."""
    override = tmp_citadel.root / "rules" / "core.md"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text("# core — forked\n", encoding="utf-8")
    prompt = llm._build_instruction("raw/notes.md")
    assert "rules/core.md" in prompt
    assert config.rel_or_abs_posix(tmp_citadel.packaged_rules / "core.md") not in prompt


# --- packaged rules: prompt validation + access grants ---------------


@pytest.fixture
def pip_like_workspace(tmp_path, make_citadel, monkeypatch) -> Path:
    """A workspace whose packaged rules live OUTSIDE it — the pip-install reality (the rules sit
    in site-packages, never under a user workspace). Built on conftest's ``make_citadel`` (the
    single layout seam), then ``config.PACKAGED_RULES_DIR`` is pointed BACK at the REAL packaged
    tree (make_citadel pins it to a stub under the temp root), so the rules' prompt tokens are
    ABSOLUTE paths here."""
    root = tmp_path / "ws"
    make_citadel(root=root)
    monkeypatch.setattr(config, "PACKAGED_RULES_DIR", REAL_RULES_DIR)
    return root


# Every (kind, read_path, segment) variant _build_instruction can emit today.
_KIND_VARIANTS = [
    ("ingest", None, None),
    ("reconcile", None, None),
    ("image", None, None),
    ("image-reconcile", None, None),
    ("delete", None, None),
    ("repo", "/tmp/okf_digest_x/repo.md", None),
    ("repo-reconcile", "/tmp/okf_digest_x/repo.md", None),
    ("ingest", "/tmp/okf_extract_x/deck.md", None),  # Office extract
    ("reconcile", "/tmp/okf_extract_x/deck.md", None),
    ("ingest", "/tmp/okf_extract_x/big.md", (1, 4)),  # large-source segments
    ("ingest", "/tmp/okf_extract_x/big.md", (3, 4)),
    ("reconcile", "/tmp/okf_extract_x/big.md", (2, 4)),
    ("curate", "/tmp/okf_findings_x/findings.md", None),  # curate: findings file arrives via read_path
]


@pytest.mark.parametrize(("kind", "read_path", "segment"), _KIND_VARIANTS)
def test_every_referenced_rules_path_exists_and_is_reachable(pip_like_workspace, kind, read_path, segment):
    """The prompt-validation invariant, for EVERY variant: each rules path a built prompt
    references (a) appears in the prompt, (b) resolves — through the same key math the rest of
    the system uses — to an EXISTING file (a prompt naming a missing rules file would silently
    ingest without the schema), and (c) is readable by the agent: under its cwd (the workspace
    root) or inside a directory _external_dirs granted (grants are recursive)."""
    prompt = llm._build_instruction("raw/notes.md", kind, read_path, segment)
    _assert_referenced_rules_reachable(prompt, "raw/notes.md", kind, read_path, segment)


def test_pdf_variant_referenced_rules_exist_and_are_reachable(pip_like_workspace):
    """The PDF prompt variant (magic-sniffed, not in _KIND_VARIANTS' phantom keys) passes the
    same existence/reachability validation."""
    raw_dir = Path(config.RAW_DIR)
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "report.pdf").write_bytes(b"%PDF-1.7\nx\n")
    prompt = llm._build_instruction("raw/report.pdf")
    assert _ref("formats/pdf.md") in prompt
    _assert_referenced_rules_reachable(prompt, "raw/report.pdf")


def test_prompt_lists_rules_in_referenced_rules_order(tmp_citadel):
    """_referenced_rules is the ONE producer of the rules read list: the prompt names exactly its
    entries, in exactly its (canonical) order — schema, core, task, format?, local?, genres.
    Exercised with a local.md present so the local/genre ordering is covered too."""
    local = tmp_citadel.root / "rules" / "local.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("house rules\n", encoding="utf-8")

    prompt = llm._build_instruction("raw/notes.md")
    tokens = [config.rel_or_abs_posix(path) for _role, path in llm._referenced_rules("raw/notes.md")]
    assert len(tokens) >= 5  # schema, core, task, local, >=1 genre
    positions = [prompt.index(token) for token in tokens]
    assert positions == sorted(positions) and len(set(positions)) == len(positions)


def test_external_dirs_always_grant_out_of_workspace_rules(pip_like_workspace):
    """With the packaged rules OUTSIDE the workspace (pip install), _external_dirs must include
    the packaged rules ROOT (one recursive grant covers tasks/formats/genres) so the agent's file
    tools — otherwise scoped to cwd — can read the very rules the prompt tells it to follow."""
    dirs = llm._external_dirs("raw/notes.md")
    assert str(Path(config.PACKAGED_RULES_DIR).resolve()) in dirs


def test_claude_and_gemini_grant_rules_dir_copilot_needs_nothing(pip_like_workspace, monkeypatch):
    """The rules-dir grant reaches each CLI's own mechanism: claude ``--add-dir``, gemini
    ``--include-directories``. copilot has NO per-directory grant mechanism and needs none —
    it always runs with ``--allow-all-paths`` (which covers site-packages)."""
    monkeypatch.setattr(config, "INGEST_MODEL", "", raising=False)
    dirs = llm._external_dirs("raw/notes.md")
    rules_dir = str(Path(config.PACKAGED_RULES_DIR).resolve())

    argv, _ = llm._build_invocation("claude", "/bin/claude", "P", dirs)
    granted = [argv[i + 1] for i, flag in enumerate(argv) if flag == "--add-dir"]
    assert rules_dir in granted

    argv, _ = llm._build_invocation("gemini", "/bin/gemini", "P", dirs)
    included = argv[argv.index("--include-directories") + 1]
    assert rules_dir in included.split(",")

    argv, _ = llm._build_invocation("copilot", "/bin/copilot", "P", dirs)
    assert "--allow-all-paths" in argv
    assert rules_dir not in argv  # extra_dirs is deliberately unused for copilot


def test_rules_inside_workspace_need_no_grant(tmp_path, make_citadel):
    """The dev-checkout shape (rules under the workspace root): the prompt names them by short
    workspace-relative tokens and the cwd already covers them, so _external_dirs stays empty and
    the all-under-workspace argv is byte-for-byte unchanged."""
    make_citadel(root=tmp_path / "repo")
    prompt = llm._build_instruction("raw/notes.md")
    for relname in ("schema.md", "core.md", "tasks/ingest.md"):
        token = _ref(relname)
        assert not Path(token).is_absolute() and token in prompt
    assert llm._external_dirs("raw/notes.md") == []


@pytest.mark.parametrize(("kind", "read_path", "segment"), _KIND_VARIANTS)
def test_prompt_size_guard_every_kind(pip_like_workspace, kind, read_path, segment):
    """The PROMPT_CHAR_BUDGET argv guard (WinError 206) holds for EVERY prompt variant even in the
    worst realistic case: the rules (incl. every enumerated genre brief) referenced by their
    ABSOLUTE site-packages paths."""
    prompt = llm._build_instruction("raw/notes.md", kind, read_path, segment)
    assert len(prompt) < PROMPT_CHAR_BUDGET


def test_build_invocation_claude_uses_stdin_and_acceptedits(monkeypatch):
    monkeypatch.setattr(config, "INGEST_MODEL", "sonnet", raising=False)
    argv, stdin_text = llm._build_invocation("claude", "/bin/claude", "PROMPT")
    assert "-p" in argv
    assert "--permission-mode" in argv and "acceptEdits" in argv
    assert "--allowedTools" in argv
    assert "--model" in argv and "sonnet" in argv
    # claude takes the prompt on STDIN (argv carries only flags).
    assert stdin_text == "PROMPT"
    assert "PROMPT" not in argv


def test_build_invocation_copilot_prompt_in_argv(monkeypatch):
    argv, stdin_text = llm._build_invocation("copilot", "/bin/copilot", "SHORT PROMPT")
    assert stdin_text is None
    assert "SHORT PROMPT" in argv
    assert "--allow-all-tools" in argv
    assert "--no-ask-user" in argv


def test_build_invocation_gemini_yolo():
    argv, stdin_text = llm._build_invocation("gemini", "/bin/gemini", "SHORT PROMPT")
    assert stdin_text is None
    assert "SHORT PROMPT" in argv
    assert "--approval-mode" in argv and "yolo" in argv


def test_run_session_claude_is_error_raises(monkeypatch):
    """A claude result envelope with is_error=true raises (e.g. quota/auth)."""

    def fake_run(*a, **k):
        return _FakeProc(
            returncode=0, stdout='{"type":"result","is_error":true,"api_error_status":429,"result":"quota"}'
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("claude", ["claude", "-p"], "PROMPT")
    assert "quota" in str(exc.value) or "429" in str(exc.value)


def test_run_session_claude_success(monkeypatch):
    """A clean claude envelope (is_error false, exit 0) does not raise."""

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout='{"type":"result","is_error":false,"result":"done"}')

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("claude", ["claude", "-p"], "PROMPT")  # no raise


def test_run_session_nonzero_exit_raises(monkeypatch):
    def fake_run(*a, **k):
        return _FakeProc(returncode=2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("copilot", ["copilot", "-p", "x"], None)
    assert "copilot" in str(exc.value)


def test_run_session_empty_output_is_success_for_copilot(monkeypatch):
    """An agentic session that legitimately changed nothing prints nothing and exits 0 —
    that must NOT be treated as a failure (this is the old 'no ops JSON' parse-bug fix)."""

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None)  # no raise
    llm._run_session("gemini", ["gemini", "-p", "x"], None)  # no raise


def test_run_session_timeout_raises(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=config.LLM_TIMEOUT)

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("claude", ["claude", "-p"], "PROMPT")
    assert "timed out" in str(exc.value)


def test_run_ingest_session_wires_resolve_build_run(monkeypatch):
    """run_ingest_session resolves the CLI, builds the invocation, and runs the session once."""
    calls = {"resolve": 0, "run": 0}

    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.setattr(
        llm, "_resolve_cli", lambda cli: calls.__setitem__("resolve", calls["resolve"] + 1) or "/bin/copilot"
    )

    def fake_run_session(cli, argv, stdin_text, *, log_label=None):
        calls["run"] += 1
        assert cli == "copilot"
        assert "/bin/copilot" in argv[0]
        # The session is labelled with the kind + source key so a transcript log can name it.
        assert log_label == "ingest.raw/notes.md"

    monkeypatch.setattr(llm, "_run_session", fake_run_session)
    llm.run_ingest_session("raw/notes.md")
    assert calls == {"resolve": 1, "run": 1}


def test_run_session_writes_transcript_when_log_dir_set(tmp_path, monkeypatch):
    """With CITADEL_LLM_LOG_DIR set, _run_session records the prompt + full CLI output to a transcript
    file — the visibility fix for an agent run that otherwise leaves no record of what it did."""
    monkeypatch.setattr(config, "LLM_LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout="the model said hello", stderr="a warning")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None, log_label="ingest.raw/notes.md")

    logs = list(tmp_path.glob("*.log"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "the model said hello" in text  # stdout captured
    assert "a warning" in text  # stderr captured
    assert "ingest.raw_notes.md" in logs[0].name  # label sanitized into the filename


def test_run_session_no_transcript_when_log_dir_unset(tmp_path, monkeypatch):
    """The transcript is strictly opt-in: with no log dir configured, nothing is written (the
    captured, no-log path is the unchanged default)."""
    monkeypatch.setattr(config, "LLM_LOG_DIR", "", raising=False)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    def fake_run(*a, **k):
        return _FakeProc(returncode=0, stdout="x")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None)
    assert list(tmp_path.glob("*.log")) == []


def test_run_session_timeout_logs_partial_transcript(tmp_path, monkeypatch):
    """On a timeout, the transcript captures the PARTIAL output the TimeoutExpired carries (what the
    model produced before the kill) instead of an empty body — and notes that it timed out."""
    monkeypatch.setattr(config, "LLM_LOG_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="copilot", timeout=config.LLM_TIMEOUT, output="partial work so far")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        llm._run_session("copilot", ["copilot", "-p", "x"], None, log_label="ingest.raw/x.md")
    assert "timed out" in str(exc.value)

    logs = list(tmp_path.glob("*.log"))
    assert len(logs) == 1
    text = logs[0].read_text(encoding="utf-8")
    assert "partial work so far" in text  # the partial output is preserved, not dropped
    assert "timed out" in text  # and the transcript is annotated as a timeout


def test_run_session_verbose_uses_streaming_not_capture(monkeypatch):
    """With config.LLM_VERBOSE set, _run_session tees output via _stream_subprocess instead of the
    silent capture path — and still applies the same exit-code error detection to its result."""
    monkeypatch.setattr(config, "LLM_VERBOSE", True, raising=False)
    monkeypatch.setattr(config, "LLM_LOG_DIR", "", raising=False)

    used = {"stream": 0, "run": 0}

    def fake_stream(cli, argv, stdin_text):
        used["stream"] += 1
        return 0, "streamed transcript", ""

    def fake_run(*a, **k):  # must NOT be called in verbose mode
        used["run"] += 1
        return _FakeProc(returncode=0, stdout="")

    monkeypatch.setattr(llm, "_stream_subprocess", fake_stream)
    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._run_session("copilot", ["copilot", "-p", "x"], None)  # no raise
    assert used == {"stream": 1, "run": 0}
