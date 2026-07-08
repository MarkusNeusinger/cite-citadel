# Troubleshooting

**Start here:** run `citadel doctor`. It's a read-only setup health check that prints OK/WARN/FAIL
lines over workspace resolution, the rules tree, the agent CLI on PATH, raw-root reachability, the
manifest, and the API-key/PDF advisories — it needs no workspace and exits non-zero only on a FAIL.
Most problems below show up there first.

### The agent CLI isn't installed or logged in

Ingest shells out to a coding-agent CLI *you* provide (`claude` / `copilot` / `gemini`) — there is
no API key and no bundled model. `citadel doctor` flags a missing CLI; the fix is to install it and
log in (each CLI's own auth flow), then set `CITADEL_LLM_CLI` in the workspace `.env` to match. If
the binary isn't on `PATH`, point at it with `CLAUDE_CODE_PATH` / `COPILOT_CLI_PATH` /
`GEMINI_CLI_PATH`.

### Rate limits, or a session that runs too long and times out

Each source gets one agent session, capped by `CITADEL_LLM_TIMEOUT` (default 1200s) — raise it for
opus or large raw files. Ingest is **all-or-nothing per source**: a timeout, error, or Ctrl+C leaves
the live wiki exactly as it was and the source simply retries on the next `citadel ingest`, so you
lose no correct pages. Heavy or unattended ingest against a consumer subscription can hit a
provider's rate limits — space the runs out, or use the tier the provider designates for
programmatic use.

### Windows: `citadel` / `citadel.exe` is blocked or missing

Antivirus can quarantine the `citadel.exe` shim `uv` generates. Use the portable invocation
everywhere instead — it needs no `.exe`:

```bash
uv run python -m citadel <subcommand>
```

For the MCP server config, set the client's `command` to `uv` with
`args: ["run", "python", "-m", "citadel", "serve"]`.

### A PDF's figures/diagrams aren't in the wiki

By default (`CITADEL_PDF_MODE=text`) ingest reads a PDF's body text only. Set
`CITADEL_PDF_MODE=images` to also have the agent look at figures, diagrams, and charts — this needs
an agent CLI whose reader actually renders PDF pages (a vision-capable backend). The same applies to
image sources: `CITADEL_IMAGE_SUPPORT=1` (the default) reads recognized images visually.

### "Nothing got ingested"

- Run `citadel status` — the read-only per-source state table shows exactly what happened to each
  file: ingested, failed, skipped-duplicate, ignored (matched `CITADEL_IGNORE_PATTERNS`), or pending.
- Already-ingested sources are skipped by sha match — that's not a bug. To deliberately re-read one,
  use `citadel ingest --force <paths>`.
- Watch a run live with `citadel ingest --verbose` (`-v`), or capture a full transcript per source
  with `citadel ingest --log-dir DIR`.
- If discovery seems to miss files, confirm they're under a walked raw root (`CITADEL_RAW_DIR`, or
  every root in `CITADEL_RAW_DIRS` when set) and aren't matching an ignore glob.

### My wiki (or raw files) live outside the workspace

That's supported: `wiki/`, `raw/`, and `docs/` can each sit on a mounted network drive or any
absolute path via `CITADEL_WIKI_DIR` / `CITADEL_RAW_DIR` / `CITADEL_DOCS_DIR` (and multi-root
`CITADEL_RAW_DIRS`). Keep `wiki/` and `raw/` under a common parent so the `## Sources` citation
links stay valid. Details in [configuration.md](configuration.md#paths--multi-root).

If you point `CITADEL_WIKI_DIR` somewhere (say a corpus's `wiki/`) but leave `CITADEL_RAW_DIR` at
the default, the wiki and its raw sources fall under different parents and every `../../raw/x`
citation resolves OUTSIDE the configured raw root. Nothing errors out, but it degrades silently: the
viewer's sources lose their names/links, and `citadel lint` reports the citations as broken. Run
`citadel doctor` — its **workspace coherence** check flags the mismatch, names one offending
citation and where it actually resolved, and prints the fix (set `CITADEL_RAW_DIR` to the `raw/`
tree next to the wiki, or select the workspace with `CITADEL_WORKSPACE`).

### Where failures are recorded

A source that could not be read (unreadable binary, an errored or timed-out session) is persisted
with its reason and surfaced two ways: in the `citadel status` table, and under a **"Could not
ingest"** section of `wiki/sources/index.md`. Nothing fails silently.

### How do I update citadel?

`citadel doctor` checks PyPI (best-effort, 2s timeout — offline it just skips) and warns when a
newer release is out, printing the right command for how you installed it:

| Installed via | Update with |
| --- | --- |
| `uv tool install` | `uv tool upgrade cite-citadel` |
| `pipx` | `pipx upgrade cite-citadel` |
| `pip` / a venv | `pip install -U cite-citadel` |
| `uvx` | nothing — `uvx cite-citadel` always runs the latest |
| a git checkout | `git pull && uv sync` |

There is deliberately no self-executing `citadel --update`: citadel cannot know which package
manager owns it, and a running `citadel.exe` cannot replace itself on Windows.
