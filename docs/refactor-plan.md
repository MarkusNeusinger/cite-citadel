# cite-citadel — The Big Refactor: Target Design & PR Roadmap

Status: **proposed** (2026-07-01). Produced by an 11-agent audit of this codebase, deep reads of
`../idiolect`, `../anyplot`, `../kurrentschrift`, 4 web-research sweeps, and a 4-critic adversarial
review of the draft. This document is the single source of truth for the refactor; update it as PRs
land, delete it when done.

## Goals (owner's brief)

1. Clean pip-installable package (`pip install cite-citadel`), usable outside a checkout. KISS.
2. Prompts/rules centralized and separated from code: a core rulebook the agent always needs,
   plus file-type-specific and content-genre-specific rules (prose ≠ meeting minutes), cleanly
   configurable (PDF text-only vs with images; repos summary vs full). Assume agents keep getting
   better: describe tasks well instead of over-tooling; specialized tools only where needed.
3. A second lifecycle process besides ingest — **curate**: re-verify facts against sources, split
   overlong pages, re-sort information, apply changed rules without re-ingesting from zero.
4. `ingest --force`: deliberately re-read an already-ingested source and reconcile the wiki.
5. Multiple raw roots; fast discovery on slow network shares (today: full re-walk + full re-hash
   every run, including deletion detection).
6. Open-source-ready polish; an auto-triggering PR skill; multiple specialized test corpora
   (runnable individually or together), all centered on the hard guarantee: **no invented facts,
   every fact cited to raw/, contradictions and changes over time traceable, counterfactual source
   facts never "corrected" from model world knowledge.**
7. **Transparency & completeness**: it must always be visible which files were NOT imported (and
   why), and an imported source must verifiably be imported *completely* — no silently partial
   wikis. Citations should carry page/line locators where that adds precision. Everything stays
   OKF-conform.
8. **The idiolect vision folds in**: raw/ can hold first-person material (interviews, voice memos,
   letters, personal emails); ingest extracts not only facts but the person's *opinions* and
   *writing style* (attributed, cited), so an LLM using the wiki via MCP — or via equivalent CLI
   commands when MCP isn't available — can write texts and answers in that person's voice with
   their background knowledge. Windows and Linux behave identically throughout.

**Greenfield policy**: backward compatibility with existing wikis/manifests is explicitly NOT a
constraint. Old workspaces re-ingest or run `--full-rescan`; no migration tooling, no compat shims.
(Operational safety — never mass-delete provenance, never corrupt a live wiki — is not back-compat
and stays non-negotiable.)

## Verified audit baseline (what's broken / what must not change)

Broken or missing today (each independently verified against the code, several empirically):

- **pip install is silently broken**: the wheel ships only `citadel/*.py`; SCHEMA.md /
  AGENT_INGEST.md are not packaged; `config._resolve_repo_root` (config.py:27) falls back to
  `<venv>/lib/` in site-packages → phantom workspace, silent success. (Verified by building the
  wheel and installing into a clean venv.)
- **Prompt prose lives in 3 places** with duplication: `llm._build_instruction` (llm.py:91-336,
  ~245 inline lines; delete/repo/image/reconcile/segment variants are hardcoded Python),
  AGENT_INGEST.md, SCHEMA.md. Only the plain-`ingest` kind honors the "rules are data" promise.
  `config.AGENT_RULES_PATH` exists but is never used.
- **Discovery cost**: two full `os.walk`s per run; `manifest.is_pending` (manifest.py:147)
  sha256-hashes every already-ingested file every run; a pending file is hashed up to 3×; deletion
  detection adds one `.exists()` stat per manifest key. Manifest stores only `{sha256, model}` — no
  stat fast-path. `RAW_DIR` is strictly one directory.
- **No `--force`**, no curate, **no Python-side PDF handling** (PDFs are handed whole to the agent
  CLI, exempt from chunking; "with images" is one hardcoded prompt sentence), repo ingest has only
  summary mode.
- **store.py is 4 modules in one** (836 lines); citation/link/fence parsing is ~4× duplicated
  across store/validate/lint/viewer with real drift (lint and check disagree on `docs/` links and
  fenced links); `rebuild_indexes` does O(sources×pages×lines) twice; viewer.py is 1753 lines
  (~1300 of string-literal HTML/CSS/JS reaching into store privates).
- **Failed repo sessions and failed delete sessions never reach the failures catalog**
  (report.errors only — no `failures.record`).
- Tests: 271 offline tests, 83% coverage, but no conftest.py (the config-monkeypatch fixture is
  copy-pasted with drift across 7 files), test_ingest.py is a 2426-line monolith, and server.py
  (19%) / cli.py (33%) / `store.search()` (0 direct tests) are thin exactly where the refactor cuts.
- The demo corpus doubles as the repo's live `raw/` — conflicts with pip-install and multi-corpus.

**Load-bearing — preserve behavior-for-behavior, pinned by tests, never "simplified":**
staging→diff-by-hash→validate→promote all-or-nothing; `_robust_*`/`robust_mkdir` SMB hardening;
`okf.safe_join`; fence-aware link-rewrite safety nets; `write_page` canonicalization; paths-only
prompts (WinError 206); the rel-or-abs dual key space; per-source manifest persistence; never-raise
MCP tools; ASCII progress; the interrupt capture-finalize-reraise pattern.

## Idea steals (and explicit rejections)

- **idiolect**: evidence-quote discipline (→ Z6); prompts as versioned package data; manifest as
  per-source state (hash+model+rules stamp); curate framed as *bounded partial recompile* with a
  `--diff` report (idiolect spec'd it, never built it — we ship it first); `citadel doctor`.
  *Rejected*: SDK coupling, pydantic/typer/rich/jinja2 stack, embeddings retrieval, numeric
  confidence scores, append-only corrections/ (our reconcile is stronger).
- **anyplot**: the prompts/ tree shape (base task + per-specialization + shared quality contract),
  composition strictly by path reference (matches our paths-only invariant); spec-polish =
  blueprint for curate (improve-or-NOOP, hard invariants, attempt caps); "reviewer distills the
  rulebook into a checklist the repair pass consumes" → lint findings feed the curate prompt by
  path. *Rejected*: label state machines, numeric score cascades, workflow engine, any prompt kept
  "in sync" with another.
- **kurrentschrift**: the open-pr skill (trigger phrasing + mandatory-routing line in CLAUDE.md;
  hard gates; CI-watch loop; never merge); SKILL.md house style (runnable §§ with dated
  "Expected:" baselines, Gotchas = real incidents); verify-skill family pattern.
- **Research**: mem0's ADD/UPDATE/DELETE/NOOP vocabulary for reconcile/force/curate prompts and
  grading; GraphRAG/Letta precedent for curate as a separate verb; restic/borg/rclone/git scan
  discipline (size+mtime_ns equality-only, no inode/ctime on SMB, racy-timestamp guard, deletion
  via prior-listing diff **with positive confirmation**, no file watchers on SMB — document why);
  fabric/simonw-llm override layering; ConflictBank/ConFiQA/FaithEval corpus methodology
  (counterfactual substitution made mechanically greppable; misinformation/temporal/semantic trap
  taxonomy; coherent fictional clusters); FACTS-style two-phase gate (check+lint eligibility, then
  content grading); Wikipedia-bot two-layer loop (offline detectors decide WHAT, agent decides HOW;
  revert-and-stop). Verified README differentiators: enforced citation grammar + check gate,
  all-or-nothing promotion, deletion reconciliation, offline lint, no embeddings store — no
  surveyed system has them.

---

## Target design

### Z1 — Workspace model (`citadel init`)

- `citadel init [DIR]` scaffolds: `citadel.toml` (**pure marker** — at most a format-version line,
  never config), `.env` from a packaged template, `raw/`, `wiki/`, and an **empty** `rules/` with a
  commented `rules/local.md` stub.
- **One config system**: everything stays `CITADEL_*` env vars + auto-loaded workspace `.env`.
  Precedence: process env > workspace `.env` > packaged defaults. Multi-root =
  `CITADEL_RAW_DIRS` as a separator-split env value (the `_parse_ignore_patterns` precedent).
  No TOML config, no second precedence chain. Tests keep monkeypatching `config.*`.
- Workspace discovery: `CITADEL_WORKSPACE` env override, else walk up from CWD for
  `citadel.toml`. **Env-vars-only workspaces remain fully valid** (no marker needed when
  `CITADEL_*_DIR`s resolve) — existing setups and MCP `citadel serve` launched from arbitrary CWDs
  keep working; the README migration note tells MCP hosts to set `CITADEL_WORKSPACE`. Fail loud
  only when *neither* marker nor env vars resolve. The dev checkout gets a marker and stays a
  workspace. The `_resolve_repo_root` pyproject-walk dies.
- Rules resolution: two layers, first-hit-wins per filename: workspace `rules/` > packaged
  `citadel/rules/` (importlib.resources; real files in site-packages, referenced by absolute path).
  `rules/local.md`, if present, is always appended as one more path (additive customization,
  upgrade-safe). A user who wants to fork a default copies that one file (`citadel rules show|eject
  <name>` as convenience). **No rules.lock, no `--update-rules`, no `.md.new` machinery** — a
  copied file is owned by the user; everything else updates with pip.
- **Key-space stability invariant**: manifest header records the workspace root identity;
  refuse to run (fail loud) when the discovered workspace differs from the manifest's — nested
  markers shadow outer ones and must not silently re-key sources (the error suggests
  `--full-rescan` / re-init; greenfield, so no migration path). Pinning test: the nested-workspace
  case.
- Agent cwd = workspace root. `_external_dirs` (and the gemini `--include-directories` path)
  **always grants the resolved packaged-rules directory**; a prompt-validation test asserts every
  rule path referenced by a built prompt is inside cwd or a granted dir.

### Z2 — Rules tree (package data `citadel/rules/`)

```
citadel/rules/
  schema.md        # OKF page format, folder routing, citation grammar, grounding/quality contract
  core.md          # generic agent behavior (from AGENT_INGEST.md's generic parts)
  tasks/ingest.md  tasks/reconcile.md  tasks/delete.md  tasks/curate.md    # lifecycle axis
  formats/repo.md  formats/image.md  formats/pdf.md  formats/office.md    # Python-detectable
  genres/prose.md  genres/meeting-minutes.md  genres/email.md
  genres/first-person.md                     # agent-judged content — a STARTER SET, not a taxonomy
  README.md        # index table: file → purpose (anyplot pattern)
```

- **Two shared files only** (schema.md + core.md); the quality contract (no invented facts,
  counterfactual preservation, contradiction handling) stays *inside* schema.md where it lives
  today — no third always-read file, no duplication.
- **Two orthogonal type dimensions, two different deciders** (this is the owner's three-tier
  distinction made structural):
  - `format` — structurally detectable in Python (repo markers, image/office extensions, PDF
    magic): code selects `formats/<x>.md`. A minutes .docx composes `formats/office.md` +
    `genres/meeting-minutes.md` (paths-only composition already supports N files).
  - `genre` — a **content judgment the agent makes**: `tasks/ingest.md` instructs "if the source
    reads like meeting minutes / an email thread / prose, also read and follow `genres/<x>.md`"
    (today's "judged from CONTENT, not name" rule, generalized). No applies-to glob engine, no
    per-path override table. The chosen genre is **stamped into the manifest at first ingest and
    reused on reconcile/force**, so later sessions can't silently reclassify and churn pages.
    *(PR3 deviation: no manifest genre stamp shipped — the agent has no return channel to report
    its judgment; instead `tasks/reconcile.md` instructs keeping the genre treatment already
    visible in the wiki, which serves the same no-churn goal.)*
  - **The shipped genre files are examples, not a fixed taxonomy** (owner clarification): the
    prompt enumerates whatever the *effective* `genres/` directory contains at prompt-build time —
    a genre file dropped into the workspace `rules/genres/` participates automatically, no code
    change. The agent applies none, one, or several by content; a source matching no genre file
    simply follows core rules. Adding "lab-notebook.md" or "support-tickets.md" later is a
    one-file act.
- **`genres/first-person.md` carries the idiolect vision — as an opt-in** (goal 8, owner
  clarification): persona/style capture is a mode, not a default. `CITADEL_STYLE_PROFILES=0|1`
  (default **0**): off, first-person sources still yield facts as usual — including attributed
  positions where they *are* the fact ("X decided/argued …"[^sN]) — but no style profiling; when
  collecting documents from many people in a company, every second document has a different,
  irrelevant style. On, the genre additionally extracts the person's **opinions and preferences**
  as attributed, dated, cited statements that schema.md distinguishes from world facts, routed
  onto `persons/` pages, and **writing-style observations** (voice, register, idiom, recurring
  phrases), each backed by verbatim cited examples, on a per-person style page. Pure rules-layer
  work — the knob only decides whether the style sections of the genre file are referenced; the
  MCP server (and the CLI equivalents, see Z11) then serve enough for an LLM to write in that
  person's voice with their background knowledge. schema.md gets an "opinions & style" convention
  section so the distinction is OKF-conform and lint-visible.
- **Wiki target language** (owner requirement): `CITADEL_WIKI_LANG` (default `en`). All wiki prose,
  page titles, headings, and tags are written in the target language **regardless of the raw
  sources' languages — including mixed-language corpora**; the language is passed as a
  variables-bullet and enforced by one core.md rule. Two deliberate exceptions keep provenance
  honest: **verbatim quotes stay in the original language** (a translated "quote" is no longer
  verbatim — and Z6's future quote verification must string-match the raw file), and proper
  names/technical terms are never translated. Where a fact's phrasing matters, the page may give
  the original-language wording alongside the translation, cited as usual. lint treats language
  purely advisorily (no offline language detection — KISS).
- No frontmatter `guards:`/`version:` bookkeeping. If a specific sentence must be pinned, a plain
  grep-in-test suffices. `rules_version` = a **runtime content hash of the effective rules files**,
  stamped per source into the manifest (zero manual maintenance; this is what curate's
  `--stale-rules` compares).
- `llm._build_instruction` shrinks to the code-invariant frame: path resolution,
  variables-as-bullets (SOURCE, WIKI, RAW, READ_PATH, SEGMENT part/total, FALLBACK_DATE),
  off-limits generated-files list, "run `citadel check` before finishing". Everything
  task/format/genre-specific becomes "Read <absolute path> and follow exactly". Paths-only stays;
  every (lifecycle × format) prompt variant Python can emit gets a <3000-char argv guard test.
- Config knobs select *which* rule file/section is referenced, never templating:
  - `CITADEL_PDF_MODE=text|images` (images degrades to text with a logged warning on CLIs without
    PDF vision). PDFs remain unchunked by design — agent-side reading; document the practical size
    ceiling in formats/pdf.md. *(PR3 deviation: the degrade-warning is deliberately not implemented —
    there is no reliable capability probe for a CLI's PDF vision; formats/pdf.md and env.example
    document the caveat instead, and a doctor advisory lands in PR9.)*
  - `CITADEL_REPO_MODE=summary|full` — **full mode is deferred** (post-roadmap). Design sketch when
    it comes: digest without the scoring cutoff, mandatory multi-segment folding via the existing
    segment machinery, same repo-reconcile diff behavior. Summary stays the default; repo.py's
    scoring policy prose moves into formats/repo.md.
  - Office-embedded-image viewing decoupled from `CITADEL_IMAGE_SUPPORT`.
- Repo-root SCHEMA.md/AGENT_INGEST.md become thin pointers for GitHub readers (or are deleted);
  README/CLAUDE.md updated. Open-Points status vocabulary (hardcoded EN/DE regexes) moves to rules.

### Z3 — Discovery: incremental scan + multi-root

- Manifest entry grows to `{sha256, model, rules_version, genre, size, mtime_ns}` — **the manifest
  is the scan cache** (no second cache file). Quick check = exact (size, mtime_ns) match → skip
  hashing; any mismatch or miss → stream-hash exactly once (sha passed through to `mark_done`).
  sha256 stays the sole arbiter of "changed".
- **Duplicate/unreadable/failed sources get stat+sha recorded in the failures catalog entries**
  so they join the quick check — otherwise every dedup-dropped .pptx twin is re-hashed forever
  (the audit's "0 reads on unchanged corpus" test is only satisfiable with this).
- One iterative `os.scandir` walk (DirEntry.stat is free on SMB directory listings) replaces
  `_walk_files` + `_repos_under`; the redundant per-candidate `is_file()` stat dies.
- **Deletion detection — candidates, then positive confirmation** (the critic-panel blocker fix):
  candidates = manifest keys *under a root that was actually walked this run* − seen-set. Each
  candidate is then **confirmed with `.exists()`** before any delete session (cost ∝ normally-empty
  candidate set, so the O(manifest) sweep still disappears). Keys under *no* configured root are
  never swept (logged instead). **Any scandir error anywhere in the walk aborts the entire deletion
  sweep** for that run. Unreachable-root guard: a root that doesn't mount / errors at top level
  produces zero deletions for its keys — an unmounted share must never read as "user deleted 5000
  sources".
- Racy-timestamp guard (git model): distrust the quick check for files whose mtime_ns is at/after
  the recorded per-entry `hashed_at` **taken from the source file's own stat clock at hash time**
  (never the manifest write time — wiki and raw may sit on different servers with skewed clocks),
  minus a 3s SMB/FAT window. mtime compared as an opaque equality token, never ordered. No inode,
  no ctime (unstable on SMB — document with the restic/borg references). No file watcher —
  inotify/SMB CHANGE_NOTIFY can't be trusted; document why.
  *(PR4 deviation on ctime: a freshly-ingested file is by definition inside the racy window
  (hashed moments after its last write), so the pure window rule would re-hash every new corpus
  once per run forever — "0 reads on an unchanged corpus" is unsatisfiable under it. The shipped
  guard records `ctime_ns` as ONE MORE OPAQUE EQUALITY token (git's own index does the same):
  ctime equality — which userspace cannot forge on POSIX — proves nothing changed since the hash
  and short-circuits the window; entries without a recorded ctime (hand-seeded/pre-PR4) fall back
  to the pure `hashed_at` window. Still never ordered, still no inode; an unstable SMB ctime
  degrades to a harmless re-hash because sha remains the sole arbiter. Windows caveat, same as
  git there: `st_ctime` is creation time, so a backdated same-size rewrite is invisible to stat —
  `--full-rescan` or any real mtime change surfaces it.)*
- Multi-root: `CITADEL_RAW_DIRS` (list env var); keys use the existing rel-or-abs discipline;
  deletion sweep scoped per root. *(PR4 addition: a byte-identical file in a second root is
  recognized as a duplicate against the SAME RUN's pending set too — one agent session, both keys
  tracked — extending the manifest-only move/duplicate detection to the cross-root drop case.)* The five hardcoded `'raw'`/`'docs'` literals (store.py:175/207,
  lint.py:180, viewer, config.display_key) collapse into one config-aware `is_source_citation`
  predicate (lives in grammar.py, see Z7; refined during PR3.5 into the config-aware predicate
  plus its config-free lexical twin `resolves_to_source` for the byte-stable rewriters — do not
  re-collapse them). **Citation form per root class is specified**: citations
  into sibling roots stay relative links; non-sibling/out-of-repo roots are cited by absolute posix
  path in the footnote definition (validate/check accept it via `source_path_for_key` — the
  mechanism already exists for out-of-repo dirs; on Windows a cross-drive relative path cannot even
  be written). Pinning test: a page citing root #2 passes check/lint and survives rewrite/rebuild.
- `citadel ingest --full-rescan`: distrust the cache, rehash everything (no re-ingest on sha match).
- Pre-refactor manifests (greenfield, no compat duty): entries without stat fields simply rehash
  until `--full-rescan` re-stamps them; a backfill-and-save on first contact is a nice-to-have
  one-liner, not a requirement. A full-rehash run announces itself in progress output so a big SMB
  run doesn't look hung.
- Behavior-pinning tests FIRST: key stability across root add/remove; cross-root same-content
  files; unreachable root ≠ mass delete; path-scoped ingest of an out-of-root file followed by a
  full run must not delete it; file-open counter (unchanged corpus without duplicates/failures ⇒ 0
  content reads).

### Z4 — `ingest --force`

- A flag threaded to `_partition_sources` that skips the `is_pending` short-circuit; a forced
  sha-matching file lands in `pending` and takes kind=reconcile automatically via the existing
  `changed_keys` logic (verified at ingest.py:1291/1382) — never plain ingest.
- **Repos**: do *not* force `old_commit=None` (that yields kind="repo", a first-time brief that
  would duplicate pages). Instead a force flag on the repo job runs **kind="repo-reconcile" with a
  full re-digest (`only=None`) and no change summary**.
- Decided semantics: `--force` clears a persisted UNREADABLE/ERROR failure record and retries;
  `--force` on a dedup-dropped key ingests exactly the requested file (bypassing `_dedup_rank`) and
  records the divergence; no deletion sweep on path-scoped force runs; manifest re-stamped with
  current model + rules_version + genre.
- `tasks/reconcile.md` gets a forced-re-read note: "the source may be unchanged — re-verify the
  wiki's facts against it and apply the current rules" (otherwise the agent hunts for a source diff
  that doesn't exist).
- *(PR5 decisions: (a) `citadel ingest --force` with NO explicit paths is REFUSED (exit 2, ingest
  never called) — the flag was ambiguous here, and a whole-corpus re-read (one agent session per
  source) must never happen by accident, so force requires naming the sources (pinned by
  test_cli.py). (b) The dedup-bypass divergence is recorded through the report's existing
  `duplicates` channel — the pair names the kept sibling the wiki now deliberately holds alongside;
  no DUPLICATE failure is persisted for a forced key. (c) No genre stamp, per the PR3 deviation —
  force re-stamps model + rules_version.)*

### Z5 — `citadel curate`

Separate verb (GraphRAG/Letta precedent), two layers (Wikipedia-bot model), **no persisted queue**:

1. **Offline detectors** (lint extensions, pure and offline): recompute the work list from the
   wiki at the start of every run — the wiki IS the database; a persisted queue would be a second
   source of truth with staleness bugs. Detectors: rules_version drift; page length (soft ~400 /
   hard ~800 lines); unresolved contradictions; orphans; per-page `[^llm]`:`[^sN]` drift ratio;
   stale×in-degree sampling for fact re-verification; **re-sort detectors** (type↔folder mismatch
   via `okf.folder_for_type`, oversized `misc/` pages, "reorganize this cluster" items) — the
   owner's "Information umsortieren" made concrete. Deterministic fixes (link rewrites, index
   rebuilds) are applied directly, not queued.
2. **Agent layer**: one staged session per page cluster (page + its cited raw files + direct link
   neighbors). Prompt = `tasks/curate.md` + the run's findings written to a temp file and
   referenced **by path** (anyplot's "review distills the rulebook into a checklist" pattern).
   Hard invariants: never invent, never break `[^sN]` provenance, preserve counterfactuals as
   stated, re-sorting allowed. Improve-or-NOOP is mandatory. **The staging diff-by-hash is the
   single result arbiter** (empty diff = NOOP, clean diff = applied, exception/check-fail = failed)
   — no machine tokens, no second result channel. Reuses staging→validate→promote unchanged.
   Failed clusters land in the existing failures catalog with an attempt count; attempt-capped,
   never auto-retried (revert-and-stop). One edit-summary line per applied batch in log.md.
- CLI: `--dry-run` (print the recomputed plan, zero tokens), `--limit N`, `--stale-rules`,
  `--diff report.md` (the idiolect steal), `CITADEL_CURATE_MODEL` (cheaper model knob).
- Fact re-verification is pre-filtered offline via manifest shas: source changed → that's
  reconcile; source gone → that's delete; only sha-unchanged sources need the agent entailment
  pass.
- MCP: add `wiki_lint` (the curate driver is genuinely useful to external clients) and tool
  behavior annotations. The raw-source reader / per-page validate / force flag move to a small
  follow-up PR — the curate agent is a CLI session with file tools and reads raw/ directly.
- *(Shipped in PR6: detectors + recompute-per-run plan (`curate.py`), the `--dry-run`/`--limit`/
  `--stale-rules`/`--diff` driver, attempt-capped revert-and-stop cluster sessions on the existing
  staging machinery, `CITADEL_CURATE_MODEL`, and the Z6 `locator` detector (via
  `lint.check_locators`, shared with `citadel lint`). `wiki_lint` + `readOnlyHint`/`destructiveHint`/
  `idempotentHint`/`openWorldHint` annotations on all eight MCP tools, and the CLI
  `read`/`index`/`sources` parity subcommands + parity test, ship here too. Deviations: `curate`
  does NOT re-stamp a re-grounded source's manifest `rules_version` (that field means "rules the
  IMPORTING session ran under"; curate operates on pages, not imports), so a `rules_version_drift`
  cluster re-plans until a real reconcile/`--force` re-ingest — mitigated by the mandatory
  improve-or-NOOP (a second clean pass is a NOOP, no wiki churn); the stale×in-degree re-verify
  sampling IS wired (reason "reverify", top-K by staleness × in-degree+1); only the
  `oversized misc/` re-sort variant remains unwired.)*

### Z6 — Provenance precision: citation locators now, evidence quotes later

- **Locators (ships with the rules split, PR3)**: the `[^sN]` footnote *definition* grammar gains
  an optional locator after the source link — `p. 12` / `pp. 3-5` for paginated formats
  (PDF/Office), `line 40` / `lines 40-52` or a `§ Heading` anchor for text files. OKF is not
  affected (verified: OKF prescribes only the frontmatter contract; the citation convention is
  this repo's SCHEMA.md layer). Rules *require* locators where they add real precision (PDF,
  Office, long texts over a threshold) and leave them optional for short sources. Because `raw/`
  is immutable and a changed source always passes through reconcile, line locators are not brittle
  here — reconcile's rules include "re-check locators of this source". lint deterministically
  verifies line/heading locators against text-bearing raw files (out-of-range line, missing
  heading = warning); page locators for PDFs stay agent-verified (no Python PDF reader by design).
  Corpora grade that locators point at the planted evidence.
- **Evidence quotes (parked, post-roadmap)**: optional verbatim quote (≤ ~300 chars) in the same
  footnote definition; required by genre rules for text-bearing sources only (a quote from a
  PDF/image cannot be string-verified offline — scope the claim honestly); deterministic lint
  check string-verifies each quote against its raw file, making "no invented facts"
  offline-checkable and curate's re-verification grep-first. Decide go/no-go after the corpora
  exist, based on how much of the real corpus is text. Locators land first because they're cheap
  and quotes compose with them (`raw/foo.md, lines 40-52: "…"`).

### Z7 — Storage-layer hygiene

- **grammar.py** (early, see roadmap): the one shared home for citation/link/fence parsing, the
  footnote/LLM-marker regexes, the fence-aware prose-line iterator, and the new
  `is_source_citation` predicate. store/validate/lint/viewer migrate to it; the lint-vs-check
  divergences (docs/ links, fenced links) get decided explicitly and tested.
- store.py splits along its four responsibilities (core CRUD/search; linkgraph; catalogs;
  open_points); everything the viewer imports as `store._private` becomes public API.
- `rebuild_indexes` builds one key→citing-pages map per traversal and reuses it (kills the
  2×O(sources×pages) scans).
- `write_page` gets `delete_page`'s reserved-name guard (essential before curate writes pages
  programmatically); "Generated — do not edit" notice lands in top-level and per-folder index.md.
- viewer → `citadel/viewer/` subpackage with real `template.html`/`app.css`/`app.js` package-data
  files; `build_bundle` stays the pure test seam; the Python↔JS resolver parity is covered by a
  **golden test on the built bundle** (no JS runtime in the test suite).
- extract.py: OOXML stays core; the ~200-line OLE/CFBF salvage becomes an isolated lazy submodule.
- **Quick fix, promoted out of the cleanup list (ships early, ~5 lines + regression test): failed
  repo sessions and failed delete sessions must call `failures.record`** so they surface under
  "Could not ingest".
- Cleanups: dead config (MAX_DIGEST_CHARS/DIGEST_TOP_N/DIGEST_CANDIDATE_N), `_sha256` duplicate,
  `_office_write_temp` rename, ingest()'s three near-duplicate loops → SourceJob abstraction,
  8-tuple → dataclass, `__version__` via importlib.metadata + `citadel --version`.

### Z8 — Packaging / CI / OSS

- pyproject: PEP 639 license, dynamic version, 3.14 classifier, drop the duplicated dev-deps table,
  sdist excludes (.claude/, .github/, uv.lock, demo wiki, CLAUDE.md, wrapper scripts).
- CI adds: **wheel-smoke job** (uv build → twine check → clean venv → `citadel --version` +
  `citadel init` + `citadel check` from a temp CWD — the regression test for the whole
  phantom-workspace bug class), **windows-latest + macos-latest runners** (the SMB/Windows
  hardening is currently never exercised on Windows in CI), Python 3.14, pytest-cov, dependabot.
- **release.yml lands early** (PR2): v* tags → PyPI Trusted Publishing. The PyPI name is verified
  unregistered — reserve it promptly; **tag v0.1.0 right after PR3** (workspace + final rules shape
  stable), v0.2.0 after the polish PR.
- `citadel doctor`: workspace found, rules resolve, agent CLI on PATH, raw roots reachable,
  manifest parses, ANTHROPIC_API_KEY billing-shadow warning (the idiolect steal, now scheduled).
- README: lead with `pip install cite-citadel` + `citadel init my-wiki`; badges; the verified
  differentiators section; installed-form MCP config (`command: citadel, args: [serve]` +
  `CITADEL_WORKSPACE`); fix the stale "injected verbatim" claim (README.md:84). Add
  CONTRIBUTING.md, CHANGELOG.md (Keep a Changelog), SECURITY.md, docs/configuration.md (config
  reference for pip users who never see .env.example).
- Demo move (see Z9): repo-root `raw/` moves to `corpora/beverages/raw/`; the committed demo wiki
  is **regenerated fresh** under the final rules (greenfield — no move-migration dance; a fresh
  ingest also makes the showcased wiki demonstrate the refactored system, locators included).
  Repo-root raw/ becomes a gitignored user workspace **in the same PR**; retarget the Pages
  workflow AND ci.yml's "lint the bundled wiki" step (easy to miss). Gate the PR on
  `citadel check` + `lint` + the verify-corpus grade over the regenerated corpus.
- Wrapper scripts citadel.cmd/.ps1: keep as documented dev-checkout conveniences, excluded from the
  sdist; `uv tool install cite-citadel` / pipx is the promoted path.
- wiki/.citadel_failures.json: gitignored (decided — it's derived per-machine state).

### Z9 — Tests & corpora

- `tests/conftest.py` first: `tmp_citadel` fixture (union of all config monkeypatches — designed
  as a **thin seam**: tests depend only on its interface, PR2 swaps its internals), `seed_page`,
  `fake_agent` factory; delete the 7 drifted fixture copies; split test_ingest.py along its `# ---`
  markers into ~7 files; close the coverage gaps (server's 7 tools incl. the never-raise contract,
  cli dispatch/exit codes, `store.search`).
- **Three shipped corpora** (not six — traps for the other genres are planted as files *inside*
  these; split one out only when combined grading proves too coarse):
  1. `corpora/beverages/` — the existing coffee+tea corpus, moved.
  2. `corpora/counterfactual-atlas/` — the direct test of the hardest guarantee: a coherent
     fictional world (ConFiQA-style cluster: fictional org + founder + dates + products) whose
     facts contradict real-world knowledge; graded that they appear **as stated, cited, never
     corrected**. Counterfactual values are mechanically greppable: planted value present with the
     right `[^sN]` = PASS; the true-world value appearing anywhere without `[^llm]` = FAIL (it
     exists nowhere in raw/, so its presence proves fabrication).
  3. `corpora/project-history/` — one fictional project over 3 years as **meeting minutes AND
     emails** (the owner's corpus, as asked), ingested in dated waves via `stages/` overlay drops
     with reconcile between waves — the only end-to-end exercise of reconcile/delete/--force.
     Graded per wave: superseded value survives only as a dated, cited, superseded statement;
     silently deleted old value = FAIL; old value still presented as current = FAIL; `--force` on
     an unchanged source diffs to NOOP. A slice of the minutes/emails is **German** while the
     corpus ingests with `CITADEL_WIKI_LANG=en` — graded that the wiki is uniformly English with
     the German-sourced facts intact, cited, and traceable. The emails double as the
     **first-person genre test** (run with `CITADEL_STYLE_PROFILES=1`): planted opinions and
     stylistic quirks per sender must land as attributed, cited opinion/style entries on the right
     `persons/` pages — an opinion presented as a world fact = FAIL; a second run with the knob
     off must yield facts only.
  - Trap taxonomy per corpus (ConflictBank): misinformation (sources disagree), temporal (dated
    change), semantic (one term, two meanings).
- **Grading stays two files per corpus** (the shipped verify-example pattern, proven): a
  `ground-truth.md` answer key — **the corpus's description file (owner requirement): it
  enumerates every deliberately planted error, contradiction, counterfactual, and load-bearing
  fact**, with the greppable values, expected citations/locators, and hard/soft criteria (sections
  A-H schema) — plus the parameterized **verify-corpus skill** (`verify-corpus <name>|all
  [--grade-only]`) that checks each planted item is really present in the generated wiki. Phase 1
  eligibility = `citadel check` + `lint` exit 0; phase 2 = answer-key grading. Mode A ingests into
  a per-corpus sandbox (never moves the live wiki aside). No checks.yaml DSL, no standalone
  scorer, no scorecard persistence — ingest is non-deterministic, so mechanical checks are content
  greps the skill already runs. **Ground truths live under .claude/skills/, never inside or beside
  the corpus raw/ — the ingest agent must not be able to see them** (defense in depth: the e2e run
  also points `CITADEL_RAW_DIR` at the corpus raw/ only).
- Prompt-validation tests: every rules file exists and parses; every (lifecycle × format) variant
  Python can emit stays <3000 chars; every referenced rules path is inside cwd or a granted dir.

### Z10 — Skills (.claude/)

- **open-pr** (ships with the roadmap): trigger "Use when asked to open or create a PR, commit and
  push, ship a change, or finish up a change — even if they do not say the word skill"; hard gates
  = `uv run pytest -q`, `ruff check .`, `ruff format --check .`, `python -m citadel lint`; a
  diff-routing table (changes to ingest.py/llm.py/rules/ → run verify-corpus first — this absorbs
  the write-rules idea); branch `claude/<topic>-<slug>` off main; `gh pr create` ready-not-draft;
  CI-watch fix loop; stop at green with the PR URL; never merge. Plus a "Self-verification
  (feedback loops)" section in CLAUDE.md: "Routing is mandatory, not advisory."
- **verify-corpus** (parameterized family replacing verify-example, per Z9).
- Deferred until a recurring need shows: /prime, audit-provenance (run once manually pre-publish),
  optimize-skills, optimize-ingest. House style for any new skill: 100-200 lines, numbered §§ of
  runnable bash with dated "Expected:" baselines, Gotchas = real incidents, cheap Mode-B path.

### Z11 — Transparency, completeness & MCP/CLI parity

- **No silently partial imports (goal 7)**: today a chunked large source promotes each segment to
  the live wiki as it completes (ingest.py:1421-1447) — a mid-source failure leaves a live,
  half-folded source that only the failures list hints at. Greenfield fix: **all segments of one
  source fold into a single staging copy; promotion happens once, after the last segment passes** —
  the live wiki only ever contains fully imported sources. Trade-off accepted and documented: a
  failure at segment N discards N-1 segments' agent work for that run (retry next run); the
  all-or-nothing guarantee is worth more than salvaged partial passes. *(Shipped in PR5: one
  staging copy per source across all segments, validation after every segment (fail fast),
  exactly one promote after the last.)*
- **`citadel status`**: one command answering "what state is my corpus in" — per source: ingested
  (date, model, rules_version, genre, segments), failed (reason, attempts), skipped-duplicate (in
  favor of which file), ignored (which pattern), pending. Same data enriches the generated
  `sources/index.md` ("Could not ingest" already exists; add the positive side: every ingested
  source with its provenance stamp). The PR1 failures-catalog fix (repo/delete sessions) feeds
  this. *(Shipped in PR6: `status.py` renders ingested — model + rules_version + a `(stale)` flag
  when the stamp predates the current rulebook — / failed — reason + attempts — / skipped-duplicate
  / ignored / pending, from the manifest + failures catalog + one stat-only walk, never re-hashing.
  Deviation: the `date` / `genre` / `segments` / forced-alongside columns are NOT shown — the
  manifest records neither an ingest wall-clock time nor a segment count nor a genre stamp, so they
  are omitted rather than fabricated; the `sources/index.md` enrichment is left as a later cheap
  add.)*
- **Full MCP↔CLI parity (goal 8)**: verified gaps — `wiki_read`, `wiki_index`, `wiki_sources`
  have no CLI counterpart today. Add `citadel read <page>`, `citadel index`, `citadel sources`
  (thin wrappers over store, like the existing subcommands), so an AI without MCP access can do
  everything through the CLI. A parity test asserts every MCP tool has a CLI equivalent (and vice
  versa where it makes sense — `lint`/`view` stay CLI-only by design, `wiki_lint` closes the gap
  from the MCP side). Document the CLI-as-MCP-fallback pattern in the README.
- **Windows = Linux everywhere**: already a convention (UTF-8 forcing, ASCII progress, robust_*);
  the Windows CI runner (Z8) makes it enforced instead of promised. New code (locators, status,
  scandir walk, init) lands with Windows-path tests.

### Z12 — Licensing, third-party-CLI terms & OSS legal hygiene

Prompted by the public-release / PyPI question: *can shelling out to `claude`/`copilot`/`gemini`
create a licensing problem?* **Assessment (engineering, not legal advice — see the disclaimer at the
end of this section): the risk looks low because the shell-out design steers clear of what the
CLIs' terms actually restrict, so the work here is docs/metadata with zero product code.** The
load-bearing part is a set of **verifiable technical facts** (checked against `llm.py`), not a legal
opinion: cite-citadel bundles no provider code and no LLM SDK (runtime deps are only `mcp` +
`pyyaml`), embeds no credentials, reimplements no backend endpoint, and never reads or forwards an
OAuth token — it does `shutil.which(<cli>)` + `subprocess` on the **official binary** the user
installed and logged into, with a paths-only prompt. Those facts line up with the two things the
vendor terms restrict — *redistributing the CLI's code* and *extracting its token for a third-party
client* — neither of which cite-citadel does; calling a vendor's own CLI programmatically is the use
each ships it for (scripted / CI). We keep **MIT** (a subprocess call to a user-installed binary is
ordinary interop, not the kind of bundling that would pull another license in). Definitive licensing
conclusions across jurisdictions are for counsel, not this doc. **Everything in this section — and
the notices it plans — is informational, not legal advice; the release checklist includes a
maintainer (and, if warranted, counsel) review of the final wording before the repo goes public.**

**Deliverables (all documentation/metadata; fold into PR9, gate-free — not a blocker for the v0.1.0
wheel, but MUST land before the repo is flipped public / announced):**

- **Affiliation & trademark disclaimer** — a `NOTICE.md` at repo root plus a "License & third-party
  tools" section in the README (the README ships as the PyPI long-description, so the notice reaches
  PyPI without touching `license-files`, which stays LICENSE-only). Text: not affiliated with,
  endorsed by, or sponsored by Anthropic, GitHub/Microsoft, or Google; "Claude", "GitHub Copilot",
  and "Gemini" are the respective owners' trademarks, named only to identify the user-supplied CLI.
  **Packaging guard**: keep `cite-citadel`/`citadel` and the pyproject `name`/`description`/`keywords`
  free of any vendor mark (they already are) — a one-line test asserts it so a later rename can't
  smuggle one in.
- **Bring-your-own-CLI terms note** — one paragraph in the README and `docs/configuration.md`:
  ingest runs *your* authenticated CLI under *your* account, and that usage is governed by that
  provider's terms (Anthropic Consumer/Commercial Terms, GitHub Copilot Product-Specific Terms,
  Google Gemini / Code Assist ToS), not by cite-citadel; cite-citadel calls the official binary only
  and does not proxy, store, or transmit credentials. Include the honest caveat: heavy / unattended
  / CI ingest against a **consumer subscription** may hit rate limits or a provider's automated-use
  expectations — for that scale prefer the tier the provider designates for programmatic use. Refine
  the current README line ("uses your existing subscription … needs no API key") to link this note
  rather than stand alone.
- **Output-ownership one-liner** — README: the generated `wiki/` is the user's; Anthropic (and
  peers) assign output rights to the user, and cite-citadel claims nothing over wiki content —
  reassurance for anyone publishing the resulting wiki.
- **SECURITY.md data-flow note** (extends the Z9 SECURITY.md): cite-citadel spawns the CLI as a
  subprocess in the workspace; raw content is read by your CLI under your account and travels
  wherever that provider's terms say (some CLIs may retain prompts/logs per provider terms — the
  linked terms note carries the specifics, kept out of this durable doc so a provider policy change
  can't date it). cite-citadel itself reads, logs, or transmits no secret. Privacy heads-up: a
  `CITADEL_LLM_LOG_DIR` transcript can contain source content — it is local-only; recommend keeping
  it out of version control.
- **`.env.example` header pointer** — one comment line: ingest uses your logged-in CLI under your
  account; see the README "License & third-party tools" section for terms.
- **`citadel doctor` cross-ref** (the Z8 billing-shadow warning): doctor already warns when a
  provider API key sits in the environment while `CITADEL_LLM_CLI=claude` (ingest may then bill the
  API instead of the subscription) — cross-reference the terms note so the subscription-vs-API story
  is told once.

**Rounding out the public-release legal surface (still all docs/metadata):**

- **Dependency-license check** — confirm the whole shipped tree is permissive so nothing copyleft
  rides along under the MIT wheel: runtime `mcp` (MIT) + `pyyaml` (MIT), dev-only `pytest`/`ruff`
  (MIT). An optional `pip-licenses` / uv-based CI step documents it (KISS: a one-off manual check is
  enough for now). Note that `mcp` is the **open** Model Context Protocol SDK, not a proprietary
  Anthropic client — depending on it creates no vendor-ToS tie.
- **Example-corpus & docs provenance — mostly already clean; verify it stays.** The demo `raw/` is
  synthetic (fictional brands — `aurora-coffee`, `thornbury-tea` — plus generic coffee/tea guides),
  safe to publish. `docs/okf-reference.md` and `docs/karpathy-llm-wiki.md` already carry
  "Source / attribution" blocks (Google's OKF blog; Karpathy's gist) framing themselves as
  paraphrases — **keep those blocks intact** when the docs move/update. Keep any new corpora (Z9's
  counterfactual-atlas / project-history) original/synthetic so nothing third-party-copyrighted ever
  ships in `raw/`.
- **CONTRIBUTING: inbound = outbound** — state that contributions are accepted under the same MIT
  license (a one-line inbound=outbound clause; optionally a DCO `Signed-off-by`). KISS — no CLA.
- **Data-governance caveat (strengthen the terms note + SECURITY.md)** — because ingest sends raw
  content to the user's CLI/provider, warn against ingesting confidential/regulated material on a
  plan whose terms permit training on inputs; the user picks the plan/tier appropriate to their data
  sensitivity. This is the user-facing complement to the "cite-citadel transmits no secret itself"
  fact.

**Roadmap:** no new PR — appended to **PR9 (OSS polish + skills)**; no code, no test gate, no effect
on the v0.1.0/v0.2.0 tags beyond "the public-repo flip waits on the disclaimer + terms note
existing".

---

## PR roadmap (order = dependencies; each PR gated by the open-pr rules once the skill exists)

| # | Scope | Notes |
|---|-------|-------|
| 1 | **Test foundation** | conftest.py (`tmp_citadel` as thin seam), test_ingest split, coverage for server/cli/search, the failures-catalog quick fix (repo+delete sessions), CLAUDE.md test-count fix. No product code changes. |
| 2 | **Workspace + packaging** | citadel.toml marker discovery (env-only workspaces stay valid), .env-from-workspace, rules packaged 1:1 as internal data (**no editable workspace rules yet** — avoids the double-churn/.new storm), minimal prompt-path repoint + `_external_dirs` grant, fail-loud guard, wheel-smoke CI, Windows/macOS runners, release.yml + Trusted Publishing, dynamic version + `--version`, PEP 639. Test: assembled prompt byte-identical modulo rules paths. |
| 3 | **Rules split + prompt externalization** | schema/core/tasks/formats/genres tree (genres = starter set, enumerated dynamically from the effective dir; incl. `genres/first-person.md` behind `CITADEL_STYLE_PROFILES`), **citation locator grammar** (Z6), **`CITADEL_WIKI_LANG`** (default en), gut `_build_instruction`, genre-by-agent + manifest genre stamp, `CITADEL_PDF_MODE`, rules_version content-hash stamping, `rules eject/show`, prompt-validation tests. **Gate: verify-example full grade before/after, same model, recorded in the PR.** |
| — | **tag v0.1.0** | Workspace model + final rules shape stable; publishes the first working wheel, reserves the name. |
| 3.5 | **grammar.py** | Shared parsing + `is_source_citation`; resolve lint-vs-check divergences. Prerequisite for 4, 6, and the store split. |
| 4 | **Discovery** | Manifest stat fields + backfill-save + progress notice, failures-catalog stat fields, single scandir walk, candidates-then-confirm deletion + abort-on-walk-error + out-of-root exclusion, racy guard (source-clock), `CITADEL_RAW_DIRS` + cross-root citation form, `--full-rescan`, workspace-identity hard guard on deletion sweeps (Z1). **Pinning tests first.** Gate: verify-example. |
| 5 | **--force + session completeness** | Per Z4 incl. repo force-reconcile and failure-record clearing. **Promote-once-per-source for segmented sources** (Z11 — single staging copy across all segments). Then the SourceJob/dataclass ingest() refactor lands here or immediately after (same-file sequencing; never parallel to 4/5). |
| 6 | **curate v1 + surface parity** | Detectors (incl. re-sort), recompute-per-run plan, agent layer on staging machinery, --dry-run/--limit/--stale-rules/--diff, failures-catalog attempt caps, `wiki_lint` MCP tool, **`citadel status` + CLI parity subcommands (`read`/`index`/`sources`) + parity test, locator lint checks** (Z11/Z6). Gate: verify-example + project-history if it exists yet. |
| 7 | **Store/viewer hygiene** | store split, index single-pass, write_page guard, viewer subpackage + golden test, extract isolation, cleanups. (Truly parallel-safe parts only — grammar.py already landed as 3.5.) |
| 8 | **Corpora** | Demo move + fresh regeneration (+ ci.yml lint step + Pages + gitignore flip, same PR), counterfactual-atlas, project-history with stages/ (incl. first-person opinion/style traps), per-corpus ground-truth description files (hidden from ingest), verify-corpus skill. |
| 9 | **OSS polish + skills** | README/badges/CONTRIBUTING/CHANGELOG/SECURITY/docs-config, doctor, open-pr skill + CLAUDE.md routing section, sdist excludes. **Licensing/third-party-CLI hygiene (Z12): NOTICE.md + affiliation/trademark disclaimer, bring-your-own-CLI terms note, output-ownership line, SECURITY.md data-flow note, no-vendor-mark packaging guard** — the public-repo flip gates on these existing. **tag v0.2.0.** |
| 10 | **Evidence quotes** | Optional; go/no-go per Z6 after corpora data exists. |

## Greenfield policy & operational safety

- **No backward compatibility is owed** (owner decision): existing wikis/manifests either re-ingest
  fresh or run `--full-rescan`; formats, keys, and prompts may change freely between PRs. No
  migration tooling, no compat shims, no dual-format readers.
- What is NOT negotiable regardless of greenfield — **operational safety on live data**: deletion
  candidates get positive `.exists()` confirmation, any walk error aborts the deletion sweep,
  out-of-root keys are never swept, promotion stays all-or-nothing, and a workspace-identity
  mismatch fails loud instead of silently re-keying. Breaking a format is fine; corrupting or
  silently thinning a wiki is not.
- Every PR touching ingest/llm/rules runs the verify-example (later verify-corpus) gate before and
  after; the load-bearing list at the top is pinned by tests before its files are touched.
