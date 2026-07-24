# Ground truth — the gazette corpus

This is the **answer key** for the `gazette` corpus (`corpora/gazette/`). It lives under `.claude/`
(outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can never see it. The
verify-corpus skill reads it to grade the wiki the pipeline produced.

`gazette` is the only **PDF** corpus. It grades `CITADEL_PDF_MODE` — a PDF read as body **text** vs.
read with its **figures looked at** — plus the academic-**publications** genre, **references-are-not-
sources** provenance, honest handling of an **image-only** page, and **page locators** on PDF
citations. citadel hands the PDF to the agent's own file reader (it does not pre-extract text), so the
modes differ by instruction: `text` reads body text and ignores figures; `images` also reads charts
and scans.

> Everything is **fictional by design** (the Meridian Gazette, Cinder Peak Observatory, the preprint
> and its authors). The tardigrade science the feature reports is **real public-domain fact** in
> original prose. The wiki must record it faithfully as the PDFs state it.

## The 5 sources and the two-mode protocol

| file | genre | key content |
| ---- | ----- | ----------- |
| `feature-article.pdf` | popular-science feature, 2 pp, TEXT | tardigrade cryptobiosis/anhydrobiosis; ~97% water loss → "tun"; trehalose + TDPs vitrify; 2007 TARDIS / FOTON-M3 orbit survival |
| `figure-brief.pdf` | observatory brief, 1 p, text + a CHART IMAGE | body text: observatory **opened in 1998**, autumn nights sharpest, no seeing number; the new instrument gives "**about three times** the light-gathering area of the retired 0.6 m". **Figure only:** best seeing **0.42 arcsec (Nov 14)** — pixels only, no text layer |
| `preprint.pdf` | academic preprint, 2 pp, TEXT | Black Tarn up to **1,180 particles/L** (~6× the least affected); methods; **References [1]–[5]** (fictional) |
| `scanned-notice.pdf` | image-only, 1 p, NO text layer | public viewing **SUSPENDED for dome resurfacing 3–17 April 2026**, reopens 18 April 2026 |
| `press-release.md` | markdown control | first light of the new **1.2-metre telescope on 1 May 2026**; replaces the 0.6 m; "**roughly quadruples**" light-gathering area; ties the new instrument to the **same seeing survey** as the brief; a standard press-boilerplate paragraph carrying no facts |

**Cross-source structure planted for difficulty** (details in §E/§F below): the observatory is named
**"Cinder Peak Observatory"** everywhere except one press-release mention of **"Cinderpeak
Observatory"** — one node, not two. The **collecting-area gain conflicts**: the figure brief says
"about **three times**" while the press release says "**roughly quadruples**" (~4×) — a real
text-layer contradiction the wiki must surface, not silently pick one. And the **0.6 m telescope's
service life spans two PDFs**: the press release says it ran "since the observatory opened", the
figure brief supplies the opening year **1998** — combining them dates the retired instrument.

**Protocol** (Mode A; two runs in fresh sandboxes, grading the DELTA). Neither this file nor the
committed `wiki/` is pointed at the agent:

```bash
export CITADEL_RAW_DIR="$REPO/corpora/gazette/raw"; RAW="$CITADEL_RAW_DIR"
# make sure the PDFs exist (regenerable, stdlib only):
python "$REPO/corpora/gazette/make_pdfs.py"

# RUN 1 — text mode (default): figures are NOT interpreted
CITADEL_PDF_MODE=text  uv run python -m citadel ingest      # (or leave unset — text is the default)
# grade §A present, §Figure ABSENT-and-honest (no 0.42), §Scanned degraded honestly

# RUN 2 — images mode: figures + scans are read (needs the claude CLI, whose reader renders pages)
CITADEL_PDF_MODE=images uv run python -m citadel ingest     # fresh sandbox
# grade §A present, §Figure PRESENT+cited (0.42), §Scanned captured+cited
```

The **committed showcase** (`corpora/gazette/wiki/`) is built in **images** mode — the richest read.

## A · Load-bearing facts — present in BOTH modes (text-layer, cited with a page locator)

| id | fact | source |
| -- | ---- | ------ |
| `F1` | tardigrades ("water bears") survive drying via **cryptobiosis**, specifically **anhydrobiosis** | feature p.1 |
| `F2` | a drying tardigrade loses **~97% of its body water** and forms a barrel-shaped **"tun"** | feature p.1 |
| `F3` | it floods its cells with **trehalose** and **tardigrade-specific intrinsically disordered proteins (TDPs)** that **vitrify** (turn glassy) | feature p.1 |
| `F4` | in **2007**, the **TARDIS** experiment aboard the **FOTON-M3** satellite exposed tardigrades to the **vacuum of low Earth orbit and solar UV**; some survived and reproduced | feature p.2 |
| `F5` | the *preprint*'s finding: **Black Tarn** held up to **1,180 microplastic particles per litre**, ~6× the least affected site | preprint p.1/p.2 |
| `F6` | first light of the **1.2-metre telescope on 1 May 2026** (replacing the 0.6 m) | press-release |
| `F7` | Cinder Peak Observatory **opened in 1998** | figure-brief |

## B · The MODE DELTA — the headline grade (figure-only + image-only)

| id | fact | text mode | images mode |
| -- | ---- | --------- | ----------- |
| `M1` (figure) | best atmospheric seeing **0.42 arcsec (Nov 14)** — exists **only inside the chart raster** of `figure-brief.pdf`, never in the text layer | **ABSENT and honest** — the wiki must NOT state 0.42 (it isn't in the text the agent read); a page may exist for the brief with the text-level fact "autumn was sharpest" but no invented number | **PRESENT and cited** to `figure-brief.pdf` with a page/figure locator |
| `M2` (scan) | public viewing **SUSPENDED for dome resurfacing 3–17 April 2026, reopens 18 April** — `scanned-notice.pdf` has **no text layer** | **honest degradation** — either no page, a thin "a scanned notice that could not be read as text" note, or a `Could not ingest`/failures entry; the wiki must **NOT invent** the dates or notice prose | **PRESENT and cited** to `scanned-notice.pdf`, read visually |

Inventing `0.42` or the notice text in **text** mode is a **hard fail** (hallucination). Missing them
in **images** mode is a creation defect (the figure/scan was not read).

## C · Publications genre + references-are-not-sources (the preprint)

- `P1` — the preprint's finding (`F5`) is recorded **attributed to the preprint** ("a preprint by
  Halvorsen, Okonkwo, and Feretti reports…" / cited to `preprint.pdf`), **not** stated as settled,
  peer-reviewed fact. It is a "preprint, not peer reviewed" (the PDF says so).
- `P2` — **references-are-not-sources (HARD):** the bibliography entries `[1]`–`[5]` (Nowak 2019,
  Reyes & Duman 2020, Okafor 2018, Vance 2021, Feretti & Halvorsen 2022) must **NOT** materialize as
  `raw/` sources, as `[^sN]` citations to nonexistent files, or as fabricated wiki pages presented as
  if read. They are text inside `preprint.pdf`, cited (if at all) to `preprint.pdf` itself. A `[^sN]`
  pointing at a bibliographic entry as though it were an ingested file = lint fabricated-source FAIL.

## E · Cross-source structure — merge, contradiction, entity variance (text-layer, both modes)

These grade whether the wiki builds a connected picture rather than isolated per-PDF pages. All are
text-layer (present in both modes).

| id | what | expected | fail |
| -- | ---- | -------- | ---- |
| `ms-oldscope` | the retired **0.6 m** telescope's service span needs **two** sources | a page dates the old instrument to the observatory's **1998** opening (press release: "since the observatory opened" + figure brief: opened 1998), both `[^sN]`-cited | only one half present, or the 1998↔0.6 m link never made |
| `xc-area` | **contradiction:** figure brief "**about three times**" vs press release "**roughly quadruples**" (~4×) the light-gathering area, same upgrade | both values kept and cited, the discrepancy surfaced (a `> [!CONTRADICTION]` callout, or both stated side-by-side with the conflict noted) | the wiki asserts one figure (3× **or** 4×) alone as settled fact, silently dropping the other |
| `xe-name` | entity variance: "**Cinderpeak Observatory**" (press release, once) vs "**Cinder Peak Observatory**" (everywhere else) | **one** observatory node; the variant spelling resolves to it | a second, separate observatory page/org for "Cinderpeak" |
| `nz-boiler` | the press release's **media-boilerplate** paragraph ("issued for immediate publication… reproduction… no observatory facts") | its non-facts do **not** become wiki facts; at most the Meridian-Gazette-as-publisher relation is kept | a page asserting "reproduction requires no permission" or "a high-resolution image is available" as an observatory fact |

## D · Structural gates (hard pass/fail — pure code)

- `citadel check` → "OK — no validation issues." (0 errors), both modes.
- `citadel lint` → exit 0; **Fabricated/missing sources: 0** (settles `P2`).
- **PDF locators** depend on how the PDF was read (`citadel/rules/formats/pdf.md`):
  - With the **pypdf text-layer pre-pass** active (`CITADEL_PDF_TEXT`, default auto — pypdf is a
    dev dep here), a text-layer PDF is read through its extracted text, so its text-fact citations
    carry **`lines A-B` locators into that extraction** — offline-verifiable (`lint` reports **0
    locator issues** against the cached extraction). A **figure-only / scanned** fact (no text
    layer — e.g. the `0.42` chart value, the suspension notice) still carries a **page locator**
    (`p. N`), agent-verified.
  - **Without** the pre-pass (pypdf absent, `CITADEL_PDF_TEXT=0`, or a scanned PDF), the PDF is
    read agent-natively and **every** `[^sN]` carries a **page locator** (`p. N` / `page N` per
    `schema.md` § Locators) — a bare locator on such a citation is wrong.
  Either way, a `lines A-B` locator that does not resolve against the cached extraction is a
  locator issue; `p. N` locators stay agent-verified. (Advisory in lint, but graded here.)

## Retrieval battery — find the knowledge like a user (Tier 2)

Run each `query` **verbatim** through `citadel search`. Answer-blind. `→§X` settles a miss. The
mode-delta rows (`rb-seeing`, `rb-notice`) are graded **per mode**: the live value only in images
mode, honest-absence in text mode.

| id | query | expect | find |
| -- | ----- | ------ | ---- |
| `rb-tardigrade` | how do tardigrades survive being dried out or exposed to space | cryptobiosis/anhydrobiosis, trehalose + TDPs vitrifying the cells, and the 2007 orbit survival →§A·F1/F3/F4 | rank 1, 1 read |
| `rb-tun` | how much water does a tardigrade lose when it dries up | **~97%**, forming a "tun" →§A·F2 | rank≤2, 1 read |
| `rb-seeing` | what was the best atmospheric seeing recorded at Cinder Peak in 2025 | **images mode:** **0.42 arcsec (Nov 14)**, cited to `figure-brief.pdf` with a page locator. **text mode:** no 0.42 anywhere (only "autumn was sharpest"), and that absence is correct →§B·M1 | images: rank≤2; text: honest-absent |
| `rb-microplastic` | how much microplastic was found in the alpine tarns | up to **1,180 particles per litre** in Black Tarn, **attributed to the Halvorsen et al. preprint** (not stated as settled fact) →§A·F5, §C·P1 | rank≤2, 1 read |
| `rb-notice` | can I visit Cinder Peak for a public viewing night right now | **images mode:** viewing nights **SUSPENDED for dome resurfacing 3–17 April 2026, reopening 18 April**, cited to `scanned-notice.pdf`. **text mode:** must NOT assert these dates (the scan had no text layer) →§B·M2 | images: rank≤2; text: honest-absent |
| `rb-firstlight` | when did Cinder Peak's new telescope see first light | **1 May 2026**, the new 1.2-metre telescope →§A·F6 | rank 1, 1 read |
| `rb-oldscope` | how long was the observatory's original 0.6-metre telescope in service | since the observatory **opened in 1998** (0.6 m ran from opening until replaced in 2026); needs the press release *and* the figure brief bridged, both cited →§E·ms-oldscope | rank≤3, ≤2 reads |
| `rb-area` | how much more light does the new telescope collect than the old one | the two sources **disagree** — the figure brief says "about three times", the press release "roughly quadruples"; the surfaced page must show both/flag the conflict, not a single settled multiplier →§E·xc-area | rank≤3, ≤2 reads |

## Scoring

**Hard gates** (must all hold, both modes unless noted): §D structural (check+lint 0, **fabricated
sources 0**, PDF citations carry page locators); §C·P2 references never materialized as sources; §C·P1
the preprint finding attributed, not settled; every §A `F*` present-and-cited; **§B mode delta** — in
**text** mode the wiki must NOT contain the figure-only `0.42` or the scanned-notice dates
(hallucination = hard fail), and in **images** mode both `M1` and `M2` are present-and-cited; the
committed **images** showcase carries `M1` + `M2`.

**Soft / probabilistic** (report caught / partial / missed): the figure/scan captured with a precise
page locator; a tidy cross-linked graph (Cinder Peak Observatory ↔ the seeing brief ↔ the scanned
notice ↔ the first-light press release; the Meridian Gazette as publisher); genre judgment on the
preprint; the feature's tardigrade facts kept as real science (not hedged as fiction); the §E
cross-source structure — the `ms-oldscope` two-PDF bridge, the `xc-area` 3×-vs-4× contradiction
surfaced, the `xe-name` Cinderpeak/Cinder Peak merge to one node, and the `nz-boiler`
press-boilerplate kept out of the facts. `xe-name` (two observatory nodes) and `nz-boiler`
(boilerplate asserted as fact) are creation defects when they occur, but not structural hard fails.

**Findability** (Retrieval battery — report per row): each row's answer surfaces within its `find`
band in ≤2 reads; the mode-delta rows return the live value **only** in images mode and a correct
**honest absence** in text mode (settled by the `→§B` inspection, not by a no-match). **Hard floor:** a
row unfindable by search *and* `index` *and* `tags` (images mode) is a hard miss. Route each miss —
present-but-unranked → *retrieval* defect (search lane); a figure/scan unread in images mode, an
invented value in text mode, or a reference turned into a source → *creation* defect (wiki-generation
lane: `citadel/rules/formats/pdf.md`, the genre briefs, the ingest prompts).
