---
type: System
title: janitor
description: Skylight service that buckets incoming events into time windows using
  the org's UTC offset, cached at startup.
resource: raw/forum-support-thread.md
tags:
- skylight
- timezone
- troubleshooting
timestamp: '2026-10-22T18:30:30Z'
citadel_version: 0.7.1
---

# janitor

`janitor` is a service of [Skylight](skylight.md). According to [Sofia Ruiz](../persons/sofia-ruiz.md) of Larkspur Support, it caches the org's UTC offset when it first starts and uses that cached offset to bucket events into time windows.[^s1]

## Stale offset after a timezone change

- Sofia Ruiz wrote on 2026-02-19 that when an org's timezone is changed, `janitor` keeps using the old offset it cached at boot, so new events are bucketed into the wrong windows and dashboards look frozen on the old data.[^s1]
- The fix she gave: set the `SKYLIGHT_TZ` environment variable to the org's IANA timezone (for example `Europe/Berlin`), then restart `janitor` so it re-reads the timezone and recomputes the offset.[^s2]
- She added that one refresh cycle may be needed for the buckets to catch up.[^s2]
- The forum user gridlock_92 reported on 2026-02-19 that, after setting `SKYLIGHT_TZ=Europe/Berlin` and restarting `janitor`, the dashboards started moving again within a minute with correct local times, and marked the answer as accepted.[^s3]

See [Skylight dashboard stale after timezone change](../concepts/skylight-dashboard-stale-after-timezone-change.md) for the full case.

## Rename from retention-svc

- In the #platform channel on 2026-02-09, [Tom Alvarez](../persons/tom-alvarez.md) asked why `retention-svc` is named that when it now runs about four unrelated cleanup jobs; [Sofia Ruiz](../persons/sofia-ruiz.md) called it "basically a janitor", and the three participants agreed to rename `retention-svc` to `janitor`.[^s4]
- The `retention-svc` → `janitor` rename is described as a low-priority ticket. The #platform export does not say whether this is the same service the forum thread (2026-02-19) calls `janitor` and describes as bucketing events by UTC offset.[^s5]

## Open Points

### Rename retention-svc to janitor

id: op-rename-retention-svc-to-janitor
- 2026-02-09: Tom Alvarez agreed to add a low-priority rename ticket. [^s4]
- 2026-02-11: ticket exists, still low priority; Sofia Ruiz said she would take it on a slow afternoon. [^s5]

## See also

- [Skylight](skylight.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)
- [Skylight dashboard stale after timezone change](../concepts/skylight-dashboard-stale-after-timezone-change.md)

## Sources

[^s1]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 55-62 — accepted answer, cause (ingested 2026-10-22)
[^s2]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 64-72 — accepted answer, fix (ingested 2026-10-22)
[^s3]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 78-82 — confirmation by gridlock_92 (ingested 2026-10-22)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 19-25 — rename agreed (ingested 2026-10-22)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 71-74 — rename ticket status (ingested 2026-10-22)
