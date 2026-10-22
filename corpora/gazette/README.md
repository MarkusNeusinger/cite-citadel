# gazette — PDF sources (text vs. images mode, publications, a scanned page)

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and generated for testing
> cite-citadel. The *Meridian Gazette*, *Cinder Peak Observatory*, the preprint and its authors are
> **fictional**. The science the feature article reports (tardigrade cryptobiosis, the 2007 FOTON-M3
> / TARDIS orbit experiment) is **real, public-domain fact** stated in original prose — nothing is
> copied from any source. The PDFs are **generated deterministically** by a committed stdlib script
> (`make_pdfs.py`, no third-party libraries), so they are regenerable. Safe to publish.

The only corpus made of **PDFs**, and the one that grades `CITADEL_PDF_MODE` — a PDF read as body
**text** vs. read with its **figures** looked at — plus the academic-**publications** genre and honest
handling of an **image-only** page. The modes differ by *instruction*: `text` reads body text — from
the PDF's text layer, or from the page image where a page has no usable text layer (a scan, or a
page whose text layer is garbled) — and ignores figures; `images` also looks at charts and scans.

## The sources

| file | what it is | the thing it tests |
| ---- | ---------- | ------------------ |
| `feature-article.pdf` | a 2-page popular-science feature (real tardigrade survival science), each page closed by the publisher's **letterhead footer** (company number, VAT ID, directors, bank and phone details) | multi-page **text-layer** extraction — these facts must appear in **both** modes — and **letterhead is not content**: the footer details must never become wiki facts |
| `figure-brief.pdf` | a one-page observatory brief whose key number (**best seeing 0.42 arcsec, Nov 14**) exists **only inside the embedded chart image**, never in the text | the **text-vs-images differentiator**: absent-and-honest in `text` mode, present-and-cited in `images` mode |
| `preprint.pdf` | a 2-page fictional academic preprint (abstract / methods / results / **references**) | the **publications** genre (its finding stays attributed to the authors) and **references-are-not-sources** (the `[1]`–`[5]` bibliography must never become fabricated raw sources or `[^sN]` to nonexistent files) |
| `field-survey.pdf` | an 11-page field report: **36 uniform station records** (`T-01`…`T-36`), each with an elevation, ring count, stem density and canopy closure | **window edges**: it is the only source long enough to chunk, and with `CITADEL_MODEL_CONTEXT_TOKENS=20000` its 4 line windows cut three records in half (`T-09`, `T-19`, `T-29`) — no station may be lost, truncated, duplicated or invented at a boundary |
| `scanned-notice.pdf` | a one-page **image-only** notice (rendered as pixels, no text layer) | honest handling: in `text` mode it is either left out or read from the page image exactly as printed — never with an invented date; in `images` mode the suspension notice is read visually |
| `calibration-sheet.pdf` | a 2-page instrument sheet: page 1 a **scanned** two-up sensor/offset table under an invisible, **column-serialized OCR text layer** (labels first, then a scrambled value run); page 2 clean notes | the **garbled-text-layer** path: citadel flags page 1 as an unreliable text layer, so the pairs must be read from the page image in **both** modes — a pair guessed from the scramble is a hallucination |
| `open-night.pdf` | a one-page public open-night invitation, stating the **local** start time | the kept twin of a same-basename pair |
| `open-night.ics` | the same event as a plain-text calendar export (start time in **UTC**) | **dedup-by-basename**: the PDF wins and the `.ics` is skipped as a duplicate, never cited |
| `press-release.md` | a clean markdown control | a non-PDF baseline in the same world |

Beyond the PDF-mode delta, the sources are wired together to test cross-source reasoning: one fact
(the retired 0.6 m telescope's service life) is **split across two PDFs** and needs both to answer,
the light-gathering-area gain is stated **inconsistently** ("about three times" in the brief vs
"roughly quadruples" in the press release — a contradiction to surface, not silently resolve), the
observatory's name appears once as **"Cinderpeak"** against "Cinder Peak" elsewhere (one node, not
two), and the press release ends with a **boilerplate paragraph carrying no facts** that must not
leak into the wiki.

## Regenerating the PDFs

```bash
python corpora/gazette/make_pdfs.py     # stdlib only; rewrites the seven PDFs into raw/ (open-night.ics is hand-written)
```

The committed showcase [`wiki/`](wiki/) is built in **images** mode (the richest read — it captures
the figure value and the scanned notice). The `verify-corpus` skill grades the **delta** by running
the corpus once in each mode (see `.claude/skills/verify-corpus/gazette/ground-truth.md`).

## What it exercises

The PDF magic-sniff dispatch, `formats/pdf.md`, `CITADEL_PDF_MODE` text/images branching, page
locators on PDF citations, references-are-not-sources provenance, the academic-paper genre, the
per-page unreliable-text-layer check (`pdftext.unreliable_pages`), letterhead kept out of the facts,
and dedup-by-basename (`CITADEL_DEDUP_BY_BASENAME`) of an `.ics` behind its PDF twin.

## Grading

The answer key is `.claude/skills/verify-corpus/gazette/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, or answer notes anywhere under `corpora/gazette/`.
