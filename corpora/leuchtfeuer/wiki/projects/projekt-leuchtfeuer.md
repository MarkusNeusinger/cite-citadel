---
type: Project
title: Projekt LEUCHTFEUER
description: Blauwal Logistik GmbH's programme to replace its legacy KOMET warehouse
  management system with the QUAYSTONE cloud WMS platform.
tags:
- logistics
- warehouse-management
- programme
resource: raw/2024-03-05-minutes-kickoff.md
timestamp: '2026-08-28T23:49:00Z'
citadel_version: 0.6.0
---

Projekt LEUCHTFEUER is [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s
programme to replace [KOMET](../systems/komet.md), its in-house-customised warehouse management
system (WMS), with [QUAYSTONE](../systems/quaystone.md), the cloud WMS platform sold by
[Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md).[^s1] The programme
was constituted at a kickoff meeting on 5 March 2024 at Blauwal's headquarters in Bremen, chaired
by [Petra Vogelsang](../persons/petra-vogelsang.md) (Head of IT), who is also the programme lead
(decision D-1).[^s8][^s6]

Jonas Petersen (PMO) issued the programme's charter on behalf of the programme lead: version 1.0
on 14 May 2024, superseded in full by Revision B, approved by the Lenkungsausschuss by circular
resolution of 17 January 2025.[^s31] Figures and dates Revision B replaces are deliberately not
restated in the charter itself; the decision history behind each change instead lives in the
steering-committee minutes, which remain authoritative for how and when each change was
decided.[^s31] The charter states it is the single authoritative statement of what the programme
is, will deliver, by when, with what money, and under whose governance — and that where a slide, a
mail, or a hallway agreement disagrees with it, the charter wins until the Lenkungsausschuss amends
it.[^s32]

## Why the programme exists

Blauwal's executive management (Geschäftsführung) decided on 27 February 2024 to replace KOMET
with QUAYSTONE.[^s1] KOMET's original vendor no longer exists, so every bug fix, carrier change,
and customs-regulation update falls to [Marek Duszek](../persons/marek-duszek.md)'s team alone,
with no escalation path.[^s1] [Heike Brandt](../persons/heike-brandt.md) (Commercial Director)
added that the money Blauwal pays every year merely to keep KOMET's licences and support contracts
alive buys no improvement; she committed to putting the exact figures in writing for the steering
committee so the business case is documented rather than anecdotal.[^s1] She kept that commitment
on 11 March 2024: KOMET's annual licence and support contracts cost EUR 310,000, for a system
whose vendor "has not existed for seven years."[^s9]

Marek Duszek's written estate assessment (action AP-2), delivered on 12 March 2024, found KOMET
running across eleven warehouses with no two installations alike, and produced Blauwal's first
complete inventory of its downstream interfaces — 27 systems in all.[^s10][^s11] Marek judges that
interface migration, not the KOMET-to-QUAYSTONE software swap itself, to be the programme's real
technical challenge; see [KOMET](../systems/komet.md) for the inventory and his customs-interface
unit-conversion caution.[^s11]

## Objectives

The charter states the programme is complete when: QUAYSTONE is the productive WMS at every
Blauwal warehouse site and KOMET is decommissioned; no shipment, stock, or article data is lost in
migration, with the movement history required for customs and audit purposes retained and
retrievable; every affected employee has been trained before the cutover of their own site; and
all external interfaces — ERP, customs, telematics, customer portals, label printing — run
productively against QUAYSTONE.[^s33]

## Scope

In scope: replacing the WMS at all warehouse sites, migrating article, stock, and open-order data,
re-connecting all downstream interfaces, procuring and rolling out new mobile data-entry devices,
training, and hypercare after each site's cutover.[^s34] Out of scope: replacing the ERP, transport
management, building automation, and any process redesign not strictly required by the platform
change; a scope addition requires a steering-committee decision and a documented budget
impact.[^s35]

## Budget

The Geschäftsführung approved a programme budget of EUR 1.8 million, covering the QUAYSTONE
licences, implementation services from Gezeitenwerk, internal backfill for the line organisation,
training, and a contingency reserve.[^s3] Heike Brandt was explicit that this is the whole
envelope: "If we need more, we go back to the Geschäftsführung — and nobody in this room wants
that meeting."[^s3]

At the steering committee meeting on 19 March 2024 Heike Brandt restated this framework and stated
explicitly that exceeding it requires a fresh Geschäftsführung decision, to be flagged early
rather than after the fact.[^s14]

The escalation Brandt described came to pass: the Geschäftsführung approved an increased
programme budget of EUR 2.4 million on 16 January 2025, on the committee's escalation, now
covering platform licences, Gezeitenwerk's implementation services, internal personnel backfill,
training, the mobile-device rollout, an enlarged interface work package, and a contingency
reserve.[^s46] The Lenkungsausschuss confirmed this increase as decision D-11 at its 10 February
2025 steering session.[^s59] Heike Brandt had by then folded the increase into charter Revision B,
issued by the PMO on 20 January 2025, and told the committee the second envelope is to be treated
as the last one: "There is no third ask in my drawer."[^s60]

The charter formalizes this framework: the budget is managed by the Commercial Director, and any
forecast overrun must be escalated to the Lenkungsausschuss before it is incurred, and a further
increase requires a new decision of the Geschäftsführung.[^s36]

The go-live announcement of 20 March 2026 puts the programme's final, actual spend at EUR 2.62
million against that EUR 2.4 million envelope — an overrun Heike Brandt flagged to the
Geschäftsführung in the autumn of 2025, with documented causes: the customs certification delay
and the extended dual-running of KOMET and QUAYSTONE account for nearly all of it.[^s90]

## Timeline and pilot

The kickoff meeting set the headline target: the full warehouse estate goes live on QUAYSTONE on
1 October 2024 (decision D-3).[^s6] [Tomás Iglesias](../persons/tomas-iglesias.md) of Gezeitenwerk
confirmed his company can staff the implementation to that date, provided the master data arrives
clean and the interface specifications are frozen by early summer.[^s4]

The pilot will run at the Bremen-Walle warehouse under the working codename SEAGULL, starting in
the third quarter of 2024 (decision D-2).[^s6] Walle was chosen deliberately: it is mid-sized, it
sits close to headquarters, and [Jörn Albers](../persons/jorn-albers.md)'s team there is regarded
as the most change-friendly crew in the estate.[^s4]

How the remaining sites follow the pilot — one warehouse at a time, or a single coordinated
cutover of everything at once — was left open at the kickoff; opinions in the room differed and
the chair declined to force the question.[^s4]

At the steering committee meeting on 19 March 2024, Jörn Albers pledged his site team's full
support for the pilot but asked that picking capacity be planned realistically during the
changeover weeks and that peak loads be kept out of the pilot.[^s15] Findings from the pilot will
be reported to the steering committee in a handover protocol (Übergabeprotokoll) before further
sites follow.[^s15]

At its extraordinary steering session of 10 February 2025, the committee named the reason for the
reset plainly: the original 1 October 2024 go-live was missed, chiefly because the interface work
package proved far larger in effort than in count and the master-data cleansing — rightly made a
precondition — could not responsibly have been declared done over the summer; the committee's
chosen response was a re-planned programme, not a re-dated slide.[^s49]

Revision B of the charter — approved by the Lenkungsausschuss by circular resolution of
17 January 2025 — resets the milestone plan: pilot cutover at Bremen-Walle (SEAGULL) for
22–23 February 2025, a pilot hold-point review for April 2025, full-estate go-live for
30 June 2025, and KOMET decommissioning with programme close for Q4 2025.[^s37] The committee
confirmed this re-planned timeline as decision D-10 at the same 10 February 2025 session, where
Tomás Iglesias committed Gezeitenwerk staffing to the new dates.[^s55] Jörn Albers asked that the
pilot weekend avoid the month-end peak, which the chosen 22–23 February weekend does.[^s56] The
chair reminded the committee of the standing principle that the date serves the sequence: any site
failing its go/no-go criteria waits for the next group, whatever that does to the schedule.[^s57]
Sabine Krüger was separately tasked with communicating the pilot weekend to customers with
Walle-routed traffic (action AP-8, due 14 February 2025).[^s58] The charter
attributes the reset to the programme's first year, which showed the original milestone plan too
ambitious for the estate's interface and master-data reality.[^s45] Version 1.0's superseded
dates are recorded in the Change Log, below.[^s48] The charter also confirms the phased,
warehouse-by-warehouse approach was adopted by steering decision at the Lenkungsausschuss's
7 May 2024 session, adopting Vogelsang's April proposal.[^s38]

At a status handover for the Bremen-Walle pilot on 30 June 2025, [Petra Vogelsang](../persons/petra-vogelsang.md)
reported on the remaining sites and put a timeline decision to the group: certification of the
customs interface by the responsible authority remained outstanding, with no expectation before
autumn 2025, and delivery of the MDE devices for three of the remaining sites had slipped on the
supplier's side (see [MDE — Mobile Datenerfassung](../abbreviations/mde-mobile-datenerfassung.md) and
Open Points, below).[^s83] Holding the remaining sites' originally planned go-live date would have
meant giving up the agreed go/no-go criteria, which the group unanimously declined.[^s84] By
**decision LA-2025-07**, the full rollout to the remaining sites is postponed to the **first
quarter of 2026**; the per-site go/no-go criteria are unchanged and the small-group staggering
continues, and the programme leadership will inform the Geschäftsführung and site leads in writing
by 4 July 2025.[^s85]

## Full-estate go-live

On 17 March 2026 the last convoy of sites crossed over and, per Petra Vogelsang's go-live
announcement to all staff, the entire Blauwal warehouse estate went live on
[QUAYSTONE](../systems/quaystone.md), passing its go/no-go gates without a waiver — closing out the
LA-2025-07 target of full-estate go-live in the first quarter of 2026.[^s91] Vogelsang called the
outcome a success in her own words: "Projekt LEUCHTFEUER — after two years and a great deal of
weather — has brought every ship into harbour. Nobody sank. That was always the whole plan." — the
programme lead's own assessment, not independently corroborated in this corpus beyond the
Bremen-Walle pilot's own metrics.[^s91][^llm3]

Vogelsang was explicit that the programme arrived well over a year after the date the first
charter promised (1 October 2024): each correction along the way — the re-planned timeline, the
database change, the pilot's hold point, the quarter given to customs certification — was argued
about at the time and, in her view, worth it. She restated the position she first took in the
programme's first month: "We chose, again and again, to arrive late rather than to arrive
wrong."[^s92]

[Marek Duszek](../persons/marek-duszek.md)'s status note of 12 January 2026, quoted in the go-live
announcement, recorded [BasaltDB](../systems/basaltdb.md) running 47 consecutive weeks without an
unplanned restart and the interface backlog at zero.[^s93]

[KOMET](../systems/komet.md) remains readable while the archive extraction for customs and audit
history is completed; its final switch-off, originally scheduled for 30 September 2026 (further
extending Revision B's Q4 2025 decommissioning target), was brought forward to 31 July 2026 once
that extraction finished earlier than planned.[^s94][^s97] Hypercare crews remain at the three
youngest sites for another two weeks.[^s94]

The programme's final operations audit for 2024–2025, accepted by the Geschäftsführung on 31 March
2026, confirmed the migration business case held up: it was argued on the licence reality and the
vendor situation, both borne out by the audit, and the programme it justified delivered
regardless.[^s102] The same audit closed out a separate, provisional KOMET downtime-cost estimate
Heike Brandt had circulated in June 2024; she formally retracted it on 15 April 2026 (see
[KOMET](../systems/komet.md) and [Heike Brandt](../persons/heike-brandt.md) for that
retraction).[^s103]

Looking beyond the programme, Vogelsang confirmed rumours among customer-facing staff of a further
platform — a customer portal built on top of QUAYSTONE — as "roughly right," with more detail
promised in April 2026 from that project's own team (see Open Points, below).[^s95]

Vogelsang closed the announcement by naming individuals and teams she credited for the outcome:
warehouse crews trained in the evenings, the interface team,
[Sabine Krüger](../persons/sabine-kruger.md)'s master-data campaign,
[Heike Brandt](../persons/heike-brandt.md), [Marek Duszek](../persons/marek-duszek.md), and
[Gezeitenwerk](../organizations/gezeitenwerk-software-gmbh.md)'s implementation partners — calling
it the largest change the company's operations have seen in a generation.[^s96]

## Pilot results

One week after the cutover weekend, [Tomás Iglesias](../persons/tomas-iglesias.md) reported to the
committee that the SEAGULL pilot cutover at Bremen-Walle was complete, calling it a
success.[^s70] It ran exactly along the runbook: the data migration completed inside its window on
the first attempt, with article masters, stock, and open orders all reconciling against the
[KOMET](../systems/komet.md) extracts with zero unexplained differences.[^s71] The
[BasaltDB](../systems/basaltdb.md) stack "behaved impeccably from the first minute," and moving the
persistence layer ahead of the pilot rather than after it "paid for itself this weekend," in Tomás
Iglesias's assessment.[^s72]

Order release at Walle stood still for only four hours over the whole cutover weekend, and Walle
received trucks from 06:00 on Monday, 24 February 2025, as planned; the first inbound wave was
processed on QUAYSTONE without a single escalation to the war room, and scanning throughput and the
pick error rate in the pilot's first week both ran within the promised targets, with the full
metrics pack going to [Jonas Petersen](../persons/jonas-petersen.md) for the project
share.[^s73]

Offering, in his words, "one sentence of pride, clearly labelled as such," Tomás Iglesias called it
the smoothest mid-size WMS cutover Gezeitenwerk has delivered in years — his own assessment of his
company's delivery, not an independently verified benchmark — and credited the outcome chiefly to
[Jörn Albers](../persons/jorn-albers.md)'s implementation crew at Walle.[^s74][^llm2]

What remained open a week after cutover: the hypercare crew stayed on site for the agreed two
weeks, three low-priority defects from the cutover weekend were logged for fixing inside hypercare
(see Open Points, below), and the label-printing interface needed one configuration follow-up for a
carrier format that appears only in month-end volumes (see
[QUAYSTONE](../systems/quaystone.md) Open Points).[^s75] From the vendor side, nothing stood in the
way of the hold-point review targeted for April 2025, and Gezeitenwerk offered to bring a
lessons-learned workshop to Bremen in the last week of March 2025, pending the committee's
schedule.[^s76]

At a status handover on 30 June 2025, four months after cutover, [Jörn Albers](../persons/jorn-albers.md)
and [Sabine Krüger](../persons/sabine-kruger.md) reviewed the cutover weekend for the group from
the site's own perspective: the data takeover was complete with no unresolved differences, and
training together with the MDE practice weeks had left the crew well prepared.[^s77]

> [!CONTRADICTION]
> Gezeitenwerk's week-one report states order release at Walle stood still for only four hours
> over the whole cutover weekend.[^s73] The site's own status handover, four months later, puts
> the operational truth of the weekend at nine hours — order release was fully down from 22:00 on
> Saturday to 07:00 on Sunday; the site had planned for an outage of this length, so no customer
> commitment was broken, and the group should expect this order of magnitude when planning the
> remaining sites.[^s78]

In its first full week of operation on QUAYSTONE, the Walle site processed 12,400 shipments with
an error rate of 0.4% across all transaction types — inside the agreed corridor. Picking
performance returned to its pre-change level in the third week and has run slightly above it
since. The two-week hypercare phase closed on schedule, and the three low-priority defects known
from the cutover weekend are fixed and signed off (see Open Points, below).[^s79]

## Cutover strategy proposal

Ahead of the steering committee's decision on how the remaining warehouses follow the SEAGULL
pilot, [Petra Vogelsang](../persons/petra-vogelsang.md) circulated a written proposal to the whole
programme list on 2 April 2024 — delivered personally, "before the PMO turns it into a slide with
a traffic light on it."[^s22]

She states her position directly, framing it explicitly as her own stance rather than a settled
outcome: "I think a big-bang cutover would be reckless for this company," and she commits to
arguing against a single coordinated cutover wherever it comes up.[^s23] Her reasoning is that
Blauwal's warehouses are physical operations — when one loses its system, trucks queue and
delivery promises are broken — and she illustrates the risk with a maritime analogy: "you don't
take the whole fleet out of harbour at once on a ship class nobody aboard has ever sailed."[^s24]

Vogelsang recounts that the first Ariane 5 rocket broke up in 1994, forty seconds into its maiden
flight, after software reused from its predecessor crammed a 64-bit value into a 16-bit slot that
had never been tested on the new vehicle — "one untested conversion, everything riding on one
launch, no second boat."[^s25] The failure's actual date was 1996; the technical cause she
describes (an unhandled 64-bit-to-16-bit conversion overflow in reused guidance software) matches
the historical record.[^llm1]

Her concrete proposal has three parts:

- **SEAGULL sails alone.** The Bremen-Walle pilot proceeds exactly as already decided, followed by
  a hold point: no second site is touched until the pilot has run stably and its lessons are
  written down.[^s26]
- **Then warehouse by warehouse, in small convoys.** The remaining sites follow in groups of at
  most two, each with its own go/no-go decision on data readiness, trained crew, and interface
  tests; a site that is not ready waits for the next convoy.[^s27]
- **The date serves the sequence, not the other way round.** If holding the line on quality costs
  calendar time, she argues Blauwal should pay in calendar time rather than force a site
  live.[^s28]

She acknowledges the single-cutover camp's arguments — one migration window, one set of interface
freezes, less time running two systems in parallel — but states she remains opposed; if the
steering committee decides against her, she commits to executing the alternative plan
loyally.[^s29] She requested written comments by 12 April 2024, so the committee sees the
disagreements rather than only the conclusions.[^s30]

The Lenkungsausschuss adopted this proposal at its 7 May 2024 session: the rollout proceeds
phased, warehouse by warehouse, with the SEAGULL hold point ahead of any second site and
small-group go/no-go decisions for the rest.[^s38]

## Platform database

Tomás Iglesias presented the two deployment options Gezeitenwerk supports for QUAYSTONE's
persistence layer. On his recommendation, the meeting decided that Blauwal's deployment will run
on [KorallenDB](../systems/korallendb.md) (decision D-4).[^s5] Marek Duszek argued against this
choice at some length and asked that his dissent be recorded in the minutes; he stated he would
not re-litigate the point outside the steering committee.[^s5] A week later he set out his
reasoning in writing: he believes Blauwal should instead have built on
[BasaltDB](../systems/basaltdb.md), whose replication story he considers simpler and whose
operational tooling and licence terms he considers better than KorallenDB's — his professional
opinion, offered for the record rather than to re-open the decision.[^s12]

The Lenkungsausschuss reversed decision D-4 by circular resolution on 13 January 2025: QUAYSTONE's
deployment now runs on [BasaltDB](../systems/basaltdb.md) instead — the platform Marek Duszek
recommended.[^s47] The reversal followed the KorallenDB vendor's revised licence terms, announced
in December 2024: per-core pricing plus an audit clause granting the vendor scheduled access to
Blauwal's own usage metering.[^s50] Heike Brandt's commercial assessment was that the revised terms
roughly double the persistence layer's five-year cost, with an audit overhead nobody had
priced in.[^s51] Tomás Iglesias confirmed that Gezeitenwerk supports QUAYSTONE on BasaltDB as a
first-class deployment, with two reference customers running it in production at comparable
volume.[^s52] The Lenkungsausschuss confirmed the reversal unanimously as decision D-9 at its
10 February 2025 steering session, timing the migration to complete before the pilot cutover so
the pilot runs on the target stack from day one; the minutes note for the record that the lead
architect's dissent on the original choice was recorded in March 2024, and that the committee
reverses that choice on commercial grounds arising since.[^s53]

As a condition of pilot readiness, Marek Duszek required the interface conversion tests to be
re-run against the BasaltDB stack before Gezeitenwerk's cutover runbook — reviewed at v0.9 —
advances to v1.0 (action AP-7, with Gezeitenwerk, due 17 February 2025), which Tomás Iglesias
accepted.[^s54][^s68]

## Training

Blauwal must train roughly 640 employees across its operational (gewerblich) and administrative
(kaufmännisch) areas on QUAYSTONE.[^s16] Training takes the form of two-day in-person sessions per site, with materials in
German; each site's training starts four weeks before that site's cutover so the material does not
go stale, and a monthly refresher session is set up for temporary staff (Springer) and new
hires.[^s16] The steering committee adopted the training plan as presented (decision
LA-2024-02).[^s19] Training of the Walle crew starts, per that plan, four weeks before its
cutover.[^s62] By 30 June 2025, 97 employees at Walle were trained on QUAYSTONE, including
temporary staff (Springer) and new hires taken on that spring; the monthly refresher session has
proven its worth and continues.[^s80]

## Mobile data-capture devices (MDE)

Operating QUAYSTONE requires new mobile data-capture ([MDE](../abbreviations/mde-mobile-datenerfassung.md))
devices: Blauwal's existing handhelds are incompatible with the new platform, and some have been
discontinued by their maker for years.[^s17] The steering committee approved procurement of 180
MDE devices (decision LA-2024-03); the tender is run by Purchasing (Einkauf), with deliveries
staggered per site ahead of each site's cutover.[^s17] [Jörn Albers](../persons/jorn-albers.md)
asked that the pilot's devices reach Bremen-Walle with enough lead time for his team to practice
under real operating conditions.[^s17] Those devices have since been delivered and staged at
Walle.[^s62] By 30 June 2025 Walle's crew — sceptical of the devices at first — would not give
them up, and picking-floor feedback had already driven two improvements to the QUAYSTONE screens
the devices run, which Gezeitenwerk folded into its standard product.[^s81] Delivery of the
devices for three of the remaining sites has since slipped on the supplier's side; Purchasing,
together with Sabine Krüger, will hold an escalation conversation with the supplier on delivery
reliability in July 2025 (see Open Points, below).[^s89]

## Governance

Per the charter, the Lenkungsausschuss meets monthly as the programme's decision body; its working
language is German and its minutes are authoritative.[^s39] Within that frame,
[Petra Vogelsang](../persons/petra-vogelsang.md) chairs the committee and reports as programme
lead; [Marek Duszek](../persons/marek-duszek.md) owns technical decisions within the platform frame
the committee sets; [Sabine Krüger](../persons/sabine-kruger.md) owns master data and training;
[Heike Brandt](../persons/heike-brandt.md) owns budget and vendor commercials; and
[Jonas Petersen](../persons/jonas-petersen.md) (PMO) keeps the record.[^s39] Gezeitenwerk's account
manager, [Tomás Iglesias](../persons/tomas-iglesias.md), attends as a guest without vote.[^s39]

The charter is amended only by decision of the Lenkungsausschuss, recorded in its minutes, and
re-issued by the PMO as a new version; a superseded version is withdrawn from circulation.[^s40]

## Principal risks

The charter names four principal risks. **Master data quality** — cleansing has progressed but
remains a hard precondition for the pilot cutover, and is tracked monthly until closed[^s41] — is
the risk [Sabine Krüger](../persons/sabine-kruger.md) already flagged at kickoff (see Open Points,
below). **Interface surface** — confirmed by the programme's first year as the largest single work
package, with each connection needing explicit conversion review and test time[^s42] — matches
[Marek Duszek](../persons/marek-duszek.md)'s assessment of [KOMET](../systems/komet.md)'s 27
downstream interfaces. **Key-person dependency** — knowledge of KOMET internals remains
concentrated in very few people until decommissioning[^s43] — reflects Marek Duszek's team being
KOMET's sole owners with no escalation path. **Dual running** replaces the charter's earlier
timeline-slack risk: the longer Revision B programme means a longer period of running KOMET and
QUAYSTONE in parallel, a risk the Lenkungsausschuss accepts consciously in exchange for per-site
go/no-go quality gates.[^s44]

## Decisions

- **D-1** — Projekt LEUCHTFEUER is constituted as described; programme lead: Petra Vogelsang.[^s6]
- **D-2** — Pilot at the Bremen-Walle warehouse, working codename SEAGULL, starting Q3 2024.[^s6]
- **D-3** — Target go-live for the full estate: 1 October 2024.[^s6]
- **D-4** — The QUAYSTONE deployment runs on KorallenDB (dissent Duszek, recorded); reversed by
  Lenkungsausschuss circular resolution of 13 January 2025 in favour of BasaltDB, confirmed
  unanimously as decision D-9 at the 10 February 2025 steering session.[^s6][^s47][^s53]
- **D-9** — Confirms the QUAYSTONE persistence layer's move from KorallenDB to BasaltDB (circular
  resolution of 13 January 2025), unanimously at the 10 February 2025 steering session.[^s63]
- **D-10** — Confirmation of the re-planned timeline: pilot cutover at Bremen-Walle
  22–23 February 2025; hold point review April 2025; full-estate go-live 30 June 2025.[^s64]
- **D-11** — Confirmation of the increased programme budget of EUR 2.4 million approved by the
  Geschäftsführung on 16 January 2025.[^s65]
- **D-12** — The committee ratifies charter Revision B, incorporating D-9 through D-11 (approved
  by circular resolution of the Lenkungsausschuss of 17 January 2025, issued by the PMO on
  20 January 2025).[^s66]
- **LA-2024-01** — The steering committee acknowledges Marek Duszek's KOMET estate assessment
  approvingly; the interface list is to be kept as a living document on the project drive.[^s19]
- **LA-2024-02** — The training plan (~640 employees, two-day in-person sessions per site) is
  adopted.[^s19]
- **LA-2024-03** — Procurement of 180 MDE devices is approved.[^s19]
- **LA-2025-07** — The full rollout to the remaining sites is postponed from its Revision-B target
  of 30 June 2025 to the first quarter of 2026; the per-site go/no-go criteria and small-group
  staggering are unchanged.[^s85]

## Meeting record

The kickoff meeting ran 09:30–12:15 at Blauwal's headquarters, room Weser 2.[^s8] Present: Petra
Vogelsang (chair), Marek Duszek, Sabine Krüger, Heike Brandt, Tomás Iglesias (Gezeitenwerk), and
[Jonas Petersen](../persons/jonas-petersen.md) (PMO), who took the minutes; there were no
apologies.[^s8] The next meeting is the
steering committee (Lenkungsausschuss) on 19 March 2024 at 14:00 in Bremen; steering committee
minutes are kept in German.[^s7]

The steering committee (Lenkungsausschuss) met on 19 March 2024, 14:00–16:30, at Blauwal's
headquarters in Bremen, room Weser 2; Petra Vogelsang chaired and opened the session, thanking
attendees for arranging it on short notice, and [Sabine Krüger](../persons/sabine-kruger.md) took
the minutes.[^s13] Present: Petra Vogelsang, [Marek Duszek](../persons/marek-duszek.md), Sabine
Krüger, Heike Brandt, [Jörn Albers](../persons/jorn-albers.md) (Bremen-Walle warehouse), and
[Jonas Petersen](../persons/jonas-petersen.md) (PMO); Tomás Iglesias sent his apologies.[^s13] The minutes were circulated for a
one-week review, with any objections to be raised with the minute-taker in writing.[^s21] The next
meeting is 7 May 2024, 14:00, in Bremen.[^s21]

The Lenkungsausschuss held an extraordinary steering session on Monday, 10 February 2025,
14:00–17:10, at Blauwal's headquarters in Bremen, room Weser 2; Petra Vogelsang chaired and
[Jonas Petersen](../persons/jonas-petersen.md) (PMO) took the minutes.[^s67] Present: Petra
Vogelsang, [Marek Duszek](../persons/marek-duszek.md), Sabine Krüger, Heike Brandt,
[Jörn Albers](../persons/jorn-albers.md) (site manager, Bremen-Walle), Tomás Iglesias
(Gezeitenwerk), and Jonas Petersen; the session was conducted in English at the guest's request,
with the German protokoll series resuming the following session.[^s67] The next meeting is the
Lenkungsausschuss on 11 March 2025, 14:00, in Bremen (German).[^s69]

The group held a status handover (Statusübergabe) for the Bremen-Walle pilot on Monday,
30 June 2025, 10:00–12:30, at the Bremen-Walle warehouse, meeting room Halle 2;
[Sabine Krüger](../persons/sabine-kruger.md) took the minutes.[^s86] Present:
[Petra Vogelsang](../persons/petra-vogelsang.md) (programme lead), Sabine Krüger,
[Jörn Albers](../persons/jorn-albers.md) (Bremen-Walle warehouse management),
[Marek Duszek](../persons/marek-duszek.md) (by video), and
[Jonas Petersen](../persons/jonas-petersen.md) (PMO); [Heike Brandt](../persons/heike-brandt.md)
and [Tomás Iglesias](../persons/tomas-iglesias.md) (Gezeitenwerk) sent their apologies.[^s86] The
next meeting is the Lenkungsausschuss on 9 September 2025, 14:00, in Bremen.[^s87]

## Change Log

- 2024-03-05: QUAYSTONE's persistence layer decided to run on KorallenDB (decision D-4), over
  Marek Duszek's recorded dissent.[^s6]
- 2025-01-13: Lenkungsausschuss circular resolution reversed that decision: QUAYSTONE's
  persistence layer now runs on BasaltDB.[^s47] Confirmed unanimously as decision D-9 at the
  10 February 2025 steering session.[^s53]
- 2024-05-14: charter version 1.0 approved a programme budget of EUR 1.8 million.[^s3]
- 2025-01-16: the Geschäftsführung increased the approved programme budget to EUR 2.4 million, on
  the committee's escalation.[^s46] Confirmed as decision D-11 at the 10 February 2025 steering
  session.[^s59]
- 2024-05-14: charter version 1.0 targeted the pilot cutover at Bremen-Walle for August 2024, a
  pilot hold-point review for September 2024, full-estate go-live for 1 October 2024, and KOMET
  decommissioning with programme close for Q4 2024.[^s48]
- 2025-01-17: Revision B reset the plan: pilot cutover at Bremen-Walle (SEAGULL) for
  22–23 February 2025, a pilot hold-point review for April 2025, full-estate go-live for
  30 June 2025, and KOMET decommissioning with programme close for Q4 2025.[^s37] Confirmed as
  decision D-10 at the 10 February 2025 steering session.[^s64]
- 2025-06-30: decision LA-2025-07 postpones the full rollout to the remaining sites from Revision
  B's 30 June 2025 target to the first quarter of 2026, after the customs-interface certification
  and the MDE-device deliveries for three sites both proved unready.[^s85]
- 2026-03-17: the entire Blauwal warehouse estate goes live on QUAYSTONE — the last convoy of
  sites passes its go/no-go gates without a waiver, closing out decision LA-2025-07's first-quarter
  2026 target.[^s91]
- 2026-03-20: KOMET's final switch-off is set for 30 September 2026, further extending Revision
  B's Q4 2025 decommissioning target; KOMET remains readable until then for archive
  extraction.[^s94]
- 2026-04-08: KOMET's final switch-off is brought forward from 30 September 2026 to 31 July 2026,
  after the archive extraction for customs and audit history finished ahead of schedule.[^s97]

## Open Points

### Article master-data cleansing
id: op-article-master-data-cleansing
- 2024-03-05: years of parallel maintenance in KOMET have left duplicate article records across
  Blauwal's sites; [Sabine Krüger](../persons/sabine-kruger.md) flagged this as the operational
  risk she is most worried about, since migrating duplicates means multiplying them. The meeting
  agreed the master data must be cleansed before the pilot cutover, not patched afterwards
  (action AP-1, owner Sabine Krüger).[^s2][^s7]
- 2024-03-19: the review is ongoing; the extent of duplicate records is significant and has grown
  over years, especially where sites created articles in parallel. The cleansing remains a
  mandatory prerequisite for the pilot cutover, and Sabine Krüger will now report cleansing
  metrics to the steering committee monthly; the committee unanimously underlined the point's
  priority.[^s18][^s20]
- 2025-02-10: Sabine Krüger reported the cleansing at roughly two thirds complete — about two
  thirds of the duplicate article records identified across the estate have been merged or
  retired, with the remainder concentrated in the two sites with the oldest parallel maintenance
  history. The trajectory supports the pilot date; the committee kept AP-1 open with its monthly
  reporting rhythm and renewed its status as a hard precondition: no pilot cutover before Walle's
  slice of the cleansing is finished.[^s61]
- 2025-06-30: Sabine Krüger reported the cleansing complete — the duplicate stragglers still
  outstanding in May at the two oldest sites are cleansed, and article maintenance now runs
  through a central check so duplicates cannot recur. AP-1 is closed and drops from the monthly
  report; the group thanked her, noting AP-1 had been the programme's most persistent point for
  over fifteen months.[^s82]

### Interface conversion tests on the BasaltDB stack
id: op-interface-conversion-tests-basaltdb
- 2025-02-10: following the reversal to BasaltDB, Marek Duszek required the interface conversion
  tests to be re-run against the BasaltDB stack before Gezeitenwerk's cutover runbook (reviewed at
  v0.9) advances to v1.0; Tomás Iglesias accepted this as a condition of readiness (action AP-7,
  owner Marek Duszek with Gezeitenwerk, due 17 February 2025).[^s54][^s68]

### Pilot weekend customer communication
id: op-pilot-weekend-communication
- 2025-02-10: Sabine Krüger was tasked with communicating the 22–23 February 2025 pilot weekend to
  customers with Walle-routed traffic (action AP-8, due 14 February 2025).[^s58]

### Cutover strategy for remaining sites
id: op-cutover-strategy
- 2024-03-05: how the remaining sites follow the SEAGULL pilot — one at a time, or a single
  coordinated cutover — was left open; Petra Vogelsang will circulate a written proposal in early
  April 2024 (action AP-3), and the steering committee will decide.[^s4][^s7]
- 2024-03-19: the decision remains owned by Petra Vogelsang; it is now targeted for the steering
  committee's 7 May 2024 meeting rather than an April proposal.[^s20][^s21]
- 2024-04-02: Petra Vogelsang circulated her personal proposal: the SEAGULL pilot proceeds as
  decided with a hold point before any second site follows, the remaining warehouses then cut over
  in small convoys of at most two with their own go/no-go criteria, and the go-live date yields to
  the cutover sequence rather than the reverse; she opposes a single coordinated cutover and
  requested written comments by 12 April 2024, ahead of the steering committee's decision at its
  7 May 2024 meeting.[^s26][^s27][^s28][^s30]
- 2024-05-07: the Lenkungsausschuss adopted Petra Vogelsang's proposal at its session that day —
  the rollout proceeds phased, warehouse by warehouse, with the SEAGULL pilot at Bremen-Walle
  followed by a hold point before any further site, and the remaining sites cutting over in small
  groups with individual go/no-go decisions; the point is resolved.[^s38]

### MDE device tender
id: op-mde-device-tender
- 2024-03-19: following the steering committee's approval of 180 MDE devices (decision
  LA-2024-03), Purchasing (Einkauf) owns the tender, targeted for April 2024.[^s20]
- 2025-06-30: delivery of the MDE devices for three of the remaining sites has slipped on the
  supplier's side; Purchasing, together with Sabine Krüger, will hold an escalation conversation
  with the supplier on delivery reliability in July 2025.[^s89]

### SEAGULL pilot weekend defects
id: op-seagull-pilot-defects
- 2025-03-03: three low-priority defects from the SEAGULL cutover weekend (22–23 February 2025)
  are logged in the tracker, with fixes scheduled to land inside the two-week hypercare
  period.[^s75]
- 2025-06-30: all three defects are fixed and signed off; the point is resolved.[^s79]

### Customs interface certification
id: op-customs-interface-certification
- 2025-06-30: certification of the customs interface by the responsible authority remains
  outstanding and, per current information, is not expected before autumn 2025 — one of two
  reasons, with the delayed MDE-device deliveries, the group gives for not holding the remaining
  sites' original rollout date. Marek Duszek owns tracking the certification, reporting to the
  group monthly.[^s88]
- 2026-03-20: the go-live announcement reports the last convoy of sites passed its go/no-go gates
  without a waiver as the entire estate went live on QUAYSTONE on 17 March 2026, and names the
  customs certification delay as one of the drivers of the programme's final cost overrun —
  indicating certification was completed ahead of go-live. The point is resolved.[^s91][^s90]

### Platform expansion beyond QUAYSTONE
id: op-platform-expansion
- 2026-03-20: the go-live announcement confirms rumours among customer-facing staff of a further
  platform built "on top of" QUAYSTONE — a customer portal — as "roughly right"; more detail is
  promised in April 2026 from that project's own team.[^s95]
- 2026-04-08: the further platform is
  [SEAGULL (customer portal programme)](seagull-customer-portal-programme.md) — Blauwal's customer
  self-service portal, mandated by the Geschäftsführung on 24 March 2026 and kicked off on
  8 April 2026 under product owner Yasmin Okafor,[^s98] targeting a first customer launch in
  Q2 2027,[^s99] and built strictly on the QUAYSTONE order and shipment APIs.[^s100] It is a
  separate initiative from this programme, unrelated to the SEAGULL codename this programme used
  for the Bremen-Walle pilot beyond the shared, now-reused name.[^s101]

## See also

- [KOMET](../systems/komet.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KorallenDB](../systems/korallendb.md)
- [BasaltDB](../systems/basaltdb.md)
- [SEAGULL (customer portal programme)](seagull-customer-portal-programme.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
- [Gezeitenwerk Software GmbH](../organizations/gezeitenwerk-software-gmbh.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Heike Brandt](../persons/heike-brandt.md)
- [Jörn Albers](../persons/jorn-albers.md)
- [Tomás Iglesias](../persons/tomas-iglesias.md)
- [Jonas Petersen](../persons/jonas-petersen.md)
- [Yasmin Okafor](../persons/yasmin-okafor.md)
- [MDE — Mobile Datenerfassung](../abbreviations/mde-mobile-datenerfassung.md)

## Sources

[^s1]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 1 — Why this programme exists (ingested 2026-08-28)
[^s2]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 2 — Current estate (ingested 2026-08-28)
[^s3]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 3 — Budget (ingested 2026-08-28)
[^s4]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 4 — Timeline and pilot (ingested 2026-08-28)
[^s5]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § TOP 5 — Platform database (ingested 2026-08-28)
[^s6]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Decisions (ingested 2026-08-28)
[^s7]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), § Action items (ingested 2026-08-28)
[^s8]: [raw/2024-03-05-minutes-kickoff.md](../../raw/2024-03-05-minutes-kickoff.md), lines 1-11 (ingested 2026-08-28)
[^s9]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 32-36 (ingested 2026-08-28)
[^s10]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 10-14 (ingested 2026-08-28)
[^s11]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 16-21 (ingested 2026-08-28)
[^s12]: [raw/2024-03-12-email-duszek-komet-assessment.md](../../raw/2024-03-12-email-duszek-komet-assessment.md), lines 49-55 (ingested 2026-08-28)
[^s13]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), lines 1-11 (ingested 2026-08-28)
[^s14]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 2 — Budget (ingested 2026-08-28)
[^s15]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 3 — Pilotierung (ingested 2026-08-28)
[^s16]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 4 — Schulungsplanung (ingested 2026-08-28)
[^s17]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 5 — Geräte für die Mobile Datenerfassung (MDE) (ingested 2026-08-28)
[^s18]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § TOP 6 — Stammdaten (AP-1) (ingested 2026-08-28)
[^s19]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Beschlüsse (ingested 2026-08-28)
[^s20]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), § Aufgaben (ingested 2026-08-28)
[^s21]: [raw/2024-03-19-protokoll-lenkungsausschuss.md](../../raw/2024-03-19-protokoll-lenkungsausschuss.md), lines 82-83 (ingested 2026-08-28)
[^s22]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 8-9 (ingested 2026-08-29)
[^s23]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 16-18 (ingested 2026-08-29)
[^s24]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 18-22 (ingested 2026-08-29)
[^s25]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 24-29 (ingested 2026-08-29)
[^s26]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 33-36 (ingested 2026-08-29)
[^s27]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 38-42 (ingested 2026-08-29)
[^s28]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 44-45 (ingested 2026-08-29)
[^s29]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 47-50 (ingested 2026-08-29)
[^s30]: [raw/2024-04-02-email-vogelsang-cutover-strategy.md](../../raw/2024-04-02-email-vogelsang-cutover-strategy.md), lines 52-53 (ingested 2026-08-29)
[^llm1]: LLM - the first Ariane 5's maiden-flight failure occurred on 4 June 1996, not 1994; the technical cause matches the historical record (added 2026-08-29)
[^s31]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 3-11 (ingested 2026-08-29)
[^s32]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 1. Purpose (ingested 2026-08-29)
[^s33]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 3. Objectives (ingested 2026-08-29)
[^s34]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 44-46 (ingested 2026-08-29)
[^s35]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 48-50 (ingested 2026-08-29)
[^s36]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 76-78 (ingested 2026-08-29)
[^s37]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 63-69 (ingested 2026-08-29)
[^s38]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 5. Approach (ingested 2026-08-29)
[^s39]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 9. Governance (ingested 2026-08-29)
[^s40]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), § 11. Change control (ingested 2026-08-29)
[^s41]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 100-101 (ingested 2026-08-29)
[^s42]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 98-99 (ingested 2026-08-29)
[^s43]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 102-103 (ingested 2026-08-29)
[^s44]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 104-106 (ingested 2026-08-29)
[^s45]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 27-29 (ingested 2026-08-29)
[^s46]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 73-76 (ingested 2026-08-29)
[^s47]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md), lines 82-85 (ingested 2026-08-29)
[^s48]: [raw/2024-05-14-charter-leuchtfeuer.md](../../raw/2024-05-14-charter-leuchtfeuer.md) — Version 1.0's milestone plan, superseded in full by Revision B and no longer stated in the current file (ingested 2026-08-29)
[^s49]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), § TOP 1 — Where the first year actually left us (ingested 2026-08-29)
[^s50]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 24-25 (ingested 2026-08-29)
[^s51]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 26-27 (ingested 2026-08-29)
[^s52]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 28-29 (ingested 2026-08-29)
[^s53]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 31-35 (ingested 2026-08-29)
[^s54]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 67-69 (ingested 2026-08-29)
[^s55]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 39-41 (ingested 2026-08-29)
[^s56]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 41-42 (ingested 2026-08-29)
[^s57]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 42-44 (ingested 2026-08-29)
[^s58]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 89-90 (ingested 2026-08-29)
[^s59]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 48-51 (ingested 2026-08-29)
[^s60]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 51-53 (ingested 2026-08-29)
[^s61]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 57-62 (ingested 2026-08-29)
[^s62]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 66-67 (ingested 2026-08-29)
[^s63]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 73-74 (ingested 2026-08-29)
[^s64]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 75-76 (ingested 2026-08-29)
[^s65]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 77-78 (ingested 2026-08-29)
[^s66]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 79-81 (ingested 2026-08-29)
[^s67]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 1-11 (ingested 2026-08-29)
[^s68]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), lines 87-88 (ingested 2026-08-29)
[^s69]: [raw/2025-02-10-minutes-steering.md](../../raw/2025-02-10-minutes-steering.md), line 92 (ingested 2026-08-29)
[^s70]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 9-11 (ingested 2026-08-29)
[^s71]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 13-16 (ingested 2026-08-29)
[^s72]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 17-18 (ingested 2026-08-29)
[^s73]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 20-24 (ingested 2026-08-29)
[^s74]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 28-32 (ingested 2026-08-29)
[^llm2]: LLM - self-promotional claim by the vendor's own account manager about Gezeitenwerk's delivery quality, not independently corroborated in this corpus (added 2026-08-29)
[^s75]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 34-38 (ingested 2026-08-29)
[^s76]: [raw/2025-03-03-email-iglesias-pilot-report.md](../../raw/2025-03-03-email-iglesias-pilot-report.md), lines 40-43 (ingested 2026-08-29)
[^s77]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 13-16 (ingested 2026-08-29)
[^s78]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 16-20 (ingested 2026-08-29)
[^s79]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 2 — Betriebszahlen der ersten Wochen (ingested 2026-08-29)
[^s80]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 34-36 (ingested 2026-08-29)
[^s81]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 36-39 (ingested 2026-08-29)
[^s82]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), § TOP 4 — Stammdaten (AP-1) (ingested 2026-08-29)
[^s83]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 52-55 (ingested 2026-08-29)
[^s84]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 55-57 (ingested 2026-08-29)
[^s85]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 59-62 (ingested 2026-08-29)
[^s86]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 1-9 (ingested 2026-08-29)
[^s87]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), line 73 (ingested 2026-08-29)
[^s88]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 68-69 (ingested 2026-08-29)
[^s89]: [raw/2025-06-30-protokoll-uebergabe-walle.md](../../raw/2025-06-30-protokoll-uebergabe-walle.md), lines 70-71 (ingested 2026-08-29)
[^s90]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 23-26 (ingested 2026-08-29)
[^s91]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 9-13 (ingested 2026-08-29)
[^llm3]: LLM - self-assessment by the programme's own leadership of the full-estate rollout's success, not independently corroborated in this corpus beyond the Bremen-Walle pilot's own metrics (added 2026-08-29)
[^s92]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 15-21 (ingested 2026-08-29)
[^s93]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 27-33 (ingested 2026-08-29)
[^s94]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 38-41 (ingested 2026-08-29)
[^s95]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 42-44 (ingested 2026-08-29)
[^s96]: [raw/2026-03-20-email-vogelsang-golive.md](../../raw/2026-03-20-email-vogelsang-golive.md), lines 46-53 (ingested 2026-08-29)
[^s97]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § AOB (ingested 2026-08-29)
[^s98]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name (ingested 2026-08-29)
[^s99]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 4 — Timeline and pilot customers (ingested 2026-08-29)
[^s100]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 39-43 (ingested 2026-08-29)
[^s101]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 20-25 (ingested 2026-08-29)
[^s102]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 51-54 (ingested 2026-08-29)
[^s103]: [raw/2026-04-15-memo-brandt-retraction.md](../../raw/2026-04-15-memo-brandt-retraction.md), lines 10-23 (ingested 2026-08-29)
