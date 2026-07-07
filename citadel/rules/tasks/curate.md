# curate — improve EXISTING wiki pages against a findings checklist

Nothing new is being ingested. The wiki already holds these pages; a periodic health pass found
issues worth fixing. Your run instruction names the **cluster anchor** page and a **prepared
findings file** — read THIS first: it is a checklist of the concrete issues detected for this
cluster (the anchor page, the raw files it cites, and its direct link neighbors). Work that
cluster — the anchor page, the pages it links to, and the raw files they cite.

## Improve or do nothing — never churn

Read the findings, then read the pages and the cited raw files they name. Act on a finding ONLY
where it genuinely holds against those sources:

- **If the findings do not hold up, make no edits and stop.** A NOOP is a correct, expected
  outcome — a wrong "fix" is worse than none. Do not reword, reorder, or touch anything the
  findings did not flag; this is not a rewrite pass.

## Hard invariants — never cross these

- **Never invent, never break provenance.** See `schema.md` § Grounding for the `[^sN]` (raw) vs
  `[^llmN]` (labeled model note) grammar and how a fact carries its marker + `## Sources` definition
  when it moves (`core.md` § Restructuring). Curation only reorganizes and repairs what is already
  cited — it never manufactures a fact or a citation.
- **Preserve counterfactuals as stated** (`schema.md` § Grounding): a sourced claim you believe is
  wrong stays as the source stated it, cited — never "corrected" out.
- **Never resurrect a deleted fact or invent a replacement for one.**

## What curation MAY do

- **Re-sort.** Move a page into the folder its `type` routes to (`schema.md` § OKF types), or
  break an oversized `misc/` grab-bag into properly-typed pages.
- **Split an overlong page** along its topics: write the focused new pages — **every fact keeping
  its `[^sN]` marker and its `## Sources` definition** — then delete the original and repoint
  inbound links (`core.md` § Restructuring). Every fact and citation survives the split.
- **Merge duplicate pages, add a missing cross-link, or fix a broken link** (`core.md` §
  Restructuring), and **resolve a flagged contradiction** only when you are highly confident — as
  a labeled `[^llmN]` resolution line, never by dropping a side (`schema.md` § Contradictions).
- **Re-verify a fact against its still-unchanged raw source** when a finding asks: correct a
  drifted paraphrase to what the file actually says, never adding beyond it.

## Before you finish

When your edits are complete, run `citadel check` **once** (or `uv run python -m citadel check`)
and fix every error on the pages you touched; only re-run it to confirm your fixes if it reported
errors. The system re-runs the same gate and rolls the WHOLE cluster back on any error — leaving
the wiki exactly as it was — so leave it clean or leave it untouched.
