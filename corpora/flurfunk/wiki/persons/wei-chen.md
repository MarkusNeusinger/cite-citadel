---
type: Person
title: Wei Chen
description: A Larkspur platform engineer who supported Skylight's event-retention
  default changes and reported their rollout.
tags:
- larkspur
- skylight
- platform-engineering
- event-retention
resource: raw/slack-export-platform-team.txt
timestamp: '2026-07-14T13:03:01Z'
citadel_version: 0.3.0
---

# Wei Chen

Wei Chen is a [Larkspur](../organizations/larkspur.md) engineer who takes part
in the company's internal `#platform` Slack channel, where the team discusses
[Skylight](../systems/skylight.md) infrastructure.[^s1]

## Event-retention default

When [Tom Alvarez](../persons/tom-alvarez.md) proposed a 7-day default
event-retention window on 9 February 2026, Chen supported it, reasoning it was
"easy to reason about" and that the team could always raise the window for an
individual customer if needed.[^s2] On 10 February, Chen reported that the
retention-default configuration change had merged and rolled out to
production, making 7 days the default everywhere.[^s3] When a customer's
support ticket about missing older dashboard data came in that same day, Chen
initially read it as "the 7 day window doing its job."[^s4]

Once the ticket turned out to involve a customer's lost compliance-audit data,
Chen agreed the 7-day default had been a mistake, saying the team had
"optimized for our disk graph not for actual customers,"[^s5] and supported
[Sofia Ruiz](../persons/sofia-ruiz.md)'s proposal to raise the default to 30
days.[^s6] See [Skylight](../systems/skylight.md) for the full event-retention
timeline.

## Renaming retention-svc to janitor

Chen joked that the `retention-svc` service was named that because "past-us
was lazy," and supported [Tom Alvarez](../persons/tom-alvarez.md)'s proposal
to rename it `janitor`.[^s7] On 11 February he asked whether the rename had
happened yet; Alvarez confirmed it was still an open, low-priority ticket.[^s8]

## Style profile

- Casual, joking asides, often trailing off with "lol": "yeah the disk graph
  looks like a hockey stick lol"[^s9]
- Expresses enthusiasm about small things in short exclamations: "the spicy
  miso is untouchable btw"[^s10]; "the deploy dashboard is so pretty now that
  refresh is instant, still not over it"[^s11]

## See also

- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)

## Sources

[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-7 — Slack export header and Chen's presence in the channel (ingested 2026-07-14)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 14 — Chen supporting the 7-day proposal (ingested 2026-07-14)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 33 — Chen reporting the 7-day default merged and rolled to production (ingested 2026-07-14)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 38 — Chen's initial read of the Northwind ticket (ingested 2026-07-14)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 48 — Chen's admission that the team optimized for disk usage over customers (ingested 2026-07-14)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 51 — Chen supporting the 30-day revision (ingested 2026-07-14)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 20-23 — Chen's joke about the service's name and support for the rename (ingested 2026-07-14)
[^s8]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 60-61 — Chen asking about the rename status (ingested 2026-07-14)
[^s9]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 10 — Chen's remark on the disk-usage graph (ingested 2026-07-14)
[^s10]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 29 — Chen on the ramen place (ingested 2026-07-14)
[^s11]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 41 — Chen on the deploy dashboard refresh (ingested 2026-07-14)
