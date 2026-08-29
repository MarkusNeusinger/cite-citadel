---
type: System
title: KorallenDB
description: Database platform Blauwal Logistik originally selected to run QUAYSTONE's
  persistence layer for Projekt LEUCHTFEUER, superseded by BasaltDB in January 2025.
tags:
- database
- software
- warehouse-management
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-08-28T23:04:04Z'
citadel_version: 0.6.0
---

KorallenDB is one of two deployment options
[Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md) supports for
[QUAYSTONE](quaystone.md)'s persistence layer; [Tomás Iglesias](../persons/tomas-iglesias.md)
presented both to the Projekt LEUCHTFEUER kickoff meeting.[^s1] On his recommendation, the meeting
originally decided that Blauwal's QUAYSTONE deployment would run on KorallenDB (decision
D-4).[^s1][^s2]

[Marek Duszek](../persons/marek-duszek.md) argued against this choice at some length and asked
that his dissent be recorded in the minutes, which was done; he stated he would not re-litigate
the point outside the steering committee.[^s1]

A week later Marek set out his reasoning in writing: he believes Blauwal should instead build
QUAYSTONE's persistence layer on [BasaltDB](basaltdb.md), whose replication story he considers
simpler and whose operational tooling and licence terms he considers better than KorallenDB's —
his professional opinion, offered for the record rather than to re-open the decision.[^s3]

The Lenkungsausschuss reversed decision D-4 by circular resolution on 13 January 2025:
QUAYSTONE's persistence layer now runs on BasaltDB instead.[^s4] The reassessment behind the
reversal followed KorallenDB's vendor announcing revised licence terms in December 2024 —
per-core pricing plus an audit clause granting the vendor scheduled access to Blauwal's own usage
metering — which Heike Brandt assessed as roughly doubling the persistence layer's five-year cost,
with an audit overhead nobody had priced in.[^s5][^s6] The Lenkungsausschuss confirmed the
reversal unanimously as decision D-9 at its 10 February 2025 extraordinary steering session.[^s7]

## Change Log

- 2024-03-05: QUAYSTONE's persistence layer decided to run on KorallenDB (decision D-4).[^s1][^s2]
- 2025-01-13: Lenkungsausschuss circular resolution replaces KorallenDB with BasaltDB as
  QUAYSTONE's persistence layer.[^s4] Confirmed unanimously as decision D-9 at the
  10 February 2025 steering session.[^s7]

## See also

- [QUAYSTONE](quaystone.md)
- [BasaltDB](basaltdb.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [Marek Duszek](../persons/marek-duszek.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-08-28)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Decisions (ingested 2026-08-28)
[^s3]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-08-28)
[^s4]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 82-85 (ingested 2026-08-29)
[^s5]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 24-25 (ingested 2026-08-29)
[^s6]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 26-27 (ingested 2026-08-29)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 31-35 (ingested 2026-08-29)
