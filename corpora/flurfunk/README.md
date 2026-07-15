# flurfunk — informal genres (chat, social, interview, application, forum)

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and was authored by hand for
> testing cite-citadel. The company (**Larkspur**), its product (**Skylight**), the people
> (Priya Nadkarni, Marcus Feld, Tom Alvarez, Wei Chen, Sofia Ruiz, Dana Kessler), and every handle
> are **fictional**; any resemblance to real persons or organizations is accidental. Safe to publish.

Seven short sources in the registers a personal wiki actually has to swallow but no other corpus
covers — a Slack export, an X/Twitter thread, a podcast interview transcript, a job application
(cover letter + CV), a community-forum support thread, and a product announcement — all set in one
consistent little world so the entities cross-link (**Larkspur** makes **Skylight**; the people
recur across sources).

## The sources

| file | genre | the trap it sets |
| ---- | ----- | ---------------- |
| `slack-export-platform-team.txt` | multi-day team chat (banter, emoji, a GIF link, typos, a lunch tangent, a sea-shanty aside) | **two** decisions are **reversed in-thread, in opposite directions**: the default event-retention window is set to **7 days** (Mon) then changed to **30 days** (Wed) after a customer loses audit data — current is the *later* value; and the default dashboard time range is proposed as **7 days** then reverted the same day back to **24 hours** — current is the *original* value. A wiki that resolves supersession by "last number wins" gets the second one wrong. Plus the buried rename `retention-svc` → `janitor`, and chat noise that must not leak into wiki prose. |
| `tweet-thread.md` | 8-tweet launch thread by **@marcusfeld** | a **quote-tweet** (`@dataskeptic`) spreads a **false** claim ("Skylight silently drops events over 1MB") that the author **debunks downthread**. The claim must never be recorded as fact — only, if at all, as an attributed-and-refuted claim. |
| `interview-transcript-founder.md` | Q/A podcast transcript with founder **Priya Nadkarni** | self-serving claims ("the only platform with sub-second refresh", "profitable since month one") must stay **attributed to her**, never flattened to wiki voice. |
| `application-cover-letter.md` + `cv.md` | a job application | one person's employment history → a `persons/` page with a **dated, complete timeline** (three roles 2015→2026 + education). The cover letter states the tenures in **relative** form ("four years at Cobalt", "the better part of eleven years") that must reconcile with the CV's absolute dates, not read as a conflict. Pair with `CITADEL_STYLE_PROFILES=1`. |
| `forum-support-thread.md` | community support thread, posts #1–#8 (with off-topic tangents) | the fix (**set `SKYLIGHT_TZ` + restart `janitor`**) emerges only at the accepted answer, **#7** — the wiki must capture the resolution, not the wrong guesses in #2–#6. |
| `announcement.md` | product announcement | the near-clean **control**: Skylight 2.0 GA on 1 April 2026 across three regions. Its one trap: it rounds the headcount to "around 30" where the interview says **28** — an approximation the wiki must reconcile, **not** flag as a contradiction. |

## What it exercises

Informal-register robustness and **attribution at scale** — the corpus-wide hard gate that "X said Y"
never becomes "Y is true" — plus in-thread reversal supersession, a quote-tweet negative row, CV
timeline completeness, chat-noise never leaking verbatim, and genre selection where the `genres/`
briefs (`social.md`, `transcript.md`, `cv.md`, `first-person.md`) are the ones under test. Retrieval
includes **handle-based queries** (`@marcusfeld`).

## Grading

The answer key is `.claude/skills/verify-corpus/flurfunk/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, or answer notes anywhere under `corpora/flurfunk/`.
