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
- Every citation into an Office source **requires a locator** (`schema.md` § Locators): use the
  page / slide / sheet position visible in the extract — `, p. 12`, or a heading anchor such as
  `, § Slide 12` or `, § Sheet: Budget` where the extract marks slides/sheets instead of pages.
