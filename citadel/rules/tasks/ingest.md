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
- If the source adds nothing new, make no edits and stop (`core.md`).

## Large sources — segmented passes

When a source is too large for one pass, the system splits it and runs you once per segment. Your
run instruction says **which segment this is** (part / total) and where the segment's slice was
written.

- **Read the slice for content; cite the whole source.** `resource:` and every `[^sN]` definition
  name the ORIGINAL source — never the segment file. Ingest only what THIS segment contains; do
  not invent continuations of it.
- **Segment 1** — the first pass. Later segments of the SAME source will follow and EXTEND the
  pages you create, so capture this segment's facts now and expect to add more.
- **Segment N > 1** — segments 1..N-1 were already folded into the wiki in prior passes. ADD this
  segment's facts, MERGING into the pages the earlier passes created — do not duplicate pages or
  restate facts already captured. More segments may follow.
