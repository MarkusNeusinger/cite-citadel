# Ground truth — the beverages (coffee + tea) corpus

This is the **answer key** for grading `corpora/beverages/` after ingest. The corpus's `raw/` is fed
to `citadel ingest`; this file is **not** — it lives under `.claude/skills/` (never inside or beside
the corpus `raw/`), so the ingest pipeline can never see it. The `verify-corpus` skill reads it to
grade the wiki the pipeline produced. (In the grep commands below, `$WIKI` is the sandbox wiki the
corpus was ingested into — substitute it for the literal `wiki/` when grading a sandbox build.)

The corpus is deliberately messy — facts repeat, contradict, hide in one place, vary in writing style,
and include invented people and one flat-out-false claim — so a clean pass exercises all three of the
project's guarantees: **stays organized**, **links keep working**, **honest provenance**.

> Some people/companies below are **fictional by design** (Caffè Aurora, Lina Marchetti, Thornbury & Lin,
> Sir Edmund Thornbury, Mei Lin). They are *not* errors — the wiki should record them faithfully as the
> sources state them.

## The 10 raw files

| file | topic | register | gist |
| ---- | ----- | -------- | ---- |
| `raw/coffee-guide.md` | coffee | structured reference | species, origin, processing, roast, ratios, caffeine |
| `raw/espresso-and-cafe-culture.md` | coffee | prose essay | espresso mechanics; Lina Marchetti founds Caffè Aurora (1987) |
| `raw/cold-brew-notes.md` | coffee | lab notebook | cold-brew method; "cold brew higher caffeine"; half-life ~3 h |
| `raw/coffee-health-faq.md` | coffee | FAQ | half-life ~5 h, 95 mg, robusta 2×, adenosine, pregnancy |
| `raw/aurora-coffee-blog.md` | coffee | brand blog | Caffè Aurora (1985); **the false "dark roast = caffeine-free" claim** |
| `raw/tea-guide.md` | tea | structured reference | Camellia sinensis, oxidation, temps, caffeine (green 28 mg) |
| `raw/tea-history-and-trade.md` | tea | prose narrative | tea trade; Thornbury & Lin (1657); green tea ~50 mg |
| `raw/matcha-and-preparation.md` | tea | how-to | matcha prep; 60–70 mg; ceremonial vs culinary grade |
| `raw/tea-health-faq.md` | tea | FAQ | L-theanine; EGCG; tea-vs-coffee caffeine compare |
| `raw/thornbury-tea-blog.md` | tea | brand blog | Thornbury & Lin (1650); tea-vs-coffee rivalry |

## A · Known facts that MUST appear in the wiki (cited to the right source)

Single-source facts (only one file states them — they must **survive** ingest, not be dropped):

| fact | source file | note |
| ---- | ----------- | ---- |
| Espresso pulled ~9 bar, ~25–30 s, ~18 g in → ~36 g out, crema; ~63 mg/shot | `espresso-and-cafe-culture.md` | espresso mechanics |
| Cold brew often **higher** caffeine than hot drip (ratio + long steep) | `cold-brew-notes.md` | the "easy to drop" fact — see §D |
| Matcha grades: ceremonial vs culinary | `matcha-and-preparation.md` | |
| Matcha ~60–70 mg (whole leaf consumed) | `matcha-and-preparation.md` | |
| **L-theanine** (calm-alert, ~unique to tea) | `tea-health-faq.md` | |
| Coffee 3–4 cups/day *associated with* lower type-2-diabetes / Parkinson's risk | `coffee-health-faq.md` | must stay an *association* |
| White tea contains caffeine (~30–55 mg) | `tea-guide.md` | |
| Caffè Aurora founder Lina Marchetti, Trieste | `espresso-and-cafe-culture.md` + `aurora-coffee-blog.md` | year contradicts (§C) |
| Thornbury & Lin (Edmund Thornbury, Mei Lin), London/Canton, traded tea **and** coffee | `tea-history-and-trade.md` + `thornbury-tea-blog.md` | year contradicts (§C) |

## B · Repetitions — must MERGE / co-cite, never duplicate one-page-per-file

| fact | files | expectation |
| ---- | ----- | ----------- |
| Robusta ≈ 2× the caffeine of Arabica | `coffee-guide.md` + `coffee-health-faq.md` | one statement, both cited (`[^s..]` ×2) |
| Drip coffee (8 oz) ≈ 95 mg | `coffee-guide.md` + `coffee-health-faq.md` | one statement, both cited |
| Green-tea brew temp 70–80 °C | `tea-guide.md` + `matcha-and-preparation.md` | merged |
| All true tea = *Camellia sinensis* | `tea-guide.md` + `matcha-and-preparation.md` (+ history) | merged |

Failure mode to catch: a `concepts/coffee-guide.md` AND a `concepts/coffee-health-faq.md` that each
restate the 95 mg / robusta facts in isolation = the pipeline made one-page-per-file instead of routing
by fit. (Page **names** are LLM-chosen and may differ — judge by content, not filename.)

## C · Contradictions — must surface as `> [!CONTRADICTION]` (or both conflicting values co-cited on one page)

| id | subject | source A | source B |
| -- | ------- | -------- | -------- |
| `green-tea-caffeine` | green-tea caffeine per cup | `tea-guide.md`: ~28 mg | `tea-history-and-trade.md`: ~50 mg |
| `half-life` | caffeine half-life | `coffee-health-faq.md`: ~5 h | `cold-brew-notes.md`: ~3 h |
| `aurora-year` | Caffè Aurora founding year | `espresso-and-cafe-culture.md`: 1987 | `aurora-coffee-blog.md`: 1985 |
| `thornbury-year` | first English tea import | `tea-history-and-trade.md`: 1657 | `thornbury-tea-blog.md`: 1650 |

A passing wiki surfaces these rather than silently picking one value. Catching all four is the
**stretch** goal; catching ≥2 and never *silently* overwriting is the **hard** goal. Report each as
caught / not-caught.

## D · The one blatantly false fact (single source → must stand, but flagged)

`aurora-coffee-blog.md` asserts: **"Aurora Midnight is a dark roast, and the roasting fire burns off
the caffeine, so Midnight is caffeine-free — the darker the roast, the less caffeine."** This is false
in reality, but it is the blog's own word and no other source makes the same Aurora-Midnight claim.

Required wiki behaviour (honest provenance):
1. The claim **appears**, cited to `aurora-coffee-blog.md` (`[^s..]`) — not silently dropped.
2. It is **not** presented as unqualified truth: ideally an `[^llm]` model-knowledge note questions it,
   or a `> [!CONTRADICTION]` ties it to `coffee-guide.md`'s "roast barely changes caffeine / dark roast
   is not decaffeinated."
3. It is **not** rewritten into the correct fact without attribution (that would be inventing/erasing).

`citadel lint` lists pages carrying `[^llm]` facts — a good signal this was handled.

## E · The subtle "must-not-be-dropped" fact

`cold-brew-notes.md` states cold brew often ends up **higher** in caffeine than hot drip (high
grounds-to-water ratio + long steep), against the "cold = less caffeine" assumption. It is mentioned
once, in a notebook among other detail — easy to lose. It **must be present** in the wiki.

## F · Cross-topic bridges (coffee ↔ tea)

- **Caffeine** is the strongest link: both topics give numbers (drip 95 mg vs black tea 47 mg; tea
  generally less than coffee). Expect either a shared caffeine `Concept` page cited by both topics, or
  dense cross-links between the coffee and tea caffeine material. The two topics must **not** end up as
  two disconnected islands.
- **Thornbury & Lin** traded tea **and** coffee → its page (likely `type: Organization`) should be
  reachable from both the tea trade material and a coffee-trade mention.

## G · Structural gates (hard pass/fail — pure code, no judgement)

- `citadel check` → **0 errors** (required fields, honest/defined citations, relative non-broken links).
- `citadel lint` → **OK** (no missing-type, no broken links, no fabricated sources, no `[[wikilinks]]`).
- Every factual sentence carries a `[^s..]` (raw) or `[^llm..]` (model) marker; every `[^s..]` resolves
  to a real `raw/` file.
- Pages routed by `type` into the right folder (`concepts/`, `organizations/`, `persons/`, …).

## H · Abbreviations (glossary + the undefined-abbreviation lint check)

The corpus seeds the abbreviation machinery on purpose:

- **Spelled out once → defined.** `TDS` (Total Dissolved Solids) and `EGCG` (epigallocatechin gallate)
  are each expanded **exactly once**, in parenthetical form, then used bare elsewhere (`TDS` in
  `cold-brew-notes.md` + `coffee-guide.md`; `EGCG` in `tea-guide.md` + `tea-health-faq.md`). The wiki
  should carry that expansion — inline (`Total Dissolved Solids (TDS)`) and/or as a `type:
  Abbreviation` glossary page — so `citadel lint` does **not** list TDS/EGCG as undefined, and they
  may appear in the generated `## Abbreviations` table in `index.md`.
- **Never spelled out in raw → defined honestly OR flagged.** `EY` (extraction yield) is used across
  the coffee brewing material (`cold-brew-notes.md` + `coffee-guide.md`) but **never** expanded in any
  raw file. Two honest outcomes are acceptable: (a) the wiki leaves it bare and `citadel lint`'s
  *Undefined abbreviations* check surfaces `EY`; or (b) — observed, and preferable — the agent creates a
  `type: Abbreviation` page that expands it (`EY — Extraction Yield`) and labels the expansion `[^llm]`,
  since that expansion is model knowledge, not from a raw file. Either way `citadel lint` should surface
  **at least one** undefined abbreviation (`EY` and/or `FAQ`); the build never fails on it (advisory).

This is what the user means by "abbreviations should appear, at least one spelled out once": TDS/EGCG
are the spelled-out-once ones (→ defined, ideally a glossary page); EY is never spelled out in raw, so
the pipeline must either flag it (lint) or define it with an honest `[^llm]` expansion — and never just
silently invent the expansion as if it came from the source.

## Scoring

**Hard gates** (must all hold): §G structural, §A single-source facts all present, §D claim present +
attributed (not silently corrected), §E subtle fact present, §F not two disconnected islands.

**Soft / probabilistic** (LLM-dependent — report, don't hard-fail on a single miss): §C contradiction
callouts (target ≥2 of 4, stretch 4/4), §B merges being maximally tidy, §D carrying an explicit `[^llm]`
caveat, §H abbreviations (TDS/EGCG carried in with their expansion and NOT flagged undefined; EY
surfaced by lint's undefined-abbreviations check). Report each soft check as caught/partial/missed so
regressions are visible across runs.
