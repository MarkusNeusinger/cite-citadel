# gazette — PDF sources (text vs. images mode, publications, a scanned page)

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and generated for testing
> cite-citadel. The *Meridian Gazette*, *Cinder Peak Observatory*, the preprint and its authors are
> **fictional**. The science the feature article reports (tardigrade cryptobiosis, the 2007 FOTON-M3
> / TARDIS orbit experiment) is **real, public-domain fact** stated in original prose — nothing is
> copied from any source. The PDFs are **generated deterministically** by a committed stdlib script
> (`make_pdfs.py`, no third-party libraries), so they are regenerable. Safe to publish.

The only corpus made of **PDFs**, and the one that grades `CITADEL_PDF_MODE` — a PDF read as body
**text** vs. read with its **figures** looked at — plus the academic-**publications** genre and honest
handling of an **image-only** page. Because citadel hands the PDF to the agent's own file reader (it
does not pre-extract text), the modes differ by *instruction*: `text` reads the body and ignores
figures; `images` also looks at charts and scans.

## The sources

| file | what it is | the thing it tests |
| ---- | ---------- | ------------------ |
| `feature-article.pdf` | a 2-page popular-science feature (real tardigrade survival science) | multi-page **text-layer** extraction — these facts must appear in **both** modes |
| `figure-brief.pdf` | a one-page observatory brief whose key number (**best seeing 0.42 arcsec, Nov 14**) exists **only inside the embedded chart image**, never in the text | the **text-vs-images differentiator**: absent-and-honest in `text` mode, present-and-cited in `images` mode |
| `preprint.pdf` | a 2-page fictional academic preprint (abstract / methods / results / **references**) | the **publications** genre (its finding stays attributed to the authors) and **references-are-not-sources** (the `[1]`–`[5]` bibliography must never become fabricated raw sources or `[^sN]` to nonexistent files) |
| `scanned-notice.pdf` | a one-page **image-only** notice (rendered as pixels, no text layer) | honest degradation: in `text` mode it must **not** invent prose; in `images` mode the suspension notice is read visually |
| `press-release.md` | a clean markdown control | a non-PDF baseline in the same world |

## Regenerating the PDFs

```bash
python corpora/gazette/make_pdfs.py     # stdlib only; rewrites the four PDFs into raw/
```

The committed showcase [`wiki/`](wiki/) is built in **images** mode (the richest read — it captures
the figure value and the scanned notice). The `verify-corpus` skill grades the **delta** by running
the corpus once in each mode (see `.claude/skills/verify-corpus/gazette/ground-truth.md`).

## What it exercises

The PDF magic-sniff dispatch, `formats/pdf.md`, `CITADEL_PDF_MODE` text/images branching, page
locators on PDF citations, references-are-not-sources provenance, and the academic-paper genre.

## Grading

The answer key is `.claude/skills/verify-corpus/gazette/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, or answer notes anywhere under `corpora/gazette/`.
