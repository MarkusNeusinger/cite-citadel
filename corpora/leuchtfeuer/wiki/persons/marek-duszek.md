---
type: Person
title: Marek Duszek
description: Lead architect at Blauwal Logistik GmbH; owns the KOMET estate assessment
  and dissented from the choice of KorallenDB for QUAYSTONE.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- leuchtfeuer
- blauwal-logistik
- komet
- korallendb
timestamp: '2026-07-03T17:04:10Z'
---

Marek Duszek is lead architect at [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md).[^s1]
Because [KOMET](../systems/komet.md)'s original vendor no longer exists, every bug fix, carrier change, and
customs-regulation update for the system lands on his team alone, with no escalation path.[^s2] At the
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) kickoff meeting on 5 March 2024 he described KOMET
as deeply embedded in the business: "The WMS is the spider in the web here — everything in this company
touches it."[^s3] He committed to producing a written assessment of the KOMET estate (action AP-2), due 15
March 2024.[^s3]

Marek delivered the KOMET estate assessment three days early, on 12 March 2024.[^s5] In it, he concluded that
migration wins in every [total cost of ownership](../abbreviations/tco-total-cost-of-ownership.md) (TCO)
scenario his team modelled, including the pessimistic ones where the timeline doubles.[^s6][^llm1] He also
asked that the migration plan give explicit review time to each of the customs interface's four unit
conversions, citing the 2001 loss of the Mars Climate Orbiter — lost over a pound-seconds/newton-seconds
mismatch — as a cautionary parallel.[^s7]

Marek argued against the choice of [KorallenDB](../systems/korallendb.md) as the persistence layer for
[QUAYSTONE](../systems/quaystone.md) and asked that his dissent be recorded in the minutes (decision D-4),
stating he would not re-litigate the point outside the steering committee.[^s4] He later put his reasons for
that dissent in writing: he would have built on [BasaltDB](../systems/basaltdb.md) from day one instead,
judging its replication story simpler, its operational tooling a decade ahead, and its licence terms honest.
He was explicit that this is his professional opinion, not a fact about the universe, and that he would
implement the committee's decision properly rather than re-litigate it.[^s8]

The Lenkungsausschuss later reversed its KorallenDB decision: per a circular resolution of 13 January 2025,
recorded in the programme charter's Revision B, QUAYSTONE's persistence layer now runs on
[BasaltDB](../systems/basaltdb.md) instead — the platform Marek had argued for from the start.[^s11]

He summarised the written assessment for the steering committee on 19 March 2024, which took favourable note
of it and asked that the interface list be kept as a living document (decision LA-2024-01).[^s9]

Per the programme charter, he owns technical decisions within the platform frame the Lenkungsausschuss
sets.[^s10]

At the steering committee's 10 February 2025 session, Marek presented his team's assessment of KorallenDB's
vendor's revised licence terms, announced in December 2024: per-core pricing plus an audit clause granting
the vendor scheduled access to usage metering. The committee confirmed the reversal to BasaltDB unanimously
as decision D-9.[^s12] At the same session, reviewing Gezeitenwerk's cutover runbook v0.9, he required the
interface conversion tests to be re-run against the BasaltDB stack before the runbook advances to v1.0
(action AP-7), a condition Tomás Iglesias accepted.[^s13]

He attended a status handover meeting at Bremen-Walle on 30 June 2025 by video.[^s14] There, he was assigned
to own the monthly follow-up report on the customs-interface certification, which remains outstanding.[^s15]

In a status note of 12 January 2026 — quoted verbatim in
[Petra Vogelsang](../persons/petra-vogelsang.md)'s go-live announcement to all staff — Marek reported that
[BasaltDB](../systems/basaltdb.md) had run 47 consecutive weeks without an unplanned restart and that the
interface backlog stood at zero, adding: "Keep it there."[^s16] In that 20 March 2026 announcement, Vogelsang
thanked him "for dissent in writing and delivery without sulking," referring to his
recorded dissent over the choice of KorallenDB and the BasaltDB migration he had argued for from the
start.[^s17]

He attended the [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)
kickoff meeting on 8 April 2026 as lead architect, where he set three architecture guardrails for the new
customer self-service portal: it is built solely on QUAYSTONE's order and shipment APIs with no direct
database access; it holds no warehouse data of its own; and customer identity and entitlements are a
first-class design topic from week one, not a hardening sprint before launch.[^s18] He said he intends to
defend these three lines "with the enthusiasm of a man who has seen the alternative."[^s18] His role in the
programme is advisory, two days a week.[^s19]

## See also

- [KOMET](../systems/komet.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL](../projects/seagull.md)
- [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)
- [Tomás Iglesias](tomas-iglesias.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [TCO — Total Cost of Ownership](../abbreviations/tco-total-cost-of-ownership.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 3-11 (ingested 2026-07-03)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-07-03)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate (ingested 2026-07-03)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-07-03)
[^s5]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 7-8 (ingested 2026-07-03)
[^s6]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 38-40 (ingested 2026-07-03)
[^s7]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 42-47 (ingested 2026-07-03)
[^s8]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-07-03)
[^s9]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 1 — Ausgangslage und Altsystem (ingested 2026-07-03)
[^s10]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance (ingested 2026-07-03)
[^s11]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform (ingested 2026-07-03)
[^s12]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited (ingested 2026-07-03)
[^s13]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness (ingested 2026-07-03)
[^s14]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 3-9 (ingested 2026-07-03)
[^s15]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § Aufgaben (ingested 2026-07-03)
[^s16]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 26-32 (ingested 2026-07-03)
[^s17]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 45-48 (ingested 2026-07-03)
[^s18]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails (ingested 2026-07-03)
[^s19]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working (ingested 2026-07-03)
[^llm1]: LLM - model knowledge, not from a raw file (added 2026-07-03)
