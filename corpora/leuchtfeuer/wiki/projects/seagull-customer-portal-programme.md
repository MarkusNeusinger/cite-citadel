---
type: Project
title: SEAGULL (customer portal programme)
description: Blauwal Logistik GmbH's programme, kicked off April 2026, to build a
  customer self-service portal on top of QUAYSTONE.
tags:
- logistics
- customer-portal
- programme
resource: raw/2026-04-08-minutes-portal-kickoff.md
aliases:
- SEAGULL
- SEAGULL portal
- customer self-service portal
timestamp: '2026-08-28T23:43:48Z'
citadel_version: 0.6.0
---

[Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md) constituted the SEAGULL portal
programme at a kickoff meeting on 8 April 2026, chaired by
[Yasmin Okafor](../persons/yasmin-okafor.md) (product owner, customer portal) — her first committee
as chair.[^s1] The programme was mandated by a Geschäftsführung decision of 24 March 2026: Blauwal
will build a customer self-service portal, running under the codename **SEAGULL**.[^s2] Yasmin
Okafor framed the programme as the payoff of the estate's uniform move to
[QUAYSTONE](../systems/quaystone.md): a single truthful window for customers into their own
shipments, replacing three phone numbers and a fax line.[^s2]

**Not to be confused with the earlier SEAGULL.** The codename SEAGULL was previously the working
title of the 2024–25 [QUAYSTONE](../systems/quaystone.md) pilot rollout at the Bremen-Walle
warehouse under [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md); that pilot phase is closed, and the
name has been released for reuse. The portal programme is a separate initiative — its own mandate,
budget line, and team — unrelated to the former pilot beyond the shared name. The PMO asked that
documents use "SEAGULL" without qualification going forward, since the pilot usage is now
historical.[^s3]

## What the portal is

The portal gives Blauwal's customers direct self-service over the web: near-real-time tracking of
their own shipments, retrieval of shipment documents including the proof of delivery (POD), stock
visibility for contract-logistics accounts, and booking of inbound time slots at the
warehouses.[^s4] [Sabine Krüger](../persons/sabine-kruger.md)'s one condition, accepted without
debate, is that the portal shows the operational truth or nothing — a portal that flatters the
numbers would cost more trust than it buys.[^s4]

## Architecture guardrails

[Marek Duszek](../persons/marek-duszek.md) set three binding architecture guardrails (decision
SG-2026-03): the portal is built on the [QUAYSTONE](../systems/quaystone.md) order and shipment
APIs, with no direct database access under any circumstance; the portal holds no warehouse data of
its own, rendering only what the platform answers; and customer identity and entitlements are a
first-class design topic from week one, not a hardening sprint before launch.[^s5] He intends to
defend the three lines "with the enthusiasm of a man who has seen the alternative," after two years
of migration discipline on [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md).[^s6]

## Timeline and pilot customers

The programme targets a first customer launch in the second quarter of 2027.[^s7] Three pilot
customers from the contract-logistics segment have agreed to co-design the first release; their
names remain confidential at their own request until the pilot agreements are countersigned.[^s7]
Yasmin Okafor was explicit about sequencing: scope grows only once the three pilots are genuinely
happy — "and genuinely means measured, not surveyed once at a steering meeting."[^s8]

## Team and ways of working

Product ownership sits with Yasmin Okafor; architecture is Marek Duszek's, in an advisory capacity
two days a week.[^s9] The operations liaison is to be named by Sabine Krüger from the Bremen-Walle
crew — the site with the longest history on QUAYSTONE.[^s9] The programme reports monthly to the
Geschäftsführung; its working language is English, with customer-facing material produced in
German.[^s9]

## KOMET decommissioning brought forward

At the same meeting, [Petra Vogelsang](../persons/petra-vogelsang.md) reported, for coordination
with the portal timeline, that [KOMET](../systems/komet.md)'s decommissioning has been brought
forward from the previously communicated end of September to 31 July 2026, since the archive
extraction for customs and audit history finished earlier than planned; Facilities and IT
operations are informed, and the portal programme is unaffected but should know the date, as the
last KOMET-era customer exports retire with it.[^s10]

## Decisions

- **SG-2026-01** — The SEAGULL portal programme is constituted; product owner: Yasmin
  Okafor.[^s11]
- **SG-2026-02** — First customer launch targeted for Q2 2027, with three contract-logistics pilot
  customers.[^s11]
- **SG-2026-03** — The architecture guardrails above are binding for the programme.[^s11]

## Meeting record

The kickoff meeting ran 10:00–12:00 on 8 April 2026 at Blauwal's headquarters in Bremen, room
Weser 2.[^s1] Present: Yasmin Okafor (chair), [Petra Vogelsang](../persons/petra-vogelsang.md),
[Marek Duszek](../persons/marek-duszek.md), [Sabine Krüger](../persons/sabine-kruger.md), and
[Jonas Petersen](../persons/jonas-petersen.md) (PMO), who took the minutes;
[Heike Brandt](../persons/heike-brandt.md) sent her apologies.[^s1] The next meeting is the SEAGULL
steering committee, 12 May 2026, 10:00, in Bremen.[^s13]

## Open Points

### Pilot customer agreements to countersignature
id: op-pilot-customer-agreements
- 2026-04-08: three contract-logistics pilot customers have agreed to co-design the first release;
  bringing their agreements to countersignature is owned by Yasmin Okafor, due May 2026 (action
  SG-AP-1).[^s12]

### API coverage gap analysis
id: op-api-coverage-gap-analysis
- 2026-04-08: a gap analysis of portal use cases against current QUAYSTONE endpoints is owned by
  Marek Duszek, due 12 May 2026 (action SG-AP-2).[^s12]

### Operations liaison for the portal programme
id: op-operations-liaison-portal
- 2026-04-08: an operations liaison for the programme, to be named by Sabine Krüger from the
  Bremen-Walle crew, is due 20 April 2026 (action SG-AP-3).[^s12]

## See also

- [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KOMET](../systems/komet.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
- [Yasmin Okafor](../persons/yasmin-okafor.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Sabine Krüger](../persons/sabine-kruger.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [Jonas Petersen](../persons/jonas-petersen.md)

## Sources

[^s1]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 1-11 (ingested 2026-08-29)
[^s2]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name (ingested 2026-08-29)
[^s3]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 20-25 (ingested 2026-08-29)
[^s4]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 2 — What the portal is (ingested 2026-08-29)
[^s5]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 39-43 (ingested 2026-08-29)
[^s6]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 45-46 (ingested 2026-08-29)
[^s7]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 4 — Timeline and pilot customers (ingested 2026-08-29)
[^s8]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), lines 53-54 (ingested 2026-08-29)
[^s9]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working (ingested 2026-08-29)
[^s10]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § AOB (ingested 2026-08-29)
[^s11]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Decisions (ingested 2026-08-29)
[^s12]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Action items (ingested 2026-08-29)
[^s13]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), line 87 (ingested 2026-08-29)
