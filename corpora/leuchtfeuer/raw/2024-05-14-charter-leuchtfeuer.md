# Projekt LEUCHTFEUER — Programme Charter

**Document:** Programme charter, Projekt LEUCHTFEUER
**Version:** Revision B — 20 January 2025
**Approved by:** Lenkungsausschuss, by circular resolution of 17 January 2025
**Author:** Jonas Petersen (PMO), on behalf of the programme lead

> **Revision note.** Revision B supersedes Version 1.0 of 14 May 2024 **in full**. Figures and
> dates that Revision B replaces are deliberately not restated in this document; the decision
> history behind each change lives in the steering-committee minutes, which remain authoritative
> for how and when each change was decided. Superseded versions are withdrawn from circulation.

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
replacement. The first programme year showed the original milestone plan to have been too
ambitious for the interface and master-data reality of the estate; Revision B resets the plan on
measured ground rather than ambition.

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

The rollout remains **phased, warehouse by warehouse**, per the steering decision of 7 May 2024.
The pilot (working codename SEAGULL) runs first at the Bremen-Walle warehouse and is followed by
an explicit hold point: no further site is touched until the pilot has run stably and its lessons
are documented. The remaining sites then follow in small groups with individual go/no-go decisions
on data readiness, trained staff, and interface test results. A site that is not ready waits for
the next group.

## 6. Milestones (Revision B)

| milestone | date |
| --------- | ---- |
| Revision B approved | 17 January 2025 |
| Pilot cutover, Bremen-Walle (SEAGULL) | 22–23 February 2025 |
| Pilot hold point review | April 2025 |
| **Full estate live on QUAYSTONE** | **30 June 2025** |
| KOMET decommissioning and programme close | Q4 2025 |

## 7. Budget

The approved programme budget is **EUR 2.4 million**, per decision of the Geschäftsführung of
16 January 2025 on the committee's escalation. It covers platform licences, Gezeitenwerk
implementation services, internal personnel backfill, training, the mobile-device rollout, an
enlarged interface work package, and a contingency reserve. The budget is managed by the
Commercial Director; any forecast overrun must be escalated to the Lenkungsausschuss before it is
incurred, and a further increase requires a new decision of the Geschäftsführung.

## 8. Platform

The target platform is QUAYSTONE (cloud deployment) by Gezeitenwerk Software GmbH. The
deployment's persistence layer runs on **BasaltDB**, per the database decision taken by circular
resolution of the Lenkungsausschuss on 13 January 2025. The migration of the persistence layer is
executed before the pilot cutover, so that the pilot runs on the target stack from its first day.

## 9. Governance

The Lenkungsausschuss meets monthly and is the programme's decision body; its working language is
German and its minutes are authoritative. The programme lead (Petra Vogelsang) chairs and reports;
the lead architect (Marek Duszek) owns technical decisions within the platform frame set by the
committee; warehouse operations (Sabine Krüger) owns master data and training; the Commercial
Director (Heike Brandt) owns budget and vendor commercials; the PMO (Jonas Petersen) keeps the
record. The account manager of Gezeitenwerk attends as a guest without vote.

## 10. Principal risks (Revision B)

- **Interface surface.** Confirmed as the largest work package by the first programme year; each
  connection carries explicit conversion review and test time in the Revision B plan.
- **Master data quality.** Cleansing has progressed but remains a hard precondition for the pilot
  cutover; it is tracked monthly until closed.
- **Key-person dependency.** Knowledge of KOMET internals remains concentrated in very few people
  until decommissioning.
- **Dual running.** The longer programme means a longer period of running two systems in
  parallel; the committee accepts this consciously in exchange for per-site go/no-go quality
  gates.

## 11. Change control

This charter is amended only by decision of the Lenkungsausschuss, recorded in its minutes, and
re-issued by the PMO as a new version of this document. Superseded versions are withdrawn from
circulation.
