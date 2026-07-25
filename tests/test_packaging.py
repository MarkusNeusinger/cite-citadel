"""Packaging metadata pins — the version is single-sourced in ``citadel/__init__.py``.

Offline stand-in for the CI wheel-smoke job: comparing ``importlib.metadata.version`` against
``citadel.__version__`` is impossible in the plain checkout (nothing is installed from the
built wheel here), so instead we pin that pyproject's dynamic-version config points at the
right file and that the version string in that file is the one the package exposes. Runtime
verification of the installed distribution stays in CI's wheel-smoke job.
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

import citadel


ROOT = Path(__file__).resolve().parents[1]

CLAUDE_MD = ROOT / "CLAUDE.md"
COPILOT_MD = ROOT / ".github" / "copilot-instructions.md"

# The one hand-written part of the generated Copilot file: its own title + provenance note. Everything
# below it is CLAUDE.md verbatim, so the two can never say different things about the same code.
COPILOT_HEADER = """# GitHub Copilot instructions — cite-citadel

Repository guidance for GitHub Copilot. **Generated from [`CLAUDE.md`](../CLAUDE.md)** — do not edit
this file by hand: change `CLAUDE.md` and regenerate with
`CITADEL_WRITE_COPILOT_DOC=1 uv run pytest tests/test_packaging.py -k copilot -q`. The drift guard in
`tests/test_packaging.py` fails whenever the two disagree.

"""


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _copilot_from_claude(claude_text: str) -> str:
    """Derive `.github/copilot-instructions.md` from CLAUDE.md: swap the title/intro for the
    generated-file header, and re-root repo-relative links one directory deeper (the Copilot file
    lives in `.github/`)."""
    first_section = re.search(r"^## ", claude_text, re.MULTILINE)
    assert first_section, "CLAUDE.md has no `## ` section heading to generate from"
    body = claude_text[first_section.start() :]
    body = re.sub(r"\]\((?!https?://|#|\.\./|/)([^)]+)\)", r"](../\1)", body)
    return COPILOT_HEADER + body


def test_version_is_dynamic_and_hatch_reads_it_from_the_package_init():
    data = _pyproject()
    assert "version" not in data["project"], "version must not be duplicated statically in [project]"
    assert "version" in data["project"]["dynamic"]
    assert data["tool"]["hatch"]["version"]["path"] == "citadel/__init__.py"


def test_dunder_version_in_the_configured_file_matches_the_package():
    path = ROOT / _pyproject()["tool"]["hatch"]["version"]["path"]
    match = re.search(r'^__version__[^=]*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"no __version__ assignment found in {path}"
    assert match.group(1) == citadel.__version__


def test_dev_deps_live_only_in_the_pep735_dependency_group():
    """No duplicated [project.optional-dependencies].dev table — [dependency-groups] (PEP 735,
    what `uv sync` installs by default) is the ONE place dev deps live. The only extra is the
    no-op `pdf` compat alias (pypdf ships as a hard runtime dep now)."""
    data = _pyproject()
    extras = data["project"].get("optional-dependencies", {})
    assert "dev" not in extras
    assert set(extras) <= {"pdf"}, f"unexpected extras: {sorted(extras)}"
    assert any(dep.startswith("pypdf") for dep in extras.get("pdf", []))
    dev = data["dependency-groups"]["dev"]
    assert any(dep.startswith("pytest") for dep in dev)
    assert any(dep.startswith("ruff") for dep in dev)
    # pypdf is a RUNTIME dependency (PDFs are a common raw/ class — offline-verifiable locators
    # out of the box), not a dev-group or optional-only one.
    assert any(dep.startswith("pypdf") for dep in data["project"]["dependencies"])


def test_pyproject_metadata_is_free_of_vendor_marks():
    """Packaging guard: the distributed identity — name, description, keywords — must name no
    provider. The coding-agent CLI is user-supplied; naming it in the package identity would read as
    endorsement, and would let a later rename smuggle a trademark onto the PyPI page. (The README /
    rules are free to name the CLIs to identify them — this pins ONLY pyproject metadata.)"""
    project = _pyproject()["project"]
    marks = re.compile(r"\b(claude|copilot|gemini|anthropic|microsoft|google)\b", re.IGNORECASE)
    fields = {"name": project["name"], "description": project["description"]}
    fields.update({f"keywords[{i}]": kw for i, kw in enumerate(project["keywords"])})
    offenders = {field: value for field, value in fields.items() if marks.search(value)}
    assert not offenders, f"vendor mark in pyproject metadata (keep it vendor-neutral): {offenders}"


def test_sdist_excludes_dev_and_corpora_trees():
    """The sdist must not carry the test corpora, CI/agent config, or dev-only files. The wheel target ships only the `citadel` package, so it is unaffected either way."""
    exclude = _pyproject()["tool"]["hatch"]["build"]["targets"]["sdist"]["exclude"]
    for expected in ("/corpora", "/.claude", "/.github", "/uv.lock", "/CLAUDE.md"):
        assert expected in exclude, f"{expected} must be excluded from the sdist"


def test_configuration_doc_covers_every_env_knob():
    """Mechanical drift guard replacing the prose-only 'keep this page in sync' promise: the
    `CITADEL_*` knobs the packaged env.example ASSIGNS and the ones docs/configuration.md documents
    must be the SAME set. A knob added to one but not the other fails HERE. Liberal in extraction
    (any assignment line, commented defaults included; any `CITADEL_*` mention in the doc), strict in
    comparison (set equality, modulo an explicit allowlist)."""
    env_text = (ROOT / "citadel" / "templates" / "env.example").read_text(encoding="utf-8")
    # Env knobs = lines that ASSIGN a CITADEL_* var (commented-out defaults included); tolerant of
    # leading indent / `#` / spacing around `=` so reformatting the template never breaks the guard.
    env_knobs = set(re.findall(r"^\s*#?\s*(CITADEL_[A-Z_]+)\s*=", env_text, re.MULTILINE))

    doc_text = (ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")
    # Doc knobs = every CITADEL_* mention (inline code, heading, or prose) — deliberately liberal.
    doc_knobs = set(re.findall(r"CITADEL_[A-Z_]+", doc_text))

    # CITADEL_WORKSPACE is DOC-ONLY on purpose: it points a launcher (e.g. an MCP host) AT a
    # workspace, so it belongs in that process's env, never inside a workspace's own .env template.
    DOC_ONLY = {"CITADEL_WORKSPACE"}

    assert env_knobs == doc_knobs - DOC_ONLY, {
        "documented but missing from env.example": sorted(doc_knobs - DOC_ONLY - env_knobs),
        "in env.example but undocumented": sorted(env_knobs - doc_knobs),
    }


def test_copilot_instructions_mirror_claude_md():
    """Mechanical drift guard replacing the prose-only 'keep the two in sync' promise: the Copilot
    instruction file is a pure derivation of CLAUDE.md (header swap + relative-link re-rooting), so a
    feature documented in one is documented in both. Drift was real — the file shipped 105 lines
    behind CLAUDE.md, still claiming 12 MCP tools and knowing nothing of `refresh`, `capture`,
    `--jobs`, or `serve --http`. Set `CITADEL_WRITE_COPILOT_DOC=1` to regenerate instead of compare."""
    expected = _copilot_from_claude(CLAUDE_MD.read_text(encoding="utf-8"))
    if os.environ.get("CITADEL_WRITE_COPILOT_DOC") == "1":
        COPILOT_MD.write_text(expected, encoding="utf-8")
    actual = COPILOT_MD.read_text(encoding="utf-8")
    assert actual == expected, (
        "`.github/copilot-instructions.md` has drifted from CLAUDE.md — regenerate it with "
        "`CITADEL_WRITE_COPILOT_DOC=1 uv run pytest tests/test_packaging.py -k copilot -q` "
        "(edit CLAUDE.md, never the generated file)."
    )


def test_readme_links_are_absolute_for_pypi():
    """README.md ships as the PyPI long-description, where relative repo links 404 (owner report
    on the v0.1.0 release page). Every markdown link outside fenced code blocks must be absolute
    (or an in-page anchor); fenced blocks may show relative citations as literal examples."""
    import re

    fence = False
    offenders = []
    for n, line in enumerate((ROOT / "README.md").read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
            continue
        if fence:
            continue
        for target in re.findall(r"\]\(([^)]+)\)", line):
            if not (target.startswith(("http://", "https://", "#"))):
                offenders.append(f"README.md:{n} -> {target}")
    assert not offenders, f"relative links break on PyPI: {offenders}"
