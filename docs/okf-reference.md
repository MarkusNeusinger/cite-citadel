# Open Knowledge Format (OKF) — reference note

> **Source / attribution.** The authoritative specification is
> [`GoogleCloudPlatform/knowledge-catalog` → `okf/SPEC.md`](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md).
> The Google Cloud blog *"How the Open Knowledge Format can improve data sharing"*
> (<https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing>)
> is a secondary introduction.
>
> This note captures just enough of OKF v0.1 to explain how this repository's `wiki/`
> directory is structured. Defer to
> [SPEC.md](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md)
> for anything not covered here.

## What OKF is

OKF is an **open, vendor-neutral specification** for representing and sharing knowledge so
that both humans and AI agents can use it. The whole point is portability: knowledge that
currently lives locked inside incompatible systems (catalogs, wikis, code comments, drives)
is instead expressed as plain files anyone can read, ship, and version-control.

> *"Just markdown. Just files. Just YAML frontmatter."*

## File structure

An OKF **bundle** is a **directory of markdown files**, each with a YAML frontmatter
block. Two filenames are reserved: `index.md` (a directory listing for progressive
disclosure, itself carrying no frontmatter) and `log.md` (chronological history). Example:

```
wiki/
├── index.md
├── concepts/
│   ├── index.md
│   └── transformer.md
└── entities/
    ├── index.md
    └── andrej-karpathy.md
```

## Frontmatter schema

```yaml
---
type: Concept            # REQUIRED — the only mandatory field
title: Transformer       # optional, human-readable
description: ...          # optional, one-line summary
resource: ...            # optional, URL/path to the authoritative source
tags: [ml, architecture] # optional, searchable tags
timestamp: 2026-06-21T... # optional, ISO 8601 last-update time
---
```

- `type` is the **only required field**; `title`, `description`, `resource`, `tags`, and
  `timestamp` are recommended-but-optional (the spec lists them in that priority order).
- The spec is *minimally opinionated*: `type` values are not registered centrally — producers
  pick descriptive ones — and producers may add custom fields, which consumers preserve on
  round-trip rather than discard.

## Cross-linking (the knowledge graph)

Concepts link to one another with **standard markdown links**, each asserting an (untyped,
directed) relationship, so the links form a graph richer than the directory tree alone. The
spec allows two path forms: **bundle-relative absolute** (a leading `/`), recommended because
it survives moves, and plain **relative** paths like `[transformer](../concepts/transformer.md)`.
File paths are concept identities, and consumers must tolerate broken links. citadel supports
**only** the relative form for wiki cross-links: a `/`-prefixed bundle-absolute link (the spec's
recommended move-stable form) is treated as a source-style reference and skipped by the link graph
— it will neither work as a wiki link nor be flagged by lint. Authors must therefore use relative
links.

## Provenance & history

- **`resource`** points to the authoritative source of a page.
- **`log.md`** gives optional chronological history (date-grouped, newest first).
- **`timestamp`** tracks versions.

## How this repo uses OKF

The `wiki/` directory is an OKF bundle. It uses the relative link form throughout and, stricter
than the spec's "tolerate broken links", treats any broken link as an error (`citadel lint` /
`check` fail on one). Beyond the standard fields, each page records the `raw/` source files it was
derived from, and **every individual fact carries an inline citation back to the exact raw source**
(see [`schema.md`](../citadel/rules/schema.md) for the precise convention). This satisfies the
project goal: *a source reference for every fact*.
