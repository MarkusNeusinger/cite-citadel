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
- **raw roots** — is every raw root ingest actually walks (``CITADEL_RAW_DIRS``) reachable (a dir
  on disk)? Also WARNs when the primary ``raw/`` was configured OUT of the walk list while holding
  files — those would silently never be ingested.
- **manifest** — does ``wiki/.citadel_ingested.json`` parse, with its format version, source count,
  and a workspace stamp matching the current root?
- **failures** — a summary of the sources the failures catalog says could not be ingested.
- **billing** — the API-key billing-shadow heads-up: ``ANTHROPIC_API_KEY`` set while
  ``CITADEL_LLM_CLI=claude`` may bill the API per-token instead of the subscription (cross-referenced
  to the README "License & third-party tools" section, where the subscription-vs-API story is told
  once).
- **PDF mode** — ``CITADEL_PDF_MODE=images`` against a non-``claude`` backend may silently ingest a
  PDF's text only, because a non-vision CLI cannot look at the figures.
- **PDF text layer** — is the optional pypdf pre-pass active (``CITADEL_PDF_TEXT``)? WARN when
  forced on (``=1``) without pypdf installed; an advisory OK naming the install command when it is
  merely unavailable — without it, PDF locators stay agent-verified instead of offline-checkable.
- **audio** — ``CITADEL_AUDIO_SUPPORT=1`` needs a whisper-class CLI on PATH
  (``CITADEL_WHISPER_CLI``); WARN when the configured binary is missing — every audio/video source
  would fail until it is installed. A plain OK note while the knob is off.
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
    ingest, so doctor stays useful before it is installed; else OK with the resolved binary path."""
    from . import llm

    cli = config.LLM_CLI or "claude"
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


def check_manifest() -> Check:
    """OK when there is no manifest yet (nothing ingested) or it parses with a matching workspace
    stamp; WARN when it is unparseable JSON (treated as empty) or its stamp names another workspace
    (keys may not line up). Reports the format version and source count.

    Reads the manifest through :func:`manifest.inspect` — ONE parse that also stashes the stamp for
    the mismatch probe below, so doctor never re-reads the file or reaches into manifest internals."""
    path = config.MANIFEST_PATH
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
    state = wikigit.repo_state(Path(config.WIKI_DIR))
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
        suggested = config.WIKI_DIR.parent / "raw"
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
            check_raw_roots(),
            check_manifest(),
            check_failures(),
            check_billing_shadow(),
            check_pdf_mode(),
            check_pdf_text(),
            check_audio_support(),
            check_wiki_git(),
            check_update(),
            check_workspace_coherence(),
        ]
    )
