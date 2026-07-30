"""Session-usage accounting: what one agent session cost, as the backend itself reports it.

The :class:`SessionUsage` value object, its combinators/formatters, and the per-backend
envelope parsers — claude's ``--output-format json`` result envelope, copilot's
``--output-format json`` JSONL stream, agy's ``--output-format stream-json`` events. All of it
is strictly PASSIVE: these parsers read external input on the accounting path, so they never
raise — junk shapes read as absent, a whole-unknown session is ``None``, and no usage path can
ever fail a session.

Split out of :mod:`citadel.llm`, which re-exports every name here — ``llm.SessionUsage`` /
``llm.combine_usage`` / ``llm._usage_from_claude_envelope`` etc. remain the addressable
surface; :mod:`citadel.llm` stays the only place that TALKS to an LLM.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionUsage:
    """What ONE agent session cost, exactly as the backend CLI reports it — never estimated,
    never priced by us (the audit's cost-observability gap: the product argues in budgets while
    the CLIs' own cost envelopes were discarded).

    - ``cost_usd`` — the session's dollar figure: the backend's OWN number where it quotes one
      (claude's ``total_cost_usd``), or copilot's AI credits converted at GitHub's published,
      fixed 1 AIC = $0.01 (see ``aic``). None for a backend that offers neither (agy).
    - ``input_tokens`` — the prompt-side total actually processed, INCLUDING cache writes/reads
      (the honest volume, not just the uncached slice).
    - ``output_tokens`` — the completion-side total.
    - ``aic`` — copilot's billing unit, **AI credits**, from its ``totalNanoAiu`` counter
      (1 AIC = 1e9 nanoAiu; it is the ``N AIC used`` figure the interactive CLI prints in its
      session footer). copilot quotes no dollars itself, so without this a copilot wiki would
      show "no cost data" forever. Its predecessor ``totalPremiumRequests`` is a legacy counter
      that GitHub retired in favour of credits, so it is deliberately NOT recorded.
    - ``model`` — the model the backend says ACTUALLY ran, as it names it
      (``claude-opus-5``, ``claude-sonnet-4.5``, ``gemini-3.1-pro-high``). This is the whole point
      of reading the session envelope: the configured ``CITADEL_INGEST_MODEL`` is a REQUEST, and
      recording it as fact would claim a model that may never have served the session (an `auto`
      selection, a backend fallback, a stale ``.env``). None when the backend named nothing.

    Every field is None when unknown; a whole-unknown session is represented as ``None`` rather
    than an empty instance (:func:`combine_usage` returns None when no part knew anything), so
    "no data" never renders as "$0.00"."""

    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    aic: float | None = None
    model: str | None = None

    def describe(self) -> str:
        """One ASCII report fragment: ``$0.42, tokens 1,234,567 in / 45,678 out, 2.51 AIC``
        — only the fields that are actually known (an unknown side is OMITTED, never rendered as
        a 0 that reads like a real count), "" when none are (so callers can skip the line). The
        model is NOT part of this fragment: it is provenance, not spend, and is reported on its
        own line/column."""
        parts: list[str] = []
        if self.cost_usd is not None:
            parts.append(format_cost(self.cost_usd))
        tokens = [
            f"{count:,} {label}"
            for count, label in ((self.input_tokens, "in"), (self.output_tokens, "out"))
            if count is not None
        ]
        if tokens:
            parts.append("tokens " + " / ".join(tokens))
        if self.aic is not None:
            parts.append(f"{format_aic(self.aic)} AIC")
        return ", ".join(parts)


def combine_usage(parts) -> SessionUsage | None:
    """Sum an iterable of ``SessionUsage | None`` into one (a chunked source's segments, a run's
    sources). Each field sums over the parts that KNOW it and stays None when none did — so a
    claude+copilot mix keeps honest semantics (cost from the sessions that priced themselves,
    tokens from the ones that counted). ``model`` is not summable: the FIRST part that named one
    wins (every segment of a source runs on the same backend/model, and a run-level mix is
    reported per source anyway). Returns None when no part carried anything, and skips
    non-``SessionUsage`` values entirely (the test fakes return None)."""
    cost = tokens_in = tokens_out = aic = model = None
    for part in parts:
        if not isinstance(part, SessionUsage):
            continue
        if part.cost_usd is not None:
            cost = (cost or 0.0) + part.cost_usd
        if part.input_tokens is not None:
            tokens_in = (tokens_in or 0) + part.input_tokens
        if part.output_tokens is not None:
            tokens_out = (tokens_out or 0) + part.output_tokens
        if part.aic is not None:
            aic = (aic or 0.0) + part.aic
        if model is None and part.model:
            model = part.model
    if cost is None and tokens_in is None and tokens_out is None and aic is None and model is None:
        return None
    return SessionUsage(cost_usd=cost, input_tokens=tokens_in, output_tokens=tokens_out, aic=aic, model=model)


def format_cost(cost_usd: float) -> str:
    """``$0.053`` / ``$1.20`` / ``$1,234.50`` — four decimals so a sub-cent session never rounds
    to a lying ``$0.00``, trailing zeros trimmed but never below the conventional two decimals.
    Never raises: a non-finite value (a hand-edited manifest is external input) formats without
    the decimal-point trimming (``$nan``) instead of crashing a status/report render."""
    if not math.isfinite(cost_usd):
        return f"${cost_usd}"
    text = f"{cost_usd:,.4f}"
    while text.endswith("0") and len(text) - text.rindex(".") > 3:  # keep >= 2 decimals
        text = text[:-1]
    return f"${text}"


# GitHub prices one AI credit at a fixed, published $0.01 (docs.github.com "GitHub Copilot
# billing"). It is a stated rate, not a market price, so converting is arithmetic rather than an
# estimate — which is what lets a mixed claude+copilot corpus have ONE comparable cost total. The
# credits themselves are always kept and shown alongside, so nothing is lost if the rate changes.
AIC_USD = 0.01


def format_aic(aic: float) -> str:
    """``2.51`` / ``0.0042`` / ``1,204.5`` — AI credits at four decimals with trailing zeros
    trimmed to at least one, so a fraction-of-a-credit session never renders as a lying ``0``.
    Never raises on a non-finite value (a hand-edited manifest is external input)."""
    if not math.isfinite(aic):
        return str(aic)
    text = f"{aic:,.4f}"
    while text.endswith("0") and len(text) - text.rindex(".") > 2:  # keep >= 1 decimal
        text = text[:-1]
    return text


def _finite_cost(value) -> float | None:
    """``value`` as a finite float, or None — the ONE sanitizer for externally-supplied cost
    figures. Rejects non-numbers, bools (an int subclass), non-finite floats (json.loads accepts
    ``Infinity``/``NaN`` by default), and ints too large for a float (``float()`` would raise
    OverflowError — accounting must never be able to fail a session)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (OverflowError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _positive_int(value) -> int | None:
    """``value`` as a positive real int, or None — the shared filter for externally-supplied
    counts (tokens, nano-AI-units). Rejects bools (an int subclass), non-ints and values <= 0,
    so a corrupted/hand-edited envelope can never surface a negative or fake-zero count."""
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _model_from_claude_envelope(env: dict) -> str | None:
    """Which model ACTUALLY served a claude session, from the envelope's ``modelUsage`` map
    (``{"claude-opus-5[1m]": {...}, "claude-haiku-4-5-...": {...}}``).

    claude routes cheap side work (title generation, small classifications) to a second, smaller
    model, so the map regularly holds more than one entry and "the first key" would report the
    wrong one. The PRIMARY model is the one that carried the session's volume, so entries are
    ranked by total token traffic (prompt + completion + both cache sides). Ties fall back to
    declaration order, which is what a single-entry map trivially yields.

    ``canonicalModel`` is preferred over the raw key when present: the key carries context-window
    suffixes (``claude-opus-5[1m]``) and dated ids that differ across releases of the same model.
    Purely defensive — a missing/foreign-shaped map (an Ollama or other proxy backend that fills
    in nothing) simply reads as None, and the caller falls back to the configured label."""
    usage = env.get("modelUsage")
    if not isinstance(usage, dict):
        return None
    best_name: str | None = None
    best_volume = -1
    for name, stats in usage.items():
        if not isinstance(name, str) or not name.strip():
            continue
        stats = stats if isinstance(stats, dict) else {}
        volume = sum(
            _positive_int(stats.get(key)) or 0
            for key in ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")
        )
        if volume > best_volume:
            canonical = stats.get("canonicalModel")
            best_name = canonical.strip() if isinstance(canonical, str) and canonical.strip() else name.strip()
            best_volume = volume
    return best_name


def _iter_jsonl(text: str):
    """Every line of ``text`` that parses as a JSON object, in order — the shared reader for the
    JSONL/stream-json envelopes copilot and agy emit. Non-JSON lines (a banner, an update notice,
    a truncated final line from a killed session) are skipped rather than fatal: these streams are
    external input on the accounting path, which must never fail a session."""
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, RecursionError):
            continue
        if isinstance(obj, dict):
            yield obj


def _usage_from_copilot_jsonl(text: str) -> SessionUsage | None:
    """The model + spend of a copilot session, from its ``--output-format json`` JSONL stream.

    copilot quotes no dollars, so its OWN billing unit is recorded instead: the
    ``session.usage_checkpoint`` events carry ``totalNanoAiu``, the nano-precision counter behind
    the ``N AIC used`` figure the interactive CLI prints in its session footer (1 AIC = 1e9
    nanoAiu). Those credits are converted to dollars at GitHub's fixed published rate
    (:data:`AIC_USD`) so a mixed-backend corpus still has one comparable cost total, while the
    credits stay recorded as the primary, un-derived figure. The legacy ``totalPremiumRequests``
    counter in the same event is deliberately ignored — GitHub retired it in favour of credits,
    and it is far too coarse to describe a session (every ingest is "1").

    The same checkpoints' ``modelCacheState`` entries name the model, as do ``assistant.message``
    events; the model is taken from the LAST event that names one (a session that switches models
    mid-run is reported by what finished it). Output tokens are summed across assistant messages —
    copilot reports no prompt-side count, so ``input_tokens`` stays honestly None.

    Best-effort like every accounting path: a stream that says nothing usable returns None."""
    model: str | None = None
    nano_aiu: int | None = None
    tokens_out = 0
    for obj in _iter_jsonl(text):
        data = obj.get("data")
        data = data if isinstance(data, dict) else {}
        kind = obj.get("type")
        if kind in ("assistant.message", "model.call_start", "session.tools_updated"):
            name = data.get("model")
            if isinstance(name, str) and name.strip():
                model = name.strip()
            tokens_out += _positive_int(data.get("outputTokens")) or 0
        elif kind == "session.usage_checkpoint":
            # Each checkpoint reports the session TOTAL so far, not a delta — take the last.
            count = _positive_int(data.get("totalNanoAiu"))
            if count is not None:
                nano_aiu = count
            cache_state = data.get("modelCacheState")
            if model is None and isinstance(cache_state, list):
                for item in cache_state:
                    name = item.get("modelId") if isinstance(item, dict) else None
                    if isinstance(name, str) and name.strip():
                        model = name.strip()
                        break
    if model is None and nano_aiu is None and not tokens_out:
        return None
    aic = round(nano_aiu / 1_000_000_000, 6) if nano_aiu is not None else None
    return SessionUsage(
        cost_usd=round(aic * AIC_USD, 6) if aic is not None else None,
        output_tokens=tokens_out or None,
        aic=aic,
        model=model,
    )


def _error_from_copilot_jsonl(text: str) -> str | None:
    """The human-readable failure reason of a failed copilot session, from the ``session.error``
    events of its ``--output-format json`` JSONL stream — None when the stream names none.

    A failed copilot session exits non-zero with an EMPTY stderr: the message that names the fix
    (a BYOK provider that does not serve the configured model, an exhausted quota) travels as a
    ``session.error`` event near the END of the stdout stream, while the stream OPENS with
    ephemeral MCP/skills status events. Truncating raw stdout as the failure reason therefore
    showed exactly that opening noise — and hid an auth-shaped message from the hermetic-retry
    detection with it. Whitespace is collapsed (copilot wraps its messages over indented lines)
    and duplicate messages are folded, order preserved. Defensive like every stream reader:
    junk shapes read as absent, never raise."""
    messages: list[str] = []
    for obj in _iter_jsonl(text):
        if obj.get("type") != "session.error":
            continue
        data = obj.get("data")
        message = data.get("message") if isinstance(data, dict) else None
        if isinstance(message, str) and message.strip():
            messages.append(" ".join(message.split()))
    return "; ".join(dict.fromkeys(messages)) if messages else None


def _usage_from_agy_stream(text: str) -> SessionUsage | None:
    """The model + token usage of an agy (Antigravity CLI) session, from its
    ``--output-format stream-json`` stream: the opening ``init`` event names the effective model,
    and the closing ``result`` event carries the session's token totals
    (``input_tokens``/``output_tokens``). agy quotes no dollar cost, so ``cost_usd`` stays None.

    The ``init`` event only carries ``model`` when a model was explicitly selected; a session left
    on the CLI's own default names nothing, which correctly reads as "unknown" (the caller then
    falls back to the configured label rather than inventing an id)."""
    model: str | None = None
    tokens_in = tokens_out = 0
    for obj in _iter_jsonl(text):
        init = obj.get("init")
        if isinstance(init, dict):
            name = init.get("model")
            if model is None and isinstance(name, str) and name.strip():
                model = name.strip()
        result = obj.get("result")
        # The final `result` event totals the whole session; per-step usage would double count.
        usage = result.get("usage") if isinstance(result, dict) else None
        if isinstance(usage, dict):
            tokens_in = _positive_int(usage.get("input_tokens")) or 0
            tokens_out = _positive_int(usage.get("output_tokens")) or 0
    if model is None and not tokens_in and not tokens_out:
        return None
    return SessionUsage(input_tokens=tokens_in or None, output_tokens=tokens_out or None, model=model)


def _usage_from_claude_envelope(env: dict | None) -> SessionUsage | None:
    """The session's cost/usage from claude's ``--output-format json`` result envelope:
    ``total_cost_usd`` plus the ``usage`` token counts, and the model that actually served it
    (:func:`_model_from_claude_envelope`). Input tokens include the cache
    creation/read counts — the prompt-side volume actually billed, not just the uncached slice.
    Defensive by design (an envelope is external input): non-numeric fields read as absent, and
    an envelope carrying nothing usable returns None."""
    if not isinstance(env, dict):
        return None
    # First FINITE-NUMERIC value wins (cost_usd is the pre-GA envelope name): a present-but-junk
    # total_cost_usd — a string, a bool, NaN/Infinity, an overflowing int — must not shadow a
    # valid legacy field, and must never raise (see _finite_cost).
    cost_usd = next(
        (cost for cost in map(_finite_cost, (env.get("total_cost_usd"), env.get("cost_usd"))) if cost is not None), None
    )
    usage = env.get("usage")
    usage = usage if isinstance(usage, dict) else {}

    def count(key: str) -> int:
        return _positive_int(usage.get(key)) or 0

    tokens_in = count("input_tokens") + count("cache_creation_input_tokens") + count("cache_read_input_tokens")
    tokens_out = count("output_tokens")
    model = _model_from_claude_envelope(env)
    if cost_usd is None and not tokens_in and not tokens_out and model is None:
        return None
    return SessionUsage(
        cost_usd=cost_usd, input_tokens=tokens_in or None, output_tokens=tokens_out or None, model=model
    )


def _last_result_envelope(text: str) -> dict | None:
    """Fallback for claude: the last JSONL object whose ``type`` is ``result`` (in case the
    CLI streams instead of emitting one JSON object)."""
    found: dict | None = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("type") == "result":
            found = obj
    return found


def _usage_from_stream(cli: str, out: str) -> SessionUsage | None:
    """The model/spend a non-claude backend reported on stdout, per backend envelope format —
    None for a backend with no known format (an unknown CLI runs on a best-effort argv and is
    never assumed to speak one)."""
    if not out:
        return None
    if cli == "copilot":
        return _usage_from_copilot_jsonl(out)
    if cli == "agy":
        return _usage_from_agy_stream(out)
    return None
