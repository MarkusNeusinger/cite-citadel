# office — binary Office files, pre-extracted

Applies when the run instruction says the source is a binary **Office** file — PowerPoint / Word
/ Excel (`.pptx`/`.docx`/`.xlsx`, their macro-enabled variants, and the legacy
`.ppt`/`.doc`/`.xls`) — which you cannot open directly.

- The system **extracted its text** to a temporary file; the run instruction names it. **Read
  that** for the content.
- Any **images embedded in the file** were extracted to a `media/` folder beside it. **View the
  informative ones** — diagrams, charts, and screenshots carry facts the text extractor cannot —
  and ingest their facts too; ignore decorative icons and logos.
- Cite the **original Office file** as the source of record: `resource:` and every `[^sN]`
  definition name the original file, never the extracted temp files.
- If it holds no usable content, make no edits and stop.
- Every citation into an Office source **requires a locator** (`schema.md` § Locators). The extract
  marks structure with headings, not pages, so use a heading anchor copied verbatim from it:
  `, § Slide 12`, `, § Speaker notes`, `, § Sheet: Budget` (or `, lines A-B` for a run of a Word
  document). **One slide/sheet per marker** — never a range like `§ Slide 2-4` (split it into
  `§ Slide 2` and `§ Slide 4`, each behind its own footnote) — and **never `p. N`**: a `.pptx`/
  `.docx`/`.xlsx` extract has slides, notes, and sheets, not pages, so a page locator cannot
  resolve.
- A **legacy** `.doc`/`.ppt`/`.xls` extract is different: the salvage from an old compound file is
  a flat run of recovered text with **no headings at all**, so a `§ Slide N` / `§ Sheet: …` anchor
  can never resolve there. Cite the recovered lines instead — `, lines A-B`, often just `, line 1`
  when the whole salvage is one line.
