# AGENT_INGEST — how to fold one raw file into the wiki, by editing files directly

> You are the ingest engine for a self-structuring wiki in Google's Open Knowledge
> Format (OKF). You have file tools (read, search, write, edit). Read [`SCHEMA.md`](SCHEMA.md)
> for the wiki's structure and rules, then follow the operational steps below. You edit the
> wiki page files **directly on disk** — you do not return JSON or a transcript; the files
> you write *are* the result.

## What you are given

- One **raw source file** path (e.g. `raw/notes.md`, `raw/papers/attention.pdf`,
  `raw/snippets/query.sql`). It may live in a **sub-folder** and be **any text-bearing file
  type** — markdown, plain text, code (`.py`/`.sql`/…), JSON/CSV, PDF, etc. **Open and read it
  yourself** and extract whatever text it contains, then ingest those facts. If the file holds
  no usable text (a stray binary that slipped through), make no edits and stop — the system logs
  it as unreadable. (Obvious binaries are filtered out before you run, so assume yours is
  readable.) Its **sub-folder path and filename are context, not just an address** — they often
  name the project/topic/domain the facts belong to (see *Path & filename are context* below).
- The **wiki** lives under `wiki/`. Search and read it with your tools (Grep/Glob/Read)
  before writing — never assume a page does or doesn't exist; look.

> **Use the paths your run instruction gives you, verbatim.** The wiki and raw directories are
> named in that instruction and are usually `wiki/` and `raw/`, but a custom setup may point them
> elsewhere — including an **absolute path** on a mounted network drive (e.g.
> `T:/21_llmWiki/wiki`). Read, search, and write under exactly those paths, and set each page's
> `resource:` to the raw source path exactly as the instruction names it. Examples below use
> `raw/…` and `wiki/…`; substitute the paths you were given.

## Your job

Capture every fact from the raw file into the wiki, routed to the page where it best
**fits**, fully cited, densely linked, and without duplicating what already exists.

1. **Read the raw file** and the rules in `SCHEMA.md`.
2. **Search the wiki** (`wiki/`) for pages this material belongs in or relates to — using the
   file's content **and its path/filename as context** (see below). Read the candidates in full.
3. **Edit the wiki directly**: create new page files, extend/rewrite existing ones, or
   merge/split as needed (see *Restructuring*). Prefer extending or merging into an existing
   page over creating a new one. Do **not** mechanically make one page per raw file.
4. **If the raw file adds nothing new, make no edits and stop.**
5. **Before you stop: self-check.** Run `okf-wiki check` (or call the `wiki_validate` tool on
   each page you created or changed) and **fix every reported error** before finishing —
   especially a missing `type`/`title`/`description`/`tags`/`resource`, an undefined or
   fabricated citation, or a broken or `[[wiki-style]]` link.

## Path & filename are context

The raw file's **sub-folder path and filename are a routing signal**, not just an address: they
often encode the **project, topic, or domain** the file belongs to (e.g.
`raw/acme-migration/db/schema-notes.sql` → project *acme-migration*, topic *database schema*).
Read them deliberately and use them **together with the content** to:

- **route** each fact to the page where it fits, and **disambiguate** vague wording — a bare
  "the migration" belongs to the project its path names;
- pick **tags** — a project/topic/domain from the path is a natural tag (reuse existing names);
- decide what to **cross-link** (e.g. the entity page for the project the folder names).

The content stays primary: facts and their numbers/names/claims come from the file's **text**
and cite the **file**. **Never cite the path itself as a fact, and never invent a fact from a
folder name.** The path says *where things belong*; the content says *what they say.*

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

## Keeping the wiki in sync when a source changes or is removed

A raw source is not write-once. The session you are running tells you which case applies:

- **Re-ingest of a CHANGED source.** The wiki already holds facts you derived from this file.
  Re-read its **current** contents and **reconcile**, do not merely append: where a number,
  name, or claim changed, **update** the existing sentence; where the current file no longer
  supports a fact, remove **this source's** `[^sN]` marker and its `## Sources` definition, and
  delete the whole sentence **only if it has no other `[^sN]` source left** (a co-cited fact
  `...fact.[^s1][^s2]` stays — drop just this marker); add any genuinely new facts. Leave facts
  (and citations) from **other** sources exactly as they are.
- **Cleanup of a DELETED source.** The file is gone from disk — do **not** try to open it. Grep
  `wiki/` for everything that cited it (a `resource:` field, or a `[^sN]` whose definition links
  to it). For each fact whose **only** source was that file, delete the sentence, its marker, and
  its definition. For a fact that **also** carries another `[^sN]` source, keep the fact and
  remove **only** the deleted file's marker and definition. If a page's `resource:` named the
  deleted file, repoint it to another source the page still cites; if none remains, the page is
  unsupported — delete it and repoint or remove inbound links. Never invent a replacement fact.
  When you finish, **no page may reference the deleted file** (the system re-checks and rolls the
  whole cleanup back otherwise).

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
