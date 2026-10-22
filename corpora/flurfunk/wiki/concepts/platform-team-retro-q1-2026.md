---
type: Concept
title: Platform team retro — Q1 2026
description: What the reconstructed Q1 2026 platform team retro records about the
  CI speed-up, the Friday demo slot, the lost coverage reporting and a coverage check.
tags:
- retros
- platform-team
- ci
- testing
resource: raw/retros/2026-q1.md
timestamp: '2026-10-22T18:33:22Z'
citadel_version: 0.7.1
---

# Platform team retro — Q1 2026

This summary is part of the [platform team retros](platform-team-retros.md), which the folder's note describes as a reconstruction that the team has not confirmed.[^s6] The statements below are therefore the contractor's reconstruction of the retro, not confirmed statements of the team.[^s6]

## What went well

- The retro records that the main CI pipeline was cut from 22 minutes to 9 minutes by splitting the integration suite into four parallel shards.[^s1]
- It records that a fortnightly Friday demo slot was started, in which one team member shows something that was shipped.[^s2]

## What went badly

- The retro records that the shard split broke code-coverage reporting for three weeks before anyone noticed.[^s3]

## Proposed for next quarter

- The retro proposes adding a check that fails the pipeline when coverage reporting goes missing.[^s4]

## Open Points

### Coverage reporting check
id: op-coverage-reporting-check
- 2026-10-22: proposed in the Q1 2026 retro (date of ingestion; the source states no date): add a check that fails the pipeline when coverage reporting goes missing. [^s4]

## See also

- [Platform team retros](platform-team-retros.md)
- [Platform team retro — Q4 2025](platform-team-retro-q4-2025.md)

## Sources

[^s1]: [raw/retros/2026-q1.md](../../raw/retros/2026-q1.md), lines 5-6 — CI pipeline cut from 22 to 9 minutes (ingested 2026-10-22)
[^s2]: [raw/retros/2026-q1.md](../../raw/retros/2026-q1.md), line 7 — fortnightly Friday demo slot (ingested 2026-10-22)
[^s3]: [raw/retros/2026-q1.md](../../raw/retros/2026-q1.md), line 11 — coverage reporting broken for three weeks (ingested 2026-10-22)
[^s4]: [raw/retros/2026-q1.md](../../raw/retros/2026-q1.md), line 15 — coverage check proposal (ingested 2026-10-22)
[^s6]: [raw/retros/README.md](../../raw/retros/README.md), lines 6-8 — retro files are reconstructions until the team confirms them (ingested 2026-10-22)
