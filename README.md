# **cite**-citadel

> **A fortress of cited knowledge.** An LLM-maintained, fully-cited personal wiki —
> every fact is attested to its source, nothing is invented.

An LLM-maintained personal wiki in Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) (OKF),
with an **MCP server** so an AI can search and read it — a KISS, pure-Python 3.12 take on Andrej
Karpathy's [LLM-Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Drop arbitrary files into `raw/` (markdown, code, JSON/CSV, PDF, PowerPoint/Word/Excel —
`.pptx`/`.docx`/`.xlsx` and legacy `.ppt`/`.doc`/`.xls` — even images, in any sub-folder). One
agentic CLI session per source folds it into a cross-linked OKF wiki under `wiki/` — **routing each
fact to the page it best fits** and splitting/merging pages as the corpus grows, rather than making
one page per file. Office files have their text extracted automatically; images are read *visually*;
a file too big for one context window is folded in over several passes; the same document in two
formats (`report.pdf` + `report.pptx`) is ingested once; and any source that can't be ingested is
recorded (with the reason) in `wiki/sources/index.md`. Every fact is cited back to its `raw/`
source, and the model uses **only** what is in `raw/`. An AI client then queries the synthesized
wiki over MCP instead of re-reading your notes.

The CLI is **`citadel`**; the PyPI package is **`cite-citadel`**. The `wiki/` directory **is** the
database — no SQLite, no vector store. Ingest runs through a **coding-agent CLI you already have**
(`claude`, `copilot`, or `gemini`), so it uses your existing subscription and **needs no API key**.

**Three guarantees that hold as the wiki grows** (full rules in
[`citadel/rules/schema.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/rules/schema.md)):

- **Stays organized** — ingest merges, splits, and deletes pages by fit; it never piles up one page
  per raw file.
- **Links keep working** — merges/renames repoint inbound cross-links; any dangling link fails
  `citadel lint` / `citadel check`.
- **Honest provenance** — raw facts are restated faithfully and cite their source as `[^sN]`. A fact
  the model adds from its own knowledge must be labeled `[^llmN]`, never disguised as a raw citation.

## Install

```bash
uv sync   # creates .venv, installs deps (just mcp + pyyaml) + the citadel CLI
```

Run commands with the **portable** invocation that works the same on Linux/macOS/Windows:

```bash
uv run python -m citadel <subcommand>
```

(`uv run citadel …` is a shorthand but can be blocked by antivirus on Windows; the `python -m` form
and the bundled `.\citadel` wrapper need no `.exe`. Prefer pip? `pip install -e '.[dev]'` works too.)

## Quickstart

Ingest shells out to a coding-agent CLI — install and log into one (default `claude`: run `claude`
once and `/login`). Everything else (`search`, `tags`, `check`, `lint`, `view`, MCP) needs no CLI.

```bash
cp ~/notes/*.md raw/                          # drop in any text-bearing files
uv run python -m citadel ingest               # fold new/changed sources into wiki/
uv run python -m citadel curate               # improve existing pages (--dry-run to preview)
uv run python -m citadel status               # per-source state: ingested / failed / pending / …
uv run python -m citadel search "caffeine"    # ranked keyword search (--tag to filter)
uv run python -m citadel view                 # open the offline, single-file HTML viewer
uv run python -m citadel serve                # run the MCP server (stdio)
```

Two health checks, both offline and CI-friendly:

```bash
uv run python -m citadel check    # strict per-page gate (fields, citations, links); ingest runs it too
uv run python -m citadel lint     # health report (contradictions, orphans, fabricated sources, …)
```

Ingest is **idempotent** — a committed `wiki/.citadel_ingested.json` manifest tracks each source's
hash and the model that imported it — and keeps the wiki in sync when a raw file is **edited,
deleted, or moved**. Configure the backend in `.env` (`citadel init` scaffolds it from the
packaged template, or copy [`citadel/templates/env.example`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/templates/env.example)):

```ini
CITADEL_LLM_CLI=claude        # claude | copilot | gemini
CITADEL_INGEST_MODEL=sonnet   # claude model alias/id
```

[`citadel/templates/env.example`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/templates/env.example) documents every knob — timeouts,
verbose/transcript debugging, an out-of-workspace `wiki/`/`raw/` on a network drive, multiple raw
roots (`CITADEL_RAW_DIRS`, a comma/newline-separated list of directories all walked by ingest),
ingesting a whole git repo as one source, the wiki's target language (`CITADEL_WIKI_LANG`, default
`en`), PDF figure reading (`CITADEL_PDF_MODE=text|images`), and opt-in persona/style capture
(`CITADEL_STYLE_PROFILES`). Re-scans are incremental — an unchanged file is skipped by a stat
quick-check without re-reading its bytes (`citadel ingest --full-rescan` re-hashes everything), and
`citadel ingest --force <paths>` deliberately re-reads already-ingested sources, re-verifying the
wiki's facts under the current rules (it requires explicit paths, so a whole-corpus re-read never
happens by accident).

**`citadel curate` is the wiki's second lifecycle** — where ingest *folds sources in*, curate
*improves the pages that already exist*. It recomputes a work plan from offline detectors every run
(no stored queue — the wiki itself is the database): pages ingested under an older rulebook,
overlong pages to split, unresolved contradictions, orphans, pages leaning on model knowledge
instead of their sources, pages filed in the wrong folder, and citation locators that no longer
point at the right place. Each flagged page cluster gets one agent session over the same
all-or-nothing staging machinery ingest uses, so a bad edit rolls back and the live wiki only ever
gains clean, validated improvements. `citadel curate --dry-run` prints the plan and runs zero
sessions; `--limit`/`--stale-rules` narrow it, `--diff report.md` writes a per-page change report,
and `CITADEL_CURATE_MODEL` lets curate run on a cheaper model than ingest. `citadel status` answers
"what state is my corpus in?" — a read-only per-source table of ingested (with model + rules
version), failed, skipped-duplicate, ignored, and pending sources, computed without re-reading a
byte.

## How it works

Three layers (Karpathy's split; [`citadel/rules/schema.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/rules/schema.md) has the
authoritative rules, which the ingest agent reads — referenced by path — every run):

1. **`raw/`** — immutable sources; ingest reads but never edits them.
2. **`wiki/`** — the LLM-owned OKF bundle: markdown pages with YAML frontmatter, routed **by kind**
   into `concepts/`, `objects/`, `systems/`, `persons/`, `organizations/`, `projects/`,
   `abbreviations/`, `misc/`, densely cross-linked, each fact carrying a citation. The reserved
   `index.md`, `log.md`, and `sources/index.md` are generated, not authored.
3. **[`citadel/rules/`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/rules/README.md)** — the schema/rules layer: `schema.md` (the
   format contract) + `core.md` (agent behavior) + per-lifecycle `tasks/`, per-file-type
   `formats/`, and agent-judged `genres/` briefs. Editing them changes how the wiki is built with
   **no code change**. The rules live in the package so a pip install carries them; the repo-root
   `SCHEMA.md`/`AGENT_INGEST.md` are just pointer stubs.

**Per-fact provenance** is the load-bearing rule. Every factual sentence ends with a GitHub-Flavored
Markdown footnote, defined in a trailing `## Sources` section that links to the originating `raw/`
file:

```markdown
Robusta has about twice the caffeine of Arabica.[^s1]

## Sources

[^s1]: [raw/coffee-guide.md](../../raw/coffee-guide.md) — coffee guide (ingested 2026-06-30)
```

This renders on GitHub, is trivially greppable, and needs zero custom tooling. A claim that can't be
cited is dropped, never invented; conflicting sources produce a `> [!CONTRADICTION]` callout. The
`wiki/` folder also opens **as-is** as an [Obsidian](https://obsidian.md) vault.

## Example corpus

The bundled `raw/` is a deliberately overlapping **coffee + tea** corpus — 10 files in mixed styles
(reference, prose, lab notes, FAQ, brand blog) with facts that repeat, contradict, and hide in one
place, plus one deliberately-false sourced claim. Run `uv run python -m citadel ingest` and watch the
wiki reorganize itself. The `verify-example` skill (`.claude/skills/verify-example/`) ingests it and
grades the result against a ground-truth answer key — an end-to-end test of the three guarantees.

**See the result without running anything.** Browse the generated demo wiki on GitHub at
[`wiki/index.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/wiki/index.md) — GitHub renders the OKF pages natively, so the `[^sN]` citations,
cross-links, glossary, and `> [!CONTRADICTION]` callouts all show inline. For the richer, interactive
view — the cross-link graph, tags, and the cited raw sources embedded — open the **live demo** at
**[markusneusinger.github.io/cite-citadel](https://markusneusinger.github.io/cite-citadel/)**, the
offline single-file viewer regenerated from the wiki on every push.

## MCP server

`citadel serve` exposes eight tools over stdio: `wiki_search`, `wiki_read`, `wiki_index`,
`wiki_sources`, `wiki_tags`, `wiki_validate`, `wiki_lint` (read-only), and `wiki_ingest` (the only
mutating one). Each carries MCP behavior annotations (`readOnlyHint` etc.) so a client can tell the
readers from the one mutating tool. Every MCP tool has a CLI counterpart — `citadel read`,
`citadel index`, `citadel sources`, `citadel lint`, … — so an AI without MCP access can do
everything through the CLI. Wire it into an MCP client (e.g. Claude Desktop):

```json
{
  "mcpServers": {
    "citadel": {
      "command": "uv",
      "args": ["run", "python", "-m", "citadel", "serve"],
      "env": { "CITADEL_LLM_CLI": "claude", "CITADEL_INGEST_MODEL": "sonnet" }
    }
  }
}
```

An AI can then `wiki_index()` to orient, `wiki_search(...)` to find pages, and `wiki_read(...)` to
pull full cited context — answering from your synthesized wiki instead of re-retrieving documents.

## Reference

- [`citadel/rules/README.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/rules/README.md) — index of the rules tree the ingest agent
  follows: [`schema.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/rules/schema.md) (structure, routing, and provenance rules),
  [`core.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/rules/core.md) (operational behavior), plus the `tasks/`, `formats/`, and
  `genres/` briefs.
- [`citadel/templates/env.example`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/templates/env.example) — every configuration knob
  (the `citadel init` `.env` template; the repo-root `.env.example` is a pointer stub).
- [`docs/karpathy-llm-wiki.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/karpathy-llm-wiki.md) ·
  [`docs/okf-reference.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/okf-reference.md) — the pattern and the format.
- `CLAUDE.md` — architecture notes for contributors.
