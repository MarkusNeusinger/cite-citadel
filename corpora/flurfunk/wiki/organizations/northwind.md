---
type: Organization
title: Northwind
description: Skylight customer that lost event history needed for a compliance audit
  under the short-lived 7-day retention default.
resource: raw/slack-export-platform-team.txt
tags:
- skylight
- customer
- retention
timestamp: '2026-10-22T18:30:30Z'
citadel_version: 0.7.1
---

# Northwind

Northwind is a customer of [Larkspur](larkspur.md)'s [Skylight](../systems/skylight.md), as reported by [Sofia Ruiz](../persons/sofia-ruiz.md) in the #platform channel.[^s1]

- On 2026-02-10 Sofia Ruiz said Northwind had opened a ticket saying some dashboards were empty for older ranges, about 10-12 days back. She told the team she would dig in.[^s1]
- On 2026-02-11 she reported that Northwind had needed three weeks of event history for a compliance audit, which had aged out under the 7-day retention window. She said they were not happy.[^s2]
- The team responded by raising the default to 30 days; see [Skylight default event-retention window](../concepts/skylight-event-retention-default.md).[^s3]

## See also

- [Skylight default event-retention window](../concepts/skylight-event-retention-default.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)
- [Skylight](../systems/skylight.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-39 — ticket about empty dashboards (ingested 2026-10-22)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 56-57 — compliance-audit history lost (ingested 2026-10-22)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 60-63 — 30-day decision (ingested 2026-10-22)
