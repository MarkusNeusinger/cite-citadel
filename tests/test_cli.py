"""Unit tests for citadel.cli — parser wiring, subcommand dispatch, exit codes, flag plumbing.

Everything runs offline through ``cli.main(argv)``: LLM-touching seams (``ingest.ingest``) and
the browser (``viewer.webbrowser``) are replaced with spies; ``search``/``tags``/``lint``/``check``
run their real implementations over a ``tmp_citadel`` wiki. ``serve`` is never invoked — we only
assert it is registered (it would block on stdio and import ``mcp``).
"""

from __future__ import annotations

import pytest

import citadel
from citadel import cli, config, viewer
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
    """Replace ``viewer.webbrowser`` with a :class:`BrowserSpy` so no browser ever launches."""
    spy = BrowserSpy()
    monkeypatch.setattr(viewer, "webbrowser", spy)
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


# --- lint: exit codes + flag plumbing -------------------------------------------------------


def test_lint_clean_wiki_exits_0(tmp_citadel, capsys):
    assert cli.main(["lint"]) == 0
    assert "Lint report" in capsys.readouterr().out


def test_lint_structural_error_exits_2(tmp_citadel, seed_page):
    seed_page("concepts/untyped.md", {"title": "No Type", "tags": []})  # missing `type` -> structural
    assert cli.main(["lint"]) == 2


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
