"""Per-session cost accounting (the 2026-07 audit's backlog #2), fully offline.

The backend CLIs' own cost/usage reports — claude's ``--output-format json`` envelope, gemini's
``--session-summary`` stats file — are parsed per session (:class:`llm.SessionUsage`), combined
per source, stamped into the manifest (carried across moves/cache re-stamps exactly like
``ingested_at``), and surfaced on the ingest/refresh/curate reports and ``citadel status``.
Accounting is strictly passive: no usage path may ever fail a session, so every parse is
defensive and "no data" is None — never a lying ``$0.00``. All faked here (subprocess / the
FakeAgent seam), never a real CLI.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from citadel import config, curate, ingest, llm, manifest, refresh, status


class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _valid_page(resource: str = "raw/notes.md") -> dict:
    """One canonical cited page for the FakeAgent to write — valid for whichever source
    ``resource`` names."""
    return {
        "concepts/topic.md": (
            {"type": "Concept", "title": "Topic", "description": "d", "tags": ["t"], "resource": resource},
            f"A sourced fact.[^s1]\n\n## Sources\n\n[^s1]: [{resource}](../../{resource}) - s\n",
        )
    }


# --- llm layer: SessionUsage / combine_usage / format_cost -----------------------------------


def test_combine_usage_sums_fieldwise_and_skips_unknown():
    """Fields sum over the parts that KNOW them; None parts and non-usage values (the fakes'
    return) are skipped; a field no part knew stays None instead of becoming a fake 0."""
    a = llm.SessionUsage(cost_usd=0.05, input_tokens=100, output_tokens=10)
    b = llm.SessionUsage(cost_usd=0.02)  # tokens unknown (e.g. a parse miss)
    combined = llm.combine_usage([a, None, b, "not-a-usage"])
    assert combined.cost_usd == pytest.approx(0.07)
    assert combined.input_tokens == 100 and combined.output_tokens == 10

    tokens_only = llm.combine_usage([llm.SessionUsage(input_tokens=5), llm.SessionUsage(input_tokens=7)])
    assert tokens_only.cost_usd is None  # no part priced itself -> cost stays honest None
    assert tokens_only.input_tokens == 12


def test_combine_usage_all_unknown_returns_none():
    assert llm.combine_usage([]) is None
    assert llm.combine_usage([None, None]) is None
    assert llm.combine_usage([None, "junk"]) is None


def test_format_cost_never_rounds_to_a_lying_zero():
    assert llm.format_cost(0.0042) == "$0.0042"
    assert llm.format_cost(0.053) == "$0.053"
    assert llm.format_cost(0.05) == "$0.05"
    assert llm.format_cost(1.0) == "$1.00"
    assert llm.format_cost(1234.5) == "$1,234.50"


def test_describe_renders_only_known_fields():
    full = llm.SessionUsage(cost_usd=0.05, input_tokens=1234567, output_tokens=45678)
    assert full.describe() == "$0.05, tokens 1,234,567 in / 45,678 out"
    assert llm.SessionUsage(cost_usd=0.31).describe() == "$0.31"
    # An unknown side is omitted — never rendered as a 0 that reads like a real count.
    assert llm.SessionUsage(output_tokens=9).describe() == "tokens 9 out"
    assert llm.SessionUsage(input_tokens=5).describe() == "tokens 5 in"
    assert llm.SessionUsage().describe() == ""


# --- claude: the result envelope's cost/usage fields ------------------------------------------


def test_usage_from_claude_envelope_reads_cost_and_cached_tokens():
    """total_cost_usd plus the usage counts; input tokens include cache creation/reads — the
    prompt-side volume actually billed, not just the uncached slice."""
    env = {
        "type": "result",
        "is_error": False,
        "total_cost_usd": 0.0553,
        "usage": {
            "input_tokens": 12,
            "cache_creation_input_tokens": 3000,
            "cache_read_input_tokens": 40000,
            "output_tokens": 496,
        },
    }
    usage = llm._usage_from_claude_envelope(env)
    assert usage.cost_usd == pytest.approx(0.0553)
    assert usage.input_tokens == 12 + 3000 + 40000
    assert usage.output_tokens == 496


def test_usage_from_claude_envelope_defensive():
    """An envelope is external input: junk types read as absent, a bool never reads as a number
    (True is an int subclass), and an envelope carrying nothing usable is None."""
    assert llm._usage_from_claude_envelope(None) is None
    assert llm._usage_from_claude_envelope({}) is None
    assert llm._usage_from_claude_envelope({"total_cost_usd": "free", "usage": {"input_tokens": "many"}}) is None
    assert llm._usage_from_claude_envelope({"total_cost_usd": True, "usage": {"output_tokens": False}}) is None
    partial = llm._usage_from_claude_envelope({"usage": {"output_tokens": 7}})
    assert partial == llm.SessionUsage(cost_usd=None, input_tokens=None, output_tokens=7)
    # First NUMERIC value wins: a present-but-junk total_cost_usd must not shadow a valid
    # legacy cost_usd (the pre-GA envelope name).
    legacy = llm._usage_from_claude_envelope({"total_cost_usd": None, "cost_usd": 0.12})
    assert legacy.cost_usd == pytest.approx(0.12)


def test_run_session_claude_returns_usage(monkeypatch):
    envelope = json.dumps(
        {
            "type": "result",
            "is_error": False,
            "result": "done",
            "total_cost_usd": 0.31,
            "usage": {"input_tokens": 1000, "output_tokens": 50},
        }
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, envelope))
    usage = llm._run_session("claude", ["claude", "-p"], "PROMPT")
    assert usage.cost_usd == pytest.approx(0.31)
    assert usage.input_tokens == 1000 and usage.output_tokens == 50


def test_run_session_claude_jsonl_stream_still_yields_usage(monkeypatch):
    """The verbose/streamed path emits JSONL; the last result envelope (the existing error-
    detection fallback) also serves the usage parse."""
    lines = '{"type":"system"}\n{"type":"result","is_error":false,"total_cost_usd":0.02,"usage":{"output_tokens":5}}'
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, lines))
    usage = llm._run_session("claude", ["claude", "-p"], "PROMPT")
    assert usage.cost_usd == pytest.approx(0.02) and usage.output_tokens == 5


def test_run_session_without_usage_returns_none(monkeypatch):
    """A claude envelope with no cost fields — and every copilot session — reports None, so
    'no data' never renders as a $0.00."""
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, '{"type":"result","is_error":false}'))
    assert llm._run_session("claude", ["claude", "-p"], "PROMPT") is None
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, "plain text"))
    assert llm._run_session("copilot", ["copilot", "-p", "x"], None) is None


# --- gemini: --session-summary behind a --help feature probe ---------------------------------


def test_gemini_summary_file_requires_advertised_flag(monkeypatch):
    """The flag is appended only when the binary ADVERTISES it — an older gemini must never be
    handed an unknown flag that would fail the whole session over optional accounting."""
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, "usage: gemini\n  --approval-mode\n"))
    assert llm._gemini_summary_file("gemini", "/bin/gemini") is None

    # An exact flag TOKEN is required: a longer option must not read as this flag (a false
    # positive would hand the CLI an unknown flag and fail the session — the very thing the
    # probe exists to prevent; a false negative merely disables optional accounting).
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, "  --session-summary-file <file>\n"))
    assert llm._gemini_summary_file("gemini", "/bin/gemini") is None

    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {})
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, "  --session-summary <file>\n"))
    path = llm._gemini_summary_file("gemini", "/bin/gemini")
    assert path is not None and path.suffix == ".json"
    path.unlink()


def test_gemini_summary_file_never_probes_other_backends(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("must not probe --help for non-gemini backends")

    monkeypatch.setattr(subprocess, "run", boom)
    assert llm._gemini_summary_file("claude", "/bin/claude") is None
    assert llm._gemini_summary_file("copilot", "/bin/copilot") is None


def test_gemini_probe_failure_degrades_to_no_accounting(monkeypatch):
    """A broken/hanging --help probe reads as 'feature absent' — accounting can never break a
    session — and the failure is cached so the binary is not re-probed every source."""
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {})
    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise OSError("no such binary")

    monkeypatch.setattr(subprocess, "run", boom)
    assert llm._gemini_summary_file("gemini", "/bin/gemini") is None
    assert llm._gemini_summary_file("gemini", "/bin/gemini") is None
    assert calls["n"] == 1


def test_usage_from_gemini_summary_walks_model_token_dicts(tmp_path):
    """The wrapper shape has shifted across gemini versions, so the parse walks for the stable
    inner token dicts (prompt/candidates) and sums across models."""
    stats = {
        "sessionMetrics": {
            "models": {
                "gemini-2.5-pro": {"api": {"totalRequests": 4}, "tokens": {"prompt": 1200, "candidates": 300}},
                "gemini-2.5-flash": {"tokens": {"prompt": 100, "candidates": 20, "total": 120}},
            }
        }
    }
    path = tmp_path / "summary.json"
    path.write_text(json.dumps(stats), encoding="utf-8")
    assert llm._usage_from_gemini_summary(path) == llm.SessionUsage(cost_usd=None, input_tokens=1300, output_tokens=320)


def test_usage_from_gemini_summary_defensive(tmp_path):
    assert llm._usage_from_gemini_summary(tmp_path / "gone.json") is None
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert llm._usage_from_gemini_summary(corrupt) is None
    foreign = tmp_path / "foreign.json"
    foreign.write_text('{"lastUpdated": "2026-07-23"}', encoding="utf-8")
    assert llm._usage_from_gemini_summary(foreign) is None


def test_run_ingest_session_gemini_appends_flag_parses_and_cleans_up(monkeypatch):
    """End-to-end gemini accounting: the probed flag appends ``--session-summary <tempfile>`` to
    the argv, the stats the CLI wrote there come back as the session's usage, and the temp file
    is deleted afterwards."""
    monkeypatch.setattr(config, "LLM_CLI", "gemini", raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda cli: "/bin/gemini")
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {"/bin/gemini": "--session-summary <file>"})
    seen: dict = {}

    def fake_run_session(cli, argv, stdin_text, *, log_label=None):
        assert cli == "gemini"
        summary = Path(argv[argv.index("--session-summary") + 1])
        seen["summary"] = summary
        stats = {"sessionMetrics": {"models": {"g": {"tokens": {"prompt": 10, "candidates": 4}}}}}
        summary.write_text(json.dumps(stats), encoding="utf-8")
        return None  # gemini's stdout reports nothing — the stats file is the source

    monkeypatch.setattr(llm, "_run_session", fake_run_session)
    usage = llm.run_ingest_session("raw/notes.md")
    assert usage == llm.SessionUsage(cost_usd=None, input_tokens=10, output_tokens=4)
    assert not seen["summary"].exists()  # cleaned up, success or not


def test_run_ingest_session_gemini_without_flag_keeps_argv_unchanged(monkeypatch):
    monkeypatch.setattr(config, "LLM_CLI", "gemini", raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda cli: "/bin/gemini")
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {"/bin/gemini": "no such flag here"})

    def fake_run_session(cli, argv, stdin_text, *, log_label=None):
        assert "--session-summary" not in argv
        return None

    monkeypatch.setattr(llm, "_run_session", fake_run_session)
    assert llm.run_ingest_session("raw/notes.md") is None


# --- manifest: the per-source usage stamp -----------------------------------------------------


def test_make_entry_stamps_and_rounds_usage():
    entry = manifest.make_entry("abc", "claude:sonnet", "rv", cost_usd=0.123456, tokens_in=100, tokens_out=9)
    assert entry["cost_usd"] == 0.1235  # 4 decimals: sub-cent precision, no float-noise digits
    assert entry["tokens_in"] == 100 and entry["tokens_out"] == 9

    bare = manifest.make_entry("abc", "claude:sonnet", "rv")
    for key in ("cost_usd", "tokens_in", "tokens_out"):
        assert key not in bare  # unknown is ABSENT, never a fake 0


def test_make_repo_entry_stamps_usage():
    entry = manifest.make_repo_entry("deadbeef", "claude:sonnet", cost_usd=1.5, tokens_in=5, tokens_out=6)
    assert entry["cost_usd"] == 1.5 and entry["tokens_in"] == 5 and entry["tokens_out"] == 6


def test_entry_usage_roundtrips_as_kwargs_and_rejects_junk():
    entry = manifest.make_entry("abc", "m", "rv", cost_usd=0.05, tokens_in=10, tokens_out=2)
    assert manifest.entry_usage(entry) == {"cost_usd": 0.05, "tokens_in": 10, "tokens_out": 2}
    assert manifest.entry_usage("bare-sha-string") == {}
    assert manifest.entry_usage(None) == {}
    junk = {"sha256": "abc", "cost_usd": "expensive", "tokens_in": True, "tokens_out": None}
    assert manifest.entry_usage(junk) == {}


def test_mark_done_stamps_usage(tmp_citadel):
    src = tmp_citadel.raw / "notes.md"
    src.write_text("alpha\n", encoding="utf-8")
    tracked: dict = {}
    manifest.mark_done(tracked, src, "claude:sonnet", "rv", cost_usd=0.02, tokens_in=8, tokens_out=3)
    entry = tracked["raw/notes.md"]
    assert entry["cost_usd"] == 0.02 and entry["tokens_in"] == 8 and entry["tokens_out"] == 3
    assert entry["ingested_at"]  # the fresh last-checked stamp still arrives alongside


# --- ingest: manifest stamp + run-report totals ------------------------------------------------


def test_ingest_stamps_usage_into_manifest_and_report(tmp_citadel, fake_agent):
    (tmp_citadel.raw / "notes.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page(), usage=llm.SessionUsage(cost_usd=0.05, input_tokens=1000, output_tokens=100))

    report = ingest.ingest()

    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    assert entry["cost_usd"] == 0.05
    assert entry["tokens_in"] == 1000 and entry["tokens_out"] == 100
    assert report.usage == llm.SessionUsage(cost_usd=0.05, input_tokens=1000, output_tokens=100)
    assert "LLM usage: $0.05, tokens 1,000 in / 100 out." in report.render()


def test_ingest_run_total_sums_across_sources(tmp_citadel, fake_agent):
    (tmp_citadel.raw / "a.md").write_text("alpha\n", encoding="utf-8")
    (tmp_citadel.raw / "b.md").write_text("beta\n", encoding="utf-8")
    fake_agent(_valid_page("raw/a.md"), usage=llm.SessionUsage(cost_usd=0.03, input_tokens=500, output_tokens=50))

    report = ingest.ingest()

    assert len(report.processed) == 2
    assert report.usage.cost_usd == pytest.approx(0.06)
    assert report.usage.input_tokens == 1000
    entries = tmp_citadel.read_manifest()
    assert entries["raw/a.md"]["cost_usd"] == 0.03  # per-source: that source's OWN session
    assert entries["raw/b.md"]["cost_usd"] == 0.03


def test_ingest_without_usage_stays_silent(tmp_citadel, fake_agent):
    """A backend that reports nothing (copilot, the fakes' default) leaves no stamp, no report
    line, and no misleading zeros — byte-for-byte the pre-accounting surfaces."""
    (tmp_citadel.raw / "notes.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page())

    report = ingest.ingest()

    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    for key in ("cost_usd", "tokens_in", "tokens_out"):
        assert key not in entry
    assert report.usage is None
    assert "LLM usage" not in report.render()


def test_chunked_source_sums_segment_usage_into_one_stamp(tmp_citadel, monkeypatch, fake_agent):
    """A large source folded in over several segment passes stamps ONE combined usage — the whole
    cost of verifying that source, matching promote-once semantics."""
    monkeypatch.setattr(config, "MAX_SOURCE_CHARS", 120)
    (tmp_citadel.raw / "big.md").write_text(("paragraph one\n\n" * 6) + ("paragraph two\n\n" * 6), encoding="utf-8")
    agent = fake_agent(_valid_page("raw/big.md"), usage=llm.SessionUsage(cost_usd=0.01, output_tokens=10))

    report = ingest.ingest()

    assert agent.count >= 2  # actually chunked
    entry = tmp_citadel.read_manifest()["raw/big.md"]
    assert entry["cost_usd"] == pytest.approx(0.01 * agent.count)
    assert entry["tokens_out"] == 10 * agent.count
    assert report.usage.cost_usd == pytest.approx(0.01 * agent.count)


def test_failed_source_counts_in_run_total_but_never_in_manifest(tmp_citadel, fake_agent):
    """A rolled-back source spent its session too: the run total counts it, while the manifest —
    the per-source 'last successful verification' stamp — records nothing."""
    (tmp_citadel.raw / "notes.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(pages={"concepts/bad.md": "garbage with no frontmatter"}, usage=llm.SessionUsage(cost_usd=0.04))

    report = ingest.ingest()

    assert report.errors
    assert "raw/notes.md" not in tmp_citadel.read_manifest()
    assert report.usage == llm.SessionUsage(cost_usd=0.04)


def test_move_carries_usage_stamp(tmp_citadel, fake_agent):
    """A recognized move re-keys the entry without a session — the usage stamp is CARRIED, like
    ingested_at, never re-minted or dropped."""
    src = tmp_citadel.raw / "notes.md"
    src.write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page(), usage=llm.SessionUsage(cost_usd=0.05, input_tokens=10, output_tokens=2))
    ingest.ingest()

    agent = fake_agent(pages={})  # a move must not re-run a session
    src.rename(tmp_citadel.raw / "renamed.md")
    ingest.ingest()

    entries = tmp_citadel.read_manifest()
    assert "raw/notes.md" not in entries
    entry = entries["raw/renamed.md"]
    assert entry["cost_usd"] == 0.05 and entry["tokens_in"] == 10 and entry["tokens_out"] == 2
    assert agent.count == 0


def test_cache_restamp_carries_usage(tmp_citadel, fake_agent):
    """A touched-but-identical file refreshes its scan-cache entry in place; no session ran, so
    the usage stamp must survive the re-stamp unchanged."""
    src = tmp_citadel.raw / "notes.md"
    src.write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page(), usage=llm.SessionUsage(cost_usd=0.05))
    ingest.ingest()

    st = src.stat()
    os.utime(src, ns=(st.st_atime_ns, st.st_mtime_ns + 5_000_000_000))  # new mtime, same bytes
    agent = fake_agent(pages={})
    report = ingest.ingest()

    assert agent.count == 0
    assert "raw/notes.md" in report.skipped
    assert tmp_citadel.read_manifest()["raw/notes.md"]["cost_usd"] == 0.05


# --- status: the per-source column + the corpus total -----------------------------------------


def test_status_renders_cost_column_and_total(tmp_citadel, fake_agent):
    (tmp_citadel.raw / "a.md").write_text("alpha\n", encoding="utf-8")
    (tmp_citadel.raw / "b.md").write_text("beta\n", encoding="utf-8")
    fake_agent(_valid_page("raw/a.md"), usage=llm.SessionUsage(cost_usd=0.03, input_tokens=500, output_tokens=50))
    ingest.ingest()

    report = status.build_status()
    text = report.render()
    assert "Recorded LLM cost: $0.06 over 2 source(s) (last session each)" in text
    assert "$0.03" in text  # the per-source column

    data = report.as_dict()
    assert data["cost_usd_total"] == pytest.approx(0.06)
    rows = {row["key"]: row for row in data["ingested"]}
    assert rows["raw/a.md"]["cost_usd"] == 0.03
    assert rows["raw/a.md"]["tokens_in"] == 500 and rows["raw/a.md"]["tokens_out"] == 50


def test_status_without_cost_stamps_shows_no_cost_line(tmp_citadel, fake_agent):
    (tmp_citadel.raw / "notes.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page())
    ingest.ingest()

    report = status.build_status()
    assert "Recorded LLM cost" not in report.render()
    assert report.as_dict()["cost_usd_total"] is None
    assert "cost_usd" not in {k for row in report.as_dict()["ingested"] for k in row}


# --- curate + refresh: the other lifecycles' reports -------------------------------------------


def test_curate_report_totals_session_usage(tmp_citadel, seed_page, fake_agent):
    """Curate rides the same session runner: a cluster's session usage lands on the curate
    report (a NOOP still spent its session; there is no manifest stamp — clusters are pages)."""
    (tmp_citadel.raw / "notes.md").write_text("body\n", encoding="utf-8")
    seed_page(
        "concepts/alice.md",  # a Person mis-filed under concepts/ -> deterministic resort cluster
        {"type": "Person", "title": "Alice", "description": "d", "tags": ["t"], "resource": "raw/notes.md"},
        "Fact.[^s1]\n\n## Sources\n\n[^s1]: [raw/notes.md](../../raw/notes.md) - s\n",
    )
    fake_agent(pages={}, usage=llm.SessionUsage(cost_usd=0.02, input_tokens=100, output_tokens=10))

    report = curate.curate()

    assert report.noop  # the arbitration itself is unchanged
    assert report.usage == llm.SessionUsage(cost_usd=0.02, input_tokens=100, output_tokens=10)
    assert "LLM usage: $0.02, tokens 100 in / 10 out." in report.render()


def test_refresh_restamps_cost_and_reports_it(tmp_citadel, fake_agent):
    """refresh delegates to a forced ingest: the reconcile session's usage re-stamps the source's
    entry (the new 'what does a re-verification cost' answer) and rides the wrapped report."""
    (tmp_citadel.raw / "notes.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page(), usage=llm.SessionUsage(cost_usd=0.01))
    ingest.ingest()

    fake_agent(_valid_page(), usage=llm.SessionUsage(cost_usd=0.04))
    report = refresh.refresh(limit=1)

    assert report.ingest_report.usage == llm.SessionUsage(cost_usd=0.04)
    assert "LLM usage: $0.04." in report.render()
    assert tmp_citadel.read_manifest()["raw/notes.md"]["cost_usd"] == 0.04


# --- hardening round (adversarial review + Copilot findings) -----------------------------------


def test_format_cost_never_raises_on_non_finite():
    """A hand-edited manifest is external input: a NaN/Infinity cost must render, not crash."""
    assert llm.format_cost(float("nan")) == "$nan"
    assert llm.format_cost(float("inf")) == "$inf"


def test_usage_from_claude_envelope_rejects_non_finite_and_overflowing_cost():
    """json.loads accepts Infinity/NaN and arbitrary-precision ints — none of them may survive
    into a SessionUsage (or crash the parse via float() OverflowError)."""
    assert llm._usage_from_claude_envelope({"total_cost_usd": float("inf")}) is None
    assert llm._usage_from_claude_envelope({"total_cost_usd": float("nan")}) is None
    assert llm._usage_from_claude_envelope({"total_cost_usd": 10**309}) is None
    # ...and a junk primary field still falls through to a valid legacy one.
    env = json.loads('{"total_cost_usd": Infinity, "cost_usd": 0.1}')
    assert llm._usage_from_claude_envelope(env).cost_usd == pytest.approx(0.1)


def test_manifest_stamp_rejects_non_finite_and_junk_values():
    """The stamp sites and entry_usage share ONE filter: only finite costs and non-negative real
    ints reach the committed JSON — and junk already IN a manifest is dropped on read."""
    entry = manifest.make_entry("abc", "m", "rv", cost_usd=float("nan"), tokens_in=-5, tokens_out=3)
    assert "cost_usd" not in entry and "tokens_in" not in entry
    assert entry["tokens_out"] == 3
    assert "cost_usd" not in manifest.make_entry("abc", "m", "rv", cost_usd=True)
    assert "cost_usd" not in manifest.make_repo_entry("deadbeef", "m", cost_usd=float("inf"))
    hand_edited = {"sha256": "abc", "cost_usd": float("inf"), "tokens_in": -1, "tokens_out": 10**9}
    assert manifest.entry_usage(hand_edited) == {"tokens_out": 10**9}
    assert manifest.entry_usage({"sha256": "abc", "cost_usd": 10**309}) == {}


def test_run_session_claude_error_envelope_carries_usage_on_the_exception(monkeypatch):
    """A failure envelope still reports what the session COST (error_max_turns, API errors) —
    the raised error carries it so the run total can honor 'failed sessions included'."""
    envelope = json.dumps(
        {
            "type": "result",
            "is_error": True,
            "api_error_status": 429,
            "result": "quota",
            "total_cost_usd": 1.87,
            "usage": {"output_tokens": 12},
        }
    )
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _FakeProc(0, envelope))
    with pytest.raises(RuntimeError) as excinfo:
        llm._run_session("claude", ["claude", "-p"], "PROMPT")
    carried = excinfo.value.session_usage
    assert carried.cost_usd == pytest.approx(1.87) and carried.output_tokens == 12


def test_failed_session_exception_usage_counts_in_run_total(tmp_citadel, fake_agent):
    """The ingest side of the carry: a session that RAISES (vs. one that returns and then fails
    validation) still lands its exception-carried spend in the run total — never the manifest."""
    (tmp_citadel.raw / "notes.md").write_text("alpha\n", encoding="utf-8")
    error = RuntimeError("claude CLI error (429): quota")
    error.session_usage = llm.SessionUsage(cost_usd=0.8)
    fake_agent(error=error)

    report = ingest.ingest()

    assert report.errors
    assert "raw/notes.md" not in tmp_citadel.read_manifest()
    assert report.usage == llm.SessionUsage(cost_usd=0.8)


def test_run_session_verbose_claude_still_returns_usage(monkeypatch):
    """CITADEL_LLM_VERBOSE=1 routes through _stream_subprocess — the envelope parse (and thus
    every cost stamp) must work on the streamed output exactly like the captured path."""
    monkeypatch.setattr(config, "LLM_VERBOSE", True, raising=False)
    monkeypatch.setattr(config, "LLM_LOG_DIR", "", raising=False)
    envelope = '{"type":"result","is_error":false,"total_cost_usd":0.07,"usage":{"output_tokens":3}}'
    monkeypatch.setattr(llm, "_stream_subprocess", lambda cli, argv, stdin_text: (0, envelope, ""))
    usage = llm._run_session("claude", ["claude", "-p"], "PROMPT")
    assert usage.cost_usd == pytest.approx(0.07) and usage.output_tokens == 3


def test_cli_help_probe_uses_devnull_stdin(monkeypatch):
    """The --help probe must never inherit stdin (a blocking --help would stall against the
    timeout; on Windows a killed .cmd shim can hang the collect) — DEVNULL gives immediate EOF."""
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {})
    seen: dict = {}

    def fake_run(argv, **kwargs):
        seen.update(kwargs)
        return _FakeProc(0, "--session-summary")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._cli_help_text("/bin/gemini")
    assert seen.get("stdin") == subprocess.DEVNULL


def test_gemini_summary_file_survives_unwritable_tempdir(monkeypatch):
    """An unwritable/full temp dir reads as 'no accounting this session' — never as a failed
    source (the session must run exactly as it would have pre-accounting)."""
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {"/bin/gemini": "--session-summary <file>"})

    def boom(*a, **k):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(llm.tempfile, "mkstemp", boom)
    assert llm._gemini_summary_file("gemini", "/bin/gemini") is None


def test_usage_from_gemini_summary_survives_pathological_nesting(tmp_path):
    """A pathologically nested stats file blows the recursion limit inside json.loads (or the
    walk) — that must record nothing, never fail the session it accounts for."""
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200000, encoding="utf-8")
    assert llm._usage_from_gemini_summary(deep) is None


def test_delete_cleanup_usage_counts_in_run_total(tmp_citadel, fake_agent):
    """A vanished source's delete-cleanup session spends real money too: it lands in the RUN
    total only — the source's manifest key is dropped, so there is no entry left to stamp."""
    src = tmp_citadel.raw / "notes.md"
    src.write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page(), usage=llm.SessionUsage(cost_usd=0.05))
    ingest.ingest()

    def delete_citing_page(*args, **kwargs):
        (Path(config.WIKI_DIR) / "concepts/topic.md").unlink()

    agent = fake_agent(side_effect=delete_citing_page, usage=llm.SessionUsage(cost_usd=0.02))
    src.unlink()
    report = ingest.ingest()

    assert "raw/notes.md" in report.sources_deleted
    assert agent.calls == [("raw/notes.md", "delete")]
    assert report.usage == llm.SessionUsage(cost_usd=0.02)
    assert "raw/notes.md" not in tmp_citadel.read_manifest()


def _repo_page(repo_key: str) -> dict:
    return {
        "systems/svc.md": (
            {"type": "System", "title": "Svc", "description": "d", "tags": ["t"], "resource": repo_key},
            f"Fact.[^s1]\n\n## Sources\n\n[^s1]: [{repo_key}]({repo_key.replace('raw/', '../../raw/')}) "
            "- repo (ingested 2026-06-21)\n",
        )
    }


def test_repo_ingest_stamps_usage(repo_wiki, fake_agent, make_repo):
    """The repo done-hook stamps the session's usage into the commit-keyed entry — the repo twin
    of the file-source stamp guarantee."""
    make_repo(repo_wiki.raw, "svc", {"README.md": "# Svc\n"})
    fake_agent(_repo_page("raw/svc"), usage=llm.SessionUsage(cost_usd=0.09, input_tokens=7, output_tokens=2))
    ingest.ingest()

    entry = repo_wiki.read_manifest()["raw/svc"]
    assert entry["kind"] == "git"
    assert entry["cost_usd"] == 0.09 and entry["tokens_in"] == 7 and entry["tokens_out"] == 2


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_repo_move_carries_usage_stamp(repo_wiki, fake_agent):
    """A repo folder rename (same commit, old path gone) is a MOVE: re-keyed without a session,
    the usage stamp carried — snap-identity marker repos are excluded from move detection, so
    this needs a REAL git repo (local git only, still offline)."""
    root = repo_wiki.raw / "svc"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("x\n", encoding="utf-8")
    for args in (
        ["init", "-q"],
        ["config", "user.email", "t@t.t"],
        ["config", "user.name", "t"],
        ["config", "commit.gpgsign", "false"],
        ["add", "-A"],
        ["commit", "-qm", "one"],
    ):
        subprocess.run(["git", *args], cwd=str(root), check=True, capture_output=True)
    fake_agent(_repo_page("raw/svc"), usage=llm.SessionUsage(cost_usd=0.09, input_tokens=7, output_tokens=2))
    ingest.ingest()
    assert repo_wiki.read_manifest()["raw/svc"]["cost_usd"] == 0.09

    agent = fake_agent(pages={})  # a move must not re-run a session
    root.rename(repo_wiki.raw / "svc-renamed")
    ingest.ingest()

    entries = repo_wiki.read_manifest()
    assert "raw/svc" not in entries
    moved = entries["raw/svc-renamed"]
    assert moved["cost_usd"] == 0.09 and moved["tokens_in"] == 7 and moved["tokens_out"] == 2
    assert agent.count == 0
