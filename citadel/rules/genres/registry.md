# registry — enumerable-entry sources (inventories, catalogs, rosters, code lists)

Applies when the source is — **or contains** — a **uniform enumeration of like entries** whose
value lies in being complete: a machine/asset inventory, a product catalog or price list, a
customer or contact roster, an error-code / problem-type table, a server or license inventory, a
bill of materials. Test: *the entries share one attribute shape, and a reader would ask "is X on
the list?"*. Run that test on every **list-shaped section** — a table, an appendix, a bulleted
inventory, a repeated stanza block — not only on the source as a whole: a prose report whose
appendix lists 20 machines is prose PLUS a registry, and the appendix alone triggers this brief.
When the test holds, the enumeration is captured completely on a `Registry` page — this brief
says how. It also applies when the wiki **already holds a registry** covering an entity this
source mentions (§ Any source maintains the rows), even if this source enumerates nothing.

## Completeness over compression

**Every entry gets a row — a skipped entry is an error, not a compression.** The granularity
floor (`core.md` § Restructuring) limits *pages*, never *rows*: compressing the tail of a catalog
into one summary sentence loses exactly the answers a registry exists for ("is X on the list?",
"what does code E-142 mean?").

- WRONG: `The catalog also lists survey chains, thermometers, sounding leads, and a rain
  gauge.[^s9]` — four products, one citation, no per-entry attributes, none findable.
- RIGHT: four bullets, four citations, each with its own locator and its stated attributes.

When the source states a total ("the plant operates 28 machines"), cite that count in the scope
paragraph — it is the registry's own completeness check.

## One page per collection

Route the enumeration to **one `Registry` page per collection** (`type: Registry` →
`wiki/registries/`; format contract: `schema.md` § Registries) — never one page per entry, and
never rows scattered as loose facts across topic pages. Like a `System` page, a registry
**accumulates across sources**: a later source listing the same collection extends the SAME page
— search for an existing registry before creating one. Title it after the collection and its
scope ("Machine registry — Aldervik plant"), never a bare "Index" or "Catalog".

## Row shape and identity

One bullet = one entry = its own citation:

```
- **HX-201** — heat exchanger, commissioned 1998, in service.[^s2]
```

- The **bold key is the entry's stable identity**: the source's own identifier verbatim (machine
  number, error code, customer ID) when it has one, else the entry's name. **Search before you
  append** — grep the page (and the wiki) for the key first, and extend the existing row instead
  of adding a near-duplicate; a second row under a variant spelling forks the entry silently.
- Group rows under `##` sections only when the source's own structure suggests it (by building,
  class, code range).
- Cite the **finest locator the format offers**: `lines A-B` (often a single line) for text and
  CSV entries; for a spreadsheet, rows of one sheet legitimately share that sheet's single
  `§ Sheet: X` marker — the sheet IS the location — with the covered keys named in the
  definition's free-text note. Facts from different places in the source still get separate
  markers (`schema.md` § Locators).

## Promotion past the granularity floor

The floor itself is unchanged: an entry earns its **own page** only when it carries several
independent cited facts (typically from a second source — a service report, a complaint, a spec).
When it does, create that page **typed by its own kind** — a machine → `Object`, a customer →
`Organization` or `Person`, a service → `System` — and reduce the registry row to **key + link +
one-line gloss + its membership citation**:

```
- **PV-014** — [PV-014 pressure vessel](../objects/pv-014-pressure-vessel.md) — 2019 vessel,
  under observation since June.[^s4]
```

The facts move to the entry's page and live ONLY there — never duplicated on the row.

## Any source maintains the rows

A registry is maintained by **every source that mentions a member**, not only by re-reads of the
enumerating source. Before routing facts about a **keyed entity** — a machine number, an error
code, a customer/license/asset ID — check `registries/` for a registry whose collection covers
it:

- A **status or attribute change** this source states updates the row, cited to this source (the
  superseded value survives as a dated `## Change Log` line — § Rows change over time).
- A **member the registry lacks** gets a new row cited to this source. The scope paragraph's
  stated total stays as its source stated it (it is that source's claim); the extra row stands
  beside it.
- An entity **past the granularity floor** still gets its own page (§ Promotion) — the row keeps
  the key + link + gloss.

Never fork the collection: facts about a listed member belong on its row (or its promoted page),
never as loose facts on a topic page where a search for the key will miss them.

## Rows change over time

Reconcile rules (`tasks/reconcile.md`) apply per row: a changed value updates the bullet, and the
superseded value survives as a dated `## Change Log` line on the registry page
(`genres/meeting-minutes.md` § Dates). A row the current source no longer lists loses this
source's marker — and when no source supports it anymore, it moves to a dated Change Log line
("2026-07: removed from the inventory.[^sN]") instead of vanishing silently; a registry's history
is part of its value.

## When a registry outgrows a page

Split a too-long registry **by key range or subclass** into sibling `Registry` pages
(`machine-registry-building-7.md`, `error-codes-e100-e199.md`), the original becoming a short hub
page linking the parts — **never a topic split**, and every row keeps its `[^sN]` marker and
`## Sources` definition.

## When NOT to registry

- Items with a terminal "done" state (action items, to-dos, open issues) → `## Open Points`
  (`genres/meeting-minutes.md`).
- Chat logs, event streams, timelines — the rows are *events in time*, not standing members of a
  collection; genre judgment and noise rules apply (`genres/chat.md`, `genres/social.md`).
- Code symbols — functions, classes, endpoints — stay under `core.md` § Code & structured
  sources (but a *data* table inside a repo is data, and this brief applies).
- A paper's references/bibliography section (`genres/publication.md` — cited works are not
  sources).
- A handful of heterogeneous one-off mentions — ordinary cited facts on the parent page; the
  registry treatment needs uniform shape.
- Abbreviation glossaries → the existing `Abbreviation` machinery (`schema.md` § Abbreviations).

Compose with `genres/contract.md` when the entries carry legal/financial amounts (verbatim
figures), and with `formats/office.md` for spreadsheet locator grammar.
