# kontor — Office documents (OOXML + legacy OLE, an embedded-image delta, dedup & ignore)

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and generated for testing
> cite-citadel. *Aldervik Kontor*, its people, warehouses, budgets, and every figure are
> **fictional**. The Office files are **generated deterministically** by a committed stdlib script
> (`make_office.py`, no third-party libraries — no python-pptx/docx/openpyxl/PIL), so they are
> regenerable and nothing is copied from any real document. Safe to publish (MIT).

The only corpus made of **binary Office documents**, and the sole test of citadel's Office pipeline:
zero-dependency text extraction from **OOXML** (`.pptx`/`.docx`/`.xlsx`) and **legacy OLE**
(`.doc`/`.ppt`/`.xls`, Office 97–2003 compound files), the **embedded-image delta**
(`CITADEL_IMAGE_SUPPORT` — a chart whose key number lives only in pixels), **dedup-by-basename**, and
**ignore-patterns**. On top of the plumbing it plants the same judgment traps the other hardened
corpora carry, so it also separates a strong model from a weak one.

The fictional world: **Aldervik Kontor** ("Kontor" = a Hanseatic trading house), a mid-size
import/trading firm — a natural home for quarterly decks, a staff handbook, a budget workbook, and a
drawer of old 97–2003 files.

## The sources

| file | what it is | the thing it tests |
| ---- | ---------- | ------------------ |
| `q3-review.pptx` | a 4-slide review deck with speaker notes and an embedded chart image | OOXML slide + **speaker-notes** extraction, and the **image delta**: the chart's `GROSS MARGIN 34.2%` is pixels-only — absent-and-honest with images off, present-and-cited with images on |
| `policy-handbook.docx` | a staff handbook with a **table** | OOXML paragraph + **table-cell** extraction |
| `budget-2026.xlsx` | a two-sheet budget workbook | OOXML **multi-sheet** cell extraction (shared strings, tab order) + a cross-sheet total |
| `legacy-memo.doc` | a 2019 memo (OLE2 compound file) | **legacy OLE salvage** (UTF-16LE text runs from a CFBF container) |
| `legacy-deck.ppt` | a 2018 kickoff deck (OLE2) | legacy OLE salvage |
| `legacy-ledger.xls` | a 2019 year-end ledger (OLE2) | legacy OLE salvage |
| `report.docx` + `report.doc` | the same summary in two formats | **dedup-by-basename**: the `.docx` is ingested, the `.doc` skipped-duplicate |
| `Thumbs.db`, `desktop.ini`, `~$policy-handbook.docx` | OS / Office junk | **ignore-patterns**: skipped at discovery, never ingested |

Beyond the plumbing, the facts are laid so a strong model pulls ahead: a **142-vs-138** headcount
**contradiction** across the deck and the budget (surface it, don't silently pick one); a **Lisbon**
warehouse that the speaker notes mark **unapproved** (attribution, not a settled fact); three
spellings of the company that must merge to **one** node; a 2019 "**about 40**" vs "**38**"
**near-miss** that is an approximation, not a contradiction; and a **two→three** warehouse count that
**supersedes** by date.

## Regenerating the files

```bash
python corpora/kontor/make_office.py            # stdlib only; rewrites every fixture into raw/
python corpora/kontor/make_office.py --check     # regenerate + assert each file round-trips
```

The committed showcase [`wiki/`](wiki/) is built in **images** mode (`CITADEL_IMAGE_SUPPORT=1`, the
richest read — it captures the chart's gross-margin figure). The `verify-corpus` / `bench-model`
skills grade the **delta** by running the corpus once with images off and once on (see
`.claude/skills/verify-corpus/kontor/ground-truth.md`).

## What it exercises

The Office magic-sniff dispatch (ZIP vs OLE2), `citadel/extract.py` (OOXML) and
`citadel/extract_ole.py` (CFBF salvage), `extract_media` + `CITADEL_IMAGE_SUPPORT`, the
`formats/office.md` brief and its slide/sheet/heading locators, `CITADEL_DEDUP_BY_BASENAME`, and
`CITADEL_IGNORE_PATTERNS`.

## Grading

The answer key is `.claude/skills/verify-corpus/kontor/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, or answer notes anywhere under `corpora/kontor/`.
