---
type: Person
title: Sofia Ruiz
description: A Larkspur engineer who investigated a customer's event-retention data-loss
  incident and owned Skylight's event-retention window increase from 7 to 30 days.
tags:
- larkspur
- skylight
- support
- event-retention
resource: raw/slack-export-platform-team.txt
timestamp: '2026-07-14T13:03:01Z'
citadel_version: 0.3.0
---

# Sofia Ruiz

Sofia Ruiz is a [Larkspur](../organizations/larkspur.md) engineer who takes
part in the company's internal `#platform` Slack channel, where the team
discusses [Skylight](../systems/skylight.md) infrastructure.[^s1] She also
works in Larkspur Support, where in February 2026 she diagnosed and fixed a
customer-reported Skylight bug.[^s2]

## Event-retention default

On 9 February 2026, when [Tom Alvarez](../persons/tom-alvarez.md) proposed a
7-day default event-retention window, Ruiz raised no objection and said to
"ship it."[^s3] During the same conversation, discussing why the
`retention-svc` service was named that, Ruiz remarked it was "basically a
janitor at this point" — the line that seeded the service's later rename.[^s4]

On 10 February, Ruiz flagged that a customer,
[Northwind](../organizations/northwind.md), had opened a support ticket
reporting that Skylight dashboards were empty for older date ranges, and said
she would investigate.[^s5] The next day she reported the issue was worse than
first thought: Northwind had needed about three weeks of event history for a
compliance audit, and it had aged out under the 7-day retention window; she
described the customer as "not happy and honestly fair."[^s6]

Ruiz proposed raising the default event-retention window to 30 days,
reasoning it would cover a normal audit/reporting cycle while staying bounded;
once the team agreed, she took ownership of the pull request and an
accompanying changelog note.[^s7] She added a note that customers on
audit-heavy plans should confirm their retention window explicitly,[^s8] and
later reported the change merged and rolled out, making 30 days the new
default.[^s9] See [Skylight](../systems/skylight.md) for the full
event-retention timeline.

## Renaming retention-svc to janitor

On 11 February, when [Wei Chen](../persons/wei-chen.md) asked whether the
retention-svc-to-janitor rename had happened, Ruiz volunteered to pick up the
still-open, low-priority ticket herself.[^s10]

## Style profile

- Reacts with brief, expressive interjections rather than full sentences,
  often emoji-only: "😂 accurate"[^s11]; "🧹 approved"[^s12]
- States a blunt conclusion, then softens it with a short qualifier: "they are
  not happy and honestly fair."[^s6]
- Signals ownership of a task plainly: "I'll own the PR and the changelog
  note."[^s7]

## See also

- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Northwind](../organizations/northwind.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Wei Chen](../persons/wei-chen.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-8 — Slack export header and Ruiz's presence in the channel (ingested 2026-07-14)
[^s2]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 53-60 — Ruiz identified as Larkspur Support, diagnosing the timezone/dashboard bug (ingested 2026-07-14)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 16 — Ruiz's "ship it" (ingested 2026-07-14)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 21 — Ruiz's "basically a janitor" remark (ingested 2026-07-14)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-39 — Ruiz flagging the Northwind ticket and starting to investigate (ingested 2026-07-14)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 45-46 — Ruiz's report of the compliance-audit data loss (ingested 2026-07-14)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 49-52 — Ruiz's 30-day proposal, the decision, and her ownership of the PR (ingested 2026-07-14)
[^s8]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 54 — the audit-heavy-plans guidance note (ingested 2026-07-14)
[^s9]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 56 — the 30-day default merged and rolled out (ingested 2026-07-14)
[^s10]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 60-62 — the rename-status exchange and Ruiz volunteering (ingested 2026-07-14)
[^s11]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 12 — Ruiz's reaction to the disk-usage graph (ingested 2026-07-14)
[^s12]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 24 — Ruiz's reaction to the rename approval (ingested 2026-07-14)
