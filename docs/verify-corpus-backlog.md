# verify-corpus lane backlog

The **durable ledger** behind verify-corpus's two optimization lanes. Every grading run (verify-corpus
Mode A/B/C, and bench-model's discriminative tier) routes each miss into a lane — **wiki-generation**
(a creation defect: improve `citadel/rules/`, the ingest prompts, `llm.py`) or **retrieval-tooling**
(a retrieval defect: improve `store_core.search` / the CLI/MCP tools), with **capability-gap** as the
escalation when no metadata fix can make a correctly-built fact findable. Before this file existed,
those findings lived only in per-run grade reports and evaporated with the sandbox; now every miss
that did not immediately become a fix is recorded here, so the lanes have durable input.

## Protocol

- **Append per run, never rewrite history.** After the grade report, add one `## Run` block per
  grading run (newest first) and one ledger row per miss. A clean run still gets a block (with
  `misses: none`) — a green streak is signal too.
- **One row per distinct miss.** If a later run reproduces an already-open entry, do not duplicate
  it: bump that entry's `last seen` date instead. A re-observed miss is prioritization signal.
- **Statuses:** `open` → `fixed (PR #N / commit)` when a shipped change resolves it (verified by a
  re-run or an offline test), or `declined (reason)` when the miss is accepted as a documented
  trade-off. Resolved rows move to § Resolved — they are the record of which grading insights became
  fixes, never deleted.
- **Row content:** the corpus + ground-truth row/guarantee id, the lane, one sentence naming the
  file+fact involved and the defect (dropped / mis-routed / mis-cited / ranked-below-fold / …), and
  the concrete route (which rules file, prompt, or search behavior a fix would touch). Enough that a
  fix session needs no access to the original sandbox.
- **Hard fails don't live here.** A hard-gate failure blocks the change that caused it and is fixed
  immediately — this ledger is for the soft misses and texture findings that would otherwise be
  lost. (A hard fail's *root-cause insight* may still land here once the failure itself is fixed.)
- **Model context matters.** Stamp each run block with the model and `rules_version` — a
  weaker-model-only miss routes differently (bench-model's rules-gap lane) than one the reference
  model also shows.

Row format:

```
| id | first seen | last seen | corpus | guarantee | lane | defect + route | status |
```

`id` is `VCB-NNN`, allocated sequentially across the whole file (grep the highest existing one).

## Open entries

| id | first seen | last seen | corpus | guarantee | lane | defect + route | status |
|----|------------|-----------|--------|-----------|------|----------------|--------|

*(No open entries yet — this ledger starts empty on 2026-07-24; the next grading run seeds it.
Historical per-run reports predating this file were not retro-imported: their sandboxes are gone,
so their misses cannot be re-verified.)*

## Resolved

| id | first seen | corpus | guarantee | lane | defect + route | status |
|----|------------|--------|-----------|------|----------------|--------|

## Runs

*(Newest first. One block per grading run — corpus, mode, model, `rules_version`, verdict, and the
`VCB-` ids the run touched, or `misses: none`.)*
