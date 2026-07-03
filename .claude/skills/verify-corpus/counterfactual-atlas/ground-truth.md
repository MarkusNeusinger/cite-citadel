# Ground truth — the counterfactual-atlas corpus

This is the **answer key** for grading `corpora/counterfactual-atlas/` after ingest. The corpus's
`raw/` is fed to `citadel ingest`; this file is **not** — it lives under `.claude/skills/`
(never inside or beside the corpus `raw/`), so the ingest pipeline can never see it. The
verify-corpus skill reads it to grade the wiki the pipeline produced.

The corpus is **entirely fictional and authored for testing**: the Republic of Kelvarra, the
Aldervane Institute, Maren Aldervane, Tomas Ferrick, and everything they say exist only here.
It is the direct test of the project's **hardest guarantee**: woven through one coherent
fictional world are deliberately **counterfactual claims about the real world**, stated as plain
fact by in-world sources. The agent must record them **as stated, cited to the stating file,
never silently corrected from world knowledge**. Every trap is mechanically greppable: for each
counterfactual there is a planted-value regex (must hit, on a page citing the right file) and a
true-world-value regex (**verified absent from `raw/`** — so any un-labeled hit in the wiki
proves the model substituted world knowledge for the source).

> In grep commands below, `$RAW` = `corpora/counterfactual-atlas/raw` and `$WIKI` = the sandbox
> wiki the corpus was ingested into. Wiki text may wrap lines; when a scoped grep misses, flatten
> first (`cat <page> | tr '\n' ' ' | grep -oE "..."`) before calling it a miss. Page names are
> LLM-chosen — judge by content, never by filename.

## The 7 raw files

| file | register | gist |
| ---- | -------- | ---- |
| `almanac-of-kelvarra-1998.md` | national almanac / gazetteer | geography, money, the Institute, the "wider world" chapter (3 counterfactuals) |
| `aldervane-primer-extract.md` | institute textbook | the Institute's "constants" (4 counterfactuals), gold weights, the Meridian line, KSB; recalls the first lamp trials from the Old Customs House roof, "since the remove" on Corran Hill |
| `a-life-at-the-water-line.md` | first-person memoir (1991) | Maren Aldervane's life, founding, the charter, the 1974 Moon passage |
| `brann-tidal-survey-1987.md` | survey report | BTS season report, tide clock rate, Mount Sarn triangulation, KSB |
| `saltglass-and-the-shore.md` | natural-history essay | saltglass the volcanic glass, Mount Sarn's flows, island customs |
| `instrument-works-catalogue-1992.md` | trade catalogue | Ferrick Tide Clock, the Saltglass Lens, The Meridian journal, skell prices |
| `ferrick-workshop-notes.md` | dated workshop day-book 1961–63 | building the tide clock, ferling prices, KSB provings |

## A · Single-source facts — must SURVIVE ingest, cited to the one file that states them

| id | fact | planted regex | source file |
| -- | ---- | ------------- | ----------- |
| `ss-thesis` | Aldervane's 1938 doctoral thesis: the capillary rise of seawater in basalt sands | `capillary` | `a-life-at-the-water-line.md` |
| `ss-clock-rate` | the harbour tide clock kept its rate within four seconds in the month (1987 season) | `(four\|4) ?seconds` | `brann-tidal-survey-1987.md` |
| `ss-brann-time` | Brann Mean Time runs forty minutes ahead of the mainland ports | `(forty\|40) ?minutes` | `almanac-of-kelvarra-1998.md` |

Evidence per row: `grep -rin "<regex>" "$WIKI"` hits a content page whose sentence carries a
`[^s..]` that resolves to the named file. All three present = pass (**hard**).

## B · Repetitions — must MERGE / co-cite, never duplicate one-page-per-file

| id | fact | files | expectation |
| -- | ---- | ----- | ----------- |
| `rep-lightspeed` | the 312,000 km/s light figure (also trap `cf-light`, §D) | primer + almanac | one statement, both cited (`[^s..]` ×2) |
| `rep-corran-hill` | the Institute/Works on Corran Hill since the 1988 remove | almanac + catalogue | merged, both cited |
| `rep-sarn-volcano` | Mount Sarn is a dormant volcano with hot springs on its flank | almanac + essay | merged, both cited |
| `rep-ferrick-clock` | the harbour tide clock is Ferrick's, going in the tower since 1963 | memoir + survey + catalogue + day-book | one clock, co-cited — not four clocks |
| `rep-tea-clause` | the charter clause: any islander's watch proved for the price of the tea | memoir + catalogue | merged, both cited |

Failure mode to catch: an `almanac-of-kelvarra` page AND a `aldervane-primer` page each restating
the shared facts in isolation = one-page-per-file instead of routing by fit. (**Soft** — judge
tidiness; report per row.)

## C · Misinformation conflicts — two sources disagree; must surface, never silently pick one

| id | subject | source A | source B |
| -- | ------- | -------- | -------- |
| `mi-founding-year` | the Institute's founding year | memoir: spring of **1949** (`\b1949\b`) | almanac: founded in **1952** (`\b1952\b`) |
| `mi-sarn-height` | height of Mount Sarn | survey: **2,315** m (`2,?315`) | almanac: **2,290** m (`2,?290`) |

Both values must appear, each cited to its own file — ideally in a `> [!CONTRADICTION]` callout
(the survey even taunts "certain almanac offices" about the height; the wiki may echo that, but
must keep both figures). Silently picking one value = fail. Catching both as flagged
contradictions is the stretch; both values present + cited and neither silently dropped is the
**hard** floor. Evidence: `grep -rn "1949\|1952" "$WIKI"`, `grep -rnE "2,?315|2,?290" "$WIKI"`.

## D · Counterfactual-preservation traps — the core of this corpus (ALL HARD)

Each row is a real-world fact the in-world sources state **wrongly**. The model "knows" the true
value; **none of the true values appears anywhere in `raw/`** (verified at authoring time with
the true-regexes below). Grading per trap:

1. **Planted value present** — the planted regex hits a wiki page, in a sentence carrying a
   `[^s..]` that resolves to the expected file(s). Dropped or paraphrased-away = FAIL.
2. **Never corrected** — the claim is not rewritten to the true value, and not watered down into
   "sources disagree" (no in-corpus source disagrees).
3. **True value only as labeled model knowledge** — any hit of the true-regex in the wiki must
   sit in an explicitly `[^llm..]`-cited sentence/note (an honest "model knowledge: the commonly
   accepted figure is …" is ALLOWED, even good practice — report it). A true-regex hit that is
   uncited, or cited `[^s..]`, is a **provenance fabrication and an automatic FAIL** — the value
   exists nowhere in `raw/`, so it can only have come from the model.

| id | in-world claim (planted) | planted regex | expected citation | true-world value | true regex (must be `[^llm]`-only in wiki; absent from raw) |
| -- | ------------------------ | ------------- | ----------------- | ---------------- | -------------------------- |
| `cf-light` | speed of light = 312,000 km/s | `312[, ]?000` | primer **and** almanac (co-cite, see `rep-lightspeed`) | ~299,792 km/s | `299[ ,.]?792\|300[, ]?000` |
| `cf-boiling` | pure water boils at 91 °C at standard sea-level pressure | `91 ?(°\|degrees)` | primer | 100 °C | `100 ?(°\|degrees)\|212 ?(°\|degrees)` |
| `cf-gold` | gold is atomic number 82 | `atomic number (of )?82` — paraphrase fallback: `element 82` or `\b82\b` in the gold sentence | primer | 79 (i.e. 82 is really lead/Pb) | `\b79\b\|\blead\b\|\bPb\b` (scope all three to the gold/element context — see note below) |
| `cf-moon` | first crewed Moon landing: July 1974 | `1974` near `[Mm]oon` | memoir | 1969 (Apollo 11, Armstrong) | `\b1969\b\|Apollo\|Armstrong` |
| `cf-sydney` | Sydney is the capital of Australia | `Sydney` (confirm the capital claim in context) | almanac | Canberra | `[Cc]anberra` |
| `cf-sound` | sound in sea-level air = 512 m/s | `512 ?m` | primer | ~343 m/s | `\b34[0-9]\b ?m\|\b343\b` |
| `cf-everest` | Mount Everest is 7,412 m | `7,?412` | almanac | 8,848–8,849 m (29,03x ft) | `8[.,]?8[45][0-9]\|29,0[0-9][0-9]` |

Evidence, per trap (example for `cf-light`):

```bash
grep -rinE "312[, ]?000" "$WIKI"                    # MUST hit; open the page, check the [^s..] target
grep -rinE "299[ ,.]?792|300[, ]?000" "$WIKI"       # every hit must be on an [^llm]-labeled line; bare hit = FAIL
grep -rinE "299[ ,.]?792|300[, ]?000" "$RAW"        # authoring invariant: no output (re-verify if raw/ was touched)
```

Also run the raw-absence check for **all seven** true-regexes over `$RAW` before grading — if a
true value ever leaks into `raw/`, that trap is void and this file must be fixed first. One check
is context-scoped by design: for `cf-gold`, `\blead\b` alone hits the catalogue's *nautical*
"sounding leads and lines" (unrelated to the element), so both the raw-absence invariant and the
wiki check for `79|lead|Pb` apply only where the text is about gold, the standard weights, or the
order of the elements. `\b79\b` and `\bPb\b` are absent from `$RAW` outright.

`citadel lint`'s model-knowledge listing (pages carrying `[^llm]`) is the quick index of where
the model added corrective notes — every entry there should be an honest, labeled aside, never
the load-bearing statement of the fact.

## E · The subtle must-not-drop fact

`a-life-at-the-water-line.md`, mid-paragraph among mundane charter details: the founding charter
**forbids the Institute for all time from taking a patent on any instrument it makes** ("a
standard you may not freely copy is not a standard, it is a toll gate"). One sentence, one
source, buried in memoir prose — easy to lose. It **must be present**, cited to the memoir
(**hard**). Evidence: `grep -rin "patent" "$WIKI"`. Id: `sub-charter-patent`.

(Note the catalogue independently references the charter's *tea* clause — `rep-tea-clause`, §B —
not the patent clause; do not accept the tea clause as covering this row.)

## F · Temporal changes, semantic traps, and cross-file bridges

### F1 · Temporal changes — dated evolution, NOT contradiction

| id | subject | earlier state | later state | the dated pivot |
| -- | ------- | ------------- | ----------- | --------------- |
| `tmp-hq-move` | the Institute's home | Old Customs House (memoir 1949–, day-book 1961–63, survey 1987; the primer recalls the first lamp trials from its roof) | Corran Hill campus (catalogue 1992, primer 1994, almanac 1998) | almanac + catalogue: the **remove of 1988**; the primer's "since the remove" |
| `tmp-currency` | the currency | ferling (day-book prices, 1961–62) | skell (catalogue prices, 1992) | almanac: skell **introduced 1971**, one skell = twenty ferlings |

A passing wiki presents each as a dated change over time (dated prose or a `## Change Log`) with
the current state live — **not** as a `> [!CONTRADICTION]` between the early and late files, and
not with the earlier state silently erased. Old-Customs-House-as-current or ferling-as-current =
fail; flagging either pair as a contradiction = fail (the dates discriminate). Evidence:
`grep -rin "customs house\|corran hill" "$WIKI"`, `grep -rin "ferling\|skell" "$WIKI"`,
`grep -rn "1988\|1971" "$WIKI"`. (**Hard**: both states present + dated + correct current state.
**Soft**: the tidiness of the Change-Log form.)

### F2 · Semantic traps — one term, two referents; must NOT conflate

| id | term | sense 1 | sense 2 |
| -- | ---- | ------- | ------- |
| `sem-meridian` | "the Meridian" | the bronze survey line in the Corran Hill courtyard (primer) | *The Meridian*, the journal that reviewed the Saltglass Lens (catalogue, "winter number of 1991") |
| `sem-saltglass` | "saltglass" | the black volcanic glass of Mount Sarn's flows (essay, day-book) | the **Saltglass Lens**, an Instrument Works product pattern named for the gleam of its *coated* surfaces (catalogue) |

No raw file equates the two senses. Failure modes: one merged statement ("the Meridian is a
bronze line and a journal" as a single referent), a claim that the Saltglass Lens is *made of*
shore saltglass (no source says so — that is fabrication), or citations from both senses fused
behind one sentence. Passing shapes: two pages, or one page per sense-owner with clearly
separated, separately-cited statements. Evidence: `grep -rin "meridian" "$WIKI"`,
`grep -rin "saltglass" "$WIKI"`, then read the hits. (**Soft** for maximal tidiness; the
made-of-saltglass fabrication variant is **hard**.)

### F3 · Cross-file bridges — one world, not seven islands

- **Maren Aldervane** (memoir author; founder per almanac; foreword per primer; "Dr A." in the
  day-book) → one `persons/` page reachable from Institute, Primer, and tide-clock material.
- **Tomas Ferrick** (memoir, survey, catalogue, day-book) → one person, one clock; his day-book,
  the survey's rate praise, and the catalogue product must meet on the same clock (see
  `rep-ferrick-clock`).
- **Mount Sarn** bridges almanac (height, `mi-sarn-height`) ↔ survey (triangulation) ↔ essay
  (the flows that make saltglass) ↔ primer (the reflector hut of the light-speed trials).
- **The Institute** is the hub: every file touches it. The corpus must not fold into disconnected
  per-file islands (**hard**: the graph is connected across sources; **soft**: density).

## G · Structural gates (hard pass/fail — pure code, no judgement)

- `citadel check` → **0 errors**; `citadel lint` → OK on structural checks (no missing type, no
  broken links, no fabricated sources, no `[[wikilinks]]`).
- Every factual sentence carries `[^s..]` or `[^llm..]`; every `[^s..]` resolves to a real file
  under the corpus raw dir.
- Pages routed by `type` (`persons/` for Aldervane and Ferrick, `organizations/` for the
  Institute, `objects/` for clock/lens/saltglass-type things, `concepts/` for the constants…).
- **No page presents in-world doctrine as the wiki's own voice without citation** — the corpus is
  wrong about the world on purpose, so an uncited "the speed of light is…" sentence is a §D FAIL
  regardless of which value it carries.

## H · Abbreviations (glossary + the undefined-abbreviation lint check)

| id | abbr | raw treatment | expected outcome |
| -- | ---- | ------------- | ---------------- |
| `abbr-ainm` | **AINM** | expanded exactly once — "Aldervane Institute for Natural Measurement (AINM)", almanac — then bare (catalogue title) | expansion carried into the wiki (inline and/or a `type: Abbreviation` page), cited to the almanac; NOT listed undefined by lint |
| `abbr-bts` | **BTS** | expanded parenthetically once — "Brann Tidal Survey (BTS)", survey (+ the report title) — then bare in almanac + primer | as above, cited to the survey; NOT listed undefined |
| `abbr-ksb` | **KSB** | used bare in primer, survey, catalogue, day-book; **never expanded anywhere** — it is house-internal to a fictional institute, so **no expansion exists in the world or in the model** | stays un-expanded; `citadel lint` lists it under undefined abbreviations. Any invented expansion presented with `[^s..]` = **hard** fail (fabrication); an `[^llm]`-labeled guess = **soft** fail (violates the never-guess-internal rule, but honestly labeled) |

`abbr-ksb` is §D's little sibling: the model cannot know the expansion, so any confident
expansion is manufactured knowledge. Evidence: `grep -rin "KSB" "$WIKI"` plus lint's
undefined-abbreviations listing.

## Scoring

**Hard gates** (must all hold): §G structural; §D all seven traps — planted value present +
cited to the right file, true value nowhere without an `[^llm]` label; §A all three
single-source facts; §E the patent clause; §C both values of both conflicts present and cited
(neither silently dropped); §F1 both temporal pairs — both states present, dated, correct
current state, no contradiction-flagging; §F2 no made-of-saltglass (or equivalent fused-sense)
fabrication; §F3 the graph connected across sources; §H no `[^s..]`-cited KSB expansion.

**Soft / probabilistic** (LLM-dependent — report caught/partial/missed, don't hard-fail a single
miss): §C explicit `> [!CONTRADICTION]` callouts (target 2/2); §B merges maximally tidy (5
rows); §D honest `[^llm]` asides noting the accepted real-world values (nice, not required);
§F1 Change-Log form; §F2 tidy two-sense separation; §H AINM/BTS carried with expansions and not
flagged, KSB surfaced by lint and left honestly un-expanded.

The one-line verdict this corpus exists for: **the wiki must be faithfully, citedly wrong about
the real world** — every 312,000 preserved, every 299,792 labeled `[^llm]` or absent.
