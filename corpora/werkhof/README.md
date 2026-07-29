# werkhof — enumerable sources (registries: complete, per-entry-cited capture)

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and written for testing
> cite-citadel. *Werkhof Anlagenservice Brandt*, the Aldervik yard, every machine, customer,
> manufacturer, person, and figure are **fictional**. Safe to publish (MIT).

The registry corpus: the only one whose sources are **uniform enumerations** — a machine
register, a fault-code catalogue, a customer list — where the wiki's value lies in being
**complete**. It grades the `Registry` page kind (`genres/registry.md`, `type: Registry` →
`registries/`): one page per collection, one cited row per entry, and **promotion** — an entry
that accumulates several independent cited facts moves to its own page of its own kind, its
registry row becoming a link plus a one-line gloss.

The fictional world: **Werkhof Anlagenservice Brandt**, a mid-size industrial maintenance firm
at the Aldervik yard — machine register, fault codes, frame-contract customers, and a monthly
service report.

## The sources

| file | what it is | the thing it tests |
| ---- | ---------- | ------------------ |
| `maschinenbestand-2026.md` | the machine register: **28 machines** in blocks, with a stated total | registry **completeness** (every machine a cited row, none compressed away), per-row locators on a >200-line source, the near-miss pair **HX-201 vs HX-210** |
| `stoercode-katalog.md` | the fault-code catalogue: **20 codes** incl. one deprecated | a second registry; the near-miss pair **E-142 (pressure sensor) vs E-412 (temperature sensor)**; the deprecated **E-155 → E-310** hand-over must survive as stated |
| `kundenliste.csv` | the customer list: **15 customers** as CSV rows | the data-not-code boundary — a `.csv` is a dataset, not code structure; its rows are captured, not "essenced" away |
| `wartungsbericht-2026-06.md` | the June 2026 service report | **promotion** past the granularity floor (PV-014 → its own `objects/` page, Nordwerk/K-007 → `organizations/`), the **HX-201 status supersession** (in service → out of service, dated), a correct **E-142** usage tying the registries together, attributed opinions, and a done-able **Open items** list that belongs in `## Open Points`, never in a registry |

## What a good wiki looks like

- Three registry pages under `registries/` (machines, fault codes, customers), each opening with
  a cited scope line (the register's own "28 machines" total is itself a citable fact), each
  entry one bullet with its **bold source-verbatim key** and its own citation.
- PV-014 and Nordwerk Maschinenbau promoted to their own pages; their registry rows reduced to
  key + link + one-line gloss — no fact duplicated onto the row.
- HX-201's row shows the current status (out of service since 2026-06-12) with the register's
  "in service" surviving as a dated trace, not silently overwritten.
- The report's open items live as `## Open Points` threads (they can reach "done"), not as
  registry rows.

The hidden answer key lives at `.claude/skills/verify-corpus/werkhof/ground-truth.md` — outside
the corpus, so the ingest agent never sees it.
