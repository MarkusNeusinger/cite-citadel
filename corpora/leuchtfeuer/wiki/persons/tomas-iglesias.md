---
type: Person
title: Tomás Iglesias
description: Account manager at Gezeitenwerk Software GmbH, representing the QUAYSTONE
  vendor on Projekt LEUCHTFEUER.
tags:
- logistics
- software
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-08-28T23:11:29Z'
citadel_version: 0.6.0
---

Tomás Iglesias is account manager at
[Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md).[^s1] At the
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) kickoff meeting he confirmed Gezeitenwerk
can staff the implementation to the 1 October 2024 go-live date, provided the master data arrives
clean and the interface specifications are frozen by early summer.[^s2] He presented the two
deployment options Gezeitenwerk supports for [QUAYSTONE](../systems/quaystone.md)'s persistence
layer, and recommended [KorallenDB](../systems/korallendb.md), which the meeting decided to
adopt.[^s3] He sent his apologies for the steering committee (Lenkungsausschuss) meeting on 19
March 2024.[^s4] As Gezeitenwerk's account manager, per the programme charter he attends the
Lenkungsausschuss as a guest without a vote.[^s5]

At the steering committee's extraordinary session of 10 February 2025, conducted in English at his
request, he confirmed that Gezeitenwerk supports QUAYSTONE on BasaltDB as a first-class
deployment, with two reference customers running it in production at comparable volume, and
committed Gezeitenwerk staffing to the re-planned timeline (pilot cutover 22–23 February 2025,
full-estate go-live 30 June 2025).[^s6][^s7] He also accepted, as a condition of pilot readiness,
Marek Duszek's requirement that the interface conversion tests be re-run against the BasaltDB
stack before Gezeitenwerk's cutover runbook — reviewed at v0.9 — advances to v1.0.[^s8]

On 3 March 2025, a week after the SEAGULL pilot cutover, he sent the committee Gezeitenwerk's
vendor summary: the cutover ran over the weekend of 22–23 February exactly along the runbook, the
data migration completed inside its window on the first attempt with zero unexplained differences
against the KOMET extracts.[^s9] He reported the BasaltDB stack "behaved impeccably from the first
minute," and that moving the persistence layer ahead of the pilot rather than after it "paid for
itself this weekend."[^s10] Offering, in his words, "one sentence of pride, clearly labelled as
such," he called it the smoothest mid-size WMS cutover Gezeitenwerk has delivered in years — his
own assessment of his company's delivery, not an independently verified benchmark — and credited
the outcome chiefly to [Jörn Albers](jorn-albers.md)'s implementation crew at
Walle.[^s11][^llm1] He reported the hypercare crew remaining on site for two weeks, three
low-priority defects from the cutover weekend logged for fixing inside hypercare, and one
outstanding configuration follow-up for the label-printing interface.[^s12] He said nothing stood
in the way, from the vendor side, of the April 2025 hold-point review, and offered to bring a
lessons-learned workshop to Bremen in the last week of March 2025.[^s13]

## Style profile

- **Labels his own opinion before giving it, keeping it separate from the facts around it** —
  "Allow me one sentence of pride, clearly labelled as such: in my view this was the smoothest
  mid-size WMS cutover we have delivered in years."[^s11]
- **Savours good news while staying measured about it** — "let me start with the headline, because
  for once the headline is a pleasure to write."[^s14]
- **Gives credit outward to the site team rather than keeping it for his own company** — "the
  implementation crew that sat in Walle over that weekend deserves them. Jörn's team met them more
  than halfway; a cutover goes like this only when the site wants it to."[^s11]
- **Volunteers the bad news unprompted rather than letting the good news stand alone** — "What
  remains, so this mail is not only sunshine: ..."[^s12]
- **Enthusiastic, fast follow-through on his own offers** — "say the word and I will book the
  travel the same day!"[^s15]
- **Warm, personalised sign-off** — "With best regards from Hamburg — and my sincere
  congratulations to the whole Walle crew."[^s16]

## See also

- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KorallenDB](../systems/korallendb.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 1-11 (ingested 2026-08-28)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-08-28)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-08-28)
[^s4]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), lines 1-11 (ingested 2026-08-28)
[^s5]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance (ingested 2026-08-29)
[^s6]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 28-29 (ingested 2026-08-29)
[^s7]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 39-41 (ingested 2026-08-29)
[^s8]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 67-69 (ingested 2026-08-29)
[^s9]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-16 (ingested 2026-08-29)
[^s10]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 17-18 (ingested 2026-08-29)
[^s11]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 28-32 (ingested 2026-08-29)
[^llm1]: LLM - self-promotional claim by the vendor's own account manager about Gezeitenwerk's delivery quality, not independently corroborated in this corpus (added 2026-08-29)
[^s12]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 34-38 (ingested 2026-08-29)
[^s13]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 40-43 (ingested 2026-08-29)
[^s14]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 9-11 (ingested 2026-08-29)
[^s15]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 41-42 (ingested 2026-08-29)
[^s16]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), line 45 (ingested 2026-08-29)
