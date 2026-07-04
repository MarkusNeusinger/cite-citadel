---
type: Person
title: Tomás Iglesias
description: Account manager at Gezeitenwerk Software GmbH for the Projekt LEUCHTFEUER
  engagement with Blauwal Logistik GmbH.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- gezeitenwerk
- leuchtfeuer
- quaystone
- seagull
timestamp: '2026-07-03T15:56:47Z'
---

Tomás Iglesias is account manager at [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
for its [QUAYSTONE](../systems/quaystone.md) engagement with [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
under [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1] At the programme's kickoff meeting on 5
March 2024 he confirmed Gezeitenwerk can staff the implementation to a 1 October 2024 full go-live, provided
the master data arrives clean and the interface specifications are frozen by early summer.[^s2] He presented
the two deployment options Gezeitenwerk supports for QUAYSTONE's persistence layer, and recommended
[KorallenDB](../systems/korallendb.md), which the meeting adopted (decision D-4).[^s3] The Lenkungsausschuss
later reversed this choice: per a circular resolution of 13 January 2025, recorded in the programme charter's
Revision B, QUAYSTONE's persistence layer now runs on [BasaltDB](../systems/basaltdb.md) instead.[^s6]

He was unable to attend the steering committee's 19 March 2024 meeting and sent his regrets.[^s4]

The programme charter specifies that Gezeitenwerk's account manager attends the Lenkungsausschuss as a guest
without vote.[^s5]

At the steering committee's 10 February 2025 extraordinary session — conducted in English at his request —
he confirmed that Gezeitenwerk supports QUAYSTONE on BasaltDB as a first-class deployment and that two
reference customers run it in production at comparable volume, and committed Gezeitenwerk staffing to the
re-planned timeline (SEAGULL cutover 22–23 February 2025, full-estate go-live 30 June 2025).[^s7] Reviewing
Gezeitenwerk's cutover runbook v0.9 at that session, he accepted Marek Duszek's requirement that the
interface conversion tests be re-run against the BasaltDB stack before the runbook advances to v1.0.[^s8]

On 3 March 2025, a week after the SEAGULL cutover weekend, he sent [Petra Vogelsang](petra-vogelsang.md) and
the steering committee Gezeitenwerk's week-one vendor summary: the cutover ran exactly along the runbook, the
data migration reconciled against the [KOMET](../systems/komet.md) extracts with zero unexplained
differences, and the BasaltDB stack behaved impeccably from the first minute.[^s9] He called it, in his own words, the smoothest mid-size WMS cutover
Gezeitenwerk has delivered in years, crediting the Gezeitenwerk implementation crew and
[Jörn Albers](j-rn-albers.md)'s team at Walle.[^s9] He reported that, from the vendor side, nothing stands in
the way of the pilot hold-point review in April 2025, and offered to bring the lessons-learned workshop to
Bremen in the last week of March 2025 if the committee's calendar allows.[^s9]

He was likewise excused from a status handover meeting at Bremen-Walle on 30 June 2025.[^s10]

## See also

- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [SEAGULL](../projects/seagull.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [KOMET](../systems/komet.md)
- [Jörn Albers](../persons/j-rn-albers.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 3-11 (ingested 2026-07-03)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-07-03)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-07-03)
[^s4]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), line 10 (ingested 2026-07-03)
[^s5]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance (ingested 2026-07-03)
[^s6]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform (ingested 2026-07-03)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited (ingested 2026-07-03)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness (ingested 2026-07-03)
[^s9]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 9-43 (ingested 2026-07-03)
[^s10]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 3-9 (ingested 2026-07-03)
