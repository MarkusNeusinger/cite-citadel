# Ground truth — the werkhof corpus

This is the **answer key** for the `werkhof` corpus (`corpora/werkhof/`). It lives under
`.claude/` (outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can never
see it. The verify-corpus skill reads it to grade the wiki the pipeline produced.

`werkhof` is the **registry corpus**: three of its four sources are uniform enumerations (a
machine register, a fault-code catalogue, a customer CSV) whose value lies in being **complete**.
Its corpus-wide guarantee is the `Registry` page kind (`genres/registry.md`): one page per
collection, one cited row per entry, **no entry compressed away** — plus **promotion**: an entry
with several independent cited facts (from the service report) moves to its own page of its own
kind, its row becoming a link + one-line gloss.

> Everything is **fictional by design** (Werkhof Anlagenservice Brandt, the Aldervik yard, every
> machine, manufacturer, customer, and person). The wiki must record it faithfully as stated.

## The 4 source files

| file | genre | gist |
| ---- | ----- | ---- |
| `maschinenbestand-2026.md` | machine register (registry) | **28 machines** in `###` blocks across four sections, stated total ("all 28 machines"); DL-102 decommissioned 2024 but still listed; PV-014 "inspection due June 2026"; near-miss IDs **HX-201** (shell-and-tube) vs **HX-210** (plate) |
| `stoercode-katalog.md` | fault-code catalogue (registry) | **20 codes** E-101…E-500, stated total; **E-155 deprecated** since rev. 3 (2024), replaced by **E-310**; near-miss **E-142** (compressed-air pressure sensor) vs **E-412** (coolant temperature sensor) |
| `kundenliste.csv` | customer list (registry, CSV) | **15 customers** K-001…K-015 with city/contract/since; K-007 = Nordwerk Maschinenbau GmbH, Wischhafen |
| `wartungsbericht-2026-06.md` | service report (prose + open items) | PV-014 inspection (4 findings + 1 opinion) → **promotion**; HX-201 out of service 2026-06-12 (**supersedes** the register's "in service"); KP-011 logged **E-142**; Nordwerk visit (4 facts) → **promotion**; 3 done-able **open items** |

Sandbox: one ingest pass, one agentic session per file (4 sessions, serial is fine).

## A · Registry completeness — the corpus-wide HARD gate

One `type: Registry` page per collection under `registries/` (three pages; exact titles/slugs are
the agent's), each with a cited scope statement. **A missing entry is a creation defect** — the
whole point of the corpus:

| id | guarantee | check |
| -- | --------- | ----- |
| `R1` | **all 28 machines** appear as rows on ONE machine-registry page: DL-101, DL-102, FR-110, FR-111, CN-120, CN-121, SW-130, PU-140, KP-010, KP-011, KP-012, PV-013, PV-014, HX-201, HX-210, KR-301, KR-302, ST-310, ST-311, ST-312, WB-320, GN-401, TR-410, CH-420, CT-430, BL-440, WT-450, FS-460 | grep the registry page for each key; count = 28 |
| `R2` | **all 20 fault codes** appear as rows on ONE fault-code-registry page: E-101, E-102, E-110, E-115, E-120, E-142, E-155, E-160, E-201, E-210, E-230, E-250, E-301, E-310, E-320, E-350, E-412, E-420, E-455, E-500 | grep; count = 20 |
| `R3` | **all 15 customers** appear as rows on ONE customer-registry page: K-001…K-015 with their names | grep; count = 15 |
| `R4` | the register's stated total ("all 28 machines") appears in the machine registry's scope statement, cited | read the page head |
| `R5` | each row carries its **own citation** with a locator (`lines A-B` into the register — REQUIRED there, the source is >200 lines); `citadel lint` reports **no locator issues** on the registry pages | lint + spot-check 3 locators resolve to the right block |

Retrieval-first: `citadel search "KP-011"`, `search "E-420"`, and `search "K-009"` (mid-list keys
that appear nowhere else) must each surface the matching registry page in the top results.

## B · Promotion past the granularity floor

| id | guarantee | check |
| -- | --------- | ----- |
| `P1` | **PV-014** has its own `objects/` page carrying the report facts: wall thickness 6.2 mm (down from 6.8 mm, 2023), pressure test passed at 14 bar, corrosion at nozzle N2 ground back and recoated, interval shortened 24 → 12 months / under observation | read the page |
| `P2` | the machine registry's PV-014 **row is a link + one-line gloss** to that page — the inspection facts are NOT duplicated on the row | read the row |
| `P3` | **Nordwerk Maschinenbau GmbH (K-007)** has its own `organizations/` page: contract extended to end of 2028, two visits/year from 2027, contact R. Albers (plant manager) | read the page |
| `P4` | the customer registry's K-007 row links to it | read the row |
| `P5` | machines with only their register block (e.g. WB-320, CT-430) do **NOT** get their own pages — the floor still holds; rows are enough | glob `objects/` |

## C · Supersession, near-misses, and judgment

| id | guarantee | check |
| -- | --------- | ----- |
| `S1` | HX-201's current status is **out of service since 2026-06-12** (tube leak), cited to the report — and the register's "in service" survives as a **dated trace** (Change Log line or dated wording), never silently overwritten | read the row / page |
| `S2` | HX-201 and **HX-210** stay two distinct entries (shell-and-tube vs plate); the report's "HX-210 covers summer load, not full winter load" is captured and cited | grep |
| `S3` | **E-142** and **E-412** are not conflated (pressure sensor vs coolant temperature sensor); KP-011's logged fault cites **E-142** and cross-links compressor and code | read |
| `S4` | **E-155** is recorded as deprecated (since rev. 3, 2024) with the hand-over to **E-310** — still a row, not dropped | grep |
| `S5` | Petersen's replacement-vessel recommendation and the Albers complaint are **attributed** ("Petersen recommends…", "Albers complained…"), never world facts | grep for unattributed forms |
| `S6` | the report's three **open items** (tube bundle, ultrasonic re-test, maintenance plan) live in an `## Open Points` thread (done-able items), **not** as registry rows | read |

## D · The CSV boundary

| id | guarantee | check |
| -- | --------- | ----- |
| `D1` | the `.csv` is treated as **data, not code**: its 15 rows are captured (R3) — not "essenced" into a one-line summary, and no `[^llm]` filler invented around it | R3 + grep `[^llm` |

## E · Structural gates

`citadel check` and `citadel lint` exit 0 (advisories allowed; no structural errors). All three
registry pages carry `type: Registry` and sit under `registries/` (routing — a registry filed
under `concepts/` or `misc/` is a creation defect). The wiki links form one connected graph:
registry pages ↔ promoted pages ↔ the report's facts.
