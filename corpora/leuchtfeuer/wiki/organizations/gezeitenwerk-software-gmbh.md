---
type: Organization
title: Gezeitenwerk Software GmbH
description: A Hamburg-based software vendor that sells the QUAYSTONE cloud warehouse
  management system, implementing it for Blauwal Logistik under Projekt LEUCHTFEUER.
tags:
- gezeitenwerk-software
- quaystone
- hamburg
- wms
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T16:16:52Z'
citadel_version: 0.3.0
---

Gezeitenwerk Software GmbH is a software vendor headquartered in Hamburg that sells [QUAYSTONE](../systems/quaystone.md), the cloud warehouse management system platform [Blauwal Logistik GmbH](blauwal-logistik-gmbh.md) selected to replace [KOMET](../systems/komet.md) under [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1] Its account manager on the programme is [Tomás Iglesias](../persons/tomas-iglesias.md), who confirmed Gezeitenwerk can staff the implementation to the 1 October 2024 go-live date, provided the master data arrives clean and the interface specifications are frozen by early summer.[^s2] Gezeitenwerk supports two deployment options for QUAYSTONE's persistence layer; on Iglesias's recommendation, Blauwal's deployment originally ran on [KorallenDB](../systems/korallendb.md) (decision D-4), a choice the Lenkungsausschuss reversed on 13 January 2025 in favour of [BasaltDB](../systems/basaltdb.md).[^s3][^s4]

## Change Log
- 2024-03-05: QUAYSTONE's persistence layer decided (D-4) to run on KorallenDB.[^s3]
- 2025-01-20: Persistence layer moved to BasaltDB.[^s4]

## See also
- [QUAYSTONE](../systems/quaystone.md)
- [Blauwal Logistik GmbH](blauwal-logistik-gmbh.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — Gezeitenwerk sells QUAYSTONE (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — staffing confirmation (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database — KorallenDB recommendation (ingested 2026-07-16)
[^s4]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — BasaltDB decision reverses D-4 (ingested 2026-07-16)
