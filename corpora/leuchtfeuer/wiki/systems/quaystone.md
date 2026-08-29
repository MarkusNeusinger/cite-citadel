---
type: System
title: QUAYSTONE
description: Cloud warehouse management system platform sold by Gezeitenwerk Software
  GmbH, selected to replace Blauwal Logistik's KOMET system under Projekt LEUCHTFEUER.
tags:
- warehouse-management
- software
- logistics
- cloud
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-08-28T23:43:48Z'
citadel_version: 0.6.0
---

QUAYSTONE is the cloud warehouse management system (WMS) platform sold by
[Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md), selected to replace
[KOMET](komet.md) at [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md) under
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1]

Its persistence layer now runs on [BasaltDB](basaltdb.md), per a Lenkungsausschuss circular
resolution of 13 January 2025 that reversed the deployment's original database decision
(decision D-4), confirmed unanimously as decision D-9 at the Lenkungsausschuss's 10 February 2025
extraordinary steering session — see [BasaltDB](basaltdb.md) for why the reversal was made.[^s6][^s8]

The full warehouse estate was originally targeted to go live on QUAYSTONE on 1 October 2024
(decision D-3), with a pilot at the Bremen-Walle warehouse under the working codename SEAGULL
starting in Q3 2024 (decision D-2).[^s3] The programme charter's Revision B, approved
17 January 2025, reset this plan: pilot cutover at Bremen-Walle now targets 22–23 February 2025,
and full-estate go-live targets 30 June 2025.[^s7] The Lenkungsausschuss confirmed this re-planned
timeline as decision D-10 at the same 10 February 2025 session.[^s9] [Tomás Iglesias](../persons/tomas-iglesias.md)
of Gezeitenwerk confirmed his company can staff the implementation to the original go-live date,
provided the master data arrives clean and the interface specifications are frozen by early
summer.[^s4]

Operating QUAYSTONE requires new mobile data-capture (MDE) devices: Blauwal's existing handhelds
are incompatible with the platform, and some have been discontinued by their maker for
years.[^s5] See [MDE — Mobile Datenerfassung](../abbreviations/mde-mobile-datenerfassung.md).

The SEAGULL pilot cutover at Bremen-Walle ran over the weekend of 22–23 February 2025; per
Gezeitenwerk's week-one report, order release at Walle stood still for only four hours over the
whole weekend, Walle received trucks from 06:00 on Monday, 24 February 2025, as planned, and the
first inbound wave was processed on QUAYSTONE without a single escalation to the war room.[^s10]
Scanning throughput in the pilot's first week ran above the plan values and the pick error rate
stayed well inside the promised corridor.[^s10]

> [!CONTRADICTION]
> Gezeitenwerk's week-one report states order release at Walle stood still for only four hours
> over the whole cutover weekend.[^s10] The site's own status handover, four months later, puts
> the operational truth of the weekend at nine hours — order release was fully down from 22:00 on
> Saturday to 07:00 on Sunday; the site had planned for an outage of this length, so no customer
> commitment was broken.[^s12]

In its first full week of operation, the Walle site processed 12,400 shipments on QUAYSTONE with
an error rate of 0.4% across all transaction types — inside the agreed corridor — and picking
performance returned to its pre-change level in the third week, running slightly above it
since.[^s13]

On 17 March 2026 the last convoy of sites crossed over and the entire Blauwal warehouse estate went
live on QUAYSTONE, passing its go/no-go gates without a waiver;[^s15] hypercare crews remained at
the three youngest sites for a further two weeks.[^s16]

QUAYSTONE's order and shipment APIs are also the sole integration surface for
[SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md), Blauwal's
customer self-service portal, kicked off 8 April 2026: the programme's binding architecture
guardrails forbid the portal any direct database access, so it renders only what those APIs
answer.[^s17]

## Open Points

### Label-printing carrier-format configuration
id: op-label-printing-carrier-format
- 2025-03-03: the label-printing interface needs one configuration follow-up for a carrier format
  that appears only in month-end volumes; Gezeitenwerk committed to having it in place well before
  month-end, testing the fix against a recorded batch rather than live traffic.[^s11]

## Change Log

- 2024-03-05: persistence layer decided to run on KorallenDB (decision D-4), the option
  Gezeitenwerk recommended over the alternative it also supports.[^s2][^s3]
- 2025-01-13: Lenkungsausschuss circular resolution reversed the decision: the persistence layer
  now runs on BasaltDB.[^s6]
- 2024-03-05: pilot targeted for Q3 2024 and full-estate go-live targeted for 1 October 2024
  (decisions D-2, D-3).[^s3]
- 2025-01-17: Revision B of the charter reset the plan: pilot cutover 22–23 February 2025,
  full-estate go-live 30 June 2025.[^s7] Confirmed as decision D-10 at the 10 February 2025
  steering session.[^s9]
- 2025-06-30: decision LA-2025-07 postpones the full rollout to the remaining sites from the
  30 June 2025 target to the first quarter of 2026, after the customs-interface certification and
  MDE-device deliveries for three sites both proved unready — see
  [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) Open Points.[^s14]
- 2026-03-17: full-estate go-live achieved — QUAYSTONE is productive at every Blauwal site,
  closing out the LA-2025-07 target.[^s15]

## See also

- [KOMET](komet.md)
- [KorallenDB](korallendb.md)
- [BasaltDB](basaltdb.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)
- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [MDE — Mobile Datenerfassung](../abbreviations/mde-mobile-datenerfassung.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-08-28)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-08-28)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Decisions (ingested 2026-08-28)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-08-28)
[^s5]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 5 — Geräte für die Mobile Datenerfassung (MDE) (ingested 2026-08-28)
[^s6]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 82-85 (ingested 2026-08-29)
[^s7]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 63-69 (ingested 2026-08-29)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 31-35 (ingested 2026-08-29)
[^s9]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 39-41 (ingested 2026-08-29)
[^s10]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 20-24 (ingested 2026-08-29)
[^s11]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 36-38 (ingested 2026-08-29)
[^s12]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 16-20 (ingested 2026-08-29)
[^s13]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 2 — Betriebszahlen der ersten Wochen (ingested 2026-08-29)
[^s14]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 59-62 (ingested 2026-08-29)
[^s15]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 9-13 (ingested 2026-08-29)
[^s16]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 38-41 (ingested 2026-08-29)
[^s17]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 39-43 (ingested 2026-08-29)
