# beverages — the coffee + tea showcase corpus

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and was authored by hand for
> testing and demonstrating cite-citadel. The brands, people, and companies (Caffè Aurora, Lina
> Marchetti, Cordwell Roastworks, Thornbury & Lin, Sir Edmund Thornbury, Mei Lin) are **fictional**;
> any resemblance to real persons or organizations is accidental. The coffee and tea science, on the
> other hand, is real. Safe to publish.

cite-citadel's **showcase** corpus and its original end-to-end test: fourteen short documents — eight
about **coffee**, six about **tea** — written in deliberately mixed registers (a reference guide, a
prose essay, lab-notebook jottings, an FAQ, brand blogs, an extraction-science reference sheet, a
tea-processing-and-cultivar deep dive, and a pair of dated seasonal bulletins two years apart) so the
same facts recur across sources in different words — and, where the sources disagree or a date moves
the story on, so the wiki has to reconcile them. It is the corpus the README walks through and the one
the committed demo wiki (`corpora/beverages/wiki/`, republished as the GitHub Pages viewer) is built
from.

## What it exercises

All three project guarantees at once: repeated facts must **stay organized** (merge onto one
co-cited page, not fan out one page per source), the coffee and tea halves must **link into one
graph** (they share caffeine and a trading house), and every fact must carry **honest provenance** —
single-source facts survive, disagreements surface as contradictions, and a deliberately-false
sourced claim is recorded as stated and questioned, never quietly corrected.

## Grading

The answer key is `.claude/skills/verify-corpus/beverages/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, or answer notes anywhere under `corpora/beverages/`.
