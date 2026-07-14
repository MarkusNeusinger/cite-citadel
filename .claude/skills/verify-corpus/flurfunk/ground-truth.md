# Ground truth — the flurfunk corpus

This is the **answer key** for the `flurfunk` corpus (`corpora/flurfunk/`). It lives under
`.claude/` (outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can never
see it. The verify-corpus skill reads it to grade the wiki the pipeline produced.

`flurfunk` is seven sources in the **informal registers** no other corpus covers — a Slack export, an
X/Twitter thread, a podcast interview transcript, a job application (cover letter + CV), a
community-forum support thread, and a product announcement — set in one consistent world
(**Larkspur** makes **Skylight**). Its corpus-wide guarantee is **attribution at scale**: "X said Y"
must never become "Y is true." It also grades in-thread reversal supersession, a quote-tweet negative
row, CV timeline completeness, and that chat noise never leaks into wiki prose.

> Everything is **fictional by design** (Larkspur, Skylight, Priya Nadkarni, Marcus Feld,
> Tom Alvarez, Wei Chen, Sofia Ruiz, Dana Kessler, and every handle). The wiki must record it
> faithfully as the sources state it — including the claims it must NOT adopt as fact.

## The 7 source files

| file | genre | gist |
| ---- | ----- | ---- |
| `slack-export-platform-team.txt` | team chat, Mon–Wed | default event-retention set to **7 days** (Mon), **reversed to 30 days** (Wed) after customer **Northwind** loses audit history; buried side-decision: rename `retention-svc` → `janitor`; heavy banter/emoji/GIF/lunch noise |
| `tweet-thread.md` | 8-tweet launch thread, **@marcusfeld** | Skylight **sub-second (<1s) refresh**, was ~5s; a **quote-tweet by @dataskeptic** falsely claims "silently drops events >1MB"; Marcus **debunks** it in 6/ (queued, not dropped) |
| `interview-transcript-founder.md` | Q/A podcast, **Priya Nadkarni** | self-serving claims: "**only** platform with true sub-second refresh", "**profitable since month one**"; plain facts: founded **2021 in Lisbon**, **28 employees** |
| `application-cover-letter.md` | cover letter, Mar 2026 | Dana Kessler applies for **Senior Platform Engineer** at Larkspur |
| `cv.md` | CV | Dana Kessler timeline (three roles 2015→2026 + TU Delft 2015) |
| `forum-support-thread.md` | support thread #1–#8 | stale-dashboard-after-timezone-change; fix at **#7** (Sofia Ruiz): set **`SKYLIGHT_TZ`** + restart **`janitor`** |
| `announcement.md` | announcement (control) | **Skylight 2.0 GA 1 April 2026**; regions **EU Frankfurt / US Virginia / APAC Singapore** |

Sandbox: one ingest pass, one agentic session per file. Pair with `CITADEL_STYLE_PROFILES=1` (the CV
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

## D · Reversal supersession — the retention window (slack)

The Slack decision reversed **in-thread**: 7 days (Mon) → 30 days (Wed, after Northwind lost audit
data). The wiki must carry:

| fact | expected | detail |
| ---- | -------- | ------ |
| default event-retention | **30 days is current** | 7 days survives only as the dated, superseded original decision (with the arc: set Monday, changed Wednesday after a customer lost audit history). **7 days presented as the current default = FAIL.** Both 7 and 30 shown as current, un-superseded = FAIL. A tidy dated change-log/open-point for the reversal is the soft target. |

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

## Retrieval battery — find the knowledge like a user (Tier 2)

Run each `query` **verbatim** through `citadel search`, read the top hits, grade (a) the `expect`
answer present + correctly cited/attributed on a surfaced page and (b) findable within `find`.
Queries are answer-blind. `→§X` settles a miss. `rb-retention` is temporal (live value only);
`rb-drops` and `rb-claim` are attribution/negative rows — existence is settled by the `→§X` grep,
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

## Scoring

**Hard gates** (must all hold): §G structural; **§C attribution** — `A1`/`A2` recorded only as
Priya's claims and `A3` never a live Skylight property (the corpus-wide gate; any of these asserted
in wiki voice or as a bare `[^llm]` fact is a hard fail); §D retention supersession (30 live, 7 only
dated); §F the forum fix is the #7 answer, not a wrong guess; §H the CV timeline complete and dated
with Dana as a **candidate**, not a Larkspur employee; §B Sofia Ruiz is **one** person page; every §A
`F*` fact present-and-cited.

**Soft / probabilistic** (report caught / partial / missed; don't hard-fail a single miss): chat
noise absent from wiki prose (§E); the reversal rendered as a tidy dated arc / open point; the
`retention-svc`→`janitor` rename and its cross-link to the forum fix; cross-link density around
Larkspur/Skylight/the people; style-profile entries for Priya and Dana; an `[^llm]` or explicit
"refuted" note on `A3`.

**Findability** (Retrieval battery — report per row, don't hard-fail a soft rank miss): each row's
answer surfaces on a correct, correctly-cited/attributed page within its `find` band in ≤2 reads;
`rb-retention` returns the **live 30 days**; the negative `rb-drops` and the attribution `rb-claim`
surface **no** page asserting the claim in wiki voice (settled by the §C grep, not a no-match).
**Hard floor:** a row unfindable by search *and* `index` *and* `tags` is a hard miss. Route each miss
— present-but-unranked → *retrieval* defect (search lane); absent / mis-attributed / an adopted claim
/ a superseded value surfacing as current / a fragmented identity → *creation* defect
(wiki-generation lane: `citadel/rules/genres/`, the ingest prompts).
