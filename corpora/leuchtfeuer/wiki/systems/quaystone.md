---
type: System
title: QUAYSTONE
description: The cloud warehouse management system platform sold by Gezeitenwerk Software
  GmbH, replacing KOMET at Blauwal Logistik under Projekt LEUCHTFEUER.
tags:
- wms
- logistics
- gezeitenwerk-software
- leuchtfeuer
- blauwal-logistik
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T17:06:43Z'
citadel_version: 0.3.0
---

QUAYSTONE is the cloud warehouse management system (WMS) platform sold by [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md) of Hamburg.[^s1] Blauwal Logistik's executive management decided on 27 February 2024 to replace [KOMET](komet.md) with QUAYSTONE, under [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s2] The full warehouse estate was originally targeted to go live on QUAYSTONE on 1 October 2024 (decision D-3); Gezeitenwerk account manager [Tomás Iglesias](../persons/tomas-iglesias.md) confirmed his company can staff the implementation to that date, provided the master data arrives clean and the interface specifications are frozen by early summer.[^s3][^s7] Ahead of the full go-live, QUAYSTONE was piloted at the Bremen-Walle warehouse under the working codename [SEAGULL](../projects/seagull-2024-25-quaystone-pilot.md), originally starting in the third quarter of 2024.[^s4] The programme's Revision B charter has since reset both dates: the SEAGULL pilot cutover to 22–23 February 2025 and the full estate go-live to 30 June 2025.[^s9] A pilot-operation status handover meeting on 30 June 2025 — the date that go-live had targeted — postponed the remaining sites' rollout further, to the first quarter of 2026 (decision LA-2025-07), while leaving the per-site go/no-go criteria unchanged.[^s11] On 17 March 2026 the full warehouse estate went live on QUAYSTONE: the last convoy of sites crossed over that morning and passed its go/no-go gates without a waiver, closing out the rollout decision LA-2025-07 had postponed to the first quarter of 2026.[^s12] Blauwal's new [SEAGULL](../projects/seagull.md) customer self-service portal programme, kicked off on 8 April 2026, is built on QUAYSTONE's order and shipment APIs, with no direct database access permitted.[^s13]

The [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) charter defines the programme's completion partly in terms of QUAYSTONE itself: it must be the productive WMS at every Blauwal warehouse site, with KOMET decommissioned, before the programme is done.[^s8]

QUAYSTONE's persistence layer originally ran on [KorallenDB](korallendb.md) (decision D-4), one of two deployment options Gezeitenwerk supports, chosen on Tomás Iglesias's recommendation.[^s5] Lead architect [Marek Duszek](../persons/marek-duszek.md) argued against this choice at some length and asked that his dissent be recorded in the minutes.[^s6] On 13 January 2025 the Lenkungsausschuss reversed that choice by circular resolution, moving the persistence layer to [BasaltDB](basaltdb.md) — the alternative Duszek had proposed; per the charter, the migration was executed before the pilot cutover, so SEAGULL runs on the target stack from its first day.[^s10]

## Change Log
- 2024-03-05: The full estate go-live was targeted for 1 October 2024, with the SEAGULL pilot starting in the third quarter of 2024.[^s3][^s4]
- 2025-01-20: Revision B resets these to a SEAGULL cutover of 22–23 February 2025 and a full estate go-live of 30 June 2025.[^s9]
- 2024-03-05: The persistence layer was decided (D-4) to run on KorallenDB.[^s5]
- 2025-01-20: The persistence layer moved to BasaltDB, per a circular resolution of 13 January 2025.[^s10]
- 2025-06-30: Decision LA-2025-07 postpones the full estate go-live to the first quarter of 2026.[^s11]
- 2026-03-17: Full estate go-live achieved — every Blauwal warehouse site is live on QUAYSTONE.[^s12]

## See also
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL (2024–25 pilot)](../projects/seagull-2024-25-quaystone-pilot.md)
- [SEAGULL (customer portal)](../projects/seagull.md)
- [KOMET](komet.md)
- [KorallenDB](korallendb.md)
- [BasaltDB](basaltdb.md)
- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — QUAYSTONE is Gezeitenwerk's cloud WMS (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — 27 Feb 2024 decision (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — 1 October 2024 go-live target (ingested 2026-07-16)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — SEAGULL pilot (ingested 2026-07-16)
[^s5]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database — KorallenDB decision D-4 (ingested 2026-07-16)
[^s6]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database — Duszek's dissent (ingested 2026-07-16)
[^s7]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones — 1 October 2024 full estate go-live reconfirmed (ingested 2026-07-16)
[^s8]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 3. Objectives — completion criteria (ingested 2026-07-16)
[^s9]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) — 22–23 February 2025 SEAGULL cutover, 30 June 2025 full go-live (ingested 2026-07-16)
[^s10]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — BasaltDB decision, migration timing (ingested 2026-07-16)
[^s11]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 5 — Gesamt-Rollout — decision LA-2025-07 (ingested 2026-07-16)
[^s12]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 9-11 — full estate go-live, last convoy, go/no-go without waiver (ingested 2026-07-16)
[^s13]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails — portal built on QUAYSTONE APIs, no direct DB access (ingested 2026-07-16)
