# Troubleshooting

**Start here:** run `citadel doctor`. It's a read-only setup health check that prints OK/WARN/FAIL
lines over workspace resolution, the rules tree, env-setting parse fallbacks (a numeric knob whose
value didn't parse silently falls back to its default — doctor is where that becomes visible), the
agent CLI on PATH, raw-root reachability, the manifest, and the API-key/PDF advisories — it needs
no workspace and exits non-zero only on a FAIL. Most problems below show up there first.

### "another citadel run is already running on this workspace"

Ingest and curate take one exclusive run lock per workspace (a `.citadel_run.lock` file next to
the wiki directory), because two concurrent runs would silently destroy each other's work. Wait
for the other run to finish — or, if it crashed hard, the lock frees itself (a dead process or a
stale lock is reclaimed automatically on the next run); deleting the named lockfile by hand is
always safe once you are sure no run is alive.

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

### A PDF's citations aren't offline-verifiable (`wiki_raw` says "no cached text-layer extraction")

PDF `lines A-B` locators verify offline only when the PDF was ingested through the optional pypdf
text-layer pre-pass (see [configuration — `CITADEL_PDF_TEXT`](configuration.md#what-gets-ingested);
`citadel doctor` shows its state). A PDF ingested **before** pypdf was installed — or on another
machine — carries agent-verified `p. N` page locators and has no local extraction cache. After
installing pypdf (`pip install cite-citadel[pdf]`), re-read it deliberately:
`citadel ingest --force raw/report.pdf`. Like the transcript cache, extractions live
content-addressed in `.citadel_pdftext/` next to the wiki dir; deleting an entry (or the dir) just
costs one re-extraction. A scanned PDF has no text layer at all and always falls back to
agent-native reading — that is expected, not a failure.

### An audio/video recording isn't in the wiki

Audio transcript ingest is **opt-in**: set `CITADEL_AUDIO_SUPPORT=1` and install a whisper-class
CLI (see [configuration — Audio/video sources](configuration.md#audiovideo-sources-whisper);
`citadel doctor` checks the binary). Two follow-ups worth knowing:

- A recording ingested **while the knob was off** was recorded as unreadable and marked done — it
  is not re-checked on later runs. After turning the knob on, re-read it deliberately:
  `citadel ingest --force raw/meeting.mp3`.
- Transcripts are cached content-addressed in `.citadel_transcripts/` next to the wiki dir, so an
  unchanged recording is never transcribed twice — including after you switch
  `CITADEL_WHISPER_MODEL`. To re-transcribe with a better model, delete the file's cache entry
  (or the whole cache dir) and run `citadel ingest --force <path>`.

### "Nothing got ingested"

- Run `citadel status` — the read-only per-source state table shows exactly what happened to each
  file: ingested, failed, skipped-duplicate, ignored (matched `CITADEL_IGNORE_PATTERNS`), or pending.
- Already-ingested sources are skipped by sha match — that's not a bug. To deliberately re-read one,
  use `citadel ingest --force <paths>`.
- Watch a run live with `citadel ingest --verbose` (`-v`), or capture a full transcript per source
  with `citadel ingest --log-dir DIR`.
- If discovery seems to miss files, confirm they're under a walked raw root (`CITADEL_RAW_DIR`, or
  every root in `CITADEL_RAW_DIRS` when set) and aren't matching an ignore glob.

### A text file is reported "unreadable" — Dropbox/OneDrive online-only files

If a plain `.md`/`.txt` source shows up as unreadable with *"reads as all NUL bytes - likely a
cloud-only placeholder"*, the sync client has evicted its content to the cloud: Windows still
reports the full file size, but reading it through WSL or a network share yields only zeros until
the file is hydrated. Fix: make the file (or its whole folder) **available offline** in
Dropbox/OneDrive — right-click it in Explorer, or open it once on the Windows side — then re-run
`citadel ingest`. Placeholders are deliberately never stat-cached as done, so the next run picks up
the hydrated content automatically. If your `raw/` lives in a synced folder permanently, pin it to
"available offline" so newly synced files don't regress to placeholders.

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
