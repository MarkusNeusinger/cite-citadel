---
type: Project
title: SEAGULL
description: Blauwal Logistik's customer self-service portal programme, built on the
  QUAYSTONE APIs to give customers direct web access to shipment tracking, documents,
  and inbound slot booking.
aliases:
- customer portal
- self-service portal
tags:
- seagull
- blauwal-logistik
- quaystone
- portal
- programme-management
resource: raw/2026-04-08-minutes-portal-kickoff.md
timestamp: '2026-07-16T17:06:43Z'
citadel_version: 0.3.0
---

SEAGULL is [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)'s programme to build a customer self-service portal, constituted by decision of the company's executive management (Geschäftsführung) of 24 March 2026.[^s1] It was chaired into being at its kickoff meeting on 8 April 2026 at Blauwal's Bremen headquarters, chaired by [Yasmin Okafor](../persons/yasmin-okafor.md) (product owner); minutes were taken by [Jonas Petersen](../persons/jonas-petersen.md) (PMO).[^s2] Okafor opened the meeting by reading out the mandate and did not hide her enthusiasm: with the warehouse estate now uniformly on [QUAYSTONE](../systems/quaystone.md), she framed the portal as finally giving customers one truthful window into their own shipments instead of three phone numbers and a fax legend.[^s3]

The codename SEAGULL is reused. It was previously the working title of [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md)'s 2024–25 [QUAYSTONE pilot rollout](seagull-2024-25-quaystone-pilot.md) at the Bremen-Walle warehouse; that pilot phase is closed and its name was released for reuse. The portal programme is a separate initiative with its own mandate, budget line, and team, unrelated to the former pilot beyond the shared name, and [Jonas Petersen](../persons/jonas-petersen.md), as PMO, asked that documents use "SEAGULL" without qualification going forward, since the pilot usage is historical.[^s4]

The portal gives Blauwal's customers direct self-service over the web: near-real-time tracking of their own shipments, retrieval of shipment documents including the proof of delivery (POD), stock visibility for contract-logistics accounts, and booking of inbound time slots at the warehouses.[^s5] [Sabine Krüger](../persons/sabine-kruger.md) (Head of Warehouse Operations) set one condition, accepted without debate: the portal shows the operational truth or it shows nothing, since a portal that flatters the numbers would cost more trust than it buys.[^s6]

Lead architect [Marek Duszek](../persons/marek-duszek.md) set three architecture guardrails for the programme, transcribed in the minutes verbatim: the portal is built on the QUAYSTONE order and shipment APIs, with no direct database access — not for reading, not "just for the dashboard", not once, not ever; the portal holds no warehouse data of its own, only rendering what the platform answers; and customer identity and entitlements are a first-class design topic from week one, not a hardening sprint before launch.[^s7] He added that, after two years of migration discipline, he intends to defend these three lines "with the enthusiasm of a man who has seen the alternative."[^s8]

The programme targets a first customer launch in the second quarter of 2027.[^s9] Three pilot customers from the contract-logistics segment have agreed to co-design the first release; their names remain confidential at their own request until the pilot agreements are countersigned.[^s10] Okafor was explicit about sequencing: scope grows only after the three pilots are genuinely happy — "and genuinely means measured, not surveyed once at a steering meeting."[^s11]

Product ownership sits with Okafor; architecture is Duszek's, in an advisory capacity of two days a week.[^s12] The operations liaison is to be named by Sabine Krüger from the Bremen-Walle crew — the site that has lived on QUAYSTONE longest (see Open Points).[^s13] The programme reports monthly to the Geschäftsführung; its working language is English, with customer-facing material produced in German.[^s14]

The kickoff recorded three decisions: SG-2026-01 constitutes the SEAGULL portal programme with Yasmin Okafor as product owner; SG-2026-02 targets first customer launch for the second quarter of 2027 with three contract-logistics pilot customers; and SG-2026-03 makes the TOP 3 architecture guardrails binding for the programme.[^s15] Next meeting: SEAGULL steering, 12 May 2026, 10:00, in Bremen.[^s16]

For coordination with the portal timeline, [Petra Vogelsang](../persons/petra-vogelsang.md) (Head of IT) reported that [KOMET](../systems/komet.md)'s decommissioning has been brought forward to 31 July 2026, since the archive extraction for customs and audit history finished earlier than planned; the portal programme is unaffected but should note the date, as the last KOMET-era customer exports retire with it.[^s17]

## Open Points

### Pilot customer agreements
id: op-pilot-customer-agreements
- 2026-04-08: Action SG-AP-1 — pilot customer agreements to go to countersignature; owner Yasmin Okafor; due May 2026.[^s18]

### API coverage gap analysis
id: op-api-coverage-gap-analysis
- 2026-04-08: Action SG-AP-2 — gap analysis of portal use cases against current QUAYSTONE API endpoints; owner Marek Duszek; due 12 May 2026.[^s19]

### Operations liaison
id: op-operations-liaison
- 2026-04-08: Action SG-AP-3 — operations liaison to be named from the Bremen-Walle crew; owner Sabine Krüger; due 20 April 2026.[^s20]

## See also
- [Projekt LEUCHTFEUER](projekt-leuchtfeuer.md)
- [SEAGULL (2024–25 pilot)](seagull-2024-25-quaystone-pilot.md)
- [QUAYSTONE](../systems/quaystone.md)
- [KOMET](../systems/komet.md)
- [Blauwal Logistik GmbH](../organizations/blauwal-logistik-gmbh.md)
- [Yasmin Okafor](../persons/yasmin-okafor.md)
- [Marek Duszek](../persons/marek-duszek.md)
- [Sabine Krüger](../persons/sabine-kruger.md)
- [Petra Vogelsang](../persons/petra-vogelsang.md)
- [Jonas Petersen](../persons/jonas-petersen.md)

## Sources
[^s1]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name — Geschäftsführung decision, mandate, codename (ingested 2026-07-16)
[^s2]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § SEAGULL programme — kickoff meeting, minutes (customer self-service portal) — date, location, chair, minutes-taker (ingested 2026-07-16)
[^s3]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name — Okafor's opening framing (ingested 2026-07-16)
[^s4]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 1 — Mandate and name — codename reuse, PMO naming request (ingested 2026-07-16)
[^s5]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 2 — What the portal is — self-service capabilities (ingested 2026-07-16)
[^s6]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 2 — What the portal is — Krüger's operational-truth condition (ingested 2026-07-16)
[^s7]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails — the three guardrails (ingested 2026-07-16)
[^s8]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 3 — Architecture guardrails — Duszek's closing remark (ingested 2026-07-16)
[^s9]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 4 — Timeline and pilot customers — Q2 2027 launch target (ingested 2026-07-16)
[^s10]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 4 — Timeline and pilot customers — three pilot customers, confidentiality (ingested 2026-07-16)
[^s11]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 4 — Timeline and pilot customers — Okafor's sequencing quote (ingested 2026-07-16)
[^s12]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working — product ownership, architecture role (ingested 2026-07-16)
[^s13]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working — operations liaison role (ingested 2026-07-16)
[^s14]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § TOP 5 — Team and ways of working — reporting cadence, working language (ingested 2026-07-16)
[^s15]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Decisions — decisions SG-2026-01 through SG-2026-03 (ingested 2026-07-16)
[^s16]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Action items — next meeting line (ingested 2026-07-16)
[^s17]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § AOB — KOMET decommissioning brought forward (ingested 2026-07-16)
[^s18]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Action items — action SG-AP-1 (ingested 2026-07-16)
[^s19]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Action items — action SG-AP-2 (ingested 2026-07-16)
[^s20]: [raw/2026-04-08-minutes-portal-kickoff.md](../../raw/2026-04-08-minutes-portal-kickoff.md), § Action items — action SG-AP-3 (ingested 2026-07-16)
