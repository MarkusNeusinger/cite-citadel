# **cite**-citadel

> **A fortress of cited knowledge.** An LLM-maintained, fully-cited personal wiki —
> every fact is attested to its source, nothing is invented.

An LLM-maintained personal wiki in Google's [Open Knowledge Format](docs/okf-reference.md) (OKF),
with an **MCP server** so an AI can search and read it — a KISS, pure-Python 3.12 take on Andrej
Karpathy's [LLM-Wiki pattern](docs/karpathy-llm-wiki.md).

Drop arbitrary text-bearing files into `raw/` (markdown, code, JSON/CSV, PDF, `.pptx`/`.docx`, … in
any sub-folder). One agentic CLI session per source folds it into a cross-linked OKF wiki under
`wiki/` — **routing each fact to the page it best fits** and splitting/merging pages as the corpus
grows, rather than making one page per file. Every fact is cited back to its `raw/` source, and the
model uses **only** what is in `raw/`. An AI client then queries the synthesized wiki over MCP
instead of re-reading your notes.

The CLI is **`citadel`**; the PyPI package is **`cite-citadel`**. The `wiki/` directory **is** the
database — no SQLite, no vector store. Ingest runs through a **coding-agent CLI you already have**
(`claude`, `copilot`, or `gemini`), so it uses your existing subscription and **needs no API key**.

**Three guarantees that hold as the wiki grows** (full rules in [`SCHEMA.md`](SCHEMA.md)):

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
deleted, or moved**. Configure the backend in `.env` (copy [`.env.example`](.env.example)):

```ini
CITADEL_LLM_CLI=claude        # claude | copilot | gemini
CITADEL_INGEST_MODEL=sonnet   # claude model alias/id
```

[`.env.example`](.env.example) documents every knob — timeouts, verbose/transcript debugging, an
out-of-repo `wiki/`/`raw/` on a network drive, and ingesting a whole git repo as one source.

## How it works

Three layers (Karpathy's split; [`SCHEMA.md`](SCHEMA.md) has the authoritative rules and is injected
verbatim into the ingest prompt):

1. **`raw/`** — immutable sources; ingest reads but never edits them.
2. **`wiki/`** — the LLM-owned OKF bundle: markdown pages with YAML frontmatter, routed **by kind**
   into `concepts/`, `objects/`, `systems/`, `persons/`, `organizations/`, `projects/`,
   `abbreviations/`, `misc/`, densely cross-linked, each fact carrying a citation. The reserved
   `index.md`, `log.md`, and `sources/index.md` are generated, not authored.
3. **[`SCHEMA.md`](SCHEMA.md)** — the schema/config layer. Editing it changes how the wiki is built
   with **no code change**.

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

## MCP server

`citadel serve` exposes seven tools over stdio: `wiki_search`, `wiki_read`, `wiki_index`,
`wiki_sources`, `wiki_tags`, `wiki_validate` (read-only), and `wiki_ingest` (the only mutating one).
Wire it into an MCP client (e.g. Claude Desktop):

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

- [`SCHEMA.md`](SCHEMA.md) — authoritative structure, routing, and provenance rules.
- [`AGENT_INGEST.md`](AGENT_INGEST.md) — the operational rules the ingest agent follows.
- [`.env.example`](.env.example) — every configuration knob.
- [`docs/karpathy-llm-wiki.md`](docs/karpathy-llm-wiki.md) ·
  [`docs/okf-reference.md`](docs/okf-reference.md) — the pattern and the format.
- `CLAUDE.md` — architecture notes for contributors.
