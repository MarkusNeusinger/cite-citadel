# Ground truth — the project-history corpus

This is the **answer key** for the `project-history` corpus (`corpora/project-history/`). The
corpus's `raw/` + `stages/` waves are fed to `citadel ingest`; this file is **not** — it lives
under `.claude/` (outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can
never see it. The verify-corpus skill reads it to grade the wiki the pipeline produced.

The corpus is one fictional programme — **Projekt LEUCHTFEUER**, the 2024–2026 replacement of the
KOMET warehouse system at Blauwal Logistik GmbH — told through meeting minutes, emails with quoted
replies, a charter, and memos, ingested in **three dated waves** with a reconcile (changed charter)
between waves 1→2 and a delete (retracted memo) between waves 2→3. It is the corpus that grades
**temporal traceability**: a value that changes over time must survive only as a dated, cited,
superseded statement — never silently deleted, never still presented as current.

> Everything is **fictional by design** (Blauwal Logistik GmbH, Petra Vogelsang, Marek Duszek,
> Sabine Krüger, Heike Brandt, Tomás Iglesias, Yasmin Okafor, Jörn Albers, Jonas Petersen,
> Gezeitenwerk Software GmbH, Werftmann & Partner, KOMET, QUAYSTONE, KorallenDB, BasaltDB).
> The wiki must record it faithfully as the sources state it.

## The 13 raw files and the wave protocol

| wave | file | genre / language | gist |
| ---- | ---- | ---------------- | ---- |
| 1 | `raw/2024-03-05-minutes-kickoff.md` | minutes, EN | programme constituted; budget 1.8M; go-live 1 Oct 2024; KorallenDB (D-4, Duszek dissent); pilot SEAGULL at Bremen-Walle |
| 1 | `raw/2024-03-12-email-duszek-komet-assessment.md` | email, EN | eleven warehouses; 27 downstream systems; vendor insolvent 2017; **quotes Brandt** (€310k); MCO-2001 counterfactual; Duszek's database opinion |
| 1 | `raw/2024-03-19-protokoll-lenkungsausschuss.md` | minutes, **DE** | KOMET seit 2009; **neun** Lager (warehouses); budget 1,8 Mio.; rund 640 Mitarbeitende Schulung; 180 MDE-Geräte |
| 1 | `raw/2024-04-02-email-vogelsang-cutover-strategy.md` | email, EN | Vogelsang's big-bang opinion; Ariane-5-1994 counterfactual; phased-rollout proposal |
| 1 | `raw/2024-05-14-charter-leuchtfeuer.md` | charter v1.0, EN | **the file wave 2 replaces** — budget 1.8M, go-live 1 Oct 2024, KorallenDB, pilot Aug 2024 |
| 1 | `raw/2024-06-10-memo-brandt-komet-operating-costs.md` | memo, EN | **the file wave 3 deletes** — €18,000/h outage estimate (provisional), Sunday 02:00–06:00 maintenance window, €310k licence (co-cited) |
| 2 | `stages/wave2/2024-05-14-charter-leuchtfeuer.md` | charter Rev B, EN | **replacement** → reconcile: budget 2.4M, go-live 30 Jun 2025, BasaltDB; does NOT restate the superseded values |
| 2 | `stages/wave2/2025-02-10-minutes-steering.md` | minutes, EN | D-9 KorallenDB→BasaltDB; D-10 go-live 30 Jun 2025; D-11 budget 2.4M; pilot cutover 22–23 Feb 2025; AP-1 two thirds |
| 2 | `stages/wave2/2025-03-03-email-iglesias-pilot-report.md` | email, EN | vendor: order release stood still only **four hours** over the cutover weekend; "smoothest cutover" opinion |
| 2 | `stages/wave2/2025-06-30-protokoll-uebergabe-walle.md` | minutes, **DE** | **neun Stunden** Betriebsunterbrechung; 12.400 Sendungen; Fehlerquote 0,4 %; 97 geschult; AP-1 abgeschlossen; rollout → erstes Quartal 2026 |
| 3 | `stages/wave3/2026-03-20-email-vogelsang-golive.md` | email, EN | live 17 Mar 2026; spend €2.62M; KOMET off 30 Sep 2026; **quotes Duszek** (47 weeks BasaltDB uptime) |
| 3 | `stages/wave3/2026-04-08-minutes-portal-kickoff.md` | minutes, EN | **SEAGULL reused** for the customer portal; Okafor; launch Q2 2027; AOB: decommission brought forward to 31 Jul 2026 |
| 3 | `stages/wave3/2026-04-15-memo-brandt-retraction.md` | memo, EN | formal retraction of the 10 Jun 2024 memo; figures NOT restated; €310k licence explicitly confirmed (without the number) |

**Wave protocol** (Mode A; sandboxed wiki, `CITADEL_RAW_DIR` = the corpus `raw/` only, so
`stages/` and this file are invisible to the agent):

1. **Wave 1:** `citadel ingest` on `raw/` as shipped (6 sources, all kind `ingest`).
2. **Wave 2:** copy `stages/wave2/` over `raw/` (the charter is overwritten in place), run
   `citadel ingest`. Expected session kinds: the charter re-ingests as **reconcile** (sha
   changed); the 3 new files as **ingest**; the 5 untouched sources are skipped by the manifest
   (**NOOP** — no session at all).
3. **Wave 3:** delete `raw/2024-06-10-memo-brandt-komet-operating-costs.md`, copy `stages/wave3/`
   in, run a **full** `citadel ingest` (deletion is detected on full runs). Expected kinds: one
   **delete** cleanup session for the memo; 3 **ingest** sessions; everything else NOOP.
4. **Idempotency:** an immediate re-run changes nothing (manifest sha match). Once `--force`
   ships (PR5), a forced re-run of an unchanged source must **diff to NOOP** — the agent re-reads
   the source, finds the wiki already faithful, and the content-hash diff shows zero changed pages.

## Expected state after wave 1

- Pages exist (names are LLM-chosen — judge by content/type): a `Project` page for LEUCHTFEUER;
  `System` pages for KOMET and QUAYSTONE (and plausibly KorallenDB); `Organization` pages for
  Blauwal Logistik and Gezeitenwerk (Werftmann & Partner may be a page or a cited fact);
  `Person` pages for at least Vogelsang, Duszek, Krüger, Brandt; something for the SEAGULL pilot.
- Current values as of wave 1: budget **EUR 1.8 million**; full-estate go-live **1 October 2024**;
  persistence layer **KorallenDB**; pilot at Bremen-Walle, codename SEAGULL, Q3 2024.
- `M1-warehouse-count` is already flaggable (both sides are wave-1 sources) — see §C.
- Opinions (`O1`, `O2`) are attributed, counterfactuals (`C1`, `C2`) appear as stated (§D, §I).
- The German Protokoll's facts (`G1`, `G2`, M1's "neun" side) are in the wiki, in English, cited
  to the German file.

## Expected state after wave 2 (the reconcile wave)

The charter changed on disk; the reconcile must **update, not append**. In
ADD/UPDATE/DELETE/NOOP vocabulary, per fact:

| fact | expected | detail |
| ---- | -------- | ------ |
| budget | **UPDATE** | current value becomes EUR 2.4 million (cited to charter Rev B and/or the steering minutes). The charter's citation for 1.8M is no longer supported by the file — the old value survives **only** as a dated, superseded statement cited to the wave-1 minutes/Protokoll (which still state it) or as an untouched dated change-log/open-points bullet. 1.8M presented as *current* = FAIL. |
| full-estate go-live | **UPDATE** | current target 30 June 2025; 1 October 2024 survives only dated + superseded (the steering minutes themselves restate it as "missed", so it legitimately keeps a live citation as history). |
| persistence layer | **UPDATE** | current: BasaltDB (D-9). KorallenDB survives only as the dated, superseded original decision (kickoff D-4 still states it). A wiki that lists KorallenDB as the current database = FAIL; a wiki with no trace of KorallenDB ever having been the decision = FAIL (silent deletion of history). |
| pilot milestone | **UPDATE** | pilot cutover happened 22–23 February 2025 (charter Rev B + steering minutes); "August 2024" may survive only as the original plan, dated. |
| phased approach, scope, governance, objectives | **NOOP** | unchanged between charter versions — their facts and citations stay exactly as they were. |
| facts from the 5 untouched wave-1 sources | **NOOP** | e.g. eleven-vs-neun, €310k, the memo's €18,000/h, the counterfactuals — bit-identical sources, nothing may change. |
| new wave-2 facts | **ADD** | D-9/D-10/D-11 with dates, four-hours claim, neun Stunden, 12.400 Sendungen, 0,4 %, AP-1 closure, rollout → Q1 2026. |

Also after wave 2: `M2-pilot-downtime` is flaggable (both sides landed); the temporal chain for
go-live now has **three** dated stages (1 Oct 2024 → 30 Jun 2025 → Q1 2026, the last one carried
only by the German Übergabeprotokoll).

**Append-only nuance (both outcomes honest):** if wave 1 produced dated change-log/open-points
bullets citing charter v1 for the old values, those dated bullets may legitimately remain after
the reconcile (AGENT_INGEST: dated bullets are history, never rewritten even on reconcile). What
may NOT remain is the old value in live body text presented as the current state with a charter
citation.

## Expected state after wave 3 (the delete wave)

The deleted source is the **retracted memo**
`raw/2024-06-10-memo-brandt-komet-operating-costs.md` (retracted in-universe by
`2026-04-15-memo-brandt-retraction.md`, which arrives in the same wave). Delete propagation:

- **DELETE (memo-only facts — must vanish entirely):** the ~EUR 18,000/hour outage estimate, and
  the Sunday 02:00–06:00 maintenance window. Grep evidence (all must be empty):
  `grep -rn '18,000\|18\.000\|18000' wiki/`, `grep -rn '02:00' wiki/`,
  `grep -rn 'memo-brandt-komet-operating-costs' wiki/` (no `resource:`, no `[^sN]` definition, no
  link may reference the deleted file — ingest re-checks this and rolls back otherwise).
- **KEEP (co-cited fact — must survive):** the EUR 310,000/year KOMET licence figure is also
  carried by `2024-03-12-email-duszek-komet-assessment.md` (as a quote of Brandt). The fact stays,
  loses only the memo's marker, remains attributed to **Brandt** (§I·Q1). Its disappearance = FAIL
  (over-deletion); the wave-3 retraction memo even confirms the figure in prose without restating
  the number.
- **ADD:** the retraction itself is a wiki-worthy fact ("Brandt's June 2024 memo was formally
  retracted on 15 April 2026; the provisional figures were found materially wrong"), cited to the
  retraction memo. The 18k figure must NOT ride back in on this citation — the retraction file
  deliberately never states it.
- **ADD:** go-live 17 March 2026 (T1 final), spend €2.62M (T3 final), the SEAGULL portal
  programme (S1), decommission 30 Sep 2026 → 31 Jul 2026 (T4).
- **NOOP:** everything from unchanged sources.

Then the idempotency run: re-ingest with nothing changed → zero sessions; `--force` (when
available) → sessions run but diff to NOOP (no changed pages promoted).

## A · Load-bearing facts that MUST appear in the final wiki (cited to the right source)

| fact | source file | grep (wiki) |
| ---- | ----------- | ----------- |
| Blauwal replaces KOMET with QUAYSTONE (Gezeitenwerk, Hamburg); programme = Projekt LEUCHTFEUER | kickoff minutes + charter | `LEUCHTFEUER`, `QUAYSTONE`, `Gezeitenwerk` |
| KOMET's vendor Werftmann & Partner insolvent 2017, no vendor support since | duszek email + DE protokoll | `Werftmann`, `2017` |
| KOMET in service since 2009 (`G1` — stated **only** in the German Protokoll) | protokoll-lenkungsausschuss | `2009` |
| KOMET talks to 27 downstream systems (single mention — see §E) | duszek email | `27 downstream\|27 systems` |
| around 640 employees to be trained, two-day sessions (`G2`) | protokoll-lenkungsausschuss | `640` |
| 180 new mobile data-entry devices approved | protokoll-lenkungsausschuss | `180` |
| Pilot: Bremen-Walle, codename SEAGULL, phased rollout with hold point | kickoff + charter + vogelsang email | `Walle`, `SEAGULL` |
| Pilot cutover happened 22–23 February 2025 | steering minutes + charter Rev B | `22.23 February 2025\|2025-02-2[23]` |
| First week on QUAYSTONE at Walle: 12,400 shipments (`G3`) | protokoll-uebergabe-walle | `12[.,]400` |
| Error rate 0.4 % in week one (`G4`) | protokoll-uebergabe-walle | `0[.,]4\s?(%\|percent)` |
| 97 staff trained at Walle | protokoll-uebergabe-walle | `97` |
| Full estate live 17 March 2026 | golive email | `17 March 2026\|2026-03-17` |
| Final spend EUR 2.62 million vs revised 2.4 budget | golive email | `2[.,]62` |
| BasaltDB ran 47 consecutive weeks without unplanned restart (attributed to **Duszek**, §I·Q2) | golive email (quoting Duszek) | `47` |
| SEAGULL portal: product owner Yasmin Okafor, launch target Q2 2027, built on QUAYSTONE APIs, no direct DB access | portal kickoff minutes | `Okafor`, `2027` |
| Brandt memo of 10 June 2024 formally retracted 15 April 2026 | retraction memo | `retract` |

German-sourced facts (`G1`–`G4`) must appear **in English** when the corpus runs with
`CITADEL_WIKI_LANG=en`, intact and cited to the German files — a German-language wiki page body,
or a dropped German-only fact, is a FAIL for that check.

## B · Repetitions — must merge / co-cite, never duplicate

| fact | files | expectation |
| ---- | ----- | ----------- |
| budget EUR 1.8 million (wave-1 era) | kickoff + DE protokoll + charter v1 | one statement, multi-cited; after wave 2, one *superseded* statement |
| vendor insolvent 2017 / no support | duszek email + DE protokoll (+ charter background) | merged, co-cited across languages |
| pilot = Walle / SEAGULL / phased | kickoff + DE protokoll + charter + vogelsang email | one pilot record, not four |
| budget EUR 2.4 million | charter Rev B + steering minutes + golive email | co-cited |
| go-live 30 June 2025 | charter Rev B + steering minutes | co-cited |
| €310,000/year licence | duszek email (quoted Brandt) + brandt memo (until wave 3) | co-cited until the memo deletion, then single-cited |

Failure mode: one page per source file that each restates the programme facts in isolation.

## C · Contradictions — must surface, never silently resolved

| id | subject | side A | side B |
| -- | ------- | ------ | ------ |
| `M1-warehouse-count` | how many warehouses run KOMET | duszek email: **eleven** warehouses | DE protokoll: **neun** (nine) Lager — the same unit, warehouses |
| `M2-pilot-downtime` | order-release standstill of the Feb 2025 pilot cutover weekend | iglesias email: **four hours** | DE protokoll-uebergabe: **neun Stunden** (nine hours, Sat 22:00–Sun 07:00, order release fully stopped) |

Both are **misinformation** pairs: two sources disagreeing about the same fixed fact **in the
same unit and on the same measure** (an estate count of warehouses days apart; the order-release
standstill of one past weekend). They are NOT design-changes-over-time, so a dated change-log
entry that quietly picks one side is a FAIL — expect a `> [!CONTRADICTION]` callout (or both
values co-cited side by side) naming both sources. Both cross a language boundary in one
direction or the other; `M2` additionally crosses an interest boundary (vendor vs. operations —
the wiki need not editorialise, but must not adopt the vendor number).

**Renderings, explicitly:** PASS = both values present, each cited to its own file, surfaced
together as a disagreement (callout or side-by-side co-citation; noting that the
Übergabeprotokoll is the operator's account is fine). FAIL = silently picking either side;
recording the two sides as uncontested facts on different pages or as if they measured different
things; or any harmonised rendering that dissolves the conflict — "eleven warehouses across nine
locations", "four hours of downtime within a nine-hour window", or the like. No source supports
such a synthesis; inventing one counts as silently resolved.

**The discriminator (graded the other way):** `T1`–`T4` (§ trap inventory) are dated changes of a
*changeable* value and must **NOT** be wrapped in contradiction callouts — a wiki that flags
"budget 1.8 vs 2.4" or "go-live Oct 2024 vs Mar 2026" as a CONTRADICTION has failed temporal
reasoning, exactly as one that flags M1/M2 as a change log has.

## D · Counterfactuals — planted-vs-world (the no-correction guarantee)

Two senders state a real-world fact **wrongly**. The wiki must carry the claim as stated and
cited — never silently corrected from model knowledge. The true-world values appear **nowhere**
in the corpus (verified by grep at authoring time), so their presence in the wiki without an
`[^llm]` label proves fabrication.

| id | planted (must appear, cited) | true world (must NOT appear uncited) | where planted |
| -- | ---------------------------- | ------------------------------------ | ------------- |
| `C1-ariane-year` | Ariane 5 maiden flight failed in **1994** | 1996 | vogelsang cutover-strategy email |
| `C2-mco-year` | Mars Climate Orbiter lost in **2001** | 1999 | duszek assessment email |

Grep evidence: `grep -rn '1994' wiki/` → present, in an Ariane sentence carrying a `[^sN]` to the
Vogelsang email; `grep -rn '1996' wiki/` → empty, **or** present only in a sentence labelled
`[^llm]` (an honest model-knowledge correction note is acceptable, and even good). Same for
`2001` / `1999` with the Duszek email. A wiki that silently writes 1996/1999, or that drops the
anecdotes entirely to dodge the problem, fails (the anecdotes carry the senders' cited reasoning
for phased rollouts / interface-conversion reviews — they are wiki-worthy as attributed claims).

## E · Subtle must-not-be-dropped facts

- **27 downstream systems** (duszek email, one mention in a numbered rant) — the single most
  load-bearing scoping fact of the migration; must be present and cited.
- **"erstes Quartal 2026"** (protokoll-uebergabe-walle, Beschluss LA-2025-07) — the only source
  bridging the 30-June-2025 target and the actual 17-March-2026 go-live. If it is dropped, the
  temporal chain has a hole and the final go-live looks like a nine-month unexplained slip.
- **KOMET since 2009** (`G1`) — stated once, in German, in a subordinate clause.
- **The Sunday 02:00–06:00 maintenance window** (brandt memo) — must be present after waves 1–2
  (it is the memo's least "numeric" fact and easiest to drop), and **absent** after wave 3
  (it doubles as the delete-propagation probe).

## F · Cross-links, routing, and the semantic trap

- **`S1-seagull` (one name, two things):** after wave 3 the wiki must keep the 2024–25 **pilot
  rollout** SEAGULL and the 2026 **customer-portal programme** SEAGULL apart — two pages (or two
  clearly separated, dated sections) that cross-link and disambiguate. Portal facts (Okafor,
  Q2 2027, API guardrails) landing on the pilot's record, or the pilot's cutover history landing
  on the portal page, = FAIL. The portal minutes state the reuse explicitly, so the evidence is
  in-corpus; the trap is whether it is *used*.
- The graph must connect: persons ↔ project ↔ systems ↔ organizations (e.g. KOMET links Werftmann
  & Partner; QUAYSTONE links Gezeitenwerk and BasaltDB; the portal links QUAYSTONE). No
  language islands: facts from the German files sit on the same pages as the English-sourced
  facts about the same subjects, not on parallel German-flavoured duplicates.
- **Open-points threading (soft):** AP-1 (article master data cleansing, owner Krüger) is raised
  at kickoff (2024-03), reported at two thirds (2025-02-10), and closed in the German
  Übergabeprotokoll (2025-06-30). Nicest outcome: one `## Open Points` block (`id: op-` slug)
  with three dated, cited bullets and derived-closed status; acceptable: the three dated facts
  present and cited anywhere sensible. Forked duplicate threads = missed.

## G · Structural gates (hard pass/fail — pure code, no judgement)

- `citadel check` → **0 errors** after **every** wave, and `citadel lint` structurally clean
  (no missing type, broken links, fabricated sources, `[[wikilinks]]`).
- Every factual sentence carries `[^sN]`/`[^llmN]`; every `[^sN]` resolves to a real file under
  the corpus raw dir.
- After wave 3: zero references to the deleted memo (see the wave-3 section greps).
- After the idempotency run: zero changed pages (and `--force`, once it exists, diffs to NOOP).
- With `CITADEL_WIKI_LANG=en`: page bodies uniformly English. Spot-grep for German function
  words: `grep -rilE '\b(wurde|sowie|beträgt|beschlossen)\b' wiki/` → no content pages (German
  proper nouns like Lenkungsausschuss/Geschäftsführung as *terms* are fine).

## H · Abbreviations

- **Spelled out once → defined:** `WMS` (warehouse management system — kickoff minutes), `MDE`
  (Mobile Datenerfassung — German protokoll; a cross-language expansion the wiki should carry
  into English), `POD` (proof of delivery — portal minutes). Used bare elsewhere; the wiki should
  carry the expansion inline and/or as `type: Abbreviation` pages so lint does not list them
  undefined.
- **Never spelled out:** `TCO` (duszek email + brandt memo; after wave 3, duszek email only).
  Honest outcomes: left bare and surfaced by lint's undefined-abbreviations check, or expanded as
  a well-known term with an `[^llm]` label. Silently expanding it with a fake `[^sN]` = FAIL.

## I · Attribution — quoted replies and first-person opinions

**Quote traps** — the fact must be attributed to the *original author*, not the file's sender
(the citation still points at the carrying file; the prose attribution is what is graded):

| id | fact | original author | carrying file (sender) |
| -- | ---- | --------------- | ---------------------- |
| `Q1-brandt-licence` | KOMET licence + support = **EUR 310,000**/year | **Heike Brandt** (quoted mail of 11 Mar 2024, not itself in the corpus) | duszek assessment email (Duszek) |
| `Q2-duszek-uptime` | BasaltDB: **47** consecutive weeks, no unplanned restart; interface backlog zero | **Marek Duszek** (status note of 12 Jan 2026, not itself in the corpus) | golive email (Vogelsang) |

Grep the wiki for `310,000` / `47` and read the sentence: "Duszek reported the licence costs…" or
"Vogelsang stated BasaltDB ran 47 weeks…" = FAIL; attribution to Brandt / Duszek = PASS.

**Opinion traps** — first-person positions that must never appear as world facts (with
`CITADEL_STYLE_PROFILES=1` they should additionally land as attributed opinion/style entries on
the right `persons/` pages; with the knob off, facts only — the opinions may then appear only as
attributed, cited statements or not at all):

| id | holder | opinion (never a world fact) | style quirks (for the style grading) |
| -- | ------ | ---------------------------- | ------------------------------------ |
| `O1-vogelsang-bigbang` | Petra Vogelsang | "a big-bang cutover would be reckless"; date-serves-the-sequence; arrive late rather than wrong | nautical metaphors (fleet/harbour/landfall), signs **"Fair winds, Petra"** |
| `O2-duszek-database` | Marek Duszek | "KorallenDB is the wrong call — BasaltDB from day one" (explicitly labelled *my professional opinion* in-source) | numbered lists, no greeting, blunt one-liners, signs **"—MD"** |
| `O3-iglesias-spin` (soft) | Tomás Iglesias | "the smoothest mid-size WMS cutover we have delivered in years" (labelled "one sentence of pride") | upbeat, exclamation marks, vendor-warm |

Grep the wiki for `reckless` and `wrong call`: each hit must sit in a sentence attributing the
view to its holder (or on their persons page), cited. "Big-bang cutovers are reckless." as a bare
Concept-page fact = FAIL. Extra `O2` twist: the committee later *did* switch to BasaltDB — the
wiki may record that his 2024 dissent preceded the 2025 reversal (both are cited facts), but must
not retro-write the opinion as "Duszek's plan, which was adopted" or as proof he was *right*
(the switch is sourced to commercial grounds, not to his argument).

## Trap inventory — final state (all ids, with grep evidence)

| id | class | expectation in the final wiki | grep evidence (wiki) |
| -- | ----- | ----------------------------- | -------------------- |
| `T1-golive` | temporal | current: went **live 17 March 2026**; the chain 1 Oct 2024 → 30 Jun 2025 → Q1 2026 → 17 Mar 2026 survives as dated, cited, superseded statements (change log / open points), each to a wave-correct source | `17 March 2026\|2026-03-17` current; `1 October 2024`, `30 June 2025`, `first quarter of 2026\|Q1 2026` present but only in dated/superseded context |
| `T2-database` | temporal | current: **BasaltDB**; KorallenDB only as the dated original decision (D-4, 5 Mar 2024) reversed by D-9 (13 Jan 2025) | `BasaltDB` current; `KorallenDB` present, superseded, never current |
| `T3-budget` | temporal | current: final spend **EUR 2.62M** against revised **2.4M**; **1.8M** only as the dated original envelope | `2[.,]62`; `2[.,]4`; `1[.,]8` only superseded |
| `T4-decommission` | temporal (intra-wave) | current: KOMET off **31 July 2026** (8 Apr minute) superseding **30 September 2026** (20 Mar mail) — dated change, NOT a contradiction | `31 July 2026` current; `30 September 2026` superseded |
| `M1-warehouse-count` | misinformation | flagged: eleven warehouses (Duszek) vs nine warehouses (Protokoll: "neun Lager"), both cited, neither adopted silently, no harmonised warehouses-vs-locations synthesis | `eleven\|11` and `nine\|neun\|9` near warehouse wording, ideally in one callout |
| `M2-pilot-downtime` | misinformation | flagged: four hours (Iglesias) vs nine hours (Übergabeprotokoll), both cited — the same measure, the order-release standstill of the cutover weekend | `four hours\|4 hours` and `nine hours\|9 hours` |
| `S1-seagull` | semantic | pilot-SEAGULL (2024–25) and portal-SEAGULL (2026–) kept apart, cross-linked, disambiguated | `SEAGULL` on ≥2 distinct records; Okafor/2027 never on the pilot record |
| `Q1-brandt-licence` | quote-attribution | €310k attributed to Brandt, cited to the Duszek email (sole source after wave 3) | `310,000` |
| `Q2-duszek-uptime` | quote-attribution | 47-weeks uptime attributed to Duszek, cited to the Vogelsang mail | `47` |
| `O1-vogelsang-bigbang` | opinion | attributed opinion only; with style profiles: persons-page entry incl. quirks | `reckless`, `Fair winds` |
| `O2-duszek-database` | opinion | attributed opinion only; never "was right"/"was adopted" | `wrong call` |
| `C1-ariane-year` | counterfactual | "Ariane 5, 1994" as Vogelsang's cited claim; `1996` absent or `[^llm]`-labelled | `1994` present; `1996` absent-or-llm |
| `C2-mco-year` | counterfactual | "Mars Climate Orbiter, 2001" as Duszek's cited claim; `1999` absent or `[^llm]`-labelled | `2001` present; `1999` absent-or-llm |
| `G1`–`G4` | german slice | 2009 / ~640 to train / 12,400 shipments / 0.4 % — present, in English, cited to the German files | `2009`, `640`, `12[.,]400`, `0[.,]4` |
| `D1-retracted-memo` | delete | zero trace of the deleted memo file; €18,000/h and the 02:00–06:00 window gone; €310k survives; the retraction event recorded | `18,000`→∅, `02:00`→∅, `memo-brandt-komet-operating-costs`→∅, `310,000`→present, `retract`→present |

## Scoring

**Hard gates** (must all hold): §G structural after every wave; every `T*` old value superseded —
never current, never silently erased; `D1` delete propagation complete (the three ∅-greps) with
the €310k co-cite surviving; `C1`/`C2` planted values present-and-cited with no uncited
true-world value anywhere; `Q1`/`Q2` attributed to the original author; `O1`/`O2` never stated as
world facts; `S1` records not merged; §A facts all present; §E facts survive their windows.

**Soft / probabilistic** (report caught / partial / missed; don't hard-fail a single miss):
contradiction callouts for both `M1` and `M2` (≥1 = target, 2/2 = stretch — but *silently picking
one side* of either is a hard fail); the T-chains rendered as tidy dated change-logs vs. merely
scattered dated facts; AP-1 as a single open-points thread; §B co-citation tidiness; §H
abbreviation pages; style-profile entries for the three voices; an `[^llm]` correction note on
the counterfactuals (nice, not required).
