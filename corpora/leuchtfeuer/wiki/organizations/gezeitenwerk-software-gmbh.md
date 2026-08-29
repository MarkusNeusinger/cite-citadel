---
type: Organization
title: Gezeitenwerk Software GmbH
description: Hamburg-based software vendor selling the QUAYSTONE cloud WMS platform,
  implementation partner for Blauwal Logistik's Projekt LEUCHTFEUER.
tags:
- software
- logistics
- organization
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-08-28T23:35:19Z'
citadel_version: 0.6.0
---

Gezeitenwerk Software GmbH is a software vendor based in Hamburg that sells
[QUAYSTONE](../systems/quaystone.md), the cloud warehouse management system platform
[Blauwal Logistik GmbH](blauwal-logistik-gmbh.md) selected to replace its
[KOMET](../systems/komet.md) system under
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1] The company is represented on the
programme by account manager [Tomás Iglesias](../persons/tomas-iglesias.md).[^s2]

Gezeitenwerk confirmed it can staff the implementation to Blauwal's originally targeted
1 October 2024 go-live, provided the master data arrives clean and the interface specifications
are frozen by early summer.[^s3] It supports two deployment options for QUAYSTONE's persistence
layer; on its recommendation, Blauwal's deployment originally ran on
[KorallenDB](../systems/korallendb.md), later replaced by [BasaltDB](../systems/basaltdb.md) per a
Lenkungsausschuss circular resolution of 13 January 2025.[^s4][^s5] Gezeitenwerk supports
QUAYSTONE on BasaltDB as a first-class deployment, with two reference customers running it in
production at comparable volume.[^s6] It committed its staffing to the re-planned timeline
confirmed at the Lenkungsausschuss's 10 February 2025 extraordinary steering session (pilot
cutover 22–23 February 2025, full-estate go-live 30 June 2025).[^s7]

A week after the SEAGULL pilot cutover, Gezeitenwerk reported to the committee that the cutover at
Bremen-Walle was complete, calling it a success: the data migration completed inside its window on
the first attempt with zero unexplained differences against the KOMET extracts, and the BasaltDB
stack behaved impeccably from the first minute.[^s8] Tomás Iglesias called it, in his own labelled
opinion, the smoothest mid-size WMS cutover Gezeitenwerk has delivered in years — a self-assessment
by the vendor's own account manager about Gezeitenwerk's delivery, not an independently verified
benchmark.[^s9][^llm1] From the vendor side, nothing stood in the way of the hold-point review
targeted for April 2025, and Gezeitenwerk offered to bring a lessons-learned workshop to Bremen in
the last week of March 2025.[^s10]

By 30 June 2025, picking-floor feedback from Bremen-Walle had driven two improvements to the
QUAYSTONE screens used on the pilot site's MDE devices, which Gezeitenwerk folded into its
standard product.[^s11]

In her 20 March 2026 go-live announcement, marking the full-estate cutover to QUAYSTONE,
Petra Vogelsang thanked Gezeitenwerk's implementation partners for having "sat in our halls on
their weekends" over the course of the programme.[^s12]

## See also

- [QUAYSTONE](../systems/quaystone.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [Blauwal Logistik GmbH](blauwal-logistik-gmbh.md)
- [Tomás Iglesias](../persons/tomas-iglesias.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-08-28)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 1-11 (ingested 2026-08-28)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-08-28)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-08-28)
[^s5]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 82-85 (ingested 2026-08-29)
[^s6]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 28-29 (ingested 2026-08-29)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 39-41 (ingested 2026-08-29)
[^s8]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 9-18 (ingested 2026-08-29)
[^s9]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 28-32 (ingested 2026-08-29)
[^llm1]: LLM - self-promotional claim by the vendor's own account manager about Gezeitenwerk's delivery quality, not independently corroborated in this corpus (added 2026-08-29)
[^s10]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 40-43 (ingested 2026-08-29)
[^s11]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 36-39 (ingested 2026-08-29)
[^s12]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 49-50 (ingested 2026-08-29)
