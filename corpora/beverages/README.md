# beverages — the coffee + tea showcase corpus

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and was authored by hand for
> testing and demonstrating cite-citadel. The brands, people, and companies (Caffè Aurora, Lina
> Marchetti, Thornbury & Lin, Sir Edmund Thornbury, Mei Lin) are **fictional**; any resemblance to
> real persons or organizations is accidental. Safe to publish.

This is cite-citadel's **showcase** corpus and its original end-to-end test: ten short documents —
five about **coffee**, five about **tea** — written in deliberately mixed registers (a structured
reference guide, a prose essay, lab-notebook jottings, an FAQ, a brand blog) so the same facts
recur across sources in different words. It is the corpus the README walks through and the one the
committed demo wiki (`corpora/beverages/wiki/`, republished as the GitHub Pages viewer) is built
from.

## The 10 raw files

| file | topic | register |
| ---- | ----- | -------- |
| `raw/coffee-guide.md` | coffee | structured reference |
| `raw/espresso-and-cafe-culture.md` | coffee | prose essay |
| `raw/cold-brew-notes.md` | coffee | lab notebook |
| `raw/coffee-health-faq.md` | coffee | FAQ |
| `raw/aurora-coffee-blog.md` | coffee | brand blog |
| `raw/tea-guide.md` | tea | structured reference |
| `raw/tea-history-and-trade.md` | tea | prose narrative |
| `raw/matcha-and-preparation.md` | tea | how-to |
| `raw/tea-health-faq.md` | tea | FAQ |
| `raw/thornbury-tea-blog.md` | tea | brand blog |

## What it exercises

The corpus is intentionally messy so a clean pass demonstrates all three of the project's
guarantees at once:

- **Stays organized** — the same facts repeat across files and must merge onto one page, co-cited,
  rather than fanning out into one isolated page per source.
- **Links keep working** — coffee and tea share a subject (caffeine) and a cross-topic trading
  house, so the two halves must connect into one graph, not two islands.
- **Honest provenance** — every fact carries a `[^sN]` citation to the file that states it;
  single-source facts survive, sources that disagree surface as contradictions instead of being
  silently reconciled, and a deliberately-false sourced claim is recorded as stated and questioned,
  never quietly corrected from world knowledge.

## Grading

The answer key is `.claude/skills/verify-corpus/beverages/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, or answer notes anywhere under `corpora/beverages/`. Run the `verify-corpus beverages`
skill to ingest the corpus into a sandbox wiki and grade the result against that key.
