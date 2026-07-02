# meeting-minutes — time-anchored tracking artifacts

Applies when the source reads like a **time-anchored tracking artifact**: meeting minutes, a
status update/mail, an open-points / action-item / TODO list, a decision log, a changelog, a spec
revision. Its value is the **sequence over time** — what was decided when, who owns the
follow-up, what is still open, how a design evolved — which the plain per-fact fold-out
dissolves. When you meet one, do the normal fold-out **and** maintain a dated thread.

## When this genre applies — and when not

A source is a tracking artifact when its **shape** says so (a dated header + attendees/owners; a
list of action items / decisions / "offene Punkte" / open issues / next steps / blockers;
per-item owners and due dates; a status mail that refers to prior items — "update on X", "still
open", "now resolved", "closed") **or** its **semantics** say so even without that shape (an
unstructured note that names an owner and an unresolved action — "Ana will look at the DB, aiming
for next sprint"). It is **not** a tracking artifact when its items are **standing/recurring** —
a runbook, checklist, policy, or reference table. Test: *can this item reach a terminal "done"
state?* If items are perennial, ingest as ordinary facts, no thread.

## Fan-out stays mandatory; the thread is an additive overlay

Every durable fact still becomes a normal cited sentence on the right entity page, exactly as
always — if you deleted the thread, no durable fact would be lost. The thread is a thin dated
ledger *on top*. So under any doubt about the genre, just fold out the facts: threading is the
higher-confidence extra step, and erring toward **not** threading is always safe.

## Where a point lives + its identity

Put the thread on the **most-relevant entity page** (the Object/System/Project/Concept the point
concerns — routed like any page), under a section headed exactly `## Open Points`. Each point is:

```
## Open Points

### Checkout latency under load
id: op-checkout-latency
- 2026-05-01: raised; users report ~30s hangs at checkout. [^s1]
- 2026-06-10: root-caused to DB pool exhaustion; fix targeted for 4.2. [^s3]
```

The `id:` line is the point's **stable identity**: `op-` + the title run through the standard
title→slug rule (`schema.md` § Page file format). Derive the slug from the point's own noun
phrase, stripping ticket numbers, dates, and status words ("Fix login timeout — still open
(JIRA-42)" → `op-login-timeout`), so two sources describing the same point converge on the same
id the way two sources about *Self-Attention* converge on one page.

## Search before you append

**Before you add a point, read the whole `## Open Points` section of that page** (Grep the wiki
for `op-<slug>` too) and either append to the existing matching `### `/`id:` block or justify to
yourself that the point is genuinely new. A near-miss on the name forks the thread silently — no
gate can merge it — so this search-before-append step is load-bearing.

## Appending across sources (this is `ingest`, not `reconcile`)

A later source updating a point is a brand-new source (task `ingest`), so nothing auto-connects
it — YOU connect it by the search above. To append: add **one** new dated bullet with its own
`[^sN]` marker and `## Sources` definition (reuse the multi-source citation grammar), leaving the
existing bullets untouched.

- **Dated bullets are append-only history — never rewrite or delete one, even on `reconcile`.**
  The reconcile rule ("remove a fact the current file no longer supports") does **not** apply to
  dated bullets: they record *what was believed then*. A correction is a **new** dated bullet
  ("2026-07-05: earlier root-cause retracted; actual cause was a network timeout. [^s3]"), not an
  edit to the June line.
- **Status is derived, not stored.** Do **not** write a mutable `Status:` field — the system
  reads the current state from the latest dated bullet. A point is *done* when the newest bullet
  says so (resolved / done / closed / fixed / shipped / erledigt / abgeschlossen); a regression
  is just a new bullet, which reopens it automatically. One source of truth.

## Status supersede ≠ contradiction

A point advancing in time ("open" then later "resolved") is **not** a contradiction — do not wrap
it in a `> [!CONTRADICTION]` callout. Contradictions are two sources disagreeing about the *same
point in time*; a status transition is the same point moving *forward*. The dated bullets already
carry both sources.

## Dates, and design that changes over time

Date each bullet with the date stated **inside** the source (meeting date, `Date:` header,
"Stand: …", a revision table); if the source states no date, fall back to the **source file's own
date, given in your run instruction**. **The date is what distinguishes a contradiction from an
evolution.** When two sources give *different* values for the same **changeable** attribute of a
thing (housing material Kunststoff → aluminium → coated; corners round → chamfered), and they
carry *different* dates, that is a **design change over time, not a conflict**: record it as a
dated thread under a `## Change Log` section on that thing's page, newest value last, and keep
the **current** value as the live cited fact in the body. Only when the values describe the
*same* moment (or an immutable property) and truly cannot both hold do you use a
`> [!CONTRADICTION]` callout. When in doubt which it is, prefer the dated Change-Log reading if
the dates differ.

The generated `wiki/open-points/index.md` catalog (built mechanically from every `## Open Points`
section) is the derived "what's still open / timeline per point" view, and `citadel lint`
surfaces near-duplicate and malformed points — neither is a source of truth; both are recomputed
from the pages. Never author the catalog (`core.md` § Off-limits).
