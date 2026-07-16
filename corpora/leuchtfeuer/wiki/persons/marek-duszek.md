---
type: Person
title: Marek Duszek
description: Lead architect at Blauwal Logistik GmbH, responsible for assessing the
  KOMET estate for Projekt LEUCHTFEUER.
tags:
- leuchtfeuer
- blauwal-logistik
- komet
- seagull
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T17:06:43Z'
citadel_version: 0.3.0
---

Marek Duszek is lead architect at [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md).[^s1] With [KOMET](../systems/komet.md)'s original vendor gone, every bug fix, carrier change, and customs-regulation update falls on his team alone, with no escalation path.[^s2] At the [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) kickoff meeting he warned against underestimating KOMET's integration surface — "The WMS is the spider in the web here — everything in this company touches it." — and took ownership of a written assessment of the KOMET estate, due 15 March 2024 (action AP-2).[^s3] He argued against running [QUAYSTONE](../systems/quaystone.md) on [KorallenDB](../systems/korallendb.md) and asked that his dissent be recorded in the minutes, stating he would not re-litigate the point outside the steering committee.[^s4]

Duszek delivered his written assessment of the KOMET estate on 12 March 2024, three days ahead of the 15 March deadline.[^s5] It found that KOMET runs in eleven warehouses with no two installations identical, and Duszek warned against planning the migration on a "one template, N copies" assumption, calling that "planning fiction."[^s6] The assessment also produced the company's first complete inventory of KOMET's 27 downstream-system interfaces; Duszek argues that re-pointing, re-testing, or retiring those connections — not the software swap — is the real project.[^s7] In the same mail he set out his case for BasaltDB over KorallenDB as QUAYSTONE's database — simpler replication, more mature operational tooling, more honest licence terms — while stressing this was his professional opinion, not a fact about the universe, and that he would implement the committee's decision properly rather than re-litigate it.[^s8] That decision was reversed on 13 January 2025, when the Lenkungsausschuss adopted [BasaltDB](../systems/basaltdb.md) by circular resolution.[^s11]

At the steering committee meeting on 19 March 2024 he summarised the assessment for the committee, which accepted it approvingly and asked that the interface list be kept as a living document on the project drive (decision LA-2024-01).[^s9]

The [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) charter formalizes that, as lead architect, he owns technical decisions within the platform frame the Lenkungsausschuss sets.[^s10]

At the Lenkungsausschuss's 10 February 2025 session he presented his team's assessment of KorallenDB's revised licence terms — per-core pricing plus a usage-metering audit clause — which underpinned the committee's reversal of the database decision to BasaltDB (decision D-9).[^s12] He also required the interface conversion tests to be re-run against the BasaltDB stack before Gezeitenwerk's cutover runbook goes to v1.0, for the [SEAGULL](../projects/seagull-2024-25-quaystone-pilot.md) pilot (action AP-7, due 17 February 2025).[^s13]

At the pilot-operation status handover meeting of 30 June 2025 — which he attended by video — the committee recorded that certification of the customs interface by the responsible authority remained outstanding and, per current information, was not expected before autumn.[^s14] He took on monthly follow-up reporting to the committee on that certification.[^s15]

In her 20 March 2026 go-live announcement, [Petra Vogelsang](petra-vogelsang.md) quoted his status note of 12 January 2026 in full, calling his numbered lists "this programme's folk art": [BasaltDB](../systems/basaltdb.md) had then run 47 consecutive weeks without an unplanned restart, and the interface backlog stood at zero.[^s16] She thanked him in the same announcement for "dissent in writing and delivery without sulking" — a reference to his recorded KorallenDB dissent.[^s17]

On 8 April 2026 he set the architecture guardrails for [SEAGULL](../projects/seagull.md), Blauwal's new customer self-service portal programme: it is built on the QUAYSTONE order and shipment APIs with no direct database access, holds no warehouse data of its own, and treats customer identity and entitlements as a first-class design topic from week one — guardrails the kickoff made binding (decision SG-2026-03).[^s18] He added that, after two years of migration discipline, he intends to defend these three lines "with the enthusiasm of a man who has seen the alternative,"[^s19] and takes on the new programme's architecture in an advisory capacity of two days a week.[^s20]

## See also
- [KOMET](../systems/komet.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [SEAGULL (2024–25 pilot)](../projects/seagull-2024-25-quaystone-pilot.md)
- [SEAGULL (customer portal)](../projects/seagull.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Projekt LEUCHTFEUER — kickoff meeting, minutes — role (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — no escalation path (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate — warning and AP-2 (ingested 2026-07-16)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database — dissent on KorallenDB (ingested 2026-07-16)
[^s5]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 7-8 — assessment delivered three days early (ingested 2026-07-16)
[^s6]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 10-12 — eleven warehouses, "planning fiction" (ingested 2026-07-16)
[^s7]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 16-21 — 27 interfaces, "the real project" (ingested 2026-07-16)
[^s8]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-54 — BasaltDB preference and reasoning (ingested 2026-07-16)
[^s9]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Beschlüsse — decision LA-2024-01 (ingested 2026-07-16)
[^s10]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance — lead architect owns technical decisions (ingested 2026-07-16)
[^s11]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — BasaltDB decision reverses D-4 (ingested 2026-07-16)
[^s12]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — Duszek's team's licence-terms assessment (ingested 2026-07-16)
[^s13]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 6 — Pilot readiness — runbook v0.9 review, AP-7 (ingested 2026-07-16)
[^s14]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 5 — Gesamt-Rollout — customs certification outstanding (ingested 2026-07-16)
[^s15]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § Aufgaben — Duszek's customs-certification follow-up ownership (ingested 2026-07-16)
[^s16]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 27-33 — quoted 12 January 2026 status note: BasaltDB uptime, interface backlog zero (ingested 2026-07-16)
[^s17]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 48-50 — Vogelsang's thanks for "dissent in writing and delivery without sulking" (ingested 2026-07-16)
[^s18]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails — the three guardrails (ingested 2026-07-16)
[^s19]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails — Duszek's closing remark (ingested 2026-07-16)
[^s20]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working — architecture advisory role (ingested 2026-07-16)
