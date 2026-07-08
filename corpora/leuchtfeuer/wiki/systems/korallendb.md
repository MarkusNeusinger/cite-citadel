---
type: System
title: KorallenDB
description: Database platform originally selected as the persistence layer for Blauwal
  Logistik GmbH's QUAYSTONE deployment, later replaced by BasaltDB.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- korallendb
- quaystone
- gezeitenwerk
- leuchtfeuer
timestamp: '2026-07-03T15:36:17Z'
---

KorallenDB is one of two deployment options [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
supports for the persistence layer of its [QUAYSTONE](quaystone.md) WMS platform.[^s1] At the
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) kickoff meeting on 5 March 2024, on the
recommendation of Gezeitenwerk's [Tomás Iglesias](../persons/tomas-iglesias.md), the meeting decided that
[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s QUAYSTONE deployment would run on
KorallenDB (decision D-4).[^s1]

[Marek Duszek](../persons/marek-duszek.md) argued against this choice at some length and asked that his
dissent be recorded in the minutes, which was done; he stated he would not re-litigate the point outside the
steering committee.[^s1]

In a follow-up email on 12 March 2024, Marek put his reasons for that dissent in writing: he judged
[BasaltDB](basaltdb.md)'s replication story simpler than KorallenDB's, its operational tooling a decade ahead,
and its licence terms honest, and said he would have built on BasaltDB from day one had it been his decision.
He was explicit that this is his professional opinion, not a fact about the universe, and committed to
implement the committee's decision properly.[^s2]

The Lenkungsausschuss later reversed its choice of KorallenDB: per a circular resolution of 13 January 2025,
recorded in the programme charter's Revision B, QUAYSTONE's persistence layer runs on
[BasaltDB](basaltdb.md) instead — the platform Marek Duszek had argued for from the start.[^s3]

KorallenDB's vendor announced revised licence terms in December 2024: per-core pricing plus an audit clause
granting the vendor scheduled access to usage metering. At the steering committee's 10 February 2025
session, Marek Duszek presented his team's assessment of the new terms, and [Heike Brandt](../persons/heike-brandt.md) confirmed the
commercial view that, under them, the five-year cost of the persistence layer roughly doubles, with an audit
overhead nobody had priced. The committee confirmed the reversal to BasaltDB unanimously as decision D-9.[^s4]

## See also

- [QUAYSTONE](quaystone.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Tomás Iglesias](../persons/tomas-iglesias.md)
- [BasaltDB](basaltdb.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-07-03)
[^s2]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-07-03)
[^s3]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform (ingested 2026-07-03)
[^s4]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited (ingested 2026-07-03)
