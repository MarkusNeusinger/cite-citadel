# project-history — one fictional programme, three years, ingested in dated waves

> **SOURCE / provenance:** Everything in this corpus is **fictional** and was authored by hand
> specifically for testing cite-citadel. The company, people, products, systems, figures, and
> events are invented; any resemblance to real persons or organizations is accidental.

This corpus is the paper trail of **Projekt LEUCHTFEUER** — the 2024–2026 replacement of the
warehouse management system at Blauwal Logistik GmbH, a fictional Bremen freight company. The
material is what a real programme leaves behind: kickoff and steering minutes, a
steering-committee Protokoll series, emails with quoted replies, a programme charter, and memos —
written by recurring people with recognizable voices. Two documents are entirely **German**
(Geschäftsdeutsch); the rest are English.

## Layout and the wave protocol

Unlike a one-shot corpus, this one is ingested in **three dated waves** that replay how a project
folder actually grows and churns:

| step | action | what it exercises |
| ---- | ------ | ----------------- |
| wave 1 | ingest `raw/` as-is (6 files — the 2024 kickoff era) | plain ingest of minutes, emails, a charter, a memo |
| wave 2 | copy `stages/wave2/` over `raw/` (4 files — 2025), then ingest. `2024-05-14-charter-leuchtfeuer.md` is **replaced** by a revised version of itself | changed-source **reconcile** |
| wave 3 | **delete** `raw/2024-06-10-memo-brandt-komet-operating-costs.md` (retracted in-universe by a wave-3 memo), copy `stages/wave3/` in (3 files — 2026), then run a **full** ingest | deleted-source **cleanup** + further ingest |
| after | re-run ingest with nothing changed (and `--force`, once available) | idempotency — the run must be a **NOOP** |

`stages/` must **never** be visible to the ingest agent: point `CITADEL_RAW_DIR` at
`corpora/project-history/raw` only, and copy the overlays in between runs.

## What it exercises

- **Temporal traceability** — decisions, dates, and figures change across the three years; the
  wiki must keep that history dated, cited, and clearly superseded instead of overwriting it or
  presenting stale values as current.
- **Reconcile / delete / force** — the one corpus that drives all three source lifecycles end to
  end, in order, on one growing wiki.
- **Minutes and email genres** — attendees, decisions, action items; `From:`/`Date:` headers,
  quoted replies, and first-person voices with opinions (pair with `CITADEL_STYLE_PROFILES=1`
  for the persons/style grading).
- **German sources, English wiki** — run with `CITADEL_WIKI_LANG=en`; the facts carried only by
  the German documents must come through intact, cited, and in English.

## Grading

The answer key is `.claude/skills/verify-corpus/project-history/ground-truth.md` — kept outside
this directory on purpose, so the ingest agent can never see it. Do not add grading material,
expected values, or answer notes anywhere under `corpora/project-history/`.
