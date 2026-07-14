---
type: Person
title: Tom Alvarez
description: A Larkspur platform engineer who proposed Skylight's original 7-day default
  event-retention window and approved its later revision to 30 days.
tags:
- larkspur
- skylight
- platform-engineering
- event-retention
resource: raw/slack-export-platform-team.txt
timestamp: '2026-07-14T13:03:01Z'
citadel_version: 0.3.0
---

# Tom Alvarez

Tom Alvarez is a [Larkspur](../organizations/larkspur.md) engineer who takes
part in the company's internal `#platform` Slack channel, where the team
discusses [Skylight](../systems/skylight.md) infrastructure such as service
configuration and deploys.[^s1]

## Event-retention default

On 9 February 2026, Alvarez pointed out that Skylight had no default
event-retention window set and that staging events were being kept
indefinitely.[^s1] He proposed a default of 7 days, reasoning it would keep
storage usage predictable since most dashboards only look at the last few days
of data.[^s2] [Wei Chen](../persons/wei-chen.md) and
[Sofia Ruiz](../persons/sofia-ruiz.md) agreed, and Alvarez confirmed the
decision, saying he would open the configuration pull request.[^s3]

After [Northwind](../organizations/northwind.md), a customer, lost event
history it needed for a compliance audit under the 7-day window, Alvarez agreed
the default had been "too aggressive" and approved
[Sofia Ruiz](../persons/sofia-ruiz.md)'s proposal to raise it to 30 days.[^s4]
See [Skylight](../systems/skylight.md) for the full event-retention timeline.

## Renaming retention-svc to janitor

In the same 9 February conversation, Alvarez asked why the `retention-svc`
service was named that, noting it had grown to run about four unrelated
cleanup jobs. When [Sofia Ruiz](../persons/sofia-ruiz.md) remarked it was
"basically a janitor at this point," Alvarez proposed renaming it
`retention-svc` to `janitor`; the team agreed, and he said he would file a
low-priority rename ticket.[^s5] Two days later he confirmed the ticket still
existed but remained low priority.[^s6]

## Style profile

- Confirms decisions in short, matter-of-fact sentences: "cool. so decision:
  Skylight default event-retention = 7 days. I'll do the config PR after
  standup."[^s3]
- Signs off on follow-up items tersely: "k I'll add a rename ticket, low
  prio."[^s5]
- Uses short acknowledgments to close out a thread: "k keep me posted."[^s7]

## See also

- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Wei Chen](../persons/wei-chen.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-9 — Slack export header and Alvarez raising the missing retention default (ingested 2026-07-14)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 13 — Alvarez's 7-day proposal and rationale (ingested 2026-07-14)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 14-18 — agreement and Alvarez confirming the 7-day decision (ingested 2026-07-14)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 47-53 — Alvarez's reaction to the Northwind data loss and his approval of the 30-day revision (ingested 2026-07-14)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 19-25 — the `retention-svc` naming discussion and rename decision (ingested 2026-07-14)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 60-61 — Alvarez confirming the rename ticket is still low priority (ingested 2026-07-14)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 40 — Alvarez asking to be kept posted on the Northwind ticket (ingested 2026-07-14)
