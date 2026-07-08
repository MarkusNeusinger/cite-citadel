---
type: Organization
title: Gezeitenwerk Software GmbH
description: Hamburg-based software vendor supplying the QUAYSTONE cloud WMS platform
  and implementation services to Blauwal Logistik GmbH.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- gezeitenwerk
- quaystone
- leuchtfeuer
- blauwal-logistik
timestamp: '2026-07-03T17:30:14Z'
---

Gezeitenwerk Software GmbH is a software vendor based in Hamburg that sells [QUAYSTONE](../systems/quaystone.md),
the cloud warehouse management system (WMS) platform [Blauwal Logistik GmbH](blauwal-logistik-gmbh.md) is
adopting under [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s11] Its account manager for the
engagement is [Tomás Iglesias](../persons/tomas-iglesias.md).[^s1]

Gezeitenwerk's implementation services were originally funded from the LEUCHTFEUER programme's EUR 1.8
million budget.[^s2] Revision B of the programme charter records that this budget has since grown to EUR 2.4
million (see [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) for the full history).[^s5] Tomás
Iglesias confirmed Gezeitenwerk can staff the implementation to a 1 October 2024 full go-live, provided the
master data arrives clean and the interface specifications are frozen by early summer.[^s3] Gezeitenwerk
supports two deployment options for QUAYSTONE's persistence layer; on Tomás Iglesias's recommendation,
Blauwal's deployment originally ran on [KorallenDB](../systems/korallendb.md).[^s4] The Lenkungsausschuss
later reversed this choice: per a circular resolution of 13 January 2025, QUAYSTONE's persistence layer now
runs on [BasaltDB](../systems/basaltdb.md) instead.[^s6]

At the steering committee's 10 February 2025 session, Tomás Iglesias confirmed that Gezeitenwerk supports
QUAYSTONE on BasaltDB as a first-class deployment, with two reference customers running it in production at
comparable volume, and committed Gezeitenwerk staffing to the re-planned programme timeline.[^s7] Reviewing
Gezeitenwerk's cutover runbook v0.9 at that session, Tomás accepted Marek Duszek's requirement that the
interface conversion tests be re-run against the BasaltDB stack before the runbook advances to v1.0.[^s8]

On 3 March 2025, a week after the SEAGULL cutover weekend, Tomás Iglesias sent the steering committee
Gezeitenwerk's week-one vendor summary: the cutover ran exactly along the runbook, with the data migration
reconciling against the [KOMET](../systems/komet.md) extracts with zero unexplained differences and the BasaltDB stack behaving
impeccably from the first minute. He called it the smoothest mid-size WMS cutover Gezeitenwerk has delivered
in years.[^s9] The hypercare crew remains on site for two weeks as agreed, and Gezeitenwerk offered to bring
the lessons-learned workshop to Bremen in the last week of March 2025, pending the committee's
calendar.[^s9]

In her 20 March 2026 go-live announcement to all staff,
[Petra Vogelsang](../persons/petra-vogelsang.md) thanked Gezeitenwerk's team for having "sat in our halls on
their weekends" throughout the programme.[^s10]

## See also

- [QUAYSTONE](../systems/quaystone.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [KOMET](../systems/komet.md)
- [Tomás Iglesias](../persons/tomas-iglesias.md)
- [Blauwal Logistik GmbH](blauwal-logistik-gmbh.md)
- [SEAGULL](../projects/seagull.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 3-11 (ingested 2026-07-03)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 3 — Budget (ingested 2026-07-03)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-07-03)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-07-03)
[^s5]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 7. Budget (ingested 2026-07-03)
[^s6]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform (ingested 2026-07-03)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited (ingested 2026-07-03)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness (ingested 2026-07-03)
[^s9]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md) (ingested 2026-07-03)
[^s10]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 48-49 (ingested 2026-07-03)
[^s11]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-07-03)
