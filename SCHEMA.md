# SCHEMA — the wiki's structure and maintenance rules

> This file is the **schema/config layer** of the three-layer LLM-Wiki pattern
> (see [`docs/karpathy-llm-wiki.md`](docs/karpathy-llm-wiki.md)). It is read by humans
> **and injected verbatim into the ingest model's system prompt**, so editing this file
> changes how the wiki is built — with no code change. The wiki uses Google's
> [Open Knowledge Format](docs/okf-reference.md).

## Layers

1. **Raw sources** — files the model reads but never edits: anything under `raw/`
   (any text-bearing file type — markdown, plain text, code such as `.py`/`.sql`, JSON/CSV,
   PDF, … — in any sub-folder) and the seed docs in `docs/`. Ingest tries to extract text from
   **every** file; one with no readable text (a binary blob) is skipped and logged as
   unreadable. The wiki tracks each source by content hash, so a change to `raw/` propagates:
   a source that was **edited** is re-ingested in *reconcile* mode (the model updates or removes
   the now-stale facts it derived from it, not just appends); a source that was **deleted** is
   detected on a full run and its facts/citations are stripped from the wiki by a cleanup session
   (kept only where another source still supports the fact); and a source that was only
   **moved/reorganized** (same bytes, new path) is recognized and **not** re-ingested — its wiki
   `resource`/citation references are repointed automatically (a move is not a deletion).
2. **The wiki** — LLM-generated OKF pages under `wiki/`: a directory of markdown files
   with YAML frontmatter, cross-linked into a knowledge graph.
3. **The schema** — this file.

## OKF types and folder routing

`type` is **required** and decides the page's home. (Per the OKF spec `type` is the only
*spec-mandated* field; this wiki's `check` gate is stricter and additionally requires `title`,
`description`, `tags`, and `resource` — see *Frontmatter fields* below.) The category set is split
**by kind** so every page has exactly one home and even a small model can route without guessing.
Route by the table; when two rows could fit, the **decision procedure** below resolves it (the
first matching rule wins). Each row says what belongs there **and what does not**, so boundaries
don't overlap.

| `type`         | Folder                | Goes here                                                                                                   | Does NOT go here |
| -------------- | --------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------- |
| `Concept`      | `wiki/concepts/`      | A principle, method, phenomenon, or topic — *how/why* knowledge that holds independent of one physical instance (espresso extraction, Ackermann steering geometry, torque). | A specific physical thing → `Object`; a named person/org → those |
| `Object`       | `wiki/objects/`       | A physical or engineered **thing you could touch**: a product, assembly, component, part, material, or device (car, engine, steering, brake caliper, an apple). | A *principle* about it → `Concept`; a software service → `System` |
| `System`       | `wiki/systems/`       | An external **software / IT** system, service, or tool a source connects to or uses: a database, API, queue, SaaS, or library (SAP, PLM, Postgres). Accumulates across sources. | A physical/mechanical part → `Object`; the vendor company → `Organization` |
| `Person`       | `wiki/persons/`       | A specific, **named human**.                                                                                | An unnamed role ("the operator") → keep as a fact on the topic page |
| `Organization` | `wiki/organizations/` | A specific, **named** company, institution, team, or group. (British spelling `Organisation` is accepted as an alias.) | A product it makes → `Object`/`System` |
| `Project`      | `wiki/projects/`      | A specific, **named initiative/effort** with a goal and a lifecycle.                                        | The ongoing topic behind it → `Concept` |
| `Abbreviation` | `wiki/abbreviations/` | A short form + its expansion (a glossary entry).                                                            | A full term with no acronym → `Concept` |
| anything else  | `wiki/misc/`          | A genuine leftover only: Note, Metric, Runbook, Event, Place. **Last resort, never a shortcut.**            | Anything that fits a row above |
| `Entity` *(legacy)* | `wiki/entities/` | **Deprecated** — the old catch-all for "person, org, project, tool". Still routed so old pages keep working; do **not** produce it. Use `Object`/`Person`/`Organization`/`Project`/`System`. | — |
| `index.md` / `log.md` / `sources/index.md` | (generated) | OKF reserved navigation/provenance files — **never authored by ingest** (see below). | — |

**Decision procedure — ask in order; the first rule that matches wins:**

1. A short form / acronym with an expansion? → **Abbreviation**
2. A specific named human? → **Person**
3. A specific named organization (company, institution, team)? → **Organization**
4. A specific named initiative/effort with a goal and lifecycle? → **Project**
5. An external software/IT system or service the source connects to or uses (DB, API, queue, SaaS, library)? → **System**
6. A physical/engineered thing you could **touch** (product, assembly, component, part, material, device)? → **Object**
7. A principle, method, phenomenon, or topic (not one specific named thing)? → **Concept**
8. None of the above? → **misc**

This split-by-kind is what fixes the old `Entity` overload: people, organizations, projects,
software systems, and physical objects are five different shapes of page, and each now has its own
browsable axis. **Hierarchy is expressed with cross-links, not nested folders** — "the steering is
part of the car" means `car`, `steering`, and `steering wheel` are each their own `Object` page,
linked *part of* / *contains*.

### Generated layer (never authored) — the provenance & navigation axis

Beside the content categories above sits a second layer the model **never writes**: the generated
navigation/provenance files. They are a real, separate browsing axis (by-type, by-tag, by-source,
by-date), not pages to route facts into — the loader skips them all and the system rebuilds them
each run. The ingest agent must never create or edit them.

`index.md` and `log.md` are the two OKF-reserved filenames and are **generated**, not written
by the model. Per OKF they carry **no YAML frontmatter**: `index.md` is the progressive-
disclosure catalog (pages by type, backlinks, a `## Tags` section) and `log.md` is the
append-only history with `## YYYY-MM-DD` date headings. The loader skips both. (`citadel view`
also writes a `.citadel_viewer.html` — a regenerable, gitignored offline viewer derived purely from
the bundle, not a source of truth; the loader skips it too.)

`wiki/sources/index.md` is also **generated** (a frontmatter-free catalog under a `# Sources`
heading, linked from `index.md`): one row per ingested raw source with the **model that imported
it** (from the manifest) and links to the pages that cite it. It is the **browse-by-source axis**
— the answer to "what do I know, and from which source?" — complementary to the by-topic axis of
the content categories. Like every `*/index.md` it is skipped by the loader; the system rebuilds it
deterministically each run, so the **ingest agent/model must never author or edit it** (only the
system writes it). The loader skips it, so `wiki_search` never returns it; instead it is surfaced
as a `## Sources` section in the generated `index.md` and read directly by the MCP `wiki_sources`
tool (and browsable in the HTML viewer).

## Frontmatter fields

```yaml
---
type: Concept                 # REQUIRED — routes the page (the only field OKF itself mandates)
title: Transformer            # REQUIRED by `check` — human label
description: A self-attention architecture.   # REQUIRED by `check` — one line; shown in index.md
resource: raw/attention.md    # REQUIRED by `check` — the PRIMARY raw file this page was derived from
tags: [ml, architecture]      # REQUIRED by `check` — ≥1 lowercase tag
timestamp: 2026-06-21T12:00:00Z   # set automatically on every write — do NOT author
---
```

`type` is all the OKF *spec* requires, but this wiki's `check` gate (`citadel check`, MCP
`wiki_validate`) treats `title`, `description`, `tags` (≥1), and `resource` as required too — a
missing one is a hard error. Extra fields beyond these are allowed and preserved.

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

## Source path & filename — routing context

A raw source's **location and name are signal, not just an address.** The sub-folders under
`raw/` and the filename often encode which **project, topic, or domain** a file belongs to —
e.g. `raw/acme-migration/db/schema-notes.sql` is about the *acme-migration* project and its
*database schema*. Read the path deliberately and use it, **together with the file's content**,
to:

- **Route** each fact to the page (or section) it best fits, and **disambiguate** vague wording
  — a note that just says "the migration" belongs to the project its path names.
- Choose **tags**: a project/topic/domain from the path is a natural tag (reuse existing names).
- Decide what to **cross-link** (e.g. link the project's entity page named by the folder).

The content stays primary. Facts, numbers, names, and claims come from the file's **text** and
cite the **file** — never cite the path itself as a fact, and never invent a fact from a folder
name alone. The path tells you **where things belong**; the content is **what they say.**

## Code & structured sources — capture the essence, not the structure

A code, config, or data file (`.py`, `.sql`, `.tsx`, `.json`, a Dockerfile, …) is ingested for
what it **means and does**, not for how it is built. Treat it like documentation you would write
*about* the code — never a transcription of it. The wiki must **not** fill up with one note per
function, component, or type; that is exactly the noise this rule exists to prevent.

**Capture** (each as a normal cited fact):

- **Purpose** — what problem this file/module/script solves and why it exists.
- **Behavior / process** — the workflow it implements: the meaningful steps, inputs → outputs,
  the pipeline or state changes a reader needs to follow it.
- **External systems and how they are reached** — which database, API, queue, bucket, or service
  it touches, and *how*: the table/endpoint/topic names, the access method (driver/ORM/HTTP call),
  the auth mechanism, the env vars / config keys it depends on. These are the reference-worthy
  operational facts worth keeping.
- **Notable decisions and domain rules** — non-obvious algorithms, the *why* behind a choice,
  invariants, limits/units, and business rules encoded in the code.

**Ignore** (this is structure, not knowledge):

- Import lists and boilerplate; function/class/component signatures and prop/type/interface
  definitions *as such*; how a UI component is wired or laid out; styling/markup; getters/setters.
- Test scaffolding, generated code, lockfiles.
- Pasting code verbatim. Quote at most a short identifier (a table name, an env var, a flag) when
  it **is** the fact; never reproduce a block of code as a "fact".

**Litmus test:** *"Would this still be true and useful if the code were rewritten in another
language or framework?"* If yes, capture it. If it only describes how this particular file is
structured, skip it.

For code, a "fact" is therefore a faithful description of intent or behavior **derived from and
cited to the file** — a slightly more interpretive mode than restating a prose sentence, but the
grounding rule still holds: it must follow from the file's contents (never from assumption) and it
carries a `[^sN]` citation like any other fact. Route these facts into a page about the
**module / subsystem / project** (use the path as context, above) — not one page per source file.

## Git repositories — one source, captured by use

A sub-folder under `raw/` that is a **git repository** (it holds a `.git/`) — or carries an opt-in
empty `.citadelsource` marker for a git-less snapshot — is ingested as **one source**, not file by
file. The system builds a deterministic **digest** of the repo's high-signal files (README,
dependency manifests, the connection/config layer, the data-transform/pipeline core, entry points;
`.gitignore` honored, lockfiles / `node_modules` / build output dropped, capped to a budget) and
the agent reads that digest. The repo folder is the **source of record**: `resource:` is the
folder path (e.g. `raw/acme-etl`) and `[^sN]` citations link to it.

Assume **~99% of the code is irrelevant** to a knowledge wiki. For a repo, capture only:

- **How to use it** — how to run/call it, how to connect to the API/service/DB, the key command(s)
  to transform the data, the env vars / config it needs.
- **What it does** — its purpose.
- **How it does it** — the data flow / pipeline steps at a readable level (not line by line, not
  one note per function).
- **What comes out** — the output / result form.

A **short verbatim code excerpt** (a few lines) is allowed *here* when the code itself **is** the
fact — a connection/auth call, the key transform command, an env var, a SQL query — cited like any
fact. This is the one place the "never paste a code block" rule above is relaxed; keep it short and
usage-oriented, never a transcription.

For every **external system** the repo touches — a database, API, queue, service, or tool (SAP,
PLM, Postgres) — create or extend a `type: System` page (see the routing table) describing the
system and how the repo uses it (tables/endpoints, access method, auth), and link the repo's pages
to it. These pages **accumulate** across sources.

A repo is versioned by its **HEAD commit**: a later commit re-ingests only the changed files
(a `git diff` reconcile), a renamed folder repoints its citations, and a deleted folder reconciles
its citations out — exactly like a single raw file changing, moving, or being removed.

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
  `citadel lint` fails on any that remain. Lint also **suggests** links — it flags a page that
  mentions another page's title in prose without linking it.

## Tags — browse by topic

Give each page 2–5 lowercase `tags` from a shared vocabulary (reuse existing tag names where
they fit). Tags are the OKF-native `tags` frontmatter field and a second navigation axis: they
boost search ranking, power `citadel tags` / `search --tag` / the MCP `wiki_tags` tool, and
are surfaced as a `## Tags` section in the generated `index.md`.

## Abbreviations — capture short + long so either form is found

Domain sources (slides, notes, code) are full of abbreviations a non-expert can't decode.
Make each one self-documenting so **both** the short and long form are captured and a search
for **either** finds it:

- **Expand on first use.** The first time a page uses an abbreviation, write it as
  `Full Form (ABBR)` — e.g. `total dissolved solids (TDS)` — then use `ABBR` afterwards. Both
  forms now sit in the page text, so a search for either matches even without a dedicated entry.
- **Give a recurring abbreviation its own page**, `type: Abbreviation`, routed to
  `wiki/abbreviations/`. Title it `ABBR — Full Form` so the title (the highest-weighted search
  field) carries both forms, and list the variants under `aliases`:

  ```yaml
  type: Abbreviation
  title: TDS — Total Dissolved Solids
  description: Brew-strength measure — the dissolved coffee solids in the cup.
  aliases: [TDS, Total Dissolved Solids]
  tags: [water, measurement]
  resource: raw/water-for-coffee.md
  ```

  Keep the body to a sentence or two defining the term, each cited like any other fact, and
  cross-link the pages that use it. The generated `index.md` collects every such page into an
  `## Abbreviations` table — the glossary forms itself, with no hand-maintained list to drift.
- **Where the expansion comes from is the normal grounding rule.** If a raw source spells it
  out, cite it `[^sN]`. If it is a well-known standard abbreviation you are highly confident
  about, you may supply the expansion as a model fact `[^llmN]`. **If it is house-/project-
  internal and nothing defines it, do not guess** — leave the bare abbreviation in place; a
  wrong expansion is worse than a missing one. `citadel lint` lists abbreviations used across
  pages but never defined, so a human can fill those gaps.

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
`citadel lint` / `citadel check`.

## Workflows

- **Ingest** — for each new/changed `raw/` file, an agentic CLI (one session per file) reads
  the raw file, searches the existing wiki, and **edits the wiki page files directly** —
  routing facts to the best page and **merging / splitting / restructuring** rather than
  duplicating. Use only facts from the raw file. Cite every fact. Flag contradictions. A
  **changed** source is re-ingested in reconcile mode (update/remove its stale facts, not just
  append); a **deleted** source triggers a cleanup session that removes the facts/citations that
  depended on it (all-or-nothing: rolled back unless nothing references it afterwards). See
  [`AGENT_INGEST.md`](AGENT_INGEST.md) for the operational rules. After the session, the system
  diffs the wiki, re-validates and re-stamps every changed page, repoints renamed-page links,
  and rebuilds the indexes.
- **Query** — an AI searches the wiki via the MCP server (`wiki_search`, `wiki_read`,
  `wiki_index`, `wiki_sources`, `wiki_tags`) and synthesizes cited answers from the pages — it does not re-read
  `raw/`.
- **Check** — the strict per-page gate (`citadel check`, MCP `wiki_validate`): required
  fields (type/title/description/tags/resource), honest citations, and relative non-broken
  links (no `[[wiki-links]]`). The ingest agent runs it on its own edits before finishing, and
  ingest re-runs it as a hard gate so a forgotten field fails the run.
- **Lint** — a periodic health check (`citadel lint`) surfaces contradictions, orphaned
  pages, facts missing citations, broken cross-links, pages missing `type`, stale pages,
  **fabricated sources** (a fact citing a `raw/` file that does not exist), **undefined
  abbreviations** (a short form used across pages but never given an entry or an inline
  expansion), and `[[wiki-style]]` links.
