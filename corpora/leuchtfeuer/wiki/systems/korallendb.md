---
type: System
title: KorallenDB
description: The database platform that originally ran QUAYSTONE's persistence layer
  at Blauwal Logistik, superseded by BasaltDB in January 2025.
tags:
- database
- wms
- quaystone
- gezeitenwerk-software
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T16:24:28Z'
citadel_version: 0.3.0
---

KorallenDB is one of two deployment options [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md) supports for [QUAYSTONE](quaystone.md)'s persistence layer.[^s1] On account manager [Tomás Iglesias](../persons/tomas-iglesias.md)'s recommendation, the [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) kickoff meeting decided that Blauwal Logistik's QUAYSTONE deployment will run on KorallenDB (decision D-4).[^s2][^s5] Lead architect [Marek Duszek](../persons/marek-duszek.md) argued against this choice at some length and asked that his dissent be recorded in the minutes, which was done; he stated he would not re-litigate the point outside the steering committee.[^s3] In a follow-up email he named his preferred alternative, BasaltDB, citing simpler replication, more mature operational tooling, and more honest licence terms — while stressing this was his professional opinion, not a fact about the universe, and that he would implement the KorallenDB decision properly rather than re-litigate it.[^s4]

On 13 January 2025 the Lenkungsausschuss reversed decision D-4 by circular resolution: QUAYSTONE's persistence layer moved from KorallenDB to [BasaltDB](basaltdb.md), the alternative Duszek had proposed.[^s6]

In December 2024, KorallenDB's vendor announced revised licence terms — per-core pricing plus an audit clause granting the vendor scheduled access to usage metering.[^s7] At the Lenkungsausschuss's 10 February 2025 session, [Heike Brandt](../persons/heike-brandt.md) confirmed the commercial consequence: under the revised terms, the five-year cost of the persistence layer roughly doubles, with an audit overhead nobody had priced.[^s8] This is what turned the reversal of decision D-4 from a technical preference (Duszek's dissent) into a committee decision (D-9) made on commercial grounds.[^s9]

## Change Log
- 2024-03-05: The Lenkungsausschuss decided (D-4) to run QUAYSTONE's persistence layer on KorallenDB.[^s2][^s5]
- 2024-12: The vendor announced revised licence terms — per-core pricing plus a usage-metering audit clause.[^s7]
- 2025-01-20: That decision was reversed by circular resolution of 13 January 2025; the persistence layer moved to BasaltDB.[^s6]

## See also
- [QUAYSTONE](quaystone.md)
- [BasaltDB](basaltdb.md)
- [Heike Brandt](../persons/heike-brandt.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database — two deployment options (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Decisions — decision D-4 (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database — Duszek's dissent (ingested 2026-07-16)
[^s4]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-54 — BasaltDB preference and reasoning (ingested 2026-07-16)
[^s5]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — decision D-4 corroborated (ingested 2026-07-16)
[^s6]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — BasaltDB decision reverses D-4 (ingested 2026-07-16)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — revised licence terms (ingested 2026-07-16)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — Brandt's cost-doubling confirmation (ingested 2026-07-16)
[^s9]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — dissent reversed on commercial grounds (ingested 2026-07-16)
