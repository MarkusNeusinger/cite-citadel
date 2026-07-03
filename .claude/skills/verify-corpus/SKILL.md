---
name: verify-corpus
description: End-to-end test + grader for the citadel ingest pipeline over the shipped test corpora — beverages (coffee+tea showcase), counterfactual-atlas (a coherent fictional world whose facts contradict reality), and project-history (a 3-year programme ingested in dated waves that drives reconcile/delete/force). Mode A ingests a corpus into a throwaway SANDBOX workspace (never a live wiki), runs the structural gates (citadel check + lint), then grades the result against that corpus's hidden ground-truth.md answer key (single-source facts, merges, contradictions, counterfactuals kept-as-stated, temporal supersession, delete propagation, cross-links, abbreviations). Use whenever the user wants to run the e2e / corpus test, verify or grade a corpus, (re)build the demo/showcase wiki, prove citations and contradictions still surface, or check that a change to ingest, llm, the rules tree (citadel/rules/), the ingest prompts, or the store still folds a corpus correctly — even if they do not say the word "skill". Takes a corpus name (beverages | counterfactual-atlas | project-history | all) and optional --grade-only.
---

# Verify a corpus end-to-end

Three shipped corpora, each a `corpora/<name>/` bundle (`raw/`, sometimes `stages/`, a `README.md`)
plus a hidden answer key at `.claude/skills/verify-corpus/<name>/ground-truth.md`. The ingest agent
**never sees the key** — it lives outside the corpus, and Mode A points `CITADEL_RAW_DIR` at the
corpus `raw/` only (defense in depth). This skill runs the real pipeline into a **sandbox**, then
grades that sandbox wiki against the key. Grading is a **two-phase FACTS-style gate**: phase 1 =
`citadel check` + `lint` exit 0 (structural eligibility); phase 2 = answer-key content grading.

**Usage:** `verify-corpus <beverages|counterfactual-atlas|project-history|all> [--grade-only]`

| corpus | what it stresses | ground-truth |
| ------ | ---------------- | ------------ |
| `beverages` | organized / links / provenance on a messy coffee+tea corpus; the showcase wiki | `.claude/skills/verify-corpus/beverages/ground-truth.md` |
| `counterfactual-atlas` | the hardest guarantee: a fictional world stated wrong about reality, kept as-stated and cited, never corrected | `.claude/skills/verify-corpus/counterfactual-atlas/ground-truth.md` |
| `project-history` | reconcile / delete / force across 3 dated waves; temporal supersession; German→English; opinions & style | `.claude/skills/verify-corpus/project-history/ground-truth.md` |

Mode A shells out to the ingest CLI (slow, uses your subscription). For fast iteration on the grader
use **Mode B** (`--grade-only`) against a sandbox you already built.

## Preconditions

- Ingest CLI installed and logged in (default `claude`; run `claude` once and `/login`). Mode B needs
  no CLI.
- Run from the repo checkout (so `uv run` resolves the project + venv). The corpus you name is the
  immutable input — never edit `corpora/<name>/` or the ground-truth.
- Real runs use `CITADEL_INGEST_MODEL=sonnet` so soft scores are apples-to-apples across runs; note
  the model (recorded per source in the sandbox `wiki/.citadel_ingested.json`).

## Sandbox setup (Mode A, per corpus — never touches a live wiki)

Build every corpus in its own throwaway workspace under a scratch dir, so the live repo wiki and the
committed `corpora/**/wiki` are never moved aside:

```bash
REPO="$(git rev-parse --show-toplevel)"
CORPUS=beverages                          # or counterfactual-atlas | project-history
SANDBOX="$(mktemp -d)/verify-$CORPUS"     # a scratch workspace OUTSIDE the repo
uv run python -m citadel init "$SANDBOX"   # scaffolds citadel.toml + .env + raw/ + wiki/

export CITADEL_WORKSPACE="$SANDBOX"        # discovery uses the sandbox, not the repo marker
export CITADEL_WIKI_DIR="$SANDBOX/wiki"
export CITADEL_INGEST_MODEL=sonnet
export CITADEL_LLM_LOG_DIR="$SANDBOX/logs" # per-source transcripts (or pass --log-dir)
WIKI="$SANDBOX/wiki"                        # $WIKI / $RAW are what the ground-truth greps use
```

`beverages` and `counterfactual-atlas` read the immutable corpus `raw/` directly (one ingest pass):

```bash
export CITADEL_RAW_DIR="$REPO/corpora/$CORPUS/raw"
RAW="$CITADEL_RAW_DIR"
time uv run python -m citadel ingest        # one agentic session per file; minutes, not seconds
```

Expect a report ending `… created, … updated, 0 errors` and **no** "WARNING — broken cross-links".
If a source errored (CLI missing / not logged in / timeout), fix it first — a grade on a partial wiki
is meaningless.

### project-history — the wave protocol

This corpus **mutates** its raw over three dated waves, so it gets a *writable copy* of `raw/` inside
the sandbox and `stages/` is never pointed at the agent (it stays invisible). Run
`citadel check` + `lint` (phase 1) **after every wave**.

```bash
export CITADEL_RAW_DIR="$SANDBOX/raw"; RAW="$CITADEL_RAW_DIR"   # sandbox's own raw (init made it)
export CITADEL_WIKI_LANG=en                 # German sources, English wiki (graded)
export CITADEL_STYLE_PROFILES=1             # the first-person opinion/style grading (§I)
SRC="$REPO/corpora/project-history"

# wave 1 — the 2024 kickoff era (6 files, all kind=ingest)
cp "$SRC/raw/"* "$RAW"/ && uv run python -m citadel ingest

# wave 2 — 2025: the charter is REPLACED in place (reconcile), 3 new files (ingest)
cp "$SRC/stages/wave2/"* "$RAW"/ && uv run python -m citadel ingest

# wave 3 — 2026: DELETE the retracted memo, drop 3 new files, run a FULL ingest (delete propagation)
rm "$RAW/2024-06-10-memo-brandt-komet-operating-costs.md"
cp "$SRC/stages/wave3/"* "$RAW"/ && uv run python -m citadel ingest

# idempotency — a no-change re-run must be a NOOP (zero sessions)
uv run python -m citadel ingest
# optional --force NOOP probe: re-reads an unchanged source, must diff to zero changed pages
uv run python -m citadel ingest --force "$RAW/2024-03-05-minutes-kickoff.md"
```

Expected session kinds are enumerated in the wave protocol of `project-history/ground-truth.md`
(wave 2: 1 reconcile + 3 ingest + 5 NOOP; wave 3: 1 delete + 3 ingest + rest NOOP). Watch the report
per wave.

## Mode B — grade-only (`--grade-only`)

Skip the build; grade a sandbox wiki already on disk. Set `SANDBOX`/`WIKI`/`RAW`/`CITADEL_*_DIR` to
that existing build, then run phase 1 + phase 2 below. Use this to iterate on the grader or a
ground-truth without re-spending an ingest.

## Phase 1 — structural gates (hard pass/fail, pure code)

```bash
uv run python -m citadel check        # expect: "OK — no validation issues."  (0 errors)
uv run python -m citadel lint          # expect final line "OK"
```

A non-zero `lint` (missing type / broken link / fabricated source / `[[wikilink]]`) or any `check`
error is an automatic FAIL — the pipeline produced a structurally invalid wiki. Do not proceed to the
grade; the structural break is the finding.

## Phase 2 — grade against the answer key

**Read `corpora`'s `ground-truth.md` in full**, then judge each lettered section against `$WIKI`
using the evidence greps the key itself carries (it enumerates every planted item with a greppable
value and expected citation). Grade by **content, not filename** — page names are LLM-chosen and vary
run to run. Wiki text may wrap; if a scoped grep misses, flatten first
(`tr '\n' ' '`) before calling it a miss. A compact starter battery per corpus — the ground-truth has
the complete list:

```bash
# --- beverages (§A single-source, §B merges, §C contradictions, §D false claim, §E subtle, §F bridges, §H abbrevs)
grep -rn "CONTRADICTION" "$WIKI" | grep -v index.md          # C: >=2 of 4 good, 4/4 great
grep -rni "caffeine-free\|burns off" "$WIKI"                 # D: the false claim must be present…
grep -rn  "\[\^llm" "$WIKI"                                  # …ideally with an [^llm] caveat near it
grep -rni "cold brew" "$WIKI" | grep -iE "higher|more caffeine"   # E: the subtle "don't drop me" fact

# --- counterfactual-atlas (§D is the point: planted-present, true-value-only-as-[^llm])
grep -rinE "312[, ]?000" "$WIKI"                             # planted must hit
grep -rinE "299[ ,.]?792|300[, ]?000" "$WIKI"                # true value: every hit MUST be [^llm]-labeled; bare = FAIL
grep -rinE "299[ ,.]?792|300[, ]?000" "$RAW"                 # authoring invariant: NO output (else the trap is void)
grep -rin "KSB" "$WIKI"                                      # §H: never expanded with [^sN] (fabrication)

# --- project-history (final state after wave 3)
grep -rn '18,000\|02:00\|memo-brandt-komet-operating-costs' "$WIKI"   # D1 delete: all THREE must be empty
grep -rn '310,000' "$WIKI"                                   # …but the co-cited €310k KEEPS (attributed to Brandt)
grep -rniE 'wurde|sowie|beträgt|beschlossen' "$WIKI"         # WIKI_LANG=en: no German content pages
grep -rn 'BasaltDB' "$WIKI"; grep -rn 'KorallenDB' "$WIKI"   # T2: BasaltDB current, KorallenDB only superseded
```

Then walk the ground-truth's own per-section grep tables (counterfactual-atlas §D has all seven
traps; project-history has the full Trap Inventory table). `uv run python -m citadel lint` also lists
pages carrying `[^llm]` facts and undefined abbreviations — a quick index for §D/§H judgement.

## Grading output

Report a table of **hard gates** (all must hold) and **soft checks** (report caught / partial /
missed — do not hard-fail a single soft miss; ingest is non-deterministic). The exact hard/soft split
is the **Scoring** section at the bottom of each corpus's ground-truth — use it verbatim. In short:

- **beverages** — hard: check 0 / lint OK / §A single-source facts / §D false claim present+attributed
  (not silently corrected) / §E subtle fact / §F not two islands / §B not one-page-per-file. Soft: §C
  contradiction callouts (≥2), §D `[^llm]` caveat, §B tidiness, §H TDS/EGCG carried + EY surfaced.
- **counterfactual-atlas** — hard: §G structural / §D all seven traps (planted present+cited, true
  value nowhere un-`[^llm]`) / §A / §E patent clause / §C both conflict values / §F1 temporal both
  states dated / §F2 no fused-sense fabrication / §F3 graph connected / §H no `[^sN]` KSB expansion.
  Soft: contradiction callouts, merge tidiness, Change-Log form, honest `[^llm]` asides.
- **project-history** — hard: §G after **every** wave / every `T*` old value superseded not erased /
  `D1` delete complete with €310k surviving / `C1`/`C2` counterfactuals kept / `Q1`/`Q2` attributed to
  the original author / `O1`/`O2` never world facts / `S1` pilot vs portal not merged / §A / §E.
  Soft: M1/M2 callouts, tidy change-logs, AP-1 thread, abbreviation pages, style-profile entries.

End with a one-line verdict per corpus and, on any hard fail, the specific guarantee it breaks
(organized / links / provenance / temporal) and the file+fact involved.

## `all`

Run the three corpora **sequentially**, each in its own sandbox (never share a workspace). Grade each,
then print one aggregate table: corpus × {phase-1 check, phase-1 lint, hard-gate verdict, soft
caught/total}. `all` passes only if every corpus passes its hard gates.

## Keep or discard the beverages build

The `beverages` sandbox wiki is the **showcase** — the committed one lives at `corpora/beverages/wiki`
and the GitHub Pages viewer is built from it. To refresh the showcase, copy a clean beverages build
over it: `rm -rf "$REPO/corpora/beverages/wiki" && cp -r "$SANDBOX/wiki" "$REPO/corpora/beverages/wiki"`,
then re-run phase 1 against `corpora/beverages` before committing. The other two sandboxes are
throwaways — `rm -rf "$SANDBOX"` when done.

## Gotchas

- **Ingest is non-deterministic.** Page filenames, wording, and which conflicts get a
  `> [!CONTRADICTION]` callout vary between runs and models. Grade semantics (present? cited? merged?
  superseded?), never exact paths. A contradiction caught before but missed now is a *soft*
  regression to note, not a hard fail.
- **Never point a corpus wiki outside its raw's parent.** The `[^sN]` links are relative
  (`../../raw/…`) and must resolve to the corpus `raw/`. The sandbox keeps `wiki/` a sibling of the
  effective raw via `CITADEL_RAW_DIR`; do not aim `CITADEL_WIKI_DIR` somewhere unrelated.
- **stages/ and the ground-truth must stay invisible to the agent.** For project-history, only ever
  copy `stages/waveN/*` INTO the sandbox raw between runs — never set `CITADEL_RAW_DIR` at `stages/`.
- **Counterfactuals and fictional entities are not errors.** 312,000 km/s, "Sydney is the capital",
  Caffè Aurora, Blauwal Logistik — all invented on purpose; recording them faithfully is the pass.
  A wiki that "fixes" them to the real value with no `[^llm]` label is a provenance FAIL.
- **The manifest makes ingest skip unchanged sources.** A fresh sandbox starts empty, so wave 1 sees
  everything; if a re-run "does nothing", that is the NOOP idempotency guarantee, not a bug.
- **Model matters.** A weaker model catches fewer contradictions / adds fewer `[^llm]` caveats. Record
  the model so soft-score comparisons stay apples-to-apples.

## Troubleshooting

- `ingest` reports a per-source CLI error → the CLI is missing or not logged in; `claude` then
  `/login`, or set `CITADEL_LLM_CLI`/`*_CLI_PATH`. Rebuild the sandbox.
- `check`/`lint` fail right after a green ingest → the agent introduced a broken cross-link or skipped
  a required field; the message names the page. That is a real pipeline finding — report it.
- Grade looks empty / everything "missing" → you are grading a stale or empty `$WIKI`; confirm
  `ls "$WIKI"/**/*.md` shows pages and that the build actually processed every source.
- project-history wave 3 still shows the memo's facts → the delete session did not run or did not
  promote; a full run is required for deletion detection, and `D1`'s three ∅-greps are the probe.
