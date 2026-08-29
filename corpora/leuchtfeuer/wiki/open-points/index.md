# Open Points

Tracked open points and their timelines, generated from every `## Open Points` section in the wiki. Grouped open-first; each links to the host page, which carries the citations. Generated — do not edit.

## Open (8)

### Interface conversion tests on the BasaltDB stack
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2025-02-10 · id: op-interface-conversion-tests-basaltdb
- 2025-02-10: following the reversal to BasaltDB, Marek Duszek required the interface conversion tests to be re-run against the BasaltDB stack before Gezeitenwerk's cutover runbook (reviewed at v0.9) advances to v1.0; Tomás Iglesias accepted this as a condition of readiness (action AP-7, owner Marek Duszek with Gezeitenwerk, due 17 February 2025).

### Pilot weekend customer communication
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2025-02-10 · id: op-pilot-weekend-communication
- 2025-02-10: Sabine Krüger was tasked with communicating the 22–23 February 2025 pilot weekend to customers with Walle-routed traffic (action AP-8, due 14 February 2025).

### MDE device tender
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2025-06-30 · id: op-mde-device-tender
- 2024-03-19: following the steering committee's approval of 180 MDE devices (decision LA-2024-03), Purchasing (Einkauf) owns the tender, targeted for April 2024.
- 2025-06-30: delivery of the MDE devices for three of the remaining sites has slipped on the supplier's side; Purchasing, together with Sabine Krüger, will hold an escalation conversation with the supplier on delivery reliability in July 2025.

### Platform expansion beyond QUAYSTONE
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2026-04-08 · id: op-platform-expansion
- 2026-03-20: the go-live announcement confirms rumours among customer-facing staff of a further platform built "on top of" QUAYSTONE — a customer portal — as "roughly right"; more detail is promised in April 2026 from that project's own team.
- 2026-04-08: the further platform is SEAGULL (customer portal programme) — Blauwal's customer self-service portal, mandated by the Geschäftsführung on 24 March 2026 and kicked off on 8 April 2026 under product owner Yasmin Okafor, targeting a first customer launch in Q2 2027, and built strictly on the QUAYSTONE order and shipment APIs. It is a separate initiative from this programme, unrelated to the SEAGULL codename this programme used for the Bremen-Walle pilot beyond the shared, now-reused name.

### Pilot customer agreements to countersignature
host: [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md) · updated 2026-04-08 · id: op-pilot-customer-agreements
- 2026-04-08: three contract-logistics pilot customers have agreed to co-design the first release; bringing their agreements to countersignature is owned by Yasmin Okafor, due May 2026 (action SG-AP-1).

### API coverage gap analysis
host: [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md) · updated 2026-04-08 · id: op-api-coverage-gap-analysis
- 2026-04-08: a gap analysis of portal use cases against current QUAYSTONE endpoints is owned by Marek Duszek, due 12 May 2026 (action SG-AP-2).

### Operations liaison for the portal programme
host: [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md) · updated 2026-04-08 · id: op-operations-liaison-portal
- 2026-04-08: an operations liaison for the programme, to be named by Sabine Krüger from the Bremen-Walle crew, is due 20 April 2026 (action SG-AP-3).

### Label-printing carrier-format configuration
host: [QUAYSTONE](../systems/quaystone.md) · updated 2025-03-03 · id: op-label-printing-carrier-format
- 2025-03-03: the label-printing interface needs one configuration follow-up for a carrier format that appears only in month-end volumes; Gezeitenwerk committed to having it in place well before month-end, testing the fix against a recorded batch rather than live traffic.

## Done (5)

### Article master-data cleansing
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2025-06-30 · id: op-article-master-data-cleansing
- 2024-03-05: years of parallel maintenance in KOMET have left duplicate article records across Blauwal's sites; Sabine Krüger flagged this as the operational risk she is most worried about, since migrating duplicates means multiplying them. The meeting agreed the master data must be cleansed before the pilot cutover, not patched afterwards (action AP-1, owner Sabine Krüger).
- 2024-03-19: the review is ongoing; the extent of duplicate records is significant and has grown over years, especially where sites created articles in parallel. The cleansing remains a mandatory prerequisite for the pilot cutover, and Sabine Krüger will now report cleansing metrics to the steering committee monthly; the committee unanimously underlined the point's priority.
- 2025-02-10: Sabine Krüger reported the cleansing at roughly two thirds complete — about two thirds of the duplicate article records identified across the estate have been merged or retired, with the remainder concentrated in the two sites with the oldest parallel maintenance history. The trajectory supports the pilot date; the committee kept AP-1 open with its monthly reporting rhythm and renewed its status as a hard precondition: no pilot cutover before Walle's slice of the cleansing is finished.
- 2025-06-30: Sabine Krüger reported the cleansing complete — the duplicate stragglers still outstanding in May at the two oldest sites are cleansed, and article maintenance now runs through a central check so duplicates cannot recur. AP-1 is closed and drops from the monthly report; the group thanked her, noting AP-1 had been the programme's most persistent point for over fifteen months.

### Cutover strategy for remaining sites
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2024-05-07 · id: op-cutover-strategy
- 2024-03-05: how the remaining sites follow the SEAGULL pilot — one at a time, or a single coordinated cutover — was left open; Petra Vogelsang will circulate a written proposal in early April 2024 (action AP-3), and the steering committee will decide.
- 2024-03-19: the decision remains owned by Petra Vogelsang; it is now targeted for the steering committee's 7 May 2024 meeting rather than an April proposal.
- 2024-04-02: Petra Vogelsang circulated her personal proposal: the SEAGULL pilot proceeds as decided with a hold point before any second site follows, the remaining warehouses then cut over in small convoys of at most two with their own go/no-go criteria, and the go-live date yields to the cutover sequence rather than the reverse; she opposes a single coordinated cutover and requested written comments by 12 April 2024, ahead of the steering committee's decision at its 7 May 2024 meeting.
- 2024-05-07: the Lenkungsausschuss adopted Petra Vogelsang's proposal at its session that day — the rollout proceeds phased, warehouse by warehouse, with the SEAGULL pilot at Bremen-Walle followed by a hold point before any further site, and the remaining sites cutting over in small groups with individual go/no-go decisions; the point is resolved.

### SEAGULL pilot weekend defects
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2025-06-30 · id: op-seagull-pilot-defects
- 2025-03-03: three low-priority defects from the SEAGULL cutover weekend (22–23 February 2025) are logged in the tracker, with fixes scheduled to land inside the two-week hypercare period.
- 2025-06-30: all three defects are fixed and signed off; the point is resolved.

### Customs interface certification
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2026-03-20 · id: op-customs-interface-certification
- 2025-06-30: certification of the customs interface by the responsible authority remains outstanding and, per current information, is not expected before autumn 2025 — one of two reasons, with the delayed MDE-device deliveries, the group gives for not holding the remaining sites' original rollout date. Marek Duszek owns tracking the certification, reporting to the group monthly.
- 2026-03-20: the go-live announcement reports the last convoy of sites passed its go/no-go gates without a waiver as the entire estate went live on QUAYSTONE on 17 March 2026, and names the customs certification delay as one of the drivers of the programme's final cost overrun — indicating certification was completed ahead of go-live. The point is resolved.

### Written assessment of the KOMET estate
host: [KOMET](../systems/komet.md) · updated 2024-03-12 · id: op-komet-estate-assessment
- 2024-03-05: Marek Duszek gave a first, deliberately verbal sketch of the KOMET estate and asked for two weeks to put together a proper written assessment enumerating the sites, interfaces, and local customisations (action AP-2, owner Marek Duszek, due 15 March 2024).
- 2024-03-12: Marek Duszek delivered the written assessment — action AP-2 done — three days ahead of the 15 March deadline: 34 pages, on the project share under folder "AP-2", covering all eleven warehouse sites and a first complete inventory of KOMET's 27 downstream interfaces. Recommended reading before the 19 March 2024 steering committee (Lenkungsausschuss) is section 2 (interfaces) and section 5 (site customisations).
