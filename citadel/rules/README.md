# citadel/rules — the rulebook the ingest agent reads

Every agent session is composed **by path reference** (never embedded content): the run
instruction built by `citadel/llm.py` names files from this tree, and the agent reads them with
its own tools. Every session reads `core.md` + `schema.md` + **one** task brief + any matching
format brief(s); genre briefs are applied by the agent's own content judgment. Editing these
files changes how the wiki is built — **with no code change**; treat them as part of the program.

| File | Purpose | Consumed by |
| ---- | ------- | ----------- |
| `schema.md` | The format contract: OKF frontmatter, folder routing, citation grammar + locators, grounding/quality contract, contradictions, links, tags, abbreviations, wiki language, opinions & style | every session |
| `core.md` | Generic behavior: paths-verbatim, workflow, path-as-context, code essence, genre selection, restructuring, off-limits, self-check | every session |
| `tasks/ingest.md` | Fold a NEW source in; segmented large-source passes | kinds `ingest`, `image`, `repo` |
| `tasks/reconcile.md` | Re-fold a CHANGED (or force-re-read) source: update/remove stale facts, re-check locators, keep genre treatment | kinds `reconcile`, `image-reconcile`, `repo-reconcile` |
| `tasks/delete.md` | Strip a REMOVED source's provenance | kind `delete` |
| `tasks/curate.md` | Improve EXISTING pages against a run's findings checklist: re-sort, split, merge, re-verify — improve-or-NOOP, never invent, never break provenance | kind `curate` (`citadel curate`) |
| `formats/repo.md` | A git repo as one source: the digest, capture-by-use, System pages, repo-reconcile | repo sources |
| `formats/image.md` | View an image source and transcribe its facts | image sources |
| `formats/pdf.md` | PDFs read whole; `text` vs `images` mode; page locators | PDF sources |
| `formats/office.md` | Pre-extracted Office text + embedded `media/`; cite the original file | Office sources |
| `genres/prose.md` | Extraction restraint for essays/articles; author claims vs reported facts | agent judgment |
| `genres/meeting-minutes.md` | Tracking artifacts: `## Open Points` threads, `## Change Log`, dates, supersede ≠ contradiction | agent judgment |
| `genres/email.md` | Threads and quoting: attribute to the original author; dedupe quote chains | agent judgment |
| `genres/first-person.md` | One person's voice: attributed positions always; opt-in style profiles | agent judgment |

The two axes are decided by two different parties: a **format** is structurally detectable, so
the *code* selects the format brief (repo markers, image/Office extensions, PDF); a **genre** is
a judgment about what the text *is*, so the *agent* selects genre briefs from the content —
never from the filename, and never in Python.

## Genres are a starter set

The `genres/` files are examples, not a taxonomy. The run instruction enumerates whatever the
**effective** `genres/` directory contains at prompt-build time, so a genre file dropped into a
workspace `rules/genres/` participates automatically — adding `lab-notebook.md` or
`support-tickets.md` is a one-file act, no code change. The agent applies none, one, or several
per source; a source matching no genre simply follows the core rules. **Each genre file starts
with one line saying when it applies.**

## Workspace overrides & `local.md`

Rules resolve in two layers, first hit wins **per filename**: the workspace `rules/` directory
over this packaged tree. To fork a default, copy that one file into the workspace
(`citadel rules eject <name>`) — a copied file is owned by the user; everything else keeps
updating with pip. A workspace `rules/local.md`, when present, is always appended as one more
path — the additive, upgrade-safe home for house rules.

## How the system drives a session (context, not agent rules)

- The wiki tracks each source by **content hash**, so a change to raw/ propagates: an **edited**
  source re-runs under `tasks/reconcile.md`; a **deleted** source runs `tasks/delete.md`
  (detected on a full run); a source merely **moved/reorganized** (same bytes, new path) is *not*
  re-ingested — its `resource`/citation references are repointed mechanically (a move is not a
  deletion).
- A source **too large for one context window** is folded in over several sequential segment
  passes (`tasks/ingest.md` § Large sources).
- When the same document exists in **multiple formats** with the same basename (`report.pptx` +
  `report.pdf`), only one is ingested (PDF preferred); the rest are skipped as duplicates.
- Sources that could **not** be ingested — unreadable files, sessions that errored or timed out,
  skipped duplicates — are recorded persistently and listed under *Could not ingest* in the
  generated `sources/index.md`.
- The agent works on a **staging copy** of the wiki; after the session the system diffs the wiki,
  re-validates and re-stamps every changed page, repoints renamed-page links, rebuilds the
  indexes, and only a fully **clean** source is promoted onto the live wiki (all segments of a
  chunked source promote once, together).
- Two gates, one strict and one advisory: **`citadel check`** (MCP `wiki_validate`) is the hard
  per-page gate the agent self-runs and the system re-runs; **`citadel lint`** is the periodic
  offline health check — contradictions, orphaned pages, facts missing citations, broken
  cross-links, pages missing `type`, stale pages, fabricated sources (a fact citing a raw file
  that does not exist), undefined abbreviations, and `[[wiki-style]]` links.
- Consumers **query the wiki, not raw/**: an AI reads it via the MCP server (`wiki_search`,
  `wiki_read`, `wiki_index`, `wiki_sources`, `wiki_tags`) and synthesizes cited answers from the
  pages.
