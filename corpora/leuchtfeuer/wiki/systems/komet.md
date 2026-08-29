---
type: System
title: KOMET
description: Blauwal Logistik GmbH's in-house-customised warehouse management system,
  being replaced by QUAYSTONE under Projekt LEUCHTFEUER.
tags:
- warehouse-management
- software
- logistics
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-08-28T23:49:00Z'
citadel_version: 0.6.0
---

KOMET is the warehouse management system (WMS)
[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md) has customised and patched
in-house for many years.[^s1] It is being replaced by [QUAYSTONE](quaystone.md) under
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md), following a Geschäftsführung decision
taken on 27 February 2024.[^s1]

KOMET's original vendor, Werftmann & Partner Softwarehaus GmbH, went insolvent in 2017; since then
there has been no vendor support of any kind, so every bug fix, every carrier change, and every
customs-regulation update lands on [Marek Duszek](../persons/marek-duszek.md)'s team alone, with no
escalation path.[^s1][^s7] The team patches KOMET against a codebase whose documentation stops
mid-sentence in places, and of the three people who understand the allocation module, two are older
than the module itself — which Marek Duszek calls the real risk clock ticking under the company,
regardless of what gets decided in any meeting.[^s7] Marek warned the kickoff meeting not to
underestimate KOMET's integration surface: "The WMS is the spider in the web here — everything in
this company touches it."[^s2] He asked for two weeks to put together a written assessment
enumerating the sites, interfaces, and local customisations one by one, so that planning would rest
on counted facts rather than estimates shouted across a meeting table (action AP-2).[^s2]

Marek delivered that written assessment on 12 March 2024, three days ahead of the 15 March
deadline.[^s4] KOMET runs in eleven warehouses, and every site carries its own local
customisations — no two installations are identical, and some of the differences exist only
because a workaround for a one-off problem (a forklift breaking down in 2011, at one site) became
the permanent process there.[^s5] Marek warned that planning the migration on a "one template, N
copies" assumption is "planning fiction."[^s5]

The assessment also produced Blauwal's first complete, current inventory of KOMET's downstream
interfaces: the system exchanges data with 27 downstream systems, among them the ERP, customs, the
fleet's telematics units, three customer portals, label printing, and the staging robots in
Walle.[^s6] Every one of those 27 connections has to be re-pointed, re-tested, or consciously
retired during the migration; Marek Duszek judges this interface work, not the software swap
itself, to be the real substance of the migration project.[^s6] The programme's first year bore
this out: by its extraordinary steering session of 10 February 2025, the committee named the
interface work package — proving far larger in effort than in count — as one of the two reasons
the original 1 October 2024 go-live could not be met, the other being master-data cleansing.[^s21]
By his status note of 12 January 2026, Marek Duszek reported the interface backlog at
zero.[^s22]

Years of parallel maintenance in KOMET have left duplicate article records across Blauwal's
sites.[^s2] See [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) for the cleansing plan.

The Projekt LEUCHTFEUER programme charter's Revision B targets KOMET's decommissioning, alongside
programme close, for Q4 2025.[^s14] Following the estate's full go-live on 17 March 2026, KOMET
remains readable while the archive extraction for customs and audit history is completed; its
final switch-off, originally scheduled for 30 September 2026, was brought forward to
31 July 2026 once that extraction finished earlier than planned — closing out seventeen years of
productive service since 2009.[^s23][^s24]

KOMET has been in productive use at Blauwal since 2009.[^s13] At the steering committee
(Lenkungsausschuss) meeting on 19 March 2024, Marek Duszek summarized his written estate
assessment for the committee, which took it in approvingly and asked that the interface list be
kept as a living document on the project drive (decision LA-2024-01).[^s13] The committee also
reaffirmed that, since the 2017 insolvency, maintenance and further development of KOMET run
entirely through Blauwal's internal IT team.[^s13]

> [!CONTRADICTION]
> Marek Duszek's written assessment of 12 March 2024 counts KOMET running in eleven
> warehouses.[^s5] The steering committee's own summary of that assessment, one week later, states
> KOMET is operated in nine warehouses.[^s13]

Keeping KOMET running also carries a hard price tag: as she had promised at the kickoff meeting,
[Heike Brandt](../persons/heike-brandt.md) put the figure in writing on 11 March 2024 — KOMET's
annual licence and support contracts cost EUR 310,000, for a system whose vendor "has not existed
for seven years."[^s8] Marek Duszek's team modelled the total cost of ownership against QUAYSTONE
and found migration wins in every scenario, including the pessimistic ones where the timeline
doubles.[^s9]

On 15 April 2026, Heike Brandt formally retracted her own memorandum of 10 June 2024, "KOMET
operating costs (provisional figures)."[^s25] The final operations audit for 2024–2025, accepted by
the Geschäftsführung on 31 March 2026, had closed the methodology that memo's downtime-cost
estimate was built on: the provisional approach double-counted contractual penalties the affected
customer accounts had in fact renegotiated, and extrapolated a peak-season hourly pattern across the
whole year, producing figures that differed from the audited ones materially, not marginally.[^s26]
Document control removed the 10 June 2024 memorandum from the project record the same day, and
Brandt asked that nobody rely on, quote, or restate its figures; the corrected figures are held in
the final audit report, distributed separately under restricted access.[^s27][^s28] The audit
separately confirmed that KOMET's annual licence and support figure, above, was — unlike the
retracted downtime estimate — contractual rather than estimated, and unaffected by the
retraction.[^s29]

Marek Duszek warns that migrations are more often undone by boring unit, encoding, and
field-length conversions than by big design mistakes; he cites the Mars Climate Orbiter, which he
says burned up in 2001 after one team used pound-seconds where the other used
newton-seconds.[^s10] The Mars Climate Orbiter was in fact lost in September 1999, not
2001.[^llm1] Blauwal's own customs interface carries four unit conversions of that same shape, and
Marek wants each one given explicit review time in the migration plan rather than folded into a
generic "testing, misc" line item.[^s11]

## Change Log

- 2024-05-14: charter version 1.0 targeted KOMET's decommissioning and programme close for
  Q4 2024.[^s20]
- 2025-01-17: Revision B reset the target to Q4 2025.[^s14]
- 2026-03-20: the go-live announcement sets KOMET's final switch-off for 30 September 2026,
  further extending the Revision B target.[^s23]
- 2026-04-08: final switch-off is brought forward from 30 September 2026 to 31 July 2026, after
  the archive extraction for customs and audit history finished ahead of schedule.[^s24]

## Open Points

### Written assessment of the KOMET estate
id: op-komet-estate-assessment
- 2024-03-05: Marek Duszek gave a first, deliberately verbal sketch of the KOMET estate and asked
  for two weeks to put together a proper written assessment enumerating the sites, interfaces, and
  local customisations (action AP-2, owner Marek Duszek, due 15 March 2024).[^s2][^s3]
- 2024-03-12: Marek Duszek delivered the written assessment — action AP-2 done — three days ahead
  of the 15 March deadline: 34 pages, on the project share under folder "AP-2", covering all eleven
  warehouse sites and a first complete inventory of KOMET's 27 downstream interfaces. Recommended
  reading before the 19 March 2024 steering committee (Lenkungsausschuss) is section 2 (interfaces)
  and section 5 (site customisations).[^s4][^s12]

## See also

- [QUAYSTONE](quaystone.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Heike Brandt](../persons/heike-brandt.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-08-28)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate (ingested 2026-08-28)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Action items (ingested 2026-08-28)
[^s4]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 7-8 (ingested 2026-08-28)
[^s5]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 10-14 (ingested 2026-08-28)
[^s6]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 16-21 (ingested 2026-08-28)
[^s7]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 23-27 (ingested 2026-08-28)
[^s8]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 32-36 (ingested 2026-08-28)
[^s9]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 38-40 (ingested 2026-08-28)
[^s10]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 42-45 (ingested 2026-08-28)
[^s11]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 45-47 (ingested 2026-08-28)
[^s12]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 57-59 (ingested 2026-08-28)
[^s13]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 1 — Ausgangslage und Altsystem (ingested 2026-08-28)
[^llm1]: LLM - model knowledge, not from a raw file: the Mars Climate Orbiter was lost in September 1999, not 2001 (added 2026-08-28)
[^s14]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 63-69 (ingested 2026-08-29)
[^s20]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md) — Version 1.0's milestone plan, superseded in full by Revision B and no longer stated in the current file (ingested 2026-08-29)
[^s21]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 1 — Where the first year actually left us (ingested 2026-08-29)
[^s22]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 27-33 (ingested 2026-08-29)
[^s23]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 38-41 (ingested 2026-08-29)
[^s24]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § AOB (ingested 2026-08-29)
[^s25]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 10-12 (ingested 2026-08-29)
[^s26]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 16-23 (ingested 2026-08-29)
[^s27]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 34-39 (ingested 2026-08-29)
[^s28]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 41-42 (ingested 2026-08-29)
[^s29]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 49-51 (ingested 2026-08-29)
