# Ground truth — the gazette corpus

This is the **answer key** for the `gazette` corpus (`corpora/gazette/`). It lives under `.claude/`
(outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can never see it. The
verify-corpus skill reads it to grade the wiki the pipeline produced.

`gazette` is the only **PDF** corpus. It grades `CITADEL_PDF_MODE` — a PDF read as body **text** vs.
read with its **figures looked at** — plus the academic-**publications** genre, **references-are-not-
sources** provenance, honest handling of an **image-only** page, **page locators** on PDF
citations, a **garbled text layer** read from the page image, the issuer's **letterhead** kept out of
the facts, and **dedup-by-basename** of a calendar export behind its PDF twin. The modes differ by
instruction: `text` reads body text — from the pypdf text layer, or from the page image where a page
has no usable text layer (a scan, or a page ingest names as an unreliable text layer) — and ignores
figures; `images` also reads charts and scans.

> Everything is **fictional by design** (the Meridian Gazette, Cinder Peak Observatory, the preprint
> and its authors). The tardigrade science the feature reports is **real public-domain fact** in
> original prose. The wiki must record it faithfully as the PDFs state it.

## The 9 sources and the run protocol

Nine files in `raw/` (7 PDFs + 1 markdown + 1 `.ics`); **8 are ingested** — `open-night.ics` is
skipped by dedup-by-basename as a duplicate of `open-night.pdf` (§H).

| file | genre | key content |
| ---- | ----- | ----------- |
| `feature-article.pdf` | popular-science feature, 2 pp, TEXT | tardigrade cryptobiosis/anhydrobiosis; ~97% water loss → "tun"; trehalose + TDPs vitrify; 2007 TARDIS / FOTON-M3 orbit survival. **Both pages close with the issuer's letterhead footer** (company no., VAT ID, two directors, IBAN, phone, registered office) — page furniture about the publisher, not facts (§E `nz-letterhead`) |
| `figure-brief.pdf` | observatory brief, 1 p, text + a CHART IMAGE | body text: observatory **opened in 1998**, autumn nights sharpest, no seeing number; the new instrument gives "**about three times** the light-gathering area of the retired 0.6 m". **Figure only:** best seeing **0.42 arcsec (Nov 14)** — pixels only, no text layer |
| `preprint.pdf` | academic preprint, 2 pp, TEXT | Black Tarn up to **1,180 particles/L** (~6× the least affected); methods; **References [1]–[5]** (fictional) |
| `field-survey.pdf` | field report, 11 pp, TEXT, **long** | the Cinder Peak treeline transect: **36 stations T-01…T-36**, each with a place name, elevation, ring count (stand age), stem density and canopy closure. Deliberately uniform and individually numbered — its only job is to be long enough to CHUNK, so a station lost at a window edge is visible as a missing station |
| `scanned-notice.pdf` | image-only, 1 p, NO text layer | public viewing **SUSPENDED for dome resurfacing 3–17 April 2026**, reopens 18 April 2026 |
| `calibration-sheet.pdf` | instrument sheet, 2 pp. p. 1: a SCANNED two-up `SENSOR \| OFFSET` table under an invisible, **column-serialized OCR text layer**; p. 2: clean text notes | the six sensor/offset pairs are pairable **only in the page image** — the text layer lists all six labels, then a scrambled value run with `0/O` and `1/l` slips. `pdftext.unreliable_pages` flags **p. 1 only** (pinned by `tests/test_corpora_fixtures.py`), so ingest keeps the text pass and names p. 1 as a page to read visually (§G) |
| `open-night.pdf` | event invitation, 1 p, TEXT | public open night **Saturday 13 June 2026, doors 21:30 local time (BST)**, ends 00:30, visitor terrace, free, booking required via the outreach desk |
| `open-night.ics` | calendar export (plain text), same basename | the SAME event with `DTSTART:20260613T203000Z` (UTC) — every fact it carries is also in the PDF; **skipped as a duplicate** of `open-night.pdf` (§H) |
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
# grade §A present, §Figure ABSENT-and-honest (no 0.42), §Scanned honest-absent OR exactly the scan's
# dates cited p. 1 (never a different date), §G pairs read from the page image, §H dedup
uv run python -m citadel status     # §H: open-night.ics under skipped-duplicate

# RUN 2 — images mode: figures + scans are read (needs a vision-capable CLI: claude/copilot/agy)
CITADEL_PDF_MODE=images uv run python -m citadel ingest     # fresh sandbox
# grade §A present, §Figure PRESENT+cited (0.42), §Scanned captured+cited, §G, §H

# RUN 3 — chunked: state a small model context so the long report splits into line windows
CITADEL_MODEL_CONTEXT_TOKENS=20000 uv run python -m citadel ingest   # fresh sandbox
# 20000 tokens -> an 8000-char window -> field-survey.pdf runs as 4 passes; grade §F
```

RUN 3 is the only run in which any source chunks; RUNS 1 and 2 fold `field-survey.pdf` in as a
single pass, so a §F failure there would mean something other than the window edges.

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
| `M2` (scan) | public viewing **SUSPENDED for dome resurfacing 3–17 April 2026, reopens 18 April** — `scanned-notice.pdf` has **no text layer** | **honest-absent, OR present exactly as the scan states it** — either no page / a thin "a scanned notice" note / a `Could not ingest` entry, **or** the suspension (3–17 April 2026, reopens 18 April) matching the scan exactly and cited `p. 1` (text mode reads a scan's body text from the page image, `formats/pdf.md` § B). **Any date that differs from the scan is the hard fail** | **PRESENT and cited** to `scanned-notice.pdf`, read visually |

Inventing `0.42` in **text** mode, or stating any notice date that differs from the scan in either
mode, is a **hard fail** (hallucination). Missing `M1`/`M2` in **images** mode is a creation defect
(the figure/scan was not read). `M1` stays the text/images discriminator: a figure is never body
text.

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
| `nz-letterhead` | the **letterhead footer** on both pages of `feature-article.pdf` (`core.md` § Letterhead & page furniture) — the article is about tardigrades, not about its publisher | a grep of the sandbox wiki finds **none** of the planted strings: `08814327`, `GB 291 4471 06`, `Helena Marsh-Ostrander`, `Tobias Wrenfield`, `GB29 MRDN 6016 1331 9268 19`, `+44 20 7946 0318` (nor `14 Lantern Row`). The Meridian Gazette may still appear as the feature's **publisher** | any planted string on any page — e.g. a Meridian Gazette org page listing its directors, company number, VAT ID, bank account or phone |

## F · Window edges — the chunked grade (RUN 3 only)

`field-survey.pdf` is the corpus's only chunkable source. Under `CITADEL_MODEL_CONTEXT_TOKENS=20000`
the budget resolves to an **8000-char window**, and its ~30 600-char extraction splits into **4
windows** (at the time of writing, lines `1-101`, `102-200`, `201-303`, `304-387` — informational
only: the exact offsets move if the extraction ever changes). Those boundaries fall **inside** three
station records, which is the entire point of this section. The three stations below are **pinned by
the offline suite** (`tests/test_corpora_fixtures.py`), so if a pypdf upgrade or a regenerated
fixture shifts the boundaries, `pytest` fails and this table is corrected — it can never quietly
send the grader hunting a defect that cannot exist:

| station | place | elevation | ring count | canopy | stem density |
| ------- | ----- | --------- | ---------- | ------ | ------------ |
| **T-09** | Hawthorn Rise | 1333 m | 123 | 67 % | 67 |
| **T-19** | Chalk Terrace | 1503 m | 73 | 57 % | 107 |
| **T-29** | Silver Bight | 1673 m | 143 | 47 % | 57 |

A pass that reads only its own window sees each of these three records cut in half. `formats/pdf.md`
says the cut unit may be read past the edge to be seen whole, and that only the pass it **begins** in
folds it in — so the correct outcome is one complete record, once.

| id | what | expected | fail |
| -- | ---- | -------- | ---- |
| `wf-all36` | **no station is lost to a boundary** | all **36** stations `T-01`…`T-36` are recoverable from the wiki, each `[^sN]`-cited to `field-survey.pdf` | any station missing entirely — the headline failure this corpus exists to catch |
| `wf-cut3` | the three **straddling** records survive intact | `T-09`, `T-19` and `T-29` each carry their full figure set (elevation, ring count, canopy, stem density) as tabled above | a straddling station present but truncated (e.g. elevation kept, canopy lost), or its numbers attached to the wrong station |
| `wf-nodup` | ownership does not move with the read | each straddling station appears **once** — not once per pass that could see it | `T-09` (or `T-19`/`T-29`) duplicated across two pages, or the same fact restated twice on one page |
| `wf-noinvent` | the edge permission is not a licence to guess | every figure matches the table above exactly | a plausible-but-wrong number at a straddling station — worse than a missing one |
| `wf-locator` | locators stay the full extraction's own line numbers | the straddling records' `lines A-B` ranges resolve against the cached extraction (`lint`: 0 locator issues), including where a range crosses a window edge | a rebased/re-counted range, or a range clipped to the window |

A **Registry**-shaped page for the transect is the natural home for 36 uniform records (see
`werkhof`'s granularity rules); the grade is on the records surviving, not on the page shape.

## G · Garbled text layer — read the page, not the scramble (BOTH modes)

`calibration-sheet.pdf` p. 1 carries a text layer that **cannot be paired**: the six labels come
first, then a detached value run in the wrong order (`O.2l`, `0.12`, `0.47`, `0.35`, `0.16`, `0.O8`).
`pdftext.unreliable_pages` flags p. 1 (and only p. 1; p. 2's clean notes keep the source on the text
path), so the run instruction names p. 1 as an unreliable text layer and `formats/pdf.md` § A tells
the agent to read that page from its image — in **both** modes. The page image pairs them as:

| sensor | offset |
| ------ | ------ |
| Dome Humidity Probe | **0.12** |
| Mirror Cell Thermistor | **0.35** |
| Primary Focus Encoder | **0.08** |
| Seeing Monitor Camera | **0.21** |
| Wind Mast Anemometer | **0.47** |
| Sky Quality Meter | **0.16** |

A naive in-order zip of the text layer pairs **every** sensor wrongly (Dome Humidity Probe 0.21,
Mirror Cell Thermistor 0.12, Primary Focus Encoder 0.47, Seeing Monitor Camera 0.35, Wind Mast
Anemometer 0.16, Sky Quality Meter 0.08) — so a correct pair proves the page was looked at.

| id | what | expected | fail |
| -- | ---- | -------- | ---- |
| `vc-header` | the legible text-layer facts | issuer **Cinder Peak Observatory** (instrument desk), **issued 22 April 2026**, checked by **Ines Varga**; from p. 2: offsets are **subtracted from the raw reading**, reference check **21 April 2026**, next calibration **due October 2026** — cited **`lines A-B`** into the extraction (a `p. 1` locator on the p. 1 header facts is also a pass — that page is named unreliable) | missing, or cited with a locator that does not resolve |
| `vc-pairs` | the six sensor/offset pairs | all six present and **correctly paired** as tabled above, cited **`p. 1`** (read from the page image), in **both** modes | a pair missing (a creation defect — the page was not looked at; recording nothing from the garbled part is the *honest* fallback, not a hallucination) |
| `vc-nomispair` | **HARD:** never guess from the scramble | no offset attached to the wrong sensor, and no offset cited to the garbled value lines (`lines A-B` inside p. 1's value run) | any mis-paired offset (especially a naive-zip pair above), or a slip copied as data (`O.2l`, `0.O8`) |
| `vc-report` | the run report names the page | the ingest report's `PDF pages read visually (unreliable text layer):` section lists `raw/calibration-sheet.pdf (p. 1)` | absent (the detector or its hand-off regressed) |

## H · Dedup-by-basename — a calendar export behind its PDF twin

`open-night.pdf` and `open-night.ics` share a stem in one folder. With `CITADEL_DEDUP_BY_BASENAME` on
(the default), the PDF wins and the `.ics` is never sent to a session (modeled on kontor's C4).

| id | what | expected | fail |
| -- | ---- | -------- | ---- |
| `dd-opennight` | the `.ics` is a recorded duplicate | the ingest report lists `raw/open-night.ics` as a duplicate of `raw/open-night.pdf`; `citadel status` shows it under **skipped-duplicate**; no page and no `[^sN]` points at `open-night.ics` | the `.ics` ingested as its own source, or cited anywhere |
| `dd-localtime` | the event is cited to the PDF, in **local** time | the open night on **Saturday 13 June 2026**, doors **21:30** local time (BST), ending 00:30, on the visitor terrace, free with booking — cited to `open-night.pdf` | `20:30` (the `.ics`'s UTC hour read as local), or the event missing |

## D · Structural gates (hard pass/fail — pure code)

- `citadel check` → "OK — no validation issues." (0 errors), both modes.
- `citadel lint` → exit 0; **Fabricated/missing sources: 0** (settles `P2`).
- **PDF locators** depend on how the PDF was read (`citadel/rules/formats/pdf.md`):
  - With the **pypdf text-layer pre-pass** active (`CITADEL_PDF_TEXT`, default auto — pypdf is a
    bundled runtime dep, so this is on by default), a text-layer PDF is read through its extracted text, so its text-fact citations
    carry **`lines A-B` locators into that extraction** — offline-verifiable (`lint` reports **0
    locator issues** against the cached extraction). A **figure-only / scanned** fact (no text
    layer — e.g. the `0.42` chart value, the suspension notice) still carries a **page locator**
    (`p. N`), agent-verified — and so does a fact read from a page the run instruction names as an
    **unreliable text layer** (the §G calibration pairs: `p. 1`), while that PDF's legible facts
    keep `lines A-B`. Mixed locators in one PDF are correct.
  - **Without** the pre-pass (pypdf absent, `CITADEL_PDF_TEXT=0`, or a scanned PDF), the PDF is
    read agent-natively and **every** `[^sN]` carries a **page locator** (`p. N` / `page N` per
    `schema.md` § Locators) — a bare locator on such a citation is wrong.
  Either way, a `lines A-B` locator that does not resolve against the cached extraction is a
  locator issue; `p. N` locators stay agent-verified. (Advisory in lint, but graded here.)

## Retrieval battery — find the knowledge like a user (Tier 2)

Run each `query` **verbatim** through `citadel search`. Answer-blind. `→§X` settles a miss. The
mode-delta rows are graded **per mode**: `rb-seeing` returns the live value only in images mode
(honest-absence in text mode); `rb-notice` returns it in images mode and, in text mode, either an
honest absence or the scan's exact dates.

| id | query | expect | find |
| -- | ----- | ------ | ---- |
| `rb-tardigrade` | how do tardigrades survive being dried out or exposed to space | cryptobiosis/anhydrobiosis, trehalose + TDPs vitrifying the cells, and the 2007 orbit survival →§A·F1/F3/F4 | rank 1, 1 read |
| `rb-tun` | how much water does a tardigrade lose when it dries up | **~97%**, forming a "tun" →§A·F2 | rank≤2, 1 read |
| `rb-seeing` | what was the best atmospheric seeing recorded at Cinder Peak in 2025 | **images mode:** **0.42 arcsec (Nov 14)**, cited to `figure-brief.pdf` with a page locator. **text mode:** no 0.42 anywhere (only "autumn was sharpest"), and that absence is correct →§B·M1 | images: rank≤2; text: honest-absent |
| `rb-microplastic` | how much microplastic was found in the alpine tarns | up to **1,180 particles per litre** in Black Tarn, **attributed to the Halvorsen et al. preprint** (not stated as settled fact) →§A·F5, §C·P1 | rank≤2, 1 read |
| `rb-notice` | can I visit Cinder Peak for a public viewing night right now | **images mode:** viewing nights **SUSPENDED for dome resurfacing 3–17 April 2026, reopening 18 April**, cited to `scanned-notice.pdf`. **text mode:** honest-absent, **or** exactly those dates cited `p. 1` to `scanned-notice.pdf` — any differing date is the hard fail →§B·M2 | images: rank≤2; text: honest-absent or exact |
| `rb-firstlight` | when did Cinder Peak's new telescope see first light | **1 May 2026**, the new 1.2-metre telescope →§A·F6 | rank 1, 1 read |
| `rb-oldscope` | how long was the observatory's original 0.6-metre telescope in service | since the observatory **opened in 1998** (0.6 m ran from opening until replaced in 2026); needs the press release *and* the figure brief bridged, both cited →§E·ms-oldscope | rank≤3, ≤2 reads |
| `rb-calibration` | what calibration offset does the wind mast anemometer have | **0.47**, cited `p. 1` to `calibration-sheet.pdf` (never `0.16`, the naive-zip pair) →§G·vc-pairs | rank≤2, 1 read |
| `rb-opennight` | what time does the public open night at Cinder Peak start | **Saturday 13 June 2026, 21:30 local time**, cited to `open-night.pdf` (never `20:30`) →§H·dd-localtime | rank≤2, 1 read |
| `rb-area` | how much more light does the new telescope collect than the old one | the two sources **disagree** — the figure brief says "about three times", the press release "roughly quadruples"; the surfaced page must show both/flag the conflict, not a single settled multiplier →§E·xc-area | rank≤3, ≤2 reads |

## Scoring

**Hard gates** (must all hold, both modes unless noted): §D structural (check+lint 0, **fabricated
sources 0**, PDF citations carry page locators); §C·P2 references never materialized as sources; §C·P1
the preprint finding attributed, not settled; every §A `F*` present-and-cited; **§B mode delta** — in
**text** mode the wiki must NOT contain the figure-only `0.42` (hallucination = hard fail), and the
scanned-notice dates are either absent or exactly the scan's (3–17 April 2026, reopens 18 April,
cited `p. 1` — any differing date is a hard fail); in **images** mode both `M1` and `M2` are
present-and-cited; **§G·vc-nomispair** — no mis-paired calibration offset, no offset cited to the
garbled lines (both modes); **§H·dd-opennight** — `open-night.ics` skipped as a duplicate and never
cited; the committed **images** showcase carries `M1` + `M2`.

**Soft / probabilistic** (report caught / partial / missed): the figure/scan captured with a precise
page locator; a tidy cross-linked graph (Cinder Peak Observatory ↔ the seeing brief ↔ the scanned
notice ↔ the first-light press release; the Meridian Gazette as publisher); genre judgment on the
preprint; the feature's tardigrade facts kept as real science (not hedged as fiction); the §E
cross-source structure — the `ms-oldscope` two-PDF bridge, the `xc-area` 3×-vs-4× contradiction
surfaced, the `xe-name` Cinderpeak/Cinder Peak merge to one node, the `nz-boiler`
press-boilerplate and the `nz-letterhead` footer kept out of the facts; the §G `vc-pairs` all six
present (in both modes) and `vc-header` cited `lines A-B`; the §H `dd-localtime` local start time.
`xe-name` (two observatory nodes), `nz-boiler` (boilerplate asserted as fact) and `nz-letterhead`
(a planted footer string in the wiki) are creation defects when they occur, but not structural hard
fails.

**Findability** (Retrieval battery — report per row): each row's answer surfaces within its `find`
band in ≤2 reads; the mode-delta rows return the live value **only** in images mode and a correct
**honest absence** in text mode (settled by the `→§B` inspection, not by a no-match). **Hard floor:** a
row unfindable by search *and* `index` *and* `tags` (images mode) is a hard miss. Route each miss —
present-but-unranked → *retrieval* defect (search lane); a figure/scan unread in images mode, an
invented value in text mode, a calibration pair guessed from the scrambled layer, a letterhead
string leaked, or a reference turned into a source → *creation* defect (wiki-generation
lane: `citadel/rules/formats/pdf.md`, the genre briefs, the ingest prompts).
