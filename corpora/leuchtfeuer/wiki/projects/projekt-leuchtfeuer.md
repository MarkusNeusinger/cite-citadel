---
type: Project
title: Projekt LEUCHTFEUER
description: Blauwal Logistik GmbH's programme to replace its KOMET warehouse management
  system with the QUAYSTONE cloud WMS platform.
resource: raw/2024-03-05-minutes-kickoff.md
tags:
- leuchtfeuer
- blauwal-logistik
- quaystone
- komet
- wms
timestamp: '2026-07-03T17:30:14Z'
---

Projekt LEUCHTFEUER is [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s programme to
replace [KOMET](../systems/komet.md), the warehouse management system (WMS) the company has customised and
patched in-house for many years, with [QUAYSTONE](../systems/quaystone.md), the cloud WMS platform sold by
[Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md) of Hamburg.[^s2] The programme
was constituted at its kickoff meeting on 5 March 2024 at Blauwal's Bremen headquarters, chaired by
[Petra Vogelsang](../persons/petra-vogelsang.md) (Head of IT), who is its programme lead (decision
D-1).[^s1] [Marek Duszek](../persons/marek-duszek.md) (lead architect), [Sabine Krüger](../persons/sabine-kruger.md)
(Head of Warehouse Operations), [Heike Brandt](../persons/heike-brandt.md) (Commercial Director),
[Tomás Iglesias](../persons/tomas-iglesias.md) (Gezeitenwerk account manager), and
[Jonas Petersen](../persons/jonas-petersen.md) (PMO, minutes) also attended.[^s1]

## Why the programme exists

Blauwal's Geschäftsführung (management board) decided on 27 February 2024 to replace KOMET with
QUAYSTONE.[^s2][^s25] KOMET's original vendor no longer exists, so every bug fix, carrier change, and
customs-regulation update lands on Marek Duszek's team alone, with no escalation path.[^s2] Heike Brandt
added the commercial angle: the money Blauwal pays every year merely to keep KOMET's licences and support
contracts alive buys no improvement of any kind, and she committed to put the exact figures in writing for
the steering committee so the business case is documented.[^s2] She did so on 11 March 2024: Blauwal's annual
licence and support costs for KOMET stand at EUR 310,000.[^s7] Marek Duszek's KOMET estate assessment (action
AP-2) was delivered three days early, on 12 March 2024.[^s8] It concluded that migration wins in every
[total cost of ownership](../abbreviations/tco-total-cost-of-ownership.md) (TCO) scenario his team modelled,
including the pessimistic ones where the timeline doubles (see [KOMET](../systems/komet.md) for the
assessment's findings).[^s10][^llm1] At the steering committee's (Lenkungsausschuss) 19 March 2024 meeting,
chaired by Petra Vogelsang and minuted by Sabine Krüger, with Tomás Iglesias sending his regrets, the
committee took favourable note of the assessment and asked that the interface list be kept as a living
document on the project drive (decision LA-2024-01); see [KOMET](../systems/komet.md).[^s11] Its next meeting
is scheduled for 7 May 2024 in Bremen.[^s17] That 7 May 2024 session adopted the phased, warehouse-by-warehouse
cutover approach Petra Vogelsang had proposed; see Timeline and pilot below.[^s28] On 10 June
2024, Brandt followed up with a fuller memorandum to the Lenkungsausschuss quantifying the cost of continuing
to run KOMET, marked provisional pending the internal operations audit.[^s36] She formally retracted that
memorandum on 15 April 2026, after the final 2024–2025 operations audit found its downtime-cost methodology
unsound.[^s48] The licence-cost reality and the vendor situation that justified the migration were unaffected
and confirmed by the same audit, and the programme they justified has in any case already delivered (see
[KOMET](../systems/komet.md) and [Heike Brandt](../persons/heike-brandt.md)).[^s49]

## Objectives

Per the charter, the programme is complete when QUAYSTONE is the productive WMS at every Blauwal warehouse
site and KOMET is decommissioned; no shipment, stock, or article data is lost in migration, with movement
history required for customs and audit purposes retained and retrievable; every affected employee has been
trained before the cutover of their own site; and all external interfaces — enterprise resource planning
(ERP), customs, telematics, customer portals, label printing — run productively against QUAYSTONE.[^s26]

## Scope

The charter also fixes the programme's scope.[^s27] In scope: replacement of the WMS at all warehouse
sites; migration of article, stock, and open-order data; re-connection of all downstream interfaces;
procurement and rollout of new [MDE devices](../objects/mde-device.md); training; and hypercare after each
site's cutover.[^s27] Out of scope: replacement of the ERP; transport management; building automation; and
any process redesign not strictly required by the platform change.[^s27] Scope additions require a
steering-committee decision and a documented budget impact.[^s27]

## Budget

The Geschäftsführung originally approved a programme budget of EUR 1.8 million, covering the QUAYSTONE
licences, implementation services from Gezeitenwerk, internal backfill for the line organisation, training,
and a contingency reserve.[^s3] Heike Brandt was explicit that this is the whole envelope: "If we need more, we go
back to the Geschäftsführung — and nobody in this room wants that meeting."[^s3] At the 19 March 2024 steering
committee meeting she reiterated that exceeding this envelope requires a fresh Geschäftsführung decision and
must be flagged early.[^s12]

Revision B of the charter records that the budget has since grown: the Geschäftsführung approved an increased
programme budget of EUR 2.4 million on 16 January 2025, on the Lenkungsausschuss's escalation, now covering
platform licences, Gezeitenwerk implementation services, internal personnel backfill, training, the
mobile-device rollout, an enlarged interface work package, and a contingency reserve.[^s30] The budget remains
managed by the Commercial Director: any forecast overrun must be escalated to the Lenkungsausschuss before it
is incurred, and a further increase requires a new Geschäftsführung decision.[^s30]

At the 10 February 2025 steering committee session, Heike Brandt reported the consequence of the longer
programme and the enlarged interface package in one number: the original envelope did not hold. On the
committee's escalation, the Geschäftsführung had approved, on 16 January 2025, the increased programme
budget of EUR 2.4 million, which the committee confirmed as decision D-11. Heike had folded the increase
into the charter revision (Revision B, issued 20 January 2025) and reminded the committee that this second
envelope is to be treated as the last one: "There is no third ask in my drawer."[^s40]

At programme close, Heike Brandt's final figures put total programme spend at EUR 2.62 million against the
revised EUR 2.4 million budget — an overrun she flagged to the Geschäftsführung in the autumn of 2025, with
the customs-certification delay and the extended dual-running of the two systems accounting for nearly all of
it.[^s54]

## Change Log — programme budget

- 2024-03-05: EUR 1.8 million approved by the Geschäftsführung. [^s3]
- 2025-01-16 (Revision B): increased to EUR 2.4 million by the Geschäftsführung, on the Lenkungsausschuss's
  escalation. [^s30]
- 2025-02-10 (decision D-11): the Lenkungsausschuss confirmed the increased EUR 2.4 million budget. [^s40]
- 2026-03-20 (programme close): final spend reported at EUR 2.62 million against the EUR 2.4 million budget,
  an overrun flagged to the Geschäftsführung in autumn 2025 and attributed to the customs-certification delay
  and extended dual-running. [^s54]

## Timeline and pilot

The full warehouse estate was originally targeted to go live on QUAYSTONE on 1 October 2024 (decision
D-3).[^s4] Tomás Iglesias confirmed Gezeitenwerk can staff the implementation to that date, provided the
master data arrives clean and the interface specifications are frozen by early summer.[^s4] The pilot runs at
the Bremen-Walle warehouse under the working codename [SEAGULL](seagull.md), originally targeted to start in
the third quarter of 2024 (decision D-2).[^s4] Walle was chosen deliberately: it is mid-sized, sits close to
headquarters, and [Jörn Albers](../persons/jorn-albers.md)'s team there is regarded as the most change-friendly
crew in the estate.[^s4]

The Lenkungsausschuss adopted the phased, warehouse-by-warehouse approach Petra Vogelsang proposed in April,
at its 7 May 2024 session: the SEAGULL pilot proceeds as decided and is followed by a hold point, then the
remaining sites cut over in small groups with individual go/no-go decisions on data readiness, trained staff,
and interface test results, with a site that is not ready waiting for the next group.[^s28]

At an extraordinary steering committee session on 10 February 2025, chaired by Petra Vogelsang and conducted
in English at Tomás Iglesias's request, the chair opened by naming the reasons the original 1 October 2024
go-live target was missed in the detail the committee now understood, rather than in hindsight generalities:
the interface work package proved far larger in effort than in count, and the master-data cleansing —
correctly made a precondition — could not responsibly have been declared done in the summer. The committee
agreed the honest response was a re-planned programme, not a re-dated slide.[^s37]

The programme's first year showed this original milestone plan to have been too ambitious for the interface
and master-data reality of the estate, so Revision B of the charter resets the plan on measured ground.[^s25]
Its milestone table records Revision B's own approval for 17 January 2025 (already granted), sets the SEAGULL
pilot cutover at Bremen-Walle for 22–23 February 2025, a pilot hold-point review for April 2025, the
full-estate go-live for 30 June 2025, and KOMET decommissioning and programme close for Q4 2025.[^s29] The
phased, warehouse-by-warehouse approach adopted at the 7 May 2024 session remains unchanged.[^s28]

At a status handover session at Bremen-Walle on 30 June 2025 — the date originally set for full-estate
go-live — Petra Vogelsang reported on the remaining sites and presented a decision proposal on the schedule:
certification of the customs interface by the responsible authority remained outstanding and, per current
information, was not expected before autumn 2025, and delivery of the MDE devices for three follow-up sites
was delayed on the supplier's side.[^s44] Holding the original go-live date for the remaining sites would have
required abandoning the agreed Go/No-Go criteria, which the committee unanimously rejected.[^s44] **Decision
LA-2025-07:** the rollout to the remaining sites is postponed to the first quarter of 2026; the per-site
Go/No-Go criteria and the small-group staggering remain unchanged, and the programme lead is to inform the
Geschäftsführung and site leads in writing by 4 July 2025.[^s44]

The full warehouse estate went live on QUAYSTONE on 17 March 2026: the last convoy of sites crossed over that
morning and passed its go/no-go gates without a waiver.[^s50] Hypercare crews remained at the three youngest
sites for a further two weeks from the go-live date.[^s51] In her go-live announcement to all staff, Vogelsang
was explicit that the programme arrived over a year after the date the first charter had promised, and framed
each correction along the way — the re-planned timeline, the persistence-layer change, the SEAGULL hold
point, and the quarter given to customs certification — as a deliberate trade of calendar time for
correctness that she said she would make every time, adding that she had said as much back in the programme's
first month.[^s52]

## Change Log — programme milestones

- 2024-03-05: SEAGULL pilot targeted for Q3 2024 (decision D-2); full-estate go-live targeted for 1 October
  2024 (decision D-3). [^s4]
- 2025-01-20 (Revision B): SEAGULL pilot cutover set for 22–23 February 2025; pilot hold-point review for
  April 2025; full-estate go-live reset to 30 June 2025; KOMET decommissioning and programme close targeted
  for Q4 2025. [^s29]
- 2025-02-10 (decision D-10): the Lenkungsausschuss confirmed the Revision B timeline; Tomás Iglesias
  committed Gezeitenwerk staffing to these dates. Jörn Albers asked that the pilot weekend avoid the
  month-end peak, which the chosen 22–23 February weekend does; the chair reaffirmed the standing principle
  that the date serves the sequence — any site failing its go/no-go criteria waits for the next group. [^s38]
- 2025-06-30 (decision LA-2025-07): rollout to the remaining sites postponed to Q1 2026, after the
  customs-interface certification and the MDE-device delivery for three sites both slipped; Go/No-Go
  criteria and staggered approach unchanged. [^s44]
- 2026-03-20: full-estate go-live completed 17 March 2026, over a year after the original 1 October 2024
  target; the last convoy of sites cleared its go/no-go gates without a waiver. [^s50]
- 2026-03-20: KOMET's final switch-off set for 30 September 2026 — later than Revision B's Q4 2025 target —
  after completion of the archive extraction required for customs and audit history. [^s53]

## Platform database

On Tomás Iglesias's recommendation, the kickoff meeting decided that the QUAYSTONE deployment would run on
[KorallenDB](../systems/korallendb.md) (decision D-4).[^s5] Marek Duszek argued against this choice at some
length and asked that his dissent be recorded in the minutes; he stated he would not re-litigate the point
outside the steering committee.[^s5] On 12 March 2024 he put his reasons in writing, naming
[BasaltDB](../systems/basaltdb.md) as the platform he would have chosen instead.[^s9]

The Lenkungsausschuss later reversed this decision: per a circular resolution of 13 January 2025, recorded in
the charter's Revision B, QUAYSTONE's persistence layer now runs on BasaltDB instead — the platform Marek
Duszek had argued for from the start — with the migration executed before the pilot cutover so the pilot runs
on the target stack from its first day.[^s31]

At the 10 February 2025 steering committee session, Marek presented his team's assessment of KorallenDB's
vendor's revised licence terms, announced in December 2024: per-core pricing plus an audit clause granting
the vendor scheduled access to usage metering. Heike Brandt confirmed the commercial view that, under the
revised terms, the five-year cost of the persistence layer roughly doubles, with an audit overhead nobody
had priced. Tomás Iglesias confirmed that Gezeitenwerk supports QUAYSTONE on BasaltDB as a first-class
deployment and that two reference customers run it in production at comparable volume. The committee
confirmed the reversal to BasaltDB unanimously (decision D-9), noting for the record that Marek Duszek's
dissent on the original choice had been recorded in March 2024 and that the committee reversed that choice
on commercial grounds that arose since.[^s39]

## Training rollout

At the 19 March 2024 steering committee meeting, Sabine Krüger presented the training plan: around 640
employees across the shop-floor and office-based functions need to be trained on QUAYSTONE.[^s13] The plan
calls for two-day in-person training sessions per site plus training materials in German, starting four
weeks before each site's cutover so the training does not go stale, with a monthly refresher session set up
for temporary staff (Springer) and new hires.[^s13] The steering committee approved the training plan as
presented (decision LA-2024-02).[^s13]

## Field devices

QUAYSTONE requires new [MDE devices](../objects/mde-device.md) for mobile data capture; Blauwal's existing
devices are incompatible with the new platform and some have been discontinued for years.[^s14] The steering
committee approved the procurement of 180 MDE devices on 19 March 2024 (decision LA-2024-03).[^s14]

## Cutover strategy proposal (AP-3)

On 2 April 2024, ahead of the steering committee, [Petra Vogelsang](../persons/petra-vogelsang.md)
circulated her promised AP-3 cutover-strategy proposal to the programme list, framed explicitly as her
personal view rather than a committee position, restating the open question of whether the remaining sites
follow QUAYSTONE one at a time or via a single coordinated cutover weekend.[^s18] She stated her opposition
directly: she considers a single, coordinated big-bang cutover of the remaining warehouse estate reckless
for the company and said she would argue against it in every room where it comes up, reasoning that Blauwal
moves physical goods through physical halls, so a warehouse that loses its system leaves trucks queuing and
delivery promises broken.[^s19] She recalled that in 1994 the first Ariane 5 rocket broke up forty seconds
into its maiden flight because one untested piece of software forced a 64-bit value into a 16-bit slot, and
used the incident as an analogy for the risk of a single, untested, all-at-once cutover.[^s20][^llm2]

Her proposal has three parts: the [SEAGULL](seagull.md) pilot proceeds exactly as decided and is followed by
a hold point — no second site is touched until the pilot has run stably and its lessons are written down;
the remaining sites then cut over warehouse by warehouse in small convoys of at most two, each cleared by
its own go/no-go decision on data readiness, trained staff, and interface tests, with any site that is not
ready waiting for the next convoy; and the calendar yields to the sequence, not the reverse — if holding the
line on quality costs time, the programme pays in calendar time rather than force a site across the
line.[^s21] She acknowledged that the single-cutover camp has real arguments — one migration window, one set
of interface freezes, less time running two systems in parallel — but said she had weighed them and remained
opposed, while committing to execute the steering committee's decision loyally if it goes against
her.[^s22] She asked for comments in writing by 12 April 2024, so the committee would see the disagreements
and not only the conclusions, ahead of its 7 May 2024 decision.[^s23] The Lenkungsausschuss adopted this
proposal at its 7 May 2024 session (see Timeline and pilot and Governance).[^s28]

## Governance

The charter formalises the programme's governance.[^s32] The Lenkungsausschuss meets monthly and is the
programme's decision body, with German as its working language and its minutes authoritative.[^s32]
Programme lead Petra Vogelsang chairs the committee and reports to it; lead architect Marek Duszek owns
technical decisions within the platform frame the committee sets; Sabine Krüger (warehouse operations) owns
master data and training; Commercial Director Heike Brandt owns budget and vendor commercials; PMO member
Jonas Petersen keeps the record.[^s32] Gezeitenwerk's account manager, Tomás Iglesias, attends as a guest
without vote.[^s32]

The charter is the single authoritative statement of what the programme is, what it delivers, by when, with
what money, and under whose governance; where a slide, a mail, or a hallway agreement disagrees with it, the
charter wins until the Lenkungsausschuss amends it.[^s24] It is amended only by Lenkungsausschuss decision,
recorded in its minutes, and re-issued by the PMO as a new version; superseded versions are withdrawn from
circulation.[^s34] Version 1.0 of the charter, dated 14 May 2024, has since been superseded in full by
Revision B, dated 20 January 2025 and authored by Jonas Petersen (PMO) on behalf of the programme lead
following the Lenkungsausschuss's approval via circular resolution of 17 January 2025; figures and dates that
Revision B replaces are deliberately not restated in it, and the decision history behind each change lives in
the steering-committee minutes.[^s35] At its 10 February 2025 session the Lenkungsausschuss ratified charter
Revision B in full, incorporating decisions D-9 through D-11 (decision D-12).[^s41]

The Lenkungsausschuss's 10 February 2025 session was itself an extraordinary one, conducted in English at
guest Tomás Iglesias's request; the German-language protokoll series was noted to resume at the next
session, the Lenkungsausschuss meeting of 11 March 2025 in Bremen.[^s42]

The steering committee met again at Bremen-Walle on 30 June 2025, for a status handover on the SEAGULL pilot
chaired by Petra Vogelsang and minuted by Sabine Krüger, with Marek Duszek attending by video; Heike Brandt
and Tomás Iglesias were excused.[^s45] Its next meeting is scheduled for 9 September 2025 in Bremen.[^s46]

## Principal risks

Revision B of the charter records four principal programme risks.[^s33] Interface surface: confirmed as the
largest work package by the programme's first year, with each connection carrying explicit conversion review
and test time in the Revision B plan.[^s33] Master data quality: cleansing has progressed but remains a hard
precondition for the pilot cutover, and is tracked monthly until closed.[^s33] Key-person dependency:
knowledge of KOMET internals remains concentrated in very few people until decommissioning.[^s33] Dual
running: the longer programme means a longer period of running two systems in parallel, a risk the
Lenkungsausschuss accepts consciously in exchange for per-site go/no-go quality gates.[^s33]

By January 2026, per Marek Duszek's status note quoted in Vogelsang's go-live announcement, BasaltDB had run
47 consecutive weeks without an unplanned restart and the interface backlog stood at zero — against the
interface surface this section names as the programme's largest work package.[^s55]

## Programme close

In her 20 March 2026 go-live announcement to all staff, Vogelsang thanked the warehouse crews who trained in
the evenings, the interface team that "re-tested until the conversions were boring," Sabine Krüger's
master-data campaign — "fifteen months of unglamorous persistence that made every cutover after Walle quietly
uneventful" — Heike Brandt "for envelopes defended and honestly reported," Marek Duszek "for dissent in
writing and delivery without sulking," and Gezeitenwerk's team for having "sat in our halls on their
weekends." She called Projekt LEUCHTFEUER "the largest change this company's operations have seen in a
generation."[^s56]

## Open Points

### Article master data cleansing
id: op-article-master-data-cleansing
- 2024-03-05: raised by Sabine Krüger; years of parallel maintenance in KOMET have left duplicate article
  records across the sites, and migrating duplicates would multiply them. The meeting agreed the master
  data must be cleansed before the pilot cutover, not patched afterwards (action AP-1, owner Sabine Krüger,
  due before the pilot cutover). [^s6]
- 2024-03-19: Sabine Krüger reported the cleansing review under way; the volume of duplicates is significant
  and has grown over years, especially where sites created article records in parallel. The steering
  committee unanimously underlined the priority of this point and will now receive monthly KPI reports on
  progress. [^s15]
- 2025-02-10: Sabine Krüger reported the cleansing roughly two thirds complete — about two thirds of the
  duplicate article records identified across the estate have been merged or retired, with the remainder
  concentrated in the two sites with the oldest parallel-maintenance history. The trajectory supports the
  pilot date. The committee kept AP-1 open with its monthly reporting rhythm and renewed its status as a
  hard precondition: no pilot cutover before Walle's slice of the cleansing is finished. [^s43]
- 2025-06-30: resolved; Sabine Krüger reported the article master data cleansing complete — the residual
  duplicates left in May from the two oldest sites are cleansed, and maintenance is now changed so new
  article records are centrally checked and duplicates cannot recur. AP-1 is closed and removed from monthly
  reporting; the steering committee thanked Sabine Krüger, noting this was the most persistent point of the
  programme, open for over fifteen months. [^s47]

### Customs interface certification
id: op-customs-interface-certification
- 2025-06-30: raised; certification of the customs interface by the responsible authority is outstanding
  and, per current information, not expected before autumn 2025 — a contributing reason for postponing the
  remaining-sites rollout to Q1 2026 (decision LA-2025-07). Marek Duszek owns a monthly follow-up report,
  ongoing. [^s44]
- 2026-03-20: resolved; the full warehouse estate went live on QUAYSTONE on 17 March 2026, with the last
  convoy of sites clearing its go/no-go gates without a waiver — Vogelsang's go-live announcement does not
  report the customs-interface certification as outstanding and counts the quarter given to it among the
  corrections that "turned out to be worth it." [^s50]

### Post-pilot cutover strategy
id: op-post-pilot-cutover-strategy
- 2024-03-05: left open; whether the sites after the SEAGULL pilot follow one warehouse at a time or via a
  single coordinated cutover was not decided — opinions in the room differed and the chair declined to
  force the question. Petra Vogelsang will circulate a written cutover-strategy proposal in early April
  2024 (action AP-3), for the steering committee to decide. [^s4]
- 2024-03-19: still open; Petra Vogelsang's cutover-strategy proposal (action AP-3) is now due for decision
  at the steering committee's next meeting, 7 May 2024. [^s16]
- 2024-04-02: Petra Vogelsang circulated her cutover-strategy proposal (action AP-3) to the programme list —
  a phased, warehouse-by-warehouse rollout in small convoys after a SEAGULL hold point, opposing a single
  coordinated cutover (see Cutover strategy proposal above) — and asked for written comments by 12 April
  2024, ahead of the steering committee's 7 May 2024 decision. [^s21][^s23]
- 2024-05-07: resolved; the Lenkungsausschuss adopted Petra Vogelsang's phased, warehouse-by-warehouse
  cutover proposal at its 7 May 2024 session — the SEAGULL pilot proceeds as decided and is followed by a
  hold point, then the remaining sites cut over in small groups with individual go/no-go decisions on data
  readiness, trained staff, and interface test results, with the calendar yielding to the sequence. [^s28]

## See also

- [KOMET](../systems/komet.md)
- [QUAYSTONE](../systems/quaystone.md)
- [SEAGULL](seagull.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [TCO — Total Cost of Ownership](../abbreviations/tco-total-cost-of-ownership.md)
- [MDE device](../objects/mde-device.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 3-11 (ingested 2026-07-03)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-07-03)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 3 — Budget (ingested 2026-07-03)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-07-03)
[^s5]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-07-03)
[^s6]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate (ingested 2026-07-03)
[^s7]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 32-36 (ingested 2026-07-03)
[^s8]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 7-8 (ingested 2026-07-03)
[^s9]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-07-03)
[^s10]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 38-40 (ingested 2026-07-03)
[^s11]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), lines 1-21 (ingested 2026-07-03)
[^s12]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 2 — Budget (ingested 2026-07-03)
[^s13]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 4 — Schulungsplanung (ingested 2026-07-03)
[^s14]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 5 — Geräte für die Mobile Datenerfassung (MDE) (ingested 2026-07-03)
[^s15]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 6 — Stammdaten (AP-1) (ingested 2026-07-03)
[^s16]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Aufgaben (ingested 2026-07-03)
[^s17]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), lines 82-83 (ingested 2026-07-03)
[^s18]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 8-14 (ingested 2026-07-03)
[^s19]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 16-22 (ingested 2026-07-03)
[^s20]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 24-29 (ingested 2026-07-03)
[^s21]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 33-45 (ingested 2026-07-03)
[^s22]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 47-50 (ingested 2026-07-03)
[^s23]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 52-53 (ingested 2026-07-03)
[^s24]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 1. Purpose (ingested 2026-07-03)
[^s25]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 2. Background (ingested 2026-07-03)
[^s26]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 3. Objectives (ingested 2026-07-03)
[^s27]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 4. Scope (ingested 2026-07-03)
[^s28]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 5. Approach (ingested 2026-07-03)
[^s29]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 6. Milestones (Revision B) (ingested 2026-07-03)
[^s30]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 7. Budget (ingested 2026-07-03)
[^s31]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 8. Platform (ingested 2026-07-03)
[^s32]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance (ingested 2026-07-03)
[^s33]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 10. Principal risks (Revision B) (ingested 2026-07-03)
[^s34]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 11. Change control (ingested 2026-07-03)
[^s35]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 1-11 (ingested 2026-07-03)
[^s36]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), § 1. Retraction (ingested 2026-07-03)
[^s37]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 1 — Where the first year actually left us (ingested 2026-07-03)
[^s38]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 3 — Re-planned timeline (ingested 2026-07-03)
[^s39]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 2 — Database decision, revisited (ingested 2026-07-03)
[^s40]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 4 — Budget (ingested 2026-07-03)
[^s41]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § Decisions (ingested 2026-07-03)
[^s42]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 1-11 (ingested 2026-07-03)
[^s43]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 5 — Master data (AP-1, standing item) (ingested 2026-07-03)
[^s44]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 5 — Gesamt-Rollout (ingested 2026-07-03)
[^s45]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 3-9 (ingested 2026-07-03)
[^s46]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), line 73 (ingested 2026-07-03)
[^s47]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 4 — Stammdaten (AP-1) (ingested 2026-07-03)
[^s48]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), § 2. Reason (ingested 2026-07-03)
[^s49]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), § 4. What this retraction does not touch (ingested 2026-07-03)
[^s50]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 9-10 (ingested 2026-07-03)
[^s51]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), line 40 (ingested 2026-07-03)
[^s52]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 14-20 (ingested 2026-07-03)
[^s53]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 37-39 (ingested 2026-07-03)
[^s54]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 22-25 (ingested 2026-07-03)
[^s55]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 26-32 (ingested 2026-07-03)
[^s56]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 45-51 (ingested 2026-07-03)
[^llm1]: LLM - model knowledge, not from a raw file (added 2026-07-03)
[^llm2]: LLM - Vogelsang dates this incident to 1994; the Ariane 5 Flight 501 maiden-flight failure actually occurred on 4 June 1996 (added 2026-07-03)
