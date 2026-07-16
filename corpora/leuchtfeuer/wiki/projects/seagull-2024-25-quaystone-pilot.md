---
type: Project
title: SEAGULL (2024-25 QUAYSTONE Pilot)
description: The Projekt LEUCHTFEUER pilot for QUAYSTONE, run at Blauwal Logistik's
  Bremen-Walle warehouse ahead of the full estate go-live; the SEAGULL codename was
  later reused for an unrelated 2026 customer-portal programme.
aliases:
- SEAGULL
- Bremen-Walle pilot
tags:
- leuchtfeuer
- pilot
- quaystone
- blauwal-logistik
- bremen
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T17:06:43Z'
citadel_version: 0.3.0
---

SEAGULL is the working codename for [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md)'s pilot rollout of [QUAYSTONE](../systems/quaystone.md), run at the Bremen-Walle warehouse starting in the third quarter of 2024 (decision D-2).[^s1] Bremen-Walle was chosen deliberately: it is a mid-sized site, it sits close to headquarters, and [Jörn Albers](../persons/jorn-albers.md)'s team there is regarded as the most change-friendly crew in the estate — whatever the pilot teaches, it teaches cheaply and close to home.[^s2] How the remaining sites follow the pilot — one warehouse at a time, or a single coordinated cutover of everything at once — was left open at the kickoff meeting, to be decided by the steering committee.[^s3]

At the steering committee meeting on 19 March 2024, Jörn Albers pledged the site team's full support for the pilot, while asking that commissioning capacity be planned realistically during the changeover weeks and that peak loads be kept out of the pilot; the pilot's findings will be reported to the steering committee in a handover protocol before further sites follow.[^s4]

In her 2 April 2024 cutover-strategy proposal (action AP-3), [Petra Vogelsang](../persons/petra-vogelsang.md) specified the pilot's hold-point concretely: no second site is to be touched until SEAGULL has run stably and its lessons are written down where the next site can read them.[^s5]

The [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md) charter's Version 1.0 milestone table narrowed SEAGULL's cutover at Bremen-Walle to August 2024 and added a pilot hold-point review for September 2024, ahead of the wider rollout.[^s6] The charter's Revision B milestone table moves SEAGULL's cutover to 22–23 February 2025 and its hold-point review to April 2025.[^s7]

By the Lenkungsausschuss's 10 February 2025 session, the mobile devices for Bremen-Walle were delivered and staged, and training of the Walle crew was starting, per the training plan, four weeks before cutover.[^s8] Gezeitenwerk's cutover runbook v0.9 was reviewed at that session; [Marek Duszek](../persons/marek-duszek.md) required the interface conversion tests to be re-run against the BasaltDB stack before the runbook goes to v1.0 (action AP-7, owner Marek Duszek with Gezeitenwerk, due 17 February 2025), and [Tomás Iglesias](../persons/tomas-iglesias.md) accepted this as a condition of readiness.[^s9] [Sabine Krüger](../persons/sabine-kruger.md) owns pilot-weekend communication to customers with Walle-routed traffic (action AP-8, due 14 February 2025).[^s10] [Jörn Albers](../persons/jorn-albers.md) asked that the pilot weekend avoid the month-end peak; the chosen weekend of 22–23 February 2025 does.[^s11] Tomás Iglesias committed Gezeitenwerk staffing to the confirmed dates.[^s12]

One week after the cutover, Tomás Iglesias reported that the pilot cutover at Bremen-Walle was done and, in his assessment, a success.[^s13] The cutover ran over the weekend of 22–23 February 2025 exactly along the runbook, and the data migration completed inside its window on the first attempt: article masters, stock, and open orders all reconciled against the KOMET extracts with zero unexplained differences.[^s14] Order release at Walle stood still for only four hours over the whole cutover weekend, and the site received trucks from 06:00 on Monday, 24 February, as planned; the first inbound wave was processed on QUAYSTONE without a single escalation to the war room.[^s15] In week one, scanning throughput ran above the plan values and the pick error rate stayed inside the promised corridor, per Iglesias's report.[^s16]

Iglesias also offered a personal assessment, explicitly labelled as such: in his view this was the smoothest mid-size WMS cutover Gezeitenwerk had delivered in years, crediting the implementation crew that worked the weekend in Walle and Jörn Albers's site team for meeting them more than halfway.[^s17] This is Gezeitenwerk's own account manager praising his company's and the site's performance; no independent source in this corpus corroborates the superlative.[^llm1]

Iglesias reported that the [BasaltDB](../systems/basaltdb.md) stack "behaved impeccably from the first minute," and that the earlier decision to migrate the persistence layer before the pilot, rather than after, paid off over the cutover weekend.[^s18] This is the vendor's own assessment of the platform it recommended; no independent source in this corpus corroborates it.[^llm2]

The report also flagged what remained open: the hypercare crew stayed on site for the agreed two weeks with three low-priority cutover-weekend defects logged in the tracker, and the label-printing interface needed a configuration follow-up for a carrier format that appears only in month-end volumes.[^s19] From Gezeitenwerk's side nothing stood in the way of the April hold-point review, and Iglesias offered to bring a lessons-learned workshop to Bremen in the last week of March 2025, pending the committee's scheduling decision.[^s20]

Four months after cutover, [Jörn Albers](../persons/jorn-albers.md) and [Sabine Krüger](../persons/sabine-kruger.md) gave the pilot's site-side retrospective at a status handover meeting on 30 June 2025: the data takeover ran completely and without unresolved differences, and the crew was well prepared for it by the training and MDE practice weeks that preceded cutover.[^s21] Bremen-Walle had planned ahead for the changeover, so no customer commitment was broken, and the site's account is that follow-up sites should expect an interruption of this order of magnitude.[^s22]

> [!CONTRADICTION]
> Gezeitenwerk account manager Tomás Iglesias's pilot report of 3 March 2025 states that order release at Walle stood still for only four hours over the whole cutover weekend[^s15], but the site's own status handover of 30 June 2025 states the cutover weekend's operational interruption was nine hours, from Saturday 22:00 to Sunday 07:00[^s22].

In its first full week of operation after cutover, the site handled 12,400 shipments through QUAYSTONE, with an error rate of 0.4% across all transaction types, within the agreed corridor; picking performance returned to its pre-changeover level in the third week and has run slightly above it since.[^s23] The hypercare phase closed on schedule after two weeks, and the three low-priority defects known from the cutover weekend are fixed and signed off.[^s24]

By the same meeting, 97 employees at the site were trained for QUAYSTONE, including temporary staff and the spring's new hires, and the monthly refresher session has proven itself and continues.[^s25] Jörn Albers reported that his crew, after initial scepticism, would not give the replacement [MDE](../abbreviations/mde-mobile-data-capture.md) devices back, and that feedback from picking had led to mask improvements in two cases which Gezeitenwerk has adopted into its standard QUAYSTONE product.[^s26]

The SEAGULL codename was released for reuse once this pilot phase closed: from April 2026 it also names an unrelated initiative, [SEAGULL](seagull.md), Blauwal's customer self-service portal programme, with its own mandate, budget line, and team.[^s27]

## Change Log
- 2024-05-14: The charter (Version 1.0) targeted SEAGULL's cutover at Bremen-Walle for August 2024 and its pilot hold-point review for September 2024.[^s6]
- 2025-01-20: Revision B moves the cutover to 22–23 February 2025 and the hold-point review to April 2025.[^s7]

## Open Points

### Hypercare and cutover-weekend defects
id: op-hypercare-and-cutover-weekend-defects
- 2025-03-03: One week after cutover, the hypercare crew remained on site for the agreed two weeks, and three low-priority defects from the cutover weekend were logged in the tracker with fixes scheduled inside the hypercare window.[^s19]
- 2025-06-30: Hypercare closed on schedule after two weeks; the three low-priority cutover-weekend defects are fixed and signed off.[^s24]

### Label-printing carrier-format follow-up
id: op-label-printing-carrier-format-follow-up
- 2025-03-03: The label-printing interface needed one configuration follow-up for a carrier format that appears only in month-end volumes; Gezeitenwerk was testing the fix against a recorded batch, not live traffic, and targeted having it in place before month-end.[^s19]

### Lessons-learned workshop
id: op-lessons-learned-workshop
- 2025-03-03: Tomás Iglesias offered to bring the lessons-learned workshop to Bremen in the last week of March 2025, pending the steering committee's scheduling decision; from Gezeitenwerk's side nothing stood in the way of the April hold-point review.[^s20]

## See also
- [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md)
- [SEAGULL (customer portal)](seagull.md)
- [QUAYSTONE](../systems/quaystone.md)
- [BasaltDB](../systems/basaltdb.md)
- [Jörn Albers](../persons/jorn-albers.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Sabine Krüger](../persons/sabine-kruger.md)
- [Tomás Iglesias](../persons/tomas-iglesias.md)
- [MDE — Mobile Data Capture](../abbreviations/mde-mobile-data-capture.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Decisions — decision D-2 (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — why Bremen-Walle was chosen (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — cutover strategy left open (ingested 2026-07-16)
[^s4]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 3 — Pilotierung — Albers's pledge, capacity request, handover protocol (ingested 2026-07-16)
[^s5]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 33-36 — the hold-point criterion (ingested 2026-07-16)
[^s6]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones — August 2024 cutover, September 2024 review (ingested 2026-07-16)
[^s7]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) — 22–23 February 2025 cutover, April 2025 review (ingested 2026-07-16)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness — devices delivered/staged, training start (ingested 2026-07-16)
[^s9]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness — runbook v0.9 review, AP-7 (ingested 2026-07-16)
[^s10]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § Action items — AP-8 (ingested 2026-07-16)
[^s11]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 3 — Re-planned timeline — Albers's month-end-peak request (ingested 2026-07-16)
[^s12]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 3 — Re-planned timeline — staffing commitment (ingested 2026-07-16)
[^s13]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 9-11 — headline: cutover done and a success (ingested 2026-07-16)
[^s14]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-16 — runbook adherence, migration completed first attempt, zero unexplained differences vs. KOMET extracts (ingested 2026-07-16)
[^s15]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 20-22 — four-hour order-release halt, Monday 06:00 trucks as planned, first inbound wave with no war-room escalation (ingested 2026-07-16)
[^s16]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 22-24 — week-one scanning throughput and pick error rate vs. plan/corridor (ingested 2026-07-16)
[^s17]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 28-32 — Iglesias's "smoothest cutover" assessment and crew credit (ingested 2026-07-16)
[^llm1]: LLM - self-promotional claim by the vendor's own account manager, not independently corroborated in this corpus (added 2026-07-16)
[^s18]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 17-18 — BasaltDB "behaved impeccably," migration-timing decision paid off (ingested 2026-07-16)
[^llm2]: LLM - self-promotional assessment of the vendor's recommended platform's performance, not independently corroborated in this corpus (added 2026-07-16)
[^s19]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 34-38 — hypercare, defects tracker, label-printing follow-up (ingested 2026-07-16)
[^s20]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 40-43 — hold-point readiness and lessons-learned workshop proposal (ingested 2026-07-16)
[^s21]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 1 — Rückblick auf den Cutover — complete data takeover, crew well prepared (ingested 2026-07-16)
[^s22]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 1 — Rückblick auf den Cutover — nine-hour operational interruption, no customer commitment broken, planning implication (ingested 2026-07-16)
[^s23]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 2 — Betriebszahlen der ersten Wochen — shipments, error rate, picking performance (ingested 2026-07-16)
[^s24]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 2 — Betriebszahlen der ersten Wochen — hypercare closed, defects fixed (ingested 2026-07-16)
[^s25]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 3 — Schulung und Mannschaft — 97 trained, monthly refresher (ingested 2026-07-16)
[^s26]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 3 — Schulung und Mannschaft — MDE acceptance, mask improvements adopted into standard (ingested 2026-07-16)
[^s27]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name — codename released for reuse (ingested 2026-07-16)
