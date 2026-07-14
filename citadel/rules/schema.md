# schema.md — the wiki's format contract (read every session)

> The schema layer of the three-layer LLM-Wiki pattern (raw sources → wiki → rules). Every agent
> session is pointed at this file **by path** and must follow it exactly, so editing it changes how
> the wiki is built — with no code change. The wiki uses Google's Open Knowledge Format (OKF; see
> `docs/okf-reference.md` in the repository). This file defines what a valid, honest wiki page IS;
> how to *behave* in a session lives in `core.md`.

## Layers

1. **Raw sources** — files under the raw directory (plus the seed docs under `docs/`, when
   present): any text-bearing file type — markdown, plain text, code such as `.py`/`.sql`,
   JSON/CSV, PDF, Office, images — in any sub-folder. You read them; you never edit them.
2. **The wiki** — LLM-maintained OKF pages under the wiki directory: markdown files with YAML
   frontmatter, cross-linked into a knowledge graph. The only thing you edit.
3. **The rules** — this tree (`README.md` in this directory is the index). Your run instruction
   composes them by path.

## OKF types and folder routing

`type` is **required** and decides the page's home. (Per the OKF spec `type` is the only
*spec-mandated* field; this wiki's `check` gate is stricter — see *Page file format*.) The
category set is split **by kind** so every page has exactly one home and even a small model can
route without guessing. Route by the table; when two rows could fit, the **decision procedure**
below resolves it (the first matching rule wins). Each row says what belongs there **and what
does not**, so boundaries don't overlap.

| `type`         | Folder                | Goes here                                                                                                   | Does NOT go here |
| -------------- | --------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------- |
| `Concept`      | `wiki/concepts/`      | A principle, method, phenomenon, or topic — *how/why* knowledge that holds independent of one physical instance (espresso extraction, Ackermann steering geometry, torque). | A specific physical thing → `Object`; a named person/org → those |
| `Object`       | `wiki/objects/`       | A physical or engineered **thing you could touch**: a product, assembly, component, part, material, or device (car, engine, steering, brake caliper, an apple). | A *principle* about it → `Concept`; a software service → `System` |
| `System`       | `wiki/systems/`       | An external **software / IT** system, service, or tool a source connects to or uses: a database, API, queue, SaaS, or library (SAP, PLM, Postgres). Accumulates across sources — one growing page per system. | A physical/mechanical part → `Object`; the vendor company → `Organization` |
| `Person`       | `wiki/persons/`       | A specific, **named human**.                                                                                | An unnamed role ("the operator") → keep as a fact on the topic page |
| `Organization` | `wiki/organizations/` | A specific, **named** company, institution, team, or group. (British spelling `Organisation` is accepted as an alias.) | A product it makes → `Object`/`System` |
| `Project`      | `wiki/projects/`      | A specific, **named initiative/effort** with a goal and a lifecycle.                                        | The ongoing topic behind it → `Concept` |
| `Abbreviation` | `wiki/abbreviations/` | A short form + its expansion (a glossary entry).                                                            | A full term with no acronym → `Concept` |
| anything else  | `wiki/misc/`          | A genuine leftover only: Note, Metric, Runbook, Event, Place. **Last resort, never a shortcut.**            | Anything that fits a row above |
| `Entity` *(legacy)* | `wiki/entities/` | **Deprecated** — the old catch-all for "person, org, project, tool". Still routed so old pages keep working; do **not** produce it. Use `Object`/`Person`/`Organization`/`Project`/`System`. | — |

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
software systems, and physical objects are five different shapes of page, and each has its own
browsable axis. **Hierarchy is expressed with cross-links, not nested folders** — "the steering is
part of the car" means `car`, `steering`, and `steering wheel` are each their own `Object` page,
linked *part of* / *contains*.

### Generated layer (never authored) — the navigation & provenance axis

Beside the content categories sits a second layer the model **never writes** (the operational
off-limits list is in `core.md`): generated navigation/provenance files the system rebuilds each
run, a real browsing axis (by-type, by-tag, by-source, by-date), not pages to route facts into.

- `index.md` and `log.md` — the two OKF-reserved filenames, carrying **no YAML frontmatter**:
  `index.md` is the progressive-disclosure catalog (pages by type, per-page backlinks, a `## Tags`
  section) and `log.md` is the append-only history with `## YYYY-MM-DD` date headings.
- `wiki/sources/index.md` — a frontmatter-free catalog under a `# Sources` heading: one row per
  ingested raw source with the **model that imported it** and links to the pages that cite it —
  the browse-by-source axis ("what do I know, and from which source?"), complementary to the
  by-topic content categories. Surfaced as a `## Sources` section in `index.md`, read by the MCP
  `wiki_sources` tool, and browsable in the HTML viewer.
- `wiki/open-points/index.md` — the derived "what's still open / timeline per point" catalog,
  built mechanically from every `## Open Points` section (see `genres/meeting-minutes.md`).
- `.citadel_viewer.html` — a regenerable, gitignored offline viewer derived purely from the
  bundle, never a source of truth.

The loader skips them all (so `wiki_search` never returns them) and the system rebuilds them
deterministically each run.

## Page file format

Each wiki page is a `.md` file that begins with a YAML frontmatter block, then a GFM body:

```yaml
---
type: Concept                 # REQUIRED — routes the page (the only field OKF itself mandates)
title: Transformer            # REQUIRED by `check` — human label
description: A self-attention architecture.   # REQUIRED by `check` — one line; shown in index.md
resource: raw/attention.md    # REQUIRED by `check` — the PRIMARY raw file this page was derived from
tags: [ml, architecture]      # REQUIRED by `check` — ≥1 lowercase tag
timestamp: 2026-06-21T12:00:00Z   # set automatically on every write — do NOT author
citadel_version: 0.3.0        # set automatically on every write — do NOT author
---
```

- The `check` gate (`citadel check`, MCP `wiki_validate`) treats `title`, `description`, `tags`
  (≥1), and `resource` as required alongside `type` — a missing one is a hard error. Extra fields
  beyond these are allowed and preserved — notably `aliases` (see § Aliases), the alternate names a
  reader might search by.
- **Do NOT write a `timestamp` or `citadel_version` field** — the system stamps both on every
  write (`timestamp` = when the page last changed, `citadel_version` = which cite-citadel release
  wrote it).
- **Never put a second `---` YAML block inside the body.** The body is markdown only.
- **Filename** is the slug of the title: lowercase, runs of non-alphanumeric → `-`, trimmed
  (title `Self-Attention` → `wiki/concepts/self-attention.md`).

## Grounding — raw is primary truth; model-added facts must be labeled

The raw files are the primary source of truth:

- Build each page from the facts in the raw text. Rephrase into clean, well-formed sentences and
  reorganize freely, but **never** change the meaning, the numbers, the names, or the claims of a
  raw fact.
- **Counterfactuals are preserved as stated.** When a source claims something you believe is
  wrong, the wiki records what the *source* says, cited to it — never "correct" a sourced fact
  from model world knowledge (a source-vs-source clash is flagged per *Contradictions*). The
  sourced statement itself stays as stated.
- **Quarantine is MANDATORY for two claim classes.** When a claim (a) conflicts with
  well-established world knowledge, or (b) is a self-promotional / marketing claim the subject
  makes about itself, you MUST write it **attributed to the source's voice** ("the brochure
  states …") AND add a `[^llmN]` note recording the conflict. Never let such a claim become the
  page's own unattributed voice — not in the body, not in the frontmatter `description`, not in
  the page **title**, not in a `## See also` gloss.
  - WRONG: a page titled *Vitamin C as a cold cure* — "Vitamin C cures the common cold.[^s1]"
  - RIGHT: "The brochure claims vitamin C cures the common cold.[^s1] This conflicts with
    established medical consensus.[^llm1]"
  - Self-check before finishing the page: re-read your frontmatter `description` — does it
    assert an attributed claim as fact? The `description` is the wiki's own voice; "A cure for
    the common cold" fails quarantine even when the body is correctly attributed.
- Beyond the mandatory quarantine notes above (which are always allowed — they are the one
  required use of your own knowledge), you **may** add a fact from your own knowledge **only**
  when all three hold: the fact is **essential** to understanding the topic, you are **highly
  confident** it is correct, and it stays **strictly on topic** (no padding, no tangents). When
  in doubt, leave it out.
- A raw-derived claim you cannot tie to a raw file: **drop it.** Never invent provenance or
  disguise a model-supplied fact as a raw citation — label it `[^llmN]`.

## Per-fact provenance — the load-bearing rule

**Every factual sentence cites its source, directly**, using a GitHub-Flavored-Markdown footnote:

- End each fact with a marker: `... self-attention.[^s1]` — `[^sN]` for a fact from a raw file,
  `[^llmN]` (a **separate** numbering) for a model-supplied fact.
- Define every marker exactly once in a trailing `## Sources` section:
  - raw: `[^s1]: [raw/attention.md](../../raw/attention.md) — short note (ingested 2026-06-21)`
    — the link is a **relative** path to the real raw file (a `concepts/` page reaches raw via
    `../../raw/<file>`). A `[^sN]` must point at a raw file that **exists** — a citation to a
    missing file, or a marker used but never defined, is a hard failure. A source path
    containing **spaces** is written in the standard markdown angle form —
    `[my report](<../../raw/my report.pdf>)` — a bare spacey path does not parse.
  - model: `[^llm1]: LLM - model knowledge, not from a raw file (added 2026-06-21)` (no link) —
    surfaced by lint for transparency/audit.
- **Multiple sources, one fact:** when several raw files support the **same** statement, cite
  them **all** behind it — `... fact.[^s1][^s2]` — and define each marker. When a new source
  corroborates a fact already on the page, ADD its marker next to the existing one; never drop or
  replace a marker that is already there.
- A later ingest that adds a fact from a new raw file appends a new `[^sN]` definition and tags
  the new fact — it leaves existing facts and citations intact.

### Locators — pin a fact inside its source

A footnote **definition** may carry a locator after the source link, separated by a comma, that
pins where in the source the cited fact lives:

```
[^s2]: [raw/report.pdf](../../raw/report.pdf), p. 12 — quarterly figures (ingested 2026-07-02)
[^s3]: [raw/report.pdf](../../raw/report.pdf), pp. 3-5 — methodology (ingested 2026-07-02)
[^s4]: [raw/notes.md](../../raw/notes.md), lines 40-52 — pool sizing (ingested 2026-07-02)
[^s5]: [raw/spec.md](../../raw/spec.md), § Error handling — retry contract (ingested 2026-07-02)
```

- **Forms:** `p. 12` / `pp. 3-5` (a paginated source), `line 40` / `lines 40-52` (a text file),
  `§ Heading name` (a heading in the source, copied verbatim).
- **Required** for every citation into a **PDF or Office** source, and for citations into a
  **text source over 200 lines**. Everywhere else, add one whenever the fact's place is
  determinable — a bare file citation with no locator is a last resort, not a default.
- **Self-verify every locator before writing it.** A `§ Heading` locator must copy a heading that
  LITERALLY exists in the raw file — never a paraphrase, a compound "A and B", a parenthetical
  "(the X section)", or a date/diary line that is not a heading. A `lines A-B` range must lie
  within the file's real length — check the line count. Prefer a `lines` range over inventing a
  heading. If your locator does not resolve against the source, fix it or drop to a plain file
  citation.
- **Never a compound locator.** A `§` locator names exactly ONE heading — never several joined
  with commas or "and" (`§ Intro, Methods` or `§ Setup and Teardown` resolves only if that
  literal heading exists). A fact drawn from several passages gets several markers, one per
  place — or one `lines A-B` range that really spans them.
- One definition = one location. Facts from different places in the same file get **separate
  markers**, each defined with its own locator (`[^s2]` and `[^s3]` above both cite
  `report.pdf`). Never stretch one whole-file range over facts from many places:
  - WRONG: one `[^s2]`, `lines 1-114`, reused behind facts from the top and the bottom of the file.
  - RIGHT: `[^s2]`, `lines 12-18`, for the first fact; `[^s3]`, `lines 90-96`, for the second.
- A locator names a place in the **current** raw file; raw files are immutable, so locators are
  stable — and when a source *does* change, the reconcile task re-checks them.
- Reserved for later: appending a short verbatim quote after the locator
  (`, lines 40-52: "…"`). Do **not** use this form yet.

## Contradictions — flag, resolve, don't overwrite

If a source contradicts another source — a different raw file, OR a claim already on an existing
wiki page — do **not** silently overwrite or drop either side. Keep BOTH claims, attributed, in a
callout that names each claim with its **own** source marker (one `[^sN]` per source):

```
> [!CONTRADICTION]
> raw/a.md reports revenue grew 12% [^s1], but raw/b.md reports 9% [^s2].
```

Then, **only if you are highly confident which side is correct**, add a short resolving line that
states which is right and why, labeled as a model-knowledge fact:

```
> Resolution: 12% is the accurate figure; the 9% number predates the restated results.[^llm1]
```

If you are not confident, leave the contradiction flagged without taking sides — never guess.
Every marker used — the `[^sN]` sources and the `[^llmN]` resolution — must be defined in
`## Sources`. (Multiple sources that *agree* on a fact are simply cited together behind it:
`... fact.[^s1][^s2]`. Two *dated* values of a changeable attribute are usually an evolution, not
a contradiction — keep BOTH, the superseded value as a dated `## Change Log` line, never dropped:
see `genres/meeting-minutes.md` and `tasks/reconcile.md`.)

**Cross-source sweep — run it before finalizing a page.** Compare every quantitative or
categorical claim you are writing against the value stated for the SAME attribute elsewhere — in
the other raw sources and on pages already in the wiki (search for the attribute; never rely on
memory). A brand's or house's claim about itself (a temperature, a percentage, a
"lowest/best/only" superlative) that diverges from the corpus's reference facts IS a
contradiction even though the two sources never cite each other. Co-locate both sides in ONE
callout on the page a reader would land on — never one side on each of two pages.

## Links — the knowledge graph

- Link pages to each other with **standard relative markdown links** whose target is the other
  page's file — e.g. from `concepts/transformer.md`:
  `[Andrej Karpathy](../persons/andrej-karpathy.md)` — using **forward slashes only**. Never
  `[[wiki-style]]` links. The file path is the page's identity; the links form the knowledge
  graph.
- **`## See also`.** End each page with a short `## See also` section (after the body, **before**
  `## Sources`) of relative links to the most closely related pages.
- **Backlinks are free.** The generated `index.md` lists, per page, who references it
  (`↳ referenced by: …`), computed from the real link graph — every page is reachable from the
  pages that mention it.
- Broken links are **tolerated** by readers (a link may point at a page not written yet), but a
  restructure never *creates* one (see `core.md` § Restructuring); `citadel lint` fails on any
  that remain, and also **suggests** links — it flags a page that mentions another page's title
  in prose without linking it.

## Tags — browse by topic

Give each page 2–5 lowercase `tags` from a shared vocabulary (reuse existing tag names where they
fit). Tags are the OKF-native `tags` frontmatter field and a second navigation axis: they boost
search ranking, power `citadel tags` / `search --tag` / the MCP `wiki_tags` tool, and are
surfaced as a `## Tags` section in the generated `index.md`.

## Aliases — the other names a reader searches by

`aliases` is a frontmatter list of **alternate names a reader might search by** — a lay synonym, an
everyday word, a nickname, or a former name. It is not only for abbreviations (which list their
short/long forms here — see below): search weights `aliases` highly (just below the title), so an
alias lets a paraphrased query reach the page even by a word the title never uses — a currency page
titled *Skell* becomes findable by "money"; a *Multi-Factor Authentication* page by "two-factor".

Add up to ~4 aliases to a page when a **genuinely common, unambiguous** everyday term would be
searched — e.g. `aliases: [money, cash]` on the currency page, `aliases: [two-factor, 2FA]` on the
MFA page, a widely-used nickname on a person page. Be conservative: only real, well-known synonyms,
never a speculative or invented one (a wrong alias misroutes searches). Most pages need none — reach
for aliases where the subject has an obvious everyday name the title omits.

## Abbreviations — capture short + long so either form is found

Domain sources (slides, notes, code) are full of abbreviations a non-expert can't decode. Make
each one self-documenting so **both** the short and long form are captured and a search for
**either** finds it:

- **Expand on first use.** The first time a page uses an abbreviation, write it as
  `Full Form (ABBR)` — e.g. `total dissolved solids (TDS)` — then use `ABBR` afterwards. Both
  forms now sit in the page text, findable either way.
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
  `## Abbreviations` glossary table — never hand-write a list.
- **Where the expansion comes from is the normal grounding rule.** If a raw source spells it out,
  cite it `[^sN]`. If it is a well-known standard abbreviation you are highly confident about,
  you may supply the expansion as a model fact `[^llmN]`. **If it is house-/project-internal and
  nothing defines it, do not guess** — leave the bare abbreviation in place; a wrong expansion is
  worse than a missing one. `citadel lint` lists abbreviations used across pages but never
  defined, so a human can fill the gaps.

## Wiki language

The wiki is written in ONE **target language**, named in your run instruction (default English) —
**regardless of the languages of the raw sources**, including a mixed-language corpus:

- All wiki **prose, page titles, headings, descriptions, and tags** are in the target language.
- **Verbatim quotes stay in their original language.** A translated "quote" is no longer verbatim
  and can no longer be matched back to the raw file — quote the original, and put a translation
  beside it if the reader needs one.
- **Proper nouns are never translated** — names of people, organizations, products, places — and
  established technical terms keep their source form.
- Where the exact original **phrasing matters** (a term of art, a contract wording, an ambiguous
  claim), give the original-language wording alongside the translation, cited as usual.

## Opinions & style

- An **opinion, stance, preference, or judgment found in a source is never a world fact.** Write
  it attributed — "X argues …", "Y prefers …", "Z decided …" — cited `[^sN]` like any fact. What
  the wiki records is that the person holds (or held) the position, not that the position is
  true. Never let an attributed position migrate into unattributed prose during a merge, split,
  or reconcile.
- **Style profiles** — observations about how a person writes or speaks — live on that person's
  `persons/` page, and are captured **only when your run instruction says style profiling is
  enabled** (the rules live in `genres/first-person.md`). Otherwise capture facts and
  load-bearing attributed positions only — no style sections.
