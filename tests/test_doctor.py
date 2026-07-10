"""Unit tests for citadel.doctor — every check's OK/WARN/FAIL path, offline.

Each check is a pure function over ``config.*`` + the manifest/failures files + ``llm._resolve_cli``,
so tests drive them through ``tmp_citadel`` + ``monkeypatch`` (no CLI, no network). The CLI wiring
(``citadel doctor`` dispatch, exit code, and workspace-optional guard) is covered at the bottom via
``cli.main``.
"""

from __future__ import annotations

import json
import socket

import pytest

from citadel import cli, config, doctor, manifest
from citadel import llm as llm_mod


@pytest.fixture(autouse=True)
def _block_real_network(monkeypatch):
    """Hard-block PyPI for EVERY doctor test: a forgotten stub must fail closed (return None), never
    hit the network. Tests that exercise the fetch install their own fake urlopen, overriding this."""

    def _no_network(*args, **kwargs):
        raise OSError("network is disabled in tests")

    monkeypatch.setattr(doctor.urllib.request, "urlopen", _no_network)


class _FakeResp:
    """A minimal stand-in for an ``http.client.HTTPResponse`` context manager: ``read()`` returns a
    fixed body so ``_fetch_latest_pypi_version`` can be tested without a socket."""

    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResp":
        return self

    def __exit__(self, *exc) -> bool:
        return False


# --- workspace ---------------------------------------------------------------------------


def test_workspace_ok_reports_root_and_mechanism(tmp_citadel):
    # The autouse conftest fixture pins WORKSPACE_FOUND=True.
    c = doctor.check_workspace()
    assert c.status == doctor.OK
    assert str(tmp_citadel.root) in c.detail


def test_workspace_fail_when_none_resolved(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    c = doctor.check_workspace()
    assert c.status == doctor.FAIL
    assert "no workspace found" in c.detail


def test_workspace_mechanism_names_the_env_override(tmp_citadel, monkeypatch):
    monkeypatch.setenv("CITADEL_WORKSPACE", str(tmp_citadel.root))
    assert "CITADEL_WORKSPACE" in doctor.check_workspace().detail


# --- rules -------------------------------------------------------------------------------


def test_rules_ok_counts_the_effective_tree(tmp_citadel):
    c = doctor.check_rules()
    assert c.status == doctor.OK
    assert "effective rules file" in c.detail
    assert "no workspace overrides" in c.detail


def test_rules_ok_counts_workspace_overrides(tmp_citadel):
    # A workspace rules/core.md shadows the packaged core.md -> counted as one override.
    override = config.workspace_rules_dir() / "core.md"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text("# my core\n", encoding="utf-8")
    c = doctor.check_rules()
    assert c.status == doctor.OK
    assert "1 workspace override" in c.detail


def test_rules_fail_when_packaged_tree_is_missing(tmp_citadel, monkeypatch, tmp_path):
    empty = tmp_path / "empty-rules"
    empty.mkdir()
    monkeypatch.setattr(config, "PACKAGED_RULES_DIR", empty)
    c = doctor.check_rules()
    assert c.status == doctor.FAIL
    assert "packaged rules tree is missing" in c.detail


# --- config ---------------------------------------------------------------------------------


def test_config_ok_when_all_settings_parsed(monkeypatch):
    monkeypatch.setattr(config, "CONFIG_WARNINGS", [])
    c = doctor.check_config()
    assert (c.status, c.name) == (doctor.OK, "config")
    assert "parsed" in c.detail


def test_config_warns_on_recorded_parse_fallback(monkeypatch):
    monkeypatch.setattr(
        config, "CONFIG_WARNINGS", ["CITADEL_MAX_SOURCE_CHARS='300k' is not an integer - using the default 300000"]
    )
    c = doctor.check_config()
    assert c.status == doctor.WARN
    assert "300k" in c.detail


# --- agent CLI ---------------------------------------------------------------------------


def test_agent_cli_ok_reports_resolved_path(tmp_citadel, monkeypatch):
    monkeypatch.setattr(llm_mod, "_resolve_cli", lambda cli: "/opt/bin/claude")
    c = doctor.check_agent_cli()
    assert c.status == doctor.OK
    assert "/opt/bin/claude" in c.detail


def test_agent_cli_warn_when_binary_missing(tmp_citadel, monkeypatch):
    def _boom(cli):
        raise RuntimeError("not found")

    monkeypatch.setattr(llm_mod, "_resolve_cli", _boom)
    monkeypatch.setattr(config, "LLM_CLI", "gemini")
    c = doctor.check_agent_cli()
    assert c.status == doctor.WARN
    assert "gemini" in c.detail
    assert "ingest will fail" in c.detail


# --- raw roots ---------------------------------------------------------------------------


def test_raw_roots_ok_when_reachable(tmp_citadel):
    # make_citadel created the raw dir on disk.
    c = doctor.check_raw_roots()
    assert c.status == doctor.OK
    assert "reachable" in c.detail


def test_raw_roots_warn_when_a_root_is_unreachable(tmp_citadel, monkeypatch, tmp_path):
    missing = tmp_path / "nope" / "raw"
    monkeypatch.setattr(config, "RAW_DIR", missing)
    monkeypatch.setattr(config, "RAW_DIRS", [missing])
    c = doctor.check_raw_roots()
    assert c.status == doctor.WARN
    assert "unreachable" in c.detail


def test_raw_roots_warn_when_none_configured(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "source_roots", lambda: [])
    c = doctor.check_raw_roots()
    assert c.status == doctor.WARN
    assert "no raw roots configured" in c.detail


# --- manifest ----------------------------------------------------------------------------


def test_manifest_ok_when_absent(tmp_citadel):
    c = doctor.check_manifest()
    assert c.status == doctor.OK
    assert "no manifest yet" in c.detail


def test_manifest_ok_when_empty_file(tmp_citadel):
    tmp_citadel.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_citadel.manifest_path.write_text("   \n", encoding="utf-8")
    c = doctor.check_manifest()
    assert c.status == doctor.OK
    assert "empty manifest" in c.detail


def test_manifest_ok_reports_count_and_matching_stamp(tmp_citadel):
    from citadel import manifest

    manifest.save({"raw/a.md": manifest.make_entry("aa" * 32), "raw/b.md": manifest.make_entry("bb" * 32)})
    c = doctor.check_manifest()
    assert c.status == doctor.OK
    assert "2 source(s)" in c.detail
    assert "workspace stamp matches" in c.detail


def test_manifest_warn_on_stamp_mismatch(tmp_citadel):
    tmp_citadel.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_citadel.manifest_path.write_text(
        json.dumps({"meta": {"format": 2, "workspace": "/some/other/root"}, "sources": {"raw/a.md": {"sha256": "aa"}}}),
        encoding="utf-8",
    )
    c = doctor.check_manifest()
    assert c.status == doctor.WARN
    assert "/some/other/root" in c.detail


def test_manifest_warn_on_corrupt_json(tmp_citadel):
    tmp_citadel.manifest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_citadel.manifest_path.write_text("{not json", encoding="utf-8")
    c = doctor.check_manifest()
    assert c.status == doctor.WARN
    assert "not valid JSON" in c.detail


# --- failures ----------------------------------------------------------------------------


def test_failures_ok_when_empty(tmp_citadel):
    c = doctor.check_failures()
    assert c.status == doctor.OK
    assert "no sources recorded as failed" in c.detail


def test_failures_warn_summarizes_by_reason(tmp_citadel):
    from citadel import failures

    cat: dict = {}
    failures.record(cat, "raw/a.tiff", failures.UNREADABLE, "binary")
    failures.record(cat, "raw/b.log", failures.ERROR, "session failed")
    failures.record(cat, "raw/c.log", failures.ERROR, "session failed")
    failures.save(cat)
    c = doctor.check_failures()
    assert c.status == doctor.WARN
    assert "3 source(s)" in c.detail
    assert "2 error" in c.detail and "1 unreadable" in c.detail


# --- billing shadow ----------------------------------------------------------------------


def test_billing_ok_without_api_key(tmp_citadel, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(config, "LLM_CLI", "claude")
    assert doctor.check_billing_shadow().status == doctor.OK


def test_billing_warn_when_key_shadows_claude_subscription(tmp_citadel, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.setattr(config, "LLM_CLI", "claude")
    c = doctor.check_billing_shadow()
    assert c.status == doctor.WARN
    assert "ANTHROPIC_API_KEY" in c.detail
    assert "License & third-party tools" in c.detail


def test_billing_ok_when_base_url_redirects_the_key(tmp_citadel, monkeypatch):
    # A local-model redirect (e.g. Ollama) means the key is never billed by Anthropic -> OK, not WARN.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ollama")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(config, "LLM_CLI", "claude")
    c = doctor.check_billing_shadow()
    assert c.status == doctor.OK
    assert "http://localhost:11434" in c.detail
    assert "the key is not sent to Anthropic's API" in c.detail


def test_billing_ok_when_key_but_backend_is_not_claude(tmp_citadel, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(config, "LLM_CLI", "copilot")
    assert doctor.check_billing_shadow().status == doctor.OK


# --- PDF mode ----------------------------------------------------------------------------


def test_pdf_ok_in_text_mode(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "PDF_MODE", "text")
    monkeypatch.setattr(config, "LLM_CLI", "copilot")
    assert doctor.check_pdf_mode().status == doctor.OK


def test_pdf_warn_images_on_non_vision_backend(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "PDF_MODE", "images")
    monkeypatch.setattr(config, "LLM_CLI", "gemini")
    c = doctor.check_pdf_mode()
    assert c.status == doctor.WARN
    assert "text only" in c.detail


def test_pdf_ok_images_on_claude(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "PDF_MODE", "images")
    monkeypatch.setattr(config, "LLM_CLI", "claude")
    assert doctor.check_pdf_mode().status == doctor.OK


# --- update check: version compare -------------------------------------------------------


def test_version_is_newer_detects_bumps():
    assert doctor.version_is_newer("0.4.0", "0.3.0")
    assert doctor.version_is_newer("0.3.1", "0.3.0")
    assert doctor.version_is_newer("1.0.0", "0.9.9")


def test_version_is_newer_false_when_equal_or_older():
    assert not doctor.version_is_newer("0.3.0", "0.3.0")
    assert not doctor.version_is_newer("0.3.0", "0.4.0")  # local dev build ahead of PyPI
    assert not doctor.version_is_newer("0.9.9", "1.0.0")


def test_version_is_newer_pads_a_shorter_version():
    assert doctor.version_is_newer("0.3.1", "0.3")  # 0.3 == 0.3.0 < 0.3.1
    assert not doctor.version_is_newer("0.3", "0.3.0")


def test_version_is_newer_is_conservative_on_non_numeric_segments():
    # A pre-release-ish segment it cannot rank -> never claims "newer" in either direction.
    assert not doctor.version_is_newer("0.3.0rc1", "0.3.0")
    assert not doctor.version_is_newer("0.3.0", "0.3.0rc1")
    # But a plain numeric bump before any weird segment still wins.
    assert doctor.version_is_newer("0.4.0rc1", "0.3.0")


# --- update check: install-method detection ----------------------------------------------


def _make_module(tmp_path, *, dev: bool, marker: str = ".git") -> str:
    """Lay out a synthetic ``<root>/citadel/doctor.py`` and return its path. ``dev=True`` also drops a
    ``pyproject.toml`` + a repo marker one level up so the dev-checkout branch fires."""
    root = tmp_path / ("repo" if dev else "site-packages")
    (root / "citadel").mkdir(parents=True)
    mod = root / "citadel" / "doctor.py"
    mod.write_text("", encoding="utf-8")
    if dev:
        (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (root / marker).mkdir()
    return str(mod)


def test_detect_update_command_dev_checkout_via_git(tmp_path):
    mod = _make_module(tmp_path, dev=True, marker=".git")
    assert doctor.detect_update_command(module_file=mod, prefix="/irrelevant") == "git pull && uv sync"


def test_detect_update_command_dev_checkout_via_corpora(tmp_path):
    mod = _make_module(tmp_path, dev=True, marker="corpora")
    assert doctor.detect_update_command(module_file=mod, prefix="/irrelevant") == "git pull && uv sync"


def test_detect_update_command_uv_tool(tmp_path):
    mod = _make_module(tmp_path, dev=False)
    prefix = "/home/u/.local/share/uv/tools/cite-citadel"
    assert doctor.detect_update_command(module_file=mod, prefix=prefix) == "uv tool upgrade cite-citadel"


def test_detect_update_command_pipx(tmp_path):
    mod = _make_module(tmp_path, dev=False)
    prefix = "/home/u/.local/pipx/venvs/cite-citadel"
    assert doctor.detect_update_command(module_file=mod, prefix=prefix) == "pipx upgrade cite-citadel"


def test_detect_update_command_uvx_ephemeral(tmp_path):
    mod = _make_module(tmp_path, dev=False)
    prefix = "/home/u/.cache/uv/environments-v2/cite-citadel-abc123"
    cmd = doctor.detect_update_command(module_file=mod, prefix=prefix)
    assert cmd.startswith("uvx cite-citadel")
    assert "latest" in cmd


def test_detect_update_command_generic_venv(tmp_path):
    mod = _make_module(tmp_path, dev=False)
    prefix = "/home/u/.venvs/myproject"
    assert doctor.detect_update_command(module_file=mod, prefix=prefix) == "pip install -U cite-citadel"


# --- update check: PyPI fetch (network hard-blocked; fakes only) --------------------------


def test_fetch_latest_parses_pypi_info_version(monkeypatch):
    body = json.dumps({"info": {"version": "1.2.3"}, "releases": {}}).encode("utf-8")
    monkeypatch.setattr(doctor.urllib.request, "urlopen", lambda url, timeout=None: _FakeResp(body))
    assert doctor._fetch_latest_pypi_version() == "1.2.3"


def test_fetch_latest_returns_none_on_oserror(monkeypatch):
    def _boom(url, timeout=None):
        raise OSError("no route to host")

    monkeypatch.setattr(doctor.urllib.request, "urlopen", _boom)
    assert doctor._fetch_latest_pypi_version() is None


def test_fetch_latest_returns_none_on_timeout(monkeypatch):
    def _timeout(url, timeout=None):
        raise socket.timeout("timed out")

    monkeypatch.setattr(doctor.urllib.request, "urlopen", _timeout)
    assert doctor._fetch_latest_pypi_version() is None


def test_fetch_latest_returns_none_on_malformed_json(monkeypatch):
    monkeypatch.setattr(doctor.urllib.request, "urlopen", lambda url, timeout=None: _FakeResp(b"{not json"))
    assert doctor._fetch_latest_pypi_version() is None


def test_fetch_latest_returns_none_when_version_key_missing(monkeypatch):
    body = json.dumps({"info": {}}).encode("utf-8")
    monkeypatch.setattr(doctor.urllib.request, "urlopen", lambda url, timeout=None: _FakeResp(body))
    assert doctor._fetch_latest_pypi_version() is None


# --- update check: check_update() glue ---------------------------------------------------


def test_check_update_warn_when_pypi_is_newer(tmp_citadel, monkeypatch):
    monkeypatch.setattr(doctor, "_fetch_latest_pypi_version", lambda timeout=2.0: "0.4.0")
    c = doctor.check_update(installed="0.3.0")
    assert c.status == doctor.WARN
    assert "0.3.0 installed, 0.4.0 on PyPI" in c.detail
    assert "run:" in c.detail


def test_check_update_ok_when_current(tmp_citadel, monkeypatch):
    monkeypatch.setattr(doctor, "_fetch_latest_pypi_version", lambda timeout=2.0: "0.3.0")
    c = doctor.check_update(installed="0.3.0")
    assert c.status == doctor.OK
    assert "0.3.0 is current" in c.detail


def test_check_update_ok_when_local_is_ahead(tmp_citadel, monkeypatch):
    monkeypatch.setattr(doctor, "_fetch_latest_pypi_version", lambda timeout=2.0: "0.3.0")
    c = doctor.check_update(installed="0.4.0")
    assert c.status == doctor.OK
    assert "0.4.0 is current" in c.detail


def test_check_update_ok_when_pypi_unreachable(tmp_citadel, monkeypatch):
    monkeypatch.setattr(doctor, "_fetch_latest_pypi_version", lambda timeout=2.0: None)
    c = doctor.check_update(installed="0.3.0")
    assert c.status == doctor.OK
    assert "could not reach PyPI" in c.detail


def test_check_update_defaults_to_installed_version(tmp_citadel, monkeypatch):
    monkeypatch.setattr(doctor, "_INSTALLED_VERSION", "9.9.9")
    monkeypatch.setattr(doctor, "_fetch_latest_pypi_version", lambda timeout=2.0: "0.3.0")
    c = doctor.check_update()
    assert c.status == doctor.OK
    assert "9.9.9 is current" in c.detail


# --- workspace coherence -----------------------------------------------------------------


_COHERENT_FM = {"type": "Concept", "title": "Topic", "description": "d", "tags": ["t"], "resource": "raw/x.md"}
_COHERENT_BODY = "A fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/x.md](../../raw/x.md) - notes\n"


def test_coherence_ok_when_citations_resolve_under_the_raw_root(tmp_citadel, seed_page):
    # Normal layout: wiki/ and raw/ share a parent, so ../../raw/x.md lands under the raw root.
    seed_page("concepts/topic.md", _COHERENT_FM, _COHERENT_BODY)
    c = doctor.check_workspace_coherence()
    assert c.status == doctor.OK
    assert c.name == "workspace coherence"
    assert "all 1 source citations resolve under the configured raw/docs roots" in c.detail


def test_coherence_warn_on_hybrid_wiki_and_raw_layout(make_citadel, seed_page, tmp_path):
    # Tonight's incident: the wiki is nested deep while raw/ stays at the workspace root, so a
    # standard ../../raw/x.md citation resolves to <wiki_parent>/raw/x.md — OUTSIDE the configured
    # raw root (tmp/raw). Everything then degrades silently; only doctor should call it out.
    make_citadel(wiki=tmp_path / "sub" / "deep" / "wiki")
    seed_page("concepts/topic.md", _COHERENT_FM, _COHERENT_BODY)
    c = doctor.check_workspace_coherence()
    assert c.status == doctor.WARN
    assert "1/1 source citation" in c.detail
    assert "concepts/topic.md" in c.detail and "OUTSIDE" in c.detail
    # names where it actually resolved (the nested raw tree) and the CITADEL_RAW_DIR / workspace fix.
    assert str(tmp_path / "sub" / "deep" / "raw") in c.detail
    assert "CITADEL_RAW_DIR" in c.detail and "CITADEL_WORKSPACE" in c.detail


def test_coherence_ok_when_no_pages(tmp_citadel):
    c = doctor.check_workspace_coherence()
    assert c.status == doctor.OK
    assert "no pages" in c.detail


def test_coherence_ok_when_only_external_citations(tmp_citadel, seed_page):
    # A page whose only Sources entry is an external URL has no raw/docs citation to check.
    seed_page(
        "concepts/topic.md",
        {"type": "Concept", "title": "Topic", "description": "d", "tags": ["t"], "resource": "https://example.com"},
        "A fact.[^s1]\n\n## Sources\n\n[^s1]: [example](https://example.com) - web\n",
    )
    c = doctor.check_workspace_coherence()
    assert c.status == doctor.OK
    assert "no source citations to check" in c.detail


def test_coherence_ok_skips_without_a_workspace(tmp_citadel, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    c = doctor.check_workspace_coherence()
    assert c.status == doctor.OK
    assert "no workspace" in c.detail


# --- report + CLI wiring -----------------------------------------------------------------


def test_report_ok_is_false_iff_a_check_fails():
    ok = doctor.DoctorReport([doctor.Check(doctor.OK, "a", "x"), doctor.Check(doctor.WARN, "b", "y")])
    bad = doctor.DoctorReport([doctor.Check(doctor.OK, "a", "x"), doctor.Check(doctor.FAIL, "b", "y")])
    assert ok.ok and not bad.ok


def test_render_lists_every_check_and_a_verdict():
    text = doctor.DoctorReport([doctor.Check(doctor.WARN, "raw roots", "unreachable")]).render()
    assert "citadel doctor" in text
    assert "[WARN] raw roots: unreachable" in text
    assert "No blocking problems." in text


def test_run_emits_the_full_check_inventory(tmp_citadel, monkeypatch):
    monkeypatch.setattr(llm_mod, "_resolve_cli", lambda cli: "/opt/bin/claude")
    # Keep run() fully offline: stub the PyPI lookup so the update check never touches the network.
    monkeypatch.setattr(doctor, "_fetch_latest_pypi_version", lambda timeout=2.0: None)
    names = [c.name for c in doctor.run().checks]
    assert names == [
        "workspace",
        "rules",
        "config",
        "agent CLI",
        "raw roots",
        "manifest",
        "failures",
        "billing",
        "PDF mode",
        "wiki git",
        "update",
        "workspace coherence",
    ]


def test_doctor_subcommand_is_registered_workspace_optional():
    args = cli.build_parser().parse_args(["doctor"])
    assert args.func is cli.cmd_doctor
    assert args.needs_workspace is False


def test_doctor_exits_0_when_no_check_fails(tmp_citadel, monkeypatch, capsys):
    monkeypatch.setattr(llm_mod, "_resolve_cli", lambda cli: "/opt/bin/claude")
    assert cli.main(["doctor"]) == 0
    assert "citadel doctor" in capsys.readouterr().out


def test_doctor_exits_1_and_runs_without_a_workspace(tmp_citadel, monkeypatch, capsys):
    # needs_workspace=False: main must NOT short-circuit with exit 2; the workspace check FAILs
    # instead, so doctor still runs and returns 1.
    monkeypatch.setattr(config, "WORKSPACE_FOUND", False)
    assert cli.main(["doctor"]) == 1
    assert "no workspace found" in capsys.readouterr().out


def test_manifest_with_non_utf8_bytes_reports_corrupt_not_crash(tmp_citadel):
    """Copilot review on PR #41: non-UTF-8 bytes in the manifest must yield the 'corrupt'
    sentinel (a WARN in doctor), never a UnicodeDecodeError crash."""
    tmp_citadel.manifest_path.write_bytes(b"\xff\xfe not json")
    fmt, count, err = manifest.inspect()
    assert err == "corrupt"
    assert count == 0
    check = doctor.check_manifest()
    assert check.status != doctor.FAIL or "corrupt" in check.detail  # WARN with the corrupt message
    assert "corrupt" in check.detail or "not valid" in check.detail
