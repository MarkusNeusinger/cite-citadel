---
type: Organization
title: Blauwal Logistik GmbH
description: Logistics company headquartered in Bremen, running Projekt LEUCHTFEUER
  to replace its KOMET warehouse management system with QUAYSTONE.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- blauwal-logistik
- leuchtfeuer
- wms
- customer-portal
timestamp: '2026-07-03T17:30:14Z'
---

Blauwal Logistik GmbH is a logistics company whose Hauptverwaltung (head office) is in Bremen, room Weser 2
of which hosted the [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) kickoff meeting on 5 March
2024.[^s1] Its Geschäftsführung (management board) decided on 27 February 2024 to replace the company's
legacy warehouse management system [KOMET](../systems/komet.md) with [QUAYSTONE](../systems/quaystone.md),
the cloud WMS platform from [Gezeitenwerk Software GmbH](gezeitenwerk-software-gmbh.md).[^s19] The
Geschäftsführung approved a programme budget of EUR 1.8 million for the replacement.[^s2] Revision B of the
programme charter records that this budget has since grown to EUR 2.4 million, approved by the
Geschäftsführung on 16 January 2025 on the Lenkungsausschuss's escalation (see
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) for the full budget history).[^s8]

The company's warehouse estate comprises eleven warehouses, each running a locally customised installation of
[KOMET](../systems/komet.md) — no two installations are identical.[^s5] The estate includes a site at
Bremen-Walle, where the QUAYSTONE pilot, codename [SEAGULL](../projects/seagull.md), is planned to start in
the third quarter of 2024.[^s3] Blauwal's steering committee (Lenkungsausschuss) for the programme was
scheduled to meet next on 19 March 2024 in Bremen; its minutes are kept in German.[^s4]

The steering committee met again on 19 March 2024 as scheduled, chaired by
[Petra Vogelsang](../persons/petra-vogelsang.md) and minuted by [Sabine Krüger](../persons/sabine-kr-ger.md),
with [Tomás Iglesias](../persons/tom-s-iglesias.md) sending his regrets.[^s6] It took three decisions
(LA-2024-01 to LA-2024-03) and set its next meeting for 7 May 2024 in Bremen.[^s7]

The steering committee held an extraordinary session on 10 February 2025, conducted in English at guest
Tomás Iglesias's request, chaired by Petra Vogelsang and minuted by
[Jonas Petersen](../persons/jonas-petersen.md), with [Marek Duszek](../persons/marek-duszek.md),
[Sabine Krüger](../persons/sabine-kr-ger.md), [Heike Brandt](../persons/heike-brandt.md), and
[Jörn Albers](../persons/j-rn-albers.md) also attending.[^s9] It took four decisions (D-9 to D-12) — reversing
the persistence layer to [BasaltDB](../systems/basaltdb.md), confirming the re-planned timeline and the
increased EUR 2.4 million budget, and ratifying charter Revision B in full — and set its next meeting for 11
March 2025 in Bremen, when the German-language protokoll series resumes.[^s9]

The SEAGULL pilot cutover at Bremen-Walle ran on 22–23 February 2025 as planned; per Gezeitenwerk's 3 March
2025 vendor summary it completed successfully, with the data migration reconciling against the KOMET
extracts with zero unexplained differences and order release at Walle standing still for only four hours
over the whole cutover weekend.[^s10]

The steering committee met again at Bremen-Walle on 30 June 2025, for a status handover on the SEAGULL pilot,
chaired by [Petra Vogelsang](../persons/petra-vogelsang.md) and minuted by
[Sabine Krüger](../persons/sabine-kr-ger.md), with [Jörn Albers](../persons/j-rn-albers.md) and
[Jonas Petersen](../persons/jonas-petersen.md) also attending and
[Marek Duszek](../persons/marek-duszek.md) joining by video; [Heike Brandt](../persons/heike-brandt.md) and
[Tomás Iglesias](../persons/tom-s-iglesias.md) were excused.[^s11] It took decision LA-2025-07, postponing the
rollout to the remaining sites to the first quarter of 2026 after the customs-interface certification and the
MDE-device delivery for three sites both slipped.[^s12] Its next meeting is set for 9 September 2025 in
Bremen.[^s13]

The full warehouse estate went live on QUAYSTONE on 17 March 2026: the last convoy of sites crossed over that
morning and passed its go/no-go gates without a waiver, completing Projekt LEUCHTFEUER's rollout.[^s14] In her
go-live announcement, Petra Vogelsang called it "the largest change this company's operations have seen in a
generation."[^s15]

On 24 March 2026 Blauwal's Geschäftsführung decided to build a customer self-service portal, chartered under
the reused codename [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)
— an initiative unrelated to the earlier, closed [2024–25 QUAYSTONE pilot](../projects/seagull.md) that had
originally carried the name.[^s16] The portal programme held its kickoff meeting on 8 April 2026, targeting a
first customer launch in the second quarter of 2027 with three contract-logistics pilot customers[^s17], and
is being built on QUAYSTONE's order and shipment APIs, with no direct database access permitted.[^s18]

## See also

- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL](../projects/seagull.md)
- [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)
- [KOMET](../systems/komet.md)
- [QUAYSTONE](../systems/quaystone.md)
- [Gezeitenwerk Software GmbH](gezeitenwerk-software-gmbh.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [Sabine Krüger](../persons/sabine-kr-ger.md)
- [Tomás Iglesias](../persons/tom-s-iglesias.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Heike Brandt](../persons/heike-brandt.md)
- [Jörn Albers](../persons/j-rn-albers.md)
- [Jonas Petersen](../persons/jonas-petersen.md)
- [Yasmin Okafor](../persons/yasmin-okafor.md)
- [BasaltDB](../systems/basaltdb.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 3-11 (ingested 2026-07-03)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 3 — Budget (ingested 2026-07-03)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-07-03)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 89-90 (ingested 2026-07-03)
[^s5]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 10-14 (ingested 2026-07-03)
[^s6]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), lines 1-11 (ingested 2026-07-03)
[^s7]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), lines 68-83 (ingested 2026-07-03)
[^s8]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 7. Budget (ingested 2026-07-03)
[^s9]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 1-11 (ingested 2026-07-03)
[^s10]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-21 (ingested 2026-07-03)
[^s11]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 3-9 (ingested 2026-07-03)
[^s12]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 5 — Gesamt-Rollout (ingested 2026-07-03)
[^s13]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), line 73 (ingested 2026-07-03)
[^s14]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 9-10 (ingested 2026-07-03)
[^s15]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 49-51 (ingested 2026-07-03)
[^s16]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name (ingested 2026-07-03)
[^s17]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 4 — Timeline and pilot customers (ingested 2026-07-03)
[^s18]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails (ingested 2026-07-03)
[^s19]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-07-03)
