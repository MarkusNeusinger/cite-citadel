---
type: System
title: Skylight
description: Larkspur's real-time analytics dashboard, with release 2.0 generally
  available in three regions since 1 April 2026.
resource: raw/announcement.md
tags:
- analytics
- dashboard
- larkspur
timestamp: '2026-10-22T18:31:14Z'
citadel_version: 0.7.1
---

# Skylight

Skylight is the real-time analytics dashboard of [Larkspur](../organizations/larkspur.md).[^s1]

## Skylight 2.0

- Larkspur announced Skylight 2.0 as generally available as of 1 April 2026.[^s1]
- Larkspur says the milestone was reached with a team of around 30 people, and describes the company as proud of it.[^s1]
- Skylight 2.0 is available in three regions: EU (Frankfurt), US (Virginia) and APAC (Singapore).[^s2]
- The announcement says that deploying in the region closest to the data keeps latency low and helps teams meet regional data residency requirements.[^s3]
- Existing customers select their region in the workspace settings; new workspaces are prompted to choose a region during setup.[^s3]
- [Priya Nadkarni](../persons/priya-nadkarni.md), founder and CEO of Larkspur, is quoted as saying that Skylight 2.0 is "the version we always wanted to ship" and that three regions give teams around the world the same real-time experience close to home.[^s4]
- Setup instructions and the full list of changes are in the Skylight 2.0 release notes in the documentation.[^s5]

## Outside perception

- In a March 2026 cover letter, job applicant [Dana Kessler](../persons/dana-kessler.md) says they were impressed by Skylight's recent sub-second refresh work, i.e. refreshing a live analytics dashboard in under a second.[^s6]

## From the founder interview

- Priya Nadkarni described Skylight as a real-time analytics dashboard: you point your event stream at it and get live views that update as things happen, "not thirty seconds later".[^s8]
- She said Larkspur recently cut dashboard refresh to under a second and that the response has been incredible.[^s9]
- She said that next, the team is pushing on scale and on "the regions story", getting Skylight closer to customers around the world.[^s9]
- She claimed Skylight is the only real-time analytics platform with true sub-second refresh; see [Larkspur](../organizations/larkspur.md) for the quarantine note on this claim.[^s10][^llm1]

## Sub-second refresh launch thread

- On 2026-02-12 [@marcusfeld](../persons/marcusfeld.md) posted a launch thread on X saying Skylight dashboards now refresh in under one second, where refresh used to take about 5 seconds.[^s13]
- He said the old pipeline recomputed the whole aggregate on every refresh, which was painful once a customer had millions of events streaming in.[^s14]
- He said the aggregation layer was rewritten to do incremental updates, folding in only the deltas since the last frame instead of a full recompute.[^s15]
- He claimed p95 refresh is now well under 1 second on the same hardware.[^s16][^llm2]

## Large events (over 1 MB)

- On 2026-02-12 X user @dataskeptic posted that Skylight "silently DROPS any event larger than 1MB".[^s17]
- @marcusfeld replied the same day that this is not true: large events are queued and processed within the retention window, never dropped, and he said this is documented at skylight.example/docs/large-events.[^s18]
- He added that a source could be misconfigured to reject oversized payloads upstream, which he called the customer's side, and that the platform itself queues such events and works them off.[^s19]
- The two claims are opposed and no other source on the wiki settles them; the retention window he refers to is described in [Skylight default event-retention window](../concepts/skylight-event-retention-default.md).

## Defaults

- The default event-retention window is 30 days since 2026-02-11, after a 7-day default was live for about a day; see [Skylight default event-retention window](../concepts/skylight-event-retention-default.md).[^s11]
- New workspaces default the dashboard time range to the last 24 hours; see [Skylight dashboard default time range](../concepts/skylight-dashboard-default-time-range.md).[^s12]

## Known issues

- Per Larkspur Support, a change of an org's timezone can leave dashboards frozen on old data until `SKYLIGHT_TZ` is set and the [janitor](janitor.md) service is restarted; see [the forum case](../concepts/skylight-dashboard-stale-after-timezone-change.md).[^s7]

## See also

- [janitor](janitor.md)
- [Larkspur](../organizations/larkspur.md)
- [Priya Nadkarni](../persons/priya-nadkarni.md)
- [Dana Kessler](../persons/dana-kessler.md)
- [Northwind](../organizations/northwind.md)
- [@marcusfeld](../persons/marcusfeld.md)

## Sources

[^s1]: [raw/announcement.md](../../raw/announcement.md), lines 3-7 — general availability announcement (ingested 2026-10-22)
[^s2]: [raw/announcement.md](../../raw/announcement.md), lines 11-15 — regions (ingested 2026-10-22)
[^s3]: [raw/announcement.md](../../raw/announcement.md), lines 17-19 — region choice and data residency (ingested 2026-10-22)
[^s4]: [raw/announcement.md](../../raw/announcement.md), lines 21-23 — CEO quote (ingested 2026-10-22)
[^s5]: [raw/announcement.md](../../raw/announcement.md), lines 25-26 — release notes pointer (ingested 2026-10-22)
[^s6]: [raw/application-cover-letter.md](../../raw/application-cover-letter.md), line 11 — applicant's view of sub-second refresh (ingested 2026-10-22)
[^s7]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 55-72 — accepted support answer (ingested 2026-10-22)
[^s8]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 17 — what Skylight is (ingested 2026-10-22)
[^s9]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 41 — recent refresh work and next steps (ingested 2026-10-22)
[^s10]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), lines 25-29 — differentiator claim (ingested 2026-10-22)
[^s11]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 63-67 — 30-day default (ingested 2026-10-22)
[^s12]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 45-47 — 24h range kept (ingested 2026-10-22)
[^s13]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 5-7 — launch post (ingested 2026-10-22)
[^s14]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 11 — old pipeline (ingested 2026-10-22)
[^s15]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 15 — incremental aggregation (ingested 2026-10-22)
[^s16]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 19 — p95 claim (ingested 2026-10-22)
[^s17]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 25-26 — @dataskeptic's post (ingested 2026-10-22)
[^s18]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 30 — reply on large events (ingested 2026-10-22)
[^s19]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 34 — upstream rejection caveat (ingested 2026-10-22)
[^llm1]: LLM - model knowledge, not from a raw file: competing real-time analytics products also market sub-second refresh, so an "only one" claim conflicts with established knowledge of the market (added 2026-10-22)
[^llm2]: LLM - model knowledge, not from a raw file: the p95 figure is a self-reported launch claim by the vendor's side, with no independent benchmark cited in the thread (added 2026-10-22)
