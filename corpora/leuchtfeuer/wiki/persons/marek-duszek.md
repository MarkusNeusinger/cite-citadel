---
type: Person
title: Marek Duszek
description: Lead architect at Blauwal Logistik GmbH, responsible for the KOMET warehouse
  management system.
tags:
- logistics
- engineering
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-08-28T23:43:48Z'
citadel_version: 0.6.0
---

Marek Duszek is lead architect at
[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md).[^s1] Per the programme charter,
he owns technical decisions for Projekt LEUCHTFEUER within the platform frame the Lenkungsausschuss
sets.[^s12] He and his team are the
sole owners of [KOMET](../systems/komet.md): every bug fix, carrier change, and
customs-regulation update lands on his team alone, with no escalation path, since KOMET's
original vendor no longer exists.[^s2] At the
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) kickoff meeting he warned against
underestimating KOMET's integration surface: "The WMS is the spider in the web here — everything
in this company touches it."[^s3] He asked for, and was given, two weeks to produce a written
assessment of the KOMET estate (action AP-2, due 15 March 2024).[^s3][^s4]

Marek argued against the meeting's decision to run QUAYSTONE's deployment on
[KorallenDB](../systems/korallendb.md) and asked that his dissent be recorded in the minutes,
which was done; he stated he would not re-litigate the point outside the steering
committee.[^s5]

A week later he set out his reasoning in writing: he believes Blauwal should instead have built
QUAYSTONE's persistence layer on [BasaltDB](../systems/basaltdb.md), whose replication story he
considers simpler and whose operational tooling and licence terms he considers better than
KorallenDB's — his professional opinion, offered for the record rather than to re-open a decision
he said he would implement as made.[^s8]

The Lenkungsausschuss reversed its original decision by circular resolution on 13 January 2025:
[QUAYSTONE](../systems/quaystone.md)'s persistence layer now runs on
[BasaltDB](../systems/basaltdb.md), the platform he recommended.[^s13] He prepared this
reassessment for the committee after KorallenDB's vendor announced revised licence terms in
December 2024 — per-core pricing plus an audit clause granting the vendor scheduled access to
Blauwal's own usage metering.[^s14] The Lenkungsausschuss confirmed the reversal unanimously as
decision D-9 at its extraordinary steering session of 10 February 2025.[^s15]

At that same session, as a condition of pilot readiness, he required the interface conversion
tests to be re-run against the BasaltDB stack before Gezeitenwerk's cutover runbook — reviewed at
v0.9 — advances to v1.0, which Tomás Iglesias accepted (action AP-7, with Gezeitenwerk, due
17 February 2025).[^s16]

He delivered the written KOMET estate assessment (action AP-2) on 12 March 2024, three days ahead
of schedule.[^s6] It produced Blauwal's first complete inventory of KOMET's downstream interfaces —
27 systems in all — and Marek judges that interface migration, not the KOMET-to-QUAYSTONE software
swap itself, to be the real substance of the project.[^s7]

At the steering committee (Lenkungsausschuss) meeting on 19 March 2024 he summarized this
assessment for the committee, which took it in approvingly.[^s11]

He attended a status handover for the Bremen-Walle pilot on 30 June 2025 by video, where he took
on tracking the customs-interface certification with the responsible authority, reporting to the
group monthly — the certification remained outstanding and, per current information, was not
expected before autumn 2025.[^s17]

By his status note of 12 January 2026, he reported [BasaltDB](../systems/basaltdb.md) running 47
consecutive weeks without an unplanned restart and the interface backlog at zero.[^s18] In her
20 March 2026 go-live announcement, Petra Vogelsang thanked him specifically "for dissent in
writing and delivery without sulking" — a callback to his own commitment, made in March 2024, to
implement the KorallenDB decision "without sabotage-by-sulking" even though he disagreed with
it.[^s19][^s8]

He attended the
[SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md) kickoff
meeting on 8 April 2026 as lead architect, setting the programme's three binding architecture
guardrails: the portal is built strictly on QUAYSTONE's order and shipment APIs with no direct
database access, holds no warehouse data of its own, and treats customer identity and entitlements
as a first-class design topic from week one.[^s20] He intends to defend the three lines "with the
enthusiasm of a man who has seen the alternative."[^s21] He advises the programme's architecture
two days a week,[^s22] and owns gap-analysing portal use cases against current QUAYSTONE
endpoints, due 12 May 2026 (action SG-AP-2).[^s23]

## Style profile

- **Dry, declarative, and pre-empts pushback** — "Anyone who plans this migration on the
  assumption of 'one template, N copies' is planning fiction, and I will say so in writing every
  time it comes up."[^s9]
- **Insists on written, dated records over verbal claims or memory** — "I want the opinion in
  writing, dated, so that whichever way this goes, we can learn from it instead of re-arguing it
  from memory."[^s8]
- **Precise about his own epistemic confidence** — separates opinion from fact even while arguing
  hard for it: "This is my professional opinion, not a fact about the universe, and the committee
  has decided otherwise; I will implement the decision properly and without
  sabotage-by-sulking."[^s8]
- **Dry, understated humour** — "No slides, on principle."[^s6] "If you read only one page, read
  the interface inventory and count to 27 yourself."[^s10]

## See also

- [KOMET](../systems/komet.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 1-11 (ingested 2026-08-28)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-08-28)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate (ingested 2026-08-28)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Action items (ingested 2026-08-28)
[^s5]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-08-28)
[^s6]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 7-8 (ingested 2026-08-28)
[^s7]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 16-21 (ingested 2026-08-28)
[^s8]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-08-28)
[^s9]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 10-12 (ingested 2026-08-28)
[^s10]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 57-59 (ingested 2026-08-28)
[^s11]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 1 — Ausgangslage und Altsystem (ingested 2026-08-28)
[^s12]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance (ingested 2026-08-29)
[^s13]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 82-85 (ingested 2026-08-29)
[^s14]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 24-25 (ingested 2026-08-29)
[^s15]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 31-35 (ingested 2026-08-29)
[^s16]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 67-69 (ingested 2026-08-29)
[^s17]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 68-69 (ingested 2026-08-29)
[^s18]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 27-33 (ingested 2026-08-29)
[^s19]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), line 49 (ingested 2026-08-29)
[^s20]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 39-43 (ingested 2026-08-29)
[^s21]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 45-46 (ingested 2026-08-29)
[^s22]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working (ingested 2026-08-29)
[^s23]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Action items (ingested 2026-08-29)
