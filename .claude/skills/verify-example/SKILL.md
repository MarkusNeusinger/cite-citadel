---
name: verify-example
description: End-to-end test of the whole citadel ingest pipeline on the bundled coffee+tea example corpus — ingest raw/ into a fresh wiki, run the structural gates (citadel check + lint), then grade the result against the ground-truth answer key (planted contradictions, repetitions, single-source facts, the one deliberately-false fact, cross-topic links). Use this whenever the user wants to run the e2e or example test, verify or grade the example corpus, (re)build the demo wiki, prove that citations and contradictions still surface, or check that a change to ingest, the rules tree (citadel/rules/), the ingest prompts, or the store still folds the corpus correctly — even if they do not say the word "skill".
---

# Verify the example corpus end-to-end

The `raw/` corpus (5 coffee + 5 tea files) is **designed** to stress the three guarantees: facts
repeat, contradict, hide in one place, vary in style, name fictional people, and include one
flat-out-false claim. The answer key is `.claude/skills/verify-example/ground-truth.md` — the ingest
never sees it (it lives outside `raw/`/`wiki/`/`docs/`). This skill runs the real pipeline, then grades
the wiki against that key. All paths are relative to the repo root.

This is a **heavy, intentional** test: Mode A shells out to the LLM ingest CLI (slow, uses your
subscription). For fast iteration on the grader, use Mode B.

## Preconditions

- The ingest CLI is installed and logged in (default `claude`; run `claude` once and `/login`). Mode B
  needs no CLI.
- The 10 example files are present: `ls raw/*.md | wc -l` → should be **10**.
- Prefer a clean-ish git tree so a stray edit is easy to see (`git status`).

## Mode A · Full E2E (ingest + grade)

Regenerates the wiki from scratch, so it both **rebuilds the showcase wiki** and tests the pipeline.

**1 · Start from an empty wiki** (so every source is ingested fresh — the manifest makes ingest
idempotent, so a leftover wiki/manifest would skip everything). Move the current wiki aside rather than
deleting it:

```bash
[ -d wiki ] && mv wiki "/tmp/citadel-wiki-bak.$(date +%s)" || true
```

**2 · Ingest the whole corpus** (one agentic session per file; minutes, not seconds):

```bash
time uv run python -m citadel ingest
```

Expected: a report ending `... created, ... updated, 0 errors` and **no** "WARNING — broken
cross-links". 10 sources processed. If a source errored (missing/again-not-logged-in CLI, timeout), fix
that first — the grade is meaningless on a partial wiki.

**3 · Structural gates** (hard pass/fail, pure code — see ground-truth §G):

```bash
uv run python -m citadel check        # expect: "OK — no validation issues."
uv run python -m citadel lint          # expect: final line "OK"
```

A non-zero `lint` (missing type / broken link / fabricated source / `[[wikilink]]`) or any `check`
error is an automatic FAIL — the pipeline produced a structurally invalid wiki.

**4 · Grade against the answer key** — read `ground-truth.md` in full, then judge each section against
the wiki using the greps below as evidence (do not grade from memory). Then go to **Grading**.

**5 · Keep or restore the wiki.** The freshly built `wiki/` is the new showcase. To keep it, leave it
(and `git add wiki/` when committing). To revert: `rm -rf wiki && mv /tmp/citadel-wiki-bak.* wiki`.

## Mode B · Grade-only (no re-ingest)

Grades the wiki that is already on disk — for iterating on the grader/ground-truth or re-checking after
a manual wiki edit. Skip steps 1–2; run **3** (gates) and **4** (grade) only.

## Grading — evidence commands

Run these and judge the output against `ground-truth.md`. Page **names** are LLM-chosen and vary run to
run — **grade by content, not by filename**.

```bash
# C · contradictions surfaced (target >=2 of 4; stretch 4/4)
grep -rn "CONTRADICTION" wiki/ | grep -v index.md
# the four subjects to confirm by eye (one value vs the other, or a callout):
grep -rni "green tea" wiki/ | grep -iE "28|50 ?mg"
grep -rni "half-life" wiki/ | grep -iE "3 ?h|5 ?h|hour"
grep -rni "aurora" wiki/ | grep -iE "198[57]"
grep -rni "thornbury\|1650\|1657" wiki/

# D · the false fact present, attributed, and questioned (not silently fixed/dropped)
grep -rni "caffeine-free\|midnight\|burns off" wiki/      # the claim must appear
grep -rn  "\[\^llm" wiki/                                  # ideally an LLM caveat near it
uv run python -m citadel lint | grep -A20 "model-supplied"  # pages carrying [^llm] facts

# E · the subtle "don't drop me" fact survived
grep -rni "cold brew" wiki/ | grep -iE "higher|more caffeine|ratio|steep"

# A · single-source facts survived
grep -rni "l-theanine" wiki/ ; grep -rni "ceremonial\|culinary" wiki/ ; grep -rni "9 ?bar\|63 ?mg" wiki/

# B · repetitions merged, not duplicated — there should NOT be one isolated page per raw file
grep -rln "95 ?mg" wiki/        # the 95 mg fact should live on ~one page, co-cited, not many
grep -rln "twice the caffeine\|2x\|2× caffeine" wiki/

# F · cross-topic bridge: coffee<->tea connected, Thornbury reachable from both
grep -rni "caffeine" wiki/ | grep -i "tea" | grep -i "coffee"
grep -rni "thornbury" wiki/

# H · abbreviations: TDS/EGCG spelled-out-once carried in (defined); EY flagged undefined
grep -rni "total dissolved solids\|(TDS)\|(EGCG)\|epigallocatechin" wiki/   # expansions preserved
grep -rln "type: Abbreviation" wiki/ 2>/dev/null || true                     # bonus: a glossary page
uv run python -m citadel lint | grep -A12 -i "undefined abbrev"              # EY should appear; TDS/EGCG should NOT

# provenance density (every fact cited)
grep -rno "\[\^s[0-9]" wiki/ | wc -l       # many raw citations
uv run python -m citadel search "caffeine"  # the search seam works
```

Optional visual check: `uv run python -m citadel view --no-open` then open the printed `file://` path.

## Pass criteria

Report a table of: **hard gates** (all must hold) and **soft checks** (report caught/partial/missed,
don't hard-fail a single miss). From `ground-truth.md`:

- **Hard:** `check` 0 errors · `lint` OK · all §A single-source facts present · §D false claim present +
  attributed (NOT silently corrected) · §E subtle fact present · §F coffee and tea not two disconnected
  islands · §B not one-isolated-page-per-raw-file.
- **Soft:** §C contradictions surfaced (≥2 good, 4/4 great) · §D carries an explicit `[^llm]` caveat ·
  §B merges maximally tidy · §H abbreviations (TDS/EGCG carried in with their expansion and not flagged
  undefined; EY surfaced by lint's undefined-abbreviations check).

End with a one-line verdict and, if anything failed, the specific guarantee it breaks (organized /
links / provenance) and the file/fact involved.

## Gotchas

- **Ingest is non-deterministic.** Page filenames, exact wording, and which contradictions get a
  `> [!CONTRADICTION]` callout vary between runs and models. Grade semantics (is the fact present, cited,
  merged?), never exact paths. A contradiction missed on one run that was caught before is a *soft*
  regression worth noting, not a hard fail.
- **The manifest makes ingest skip unchanged sources.** If you forget step 1 (empty wiki) the run does
  nothing and the grade reflects the *old* wiki. Always start Mode A from a moved-aside wiki.
- **A wiki outside the repo root breaks citations.** Do NOT point `CITADEL_WIKI_DIR` at `/tmp` for this —
  the `[^s..]` links are `../../raw/...` relative and must resolve to the repo's `raw/`. Keep `wiki/` at
  the repo root (sibling of `raw/`); only the *backup* goes to `/tmp`.
- **The false fact is supposed to be in the wiki.** Do not "fix" it. A wiki that silently states the
  truth instead, with no `aurora-coffee-blog.md` citation, is a provenance FAIL, not a pass.
- **Fictional entities are not errors.** Caffè Aurora, Lina Marchetti, Thornbury & Lin etc. are invented
  on purpose; the wiki recording them is correct.
- **Model matters.** A weaker `CITADEL_INGEST_MODEL` catches fewer contradictions and adds fewer `[^llm]`
  caveats. Note the model (it is recorded per source in `wiki/.citadel_ingested.json` and the report) so
  soft-score comparisons are apples-to-apples.

## Troubleshooting

- `ingest` reports a per-source error about the CLI → it is missing or not logged in; `claude` then
  `/login`, or set `CITADEL_LLM_CLI`/`*_CLI_PATH`. Re-run from step 1.
- `check`/`lint` fail right after a green ingest → the agent introduced a broken cross-link or skipped a
  required field; read the issue, it names the page. This is a real pipeline finding, report it.
- Grade looks empty / everything "missing" → you are likely grading a stale or empty `wiki/`; confirm
  `ls wiki/**/*.md` shows pages and that step 2 actually processed 10 sources.
