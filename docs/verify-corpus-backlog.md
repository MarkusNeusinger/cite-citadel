# verify-corpus lane backlog

The **durable ledger** behind verify-corpus's two optimization lanes. Every grading run (verify-corpus
Mode A/B/C, and bench-model's discriminative tier) routes each miss into a lane — **wiki-generation**
(a creation defect: improve `citadel/rules/`, the ingest prompts, `llm.py`) or **retrieval-tooling**
(a retrieval defect: improve `store_core.search` / the CLI/MCP tools), with **capability-gap** as the
escalation when no metadata fix can make a correctly-built fact findable. Before this file existed,
those findings lived only in per-run grade reports and evaporated with the sandbox; now every miss
that did not immediately become a fix is recorded here, so the lanes have durable input.

## Protocol

- **Append per run, never rewrite history.** After the grade report, add one `### <date> <corpus>`
  sub-block under the single `## Runs` section (newest first) and one ledger row per miss. A clean
  run still gets a block (with `misses: none`) — a green streak is signal too.
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
| VCB-001 | 2026-07-25 | 2026-07-25 | beverages | offline-verifiable locators (schema.md § Sources) | wiki-generation | **haiku-only.** Haiku cites whole sections (`§ Caffeine — …`) where sonnet cites `line 9`, and it appends its own gloss to the heading, so 5 locators name a heading the source does not contain and `lint.check_locators` cannot verify any of them (`concepts/caffeine.md` ×2, `concepts/coffee.md`, `objects/aurora-midnight.md`, `organizations/caffe-aurora.md`; one concatenates two headings: `§ It Started With Lina, What We Actually Mean By "Sourcing" — company history…`). Route: `citadel/rules/schema.md`'s locator grammar — state that `§` takes the heading text VERBATIM and nothing else, and that `lines A-B` is preferred for a text source; the reference model needs no such spelling-out, a weaker one does. | open |
| VCB-002 | 2026-07-25 | 2026-07-25 | beverages | every factual sentence carries a footnote | wiki-generation | **haiku-only.** One uncited sentence survived the agent's own `citadel check` because it is inside a sentence the parser reads as cited: `concepts/coffee.md` — "The plant and its cultivation are dominated by two species: [Arabica and Robusta…". Lint's advisory `missing citations` caught it; `check` did not. Route: the `tasks/ingest.md` self-check step (re-read every paragraph for a trailing footnote), and worth asking whether this shape should be a `check` error rather than a lint advisory. | open |
| VCB-003 | 2026-07-25 | 2026-07-25 | beverages | `[^llmN]` is for model-supplied facts only, never a shortcut | wiki-generation | **haiku-only.** 4 pages carry model-supplied facts (`concepts/caffeine.md`, `concepts/tea.md`, `objects/aurora-midnight.md`, `organizations/thornbury-lin.md`) where the sonnet showcase of the same corpus has none — the corpus is fully covered by its raw sources, so an `[^llmN]` here is a weaker model reaching for the LLM lane instead of the source. Not a provenance violation (the lane is honest and lint surfaces it), so a soft miss. Route: `citadel/rules/core.md`'s `[^llmN]` section — make "prefer dropping the claim over sourcing it to yourself" explicit. | open |
| VCB-004 | 2026-07-25 | 2026-07-25 | beverages | dense cross-linking between related pages | wiki-generation | **Unattributed between model and `--jobs`.** 36 un-linked mentions where the committed sonnet showcase lints 0 (e.g. `concepts/tea.md → concepts/coffee.md`, `organizations/caffe-aurora.md → concepts/cold-brew.md`). Two candidate causes and this run cannot separate them: haiku links less densely, and `--jobs 4` means concurrent sessions cannot see each other's new pages (the documented, accepted cost of parallelism — `curate` is its designed cleanup). Route: re-run beverages on haiku with `--jobs 1` and diff this counter; only if serial haiku is also high is this a rules-lane miss rather than a parallelism trade-off. | open |
| VCB-006 | 2026-07-31 | 2026-07-31 | leuchtfeuer | T4 intra-wave temporal supersession (decommission 30 Sep → 31 Jul 2026) | wiki-generation | The 8 Apr 2026 portal-minutes session recorded the brought-forward KOMET decommission (31 Jul 2026) on `projects/seagull-customer-portal.md` but left `projects/projekt-leuchtfeuer.md` still stating "switched off on 30 September 2026" as the live plan (cited to the 20 Mar go-live mail, ingested one session earlier in the same wave). Cross-PAGE supersession: the new source's session updated the page it landed on but did not hunt other pages asserting the now-old value. Route: `tasks/ingest.md` — when a new source supersedes a dated value, grep the whole wiki for the superseded value and update every page presenting it as current. | open |
| VCB-007 | 2026-07-31 | 2026-07-31 | leuchtfeuer | style-profile quirks (§I, `CITADEL_STYLE_PROFILES=1`) | wiki-generation | Opinions all correctly attributed (O1/O2/O3 pass), but the persons pages carry no style-quirk entries — Vogelsang's nautical metaphors / "Fair winds" sign-off and Duszek's "—MD" are absent; the POD abbreviation (portal minutes) also has no expansion/page where WMS and MDE got both. Route: `genres/first-person.md` + the style-profile brief — spell out that sign-offs and recurring metaphors belong on the persons page when profiling is ON. | open |

## Resolved

| id | first seen | corpus | guarantee | lane | defect + route | status |
|----|------------|--------|-----------|------|----------------|--------|
| VCB-005 | 2026-07-29 | kelvarra | complete enumeration of catalog entries | wiki-generation | An enumerable source's tail was compressed instead of captured: `organizations/instrument-works.md` presses 5 "Sundries" products (survey chains, thermometers, sounding leads, tide-pole, rain gauge) into ONE footnote `[^s9]` with no per-entry attributes and no per-entry retrievability — the granularity floor + essence-not-structure rules actively demanded it. Route: the `Registry` page kind — `genres/registry.md`, the `Registry` type row + `## Registries` contract in `schema.md`, floor/essence carve-outs in `core.md`, `okf.folder_for_type`, registry-aware curate length guidance. | fixed (PR #134 — capability verified by the werkhof Mode A run below; the kelvarra showcase itself keeps its pre-registry wiki until its next rebuild, so its catalogue page still shows the old compression) |

## Runs

*(Newest first. One `### <date> <corpus>` sub-block per grading run — mode, model, `rules_version`,
verdict, and the `VCB-` ids the run touched, or `misses: none`. This `## Runs` heading stays
singular; runs nest under it.)*

### 2026-08-06 werkhof (regression run for PR #143 — the sharpened Registry creation triggers)

- **Mode:** Mode A into a scratch sandbox (`CITADEL_RAW_DIR` at the corpus `raw/`), grading that the
  sharpened rules (section-level genre trigger in `core.md`, the ingest-brief enumeration check, the
  reconcile new-content carve-out, `genres/registry.md`'s "Any source maintains the rows") do not
  regress the registry corpus. Full answer-key walk afterwards, retrieval-first.
- **Model:** `claude:claude-sonnet-5` (`CITADEL_INGEST_MODEL=sonnet`) · serial · `rules_version
  f6db490a45dc` · every source paid the per-source hermetic-auth retry (container auth shape) ·
  $3.49 recorded, 4 processed, 0 errors.
- **Result:** `check` exit 0, `lint` exit 0 (advisories: 3 undefined abbreviations HX/PV/N2 — N2 is
  the vessel nozzle designation, texture). All three collections again `type: Registry` under
  `registries/` with **28/28 machines, 20/20 fault codes, 15/15 customers**, one `[^sN]` per row
  (`lines A-B` on the register, `line N` per code/CSV row; locator issues 0). The stated "all 28"
  total cited in the scope line. Promotion: PV-014 + HX-201 → `objects/`, Nordwerk (K-007) →
  `organizations/`, rows reduced to key + link + gloss; WB-320/CT-430 stayed rows. HX-201's
  out-of-service supersession landed as a dated `## Change Log` pair (register "in service" 
  2026-01-15 kept beside the 2026-06-12 outage); E-142/E-412 and HX-201/HX-210 never conflated;
  E-155's deprecation row survives with the E-310 hand-over; Petersen/Albers attributed; the three
  done-able report items are `## Open Points` threads; CSV treated as data (0 `[^llm]` pages).
  Retrieval: `KP-011`, `E-420`, `K-009` each rank 1. Registries ↔ promoted pages ↔ fault catalogue
  fully cross-linked.
- **Verdict:** PASS on every guarantee — the sharpened creation triggers keep werkhof's registry
  behavior intact. `misses: none`.

### 2026-07-31 leuchtfeuer (grading PR #139 — `--reingest`, the reconcile fresh-eyes brief, the delete-brief reingest note)

- **Mode:** Mode A in a scratch sandbox, full wave protocol (`stages/initial` → wave2 → wave3 with
  the memo delete), then the NOOP re-run, a `--force` probe, and a live `--reingest` probe of the
  PR's own feature on the heavily-cited kickoff minutes. Retrieval-first grade afterwards.
- **Model:** `claude:claude-sonnet-5` (`CITADEL_INGEST_MODEL=sonnet`) · serial · wave 1 paid the
  per-source hermetic-auth retry (container auth shape), waves 2-3 ran with `CITADEL_HERMETIC=0`.
- **Result:** `check` + `lint` exit 0 after every wave AND after both probes. Wave kinds exactly as
  scripted (6 ingest / 1 reconcile + 3 ingest + 5 NOOP / 1 delete + 3 ingest + 8 NOOP); idempotency
  re-run zero sessions. **D1 delete propagation clean** (18k/02:00/memo-ref ∅ on all pages; €310k
  survives attributed to Brandt; retraction recorded). C1/C2 planted values cited with honest
  `[^llm]` correction notes; M1+M2 both flagged as callouts (2/2 stretch); Q1/Q2 attributed to the
  original authors; O1/O2 attributed, O2 never retro-written as "was right"; S1 pilot/portal kept
  apart and cross-linked; G1–G4 in English, cited to the German files; German-function-word grep
  clean; TCO honestly bare; AP-1 a single `op-` thread. Retrieval battery **9/9 correct+cited**,
  findability 8/9 in band (`rb-golive` rank 2 behind the pilot page — texture, above floor).
- **PR #139 probes:** the `--force` probe under the new fresh-eyes reconcile brief found no missing
  facts and no churn but **fixed three imprecise first-pass locators** (wrapped attendee lines) —
  exactly the intended "more than verification" behavior with a faithful wiki still converging.
  The `--reingest` probe ran delete-cleanup + fresh import in one run (report's "Re-ingested fresh"
  section, manifest re-stamped, gates green) and the full battery passed on the post-reingest wiki.
- **Misses:** VCB-006 (T4 cross-page supersession — the one temporal miss, on plain wave-3 ingest
  sessions untouched by the PR's diff), VCB-007 (style-quirk capture). Verdict: **PASS** on the
  delete/reconcile/reingest machinery under test; T4 recorded as the run's temporal miss with its
  rules-lane route.

### 2026-07-29 werkhof (first run — the registry corpus, grading PR #134's Registry feature)

- **Mode:** Mode A into the corpus workspace itself (`CITADEL_WORKSPACE=corpora/werkhof`), building
  the committed showcase; full answer-key walk of `werkhof/ground-truth.md` afterwards,
  retrieval-first.
- **Model:** `claude:claude-sonnet-5` (`CITADEL_INGEST_MODEL=sonnet`) · **rules_version:**
  `ed2320969640` · serial (`--jobs 1`) · 4 sources, 8 sessions (each first `--bare` attempt hit the
  container's auth-in-user-settings shape and retried without hermetic isolation — the shipped
  hermetic-auth fallback working as designed) · $4.14 recorded.
- **Result:** `check` exit 0, `lint` exit 0 (advisories: 2 undefined abbreviations HX/PV). All three
  collections came out as `type: Registry` pages under `registries/` with **28/28 machines, 20/20
  fault codes, 15/15 customers** as rows, one `[^sN]` per row (`lines A-B` block locators on the
  machine register, `line N` per code/CSV row; locator issues 0, so every one offline-verifies). The
  register's stated "all 28" total is cited in the scope line. **Promotion** worked unprompted:
  PV-014 and HX-201 → `objects/`, Nordwerk (K-007) → `organizations/`, each registry row reduced to
  key + link + gloss; register-only machines stayed rows (no stub pages). The HX-201 register-vs-report
  status supersession landed as a dated trace; E-142 vs E-412 and HX-201 vs HX-210 never conflated;
  E-155's deprecation hand-over survives as a row; Petersen/Albers stay attributed; the report's three
  done-able items landed as `## Open Points` threads (3 points in the generated catalog), not registry
  rows; the CSV was treated as data (0 `[^llm]` pages). Retrieval: mid-list keys `KP-011`, `E-420`,
  `K-009` each surface their registry page as the top hit.
- **Verdict:** PASS on every guarantee — the Registry rules produce complete, per-row-cited,
  retrievable registries with correct promotion on the first try. **VCB-005** recorded and moved to
  § Resolved on this evidence. `misses: none`.

### 2026-07-25 beverages + a purpose-built overlap corpus

- **Mode:** Mode A, but scoped as a **parallelism + model** test rather than a full answer-key grade:
  the question was whether `citadel ingest --jobs N` (shipped in 0.5.0) holds its guarantees under
  real page contention, and how a weaker model behaves on the same corpus. Structural gates ran in
  full; content grading was a comparison against the committed sonnet showcase of the same corpus
  plus per-fact checks on the overlap corpus, not a walk of `beverages/ground-truth.md`. A full
  answer-key grade is still owed.
- **Model:** `claude:haiku` · **rules_version:** `c99fc290864f` · `--jobs 4` · `CITADEL_HERMETIC=0`
  (the container authenticates the CLI through user-level settings that `--bare` skips — the
  hermetic-auth hint shipped in the same release came out of this).
- **Overlap corpus** (4 sources all describing one object, written for this run): forced **3 of 4
  sources to race** the same page. `check` and `lint` both exit 0 with every counter zero, the one
  merged page cites all four sources, and every source's unique facts survived three consecutive
  serial re-runs. Promote-once, all-or-nothing, and merge-into-the-winner hold under a 3-way
  collision. 7 sessions / 277 s / $0.93.
- **beverages** (14 sources): 14/14 ingested, 0 failed, **3 raced**, 35 pages vs the showcase's 36,
  `check` exit 0, `lint` exit 0 (0 broken links, 0 orphans, 0 fabricated sources, 0 wikilinks),
  $3.55 recorded. The runner was killed mid-run by the harness, which incidentally verified the
  crash contract: the live wiki stayed valid, 7 sources were durably recorded and 7 returned to
  `pending`, and the resumed run re-ran exactly those 7 — nothing half-ingested, nothing paid for
  twice.
- **Verdict:** parallel ingest PASSES on structure and provenance integrity. The deltas are model
  quality, not concurrency: **VCB-001** (unverifiable `§` locators — the sharpest haiku-vs-sonnet
  gap), **VCB-002** (one uncited sentence), **VCB-003** (unnecessary `[^llmN]` pages), and
  **VCB-004** (cross-linking, unattributed between haiku and `--jobs` until a serial-haiku baseline
  runs).
