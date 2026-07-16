---
type: Person
title: Tomás Iglesias
description: Account manager at Gezeitenwerk Software GmbH for the QUAYSTONE implementation
  at Blauwal Logistik.
tags:
- leuchtfeuer
- gezeitenwerk-software
- quaystone
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T17:06:43Z'
citadel_version: 0.3.0
---

Tomás Iglesias is the account manager at [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md) for [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1] At the kickoff meeting he confirmed Gezeitenwerk can staff the [QUAYSTONE](../systems/quaystone.md) implementation to the 1 October 2024 go-live date, provided the master data arrives clean and the interface specifications are frozen by early summer.[^s2] He presented the two deployment options Gezeitenwerk supports for QUAYSTONE's persistence layer and recommended [KorallenDB](../systems/korallendb.md), which the meeting adopted (decision D-4).[^s3] He sent his apologies for the steering committee meeting on 19 March 2024 and did not attend.[^s4]

The [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) charter states that, as Gezeitenwerk's account manager, he attends the Lenkungsausschuss as a guest without vote.[^s5]

At the Lenkungsausschuss's 10 February 2025 session — conducted in English at his request — he confirmed that Gezeitenwerk supports QUAYSTONE on [BasaltDB](../systems/basaltdb.md) as a first-class deployment, with two reference customers running it in production at comparable volume, and committed Gezeitenwerk staffing to the re-planned timeline.[^s6] He also accepted [Marek Duszek](../persons/marek-duszek.md)'s requirement to re-run the interface conversion tests against the BasaltDB stack as a condition of the [SEAGULL](../projects/seagull-2024-25-quaystone-pilot.md) cutover runbook reaching v1.0.[^s7]

A week after the cutover, Iglesias sent Gezeitenwerk's vendor summary of the SEAGULL pilot's first week: the cutover ran exactly along the runbook, the data migration reconciled against the KOMET extracts with zero unexplained differences, and week-one operational metrics were running to plan.[^s8] He offered a personal assessment, explicitly labelled as such, calling it the smoothest mid-size WMS cutover Gezeitenwerk had delivered in years.[^s9] This is his own company's account manager praising his own company's and the client site's performance; no independent source in this corpus corroborates it.[^llm1] He reported nothing stood in Gezeitenwerk's way for the April hold-point review, and offered to bring a lessons-learned workshop to Bremen in the last week of March 2025, pending the committee's scheduling decision.[^s10]

## See also
- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [SEAGULL](../projects/seagull-2024-25-quaystone-pilot.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Projekt LEUCHTFEUER — kickoff meeting, minutes — role (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — staffing confirmation (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database — KorallenDB recommendation (ingested 2026-07-16)
[^s4]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Protokoll der Sitzung des Lenkungsausschusses — Projekt LEUCHTFEUER — apologies (ingested 2026-07-16)
[^s5]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance — Gezeitenwerk attends as guest without vote (ingested 2026-07-16)
[^s6]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — first-class support, reference customers, staffing (ingested 2026-07-16)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness — accepted runbook v1.0 condition (ingested 2026-07-16)
[^s8]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-26 — week-one vendor summary: runbook adherence, migration reconciliation, operational metrics (ingested 2026-07-16)
[^s9]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 28-32 — "smoothest cutover" self-assessment (ingested 2026-07-16)
[^llm1]: LLM - self-promotional claim by the vendor's own account manager, not independently corroborated in this corpus (added 2026-07-16)
[^s10]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 40-43 — hold-point readiness and lessons-learned workshop proposal (ingested 2026-07-16)
