# Ground truth — the beverages (coffee + tea) corpus

This is the **answer key** for grading `corpora/beverages/` after ingest. The corpus's `raw/` is fed
to `citadel ingest`; this file is **not** — it lives under `.claude/skills/` (never inside or beside
the corpus `raw/`), so the ingest pipeline can never see it. The `verify-corpus` skill reads it to
grade the wiki the pipeline produced. (In the grep commands below, `$WIKI` is the sandbox wiki the
corpus was ingested into — substitute it for the literal `wiki/` when grading a sandbox build.)

The corpus is deliberately messy — facts repeat, contradict, hide in one place, vary in writing style,
and include invented people and one flat-out-false claim — so a clean pass exercises all three of the
project's guarantees: **stays organized**, **links keep working**, **honest provenance**.

> Some people/companies below are **fictional by design** (Caffè Aurora, Lina Marchetti, Cordwell
> Roastworks, Thornbury & Lin, Sir Edmund Thornbury, Mei Lin). They are *not* errors — the wiki should
> record them faithfully as the sources state them.

## The 14 raw files

| file | topic | register | gist |
| ---- | ----- | -------- | ---- |
| `raw/coffee-guide.md` | coffee | structured reference | species, origin, processing, roast, ratios, caffeine |
| `raw/espresso-and-cafe-culture.md` | coffee | prose essay | espresso mechanics; Lina Marchetti founds Caffè Aurora (1987) |
| `raw/cold-brew-notes.md` | coffee | lab notebook | cold-brew method; "cold brew higher caffeine"; half-life ~3 h; Cordwell Roastworks bean |
| `raw/coffee-health-faq.md` | coffee | FAQ | half-life ~5 h, 95 mg, robusta 2×, adenosine, pregnancy |
| `raw/aurora-coffee-blog.md` | coffee | brand blog | Caffè Aurora (1985); **the false "dark roast = caffeine-free" claim** |
| `raw/brewing-science-notes.md` | coffee | lab reference sheet | SCA Golden Cup 18–22% EY / 1.15–1.35% TDS; grind/time/temp; water GH/KH ~150 ppm; immersion vs percolation; espresso vs filter; Cordwell Roastworks lab |
| `raw/aurora-bulletin-2024.md` | coffee | dated brand bulletin (spring 2024) | Aurora lineup + prices; **planted false "coffee loses caffeine with age" claim**; 2 open questions |
| `raw/aurora-bulletin-2026.md` | coffee | dated brand bulletin (spring 2026) | superseding lineup/prices/roast; resolves a 2024 open Q + new one; **contradiction cluster vs science-notes/cold-brew** |
| `raw/tea-guide.md` | tea | structured reference | Camellia sinensis, oxidation, temps, caffeine (green 28 mg) |
| `raw/tea-history-and-trade.md` | tea | prose narrative | tea trade; Thornbury & Lin (1657); green tea ~50 mg |
| `raw/matcha-and-preparation.md` | tea | how-to | matcha prep; 60–70 mg; ceremonial vs culinary grade |
| `raw/tea-health-faq.md` | tea | FAQ | L-theanine; EGCG; tea-vs-coffee caffeine compare |
| `raw/thornbury-tea-blog.md` | tea | brand blog | Thornbury & Lin (1650); tea-vs-coffee rivalry |
| `raw/tea-processing-and-cultivars.md` | tea | enthusiast field notes | six classes incl. yellow + dark/heicha; sheng vs shou pu-erh; Yabukita / Da Hong Pao / Darjeeling flushes; shading → L-theanine/umami |

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

## I · Deep-dive nerd facts that MUST survive — and they must be TRUE

The four enrichment files carry **real** preparation/processing/cultivar knowledge (the showcase is
also a public demo, so the wiki must actually teach the correct science, not vibes). Each fact below is
single-source unless noted — it must **survive** ingest, cited to its file, and carry the **true** value.
A 4–6 grep spot-check that the real numbers landed (flatten with `tr '\n' ' '` first if a scoped grep
misses on a wrap):

| true fact | source | grep hint |
| --------- | ------ | --------- |
| SCA Golden Cup: extraction **18–22%**, strength **1.15–1.35% TDS** | `brewing-science-notes.md` | `grep -rn "18-22\|1.15"` |
| SCA golden ratio ~**55 g/L** (≈ 1:16–1:18); brew temp ~**93 °C / 90.5–96 °C** | `brewing-science-notes.md` | `grep -rniE "55 ?g|1:1[678]|90.5-96|93"` |
| water target ~**150 ppm** TDS, GH/KH balance | `brewing-science-notes.md` | `grep -rn "150"` |
| **immersion vs percolation** distinction present | `brewing-science-notes.md` | `grep -rin "percolat\|immersion"` |
| six tea classes incl. **yellow** + **dark/heicha** (not just 5) | `tea-processing-and-cultivars.md` | `grep -rin "heicha\|yellow tea\|dark tea"` |
| **sheng vs shou** pu-erh; shou = **wo dui / wet piling**, **1973**, **45–60 days** | `tea-processing-and-cultivars.md` | `grep -rniE "sheng|shou|wet piling|1973"` |
| **Yabukita** ~**70%** of Japanese tea, registered **1953** | `tea-processing-and-cultivars.md` | `grep -rn "Yabukita\|1953"` |
| **Da Hong Pao** Wuyi **rock oolong / yancha**; **rock rhyme** (yan yun); Rou Gui / Shui Xian | `tea-processing-and-cultivars.md` | `grep -rin "Da Hong Pao\|rock rhyme\|yancha"` |
| **Darjeeling**: **muscatel = second flush**, not first | `tea-processing-and-cultivars.md` | `grep -rin "muscatel"` |
| shading (~**20–30 days**) → **L-theanine up, catechins down, umami**; tencha → matcha | `tea-processing-and-cultivars.md` + `matcha-and-preparation.md` | `grep -rin "shad\|umami\|tencha"` |

These MERGE cleanly with the existing corpus (green temp 70–80 °C, all *Camellia sinensis*, EGCG/catechins,
L-theanine, matcha 60–70 mg, China vs Assam variety) — a good build co-cites the new file alongside the
old one, it does not spin up a second isolated page. Also **entity/cross-link:** `Cordwell Roastworks`
now spans `cold-brew-notes.md` + `brewing-science-notes.md` (one `type: Organization`-ish page reachable
from both), just as Thornbury & Lin bridges tea and coffee in §F.

## J · Temporal supersession — the Aurora bulletin pair (2024 → 2026)

The two dated bulletins state Aurora's **own** facts that **evolve over time**. These are **dated
updates, NOT contradictions**: the wiki keeps the current (2026) value as the live fact and records the
2024 value as **dated / superseded** (e.g. "as of spring 2024 …", a history note, or struck through),
each cited to its own bulletin. It must **not** raise a `> [!CONTRADICTION]` between the two dates (they
do not conflict — they are two points in time) and must **not** silently drop the 2024 value.

| subject | 2024 (superseded) | 2026 (current / live) |
| ------- | ----------------- | --------------------- |
| Aurora Midnight 250 g price | €13.50 | **€16.00** |
| Aurora Midnight roast profile | near-black, oily dark roast | **full-city-plus** (pulled back, sweeter) |
| Harbour Blonde price | €12.00 | **€14.00** |
| Piazza Espresso price | €12.50 | **€14.50** |
| Dolce Decaf price | €13.00 | **€15.00** |
| seasonal single origin | Rift Valley (washed Kenyan) | **Wildflower Natural** (natural Ethiopian) |

Pass = the 2026 values are the live statement, each 2024 value still present but explicitly dated/superseded
(both cited to their bulletin). Fail modes: (a) a bare `> [!CONTRADICTION]` between the two prices/roasts
(they are two dates, not a conflict); (b) the 2024 values silently gone with no dated trace.
`grep -rn "13.50\|16.00" "$WIKI"` — both Midnight prices should appear, the older one marked as prior.

## K · The contradiction CLUSTER — 2026 bulletin vs. the science (source-vs-source)

Distinct from §J: the 2026 bulletin also makes brewing claims that **directly contradict other sources on
the same topic**, and **both sides are citable**. These SHOULD surface as `> [!CONTRADICTION]` (or both
values co-cited on one page), kept **attributed to Aurora**, never silently corrected and never silently
dropped.

| id | topic | Aurora 2026 (source A) | other source (source B) |
| -- | ----- | ---------------------- | ----------------------- |
| `filter-temp` | ideal filter / pour-over water temp | `aurora-bulletin-2026.md`: **80 °C** | `brewing-science-notes.md`: SCA **~90.5–96 °C** (93 °C) |
| `ideal-extraction` | target extraction yield | `aurora-bulletin-2026.md`: **~30%** | `brewing-science-notes.md`: SCA **18–22%** (>22% over-extracted) |
| `cold-brew-caffeine` | cold brew vs. hot caffeine | `aurora-bulletin-2026.md`: cold brew is **lowest** caffeine | `cold-brew-notes.md`: cold brew often **higher** than hot drip |

Target ≥2 of 3 surfaced (stretch 3/3); report each caught / not-caught. Note `cold-brew-caffeine`
re-attacks the very myth §E's fact busts — a wiki that lets Aurora's "lowest caffeine" quietly overwrite
`cold-brew-notes.md`'s "higher caffeine" fact fails **both** §E and §K. `grep -rin "CONTRADICTION" "$WIKI"
| grep -v index.md` should now show more callouts than the four §C ones.

## L · The second planted-false claim (2024 bulletin) — attributed, not corrected

Parallel to §D. `aurora-bulletin-2024.md` asserts, in marketing voice: **"Coffee starts losing its
caffeine the moment it leaves the roaster … a month-old bag simply does not wake you up the way a fresh
one does."** This is false in reality — caffeine is a stable molecule; staling loses aroma and CO₂, not
caffeine (see `coffee-guide.md`: "caffeine is a remarkably stable molecule"). Required behaviour:

1. The claim **appears**, cited to `aurora-bulletin-2024.md` — not silently dropped.
2. It is **not** presented as unqualified truth — ideally an `[^llm]` note pushes back, or a
   `> [!CONTRADICTION]` ties it to `coffee-guide.md`'s caffeine-stability line.
3. It is **not** silently rewritten into the correct fact without attribution.

So beverages now carries **two** attributed-false claims (§D dark-roast, §L caffeine-fades-with-age) — both
must stand as stated-and-questioned, neither quietly "fixed."

## M · Open points — the "still testing" threads

The bulletins seed open-point threads (Karpathy open-questions); expect them parsed into a page's
`## Open Points` and/or the generated `open-points/` index:

- **2024:** "still testing the **60-hour Midnight rest**" → **RESOLVED in 2026** ("the 60-hour rest won;
  now standard"). The wiki should show this as an open point later **closed/resolved**, not two live
  contradictory questions.
- **2024:** "still deciding on a **natural-process Ethiopian** for summer" → also resolved in 2026 (it
  "made the cut" as Wildflower Natural).
- **2026 (new, still open):** "still testing whether **lightly mineralised water** helps the Wildflower
  natural."

Pass = at least the Midnight-rest thread shows an open→resolved arc, and the 2026 mineralised-water
question reads as a live open point. Soft/probabilistic (open-point handling varies by run).

## N · New abbreviations (extends §H)

The enrichment adds more glossary / undefined-abbreviation material:

- **Spelled out once → defined.** `SCA` (Specialty Coffee Association), `GH` (general hardness), `KH`
  (carbonate hardness), and `PPO` (polyphenol oxidase) are each expanded **exactly once** — `SCA`/`GH`/`KH`
  in `brewing-science-notes.md`, `PPO` in `tea-processing-and-cultivars.md` — then used bare. The wiki
  should carry the expansion so `citadel lint` does **not** flag them undefined.
- `EY` stays **never** spelled out in any raw file: the enrichment writes "extraction yield" in full and
  never pairs it with the acronym, so §H's EY undefined-abbreviation expectation is **unchanged**.

## Scoring

**Hard gates** (must all hold): §G structural, §A single-source facts all present, §D claim present +
attributed (not silently corrected), §E subtle fact present, §F not two disconnected islands, §I deep-dive
nerd facts present **and true** (the real SCA/cultivar/processing values landed), §J supersession handled
(2026 values live, 2024 values dated-not-dropped, no false date-vs-date contradiction), §L second
false claim present + attributed (not silently corrected).

**Soft / probabilistic** (LLM-dependent — report, don't hard-fail on a single miss): §C contradiction
callouts (target ≥2 of 4, stretch 4/4), §K contradiction-cluster callouts (target ≥2 of 3, stretch 3/3),
§B merges being maximally tidy (incl. the new tea/coffee deep-dive pages co-citing, not fanning out),
§D and §L carrying an explicit `[^llm]` caveat, §M open-point open→resolved arc, §H + §N abbreviations
(TDS/EGCG/SCA/GH/KH/PPO carried in with their expansion and NOT flagged undefined; EY surfaced by lint's
undefined-abbreviations check). Report each soft check as caught/partial/missed so regressions are visible
across runs.
