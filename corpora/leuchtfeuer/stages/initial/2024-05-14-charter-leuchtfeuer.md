# Projekt LEUCHTFEUER — Programme Charter

**Document:** Programme charter, Projekt LEUCHTFEUER
**Version:** 1.0 — 14 May 2024
**Approved by:** Lenkungsausschuss, session of 7 May 2024
**Author:** Jonas Petersen (PMO), on behalf of the programme lead

## 1. Purpose

This charter is the single authoritative statement of what Projekt LEUCHTFEUER is, what it will
deliver, by when, with what money, and under whose governance. Where a slide, a mail, or a hallway
agreement disagrees with this charter, this charter wins until the Lenkungsausschuss amends it.

## 2. Background

Blauwal Logistik GmbH operates its warehouse estate on KOMET, a heavily customised warehouse
management system whose original vendor no longer exists. All maintenance is carried by the
internal IT organisation, without vendor support, against rising operational risk and standing
annual licence costs that purchase no improvement. The Geschäftsführung therefore decided on
27 February 2024 to replace KOMET across the estate with QUAYSTONE, the cloud WMS platform of
Gezeitenwerk Software GmbH, Hamburg, and constituted Projekt LEUCHTFEUER to deliver that
replacement.

## 3. Objectives

The programme is complete when all of the following hold:

- QUAYSTONE is the productive WMS at every Blauwal warehouse site, and KOMET is decommissioned.
- No shipment, stock, or article data is lost in migration; movement history required for customs
  and audit purposes is retained and retrievable.
- Every affected employee has been trained before the cutover of their own site.
- All external interfaces — ERP, customs, telematics, customer portals, label printing — run
  productively against QUAYSTONE.

## 4. Scope

**In scope:** replacement of the WMS at all warehouse sites; migration of article, stock, and open
order data; re-connection of all downstream interfaces; procurement and rollout of new mobile
data-entry devices; training; hypercare after each site cutover.

**Out of scope:** replacement of the ERP; transport management; building automation; any process
redesign not strictly required by the platform change. Scope additions require a steering-committee
decision and a documented budget impact.

## 5. Approach

The rollout is **phased, warehouse by warehouse**, per the steering decision of 7 May 2024
adopting the programme lead's April proposal. The pilot (working codename SEAGULL) runs first at
the Bremen-Walle warehouse and is followed by an explicit hold point: no further site is touched
until the pilot has run stably and its lessons are documented. The remaining sites then follow in
small groups with individual go/no-go decisions on data readiness, trained staff, and interface
test results. A site that is not ready waits for the next group.

## 6. Milestones

| milestone | date |
| --------- | ---- |
| Charter approved, programme constituted | 7 May 2024 |
| Pilot cutover, Bremen-Walle (SEAGULL) | August 2024 |
| Pilot hold point review | September 2024 |
| **Full estate live on QUAYSTONE** | **1 October 2024** |
| KOMET decommissioning and programme close | Q4 2024 |

## 7. Budget

The approved programme budget is **EUR 1.8 million**, granted by the Geschäftsführung on
27 February 2024. It covers platform licences, Gezeitenwerk implementation services, internal
personnel backfill, training, the mobile-device rollout, and a contingency reserve. The budget is
managed by the Commercial Director; any forecast overrun must be escalated to the
Lenkungsausschuss before it is incurred, and an increase requires a new decision of the
Geschäftsführung.

## 8. Platform

The target platform is QUAYSTONE (cloud deployment) by Gezeitenwerk Software GmbH. Per steering
decision D-4 of 5 March 2024, the deployment's persistence layer runs on **KorallenDB**. The
dissent of the lead architect on the database choice is recorded in the kickoff minutes.

## 9. Governance

The Lenkungsausschuss meets monthly and is the programme's decision body; its working language is
German and its minutes are authoritative. The programme lead (Petra Vogelsang) chairs and reports;
the lead architect (Marek Duszek) owns technical decisions within the platform frame set by the
committee; warehouse operations (Sabine Krüger) owns master data and training; the Commercial
Director (Heike Brandt) owns budget and vendor commercials; the PMO (Jonas Petersen) keeps the
record. The account manager of Gezeitenwerk attends as a guest without vote.

## 10. Principal risks

- **Master data quality.** Duplicate article records across sites; cleansing is a hard
  precondition for the pilot cutover and is tracked monthly.
- **Interface surface.** The number and variety of downstream connections is the largest single
  work package; each connection needs explicit conversion review and test time.
- **Key-person dependency.** Knowledge of KOMET internals is concentrated in very few people;
  their availability is a programme risk until decommissioning.
- **Timeline ambition.** The milestone plan has no slack between the pilot hold point and the
  full-estate date; any pilot slippage moves the estate date. The committee accepts this risk
  knowingly in exchange for a shorter dual-running period.

## 11. Change control

This charter is amended only by decision of the Lenkungsausschuss, recorded in its minutes, and
re-issued by the PMO as a new version of this document. Superseded versions are withdrawn from
circulation.
