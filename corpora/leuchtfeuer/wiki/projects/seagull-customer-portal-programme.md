---
type: Project
title: SEAGULL (customer portal programme)
description: Blauwal Logistik GmbH's 2026 programme to build a customer self-service
  portal on QUAYSTONE's APIs — codename SEAGULL, reused from the unrelated, closed
  2024–25 pilot rollout.
resource: raw/2026-04-08-minutes-portal-kickoff.md
tags:
- seagull
- quaystone
- blauwal-logistik
- customer-portal
timestamp: '2026-07-03T17:04:10Z'
---

Blauwal Logistik GmbH's SEAGULL portal programme held its kickoff meeting on Wednesday, 8 April 2026,
10:00–12:00, at the company's Hauptverwaltung in Bremen (room Weser 2); Yasmin Okafor (product owner,
customer portal) chaired, and Jonas Petersen (PMO) took the minutes.[^s1] Also present were Petra
Vogelsang (Head of IT), Marek Duszek (lead architect), and Sabine Krüger (Head of Warehouse
Operations); Heike Brandt sent apologies.[^s1]

## Mandate and the SEAGULL name

By decision of Blauwal's Geschäftsführung on 24 March 2026, the company will build a customer
self-service portal, and the programme carries the codename SEAGULL.[^s2] Yasmin Okafor, opening her
first committee as chair, noted that with the warehouse estate now uniformly on
[QUAYSTONE](../systems/quaystone.md), the company can finally show customers one truthful window into
their own shipments instead of three phone numbers and a fax legend.[^s2]

**The name is reused, not continued.** The codename SEAGULL was previously the working title of the
[2024–25 QUAYSTONE pilot rollout](seagull.md) at the Bremen-Walle warehouse; that pilot phase is
closed and the name has been released for reuse.[^s2] This portal programme is a separate initiative,
with its own mandate, budget line, and team, and is unrelated to the former pilot beyond the shared
name.[^s2] The PMO asked that documents use "SEAGULL" without qualification going forward, as the
pilot usage is historical.[^s2]

## What the portal is

The portal gives Blauwal's customers direct self-service over the web: near-real-time tracking of
their own shipments, retrieval of shipment documents including the proof of delivery (POD), stock
visibility for contract-logistics accounts, and booking of inbound time slots at the warehouses.[^s3]
Sabine Krüger's one condition for the portal, accepted without debate, was that it shows the
operational truth or it shows nothing — a portal that flatters the numbers would cost more trust than
it buys.[^s3]

## Architecture guardrails

Marek Duszek set three architecture guardrails for the programme:[^s4]

1. The portal is built on the QUAYSTONE order and shipment APIs — no direct database access, not for
   reading, not "just for the dashboard," not once, not ever.[^s4]
2. The portal holds no warehouse data of its own; it renders what the platform answers.[^s4]
3. Customer identity and entitlements are a first-class design topic from week one, not a hardening
   sprint before launch.[^s4]

He added that after two years of migration discipline he intends to defend these three lines "with the
enthusiasm of a man who has seen the alternative."[^s4]

## Timeline and pilot customers

The programme targets a first customer launch in the second quarter of 2027.[^s5] Three pilot
customers from the contract-logistics segment have agreed to co-design the first release; their names
remain confidential at their own request until the pilot agreements are countersigned.[^s5] Yasmin
Okafor was explicit about sequencing: scope grows only after the three pilots are genuinely happy,
"and genuinely means measured, not surveyed once at a steering meeting."[^s5]

## Team and ways of working

Product ownership sits with Yasmin Okafor; architecture is Marek Duszek's, in an advisory role two
days a week.[^s6] The operations liaison is to be named by Sabine Krüger from the Walle crew — the
site that has lived on the QUAYSTONE platform longest.[^s6] The programme reports monthly to the
Geschäftsführung; its working language is English, with customer-facing material in German.[^s6]

## Coordination with the KOMET decommissioning

Petra Vogelsang reported, for coordination with the portal timeline, that the decommissioning of
[KOMET](../systems/komet.md) has been brought forward to 31 July 2026, since the archive extraction
for customs and audit history finished earlier than planned.[^s7] The portal programme is unaffected
by the earlier date but should know it, as the last KOMET-era customer exports retire with the
system.[^s7]

## Decisions

- SG-2026-01 — The SEAGULL portal programme is constituted; product owner Yasmin Okafor.[^s8]
- SG-2026-02 — First customer launch targeted for Q2 2027, with three contract-logistics pilot
  customers.[^s8]
- SG-2026-03 — The architecture guardrails above are binding for the programme.[^s8]

The next meeting, a SEAGULL steering session, is set for 12 May 2026, 10:00, in Bremen.[^s10]

## Open Points

### Pilot customer agreements countersignature
id: op-pilot-customer-agreements-countersignature
- 2026-04-08: raised; the three pilot customer agreements are to be brought to countersignature
  (action SG-AP-1, owner Yasmin Okafor), due May 2026. [^s9]

### API coverage gap analysis
id: op-api-coverage-gap-analysis
- 2026-04-08: raised; a gap analysis of portal use cases against current QUAYSTONE endpoints is due
  (action SG-AP-2, owner Marek Duszek), due 12 May 2026. [^s9]

### SEAGULL operations liaison
id: op-seagull-operations-liaison
- 2026-04-08: raised; an operations liaison for the programme is to be named from the Walle crew
  (action SG-AP-3, owner Sabine Krüger), due 20 April 2026. [^s9]

## See also

- [SEAGULL (2024–25 QUAYSTONE pilot)](seagull.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KOMET](../systems/komet.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
- [Yasmin Okafor](../persons/yasmin-okafor.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [Sabine Krüger](../persons/sabine-kr-ger.md)
- [Jonas Petersen](../persons/jonas-petersen.md)
- [Heike Brandt](../persons/heike-brandt.md)

## Sources

[^s1]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 3-10 (ingested 2026-07-03)
[^s2]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name (ingested 2026-07-03)
[^s3]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 2 — What the portal is (ingested 2026-07-03)
[^s4]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails (ingested 2026-07-03)
[^s5]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 4 — Timeline and pilot customers (ingested 2026-07-03)
[^s6]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working (ingested 2026-07-03)
[^s7]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § AOB (ingested 2026-07-03)
[^s8]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Decisions (ingested 2026-07-03)
[^s9]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Action items (ingested 2026-07-03)
[^s10]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), line 87 (ingested 2026-07-03)
