# Projekt LEUCHTFEUER — kickoff meeting, minutes

**Date:** Tuesday, 5 March 2024, 09:30–12:15
**Location:** Blauwal Logistik GmbH, Hauptverwaltung Bremen, room Weser 2
**Chair:** Petra Vogelsang (Head of IT, programme lead)
**Minutes:** Jonas Petersen (PMO)

**Present:** Petra Vogelsang (IT, chair) — Marek Duszek (lead architect) — Sabine Krüger (Head of
Warehouse Operations) — Heike Brandt (Commercial Director) — Tomás Iglesias (Gezeitenwerk Software
GmbH, account manager) — Jonas Petersen (PMO)
**Apologies:** none

## TOP 1 — Why this programme exists

Petra opened the meeting by walking the room through the decision the Geschäftsführung took on
27 February 2024: Blauwal Logistik GmbH will replace KOMET, the warehouse management system (WMS)
the company has customised and patched in-house for many years, with QUAYSTONE, the cloud WMS
platform sold by Gezeitenwerk Software GmbH of Hamburg. The replacement programme runs under the
name Projekt LEUCHTFEUER, and this meeting constitutes it.

Nobody in the room needed convincing on the *why*. KOMET's original vendor no longer exists, so
every bug fix, every carrier change, and every customs-regulation update lands on Marek's team
alone, with no escalation path behind them. Heike added the commercial angle: the money Blauwal
pays every year merely to keep KOMET's licences and support contracts alive buys no improvement of
any kind. She will put the exact figures in writing for the steering committee so the business case
is documented, not folklore.

## TOP 2 — Current estate

Marek gave a first, deliberately verbal sketch of the KOMET estate and asked for two weeks to put a
proper written assessment together (action AP-2). His one warning to the room: do not
underestimate the integration surface. "The WMS is the spider in the web here — everything in this
company touches it." The written assessment will enumerate the sites, the interfaces, and the
local customisations one by one, so that planning rests on counted facts rather than on estimates
shouted across a meeting table.

Sabine flagged the state of the article master data as the operational risk she loses sleep over.
Years of parallel maintenance in KOMET have left duplicate article records across the sites, and
migrating duplicates means multiplying them. The meeting agreed without dissent that the master
data must be cleansed **before** the pilot cutover, not patched afterwards (action AP-1).

## TOP 3 — Budget

Heike confirmed that the Geschäftsführung has approved a programme budget of EUR 1.8 million for
Projekt LEUCHTFEUER. The envelope covers the QUAYSTONE licences, implementation services from
Gezeitenwerk, internal backfill for the line organisation, training, and a contingency reserve. She
was explicit that this figure is the whole envelope: "If we need more, we go back to the
Geschäftsführung — and nobody in this room wants that meeting."

## TOP 4 — Timeline and pilot

After discussion the meeting set the headline target: **the full warehouse estate goes live on
QUAYSTONE on 1 October 2024** (decision D-3). Tomás confirmed that Gezeitenwerk can staff the
implementation to that date, provided the master data arrives clean and the interface
specifications are frozen by early summer.

The pilot will run at the Bremen-Walle warehouse under the working codename **SEAGULL**, starting
in the third quarter of 2024 (decision D-2). Walle was chosen deliberately: it is mid-sized, it
sits close to headquarters, and Jörn Albers's team there is regarded as the most change-friendly
crew in the estate. Whatever SEAGULL teaches us, it teaches us cheaply and close to home.

How the remaining sites follow the pilot — one warehouse at a time, or a single coordinated
cutover of everything at once — was **left open**. Opinions in the room differed and the chair
declined to force the question today. Petra will circulate a written cutover-strategy proposal in
early April (action AP-3), and the steering committee will decide.

## TOP 5 — Platform database

Tomás presented the two deployment options Gezeitenwerk supports for QUAYSTONE's persistence
layer. On his recommendation the meeting decided that Blauwal's deployment will run on
**KorallenDB** (decision D-4). Marek argued against this choice at some length and asked that his
dissent be recorded in the minutes, which is hereby done. He stated he will not re-litigate the
point outside the steering committee.

## Decisions

- **D-1** — Projekt LEUCHTFEUER is constituted as described; programme lead: Petra Vogelsang.
- **D-2** — Pilot at the Bremen-Walle warehouse, working codename SEAGULL, starting Q3 2024.
- **D-3** — Target go-live for the full estate: 1 October 2024.
- **D-4** — The QUAYSTONE deployment runs on KorallenDB (dissent Duszek, recorded).

## Action items

- **AP-1** — Article master data cleansing across the estate — owner: Sabine Krüger — due: before
  the pilot cutover.
- **AP-2** — Written assessment of the KOMET estate — owner: Marek Duszek — due: 15 March 2024.
- **AP-3** — Cutover-strategy proposal — owner: Petra Vogelsang — due: early April 2024.

**Next meeting:** Lenkungsausschuss (steering committee), 19 March 2024, 14:00, Bremen. Steering
committee minutes are kept in German.
