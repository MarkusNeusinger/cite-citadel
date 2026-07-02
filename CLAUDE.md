# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cite-citadel` (CLI: `citadel`, PyPI package: `cite-citadel`) is an LLM-maintained, fully-cited
personal wiki in Google's [Open Knowledge Format](docs/okf-reference.md), with an MCP server so an
AI can search and read it. It implements Karpathy's LLM-Wiki pattern: drop arbitrary text-bearing
files into `raw/`, and one agentic CLI session per source folds each into a cross-linked OKF wiki
under `wiki/`. Pure Python 3.12, KISS. Runtime deps are only `mcp` and `pyyaml` — **there is no LLM
SDK and no API key**: ingest shells out to a coding-agent CLI you already have logged in
(`claude`/`copilot`/`gemini`).

## Commands

Setup: `uv sync` (creates `.venv`, installs deps + the `dev` group + the `citadel` script).

Use the **portable** invocation everywhere — it works identically on Linux/macOS/Windows and needs
no `.exe` (the `uv run citadel …` shorthand often breaks on Windows because AV quarantines uv's
generated `citadel.exe`):

```bash
uv run python -m citadel <subcommand>
```

Subcommands: `ingest [paths…]` (fold raw/ into the wiki; `--verbose`/`-v` streams the agent
session, `--log-dir DIR` writes a transcript per source, `--quiet` drops the progress spinner),
`serve` (MCP stdio server), `search <query> [--tag T] [--limit N]`, `tags [tag]`,
`lint [--stale-days N]`, `check [paths…]`, `view [--out PATH] [--no-open] [--obsidian]`.

Tests (pytest, all offline — no CLI/network is ever spawned):

```bash
uv run pytest -q                                    # whole suite (~370 tests, ~3s)
uv run pytest tests/test_ingest_core.py -q          # one file
uv run pytest tests/test_ingest_core.py::test_ingest_creates_pages   # one test
```

New tests build on the shared fixtures in `tests/conftest.py` — that layer is THE pattern:
`tmp_citadel` (a temp repo/wiki/raw/docs layout wired into `config.*`; `tmp_citadel_external`
for the out-of-repo mounted-drive layout, `make_citadel` for custom ones), `seed_page` (write a
canonical OKF page into the configured wiki), and `fake_agent` (a recording `FakeAgent`
installed over `llm.run_ingest_session` — pages to write, an error to raise, or a
`side_effect`). Don't re-create per-file `_wire*`/fake-session copies.

Lint and format with **ruff** (config in `pyproject.toml`; CI gates both, alongside pytest):

```bash
uv run ruff check .       # lint
uv run ruff format .      # auto-format (CI runs `ruff format --check .`)
```

Python 3.12+ is required. There is no separate build step — `pytest` and `ruff` are the checks.

## Architecture

**The `wiki/` directory _is_ the database.** No SQLite, no vector store, no second source of truth.
Pages are markdown files with YAML frontmatter; everything (search, index, graph, provenance) is
recomputed from them in memory.

**Three layers** (the README and `SCHEMA.md` are authoritative):
1. `raw/` — immutable sources the agent reads but never edits.
2. `wiki/` — the LLM-owned OKF bundle: pages routed *by kind* into `concepts/`, `objects/`,
   `systems/`, `persons/`, `organizations/`, `projects/`, `abbreviations/`, `misc/` (see
   `okf.folder_for_type`), cross-linked with relative markdown links, each fact carrying a footnote
   citation.
3. `SCHEMA.md` + `AGENT_INGEST.md` — the schema/rules layer. These are **read by the ingest agent
   at run time** (referenced by path in the prompt), so editing them changes how the wiki is built
   with **no code change**. Treat them as part of the program.

**Ingest is the heart of the system** (`ingest.py` → `llm.py`). The flow per source:
- `ingest.ingest()` partitions candidates into pending / already-ingested (sha match) / reorganized
  (moved-or-duplicate) / unreadable (binary) / deleted (vanished from disk, full runs only) /
  same-basename document duplicates (skipped in favor of one preferred format). A pending Office
  source is extracted to text first; a pending image is read visually; a pending source larger than
  `CITADEL_MAX_SOURCE_CHARS` is folded in over several passes.
- For each pending source it runs the agent against a **per-source staging copy** of the wiki (a
  sibling dir, never the live wiki), then snapshots before/after and **diffs by content hash** to
  learn what the agent created/updated/deleted — the agent has no return value, its file edits *are*
  the result.
- It then re-imposes invariants on every changed page (`validate.validate_page` + `store.write_page`
  to canonicalize YAML and stamp the timestamp), repairs renamed-page links, and **only on a fully
  clean session promotes staging onto the live wiki** with a non-destructive copy-over-then-prune.
  Any failure/timeout/Ctrl+C leaves the live wiki exactly as it was; the source is retried next run.
  This all-or-nothing + network-share-hardened machinery (`_robust_*`, `robust_mkdir`) is load-bearing
  — don't simplify it away.

**`llm.py` is the ONLY place that talks to an LLM**, and it does so by shelling out to a CLI in
agentic mode (`cwd` = repo root, autonomous file tools). The prompt is **paths-only** — it references
the source and rules by path, never embeds file content — which keeps argv tiny (the Windows
`WinError 206` fix). `kind` selects the propagation: `ingest` (new), `reconcile` (changed source —
update/remove stale facts, don't just append), `delete` (source removed — strip its provenance),
`repo`/`repo-reconcile` (a whole git repo folded as one digest), and `image`/`image-reconcile` (an
image source read visually). A large source is split into segments and folded in over several passes
(`segment=(part, total)` on `run_ingest_session`, telling later passes to MERGE into earlier ones).
`run_ingest_session` is the single seam tests monkeypatch.

**Two checking layers, one implementation** (`validate.py`):
- `citadel check` / `wiki_validate` — the **strict per-page gate** (required fields, honest/defined
  citations, relative non-broken links, no `[[wikilinks]]`). The ingest agent self-runs it; ingest
  re-runs it and fails the source on any error.
- `citadel lint` (`lint.py`) — a **pure offline health check** (contradictions, orphans, missing
  cites, broken links, stale, fabricated sources, undefined abbreviations). Only *structural*
  problems (missing type, broken links, bad sources, wikilinks) flip its non-zero exit; the rest are
  advisory. Both layers parse citations/links/fences through `grammar.py`, so lint and `citadel
  check` agree by construction: a citation into `raw/` or `docs/` is legal provenance (never a
  broken link), and a link inside a ``` code fence is literal text.

**Other modules:** `okf.py` is the OKF format core (parse/dump, type→folder routing, link math, and
the non-negotiable `safe_join` path guard — reuse it for any wiki-relative path). `grammar.py` is
the **single home of the markdown grammar** (link/footnote/fence/Sources-heading parsing and the
source-citation predicates) that `store`, `validate`, `lint`, and the viewer all parse through;
never re-define any of it locally. `store.py` is the
"database": `load()`, the single swappable `search()` seam, `rebuild_indexes()` (regenerates
`index.md`, per-folder `index.md`, and `sources/index.md` mechanically from frontmatter +
manifest), and the deterministic link-rewrite safety nets (`rewrite_links`, `rewrite_raw_references`,
`find_raw_references`, `find_broken_links`), all fence-aware via `grammar.py`. `manifest.py` tracks idempotency in
`wiki/.citadel_ingested.json` (per source: sha256 or git commit + importing model). `failures.py`
persists the sources that could NOT be ingested (`wiki/.citadel_failures.json`: unreadable /
errored / timed-out, with a reason), surfaced by `store` under a "Could not ingest" section of
`sources/index.md`. `repo.py` builds the digest for git-repo sources. `extract.py` pulls text from
Office files (stdlib-only): OOXML `.pptx`/`.docx`/`.xlsx` (+ macro-enabled) via zipfile+ElementTree,
and legacy OLE `.ppt`/`.doc`/`.xls` via the CFBF reader + best-effort text salvage in
`extract_ole.py` (imported lazily, only when a legacy OLE file is dispatched); its
`extract_media` also pulls embedded raster images out of OOXML files so the agent can view them.
`server.py` is the FastMCP stdio server (7 tools; only `wiki_ingest` mutates; tools never raise —
they return error strings). The `viewer/` subpackage builds the self-contained offline HTML viewer
(build logic in `__init__.py`; `template.html`/`app.css`/`app.js` are real package-data assets loaded
via `importlib.resources`). `config.py` resolves all paths/settings. `cli.py` mirrors the MCP tools as subcommands.

## Conventions specific to this codebase

- **`config.*` is read at call time** (`from . import config` then `config.WIKI_DIR`), never imported
  by value — so tests can monkeypatch the whole filesystem layout. Honor this when adding code.
- **Tests redirect everything to `tmp_path`** by monkeypatching `config.*` (including `REPO_ROOT`,
  which the agent's `cwd` reads) and replace `llm.run_ingest_session` with a fake that writes files
  into the temp wiki. No test spawns a real CLI. Follow that pattern; keep tests offline.
- **Never hand-edit generated files** — `index.md`, `log.md`, any `*/index.md`, `sources/index.md`,
  `.citadel_viewer.html`, and `.citadel_ingested.json` are regenerated. The ingest agent prompt and
  `store.delete_page` both refuse to touch them.
- **Provenance grammar is load-bearing:** raw facts cite `[^sN]` → a real `raw/` file; model-supplied
  facts use `[^llmN]` (source: `LLM`) and must never be disguised as raw citations. A `[^sN]` to a
  missing file fails lint/check.
- **`wiki/`, `raw/`, `docs/` can live outside the repo** (e.g. a mounted network drive) via
  `CITADEL_*_DIR`. Path handling distinguishes repo-relative keys from absolute out-of-repo keys
  (`config.rel_or_abs_posix` / `source_path_for_key`) — preserve that when touching path logic.
- **Cross-platform robustness is intentional**, not over-engineering: UTF-8 forcing, BOM stripping,
  ASCII-only progress output, read-only-bit clearing, and network-share retry loops all fix real
  Windows/SMB failures.
- Config knobs live in `.env` (auto-loaded, gitignored; see `.env.example`): `CITADEL_LLM_CLI`,
  `CITADEL_INGEST_MODEL`, `CITADEL_LLM_TIMEOUT`, `CITADEL_LLM_VERBOSE`, `CITADEL_LLM_LOG_DIR`,
  `CITADEL_REPO_SUPPORT`, `CITADEL_IMAGE_SUPPORT` (read images visually), `CITADEL_MAX_SOURCE_CHARS`
  (large-source chunking threshold), `CITADEL_DEDUP_BY_BASENAME` (skip same-basename document
  duplicates), `CITADEL_IGNORE_PATTERNS` (OS/junk-file globs skipped at discovery — `Thumbs.db`,
  `desktop.ini`, `~$` locks, …; a `+` prefix extends the built-in defaults), the `CITADEL_*_DIR`
  path overrides, and `*_CLI_PATH` binary overrides.
