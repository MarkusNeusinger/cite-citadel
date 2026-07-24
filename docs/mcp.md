# MCP server

`citadel serve` runs a FastMCP **stdio** server that exposes your synthesized wiki to any AI
client. The AI queries the cited wiki instead of re-reading your raw notes — and because every MCP
tool has a CLI twin (`citadel read`, `citadel search`, …), an AI without MCP access can do the same
work through shell commands.

Portable invocation (identical on Linux/macOS/Windows, needs no `.exe`):

```bash
uv run python -m citadel serve
```

A global install (`uv tool install cite-citadel` or `pip install cite-citadel`) drops the prefix, so
the command is just `citadel serve`.

## Workspace resolution

`serve` operates on a **workspace** — a directory holding a `citadel.toml` marker (scaffold one with
`citadel init`). Discovery order:

1. `CITADEL_WORKSPACE=/path/to/workspace` in the server's environment (highest priority),
2. else the nearest `citadel.toml` marker walking up from the server's working directory,
3. else an **env-dirs workspace**: both `CITADEL_WIKI_DIR` and `CITADEL_RAW_DIR` set (no marker
   needed — the two directories *are* the workspace).

An MCP client usually launches the server from an arbitrary CWD, so setting `CITADEL_WORKSPACE`
explicitly is the reliable choice. `wiki/`, `raw/`, and `docs/` can live outside the workspace via
the `CITADEL_*_DIR` overrides — see [configuration.md](configuration.md#paths--multi-root).

## Tools

`citadel serve` exposes **thirteen tools** — eleven read-only and two mutating: `wiki_capture`
(append-only note capture into the raw/ capture log — it never touches the wiki) and `wiki_ingest`
(the only tool that writes the wiki). Each carries MCP behavior annotations (`readOnlyHint` etc.)
so a client can tell the readers from the mutating tools, and none ever raises — errors come back
as plain strings. The server also hands the recommended tool flow up through
`initialize.instructions`, so a client that surfaces it gets the orientation for free — and the
same flows ship as [prompts](#prompts), with the wiki's documents addressable as
[`wiki://` resources](#resources).

| Tool | What it does |
|------|--------------|
| `wiki_search` | Ranked BM25 search across all pages (title/aliases/tags/description/body). Terms are AND-matched on content words (OR-retried when nothing fully matches); `tag:x` / `type:y` tokens in the query filter instead of match. `limit` (default 8, capped at 50) and `offset` page through the ranked list. |
| `wiki_define` | Glossary lookup — the meaning/expansion of a term (abbreviation → exact title → search fallback). |
| `wiki_read` | Full verbatim OKF page text for a rel_path, including all `[^sN]` citations. Output capped at 20k chars (`max_chars=0` lifts the cap). |
| `wiki_raw` | Read the raw source behind a `[^sN]` citation (locator-aware: `lines A-B`, `§ Heading`, or combined) — the trust-but-verify spot-check. Output line-numbered and capped at 20k chars; narrow with a locator. |
| `wiki_neighbors` | A page's link neighborhood: links-out, backlinks, and cited sources. |
| `wiki_index` | The `index.md` catalog of all pages with one-line descriptions — the cheap first read to orient. |
| `wiki_sources` | The `sources/index.md` provenance catalog — one row per ingested source and the pages citing it. |
| `wiki_tags` | Browse by tag: every tag and its pages, or one tag's pages. |
| `wiki_validate` | The strict per-page gate (required fields, honest citations, non-broken links). |
| `wiki_lint` | The whole-wiki advisory health check (contradictions, orphans, missing cites, …; tunable `stale_days`). |
| `wiki_status` | Per-source corpus state (ingested/failed/skipped/ignored/pending) — the read-only twin of `citadel status`. |
| `wiki_capture` | Append ONE attributed, dated note from the conversation to `raw/captures/YYYY-MM.md` — the conversational-capture bridge (see [capture.md](capture.md)). Append-only, never touches the wiki; the next ingest folds it in with real `[^sN]` line locators. |
| `wiki_ingest` | **The only tool that writes the wiki** — fold new/changed raw files into it (idempotent via the sha manifest). |

## Prompts

The recommended tool flows also ship as four MCP **prompts** — clients like Claude Desktop
surface them as slash-command-like entries, so a user can invoke a whole workflow instead of
narrating it:

| Prompt | Arguments | Workflow it packages |
|--------|-----------|----------------------|
| `wiki_answer` | `question` | Answer strictly from the cited wiki: orient (`wiki_index`/`wiki_define`) → `wiki_search` → `wiki_read` → cite pages, spot-checking load-bearing claims via `wiki_raw`. |
| `wiki_verify` | `rel_path` | Verify one page against its provenance: resolve every `[^sN]` citation through `wiki_raw` and report supported / unsupported / unreadable per fact, plus the `wiki_validate` gate. |
| `wiki_capture_note` | `statement`, `source` (optional) | Record ONE durable statement via `wiki_capture`, attributed (defaulting to the user in-conversation), and report the appended line range. |
| `wiki_health` | — | Corpus + wiki review: `wiki_status`, then `wiki_lint`, then the single most useful next maintenance action. |

## Resources

The wiki's documents are also addressable as MCP **resources** under a `wiki://` scheme
(`text/markdown`, byte-identical to their tool twins):

- `wiki://index` — the page catalog (`wiki_index`'s twin),
- `wiki://sources` — the provenance catalog (`wiki_sources`'s twin),
- `wiki://tags` — the tag overview (`wiki_tags`'s twin),
- `wiki://page/{folder}/{name}` — a **template** serving any page's full, uncapped text by
  rel_path, e.g. `wiki://page/concepts/transformer.md` (an OKF rel_path is always exactly
  `folder/name.md`).

Resources share the tools' never-raise contract: a missing page or an unsafe path reads back
as a clear `error: …` body, never a crashed server. Subscribe/`listChanged` notifications are
not offered — the wiki only changes through staged ingest/curate runs, so re-reading after a
`wiki_ingest` is the refresh model.

## Claude Desktop

Add citadel to `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "citadel": {
      "command": "citadel",
      "args": ["serve"],
      "env": {
        "CITADEL_WORKSPACE": "/path/to/your/workspace",
        "CITADEL_LLM_CLI": "claude",
        "CITADEL_INGEST_MODEL": "sonnet"
      }
    }
  }
}
```

`CITADEL_LLM_CLI` / `CITADEL_INGEST_MODEL` only matter if you let the AI call `wiki_ingest`; the
eleven read-only tools need neither. On Windows, set `"command": "uv"` and
`"args": ["run", "python", "-m", "citadel", "serve"]` to sidestep the antivirus-quarantined
`citadel.exe` (see below).

## Claude Code

Register the server with the `claude mcp add` command (the `--` separates citadel's args from
Claude's):

```bash
claude mcp add citadel -e CITADEL_WORKSPACE=/path/to/your/workspace -- citadel serve
```

## A generic stdio client

Any MCP client that speaks stdio launches the same command:

- **command:** `citadel` (or `uv run python -m citadel` from a checkout / on Windows)
- **args:** `["serve"]`
- **env:** at minimum `CITADEL_WORKSPACE` pointing at your workspace; add `CITADEL_LLM_CLI` /
  `CITADEL_INGEST_MODEL` if the client should be able to ingest.

## If the server won't start

- **Run `citadel doctor` first** — it prints OK/WARN/FAIL lines for workspace resolution, the rules
  tree, the agent CLI on PATH, raw-root reachability, and the manifest. Fix any FAIL before wiring up
  a client.
- **"No workspace found"** — the server isn't inside a workspace and `CITADEL_WORKSPACE` isn't set.
  Set `CITADEL_WORKSPACE` in the client's `env`, or `cd` into a workspace and run `citadel init` if
  you haven't scaffolded one.
- **Python 3.12+ is required** — older interpreters won't import the package.
- **Windows** — prefer the portable `uv run python -m citadel serve`; the `citadel.exe` shim uv
  generates can be quarantined by antivirus.

For anything else, see [troubleshooting.md](troubleshooting.md).
