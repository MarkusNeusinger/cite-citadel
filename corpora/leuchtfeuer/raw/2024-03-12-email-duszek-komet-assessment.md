From: Marek Duszek <m.duszek@blauwal-logistik.example>
To: Petra Vogelsang <p.vogelsang@blauwal-logistik.example>
Cc: Sabine Krüger <s.krueger@blauwal-logistik.example>; Heike Brandt <h.brandt@blauwal-logistik.example>; Jonas Petersen <j.petersen@blauwal-logistik.example>
Date: Tue, 12 Mar 2024 08:47:00 +0100
Subject: KOMET estate assessment (AP-2) — read before the Lenkungsausschuss

Assessment done, three days early. Long form is in the project share; the short form is below. No
slides, on principle.

1. KOMET runs in eleven warehouses. Every site carries local customisations and no two
installations are identical. Anyone who plans this migration on the assumption of "one template,
N copies" is planning fiction, and I will say so in writing every time it comes up. The per-site
delta list is section 5 of the assessment; some of those deltas exist because a forklift broke in
2011 and the workaround became the process.

2. KOMET exchanges data with 27 downstream systems — the ERP, customs, the telematics units in
the fleet, three customer portals, label printing, staging robots in Walle, the works. Before
this assessment, nobody in this company had ever seen a complete and current interface inventory;
building one was most of the work, and I am now confident in that number. Every single one of
those 27 connections has to be re-pointed, re-tested, or consciously killed during the migration.
This is the real project. The software swap is the easy part.

3. The original vendor, Werftmann & Partner Softwarehaus GmbH, went insolvent in 2017. Since then
there has been no vendor support of any kind: my team patches KOMET ourselves, against a codebase
whose documentation stops mid-sentence in places. Two of the three people who understand the
allocation module are older than the module. This is the actual risk clock ticking under the
company, and it ticks regardless of what we decide in any meeting.

4. On the money, Heike said it more crisply than I could, so I will simply quote her instead of
paraphrasing badly. From her mail of Monday:

   On Mon, 11 Mar 2024 at 16:42, Heike Brandt <h.brandt@blauwal-logistik.example> wrote:
   > To put a number on the standstill: the annual licence and support
   > contracts for KOMET now stand at EUR 310,000 — for a system whose
   > vendor has not existed for seven years. We pay this every year for
   > the privilege of standing still.

   Nothing in the TCO comparison is close. Migration wins in every scenario my team has modelled,
   including the pessimistic ones where the timeline doubles. The numbers are hers; the
   architecture conclusion is mine; they point the same way.

5. Interfaces are where migrations die, so one cautionary tale for the file. It is never the big
design that kills you, it is the boring conversions — units, encodings, field lengths. The Mars
Climate Orbiter burned up in 2001 because one team wrote pound-seconds where the other read
newton-seconds; a spacecraft was lost over a unit label nobody re-checked. Our customs interface
alone carries four unit conversions of exactly this shape. I want explicit review time for every
one of them in the plan, not a line item called "testing, misc".

6. For the record, since Tuesday's minutes recorded my dissent but not my reasons: I still think
KorallenDB is the wrong call. If it were my decision we would build on BasaltDB from day one — the
replication story is simpler, the operational tooling is a decade ahead, and the licence terms are
honest. This is my professional opinion, not a fact about the universe, and the committee has
decided otherwise; I will implement the decision properly and without sabotage-by-sulking. But I
want the opinion in writing, dated, so that whichever way this goes, we can learn from it instead
of re-arguing it from memory.

7. Full assessment: 34 pages, project share, folder "AP-2". Read at minimum section 2 (interfaces)
and section 5 (customisations) before the 19th. If you read only one page, read the interface
inventory and count to 27 yourself.

—MD
