"""Packaging metadata pins — the version is single-sourced in ``citadel/__init__.py``.

Offline stand-in for the CI wheel-smoke job: comparing ``importlib.metadata.version`` against
``citadel.__version__`` is impossible in the plain checkout (nothing is installed from the
built wheel here), so instead we pin that pyproject's dynamic-version config points at the
right file and that the version string in that file is the one the package exposes. Runtime
verification of the installed distribution stays in CI's wheel-smoke job.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import citadel


ROOT = Path(__file__).resolve().parents[1]


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


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
    """The duplicated [project.optional-dependencies].dev table is gone — [dependency-groups]
    (PEP 735, what `uv sync` installs by default) is the ONE place dev deps live."""
    data = _pyproject()
    assert "optional-dependencies" not in data["project"]
    assert any(dep.startswith("pytest") for dep in data["dependency-groups"]["dev"])
    assert any(dep.startswith("ruff") for dep in data["dependency-groups"]["dev"])


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
