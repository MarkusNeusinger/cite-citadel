---
type: Person
title: Tom Alvarez
description: 'Larkspur engineer active in the #platform Slack channel; proposed Skylight''s
  event-retention and dashboard-default changes.'
resource: raw/slack-export-platform-team.txt
tags:
- larkspur
- platform-engineering
- skylight
timestamp: '2026-07-16T15:01:11Z'
citadel_version: 0.3.0
---

Tom Alvarez posts in Larkspur's `#platform` Slack channel.[^s1]

## Event retention default

On 2026-02-09, Alvarez raised that [Skylight](../systems/skylight.md) had no default
event-retention window and staging was hoarding events indefinitely.[^s2] He proposed setting the
default to 7 days.[^s3] He then announced the decision and said he would do the config PR after
standup.[^s4]

On 2026-02-11, after Northwind's compliance-audit data loss came to light, Alvarez agreed the
7-day default had been too aggressive.[^s10] He approved bumping the default to 30 days ("30
works. do it").[^s11]

## `retention-svc` naming

Also on 2026-02-09, Alvarez asked why the `retention-svc` service was named that, noting it now
does about four unrelated cleanup jobs.[^s5] He proposed renaming it to `janitor`.[^s6] He said he
would file a rename ticket, marked low priority.[^s7] As of 2026-02-11, he confirmed the ticket
still existed and was still low priority.[^s12]

## Dashboard time-range default

On 2026-02-10, Alvarez proposed defaulting new workspaces' dashboard time range to the last 7
days (instead of 24 hours) and announced it as a decision.[^s8] Minutes later, after [Wei
Chen](wei-chen.md) pointed out this would conflict with the 7-day event-retention default,
Alvarez agreed and reverted the decision, keeping the default at 24 hours.[^s9]

## See also

- [Skylight](../systems/skylight.md)
- [Larkspur](../organizations/larkspur.md)
- [Wei Chen](wei-chen.md)
- [Sofia Ruiz](sofia-ruiz.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-6 — Slack export header and Alvarez's presence in #platform (ingested 2026-07-16)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 9 — raises that Skylight has no default retention window (ingested 2026-07-16)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 13 — proposes a 7-day default (ingested 2026-07-16)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 17 — announces the decision, commits to the config PR (ingested 2026-07-16)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 19 — asks why retention-svc is named that (ingested 2026-07-16)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 22 — proposes renaming retention-svc to janitor (ingested 2026-07-16)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 25 — commits to filing a low-priority rename ticket (ingested 2026-07-16)
[^s8]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 42-44 — proposes and decides the 7-day dashboard default (ingested 2026-07-16)
[^s9]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 46 — agrees with the catch and reverts to 24 hours (ingested 2026-07-16)
[^s10]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 57 — agrees the 7-day retention default was too aggressive (ingested 2026-07-16)
[^s11]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 60 — approves bumping the default to 30 days (ingested 2026-07-16)
[^s12]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 71 — confirms the rename ticket still exists, still low priority (ingested 2026-07-16)
