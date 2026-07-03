"""Unit tests for citadel.doctor — every check's OK/WARN/FAIL path, offline.

Each check is a pure function over ``config.*`` + the manifest/failures files + ``llm._resolve_cli``,
so tests drive them through ``tmp_citadel`` + ``monkeypatch`` (no CLI, no network). The CLI wiring
(``citadel doctor`` dispatch, exit code, and workspace-optional guard) is covered at the bottom via
``cli.main``.
"""

from __future__ import annotations

import json

from citadel import cli, config, doctor
from citadel import llm as llm_mod


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
    monkeypatch.setattr(config, "LLM_CLI", "claude")
    c = doctor.check_billing_shadow()
    assert c.status == doctor.WARN
    assert "ANTHROPIC_API_KEY" in c.detail
    assert "License & third-party tools" in c.detail


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
    names = [c.name for c in doctor.run().checks]
    assert names == ["workspace", "rules", "agent CLI", "raw roots", "manifest", "failures", "billing", "PDF mode"]


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
