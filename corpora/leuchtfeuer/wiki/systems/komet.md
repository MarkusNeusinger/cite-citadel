---
type: System
title: KOMET
description: Blauwal Logistik's long-serving, in-house-customised warehouse management
  system, being replaced by QUAYSTONE under Projekt LEUCHTFEUER.
tags:
- wms
- logistics
- blauwal-logistik
- leuchtfeuer
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T17:12:37Z'
citadel_version: 0.3.0
---

KOMET is the warehouse management system (WMS) that [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md) has customised and patched in-house for many years.[^s1] KOMET has been in continuous productive use at Blauwal since 2009.[^s17] It is being replaced by [QUAYSTONE](quaystone.md) under [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md), following the company's executive management's decision of 27 February 2024.[^s2] KOMET's original vendor no longer exists, so every bug fix, carrier change, and customs-regulation update lands on lead architect [Marek Duszek](../persons/marek-duszek.md)'s team alone, with no escalation path behind them.[^s3] Duszek described the system's central role bluntly: "The WMS is the spider in the web here — everything in this company touches it."[^s4] The original vendor, Werftmann & Partner Softwarehaus GmbH, went insolvent in 2017; since then there has been no vendor support of any kind, and Duszek's team patches KOMET itself against a codebase whose documentation "stops mid-sentence in places."[^s7][^s18] Of the three people who still understand the allocation module, two are older than the module itself.[^s8]

Duszek's written estate assessment, delivered 12 March 2024, put numbers on KOMET's footprint: it runs in eleven warehouses, and every site carries local customisations, with no two installations identical — some of the per-site differences trace back as far as a forklift breaking down in 2011, whose workaround became permanent process.[^s9] He warned that anyone planning the migration on a "one template, N copies" assumption "is planning fiction."[^s10] The assessment also produced the company's first complete interface inventory: KOMET exchanges data with 27 downstream systems — the ERP, customs, the fleet's telematics units, three customer portals, label printing, and staging robots in Walle — every one of which must be re-pointed, re-tested, or consciously retired during the migration.[^s11] Duszek argues that this interface work, not the software swap itself, is the real project.[^s12]

> [!CONTRADICTION]
> Duszek's 12 March 2024 estate assessment states KOMET runs in eleven warehouses[^s9], but the Blauwal steering committee's 19 March 2024 minutes state it runs in nine warehouses[^s19].

Duszek cited the Mars Climate Orbiter disaster as a cautionary tale about unit-conversion errors in interface work, dating the spacecraft's loss to 2001 and attributing it to one engineering team writing pound-seconds where another read newton-seconds.[^s13] NASA's Mars Climate Orbiter was actually lost in 1999, not 2001, though the pound-seconds/newton-seconds mismatch Duszek describes is the real, well-documented cause.[^llm1] He warned that Blauwal's customs interface alone carries four unit conversions "of exactly this shape" and asked for explicit review time for each one in the migration plan, rather than a line item called "testing, misc."[^s14]

Years of parallel maintenance in KOMET have left duplicate article records across Blauwal's sites; [Sabine Krüger](../persons/sabine-kruger.md) flagged this as the operational risk she loses sleep over, since migrating the duplicates would only multiply them.[^s5]

The [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) charter names KOMET's key-person dependency and its interface surface among the programme's principal risks: knowledge of KOMET internals is concentrated in very few people, a risk until decommissioning, and the interface surface is the programme's largest single work package, with each connection needing explicit conversion review and test time.[^s21] The charter (Version 1.0) targeted KOMET's decommissioning for the fourth quarter of 2024; Revision B moves that target to the fourth quarter of 2025.[^s22][^s27]

In her 20 March 2026 go-live announcement, marking the full warehouse estate's cutover to QUAYSTONE, [Petra Vogelsang](../persons/petra-vogelsang.md) confirmed KOMET remains readable while the programme completes an archive extraction for customs and audit history, with the system's final switch-off now set for 30 September 2026 — closing out seventeen years of productive service she marked with "a small wake."[^s28]

At the kickoff of the [SEAGULL](../projects/seagull.md) customer self-service portal programme on 8 April 2026, Petra Vogelsang reported, for coordination with the portal's timeline, that KOMET's decommissioning has been brought forward to 31 July 2026: the archive extraction for customs and audit history finished earlier than planned, so there is no reason to keep the system running until the previously communicated end of September. The portal programme is unaffected but was informed, since the last KOMET-era customer exports retire with it.[^s29]

On 15 April 2026, Heike Brandt formally retracted her memorandum of 10 June 2024, "KOMET operating costs (provisional figures)," and every provisional figure it contained, with immediate effect.[^s30] The final KOMET operations audit for 2024–2025, accepted by Blauwal's Geschäftsführung on 31 March 2026, closed the methodology behind the 2024 memorandum's downtime-cost estimate against it: the provisional approach had double-counted contractual penalties that the affected customer accounts had since renegotiated, and had extrapolated a peak-season hourly downtime pattern across the whole year, producing figures materially different from the audited ones.[^s31] Document control removed the 2024 memorandum from the project record the same day, and any existing document reproducing its figures is to treat that passage as withdrawn and remove it at its next revision.[^s32] The corrected figures are held in the final audit report, distributed separately under restricted access through document control; Brandt deliberately reproduces none of them, old or corrected, in the retraction itself.[^s33] The retraction leaves the migration's business case unaffected, since it was argued on the licence reality and the vendor situation rather than on the retracted downtime estimate, and the programme it justified has in any case delivered.[^s34]

## Change Log
- 2024-05-14: The charter (Version 1.0) targeted KOMET's decommissioning for the fourth quarter of 2024.[^s22]
- 2025-01-20: Revision B moves KOMET's decommissioning target to the fourth quarter of 2025.[^s27]
- 2026-03-20: Final switch-off date set to 30 September 2026, superseding Revision B's fourth-quarter-2025 target, pending completion of the customs/audit archive extraction.[^s28]
- 2026-04-08: Final switch-off date brought forward to 31 July 2026, superseding the 20 March 2026 date, after the customs/audit archive extraction finished early.[^s29]

## Open Points

### KOMET estate assessment
id: op-komet-estate-assessment
- 2024-03-05: Marek Duszek gave a first, deliberately verbal sketch of the KOMET estate and asked for two weeks to put together a proper written assessment enumerating the sites, interfaces, and local customisations, so that Projekt LEUCHTFEUER's planning rests on counted facts rather than estimates (action AP-2, owner Marek Duszek, due 15 March 2024).[^s6]
- 2024-03-12: Duszek delivered the written assessment three days ahead of the deadline[^s15] — 34 pages on the project share (folder "AP-2"), with section 2 (interfaces) and section 5 (customisations) flagged as required reading before the 19 March steering committee.[^s16]
- 2024-03-19: Duszek summarised the assessment for the steering committee, which accepted it approvingly and asked that the interface list be kept as a living document on the project drive (decision LA-2024-01).[^s20]

### KOMET operating-cost audit
id: op-komet-operating-cost-audit
- 2026-04-15: Heike Brandt formally retracted her 10 June 2024 memorandum "KOMET operating costs (provisional figures)" after the final 2024–2025 operations audit found its downtime-cost estimate's methodology unsound — it had double-counted renegotiated contractual penalties and extrapolated a peak-season pattern across the whole year. The memorandum was withdrawn from the project record and its figures are not to be relied on, quoted, or restated; corrected figures are held separately, under restricted access.[^s30][^s31][^s32]

## See also
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [QUAYSTONE](quaystone.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
- [SEAGULL (customer portal)](../projects/seagull.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — KOMET is in-house customised (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — 27 Feb 2024 replacement decision (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — vendor gone, no escalation path (ingested 2026-07-16)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate — Duszek's "spider in the web" quote (ingested 2026-07-16)
[^s5]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate — duplicate article records (ingested 2026-07-16)
[^s6]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate — AP-2 written assessment (ingested 2026-07-16)
[^s7]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 23-25 — vendor name, 2017 insolvency, no support, documentation (ingested 2026-07-16)
[^s8]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 25-26 — allocation module bus factor (ingested 2026-07-16)
[^s9]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 10-14 — eleven warehouses, customisations, forklift anecdote (ingested 2026-07-16)
[^s10]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 11-12 — "planning fiction" (ingested 2026-07-16)
[^s11]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 16-19 — 27 downstream systems, first interface inventory (ingested 2026-07-16)
[^s12]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 19-21 — "the real project" (ingested 2026-07-16)
[^s13]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 43-45 — Mars Climate Orbiter anecdote as stated (ingested 2026-07-16)
[^llm1]: LLM - model knowledge: Mars Climate Orbiter was lost in 1999, not 2001 (added 2026-07-16)
[^s14]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 45-47 — customs interface unit conversions, review-time request (ingested 2026-07-16)
[^s15]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 7-8 — assessment delivered three days early (ingested 2026-07-16)
[^s16]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 57-59 — 34 pages, folder AP-2, read before the 19th (ingested 2026-07-16)
[^s17]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 1 — Ausgangslage und Altsystem — productive use since 2009 (ingested 2026-07-16)
[^s18]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 1 — Ausgangslage und Altsystem — vendor insolvency 2017, internal IT maintenance since (ingested 2026-07-16)
[^s19]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 1 — Ausgangslage und Altsystem — nine warehouses (ingested 2026-07-16)
[^s20]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Beschlüsse — decision LA-2024-01 (ingested 2026-07-16)
[^s21]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 10. Principal risks — key-person dependency and interface surface (ingested 2026-07-16)
[^s22]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones — Q4 2024 decommissioning target (ingested 2026-07-16)
[^s27]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) — Q4 2025 decommissioning target (ingested 2026-07-16)
[^s28]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 38-41 — KOMET readable during archive extraction, 30 September 2026 switch-off, "small wake" for seventeen years of service (ingested 2026-07-16)
[^s29]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § AOB — KOMET decommissioning brought forward (ingested 2026-07-16)
[^s30]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 10-12 — retraction of the 10 June 2024 memorandum, immediate effect (ingested 2026-07-16)
[^s31]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 16-23 — audit findings: double-counted penalties, extrapolated peak-season pattern, materially wrong (ingested 2026-07-16)
[^s32]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 34-37 — removed from project record, treat reproductions as withdrawn (ingested 2026-07-16)
[^s33]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 41-45 — corrected figures in the final audit report, restricted access, non-reproduction (ingested 2026-07-16)
[^s34]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 51-54 — migration business case unaffected (ingested 2026-07-16)
