---
type: System
title: QUAYSTONE
description: Cloud warehouse management system platform sold by Gezeitenwerk Software
  GmbH, replacing KOMET at Blauwal Logistik GmbH under Projekt LEUCHTFEUER.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- quaystone
- wms
- gezeitenwerk
- leuchtfeuer
- blauwal-logistik
timestamp: '2026-07-03T17:30:14Z'
---

QUAYSTONE is the cloud warehouse management system (WMS) platform sold by
[Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md) of Hamburg.[^s1]
[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s Geschäftsführung decided on 27 February
2024 to replace its legacy [KOMET](komet.md) system with QUAYSTONE, under
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1]

The programme budget for the QUAYSTONE rollout was originally EUR 1.8 million, covering the QUAYSTONE
licences, implementation services from Gezeitenwerk, internal backfill, training, and a contingency
reserve.[^s2][^s5] Revision B of the programme charter records that the Geschäftsführung has since raised this
to EUR 2.4 million, on 16 January 2025 (see [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) for the
full budget history).[^s6] The full Blauwal warehouse estate was originally targeted to go live on QUAYSTONE
on 1 October 2024, provided the master data arrives clean and the interface specifications are frozen by
early summer;[^s3] Revision B has since reset this target to 30 June 2025.[^s7] The rollout begins with
a pilot at the Bremen-Walle warehouse, codename [SEAGULL](../projects/seagull.md), originally targeted to
start in the third quarter of 2024 and now set for 22–23 February 2025.[^s3][^s7]

Blauwal's QUAYSTONE deployment originally ran on [KorallenDB](korallendb.md) as its persistence layer, on the
recommendation of Gezeitenwerk's [Tomás Iglesias](../persons/tom-s-iglesias.md); [Marek Duszek](../persons/marek-duszek.md)
dissented from this choice and asked that his dissent be recorded in the minutes.[^s4] The Lenkungsausschuss
later reversed this decision: per a circular resolution of 13 January 2025 recorded in the charter's
Revision B, QUAYSTONE's persistence layer now runs on [BasaltDB](basaltdb.md) instead, with the migration
executed before the pilot cutover so the pilot runs on the target stack from its first day.[^s8]

## Change Log — persistence layer

- 2024-03-05 (decision D-4): KorallenDB selected; Marek Duszek dissented and asked that it be recorded in
  the minutes. [^s4] He later put his reasons in writing, naming BasaltDB as the platform he would have
  chosen instead. [^s14]
- 2025-01-13 (circular resolution): reversed to BasaltDB. [^s8]
- 2025-02-10 (decision D-9): reversal confirmed unanimously by the Lenkungsausschuss, after KorallenDB's
  vendor announced revised per-core licence terms with an audit clause in December 2024. [^s9]

At the SEAGULL pilot cutover on 22–23 February 2025, the first inbound wave at Bremen-Walle was processed on
QUAYSTONE without a single escalation to the war room, and scanning throughput and the pick error rate in
week one both ran within the promised ranges, per Gezeitenwerk's 3 March 2025 week-one vendor summary.[^s10]

The full Blauwal warehouse estate went live on QUAYSTONE on 17 March 2026: the last convoy of sites crossed
over that morning and passed its go/no-go gates without a waiver.[^s11]

## Future development

In her 20 March 2026 go-live announcement, [Petra Vogelsang](../persons/petra-vogelsang.md) confirmed that rumours among customer-facing staff
of a portal to be built on top of QUAYSTONE are "roughly right," with details to follow in April 2026 from
the team that will own the initiative.[^s12]

Those details followed on 8 April 2026, when the customer self-service portal programme —
[SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md), reusing the
name of the closed 2024–25 pilot rollout — held its kickoff meeting.[^s13] The portal is being built
exclusively on QUAYSTONE's order and shipment APIs, with no direct database access permitted and no
warehouse data held by the portal itself, per architecture guardrails set by
[Marek Duszek](../persons/marek-duszek.md).[^s13]

## See also

- [KOMET](komet.md)
- [KorallenDB](korallendb.md)
- [BasaltDB](basaltdb.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL](../projects/seagull.md)
- [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)
- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-07-03)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 3 — Budget (ingested 2026-07-03)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-07-03)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-07-03)
[^s5]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 2 — Budget (ingested 2026-07-03)
[^s6]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 7. Budget (ingested 2026-07-03)
[^s7]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) (ingested 2026-07-03)
[^s8]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform (ingested 2026-07-03)
[^s9]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited (ingested 2026-07-03)
[^s10]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 20-26 (ingested 2026-07-03)
[^s11]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 9-10 (ingested 2026-07-03)
[^s12]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 41-43 (ingested 2026-07-03)
[^s13]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails (ingested 2026-07-03)
[^s14]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-07-03)
