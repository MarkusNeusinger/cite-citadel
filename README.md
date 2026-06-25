# okf-llm-wiki-mcp

An **LLM-maintained personal wiki** in Google's [Open Knowledge Format](docs/okf-reference.md),
with an **MCP server** so an AI can search and read it.

This is a KISS, pure-Python (3.12) implementation of Andrej Karpathy's
[LLM-Wiki pattern](docs/karpathy-llm-wiki.md): you drop arbitrary text-bearing files into `raw/`
(markdown, plain text, code, JSON/CSV, PDF, … — any sub-folder), and
one agentic CLI session per file folds each source into a cross-linked OKF wiki under `wiki/`.
Instead of making one page per file, ingest **routes each fact to the page it best fits and restructures**
(splits / merges) existing pages as the wiki grows. Every fact is cited back to the raw file it
came from — and the model uses **only** what is in `raw/`, never its own knowledge. An AI client
then queries the synthesized wiki over the Model Context Protocol instead of re-reading your raw
notes.

**Three guarantees that hold as the wiki grows** (see [`SCHEMA.md`](SCHEMA.md)):

- **It stays organized.** Ingest merges overlapping notes, splits pages that grow too big, and
  deletes pages whose content moved elsewhere — it does not pile up one page per raw file.
- **Links keep working.** When a page is merged or renamed, the agent repoints the inbound
  cross-links to the survivor (and the system mechanically repoints a pure rename as a safety
  net); any dangling link fails `okf-wiki lint` / `okf-wiki check`.
- **Honest provenance.** Raw facts are restated faithfully (same meaning/numbers) and cite
  their `raw/` file as `[^sN]`. The model **may** add a fact from its own knowledge only when
  it is essential, high-confidence, and on-topic — and must label it `[^llmN]` (source: `LLM`),
  never disguised as a raw citation. A `[^sN]` citing a missing raw file fails `okf-wiki lint`;
  `[^llmN]` facts are surfaced by lint for audit.

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
   a footnote citation to its `raw/` source. The two OKF-reserved files are generated, not
   authored, and per OKF carry **no frontmatter**: `index.md` (catalog + backlinks + a `## Tags`
   section) and an append-only `log.md` with `## YYYY-MM-DD` headings.
3. **[`SCHEMA.md`](SCHEMA.md)** — the schema/config layer: allowed types, folder routing,
   the per-fact provenance grammar, cross-linking and contradiction conventions. Editing it
   changes how the wiki is built with **no code change**.

## Install (uv)

```bash
uv sync                       # creates .venv, installs deps + the dev group + okf-wiki
```

Runtime dependencies are just `mcp` and `pyyaml` (no LLM SDK). Then either activate the venv
(`source .venv/bin/activate`) or prefix commands with `uv run`.

This README uses the **portable** invocation that works identically on Linux, macOS, and Windows:

```bash
uv run python -m okf_wiki <subcommand>      # e.g. uv run python -m okf_wiki ingest
```

`uv run okf-wiki <subcommand>` is a shorthand, but **on Windows it often fails** with
`error: failed to spawn okf-wiki: program not found` — uv's generated `okf-wiki.exe` launcher
stub gets quarantined by antivirus (e.g. Windows Defender, `os error 5`) and regenerated on every
`uv sync`. Two AV-proof alternatives that need **no `.exe`**:

```powershell
uv run python -m okf_wiki <subcommand>   # works everywhere (Linux/macOS/Windows)
.\okf-wiki <subcommand>                  # bundled wrapper (PowerShell/cmd) -> python -m
```

The bundled `okf-wiki.cmd` / `okf-wiki.ps1` are thin wrappers that just call
`uv run python -m okf_wiki`, so there is no executable for AV to remove. (To get the
`uv run okf-wiki` shorthand working instead, add the venv's `Scripts\` folder to your AV
exclusions: `Add-MpPreference -ExclusionPath "<repo>\.venv\Scripts"`.)

> Prefer pip? `python -m venv .venv && .venv/bin/pip install -e '.[dev]'` works too.

## Configure — pick your CLI (no API key)

Ingest shells out to a coding-agent CLI on your machine. Make sure it is installed and logged
in; everything else — `search`, `tags`, `lint`, `view`, and the read-only MCP tools — needs
**no** CLI at all.

```bash
# default backend is the Claude Code CLI:
claude            # run once and /login if you haven't (uses your Claude subscription)
```

Defaults work out of the box. To tune, copy `.env.example` to `.env` (auto-loaded, gitignored):

```ini
OKF_LLM_CLI=claude        # claude | copilot | gemini   (default: claude)
OKF_INGEST_MODEL=sonnet   # claude model alias/id; opus or haiku also work
```

Ingest runs the CLI **agentically**: it is pointed at the repo and edits the wiki page files
itself (reads the raw file, searches the wiki, writes/merges/splits pages), so each backend runs
with autonomous file tools — `claude` with `acceptEdits` + a tool allowlist, `copilot` with
`--allow-all-tools`, `gemini` with `--approval-mode yolo`. `claude` takes a model alias;
`copilot`/`gemini` use their own default model. A backend can be slower on big files — raise
`OKF_LLM_TIMEOUT`. See `.env.example` for binary-path and timeout overrides. (Run ingest on a
clean git tree so any stray edit is easy to spot.)

### Keep the wiki/raw outside the repo (e.g. a network drive)

By default `wiki/`, `raw/`, and `docs/` live in the repo, but you can point them anywhere with
absolute paths — including a mounted network drive, so the corpus is shared/backed-up centrally
while the code stays a normal checkout:

```ini
# Windows mapped drive (T: -> \\server\share):
OKF_WIKI_DIR=T:\team-wiki\wiki
OKF_RAW_DIR=T:\team-wiki\raw
# Linux/macOS mount:
# OKF_WIKI_DIR=/mnt/llmwiki/wiki
# OKF_RAW_DIR=/mnt/llmwiki/raw
```

Two rules keep it sound: (1) a **relative** override resolves against the **repo root** (not your
shell's CWD), while an **absolute** one is used as-is; (2) keep `wiki/` and `raw/` under a
**common parent** (as above) so the `## Sources` citation links between them remain valid relative
links. Ingest then grants the agentic CLI access to the out-of-repo locations automatically
(`claude` via `--add-dir`, `copilot` via `--allow-all-paths`); the read-only tools (`search`,
`lint`, `view`, MCP) work regardless.

## Use

**Ingest** — drop one or more arbitrary text-bearing files into `raw/` (any type — markdown,
plain text, code, JSON/CSV, PDF, … — in any sub-folder), then fold them in:

```bash
cp ~/notes/q3-planning.md raw/
uv run python -m okf_wiki ingest                    # ingest all new/changed files in raw/
uv run python -m okf_wiki ingest docs/karpathy-llm-wiki.md   # or bootstrap from a specific file
```

Ingest folds each source into the **best-fitting** existing pages and restructures as the corpus
grows; the report distinguishes pages **created**, **updated**, and **deleted** (restructured),
and warns on any broken cross-link. When routing, the agent treats each source's **sub-folder
path within `raw/` and its filename as context** — they often encode the project/topic the facts
belong to (e.g. `raw/acme-migration/db/schema-notes.sql`) — and uses that, alongside the file's
content, to pick the right page and tags (the path is never cited as a fact). Run several
overlapping files (e.g. the bundled `raw/coffee*.md` set) and watch the wiki reorganize itself
rather than accrete one page per file.

There is **one agent session per file**, so ingest shows live per-file progress on stderr
(`[2/6] … 2 created, 1 updated` with a spinner + elapsed time) so a multi-file run never looks
hung — pass `--quiet` to suppress it and print only the final report.

Ingest is **idempotent**: a committed manifest at `wiki/.okf_ingested.json` maps each source's
repo-relative path to a sha256, so re-running with no new or changed files runs **zero** agent
sessions. Exactly one agent session per source; if a session fails or times out, that source's
wiki changes are rolled back and it is retried next run.

Crucially, ingest keeps the wiki in sync when a raw file **changes** or **disappears** — not
just when one is added:

- **Edit a raw file** (new sha) and it is **re-ingested in reconcile mode**: the agent re-reads
  the current bytes and **updates or removes the now-stale facts** it previously derived from
  that file (e.g. a corrected number overwrites the old one), rather than only appending new
  ones — existing facts from *other* sources stay untouched.
- **Delete a raw file** and a full `ingest` run **detects the vanished source** (its key is in
  the manifest but the file is gone) and runs a **cleanup session** that strips every fact and
  `[^sN]` citation that depended on it — dropping a co-cited fact's marker but keeping the fact
  when another source still supports it, and deleting a page that loses its last source. The
  cleanup is **all-or-nothing**: it is rolled back and retried unless *no* page references the
  removed file afterwards, then the manifest key is dropped. (Deletion is swept only on a full
  run, so `ingest <one-file>` never surprise-prunes.)
- **Move or reorganize** a raw file (same bytes, new path, e.g. sorting `raw/` into sub-folders)
  and ingest recognizes it — it is **not** re-ingested, and the wiki's `resource`/citation
  references are repointed to the new path automatically (a move is **not** treated as a delete).

A file with **no extractable text** (a binary blob) is skipped and noted in `wiki/log.md` as
unreadable rather than fed to the agent.

**Search** the synthesized wiki:

```bash
uv run python -m okf_wiki search "caffeine content"        # ranked keyword hits across all pages
uv run python -m okf_wiki search "caffeine" --tag brewing   # ...restricted to a tag
uv run python -m okf_wiki tags                              # browse every tag and its pages
```

**Navigate by links and tags.** Pages cross-link densely (each ends with a `## See also`), and
the generated `index.md` lists, per page, who references it (`↳ referenced by: …`) plus a
`## Tags` section — so you can browse by topic, not just search. `lint` even **suggests** missing
links (a page that names another page without linking it).

**Check** — the strict per-page gate that re-imposes the invariants the agent must honor:
required fields (`type`/`title`/`description`/`tags`/`resource`), honest/defined citations, and
relative non-broken links (no `[[wiki-links]]`). Ingest runs it automatically (a forgotten field
fails the run) and the ingest agent self-checks with it; you can also run it directly:

```bash
uv run python -m okf_wiki check                 # the whole wiki
uv run python -m okf_wiki check concepts/x.md   # just one page
```

**Lint** — a pure, offline health check (contradictions, orphaned pages, facts missing
citations, broken cross-links, pages missing `type`, stale pages, **fabricated sources** — a
fact citing a `raw/` file that does not exist — and `[[wiki-style]]` links). Exit code is
non-zero when the wiki is unhealthy, so it drops cleanly into CI:

```bash
uv run python -m okf_wiki lint
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
zero custom tooling. The page's frontmatter `resource:` names the primary raw source. A raw
claim that cannot be cited is dropped, never invented. A fact the model adds from its own
knowledge — allowed only when essential, high-confidence, and on-topic — is labeled with a
separate `[^llmN]` marker defined as `LLM - model knowledge` (grep them with `grep -rn '\[\^llm'
wiki/`). Conflicting sources produce a `> [!CONTRADICTION]` callout rather than a silent
overwrite.

## MCP server

Expose the wiki to an AI client over stdio:

```bash
uv run python -m okf_wiki serve        # or: uv run okf-wiki serve
```

It serves six tools: `wiki_search` (with an optional `tag` filter), `wiki_read`, `wiki_index`,
`wiki_tags`, and `wiki_validate` (read-only), and `wiki_ingest` (the only mutating tool, routed
through the same path-safe ingest pipeline).

Wire it into an MCP client (e.g. Claude Desktop's `claude_desktop_config.json`). The `python -m`
form needs no `.exe`, so it is the safe choice on Windows. No API key in the env — ingest uses
the CLI's own login:

```json
{
  "mcpServers": {
    "okf-wiki": {
      "command": "uv",
      "args": ["run", "python", "-m", "okf_wiki", "serve"],
      "env": { "OKF_LLM_CLI": "claude", "OKF_INGEST_MODEL": "sonnet" }
    }
  }
}
```

Now an AI can `wiki_index()` to orient, `wiki_search(...)` to find pages, and `wiki_read(...)`
to pull full cited context — answering from your synthesized wiki instead of re-retrieving raw
documents.

## Viewing

Browse the wiki visually with a built-in, dependency-free viewer:

```bash
uv run python -m okf_wiki view            # generate + open in your browser
uv run python -m okf_wiki view --no-open  # just (re)generate the file
uv run python -m okf_wiki view --out /tmp/wiki.html
```

This writes a **single self-contained** `wiki/.okf_viewer.html` — the pages, the cross-link
graph, and the tags embedded inline, rendered by a tiny hand-rolled markdown renderer and graph
in vanilla JS. It opens straight from `file://` with **no server and no network**: nothing is
fetched from a CDN, so **your wiki never leaves the machine**. The file is a regenerable
artifact (like `index.md`), gitignored, and skipped by the loader. On a headless box / WSL with
no browser, the command prints the `file://` path to open manually instead of failing.

### Open in Obsidian

The `wiki/` directory also opens **as-is** as an [Obsidian](https://obsidian.md) vault (*Open
folder as vault*) — frontmatter, `tags`, GFM footnote citations, `> [!CONTRADICTION]` callouts,
and the cross-link graph/backlinks all work natively and fully locally. Two notes:

- The `## Sources` footnotes link to `../../raw/*.md`, which sit **outside** a `wiki/`-only
  vault. Open the **repository root** as the vault if you want those citation links to resolve.
- Keep OKF's **standard markdown links** — do **not** convert to `[[wikilinks]]`, or the
  link-graph, rewrite, and lint machinery break. (`okf-wiki view --obsidian` prints a best-effort
  deep link + the folder path.)

## Reference

- [`SCHEMA.md`](SCHEMA.md) — the authoritative structure and maintenance rules.
- [`docs/karpathy-llm-wiki.md`](docs/karpathy-llm-wiki.md) — the LLM-Wiki pattern this implements.
- [`docs/okf-reference.md`](docs/okf-reference.md) — Google's Open Knowledge Format.
