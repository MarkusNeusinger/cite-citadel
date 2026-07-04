# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Two more graded test corpora** under `corpora/`, bringing the total to five: **literature** (the
  whole of *Pride and Prejudice* as one ~730k-char source — large-source multi-segment chunking,
  relationship extraction, in-novel misinformation, narrative supersession) and
  **injection-resistance** (three mundane documents with adversarial instructions embedded, graded
  that the ingest agent treats them as content and never executes them). Each ships a hidden
  `ground-truth.md` answer key and is wired into the parameterized `verify-corpus` skill.
- **Community health files** for the public repo: `.github/dependabot.yml` (weekly `uv` + GitHub
  Actions updates) and `.github/ISSUE_TEMPLATE/` (bug report, feature request, and a config that
  routes questions to Discussions and security reports to the policy).

## [0.2.0] - 2026-07-03

### Added

- **`citadel ingest --force`** — deliberately re-read an already-ingested source and reconcile the
  wiki against it (never a plain re-ingest); repos force a full re-digest via `repo-reconcile`;
  clears a persisted unreadable/errored failure record.
- **Multi-root raw** via `CITADEL_RAW_DIRS`, and **`citadel ingest --full-rescan`** to distrust the
  scan cache and rehash everything.
- **`citadel curate`** — a second lifecycle that re-verifies facts, splits overlong pages, and
  re-sorts information without re-ingesting from zero. Flags: `--dry-run`, `--limit`, `--stale-rules`,
  `--diff`; model knob `CITADEL_CURATE_MODEL`.
- **`citadel status`** — per-source state (ingested with model + rules version, failed with reason +
  attempts, skipped-duplicate, ignored, pending) from the manifest and failures catalog, no re-hash.
- **Full CLI ↔ MCP parity** — new `citadel read` / `citadel index` / `citadel sources` subcommands,
  a new `wiki_lint` MCP tool, and behavior annotations (`readOnlyHint` etc.) on all eight MCP tools,
  so an AI without MCP access can drive everything through the shell.
- **`citadel doctor`** — preflight check: workspace found, rules resolve, agent CLI on PATH, raw roots
  reachable, manifest parses, and an API-key billing-shadow warning.
- **OSS project docs** — `NOTICE.md` (affiliation & trademark disclaimer, dependency-license record),
  `CONTRIBUTING.md`, this `CHANGELOG.md`, `SECURITY.md`, `docs/configuration.md`, README badges, and a
  "License & third-party tools" section (bring-your-own-CLI terms + output ownership).
- **`open-pr` skill** and a mandatory self-verification routing section in `CLAUDE.md`.
- **Three graded test corpora** under `corpora/` (beverages, counterfactual-atlas, project-history)
  with hidden answer keys, driven by the parameterized `verify-corpus` skill.

### Changed

- **Incremental discovery** — the manifest doubles as the scan cache, so an unchanged corpus now
  does **zero content reads**.
- **Deletion is safe by construction** — an unreachable share or a walk error can never read as mass
  deletion, and out-of-root keys are never swept.
- **Segmented sources promote once** — a large source's passes fold into one staging copy and promote
  together, so the live wiki never holds a half-folded source.
- **Store hygiene** — index rebuilds are single-pass (much faster) and `write_page` gained a
  reserved-name guard.
- Packaging: the sdist now **excludes** the test corpora, CI/agent config, and dev-only files (the
  wheel is unchanged); the pyproject `description` is vendor-neutral.

### Fixed

- Failed repo and delete sessions now reach the failures catalog and surface under "Could not
  ingest".
- `lint` and `check` agree on citation/link grammar by construction (shared `grammar.py`).

## [0.1.0] — 2026-07-02

First public, pip-installable release (`pip install cite-citadel`), and the PyPI name reservation.

### Added

- **Workspace model** — `citadel init` scaffolds a workspace (`citadel.toml` marker, `.env`, `raw/`,
  `wiki/`, `rules/`); discovery walks up for the marker or resolves `CITADEL_*_DIR` env vars, and
  fails loud rather than inventing a phantom workspace. `citadel --version`.
- **Rules tree as package data** — `citadel/rules/` (`schema.md`, `core.md`, `tasks/`, `formats/`,
  `genres/`) ships inside the wheel and is read by the ingest agent at run time; the prompt builder
  shrank to a paths-only frame. Editing the rules changes how the wiki is built with no code change.
- **Citation locators** — footnote definitions may carry `p. 12` / `pp. 3-5`, `line 40` /
  `lines 40-52`, or a `§ Heading` anchor; `lint` verifies line/heading locators against raw files.
- **`CITADEL_WIKI_LANG`** (default `en`) — the wiki is written in one target language regardless of
  the sources' languages, with verbatim quotes and proper names left untranslated.
- Release pipeline (v* tags → PyPI Trusted Publishing), wheel-smoke CI, Windows + macOS runners,
  Python 3.12–3.14, PEP 639 license metadata, dynamic single-sourced version.

### Changed

- Shared citation/link/fence parsing consolidated into `grammar.py`; viewer moved to a subpackage
  with a golden bundle test; Office/OLE extraction isolated.

[Unreleased]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MarkusNeusinger/cite-citadel/releases/tag/v0.1.0
