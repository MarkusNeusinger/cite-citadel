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

Ingest shells out to a coding-agent CLI *you* provide (`claude` / `copilot` / `agy`) — there is
no API key and no bundled model. `citadel doctor` flags a missing CLI; the fix is to install it and
log in (each CLI's own auth flow), then set `CITADEL_LLM_CLI` in the workspace `.env` to match. If
the binary isn't on `PATH`, point at it with `CLAUDE_CODE_PATH` / `COPILOT_CLI_PATH` /
`AGY_CLI_PATH`.

### Every session fails with an authentication error, but the CLI works when I run it myself

Hermetic sessions (`CITADEL_HERMETIC=1`, the default) append the backend's session-isolation flag —
claude's `--bare` — so your personal agent configuration never leaks into ingest. On some machines
that same configuration is where the CLI keeps its **credentials** (a managed container, a
devcontainer, an `apiKeyHelper` in `~/.claude/settings.json`), and skipping it leaves the session
unauthenticated. The backend reports this as *"Authentication error · This may be a temporary network
issue, please try again"*, which points at the network rather than the cause — so citadel appends the
hint naming this knob whenever an auth-shaped failure happens on a hermetic run.

The fix is one line in the workspace `.env`:

```bash
CITADEL_HERMETIC=0        # run sessions with your personal agent config (and its credentials)
```

You lose only the isolation (your hooks / `CLAUDE.md` / MCP servers are visible to ingest sessions
again). If instead the CLI fails interactively too, it is a plain login problem — see above.

### Rate limits, or a session that runs too long and times out

Each source gets one agent session, capped by `CITADEL_LLM_TIMEOUT` (default 1200s) — raise it for
opus or large raw files. Ingest is **all-or-nothing per source**: a timeout, error, or Ctrl+C leaves
the live wiki exactly as it was and the source simply retries on the next `citadel ingest`, so you
lose no correct pages. Heavy or unattended ingest against a consumer subscription can hit a
provider's rate limits — space the runs out, or use the tier the provider designates for
programmatic use.

A source large enough to be **chunked** (over `CITADEL_MAX_SOURCE_CHARS`) runs several sessions, and
the retry no longer starts over: each completed segment is checkpointed, so the next run replays
that work and continues at the segment that died (`citadel doctor` lists what is waiting, e.g.
`resume: 1 checkpoint(s) waiting to continue: raw/book.txt (3/7 segments)`). The checkpoint is
dropped automatically whenever it could no longer be trusted — you edited the source, changed model
/rules/language, or another run changed a page it had banked — and then the source is re-imported in
full. To force that yourself, delete `.citadel_resume/` next to the wiki dir, or set
`CITADEL_RESUME=0`.

A source that is large for **your model** but not large in absolute terms is the case that bites
hardest against a local backend: it plans a single pass, the session's context fills up mid-way, and
because a single-pass source never checkpoints, every failed attempt starts over from nothing. Tell
citadel what the model can hold and both halves resolve — the source is split, and the splits are
resumable:

```bash
CITADEL_MODEL_CONTEXT_TOKENS=100000   # your n_ctx; derives a 40 000-char source window
CITADEL_MAX_SOURCE_CHARS=25000        # optional hard ceiling — the smaller of the two wins
```

`citadel doctor` prints the resolved *chunk budget*, so you can check the arithmetic before paying
for a run. Watch out for a second, independent limit while you are there: if the proxy or gateway in
front of your model caps a single HTTP request (a 10-minute cut is common), a slow model can lose a
long request and, with it, its prompt cache — which shows up as the same run getting slower rather
than as an error. Smaller windows shorten each request and keep it under such a cap.

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
an agent CLI whose reader actually renders PDF pages (a vision-capable backend: claude, copilot,
and agy all do; against an unrecognized backend `citadel doctor` warns that images mode may
silently degrade to text-only). The same applies to
image sources: `CITADEL_IMAGE_SUPPORT=1` (the default) reads recognized images visually.

### A PDF's citations aren't offline-verifiable (`wiki_raw` says "no cached text-layer extraction")

PDF `lines A-B` locators verify offline against a per-machine extraction cache
(`.citadel_pdftext/` next to the wiki dir). The pypdf text-layer pre-pass runs by default (pypdf
is a bundled dependency; see [configuration — `CITADEL_PDF_TEXT`](configuration.md#what-gets-ingested);
`citadel doctor` shows its state), so most PDFs get it automatically. A PDF shows "no cached
extraction" when it was ingested **on another machine** (the cache is local — re-read it with
`citadel ingest --force raw/report.pdf` to rebuild it here), when the cache entry was **deleted**,
when it was ingested with `CITADEL_PDF_TEXT=0`, or in the unusual case that pypdf was
**force-removed** from the environment (reinstall it, then `--force`). A scanned/image-only PDF has
no text layer at all and always falls back to agent-verified `p. N` page locators — that is
expected, not a failure. Deleting a cache entry (or the whole dir) just costs one re-extraction.

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
  file: ingested, failed, skipped-duplicate, ignored (matched `CITADEL_IGNORE_PATTERNS`), oversized
  (over `CITADEL_MAX_SOURCE_BYTES`), not included (outside `CITADEL_INCLUDE_PATTERNS`), or pending.
  An ingested source that produced **zero entries** (no wiki page cites it) is marked `NO PAGES`.
- If you set an **allowlist** (`CITADEL_INCLUDE_PATTERNS`), check it first: a single typo (`*.pdff`,
  or a path-shaped `reports/*.pdf` — patterns match file *names*) filters the whole corpus away, and
  the run then looks like a clean pass over nothing. `citadel doctor`'s **include patterns** line
  WARNs on exactly that, and says how many files the allowlist admits versus filters out.
- `citadel ingest --retry` re-runs everything stuck in one go: every failed source still on disk
  plus every `NO PAGES` source (as a forced reconcile). No paths needed — it prints the set first.
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

### The scan is slow, or a raw root also holds huge machine-data files

Discovery stream-hashes every new candidate in full before anything can classify it, so a folder of
multi-GB `.tdms` sensor dumps (or video, or database exports) costs real time on every first scan —
even though every one of them ends up recorded as unreadable binary. Set a **size ceiling**:
`CITADEL_MAX_SOURCE_BYTES=52428800` (50 MB) skips anything larger straight from the walk's own
`stat`, so those files are never opened. Skips are listed on the run report (*Oversized*) and in
`citadel status`, never dropped silently; naming a path explicitly (`citadel ingest big.tdms`)
ingests it anyway. Off by default — see
[configuration.md](configuration.md#what-gets-ingested).

When the noise is a *file type* rather than a size — a raw root shared with a working directory full
of exports, archives, or binaries — say what you *do* want instead:
`CITADEL_INCLUDE_PATTERNS=.pdf,.txt,.md` reads only those and skips everything else at the same
walk-level cost (never opened, never hashed). It is the allowlist counterpart to
`CITADEL_IGNORE_PATTERNS`, and the two compose — the ignore globs still win, so OS junk stays out
even if a whitelisted extension would have matched it.

### Windows: the agent CLI fails on a mapped network drive (`T:\…`)

Symptoms, on a workspace that works perfectly when you `cd` into it yourself: sessions fail with
*"environment blocks UNC/network paths"* or plain "file not found" for paths that plainly exist, and
`git init` / `git add` in the wiki complain about `core.filemode` or `safe.directory`.

Cause: `Path.resolve()` rewrites a mapped drive into its UNC form (`T:\wiki` →
`\\fileserver\share\wiki`), and that resolved path used to be what citadel handed the agent CLI as
its working directory. Citadel now hands child processes the spelling you configured (the drive
letter) while keeping the resolved form as its internal identity — run `citadel doctor` and read the
**child paths** line to see which working directory sessions will use. If it WARNs that only a UNC
spelling is known, map the share to a drive letter and either run citadel from that drive or set
`CITADEL_WORKSPACE=T:\your-workspace`.

WSL is not a workaround here: a DrvFs mount of the same SMB share (`/mnt/t/…`) does not support the
POSIX metadata operations the staging copy and `git init` need, so it fails differently (*Operation
not permitted*). Run citadel natively on Windows against the drive letter.

### My whole wiki turned up as raw sources

This happened when a raw root sat above the wiki (`CITADEL_RAW_DIRS=T:\` with the wiki inside it):
discovery walked the wiki's own pages back in as sources. Discovery now excludes the wiki directory
from every walk, and the next run also sweeps the self-ingested keys out of the manifest and the
failures catalog — so a plain `citadel ingest` cleans it up. The pages those sessions created are
ordinary wiki pages; delete the ones you don't want, or let `citadel curate` fold them in.
`citadel doctor`'s **wiki placement** check flags the nesting itself.

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
