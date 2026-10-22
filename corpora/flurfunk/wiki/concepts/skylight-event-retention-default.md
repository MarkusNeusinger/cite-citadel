---
type: Concept
title: Skylight event retention default
description: How long Skylight keeps events by default — currently 30 days, after
  a 7-day default was set and reverted in February 2026.
resource: raw/slack-export-platform-team.txt
tags:
- skylight
- retention
- platform
- decision
timestamp: '2026-10-22T18:30:30Z'
citadel_version: 0.7.1
---

# Skylight default event-retention window

The current default event-retention window for [Skylight](../systems/skylight.md) is **30 days**. It was set on 2026-02-11 by [Sofia Ruiz](../persons/sofia-ruiz.md), [Tom Alvarez](../persons/tom-alvarez.md) and [Wei Chen](../persons/wei-chen.md) in the #platform channel, replacing a 7-day default that had been live for about one day.[^s5][^s6]

## Why a default was needed

- On 2026-02-09 at 09:11 Tom Alvarez noted that there was still no default event-retention window and that staging was keeping events forever; Wei Chen described the disk graph as a "hockey stick".[^s1]

## Change Log

- 2026-02-09: Tom Alvarez proposed a 7-day default (reasoning: it keeps storage sane and most dashboards only look at the last few days). Wei Chen and Sofia Ruiz agreed, and at 09:18 Tom recorded the decision "Skylight default event-retention = 7 days" and said he would do the config PR.[^s2]
- 2026-02-10: At 10:04 Wei Chen reported the retention default PR merged and rolled to prod, "7 days everywhere now".[^s3]
- 2026-02-10: At 10:22 Sofia Ruiz reported that [Northwind](../organizations/northwind.md) had opened a ticket about dashboards being empty for older ranges (about 10-12 days back); Wei Chen said that was the 7-day window working as designed.[^s4]
- 2026-02-11: At 08:51 Sofia Ruiz reported that Northwind had needed three weeks of event history for a compliance audit and that it had aged out under the 7-day window. Tom Alvarez said 7 days was too aggressive, and Wei Chen said the team had "optimized for our disk graph not for actual customers".[^s5]
- 2026-02-11: Sofia proposed 30 days (covers a normal audit/reporting cycle and is still bounded); Tom and Wei agreed. At 08:57 she recorded the decision "default event-retention = 30 days, reverting the 7 day default" and took ownership of the PR and the changelog note.[^s5]
- 2026-02-11: At 09:20 Sofia said the PR was up and that it also adds a note that customers on audit-heavy plans should confirm their window explicitly. At 09:40 she reported it merged and rolling out, with 30 days the default "as of now".[^s6]

## Related decision

The dashboard time-range default was discussed in the same period, tied to this retention value; see [Skylight dashboard default time range](skylight-dashboard-default-time-range.md).

## See also

- [Skylight](../systems/skylight.md)
- [Northwind](../organizations/northwind.md)
- [Skylight dashboard default time range](skylight-dashboard-default-time-range.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Wei Chen](../persons/wei-chen.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 9-12 — problem statement (ingested 2026-10-22)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 13-17 — 7-day proposal and decision (ingested 2026-10-22)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 33 — 7-day default rolled to prod (ingested 2026-10-22)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-39 — Northwind ticket (ingested 2026-10-22)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 56-63 — audit data loss, 30-day decision (ingested 2026-10-22)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 65-67 — PR, audit-plan note, rollout (ingested 2026-10-22)
