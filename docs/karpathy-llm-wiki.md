# The LLM Wiki — an LLM-maintained personal knowledge base

> **Source / attribution.** This document summarizes Andrej Karpathy's note proposing
> the "LLM wiki" pattern. The authoritative original is the gist:
> <https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>
>
> This file is a faithful paraphrase kept under `docs/` as the founding idea for this
> repository. When in doubt, defer to the gist. This project (`cite-citadel`) is an
> implementation of the pattern, with the wiki stored in Google's
> [Open Knowledge Format](./okf-reference.md).

## Core concept

Instead of a traditional RAG system that re-retrieves raw documents on every query, an
LLM **incrementally builds and maintains a structured, interlinked collection of markdown
files** that sits between you and the raw sources.

The knowledge is *compiled once* into a wiki and then maintained, rather than being
re-derived from scratch on each question. The wiki is the durable artifact; the raw
sources are the ground truth it is built from.

## Three layers

1. **Raw sources** — immutable documents (articles, papers, notes, data files) that the
   LLM *reads but never modifies*. In this repo: the `raw/` directory.
2. **The wiki** — LLM-generated markdown pages: summaries, entities, concepts, and
   synthesis, cross-linked into a graph. In this repo: the `wiki/` directory, written in
   [OKF](./okf-reference.md).
3. **The schema** — a configuration document defining the wiki's structure and the
   workflows that maintain it. In this repo: the
   [`citadel/rules/`](../citadel/rules/README.md) tree, led by
   [`schema.md`](../citadel/rules/schema.md).

## Main operations

- **Ingest** — when new sources arrive, the LLM reads them, extracts the key
  information, and *integrates* the findings into the existing wiki pages: updating
  cross-references and flagging contradictions, rather than re-deriving knowledge
  repeatedly.
- **Query** — you ask a question; the LLM searches the wiki pages and synthesizes an
  answer *with citations*. High-value answers can be filed back into the wiki as new
  pages.
- **Lint** — periodic health checks surface contradictions, stale claims, orphaned
  pages, missing cross-references, and data gaps.

## Supporting infrastructure

- **`index.md`** — a content-oriented catalog of all wiki pages, each with a one-line
  summary (progressive disclosure as you navigate).
- **`log.md`** — an append-only, chronological record of ingests, queries, and
  maintenance operations.

## Why it works

Wikis usually decay because the *maintenance burden* falls on humans who eventually stop
updating cross-references and reconciling contradictions. An LLM does not tire of this
work, which makes persistent, always-consistent knowledge compilation feasible where a
human team would give up.

- **Human responsibility:** curating which sources go in, directing the analysis, asking
  good questions.
- **LLM responsibility:** all maintenance — summarization, structuring, cross-referencing,
  and consistency.

## How this repo realizes the pattern

| Karpathy's pattern        | This repository                                              |
| ------------------------- | ----------------------------------------------------------- |
| Raw sources (immutable)   | `raw/*.md` — drop arbitrary markdown here                   |
| The wiki (LLM-generated)  | `wiki/` as an [OKF](./okf-reference.md) bundle              |
| The schema/config         | the [`citadel/rules/`](../citadel/rules/README.md) tree     |
| Ingest / Query / Lint     | the `citadel` CLI (`ingest`, `lint`) + the MCP server      |
| Per-fact source reference | every fact in a wiki page cites the `raw/` file it came from |
| Querying the wiki         | an **MCP server** an AI can use to search and read the wiki |
