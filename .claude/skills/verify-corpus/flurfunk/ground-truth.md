# Ground truth — the flurfunk corpus

This is the **answer key** for the `flurfunk` corpus (`corpora/flurfunk/`). It lives under
`.claude/` (outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can never
see it. The verify-corpus skill reads it to grade the wiki the pipeline produced.

`flurfunk` is eleven sources in the **informal registers** no other corpus covers — a Slack export, an
X/Twitter thread, a podcast interview transcript, a job application (cover letter + CV), a
community-forum support thread, a product announcement, and a `retros/` folder of three
reconstructed team retros led by a README folder note — set in one consistent world
(**Larkspur** makes **Skylight**). Its corpus-wide guarantee is **attribution at scale**: "X said Y"
must never become "Y is true." It also grades in-thread reversal supersession, a quote-tweet negative
row, CV timeline completeness, that chat noise never leaks into wiki prose, that a partial list
split across sources is merged rather than flagged, that a source's editorial to-do never becomes
content, and that a folder note's caveat reaches the files beside it.

> Everything is **fictional by design** (Larkspur, Skylight, Priya Nadkarni, Marcus Feld,
> Tom Alvarez, Wei Chen, Sofia Ruiz, Dana Kessler, and every handle). The wiki must record it
> faithfully as the sources state it — including the claims it must NOT adopt as fact.

## The 11 source files

| file | genre | gist |
| ---- | ----- | ---- |
| `slack-export-platform-team.txt` | team chat, Mon–Wed | default event-retention set to **7 days** (Mon), **reversed to 30 days** (Wed) after customer **Northwind** loses audit history; a **second, same-day reversal** (Tue): default dashboard time range proposed **7 days** then reverted back to **24 hours** — current value is the ORIGINAL 24h, not the last-mentioned 7; buried side-decision: rename `retention-svc` → `janitor`; Sofia works from "**Larkspur's Berlin office**" (Tue 16:41 — a third site, §D3); heavy banter/emoji/GIF/lunch/shanty noise |
| `tweet-thread.md` | 8-tweet launch thread, **@marcusfeld** | Skylight **sub-second (<1s) refresh**, was ~5s; a **quote-tweet by @dataskeptic** falsely claims "silently drops events >1MB"; Marcus **debunks** it in 6/ (queued, not dropped) |
| `interview-transcript-founder.md` | Q/A podcast, **Priya Nadkarni** | self-serving claims: "**only** platform with true sub-second refresh", "**profitable since month one**"; plain facts: founded **2021 in Lisbon**, **28 employees** (the announcement rounds this to "around 30" — an approximation, NOT a contradiction); "Engineering sits in **Lisbon and Porto**" (a partial site list — §D3) |
| `application-cover-letter.md` | cover letter, Mar 2026 | Dana Kessler applies for **Senior Platform Engineer** at Larkspur |
| `cv.md` | CV | Dana Kessler timeline (three roles 2015→2026 + TU Delft 2015) |
| `forum-support-thread.md` | support thread #1–#8 | stale-dashboard-after-timezone-change; fix at **#7** (Sofia Ruiz): set **`SKYLIGHT_TZ`** + restart **`janitor`** |
| `announcement.md` | announcement (control) | **Skylight 2.0 GA 1 April 2026**; regions **EU Frankfurt / US Virginia / APAC Singapore**; one editor's housekeeping line "[Editor: pricing table to follow before publishing.]" (§D4 — must not reach the wiki) |
| `retros/README.md` | folder note | "these quarterly retro summaries were **reconstructed afterwards by a contractor** from the chat history; the platform team **has not confirmed** them" — the caveat for the three files beside it (§I) |
| `retros/2025-q3.md` | team retro, first person plural | on-call rotation moved from fortnightly to **weekly**, handoff **Mondays 10:00**; **14** flaky integration tests quarantined in August |
| `retros/2025-q4.md` | team retro, first person plural | flaky tests down to **3**; ingestion outage **14 November** (~40 min) → **written postmortem template** adopted; staging out of disk twice in December |
| `retros/2026-q1.md` | team retro, first person plural | main CI pipeline cut from **22 to 9 minutes** (four parallel shards); fortnightly **Friday demo slot**; coverage reporting broken for three weeks |

Sandbox: one ingest pass, one agentic session per file (11 sessions; `retros/README.md` is a folder
note, so it is ingested before its three siblings). Pair with `CITADEL_STYLE_PROFILES=1` (the CV
+ interview give voices to profile).

## A · Load-bearing facts that MUST appear in the final wiki (cited to the right source)

| id | fact | source of record |
| -- | ---- | ---------------- |
| `F1` | **Larkspur** makes **Skylight**, a real-time analytics dashboard | announcement / interview / tweet |
| `F2` | Larkspur was **founded in 2021 in Lisbon**; has **28 employees** | interview |
| `F3` | **Skylight 2.0 is GA as of 1 April 2026** | announcement |
| `F4` | Skylight 2.0 runs in **three regions: EU (Frankfurt), US (Virginia), APAC (Singapore)** | announcement |
| `F5` | Skylight now refreshes in **under one second** (previously **~5 seconds**) | tweet / announcement |
| `F6` | Skylight's default **event-retention window is 30 days** (current) | slack |
| `F7` | the internal service **`retention-svc` was renamed `janitor`** | slack |
| `F8` | stale-data-after-timezone-change is fixed by setting **`SKYLIGHT_TZ`** to the org's IANA timezone and **restarting `janitor`** | forum #7 |
| `F9` | Dana Kessler's employment timeline (see §H) | cv |
| `F10` | the default **dashboard time range for new workspaces is 24 hours** (a 7-day default was proposed and **reverted the same day**; 24h is current) | slack |

## B · Merges, cross-links, and the one-person trap

- **Larkspur** (`Organization`) links to **Priya Nadkarni** (founder/CEO), **@marcusfeld** (the
  launch-thread author — the raw tweet shows only the handle, no real name, so the page is titled by
  the handle and MUST NOT invent a name), **Skylight** (product), and the platform team.
- **Skylight** is one page (an `Object`/`System`/`Project` — agent-judged) co-cited from the tweet,
  announcement, interview, forum, and slack — **not** one Skylight page per source.
- **Sofia Ruiz appears in BOTH the Slack export and the forum thread** (Larkspur platform + support).
  She must be **one** `persons/` page, co-cited to both — two separate Sofia pages is a creation
  defect (identity fragmentation).

## C · Attribution — the corpus-wide HARD gate ("X said Y" ≠ "Y is true")

Self-serving or contested claims stay **attributed to their speaker**, never flattened to wiki voice
and never a bare `[^llm]` fact:

| id | claim | must be recorded as |
| -- | ----- | ------------------- |
| `A1` | "Larkspur is the **only** real-time analytics platform with true sub-second refresh" | **Priya Nadkarni's claim** (her interview), not a neutral wiki fact. "Larkspur is the only…" in wiki voice = FAIL. |
| `A2` | "we've been **profitable since our first month**" | **Priya's claim**, attributed to the interview — not stated as established fact. |
| `A3` | "Skylight **silently drops events larger than 1MB**" | a **false claim by @dataskeptic that Marcus Feld refuted** (events are queued, not dropped). It must appear **only** as an attributed-and-refuted claim, or not at all — **never** as a Skylight property in wiki voice or a bare `[^llm]` fact. This is the negative row `rb-drops`. |

The plain facts `F2` (founded 2021 Lisbon / 28 employees) are stated flatly by Priya and may be
recorded as facts cited to the interview — the gate is on the **self-serving/contested** claims
`A1`/`A2`/`A3`, not on every sentence she speaks.

## D · Reversal supersession — TWO in-thread reversals that resolve in OPPOSITE directions (slack)

The Slack thread carries **two** decisions that each reverse in-thread — and they land on opposite
ends on purpose, so "the last value mentioned is the current one" is a **wrong** heuristic that fails
one of them:

| fact | expected | detail |
| ---- | -------- | ------ |
| default event-retention (`D1`) | **30 days is current** | 7 days (Mon) → 30 days (Wed) after Northwind lost audit history. 7 days survives only as the dated, superseded **original** decision. Here current = the **later** value. **7 days as the current default = FAIL.** Both shown as current = FAIL. |
| default dashboard time range (`D2`) | **24 hours is current** | proposed as 7 days (Tue 14:05) then **reverted the same day** (Tue 14:32) back to 24 hours once Wei noted a 7-day range would show half-empty charts under the 7-day retention. Here current = the **original** value; the "last 7 days" proposal is the dead one. **A wiki that records the dashboard default range as 7 days took the last-mentioned number and missed the reversal = FAIL.** |

A tidy dated change-log/open-point for each reversal is the soft target. The trap is `D2`: a model
that resolves supersession by recency alone will wrongly output 7 days.

## D2 · Approximation is NOT contradiction — the headcount (interview vs announcement)

The interview states **28 employees** (precise); the announcement says a team of **"around 30"**
(rounded). These are the **same fact approximated**, not a conflict. The wiki must **not** raise a
`> [!CONTRADICTION]` between them: record 28 as the figure (cited to the interview), optionally noting
the announcement's "around 30" as a rounded restatement. Flagging 28-vs-30 as a contradiction, or
asserting two different headcounts as both current-and-conflicting, is a creation defect.

## D3 · Partial lists are NOT a contradiction — Larkspur's sites (interview vs slack)

The interview has Priya say "Engineering sits in **Lisbon and Porto**"; the Slack export has Sofia
working from "**Larkspur's Berlin office**". Neither source calls its list complete (no "only",
"all", or stated count), so these are two partial views of one open-ended set — not a conflict.

**Pass:** the page that holds Larkspur's sites/offices (normally `organizations/larkspur.md`) names
**all three — Lisbon, Porto, Berlin** — each behind its own source's marker (Lisbon/Porto → the
interview, Berlin → the Slack export), and **no** `> [!CONTRADICTION]` callout anywhere in the wiki
mentions Larkspur's sites (`grep -rn -A6 '\[!CONTRADICTION\]' wiki/ | grep -iE
'lisbon|porto|berlin' | grep -v 'Europe/Berlin'` → nothing; a hit on Dana's "Cobalt Systems,
Berlin" CV line is not about the sites — read it before failing). **FAIL:** a contradiction callout over the sites, a site dropped
from the union, or Berlin cited to the interview / Porto to the Slack export (a wrong marker). The
founding city (Lisbon, 2021 — §A·F2) is a separate fact and may stand beside the site list.

## D4 · A source's housekeeping is NOT content — the editor's line (announcement)

`announcement.md` carries "[Editor: pricing table to follow before publishing.]" — a note about the
DOCUMENT's own completeness, not a fact about Skylight. **Pass:** `grep -rni 'pricing table' wiki/`
finds nothing — not as a fact, not as an `## Open Points` entry, not as a quote. **FAIL:** any hit
(e.g. "a pricing table is to follow", or an open point "pricing table pending"). Skylight pricing
must not be invented either (the source gives none).

## E · Chat noise must NOT leak into wiki FACTUAL prose

The wiki's **factual** prose must not carry the Slack/forum noise as content: the GIF link
(`giphy.com`) embedded as a fact, the lunch/ramen tangent recorded as a substantive fact, emoji
strewn through narrative sentences, "rip 7 days we hardly knew ye" as prose. The gate is on
substantive facts: a page must not assert "the team went for ramen" or reproduce banter as narrative.

**Caveat when `CITADEL_STYLE_PROFILES=1` (this corpus pairs with it):** a `persons/` **Style profile**
section may quote SHORT stylistic samples — an emoji, a "lol", a one-line aside — as *cited* evidence
of that person's voice. That is the style-profile feature working, **not** leakage. So scope the grep
to factual sections: a `giphy`/`ramen`/emoji hit **inside a `## Style profile` block, cited**, is
fine; the same in an `## Event retention` / `## Career` / narrative paragraph is a creation defect.

## F · Forum thread — the fix is the ACCEPTED answer (#7), not the wrong guesses

The resolution captured must be the **#7** answer (`SKYLIGHT_TZ` + restart `janitor`; cause =
`janitor` caching the old offset), **not** the dead-end guesses in #2–#6 (browser cache, hard
refresh, ingestion buffer). A wiki that records "clear your browser cache" as the fix, or the
me-too/wrong-guess posts as resolution, is a creation defect. `janitor` here is the same renamed
service as §A·F7 — a nice cross-link, not required.

## G · Structural gates (hard pass/fail — pure code, no judgement)

- `citadel check` → "OK — no validation issues." (0 errors).
- `citadel lint` → exit 0 (no missing type, no broken link, no fabricated source, no `[[wikilink]]`).

## H · CV timeline — completeness (cited to `cv.md`)

A `persons/dana-kessler.md` page carries the **complete, dated** employment history — all three roles
and the education, cited to the CV:

| period | role | employer |
| ------ | ---- | -------- |
| 2015–2018 | Backend Engineer | Meridian Logistics (Rotterdam) |
| 2018–2022 | Senior Software Engineer | Cobalt Systems (Berlin) |
| 2022–2026 | Staff Engineer | Halcyon Cloud (Amsterdam) |
| — | BSc Computer Science, **2015** | TU Delft |

A missing role, an undated role, or a page that keeps only the most recent job is a creation defect.
The cover letter (Mar 2026, Senior Platform Engineer at Larkspur) links Dana to Larkspur but is a
job **application** — Dana is a candidate, not a Larkspur employee. A wiki that records Dana as
already working at Larkspur is a creation defect.

**Relative-duration reconciliation (soft, `H2`):** the cover letter states the tenures in relative
form — "the last **four years** at Halcyon Cloud", "**four years** at Cobalt Systems", "the better
part of **eleven years**" total — while the CV gives the absolute ranges (Halcyon 2022–2026, Cobalt
2018–2022, career from 2015). These **agree** (2022–2026 = 4, 2018–2022 = 4, 2015→2026 ≈ 11): a
strong wiki reconciles them without inventing a conflict. Treating the relative and absolute forms as
contradictory, or double-counting them into a wrong total, is a creation defect.

## I · Folder note — the retros are an UNCONFIRMED reconstruction (`retros/README.md`)

`raw/retros/README.md` says the three retros beside it were **reconstructed afterwards by a
contractor from the chat history** and that **the platform team has not confirmed them**. The retros
themselves are written as "we" — the trap is that, read on its own, each looks like the platform
team's first-hand account.

**Pass:** every retro fact that reaches the wiki (the weekly on-call rotation with the Monday 10:00
handoff, the 14 quarantined tests, the 14 November outage + postmortem template, the 22→9-minute CI
pipeline, the Friday demo slot, …) is recorded as an **unconfirmed reconstruction** — attributed to
the contractor's reconstruction / the retro summaries, with the caveat stated on that page and the
caveat cited to `raw/retros/README.md` (a `[^sN]` whose definition names the README), the retro
fact itself cited to its own retro file. Check it on every page that cites a `retros/20*.md` file:
`grep -rln 'retros/20' wiki/` → each hit also cites `retros/README.md` and carries the caveat in
prose.

**FAIL (hard, part of the §C attribution gate):** a retro fact stated in plain wiki voice ("the
platform team moved on-call to weekly shifts"), or as the platform team's own account ("the team
reported…", "in its Q1 2026 retro the team says…") with no reconstruction caveat — i.e. the caveat
lives only on the README's own page and the sibling facts are unqualified. That is exactly the
misattribution the folder-note ordering and the `core.md` folder-note rule exist to prevent. A
retro fact cited to the README instead of its own retro file is a provenance defect (soft).

## Retrieval battery — find the knowledge like a user (Tier 2)

Run each `query` **verbatim** through `citadel search`, read the top hits, grade (a) the `expect`
answer present + correctly cited/attributed on a surfaced page and (b) findable within `find`.
Queries are answer-blind. `→§X` settles a miss. `rb-retention` is temporal (live value only);
`rb-drops`, `rb-claim` and `rb-oncall` are attribution/negative rows — existence is settled by the `→§X` grep,
never by "search found nothing".

| id | query | expect | find |
| -- | ----- | ------ | ---- |
| `rb-retention` | how long does Skylight keep events by default | **30 days** (current); 7 days appears only as the dated, superseded original decision, never as current →§D, §A·F6 | rank 1, 1 read |
| `rb-handle` | who posts as @marcusfeld | a Person page for the **@marcusfeld** handle — the X account that posted the Skylight sub-second-refresh launch thread and rebutted the @dataskeptic claim, linked to Larkspur/Skylight (the raw shows only the handle, so no real name is invented) →§B | rank≤2, 1 read |
| `rb-drops` | does Skylight drop events larger than 1MB | **NOT live** — no page may assert Skylight drops >1MB events as fact; it appears only as **@dataskeptic's refuted claim** (Marcus: queued, not dropped), if at all →§C·A3 | attributed-only; no live assertion |
| `rb-refresh` | how fast do Skylight dashboards refresh now | **under one second** (down from ~5 s) →§A·F5 | rank≤2, 1 read |
| `rb-claim` | is Larkspur the only platform with sub-second refresh | recorded **only as Priya Nadkarni's claim** (interview), never as a neutral wiki fact →§C·A1 | attributed-only |
| `rb-cv` | where did Dana Kessler work before applying to Larkspur | the full timeline — **Meridian Logistics, Cobalt Systems, Halcyon Cloud** (dated), not just the latest →§H | rank 1, 1 read |
| `rb-timezone` | Skylight dashboard stuck on old data after our timezone changed | set **`SKYLIGHT_TZ`** to the org's IANA timezone and **restart `janitor`** (the #7 accepted answer), not the browser-cache guesses →§F, §A·F8 | rank≤2, ≤2 reads |
| `rb-ga` | when did Skylight 2.0 launch and where can I run it | **1 April 2026**, in **EU (Frankfurt), US (Virginia), APAC (Singapore)** →§A·F3/F4 | rank 1, 1 read |
| `rb-range` | what time range does a new Skylight dashboard show by default | **24 hours** — a "last 7 days" default was proposed and reverted the same day, so 7 days is NOT current; a wiki answering 7 days followed recency past the reversal →§D·D2, §A·F10 | rank≤2, ≤2 reads |
| `rb-headcount` | how many people work at Larkspur | **28** (the interview's precise figure); the announcement's "around 30" is the same number rounded, not a second, conflicting headcount →§D2 | rank≤2, 1 read |
| `rb-sites` | where does Larkspur have offices | **Lisbon, Porto** (interview) **and Berlin** (Slack), each cited to its own source, no contradiction callout →§D3 | rank≤2, 1 read |
| `rb-oncall` | how does the platform team's on-call rotation work | **weekly** shifts, handoff **Mondays 10:00** (was fortnightly) — stated as the contractor's **unconfirmed reconstruction** (caveat cited to `retros/README.md`), never as the team's confirmed account →§I | rank≤2, ≤2 reads; attributed-only |

## Scoring

**Hard gates** (must all hold): §G structural; **§C attribution** — `A1`/`A2` recorded only as
Priya's claims and `A3` never a live Skylight property (the corpus-wide gate; any of these asserted
in wiki voice or as a bare `[^llm]` fact is a hard fail); §D **both** reversals resolved to the right
current value — retention **30 live** (7 dated) AND dashboard range **24h live** (the reverted 7-day
proposal dead, not surfaced as current); §F the forum fix is the #7 answer, not a wrong guess; §H the
CV timeline complete and dated with Dana as a **candidate**, not a Larkspur employee; §B Sofia Ruiz is
**one** person page; every §A `F*` fact present-and-cited; §I every retro fact carries the
unconfirmed-reconstruction caveat cited to `raw/retros/README.md` (a retro fact in plain wiki voice or
as the team's own account is an attribution failure, same gate as §C); §D3 no contradiction callout
over the three sites (the rule #160 adds — hard, unlike §D2's soft reconciliation); §D4 `pricing
table` absent from the wiki.

**Soft / probabilistic** (report caught / partial / missed; don't hard-fail a single miss): chat
noise absent from wiki prose (§E — now including the sea-shanty aside and the forum's F1/off-topic
tangent); both reversals rendered as tidy dated arcs / open points; the 28-vs-"around 30" headcount
reconciled without a spurious contradiction (§D2); the §D3 union complete with each site behind
its own source's marker; the cover-letter relative durations reconciled
with the CV's absolute dates (§H2); the `retention-svc`→`janitor` rename and its cross-link to the
forum fix; cross-link density around Larkspur/Skylight/the people; style-profile entries for Priya
and Dana; an `[^llm]` or explicit "refuted" note on `A3`.

**Findability** (Retrieval battery — report per row, don't hard-fail a soft rank miss): each row's
answer surfaces on a correct, correctly-cited/attributed page within its `find` band in ≤2 reads;
`rb-retention` returns the **live 30 days**; the negative `rb-drops` and the attribution `rb-claim`
surface **no** page asserting the claim in wiki voice (settled by the §C grep, not a no-match).
**Hard floor:** a row unfindable by search *and* `index` *and* `tags` is a hard miss. Route each miss
— present-but-unranked → *retrieval* defect (search lane); absent / mis-attributed / an adopted claim
/ a superseded value surfacing as current / a fragmented identity → *creation* defect
(wiki-generation lane: `citadel/rules/genres/`, the ingest prompts).
