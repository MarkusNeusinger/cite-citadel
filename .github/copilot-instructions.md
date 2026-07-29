# GitHub Copilot instructions — cite-citadel

Repository guidance for GitHub Copilot. **Generated from [`CLAUDE.md`](../CLAUDE.md)** — do not edit
this file by hand: change `CLAUDE.md` and regenerate with
`CITADEL_WRITE_COPILOT_DOC=1 uv run pytest tests/test_packaging.py -k copilot -q`. The drift guard in
`tests/test_packaging.py` fails whenever the two disagree.

## What this is

`cite-citadel` (CLI: `citadel`, PyPI package: `cite-citadel`) is an LLM-maintained, fully-cited
personal wiki in Google's [Open Knowledge Format](../docs/okf-reference.md), with an MCP server so an
AI can search and read it. It implements Karpathy's LLM-Wiki pattern: drop arbitrary text-bearing
files into `raw/`, and one agentic CLI session per source folds each into a cross-linked OKF wiki
under `wiki/`. Pure Python 3.12, KISS. Runtime deps are only `mcp`, `pyyaml`, `pypdf`, and `rich`
(all pure-Python, no native weight) — **there is no LLM SDK and no API key**: ingest shells
out to a coding-agent CLI you already have logged in
(`claude`/`copilot`/`agy`).

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
session, `--log-dir DIR` writes a transcript per source, `--quiet` drops the live progress display,
`--jobs N`/`-j` folds N sources in CONCURRENTLY (default 1 = serial; `CITADEL_JOBS`),
`--full-rescan` distrusts the manifest's stat cache and re-hashes every tracked source,
`--force <paths>` deliberately re-reads already-ingested sources as a reconcile — it requires
explicit paths and is refused without them), `refresh [--limit N] [--min-age-days D] [--dry-run] [--jobs N]`
(the THIRD lifecycle: re-verify the least-recently-checked sources — ordered by the manifest's
`ingested_at` stamp, oldest/stampless first — through forced reconcile sessions on an explicit
per-run budget of N sources; the sustainable alternative to regenerating the wiki after a model
upgrade), `curate [--dry-run] [--limit N] [--stale-rules]
[--diff PATH] [--retry]` (the SECOND lifecycle: improve EXISTING pages — re-sort/split/re-ground/resolve
contradictions/fix locators — against a recomputed findings checklist), `status` (read-only
per-source state table: ingested / failed / skipped-duplicate / ignored / oversized / pending; MCP twin
`wiki_status`), `doctor`
(read-only setup health check — OK/WARN/FAIL lines for workspace / rules / config-parse fallbacks /
agent CLI / the configured ingest model / raw roots / wiki placement
(the wiki nested inside a raw root) / child paths (the UNC-vs-drive-letter cwd) /
manifest / billing / the HTTP-serve posture / wiki-git state / a best-effort PyPI update check / workspace coherence; needs no workspace, exits 1 only on a FAIL),
`serve [--http [--host H] [--port P] [--path /mcp] [--read-only]]` (the MCP server — stdio by
default; `--http` serves the SAME surface over MCP's Streamable HTTP transport for a client that is
not on this machine, mandatory bearer token, loopback default, optional read-only), `capture <text> [--from WHO] [--topic T]` (append one attributed note from a
conversation to the raw/ capture log `raw/captures/YYYY-MM.md`; `-` reads stdin; the next ingest
folds it in — the conversational-capture bridge, MCP twin `wiki_capture`),
`search <query> [--tag T] [--limit N]`, `define <term>` / `read <rel_path>` /
`raw <key> [--locator L]` / `neighbors <rel_path>` / `index` / `sources` (CLI twins of the
`wiki_define`/`wiki_read`/`wiki_raw`/`wiki_neighbors`/`wiki_index`/`wiki_sources` MCP tools
— full CLI↔MCP parity),
`tags [tag]`, `lint [--stale-days N]` (exit 3 when the report is not clean — its own code, distinct
from the usage/no-workspace exit 2), `check [paths…]`, `view [--out PATH] [--no-open]
[--obsidian]`, `rules list|show|eject`. `citadel --version` prints the version and (like `--help`)
needs no workspace.

Tests (pytest, all offline — no LLM CLI and no network is ever spawned; only `test_wikigit`
shells out, to local `git`):

```bash
uv run pytest -q                                    # whole offline suite, a few seconds
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

Nine synthetic corpora live under `corpora/` (`corpora/<name>/{raw/, stages/?, README.md}`),
runnable individually or together: **beverages** (the coffee+tea showcase), **kelvarra** (a
coherent fictional world stated wrong about reality — graded that facts appear as stated, cited,
never corrected), **leuchtfeuer** (a 3-year programme ingested in dated `stages/` waves that
drives reconcile/delete/force, temporal supersession, German→English, and attributed opinions — its
committed `raw/` is the FINAL post-wave state and `stages/initial/` holds the wave-1 originals),
**pemberley** (the whole of *Pride and Prejudice* as one ~730k-char source — large-source
multi-segment chunking, relationship extraction, in-novel misinformation, narrative supersession),
**injection-resistance** (three mundane documents with adversarial instructions embedded — the
agent must treat them as content, never execute them), **clockwork** (a whole git repository folded
in as ONE digest via `CITADEL_REPO_SUPPORT`, with a second commit driving `repo-reconcile` — its
committed inputs are the `repo-src/` + `repo-src-wave2/` trees materialized into a checkout, since a
git repo cannot be committed inside this repo), **flurfunk** (seven informal-genre sources — a
chat export, a tweet thread, an interview, a job application, a forum thread, an announcement —
grading attribution, "X said Y" ≠ "Y is true", in-thread reversal, and CV timelines), **gazette**
(five PDF/markdown sources whose stdlib-generated PDFs grade `CITADEL_PDF_MODE` text-vs-images — a
figure-only number and an image-only page absent in text mode, present in images mode — plus the
academic-publications genre and references-are-not-sources), and **kontor** (binary Office documents — OOXML `.pptx`/`.docx`/`.xlsx` and legacy OLE `.doc`/`.ppt`/`.xls`, generated stdlib-only via `make_office.py` — the sole test of the Office text-extraction path (`extract.py` + `extract_ole.py`), an embedded-chart **image delta** (`CITADEL_IMAGE_SUPPORT`), **dedup-by-basename**, and **ignore-patterns**, with the same discriminative judgment traps as the hardened corpora — all fictional, Aldervik Kontor). **Each corpus carries its own committed,
graded showcase wiki** at `corpora/<name>/wiki/` (its own nested `citadel.toml` marker,
`meta.workspace` neutralized to `""`, no viewer artifact); CI lints every one and the GitHub Pages
site (`.github/workflows/pages.yml`) builds a **gallery** with one offline viewer per corpus. Each
carries a hidden answer key at `.claude/skills/verify-corpus/<name>/ground-truth.md` — **outside the
corpus so the ingest agent never sees it** (Mode A also points `CITADEL_RAW_DIR` at the corpus `raw/`
only). The parameterized `verify-corpus` skill (`verify-corpus <name>|all [--grade-only]`) ingests a
corpus into a throwaway sandbox workspace (never a live wiki) and grades it the way a user consumes
the wiki: `citadel check` + `lint` exit 0 (structural eligibility), then a **retrieval-first** content
grade — driving citadel's own read tools (`search`/`read`/`index`/`tags`) to prove each answer-key
guarantee is both correct+cited and easily findable, dropping to a file-level grep only to separate a
wiki-creation defect from a retrieval one (its misses feed two optimization lanes: the ingest/rules
generator and the search tools — persisted per run in the committed ledger
`docs/verify-corpus-backlog.md`). Corpora live
**outside** `citadel/`, so they never ship in the wheel. The repo-root `raw/` + `wiki/` are a
gitignored developer workspace (the checkout's `citadel.toml` marker still makes it a workspace).

## Self-verification (feedback loops)

Two `.claude/skills/` skills close the loop between a change and its proof:

- **verify-corpus** (`verify-corpus
  <beverages|kelvarra|leuchtfeuer|pemberley|injection-resistance|clockwork|flurfunk|gazette|kontor|all>
  [--grade-only]`) — the end-to-end corpus grader: ingests a corpus into a throwaway sandbox and
  grades the result against its hidden `ground-truth.md` by querying the wiki through citadel's own
  read tools like a user (retrieval-first), falling back to file greps only to tell a wiki-creation
  defect from a retrieval one. Run it after any change to `ingest.py`, `llm.py`, or the rules tree
  (`citadel/rules/`).
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
   `systems/`, `persons/`, `organizations/`, `projects/`, `abbreviations/`, `registries/`, `misc/`
   (see `okf.folder_for_type`), cross-linked with relative markdown links, each fact carrying a
   footnote citation.
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
  (moved-or-duplicate) / unreadable (binary; an all-NUL read is flagged as a cloud-only placeholder
  — Dropbox/OneDrive online-only — and never stat-cached as done, so it ingests once hydrated) /
  deleted (vanished from disk, full runs only) /
  same-basename document duplicates (skipped in favor of one preferred format). A pending Office
  source is extracted to text first; a pending image is read visually; a pending audio/video
  recording (`CITADEL_AUDIO_SUPPORT`, opt-in) is transcribed through a local whisper-class CLI
  (`transcribe.py`, content-addressed cache `.citadel_transcripts/` beside the wiki) and the agent
  reads the `[HH:MM:SS]`-stamped transcript; a pending PDF (pypdf is a bundled dep —
  `CITADEL_PDF_TEXT`, default auto) gets its text layer extracted (`pdftext.py`, content-addressed
  cache `.citadel_pdftext/`) and the agent reads the `[p. N]`-marked extraction, falling back to
  the direct agent read when there is no usable text layer; a pending source larger than
  `CITADEL_MAX_SOURCE_CHARS` is folded in over several passes (all against one staging copy — see
  the promote bullet below). `ingest --force <paths>` bypasses the sha short-circuit: the named
  sources land in pending as reconciles (a repo re-digests in full), and the manifest is re-stamped
  with the current model + rules version.
- **Discovery is incremental and deletion-safe**: one iterative `os.scandir`
  walk over every `CITADEL_RAW_DIRS` root keeps each file's stat; the **manifest doubles as the
  scan cache** (an entry's `size`/`mtime_ns`/`ctime_ns`/`hashed_at_ns` are a skip-hint — sha256
  stays the sole arbiter of "changed"; `--full-rescan` distrusts the cache). Two things are pruned
  from the walk before any of that: the **wiki dir itself** (`_is_wiki_internal`, lexical — a raw
  root ABOVE the wiki, e.g. the whole of `T:\`, would otherwise fold the generated wiki back in as
  sources run after run; a root that IS the wiki is refused without arming the sweep, an explicit
  path inside it is refused too, and the run-start migration sweep clears any already-self-ingested
  key), and files over `CITADEL_MAX_SOURCE_BYTES` (the size complement to the name-matching ignore
  globs — skipped from the walk's own stat, so a 10 GB sensor dump is never opened, let alone
  hashed; reported, never silent, and off by default). Deletion candidates
  come from the walked-seen-set diff and each is positively **confirmed with `.exists()`**; any
  walk error aborts the whole sweep, an unreachable root contributes no candidates, keys under no
  configured root are logged and never swept, and a workspace-identity mismatch whose keys do not
  resolve refuses the sweep. A flaky share or unmounted root must NEVER read as mass deletion —
  don't weaken these guards.
- For each pending source it runs the agent against a **per-source staging copy** of the wiki (a
  sibling dir, never the live wiki), then snapshots before/after and **diffs by content hash** to
  learn what the agent created/updated/deleted — the agent's file edits *are* the result (the
  session seam's return value is only passive cost/usage telemetry, never consulted for what
  changed).
- It then re-imposes invariants on every changed page (`validate.validate_page` + `store.write_page`
  to canonicalize YAML and stamp the timestamp) after **every** agent pass, repairs renamed-page
  links, and **only on a fully clean source promotes staging onto the live wiki — exactly once per
  source** — with a non-destructive copy-over-then-prune. A chunked large source folds ALL its
  segments into that one staging copy before the single promote (the live wiki
  never holds a partially imported source; a failure at segment N still discards the whole staging
  copy — but no longer the MONEY: each completed segment banks its delta as a **resume checkpoint**
  (`resume.py`, `CITADEL_RESUME`, `.citadel_resume/` beside the wiki) that the next run replays into
  its fresh staging copy to continue at segment N. Every reuse is guarded — identity (source sha,
  model, rules version, segment content, prompt knobs), blob integrity, per-page base state in the
  live wiki, plus re-validation and a no-new-broken-links check of the replayed delta — and every
  guard failure falls back to a full restart at segment 1 *in the same run*, so the pre-resume
  behavior is the floor). Any
  failure/timeout/Ctrl+C leaves the live wiki exactly as it was; the source is retried next run.
  Deletion cleanups, then pending files, then repos all drive this through ONE shared per-source
  loop (`_SourceJob` + `_run_source_jobs`) — **deletions run first** so a delete cleanup strips a
  vanished source's stale provenance before any pending session touches a page that still cites it
  (else that pre-existing bad citation would fail the pending session's validation and roll it
  back). This all-or-nothing + network-share-hardened machinery (`_robust_*`, `robust_mkdir`) is
  load-bearing — don't simplify it away. **Bounded parallelism** (`--jobs N` / `CITADEL_JOBS`, default 1 = serial): the per-source staging
  copy IS the isolation primitive, so N sources run at once through the same `_SourceJob` loop —
  worker threads only plan/stage/run/promote, while every SHARED write (report, manifest, failures)
  stays on the main thread. One lock (`_LIVE_WIKI_LOCK`) guards the only two moments that touch the
  live wiki: the clone (taken together with a hash snapshot of what was cloned) and the promote.
  Under it the promote is **base-aware** — it prunes only what its own clone had and its staging
  lacks (else it would delete a concurrent source's new pages), and it REFUSES, before writing a
  byte, if a path it would touch has moved since the clone; that source is then re-run SERIALLY at
  the end of its group, where it merges into the winner's page (reported as `raced`). What
  parallelism costs is cross-linking, not safety — concurrent sessions cannot see each other's new
  pages — which is why the default is 1. The redirect this rides on is context-local
  (`config.wiki_redirect` → a ContextVar behind `config.wiki_dir()`; children get their wiki via
  `config.child_env()`), never a `config.WIKI_DIR`/`os.environ` assignment.
  **One mutating run per workspace**: ingest and curate take
  an exclusive run lock (`runlock.py`, a dotfile sibling of the wiki; stale locks reclaimed via
  dead-pid/mtime, refreshed per source) so a second concurrent run fails loud instead of silently
  destroying the first one's staging/promotes; manifest + failures saves are atomic
  (`config.atomic_write_text`, temp-sibling + `os.replace`), and the stale-staging sweep runs once
  at run start under the lock, never per source.

**`llm.py` is the ONLY place that talks to an LLM**, and it does so by shelling out to a CLI in
agentic mode (`cwd` = `config.child_cwd()` — the workspace root in its child-friendly spelling —
autonomous file tools). The prompt is **paths-only** — it references
the source and rules by path, never embeds file content — which keeps argv tiny (the Windows
`WinError 206` fix). One per-kind spec table (`_KIND_SPECS`) maps each `kind` to its task-rule
file, whether it reads a source, and its format policy; an unknown kind fails loud. `kind` selects
the propagation: `ingest` (new), `reconcile` (changed source — update/remove stale facts, don't
just append), `delete` (source removed — strip its provenance), `repo`/`repo-reconcile` (a whole
git repo folded as one digest), `image`/`image-reconcile` (an image source read visually),
`audio`/`audio-reconcile` (an audio/video source read via its whisper transcript),
`pdf`/`pdf-reconcile` (a PDF read via its pypdf text-layer extraction), and
`curate` (improve an existing page cluster against a findings file — reads that file by path, not a
raw source). A large source is split into segments and folded in over several passes
(`segment=(part, total)` on `run_ingest_session`, telling later passes to MERGE into earlier ones).
`run_ingest_session` is the single seam tests monkeypatch; it returns the session's best-effort
`SessionUsage` (the backend's OWN report of what it spent AND which model actually served the
session: claude's result envelope - `total_cost_usd` plus the `modelUsage` map, whose PRIMARY
entry is the one carrying the token volume, since claude routes cheap side work to a smaller
model; copilot's `--output-format json` JSONL - no dollars, so its own billing unit is recorded
instead: `totalNanoAiu`, the counter behind the `N AIC used` session footer (1 AIC = 1e9 nanoAiu),
converted to `cost_usd` at GitHub's fixed published $0.01/credit so a mixed corpus keeps ONE
comparable total while the un-derived credits stay stamped beside it (the retired
`totalPremiumRequests` is deliberately ignored); agy's `--output-format stream-json` - the
opening `init.model` plus the
closing `result.usage` token totals; None when nothing was reported - accounting is strictly
passive and can never fail a session), which ingest sums per source into the manifest stamp and
per run onto the reports. **The REPORTED model wins**: `config.model_label_for(reported)` stamps
the backend plus what actually ran, and falls back to the configured label only when the backend
named nothing (an Ollama/proxy backend, or agy left on its own default), so the manifest never
claims a model that never ran.

**Two checking layers, one implementation** (`validate.py`):
- `citadel check` / `wiki_validate` — the **strict per-page gate** (required fields, honest/defined
  citations, relative non-broken links, no `[[wikilinks]]`). The ingest agent self-runs it; ingest
  re-runs it and fails the source on any error.
- `citadel lint` (`lint.py`) — a **pure offline health check** (contradictions, orphans, missing
  cites, broken links, stale, fabricated sources, undefined abbreviations, near-duplicate/malformed
  open points, and **locator issues** — a `lines A-B` range past a text source's end or a
  `§ Heading` naming a heading the source lacks, via `lint.check_locators`, shared with curate).
  Only *structural* problems (missing type, broken links, bad sources, wikilinks) flip its non-zero
  exit (code 3 — lint's own, so CI can tell "wiki has problems" from the usage/no-workspace exit 2);
  the rest — locator issues included — are advisory. Both layers parse citations/links/fences
  through `grammar.py`, so lint and `citadel check` agree by construction: a citation into `raw/` or
  `docs/` is legal provenance (never a broken link), and a link inside a ``` code fence is literal text.

**Curate is the second wiki lifecycle** (`curate.py`, `citadel curate`). It has **no persisted
queue — the plan is recomputed from offline detectors every run** (the wiki IS the database):
`rules_version_drift`, `page_length_hard`, `contradiction`, `orphan`, `llm_drift`, `resort`
(type↔folder mismatch via `okf.folder_for_type`), and `locator` (from `lint.check_locators`);
fact re-verification is pre-filtered offline through manifest shas (`reverify_candidates` — changed
= reconcile's job, gone = delete's job). Each planned page CLUSTER (page + cited raw files + link
neighbors) runs ONE staged `kind="curate"` session over ingest's existing staging machinery, its
findings written to a temp file referenced by path. **The staging diff-by-hash is the single result
arbiter** (empty = NOOP, clean promoted = applied, exception/check-fail = failed → revert-and-stop).
A failed cluster lands in the failures catalog keyed by page rel_path with an additive `attempts`
counter (default cap 2, never auto-retried until an explicit retry). `--dry-run` prints the plan
with zero sessions; `--limit`/`--stale-rules` shape it; `--diff PATH` writes a per-page change
report; `--retry` re-includes attempt-capped clusters (the explicit retry that bypasses the cap);
curate sessions run under `CITADEL_CURATE_MODEL` (falling back to the ingest model).

**Refresh is the third lifecycle** (`refresh.py`, `citadel refresh`): budget-controlled
re-verification of existing SOURCES, so an aging wiki is brought up to the current model + rules a
slice at a time instead of ever being regenerated. Every successful session stamps its source's
manifest entry with an `ingested_at` last-checked time (`manifest.now_iso`; stamped ONLY in
`mark_done`/the repo done-hook — moves and cache re-stamps CARRY the old stamp, so "last checked"
never lies). `refresh.plan()` orders the manifest by that stamp (oldest first, a stampless
pre-refresh entry counting as oldest; only model-imported, still-on-disk sources qualify;
`--min-age-days` drops fresh ones so scheduled runs self-limit) and `refresh.refresh(limit=N)`
hands the queue head to `ingest.ingest(paths, force=True)` — one `kind="reconcile"` session per
source through the existing staging machinery, the success re-stamp rotating it to the back, so
repeated runs walk the corpus round-robin with NO persisted queue (the manifest IS the queue).
The budget is always explicit (`limit >= 1` enforced, default 1), mirroring `--force`'s
no-accidental-corpus-wide-run refusal. CLI-only, like curate.

An auth-shaped session failure under hermetic isolation is **retried once without the isolation
flags**: on a machine whose CLI credentials live in exactly the personal config `--bare` skips,
every session used to die on authentication until the user found `CITADEL_HERMETIC=0`. The retry
is scoped to that signature (flags actually passed + an auth-shaped message), so a real credential
problem still fails instead of looping.

**Status is the read-only corpus view** (`status.py`, `citadel status`): the manifest + failures
catalog + one stat-only walk (never re-hashes) rendered as a per-source state table — ingested
(model + rules_version, `(stale)` when it predates the current rulebook, `checked YYYY-MM-DD` from
the `ingested_at` stamp, the last session's cost when recorded, with copilot's AI credits shown
beside the dollars they converted into — with `Recorded LLM cost` / `Recorded AI credits` corpus
totals above the table), failed (reason, attempts),
skipped-duplicate, ignored (pattern), oversized (over `CITADEL_MAX_SOURCE_BYTES`, with the size),
pending.

**Other modules:** `okf.py` is the OKF format core (parse/dump, type→folder routing, link math, and
the non-negotiable `safe_join` path guard — reuse it for any wiki-relative path). `grammar.py` is
the **single home of the markdown grammar** (link/footnote/fence/Sources-heading parsing, the
source-citation predicates, and the `[^sN]` **locator** parser — `parse_locator`/`source_headings`,
which `lint.check_locators` and curate consume) that `store`, `validate`, `lint`, and the viewer all
parse through; never re-define any of it locally. `store.py` is a thin **facade** re-exporting the "database"
API, split by responsibility into four sibling modules (import them through `store`, not directly):
`store_core.py` (`load()`, the single swappable `search()` seam, `read/write/delete_page` — both
mutators share the reserved-name guard that refuses `index.md`/`*/index.md`/`log.md`/dotfiles —
plus the CLI/MCP text providers and the `log.md` writer); `linkgraph.py` (the deterministic
link-rewrite safety nets `rewrite_links`, `rewrite_raw_references`, `find_raw_references`,
`find_broken_links`, and the `inbound_map` backlink graph, all fence-aware via `grammar.py`);
`catalogs.py` (`rebuild_indexes()`, which regenerates `index.md`, per-folder `index.md`,
`sources/index.md`, and `open-points/index.md` mechanically from frontmatter + manifest); and
`open_points.py` (parsing `## Open Points` threads and deriving each point's status).
`pagecache.py` is the read-path snapshot cache behind `store_core.load()` (`CITADEL_PAGE_CACHE`,
`auto` = on only in `citadel serve`, which opts in): a long-lived MCP server otherwise re-walks and
re-parses the WHOLE wiki on every tool call, so the last load is kept in memory and re-validated
per call by a **stat-only** scandir fingerprint (`(rel_path, size, mtime_ns, ctime_ns)` over exactly
the files `load()` parses) — ~4 ms vs ~700 ms at 1000 pages, with search's per-page term-frequency
tables memoized on the same snapshot (a 1000-page `wiki_search`: ~1.4 s → ~50 ms). Nothing is
persisted (the wiki stays the database) and staleness is designed out: the fingerprint is taken
BEFORE and AFTER the load and must match, a snapshot whose newest stamp is younger than the settle
window is never stored (coarse-mtime filesystems), the single slot is keyed by wiki dir (ingest's
staging redirect can never be served the live wiki), `write_page`/`delete_page` invalidate, and
`ingest()`/`curate()` wear `@pagecache.bypass` so the diff-by-hash machinery always reads disk.
`manifest.py` tracks idempotency in
`wiki/.citadel_ingested.json` (per source: sha256 or git commit + importing model + the last
session's backend-reported `cost_usd`/`tokens_in`/`tokens_out`, carried across moves/re-stamps
like `ingested_at`). `failures.py`
persists the sources that could NOT be ingested (`wiki/.citadel_failures.json`: unreadable /
errored / timed-out, with a reason), surfaced by `store` under a "Could not ingest" section of
`sources/index.md`. `repo.py` builds the digest for git-repo sources. `extract.py` pulls text from
Office files (stdlib-only): OOXML `.pptx`/`.docx`/`.xlsx` (+ macro-enabled) via zipfile+ElementTree,
and legacy OLE `.ppt`/`.doc`/`.xls` via the CFBF reader + best-effort text salvage in
`extract_ole.py` (imported lazily, only when a legacy OLE file is dispatched); its
`extract_media` also pulls embedded raster images out of OOXML files so the agent can view them.
`transcribe.py` is the whisper-CLI seam for audio/video sources (`CITADEL_AUDIO_SUPPORT`, opt-in):
detection by extension+magic, one shell-out per content (openai-whisper flag convention), the
`[HH:MM:SS]`-per-line transcript cached content-addressed in `.citadel_transcripts/` beside the
wiki — the same cached text `lint`/`wiki_raw`/the viewer verify and serve audio citations against;
`transcript_for` is the ingest seam tests monkeypatch (whisper itself is never an LLM concern, so
this lives beside `extract.py`, not in `llm.py`).
`pdftext.py` is the same idea for PDFs (the audio pattern applied to the PDF class): pypdf is a
bundled runtime dep (PDFs are a common raw/ class), so with `CITADEL_PDF_TEXT` (default auto = on
when pypdf imports, which it always does unless deliberately uninstalled) a
genuine PDF's (`%PDF-` magic) text layer is extracted once per content into a `[p. N]`-page-marked
line-stable text, cached content-addressed in `.citadel_pdftext/` beside the wiki — the agent
reads it under the `pdf`/`pdf-reconcile` kinds while citing the original `.pdf` with `lines A-B`
locators the same cache lets `lint`/`wiki_raw`/the viewer verify offline; `text_for` is the ingest
seam, strictly best-effort (scanned / encrypted / corrupt / pypdf force-removed → None → the
agent-native read with agent-verified `p. N` locators — never a failed source).
`resume.py` is the chunked-source resume-checkpoint store (`CITADEL_RESUME`): after each completed segment ingest banks the promote-shaped delta in `.citadel_resume/` beside the wiki, guarded by identity (source sha, model, rules version, segment content, prompt knobs), blob integrity, per-page live base state, re-validation of the replay and an attempt cap — so an interrupted large source continues at its failed segment instead of re-buying the earlier ones, and every guard failure degrades to a full restart. `curate.py` is the second lifecycle (offline detectors + staged cluster sessions; see above).
`status.py` is the read-only per-source state view; `doctor.py` (`citadel doctor`) is the read-only
setup health check (OK/WARN/FAIL lines over workspace resolution, the rules tree, the agent CLI on
PATH, raw-root reachability, manifest parse + stamp, failures summary, the API-key/PDF/audio
advisories, the wiki-git state, a best-effort PyPI update check naming the right upgrade command
per install method, and workspace coherence).
`progress.py` is the CLI's live console reporter (`rich`), wired in only by `cmd_ingest`/`cmd_refresh`
— the MCP server passes no progress, so its stdio stays clean. On a terminal it renders a live
region: one spinner row per IN-FLIGHT source (which is what makes `--jobs N` legible) plus an
overall bar, while finished sources scroll away above it as permanent one-line verdicts carrying
what the session actually spent (`[2/3] OK raw/notes.md 18.4s 2 created $0.0123 1.2k in / 456 out
claude-opus-5` — only fields the backend genuinely reported). Off a TTY or under `--verbose` it
degrades to a START line plus a verdict line per source. Two invariants are load-bearing: every
composed string is ASCII-only and the spinner is pinned to rich's ASCII `line` frames (a cp1252
Windows console must be able to encode it), and every write goes through a swallow-everything guard
— console output must never be able to fail a run that already spent money. Source keys are
shortened by `config.display_key`, which drops the whole prefix before the raw folder in three
tiers: an exact prefix match, a cut at the last path segment NAMED like a configured root (this is
what rescues a Windows drive letter mapped to a share, where `T:\proj\raw` and the key's
`//fileserver.../proj/raw/...` are one folder but share no text), and finally a `.../`-marked tail
clip, so no absolute key can ever flood the console.
`wikigit.py` is the best-effort wiki-HISTORY layer: after every run that changed the wiki (ingest or
curate) it commits the whole wiki dir as ONE commit (and pushes to `CITADEL_WIKI_GIT_REMOTE` when
set), so every change is a reviewable diff; `auto` (default) only acts when the wiki dir is already
its own git repo, `CITADEL_WIKI_GIT=1` also `git init`s it on first use (refusing an embedded repo
inside another working tree), and any git problem is a report note, never a failed run. `server.py` is the FastMCP stdio server (13
tools — 11 read-only incl. `wiki_raw` (the cited-source reader, backed by `rawsource.py`),
`wiki_neighbors` (a page's links-out/backlinks/cited-sources graph), `wiki_lint` (with a tunable
`stale_days`) and `wiki_status` (the per-source state view), plus two mutating:
`wiki_capture` (append-only conversational note capture into `raw/captures/`, backed by
`capture.py` — it never touches the wiki) and `wiki_ingest` (the only wiki-writer); every tool carries MCP behavior
annotations — `readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint` — never raises,
returning error strings instead, and hands the recommended tool flow up through
`initialize.instructions`; the server also publishes four workflow **prompts** —
`wiki_answer`/`wiki_verify`/`wiki_capture_note`/`wiki_health`, slash-command-like packaged flows
— and the wiki's documents as `wiki://` **resources** (`wiki://index`/`wiki://sources`/
`wiki://tags` + the `wiki://page/{folder}/{name}` per-page template), byte-identical to their
tool twins and sharing the tools' never-raise contract). `httpserve.py` is the OPT-IN
**Streamable HTTP** transport for that same surface (`citadel serve --http`) — the only network
surface citadel has, so it is strict by construction: a mandatory bearer token
(`CITADEL_HTTP_TOKEN`, ≥16 chars — `serve` refuses to start without one) checked in a ~30-line ASGI
wrapper BEFORE the MCP session layer (constant-time compare, 401 + `WWW-Authenticate`, no
"unauthenticated for a minute" mode), a loopback bind by default (a public bind warns — the
transport is plain HTTP, the intended remote path is a TLS-terminating tunnel), a Host/Origin
admission policy owned by that same wrapper (the SDK's own middleware couples the two checks to
one flag and can express neither "any host" nor "one browser origin") — `Host` derived from the
bind address or named in `CITADEL_HTTP_ALLOWED_HOSTS` (a tunnel forwards its own hostname; a
wildcard `0.0.0.0` bind derives nothing, so it REFUSES to start instead of 421-ing every request),
browser `Origin`s refused unless `CITADEL_HTTP_ALLOWED_ORIGINS` admits them — and an optional read-only mode
(`--read-only`/`CITADEL_HTTP_READ_ONLY`) that has the two mutating tools refuse while leaving the
11 readers and the advertised tool list untouched (`server.set_read_only`). No new dependency —
starlette/uvicorn already ship with `mcp`. The `viewer/` subpackage builds the self-contained offline HTML
viewer (build logic in `__init__.py`; `template.html`/`app.css`/`app.js` are real package-data
assets loaded via `importlib.resources`). `config.py` resolves all paths/settings — including the
**native-form registry** (`NATIVE_FORMS`/`native_form`/`child_cwd`): every configured path stays
`resolve()`-d, which is what makes path identity unambiguous, but on Windows that rewrites a mapped
drive (`T:\team-wiki`) into its UNC form, and a UNC `cwd` is refused outright by some agent CLIs
(and read as a different repository by git). So the NON-resolved spelling citadel already holds (the
`.env` value, the launching drive) is remembered alongside the resolved one and handed to CHILD
processes only — the agent CLI's `cwd` + directory grants, git's `-C` — and every path UNDER an
aliased directory inherits it (a default `wiki/` has no `.env` value of its own to record, yet it is
what git gets as `-C`). An alias is recorded only when both spellings of one directory are known AND
resolution turned a non-UNC path into a UNC one, so POSIX and ordinary Windows paths keep exactly
one spelling. `cli.py` mirrors
the MCP tools as subcommands (full parity: `define`/`read`/`raw`/`neighbors`/`index`/`sources`/`capture` twin their tools;
`view` stays CLI-only and `wiki_lint`/`wiki_status` close the `lint`/`status` gaps from the MCP side). `capture.py`
is the conversational-capture bridge behind `wiki_capture`/`citadel capture`: an append-only,
dated, attributed note into the monthly `raw/captures/YYYY-MM.md` log under the primary raw root
— an ordinary raw source the normal lifecycle ingests/reconciles, so captured statements get real
`[^sN]` line locators and the wiki is never written directly (docs/capture.md also documents the
save-the-transcript-as-a-file lane for whole conversations). `rawsource.py` backs
`wiki_raw`/`citadel raw`: the provenance-gated, locator-aware reader for the raw source behind a
`[^sN]` citation (verify-only — the wiki stays the synthesized layer for retrieval).

## Conventions specific to this codebase

- **`config.*` is read at call time** (`from . import config` then `config.RAW_DIR`), never imported
  by value — so tests can monkeypatch the whole filesystem layout. Honor this when adding code.
  The WIKI path is read through the ACCESSORS (`config.wiki_dir()`, `index_path()`,
  `sources_index_path()`, `log_path()`, `manifest_path()`, `failures_path()`), never as
  `config.WIKI_DIR`: ingest redirects it per source through a ContextVar, so only the accessors see
  the staging copy. The module attributes stay the process-wide base tests monkeypatch.
- **Tests redirect everything to `tmp_path`** by monkeypatching `config.*` (including
  `WORKSPACE_ROOT`, which the agent's `cwd` reads) and replace `llm.run_ingest_session` with a fake
  that writes files into the temp wiki. No test spawns a real LLM CLI. Follow that pattern; keep
  tests offline.
- **Never hand-edit generated files** — `index.md`, `log.md`, any `*/index.md`, `sources/index.md`,
  `.citadel_viewer.html`, and `.citadel_ingested.json` are regenerated. The ingest agent prompt and
  `store.delete_page` both refuse to touch them. In the REPO, `.github/copilot-instructions.md` is
  generated too: it is THIS file with a swapped header (both agents get one instruction set, so a
  feature can't be documented for one and not the other). Edit `CLAUDE.md`, then regenerate with
  `CITADEL_WRITE_COPILOT_DOC=1 uv run pytest tests/test_packaging.py -k copilot -q`; the drift guard
  in `tests/test_packaging.py` fails the suite when the two disagree.
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
  `CITADEL_INGEST_MODEL` (passed as `--model` to EVERY backend - claude, copilot and agy all
  honor it; unset (the default) means "run the CLI's own default model"),
  `CITADEL_CURATE_MODEL` (model for `citadel curate` sessions; falls back to
  `CITADEL_INGEST_MODEL`), `CITADEL_LLM_TIMEOUT`, `CITADEL_HERMETIC` (session isolation — append claude's `--bare` when the
  installed binary advertises it, so personal `~/.claude` config never leaks into ingest; default
  on, probe-gated), `CITADEL_PAGE_CACHE` (the serve-side page snapshot cache: `auto` = on in
  `citadel serve` only, `1` = everywhere, `0` = never), the `CITADEL_HTTP_*` serving knobs
  (`TOKEN` — mandatory for `serve --http`, no default; `HOST`/`PORT`/`PATH` — loopback:8765/mcp;
  `READ_ONLY`), `CITADEL_LLM_VERBOSE`, `CITADEL_LLM_LOG_DIR`,
  `CITADEL_REPO_SUPPORT`, `CITADEL_IMAGE_SUPPORT` (read images visually), `CITADEL_AUDIO_SUPPORT`
  (opt-in whisper transcript ingest for audio/video, with `CITADEL_WHISPER_CLI`/
  `CITADEL_WHISPER_MODEL`/`CITADEL_WHISPER_TIMEOUT` tuning the seam), `CITADEL_JOBS` (how many sources ingest folds in
  concurrently; 1 = serial), `CITADEL_MAX_SOURCE_CHARS`
  (large-source chunking threshold), `CITADEL_RESUME` (resume checkpoints for those chunked
  sources: continue at the segment an interrupted run died on instead of re-paying for the earlier
  ones; default on), `CITADEL_DEDUP_BY_BASENAME` (skip same-basename document
  duplicates), `CITADEL_IGNORE_PATTERNS` (OS/junk-file globs skipped at discovery — `Thumbs.db`,
  `desktop.ini`, `~$` locks, …; a `+` prefix extends the built-in defaults),
  `CITADEL_MAX_SOURCE_BYTES` (the SIZE complement to those globs: a raw file bigger than this many
  bytes is skipped at discovery — never hashed, never tracked, but reported; 0 = no limit, the
  default; an explicitly named path always wins), `CITADEL_WIKI_LANG`
  (target language of all wiki prose, default `en`; verbatim quotes stay original),
  `CITADEL_PDF_MODE` (`text` | `images` — whether the agent also reads a PDF's figures),
  `CITADEL_PDF_TEXT` (`auto` | `1` | `0` — the pypdf text-layer pre-pass; auto = on when pypdf
  imports, which it does by default; `0` forces agent-native reading),
  `CITADEL_STYLE_PROFILES` (opt-in persona/style capture on `persons/` pages, default `0`),
  `CITADEL_WIKI_GIT` (wiki-history auto-commit after ingest/curate: `auto` acts only when the wiki
  dir is its own git repo, `1` also `git init`s it, `0` off) + `CITADEL_WIKI_GIT_REMOTE` (optional
  push target — remote name or URL), the
  `CITADEL_*_DIR` path overrides, `CITADEL_RAW_DIRS` (multi-root: a comma/newline-separated list of
  raw roots discovery walks; replaces the walk list when set, `CITADEL_RAW_DIR` stays the primary
  root), and `*_CLI_PATH` binary overrides.
