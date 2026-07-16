---
type: Person
title: Sofia Ruiz
description: Larkspur Support engineer who diagnosed and fixed a Skylight dashboard
  timezone-caching bug.
resource: raw/forum-support-thread.md
tags:
- larkspur
- skylight
- support
- platform-engineering
timestamp: '2026-07-16T15:01:11Z'
citadel_version: 0.3.0
---

Sofia Ruiz works in [Larkspur](../organizations/larkspur.md) Support.[^s1]

On 2026-02-19, on the Larkspur Community Forum's Skylight Support board, Ruiz posted the
accepted answer diagnosing and fixing a bug where [Skylight](../systems/skylight.md) dashboards
froze on stale data after a customer changed their organization's configured timezone.[^s1] She
explained that Skylight's `janitor` service caches an org's UTC offset when it first starts and
uses that cached offset to bucket incoming events into time windows, so a timezone change leaves
`janitor` bucketing new events by the stale offset until it is restarted.[^s2] Her fix: set the
`SKYLIGHT_TZ` environment variable to the org's IANA timezone and restart `janitor` so it
re-reads the timezone.[^s3]

Ruiz is also active in Larkspur's `#platform` Slack channel, alongside [Tom
Alvarez](tom-alvarez.md) and [Wei Chen](wei-chen.md).[^s4] In February 2026 she took part in the
team's back-and-forth on [Skylight](../systems/skylight.md)'s default event-retention window: she
raised no objection to setting it to 7 days on 2026-02-09,[^s5] flagged the customer Northwind's
resulting support ticket about empty older-range dashboards on 2026-02-10,[^s6] and on 2026-02-11
reported that Northwind had lost three weeks of event history needed for a compliance audit under
the 7-day window.[^s7] She proposed bumping the default to 30 days, owned the PR and changelog
note, and rolled the new default out to production.[^s8] She also approved renaming the
`retention-svc` service to `janitor`[^s9] and, on 2026-02-11, volunteered to pick up the
still-open, low-priority rename ticket.[^s10]

## See also

- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Tom Alvarez](tom-alvarez.md)
- [Wei Chen](wei-chen.md)

## Sources

[^s1]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 55-57 — Ruiz posts the accepted answer as Larkspur Support (ingested 2026-07-15)
[^s2]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 59-62 — Ruiz's root-cause diagnosis of the `janitor` caching bug (ingested 2026-07-15)
[^s3]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 64-72 — Ruiz's fix steps (ingested 2026-07-15)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-8 — Slack export header and Ruiz's presence in #platform (ingested 2026-07-16)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 16 — no objection to the 7-day retention proposal (ingested 2026-07-16)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-39 — flags Northwind's ticket about empty older-range dashboards (ingested 2026-07-16)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 55-56 — reports Northwind's compliance-audit data loss (ingested 2026-07-16)
[^s8]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 59-66 — proposes the 30-day bump, owns the PR/changelog, rolls it out (ingested 2026-07-16)
[^s9]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 24 — approves renaming retention-svc to janitor (ingested 2026-07-16)
[^s10]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 72 — volunteers to take the rename ticket (ingested 2026-07-16)
