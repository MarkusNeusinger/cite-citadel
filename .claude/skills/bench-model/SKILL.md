---
name: bench-model
description: Benchmark an LLM (model and/or agent CLI) on citadel's wiki-building quality — the model-focused twin of verify-corpus (which tests the PIPELINE with a fixed model, while bench-model tests a MODEL with the fixed pipeline). Mode A ingests a corpus into a throwaway sandbox with the chosen CITADEL_INGEST_MODEL / CITADEL_LLM_CLI, grades it with verify-corpus's retrieval-first method, then applies a DISCRIMINATIVE tier (locator precision, oblique-query retrieval, merge quality, redundancy/cross-links, judgment delta on contradictions + planted-false claims) so runs by models of different strength never tie at the top — if two models both ace the grade, the test was too easy, which is itself a finding. Ends with a side-by-side metrics table and a verdict (is the cheaper model's wiki acceptable, where does it degrade first, what rule changes would close the gap). Use whenever the user wants to compare models on wiki creation (sonnet vs haiku, a new Claude model, gemini/copilot, or open/local models via the CITADEL_LLM_CLI seam), asks "does model X suffice for ingest?", wants a cost/quality trade-off measured, or wants to re-run the model bench from the 2026-07 audit — even if they do not say the word "skill". Takes a corpus name, a model id, and optionally a CLI and a baseline sandbox to compare against.
---

# Bench a model on wiki creation

**Usage:** `bench-model <corpus> <model> [--cli claude|copilot|gemini] [--baseline SANDBOX] [--grade-only SANDBOX]`

Everything sandbox/grading-related follows **verify-corpus** (read its SKILL.md first — sandbox
recipe, phase 1 structural gates, phase 2 retrieval-first grading, the creation-vs-retrieval miss
matrix, the gotchas). This skill changes the *question*: not "does the pipeline still work?" but
"how well does THIS model drive it?" — so the model is the variable, the grade gains a
discriminative tier, and the output is a comparison, not just pass/fail.

## Reference points (2026-07 audit, beverages, 14 sources)

| | claude-sonnet-5 | claude-haiku-4-5 |
| --- | --- | --- |
| pace | ~7.5 min/source | ~3 min/source (~2.5× faster) |
| structural gates | check+lint clean | check+lint clean |
| ground-truth grade | no wiki-defects on its subset | 7 wiki-defects |
| judgment failures | none observed | 3 uncaught contradictions; a planted-false claim ("coffee loses caffeine with age") adopted as unqualified wiki-voice truth; partial 2024→2026 supersession |

The pattern to test for: **cheap models produce structurally valid, well-cited pages at speed but
miss judgment-heavy work** — surfacing contradictions, quarantining suspicious claims, temporal
supersession, open-points discipline. Structural gates alone will NOT separate models.

## Mode A — build with the model under test

Per verify-corpus's sandbox recipe, with the model pinned; run ingest **in the background** (a
foreground shell call gets killed by per-command timeouts long before a full corpus finishes):

```bash
REPO="$(git rev-parse --show-toplevel)"
SANDBOX="$(mktemp -d)/bench-<corpus>-<model>"
uv run python -m citadel init "$SANDBOX"
cat > "$SANDBOX/.env" <<EOF
CITADEL_LLM_CLI=claude                 # or copilot / gemini — the seam for open/local models
CITADEL_INGEST_MODEL=<model>
CITADEL_LLM_LOG_DIR=$SANDBOX/logs
CITADEL_RAW_DIR=$REPO/corpora/<corpus>/raw
EOF
# sanity-check the model id first (cheap):  claude --model <model> -p "Reply with exactly: ok"
CITADEL_WORKSPACE="$SANDBOX" uv run python -m citadel ingest --quiet &   # background; poll:
uv run python -c "import json;print(len(json.load(open('$SANDBOX/wiki/.citadel_ingested.json'))['sources']))"
```

- A killed/interrupted run is safe (all-or-nothing per source) and **resumes idempotently** from the
  manifest — just rerun the same ingest command.
- Budget by pace × source count; corpora with waves (leuchtfeuer) or chunking (pemberley) follow
  their verify-corpus protocols. For a quick model probe, beverages is the default; add
  injection-resistance when benching a weak/untrusted model (3 quick sources, high signal).
- Record the model: the manifest stamps it per source; grades are only comparable apples-to-apples.
- For open/local models keep `CITADEL_INGEST_MODEL`/`CITADEL_LLM_CLI` pointed at whatever CLI fronts
  them (see docs/configuration.md for `*_CLI_PATH` overrides); the bench procedure is unchanged.

## Grade — verify-corpus phases 1+2, then the discriminative tier

Run verify-corpus **phase 1** (check + lint exit 0) and **phase 2** (the ground-truth retrieval
battery, retrieval-first, misses classified creation-vs-retrieval) unchanged. Where the corpus's
ground-truth commits `st-*` **stretch guarantees** (beverages does — its `## Stretch guarantees`
section is this tier made permanent, with thresholds from the 2026-07 bench), grade those verbatim
and report the `stretch N/M` line. For corpora without a committed stretch section, apply the ad-hoc
discriminative tier below — identical procedure for every wiki being compared:

1. **Locator precision** — sample ~10 `[^sN]` citations across pages; resolve each with
   `uv run python -m citadel raw <key> --locator "<loc>"` (the portable invocation); check the
   located span actually contains the cited fact.
   Report precise / vague (fact nearby but outside the span) / wrong per wiki.
2. **Oblique retrieval** — ~8 user-phrased questions that do NOT reuse page-title words
   ("does letting coffee sit make it weaker?", "who started the cafe in Trieste?"). Same queries on
   every wiki via `uv run python -m citadel search`; score rank-of-relevant-page; unfindable =
   hard miss.
3. **Merge quality** — near-duplicate/overlapping pages (e.g. three caffeine pages), one-page-per-
   source dumps, and whether canonical shared facts (robusta 2×, drip ~95 mg) live in ONE place
   with co-citations or are scattered.
4. **Redundancy & cross-links** — pick ~5 canonical facts, count pages restating each (linked vs
   unlinked repetition); compare links-out per page and lint's orphan count.
5. **Judgment delta** — the corpus's contradiction and planted-false-claim guarantees, graded
   strictly: attributed + `[!CONTRADICTION]`/`[^llm]`-questioned = pass; unqualified wiki-voice
   adoption or silent overwrite = the serious failure class.

**Saturation check (owner rule):** if all models under comparison tie at the top of BOTH the
ground-truth grade (incl. its `stretch N/M` line) and the discriminative tier, the bench is too easy
— file that as a finding and harden the corpus's committed `st-*` stretch guarantees (or propose new
ones) rather than reporting a tie as success.

## Output

One metrics table across runs — sources ingested, wall-clock, pages, `[^s` citations, check/lint,
ground-truth passed/total + `stretch N/M` (+ wiki-defect list), locator precision, oblique-retrieval score,
redundancy, orphans — followed by a verdict: is the cheaper model's wiki acceptable for real use,
where does it degrade first, what is the cost/quality trade, and which `citadel/rules/` changes
would close the gap (cite the specific failures). Route every defect into the two verify-corpus
lanes (wiki-generation vs retrieval-tooling).

## Gotchas

- Never bench against a live wiki or the repo workspace; never touch the repo `.env`. Sandboxes are
  throwaways (`rm -rf`), kept only while a `--baseline` comparison still needs them.
- Ingest is non-deterministic — compare semantics and defect *classes*, not page paths or counts
  alone; a one-guarantee flip between runs of the same model is noise, a defect-class gap
  (e.g. contradictions missed) is signal.
- Don't grade a partial wiki against the full ground-truth without flagging it: a capped/interrupted
  run leaves pending sources, and their guarantees must be counted as `skipped`, not failed.
