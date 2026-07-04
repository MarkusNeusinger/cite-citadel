# Projekt LEUCHTFEUER — steering committee, minutes (extraordinary session in English)

**Date:** Monday, 10 February 2025, 14:00–17:10
**Location:** Blauwal Logistik GmbH, Hauptverwaltung Bremen, room Weser 2
**Chair:** Petra Vogelsang (programme lead)
**Minutes:** Jonas Petersen (PMO)

**Present:** Petra Vogelsang — Marek Duszek — Sabine Krüger — Heike Brandt — Jörn Albers
(site manager, Bremen-Walle) — Tomás Iglesias (Gezeitenwerk Software GmbH) — Jonas Petersen
**Note:** conducted in English at the guest's request; the German protokoll series resumes next
session.

## TOP 1 — Where the first year actually left us

The chair opened with the plain sentence the committee owed itself: the original go-live target of
1 October 2024 was missed, and missed for reasons the programme now understands in detail rather
than in hindsight generalities. The interface work package proved far larger in effort than in
count, and the master-data cleansing — correctly made a precondition — could not responsibly have
been declared done in the summer. The committee agreed that the honest response is a re-planned
programme, not a re-dated slide, and dealt with the consequences in the decisions below.

## TOP 2 — Database decision, revisited

Marek presented the assessment his team prepared after the KorallenDB vendor announced revised
licence terms in December: per-core pricing plus an audit clause that grants the vendor scheduled
access to usage metering. Heike confirmed the commercial view — under the revised terms the
five-year cost of the persistence layer roughly doubles, with an audit overhead nobody priced.
Tomás confirmed that Gezeitenwerk supports QUAYSTONE on BasaltDB as a first-class deployment and
that two reference customers run it in production at comparable volume.

By circular resolution of 13 January 2025, confirmed unanimously in this session, **the
persistence layer moves from KorallenDB to BasaltDB** (decision D-9). The migration happens before
the pilot cutover, so the pilot runs on the target stack from day one. The minutes note for the
record that the lead architect's dissent on the original database choice was recorded in March
2024; the committee reverses that choice today on commercial grounds arising since.

## TOP 3 — Re-planned timeline

The committee confirmed the re-planned timeline circulated with charter Revision B (decision
D-10): pilot cutover at Bremen-Walle on the weekend of **22–23 February 2025**, hold point review
in April, and **full-estate go-live on 30 June 2025**. Tomás committed Gezeitenwerk staffing to these dates. Jörn asked that the pilot
weekend avoid the month-end peak, which the chosen weekend does. The chair reminded the room of
the standing principle that the date serves the sequence: any site failing its go/no-go criteria
waits for the next group, whatever that does to the chart.

## TOP 4 — Budget

Heike reported the consequence of the longer programme and the enlarged interface package in one
number: the original envelope does not hold. On the committee's escalation, the Geschäftsführung
approved on 16 January 2025 an increased programme budget of **EUR 2.4 million** (decision D-11,
confirming). Heike has folded the increase into the charter revision (Revision B, issued
20 January 2025) and reminded the committee that this second envelope is to be treated as the
last one: "There is no third ask in my drawer."

## TOP 5 — Master data (AP-1, standing item)

Sabine reported that the article master data cleansing stands at roughly two thirds complete:
about two thirds of the duplicate article records identified across the estate have been merged or
retired, with the remainder concentrated in the two sites with the oldest parallel maintenance
history. The trajectory supports the pilot date. The committee kept AP-1 open with its monthly
reporting rhythm and renewed its status as a hard precondition: no pilot cutover before Walle's
slice of the cleansing is finished.

## TOP 6 — Pilot readiness

The mobile devices for Walle are delivered and staged; training of the Walle crew starts, per the
training plan, four weeks before cutover. Gezeitenwerk's cutover runbook v0.9 was reviewed; Marek
requires the interface conversion tests to be re-run against the BasaltDB stack before the runbook
goes to v1.0, and Tomás accepted this as a condition of readiness.

## Decisions

- **D-9** — The QUAYSTONE persistence layer moves from KorallenDB to **BasaltDB** (circular
  resolution of 13 January 2025, confirmed unanimously).
- **D-10** — Confirmation of the revised timeline: pilot cutover Bremen-Walle 22–23 February
  2025; hold point review April 2025; full-estate go-live **30 June 2025**.
- **D-11** — Confirmation of the increased programme budget of **EUR 2.4 million** approved by the
  Geschäftsführung on 16 January 2025.
- **D-12** — The committee ratifies charter Revision B, incorporating D-9 through D-11 (approved
  by circular resolution of the Lenkungsausschuss of 17 January 2025, issued by the PMO on
  20 January 2025).

## Action items

- **AP-1** — Article master data cleansing — owner: Sabine Krüger — standing, monthly report;
  Walle slice to be closed before pilot cutover.
- **AP-7** — Interface conversion tests re-run on the BasaltDB stack before runbook v1.0 —
  owner: Marek Duszek, with Gezeitenwerk — due: 17 February 2025.
- **AP-8** — Pilot weekend communication to customers with Walle-routed traffic — owner: Sabine
  Krüger — due: 14 February 2025.

**Next meeting:** Lenkungsausschuss, 11 March 2025, 14:00, Bremen (German).
