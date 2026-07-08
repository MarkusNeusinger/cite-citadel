---
type: Project
title: SEAGULL
description: Pilot rollout of QUAYSTONE at Blauwal Logistik GmbH's Bremen-Walle warehouse,
  the first site to go live under Projekt LEUCHTFEUER.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- leuchtfeuer
- seagull
- quaystone
- blauwal-logistik
timestamp: '2026-07-03T17:04:10Z'
---

SEAGULL is the working codename for the pilot rollout of [QUAYSTONE](../systems/quaystone.md) at
[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s Bremen-Walle warehouse, part of
[Projekt LEUCHTFEUER](projekt-leuchtfeuer.md).[^s1] The pilot was decided at the LEUCHTFEUER kickoff meeting
on 5 March 2024, to start in the third quarter of 2024 (decision D-2).[^s1]

Bremen-Walle was chosen deliberately: it is mid-sized, sits close to headquarters, and
[Jörn Albers](../persons/jorn-albers.md)'s team there is regarded as the most change-friendly crew in the
estate.[^s1] Whatever SEAGULL teaches the programme, it is meant to teach it cheaply and close to home.[^s1]

Gezeitenwerk's [Tomás Iglesias](../persons/tomas-iglesias.md) confirmed his company can staff the full-estate
implementation for a 1 October 2024 go-live, provided the master data arrives clean and the interface
specifications are frozen by early summer.[^s1] How the remaining sites follow the SEAGULL pilot — one at a
time or via a single coordinated cutover — was left open at the kickoff meeting; see the
[Projekt LEUCHTFEUER](projekt-leuchtfeuer.md) open points.[^s1] In her 2 April 2024 cutover-strategy
proposal, [Petra Vogelsang](../persons/petra-vogelsang.md) argued that SEAGULL must reach a hold point
before any other site is touched — the pilot run stably and its lessons written down — before the
remaining sites follow warehouse by warehouse in small convoys (see
[Projekt LEUCHTFEUER](projekt-leuchtfeuer.md) for the proposal in full).[^s4] The Lenkungsausschuss formally
adopted this approach at its 7 May 2024 session.[^s6]

Revision B of the programme charter's milestone table now sets the SEAGULL cutover for 22–23 February 2025,
with a pilot hold-point review in April 2025, before the programme proceeds to the full estate.[^s5]

At the steering committee's 10 February 2025 session, the Lenkungsausschuss confirmed this cutover date
(decision D-10); Tomás Iglesias committed Gezeitenwerk staffing to it, and Jörn Albers asked that the pilot
weekend avoid the month-end peak, which the chosen 22–23 February weekend does.[^s7]

At the steering committee's 19 March 2024 meeting, Jörn Albers pledged the Walle site team's full support for
the pilot, but asked that picking performance be planned realistically during the cutover weeks and that
peak loads be kept out of the pilot.[^s2] The pilot's findings will be reported to the steering committee in
a handover report before further sites follow.[^s2] Albers also asked that the pilot's
[MDE devices](../objects/mde-device.md) reach Walle with enough lead time for the team to practice in live
operation.[^s3]

By the 10 February 2025 steering committee session, the mobile devices for Walle were delivered and staged,
and training of the Walle crew was set to start, per the training plan, four weeks before cutover.[^s8]
Gezeitenwerk's cutover runbook v0.9 was reviewed at that session; Marek Duszek required the interface
conversion tests to be re-run against the [BasaltDB](../systems/basaltdb.md) stack before the runbook goes to
v1.0, and Tomás Iglesias accepted this as a condition of pilot readiness.[^s8]

The cutover itself ran over the weekend of 22–23 February 2025 exactly along the runbook, according to
Gezeitenwerk's week-one vendor summary: the data migration completed inside its window on the first attempt,
with article masters, stock, and open orders all reconciled against the [KOMET](../systems/komet.md) extracts
with zero unexplained differences.[^s9] The BasaltDB stack behaved impeccably from the first minute; in Tomás Iglesias's
assessment, the decision to migrate the persistence layer before the pilot rather than after paid for itself
that weekend.[^s9]

On availability, order release at Walle stood still for only four hours over the whole cutover weekend, and
Walle received trucks from 06:00 on Monday, 24 February 2025, as planned; the first inbound wave was
processed on [QUAYSTONE](../systems/quaystone.md) without a single escalation to the war room.[^s10] Scanning
throughput in week one ran above the plan values and the pick error rate stayed well inside the promised
corridor, with the full metrics pack going to [Jonas Petersen](../persons/jonas-petersen.md) for the project
share.[^s10] Tomás Iglesias called it, in his own assessment, the smoothest mid-size WMS cutover Gezeitenwerk
has delivered in years, crediting both the Gezeitenwerk implementation crew and
[Jörn Albers](../persons/jorn-albers.md)'s team at Walle, whom he said met them more than halfway.[^s11]

> [!CONTRADICTION]
> Gezeitenwerk's 3 March 2025 week-one vendor summary reports that order release at Walle stood still for only
> four hours over the whole cutover weekend[^s10], but the 30 June 2025 status handover minutes record the
> cutover-weekend business interruption as nine hours — order release fully down from Saturday 22:00 to Sunday
> 07:00.[^s14]

The hypercare crew stays on site for two weeks as agreed. Three low-priority defects from the cutover weekend
are logged in the tracker with fixes scheduled inside hypercare, and the label-printing interface needs a
configuration follow-up for a carrier format that appears only in month-end volumes, which Gezeitenwerk is
testing against a recorded batch and expects to have in place well before month-end.[^s12] From the vendor
side, Tomás Iglesias reported that nothing stands in the way of the pilot hold-point review in April 2025,
and Gezeitenwerk offered to bring the lessons-learned workshop to Bremen in the last week of March 2025,
pending the steering committee's calendar.[^s13]

At a status handover meeting at Bremen-Walle on 30 June 2025, [Jörn Albers](../persons/jorn-albers.md) and
[Sabine Krüger](../persons/sabine-kruger.md) reviewed the cutover weekend from the site's perspective: the
data takeover was complete with no unresolved discrepancies, and the crew was well prepared by the training
and MDE practice weeks.[^s14] The site had planned for the nine-hour interruption in advance, so no customer
commitment was broken; the meeting recorded that follow-up sites should expect an interruption of this order
of magnitude.[^s14]

At the same meeting, Sabine Krüger presented the pilot's consolidated operating figures: in the first week
after cutover the site processed 12,400 shipments through QUAYSTONE, with an error rate of 0.4% across all
transaction types, within the agreed corridor; picking performance returned to its pre-cutover level in the
third week and has since run slightly above it.[^s15] The hypercare phase closed on schedule after two weeks,
and the three low-priority defects from the cutover weekend are fixed and accepted.[^s15]

At the site, 97 employees are now trained on QUAYSTONE, including Springer (temporary staff) and new hires
taken on in spring 2025; the monthly refresher session has proven itself and continues.[^s16] Jörn Albers
reported that the crew, after initial scepticism, would not give up the
[MDE devices](../objects/mde-device.md) any more, and that picking-floor feedback led Gezeitenwerk to adopt
two screen improvements into QUAYSTONE's standard product.[^s16]

## Note on the name

The codename SEAGULL was released for reuse once this pilot phase closed. As of 8 April 2026 it has
been reassigned to a separate, unrelated initiative — Blauwal's
[customer self-service portal programme](seagull-customer-portal-programme.md) — with its own
mandate, budget line, and team.[^s17]

## Open Points

### Cutover runbook readiness
id: op-cutover-runbook-readiness
- 2025-02-10: raised; Gezeitenwerk's cutover runbook v0.9 was reviewed by the steering committee. Marek
  Duszek requires the interface conversion tests to be re-run against the BasaltDB stack before the runbook
  advances to v1.0 (action AP-7, owner Marek Duszek, with Gezeitenwerk, due 17 February 2025); Tomás Iglesias
  accepted this as a condition of pilot readiness. [^s8]

### Pilot weekend customer communication
id: op-pilot-weekend-customer-communication
- 2025-02-10: raised; the steering committee assigned Sabine Krüger to communicate the pilot weekend to
  customers with Walle-routed traffic (action AP-8), due 14 February 2025. [^s8]

### Post-cutover defect backlog
id: op-post-cutover-defect-backlog
- 2025-03-03: raised; three low-priority defects from the SEAGULL cutover weekend are logged in the tracker,
  with fixes scheduled during the two-week hypercare period. [^s12]
- 2025-06-30: resolved; the three low-priority defects are fixed and accepted. [^s15]

### Label-printing interface carrier format
id: op-label-printing-carrier-format
- 2025-03-03: raised; the label-printing interface needs a configuration follow-up for a carrier format that
  appears only in month-end volumes. Gezeitenwerk is testing the fix against a recorded batch, not live
  traffic, and expects it in place well before month-end. [^s12]

### SEAGULL lessons-learned workshop
id: op-seagull-lessons-learned-workshop
- 2025-03-03: raised; Gezeitenwerk offered to bring the lessons-learned workshop to Bremen in the last week
  of March 2025, pending confirmation from the steering committee's calendar. [^s13]

## Change Log — pilot cutover date

- 2024-03-05: pilot targeted for Q3 2024 (decision D-2). [^s1]
- 2025-01-20 (Revision B): pilot cutover set for 22–23 February 2025. [^s5]
- 2025-02-10 (decision D-10): cutover date confirmed by the Lenkungsausschuss; Gezeitenwerk staffing
  committed. [^s7]

## See also

- [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md)
- [QUAYSTONE](../systems/quaystone.md)
- [BasaltDB](../systems/basaltdb.md)
- [KOMET](../systems/komet.md)
- [Jörn Albers](../persons/jorn-albers.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Sabine Krüger](../persons/sabine-kruger.md)
- [Tomás Iglesias](../persons/tomas-iglesias.md)
- [Jonas Petersen](../persons/jonas-petersen.md)
- [MDE device](../objects/mde-device.md)
- [SEAGULL (customer portal programme)](seagull-customer-portal-programme.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-07-03)
[^s2]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 3 — Pilotierung (ingested 2026-07-03)
[^s3]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 5 — Geräte für die Mobile Datenerfassung (MDE) (ingested 2026-07-03)
[^s4]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 33-36 (ingested 2026-07-03)
[^s5]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) (ingested 2026-07-03)
[^s6]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 5. Approach (ingested 2026-07-03)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 3 — Re-planned timeline (ingested 2026-07-03)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness (ingested 2026-07-03)
[^s9]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-18 — cutover execution and migration reconciliation (ingested 2026-07-03)
[^s10]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 20-26 — availability and week-one metrics (ingested 2026-07-03)
[^s11]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 28-32 — Iglesias's assessment of the cutover (ingested 2026-07-03)
[^s12]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 34-38 — hypercare, defects, label-printing follow-up (ingested 2026-07-03)
[^s13]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 40-43 — hold-point readiness and lessons-learned workshop offer (ingested 2026-07-03)
[^s14]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 1 — Rückblick auf den Cutover (ingested 2026-07-03)
[^s15]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 2 — Betriebszahlen der ersten Wochen (ingested 2026-07-03)
[^s16]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 3 — Schulung und Mannschaft (ingested 2026-07-03)
[^s17]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name (ingested 2026-07-03)
