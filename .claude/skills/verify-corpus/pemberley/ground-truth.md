# Ground truth — the pemberley corpus

This is the **answer key** for grading `corpora/pemberley/` after ingest. The corpus's `raw/` (one
file, the whole novel) is fed to `citadel ingest`; this file is **not** — it lives under
`.claude/skills/` (never inside or beside the corpus `raw/`), so the ingest pipeline can never see
it. The verify-corpus skill reads it to grade the wiki the pipeline produced.

The corpus is a single ~730,000-character public-domain source: **Jane Austen, *Pride and
Prejudice*** (Project Gutenberg #1342, boilerplate stripped), in `raw/pride-and-prejudice.txt`. It
is the project's **large-source + narrative** stress test. Because one file dwarfs
`CITADEL_MAX_SOURCE_CHARS`, ingest folds it in over **many segments** into one staging copy; the
grade proves that (1) every third of the book survived the merge, (2) the relationship graph came
out connected, (3) in-novel misinformation is attributed not adopted, and (4) the narrative's early
states survive only as arc, never as the wiki's current fact.

> In grep commands below, `$RAW` = `corpora/pemberley/raw` and `$WIKI` = the sandbox wiki the
> corpus was ingested into. There is exactly **one** raw file, so every `[^sN]` in a passing wiki
> resolves to `pride-and-prejudice.txt`. Wiki prose wraps; when a scoped grep misses, flatten first
> (`cat <page> | tr '\n' ' ' | grep -iE "…"`) before calling it a miss. Page names are LLM-chosen —
> judge by content and `type`, never by filename. Names must match the text: **Mr. Darcy** /
> **Fitzwilliam Darcy**, **Wickham**, **Mr. Bingley**, **Mr. Collins**, **Lady Catherine de Bourgh**.

## The one raw file

| file | chars | what it is |
| ---- | ----- | ---------- |
| `pride-and-prejudice.txt` | ~730k | the full novel, title page through "THE END", reproduced text-faithfully (line endings normalized to LF); only the PG START/END marker lines and any wrapping licence text removed |

**Authoring invariant (re-verify if `raw/` was touched):** every planted regex below was confirmed
to **hit** `$RAW`, and every "must be absent / only-as-arc" true value was confirmed against the
text. `grep -ic "gutenberg" "$RAW/pride-and-prejudice.txt"` must return **0** (no boilerplate left).

## A · Relationship graph — must come out connected and correctly paired (HARD)

The core structural guarantee: one connected graph of people, marriages, and estates — not a
per-chapter pile.

### A1 · The five Bennet sisters (all five must be present as people)

| sister | grep (wiki) | note |
| ------ | ----------- | ---- |
| Jane Bennet (eldest) | `\bJane\b` | marries Bingley (§A2) |
| Elizabeth Bennet ("Lizzy") | `Elizabeth\|Lizzy` | the protagonist; marries Darcy |
| Mary Bennet | `\bMary\b` | the bookish middle sister; does not marry in the novel |
| Catherine "Kitty" Bennet | `\bKitty\b\|Catherine Bennet` | a sister — **not** Lady Catherine de Bourgh (see the trap below) |
| Lydia Bennet (youngest) | `\bLydia\b` | elopes with, then marries, Wickham |

**Semantic trap (HARD not to conflate):** "Catherine" names two different people — **Kitty**
(Catherine Bennet, a Bennet sister) and **Lady Catherine de Bourgh** (Darcy's aunt, mistress of
Rosings). They must not be merged into one person. Their parents are **Mr. Bennet** and **Mrs.
Bennet** of Longbourn (`Mr\. Bennet`, `Mrs\. Bennet`).

### A2 · The marriages that conclude the novel (each pairing HARD)

| couple | grep (wiki) — married-name anchor | who |
| ------ | --------------------------------- | --- |
| Jane Bennet ↔ **Mr. Bingley** | `Mrs\. Bingley` | eldest sister + Netherfield's tenant |
| Elizabeth Bennet ↔ **Mr. Darcy** | `Mrs\. Darcy` | protagonist + master of Pemberley |
| Lydia Bennet ↔ **Wickham** | `Mrs\. Wickham` | youngest sister + the militia officer (after the elopement) |
| **Charlotte Lucas** ↔ **Mr. Collins** | `Mrs\. Collins` | Elizabeth's friend + the clergyman heir to Longbourn |

Each of the four couples must be recorded as a marriage/pairing, each partner cross-linked. Wrong
pairings (e.g. Elizabeth↔Bingley, Jane↔Darcy) = FAIL. The final chapter states three of them
together — "Mrs. Bennet got rid of her two most deserving daughters … visited **Mrs. Bingley**, and
talked of **Mrs. Darcy**"; Lydia is **Mrs. Wickham** and Charlotte **Mrs. Collins** earlier in the
book. Evidence: `grep -rinE "Mrs\. (Bingley|Darcy|Wickham|Collins)" "$WIKI" | grep -v index.md`.

### A3 · The four estates and their occupants (HARD: estate present + correct occupant)

| estate | grep | occupant / role |
| ------ | ---- | --------------- |
| **Longbourn** | `Longbourn` | the Bennet family home; entailed away to Mr. Collins |
| **Netherfield** | `Netherfield` | rented by Mr. Bingley (near the Bennets) |
| **Pemberley** | `Pemberley` | Mr. Darcy's estate in Derbyshire |
| **Rosings** | `Rosings` | Lady Catherine de Bourgh's seat in Kent; Mr. Collins's Hunsford parsonage adjoins it |

Each estate should be its own `objects/` (or `systems/`/place) record, linked to its occupant.
Longbourn-as-Darcy's or Pemberley-as-Bingley's = FAIL. Evidence:
`grep -rin "Pemberley" "$WIKI"` etc., then read the linked occupant.

### A4 · The economic engine — the entail on Longbourn (HARD)

The motive force of the whole marriage plot: **Longbourn is entailed to the male line**, so on Mr.
Bennet's death the estate passes to his cousin **Mr. Collins** — none of the five daughters can
inherit it. That is why the sisters must marry, and marry security: the romance is a survival plot,
not a courtship for its own sake. §A3 already places Longbourn↔Collins; A4 adds the *why* — the
entail and its consequence, the fact every scholar names as the novel's economic driver.

| check | expectation | grep (wiki) |
| ----- | ----------- | ----------- |
| the entail is recorded | Longbourn entailed to the male line / to Mr. Collins | `entail` on the Longbourn / Bennet / Collins page |
| its consequence is recorded | the daughters cannot inherit → the pressure to marry | `entail` near `Collins` and (`daughters`\|`inherit`\|`male`) |

PASS = the wiki states Longbourn is entailed to Mr. Collins **and** that this disinherits the Bennet
daughters (so the sisters must marry). FAIL = the entail is absent, or Longbourn is recorded as
freely inheritable by the daughters. Id: `econ-entail`.

## B · In-novel misinformation — Wickham's false account (HARD: attributed, not adopted)

Early in the novel Wickham tells Elizabeth a **false** story: that the late (old) Mr. Darcy
*bequeathed him the best living in his gift*, and that the present Mr. Darcy cruelly, out of
jealousy, denied him this inheritance and left him to a military life. Elizabeth (and the first-time
reader) believes it.

The **truth** is delivered later, in **Darcy's letter** (§E middle third, "Be not alarmed, madam"):
Wickham **resigned all claim** to the living and **accepted three thousand pounds in return**, spent
it in idleness, then came back demanding the living anyway; Darcy refused. Wickham is the villain,
not the victim.

Grading — the wiki must record Wickham's version **as Wickham's claim**, and the letter **as the
correction**, never state the false version in the wiki's own voice:

| check | expectation | grep |
| ----- | ----------- | ---- |
| the claim is present, **attributed to Wickham** | a sentence tying the living/inheritance grievance to Wickham *saying* it | `bequeath\|the best living\|the living` on a page attributing it to Wickham |
| the correction is present, from **Darcy's letter** | Wickham resigned the claim and took £3,000 | `three thousand pounds\|resigned all claim` |
| **never adopted as plain fact** | no uncited/`[^sN]`-as-narrator sentence stating "Darcy cheated/robbed Wickham of his inheritance" as truth | read the hits: a bare "Darcy denied Wickham his rightful living" with no attribution = FAIL |

PASS = the grievance is framed as Wickham's account and marked later-revealed-false (the two
versions may sit in one "disputed"/"revealed" note, or Darcy's page carries the true account and
Wickham's page the claim, cross-linked). FAIL = the wiki asserts Wickham's slander as the settled
history of Darcy, or drops the episode entirely to dodge it (it is load-bearing character material).
Id: `mi-wickham-living`.

## C · Narrative supersession — early states survive only as arc, not final fact (HARD)

A value that *changes over the course of the story* must be recorded as the arc, with the **ending**
as the current state — never the opening state frozen as the wiki's fact, never the arc silently
erased.

| id | early state (arc only) | final state (current) | evidence |
| -- | ---------------------- | --------------------- | -------- |
| `sup-lizzy-darcy` | Elizabeth **dislikes** Darcy — refuses his first proposal ("the last man in the world whom I could ever be prevailed on to marry") | she **accepts** him; they marry (Mrs. Darcy) | `last man in the world` (early) + `Mrs\. Darcy` (final) |
| `sup-proposals` | Darcy's **first proposal** at Hunsford is **refused** | his **second proposal** is **accepted** ("you are too generous to trifle with me … my affections and wishes are unchanged") | `first proposal\|refused` + `affections and wishes are unchanged\|second proposal\|accepted` |
| `sup-jane-bingley` | Jane and Bingley are **separated** (Bingley's party quits Netherfield; the match is discouraged) | they **reunite** and marry (Mrs. Bingley) | `separat\|Netherfield` early + `Mrs\. Bingley` final |

PASS = the final state is the live/current fact and the earlier state appears only as dated/ordered
narrative history (a "story arc", "initially … later …", or change-log framing). FAIL = the wiki
states Elizabeth *dislikes* Darcy or that his proposal *was refused* as the standing current fact,
or omits the reversal so the arc is invisible. Reversal traps must **not** be rendered as a
`> [!CONTRADICTION]` between two sources — there is only one source, and the change is narrative
time, not a disagreement.

**The arc's turning points — the mechanism, not just the endpoints (SOFT enrichment).** Elizabeth's
reversal is not a bare flip; scholars treat two pivots as the novel's hinge. **Darcy's letter**
(§B/§E — it refutes Wickham and explains the Jane–Bingley separation, forcing Elizabeth to confront
her own prejudice) and the **Pemberley visit** (the housekeeper's praise and Darcy's changed,
gracious manner on his own ground reverse her estimate of him). Darcy's letter is already HARD via
§B/§E; the **Pemberley turn** is graded soft here — if the wiki records the Pemberley visit as the
point Elizabeth's opinion of Darcy begins to change, credit it. Grep: `Pemberley` near Elizabeth and
(`opinion`\|`view`\|`changed`\|`altered`\|`began`). Id: `sup-pemberley-turn` (soft).

## D · Narrator irony — the famous opening sentence (SOFT)

*Pride and Prejudice* opens: **"It is a truth universally acknowledged, that a single man in
possession of a good fortune must be in want of a wife."** This is the narrator's **ironic**
observation (immediately undercut by the Bennet household), not a universal fact about the world.

If the wiki surfaces this line at all, it must be attributed as the **novel's / narrator's opening
observation** (cited to the source), never asserted as the wiki's own truth-claim about single men.
A bare Concept-page fact "Wealthy single men want wives[^s1]" that misreads the irony as doctrine is
the failure mode. Evidence: `grep -rin "universally acknowledged" "$WIKI"` — read the framing.
(Soft: presence is optional; if present, correct ironic attribution is what is judged.) Id:
`irony-opening`.

## E · Chunking integrity — every third of the novel must be present and cited (HARD)

The point of the corpus: one ~730k-char file is folded in over many segments, and **facts from the
first, middle, and last third must ALL appear and cite the source** — proving every segment merged
into the one staging copy, not just the first pass. Each anchor below was verified against the text
at the approximate position shown.

| third | anchor fact | grep (wiki) | ~position in file |
| ----- | ----------- | ----------- | ----------------- |
| **first** | the **Netherfield ball** (Bingley gives a ball at Netherfield) | `Netherfield ball\|ball at Netherfield` | ~27% |
| **first** | **Jane falls ill** at Netherfield (caught cold riding in the rain; stays to be nursed) | `caught (a )?cold\|violent cold\|very ill` near Jane/Netherfield | ~13% |
| **middle** | the **Hunsford proposal** (Darcy's first proposal, at the Hunsford parsonage/Rosings) | `Hunsford` + first-proposal framing | ~53% |
| **middle** | **Darcy's letter** ("Be not alarmed, madam …") explaining Wickham and the Jane–Bingley affair | `Be not alarmed\|Darcy's letter` | ~53% |
| **last** | **Lydia's elopement** with Wickham (from Brighton; the family scandal) | `elope\|Brighton\|Mrs\. Wickham` | ~72% |
| **last** | **Lady Catherine's visit** to Longbourn to browbeat Elizabeth ("Obstinate, headstrong girl!") | `obstinate, headstrong\|Lady Catherine` at Longbourn | ~91% |
| **last** | **the engagements** that close the novel (Elizabeth–Darcy, Jane–Bingley) | `Mrs\. Darcy` + `Mrs\. Bingley` | ~94–99% |

Grading: at least one anchor from **each** third must be present and cited. A wiki rich in
first-third facts but empty of the Hunsford proposal / Darcy's letter (middle) or the
elopement / Lady Catherine's visit / the engagements (last) proves **segments were dropped** — the
chunk-merge failed — and is a HARD FAIL even if `check`/`lint` pass. Evidence: run each grep; every
hit must carry a `[^sN]` to `pride-and-prejudice.txt`.

## F · Structural gates (HARD pass/fail — pure code, no judgement)

- `citadel check` → **0 errors**; `citadel lint` structurally clean (no missing `type`, no broken
  links, no fabricated sources, no `[[wikilinks]]`).
- **Every `[^sN]` resolves to `pride-and-prejudice.txt`** — the only raw file. A `[^sN]` to any
  other path is a fabricated source (there is none) = FAIL:
  `grep -rhoE "\[\^s[0-9]+\]:.*" "$WIKI"` — every definition points at the novel.
- `persons/` pages exist for the principals (at minimum Elizabeth, Darcy, Jane, Bingley, Wickham,
  Mr. Collins, Lady Catherine de Bourgh); estates routed to `objects/`/place records.
- **Graph connected** — no per-chapter islands: persons ↔ marriages ↔ estates cross-link into one
  component (Elizabeth → Darcy → Pemberley; Jane → Bingley → Netherfield; the Bennets → Longbourn →
  Mr. Collins → Rosings/Lady Catherine). Orphan principals = FAIL.
- No page states in-novel misinformation (§B) or a superseded early state (§C) as the wiki's own
  uncited current fact.

## G · Locators — plausible pointers into a 730k-char source (SOFT)

Because the source is one enormous file, citations should carry **locators** that actually point
into it. The **Z6-safe form for this source is a `lines A-B` range**: `citadel lint`'s Z6 check
validates line ranges against the file, so a passing wiki's ranges should land in the right region
(a first-third fact citing an early line range, a last-third fact a late one) and never run past the
file's end. The novel *does* carry chapter headings in its prose — but as **plain text**, mostly
`CHAPTER <roman>.` in uppercase (e.g. `CHAPTER II.` … `CHAPTER LXI.`), with some inconsistency:
chapters 1 and 46 read `Chapter I.` / `Chapter XLVI.` (mixed case) and chapters XIII/XIV drop the
trailing period. A `§ <chapter heading>` locator will nonetheless **trip Z6** on this source: Z6
builds its heading set only from Markdown `#` lines, and a plain-`.txt` novel has none — so any
`§ CHAPTER …` reads as "names a heading not in the source." That flag is **harmless** (Z6 is
advisory, not a structural gate), but prefer `lines A-B` ranges to keep locators clean. (Soft:
locator *presence and plausibility* is graded, not exactness; ingest may cite the whole file without
a locator and still pass structurally.) Id: `loc-plausible`.

## H · Marriage-plot machinery — the pragmatic foil and the hidden rescue (HARD + soft)

Beyond the pairings of §A, the plot turns on two load-bearing mechanisms: the **contrast** between
marrying for security and marrying for love, and the **hidden** act that saves the family from ruin.

### H1 · Mr. Collins's refused proposal and Charlotte's pragmatic marriage

Mr. Collins first proposes to **Elizabeth**, who **refuses** him (against her mother's will); days
later **Charlotte Lucas accepts** the same Mr. Collins — not for love but for **security** ("I am not
romantic … I ask only a comfortable home"), the marriage-for-establishment foil to Elizabeth's
insistence on marrying for love. The Charlotte↔Collins marriage is already required in §A2; here the
*sequence and its meaning* are graded.

| check | HARD/soft | grep (wiki) |
| ----- | --------- | ----------- |
| Collins proposed to Elizabeth and was **refused** | HARD | `Collins` near (`refus`\|`declin`\|`reject`) on Elizabeth's or Collins's page |
| Charlotte's marriage is **pragmatic** (security, not love) | soft | `Charlotte` near (`security`\|`comfortable`\|`not romantic`\|`establishment`\|`pragmat`) |

PASS (hard) = the wiki records Elizabeth's refusal of Collins as an event. FAIL = only the Charlotte
marriage survives, with no trace that Collins first proposed to and was refused by Elizabeth. Id:
`plot-collins-refusal`.

### H2 · Darcy's hidden rescue of the Lydia scandal (HARD)

The last-third crisis (§E: Lydia elopes with Wickham, threatening the reputation and marriage
prospects of **all five** sisters) is resolved by Darcy in **secret**: he tracks the pair down,
**pays Wickham's debts**, and buys/settles the marriage (money to Wickham to make him marry Lydia);
the Bennets are allowed to believe their uncle **Mr. Gardiner** arranged it. A faithful wiki must
record **Darcy — not Gardiner —** as the one who brought the marriage about.

| check | HARD/soft | grep (wiki) |
| ----- | --------- | ----------- |
| Darcy **resolved** the elopement (paid / settled / arranged) | HARD | `Darcy` near (`paid`\|`debts`\|`settled`\|`settlement`\|`arranged`\|`brought about`) and Wickham/Lydia |
| he did it **secretly** / Gardiner is credited | soft | `secret`\|`Gardiner` on the same page |

PASS (hard) = the wiki attributes the resolution of the Lydia affair to Darcy's intervention (paying
Wickham's debts / securing the marriage). FAIL = the elopement merely "ends in marriage" with no
record of Darcy's role, or the settlement is stated as Mr. Gardiner's doing as the wiki's own fact.
Id: `plot-darcy-rescue`.

### H3 · The two title flaws as character arcs, and Lady Catherine's failed intervention (SOFT)

The title names the engine: **Darcy's pride** (haughty, aloof — softened by love and by Elizabeth's
rebuke) and **Elizabeth's prejudice** (her quick, witty first judgments — corrected by Darcy's letter
and Pemberley). A rich character wiki carries Darcy as proud/haughty with his manner reforming, and
Elizabeth as clever/lively and quick-to-judge with her prejudice corrected. Separately, §E already
anchors **Lady Catherine's** visit; note (soft) that her failed attempt to extract a promise from
Elizabeth ironically *advances* the match — it emboldens Darcy to propose a second time. Greps:
Darcy page `proud`\|`pride`\|`haughty`; Elizabeth page `prejudic`\|`witty`\|`clever`\|`lively`. Id:
`char-title-flaws` (soft).

## Retrieval battery — find the knowledge like a user (Tier 2)

The grader plays a reader with a question: it runs each `query` **verbatim** through `citadel
search`, reads the top hits, and grades (a) the `expect` answer is present + correctly cited on a
surfaced page and (b) it was *findable* within the `find` band. Queries are frozen and answer-blind
— phrased from the question side, never naming the answer (the partner, the outcome, the true agent)
and never quoting a verbatim wiki sentence (so they can't game `search`'s substring bonus). There is
one raw file, so `→§X` points at the lettered section whose grep settles a miss (creation-vs-
retrieval). Negatives say `NOT the live answer`: the tempting query must not surface the forbidden
thing — Wickham's slander of Darcy, or Mr. Gardiner credited as Lydia's real rescuer — in the wiki's
own voice. Ranks are soft/reported; only *unfindable by search+index+tags* is a hard floor.

| id | query | expect | find |
| -- | ----- | ------ | ---- |
| `rb-lydia-wickham` | which officer does Lydia Bennet run away with and marry | the youngest sister elopes with, then marries, **George Wickham**, the militia officer (she signs herself "Lydia Wickham"); on Lydia's page, cited `[^sN]`, cross-linked to Wickham →§A2 | rank≤2, 1 read |
| `rb-eliza-darcy` | who does Elizabeth Bennet fall in love with and marry | the protagonist marries **Mr. Darcy**, master of Pemberley — she accepts his second proposal; on Elizabeth's page, cited. An Elizabeth↔Bingley / Jane↔Darcy pairing = FAIL →§A2 | rank≤2, 1 read |
| `rb-collins-charlotte` | does Elizabeth accept Mr Collins's offer of marriage | **No — Elizabeth refuses** Collins (against her mother's will); days later **Charlotte Lucas accepts** him for a secure establishment, not love; on Elizabeth's page, cited →§H1 | rank≤2, 1 read |
| `rb-jane-ill` | why does Jane Bennet fall ill and have to stay at Netherfield | sent to Netherfield **on horseback in the rain** at her mother's contrivance, Jane **catches cold and falls ill**, staying to be nursed by Elizabeth; on Jane's page, cited — proves the **first-third** chunk survived →§E | rank≤2, 1 read |
| `rb-hunsford-proposal` | what happens when Mr Darcy first proposes to Elizabeth | Darcy's **first proposal, at the Hunsford parsonage** near Rosings — dwelling on the match's "degradation" — is **refused**; on Darcy's/Elizabeth's page, cited — proves the **middle-third** chunk survived →§E | rank≤2, 1 read |
| `rb-wickham-slander` | did Mr Darcy cheat Wickham out of the inheritance his father left him | **NOT the wiki's own fact.** The living/inheritance grievance appears **as Wickham's claim**, corrected by **Darcy's letter** (Wickham resigned the claim, took £3,000, later demanded it back) inside a `[!CONTRADICTION]`; search must **NOT** surface "Darcy robbed Wickham" as wiki-voice truth →§B | rank≤2, ≤2 reads |
| `rb-lady-catherine` | what does Lady Catherine demand of Elizabeth when she comes to Longbourn | Lady Catherine arrives unannounced and demands Elizabeth **promise never to marry Darcy**; Elizabeth **refuses** and she leaves in anger; on Elizabeth's/Longbourn's page, cited — proves the **last-third** chunk survived, and Lady Catherine (Rosings) ≠ Kitty →§E,§A1 | rank≤2, 1 read |
| `rb-darcy-rescue` | who paid off Wickham's debts so that he would marry Lydia | **Mr. Darcy, in secret** — he traced the pair, paid Wickham's debts, settled money on Lydia and bought his commission, **insisting Mr. Gardiner be given the credit**; on Elizabeth's/Darcy's page, cited. The "Mr. Gardiner arranged the settlement" version (the Wickham/Lydia/Longbourn pages) is the **cover story**, **NOT** the true agent →§H2 | rank≤3, ≤2 reads (behind the cover-story hit) |
| `rb-entail` | can the Bennet daughters inherit Longbourn | **No** — Longbourn is **entailed, in default of male heirs, to Mr. Collins**, so none of the five daughters can inherit; the reason the sisters must marry; on Mr. Bennet's/Longbourn's page, cited →§A4 | rank≤2, 1 read |

## Scoring

**Hard gates** (must all hold): §F structural — check + lint clean, every `[^sN]` → the novel file,
principals have pages, graph connected; §A1 all five Bennet sisters present with Kitty ≠ Lady
Catherine; §A2 all four marriages correctly paired; §A3 the four estates with correct occupants;
§B Wickham's living-grievance recorded **as his claim** and corrected by Darcy's letter, never
adopted as plain fact; §C all three supersession arcs — final state current, early state only as
arc, no contradiction-flagging of a single-source narrative change; §E at least one cited anchor
from **each** third of the novel (first + middle + last), proving every segment folded in; §A4
Longbourn entailed to Mr. Collins with the Bennet daughters disinherited (the economic engine of the
marriage plot); §H1 Elizabeth's refusal of Mr. Collins recorded as an event; §H2 Darcy's hidden
rescue of the Lydia scandal attributed to **Darcy** (he paid Wickham's debts / secured the marriage),
not to Mr. Gardiner.

**Soft / probabilistic** (report caught / partial / missed; don't hard-fail a single miss): §D the
ironic opening sentence attributed as the narrator's observation if surfaced at all; §A tidiness of
the marriage/estate cross-links; richness of the graph beyond the required principals; §G locator
plausibility (`lines A-B` pointers landing in the right region with no Z6 range-overrun flags; a
`§` chapter-heading locator, if used, trips Z6 only harmlessly);
§C the Pemberley visit as the turn in Elizabeth's view of Darcy (`sup-pemberley-turn`); §H1
Charlotte's marriage framed as pragmatic (security over love); §H3 the two title flaws (Darcy's
pride, Elizabeth's prejudice) as character arcs and Lady Catherine's failed intervention ironically
advancing the match; Mary and Kitty fleshed out beyond a bare mention.

**Findability** (the Retrieval battery — report per row, don't hard-fail a soft rank miss): each
row's answer surfaces on a correct, correctly-cited page via `citadel search` within its `find`
band, readable in ≤2 reads; the negatives must not surface as the live answer — `rb-wickham-slander`
(Darcy cheated Wickham is Wickham's later-refuted claim, never wiki-voice) and `rb-darcy-rescue`
(Mr. Gardiner is the cover story Darcy imposed, not Lydia's real rescuer). **Hard floor:** a row
whose answer is unfindable by search *and* `index` *and* `tags` is a hard miss. Route each miss into
the improvement backlog — fact present-but-unranked → *retrieval* defect (search-tooling lane); fact
absent/mangled/mis-cited → *creation* defect (wiki-generation lane).

The one-line verdict this corpus exists for: **the whole novel folds in across every segment, the
relationships come out right, and the story's lies and reversals are recorded as narrated — Wickham's
slander as Wickham's, the refused proposal as history, Mrs. Darcy as the ending.**
