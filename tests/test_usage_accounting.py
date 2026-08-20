"""Per-session cost accounting (the 2026-07 audit's backlog #2), fully offline.

The backend CLIs' own cost/usage reports — claude's ``--output-format json`` envelope, copilot's
JSONL stream, agy's ``stream-json`` events — are parsed per session (:class:`llm.SessionUsage`), combined
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


# --- the effective model each backend reports -------------------------------------------------
#
# Every fixture below is a TRIMMED but shape-faithful copy of what the installed CLI actually
# emitted in a probe session, so the parsers are tested against the real envelopes.


def test_claude_envelope_names_the_model_that_carried_the_session():
    """claude routes cheap side work to a smaller model, so modelUsage regularly holds two
    entries: the PRIMARY one is the one with the token volume, not the first key. canonicalModel
    wins over the raw key, which carries context-window suffixes and dated ids."""
    env = {
        "type": "result",
        "total_cost_usd": 0.21,
        "modelUsage": {
            "claude-haiku-4-5-20251001": {"inputTokens": 40, "outputTokens": 12, "canonicalModel": "claude-haiku-4-5"},
            "claude-opus-5[1m]": {
                "inputTokens": 120,
                "outputTokens": 900,
                "cacheReadInputTokens": 40000,
                "cacheCreationInputTokens": 3000,
                "canonicalModel": "claude-opus-5",
                "provider": "firstParty",
            },
        },
    }
    assert llm._usage_from_claude_envelope(env).model == "claude-opus-5"
    assert llm._model_from_claude_envelope({"modelUsage": {"llama3.1:8b": {"outputTokens": 5}}}) == "llama3.1:8b"


def test_claude_model_parse_is_defensive_so_proxy_backends_fall_back():
    """An Ollama/proxy-backed claude fills in nothing here. That must read as 'unknown' (the
    caller then stamps the configured label), never as a crash or an invented id."""
    for env in ({}, {"modelUsage": None}, {"modelUsage": {}}, {"modelUsage": {"": {}, "  ": {}}}):
        assert llm._model_from_claude_envelope(env) is None
    # A junk stats value must not shadow the key itself.
    assert llm._model_from_claude_envelope({"modelUsage": {"m": "not-a-dict"}}) == "m"


def test_usage_from_copilot_jsonl_reads_model_and_ai_credits():
    """copilot quotes no dollars — its billing unit is the AI credit, metered as totalNanoAiu
    (1 AIC = 1e9), which is also the "N AIC used" figure its interactive footer shows. Those
    credits convert to dollars at GitHub's fixed published rate so a mixed corpus stays
    comparable. copilot reports no prompt-side count, so input_tokens stays honestly None."""
    stream = "\n".join(
        [
            "Some banner line that is not JSON",
            json.dumps({"type": "model.call_start", "data": {"model": "claude-sonnet-4.5"}}),
            json.dumps({"type": "assistant.message", "data": {"model": "claude-sonnet-4.5", "outputTokens": 120}}),
            json.dumps({"type": "assistant.message", "data": {"model": "claude-sonnet-4.5", "outputTokens": 30}}),
            json.dumps(
                {"type": "session.usage_checkpoint", "data": {"totalNanoAiu": 2508300000, "totalPremiumRequests": 1}}
            ),
            '{"type": "result", "usage": {"premi',  # a killed session truncates its last line
        ]
    )
    usage = llm._usage_from_copilot_jsonl(stream)
    assert usage.model == "claude-sonnet-4.5"
    assert usage.aic == pytest.approx(2.5083)
    assert usage.cost_usd == pytest.approx(0.025083)  # 1 AIC = $0.01
    assert usage.output_tokens == 150
    assert usage.input_tokens is None
    # The retired premium-request counter is deliberately ignored: every ingest session is "1".


def test_copilot_checkpoints_report_totals_not_deltas():
    """Each usage_checkpoint restates the session total, so the LAST one wins — summing them
    would multiply the billed credits."""
    stream = "\n".join(
        [
            json.dumps({"type": "session.usage_checkpoint", "data": {"totalNanoAiu": 1000000000}}),
            json.dumps({"type": "session.usage_checkpoint", "data": {"totalNanoAiu": 3000000000}}),
        ]
    )
    assert llm._usage_from_copilot_jsonl(stream).aic == pytest.approx(3.0)


def test_copilot_falls_back_to_the_cache_state_model():
    stream = json.dumps(
        {
            "type": "session.usage_checkpoint",
            "data": {"totalPremiumRequests": 1, "modelCacheState": [{"modelId": "gpt-5.4"}]},
        }
    )
    assert llm._usage_from_copilot_jsonl(stream).model == "gpt-5.4"


def test_usage_from_agy_stream_reads_init_model_and_result_totals():
    """agy names the effective model only in its opening init event, and totals the session in
    the closing result event."""
    stream = "\n".join(
        [
            json.dumps({"event": "init", "init": {"model": "gemini-3.1-pro-high", "permission_mode": "bypass"}}),
            json.dumps({"event": "message", "message": {"text": "working"}}),
            json.dumps(
                {
                    "event": "result",
                    "result": {"usage": {"input_tokens": 8123, "output_tokens": 611, "thinking_tokens": 40}},
                }
            ),
        ]
    )
    usage = llm._usage_from_agy_stream(stream)
    assert (usage.model, usage.input_tokens, usage.output_tokens) == ("gemini-3.1-pro-high", 8123, 611)
    assert usage.cost_usd is None  # agy quotes no dollars


def test_agy_without_an_explicit_model_reports_no_model():
    """Left on the CLI's own default, agy's init event carries no model key at all — 'unknown' is
    the honest answer, not a guess."""
    stream = (
        json.dumps({"event": "init", "init": {"cwd": "/w"}})
        + "\n"
        + json.dumps({"event": "result", "result": {"usage": {"input_tokens": 5, "output_tokens": 2}}})
    )
    usage = llm._usage_from_agy_stream(stream)
    assert usage.model is None and usage.input_tokens == 5


def test_stream_parsers_are_defensive_about_junk():
    """These streams are external input on the accounting path, which may never fail a session."""
    for text in ("", "not json at all\n", "{not json\n", json.dumps({"type": "noise"}), "[1,2,3]\n"):
        assert llm._usage_from_copilot_jsonl(text) is None
        assert llm._usage_from_agy_stream(text) is None
    # Negative/bool counts from a corrupted stream never surface.
    assert llm._usage_from_agy_stream(json.dumps({"result": {"usage": {"input_tokens": -5}}})) is None
    junk_credits = json.dumps({"type": "session.usage_checkpoint", "data": {"totalNanoAiu": -5}})
    assert llm._usage_from_copilot_jsonl(junk_credits) is None


def test_usage_from_stream_dispatches_per_backend():
    """claude reports through its result envelope, not this seam."""
    assert llm._usage_from_stream("claude", json.dumps({"type": "result"})) is None
    copilot = json.dumps({"type": "assistant.message", "data": {"model": "m", "outputTokens": 3}})
    assert llm._usage_from_stream("copilot", copilot).model == "m"
    agy = json.dumps({"event": "init", "init": {"model": "g"}})
    assert llm._usage_from_stream("agy", agy).model == "g"


def test_combine_usage_carries_the_model_and_sums_credits():
    """A chunked source runs every segment on the same model, so the first known one describes
    the whole import; AI credits sum like tokens."""
    parts = [
        llm.SessionUsage(output_tokens=10, aic=1.5),
        llm.SessionUsage(output_tokens=5, aic=1.25, model="claude-sonnet-4.5"),
    ]
    combined = llm.combine_usage(parts)
    assert combined.model == "claude-sonnet-4.5"
    assert combined.aic == pytest.approx(2.75) and combined.output_tokens == 15
    assert "2.75 AIC" in llm.SessionUsage(aic=2.75).describe()


def test_format_aic_never_rounds_a_fraction_of_a_credit_to_zero():
    assert llm.format_aic(2.5083) == "2.5083"
    assert llm.format_aic(2.0) == "2.0"
    assert llm.format_aic(0.0004) == "0.0004"
    assert llm.format_aic(1204.5) == "1,204.5"
    assert llm.format_aic(float("nan")) == "nan"  # never raises on a hand-edited manifest


# --- hermetic isolation: the auth-failure auto-retry -------------------------------------------


def test_hermetic_auth_failure_retries_once_without_the_isolation_flag(tmp_citadel, monkeypatch, capsys):
    """On a machine whose CLI credentials live in the personal config `--bare` skips, EVERY
    session died on authentication until the user found CITADEL_HERMETIC=0. Isolation is a
    hardening nicety; ingesting at all is the product — so an auth-shaped failure under hermetic
    mode retries ONCE without the flag, loudly."""
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda cli: "/bin/claude")
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {"/bin/claude": "--bare"})
    seen: list[bool] = []

    def fake_run_session(cli, argv, stdin_text, *, log_label=None):
        bare = "--bare" in argv
        seen.append(bare)
        if bare:
            message = "claude CLI error: Not logged in - Please run /login"
            error = RuntimeError(message + llm._hermetic_auth_hint(cli, argv, message))
            error.hermetic_auth_failure = True
            raise error
        return llm.SessionUsage(cost_usd=0.02)

    monkeypatch.setattr(llm, "_run_session", fake_run_session)
    assert llm.run_ingest_session("raw/notes.md") == llm.SessionUsage(cost_usd=0.02)
    assert seen == [True, False]  # exactly one retry, and it dropped the flag
    assert "retrying this session without hermetic isolation" in capsys.readouterr().err


def test_a_real_credential_problem_still_fails_instead_of_looping(tmp_citadel, monkeypatch):
    """The retry is scoped tightly: it happens once, so a genuinely logged-out CLI fails the
    source rather than spinning."""
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda cli: "/bin/claude")
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {"/bin/claude": "--bare"})
    calls = {"n": 0}

    def always_auth_fail(cli, argv, stdin_text, *, log_label=None):
        calls["n"] += 1
        error = RuntimeError("claude CLI error: Not logged in")
        error.hermetic_auth_failure = "--bare" in argv
        raise error

    monkeypatch.setattr(llm, "_run_session", always_auth_fail)
    with pytest.raises(RuntimeError, match="Not logged in"):
        llm.run_ingest_session("raw/notes.md")
    assert calls["n"] == 2


def test_a_non_auth_failure_is_never_retried(tmp_citadel, monkeypatch):
    """Re-running a session costs real money, so anything but the auth signature is re-raised
    untouched — including an auth-shaped failure when no isolation flag was even passed."""
    monkeypatch.setattr(config, "LLM_CLI", "claude", raising=False)
    monkeypatch.setattr(llm, "_resolve_cli", lambda cli: "/bin/claude")
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {"/bin/claude": "--bare"})
    calls = {"n": 0}

    def boom(cli, argv, stdin_text, *, log_label=None):
        calls["n"] += 1
        raise RuntimeError("the claude CLI failed (exit 1): rate limited")

    monkeypatch.setattr(llm, "_run_session", boom)
    with pytest.raises(RuntimeError, match="rate limited"):
        llm.run_ingest_session("raw/notes.md")
    assert calls["n"] == 1

    # No advertised flag = nothing to drop, so no retry even on an auth-shaped message.
    monkeypatch.setattr(llm, "_HELP_TEXT_CACHE", {"/bin/claude": "no isolation flag here"})
    calls["n"] = 0

    def auth_fail(cli, argv, stdin_text, *, log_label=None):
        calls["n"] += 1
        raise RuntimeError("claude CLI error: Not logged in")

    monkeypatch.setattr(llm, "_run_session", auth_fail)
    with pytest.raises(RuntimeError, match="Not logged in"):
        llm.run_ingest_session("raw/notes.md")
    assert calls["n"] == 1


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


def test_seconds_stamp_rounds_carries_and_rejects_junk():
    """The `seconds` field — citadel's own wall-clock measurement — follows the usage-stamp
    contract: rounded on write, read back by entry_usage as kwargs (so the move/re-stamp carry
    sites splat it through unchanged), junk dropped rather than coerced, unknown ABSENT."""
    entry = manifest.make_entry("abc", "m", "rv", seconds=123.44)
    assert entry["seconds"] == 123.4  # one decimal: sub-second precision without float noise
    assert manifest.entry_usage(entry)["seconds"] == 123.4
    carried = manifest.make_entry("abc", "m", "rv", **manifest.entry_usage(entry))
    assert carried["seconds"] == 123.4  # a move/re-stamp carries the stamp like ingested_at
    for junk in (float("nan"), float("inf"), -5, "fast", True):
        assert "seconds" not in manifest.make_entry("abc", "m", "rv", seconds=junk)
    assert "seconds" not in manifest.make_entry("abc", "m", "rv")  # unknown is ABSENT


def test_ingest_stamps_wall_clock_seconds(tmp_citadel, fake_agent):
    """Every successful source records how long the run spent on it. On a local model, TIME is
    the cost — the backend reports no dollars — so the duration belongs in the manifest beside
    the backend-reported figures, and `citadel status` / the viewer render it from there."""
    (tmp_citadel.raw / "notes.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page())
    ingest.ingest()
    entry = tmp_citadel.read_manifest()["raw/notes.md"]
    assert isinstance(entry.get("seconds"), (int, float)) and entry["seconds"] >= 0


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


def test_ai_credits_travel_from_the_session_to_status(tmp_citadel, fake_agent):
    """copilot bills in AI credits, not dollars, so that unit gets its own stamp all the way
    through: session -> manifest -> the status table and its corpus total. The derived dollars
    ride ALONGSIDE the credits, never instead of them."""
    (tmp_citadel.raw / "a.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page("raw/a.md"), usage=llm.SessionUsage(cost_usd=0.025083, aic=2.5083, output_tokens=40))
    ingest.ingest()

    entry = tmp_citadel.read_manifest()["raw/a.md"]
    assert entry["aic"] == pytest.approx(2.5083) and entry["cost_usd"] == pytest.approx(0.0251)
    report = status.build_status()
    rendered = report.render()
    assert "$0.0251 (2.5083 AIC)" in rendered
    assert "Recorded AI credits: 2.5083 AIC over 1 source(s)" in rendered
    assert report.as_dict()["aic_total"] == pytest.approx(2.5083)


def test_credits_without_dollars_are_still_shown_everywhere(tmp_citadel, fake_agent):
    """``cost_usd`` and ``aic`` are stamped INDEPENDENTLY, so a session can report credits and no
    dollars. Every consumer must then show the credits: rendering ``—`` would hide spend the
    corpus total is already counting."""
    (tmp_citadel.raw / "a.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page("raw/a.md"), usage=llm.SessionUsage(aic=2.5083, output_tokens=40))
    ingest.ingest()

    entry = tmp_citadel.read_manifest()["raw/a.md"]
    assert entry["aic"] == pytest.approx(2.5083) and "cost_usd" not in entry
    assert "2.5083 AIC" in status.build_status().render()
    catalog = (config.wiki_dir() / "sources" / "index.md").read_text(encoding="utf-8")
    assert "2.5083 AIC" in catalog and "| — |" not in catalog.split("raw/a.md")[1].split("\n")[0]


def test_ingest_stamps_the_model_the_backend_actually_reported(tmp_citadel, fake_agent, monkeypatch):
    """The manifest must name what RAN, not what .env asked for — the configured label is only a
    fallback for a backend that reported nothing."""
    monkeypatch.setattr(config, "LLM_CLI", "copilot", raising=False)
    monkeypatch.setattr(config, "INGEST_MODEL", "auto", raising=False)
    (tmp_citadel.raw / "a.md").write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page("raw/a.md"), usage=llm.SessionUsage(model="claude-sonnet-4.5", aic=1.0))
    ingest.ingest()
    assert tmp_citadel.read_manifest()["raw/a.md"]["model"] == "copilot:claude-sonnet-4.5"

    (tmp_citadel.raw / "b.md").write_text("beta\n", encoding="utf-8")
    fake_agent(_valid_page("raw/b.md"), usage=llm.SessionUsage(aic=1.0))  # nothing reported
    ingest.ingest()
    assert tmp_citadel.read_manifest()["raw/b.md"]["model"] == "copilot:auto"


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
        return _FakeProc(0, "--bare")

    monkeypatch.setattr(subprocess, "run", fake_run)
    llm._cli_help_text("/bin/claude")
    assert seen.get("stdin") == subprocess.DEVNULL


def test_stream_parsers_survive_pathological_nesting():
    """A pathologically nested line blows the recursion limit inside json.loads — that must
    record nothing, never fail the session it accounts for."""
    deep = "[" * 200000
    assert llm._usage_from_copilot_jsonl("{" * 200000) is None
    assert llm._usage_from_agy_stream(deep) is None
    assert list(llm._iter_jsonl("{" * 200000)) == []


def test_delete_cleanup_usage_counts_in_run_total(tmp_citadel, fake_agent):
    """A vanished source's delete-cleanup session spends real money too: it lands in the RUN
    total only — the source's manifest key is dropped, so there is no entry left to stamp."""
    src = tmp_citadel.raw / "notes.md"
    src.write_text("alpha\n", encoding="utf-8")
    fake_agent(_valid_page(), usage=llm.SessionUsage(cost_usd=0.05))
    ingest.ingest()

    def delete_citing_page(*args, **kwargs):
        (Path(config.wiki_dir()) / "concepts/topic.md").unlink()

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
