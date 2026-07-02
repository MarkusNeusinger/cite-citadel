# pdf — read whole; figures per mode; page locators

Applies when the source is a **PDF**. Open and read it directly with your file reader.

A PDF is read **whole, unchunked by design** — the system never splits a PDF into segments the
way it does large text sources, because page numbers, figures, and layout carry meaning the
slicer would destroy. That puts a practical ceiling on PDF size: a very large PDF (hundreds of
dense pages) may not fit one session — such a run fails/times out and lands under *Could not
ingest*; the remedy is to split the PDF file itself in raw/.

Your run instruction names the active **PDF mode**:

- **text** — ingest the body text (including tables, rendered as text). Do not spend the session
  interpreting figures.
- **images** — additionally **LOOK AT** the pages' figures, diagrams, and charts (not just the
  body text) and capture what they show, cited like any fact.

Images mode requires a backend whose file reader renders PDF pages visually (e.g. the claude
CLI); other backends may silently ingest text only.

Locators are required here — every PDF citation carries a **page locator**; see `schema.md`
§ Locators for the forms.
