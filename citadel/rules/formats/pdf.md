# pdf — extracted text layer when prepared; figures per mode; verifiable locators

Applies when the source of record is a **PDF**. There are two ways a PDF session is set up; your
run instruction tells you which one you are in.

## A) A "Prepared file" is named (the extracted text layer)

The system extracted the PDF's embedded text layer for you (pypdf pre-pass). The prepared file is
the **verification copy** of the source: read IT for the body text — do not re-read the PDF for
text — and cite the **original `.pdf` file** as the source of record.

- **Locators are `lines A-B` into the prepared file.** Its line numbers are exactly what the
  offline checks (`citadel check`/`lint`, `wiki_raw`, the viewer) verify against — never rebase
  or re-count them. Every page opens with a `[p. N]` marker line, so the page a fact came from is
  visible in the cited lines themselves; do not cite the marker line alone.
- A **large** extraction may be split across passes: the prepared file then holds the WHOLE
  extraction and your run instruction bounds THIS pass to a line window. Read only that window
  (ranged/offset reads) — the file's own line numbers ARE the locator line numbers.
- An empty stretch under a `[p. N]` marker means that page has no text layer (a figure-only or
  scanned page). In **text** mode, note nothing for it; in **images** mode, read that page in the
  original PDF (below).

Your run instruction also names the active **PDF mode**:

- **text** — ingest the extracted body text only. Do not spend the session interpreting figures.
- **images** — additionally **LOOK AT** the original PDF's figures, diagrams, and charts (open
  the `.pdf` itself with your file reader) and capture what they show, cited like any fact. A
  fact that lives **only in pixels** (a chart value, an image-only page) cannot carry a `lines`
  locator into the text layer — cite it with a **page locator** (`p. 12`) instead.

## B) No prepared file (agent-native reading)

No text layer was extracted (pypdf not installed, a scanned/image-only PDF, or the pre-pass is
off). Open and read the PDF directly with your file reader.

- Such a PDF is read **whole, unchunked by design** — the system never splits the PDF file into
  segments the way it does large text sources, because page numbers, figures, and layout carry
  meaning a slicer would destroy. That puts a practical ceiling on PDF size: a very large PDF
  (hundreds of dense pages) may not fit one session — such a run fails/times out and lands under
  *Could not ingest*; the remedy is to split the PDF file itself in raw/.
- The PDF-mode bullet applies as in A: **text** ingests the body text (tables rendered as text);
  **images** additionally captures what the figures show.
- **Locators are page locators** (`p. 12` / `pp. 3-5`); see `schema.md` § Locators. They are
  agent-verified — there is no offline text to check them against, so verify them yourself with
  extra care.

Images mode requires a backend whose file reader renders PDF pages visually (e.g. the claude
CLI); other backends may silently ingest text only.

Locators are **required** for every PDF citation in both setups (`schema.md` § Locators).
