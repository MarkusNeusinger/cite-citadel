"""citadel — an LLM-maintained personal wiki in Google OKF, with an MCP search server."""

# The ONE source of the version: pyproject.toml reads it via hatch's dynamic version
# ([tool.hatch.version] path = "citadel/__init__.py"), and `citadel --version` prints it.
# No `: str` annotation — hatchling's default version regex would not match it.
__version__ = "0.2.0"
