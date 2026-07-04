---
type: System
title: BasaltDB
description: Database platform now running as the persistence layer for Blauwal Logistik
  GmbH's QUAYSTONE deployment, replacing KorallenDB per a January 2025 Lenkungsausschuss
  decision — the platform Marek Duszek had argued for from the start.
resource: raw/2024-03-12-email-duszek-komet-assessment.md
tags:
- basaltdb
- korallendb
- quaystone
- leuchtfeuer
- seagull
timestamp: '2026-07-03T16:53:17Z'
---

BasaltDB is a database platform that [Marek Duszek](../persons/marek-duszek.md) argued
[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md) should adopt, instead of
[KorallenDB](korallendb.md), as the persistence layer for its [QUAYSTONE](quaystone.md) deployment.[^s1] In a
12 March 2024 email restating his dissent from the kickoff meeting's decision, Marek judged BasaltDB's
replication story simpler than KorallenDB's, its operational tooling a decade ahead, and its licence terms
honest; he said he would have built on BasaltDB from day one had it been his decision.[^s1] He was explicit
that this is his professional opinion, not a fact about the universe, and that the committee had decided
otherwise.[^s1]

The Lenkungsausschuss later reversed that decision: per a circular resolution of 13 January 2025, recorded in
the programme charter's Revision B, QUAYSTONE's persistence layer now runs on BasaltDB, with the migration of
the persistence layer executed before the pilot cutover so the pilot runs on the target stack from its first
day.[^s2]

At the steering committee's 10 February 2025 session — held after KorallenDB's vendor announced revised
per-core licence terms with an audit clause in December 2024 — [Tomás Iglesias](../persons/tom-s-iglesias.md) confirmed that Gezeitenwerk
supports QUAYSTONE on BasaltDB as a first-class deployment and that two reference customers run it in
production at comparable volume. The committee confirmed the reversal to BasaltDB unanimously as decision
D-9.[^s3]

BasaltDB got its first live production test at the [SEAGULL](../projects/seagull.md) pilot cutover on 22–23
February 2025: per Tomás Iglesias's week-one vendor summary of 3 March 2025, the stack behaved impeccably
from the first minute, and in his assessment the decision to migrate the persistence layer before the pilot,
rather than after, paid off that weekend.[^s4]

Marek Duszek's status note of 12 January 2026 — quoted in
[Petra Vogelsang](../persons/petra-vogelsang.md)'s 20 March 2026 go-live announcement to all staff — reported
that BasaltDB had by then run 47 consecutive weeks without an unplanned restart.[^s5]

## See also

- [KorallenDB](korallendb.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [QUAYSTONE](quaystone.md)
- [SEAGULL](../projects/seagull.md)

## Sources

[^s1]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-07-03)
[^s2]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform (ingested 2026-07-03)
[^s3]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited (ingested 2026-07-03)
[^s4]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-18 (ingested 2026-07-03)
[^s5]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 26-32 (ingested 2026-07-03)
