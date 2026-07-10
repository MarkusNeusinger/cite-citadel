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

`citadel serve` exposes **twelve tools** — eleven read-only and one mutating (`wiki_ingest`). Each
carries MCP behavior annotations (`readOnlyHint` etc.) so a client can tell the readers from the one
mutating tool, and none ever raises — errors come back as plain strings. The server also hands the
recommended tool flow up through `initialize.instructions`, so a client that surfaces it gets the
orientation for free.

| Tool | What it does |
|------|--------------|
| `wiki_search` | Keyword search across all pages (title/tags/description/body); ranked hits with snippets. |
| `wiki_define` | Glossary lookup — the meaning/expansion of a term (abbreviation → exact title → search fallback). |
| `wiki_read` | Full verbatim OKF page text for a rel_path, including all `[^sN]` citations. |
| `wiki_raw` | Read the raw source behind a `[^sN]` citation (locator-aware) — the trust-but-verify spot-check. |
| `wiki_neighbors` | A page's link neighborhood: links-out, backlinks, and cited sources. |
| `wiki_index` | The `index.md` catalog of all pages with one-line descriptions — the cheap first read to orient. |
| `wiki_sources` | The `sources/index.md` provenance catalog — one row per ingested source and the pages citing it. |
| `wiki_tags` | Browse by tag: every tag and its pages, or one tag's pages. |
| `wiki_validate` | The strict per-page gate (required fields, honest citations, non-broken links). |
| `wiki_lint` | The whole-wiki advisory health check (contradictions, orphans, missing cites, …; tunable `stale_days`). |
| `wiki_status` | Per-source corpus state (ingested/failed/skipped/ignored/pending) — the read-only twin of `citadel status`. |
| `wiki_ingest` | **The only mutating tool** — fold new/changed raw files into the wiki (idempotent via the sha manifest). |

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
