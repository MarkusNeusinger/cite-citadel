# ingest — fold ONE new raw source into the wiki

The source is **new**: the wiki does not cite it yet. Capture **every fact** it holds — for
code/config/data, its *essence* (`core.md` § Code & structured sources) — routed to the page
where it best fits, fully cited per `schema.md`, densely cross-linked, and without duplicating
what already exists.

- **Open and read the source yourself.** It may be any text-bearing file type — markdown, plain
  text, code such as `.py`/`.sql`, JSON/CSV, … — unless a format brief routes you to a prepared
  file instead (a PDF, Office file, image, or git repo; the run instruction says which applies).
- Apply the matching **genre briefs** (`core.md` § Genres) — judged from the content you just
  read.
- **Enumeration check.** If the source — or any section of it (a table, an appendix, a bulleted
  inventory) — lists like entries, that section is registry material (`genres/registry.md`):
  captured row-by-row on a `Registry` page, never scattered as loose facts. And when the source
  mentions a **keyed entity** (a machine number, an error code, a customer ID), check
  `registries/` first — an existing row is that fact's home.
- **Pre-write dedup.** Before writing a canonical, headline fact, search the wiki for it: if the
  same fact already lives on a page, add your `[^sN]` marker beside the existing statement there
  (`schema.md` § Per-fact provenance) instead of restating the fact on another page.
- If the source adds nothing new, make no edits and stop (`core.md`).

## Large sources — segmented passes

When a source is too large for one pass, the system splits it and runs you once per segment. Your
run instruction says **which segment this is** (part / total) and where the segment's slice was
written.

- **Read the slice for content; cite the whole source.** `resource:` and every `[^sN]` definition
  name the ORIGINAL source — never the segment file. Ingest only what THIS segment contains; do
  not invent continuations of it.
- **At the edges, a cut unit may be read whole — but not claimed.** Segments are split on
  paragraph or line boundaries, never on meaning, so a sentence, table row, or list item can be
  cut by the edge. Where your format brief says the prepared file holds the WHOLE text and bounds
  you to a line window (PDF extractions, transcripts), read the few lines past the edge needed to
  see that unit entire. Fold it in only if it **begins** inside your window, and cite the range it
  actually occupies; a unit that began earlier belongs to the pass that owned it. Where instead
  you were handed a physically sliced segment file, the slice is all there is — say what it
  supports and stop.
- **Segment 1** — the first pass. Later segments of the SAME source will follow and EXTEND the
  pages you create, so capture this segment's facts now and expect to add more.
- **Segment N > 1** — segments 1..N-1 were already folded into the wiki in prior passes. ADD this
  segment's facts, MERGING into the pages the earlier passes created — do not duplicate pages or
  restate facts already captured. More segments may follow.
