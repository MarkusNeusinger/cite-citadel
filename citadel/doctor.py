"""``citadel doctor`` — a read-only diagnostic of the environment an ingest run needs.

One command answering "is my setup sane?" without touching a byte. Each check emits ONE
``OK`` / ``WARN`` / ``FAIL`` line so the first non-green line names what to fix:

- **workspace** — did discovery resolve a workspace, and via which mechanism (``CITADEL_WORKSPACE``
  env / ``citadel.toml`` marker / the ``CITADEL_WIKI_DIR``+``CITADEL_RAW_DIR`` env-dirs pair)? FAIL
  when none resolved (nearly every other command needs one).
- **rules** — does the effective rules tree resolve (packaged defaults + any workspace overrides),
  and how many files? FAIL when the packaged tree is missing entirely.
- **config** — did every env setting parse? A numeric knob whose value is not an integer
  (``CITADEL_MAX_SOURCE_CHARS=300k``, say) silently falls back to its default at import — this WARN
  line is where that fallback becomes visible.
- **agent CLI** — is the ``CITADEL_LLM_CLI`` binary on PATH (which path does it resolve to)? WARN,
  not FAIL — the CLI is only needed to *ingest*, and doctor must stay useful before it is installed.
- **ingest model** — which model ingest will ASK for. Every backend (claude/copilot/agy) is passed
  ``--model``, so an unset ``CITADEL_INGEST_MODEL`` simply means "the CLI's own default"; a
  RETIRED backend name (``gemini``, now Antigravity's ``agy``) FAILs here with its migration hint.
- **raw roots** — is every raw root ingest actually walks (``CITADEL_RAW_DIRS``) reachable (a dir
  on disk)? Also WARNs when the primary ``raw/`` was configured OUT of the walk list while holding
  files — those would silently never be ingested.
- **wiki placement** — does the wiki dir sit INSIDE a walked raw root (a whole mounted drive as one
  root)? Discovery excludes the wiki either way, so this is a clarity WARN, not data loss.
- **child paths** — the UNC advisory: ``resolve()`` rewrites a Windows mapped drive into its UNC
  form, which some agent CLIs refuse as a working directory; names the drive-letter spelling
  citadel hands child processes, or WARNs when only a UNC one exists.
- **manifest** — does ``wiki/.citadel_ingested.json`` parse, with its format version, source count,
  and a workspace stamp matching the current root?
- **failures** — a summary of the sources the failures catalog says could not be ingested.
- **billing** — the API-key billing-shadow heads-up: ``ANTHROPIC_API_KEY`` set while
  ``CITADEL_LLM_CLI=claude`` may bill the API per-token instead of the subscription (cross-referenced
  to the README "License & third-party tools" section, where the subscription-vs-API story is told
  once).
- **PDF mode** — ``CITADEL_PDF_MODE=images`` against a non-``claude`` backend may silently ingest a
  PDF's text only, because a non-vision CLI cannot look at the figures.
- **PDF text layer** — is the pypdf pre-pass active (``CITADEL_PDF_TEXT``)? pypdf is a bundled
  dependency, so this WARNs only in the unusual case that it was force-removed from the environment
  (PDF locators then stay agent-verified instead of offline-checkable); otherwise a plain on/off echo.
- **audio** — ``CITADEL_AUDIO_SUPPORT=1`` needs a whisper-class CLI on PATH
  (``CITADEL_WHISPER_CLI``); WARN when the configured binary is missing — every audio/video source
  would fail until it is installed. A plain OK note while the knob is off.
- **HTTP serve** — the opt-in Streamable HTTP transport (``citadel serve --http``): a plain "stdio
  only" note while no ``CITADEL_HTTP_TOKEN`` is set, otherwise where it would listen and whether the
  mutating tools are exposed — WARNing on a token too short for ``serve --http`` to accept (a
  refusal you would otherwise meet only at start-up) and on a non-loopback bind, which puts an
  unencrypted MCP endpoint on the network.
- **update** — is a newer ``cite-citadel`` published on PyPI than the installed version? WARN with the
  exact upgrade command for the *detected* install method (dev checkout / uv tool / uvx / pipx / pip)
  when behind; OK when current. The PyPI lookup is best-effort over a 2s timeout — any network absence
  degrades to an OK "check skipped" line, never a WARN/FAIL, so ``doctor`` stays useful fully offline.
- **coherence** — do the wiki's ``## Sources`` citations actually resolve UNDER a configured raw/docs
  root ("workspace coherence")? A wiki whose ``CITADEL_WIKI_DIR`` and ``CITADEL_RAW_DIR`` sit under
  different parents makes every ``../../raw/x`` citation resolve OUTSIDE the raw root, and everything
  degrades silently — ``grammar.is_source_citation`` rejects it, ``lint`` reports the sources broken,
  the viewer's source records lose their names/links — yet nothing else says the roots don't line up.
  WARN (never FAIL — advisory) naming the count, one example, where it resolved, and the fix; OK when
  every citation resolves under a root. Read-only over ``store.load`` and O(pages).

Read-only and defensive: every check degrades to a WARN/FAIL line rather than raising, so ``doctor``
never crashes on a half-configured workspace. Exit code is 0 unless some check FAILs. It opts out of
the workspace guard (``needs_workspace=False``) precisely so it can diagnose a MISSING workspace.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path

from . import __version__ as _INSTALLED_VERSION
from . import config, failures, manifest, wikigit


OK = "OK"
WARN = "WARN"
FAIL = "FAIL"


@dataclass
class Check:
    """One diagnostic line: its ``status`` (OK/WARN/FAIL), a short ``name``, and a human ``detail``."""

    status: str
    name: str
    detail: str


@dataclass
class DoctorReport:
    """The full set of checks, rendered as a plain ASCII block. ``ok`` is False iff any FAIL."""

    checks: list[Check] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(c.status == FAIL for c in self.checks)

    def render(self) -> str:
        lines = ["citadel doctor", "==============", ""]
        for c in self.checks:
            lines.append(f"[{c.status:<4}] {c.name}: {c.detail}")
        lines.append("")
        lines.append("No blocking problems." if self.ok else "FAIL - fix the failing check(s) above.")
        return "\n".join(lines).rstrip() + "\n"


def check_workspace() -> Check:
    """FAIL when no workspace resolved (the fail-loud guard would stop every other command); else OK
    with the resolved root and the mechanism that found it."""
    if not config.WORKSPACE_FOUND:
        return Check(
            FAIL, "workspace", "no workspace found - run `citadel init [DIR]`, cd into one, or set CITADEL_WORKSPACE"
        )
    return Check(OK, "workspace", f"{config.WORKSPACE_ROOT} (via {config.workspace_mechanism()})")


def check_rules() -> Check:
    """FAIL when the packaged rules tree resolves to nothing (a broken install); else OK with the
    effective file count and how many are workspace overrides shadowing the packaged defaults."""
    names = config.rules_relnames()
    if not names:
        return Check(
            FAIL,
            "rules",
            f"no rules files found under {config.PACKAGED_RULES_DIR} - the packaged rules tree is missing",
        )
    ws = config.workspace_rules_dir()
    overrides = 0
    if ws is not None:
        ws_res = config._safe_resolve(ws)
        for rel in names:
            try:
                if config._safe_resolve(config.effective_rules_file(rel)).is_relative_to(ws_res):
                    overrides += 1
            except (OSError, ValueError):
                pass
    detail = f"{len(names)} effective rules file(s)"
    detail += f", {overrides} workspace override(s)" if overrides else ", no workspace overrides"
    return Check(OK, "rules", detail)


def check_config() -> Check:
    """WARN when config fell back on a default because an env setting failed to parse (a
    non-integer numeric knob, say) — the value in effect is the default, not what the ``.env``
    says. OK when every setting parsed."""
    if config.CONFIG_WARNINGS:
        return Check(WARN, "config", "; ".join(config.CONFIG_WARNINGS))
    return Check(OK, "config", "all env settings parsed")


def check_agent_cli() -> Check:
    """WARN (not FAIL) when the configured ingest CLI binary is not on PATH — it is only needed to
    ingest, so doctor stays useful before it is installed; else OK with the resolved binary path.
    A RETIRED backend name (``gemini``) FAILs instead: no binary can satisfy it, and the migration
    hint is more useful than a PATH complaint."""
    from . import llm

    try:
        cli = llm.resolve_cli_name(config.LLM_CLI)
    except RuntimeError as exc:
        return Check(FAIL, "agent CLI", str(exc))
    try:
        path = llm._resolve_cli(cli)
    except RuntimeError:
        return Check(
            WARN,
            "agent CLI",
            f"{cli!r} not on PATH - ingest will fail until it is installed and logged in "
            f"(or set CITADEL_LLM_CLI / *_CLI_PATH)",
        )
    return Check(OK, "agent CLI", f"{cli!r} -> {path}")


def check_ingest_model() -> Check:
    """What model ingest will ASK the backend for — and, when the manifest already knows, what the
    backend last REPORTED actually running.

    Every supported backend honors ``--model``, so ``CITADEL_INGEST_MODEL`` is never inert any
    more (the pre-agy WARN this replaces): unset simply means "run the CLI's own default model",
    which is a legitimate, and common, setup. The recorded label is shown alongside because that
    is what lands in the manifest and the wiki's Sources catalog.

    One trap IS worth a WARN: the copilot backend also reads its own ``COPILOT_MODEL`` env var,
    and the ``--model`` flag citadel passes OVERRIDES it. A user who points copilot at a BYOK
    provider via ``COPILOT_PROVIDER_*``/``COPILOT_MODEL`` (a local Ollama-style endpoint) while a
    stale ``CITADEL_INGEST_MODEL`` still names a model that provider does not serve gets an
    instant per-source failure — so when both are set and disagree, name the shadowing here."""
    configured = (config.INGEST_MODEL or "").strip()
    detail = f"requesting {configured!r}" if configured else "unset - each CLI runs its own default model"
    if configured and (config.LLM_CLI or "claude").strip().lower() == "copilot":
        env_model = os.environ.get("COPILOT_MODEL", "").strip()
        provider = os.environ.get("COPILOT_PROVIDER_BASE_URL", "").strip()
        if env_model and env_model != configured:
            return Check(
                WARN,
                "ingest model",
                f"CITADEL_INGEST_MODEL={configured!r} shadows COPILOT_MODEL={env_model!r} - the --model"
                " flag citadel passes overrides the env var, so sessions request"
                f" {configured!r}"
                + (f", which the BYOK provider at {provider!r} must actually serve" if provider else "")
                + f". Set CITADEL_INGEST_MODEL={env_model} (or unset it) if the env var names the intended model",
            )
    return Check(
        OK, "ingest model", f"{detail}; recorded as {config.ingest_model_label()!r} unless the session reports one"
    )


def _primary_raw_excluded_from_walk(walked: list[Path]) -> bool:
    """True when the primary ``RAW_DIR`` is NOT among the walked roots (a ``CITADEL_RAW_DIRS``
    that replaced the walk list without re-listing it) while it exists and holds at least one
    entry — files that are citable but will never be scanned. Same path-identity normalization
    as :func:`config.source_roots`; degrades to False on any OS error (doctor never raises)."""
    primary = os.path.normcase(os.path.normpath(str(config.RAW_DIR)))
    if any(os.path.normcase(os.path.normpath(str(r))) == primary for r in walked):
        return False
    try:
        return Path(config.RAW_DIR).is_dir() and any(Path(config.RAW_DIR).iterdir())
    except OSError:
        return False


def check_raw_roots() -> Check:
    """The raw roots ingest actually WALKS (``config.RAW_DIRS`` — exactly discovery's list, not
    the wider :func:`config.source_roots` union, which counts cite-only roots as reachable). WARN
    when a walked root is not a reachable directory (an unmounted share, a not-yet-created raw/),
    and when the primary ``raw/`` is configured OUT of the walk list while holding files — its
    sources would silently never be ingested; else OK with the walked root count."""
    roots = [Path(r) for r in config.RAW_DIRS]
    if not roots:
        return Check(WARN, "raw roots", "no raw roots configured")
    missing = [r for r in roots if not r.is_dir()]
    if missing:
        return Check(
            WARN,
            "raw roots",
            f"{len(missing)}/{len(roots)} walked raw root(s) unreachable: " + ", ".join(str(r) for r in missing),
        )
    if _primary_raw_excluded_from_walk(roots):
        return Check(
            WARN,
            "raw roots",
            f"primary raw/ ({config.RAW_DIR}) is not in the CITADEL_RAW_DIRS walk list - its files "
            "are never scanned; include `raw` in CITADEL_RAW_DIRS to walk it",
        )
    return Check(OK, "raw roots", f"{len(roots)} walked raw root(s) reachable")


def check_wiki_placement() -> Check:
    """WARN when the wiki directory lies under a walked raw root — the self-ingest layout (a whole
    mounted drive configured as one raw root, with the wiki somewhere inside it). Discovery now
    excludes the wiki automatically (``ingest._is_wiki_internal``), so this is not a data-loss FAIL;
    it is worth saying out loud because the nesting still costs clarity: every wiki file sits inside
    a source tree, so a stray citation INTO the wiki looks like legal provenance, and any
    third-party tool pointed at the raw root sees generated pages as content. OK otherwise."""
    from . import grammar

    wiki = Path(config.WIKI_DIR)
    covering = [Path(r) for r in config.RAW_DIRS if grammar.is_within(wiki, r)]
    if not covering:
        return Check(OK, "wiki placement", "the wiki dir is outside every walked raw root")
    return Check(
        WARN,
        "wiki placement",
        f"the wiki dir ({wiki}) lies under walked raw root(s) {', '.join(str(r) for r in covering)} - "
        "discovery excludes it automatically (generated pages are never sources), but prefer a wiki "
        "outside the raw tree: narrow CITADEL_RAW_DIRS, or move the wiki with CITADEL_WIKI_DIR",
    )


def check_child_paths() -> Check:
    """The UNC advisory. ``Path.resolve()`` rewrites a Windows mapped network drive (``T:\\wiki``)
    into its UNC form (``\\\\server\\share\\wiki``), and that resolved path used to be what citadel
    handed to the agent CLI as its working directory — where some backends refuse to run at all
    ("environment blocks UNC/network paths") and git treats the spelling as a different repository.

    OK (with the drive-letter cwd named) when citadel recorded a non-UNC alias for the workspace,
    OK when no UNC path is involved at all, and WARN when the workspace really is UNC-only — then
    the agent genuinely runs on a UNC cwd, and the fix is to map the share to a drive letter and
    point ``CITADEL_WORKSPACE`` (or run citadel from) there."""
    root = Path(config.WORKSPACE_ROOT)
    native = config.native_form(root)
    if config._path_id(native) != config._path_id(root):
        return Check(OK, "child paths", f"agent sessions run in {native} (workspace resolves to {root})")
    if config._is_unc_path(root):
        return Check(
            WARN,
            "child paths",
            f"the workspace resolves to a UNC path ({root}) and no drive-letter spelling of it is "
            "known here - some agent CLIs refuse a UNC working directory and git treats it as a "
            "separate repository; map the share to a drive letter and set CITADEL_WORKSPACE to it "
            "(or run citadel from that drive) if sessions fail with path errors",
        )
    return Check(OK, "child paths", "no UNC/network path rewriting in effect")


def check_manifest() -> Check:
    """OK when there is no manifest yet (nothing ingested) or it parses with a matching workspace
    stamp; WARN when it is unparseable JSON (treated as empty) or its stamp names another workspace
    (keys may not line up). Reports the format version and source count.

    Reads the manifest through :func:`manifest.inspect` — ONE parse that also stashes the stamp for
    the mismatch probe below, so doctor never re-reads the file or reaches into manifest internals."""
    path = config.manifest_path()
    fmt, count, error = manifest.inspect()
    if error == "missing":
        return Check(OK, "manifest", f"no manifest yet ({path.name}) - nothing ingested")
    if error == "empty":
        return Check(OK, "manifest", f"empty manifest ({path.name})")
    if error is not None:  # "corrupt"
        return Check(WARN, "manifest", f"{path} is not valid JSON - treated as empty; re-ingest to rebuild")
    base = f"{count} source(s), format {fmt if fmt is not None else 'legacy/none'}"
    mismatch = manifest.stamped_workspace_mismatch()
    if mismatch:
        return Check(
            WARN,
            "manifest",
            f"{base}; stamped workspace {mismatch} != current {config.WORKSPACE_ROOT} (keys may not line up)",
        )
    return Check(OK, "manifest", f"{base}; workspace stamp matches")


def check_failures() -> Check:
    """WARN with a per-reason summary when the failures catalog lists stuck sources; else OK."""
    catalog = failures.load()
    if not catalog:
        return Check(OK, "failures", "no sources recorded as failed")
    reasons = Counter(str((e or {}).get("reason") or "?") for e in catalog.values() if isinstance(e, dict))
    summary = ", ".join(f"{n} {r}" for r, n in sorted(reasons.items()))
    return Check(WARN, "failures", f"{len(catalog)} source(s) could not be ingested ({summary}) - see `citadel status`")


def check_billing_shadow() -> Check:
    """WARN when ``ANTHROPIC_API_KEY`` is set while the claude CLI is the backend: the claude CLI may
    then bill the API per-token instead of using the logged-in subscription. Cross-references the
    README terms section so the subscription-vs-API story is told once. When ``ANTHROPIC_BASE_URL``
    also redirects the CLI at another endpoint (e.g. a local Ollama server), the key is not sent to
    Anthropic's API, so the subscription-vs-API-key WARN would be misleading — report OK noting the
    redirect (billing, if any, depends on that endpoint) instead."""
    cli = (config.LLM_CLI or "claude").strip().lower()
    if cli == "claude" and os.environ.get("ANTHROPIC_API_KEY", "").strip():
        base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
        if base_url:
            return Check(
                OK,
                "billing",
                f"ANTHROPIC_BASE_URL redirects requests to {base_url} - the key is not sent to "
                "Anthropic's API; billing (if any) depends on that endpoint",
            )
        return Check(
            WARN,
            "billing",
            "ANTHROPIC_API_KEY is set while CITADEL_LLM_CLI=claude - the claude CLI may bill the API "
            "per-token instead of your subscription; unset it to ingest on the subscription. See the "
            "README 'License & third-party tools' section.",
        )
    return Check(OK, "billing", "no API-key billing shadow")


def check_pdf_mode() -> Check:
    """WARN when ``CITADEL_PDF_MODE=images`` is set against a non-claude backend: a non-vision CLI
    cannot look at a PDF's figures, so it may silently ingest the text only."""
    cli = (config.LLM_CLI or "claude").strip().lower()
    if config.PDF_MODE == "images" and cli != "claude":
        return Check(
            WARN,
            "PDF mode",
            f"CITADEL_PDF_MODE=images but CITADEL_LLM_CLI={cli} - a non-vision backend may silently "
            "ingest PDF text only (figures/diagrams skipped)",
        )
    return Check(OK, "PDF mode", f"PDF mode {config.PDF_MODE}")


def check_pdf_text() -> Check:
    """Advisory line for the pypdf text-layer pre-pass (:mod:`citadel.pdftext`). pypdf is a bundled
    dependency, so this WARNs only in the unusual case that it was force-removed from the
    environment (``CITADEL_PDF_TEXT`` on/auto but pypdf unimportable) — every PDF then falls back
    to agent-native reading. Otherwise a plain state echo: on (with what it buys), or off."""
    from . import pdftext

    have = pdftext.available()
    mode = config.PDF_TEXT
    if mode == "off":
        return Check(OK, "PDF text", "text-layer pre-pass off (CITADEL_PDF_TEXT=0) - PDF locators stay agent-verified")
    if not have:
        return Check(
            WARN,
            "PDF text",
            "pypdf (a bundled dependency) is not importable - it was force-removed from this "
            "environment, so PDFs fall back to agent-native reading and their locators stay "
            "agent-verified; reinstall it (`pip install pypdf`, or reinstall cite-citadel) to make "
            "`lines A-B` PDF citations offline-verifiable",
        )
    return Check(OK, "PDF text", "text-layer pre-pass on (pypdf) - PDF `lines A-B` locators verify offline")


def check_http_serve() -> Check:
    """State echo for the opt-in HTTP transport (:mod:`citadel.httpserve`), WARNing on the two
    configurations that would surprise their operator: a token too short for ``serve --http`` to
    accept (which you would otherwise discover only when the server refuses to start), and a
    non-loopback bind, which puts an unencrypted MCP endpoint on the network. Nothing here is a
    FAIL — the transport is opt-in per invocation, and stdio serving is unaffected."""
    from . import httpserve

    if not config.HTTP_TOKEN:
        return Check(
            OK,
            "HTTP serve",
            "stdio only - `citadel serve --http` needs CITADEL_HTTP_TOKEN (it refuses to serve unauthenticated)",
        )
    # Rendered exactly as the server would serve it: the host in URL spelling (an IPv6 bind needs
    # brackets to be copy-pasteable) and the path through the same normalizer the app uses, so a
    # `CITADEL_HTTP_PATH=mcp` cannot be reported as `127.0.0.1:8765mcp`.
    where = f"{httpserve.format_host(config.HTTP_HOST)}:{config.HTTP_PORT}{httpserve.normalize_path(config.HTTP_PATH)}"
    mode = "read-only" if config.HTTP_READ_ONLY else "read+write (wiki_capture/wiki_ingest exposed)"
    if len(config.HTTP_TOKEN) < httpserve.MIN_TOKEN_CHARS:
        return Check(
            WARN,
            "HTTP serve",
            f"CITADEL_HTTP_TOKEN is only {len(config.HTTP_TOKEN)} characters - `citadel serve --http` "
            f"refuses anything under {httpserve.MIN_TOKEN_CHARS}; generate one with "
            'python -c "import secrets; print(secrets.token_urlsafe(32))"',
        )
    try:
        hosts = httpserve.check_hosts(config.HTTP_HOST)
    except httpserve.HttpServeError as e:
        # A wildcard bind with no allowlist: `serve --http` would refuse to start. Surfacing it here
        # is the whole point of the check — the alternative is discovering it at start-up.
        return Check(WARN, "HTTP serve", str(e))
    accepts = "any Host" if hosts is None else f"Host: {', '.join(hosts)}"
    if not httpserve.is_loopback(config.HTTP_HOST):
        return Check(
            WARN,
            "HTTP serve",
            f"CITADEL_HTTP_HOST={config.HTTP_HOST} binds beyond this machine over PLAIN HTTP ({where}, "
            f"{mode}, accepts {accepts}) - prefer a loopback bind behind a TLS-terminating tunnel "
            "(cloudflared, tailscale, ssh -R)",
        )
    return Check(
        OK, "HTTP serve", f"token set - `citadel serve --http` would listen on {where}, {mode}, accepts {accepts}"
    )


def check_resume() -> Check:
    """State echo for resume checkpoints (:mod:`citadel.resume`), naming any that are waiting.

    There is no dependency that can be missing here, so this never FAILs and never WARNs: it exists
    because a banked half-import is otherwise completely invisible — "raw/book.pdf (3/7 segments)"
    is what tells you the next run continues there instead of re-buying the first three passes.
    (A bad ``CITADEL_RESUME`` value is already reported by the config-fallback check.)"""
    from . import resume

    if not config.RESUME:
        return Check(OK, "resume", "resume checkpoints off (CITADEL_RESUME=0) - a chunked source restarts at segment 1")
    waiting = resume.pending()
    if not waiting:
        return Check(OK, "resume", "resume checkpoints on - none pending")
    from . import llm

    def describe(p) -> str:
        # The banked spend appears NOWHERE else: an unfinished source has no manifest entry, so
        # `citadel status` files it under Failed with no cost at all.
        cost = f", {llm.format_cost(p.cost_usd)} banked" if p.cost_usd is not None else ""
        return f"{p.key} ({p.completed}/{p.total} segments{cost})"

    listed = ", ".join(describe(p) for p in waiting[:5])
    more = f", +{len(waiting) - 5} more" if len(waiting) > 5 else ""
    return Check(OK, "resume", f"{len(waiting)} checkpoint(s) waiting to continue: {listed}{more}")


def check_audio_support() -> Check:
    """WARN when ``CITADEL_AUDIO_SUPPORT=1`` but the whisper-class CLI it needs is not on PATH —
    every audio/video source would fail (and retry) until it is installed. A plain status echo
    otherwise; WARN not FAIL, like the agent-CLI check (only ingest needs the binary)."""
    if not config.AUDIO_SUPPORT:
        return Check(OK, "audio", "audio support off (CITADEL_AUDIO_SUPPORT=0) - audio/video files log as unreadable")
    from . import transcribe

    try:
        path = transcribe.resolve_whisper()
    except RuntimeError:
        return Check(
            WARN,
            "audio",
            f"CITADEL_AUDIO_SUPPORT=1 but {config.WHISPER_CLI!r} is not on PATH - every audio/video "
            "source will fail until it is installed (or point CITADEL_WHISPER_CLI at the binary)",
        )
    return Check(OK, "audio", f"{config.WHISPER_CLI!r} -> {path}")


def check_wiki_git() -> Check:
    """Advisory line for the wiki-history layer (:mod:`citadel.wikigit`): which mode is active and
    whether an autocommit would actually run. WARN only when the user explicitly opted in
    (``CITADEL_WIKI_GIT=1``) but the layer cannot deliver (no git binary, or the wiki dir sits
    inside another git working tree); the default auto-without-repo state is a plain OK note."""
    mode = config.WIKI_GIT
    if mode == "off":
        return Check(OK, "wiki git", "off (CITADEL_WIKI_GIT=0) - wiki changes are not committed")
    if shutil.which("git") is None:
        detail = "git not found on PATH - wiki history skipped"
        return Check(WARN if mode == "init" else OK, "wiki git", detail)
    state = wikigit.repo_state(Path(config.wiki_dir()))
    remote = f" (push: {config.WIKI_GIT_REMOTE})" if config.WIKI_GIT_REMOTE else ""
    if state == wikigit.REPO:
        return Check(OK, "wiki git", f"wiki dir is a git repo - changes commit after each ingest/curate{remote}")
    if state == wikigit.NESTED:
        if mode == "init":
            return Check(
                WARN,
                "wiki git",
                "CITADEL_WIKI_GIT=1 but the wiki dir sits inside another git working tree - "
                "init refused; `git init` it yourself to overrule",
            )
        return Check(OK, "wiki git", "wiki dir sits inside another git working tree - auto-commit stays off")
    if mode == "init":
        return Check(OK, "wiki git", f"wiki dir will be `git init`ed on the next ingest/curate{remote}")
    return Check(
        OK, "wiki git", "wiki dir is not a git repo - `git init` it (or set CITADEL_WIKI_GIT=1) to keep wiki history"
    )


PYPI_JSON_URL = "https://pypi.org/pypi/cite-citadel/json"


def _as_int(part: str) -> int | None:
    """Parse one dotted version segment as an int, or None when it is non-numeric (e.g. ``0rc1``)."""
    try:
        return int(part)
    except ValueError:
        return None


def version_is_newer(candidate: str, baseline: str) -> bool:
    """True iff ``candidate`` is a strictly newer version than ``baseline`` under a naive dotted
    compare (no ``packaging`` dependency). Split both on ``.`` and compare segment by segment: numeric
    pairs compare as ints, and the first difference decides. A non-numeric segment (``0.3.0rc1``) that
    differs from its counterpart is treated as *unorderable* — the function conservatively returns
    False (never claims "newer" it cannot prove), so doctor won't nag on a version it can't rank."""
    for c, b in zip_longest(candidate.split("."), baseline.split("."), fillvalue="0"):
        if c == b:
            continue
        ci, bi = _as_int(c), _as_int(b)
        if ci is not None and bi is not None:
            if ci != bi:
                return ci > bi
            continue  # numerically equal (e.g. "01" vs "1") — keep comparing
        return False  # a differing non-numeric segment: not confidently newer
    return False


def detect_update_command(module_file: str | None = None, prefix: str | None = None) -> str:
    """Return the exact upgrade command for THIS install, from where the package lives on disk.

    Pure and unit-testable: ``module_file`` (defaults to this module's path) and ``prefix`` (defaults
    to ``sys.prefix``) are injectable. Detection order:

    - **dev checkout** — the package sits next to a repo checkout (a ``pyproject.toml`` one level up
      alongside a ``.git``/``corpora`` marker) -> ``git pull && uv sync``.
    - **uv tool** — ``prefix`` has consecutive ``uv``/``tools`` segments -> ``uv tool upgrade``.
    - **pipx** — a ``pipx`` segment in ``prefix`` -> ``pipx upgrade``.
    - **uvx ephemeral** — a uv cache env (``archive-v0`` / ``environments-*`` under ``uv``) -> a note
      that uvx always fetches the latest on the next run.
    - **generic** — otherwise ``pip install -U``.
    """
    if module_file is None:
        module_file = __file__
    if prefix is None:
        prefix = sys.prefix

    repo_root = Path(module_file).resolve().parents[1]
    if (repo_root / "pyproject.toml").is_file() and ((repo_root / ".git").exists() or (repo_root / "corpora").is_dir()):
        return "git pull && uv sync"

    parts = [p.lower() for p in Path(prefix).parts]
    for a, b in zip(parts, parts[1:], strict=False):
        if a == "uv" and b == "tools":
            return "uv tool upgrade cite-citadel"
    if "pipx" in parts:
        return "pipx upgrade cite-citadel"
    if "uv" in parts and any(p == "archive-v0" or p.startswith("environments-") or "cache" in p for p in parts):
        return "uvx cite-citadel (uvx always runs the latest on the next run)"
    return "pip install -U cite-citadel"


def _fetch_latest_pypi_version(timeout: float = 2.0) -> str | None:
    """Best-effort GET of PyPI's ``info.version`` for cite-citadel over stdlib urllib. Returns None on
    ANY failure (offline, DNS, timeout, HTTP error, malformed JSON) so the caller can degrade to an OK
    "check skipped" line — a missing network must never surface as a WARN/FAIL."""
    try:
        with urllib.request.urlopen(PYPI_JSON_URL, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        version = str(data["info"]["version"]).strip()
        return version or None
    except Exception:
        return None


def check_update(installed: str | None = None) -> Check:
    """WARN when a newer cite-citadel is on PyPI, naming the exact upgrade command for this install;
    OK when current, when PyPI is behind (a dev/pre-release build), or when PyPI is unreachable."""
    installed = installed or _INSTALLED_VERSION
    latest = _fetch_latest_pypi_version()
    if latest is None:
        return Check(OK, "update", "could not reach PyPI - update check skipped")
    if version_is_newer(latest, installed):
        return Check(WARN, "update", f"{installed} installed, {latest} on PyPI - run: {detect_update_command()}")
    return Check(OK, "update", f"{installed} is current")


def check_workspace_coherence() -> Check:
    """WARN when a page's ``## Sources`` citation resolves OUTSIDE every configured raw/docs root while
    still plainly naming a ``raw``/``docs`` tree — the silent misconfiguration where the wiki and its
    raw sources sit under different parents (e.g. ``CITADEL_WIKI_DIR`` points into a corpus while
    ``CITADEL_RAW_DIR`` is left at the default). Every such ``../../raw/x`` citation then fails
    :func:`grammar.is_source_citation`, so ``lint`` reports the sources broken and the viewer's source
    records get browser-unreachable identities — yet nothing else says the roots don't line up.

    Reuses the ONE shared citation walk (:func:`grammar.source_definitions` +
    :func:`grammar.def_link_target`, exactly as ``lint`` and the viewer do) and the grammar's own
    resolution (:func:`grammar.is_source_citation` / :func:`grammar.link_abs`) — never re-implemented.
    Read-only over :func:`store.load` (wikis are small; ``lint`` does the same) and O(pages). Skips
    when no workspace resolved or the wiki has no pages, so ``doctor`` keeps working everywhere; never
    FAILs (advisory) and, like the other checks, never raises."""
    if not config.WORKSPACE_FOUND:
        return Check(OK, "workspace coherence", "no workspace - source-citation coherence not checked")
    try:
        from . import grammar, store

        pages = store.load()
        if not pages:
            return Check(OK, "workspace coherence", "no pages yet - source-citation coherence not checked")
        # A resolved citation that names one of these path segments is plainly TRYING to be provenance:
        # the literal ``raw``/``docs`` conventions plus the configured DOCS_DIR basename (which may be
        # customized, e.g. ``documentation``).
        docs_seg = Path(config.DOCS_DIR).name.lower()
        provenance_segs = {"raw", "docs", docs_seg} - {""}
        total = incoherent = 0
        example: tuple[str, str, str] | None = None
        for page in pages:
            for _marker_id, rest in grammar.source_definitions(page.body):
                target = grammar.def_link_target(rest)
                if target is None or grammar.is_external(target):
                    continue
                if grammar.is_source_citation(page.rel_path, target):
                    total += 1  # resolves under a configured root — coherent
                    continue
                abs_path = grammar.link_abs(page.rel_path, target)  # the grammar's own resolution
                if abs_path is None:
                    continue
                if provenance_segs & {p.lower() for p in Path(abs_path).parts}:
                    total += 1
                    incoherent += 1
                    if example is None:
                        example = (page.rel_path, target, abs_path)
        if total == 0:
            return Check(OK, "workspace coherence", "no source citations to check")
        if incoherent == 0 or example is None:
            return Check(
                OK, "workspace coherence", f"all {total} source citations resolve under the configured raw/docs roots"
            )
        page_rel, target, abs_path = example
        suggested = config.wiki_dir().parent / "raw"
        return Check(
            WARN,
            "workspace coherence",
            f"{incoherent}/{total} source citation(s) resolve OUTSIDE the configured raw/docs roots "
            f"(e.g. {page_rel} cites '{target}' -> {abs_path}); set CITADEL_RAW_DIR (or CITADEL_DOCS_DIR "
            f"for docs/ citations) to the tree next to the wiki (e.g. {suggested}) or select the "
            f"workspace with CITADEL_WORKSPACE",
        )
    except Exception as exc:  # never raise: doctor must survive a half-built or unreadable wiki
        return Check(WARN, "workspace coherence", f"could not check workspace coherence: {exc}")


def run() -> DoctorReport:
    """Run every check in order and return the report. Read-only; the caller maps ``ok`` to the exit
    code (0 unless a FAIL)."""
    return DoctorReport(
        checks=[
            check_workspace(),
            check_rules(),
            check_config(),
            check_agent_cli(),
            check_ingest_model(),
            check_raw_roots(),
            check_wiki_placement(),
            check_child_paths(),
            check_manifest(),
            check_failures(),
            check_billing_shadow(),
            check_pdf_mode(),
            check_pdf_text(),
            check_audio_support(),
            check_resume(),
            check_http_serve(),
            check_wiki_git(),
            check_update(),
            check_workspace_coherence(),
        ]
    )
