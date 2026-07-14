---
type: System
title: Skylight
description: Larkspur's real-time analytics dashboard, released as Skylight 2.0 in
  three regions.
tags:
- analytics
- dashboard
- saas
- larkspur
- support
resource: raw/announcement.md
timestamp: '2026-07-14T13:11:54Z'
citadel_version: 0.3.0
---

# Skylight

Skylight is [Larkspur](../organizations/larkspur.md)'s real-time analytics dashboard.[^s1] A
customer points an event stream at it and gets live views that update as events happen, rather
than thirty seconds later.[^s13]

## Skylight 2.0 general availability

Skylight 2.0, the latest release of Skylight, became generally available on 1 April 2026.[^s1]

Skylight 2.0 is available in three regions: EU (Frankfurt), US (Virginia), and APAC (Singapore).[^s2]

Existing customers can select their region from the workspace settings; new workspaces are
prompted to choose a region during setup.[^s3] According to the announcement, deploying in the
region closest to a customer's data keeps latency low and helps teams meet regional data
residency requirements.[^s3]

[Priya Nadkarni](../persons/priya-nadkarni.md), Larkspur's founder and CEO, described Skylight 2.0
as "the version we always wanted to ship," saying that bringing it to three regions means teams
around the world get the same real-time experience close to home.[^s4]

## Refresh speed

On 12 February 2026, [@marcusfeld](../persons/marcusfeld.md) posted a launch thread on X
announcing that Skylight's dashboard refresh time had dropped from roughly five seconds to under
one second.[^s25] He attributed the improvement to a rewrite of the aggregation layer: the
previous pipeline recomputed the whole aggregate on every refresh — fine at small scale, but slow
once a customer had millions of events streaming in[^s26] — while the rewritten pipeline instead
performs incremental updates, folding in only the deltas since the last frame rather than a full
recompute.[^s31] He reported the change brought p95 refresh to well under one second on the same
hardware.[^s27]

In a podcast interview, [Priya Nadkarni](../persons/priya-nadkarni.md) said Larkspur had recently
cut Skylight's dashboard refresh time to under a second,[^s14][^s25] calling the response
"incredible," and that the company's focus next is on scaling and on the "regions story," getting
Skylight closer to customers around the world — while the "north star" stays the same: real-time
that's actually real-time.[^s14]

In the same interview, Nadkarni described Skylight as "the only real-time analytics platform with
true sub-second refresh," saying she had looked closely at the competition and that others are
"doing polling and calling it streaming."[^s15][^s16] This is a self-promotional competitive claim
made by Larkspur's own founder; the corpus contains no independent source comparing Skylight's
refresh latency against competing products.[^llm1]

## Event retention

By default, Skylight retains a customer's ingested events for 30 days.[^s21] Larkspur's platform
team set this default after reversing an earlier, more aggressive one: on 9 February 2026 the
team set the default event-retention window to 7 days, after finding that staging had been
retaining events indefinitely, choosing 7 days to keep storage usage predictable since most
dashboards only look at the last few days of data.[^s17]

After [Northwind](../organizations/northwind.md), a customer, opened a support ticket reporting
empty dashboards for older date ranges,[^s18] Larkspur discovered the issue was more serious:
Northwind had needed about three weeks of event history for a compliance audit, and that history
had already aged out under the 7-day window.[^s19] The team agreed the 7-day default had been too
aggressive — optimized, in their own words, for the storage-usage graph rather than for
customers[^s20] — and on 11 February 2026 raised the default to 30 days, reverting the 7-day
default and reasoning that 30 days covers a normal audit/reporting cycle while staying
bounded.[^s20] Larkspur also began advising customers on audit-heavy plans to confirm their
retention window explicitly.[^s21]

## Change Log

- 2026-02-09: default event-retention window set to 7 days.[^s17]
- 2026-02-11: default event-retention window raised to 30 days, reverting the 7-day default,
  after [Northwind](../organizations/northwind.md) lost compliance-audit data under the 7-day
  window.[^s20]

## Large event handling

> [!CONTRADICTION]
> On 12 February 2026, X user @dataskeptic claimed Skylight "silently DROPS any event larger than
> 1MB."[^s28] Replying the same day, [@marcusfeld](../persons/marcusfeld.md) denied this, stating
> events over 1MB are QUEUED and processed within the retention window rather than dropped, and
> pointing to Skylight's documentation (skylight.dev/docs/large-events) as evidence this has been
> the platform's behavior for months.[^s29] He allowed that a source could be misconfigured
> upstream to reject oversized payloads before they reach Skylight, but maintained that is
> distinct from the platform itself dropping events.[^s30]

The corpus contains no independent source (e.g. Skylight's own documentation) to confirm which
side is accurate.[^llm2]

## Known issue: dashboards stale after a timezone change

Skylight's `janitor` service caches an org's UTC offset when it first starts, and uses that cached
offset to bucket incoming events into time windows.[^s8] When an org's timezone is changed,
`janitor` keeps bucketing events with the OLD cached offset until it is restarted, so new events
land in the wrong windows and the dashboards appear frozen on stale data even though ingestion
itself stays healthy.[^s8] The fix is to set the `SKYLIGHT_TZ` environment variable to the org's
IANA timezone and restart `janitor`; it then recomputes the offset and dashboards resume rolling
forward, typically within one refresh cycle.[^s9][^s10]

A separate forum user, mattb, reported a similar-looking freeze after a DST change that was never
root-caused; they worked around it by rebuilding the dashboard from scratch and copying the
configuration over.[^s12]

## Open Points

### Dashboards stale after a timezone change
id: op-dashboards-stale-after-timezone-change
- 2026-02-18: raised by gridlock_92 in the Larkspur community forum: after moving their org from
  US/Eastern to Europe/Berlin, Skylight dashboards froze on old data even though new events kept
  landing; a browser-cache cause and an ingestion outage were both ruled out.[^s5][^s6][^s7]
- 2026-02-19: root-caused and fixed by [Sofia Ruiz](../persons/sofia-ruiz.md) of Larkspur
  Support: `janitor` was bucketing events with the org's stale, cached UTC offset; the fix is to
  set `SKYLIGHT_TZ` to the org's IANA timezone and restart `janitor`.[^s8][^s9][^s10]
- 2026-02-19: resolved; gridlock_92 confirmed the dashboards resumed rolling forward within a
  minute of applying the fix.[^s11]

### Rename retention-svc to janitor
id: op-rename-retention-svc-to-janitor
- 2026-02-09: during the event-retention discussion, [Sofia Ruiz](../persons/sofia-ruiz.md)
  remarked the `retention-svc` service was "basically a janitor at this point,"[^s22] and
  [Tom Alvarez](../persons/tom-alvarez.md) proposed renaming it `retention-svc` to `janitor`,
  noting it had grown to run about four unrelated cleanup jobs; the team agreed, and Alvarez filed
  a low-priority rename ticket.[^s23]
- 2026-02-11: still open; the rename ticket exists but remains low priority and undone.
  [Sofia Ruiz](../persons/sofia-ruiz.md) volunteered to pick it up.[^s24]

## See also

- [Larkspur](../organizations/larkspur.md)
- [Priya Nadkarni](../persons/priya-nadkarni.md)
- [Northwind](../organizations/northwind.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Wei Chen](../persons/wei-chen.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)
- [@marcusfeld](../persons/marcusfeld.md)

## Sources

[^s1]: [raw/announcement.md](../../raw/announcement.md), lines 1-6 — Skylight 2.0 general-availability announcement (ingested 2026-07-14)
[^s2]: [raw/announcement.md](../../raw/announcement.md), lines 8-12 — the three GA regions (ingested 2026-07-14)
[^s3]: [raw/announcement.md](../../raw/announcement.md), lines 14-16 — region selection and rationale (ingested 2026-07-14)
[^s4]: [raw/announcement.md](../../raw/announcement.md), lines 18-20 — Priya Nadkarni's quote (ingested 2026-07-14)
[^s5]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 9-13 — gridlock_92's initial report (ingested 2026-07-14)
[^s6]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 26-27 — browser cache ruled out (ingested 2026-07-14)
[^s7]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 40-41 — ingestion confirmed healthy, dashboards not rolling forward past the timezone switch (ingested 2026-07-14)
[^s8]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 57-60 — Sofia Ruiz's root-cause explanation of `janitor`'s cached-offset bucketing (ingested 2026-07-14)
[^s9]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 64-66 — the fix: set `SKYLIGHT_TZ` and restart `janitor` (ingested 2026-07-14)
[^s10]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 68-70 — dashboards resume rolling forward after the restart (ingested 2026-07-14)
[^s11]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 78-80 — gridlock_92 confirms the fix worked (ingested 2026-07-14)
[^s12]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 47-49 — mattb's similar, unresolved DST-related incident (ingested 2026-07-14)
[^s13]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 17 — Nadkarni on how Skylight's live views update (ingested 2026-07-14)
[^s14]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 41 — Nadkarni on the recent sub-second refresh cut and Larkspur's forward-looking roadmap (ingested 2026-07-14)
[^s15]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 25 — Nadkarni's "only real-time platform with true sub-second refresh" claim (ingested 2026-07-14)
[^s16]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 29 — Nadkarni reiterating the "only ones" claim (ingested 2026-07-14)
[^s17]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 9-17 — the 9 February 2026 decision to set the default event-retention window to 7 days (ingested 2026-07-14)
[^s18]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-40 — Northwind's support ticket about empty dashboards for older date ranges (ingested 2026-07-14)
[^s19]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 45-46 — Northwind's compliance-audit event history lost under the 7-day window (ingested 2026-07-14)
[^s20]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 47-52 — the 11 February 2026 decision to raise the default to 30 days, reverting the 7-day default (ingested 2026-07-14)
[^s21]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 54-56 — the audit-heavy-plans guidance and the 30-day default merged and rolled out (ingested 2026-07-14)
[^s22]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 21 — Sofia Ruiz's "basically a janitor" remark (ingested 2026-07-14)
[^s23]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 19-25 — the 9 February 2026 decision to rename `retention-svc` to `janitor` (ingested 2026-07-14)
[^s24]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 60-61 — the 11 February 2026 status check confirming the rename is still pending (ingested 2026-07-14)
[^s25]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 3-7 — @marcusfeld's launch post announcing sub-second refresh, down from ~5 seconds (ingested 2026-07-14)
[^s26]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 11 — the old pipeline's full-recompute-per-refresh design (ingested 2026-07-14)
[^s27]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 19 — p95 refresh result on the same hardware (ingested 2026-07-14)
[^s28]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 25-26 — @dataskeptic's claim that Skylight drops events over 1MB (ingested 2026-07-14)
[^s29]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 30 — @marcusfeld's rebuttal, citing the docs (ingested 2026-07-14)
[^s30]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 34 — the misconfiguration caveat (ingested 2026-07-14)
[^s31]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 15 — the incremental-update rewrite ("only the deltas... no full recompute") (ingested 2026-07-14)
[^llm1]: LLM - self-promotional competitive claim by Larkspur's founder that Skylight is the only real-time analytics platform with true sub-second refresh; not independently verifiable from this corpus (added 2026-07-14)
[^llm2]: LLM - the large-event-handling dispute between @dataskeptic and @marcusfeld is unresolved; the corpus has no independent source (e.g. Skylight's actual documentation) confirming either side (added 2026-07-14)
