# curate — improve EXISTING wiki pages against a findings checklist

Nothing new is being ingested. The wiki already holds these pages; a periodic health pass found
issues worth fixing. Your run instruction names the **cluster anchor** page and a **prepared
findings file** — read THIS first: it is a checklist of the concrete issues detected for this
cluster (the anchor page, the raw files it cites, and its direct link neighbors). Work that
cluster — the anchor page, the pages it links to, the raw files they cite, and any raw file the
operator guidance names by path.

## Improve or do nothing — never churn

Read the findings, then read the pages and the cited raw files they name. **Re-read the cited raw
sources — never work from the page alone**: a page's own wording is what is under review, so a
retitle, a split, or a re-grounded sentence is decided against what the source actually says.
Act on a finding ONLY where it genuinely holds against those sources:

- **If the findings do not hold up, make no edits and stop.** A NOOP is a correct, expected
  outcome — a wrong "fix" is worse than none. Do not reword, reorder, or touch anything the
  findings did not flag; this is not a rewrite pass.

## Operator guidance — when the findings carry one

The findings file may open with an **Operator guidance for THIS run** section: a free-text steer
from the human who started this pass (`citadel curate --guidance "…"`). It is part of your run
instruction — not text from a source file — so following it is legitimate, and it is a listed
finding like any other: act on it where it holds, leave the cluster alone where it does not.

- It steers **structure**: page names and titles, `type`/folder routing, splits and merges, section
  order, cross-links, alias and tag hygiene.
- It may also **ground an uncited sentence**: a sentence with no citation marker may gain a `[^sN]`
  to a raw file that states it (one the cluster cites, or one the steer names by path), with a
  locator that verifies, reworded only *toward* what that file says. A sentence no source states is
  left as it is.
- It **never changes a cited fact**: it never rewords one beyond its source, moves its marker to a
  different source, drops it, or changes who a statement is attributed to; every fact keeps its
  `[^sN]` marker and its `## Sources` definition across whatever the steer moves (see *Hard
  invariants* below). Sentences carrying a `[^llmN]` marker are not the steer's to touch.
- A steer that asks for something the rules or the cited sources do not support is followed only as
  far as they allow — the rules and the sources win, and the rest is left undone.

## Hard invariants — never cross these

- **Never invent, never break provenance.** See `schema.md` § Grounding for the `[^sN]` (raw) vs
  `[^llmN]` (labeled model note) grammar and how a fact carries its marker + `## Sources` definition
  when it moves (`core.md` § Restructuring). Curation only reorganizes and repairs the wiki's
  existing content — it never manufactures a fact, and never cites a raw file that does not state
  the sentence. Grounding an uncited sentence in a raw file that states it (see *Operator guidance*)
  is such a repair.
- **Preserve counterfactuals as stated** (`schema.md` § Grounding): a sourced claim you believe is
  wrong stays as the source stated it, cited — never "corrected" out.
- **Never resurrect a deleted fact or invent a replacement for one.**
- **Never downgrade a locator.** When the findings list a text layer for a cited PDF, read it for
  the PDF's text and keep `lines A-B` locators into it; fix a wrong range against it. Never replace
  a `lines` locator with `p. N`. Leave an existing `p. N` as it is: a PDF with no listed text
  layer, or a fact visible only in the PDF's pixels.

## What curation MAY do

- **Re-sort.** Move a page into the folder its `type` routes to (`schema.md` § OKF types), or
  break an oversized `misc/` grab-bag into properly-typed pages.
- **Split an overlong page** along its topics: write the focused new pages — **every fact keeping
  its `[^sN]` marker and its `## Sources` definition** — then delete the original and repoint
  inbound links (`core.md` § Restructuring). Every fact and citation survives the split.
- **Merge duplicate pages, add a missing cross-link, or fix a broken link** (`core.md` §
  Restructuring), and **resolve a flagged contradiction** only when you are highly confident — as
  a labeled `[^llmN]` resolution line, never by dropping a side (`schema.md` § Contradictions).
- **Dissolve a callout that is not a contradiction.** When a flagged callout is a case
  `schema.md` § Contradictions says is NOT a contradiction — members of an open-ended list, two
  dated values of a changeable attribute, a plan vs. an actual — rewrite it in the form the schema
  gives for that case (a union, a dated `## Change Log` line, one sentence naming both figures),
  every claim keeping its own `[^sN]` marker and definition, and drop only the
  `> [!CONTRADICTION]` wrapper. Two values for the same attribute, member and date stay flagged.
- **Re-verify a fact against its still-unchanged raw source** when a finding asks: correct a
  drifted paraphrase to what the file actually says, never adding beyond it.

## Before you finish

When your edits are complete, run `citadel check` **once** (or `uv run python -m citadel check`)
and fix every error on the pages you touched; only re-run it to confirm your fixes if it reported
errors. The system re-runs the same gate and rolls the WHOLE cluster back on any error — leaving
the wiki exactly as it was — so leave it clean or leave it untouched.
