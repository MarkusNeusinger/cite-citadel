# SCHEMA — the wiki's structure and maintenance rules

> This file is the **schema/config layer** of the three-layer LLM-Wiki pattern
> (see [`docs/karpathy-llm-wiki.md`](docs/karpathy-llm-wiki.md)). It is read by humans
> **and injected verbatim into the ingest model's system prompt**, so editing this file
> changes how the wiki is built — with no code change. The wiki uses Google's
> [Open Knowledge Format](docs/okf-reference.md).

## Layers

1. **Raw sources** — immutable files the model reads but never edits: `raw/*.md` (user
   drops arbitrary markdown here) and the seed docs in `docs/`.
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
| `Index` / `Log`      | (generated)       | `index.md` catalogs and `log.md` — not authored by ingest. |

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

## Per-fact provenance — the load-bearing rule

**Every factual sentence cites the `raw/` file it came from, directly**, using a
GitHub-Flavored-Markdown footnote:

- End each fact with a marker: `... self-attention.[^s1]`
- Define every marker once in a trailing `## Sources` section, linking to the raw file
  with a **relative** path:
  `[^s1]: [raw/attention.md](../../raw/attention.md) — short note (ingested 2026-06-21)`
- Multiple sources for one fact: `... fact.[^s1][^s2]`.
- A claim you cannot tie to a raw file: **drop it.** Never invent provenance.
- A later ingest that adds a fact from a new raw file appends a new `[^sN]` definition and
  tags the new fact — it leaves existing facts and citations intact.

## Cross-linking

Link pages to each other with **relative** markdown links whose target is the other page's
file, e.g. from `concepts/transformer.md`:
`[Andrej Karpathy](../entities/andrej-karpathy.md)`. The file path is the page's identity;
the links form the knowledge graph. Link a concept whenever you mention its subject.

## Contradictions — flag, don't overwrite

If a raw file contradicts an existing page, **do not silently overwrite**. Insert a callout
that names both claims with both source markers:

```
> [!CONTRADICTION]
> raw/a.md says revenue grew 12% [^s1]; raw/b.md says it grew 9% [^s2].
```

## Workflows

- **Ingest** — for each new/changed `raw/` file: read it, compare against the existing wiki
  pages provided in the digest, and return page operations that **merge into** existing
  pages (returning the full merged body) rather than duplicating. Cite every fact. Flag
  contradictions. (One model call per file.)
- **Query** — an AI searches the wiki via the MCP server (`wiki_search`, `wiki_read`,
  `wiki_index`) and synthesizes cited answers from the pages — it does not re-read `raw/`.
- **Lint** — a periodic health check (`okf-wiki lint`) surfaces contradictions, orphaned
  pages, facts missing citations, broken cross-links, pages missing `type`, and stale pages.
