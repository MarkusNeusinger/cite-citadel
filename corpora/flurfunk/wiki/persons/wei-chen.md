---
type: Person
title: Wei Chen
description: 'Larkspur engineer active in the #platform Slack channel; caught the
  conflict that reversed a Skylight dashboard-default decision.'
resource: raw/slack-export-platform-team.txt
tags:
- larkspur
- platform-engineering
- skylight
timestamp: '2026-07-16T15:01:11Z'
citadel_version: 0.3.0
---

Wei Chen posts in Larkspur's `#platform` Slack channel.[^s1]

On 2026-02-09, Chen agreed with [Tom Alvarez](tom-alvarez.md)'s proposal to set
[Skylight](../systems/skylight.md)'s default event-retention window to 7 days, saying it was
"easy to reason about" and that it could be raised per-customer if someone complained.[^s2] Chen
also agreed with renaming the `retention-svc` service to `janitor`, joking that the old name was
because "past-us was lazy."[^s3]

On 2026-02-10, Chen noted that new workspaces still defaulted their dashboard time range to "last
24 hours," which was generating "where's my data" support tickets from users expecting to see a
week of data — the observation that led Alvarez to propose a 7-day dashboard default.[^s4]
Minutes after that was decided, Chen caught that a 7-day dashboard default would show a
half-empty chart the moment the 7-day retention window pruned older events, making the product
look more broken rather than less — the catch that reversed the decision back to a 24-hour
default.[^s5]

On 2026-02-11, after Northwind's compliance-audit data loss came to light, Chen said the team had
"optimized for our disk graph not for actual customers," and supported bumping the default
event-retention window to 30 days.[^s6]

## See also

- [Skylight](../systems/skylight.md)
- [Larkspur](../organizations/larkspur.md)
- [Tom Alvarez](tom-alvarez.md)
- [Sofia Ruiz](sofia-ruiz.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-7 — Slack export header and Chen's presence in #platform (ingested 2026-07-16)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 14 — agrees with the 7-day retention proposal (ingested 2026-07-16)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 20-23 — agrees with renaming retention-svc to janitor (ingested 2026-07-16)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 41 — notes the 24-hour default is generating support tickets (ingested 2026-07-16)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 45 — catches the conflict between the dashboard and retention defaults (ingested 2026-07-16)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 58 — "optimized for our disk graph not for actual customers" (ingested 2026-07-16)
