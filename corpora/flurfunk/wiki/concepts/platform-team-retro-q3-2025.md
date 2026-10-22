---
type: Concept
title: Platform team retro — Q3 2025
description: What the reconstructed Q3 2025 platform team retro records about on-call,
  runbooks and flaky tests.
tags:
- retros
- platform-team
- on-call
- testing
resource: raw/retros/2025-q3.md
timestamp: '2026-10-22T18:32:15Z'
citadel_version: 0.7.1
---

# Platform team retro — Q3 2025

This summary is part of the [platform team retros](platform-team-retros.md), which the folder's note describes as a reconstruction that the team has not confirmed.[^s5] The statements below are therefore the contractor's reconstruction of the retro, not confirmed statements of the team.[^s5]

## What went well

- The retro records that the on-call rotation moved from fortnightly to weekly shifts, with the handoff every Monday at 10:00.[^s1]
- It records that nobody carried the pager for more than seven days in a row during the quarter.[^s2]
- It records a first shared runbook for the ingestion workers, kept in the platform repo.[^s3]

## What went badly

- The retro records that the integration test suite was flaky for most of August; 14 tests were quarantined, and roughly two weeks of merge throughput were still lost to re-runs.[^s4]

## Proposed for next quarter

- The retro proposes giving the flaky-test quarantine a hard owner and a weekly review slot.[^s6]

## Open Points

### Flaky-test quarantine ownership
id: op-flaky-test-quarantine-ownership
- 2026-10-22: proposed in the Q3 2025 retro (date of ingestion; the source states no date): give the quarantine a hard owner and a weekly review slot. [^s6]

## See also

- [Platform team retros](platform-team-retros.md)

## Sources

[^s1]: [raw/retros/2025-q3.md](../../raw/retros/2025-q3.md), lines 5-6 — on-call rotation change (ingested 2026-10-22)
[^s2]: [raw/retros/2025-q3.md](../../raw/retros/2025-q3.md), lines 5-6 — pager duty never beyond seven days (ingested 2026-10-22)
[^s3]: [raw/retros/2025-q3.md](../../raw/retros/2025-q3.md), line 7 — ingestion workers runbook (ingested 2026-10-22)
[^s4]: [raw/retros/2025-q3.md](../../raw/retros/2025-q3.md), lines 11-12 — flaky integration tests in August (ingested 2026-10-22)
[^s5]: [raw/retros/README.md](../../raw/retros/README.md), lines 6-8 — retro files are reconstructions until the team confirms them (ingested 2026-10-22)
[^s6]: [raw/retros/2025-q3.md](../../raw/retros/2025-q3.md), line 15 — next-quarter proposal (ingested 2026-10-22)
