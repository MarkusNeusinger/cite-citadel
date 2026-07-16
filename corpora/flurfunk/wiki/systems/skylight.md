---
type: System
title: Skylight
description: Larkspur's real-time analytics dashboard, a SaaS product currently at
  version 2.0.
resource: raw/announcement.md
tags:
- skylight
- larkspur
- analytics
- saas
- dashboard
timestamp: '2026-07-16T15:06:51Z'
citadel_version: 0.3.0
---

Skylight is [Larkspur](../organizations/larkspur.md)'s real-time analytics dashboard.[^s1]

**Skylight 2.0**, the latest release, became generally available (GA) on 1 April 2026.[^s2]

Skylight 2.0 is available in three regions: EU (Frankfurt), US (Virginia), and APAC
(Singapore).[^s3] Deploying in the region closest to a customer's data keeps latency low and
helps teams meet regional data-residency requirements.[^s3] Existing customers can select their
region from workspace settings; new workspaces are prompted to choose a region during setup.[^s3]

Announcing the release, [Priya Nadkarni](../persons/priya-nadkarni.md), Larkspur's founder and
CEO, said: "Skylight 2.0 is the version we always wanted to ship. Bringing it to three regions
means teams around the world get the same real-time experience close to home."[^s4]

In a 14 July 2026 interview on The Build Loop podcast, Nadkarni described Skylight as a product
where a customer points their event stream at it and gets live views that "actually update as
things happen, not thirty seconds later."[^s12]

In the same interview, Nadkarni claimed Skylight is "the only real-time analytics platform with
true sub-second refresh," saying she has "looked at the competition closely" and believes rivals
are "doing polling and calling it streaming."[^s13] This is a self-promotional superlative from
the product's own founder; no independent source in this corpus verifies or contradicts an
"only" claim about the competitive landscape, so it should be read as Larkspur's own positioning
rather than a confirmed fact.[^llm1]

Nadkarni also said Larkspur had recently cut Skylight's dashboard refresh time to under a
second, calling the response "incredible," and that the team's near-term priorities are scaling
and extending Skylight's regional footprint to bring it closer to customers worldwide, while
keeping "real-time that's actually real-time" as the constant goal.[^s14]

## Event retention default

Before 2026-02-09, Skylight had no default event-retention window: staging environments retained
events indefinitely and disk usage was climbing without bound.[^s15] That day, the Larkspur
platform team decided to set the default event-retention window to 7 days, reasoning that most
dashboards only look at the last few days and that any customer needing longer could get a
per-customer exception.[^s16] The 7-day default was merged and rolled out to production on
2026-02-10.[^s17]

Later that day, the customer Northwind opened a support ticket reporting that some dashboards
were empty for date ranges 10-12 days back — the 7-day window pruning events as designed.[^s18]
On 2026-02-11, the issue proved more serious: Northwind needed three weeks of event history for a
compliance audit, and the data had already aged out under the 7-day window.[^s19] The Larkspur
platform team concluded the 7-day default had been too aggressive — optimized for Larkspur's own
disk usage rather than customer needs — and decided to raise the default event-retention window
to 30 days, covering a normal audit/reporting cycle while remaining bounded.[^s20] The 30-day
default was merged and rolled out on 2026-02-11, replacing the 7-day default;[^s21] the rollout
also added a note that customers on audit-heavy plans should confirm their retention window
explicitly.[^s22]

## Change Log

- 2026-02-09: default event-retention window set to 7 days (not yet deployed).[^s16]
- 2026-02-10: 7-day default live in production.[^s17]
- 2026-02-11: reverted; default event-retention window raised to 30 days, live as of 09:40.[^s21]

## Dashboard time-range default

New workspaces' dashboards default their time range to "last 24 hours."[^s23] On 2026-02-10,
[Wei Chen](../persons/wei-chen.md) noted this narrow default was generating "where's my data"
support tickets from users who expected to see a week of data, and [Tom
Alvarez](../persons/tom-alvarez.md) proposed defaulting new workspaces' dashboard time range to
the last 7 days instead; the team decided to make the change.[^s24] Minutes later, Chen caught
that a 7-day dashboard default would show a half-empty chart the moment the (then 7-day)
event-retention window pruned older events, making Skylight look more broken rather than less —
so the decision was reverted the same day, and the dashboard time-range default for new
workspaces remained 24 hours.[^s25]

## Dashboard refresh latency

In a thread posted on X on 2026-02-12, an account posting as @marcusfeld — writing in "we"/"the
team" language and tagging the thread #Skylight #Larkspur, consistent with speaking for
Larkspur — announced that Skylight dashboards now refresh in under one second, down from the
roughly 5 seconds refreshes used to take before.[^s30] @marcusfeld said the old pipeline
recomputed the whole aggregate on every refresh, which was fine at small scale but painful once a
customer had millions of events streaming in.[^s31] Larkspur rewrote the aggregation layer to
apply incremental updates — folding in only the deltas since the last refresh instead of doing a
full recompute.[^s32] @marcusfeld reported the result as a p95 refresh time now well under 1
second on the same hardware.[^s33] This matches Nadkarni's later, less detailed mention, in the 14
July 2026 podcast interview, of a recent cut to sub-second refresh.[^s14]

## Large-event handling

Responding to the refresh announcement, an account posting as @dataskeptic claimed on X on
2026-02-12 that Skylight silently drops any event larger than 1MB.[^s34]

> [!CONTRADICTION]
> @dataskeptic claimed Skylight silently drops any event over 1MB.[^s34] @marcusfeld responded
> the same day that this is false: oversized events are queued and processed within the retention
> window rather than dropped, pointing to Skylight's own documentation on large events as
> support.[^s35] @marcusfeld allowed that a misconfigured upstream source could itself reject
> oversized payloads before they ever reach the platform, but maintained the platform itself never
> silently drops them.[^s36]

This is Larkspur's own rebuttal to a public criticism of its product, given by an account speaking
for Larkspur; no independent source in this corpus confirms or refutes either side of the
dispute.[^llm2]

## `retention-svc` naming

The Skylight service that caches an org's UTC offset and handles several cleanup jobs (see Known
issues, below) was originally named `retention-svc`, though by 2026 it performed roughly four
unrelated cleanup jobs beyond retention.[^s26] On 2026-02-09, the Larkspur platform team
informally agreed to rename it to `janitor`, and Tom Alvarez said he would file a rename ticket,
marked low priority.[^s27] By the 2026-02-18–19 timezone-caching incident described below, the
service is referred to simply as `janitor`.[^s8]

## Known issues

### Dashboards freeze on stale data after a timezone change

On the Larkspur Community Forum's Skylight Support board, user gridlock_92 reported on
2026-02-18 that after their organization changed its configured timezone from US/Eastern to
Europe/Berlin, Skylight dashboards froze on old data — new events kept landing in the raw event
log, but the dashboards would not roll forward past the timezone switch.[^s5] They ruled out a
browser-side cause (a hard refresh, a full cache clear, an incognito window, and a different
machine all showed the same stale numbers, so it was server-side),[^s6] and confirmed the event
ingestion pipeline itself was healthy, isolating the problem to the dashboards not rolling
forward past the switch.[^s7]

[Sofia Ruiz](../persons/sofia-ruiz.md) of Larkspur Support explained the cause on 2026-02-19:
Skylight's `janitor` service caches an org's UTC offset when it first starts, and uses that
cached offset to bucket incoming events into time windows, so when an org's timezone changes,
`janitor` keeps bucketing new events by the stale offset and dashboards look frozen on the old
data.[^s8] The fix is to set the `SKYLIGHT_TZ` environment variable to the org's IANA timezone
(`Europe/Berlin` in gridlock_92's case) and restart the `janitor` service so it re-reads the
timezone; buckets may need one refresh cycle to catch up.[^s9] gridlock_92 confirmed the fix
worked: dashboards started moving again with the correct local times within a minute of
restarting `janitor` with `SKYLIGHT_TZ=Europe/Berlin`.[^s10]

Forum user mattb reported hitting a similar-looking issue once after a daylight-saving-time
change; without a root cause at the time, they worked around it by standing up a fresh dashboard
and copying its configuration over.[^s11]

## Open Points

### `retention-svc` rename to `janitor`
id: op-retention-svc-rename
- 2026-02-09: Tom Alvarez proposed renaming the `retention-svc` service to `janitor`; Wei Chen and
  Sofia Ruiz agreed.[^s27] Alvarez said he would file a rename ticket, marked low priority.[^s28]
- 2026-02-11: the rename ticket still existed and was still low priority; Sofia Ruiz volunteered
  to take it.[^s29]

## See also

- [Larkspur](../organizations/larkspur.md)
- [Priya Nadkarni](../persons/priya-nadkarni.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Wei Chen](../persons/wei-chen.md)

## Sources

[^s1]: [raw/announcement.md](../../raw/announcement.md), lines 5-7 — Skylight described as Larkspur's real-time analytics dashboard (ingested 2026-07-15)
[^s2]: [raw/announcement.md](../../raw/announcement.md), lines 5-7 — Skylight 2.0 GA date (ingested 2026-07-15)
[^s3]: [raw/announcement.md](../../raw/announcement.md), lines 9-17 — three-region availability and region selection (ingested 2026-07-15)
[^s4]: [raw/announcement.md](../../raw/announcement.md), lines 19-21 — Nadkarni's launch quote (ingested 2026-07-15)
[^s5]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 7-13 — gridlock_92's initial bug report (ingested 2026-07-15)
[^s6]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 24-27 — gridlock_92 rules out a browser-side cause (ingested 2026-07-15)
[^s7]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 38-41 — gridlock_92 confirms ingestion is healthy and isolates the issue to dashboards (ingested 2026-07-15)
[^s8]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 59-62 — Sofia Ruiz's root-cause diagnosis (ingested 2026-07-15)
[^s9]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 64-72 — Sofia Ruiz's fix steps (ingested 2026-07-15)
[^s10]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 78-82 — gridlock_92 confirms the fix worked (ingested 2026-07-15)
[^s11]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 45-49 — mattb's daylight-saving-time anecdote and workaround (ingested 2026-07-15)
[^s12]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 17 — Nadkarni's product description (ingested 2026-07-14)
[^s13]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), lines 25-29 — Nadkarni's "only" real-time/sub-second-refresh claim (ingested 2026-07-14)
[^s14]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 41 — recent refresh-time progress and roadmap (ingested 2026-07-14)
[^llm1]: LLM - self-promotional competitive superlative from the product's own founder, not independently corroborated in this corpus (added 2026-07-14)
[^s15]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 9 — no default retention window, staging hoarding events (ingested 2026-07-16)
[^s16]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 13-17 — 7-day retention proposal and decision (ingested 2026-07-16)
[^s17]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 33 — 7-day default merged and rolled to production (ingested 2026-07-16)
[^s18]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-39 — Northwind's first ticket about empty older-range dashboards (ingested 2026-07-16)
[^s19]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 55-56 — Northwind's compliance-audit data loss (ingested 2026-07-16)
[^s20]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 57-62 — team concludes 7 days was too aggressive, decides on 30 days (ingested 2026-07-16)
[^s21]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 66 — 30-day default merged and rolled out (ingested 2026-07-16)
[^s22]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 64 — note for customers on audit-heavy plans (ingested 2026-07-16)
[^s23]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 41 — 24-hour dashboard default and resulting support tickets (ingested 2026-07-16)
[^s24]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 42-44 — 7-day dashboard default proposal and decision (ingested 2026-07-16)
[^s25]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 45-47 — the conflict caught and the reversal to 24 hours (ingested 2026-07-16)
[^s26]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 19 — retention-svc's name and its unrelated cleanup jobs (ingested 2026-07-16)
[^s27]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 21-24 — informal agreement to rename retention-svc to janitor (ingested 2026-07-16)
[^s28]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 25 — Alvarez commits to filing the rename ticket (ingested 2026-07-16)
[^s29]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 70-72 — rename ticket still open and low priority as of 2026-02-11 (ingested 2026-07-16)
[^s30]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 3-7 — @marcusfeld's launch post: date, headline, and prior ~5s baseline (ingested 2026-07-16)
[^s31]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 11 — old pipeline: full recompute on every refresh (ingested 2026-07-16)
[^s32]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 15 — rewrite to incremental aggregation (ingested 2026-07-16)
[^s33]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 19 — result: p95 refresh well under 1 second (ingested 2026-07-16)
[^s34]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 25-26 — @dataskeptic's claim that events over 1MB are silently dropped (ingested 2026-07-16)
[^s35]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 30 — @marcusfeld's rebuttal: events are queued, not dropped (ingested 2026-07-16)
[^s36]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 34 — @marcusfeld distinguishes upstream misconfiguration from platform behavior (ingested 2026-07-16)
[^llm2]: LLM - self-promotional rebuttal from an account speaking for the company, not independently corroborated in this corpus (added 2026-07-16)
