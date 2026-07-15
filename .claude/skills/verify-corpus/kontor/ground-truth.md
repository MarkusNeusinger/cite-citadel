# Ground truth — the kontor corpus

This is the **answer key** for the `kontor` corpus (`corpora/kontor/`). It lives under `.claude/`
(outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can never see it. The
verify-corpus / bench-model skills read it to grade the wiki the pipeline produced.

`kontor` is the only **Office-documents** corpus. It is the sole test of citadel's binary-Office
pipeline: **OOXML** text extraction (`.pptx` slides + speaker notes, `.docx` paragraphs + tables,
`.xlsx` multi-sheet cells), **legacy OLE** salvage (`.doc`/`.ppt`/`.xls`), the **embedded-image
delta** (`CITADEL_IMAGE_SUPPORT` — a chart whose number lives only in pixels), **dedup-by-basename**
(one format preferred, the twin skipped), and **ignore-patterns** (junk files skipped at discovery).
On top of that it carries the same discriminative judgment traps the other hardened corpora do
(cross-source contradiction, attribution, entity-variance merge, near-miss ≠ contradiction, temporal
supersession) so it separates a strong model from a weak one, not just a working pipeline from a
broken one.

> Everything is **fictional by design** — *Aldervik Kontor*, its people, warehouses, and every
> figure. The Office files are **generated deterministically** by a committed stdlib script
> (`make_office.py`, no third-party libraries), so they are regenerable. Nothing is copied from any
> real document. Safe to publish (MIT).

## The 8 ingested sources + 3 junk files, and the two-mode protocol

citadel extracts each Office file's TEXT to a temp markdown for the agent (the wiki still cites the
ORIGINAL Office file), and — when `CITADEL_IMAGE_SUPPORT=1` — also hands over the images embedded in
it. So the modes differ by whether the chart PNG is read.

| file | kind | key content |
| ---- | ---- | ----------- |
| `q3-review.pptx` | OOXML PowerPoint | Q3 2026 revenue EUR 6.4 M (from 5.8 M in Q2); **142** staff; warehouses Rotterdam/Hamburg/Gdansk; **speaker notes:** Lisbon warehouse NOT approved, Q4 opening tentative; **chart PNG only:** `GROSS MARGIN 34.2%` |
| `policy-handbook.docx` | OOXML Word | "Aldervik **Trading** Kontor"; support hours Mon–Fri 09:00–17:00 CET; a role/leave/remote **table**; six-month probation |
| `budget-2026.xlsx` | OOXML Excel | sheet **Summary** (Marketing 88 k, Engineering 150 k, Warehousing & Logistics 210 k, Sales 120 k, **Total 568 k**); sheet **Headcount** (Total **138** FTE) |
| `legacy-memo.doc` | legacy OLE Word | 12 Mar 2019: **two** warehouses (Rotterdam, Hamburg); team "about 40" |
| `legacy-deck.ppt` | legacy OLE PowerPoint | 2018 kickoff: founded **2011** in Aldervik harbour; original business dried goods + textiles |
| `legacy-ledger.xls` | legacy OLE Excel | 2019 year-end: staff **38**; revenue EUR 4.1 M |
| `report.docx` | OOXML Word | 2026 sustainability summary: warehouse energy use fell **12 %** YoY |
| `report.doc` | legacy OLE Word | *same content as `report.docx`* — the dedup twin, must be **skipped** |
| `Thumbs.db`, `desktop.ini`, `~$policy-handbook.docx` | junk | must be **ignored** at discovery — no page, no source entry |

**Protocol** (Mode A; two runs in fresh sandboxes, grading the DELTA). Neither this file nor the
committed `wiki/` is pointed at the agent:

```bash
export CITADEL_RAW_DIR="$REPO/corpora/kontor/raw"
python "$REPO/corpora/kontor/make_office.py"          # regenerate fixtures (stdlib only)

# RUN 1 — images OFF: the embedded chart is not read
CITADEL_IMAGE_SUPPORT=0 uv run python -m citadel ingest
# grade §A present, §B ABSENT-and-honest (no 34.2 %), §C/§D as noted

# RUN 2 — images ON (default): the chart PNG is read (needs a vision-capable CLI, e.g. claude)
CITADEL_IMAGE_SUPPORT=1 uv run python -m citadel ingest   # fresh sandbox
# grade §A present, §B PRESENT+cited (34.2 %), §C/§D as noted
```

The **committed showcase** (`corpora/kontor/wiki/`) is built in **images** mode — the richest read.

## A · Load-bearing facts — present in BOTH modes (cited, with a slide/sheet/heading locator)

| id | fact | source |
| -- | ---- | ------ |
| `F1` | Q3 2026 revenue was **EUR 6.4 million**, up from **EUR 5.8 million** in Q2 | `q3-review.pptx` § Slide 2 |
| `F2` | standard customer support hours are **Mon–Fri, 09:00–17:00 CET** | `policy-handbook.docx` |
| `F3` | the leave/remote **table**: warehouse 25 d / 0 remote, office 28 d / 2, managers 30 d / 3 | `policy-handbook.docx` |
| `F4` | 2026 department budgets sum to **EUR 568,000** (Marketing 88 k, Engineering 150 k, Warehousing & Logistics 210 k, Sales 120 k) | `budget-2026.xlsx` § Sheet: Summary |
| `F5` | Aldervik Kontor was **founded in 2011** in Aldervik harbour; original business dried goods + textiles | `legacy-deck.ppt` |
| `F6` | 2019 year-end: **38 staff**, revenue **EUR 4.1 million** | `legacy-ledger.xls` |
| `F7` | the 2026 sustainability summary: warehouse energy use **fell 12 %** year over year | `report.docx` (NOT report.doc) |

## B · The MODE DELTA — the headline grade (chart-image-only fact)

| id | fact | images OFF | images ON |
| -- | ---- | ---------- | --------- |
| `M1` | **gross margin 34.2 %** — exists **only** inside the chart raster of `q3-review.pptx`, never in any slide's text | **ABSENT and honest** — the wiki must NOT state 34.2 % (it was never in the text the agent read); revenue etc. still present | **PRESENT and cited** to `q3-review.pptx` with a slide/figure locator |

Inventing `34.2 %` with images OFF is a **hard fail** (hallucination). Missing it with images ON is a
creation defect (the embedded chart was not read). The committed images showcase carries `M1`.

## C · Office-pipeline gates (hard pass/fail — the reason this corpus exists)

- `C1` **OOXML text** — the slide, speaker-notes, table, and both-sheet facts (`F1`–`F4`) are all present.
- `C2` **Legacy OLE salvage** — the `.doc`/`.ppt`/`.xls` facts (`F5`, `F6`, and the 2019 memo's warehouses) are present, recovered from the binary compound files.
- `C3` **Cite the ORIGINAL Office file (HARD):** every `[^sN]` behind an Office fact names the original `raw/*.pptx|docx|xlsx|doc|ppt|xls`, **never** an extracted temp file, and carries a locator (`§ Slide 2`, `§ Sheet: Summary`, or a heading anchor per `formats/office.md`).
- `C4` **Dedup-by-basename (HARD):** `report.doc` is dropped in favour of `report.docx`; the sustainability fact (`F7`) is cited to **`report.docx`**; there is **no** second page for `report.doc` and **no** `[^sN]` pointing at it. The drop is recorded in `wiki/.citadel_failures.json` with reason `duplicate`, so `citadel status` lists it under **skipped-duplicate** (not `failed`) and `sources/index.md` under **Could not ingest** as a `duplicate` — never as an ingested source.
- `C5` **Ignore-patterns (HARD):** `Thumbs.db`, `desktop.ini`, `~$policy-handbook.docx` produce **no** page, **no** `[^sN]`, and **no** `sources/` entry — skipped silently at discovery.

## D · Discriminative tier — judgment (separates strong vs weak models)

- `D1` **Contradiction surfaced, not silently resolved:** the deck's **142 staff** and the budget's **138 FTE** (same metric, 2026) are BOTH recorded and cited, with the discrepancy flagged (a `[!CONTRADICTION]`, an open point, or explicit "the deck says 142, the budget 138"). Silently picking one number and dropping the other = the serious failure.
- `D2` **Attribution ("X said Y" ≠ "Y is true"):** the **Lisbon** warehouse is recorded as **tentative / not approved by the board**, NOT as a settled fourth warehouse. Stating "Aldervik has a Lisbon warehouse" as fact = fail.
- `D3` **Entity-variance → one node:** `Aldervik Kontor`, `Aldervik Trading Kontor`, and `Aldervik` resolve to a **single** Organization page — not two or three. (Secondary: deck "Logistics" and budget "Warehousing & Logistics" are one department.)
- `D4` **Near-miss ≠ contradiction:** the 2019 memo's "**about 40**" and the 2019 ledger's "**38**" (same year) are an **approximation**, recorded consistently and NOT logged as a contradiction.
- `D5` **Temporal supersession:** **two** warehouses in 2019 (memo) → **three** in 2026 (deck), both dated; the current state is the 2026 one, the 2019 count kept as history, not overwritten silently.
- `D6` **Multi-source synthesis:** the total 2026 budget **EUR 568,000** (sum across the Summary sheet) is available; a staff answer reflects the cross-source 142/138 tension rather than one bare number.

## E · Structural gates (hard pass/fail — pure code, both modes)

- `citadel check` → "OK — no validation issues." (0 errors).
- `citadel lint` → exit 0; **Fabricated/missing sources: 0** (no temp file or junk file ever cited).
- **Locators:** every `[^sN]` into an Office source carries a slide/sheet/heading locator (`formats/office.md`); a bare Office citation is a miss (advisory in lint, graded here).

## Retrieval battery — find the knowledge like a user (Tier 2)

Run each `query` **verbatim** through `citadel search`. Answer-blind. `→§X` settles a miss. The
delta row (`rb-margin`) is graded **per mode**: the live value only with images ON, honest-absence
with images OFF.

| id | query | expect | find |
| -- | ----- | ------ | ---- |
| `rb-revenue` | how much did Aldervik make in the third quarter | **EUR 6.4 million** (up from 5.8 M) →§A·F1 | rank≤2, 1 read |
| `rb-margin` | what was Aldervik's gross margin | **images ON:** **34.2 %**, cited to `q3-review.pptx` with a slide locator. **images OFF:** no 34.2 % anywhere, and that absence is correct →§B·M1 | ON: rank≤2; OFF: honest-absent |
| `rb-headcount` | how many people work at Aldervik Kontor | the **142-vs-138 discrepancy surfaced** (both cited), not one bare number →§D·D1 | rank≤2, ≤2 reads |
| `rb-support` | when can I reach Aldervik customer support | **Mon–Fri, 09:00–17:00 CET** →§A·F2 | rank≤2, 1 read |
| `rb-budget` | what is Aldervik's total budget for 2026 | **EUR 568,000** (sum of the department rows) →§A·F4, §D·D6 | rank≤2, ≤2 reads |
| `rb-lisbon` | does Aldervik have a warehouse in Lisbon | **no** — it is unapproved / tentative, per the board (not a settled warehouse) →§D·D2 | rank≤2, 1 read |
| `rb-founded` | when was Aldervik Kontor founded | **2011**, in Aldervik harbour →§A·F5 | rank≤2, 1 read |
| `rb-energy` | how did Aldervik's warehouse energy use change | **fell 12 %** year over year, cited to `report.docx` →§A·F7, §C·C4 | rank≤2, 1 read |

## Scoring

**Hard gates** (must all hold, both modes unless noted): §E structural (check+lint 0, **fabricated
sources 0**, Office citations carry locators); §C `C3` cite-original, `C4` dedup skip, `C5` junk
ignored; every §A `F*` present-and-cited; **§B mode delta** — with images OFF the wiki must NOT
contain `34.2 %` (hallucination = hard fail), with images ON `M1` is present-and-cited; the committed
**images** showcase carries `M1`.

**Discriminative** (report caught / partial / missed, per §D): `D1` contradiction surfaced, `D2`
Lisbon attributed-tentative, `D3` entity merge to one node, `D4` near-miss not flagged, `D5`
supersession dated, `D6` synthesis available. These are where a weaker model degrades first —
structurally valid pages that silently pick 142-or-138, assert a Lisbon warehouse, split Aldervik
into two nodes, or flag 38-vs-40 as a contradiction.

**Findability** (Retrieval battery — report per row): each row's answer surfaces within its `find`
band; the delta row returns the live value **only** with images ON and a correct **honest absence**
with images OFF (settled by the `→§B` inspection, not by a no-match). **Hard floor:** a row
unfindable by search *and* `index` *and* `tags` (images ON) is a hard miss. Route each miss —
present-but-unranked → *retrieval* defect (search lane); a chart unread with images ON, an invented
value with images OFF, a duplicate/junk source materialized, a contradiction silently resolved, or a
temp file cited → *creation* defect (wiki-generation lane: `citadel/rules/formats/office.md`, the
genre briefs, the ingest prompts).
