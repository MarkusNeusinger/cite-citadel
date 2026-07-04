# SEAGULL programme — kickoff meeting, minutes (customer self-service portal)

**Date:** Wednesday, 8 April 2026, 10:00–12:00
**Location:** Blauwal Logistik GmbH, Hauptverwaltung Bremen, room Weser 2
**Chair:** Yasmin Okafor (product owner, customer portal)
**Minutes:** Jonas Petersen (PMO)

**Present:** Yasmin Okafor (chair) — Petra Vogelsang (Head of IT) — Marek Duszek (lead
architect) — Sabine Krüger (Head of Warehouse Operations) — Jonas Petersen (PMO)
**Apologies:** Heike Brandt

## TOP 1 — Mandate and name

Yasmin opened her first committee as chair by reading out the mandate: by decision of the
Geschäftsführung of 24 March 2026, Blauwal will build a **customer self-service portal**, and the
programme carries the codename **SEAGULL**. She did not hide her enthusiasm: with the estate now
uniformly on QUAYSTONE, the company can finally show customers one truthful window into their own
shipments instead of three phone numbers and a fax legend.

**Note on the name, for the record:** the codename SEAGULL was previously the working title of the
2024–25 QUAYSTONE pilot rollout at the Bremen-Walle warehouse. That pilot phase is closed and the
name has been released for reuse; the portal programme is a separate initiative with its own
mandate, budget line, and team, and is unrelated to the former pilot beyond the shared bird. The
PMO asked that documents use "SEAGULL" without qualification going forward, as the pilot usage is
historical.

## TOP 2 — What the portal is

The portal gives Blauwal's customers direct self-service over the web: tracking of their own
shipments in near-real time, retrieval of shipment documents including the proof of delivery
(POD), stock visibility for contract-logistics accounts, and the booking of inbound time slots at
the warehouses. Sabine's one condition, accepted without debate: the portal shows the operational
truth or it shows nothing — a portal that flatters the numbers would cost more trust than it buys.

## TOP 3 — Architecture guardrails

Marek set the technical guardrails in his customary form, transcribed here faithfully:

1. The portal is built **on the QUAYSTONE order and shipment APIs**. No direct database access,
   not for reading, not "just for the dashboard", not once, not ever.
2. The portal holds no warehouse data of its own; it renders what the platform answers.
3. Customer identity and entitlements are a first-class design topic from week one, not a
   hardening sprint before launch.

He added that after two years of migration discipline he intends to defend these three lines "with
the enthusiasm of a man who has seen the alternative".

## TOP 4 — Timeline and pilot customers

The programme targets a **first customer launch in the second quarter of 2027**. Three pilot
customers from the contract-logistics segment have agreed to co-design the first release; their
names remain confidential at their own request until the pilot agreements are countersigned.
Yasmin was explicit about sequencing: scope grows only after the three pilots are genuinely happy,
"and genuinely means measured, not surveyed once at a steering meeting".

## TOP 5 — Team and ways of working

Product ownership: Yasmin Okafor. Architecture: Marek Duszek (advisory, two days a week).
Operations liaison: named by Sabine Krüger from the Walle crew — the site that has lived on the
platform longest. The programme reports monthly to the Geschäftsführung; working language is
English, with customer-facing material in German.

## AOB

Petra reported, for coordination with the portal timeline, that **the decommissioning of KOMET
has been brought forward to 31 July 2026** — the archive extraction for customs and audit history
finished earlier than planned, so there is no reason to keep the old system breathing until the
end of September as previously communicated. Facilities and IT operations are informed; the
portal programme is unaffected but should know the date, as the last KOMET-era customer exports
retire with it.

## Decisions

- **SG-2026-01** — The SEAGULL portal programme is constituted; product owner: Yasmin Okafor.
- **SG-2026-02** — First customer launch targeted for Q2 2027, with three contract-logistics
  pilot customers.
- **SG-2026-03** — Architecture guardrails per TOP 3 are binding for the programme.

## Action items

- **SG-AP-1** — Pilot customer agreements to countersignature — owner: Yasmin Okafor — due:
  May 2026.
- **SG-AP-2** — API coverage gap analysis (portal use cases vs. current QUAYSTONE endpoints) —
  owner: Marek Duszek — due: 12 May 2026.
- **SG-AP-3** — Operations liaison named — owner: Sabine Krüger — due: 20 April 2026.

**Next meeting:** SEAGULL steering, 12 May 2026, 10:00, Bremen.
