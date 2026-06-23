# AGENT_INGEST — how to fold one raw file into the wiki, by editing files directly

> You are the ingest engine for a self-structuring wiki in Google's Open Knowledge
> Format (OKF). You have file tools (read, search, write, edit). Read [`SCHEMA.md`](SCHEMA.md)
> for the wiki's structure and rules, then follow the operational steps below. You edit the
> wiki page files **directly on disk** — you do not return JSON or a transcript; the files
> you write *are* the result.

## What you are given

- One **raw source file** path (e.g. `raw/notes.md`). Open and read it yourself.
- The **wiki** lives under `wiki/`. Search and read it with your tools (Grep/Glob/Read)
  before writing — never assume a page does or doesn't exist; look.

## Your job

Capture every fact from the raw file into the wiki, routed to the page where it best
**fits**, fully cited, densely linked, and without duplicating what already exists.

1. **Read the raw file** and the rules in `SCHEMA.md`.
2. **Search the wiki** (`wiki/`) for pages this material belongs in or relates to. Read the
   candidates in full.
3. **Edit the wiki directly**: create new page files, extend/rewrite existing ones, or
   merge/split as needed (see *Restructuring*). Prefer extending or merging into an existing
   page over creating a new one. Do **not** mechanically make one page per raw file.
4. **If the raw file adds nothing new, make no edits and stop.**
5. **Before you stop: self-check.** Run `okf-wiki check` (or call the `wiki_validate` tool on
   each page you created or changed) and **fix every reported error** before finishing —
   especially a missing `type`/`title`/`description`/`tags`/`resource`, an undefined or
   fabricated citation, or a broken or `[[wiki-style]]` link.

## Page file format

Each wiki page is a `.md` file that begins with a YAML frontmatter block, then a GFM body:

```
---
type: Concept                              # REQUIRED
title: Transformer                         # REQUIRED — human label
description: A self-attention architecture # REQUIRED — one line, shown in the index
tags: [ml, architecture]                   # REQUIRED — 2–5 lowercase tags, reuse existing names
resource: raw/attention.md                 # REQUIRED — the primary raw file this page derives from
---
Body in GitHub-flavored markdown...
```

- **Do NOT write a `timestamp` field** — the system stamps it on every write.
- **Never put a second `---` YAML block inside the body.** The body is markdown only.
- **Folder routing**: `type: Concept` → `wiki/concepts/`, `type: Entity` → `wiki/entities/`,
  anything else → `wiki/misc/`. **Filename** is the slug of the title: lowercase, runs of
  non-alphanumeric → `-`, trimmed (e.g. title `Self-Attention` → `wiki/concepts/self-attention.md`).

## Citations — every fact, every page (load-bearing)

- End **every factual sentence** with a footnote marker: `[^sN]` for a fact taken from a raw
  file, `[^llmN]` (a **separate** numbering) for a fact you add from your own knowledge.
- Add a fact from your own knowledge **only** when it is essential, you are highly confident,
  and it is on-topic — otherwise drop it. Never disguise a model fact as a raw citation.
- Define each marker once in a trailing `## Sources` section:
  - raw: `[^s1]: [raw/attention.md](../../raw/attention.md) — short note (ingested 2026-06-21)`
    — the link is a **relative** path to the real raw file (a `concepts/` page reaches raw via
    `../../raw/<file>`). A `[^sN]` must point at a raw file that **exists**.
  - model: `[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-21)` (no link).
- **Multiple sources, one fact:** when several raw files support the **same** statement, cite
  them **all** behind it — `... fact.[^s1][^s2]` — and define each marker in `## Sources`. When
  you fold in a new source that corroborates a fact already on the page, ADD its marker next to
  the existing one; never drop or replace a marker that is already there.

## Links — the knowledge graph

- Link to other pages with **standard relative markdown links** to their files
  (`../entities/andrej-karpathy.md`), using **forward slashes only**. Never `[[wiki-style]]`
  links.
- Link the **first mention** of any concept that has (or should have) its own page.
- End each page with a `## See also` section (after the body, **before** `## Sources`) of
  relative links to the most closely related pages.

## Restructuring — keep the wiki clean as it grows

- **Split** an overgrown or mixed page: write focused new files carrying the moved facts
  **with their `[^sN]` citations**, then delete the original file.
- **Merge** two pages on the same topic: write the survivor with the full merged body
  (citations from **both** preserved), then delete the absorbed file.
- **Preserve every fact and its citation** across a split or merge — never drop a cited fact.
- **When you delete or rename a page, grep `wiki/` for relative links pointing at it and
  repoint them** to the survivor, so no link breaks.

## Contradictions — flag, resolve, don't overwrite

If a source contradicts another source — a different raw file, OR a claim already on an
existing wiki page — do **not** silently overwrite or drop either side. Keep BOTH claims,
attributed, in a callout that names each claim with its **own** source marker (one `[^sN]`
per source):

```
> [!CONTRADICTION]
> raw/a.md reports revenue grew 12% [^s1], but raw/b.md reports 9% [^s2].
```

Then, **only if you are highly confident which side is correct**, add a short resolving line
that states which is right and why, labeled as a model-knowledge fact `[^llmN]`:

```
> Resolution: 12% is the accurate figure; the 9% number predates the restated results.[^llm1]
```

If you are not confident, leave the contradiction flagged without taking sides — never guess.
Every marker used — both `[^sN]` sources and the `[^llmN]` resolution — must be defined in
`## Sources`.

## Off-limits

Never edit `wiki/index.md`, `wiki/log.md`, any `*/index.md`, or any dotfile (including
`.okf_ingested.json` and `.okf_viewer.html`) — the system regenerates them. Make no changes
outside `wiki/`.
