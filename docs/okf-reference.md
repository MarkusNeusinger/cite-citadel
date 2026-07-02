# Open Knowledge Format (OKF) — reference note

> **Source / attribution.** Google Cloud blog, *"How the Open Knowledge Format can
> improve data sharing"*:
> <https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing>
>
> This note captures just enough of OKF v0.1 to explain how this repository's `wiki/`
> directory is structured. Defer to the official specification for anything not covered
> here.

## What OKF is

OKF is an **open, vendor-neutral specification** for representing and sharing knowledge so
that both humans and AI agents can use it. The whole point is portability: knowledge that
currently lives locked inside incompatible systems (catalogs, wikis, code comments, drives)
is instead expressed as plain files anyone can read, ship, and version-control.

> *"Just markdown. Just files. Just YAML frontmatter."*

## File structure

An OKF **bundle** is a **directory of markdown files**, each with a YAML frontmatter
block. Directories may contain an `index.md` for progressive disclosure. Example:

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

- `type` is the **only required field**. Everything else is optional.
- The spec is *minimally opinionated*: producers choose which `type` values exist and may
  add their own fields. Consumers ignore what they do not understand.

## Cross-linking (the knowledge graph)

Concepts link to one another with **standard markdown links**, e.g.
`[transformer](../concepts/transformer.md)`. File paths are concept identities, and the
links form a graph richer than the directory tree alone.

## Provenance & history

- **`resource`** points to the authoritative source of a page.
- **`log.md`** gives optional append-only chronological history.
- **`timestamp`** tracks versions.

## How this repo uses OKF

The `wiki/` directory is an OKF bundle. Beyond the standard fields, each page records the
`raw/` source files it was derived from, and **every individual fact carries an inline
citation back to the exact raw source** (see [`schema.md`](../citadel/rules/schema.md) for the precise
convention). This satisfies the project goal: *a source reference for every fact*.
