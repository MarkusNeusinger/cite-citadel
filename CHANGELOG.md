# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **`citadel lint` — fewer advisory false positives on real ingests.** A `## See also` navigation
  list is no longer counted as a "Missing citations" paragraph (a link title such as
  `Immersion vs. Percolation Brewing` had faked a second sentence — 18 false hits on a fresh
  beverages build). The undefined-abbreviation nudge now skips fiscal-period labels (`Q1`..`Q4`,
  `H1`/`H2`) and roman numerals used in an ordinal context (`Chapter IV`), while still surfacing a
  genuine abbreviation that merely parses as a numeral (`DC`). Advisory-only; no structural gate
  changes. Surfaced by the verify-corpus Mode-A harvest.

### Added

- **`wiki_define` / `citadel define` — glossary lookup.** An eleventh read-only MCP tool (+ its CLI
  twin) answers a short "what does X stand for / mean?" as a *lookup* rather than full-text
  retrieval: it surfaces a `type: Abbreviation` glossary hit (matching the short form, expansion,
  title, or an alias, rendered `SHORT — Expansion`) first, then an exact-title/alias page of any
  type, then falls back to the closest `wiki_search` hits when nothing matches exactly. Backed by the
  new `store.define_text`. Read-only, no new dependency.

### Changed

- **Light stemming in search.** `store_core._tokenize` now applies a small, deterministic,
  dependency-free suffix strip (`brewing`/`brew`, `founded`/`founding`, `magnets`/`magnet` collapse to
  a shared token) so paraphrased query forms match. It is applied symmetrically to both the query and
  the page text, so the field-weight / IDF scoring contract is unchanged; the `test_search.py`
  characterization tests still pass unmodified.
- **Leaner, more predictable ingest sessions.** The run instruction and `core.md` now tell the agent
  that the raw source tree is a **read-only input** (read it for content and citations, never write,
  create, move, or delete under it) and that reading/searching go through the agent's **built-in
  file tools** rather than the shell, which stays reserved for the `citadel check` self-check and
  page deletes/renames. The self-check now runs **once** and re-runs only to confirm fixes when it
  reported errors, instead of being invoked repeatedly. Together these cut the number of shell
  subprocesses a session spawns and keep every write inside the wiki — no functional change to the
  wiki that gets produced. (Editing any `rules/` file bumps `rules_version`, so `citadel status`
  shows previously ingested sources as `(stale)` — expected, cosmetic.)

## [0.3.0] - 2026-07-06

### Added

- **`wiki_neighbors` / `citadel neighbors` — walk a page's link graph.** A tenth read-only MCP tool
  (+ its CLI twin) prints a page's **links out** (its wiki cross-links, resolved to rel_paths, each
  flagged `(missing)` if the target page is gone), **linked from** (the backlink graph), and **cites
  sources** (the raw/`docs/` source keys it cites, with per-source counts — the keys to hand to
  `wiki_raw`), so an AI can traverse the graph without doing relative-path math itself. Backed by
  `store.neighbors_text`.
- **`wiki_raw` / `citadel raw` — read the raw source behind a citation.** A new read-only MCP tool
  (the ninth) and its CLI twin resolve a `[^sN]` citation's provenance for spot-checking: given the
  cited source key (e.g. `raw/notes.md`) and, optionally, the citation's locator tail (`lines 76-83`,
  `§ Method`, or a combined `§ Method, lines 5-9`), it returns the cited source's text — or exactly
  the slice the locator names — line-numbered and size-capped. A provenance gate makes only sources
  the wiki actually cites (the ingest manifest, or a `docs/` file) readable, so it verifies the
  synthesized wiki without becoming a bulk re-retrieval path; PDFs/images/undecodable files return an
  honest "read it directly" message. Backed by the new `citadel/rawsource.py`.
- **Two more graded test corpora** under `corpora/`, bringing the total to five: **pemberley** (the
  whole of *Pride and Prejudice* as one ~730k-char source — large-source multi-segment chunking,
  relationship extraction, in-novel misinformation, narrative supersession) and
  **injection-resistance** (three mundane documents with adversarial instructions embedded, graded
  that the ingest agent treats them as content and never executes them). Each ships a hidden
  `ground-truth.md` answer key and is wired into the parameterized `verify-corpus` skill.
- **A committed, graded showcase wiki for every corpus** (not just beverages): each
  `corpora/<name>/` is now its own self-contained workspace with a nested `citadel.toml` marker and
  a lint-clean `wiki/`. CI lints all five.
- **GitHub Pages gallery.** `.github/workflows/pages.yml` builds one offline single-file viewer per
  corpus into `site/<name>/` and publishes a lean landing page (`.github/pages-index.html`) — a
  disclaimer banner plus one card per corpus — that links each demo.
- **Community health files** for the public repo: `.github/dependabot.yml` (weekly `uv` + GitHub
  Actions updates) and `.github/ISSUE_TEMPLATE/` (bug report, feature request, and a config that
  routes questions to Discussions and security reports to the policy).

### Changed

- **Search now weights rare terms (IDF).** `store_core.search` scales each token's field weight by its
  inverse document frequency, so a rare, discriminating query term (an acronym, a proper noun)
  outranks one common to the whole wiki — a "TDS" or "espresso" lookup surfaces its own page instead
  of being buried under generic topic pages (measured on the showcase corpora: rank 4→2 and 3→1, no
  regressions). Pure-Python, no new dependency, recomputed per search; the `search()` seam signature
  and MCP surface are unchanged. A golden-rank test locks the behavior against a regression to plain
  overlap.
- **`verify-corpus` now grades retrieval-first.** Phase 2 checks each corpus guarantee the way a user
  consumes the wiki — driving `citadel search`/`read`/`index`/`tags` to prove the answer is both
  correct+cited and *findable* (not merely present on disk), and drops to a file-level grep only to
  classify a miss as a wiki-*creation* defect or a *retrieval* defect. Each corpus's hidden
  `ground-truth.md` gains a frozen, answer-blind `## Retrieval battery`, and the grade's misses route
  into two optimization lanes (the ingest/rules generator and the search tools). Test-only — no wiki
  or corpus content changed.
- **Renamed three corpora** to their in-world names — the fictional-republic corpus is now
  **`kelvarra`**, the three-year-programme corpus is now **`leuchtfeuer`**, and the *Pride and
  Prejudice* corpus is now **`pemberley`** (directories, hidden answer-key directories, and every
  reference across docs, workflows, and the `verify-corpus` skill).
- **`leuchtfeuer` layout inverted.** Its committed `raw/` now holds the **final** post-wave-3 file
  set (11 files, cited by the committed wiki); the wave history moved under `stages/` —
  `stages/initial/` (the 2024 wave-1 originals, charter Rev A + the later-deleted memo), plus the
  existing `stages/wave2/`/`stages/wave3/` overlays. The sandbox wave protocol now seeds the raw
  from `stages/initial/`.

### Fixed

- **Locator lint no longer false-flags the combined `§ Heading, line N` citation form.** The Z6
  locator check treated the whole `Heading, line N` as a heading name and failed to find it —
  producing false-positive advisories (13 on the beverages showcase alone) and phantom `locator`
  findings in `citadel curate` (the check is shared). The locator parser is now a single
  `grammar.parse_locator` (moved to the citation-grammar home, next to `source_definitions`), which
  splits the combined form and verifies **both** the heading and the line range; `lint._locator_problem`
  is a thin consumer. All five showcase corpora now lint with zero locator advisories.

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
- **Three graded test corpora** under `corpora/` (beverages, kelvarra, leuchtfeuer)
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

[Unreleased]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MarkusNeusinger/cite-citadel/releases/tag/v0.1.0
