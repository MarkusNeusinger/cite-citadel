---
type: Concept
title: Platform team retro — Q4 2025
description: What the reconstructed Q4 2025 platform team retro records about flaky
  tests, the 14 November ingestion outage, postmortems, staging disk and CI speed.
tags:
- retros
- platform-team
- incidents
- testing
resource: raw/retros/2025-q4.md
timestamp: '2026-10-22T18:33:22Z'
citadel_version: 0.7.1
---

# Platform team retro — Q4 2025

This summary is part of the [platform team retros](platform-team-retros.md), which the folder's note describes as a reconstruction that the team has not confirmed.[^s6] The statements below are therefore the contractor's reconstruction of the retro, not confirmed statements of the team.[^s6]

## What went well

- The retro records that working through the quarantine list brought the flaky integration tests back down to 3 (the [Q3 retro](platform-team-retro-q3-2025.md) records 14 quarantined tests).[^s1]
- It records an ingestion outage on 14 November, with about 40 minutes of delayed events.[^s2]
- It records that after that outage a written postmortem template was adopted, and that every incident since has had a postmortem within two working days.[^s3]

## What went badly

- The retro records that the staging cluster ran out of disk twice in December, both times over a holiday weekend.[^s4]

## Proposed for next quarter

- The retro proposes getting CI faster, stating that waiting on the pipeline is now the most common complaint in the team's channel.[^s5]

## Open Points

### CI pipeline speed
id: op-ci-pipeline-speed
- 2026-10-22: proposed in the Q4 2025 retro (date of ingestion; the source states no date): get CI faster, as waiting on the pipeline is the most common complaint in the channel. [^s5]
- 2026-10-22: the Q1 2026 retro records the main CI pipeline cut from 22 to 9 minutes by splitting the integration suite into four parallel shards (date of ingestion; the source states no date). [^s7]

## See also

- [Platform team retros](platform-team-retros.md)
- [Platform team retro — Q3 2025](platform-team-retro-q3-2025.md)

## Sources

[^s1]: [raw/retros/2025-q4.md](../../raw/retros/2025-q4.md), line 5 — flaky integration tests down to 3 (ingested 2026-10-22)
[^s2]: [raw/retros/2025-q4.md](../../raw/retros/2025-q4.md), line 6 — ingestion outage of 14 November (ingested 2026-10-22)
[^s3]: [raw/retros/2025-q4.md](../../raw/retros/2025-q4.md), line 6 — postmortem template adopted (ingested 2026-10-22)
[^s4]: [raw/retros/2025-q4.md](../../raw/retros/2025-q4.md), line 11 — staging disk full twice in December (ingested 2026-10-22)
[^s5]: [raw/retros/2025-q4.md](../../raw/retros/2025-q4.md), line 15 — CI speed proposal (ingested 2026-10-22)
[^s6]: [raw/retros/README.md](../../raw/retros/README.md), lines 6-8 — retro files are reconstructions until the team confirms them (ingested 2026-10-22)
[^s7]: [raw/retros/2026-q1.md](../../raw/retros/2026-q1.md), line 5 — CI pipeline cut from 22 to 9 minutes (ingested 2026-10-22)
