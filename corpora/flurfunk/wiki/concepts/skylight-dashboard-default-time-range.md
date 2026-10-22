---
type: Concept
title: Skylight dashboard default time range
description: The default time range of dashboards in new Skylight workspaces — kept
  at last 24 hours after a briefly adopted switch to 7 days was scrapped.
resource: raw/slack-export-platform-team.txt
tags:
- skylight
- dashboard
- platform
- decision
timestamp: '2026-10-22T18:30:30Z'
citadel_version: 0.7.1
---

# Skylight dashboard default time range

As of the end of the #platform thread on 2026-02-10, the dashboard time range in new [Skylight](../systems/skylight.md) workspaces stays at **last 24 hours**; a proposed change to 7 days was scrapped the same afternoon.[^s3]

## Change Log

- 2026-02-10: At 14:02 Wei Chen said new workspaces default the dashboard time range to "last 24 hours" and that support keeps getting "where's my data" tickets from people who expected to see a week.[^s1]
- 2026-02-10: Tom Alvarez proposed and, at 14:05, recorded a decision to default new dashboards to the last 7 days; Sofia Ruiz agreed.[^s1]
- 2026-02-10: At 14:31 Wei Chen objected that, with the event-retention default then at 7 days, a "last 7 days" range would show a half-empty chart as soon as retention pruned anything. Tom Alvarez scrapped the change ("keep the dashboard default range at 24 hours") and Sofia Ruiz agreed to revert it.[^s2][^s3]

The 7-day retention default referred to here was itself replaced by 30 days the next day; see [Skylight default event-retention window](skylight-event-retention-default.md). The thread does not say whether the range decision was revisited after that.[^s4]

## Open Points

### Dashboard default time range

id: op-dashboard-default-time-range
- 2026-02-10: Tom Alvarez said the team could revisit the 24-hour default "once retention is sorted". [^s2]
- 2026-02-11: retention was moved to 30 days; no message in the export revisits the dashboard range. [^s4]

## See also

- [Skylight](../systems/skylight.md)
- [Skylight default event-retention window](skylight-event-retention-default.md)
- [Wei Chen](../persons/wei-chen.md)
- [Tom Alvarez](../persons/tom-alvarez.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 41-44 — problem and 7-day decision (ingested 2026-10-22)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 45-46 — objection and scrapped decision (ingested 2026-10-22)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 46-47 — 24 hours kept, revert (ingested 2026-10-22)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 56-68 — retention moved to 30 days (ingested 2026-10-22)
