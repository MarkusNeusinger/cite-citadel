---
type: Organization
title: Northwind
description: A Larkspur customer whose compliance-audit event history was lost under
  Skylight's short-lived 7-day event-retention default.
tags:
- customer
- skylight
- larkspur
- event-retention
resource: raw/slack-export-platform-team.txt
timestamp: '2026-07-14T13:03:01Z'
citadel_version: 0.3.0
---

# Northwind

Northwind is a customer of [Larkspur](../organizations/larkspur.md)'s
[Skylight](../systems/skylight.md) analytics dashboard.[^s1]

On 10 February 2026, Northwind opened a support ticket reporting that Skylight
dashboards were empty for date ranges roughly 10-12 days back.[^s1]
[Sofia Ruiz](../persons/sofia-ruiz.md) of Larkspur began investigating.[^s2]

The next day, Ruiz reported the issue was worse than first understood: Northwind
had needed about three weeks of event history for a compliance audit, and that
history had already aged out and been deleted under Skylight's then-current
7-day default event-retention window.[^s3] Larkspur assessed Northwind's
reaction as "not happy and honestly fair."[^s3]

In response, Larkspur raised Skylight's default event-retention window from 7 to
30 days — see [Skylight](../systems/skylight.md) for the full timeline.[^s4]

## See also

- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-37 — Northwind's support ticket about empty dashboards for older date ranges (ingested 2026-07-14)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 39 — Ruiz beginning to investigate (ingested 2026-07-14)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 45-46 — the compliance-audit data loss and Ruiz's assessment (ingested 2026-07-14)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 49-56 — the team's decision to raise the default to 30 days in response (ingested 2026-07-14)
