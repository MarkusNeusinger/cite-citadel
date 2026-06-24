# SCHEMA — the wiki's structure and maintenance rules

> This file is the **schema/config layer** of the three-layer LLM-Wiki pattern
> (see [`docs/karpathy-llm-wiki.md`](docs/karpathy-llm-wiki.md)). It is read by humans
> **and injected verbatim into the ingest model's system prompt**, so editing this file
> changes how the wiki is built — with no code change. The wiki uses Google's
> [Open Knowledge Format](docs/okf-reference.md).

## Layers

1. **Raw sources** — immutable files the model reads but never edits: anything under `raw/`
   (any text-bearing file type — markdown, plain text, code such as `.py`/`.sql`, JSON/CSV,
   PDF, … — in any sub-folder) and the seed docs in `docs/`. Ingest tries to extract text from
   **every** file; one with no readable text (a binary blob) is skipped and logged as
   unreadable. A raw file that was only **moved/reorganized** (same bytes, new path) is
   recognized and **not** re-ingested — its wiki `resource`/citation references are repointed
   automatically.
2. **The wiki** — LLM-generated OKF pages under `wiki/`: a directory of markdown files
   with YAML frontmatter, cross-linked into a knowledge graph.
3. **The schema** — this file.

## OKF types and folder routing

`type` is the only **required** frontmatter field. Producers may use any type. This wiki
routes by type:

| `type`               | Folder            | Meaning                                       |
| -------------------- | ----------------- | --------------------------------------------- |
| `Concept`            | `wiki/concepts/`  | An idea/topic synthesized across sources.     |
| `Entity`             | `wiki/entities/`  | A named thing: person, org, project, tool.    |
| anything else        | `wiki/misc/`      | Note, Metric, Runbook, etc.                   |
| `index.md` / `log.md`| (generated)       | OKF reserved navigation/history files — not authored by ingest. |

`index.md` and `log.md` are the two OKF-reserved filenames and are **generated**, not written
by the model. Per OKF they carry **no YAML frontmatter**: `index.md` is the progressive-
disclosure catalog (pages by type, backlinks, a `## Tags` section) and `log.md` is the
append-only history with `## YYYY-MM-DD` date headings. The loader skips both. (`okf-wiki view`
also writes a `.okf_viewer.html` — a regenerable, gitignored offline viewer derived purely from
the bundle, not a source of truth; the loader skips it too.)

## Frontmatter fields

```yaml
---
type: Concept                 # REQUIRED — the only mandatory field
title: Transformer            # human label
description: A self-attention architecture.   # one line; shown in index.md
resource: raw/attention.md    # the PRIMARY raw file this page was derived from
tags: [ml, architecture]      # lowercase
timestamp: 2026-06-21T12:00:00Z   # set automatically on every write
---
```

Extra fields are allowed and preserved.

## Grounding — raw is primary truth; model-added facts must be labeled

The `raw/` files are the primary source of truth. The ingest model must:

- Build each page from the facts in the raw text. Rephrase into clean, well-formed
  sentences and reorganize freely, but **never** change the meaning, the numbers, the names,
  or the claims of a raw fact.
- It **may** add a fact from its own knowledge **only** when all three hold: the fact is
  **essential** to understanding the topic, the model is **highly confident** it is correct,
  and it stays **strictly on topic** (no padding, no tangents). When in doubt, leave it out.
- Cite every factual sentence: `[^sN]` for a fact from a raw file, `[^llmN]` (a separate
  numbering) for a model-supplied fact. A `[^sN]` marker must point to a **real** `raw/`
  file — a citation to a missing file, or a marker used but never defined, is a lint failure.
  A `[^llmN]` is defined in `## Sources` as `[^llmN]: LLM - model knowledge, not from a raw
  file (added <date>)` and is surfaced by lint for transparency/audit.

## Per-fact provenance — the load-bearing rule

**Every factual sentence cites the `raw/` file it came from, directly**, using a
GitHub-Flavored-Markdown footnote:

- End each fact with a marker: `... self-attention.[^s1]`
- Define every marker once in a trailing `## Sources` section, linking to the raw file
  with a **relative** path:
  `[^s1]: [raw/attention.md](../../raw/attention.md) — short note (ingested 2026-06-21)`
- Multiple sources for one fact: `... fact.[^s1][^s2]`.
- A raw-derived claim you cannot tie to a raw file: **drop it.** Never invent provenance or
  disguise a model-supplied fact as a raw citation — label it `[^llmN]` instead (see
  Grounding above).
- A later ingest that adds a fact from a new raw file appends a new `[^sN]` definition and
  tags the new fact — it leaves existing facts and citations intact.

## Cross-linking — the knowledge graph

Link pages to each other with **standard relative markdown links** whose target is the
other page's file, e.g. from `concepts/transformer.md`:
`[Andrej Karpathy](../entities/andrej-karpathy.md)` — never `[[wiki-style]]` links. The file
path is the page's identity; the links form the knowledge graph.

- **Link densely.** Link the **first mention** of any concept that has (or clearly should
  have) its own page. A well-connected graph is what makes the wiki navigable.
- **`## See also`.** End each page with a short `## See also` section (after the body, before
  `## Sources`) of relative links to the most closely related pages.
- **Backlinks are free.** The generated `index.md` lists, per page, who references it
  (`↳ referenced by: …`), computed from the real link graph — so every page is reachable from
  the pages that mention it.
- Broken links are **tolerated** by readers (a link may point at a page not written yet), but
  a restructure never *creates* one: merges/renames repoint inbound links automatically, and
  `okf-wiki lint` fails on any that remain. Lint also **suggests** links — it flags a page that
  mentions another page's title in prose without linking it.

## Tags — browse by topic

Give each page 2–5 lowercase `tags` from a shared vocabulary (reuse existing tag names where
they fit). Tags are the OKF-native `tags` frontmatter field and a second navigation axis: they
boost search ranking, power `okf-wiki tags` / `search --tag` / the MCP `wiki_tags` tool, and
are surfaced as a `## Tags` section in the generated `index.md`.

## Contradictions — flag, resolve, don't overwrite

If a source contradicts another (a different raw file, or a claim already on a wiki page),
**do not silently overwrite** or drop either side. Keep both claims, attributed, in a callout
that names each with its own source marker:

```
> [!CONTRADICTION]
> raw/a.md says revenue grew 12% [^s1]; raw/b.md says it grew 9% [^s2].
```

Then, **only when highly confident**, add a short resolving line stating which is correct and
why, as a model-knowledge `[^llmN]` fact (defined in `## Sources`). If unsure, leave it flagged
without taking sides — never guess. (Multiple sources that *agree* on a fact are cited together
behind it: `... fact.[^s1][^s2]`.)

## Restructuring — keep the wiki clean as it grows

Ingest does **not** mechanically produce one wiki page per raw file. It routes each piece
of information to the page where it best **fits**, and reorganizes existing pages when
needed:

- **Route to the best home.** Prefer extending or merging into an existing page over
  creating a new one; create a new page only when no existing page fits.
- **Split** a page that has grown too large or mixes unrelated topics: write the focused
  new pages (each carrying the moved facts *with* their `[^sN]` citations) and `delete` the
  original.
- **Merge** two pages on the same topic: write the surviving page with the full merged body
  (citations from both preserved) and `delete` the absorbed page.
- **Preserve every fact and citation** across a split or merge — never drop a cited fact.

**Links keep working.** When you delete or rename a page because its content moved, repoint
the inbound cross-links to the survivor yourself (grep the wiki for relative links to the old
file). For a pure rename (same title, new path) the system also repoints inbound links
mechanically as a safety net; any link left dangling is surfaced by ingest and fails
`okf-wiki lint` / `okf-wiki check`.

## Workflows

- **Ingest** — for each new/changed `raw/` file, an agentic CLI (one session per file) reads
  the raw file, searches the existing wiki, and **edits the wiki page files directly** —
  routing facts to the best page and **merging / splitting / restructuring** rather than
  duplicating. Use only facts from the raw file. Cite every fact. Flag contradictions. See
  [`AGENT_INGEST.md`](AGENT_INGEST.md) for the operational rules. After the session, the system
  diffs the wiki, re-validates and re-stamps every changed page, repoints renamed-page links,
  and rebuilds the indexes.
- **Query** — an AI searches the wiki via the MCP server (`wiki_search`, `wiki_read`,
  `wiki_index`, `wiki_tags`) and synthesizes cited answers from the pages — it does not re-read
  `raw/`.
- **Check** — the strict per-page gate (`okf-wiki check`, MCP `wiki_validate`): required
  fields (type/title/description/tags/resource), honest citations, and relative non-broken
  links (no `[[wiki-links]]`). The ingest agent runs it on its own edits before finishing, and
  ingest re-runs it as a hard gate so a forgotten field fails the run.
- **Lint** — a periodic health check (`okf-wiki lint`) surfaces contradictions, orphaned
  pages, facts missing citations, broken cross-links, pages missing `type`, stale pages,
  **fabricated sources** (a fact citing a `raw/` file that does not exist), and
  `[[wiki-style]]` links.
