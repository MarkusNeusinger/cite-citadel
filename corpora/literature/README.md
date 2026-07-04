# literature — one long novel as a chunking + narrative stress test

> **SOURCE / provenance:** Jane Austen, *Pride and Prejudice* (1813). **Public domain.** Text
> derived from Project Gutenberg eBook #1342 with all Project Gutenberg boilerplate removed
> (everything up to and including the `*** START OF …***` line and from the `*** END OF …***` line
> onward — no trademark or licence text remains); Project Gutenberg is **not affiliated with** this
> project. The novel body is reproduced text-faithfully — no prose altered or abridged; only line
> endings were normalized to LF.

A single ~730,000-character plain-text source: the whole novel, title page through finis, in
`raw/pride-and-prejudice.txt`.

## What it exercises

- **Large-source multi-segment chunking** — one file far past `CITADEL_MAX_SOURCE_CHARS` is folded
  in over many passes against one staging copy; every third of the book must survive the merge.
- **Relationship extraction** — five sisters, four marriages, four estates and their occupants must
  come out as a connected `persons/` + `objects/` graph, not a per-chapter pile.
- **In-novel misinformation** — Wickham's false account of Darcy must be recorded *as Wickham's
  claim*, later revealed false by Darcy's letter — never adopted as plain fact.
- **Narrative supersession** — early states (Elizabeth's dislike; the refused first proposal;
  Jane and Bingley's separation) are the *arc*, not the *final fact*; the wiki's current state is
  the ending.

## Grading

The answer key is `.claude/skills/verify-corpus/literature/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, plot summaries, or answer notes anywhere under `corpora/literature/`.
