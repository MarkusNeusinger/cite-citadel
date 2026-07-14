# **cite**-citadel

[![CI](https://img.shields.io/github/actions/workflow/status/MarkusNeusinger/cite-citadel/ci.yml?branch=main&label=CI)](https://github.com/MarkusNeusinger/cite-citadel/actions/workflows/ci.yml)
[![codecov](https://codecov.io/github/MarkusNeusinger/cite-citadel/graph/badge.svg)](https://codecov.io/github/MarkusNeusinger/cite-citadel)
[![PyPI](https://img.shields.io/pypi/v/cite-citadel)](https://pypi.org/project/cite-citadel/)
[![Python versions](https://img.shields.io/pypi/pyversions/cite-citadel)](https://pypi.org/project/cite-citadel/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/MarkusNeusinger/cite-citadel/blob/main/LICENSE)

> **A fortress of cited knowledge.** An LLM-maintained, fully-cited personal wiki —
> every fact is attested to its source, nothing is invented.

An LLM-maintained personal wiki in Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md) (OKF),
with an **MCP server** (and a CLI that mirrors every MCP tool) so an AI can search and read it —
a KISS, pure-Python 3.12 take on Andrej Karpathy's [LLM-Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).

Drop arbitrary files into `raw/`, in any sub-folder — **if the agent CLI you use can open it, citadel
can ingest it** (few exceptions). One agentic CLI session per source folds it into a cross-linked OKF
wiki under `wiki/`, **routing each fact to the page it best fits** and splitting/merging pages as the
corpus grows rather than making one page per file. Built-in helpers cover the rest: Office text
extraction, visual image reading, multi-pass folding for oversized files, duplicate-format dedup, and a
record (with the reason) in `wiki/sources/index.md` for anything that can't be read. Every fact cites its
`raw/` source and the model uses **only** what is in `raw/`; an AI client then queries the synthesized
wiki over MCP instead of re-reading your notes.

The CLI is **`citadel`**; the PyPI package is **`cite-citadel`**. The `wiki/` directory **is** the
database — no SQLite, no vector store. Ingest runs through a **coding-agent CLI you already have**
(`claude`, `copilot`, or `gemini`), so it uses your existing subscription and **needs no API key** —
that usage is under your account and your provider's terms (see
[License & third-party tools](#license--third-party-tools)).

**Three guarantees that hold as the wiki grows** (full rules in
[`citadel/rules/schema.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/citadel/rules/schema.md)):

- **Stays organized** — ingest merges, splits, and deletes pages by fit; it never piles up one page
  per raw file.
- **Links keep working** — merges/renames repoint inbound cross-links; any dangling link fails
  `citadel lint` / `citadel check`.
- **Honest provenance** — raw facts are restated faithfully and cite their source as `[^sN]`. A fact
  the model adds from its own knowledge must be labeled `[^llmN]`, never disguised as a raw citation.

## Quickstart

Ingest runs through a coding-agent CLI you already have — no API key, just your existing subscription.

```bash
uv init my-wiki && cd my-wiki
uv add cite-citadel
uv run citadel init
nano .env                 # pick your agent CLI (claude | copilot | gemini) — must be logged in
cp ~/notes/* raw/         # drop in anything your agent can open
uv run citadel ingest     # one agent session per source builds the cited wiki
uv run citadel view       # browse it offline
```

Every other knob is documented inline in the generated `.env`. A global install (`uv tool install
cite-citadel`; plain `pip install cite-citadel` works too) drops the `uv run` prefixes; `citadel
doctor` warns when a newer release is on PyPI and prints the update command matching your install
(see [docs/troubleshooting.md](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/troubleshooting.md#how-do-i-update-citadel)). On Windows,
use `uv run python -m citadel` — the `uv run citadel` shorthand can be antivirus-blocked (see the
contributor note below).

**Local models.** For a fully private wiki, point the same agent CLI at a local model (Ollama) so
nothing you ingest ever leaves your machine or LAN — see
[Local models (Ollama)](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/configuration.md#local-models-ollama).

> **Contributing?** Run from a checkout: `uv sync`, then the portable `uv run python -m citadel
> <subcommand>` (identical on Linux/macOS/Windows and needs no `.exe` — on Windows, antivirus can
> quarantine uv's generated `citadel.exe`).

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
   **no code change**. The rules live in the package so a pip install carries them.

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

Every page's frontmatter records **when it last changed and which cite-citadel release wrote it**
(`timestamp` + `citadel_version`, both stamped automatically), and `citadel curate --stale-rules`
refreshes pages whose sources were ingested under an older rulebook. For a full audit trail, `git
init` the `wiki/` folder once (or set `CITADEL_WIKI_GIT=1`): citadel then **auto-commits the wiki
after every ingest/curate run** — each change a reviewable diff — and can push to a remote
(GitHub/GitLab) via `CITADEL_WIKI_GIT_REMOTE`. See
[`docs/configuration.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/configuration.md) § Wiki history.

## Test corpora

Five synthetic corpora live under [`corpora/`](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora),
each ingestible on its own or all together and each shipping its own committed, CI-linted showcase
wiki at `corpora/<name>/wiki/`:

- **[beverages](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/beverages)** — the everyday coffee + tea showcase: overlapping facts that repeat, contradict, and hide in one place, plus a planted false sourced claim.
- **[kelvarra](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/kelvarra)** — a coherent fictional world whose facts contradict reality, graded to appear as stated, cited, never corrected.
- **[leuchtfeuer](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/leuchtfeuer)** — a three-year programme ingested in dated waves: reconcile / delete / force, temporal supersession, German→English, attributed opinions.
- **[pemberley](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/pemberley)** — all of *Pride and Prejudice* as one ~730k-char source: large-source multi-segment chunking, relationship extraction, narrative supersession.
- **[injection-resistance](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/injection-resistance)** — mundane documents with adversarial instructions embedded, which the agent must treat as content and never execute.

> **These are test inputs, not reference material.** Every wiki here is machine-generated by an LLM
> agent from the raw sources, and some corpora deliberately contain planted errors, contradictions,
> or entirely fictional "facts" — do not treat any of them as real-world knowledge.

**See it without running anything:** browse a showcase wiki on GitHub (e.g.
[`corpora/beverages/wiki/index.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/corpora/beverages/wiki/index.md))
or the interactive **[live demo gallery](https://markusneusinger.github.io/cite-citadel/)** — one
viewer per corpus. `verify-corpus` grades each against a hidden answer key it never sees; per-corpus
detail lives in each `corpora/<name>/README.md` and `CLAUDE.md`.

## MCP server

`citadel serve` exposes **twelve tools** over stdio — eleven read-only (`wiki_search`,
`wiki_define`, `wiki_read`, `wiki_raw`, `wiki_neighbors`, `wiki_index`, `wiki_sources`,
`wiki_tags`, `wiki_validate`, `wiki_lint`, `wiki_status`) and one mutating (`wiki_ingest`) — each
with MCP behavior annotations (`readOnlyHint` etc.) so a client can tell them apart. Every tool has
a CLI counterpart (`citadel read`, `citadel index`, `citadel lint`, …), so an AI without MCP access
can do everything through the shell.

Wire it into any stdio MCP client (Claude Desktop, Claude Code, a generic stdio client) by launching
`citadel serve` with `CITADEL_WORKSPACE` set to your workspace. An AI then `wiki_index()`s to orient,
`wiki_search(...)`es to find pages, and `wiki_read(...)`s for full cited context — answering from
your synthesized wiki instead of re-retrieving documents. Copy-paste config and "if the server won't
start": [**docs/mcp.md**](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/mcp.md).

## Reference

- [**`docs/`**](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/index.md) — the docs
  hub: an "I want to…" table pointing at configuration (every `CITADEL_*` knob), MCP setup,
  curate/status/maintenance, troubleshooting, the OKF format, and the founding idea.
- `CLAUDE.md` — architecture notes for contributors.
- [`CONTRIBUTING.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/CONTRIBUTING.md) ·
  [`CHANGELOG.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/CHANGELOG.md) ·
  [`SECURITY.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/SECURITY.md)

## License & third-party tools

cite-citadel is released under the [MIT License](https://github.com/MarkusNeusinger/cite-citadel/blob/main/LICENSE).

**Not affiliated.** cite-citadel is independent — not affiliated with or endorsed by Anthropic,
GitHub/Microsoft, or Google. "Claude", "GitHub Copilot", and "Gemini" are their owners' trademarks
naming only the user-supplied CLI; full disclaimer in [NOTICE.md](https://github.com/MarkusNeusinger/cite-citadel/blob/main/NOTICE.md).

**Bring your own CLI — your account, your provider's terms.** Ingest runs *your* authenticated
coding-agent CLI under *your* account, governed by **that provider's** terms, not by cite-citadel:
[Anthropic Consumer](https://www.anthropic.com/legal/consumer-terms) /
[Commercial Terms](https://www.anthropic.com/legal/commercial-terms),
the [GitHub Copilot product-specific terms](https://docs.github.com/en/site-policy/github-terms/github-copilot-product-specific-terms),
and the [Gemini Code Assist / API terms](https://developers.google.com/gemini-code-assist/resources/terms-of-service)
(credential handling is covered in NOTICE.md above). Honest caveat: heavy, unattended, or CI ingest
against a **consumer subscription** can hit rate limits or a provider's automated-use expectations —
for that scale prefer the tier the provider designates for programmatic use.

**Your wiki is yours.** The providers assign output rights to you, and cite-citadel claims nothing
over `wiki/` content — publish the generated wiki freely.
