# okf-llm-wiki-mcp

An **LLM-maintained personal wiki** in Google's [Open Knowledge Format](docs/okf-reference.md),
with an **MCP server** so an AI can search and read it.

This is a KISS, pure-Python (3.12) implementation of Andrej Karpathy's
[LLM-Wiki pattern](docs/karpathy-llm-wiki.md): you drop arbitrary markdown into `raw/`, and
one LLM call per file folds each source into a cross-linked OKF wiki under `wiki/`. Every fact
is cited back to the raw file it came from. An AI client then queries the synthesized wiki over
the Model Context Protocol instead of re-reading your raw notes.

Ingest runs through a **coding-agent CLI you already have** (`claude`, `copilot`, or `gemini`)
— so it uses your existing subscription (e.g. a Claude Max plan) and **needs no API key**.

The `wiki/` directory **is** the database — there is no SQLite, no vector store, no second
source of truth to keep in sync.

## The three layers

This project mirrors Karpathy's three-layer split (see [`SCHEMA.md`](SCHEMA.md) for the full,
authoritative rules — that file is also injected verbatim into the ingest model's prompt):

1. **`raw/`** — immutable sources. You drop arbitrary `.md` here; ingest reads them but never
   edits them. The seed articles in `docs/` are also ingestable on demand.
2. **`wiki/`** — the LLM-owned OKF bundle: markdown pages with YAML frontmatter, routed into
   `concepts/`, `entities/`, and `misc/`, cross-linked with relative links, each fact carrying
   a footnote citation to its `raw/` source. Mechanically-regenerated `index.md` catalogs and
   an append-only `log.md` live alongside.
3. **[`SCHEMA.md`](SCHEMA.md)** — the schema/config layer: allowed types, folder routing,
   the per-fact provenance grammar, cross-linking and contradiction conventions. Editing it
   changes how the wiki is built with **no code change**.

## Install (uv)

```bash
uv sync                       # creates .venv, installs deps + the dev group + okf-wiki
```

Runtime dependencies are just `mcp` and `pyyaml` (no LLM SDK). Then either activate the venv
(`source .venv/bin/activate`) or prefix commands with `uv run` (e.g. `uv run okf-wiki ...`).

> Prefer pip? `python -m venv .venv && .venv/bin/pip install -e '.[dev]'` works too.

## Configure — pick your CLI (no API key)

Ingest shells out to a coding-agent CLI on your machine. Make sure it is installed and logged
in; the read-only tools (`search`, `read`, `index`) and `lint` need **no** CLI at all.

```bash
# default backend is the Claude Code CLI:
claude            # run once and /login if you haven't (uses your Claude subscription)
```

Defaults work out of the box. To tune, copy `.env.example` to `.env` (auto-loaded, gitignored):

```ini
OKF_LLM_CLI=claude        # claude | copilot | gemini   (default: claude)
OKF_INGEST_MODEL=sonnet   # claude model alias/id; opus or haiku also work
```

`copilot`/`gemini` use their own default model. See `.env.example` for binary-path overrides,
the per-call timeout, and path overrides.

## Use

**Ingest** — drop one or more arbitrary markdown files into `raw/`, then fold them in:

```bash
cp ~/notes/q3-planning.md raw/
uv run okf-wiki ingest                      # ingest all new/changed files in raw/
uv run okf-wiki ingest docs/karpathy-llm-wiki.md   # or bootstrap from a specific file
```

Ingest is **idempotent**: a committed manifest at `wiki/.okf_ingested.json` maps each source's
repo-relative path to a sha256, so re-running with no new or changed files makes **zero** LLM
calls. Edit a raw file (new sha) and it is re-ingested, patching the existing pages. Exactly
one LLM call per source — no agent loop.

**Search** the synthesized wiki:

```bash
uv run okf-wiki search "caffeine content"   # ranked keyword hits across all pages
```

**Lint** — a pure, offline health check (contradictions, orphaned pages, facts missing
citations, broken cross-links, pages missing `type`, stale pages). Exit code is non-zero when
the wiki is unhealthy, so it drops cleanly into CI:

```bash
uv run okf-wiki lint
```

## Per-fact provenance

Provenance is the load-bearing rule. Every factual sentence in a wiki page ends with a
GitHub-Flavored-Markdown footnote marker (`[^s1]`), defined in a trailing `## Sources` section
that links **relatively** to the originating `raw/` file:

```markdown
Robusta has about twice the caffeine of Arabica.[^s1]

## Sources

[^s1]: [raw/caffeine.md](../../raw/caffeine.md) — caffeine notes (ingested 2026-06-22)
```

This renders on GitHub for free, is trivially greppable (`grep -rn '\[\^s' wiki/`), and needs
zero custom tooling. The page's frontmatter `resource:` names the primary raw source. Claims
that cannot be cited to a raw file are dropped, not invented. Conflicting sources produce a
`> [!CONTRADICTION]` callout rather than a silent overwrite.

## MCP server

Expose the wiki to an AI client over stdio:

```bash
uv run okf-wiki serve        # or: uv run python -m okf_wiki.server
```

It serves four tools: `wiki_search`, `wiki_read`, `wiki_index` (read-only), and `wiki_ingest`
(the only mutating tool, routed through the same path-safe ingest pipeline).

Wire it into an MCP client (e.g. Claude Desktop's `claude_desktop_config.json`). No API key in
the env — ingest uses the CLI's own login:

```json
{
  "mcpServers": {
    "okf-wiki": {
      "command": "okf-wiki",
      "args": ["serve"],
      "env": { "OKF_LLM_CLI": "claude", "OKF_INGEST_MODEL": "sonnet" }
    }
  }
}
```

Now an AI can `wiki_index()` to orient, `wiki_search(...)` to find pages, and `wiki_read(...)`
to pull full cited context — answering from your synthesized wiki instead of re-retrieving raw
documents.

## Reference

- [`SCHEMA.md`](SCHEMA.md) — the authoritative structure and maintenance rules.
- [`docs/karpathy-llm-wiki.md`](docs/karpathy-llm-wiki.md) — the LLM-Wiki pattern this implements.
- [`docs/okf-reference.md`](docs/okf-reference.md) — Google's Open Knowledge Format.
