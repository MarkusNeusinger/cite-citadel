"""Unit tests for citadel.cli — parser wiring, subcommand dispatch, exit codes, flag plumbing.

Everything runs offline through ``cli.main(argv)``: LLM-touching seams (``ingest.ingest``) and
the browser (``viewer.webbrowser``) are replaced with spies; ``search``/``tags``/``lint``/``check``
run their real implementations over a ``tmp_citadel`` wiki. ``serve`` never reaches a real server
— it is only parsed, or driven into its MCP-SDK import failure (a real one would block on stdio).
"""

from __future__ import annotations

import io
import os
import re
import signal
import sys

import pytest

import citadel
from citadel import cli, config, manifest, viewer
from citadel import ingest as ingest_mod
from citadel import lint as lint_mod
from citadel import store as store_mod
from citadel.ingest import IngestReport
from citadel.lint import LintReport
from citadel.progress import ConsoleProgress


# --- shared spies / page material ----------------------------------------------------------


class IngestSpy:
    """Stands in for ``ingest.ingest``: records (paths, progress, extra kwargs such as
    ``full_rescan``), returns a canned report."""

    def __init__(self, report: IngestReport):
        self.report = report
        self.called = False
        self.paths = None
        self.progress = None
        self.kwargs: dict = {}

    def __call__(self, paths=None, progress=None, **kwargs):
        self.called = True
        self.paths = paths
        self.progress = progress
        self.kwargs = kwargs
        return self.report


class BrowserSpy:
    """Stands in for the ``webbrowser`` module inside ``viewer`` — records every URL opened."""

    def __init__(self, result: bool = True):
        self.result = result
        self.opened: list[str] = []

    def open(self, url: str) -> bool:
        self.opened.append(url)
        return self.result


def _report(**overrides) -> IngestReport:
    base: dict = {"processed": [], "skipped": [], "pages_written": [], "errors": []}
    base.update(overrides)
    return IngestReport(**base)


@pytest.fixture
def ingest_spy(monkeypatch):
    """Install an :class:`IngestSpy` over ``ingest.ingest`` (clean report) and return it."""
    spy = IngestSpy(_report())
    monkeypatch.setattr(ingest_mod, "ingest", spy)
    # Pin the observability knobs so the flag tests are deterministic and any mutation
    # cmd_ingest performs is rolled back by monkeypatch at teardown.
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)
    monkeypatch.setattr(config, "LLM_LOG_DIR", "logs-from-env", raising=False)
    return spy


@pytest.fixture
def browser_spy(monkeypatch):
    """Replace ``viewer.webbrowser`` with a :class:`BrowserSpy` so no browser ever launches, and
    pin non-WSL so the suite stays hermetic on a WSL dev box (the WSL open path — wslview /
    explorer.exe / wslpath — is exercised by its own tests in test_viewer.py)."""
    spy = BrowserSpy()
    monkeypatch.setattr(viewer, "webbrowser", spy)
    monkeypatch.setattr(viewer, "_is_wsl", lambda: False)
    return spy


@pytest.fixture
def good_page(tmp_citadel, seed_page, transformer_page):
    """A validation-clean page at concepts/transformer.md (with its cited raw source) — the
    canonical ``transformer_page`` agent output, seeded directly instead of via ingest."""
    (tmp_citadel.raw / "notes.md").write_text("source\n", encoding="utf-8")
    frontmatter, body = transformer_page["concepts/transformer.md"]
    seed_page("concepts/transformer.md", dict(frontmatter), body)
    return tmp_citadel


# --- parser: registration, unknown command, no args ---------------------------------------


def test_serve_subcommand_is_registered_but_never_invoked():
    # Parsing only — calling cmd_serve would import mcp and block on stdio.
    args = cli.build_parser().parse_args(["serve"])
    assert args.func is cli.cmd_serve


def test_every_documented_subcommand_is_registered():
    parser = cli.build_parser()
    funcs = {
        "ingest": cli.cmd_ingest,
        "serve": cli.cmd_serve,
        "tags": cli.cmd_tags,
        "lint": cli.cmd_lint,
        "check": cli.cmd_check,
        "view": cli.cmd_view,
    }
    for command, func in funcs.items():
        assert parser.parse_args([command]).func is func
    assert parser.parse_args(["search", "q"]).func is cli.cmd_search
    assert parser.parse_args(["define", "TDS"]).func is cli.cmd_define
    assert parser.parse_args(["raw", "raw/notes.md"]).func is cli.cmd_raw
    assert parser.parse_args(["neighbors", "concepts/x.md"]).func is cli.cmd_neighbors


def test_unknown_subcommand_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["frobnicate"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_no_args_exits_2(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_version_prints_and_exits_0_without_a_workspace(monkeypatch, tmp_path, capsys):
    """``citadel --version`` must work from a bare CWD with NO workspace at all: argparse's
    version action exits during parse_args, so main's fail-loud guard is never reached."""
    monkeypatch.chdir(tmp_path)  # a bare tmp CWD — no citadel.toml, no CITADEL_* dirs
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)  # what discovery resolves there
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"citadel {citadel.__version__}"


def test_runtime_error_from_subcommand_prints_to_stderr_and_returns_1(monkeypatch, capsys):
    def boom(**_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(viewer, "view", boom)
    assert cli.main(["view"]) == 1
    captured = capsys.readouterr()
    assert "error: boom" in captured.err


# --- ingest: dispatch, exit codes, flag plumbing -------------------------------------------


def test_ingest_dispatches_prints_report_and_returns_0(ingest_spy, capsys):
    assert cli.main(["ingest", "--quiet"]) == 0
    assert ingest_spy.called
    assert ingest_spy.paths is None  # no positional paths -> ingest all of raw/
    assert "Ingest complete" in capsys.readouterr().out


def test_ingest_full_rescan_flag_reaches_ingest(ingest_spy):
    """``--full-rescan`` hands ``full_rescan=True`` through to ``ingest.ingest`` (the flag must
    actually reach discovery); without it the kwarg is False."""
    assert cli.main(["ingest", "--quiet"]) == 0
    assert ingest_spy.kwargs["full_rescan"] is False
    assert cli.main(["ingest", "--quiet", "--full-rescan"]) == 0
    assert ingest_spy.kwargs["full_rescan"] is True


def test_ingest_forwards_explicit_paths(ingest_spy):
    assert cli.main(["ingest", "raw/a.md", "raw/b.md", "--quiet"]) == 0
    assert ingest_spy.paths == ["raw/a.md", "raw/b.md"]


def test_ingest_force_flag_reaches_ingest(ingest_spy):
    """``--force`` hands ``force=True`` through to ``ingest.ingest`` alongside the explicit paths; without the flag the kwarg defaults to False."""
    assert cli.main(["ingest", "--quiet", "raw/a.md"]) == 0
    assert ingest_spy.kwargs["force"] is False
    assert cli.main(["ingest", "--quiet", "--force", "raw/a.md"]) == 0
    assert ingest_spy.kwargs["force"] is True
    assert ingest_spy.paths == ["raw/a.md"]


def test_ingest_guidance_flag_sets_the_config_steer(ingest_spy, monkeypatch):
    """``--guidance`` lands in ``config.INGEST_GUIDANCE`` (read at call time by the prompt
    builder), overriding an env-set steer; an explicit ``--guidance ""`` disables the env steer
    for this run — the same convention as ``--log-dir ""``."""
    monkeypatch.setattr(config, "INGEST_GUIDANCE", "from-env", raising=False)
    assert cli.main(["ingest", "--quiet"]) == 0
    assert config.INGEST_GUIDANCE == "from-env"  # no flag: the env steer stands
    assert cli.main(["ingest", "--quiet", "--guidance", "create one\nmachine registry"]) == 0
    assert config.INGEST_GUIDANCE == "create one machine registry"  # newlines collapsed: line-shaped
    assert cli.main(["ingest", "--quiet", "--guidance", ""]) == 0
    assert config.INGEST_GUIDANCE == ""


def test_curate_guidance_flag_sets_the_config_steer_and_forwards_paths(monkeypatch, capsys):
    """`citadel curate --guidance` mirrors ingest's convention on the SECOND lifecycle: the flag
    lands in ``config.CURATE_GUIDANCE`` (read at call time when the findings are rendered),
    overrides the env twin, collapses newlines, and an explicit `--guidance ""` disables the env
    steer for this run. The positional paths reach ``curate.curate`` as its first argument — under
    a steer they are the ask itself, so they must not be dropped."""
    from citadel import curate as curate_mod

    class _Report:
        failed: list[str] = []

        def render(self) -> str:
            return ""

    seen: list[tuple] = []
    monkeypatch.setattr(curate_mod, "curate", lambda *a, **k: (seen.append((a, k)), _Report())[1])
    monkeypatch.setattr(config, "CURATE_GUIDANCE", "from-env", raising=False)

    assert cli.main(["curate", "--dry-run"]) == 0
    assert config.CURATE_GUIDANCE == "from-env"  # no flag: the env steer stands
    assert seen[-1][0] == (None,)  # no paths -> the whole wiki

    assert cli.main(["curate", "--guidance", "retitle the\nmachine pages", "registries/"]) == 0
    assert config.CURATE_GUIDANCE == "retitle the machine pages"  # newlines collapsed
    assert seen[-1][0] == (["registries/"],)

    assert cli.main(["curate", "--guidance", ""]) == 0
    assert config.CURATE_GUIDANCE == ""
    # The ingest steer is a SEPARATE knob — one lifecycle's steer never leaks into the other.
    assert cli.main(["curate", "--guidance", "curate-only"]) == 0
    assert config.INGEST_GUIDANCE != "curate-only"


def test_curate_guidance_over_the_cap_is_rejected(monkeypatch, capsys):
    """The shared cap guards the EFFECTIVE curate steer too (flag or CITADEL_CURATE_GUIDANCE),
    refused as a usage error before any session is planned."""
    from citadel import curate as curate_mod

    def boom(*_a, **_k):  # never reached: the cap check runs first
        raise AssertionError("curate must not run with an over-cap steer")

    monkeypatch.setattr(curate_mod, "curate", boom)
    monkeypatch.setattr(config, "CURATE_GUIDANCE", "", raising=False)
    oversize = "x" * (config.GUIDANCE_MAX_CHARS + 1)

    assert cli.main(["curate", "--guidance", oversize]) == 2
    assert "--guidance" in capsys.readouterr().err
    assert config.CURATE_GUIDANCE == ""  # the error path never mutates the config steer
    monkeypatch.setattr(config, "CURATE_GUIDANCE", oversize, raising=False)
    assert cli.main(["curate"]) == 2
    assert "CITADEL_CURATE_GUIDANCE" in capsys.readouterr().err


def test_ingest_guidance_over_the_cap_is_rejected(ingest_spy, monkeypatch, capsys):
    """A steer past GUIDANCE_MAX_CHARS is a usage error (exit 2) before ``ingest.ingest`` is ever
    called — the prompt must stay argv-safe; a document-sized steer belongs in rules/local.md.
    The cap guards the EFFECTIVE steer: the flag and an env-set CITADEL_INGEST_GUIDANCE alike."""
    monkeypatch.setattr(config, "INGEST_GUIDANCE", "", raising=False)
    oversize = "x" * (config.GUIDANCE_MAX_CHARS + 1)
    assert cli.main(["ingest", "--quiet", "--guidance", oversize]) == 2
    assert "--guidance" in capsys.readouterr().err
    assert config.INGEST_GUIDANCE == ""  # the error path never mutates the config steer
    monkeypatch.setattr(config, "INGEST_GUIDANCE", oversize, raising=False)
    assert cli.main(["ingest", "--quiet"]) == 2
    assert "CITADEL_INGEST_GUIDANCE" in capsys.readouterr().err
    assert not ingest_spy.called


def test_ingest_force_without_paths_is_rejected(ingest_spy):
    """The SAFER semantics are pinned here: ``citadel ingest --force`` with NO explicit paths is refused with a
    non-zero exit and ``ingest.ingest`` is never called. Forcing the ENTIRE corpus would re-run
    one agent session per source; that must never happen by accident — force requires explicit
    paths (``cmd_ingest`` refuses with exit 2 before ``ingest.ingest`` is reached)."""
    try:
        rc = cli.main(["ingest", "--quiet", "--force"])
    except SystemExit as exc:  # an argparse-level rejection is an acceptable implementation too
        rc = exc.code
    assert rc not in (0, None)
    assert not ingest_spy.called


def test_ingest_reingest_flag_reaches_ingest(ingest_spy):
    """``--reingest`` hands ``reingest=True`` through to ``ingest.ingest`` alongside the explicit
    paths; without the flag the kwarg defaults to False."""
    assert cli.main(["ingest", "--quiet", "raw/a.md"]) == 0
    assert ingest_spy.kwargs["reingest"] is False
    assert cli.main(["ingest", "--quiet", "--reingest", "raw/a.md"]) == 0
    assert ingest_spy.kwargs["reingest"] is True
    assert ingest_spy.paths == ["raw/a.md"]


def test_ingest_reingest_without_paths_is_rejected(ingest_spy, capsys):
    """Same explicit-paths rule as ``--force``, with sharper teeth (two sessions per source):
    ``--reingest`` alone is refused with exit 2 before ``ingest.ingest`` is reached."""
    assert cli.main(["ingest", "--quiet", "--reingest"]) == 2
    assert not ingest_spy.called
    assert "--reingest requires explicit paths" in capsys.readouterr().err


def test_ingest_reingest_refuses_force_and_retry(ingest_spy, capsys):
    """``--reingest`` and ``--force`` are different intents (strip-and-re-import vs reconcile in
    place) and refuse each other; ``--retry`` computes its own set and refuses both."""
    assert cli.main(["ingest", "--quiet", "--force", "--reingest", "raw/a.md"]) == 2
    assert cli.main(["ingest", "--quiet", "--retry", "--reingest"]) == 2
    assert not ingest_spy.called


def test_ingest_source_error_exits_1(ingest_spy):
    ingest_spy.report = _report(errors=["raw/a.md: agent failed"])
    assert cli.main(["ingest", "--quiet"]) == 1


def test_ingest_broken_links_exit_1(ingest_spy):
    ingest_spy.report = _report(broken_links=[("concepts/a.md", "concepts/gone.md")])
    assert cli.main(["ingest", "--quiet"]) == 1


def test_ingest_quiet_passes_no_progress(ingest_spy):
    cli.main(["ingest", "--quiet"])
    assert ingest_spy.progress is None


def test_ingest_default_progress_has_spinner(ingest_spy):
    cli.main(["ingest"])
    assert isinstance(ingest_spy.progress, ConsoleProgress)
    assert ingest_spy.progress.spinner is True


def test_ingest_verbose_flag_sets_config_and_drops_spinner(ingest_spy):
    assert cli.main(["ingest", "-v"]) == 0
    assert config.LLM_VERBOSE is True  # read at call time by llm._run_session
    assert isinstance(ingest_spy.progress, ConsoleProgress)
    assert ingest_spy.progress.spinner is False


def test_env_enabled_verbose_also_drops_spinner(monkeypatch, ingest_spy):
    """Regression: spinner suppression keys off the RESOLVED config.LLM_VERBOSE, not just the
    --verbose flag — a session enabled via CITADEL_LLM_VERBOSE used to keep the spinner, which
    clobbered the streamed transcript by rewriting the same line with \\r."""
    monkeypatch.setattr(config, "LLM_VERBOSE", True, raising=False)
    cli.main(["ingest"])
    assert isinstance(ingest_spy.progress, ConsoleProgress)
    assert ingest_spy.progress.spinner is False


def test_ingest_log_dir_flag_reaches_config(ingest_spy, tmp_path):
    log_dir = str(tmp_path / "transcripts")
    cli.main(["ingest", "--quiet", "--log-dir", log_dir])
    assert config.LLM_LOG_DIR == log_dir


def test_ingest_empty_log_dir_disables_logging(ingest_spy):
    """Regression: an explicit `--log-dir ""` must be honored as "disable logging" (the
    documented override of CITADEL_LLM_LOG_DIR). A truthiness check on args.log_dir silently
    fell through to the env value; cli.cmd_ingest must test `is not None` instead."""
    cli.main(["ingest", "--quiet", "--log-dir", ""])
    assert config.LLM_LOG_DIR == ""


def test_ingest_without_log_dir_keeps_env_value(ingest_spy):
    cli.main(["ingest", "--quiet"])
    assert config.LLM_LOG_DIR == "logs-from-env"


# --- search: flag plumbing into store.search + output --------------------------------------


def test_search_query_and_limit_reach_store_search(monkeypatch, capsys):
    seen = {}

    def fake_search(query, pages=None, limit=8):
        seen.update(query=query, pages=pages, limit=limit)
        return []

    monkeypatch.setattr(store_mod, "search", fake_search)
    assert cli.main(["search", "coffee", "--limit", "3"]) == 0
    assert seen == {"query": "coffee", "pages": None, "limit": 3}
    assert "No matches for 'coffee'." in capsys.readouterr().out


def test_search_nonpositive_limit_falls_back_to_default(monkeypatch, capsys):
    """``--limit 0`` (or negative) is treated as unset: the default 8 reaches store.search —
    matching wiki_search — instead of slicing the hits empty and printing a false "No matches"."""
    seen = {}

    def fake_search(query, pages=None, limit=8):
        seen["limit"] = limit
        return []

    monkeypatch.setattr(store_mod, "search", fake_search)
    assert cli.main(["search", "coffee", "--limit", "0"]) == 0
    assert seen["limit"] == 8
    assert cli.main(["search", "coffee", "--limit", "-3"]) == 0
    assert seen["limit"] == 8


def test_search_tag_prefilters_pages_case_insensitively(monkeypatch, tmp_citadel, seed_page):
    seed_page("concepts/ml.md", {"type": "Concept", "title": "ML", "tags": ["ML"]})
    seed_page("concepts/bio.md", {"type": "Concept", "title": "Bio", "tags": ["bio"]})
    seen = {}

    def fake_search(query, pages=None, limit=8):
        seen["pages"] = pages
        return []

    monkeypatch.setattr(store_mod, "search", fake_search)
    assert cli.main(["search", "x", "--tag", "ml"]) == 0
    assert [p.rel_path for p in seen["pages"]] == ["concepts/ml.md"]


def test_search_unknown_tag_prints_message_without_searching(monkeypatch, tmp_citadel, seed_page, capsys):
    seed_page("concepts/ml.md", {"type": "Concept", "title": "ML", "tags": ["ml"]})

    def fail_search(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("store.search must not be called for an unknown tag")

    monkeypatch.setattr(store_mod, "search", fail_search)
    assert cli.main(["search", "x", "--tag", "nope"]) == 0
    assert "No pages tagged 'nope'." in capsys.readouterr().out


def test_search_prints_hits_with_tags_and_snippet(good_page, capsys):
    assert cli.main(["search", "transformer"]) == 0
    out = capsys.readouterr().out
    assert "concepts/transformer.md\tTransformer\t" in out
    assert "[ml]" in out
    assert "Transformers use self-attention." in out  # the snippet line


# --- define ---------------------------------------------------------------------------------


def test_define_prints_abbreviation_glossary_entry(tmp_citadel, seed_page, capsys):
    seed_page(
        "abbreviations/tds.md",
        {"type": "Abbreviation", "title": "TDS — Total Dissolved Solids", "description": "Mineral content."},
    )
    assert cli.main(["define", "TDS"]) == 0
    out = capsys.readouterr().out
    assert "# Definition: TDS" in out
    assert "## TDS — Total Dissolved Solids" in out


def test_define_unknown_term_prints_fallback_message(tmp_citadel, seed_page, capsys):
    seed_page("concepts/a.md", {"type": "Concept", "title": "A"})
    assert cli.main(["define", "zzz-unknown"]) == 0
    assert "No glossary entry or exact-title page for 'zzz-unknown'." in capsys.readouterr().out


# --- tags -----------------------------------------------------------------------------------


def test_tags_empty_wiki(tmp_citadel, capsys):
    assert cli.main(["tags"]) == 0
    assert "No tags yet." in capsys.readouterr().out


def test_tags_lists_every_tag_with_pages(tmp_citadel, seed_page, capsys):
    seed_page("concepts/a.md", {"type": "Concept", "title": "A", "tags": ["ml", "ai"]})
    seed_page("concepts/b.md", {"type": "Concept", "title": "B", "tags": ["ml"]})
    assert cli.main(["tags"]) == 0
    out = capsys.readouterr().out
    assert "ai (1)" in out
    assert "ml (2)" in out
    assert out.index("ai (1)") < out.index("ml (2)")  # sorted
    assert "concepts/a.md\tA" in out


def test_tags_single_tag_case_insensitive(tmp_citadel, seed_page, capsys):
    seed_page("concepts/a.md", {"type": "Concept", "title": "A", "tags": ["ML"]})
    assert cli.main(["tags", "ml"]) == 0
    out = capsys.readouterr().out
    assert "# ml (1)" in out
    assert "- concepts/a.md\tA" in out


def test_tags_unknown_tag(tmp_citadel, seed_page, capsys):
    seed_page("concepts/a.md", {"type": "Concept", "title": "A", "tags": ["ml"]})
    assert cli.main(["tags", "nope"]) == 0
    assert "No pages tagged 'nope'." in capsys.readouterr().out


# --- read / neighbors / raw: error-path exit codes + messages -------------------------------


@pytest.mark.parametrize("command", ["read", "neighbors"])
def test_read_and_neighbors_unsafe_path_exits_1_without_doubled_prefix(tmp_citadel, command, capsys):
    """A traversal path exits 1 with ONE 'unsafe path:' prefix — cmd_read/cmd_neighbors used to
    wrap the already-self-describing OKFError into "error: unsafe path: unsafe path: …"."""
    assert cli.main([command, "../citadel.toml"]) == 1
    err = capsys.readouterr().err
    assert "error: unsafe path:" in err
    assert err.count("unsafe path:") == 1


def test_raw_unresolvable_locator_exits_1(tmp_citadel, capsys):
    """An unparseable --locator is a clear error (exit 1) like every other bad locator — it used
    to silently print the whole source with exit 0, undetectable by scripts."""
    from citadel import config, manifest

    (tmp_citadel.raw / "notes.md").write_text("hello\nworld\n", encoding="utf-8")
    key = config.rel_or_abs_posix(tmp_citadel.raw / "notes.md")
    manifest.save({key: manifest.make_entry("aa" * 32)})

    assert cli.main(["raw", key, "--locator", "gibberish locator"]) == 1
    captured = capsys.readouterr()
    assert "not offline-resolvable" in captured.err
    assert "hello" not in captured.out  # no silent whole-source fallback


# --- read / neighbors / raw / index / sources: SUCCESS + not-found dispatch through cli.main -
#
# These drive the CLI reader-twin HANDLERS end-to-end (the documented CLI<->MCP parity contract)
# — exit code + stdout/stderr — over a seeded wiki, complementing the store-level tests in
# test_define.py / test_neighbors.py / test_rawsource.py which call the providers directly.


def test_read_prints_page_text_and_exits_0(good_page, capsys):
    assert cli.main(["read", "concepts/transformer.md"]) == 0
    out = capsys.readouterr().out
    assert "title: Transformer" in out  # the frontmatter
    assert "Transformers use self-attention." in out  # the body
    assert out.endswith("\n")  # cmd_read guarantees a trailing newline


def test_read_missing_page_exits_1_with_not_found(good_page, capsys):
    """A typo'd rel_path is a FileNotFoundError inside store.read_page_text — cmd_read maps it to
    exit 1 with an actionable stderr line, never a silent empty 'OK'."""
    assert cli.main(["read", "concepts/no-such-page.md"]) == 1
    assert "error: page not found: concepts/no-such-page.md" in capsys.readouterr().err


def test_neighbors_prints_graph_and_exits_0(tmp_citadel, seed_page, capsys):
    seed_page(
        "concepts/a.md", {"type": "Concept", "title": "A", "description": "d", "tags": ["t"]}, "A links to [B](b.md).\n"
    )
    seed_page("concepts/b.md", {"type": "Concept", "title": "B", "description": "d", "tags": ["t"]}, "Plain B.\n")

    assert cli.main(["neighbors", "concepts/a.md"]) == 0
    out = capsys.readouterr().out
    assert "# Neighbors of concepts/a.md — A" in out
    assert "concepts/b.md — B" in out
    assert out.endswith("\n")


def test_neighbors_missing_page_exits_1_with_not_found(tmp_citadel, capsys):
    assert cli.main(["neighbors", "concepts/nope.md"]) == 1
    assert "error: page not found: concepts/nope.md" in capsys.readouterr().err


def test_raw_prints_cited_source_and_exits_0(tmp_citadel, capsys):
    from citadel import config, manifest

    (tmp_citadel.raw / "notes.md").write_text("hello\nworld\n", encoding="utf-8")
    key = config.rel_or_abs_posix(tmp_citadel.raw / "notes.md")
    manifest.save({key: manifest.make_entry("aa" * 32)})

    assert cli.main(["raw", key]) == 0
    out = capsys.readouterr().out
    assert "hello" in out and "world" in out  # the whole source, line-numbered
    assert out.endswith("\n")


def test_raw_uncited_key_exits_1(tmp_citadel, capsys):
    """A key the wiki does not cite (absent from the manifest) is a SourceError — cmd_raw maps the
    provenance-gate rejection to exit 1, never dumping an arbitrary file."""
    (tmp_citadel.raw / "secret.md").write_text("uncited\n", encoding="utf-8")
    assert cli.main(["raw", "raw/secret.md"]) == 1
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert "uncited" not in captured.out  # never leaked an ungated file


def test_index_prints_generated_catalog_and_exits_0(tmp_citadel, seed_page, capsys):
    from citadel import config, manifest
    from citadel import store as store_module

    (tmp_citadel.raw / "notes.md").write_text("src\n", encoding="utf-8")
    seed_page(
        "concepts/x.md",
        {"type": "Concept", "title": "X", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
    )
    manifest.save({"raw/notes.md": manifest.make_entry("aa" * 32, "claude:sonnet", config.rules_version())})
    store_module.rebuild_indexes()

    assert cli.main(["index"]) == 0
    out = capsys.readouterr().out
    assert "# Wiki Index" in out and "concepts/x.md" in out


def test_index_without_a_wiki_yet_exits_0_with_hint(tmp_citadel, capsys):
    """No index.md on disk (never ingested) is not an error — cmd_index prints a build hint and
    still exits 0 (the FileNotFoundError branch)."""
    assert cli.main(["index"]) == 0
    assert "No wiki index yet" in capsys.readouterr().out


def test_sources_prints_generated_catalog_and_exits_0(tmp_citadel, seed_page, capsys):
    from citadel import config, manifest
    from citadel import store as store_module

    (tmp_citadel.raw / "notes.md").write_text("src\n", encoding="utf-8")
    seed_page(
        "concepts/x.md",
        {"type": "Concept", "title": "X", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - n\n",
    )
    manifest.save({"raw/notes.md": manifest.make_entry("aa" * 32, "claude:sonnet", config.rules_version())})
    store_module.rebuild_indexes()

    assert cli.main(["sources"]) == 0
    out = capsys.readouterr().out
    assert "# Sources" in out and "raw/notes.md" in out


def test_sources_without_a_catalog_yet_exits_0_with_hint(tmp_citadel, capsys):
    assert cli.main(["sources"]) == 0
    assert "No sources catalog yet" in capsys.readouterr().out


# --- lint: exit codes + flag plumbing -------------------------------------------------------


def test_lint_clean_wiki_exits_0(tmp_citadel, capsys):
    assert cli.main(["lint"]) == 0
    assert "Lint report" in capsys.readouterr().out


def test_lint_structural_error_exits_3(tmp_citadel, seed_page):
    """An unclean report exits with lint's OWN code 3 — 2 previously collided with the
    usage/no-workspace code, so CI could not tell "wiki has problems" from "invoked wrong"."""
    seed_page("concepts/untyped.md", {"title": "No Type", "tags": []})  # missing `type` -> structural
    assert cli.main(["lint"]) == 3


def test_lint_advisory_findings_keep_exit_0(good_page):
    # A single valid page is an orphan (and carries no other structural problem) —
    # advisory categories must not flip the exit code.
    assert cli.main(["lint"]) == 0


def test_lint_stale_days_flag_reaches_lint(monkeypatch):
    seen = {}

    def fake_lint(pages=None, stale_days=365):
        seen["stale_days"] = stale_days
        return LintReport()

    monkeypatch.setattr(lint_mod, "lint", fake_lint)
    assert cli.main(["lint", "--stale-days", "30"]) == 0
    assert seen["stale_days"] == 30
    cli.main(["lint"])
    assert seen["stale_days"] == 365  # documented default


# --- check: exit codes + path filtering -----------------------------------------------------


def test_check_clean_wiki_exits_0(good_page, capsys):
    assert cli.main(["check"]) == 0
    assert "OK" in capsys.readouterr().out


def test_check_validation_error_exits_1(tmp_citadel, seed_page, capsys):
    seed_page("concepts/bad.md", {"title": "Bad"})  # missing type/description/tags/resource
    assert cli.main(["check"]) == 1
    assert "concepts/bad.md" in capsys.readouterr().out


def test_check_rel_path_filter_scopes_the_report(good_page, seed_page, capsys):
    seed_page("concepts/bad.md", {"title": "Bad"})
    # Scoped to the clean page: the bad page's errors are filtered out -> exit 0.
    assert cli.main(["check", "concepts/transformer.md"]) == 0
    assert "concepts/bad.md" not in capsys.readouterr().out
    # Scoped to the bad page: exit 1 and only that page reported.
    assert cli.main(["check", "concepts/bad.md"]) == 1
    out = capsys.readouterr().out
    assert "concepts/bad.md" in out
    assert "concepts/transformer.md" not in out


def test_check_accepts_absolute_file_path_inside_wiki(good_page, seed_page):
    bad = seed_page("concepts/bad.md", {"title": "Bad"})
    assert cli.main(["check", str(bad)]) == 1


def test_check_nonexistent_page_is_an_error(good_page, capsys):
    # A typo'd path must never read as a clean "OK" (false green in CI).
    assert cli.main(["check", "concepts/no-such-page.md"]) == 1
    assert "error: no such page: concepts/no-such-page.md" in capsys.readouterr().out


def test_check_generated_file_is_named_not_validated(good_page, capsys):
    # index.md exists on disk but is generated — excluded from validation, so name that
    # instead of pretending it was checked.
    (good_page.wiki / "index.md").write_text("# Index\n", encoding="utf-8")
    assert cli.main(["check", "index.md"]) == 1
    assert "error: not a validated page: index.md" in capsys.readouterr().out


def test_check_reports_missing_alongside_existing_pages(good_page, capsys):
    # One existing clean page + one typo: the miss is an error, the clean page still reports.
    assert cli.main(["check", "concepts/transformer.md", "concepts/typo.md"]) == 1
    out = capsys.readouterr().out
    assert "error: no such page: concepts/typo.md" in out


# --- view: writes the offline viewer, never opens a real browser ----------------------------


def test_view_out_and_no_open_writes_file_without_browser(good_page, browser_spy, tmp_path, capsys):
    out_file = tmp_path / "viewer" / "wiki.html"
    assert cli.main(["view", "--no-open", "--out", str(out_file)]) == 0
    assert out_file.is_file()
    assert browser_spy.opened == []
    assert "wrote" in capsys.readouterr().out


def test_view_default_out_is_wiki_dotfile(good_page, browser_spy):
    assert cli.main(["view", "--no-open"]) == 0
    assert (good_page.wiki / ".citadel_viewer.html").is_file()


def test_view_opens_browser_by_default(good_page, browser_spy, tmp_path):
    out_file = tmp_path / "wiki.html"
    assert cli.main(["view", "--out", str(out_file)]) == 0
    assert browser_spy.opened == [out_file.resolve().as_uri()]


def test_view_browser_failure_prints_hint_but_exits_0(good_page, browser_spy, tmp_path, capsys):
    browser_spy.result = False  # headless box: webbrowser.open reports failure
    assert cli.main(["view", "--out", str(tmp_path / "wiki.html")]) == 0
    assert "could not launch a browser" in capsys.readouterr().out


def test_view_obsidian_deep_links_instead_of_writing(good_page, browser_spy, capsys):
    assert cli.main(["view", "--obsidian"]) == 0
    assert len(browser_spy.opened) == 1
    assert browser_spy.opened[0].startswith("obsidian://open?path=")
    out = capsys.readouterr().out
    assert "Obsidian" in out
    assert not (good_page.wiki / ".citadel_viewer.html").exists()  # no viewer file in obsidian mode


# --- Ctrl+C: exit 130 with the wiki's state, never a traceback ----------------------------------


class _TtyStream(io.StringIO):
    """An in-memory stderr that claims to be a terminal, so ConsoleProgress opens its real live
    region (spinner rows + overall bar) on it, exactly as on a console."""

    def isatty(self):
        return True


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _note(err: str) -> list[str]:
    """The interrupt note's lines: everything from the ``interrupted`` line on, ANSI removed."""
    lines = _ANSI.sub("", err).splitlines()
    start = max(i for i, line in enumerate(lines) if line.startswith("interrupted"))
    return lines[start:]


def test_ctrl_c_during_ingest_exits_130_with_the_state_after_stopping_the_live_region(tmp_citadel, monkeypatch):
    """Ingest re-raises a captured Ctrl+C after rolling back the source in flight and finalizing
    the finished ones. main must turn that into exit 130 plus a note saying what was kept and how to
    continue — and cmd_ingest must take the live region down FIRST, or the note is drawn into a
    stale spinner region that keeps refreshing over it."""
    seen = {}

    class Stderr(_TtyStream):
        def write(self, text):
            if text.startswith("interrupted"):
                seen["live_at_note"] = seen["progress"]._live
            return super().write(text)

    def interrupted_ingest(paths=None, progress=None, **_kwargs):
        seen["progress"] = progress
        progress("start", {"pending": 2, "skipped": 0})
        progress("source_start", {"index": 1, "total": 2, "source": "raw/a.md"})
        assert progress._live is not None  # precondition: a real live region is up
        raise KeyboardInterrupt  # what ingest re-raises after its rollback + finalize

    stderr = Stderr()
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(ingest_mod, "ingest", interrupted_ingest)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    assert cli.main(["ingest"]) == 130
    assert seen["progress"]._live is None
    assert seen["live_at_note"] is None  # stopped BEFORE the note was written
    err = stderr.getvalue()
    assert "Traceback" not in err and "KeyboardInterrupt" not in err
    note = _note(err)
    assert note == [
        "interrupted: sources finished before Ctrl+C are kept in the wiki; any source still in flight was rolled back.",
        "Run `citadel status` to see what is still pending and `citadel ingest` to continue.",
    ]
    assert all(line.isascii() for line in note)  # a cp1252 console must be able to print it


def test_stopping_the_live_region_again_after_a_normal_run_is_harmless(tmp_citadel, monkeypatch):
    """The cleanup sends ``done`` unconditionally — on a normal run ingest has already sent it from
    its finalize step, so the second stop must be a silent no-op, not an error or a second report."""
    seen = {}

    def clean_ingest(paths=None, progress=None, **_kwargs):
        seen["progress"] = progress
        progress("start", {"pending": 1, "skipped": 0})
        progress("done", {"processed": 1, "created": 1, "updated": 0, "deleted": 0, "broken": 0})
        return _report(processed=["raw/a.md"])

    monkeypatch.setattr(sys, "stderr", _TtyStream())
    monkeypatch.setattr(ingest_mod, "ingest", clean_ingest)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    assert cli.main(["ingest"]) == 0
    assert seen["progress"]._live is None


def _interrupted_with(report=None):
    """A stand-in for ``ingest.ingest`` that re-raises Ctrl+C the way the real one does: after its
    finalize step, with the run's report riding on the exception (None: interrupted before any
    source ran, so there is no report to carry)."""

    def interrupted(*_args, **_kwargs):
        exc = KeyboardInterrupt()
        if report is not None:
            exc.citadel_report = report
        raise exc

    return interrupted


@pytest.mark.parametrize(
    ("argv", "report", "hint"),
    [
        (
            ["ingest", "--force", "raw/a.md", "raw/b.md"],
            _report(processed=["raw/a.md"]),
            "Re-run `citadel ingest --force` on the requested paths NOT listed under Processed above "
            "(those are done; forcing them again re-pays their sessions).",
        ),
        (
            ["ingest", "--force", "raw/a.md"],
            None,
            "No source finished; re-run the same `citadel ingest --force` command.",
        ),
        (
            ["ingest", "--retry"],
            None,
            "Re-run the same `citadel ingest --retry` command to continue with whatever is still stuck.",
        ),
    ],
)
def test_ctrl_c_during_a_forced_ingest_points_at_the_right_way_on(tmp_citadel, monkeypatch, capsys, argv, report, hint):
    """A plain run re-detects whatever the interrupt left; a forced one does not (a rolled-back
    reconcile still reads as ingested), so "run `citadel ingest`" would silently do nothing for it.
    Which forced paths are done is read off the printed report, never off `citadel status`: its
    last-checked column is a DATE, so a source finished this run and one checked earlier the same
    day look identical. ``--retry`` recomputes its stuck set, so re-running it is the continuation."""
    monkeypatch.setattr(ingest_mod, "ingest", _interrupted_with(report))
    monkeypatch.setattr(ingest_mod, "retry_candidates", lambda: (["raw/a.md"], []))
    assert cli.main([*argv, "--quiet"]) == 130
    captured = capsys.readouterr()
    note = _note(captured.err)
    assert note[0].startswith("interrupted: sources finished before Ctrl+C are kept in the wiki")
    assert note[1] == hint
    if report is not None:  # the continuation list the hint points at is on stdout
        assert "Processed:\n  - raw/a.md" in captured.out


_REINGEST_REST = "Re-run `citadel ingest --reingest` on the requested paths not listed under Processed."


@pytest.mark.parametrize(
    ("report", "note_tail"),
    [
        (
            # `--reingest a b c`: a re-imported, b stripped only, c's cleanup in flight (rolled back).
            _report(processed=["raw/a.md"], reingest_cleaned=["raw/a.md", "raw/b.md"]),
            [
                "These were stripped but not yet re-imported, so they are OUT of the wiki until "
                "`citadel ingest <path>` imports them fresh: raw/b.md",
                "Re-run `citadel ingest --reingest` on every other requested path not listed under "
                "Processed (its old treatment is untouched).",
            ],
        ),
        (_report(processed=["raw/a.md", "raw/b.md"], reingest_cleaned=["raw/a.md", "raw/b.md"]), [_REINGEST_REST]),
        (None, [_REINGEST_REST]),
    ],
)
def test_ctrl_c_during_a_reingest_names_the_sources_left_out_of_the_wiki(
    tmp_citadel, monkeypatch, capsys, report, note_tail
):
    """``--reingest`` is NOT rolled back as a unit: its cleanups run first and each one strips the
    source and drops its manifest key as it finishes, so a Ctrl+C during the fresh imports leaves
    those sources absent from the wiki. The note names each one and the way back — a PLAIN ingest of
    the path (it is untracked now; another --reingest would only re-clean it) — and still sends every
    requested path whose cleanup never finished back through --reingest."""
    monkeypatch.setattr(ingest_mod, "ingest", _interrupted_with(report))
    assert cli.main(["ingest", "--reingest", "raw/a.md", "raw/b.md", "raw/c.md", "--quiet"]) == 130
    note = _note(capsys.readouterr().err)
    assert note == [
        "interrupted: sources listed under Processed above are re-imported; a cleanup still in flight was rolled back.",
        *note_tail,
    ]
    assert "kept in the wiki" not in note[0]
    assert all(line.isascii() for line in note)


def test_report_never_calls_a_stripped_only_reingest_source_re_ingested():
    """A cleanup is booked before its fresh import runs, so an interrupted (or failed) --reingest
    leaves cleaned keys that were never re-imported. The printed report must say they are OUT of the
    wiki — the same state the interrupt note names — not "Re-ingested fresh"."""
    text = _report(processed=["raw/a.md"], reingest_cleaned=["raw/a.md", "raw/b.md"]).render()
    fresh, stripped = text.split("Stripped for re-ingest but NOT re-imported")
    assert "Re-ingested fresh" in fresh and "  - raw/a.md" in fresh and "raw/b.md" not in fresh.split("Re-ingested")[1]
    assert "  - raw/b.md" in stripped and "raw/a.md" not in stripped


@pytest.mark.parametrize(
    "error", [BrokenPipeError(32, "Broken pipe"), ValueError("I/O operation on closed file.")], ids=["broken", "closed"]
)
def test_ctrl_c_with_a_dead_stdout_still_exits_130_and_still_writes_the_note(tmp_citadel, monkeypatch, error):
    """`citadel ingest | tee log` + Ctrl+C: the same SIGINT can take stdout down (BrokenPipeError,
    or ValueError once the stream is truly closed) inside the very handler that exists to replace a
    traceback. Each write is best-effort ON ITS OWN, so the dead report write costs neither the exit
    code nor the stderr note."""

    class _DeadStream(io.StringIO):
        def write(self, text):
            raise error

    stderr = io.StringIO()
    monkeypatch.setattr(ingest_mod, "ingest", _interrupted_with(_report(processed=["raw/a.md"])))
    monkeypatch.setattr(sys, "stdout", _DeadStream())
    monkeypatch.setattr(sys, "stderr", stderr)
    assert cli.main(["ingest", "--force", "raw/a.md", "--quiet"]) == 130
    assert stderr.getvalue().startswith("interrupted: sources finished before Ctrl+C are kept in the wiki")

    monkeypatch.setattr(sys, "stderr", _DeadStream())  # and both streams dead: still a clean 130
    assert cli.main(["ingest", "--force", "raw/a.md", "--quiet"]) == 130


@pytest.mark.parametrize(
    "argv", [["ingest", "raw/big.pdf"], ["ingest", "--guidance", "one machine registry"], ["ingest", "--guidance", ""]]
)
def test_ctrl_c_during_a_scoped_or_steered_ingest_says_re_run_the_same_command(tmp_citadel, monkeypatch, capsys, argv):
    """A bare `citadel ingest` would be a different run: it drops the --guidance steer (part of a
    chunked source's resume-checkpoint identity, so the segments already paid for are bought again)
    and sweeps in every pending source the path list left out. An explicit ``--guidance ""`` (an
    env steer switched off) is part of the command too."""
    monkeypatch.setattr(config, "INGEST_GUIDANCE", "", raising=False)  # restored after the flag sets it

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ingest_mod, "ingest", interrupted)
    assert cli.main([*argv, "--quiet"]) == 130
    note = _note(capsys.readouterr().err)
    assert note[1] == (
        "Run `citadel status` to see what is still pending, then re-run the same `citadel ingest` "
        "command (same paths and flags) to continue."
    )


def test_ctrl_c_during_refresh_exits_130_and_stops_the_live_region(tmp_citadel, monkeypatch):
    """Refresh IS a forced ingest underneath, so the same re-raise reaches cmd_refresh — which must
    stop its own live region too, and say that the unreached sources are still at the queue head."""
    from citadel import refresh as refresh_mod

    seen = {}

    def interrupted_refresh(progress=None, **_kwargs):
        seen["progress"] = progress
        progress("start", {"pending": 1, "skipped": 0})
        assert progress._live is not None
        raise KeyboardInterrupt

    stderr = _TtyStream()
    monkeypatch.setattr(sys, "stderr", stderr)
    monkeypatch.setattr(refresh_mod, "refresh", interrupted_refresh)
    monkeypatch.setattr(config, "LLM_VERBOSE", False, raising=False)

    assert cli.main(["refresh", "--limit", "3"]) == 130
    assert seen["progress"]._live is None
    note = _note(stderr.getvalue())
    assert "keeps its old last-checked stamp" in note[0]
    assert note[1].startswith(
        "Re-run the same `citadel refresh` command to continue, with --limit lowered by the sources listed under "
        "Processed above"
    )


def test_ctrl_c_during_curate_exits_130_with_the_cluster_state(tmp_citadel, monkeypatch, capsys):
    """Curate promotes each cluster as it finishes and rolls back the one in flight, but the
    interrupt skips its end-of-run index rebuild — the note says so, and how the next run heals it."""
    from citadel import curate as curate_mod

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(curate_mod, "curate", interrupted)
    monkeypatch.setattr(config, "CURATE_GUIDANCE", "", raising=False)
    assert cli.main(["curate"]) == 130
    err = capsys.readouterr().err
    assert "Traceback" not in err
    note = _note(err)
    assert note == [
        "interrupted: clusters applied before Ctrl+C are kept in the wiki (indexes rebuilt); the one in flight "
        "was rolled back.",
        "Run `citadel curate` to continue - it recomputes its plan.",
    ]


@pytest.mark.parametrize(
    ("argv", "env_steer", "named_again"),
    [
        (["curate", "--limit", "3"], "", False),
        (["curate", "--stale-rules"], "", False),
        (["curate", "--retry"], "", False),
        (["curate", "concepts/"], "", False),  # paths without a steer only FILTER the detector plan
        (["curate", "--guidance", "retitle the machine pages", "registries/"], "", True),
        (["curate", "registries/"], "retitle the machine pages", True),  # CITADEL_CURATE_GUIDANCE steers too
    ],
)
def test_ctrl_c_during_a_scoped_curate_says_re_run_the_same_command(
    tmp_citadel, monkeypatch, capsys, argv, env_steer, named_again
):
    """A bare `citadel curate` after a scoped run is a different, often far bigger one: no --limit
    means one paid session per flagged cluster wiki-wide, and no steer/paths means the guided pages
    still to do are never planned. A page named under --guidance is planned whatever its state, so
    re-running the same command re-plans the ones already done — the note says so."""
    from citadel import curate as curate_mod

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(curate_mod, "curate", interrupted)
    monkeypatch.setattr(config, "CURATE_GUIDANCE", env_steer, raising=False)  # restored after the flag sets it
    assert cli.main(argv) == 130
    note = _note(capsys.readouterr().err)
    assert note[1].startswith(
        "Re-run the same `citadel curate` command (same paths and flags) to continue - it recomputes its plan"
    )
    assert note[1].endswith(".") and "rebuilds the indexes" not in note[1]
    assert ("a page named under --guidance is planned again even if done" in note[1]) is named_again
    assert "Run `citadel curate` to continue" not in note[1]


def test_ctrl_c_during_curate_stale_rules_points_at_refresh(tmp_citadel, monkeypatch, capsys):
    """Curate never re-stamps a source, so re-running an interrupted --stale-rules plans the
    applied clusters again: the note names the refresh command that clears (stale)."""
    from citadel import curate as curate_mod

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(curate_mod, "curate", interrupted)
    monkeypatch.setattr(config, "CURATE_GUIDANCE", "", raising=False)
    src = tmp_citadel.raw / "old.md"
    src.write_text("body\n", encoding="utf-8")
    tracked = manifest.load()
    tracked["raw/old.md"] = manifest.make_entry(manifest.file_sha256(src), "claude:sonnet", "0000oldrules")
    manifest.save(tracked)
    assert cli.main(["curate", "--stale-rules"]) == 130
    note = _note(capsys.readouterr().err)
    assert "`citadel refresh --stale-rules --limit 1` re-verifies the stale sources" in note[2]
    assert all(line.isascii() for line in note)


@pytest.mark.parametrize("argv", [["view", "--no-open"], ["curate", "--dry-run"], ["serve"]])
def test_ctrl_c_in_a_command_that_changed_nothing_is_a_plain_note(tmp_citadel, monkeypatch, capsys, argv):
    """A read-only command, a dry run, or a stdio server stopped from the terminal changed nothing:
    exit 130 with a bare ``interrupted`` — no lifecycle state to report, and no traceback."""
    from citadel import curate as curate_mod

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(viewer, "view", interrupted)
    monkeypatch.setattr(curate_mod, "curate", interrupted)
    monkeypatch.setattr("citadel.server.main", interrupted)
    assert cli.main(argv) == 130
    assert capsys.readouterr().err == "interrupted\n"


@pytest.mark.skipif(os.name != "posix", reason="the die-of-SIGINT convention is POSIX shells'")
def test_ctrl_c_at_the_process_entry_dies_of_sigint_so_a_shell_loop_stops(tmp_citadel, monkeypatch, capsys):
    """A process that EXITS 130 reads to bash as "the child handled Ctrl+C", so a
    `for f in raw/*.md; do citadel ingest "$f"; done` loop would start the next paid session; one
    that DIES of SIGINT stops it. So the process entry (main() called bare, as the console script
    and `python -m citadel` do) re-delivers SIGINT with the default action after printing its note,
    while an in-process caller passing argv keeps getting 130 back. Both syscalls are faked here —
    the real ones would end the test run."""
    calls = []
    monkeypatch.setattr(signal, "signal", lambda signum, handler: calls.append(("signal", signum, handler)))
    monkeypatch.setattr(os, "kill", lambda pid, signum: calls.append(("kill", pid, signum)))

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(viewer, "view", interrupted)

    assert cli.main(["view", "--no-open"]) == 130
    assert calls == []  # argv given: an in-process caller, never killed

    monkeypatch.setattr(sys, "argv", ["citadel", "view", "--no-open"])
    assert cli.main() == 130  # the faked kill returns, so the plain-130 fallback is what remains
    assert calls == [("signal", signal.SIGINT, signal.SIG_DFL), ("kill", os.getpid(), signal.SIGINT)]
    assert capsys.readouterr().err == "interrupted\ninterrupted\n"  # the note still prints first


# --- serve: an unusable MCP SDK is a remedy, not a traceback ------------------------------------


@pytest.mark.parametrize("argv", [["serve"], ["serve", "--http"]])
def test_serve_with_an_mcp_sdk_lacking_mcpserver_exits_1_with_the_remedy(tmp_citadel, monkeypatch, capsys, argv):
    """A 1.x SDK has no ``mcp.server.mcpserver``, which citadel.server imports at load time (and
    httpserve through it): both transports must exit 1 naming the failed import and the reinstall
    command, instead of a ModuleNotFoundError traceback. The command is ``citadel doctor``'s own
    (worded for the installed version, spelled for this install) — never a copy that could drift
    from what doctor tells the same user about the same environment."""
    from citadel import doctor

    # A None entry makes the import machinery raise ModuleNotFoundError for that name; dropping the
    # loaded citadel.server forces the real import chain to run again (monkeypatch restores both).
    monkeypatch.setitem(sys.modules, "mcp.server.mcpserver", None)
    monkeypatch.delitem(sys.modules, "citadel.server", raising=False)
    monkeypatch.delattr(citadel, "server", raising=False)
    monkeypatch.setattr(doctor, "mcp_sdk_version", lambda: "1.28.1")  # the breakage: a 1.x SDK installed

    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert err.startswith("error: `citadel serve` cannot start - the installed MCP SDK does not import")
    assert "mcp.server.mcpserver" in err
    assert err.rstrip("\n").endswith(doctor.mcp_sdk_remedy("1.28.1"))
    assert "citadel needs mcp>=2,<3 - run: " in err


def test_serve_does_not_relabel_an_unrelated_import_error(tmp_citadel, monkeypatch):
    """Only an ImportError about the MCP SDK itself gets the mcp>=2,<3 remedy: a broken citadel module
    is a real bug, and pointing its user at a reinstall of mcp would send them the wrong way."""
    monkeypatch.setitem(sys.modules, "citadel.server", None)
    monkeypatch.delattr(citadel, "server", raising=False)
    with pytest.raises(ImportError) as exc:
        cli.main(["serve"])
    assert exc.value.name == "citadel.server"
