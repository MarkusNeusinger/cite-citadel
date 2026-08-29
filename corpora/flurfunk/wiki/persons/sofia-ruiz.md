---
type: Person
title: Sofia Ruiz
description: 'Larkspur engineer on Skylight Support and the #platform channel; diagnosed
  a timezone-related dashboard bug and owned Skylight''s event-retention default changes
  in February 2026.'
tags:
- support
- skylight
- larkspur
- platform
resource: raw/forum-support-thread.md
timestamp: '2026-08-29T00:18:16Z'
citadel_version: 0.6.0
---

Sofia Ruiz works on [Larkspur](../organizations/larkspur.md)'s Skylight Support team.[^s1]

On 2026-02-19, in the Larkspur Community Forum, Ruiz diagnosed a bug where
[Skylight](../systems/skylight.md) dashboards froze on stale data after a customer changed their
org's timezone: the `janitor` service caches an org's UTC offset when it starts and uses that
cached offset to bucket events into time windows, so it keeps bucketing against the old offset
after a timezone change.[^s2] She gave the fix — set the `SKYLIGHT_TZ` environment variable to the
org's IANA timezone and restart `janitor` so it re-reads the timezone — and noted the dashboards
might take one refresh cycle to catch up.[^s3] She also offered to dig in further if the fix did
not clear the issue.[^s4] The customer confirmed the fix worked and marked her reply as the
thread's accepted answer.[^s5]

## #platform channel: event-retention and dashboard decisions

In Larkspur's internal #platform Slack channel, Ruiz raised that a customer, Northwind, had opened
a ticket reporting empty [Skylight](../systems/skylight.md) dashboards for date ranges 10-12 days
back, and said she would dig into it.[^s7] She later reported that Northwind actually needed 3
weeks of event history for a compliance audit that had aged out under Skylight's 7-day
event-retention default, calling the situation "worse than I thought."[^s8] She proposed bumping
the default event-retention window to 30 days, and, once the team agreed, owned the resulting PR
and its changelog note — which also flags that customers on audit-heavy plans should confirm their
retention window explicitly — merging and rolling it out on 2026-02-11.[^s9][^s10][^s11] (See
Skylight's Change Log for the full retention-window history.)

Ruiz also took on the open ticket to rename Skylight's `retention-svc` service to `janitor`, a
rename the #platform team had agreed to informally on 2026-02-09 but left as a low-priority,
unstarted ticket.[^s12]

## Style profile

- Opens by naming the person she's replying to and reassuring them before diagnosing: "Hi
  gridlock_92 — this is a known one and it's fixable, no need to rebuild anything."[^s6]
- Leads the technical explanation with a plain-language framing before the mechanism: "What's
  happening: the `janitor` service caches your org's UTC offset when it first starts, and it uses
  that cached offset to bucket events into time windows."[^s2]
- Gives the fix as a short, numbered list rather than prose.[^s3]
- Closes by inviting further contact if the fix doesn't resolve things: "Let me know if it doesn't
  clear up after the restart and I'll dig in further."[^s4]

## See also
- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Wei Chen](../persons/wei-chen.md)

## Sources
[^s1]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), line 55 — byline: Sofia Ruiz (Larkspur Support) (ingested 2026-08-29)
[^s2]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 57-62 — Ruiz's explanation of the janitor timezone-caching bug (ingested 2026-08-29)
[^s3]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 64-72 — Ruiz's fix: SKYLIGHT_TZ env var and janitor restart (ingested 2026-08-29)
[^s4]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), line 74 — Ruiz's closing offer to help further (ingested 2026-08-29)
[^s5]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 80-82 — gridlock_92 confirms the fix worked and marks the reply accepted (ingested 2026-08-29)
[^s6]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), line 57 — Ruiz's opening line (ingested 2026-08-29)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-39 — Sofia Ruiz relays Northwind's ticket about empty dashboards and says she'll dig in (ingested 2026-08-29)
[^s8]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 55 — Sofia Ruiz, 2026-02-11 08:51: Northwind needed 3 weeks of event history that aged out under the 7-day window, "worse than I thought" (ingested 2026-08-29)
[^s9]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 59-62 — Sofia Ruiz proposes the 30-day retention default and owns the PR and changelog note (ingested 2026-08-29)
[^s10]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 64 — Sofia Ruiz, 2026-02-11 09:20: changelog note advising customers on audit-heavy plans to confirm their retention window explicitly (ingested 2026-08-29)
[^s11]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 66 — Sofia Ruiz, 2026-02-11 09:40: 30-day retention default merged and rolled out (ingested 2026-08-29)
[^s12]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 71-72 — Tom Alvarez confirms the janitor rename ticket is still open and low priority; Sofia Ruiz says she'll take it (ingested 2026-08-29)
