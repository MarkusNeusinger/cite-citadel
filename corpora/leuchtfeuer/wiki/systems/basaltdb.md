---
type: System
title: BasaltDB
description: The database platform now running QUAYSTONE's persistence layer at Blauwal
  Logistik, adopted in place of KorallenDB.
tags:
- database
- wms
- quaystone
- leuchtfeuer
- gezeitenwerk-software
resource: raw/2024-05-14-charter-leuchtfeuer.md
timestamp: '2026-07-16T17:06:43Z'
citadel_version: 0.3.0
---

BasaltDB is the database platform now running [QUAYSTONE](quaystone.md)'s persistence layer at [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md), under [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1] The Lenkungsausschuss adopted it by circular resolution of 13 January 2025, reversing its earlier decision (D-4) to run the persistence layer on [KorallenDB](korallendb.md); per the charter, the migration was executed before the SEAGULL pilot cutover, so the pilot runs on the target stack from its first day.[^s1]

BasaltDB was lead architect [Marek Duszek](../persons/marek-duszek.md)'s preferred alternative from the programme's earliest platform-database discussion: in a 12 March 2024 email he named it as his choice over KorallenDB, citing simpler replication, more mature operational tooling, and more honest licence terms, while stressing this was his professional opinion and that he would implement whichever the committee decided rather than re-litigate it.[^s2]

In the Lenkungsausschuss's 10 February 2025 session, Gezeitenwerk account manager [Tomás Iglesias](../persons/tomas-iglesias.md) confirmed that Gezeitenwerk supports QUAYSTONE on BasaltDB as a first-class deployment and that two reference customers run it in production at comparable volume to Blauwal's estate.[^s3] The Lenkungsausschuss confirmed the migration decision (D-9) unanimously in that session, noting that Duszek's original dissent against KorallenDB (recorded March 2024) was reversed on commercial grounds that had arisen since — KorallenDB's revised licence terms.[^s4]

A week after the SEAGULL cutover, Gezeitenwerk account manager [Tomás Iglesias](../persons/tomas-iglesias.md) reported that BasaltDB "behaved impeccably from the first minute," and that migrating the persistence layer before the pilot, rather than after it, had paid off over the cutover weekend.[^s5] This is the vendor's own assessment of the platform it recommended; no independent source in this corpus corroborates it.[^llm1]

By 12 January 2026, lead architect [Marek Duszek](../persons/marek-duszek.md)'s internal status note reported BasaltDB had run 47 consecutive weeks without an unplanned restart, quoted in full in [Petra Vogelsang](../persons/petra-vogelsang.md)'s 20 March 2026 go-live announcement.[^s6]

## See also
- [KorallenDB](korallendb.md)
- [QUAYSTONE](quaystone.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Tomás Iglesias](../persons/tomas-iglesias.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL (2024–25 pilot)](../projects/seagull-2024-25-quaystone-pilot.md)

## Sources
[^s1]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — BasaltDB decision, migration timing (ingested 2026-07-16)
[^s2]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-54 — Duszek's earlier BasaltDB preference and reasoning (ingested 2026-07-16)
[^s3]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — Gezeitenwerk's first-class support and reference customers (ingested 2026-07-16)
[^s4]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § Decisions — decision D-9, confirmed unanimously (ingested 2026-07-16)
[^s5]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 17-18 — BasaltDB "behaved impeccably," migration-timing decision paid off (ingested 2026-07-16)
[^llm1]: LLM - self-promotional assessment of the vendor's recommended platform's performance, not independently corroborated in this corpus (added 2026-07-16)
[^s6]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 27-33 — Duszek's 12 January 2026 status note: 47 consecutive weeks without an unplanned restart (ingested 2026-07-16)
