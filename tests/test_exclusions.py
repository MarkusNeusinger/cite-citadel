"""Corpus exclusions inside agent sessions (#157), offline.

Discovery keeps excluded files out of the source list; these tests pin what keeps a SESSION from
opening one anyway and what catches it when it did:

- the run instruction's ``Excluded from this corpus`` bullet (every backend);
- claude's narrowed shell (no bare ``Bash``) and per-path Read denies in a ``--settings`` file;
- copilot's ``--deny-tool`` list;
- the post-hoc citation guard in ``validate.source_issues`` (check / lint / curate / ingest);
- ``permission_denials`` surfaced as a run warning, never a failure;
- doctor's per-backend enforcement line.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from citadel import config, curate, doctor, ingest, lint, llm, manifest, readdeny, resume, store, validate


PROMPT_CHAR_BUDGET = 8000


# --- (a) the run-instruction bullet ---------------------------------------------------------


def test_exclusion_bullet_only_when_user_exclusions_are_configured(tmp_citadel, monkeypatch):
    prompt = llm._build_instruction("raw/notes.md", "ingest")
    assert "Excluded from this corpus" not in prompt  # the 22 built-in junk globs never count

    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "private", "*.secret"])
    prompt = llm._build_instruction("raw/notes.md", "ingest")
    assert "Excluded from this corpus" in prompt
    assert "private, *.secret" in prompt
    assert "Thumbs.db" not in prompt


@pytest.mark.parametrize("kind", ["ingest", "reconcile", "pdf", "image", "audio", "repo", "curate"])
def test_exclusion_bullet_for_every_kind_that_may_open_raw_files(tmp_citadel, monkeypatch, kind):
    monkeypatch.setattr(config, "INCLUDE_PATTERNS", ["*.pdf"])
    read_path = "/tmp/x.md" if kind in ("pdf", "audio", "curate") else None
    assert "Excluded from this corpus" in llm._build_instruction("raw/a.pdf", kind, read_path)


def test_exclusion_bullet_never_for_delete(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", 1000)
    assert "Excluded from this corpus" not in llm._build_instruction("raw/gone.md", "delete")


def test_exclusion_bullet_is_capped_so_the_prompt_size_guard_holds(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, *(f"pattern-{i}" for i in range(200))])
    prompt = llm._build_instruction("raw/notes.md", "ingest")
    assert "+180 more" in prompt
    assert len(prompt) < PROMPT_CHAR_BUDGET


@pytest.mark.parametrize(
    ("attr", "value"), [("IGNORE_PATTERNS", ["private"]), ("INCLUDE_PATTERNS", ["*.pdf"]), ("MAX_SOURCE_BYTES", 10)]
)
def test_exclusion_inputs_join_the_resume_identity(monkeypatch, attr, value):
    before = resume.knob_stamp()
    current = getattr(config, attr)
    monkeypatch.setattr(config, attr, [*current, *value] if isinstance(current, list) else value)
    assert resume.knob_stamp() != before


# --- (b1)/(c) argv --------------------------------------------------------------------------


def _probe(monkeypatch, text: str) -> None:
    monkeypatch.setattr(llm, "_cli_help_text", lambda _path: text)


def test_claude_argv_has_no_bare_bash_and_narrows_the_shell(monkeypatch):
    _probe(monkeypatch, "")
    argv, _ = llm._build_invocation("claude", "/bin/claude", "P")
    allowed = argv[argv.index("--allowedTools") + 1 : argv.index("--disallowedTools")]
    assert "Bash" not in allowed and "Read Edit Write Grep Glob Bash" not in argv
    assert "Bash(citadel check)" in allowed and "Bash(uv run python -m citadel check *)" in allowed
    for cmd in ("rm", "rmdir", "mv", "mkdir"):
        assert f"Bash({cmd} *)" in allowed
    assert not any(r.startswith(("Bash(python -c", "Bash(node", "Bash(uv run python -c")) for r in allowed)
    denied = argv[argv.index("--disallowedTools") + 1 :][:4]
    assert denied == ["Bash(grep *)", "Bash(rg *)", "Bash(find *)", "Bash(cp *)"]
    assert "--permission-prompts" not in argv  # not advertised -> never passed
    assert "--settings" not in argv


def test_claude_argv_adds_permission_prompts_and_settings_when_advertised(monkeypatch):
    _probe(monkeypatch, "  --permission-prompts <target>\n  --settings <file-or-json>\n")
    argv, _ = llm._build_invocation("claude", "/bin/claude", "P", settings_path="/tmp/s.json")
    assert argv[argv.index("--permission-prompts") + 1] == "none"
    assert argv[argv.index("--settings") + 1] == "/tmp/s.json"


def test_copilot_argv_denies_interpreters_and_readers():
    argv, _ = llm._build_invocation("copilot", "/bin/copilot", "P")
    denied = [argv[i + 1] for i, a in enumerate(argv) if a == "--deny-tool"]
    assert denied == list(llm._COPILOT_DENIED_TOOLS)
    assert "shell(python)" in denied and "shell(cat)" in denied


def test_agy_argv_is_unchanged():
    argv, _ = llm._build_invocation("agy", "/bin/agy", "P")
    assert "--deny-tool" not in argv and "--settings" not in argv


# --- (b2) the Read-deny settings file -------------------------------------------------------


def _private_layout(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "private", "*.secret"])
    (tmp_citadel.raw / "private").mkdir()
    (tmp_citadel.raw / "private" / "pay.txt").write_text("salary 1234\n", encoding="utf-8")
    (tmp_citadel.raw / "notes.md").write_text("notes\n", encoding="utf-8")
    (tmp_citadel.raw / "notes.secret").write_text("x\n", encoding="utf-8")
    readdeny.install(readdeny.entries_from_walk(ingest._discover_walk(None)))


def test_settings_file_shape_is_pinned(tmp_citadel, monkeypatch):
    _private_layout(tmp_citadel, monkeypatch)
    rules, unenforced = readdeny.session_rules("raw/notes.md")
    assert unenforced == 0
    assert rules == [
        readdeny.rule_for(tmp_citadel.raw / "private", True),
        readdeny.rule_for(tmp_citadel.raw / "notes.secret", False),
    ]
    assert all(r.startswith("Read(//") and r.endswith(")") for r in rules)
    assert rules[0].endswith("/private/**)")
    path = readdeny.write_settings(rules)
    try:
        assert json.loads(Path(path).read_text(encoding="utf-8")) == {"permissions": {"deny": rules}}
    finally:
        Path(path).unlink()


def test_windows_drive_path_renders_with_double_slash(monkeypatch):
    monkeypatch.setattr(config, "native_form", lambda p: Path("T:/team/raw/private"))
    assert readdeny.rule_for("T:/team/raw/private", True) == "Read(//t/team/raw/private/**)"


def test_deny_list_never_covers_the_session_source_wiki_caches_rules_or_docs(tmp_citadel, monkeypatch):
    readdeny.install(
        [
            (tmp_citadel.raw / "notes.md", False),
            (config.wiki_dir(), True),
            (config.WIKI_DIR.parent / ".citadel_pdftext", True),
            (config.PACKAGED_RULES_DIR, True),
            (config.DOCS_DIR, True),
            (Path("/tmp/prep"), True),
        ]
    )
    rules, _ = readdeny.session_rules("raw/notes.md", read_path="/tmp/prep/extract.md")
    assert rules == []


def test_an_explicit_source_under_an_ignored_folder_stays_readable(tmp_citadel, monkeypatch):
    _private_layout(tmp_citadel, monkeypatch)
    (tmp_citadel.raw / "private" / "other.txt").write_text("y\n", encoding="utf-8")
    rules, _ = readdeny.session_rules("raw/private/pay.txt")
    assert readdeny.rule_for(tmp_citadel.raw / "private", True) not in rules
    assert readdeny.rule_for(tmp_citadel.raw / "private" / "other.txt", False) in rules
    assert not any("pay.txt" in r for r in rules)


def test_cap_reports_the_unenforced_count(tmp_citadel, monkeypatch):
    monkeypatch.setattr(readdeny, "DENY_CAP", 2)
    readdeny.install([(tmp_citadel.raw / f"f{i}.secret", False) for i in range(5)])
    rules, unenforced = readdeny.session_rules("raw/notes.md")
    assert len(rules) == 2 and unenforced == 3


def test_expansion_budget_exhaustion_is_reported_never_silent(tmp_citadel, monkeypatch):
    _private_layout(tmp_citadel, monkeypatch)
    for i in range(4):
        (tmp_citadel.raw / "private" / f"other{i}.txt").write_text("y\n", encoding="utf-8")
    monkeypatch.setattr(readdeny, "_EXPAND_CAP", 2)
    rules, unenforced = readdeny.session_rules("raw/private/pay.txt")
    assert not any("pay.txt" in r for r in rules)
    assert unenforced >= 1  # the siblings past the budget are undenied — and said so


def test_expansion_iterator_is_bounded_by_the_budget(tmp_citadel, monkeypatch):
    _private_layout(tmp_citadel, monkeypatch)
    consumed = []
    real_scandir = readdeny.os.scandir

    class _Counting:
        def __init__(self, path):
            self._ctx = real_scandir(path)

        def __enter__(self):
            it = self._ctx.__enter__()

            def gen():
                for entry in it:
                    consumed.append(entry.name)
                    yield entry

            return gen()

        def __exit__(self, *exc):
            return self._ctx.__exit__(*exc)

    for i in range(50):
        (tmp_citadel.raw / "private" / f"other{i:02}.txt").write_text("y\n", encoding="utf-8")
    monkeypatch.setattr(readdeny.os, "scandir", _Counting)
    monkeypatch.setattr(readdeny, "_EXPAND_CAP", 5)
    _rules, unenforced = readdeny.session_rules("raw/private/pay.txt")
    assert len(consumed) <= 6 and unenforced >= 1


def test_expansion_listing_error_is_reported_never_silent(tmp_citadel, monkeypatch):
    _private_layout(tmp_citadel, monkeypatch)
    (tmp_citadel.raw / "private" / "other.txt").write_text("y\n", encoding="utf-8")

    def boom(path):
        raise PermissionError(13, "denied", str(path))

    monkeypatch.setattr(readdeny.os, "scandir", boom)
    rules, unenforced = readdeny.session_rules("raw/private/pay.txt")
    assert readdeny.rule_for(tmp_citadel.raw / "private", True) not in rules
    assert unenforced >= 1


def test_an_admitted_repo_blocks_collapsing_its_folder(tmp_citadel):
    from types import SimpleNamespace

    group = tmp_citadel.raw / "group"
    walk = SimpleNamespace(
        files=[], repos=[group / "project"], ignored=[], not_included=[group / "sidecar.txt"], oversized=[]
    )
    assert readdeny.entries_from_walk(walk) == [(group / "sidecar.txt", False)]


def _session_harness(monkeypatch, run):
    monkeypatch.setattr(llm, "resolve_cli_name", lambda cli: "claude")
    monkeypatch.setattr(llm, "_resolve_cli", lambda cli: "/bin/claude")
    _probe(monkeypatch, "--settings --permission-prompts --bare")
    monkeypatch.setattr(config, "HERMETIC", True, raising=False)
    monkeypatch.setattr(llm, "_build_instruction", lambda *a, **k: "prompt")
    monkeypatch.setattr(llm, "_run_session", run)


def test_settings_file_rides_the_hermetic_retry_and_is_removed_after_a_raise(tmp_citadel, monkeypatch):
    _private_layout(tmp_citadel, monkeypatch)
    argvs: list[list[str]] = []

    def run(cli, argv, stdin, *, log_label=None):
        argvs.append(list(argv))
        assert Path(argv[argv.index("--settings") + 1]).is_file()
        if len(argvs) == 1:
            exc = RuntimeError("auth failed")
            exc.hermetic_auth_failure = True
            raise exc
        raise RuntimeError("second failure")

    _session_harness(monkeypatch, run)
    with pytest.raises(RuntimeError, match="second failure"):
        llm.run_ingest_session("raw/notes.md")
    assert "--bare" in argvs[0] and "--bare" not in argvs[1]
    assert "--settings" in argvs[1]  # the retry keeps the enforcement
    assert not Path(argvs[0][argvs[0].index("--settings") + 1]).exists()


def test_no_settings_when_the_probe_lacks_it(tmp_citadel, monkeypatch):
    _private_layout(tmp_citadel, monkeypatch)
    seen: list = []
    _session_harness(monkeypatch, lambda cli, argv, stdin, *, log_label=None: seen.append(argv))
    _probe(monkeypatch, "")
    llm.run_ingest_session("raw/notes.md")
    assert "--settings" not in seen[0]


# --- (d) the post-hoc citation guard --------------------------------------------------------


def _cite(seed_page, rel_path: str, key: str) -> None:
    seed_page(
        rel_path,
        {"type": "Concept", "title": "T", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        f"A fact.[^s1]\n\n## Sources\n\n[^s1]: [{key}](../../{key}) - s\n",
    )


@pytest.mark.parametrize(
    ("setup", "key"),
    [
        (lambda c, m: m.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "*.secret"]), "raw/x.secret"),
        (lambda c, m: m.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "private"]), "raw/private/x.md"),
        (lambda c, m: None, "raw/.hidden/x.md"),
        (lambda c, m: m.setattr(config, "INCLUDE_PATTERNS", ["*.pdf"]), "raw/x.md"),
        (lambda c, m: m.setattr(config, "MAX_SOURCE_BYTES", 3), "raw/x.md"),
    ],
)
def test_citation_to_an_untracked_excluded_file_is_a_check_error(tmp_citadel, seed_page, monkeypatch, setup, key):
    target = tmp_citadel.root / key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("excluded content\n", encoding="utf-8")
    (tmp_citadel.raw / "notes.md").write_text("n\n", encoding="utf-8")
    setup(tmp_citadel, monkeypatch)
    _cite(seed_page, "concepts/t.md", key)
    page = store.read_page("concepts/t.md")
    issues = validate.source_issues("concepts/t.md", page.body)
    assert any("excluded from the corpus" in i for i in issues)

    # A TRACKED key is exempt (ingested before the exclusion, or named explicitly).
    tracked = manifest.load()
    tracked[key] = manifest.make_entry("aa" * 32, "claude:x", "r")
    manifest.save(tracked)
    assert validate.source_issues("concepts/t.md", page.body) == []


def test_the_running_session_source_is_exempt(tmp_citadel, seed_page, monkeypatch):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "*.secret"])
    (tmp_citadel.raw / "x.secret").write_text("s\n", encoding="utf-8")
    _cite(seed_page, "concepts/t.md", "raw/x.secret")
    body = store.read_page("concepts/t.md").body
    with config.session_source("raw/x.secret"):
        assert validate.source_issues("concepts/t.md", body) == []
        assert config.child_env()["CITADEL_SESSION_SOURCE"] == "raw/x.secret"
    assert validate.source_issues("concepts/t.md", body)


def test_excluded_citation_fails_lint_and_plans_curate(tmp_citadel, seed_page, monkeypatch):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "private"])
    (tmp_citadel.raw / "private").mkdir()
    (tmp_citadel.raw / "private" / "pay.txt").write_text("s\n", encoding="utf-8")
    (tmp_citadel.raw / "notes.md").write_text("n\n", encoding="utf-8")
    _cite(seed_page, "concepts/t.md", "raw/private/pay.txt")
    report = lint.lint()
    assert not report.ok() and report.bad_sources
    plan = curate.build_plan()
    assert curate.REASON_BAD_SOURCE in {r for item in plan.items if item.page == "concepts/t.md" for r in item.reasons}


def test_a_session_that_cites_an_excluded_file_fails_and_leaves_the_wiki(
    tmp_citadel, fake_agent, cite_page, monkeypatch
):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "private"])
    (tmp_citadel.raw / "private").mkdir()
    (tmp_citadel.raw / "private" / "pay.txt").write_text("salary\n", encoding="utf-8")
    (tmp_citadel.raw / "notes.md").write_text("notes\n", encoding="utf-8")
    fake_agent(side_effect=lambda rel_key, **kw: cite_page("misc/leak.md", "raw/private/pay.txt", "Salary."))
    report = ingest.ingest()
    assert report.errors and any("excluded from the corpus" in e for e in report.errors)
    assert not (config.wiki_dir() / "misc" / "leak.md").exists()


def test_a_session_cannot_whitelist_its_excluded_citation_through_the_manifest(
    tmp_citadel, fake_agent, cite_page, monkeypatch
):
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "private"])
    (tmp_citadel.raw / "private").mkdir()
    (tmp_citadel.raw / "private" / "pay.txt").write_text("salary\n", encoding="utf-8")
    (tmp_citadel.raw / "notes.md").write_text("notes\n", encoding="utf-8")
    live_manifest = config.manifest_path()

    def leak(rel_key, **kw):
        cite_page("misc/leak.md", "raw/private/pay.txt", "Salary.")
        # The agent "tracks" the excluded file in the manifest it can write: staging's copy, and
        # even the live one — neither may vouch for the citation.
        for path in {config.manifest_path(), live_manifest}:
            data = {"meta": {}, "sources": {"raw/private/pay.txt": manifest.make_entry("aa" * 32, "x", "r")}}
            path.write_text(json.dumps(data), encoding="utf-8")

    fake_agent(side_effect=leak)
    report = ingest.ingest()
    assert any("excluded from the corpus" in e for e in report.errors)
    assert not (config.WIKI_DIR / "misc" / "leak.md").exists()


def test_tracked_keys_lookup_never_displaces_the_manifest_meta_stash(tmp_citadel, monkeypatch, tmp_path):
    manifest.save({})
    data = json.loads(config.manifest_path().read_text(encoding="utf-8"))
    data["meta"] = {"format": 2, "workspace": "/elsewhere/ws", "workspaces": ["/elsewhere/ws"]}
    config.manifest_path().write_text(json.dumps(data), encoding="utf-8")
    manifest.load(warn=False)
    other = tmp_path / "staging"
    other.mkdir()
    (other / ".citadel_ingested.json").write_text(json.dumps({"meta": {}, "sources": {"raw/a.md": {}}}), "utf-8")
    with config.wiki_redirect(other):
        assert "raw/a.md" in validate._tracked_keys()
    assert manifest.stamped_workspace_mismatch() == "/elsewhere/ws"


def test_tracked_keys_cache_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(validate, "_TRACKED_CACHE", type(validate._TRACKED_CACHE)())
    for i in range(validate._TRACKED_CACHE_MAX * 3):
        path = tmp_path / f"m{i}.json"
        path.write_text(json.dumps({"sources": {f"raw/{i}.md": {}}}), encoding="utf-8")
        assert validate.manifest_keys(path) == frozenset({f"raw/{i}.md"})
    assert len(validate._TRACKED_CACHE) == validate._TRACKED_CACHE_MAX
    # Per-manifest invalidation still holds: a rewrite (new size) re-parses.
    path = tmp_path / "m0.json"
    path.write_text(json.dumps({"sources": {"raw/0.md": {}, "raw/new.md": {}}}), encoding="utf-8")
    assert validate.manifest_keys(path) == frozenset({"raw/0.md", "raw/new.md"})


def test_untrackable_key_under_a_newly_ignored_folder(tmp_citadel, monkeypatch):
    (tmp_citadel.raw / "private").mkdir()
    (tmp_citadel.raw / "private" / "pay.txt").write_text("s\n", encoding="utf-8")
    assert not ingest._is_untrackable_key("raw/private/pay.txt")
    monkeypatch.setattr(config, "IGNORE_PATTERNS", [*config.IGNORE_PATTERNS, "private"])
    assert ingest._is_untrackable_key("raw/private/pay.txt")


# --- denials -------------------------------------------------------------------------------


def test_permission_denials_are_parsed_and_warned_never_failed():
    usage = llm._usage_from_claude_envelope(
        {
            "total_cost_usd": 0.1,
            "permission_denials": [{"tool_name": "Read", "tool_input": {"file_path": "/w/raw/private/pay.txt"}}],
        }
    )
    assert usage.denials == ("Read: /w/raw/private/pay.txt",)
    report = ingest.IngestReport([], [], [], [])
    outcome = ingest._SourceOutcome(True, usage=usage)
    ingest._record_spend(outcome, report, "raw/notes.md")
    assert report.denials == ["raw/notes.md: Read: /w/raw/private/pay.txt"]
    assert "permissions denied" in report.render()
    assert not report.errors


# --- doctor ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cli", "help_text", "status"),
    [
        ("claude", "--settings --permission-prompts", doctor.OK),
        ("claude", "--settings", doctor.WARN),
        ("copilot", "", doctor.WARN),
        ("agy", "", doctor.WARN),
    ],
)
def test_doctor_states_enforcement_per_backend(monkeypatch, cli, help_text, status):
    monkeypatch.setattr(config, "LLM_CLI", cli)
    monkeypatch.setattr(config, "INCLUDE_PATTERNS", ["*.pdf"])
    monkeypatch.setattr(llm, "_resolve_cli", lambda c: f"/bin/{c}")
    _probe(monkeypatch, help_text)
    assert doctor.check_exclusion_enforcement().status == status


def test_doctor_ok_without_exclusions(monkeypatch):
    monkeypatch.setattr(config, "INCLUDE_PATTERNS", [])
    monkeypatch.setattr(config, "MAX_SOURCE_BYTES", 0)
    assert doctor.check_exclusion_enforcement().status == doctor.OK


@pytest.fixture(autouse=True)
def _clear_denies():
    readdeny.clear()
    yield
    readdeny.clear()
