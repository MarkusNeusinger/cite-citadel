---
type: Project
title: Projekt LEUCHTFEUER
description: Blauwal Logistik's programme to replace its KOMET warehouse management
  system with the QUAYSTONE cloud WMS platform.
tags:
- leuchtfeuer
- logistics
- wms
- programme-management
- blauwal-logistik
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-07-16T17:06:43Z'
citadel_version: 0.3.0
---

Projekt LEUCHTFEUER is [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s programme to replace [KOMET](../systems/komet.md), its long-serving, in-house-customised [warehouse management system (WMS)](../abbreviations/wms-warehouse-management-system.md), with [QUAYSTONE](../systems/quaystone.md), the cloud WMS platform sold by [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md).[^s1] The programme was constituted by its kickoff meeting on 5 March 2024 at Blauwal Logistik's Bremen headquarters, chaired by [Petra Vogelsang](../persons/petra-vogelsang.md) (Head of IT), who is also the programme lead (decision D-1); minutes were taken by [Jonas Petersen](../persons/jonas-petersen.md) (PMO).[^s2] Also present: [Marek Duszek](../persons/marek-duszek.md) (lead architect), [Sabine Krüger](../persons/sabine-kruger.md) (Head of Warehouse Operations), [Heike Brandt](../persons/heike-brandt.md) (Commercial Director), and [Tomás Iglesias](../persons/tomas-iglesias.md) (Gezeitenwerk account manager).[^s2]

The programme follows the company's executive management (Geschäftsführung)'s decision of 27 February 2024 to replace KOMET with QUAYSTONE.[^s3] KOMET's original vendor no longer exists, so every bug fix, carrier change, and customs-regulation update falls on Marek Duszek's architecture team alone, with no escalation path behind them; Heike Brandt added that the money Blauwal pays every year merely to keep KOMET's licences and support contracts alive buys no improvement of any kind, and she committed to putting the exact figures in writing for the steering committee so the business case is documented rather than anecdotal.[^s4] She delivered on that commitment on 11 March 2024: KOMET's annual licence and support contracts stand at EUR 310,000, for a system whose vendor has not existed for seven years.[^s13] Duszek, forwarding her figures the next day alongside his KOMET estate assessment, called the resulting cost comparison decisive — nothing in the TCO analysis is close, with migration winning in every modelled scenario, including ones where the timeline doubles.[^s14]

The Geschäftsführung has approved a programme budget of EUR 1.8 million, covering the QUAYSTONE licences, Gezeitenwerk's implementation services, internal backfill for the line organisation, training, and a contingency reserve; Heike Brandt was explicit that this is the whole envelope and any overrun would mean going back to the Geschäftsführung.[^s5]

The headline timeline target is that the full warehouse estate goes live on QUAYSTONE on 1 October 2024 (decision D-3), which Tomás Iglesias confirmed Gezeitenwerk can staff to, provided the master data arrives clean and the interface specifications are frozen by early summer.[^s6] Ahead of the full go-live, the programme runs a pilot at the Bremen-Walle warehouse under the working codename [SEAGULL](seagull-2024-25-quaystone-pilot.md), starting in the third quarter of 2024 (decision D-2).[^s7] How the remaining sites follow the pilot — one warehouse at a time, or a single coordinated cutover of everything at once — was left open at the kickoff meeting; opinions in the room differed and the chair declined to force the question.[^s8]

The QUAYSTONE deployment's persistence layer originally ran on [KorallenDB](../systems/korallendb.md) (decision D-4).[^s9][^s35] On 13 January 2025 the Lenkungsausschuss reversed that decision by circular resolution, moving the persistence layer to [BasaltDB](../systems/basaltdb.md) (decision D-9, confirmed unanimously in the Lenkungsausschuss's 10 February 2025 session); the migration was executed before the pilot cutover, so SEAGULL runs on the target stack from its first day.[^s46][^s52]

Next meeting: the steering committee (Lenkungsausschuss), 19 March 2024, 14:00, in Bremen; steering committee minutes are kept in German.[^s10]

The steering committee met as scheduled on 19 March 2024 at Blauwal's Bremen headquarters, chaired by Petra Vogelsang, with Sabine Krüger taking the minutes this time; Marek Duszek, Heike Brandt, and Jörn Albers (site lead, Bremen-Walle) also attended, while Tomás Iglesias sent his apologies.[^s15] The committee reaffirmed the EUR 1.8 million programme budget and its components, and Heike Brandt again stressed that any overrun would require a fresh Geschäftsführung decision.[^s16] It approved the training plan for the QUAYSTONE rollout — roughly 640 employees across commercial and warehouse roles, two-day on-site sessions with German-language training materials starting four weeks before each site's cutover, plus a monthly refresher slot for temporary staff and new hires (decision LA-2024-02).[^s17] It also approved the procurement of 180 replacement [mobile data capture (MDE)](../abbreviations/mde-mobile-data-capture.md) devices, since the existing handhelds are incompatible with QUAYSTONE and some have long been discontinued by their vendor (decision LA-2024-03); Procurement will run the tender, with deliveries staggered per site ahead of each cutover.[^s18] The next steering committee meeting is scheduled for 7 May 2024 in Bremen; minutes are circulated with a week's notice for review, and objections go to the minutes-taker in writing.[^s19]

The programme's governance rests on a formal charter, authored by [Jonas Petersen](../persons/jonas-petersen.md) (PMO) on behalf of the programme lead.[^s28] The charter states it is the single authoritative statement of the programme's scope, deliverables, timeline, and budget, and that it prevails over a conflicting slide, mail, or hallway agreement until the Lenkungsausschuss amends it.[^s29] The charter is now in its Revision B, dated 20 January 2025 and approved by the Lenkungsausschuss via circular resolution of 17 January 2025; per the charter's own change-control rule, Revision B supersedes Version 1.0 of 14 May 2024 in full, and Version 1.0 is withdrawn from circulation.[^s41] Revision B deliberately does not restate the figures and dates it replaces, pointing instead to the steering-committee minutes as the authoritative record of how and when each change was decided.[^s42] Revision B's own account of why a reset was needed: the programme's first year showed the original milestone plan to have been too ambitious for the interface and master-data reality of the estate.[^s43]

The charter defines the programme as complete only once four conditions all hold: QUAYSTONE is the productive WMS at every Blauwal warehouse site and KOMET is decommissioned; no shipment, stock, or article data is lost in migration, with the movement history required for customs and audit purposes retained and retrievable; every affected employee has been trained before the cutover of their own site; and all external interfaces — ERP, customs, telematics, customer portals, label printing — run productively against QUAYSTONE.[^s30]

Its scope covers the WMS replacement at all warehouse sites, migration of article, stock, and open order data, re-connection of all downstream interfaces, procurement and rollout of new mobile data-entry devices, training, and hypercare after each site cutover; explicitly out of scope are replacing the ERP, transport management, building automation, and any process redesign not strictly required by the platform change, and any scope addition requires a steering-committee decision with a documented budget impact.[^s31]

Per the steering decision of 7 May 2024, the Lenkungsausschuss adopted [Petra Vogelsang](../persons/petra-vogelsang.md)'s April cutover-strategy proposal: the rollout is phased warehouse by warehouse, with [SEAGULL](seagull-2024-25-quaystone-pilot.md) running first and an explicit hold point after it — no further site is touched until the pilot has run stably and its lessons are documented — after which the remaining sites follow in small groups with individual go/no-go decisions on data readiness, trained staff, and interface test results, and a site that is not ready waits for the next group.[^s32]

Revision B's milestone table resets the plan: Revision B approved 17 January 2025, the [SEAGULL](seagull-2024-25-quaystone-pilot.md) pilot cutover at Bremen-Walle on 22–23 February 2025, a pilot hold-point review in April 2025, the full estate live on QUAYSTONE by 30 June 2025, and KOMET decommissioning and programme close in the fourth quarter of 2025.[^s44] The Lenkungsausschuss confirmed this timeline again in its 10 February 2025 session (decision D-10), with [Tomás Iglesias](../persons/tomas-iglesias.md) committing Gezeitenwerk staffing to the dates.[^s53]

> [!CONTRADICTION]
> The kickoff minutes date Projekt LEUCHTFEUER's constitution to the 5 March 2024 meeting (decision D-1)[^s2], but the charter's milestone table dates "programme constituted" to 7 May 2024[^s33].

The charter formalizes budget governance: the programme budget is managed by the Commercial Director, and any forecast overrun must be escalated to the Lenkungsausschuss before it is incurred, with an increase requiring a new decision of the Geschäftsführung.[^s34] That escalation happened: on 16 January 2025 the Geschäftsführung approved an increased programme budget of EUR 2.4 million, on the committee's escalation, now also covering an enlarged interface work package.[^s45] The Lenkungsausschuss confirmed the increase in its 10 February 2025 session (decision D-11); [Heike Brandt](../persons/heike-brandt.md) told the committee this second envelope is to be treated as the last one — "There is no third ask in my drawer."[^s54]

The charter also formalizes the programme's governance: the Lenkungsausschuss meets monthly and is the programme's decision body, with German as its working language and its minutes authoritative; the programme lead chairs and reports, the lead architect owns technical decisions within the platform frame the committee sets, warehouse operations owns master data and training, the Commercial Director owns budget and vendor commercials, the PMO keeps the record, and the Gezeitenwerk account manager attends as a guest without vote.[^s36]

The charter names four principal risks: master-data quality — duplicate article records across sites, a hard precondition for the pilot cutover, tracked monthly; the interface surface — the programme's largest single work package, with each connection needing explicit conversion review and test time; key-person dependency — knowledge of [KOMET](../systems/komet.md) internals is concentrated in very few people, whose availability is a programme risk until decommissioning; and timeline ambition — the milestone plan has no slack between the pilot hold point and the full-estate date, so any pilot slippage moves the estate date, a risk the committee accepts knowingly in exchange for a shorter dual-running period.[^s37]

Revision B reconfirms three of these four risks and reframes the fourth: master-data quality — cleansing has progressed but remains a hard precondition for the pilot cutover, tracked monthly until closed; the interface surface — confirmed by the first programme year as the largest work package, with each connection still carrying explicit conversion review and test time; key-person dependency — knowledge of KOMET internals remains concentrated in very few people until decommissioning; and, replacing the earlier timeline-ambition risk, dual running — the longer programme now means a longer period of running two systems in parallel, a risk the committee accepts consciously in exchange for per-site go/no-go quality gates.[^s47]

The charter itself can be amended only by decision of the Lenkungsausschuss, recorded in its minutes and re-issued by the PMO as a new version; superseded versions are withdrawn from circulation.[^s38]

The Lenkungsausschuss met in an extraordinary session on 10 February 2025 at Blauwal's Bremen headquarters, conducted in English at guest [Tomás Iglesias](../persons/tomas-iglesias.md)'s request; the German-language protokoll series was set to resume at the next session, 11 March 2025.[^s48] The committee's own account of the missed original go-live: the interface work package proved far larger in effort than its item count suggested, and the master-data cleansing — correctly made a precondition — could not responsibly have been declared done over the summer; the committee judged the honest response to be a re-planned programme, not a re-dated slide.[^s49]

The database reversal (D-9) turned on commercial grounds that arose after the kickoff: KorallenDB's vendor announced revised licence terms in December 2024 — per-core pricing plus an audit clause granting the vendor scheduled access to usage metering — and [Marek Duszek](../persons/marek-duszek.md)'s team assessed that the five-year cost of the persistence layer would roughly double under the new terms, with an audit overhead nobody had priced, which [Heike Brandt](../persons/heike-brandt.md) confirmed commercially.[^s50] [Tomás Iglesias](../persons/tomas-iglesias.md) confirmed that Gezeitenwerk supports QUAYSTONE on [BasaltDB](../systems/basaltdb.md) as a first-class deployment, with two reference customers running it in production at comparable volume.[^s51] The Lenkungsausschuss confirmed D-9 unanimously in this session, minuting that Duszek's original dissent (recorded March 2024) is reversed today on commercial grounds arising since.[^s52]

On 30 June 2025 — the exact date Revision B had set for the full estate go-live — Bremen-Walle hosted a pilot-operation status handover meeting (Statusübergabe Pilotbetrieb), with [Sabine Krüger](../persons/sabine-kruger.md) taking the minutes; [Petra Vogelsang](../persons/petra-vogelsang.md), [Jörn Albers](../persons/jorn-albers.md), and [Jonas Petersen](../persons/jonas-petersen.md) attended in person and [Marek Duszek](../persons/marek-duszek.md) by video, while [Heike Brandt](../persons/heike-brandt.md) and [Tomás Iglesias](../persons/tomas-iglesias.md) sent their apologies.[^s57] Petra Vogelsang reported on the status of the remaining sites and put a resolution on the timeline to the meeting: certification of the customs interface by the responsible authority remained outstanding and, per current information, was not expected before autumn, and delivery of the replacement MDE devices for three follow-up sites had slipped on the supplier side; holding the originally planned go-live date for the remaining sites would have been possible only by abandoning the agreed go/no-go criteria, which the committee rejected unanimously.[^s58]

**Decision LA-2025-07:** the overall rollout to the remaining sites is postponed to the first quarter of 2026. The per-site go/no-go criteria are unchanged and the staggered small-group rollout continues; the programme leadership is to inform the Geschäftsführung and the site leads in writing by 4 July 2025.[^s59] The next steering committee meeting is scheduled for 9 September 2025, 14:00, in Bremen.[^s60]

On 17 March 2026 the entire Blauwal warehouse estate — every site Blauwal Logistics operates — went live on QUAYSTONE: the last convoy of sites crossed over that morning and passed its go/no-go gates without a waiver.[^s63] In her go-live announcement to all staff, [Petra Vogelsang](../persons/petra-vogelsang.md) was explicit that the programme arrived well over a year after the date the first charter had promised (1 October 2024[^s6]), naming the re-planned timeline, the database change, the pilot's hold point, and the quarter given to customs-interface certification as corrections that were each argued about at the time but, in her assessment, turned out to be worth it — the trade of arriving late rather than wrong.[^s64]

[Heike Brandt](../persons/heike-brandt.md)'s closing figures put total programme spend at EUR 2.62 million against the revised budget of EUR 2.4 million[^s45][^s65] — an overrun she flagged to the Geschäftsführung in autumn 2025, with documented causes: the customs certification delay and the extended dual-running of the two systems account for nearly all of it.[^s65]

The stability story behind the go-live is captured in lead architect [Marek Duszek](../persons/marek-duszek.md)'s status note of 12 January 2026, quoted in full in Vogelsang's announcement: "BasaltDB has now run 47 consecutive weeks without an unplanned restart" and "Interface backlog: zero. Keep it there."[^s66] The latter closes out the interface surface the charter named as the programme's largest single work package.[^s37]

[KOMET](../systems/komet.md) remains readable while the programme completes an archive extraction for customs and audit history; the system is set to be finally switched off on 30 September 2026, closing out seventeen years of productive service. Hypercare crews remain at the three youngest sites for a further two weeks after go-live.[^s67]

Vogelsang's announcement also looked beyond LEUCHTFEUER: once operations have settled, the company will discuss what it builds on top of QUAYSTONE, and she confirmed customer-facing staff's rumours of a portal are "roughly right," with more detail due in April 2026 from the team that owns it (see Open Points).[^s68] She closed the announcement by calling the rollout "the largest change this company's operations have seen in a generation."[^s69]

## Change Log
- 2024-05-14: Charter issued as Version 1.0, approved by the Lenkungsausschuss at its session of 7 May 2024.[^s28]
- 2025-01-20: Version 1.0 superseded in full by Revision B, approved by circular resolution of 17 January 2025.[^s41]
- 2024-05-14: Milestone plan (Version 1.0) targeted the SEAGULL pilot cutover at Bremen-Walle for August 2024, a pilot hold-point review for September 2024, full estate go-live for 1 October 2024, and KOMET decommissioning for the fourth quarter of 2024.[^s33]
- 2025-01-20: Revision B resets the milestone plan to a SEAGULL cutover of 22–23 February 2025, a hold-point review in April 2025, full estate go-live by 30 June 2025, and KOMET decommissioning in the fourth quarter of 2025.[^s44]
- 2024-03-05: The approved programme budget stood at EUR 1.8 million.[^s5][^s16]
- 2025-01-20: The Geschäftsführung increased the approved budget to EUR 2.4 million, on the committee's escalation.[^s45]
- 2024-03-05: QUAYSTONE's persistence layer was decided (D-4) to run on KorallenDB.[^s9][^s35]
- 2025-01-20: The persistence layer moved to BasaltDB, per a circular resolution of 13 January 2025.[^s46]
- 2025-02-10: The Lenkungsausschuss ratified charter Revision B as decision D-12, incorporating D-9 through D-11, confirming its earlier circular-resolution approval of 17 January 2025.[^s55]
- 2024-05-14: The charter's fourth principal risk was timeline ambition — no slack between the pilot hold point and the full-estate date, accepted in exchange for a shorter dual-running period.[^s37]
- 2025-01-20: Revision B reframes the fourth risk as dual running — a longer period of running two systems in parallel, accepted in exchange for per-site go/no-go quality gates.[^s47]
- 2025-06-30: Decision LA-2025-07 postpones the rollout to the remaining sites to the first quarter of 2026; the per-site go/no-go criteria are unchanged.[^s59]
- 2026-03-17: Full estate go-live achieved — every Blauwal warehouse site is live on QUAYSTONE.[^s63]
- 2026-03-20: KOMET's decommissioning target moves to 30 September 2026 (from Revision B's fourth quarter of 2025), pending completion of the customs/audit archive extraction.[^s67]
- 2026-03-20: Final programme spend closes at EUR 2.62 million against the EUR 2.4 million budget — an overrun attributed to the customs certification delay and extended dual-running.[^s65]

## Open Points

### Article master data cleansing
id: op-article-master-data-cleansing
- 2024-03-05: Sabine Krüger flagged the state of the article master data as the operational risk she loses sleep over — years of parallel maintenance in KOMET have left duplicate article records across the sites, and migrating duplicates would multiply them. The meeting agreed the master data must be cleansed before the pilot cutover, not patched afterwards (action AP-1, owner Sabine Krüger).[^s11]
- 2024-03-19: Cleansing is under way; the scope of duplicates has proven considerable and has grown over years, especially where sites created articles in parallel. It remains a mandatory precondition for the pilot cutover, and Sabine Krüger now reports progress to the steering committee monthly with KPIs — a priority the committee underlined unanimously.[^s20]
- 2025-01-20: Revision B reconfirms that cleansing has progressed but remains a hard precondition for the pilot cutover, tracked monthly until closed.[^s47]
- 2025-02-10: Cleansing stands at roughly two thirds complete, with the remainder concentrated in the two sites with the oldest parallel maintenance history; the trajectory supports the pilot date. The committee kept AP-1 open with its monthly reporting rhythm and renewed its status as a hard precondition.[^s56]
- 2025-06-30: Reported complete — the remaining duplicate stock from the two oldest sites is cleared, and new article records are now centrally reviewed so duplicates cannot recur. Action AP-1 is closed and dropped from monthly reporting; the Lenkungsausschuss thanked Sabine Krüger explicitly, noting the point had been the programme's most persistent for over fifteen months.[^s61]

### Customs interface certification
id: op-customs-interface-certification
- 2025-06-30: Certification of the customs interface by the responsible authority remains outstanding and, per current information, is not expected before autumn 2025; Marek Duszek owns monthly follow-up reporting to the committee on it.[^s58][^s62]
- 2026-03-20: With the full estate live and every go/no-go gate cleared without a waiver, Vogelsang's go-live announcement retrospectively counts "the quarter we gave the customs certification" among the corrections that turned out to be worth it — suggesting certification is now in place, though the announcement gives no explicit certification date.[^s64]

### Portal built on QUAYSTONE
id: op-portal-on-quaystone
- 2026-03-20: Vogelsang's go-live announcement says the company will discuss what it builds "on top of" QUAYSTONE once operations have settled; customer-facing staff's rumours of a portal are "roughly right," with more detail due in April 2026 from the team that owns it.[^s68]
- 2026-04-08: The rumoured portal materialises as [SEAGULL](seagull.md), Blauwal's new customer self-service portal programme, constituted by a Geschäftsführung decision of 24 March 2026 and kicked off on 8 April 2026 under product owner [Yasmin Okafor](../persons/yasmin-okafor.md) — a separate initiative from Projekt LEUCHTFEUER, with its own mandate, budget line, and team, that reuses the pilot's released codename.[^s70]

### Cutover strategy for remaining sites
id: op-cutover-strategy
- 2024-03-05: Left open whether the sites after the [SEAGULL](seagull-2024-25-quaystone-pilot.md) pilot follow one at a time or in a single coordinated cutover. Petra Vogelsang will circulate a written cutover-strategy proposal in early April 2024 (action AP-3) for the steering committee to decide.[^s12]
- 2024-03-19: Reconfirmed as a task: Petra Vogelsang is to bring the cutover strategy to the steering committee for decision at the May meeting.[^s21]
- 2024-04-02: Petra Vogelsang circulated her written cutover-strategy proposal (action AP-3) ahead of the steering committee.[^s22] She argues a single, big-bang cutover of the whole estate would be reckless for the company (see [Petra Vogelsang](../persons/petra-vogelsang.md) for her full reasoning).[^s23] Her concrete proposal: [SEAGULL](seagull-2024-25-quaystone-pilot.md) sails first exactly as already decided, then a hold point during which no second site is touched until the pilot has run stably and its lessons are documented;[^s24] the remaining sites then migrate in convoys of at most two, each gated by its own go/no-go decision on data readiness, trained crew, and interface tests, with an unready site deferred to the next convoy;[^s25] and the cutover date follows the readiness of the sequence rather than a fixed calendar.[^s26] Comments on the proposal were due in writing by 12 April 2024, with the decision remaining the steering committee's.[^s27]
- 2024-05-07: Resolved — the Lenkungsausschuss adopted Vogelsang's proposal: the rollout is phased warehouse by warehouse, SEAGULL first, then a hold point, then the remaining sites in small groups with individual go/no-go decisions on data readiness, trained staff, and interface test results.[^s32]

## See also
- [SEAGULL (2024–25 pilot)](seagull-2024-25-quaystone-pilot.md)
- [SEAGULL (customer portal)](seagull.md)
- [KOMET](../systems/komet.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [MDE — Mobile Data Capture](../abbreviations/mde-mobile-data-capture.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [Jörn Albers](../persons/jorn-albers.md)

## Sources
[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — the programme's purpose (ingested 2026-07-16)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Projekt LEUCHTFEUER — kickoff meeting, minutes — date, chair, minutes-taker, and attendees (ingested 2026-07-16)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — 27 Feb 2024 board decision (ingested 2026-07-16)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists — rationale for replacement (ingested 2026-07-16)
[^s5]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 3 — Budget — EUR 1.8m envelope (ingested 2026-07-16)
[^s6]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — 1 October 2024 go-live target (ingested 2026-07-16)
[^s7]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — SEAGULL pilot at Bremen-Walle (ingested 2026-07-16)
[^s8]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — cutover strategy left open (ingested 2026-07-16)
[^s9]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Decisions — decision D-4 (ingested 2026-07-16)
[^s10]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Action items — next meeting line (ingested 2026-07-16)
[^s11]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate — master data risk and AP-1 (ingested 2026-07-16)
[^s12]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot — AP-3 cutover-strategy proposal (ingested 2026-07-16)
[^s13]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 32-36 — quoted mail of 11 March 2024, EUR 310,000 figure (ingested 2026-07-16)
[^s14]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 38-40 — Duszek's TCO conclusion (ingested 2026-07-16)
[^s15]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Protokoll der Sitzung des Lenkungsausschusses — Projekt LEUCHTFEUER — date, location, chair, minutes-taker, attendees, apologies (ingested 2026-07-16)
[^s16]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 2 — Budget — budget reaffirmed, overrun rule (ingested 2026-07-16)
[^s17]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 4 — Schulungsplanung — training plan, decision LA-2024-02 (ingested 2026-07-16)
[^s18]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 5 — Geräte für die Mobile Datenerfassung (MDE) — 180 devices, decision LA-2024-03 (ingested 2026-07-16)
[^s19]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Aufgaben — next meeting, review period (ingested 2026-07-16)
[^s20]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 6 — Stammdaten (AP-1) — cleansing progress, monthly KPI reporting (ingested 2026-07-16)
[^s21]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Aufgaben — cutover-strategy task for May meeting (ingested 2026-07-16)
[^s22]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 8-9 — proposal circulated as promised at kickoff, ahead of the steering committee (ingested 2026-07-16)
[^s23]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 16-17 — her stance that a big-bang cutover would be reckless (ingested 2026-07-16)
[^s24]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 33-36 — SEAGULL first, then a hold point (ingested 2026-07-16)
[^s25]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 38-42 — remaining sites in convoys of at most two, gated go/no-go (ingested 2026-07-16)
[^s26]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 44-45 — the date follows the sequence, not the reverse (ingested 2026-07-16)
[^s27]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 52-53 — comments due by the 12th, committee retains the decision (ingested 2026-07-16)
[^s28]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 3-6 — charter version, approval, author (ingested 2026-07-16)
[^s29]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 1. Purpose — charter's authoritative status (ingested 2026-07-16)
[^s30]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 3. Objectives — completion criteria (ingested 2026-07-16)
[^s31]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 4. Scope — in-scope and out-of-scope items (ingested 2026-07-16)
[^s32]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 5. Approach — 7 May 2024 adoption of the phased cutover proposal (ingested 2026-07-16)
[^s33]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones — milestone table (ingested 2026-07-16)
[^s34]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 7. Budget — budget management and escalation rule (ingested 2026-07-16)
[^s35]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — KorallenDB decision D-4 corroborated (ingested 2026-07-16)
[^s36]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance — meeting cadence and role ownership (ingested 2026-07-16)
[^s37]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 10. Principal risks — the four named risks (ingested 2026-07-16)
[^s38]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 11. Change control — amendment procedure (ingested 2026-07-16)
[^s41]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 4-5 — Revision B version and approval by circular resolution (ingested 2026-07-16)
[^s42]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 8-11 — revision note: supersedes Version 1.0 in full, decision history in steering minutes (ingested 2026-07-16)
[^s43]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 2. Background — first programme year, Revision B resets the plan (ingested 2026-07-16)
[^s44]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) — reset milestone table (ingested 2026-07-16)
[^s45]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 7. Budget — EUR 2.4m budget, 16 January 2025 decision (ingested 2026-07-16)
[^s46]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform — BasaltDB decision, migration timing (ingested 2026-07-16)
[^s47]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 10. Principal risks (Revision B) — reconfirmed and reframed risks (ingested 2026-07-16)
[^s48]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § Projekt LEUCHTFEUER — steering committee, minutes (extraordinary session in English) — date, location, English-session note, next meeting (ingested 2026-07-16)
[^s49]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 1 — Where the first year actually left us — committee's account of the missed target (ingested 2026-07-16)
[^s50]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — revised KorallenDB licence terms and cost-doubling assessment (ingested 2026-07-16)
[^s51]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited — Gezeitenwerk's BasaltDB first-class support and reference customers (ingested 2026-07-16)
[^s52]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § Decisions — decision D-9, confirmed unanimously (ingested 2026-07-16)
[^s53]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 3 — Re-planned timeline — decision D-10, staffing commitment (ingested 2026-07-16)
[^s54]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 4 — Budget — decision D-11, Brandt's quote (ingested 2026-07-16)
[^s55]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § Decisions — decision D-12 (ingested 2026-07-16)
[^s56]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 5 — Master data (AP-1, standing item) — two-thirds-complete status (ingested 2026-07-16)
[^s57]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § Protokoll — Statusübergabe Pilotbetrieb Lager Bremen-Walle (Projekt LEUCHTFEUER) — date, minutes-taker, attendees, apologies (ingested 2026-07-16)
[^s58]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 5 — Gesamt-Rollout — customs certification, MDE delivery delay, go/no-go rejection (ingested 2026-07-16)
[^s59]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 5 — Gesamt-Rollout — decision LA-2025-07, written-notification commitment (ingested 2026-07-16)
[^s60]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § Aufgaben — next meeting line (ingested 2026-07-16)
[^s61]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 4 — Stammdaten (AP-1) — cleansing complete, AP-1 closed, committee's thanks (ingested 2026-07-16)
[^s62]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § Aufgaben — Duszek's customs-certification follow-up ownership (ingested 2026-07-16)
[^s63]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 9-11 — full estate go-live, last convoy, go/no-go without waiver (ingested 2026-07-16)
[^s64]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 15-21 — timeline honesty: well-over-a-year-late framing, corrections list, arrive-late-not-wrong trade (ingested 2026-07-16)
[^s65]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 23-26 — closing budget figures: EUR 2.62m actual vs EUR 2.4m revised budget, overrun causes (ingested 2026-07-16)
[^s66]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 27-33 — quoted status note of Marek Duszek, 12 January 2026: BasaltDB uptime, interface backlog zero (ingested 2026-07-16)
[^s67]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 38-41 — KOMET wind-down: archive extraction, 30 September 2026 switch-off, hypercare at three youngest sites (ingested 2026-07-16)
[^s68]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 42-44 — portal rumour, more detail due April 2026 (ingested 2026-07-16)
[^s69]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 46-52 — closing acknowledgements, "largest change... in a generation" (ingested 2026-07-16)
[^s70]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name — Geschäftsführung decision, kickoff, codename reuse (ingested 2026-07-16)
