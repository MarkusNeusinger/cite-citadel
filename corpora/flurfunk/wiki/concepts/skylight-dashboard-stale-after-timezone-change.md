---
type: Concept
title: Skylight dashboard stale after timezone change
description: Forum case of Skylight dashboards freezing after an org changed timezone,
  and the SKYLIGHT_TZ plus janitor restart fix.
resource: raw/forum-support-thread.md
tags:
- skylight
- timezone
- troubleshooting
timestamp: '2026-10-22T18:28:05Z'
citadel_version: 0.7.1
---

# Skylight dashboard stale after timezone change

A thread on the Larkspur Community Forum (Skylight Support), opened 2026-02-18.

## Problem

- gridlock_92 reported on 2026-02-18 that after their org moved from US/Eastern to Europe/Berlin the previous week, their [Skylight](../systems/skylight.md) dashboards were stuck on old data, frozen at the moment of the switch, although new events were visible in the raw event log.[^s1]
- gridlock_92 stated that ingestion status was green and events were landing; the dashboards computed against the old data and would not roll forward past the timezone switch.[^s2]

## Ruled out

- hannah.op suggested a hard refresh (Ctrl+Shift+R) because the frontend might cache aggregates; gridlock_92 reported having tried that, clearing the whole browser cache, an incognito window and a different machine, with the same stale numbers, and concluded the problem was server-side.[^s3]
- hannah.op also suggested the event stream might have stopped, with events only landing in a buffer, and recommended checking the ingestion status page.[^s4]
- mattb wrote that they had hit something similar after a daylight-saving change, never root-caused it, and worked around it by creating a fresh dashboard and copying the config over; they called this an ugly workaround.[^s5]

## Accepted answer

- On 2026-02-19 [Sofia Ruiz](../persons/sofia-ruiz.md) of Larkspur Support called it a known, fixable issue needing no rebuild, and explained that the [janitor](../systems/janitor.md) service caches the org's UTC offset at first start and keeps using the old offset after a timezone change, so new events land in the wrong time windows.[^s6]
- Her fix: set `SKYLIGHT_TZ` to the org's IANA timezone (here `Europe/Berlin`) and restart `janitor`; allow one refresh cycle for the buckets to catch up.[^s7]
- gridlock_92 confirmed on 2026-02-19 that this worked, with dashboards moving again within a minute and showing correct local times.[^s8]

## See also

- [janitor](../systems/janitor.md)
- [Skylight](../systems/skylight.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)

## Sources

[^s1]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 7-13 — original post (ingested 2026-10-22)
[^s2]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 38-41 — ingestion green (ingested 2026-10-22)
[^s3]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 17-27 — browser-cache suggestion and reply (ingested 2026-10-22)
[^s4]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 31-34 — event-stream suggestion (ingested 2026-10-22)
[^s5]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 45-48 — mattb's workaround (ingested 2026-10-22)
[^s6]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 55-62 — cause (ingested 2026-10-22)
[^s7]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 64-72 — fix (ingested 2026-10-22)
[^s8]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 78-82 — confirmation (ingested 2026-10-22)
