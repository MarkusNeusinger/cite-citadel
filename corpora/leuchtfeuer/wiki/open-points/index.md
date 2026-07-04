# Open Points

Tracked open points and their timelines, generated from every `## Open Points` section in the wiki. Grouped open-first; each links to the host page, which carries the citations. Generated — do not edit.

## Open (10)

### Pilot customer agreements countersignature
host: [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md) · updated 2026-04-08 · id: op-pilot-customer-agreements-countersignature
- 2026-04-08: raised; the three pilot customer agreements are to be brought to countersignature (action SG-AP-1, owner Yasmin Okafor), due May 2026.

### API coverage gap analysis
host: [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md) · updated 2026-04-08 · id: op-api-coverage-gap-analysis
- 2026-04-08: raised; a gap analysis of portal use cases against current QUAYSTONE endpoints is due (action SG-AP-2, owner Marek Duszek), due 12 May 2026.

### SEAGULL operations liaison
host: [SEAGULL (customer portal programme)](../projects/seagull-customer-portal-programme.md) · updated 2026-04-08 · id: op-seagull-operations-liaison
- 2026-04-08: raised; an operations liaison for the programme is to be named from the Walle crew (action SG-AP-3, owner Sabine Krüger), due 20 April 2026.

### Cutover runbook readiness
host: [SEAGULL](../projects/seagull.md) · updated 2025-02-10 · id: op-cutover-runbook-readiness
- 2025-02-10: raised; Gezeitenwerk's cutover runbook v0.9 was reviewed by the steering committee. Marek Duszek requires the interface conversion tests to be re-run against the BasaltDB stack before the runbook advances to v1.0 (action AP-7, owner Marek Duszek, with Gezeitenwerk, due 17 February 2025); Tomás Iglesias accepted this as a condition of pilot readiness.

### Pilot weekend customer communication
host: [SEAGULL](../projects/seagull.md) · updated 2025-02-10 · id: op-pilot-weekend-customer-communication
- 2025-02-10: raised; the steering committee assigned Sabine Krüger to communicate the pilot weekend to customers with Walle-routed traffic (action AP-8), due 14 February 2025.

### Label-printing interface carrier format
host: [SEAGULL](../projects/seagull.md) · updated 2025-03-03 · id: op-label-printing-carrier-format
- 2025-03-03: raised; the label-printing interface needs a configuration follow-up for a carrier format that appears only in month-end volumes. Gezeitenwerk is testing the fix against a recorded batch, not live traffic, and expects it in place well before month-end.

### SEAGULL lessons-learned workshop
host: [SEAGULL](../projects/seagull.md) · updated 2025-03-03 · id: op-seagull-lessons-learned-workshop
- 2025-03-03: raised; Gezeitenwerk offered to bring the lessons-learned workshop to Bremen in the last week of March 2025, pending confirmation from the steering committee's calendar.

### KOMET estate assessment
host: [KOMET](../systems/komet.md) · updated 2024-03-19 · id: op-komet-estate-assessment
- 2024-03-05: Marek Duszek gave a first, deliberately verbal sketch of the KOMET estate and asked for two weeks to put a proper written assessment together — enumerating the sites, the interfaces, and the local customisations one by one (action AP-2, owner Marek Duszek, due 15 March 2024).
- 2024-03-12: Marek Duszek delivered the written KOMET estate assessment three days early. The full assessment runs 34 pages on the project share, folder "AP-2"; he asked readers to cover at minimum section 2 (interfaces) and section 5 (customisations) before the 19 March steering-committee meeting.
- 2024-03-19: the steering committee took favourable note of the written assessment and asked that the interface list be kept as a living document on the project drive (decision LA-2024-01).

### Unplanned KOMET downtime cost estimate
host: [KOMET](../systems/komet.md) · updated 2026-04-15 · id: op-komet-downtime-cost-estimate
- 2026-04-15: retracted; Heike Brandt formally withdrew her 10 June 2024 memorandum, "KOMET operating costs (provisional figures)," which had reported a provisional per-hour estimate for unplanned KOMET downtime. Blauwal's final 2024–2025 operations audit, accepted by the Geschäftsführung on 31 March 2026, found the estimate's methodology had double-counted contractual penalties the affected customer accounts had since renegotiated and had extrapolated a peak-season hourly pattern across the whole year. The retracted memorandum was removed from the project record by document control; its provisional figures are not to be quoted or restated in any new document, and the audited replacement figures are held separately under restricted access rather than reproduced here.

### KOMET final switch-off
host: [KOMET](../systems/komet.md) · updated 2026-04-08 · id: op-komet-final-switch-off
- 2026-03-20: raised; following the full-estate QUAYSTONE go-live, KOMET remains readable while Blauwal completes the archive extraction required for customs and audit history; final switch-off is set for 30 September 2026.
- 2026-04-08: brought forward; the archive extraction for customs and audit history finished earlier than planned, so final switch-off is now set for 31 July 2026 instead of 30 September 2026. Facilities and IT operations are informed; the SEAGULL portal programme is unaffected but was notified, as the last KOMET-era customer exports retire with the system.

## Done (5)

### MDE device procurement
host: [MDE Device](../objects/mde-device.md) · updated 2026-03-20 · id: op-mde-device-procurement
- 2024-03-19: 180 MDE devices approved (decision LA-2024-03); the tender is run by Blauwal's procurement department (action, owner Einkauf, due April 2024), with delivery staggered per site ahead of each site's cutover.
- 2025-02-10: the mobile devices for Bremen-Walle are delivered and staged ahead of the SEAGULL pilot cutover.
- 2025-06-30: delivery of the MDE devices for three follow-up sites is delayed on the supplier's side; the steering committee is to hold an escalation conversation with the MDE supplier on delivery reliability (owner: procurement (Einkauf) with Sabine Krüger, due July 2025).
- 2026-03-20: resolved; the full warehouse estate went live on QUAYSTONE on 17 March 2026, with the last convoy of sites — which would have included the delayed follow-up sites — clearing its go/no-go gates without a waiver.

### Article master data cleansing
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2025-06-30 · id: op-article-master-data-cleansing
- 2024-03-05: raised by Sabine Krüger; years of parallel maintenance in KOMET have left duplicate article records across the sites, and migrating duplicates would multiply them. The meeting agreed the master data must be cleansed before the pilot cutover, not patched afterwards (action AP-1, owner Sabine Krüger, due before the pilot cutover).
- 2024-03-19: Sabine Krüger reported the cleansing review under way; the volume of duplicates is significant and has grown over years, especially where sites created article records in parallel. The steering committee unanimously underlined the priority of this point and will now receive monthly KPI reports on progress.
- 2025-02-10: Sabine Krüger reported the cleansing roughly two thirds complete — about two thirds of the duplicate article records identified across the estate have been merged or retired, with the remainder concentrated in the two sites with the oldest parallel-maintenance history. The trajectory supports the pilot date. The committee kept AP-1 open with its monthly reporting rhythm and renewed its status as a hard precondition: no pilot cutover before Walle's slice of the cleansing is finished.
- 2025-06-30: resolved; Sabine Krüger reported the article master data cleansing complete — the residual duplicates left in May from the two oldest sites are cleansed, and maintenance is now changed so new article records are centrally checked and duplicates cannot recur. AP-1 is closed and removed from monthly reporting; the steering committee thanked Sabine Krüger, noting this was the most persistent point of the programme, open for over fifteen months.

### Customs interface certification
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2026-03-20 · id: op-customs-interface-certification
- 2025-06-30: raised; certification of the customs interface by the responsible authority is outstanding and, per current information, not expected before autumn 2025 — a contributing reason for postponing the remaining-sites rollout to Q1 2026 (decision LA-2025-07). Marek Duszek owns a monthly follow-up report, ongoing.
- 2026-03-20: resolved; the full warehouse estate went live on QUAYSTONE on 17 March 2026, with the last convoy of sites clearing its go/no-go gates without a waiver — Vogelsang's go-live announcement does not report the customs-interface certification as outstanding and counts the quarter given to it among the corrections that "turned out to be worth it."

### Post-pilot cutover strategy
host: [Projekt LEUCHTFEUER](../projects/projekt-leuchtfeuer.md) · updated 2024-05-07 · id: op-post-pilot-cutover-strategy
- 2024-03-05: left open; whether the sites after the SEAGULL pilot follow one warehouse at a time or via a single coordinated cutover was not decided — opinions in the room differed and the chair declined to force the question. Petra Vogelsang will circulate a written cutover-strategy proposal in early April 2024 (action AP-3), for the steering committee to decide.
- 2024-03-19: still open; Petra Vogelsang's cutover-strategy proposal (action AP-3) is now due for decision at the steering committee's next meeting, 7 May 2024.
- 2024-04-02: Petra Vogelsang circulated her cutover-strategy proposal (action AP-3) to the programme list — a phased, warehouse-by-warehouse rollout in small convoys after a SEAGULL hold point, opposing a single coordinated cutover (see Cutover strategy proposal above) — and asked for written comments by 12 April 2024, ahead of the steering committee's 7 May 2024 decision.
- 2024-05-07: resolved; the Lenkungsausschuss adopted Petra Vogelsang's phased, warehouse-by-warehouse cutover proposal at its 7 May 2024 session — the SEAGULL pilot proceeds as decided and is followed by a hold point, then the remaining sites cut over in small groups with individual go/no-go decisions on data readiness, trained staff, and interface test results, with the calendar yielding to the sequence.

### Post-cutover defect backlog
host: [SEAGULL](../projects/seagull.md) · updated 2025-06-30 · id: op-post-cutover-defect-backlog
- 2025-03-03: raised; three low-priority defects from the SEAGULL cutover weekend are logged in the tracker, with fixes scheduled during the two-week hypercare period.
- 2025-06-30: resolved; the three low-priority defects are fixed and accepted.
