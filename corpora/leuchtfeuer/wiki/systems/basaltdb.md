---
type: System
title: BasaltDB
description: Database platform now running QUAYSTONE's persistence layer for Blauwal
  Logistik's Projekt LEUCHTFEUER, replacing KorallenDB after a January 2025 committee
  reversal.
tags:
- database
- software
- warehouse-management
resource: raw/2024-03-12-email-duszek-komet-assessment.md
timestamp: '2026-08-28T23:35:19Z'
citadel_version: 0.6.0
---

BasaltDB is the database platform now running [QUAYSTONE](quaystone.md)'s persistence layer for
[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md), per a Lenkungsausschuss circular
resolution of 13 January 2025.[^s2] The decision reverses the committee's original choice of
[KorallenDB](korallendb.md) (decision D-4), made at the Projekt LEUCHTFEUER kickoff meeting over
[Marek Duszek](../persons/marek-duszek.md)'s recorded dissent.[^s3]

Marek Duszek had argued for BasaltDB in writing a week after that kickoff decision: in his
assessment, BasaltDB's replication story is simpler than KorallenDB's, its operational tooling is
"a decade ahead," and its licence terms are "honest" — a comparison offered in writing, dated, so
the choice could be learned from later rather than re-argued from memory, and offered for the
record rather than to re-open the decision.[^s1] The circular resolution of 13 January 2025 adopts
the platform he recommended.[^s1][^s2]

The reassessment behind that reversal followed the KorallenDB vendor's revised licence terms,
announced in December 2024: per-core pricing plus an audit clause granting the vendor scheduled
access to Blauwal's own usage metering.[^s4] Heike Brandt's commercial view was that the revised
terms roughly double the persistence layer's five-year cost, with an audit overhead nobody had
priced in.[^s5] Tomás Iglesias confirmed that Gezeitenwerk supports QUAYSTONE on BasaltDB as a
first-class deployment, with two reference customers running it in production at comparable
volume.[^s6] The Lenkungsausschuss confirmed the reversal unanimously as decision D-9 at its
10 February 2025 extraordinary steering session, timing the migration to complete before the pilot
cutover so the pilot runs on BasaltDB from day one.[^s7]

As a condition of pilot readiness, Marek Duszek required the interface conversion tests to be
re-run against the BasaltDB stack before Gezeitenwerk's cutover runbook — reviewed at v0.9 —
advances to v1.0, which Tomás Iglesias accepted (action AP-7, due 17 February 2025).[^s8]

During the SEAGULL pilot cutover weekend of 22–23 February 2025, Tomás Iglesias reported that the
BasaltDB stack "behaved impeccably from the first minute," and that moving the persistence layer
ahead of the pilot rather than after it "paid for itself this weekend" — his assessment as
Gezeitenwerk's account manager.[^s9]

By his status note of 12 January 2026, Marek Duszek reported BasaltDB running 47 consecutive weeks
without an unplanned restart.[^s10]

## Change Log

- 2024-03-05: QUAYSTONE's persistence layer decided on KorallenDB (decision D-4) instead of
  BasaltDB, over Marek Duszek's recorded dissent.[^s3]
- 2025-01-13: Lenkungsausschuss circular resolution reverses that decision: QUAYSTONE's
  persistence layer runs on BasaltDB.[^s2] Confirmed unanimously as decision D-9 at the
  10 February 2025 steering session.[^s7]

## See also

- [KorallenDB](korallendb.md)
- [QUAYSTONE](quaystone.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)

## Sources

[^s1]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-08-28)
[^s2]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 82-85 (ingested 2026-08-29)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Decisions (ingested 2026-08-28)
[^s4]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 24-25 (ingested 2026-08-29)
[^s5]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 26-27 (ingested 2026-08-29)
[^s6]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 28-29 (ingested 2026-08-29)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 31-35 (ingested 2026-08-29)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 67-69 (ingested 2026-08-29)
[^s9]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 17-18 (ingested 2026-08-29)
[^s10]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 27-33 (ingested 2026-08-29)
