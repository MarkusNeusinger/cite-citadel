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
| `slack-export-platform-team.txt` | multi-day team chat (banter, emoji, a GIF link, typos, a lunch tangent) | a real decision is **reversed in-thread**: the default event-retention window is set to **7 days** on Monday, then changed to **30 days** on Wednesday after a customer loses audit data. The wiki must carry **30 days** as current, with the arc preserved — and must not leak the chat noise into wiki prose. A second decision (rename `retention-svc` → `janitor`) is buried in jokes. |
| `tweet-thread.md` | 8-tweet launch thread by **@marcusfeld** | a **quote-tweet** (`@dataskeptic`) spreads a **false** claim ("Skylight silently drops events over 1MB") that the author **debunks downthread**. The claim must never be recorded as fact — only, if at all, as an attributed-and-refuted claim. |
| `interview-transcript-founder.md` | Q/A podcast transcript with founder **Priya Nadkarni** | self-serving claims ("the only platform with sub-second refresh", "profitable since month one") must stay **attributed to her**, never flattened to wiki voice. |
| `application-cover-letter.md` + `cv.md` | a job application | one person's employment history → a `persons/` page with a **dated, complete timeline** (three roles 2015→2026 + education). Pair with `CITADEL_STYLE_PROFILES=1`. |
| `forum-support-thread.md` | community support thread, posts #1–#8 | the fix (**set `SKYLIGHT_TZ` + restart `janitor`**) emerges only at the accepted answer, **#7** — the wiki must capture the resolution, not the wrong guesses in #2–#6. |
| `announcement.md` | product announcement | the clean **control**: Skylight 2.0 GA on 1 April 2026 across three regions, no attribution trap. |

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
