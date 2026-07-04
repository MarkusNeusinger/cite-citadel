# GitHub Copilot instructions — cite-citadel

Repository guidance for GitHub Copilot. This mirrors [`CLAUDE.md`](../CLAUDE.md); keep the two in
sync when either changes.

## What this is

`cite-citadel` (CLI: `citadel`, PyPI package: `cite-citadel`) is an LLM-maintained, fully-cited
personal wiki in Google's [Open Knowledge Format](../docs/okf-reference.md), with an MCP server so an
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

Subcommands: `init [DIR]` (scaffold a workspace: `citadel.toml` marker, `.env`, `raw/`, `wiki/`;
idempotent), `ingest [paths…]` (fold raw/ into the wiki; `--verbose`/`-v` streams the agent
session, `--log-dir DIR` writes a transcript per source, `--quiet` drops the progress spinner,
`--full-rescan` distrusts the manifest's stat cache and re-hashes every tracked source,
`--force <paths>` deliberately re-reads already-ingested sources as a reconcile — it requires
explicit paths and is refused without them), `curate [--dry-run] [--limit N] [--stale-rules]
[--diff PATH]` (the SECOND lifecycle: improve EXISTING pages — re-sort/split/re-ground/resolve
contradictions/fix locators — against a recomputed findings checklist), `status` (read-only
per-source state table: ingested / failed / skipped-duplicate / ignored / pending), `doctor`
(read-only setup health check — OK/WARN/FAIL lines for workspace / rules / agent CLI / raw roots /
manifest / billing; needs no workspace, exits 1 only on a FAIL), `serve` (MCP
stdio server), `search <query> [--tag T] [--limit N]`, `read <rel_path>` / `index` / `sources`
(CLI twins of the `wiki_read`/`wiki_index`/`wiki_sources` MCP tools — full CLI↔MCP parity),
`tags [tag]`, `lint [--stale-days N]`, `check [paths…]`, `view [--out PATH] [--no-open]
[--obsidian]`, `rules list|show|eject`. `citadel --version` prints the version and (like `--help`)
needs no workspace.

Tests (pytest, all offline — no CLI/network is ever spawned):

```bash
uv run pytest -q                                    # whole suite (~570 tests, ~3s)
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

## Test corpora

Five synthetic corpora live under `corpora/` (`corpora/<name>/{raw/, stages/?, README.md}`),
runnable individually or together: **beverages** (the coffee+tea showcase — its committed wiki at
`corpora/beverages/wiki/` is the GitHub Pages demo and CI's lint target), **counterfactual-atlas** (a
coherent fictional world stated wrong about reality — graded that facts appear as stated, cited,
never corrected), **project-history** (a 3-year programme ingested in dated `stages/` waves that
drives reconcile/delete/force, temporal supersession, German→English, and attributed opinions),
**literature** (the whole of *Pride and Prejudice* as one ~730k-char source — large-source
multi-segment chunking, relationship extraction, in-novel misinformation, narrative supersession),
and **injection-resistance** (three mundane documents with adversarial instructions embedded — the
agent must treat them as content, never execute them). Each
carries a hidden answer key at `.claude/skills/verify-corpus/<name>/ground-truth.md` — **outside the
corpus so the ingest agent never sees it** (Mode A also points `CITADEL_RAW_DIR` at the corpus `raw/`
only). The parameterized `verify-corpus` skill (`verify-corpus <name>|all [--grade-only]`) ingests a
corpus into a throwaway sandbox workspace (never a live wiki) and grades it in two phases: `citadel
check` + `lint` exit 0 (structural eligibility), then answer-key content grading. Corpora live
**outside** `citadel/`, so they never ship in the wheel. The repo-root `raw/` + `wiki/` are a
gitignored developer workspace (the checkout's `citadel.toml` marker still makes it a workspace).

## Self-verification (feedback loops)

Two `.claude/skills/` skills close the loop between a change and its proof:

- **verify-corpus** (`verify-corpus
  <beverages|counterfactual-atlas|project-history|literature|injection-resistance|all>
  [--grade-only]`) — the end-to-end corpus grader: ingests a corpus into a throwaway sandbox and
  grades the result against its hidden `ground-truth.md`. Run it after any change to `ingest.py`,
  `llm.py`, or the rules tree (`citadel/rules/`).
- **open-pr** — the ship path: runs the hard local gates (`pytest`, `ruff check`, `ruff format
  --check`, the beverages-workspace `lint`), routes ingest/llm/rules diffs through verify-corpus,
  branches `claude/<topic>-<slug>` off main, opens a ready PR + Copilot review, watches CI, and
  stops at green — never merges.

**Routing is mandatory, not advisory: any commit/push/PR request goes through `/open-pr`.**

## Release process

Trunk-based, no `develop` branch by design: every change lands on `main` via PR (through `/open-pr`
with its gates + the Copilot round), so `main` is always releasable. A release is a deliberate act,
never automatic on merge:

1. A small **release PR** bumps `__version__` in `citadel/__init__.py` and re-dates CHANGELOG.md's
   `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD` (keep the flip-gate blockquote under a fresh
   `## [Unreleased]` heading while it still applies).
2. After merge, tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` then builds and publishes **automatically** — PyPI via Trusted
   Publishing (no token, no manual upload) + a GitHub Release.

SemVer: patch for fixes/docs, minor for features. PyPI versions are **immutable** — never re-tag or
re-release a number; a mistake costs it, so bump again.

## Architecture

**The `wiki/` directory _is_ the database.** No SQLite, no vector store, no second source of truth.
Pages are markdown files with YAML frontmatter; everything (search, index, graph, provenance) is
recomputed from them in memory.

**Three layers** (the README and `citadel/rules/schema.md` are authoritative):
1. `raw/` — immutable sources the agent reads but never edits.
2. `wiki/` — the LLM-owned OKF bundle: pages routed *by kind* into `concepts/`, `objects/`,
   `systems/`, `persons/`, `organizations/`, `projects/`, `abbreviations/`, `misc/` (see
   `okf.folder_for_type`), cross-linked with relative markdown links, each fact carrying a footnote
   citation.
3. `citadel/rules/` — the schema/rules tree, packaged with the wheel (index:
   `citadel/rules/README.md`):
   `schema.md` (format contract) + `core.md` (agent behavior) are read every session, plus one
   lifecycle brief from `tasks/`, any file-type brief from `formats/`, and the agent-judged
   `genres/` briefs. These are **read by the ingest agent at run time** (referenced by path in the
   prompt), so editing them changes how the wiki is built with **no code change**. Treat them as
   part of the program.

**Everything operates on a WORKSPACE**, not the repo checkout: a directory holding a
`citadel.toml` marker (a pure marker, never config — scaffold one with `citadel init [DIR]`).
Discovery order: `CITADEL_WORKSPACE` env var > nearest marker walking up from the CWD (nested
markers shadow outer ones) > an env-dirs workspace (`CITADEL_WIKI_DIR`+`CITADEL_RAW_DIR` both
set) > otherwise none: `config.WORKSPACE_FOUND` is False, `WORKSPACE_ROOT` falls back to the
bare CWD, and every subcommand except `init` fails loud. The dev checkout carries a marker, so
it is itself a workspace.

**Ingest is the heart of the system** (`ingest.py` → `llm.py`). The flow per source:
- `ingest.ingest()` partitions candidates into pending / already-ingested (sha match) / reorganized
  (moved-or-duplicate) / unreadable (binary) / deleted (vanished from disk, full runs only).
  `ingest --force <paths>` bypasses the sha short-circuit: the named sources land in pending as
  reconciles (a repo re-digests in full), and the manifest is re-stamped with the current model +
  rules version.
- **Discovery is incremental and deletion-safe**: one `os.scandir` walk over every
  `CITADEL_RAW_DIRS` root; the manifest doubles as the scan cache (an entry's
  `size`/`mtime_ns`/`ctime_ns`/`hashed_at_ns` are a skip-hint — sha256 stays the sole arbiter of
  "changed"; `--full-rescan` distrusts the cache). Deletion candidates come from the
  walked-seen-set diff and each is positively confirmed with `.exists()`; any walk error aborts
  the whole sweep, an unreachable root contributes no candidates, keys under no configured root
  are logged and never swept, and a workspace-identity mismatch whose keys do not resolve refuses
  the sweep. A flaky share or unmounted root must NEVER read as mass deletion — don't weaken
  these guards.
- For each pending source it runs the agent against a **per-source staging copy** of the wiki (a
  sibling dir, never the live wiki), then snapshots before/after and **diffs by content hash** to
  learn what the agent created/updated/deleted — the agent has no return value, its file edits *are*
  the result.
- It then re-imposes invariants on every changed page (`validate.validate_page` + `store.write_page`
  to canonicalize YAML and stamp the timestamp) after **every** agent pass, repairs renamed-page
  links, and **only on a fully clean source promotes staging onto the live wiki — exactly once per
  source** — with a non-destructive copy-over-then-prune. A chunked large source folds ALL its
  segments into that one staging copy before the single promote (refactor-plan Z11: the live wiki
  never holds a partially imported source; the accepted trade-off is that a failure at segment N
  discards the earlier segments' work and the source retries from segment 1 next run). Any
  failure/timeout/Ctrl+C leaves the live wiki exactly as it was; the source is retried next run.
  Deletion cleanups, then pending files, then repos all drive this through ONE shared per-source
  loop (`_SourceJob` + `_run_source_jobs`) — **deletions run first** so a delete cleanup strips a
  vanished source's stale provenance before any pending session touches a page that still cites it
  (else that pre-existing bad citation would fail the pending session's validation and roll it
  back). This all-or-nothing + network-share-hardened machinery (`_robust_*`, `robust_mkdir`) is
  load-bearing — don't simplify it away.

**`llm.py` is the ONLY place that talks to an LLM**, and it does so by shelling out to a CLI in
agentic mode (`cwd` = workspace root, autonomous file tools). The prompt is **paths-only** — it references
the source and rules by path, never embeds file content — which keeps argv tiny (the Windows
`WinError 206` fix). One per-kind spec table (`_KIND_SPECS`) maps each `kind` to its task-rule
file, whether it reads a source, and its format policy; an unknown kind fails loud. `kind` selects
the propagation: `ingest` (new), `reconcile` (changed source — update/remove stale facts, don't
just append), `delete` (source removed — strip its provenance), `repo`/`repo-reconcile` (a whole
git repo folded as one digest), `image`/`image-reconcile` (an image read visually), and `curate`
(improve an existing page cluster against a findings file read by path, not a raw source).
`run_ingest_session` is the single seam tests monkeypatch.

**Two checking layers, one implementation** (`validate.py`):
- `citadel check` / `wiki_validate` — the **strict per-page gate** (required fields, honest/defined
  citations, relative non-broken links, no `[[wikilinks]]`). The ingest agent self-runs it; ingest
  re-runs it and fails the source on any error.
- `citadel lint` (`lint.py`) — a **pure offline health check** (contradictions, orphans, missing
  cites, broken links, stale, fabricated sources, undefined abbreviations, and **Z6 locator issues**
  — an out-of-range `lines A-B` range or a missing `§ Heading`, via `lint.check_locators`, shared
  with curate). Only *structural* problems (missing type, broken links, bad sources, wikilinks) flip
  its non-zero exit; the rest — locator issues included — are advisory. Both layers parse
  citations/links/fences through `grammar.py`, so lint and `citadel check` agree by construction: a
  citation into `raw/` or `docs/` is legal provenance (never a broken link), and a link inside a
  ``` code fence is literal text.

**Curate is the second wiki lifecycle** (`curate.py`, `citadel curate`) — **no persisted queue**:
the plan is recomputed from offline detectors (`rules_version_drift`, `page_length_hard`,
`contradiction`, `orphan`, `llm_drift`, `resort` via `okf.folder_for_type`, `locator`) each run.
Each page CLUSTER runs ONE staged `kind="curate"` session over ingest's staging machinery; **the
staging diff-by-hash is the single result arbiter** (empty = NOOP, clean = applied, fail =
revert-and-stop → attempt-capped failures-catalog record). `--dry-run`/`--limit`/`--stale-rules`/
`--diff` shape the run; sessions use `CITADEL_CURATE_MODEL` (falls back to the ingest model).
`status.py` (`citadel status`) is the read-only per-source state view (manifest + failures + one
stat-only walk; never re-hashes).

**Other modules:** `okf.py` is the OKF format core (parse/dump, type→folder routing, link math, and
the non-negotiable `safe_join` path guard — reuse it for any wiki-relative path). `grammar.py` is
the **single home of the markdown grammar** (link/footnote/fence/Sources-heading parsing and the
source-citation predicates) that `store`, `validate`, `lint`, and the viewer all parse through;
never re-define any of it locally. `store.py` is a thin **facade** re-exporting the "database"
API, split by responsibility into four sibling modules (import them through `store`): `store_core.py`
(`load()`, the single swappable `search()` seam, `read/write/delete_page` — both mutators share the
reserved-name guard refusing `index.md`/`*/index.md`/`log.md`/dotfiles — plus the CLI/MCP text
providers and the `log.md` writer); `linkgraph.py` (the deterministic link-rewrite safety nets
`rewrite_links`, `rewrite_raw_references`, `find_raw_references`, `find_broken_links`, and the
`inbound_map` backlink graph, all fence-aware via `grammar.py`); `catalogs.py` (`rebuild_indexes()`,
regenerating `index.md`, per-folder `index.md`, `sources/index.md`, and `open-points/index.md`
mechanically from frontmatter + manifest); and `open_points.py` (parsing `## Open Points` threads
and deriving each point's status). `manifest.py` tracks idempotency in
`wiki/.citadel_ingested.json` (per source: sha256 or git commit + importing model). `repo.py` builds
the digest for git-repo sources. `extract.py` pulls text from Office files (stdlib-only); the legacy
OLE/CFBF salvage lives in `extract_ole.py`, imported lazily only when a legacy `.ppt`/`.doc`/`.xls`
is dispatched. `curate.py` is the second lifecycle and `status.py` the read-only per-source state
view (both above); `doctor.py` (`citadel doctor`) is the read-only setup health check (OK/WARN/FAIL
lines over workspace resolution, the rules tree, the agent CLI on PATH, raw-root reachability,
manifest parse + stamp, failures summary, and the API-key/PDF advisories). `server.py` is the
FastMCP stdio server (8 tools — 7 read-only incl. `wiki_lint`,
only `wiki_ingest` mutates; every tool carries MCP behavior annotations and never raises, returning
error strings). The `viewer/` subpackage builds the self-contained offline HTML viewer
(`template.html`/`app.css`/`app.js` are package-data assets loaded via `importlib.resources`).
`config.py` resolves all paths/settings. `cli.py` mirrors the MCP tools as subcommands with full
parity (`read`/`index`/`sources` twin the readers; `lint`/`view` stay CLI-only, `wiki_lint` closes
the gap from the MCP side).

## Conventions specific to this codebase

- **`config.*` is read at call time** (`from . import config` then `config.WIKI_DIR`), never imported
  by value — so tests can monkeypatch the whole filesystem layout. Honor this when adding code.
- **Tests redirect everything to `tmp_path`** by monkeypatching `config.*` (including
  `WORKSPACE_ROOT`, which the agent's `cwd` reads) and replace `llm.run_ingest_session` with a fake
  that writes files into the temp wiki. No test spawns a real CLI. Follow that pattern; keep tests
  offline.
- **Never hand-edit generated files** — `index.md`, `log.md`, any `*/index.md`, `sources/index.md`,
  `.citadel_viewer.html`, and `.citadel_ingested.json` are regenerated. The ingest agent prompt and
  `store.delete_page` both refuse to touch them.
- **Provenance grammar is load-bearing:** raw facts cite `[^sN]` → a real `raw/` file; model-supplied
  facts use `[^llmN]` (source: `LLM`) and must never be disguised as raw citations. A `[^sN]` to a
  missing file fails lint/check.
- **`wiki/`, `raw/`, `docs/` can live outside the workspace** (e.g. a mounted network drive) via
  `CITADEL_*_DIR`. Path handling distinguishes workspace-relative keys from absolute out-of-workspace
  keys (`config.rel_or_abs_posix` / `source_path_for_key`) — preserve that when touching path logic.
- **Cross-platform robustness is intentional**, not over-engineering: UTF-8 forcing, BOM stripping,
  ASCII-only progress output, read-only-bit clearing, and network-share retry loops all fix real
  Windows/SMB failures.
- Config knobs live in the workspace-root `.env` (auto-loaded, gitignored; template:
  `citadel/templates/env.example`): `CITADEL_LLM_CLI`,
  `CITADEL_INGEST_MODEL`, `CITADEL_CURATE_MODEL` (model for `citadel curate`; falls back to the
  ingest model), `CITADEL_LLM_TIMEOUT`, `CITADEL_LLM_VERBOSE`, `CITADEL_LLM_LOG_DIR`,
  `CITADEL_REPO_SUPPORT`, `CITADEL_WIKI_LANG` (target language of all wiki prose, default `en`),
  `CITADEL_PDF_MODE` (`text` | `images`), `CITADEL_STYLE_PROFILES` (opt-in style capture, default
  `0`), the `CITADEL_*_DIR` path overrides, `CITADEL_RAW_DIRS` (multi-root: a comma/newline-separated
  list of raw roots discovery walks), and `*_CLI_PATH` binary overrides.
