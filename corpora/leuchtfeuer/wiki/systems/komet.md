---
type: System
title: KOMET
description: Blauwal Logistik GmbH's legacy, in-house-customised warehouse management
  system, being replaced by QUAYSTONE under Projekt LEUCHTFEUER.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- komet
- wms
- blauwal-logistik
- leuchtfeuer
- budget
timestamp: '2026-07-03T17:04:10Z'
---

KOMET is the warehouse management system (WMS) that [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
has customised and patched in-house for many years.[^s1] Blauwal's Geschäftsführung decided on 27 February
2024 to replace it with [QUAYSTONE](quaystone.md), under [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md).[^s1]
Marek described KOMET as deeply embedded in the business: "The WMS is the spider in the web here — everything
in this company touches it."[^s2]

## Vendor and support

KOMET's original vendor, [Werftmann & Partner Softwarehaus GmbH](../organizations/werftmann-partner-softwarehaus-gmbh.md),
went insolvent in 2017; since then there has been no vendor support of any kind, so every bug fix, carrier
change, and customs-regulation update falls to [Marek Duszek](../persons/marek-duszek.md)'s team alone, with
no escalation path, against a codebase whose documentation stops mid-sentence in places.[^s1][^s3][^s10] Two of the
three people who understand the allocation module are older than the module itself — a risk Marek called "the
actual risk clock ticking under the company," running regardless of what gets decided in any meeting.[^s3]
Blauwal's annual licence and support costs for KOMET stand at EUR 310,000, according to
[Heike Brandt](../persons/heike-brandt.md).[^s6][^s17] Blauwal's final 2024–2025 operations audit, accepted by
the Geschäftsführung on 31 March 2026, confirmed this figure as reported to the steering committee elsewhere
and repeatedly, since it is contractual rather than estimated.[^s17] Revision B of the programme charter
now targets KOMET's decommissioning, and the programme's close, for Q4 2025.[^s12]

Following the full-estate QUAYSTONE go-live on 17 March 2026, KOMET remains readable while Blauwal completes
the archive extraction required for customs and audit history; the system was initially scheduled for final
switch-off on 30 September 2026 — later than Revision B's Q4 2025 target — after seventeen years in
productive use.[^s22] That date has since moved forward: with the archive extraction finished earlier than
planned, KOMET's final switch-off is now set for 31 July 2026.[^s23]

## Site estate and customisations

KOMET has been in productive use at Blauwal since 2009.[^s10] KOMET runs in eleven warehouses, and every site
carries local customisations — no two installations are identical.[^s4]

> [!CONTRADICTION]
> Marek Duszek's KOMET estate assessment counts eleven warehouses running KOMET[^s4], but the 19 March 2024
> steering-committee minutes state KOMET "wird in neun Lagern betrieben" (is operated in nine warehouses)[^s10].

The per-site delta list is section 5 of Marek Duszek's KOMET estate assessment; some deltas
exist only because a forklift broke in 2011 and the resulting workaround became the process.[^s4] Years of
parallel maintenance have also left duplicate article records across Blauwal's sites; migrating these
duplicates into QUAYSTONE unchanged would multiply them, which is why the LEUCHTFEUER kickoff meeting agreed
the article master data must be cleansed before the pilot cutover (see
[Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)).[^s2]

## Interfaces

KOMET exchanges data with 27 downstream systems — among them the ERP, customs, the telematics units in the
fleet, three customer portals, label printing, and staging robots in Walle.[^s5] Before Marek Duszek's
assessment, Blauwal had never had a complete and current interface inventory; building one was most of the
assessment's work.[^s5] Every one of the 27 connections has to be re-pointed, re-tested, or consciously killed
during the migration — in Marek's assessment this interface work is the real project, and the software swap
itself is the easy part.[^s5] As a cautionary parallel, Marek cited the 2001 loss of the Mars Climate Orbiter,
which burned up because one team wrote pound-seconds where the other read newton-seconds; he noted the
customs interface alone carries four unit conversions of the same shape, and asked that each get explicit
review time in the migration plan rather than being folded into a generic "testing, misc" line item.[^s7]
Marek Duszek's status note of 12 January 2026 — quoted in
[Petra Vogelsang](../persons/petra-vogelsang.md)'s go-live announcement — reported the interface backlog at
zero.[^s21]

## Pilot migration reconciliation

During the [SEAGULL](../projects/seagull.md) pilot cutover on 22–23 February 2025, the migrated article
masters, stock, and open-order data reconciled against KOMET's extracts with zero unexplained differences,
according to Gezeitenwerk's week-one vendor summary of 3 March 2025.[^s16]

## Open Points

### KOMET estate assessment
id: op-komet-estate-assessment
- 2024-03-05: Marek Duszek gave a first, deliberately verbal sketch of the KOMET estate and asked for two
  weeks to put a proper written assessment together — enumerating the sites, the interfaces, and the local
  customisations one by one (action AP-2, owner Marek Duszek, due 15 March 2024). [^s2]
- 2024-03-12: Marek Duszek delivered the written KOMET estate assessment three days early.[^s8] The full
  assessment runs 34 pages on the project share, folder "AP-2"; he asked readers to cover at minimum section
  2 (interfaces) and section 5 (customisations) before the 19 March steering-committee meeting. [^s9]
- 2024-03-19: the steering committee took favourable note of the written assessment and asked that the
  interface list be kept as a living document on the project drive (decision LA-2024-01). [^s11]

### Unplanned KOMET downtime cost estimate
id: op-komet-downtime-cost-estimate
- 2026-04-15: retracted; Heike Brandt formally withdrew her 10 June 2024 memorandum, "KOMET operating costs
  (provisional figures)," which had reported a provisional per-hour estimate for unplanned KOMET
  downtime.[^s18] Blauwal's final 2024–2025 operations audit, accepted by the Geschäftsführung on 31 March
  2026, found the estimate's methodology had double-counted contractual penalties the affected customer
  accounts had since renegotiated and had extrapolated a peak-season hourly pattern across the whole
  year.[^s19] The retracted memorandum was removed from the project record by document control; its
  provisional figures are not to be quoted or restated in any new document, and the audited replacement
  figures are held separately under restricted access rather than reproduced here.[^s20]

### KOMET final switch-off
id: op-komet-final-switch-off
- 2026-03-20: raised; following the full-estate QUAYSTONE go-live, KOMET remains readable while Blauwal
  completes the archive extraction required for customs and audit history; final switch-off is set for 30
  September 2026. [^s22]
- 2026-04-08: brought forward; the archive extraction for customs and audit history finished earlier than
  planned, so final switch-off is now set for 31 July 2026 instead of 30 September 2026. Facilities and IT
  operations are informed; the SEAGULL portal programme is unaffected but was notified, as the last
  KOMET-era customer exports retire with the system. [^s23]

## See also

- [QUAYSTONE](quaystone.md)
- [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md)
- [SEAGULL](../projects/seagull.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [Werftmann & Partner Softwarehaus GmbH](../organizations/werftmann-partner-softwarehaus-gmbh.md)
- [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-07-03)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate (ingested 2026-07-03)
[^s3]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 23-27 (ingested 2026-07-03)
[^s4]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 10-14 (ingested 2026-07-03)
[^s5]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 16-21 (ingested 2026-07-03)
[^s6]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 32-36 (ingested 2026-07-03)
[^s7]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 42-47 (ingested 2026-07-03)
[^s8]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 7-8 (ingested 2026-07-03)
[^s9]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 57-59 (ingested 2026-07-03)
[^s10]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 1 — Ausgangslage und Altsystem (ingested 2026-07-03)
[^s11]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Beschlüsse (ingested 2026-07-03)
[^s12]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) (ingested 2026-07-03)
[^s16]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-16 (ingested 2026-07-03)
[^s17]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), § 4. What this retraction does not touch (ingested 2026-07-03)
[^s18]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), § 1. Retraction (ingested 2026-07-03)
[^s19]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), § 2. Reason (ingested 2026-07-03)
[^s20]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), § 3. Handling of the withdrawn document (ingested 2026-07-03)
[^s21]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 26-32 (ingested 2026-07-03)
[^s22]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 37-39 (ingested 2026-07-03)
[^s23]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § AOB (ingested 2026-07-03)
