# Recipes: sync & scheduled runs

Citadel's artifact is plain files — markdown pages plus two JSON dotfiles — and its lifecycles
are ordinary CLI commands with honest exit codes. That makes the two most-requested operational
patterns boring in the best way: **multi-device sync** is a file-sync problem git already solves,
and **unattended maintenance** is one cron line. This page collects the recipes for both.

## Sync across devices

### The one rule: one writer, many readers

Exactly **one machine runs the mutating lifecycles** (`ingest`, `curate`, `refresh`, MCP's
`wiki_ingest`); every other device consumes the wiki read-only (browse it, search it, run
`citadel serve` against it). The run lock protects two runs racing on *one* filesystem, but it
cannot protect across a sync service: propagation delay means two machines can each "win" the
lock locally, and the manifest is last-write-wins — the loser's work gets silently re-ingested or
pruned. Reading a synced copy anywhere is always safe; writing from two places is never worth it.

### Recipe: wiki-history git + a private remote (recommended)

The [wiki-history layer](configuration.md#wiki-history-git) already commits the whole wiki after
every run that changed it; add a push target and every device is one `git pull` away:

```bash
# on the writer machine, once:
cd <workspace>/wiki
git init                                              # opts the wiki into history (auto mode)
git remote add origin git@github.com:you/my-wiki.git  # a PRIVATE repo — this is your knowledge
```

```dotenv
# .env
CITADEL_WIKI_GIT_REMOTE=origin
```

Every ingest/curate run now ends with one commit and one push (best-effort — a failed push is a
report note, never a failed run). One caveat: if your *workspace* already sits inside a git
working tree (say, a dotfiles or project checkout), `git init` in `wiki/` creates a nested repo —
workable, but confusing (`CITADEL_WIKI_GIT=1` refuses to auto-init exactly this layout). In that
situation prefer the whole-workspace recipe below. On any other device, `git clone` once and `git pull` whenever:
the wiki opens as-is in [Obsidian](https://obsidian.md), any markdown editor, or the git host's
web/mobile UI. Because the manifest (`.citadel_ingested.json`) lives *inside* `wiki/`, it travels
with the pages — a pulled mirror answers `citadel status`, `search`, and `serve` correctly.

Want full provenance portability — jumping from a citation to the raw source on any device? Put
the **whole workspace** under one git repo instead (`raw/` + `wiki/` + `citadel.toml`). Two
things change: keep machine-specific and regenerable files out, and commit yourself (the
wiki-history layer only auto-commits a wiki dir that is its *own* repo — in this layout, append a
`git add -A && git commit` to your scheduled run, see below):

```gitignore
.env                     # machine-specific paths, possibly provider tokens
.citadel_run.lock
.citadel_pdftext/        # regenerable content-addressed caches
.citadel_transcripts/
.citadel_resume/         # banked segments of an interrupted chunked ingest
wiki/.citadel_viewer.html
```

(Also exclude `CITADEL_LLM_LOG_DIR` if you set it — transcripts can contain source content.)

### Recipe: file-sync services (Dropbox / OneDrive / Syncthing)

A sync service fits two roles well:

- **A phone-fed capture inbox**: a synced folder added as an extra raw root
  (`CITADEL_RAW_DIRS=raw, ~/Dropbox/wiki-inbox`) so clippings, photos, and voice memos land there
  on the go — the README's "Obsidian vault as a capture inbox" pattern. Cloud-only ("online-only")
  placeholder files are detected and simply deferred until hydrated, never mis-recorded as
  ingested.
- **Read-only wiki mirrors**: syncing `wiki/` to other devices for browsing is fine.

What it does *not* fit is multi-writer operation: sync services resolve concurrent edits by
duplicating files ("conflicted copy"), which breaks the one-source-of-truth model the manifest
and staged promotion depend on. Keep all mutating runs on the one writer machine.

### Reading on a phone

- The git host's mobile app or web UI on the pushed wiki repo — pages render as ordinary
  markdown, citations and all.
- Obsidian mobile (or any markdown app) on a synced copy — browse freely, just don't let it
  *write* into `wiki/`.
- `citadel view` builds the wiki into **one self-contained offline HTML file** (search, graph,
  citation popovers, no server) — sync or send that single file to any device.

## Scheduled runs

Unattended runs are safe by design, which is exactly what makes scheduling them attractive:

- **Idempotent** — unchanged sources are sha-short-circuited, so a nightly ingest with nothing
  new in `raw/` spawns zero agent sessions and costs nothing.
- **Self-limiting refresh** — `--min-age-days D` makes a scheduled refresh a free no-op once
  everything has been checked within D days; `--limit N` caps every run at N sessions.
- **Overlap-safe** — a run colliding with another fails loud on the run lock (non-zero exit)
  instead of corrupting anything; the next tick just runs.
- **All-or-nothing** — a run killed mid-flight (reboot, timeout) leaves the live wiki exactly as
  it was; the interrupted source retries next run. A file caught mid-copy is reconciled at the
  next tick once its content settles.
- **Auditable** — `ingest`/`refresh` exit 1 when any source failed; `citadel status` shows
  failures, per-source `checked` dates, and the recorded LLM cost total; `log.md` and the
  wiki-git diffs show what changed while you slept.

The canonical pair to schedule:

```bash
citadel ingest --quiet                        # nightly: fold in whatever landed in raw/
citadel refresh --limit 5 --min-age-days 30   # weekly: re-verify the 5 longest-unchecked sources
```

Together they keep the wiki current in both directions: new knowledge lands within a day, and old
imports are re-verified round-robin under the current model + rules (~20 sources/month at these
numbers — size the budget against `citadel status`'s recorded cost).

### Working off a big backlog: `--jobs N`

A nightly run has hours, so it can afford to be serial — and serial is what gives the richest
cross-linking, because every session sees the pages the previous one wrote. When you are folding in
a *backlog* of largely unrelated sources (a first import, a newly mounted archive), the run is
dominated by per-session latency instead, and `--jobs` trades some of that linking for wall-clock:

```bash
citadel ingest --jobs 4     # or set CITADEL_JOBS=4 for every run in this workspace
```

Each source keeps its own staging copy and its own all-or-nothing promote — nothing about the
safety model changes — but concurrent sessions cannot see each other's new pages, so they link less
richly and can create two pages for one topic. Two things absorb that: a source whose promote raced
another one over the same page is automatically re-run serially (the report lists it under *Re-run
serially*), and a later `citadel curate` pass merges and re-grounds what parallel sessions left
apart. Lots of races in the report means the corpus is more connected than the run assumed — lower
`--jobs`. Rate limits on your agent CLI are the practical ceiling; citadel imposes none.

### cron (Linux, macOS)

```cron
# m  h dom mon dow
0 3 * * *   cd /home/me/knowledge && /home/me/.local/bin/citadel ingest --quiet >> /home/me/citadel-cron.log 2>&1
0 4 * * 0   cd /home/me/knowledge && /home/me/.local/bin/citadel refresh --limit 5 --min-age-days 30 >> /home/me/citadel-cron.log 2>&1
```

Cron runs with a minimal environment, so two things must resolve without your shell profile:
`citadel` itself (use the absolute path — `which citadel`) and the agent CLI it shells out to.
For the latter, skip fighting cron's `PATH` entirely: the workspace `.env` is auto-loaded, so set
the binary override there once (`CLAUDE_CODE_PATH=/home/me/.local/bin/claude`, or
`COPILOT_CLI_PATH`/`GEMINI_CLI_PATH`) and the CLI must simply be **logged in for that user**.
`citadel doctor` from a bare-environment shell (`env -i sh -c '…'`) is the quick preflight. On
macOS, grant `cron` Full Disk Access (or use `launchd`) if the workspace lives under `~/Documents`
or another protected folder.

### systemd user timer (Linux)

`~/.config/systemd/user/citadel-ingest.service`:

```ini
[Unit]
Description=citadel nightly ingest

[Service]
Type=oneshot
WorkingDirectory=%h/knowledge
ExecStart=%h/.local/bin/citadel ingest --quiet
```

`~/.config/systemd/user/citadel-ingest.timer`:

```ini
[Unit]
Description=citadel nightly ingest

[Timer]
OnCalendar=*-*-* 03:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user enable --now citadel-ingest.timer
loginctl enable-linger "$USER"     # keep user timers running while logged out
journalctl --user -u citadel-ingest.service   # the run log
```

`Persistent=true` catches up on a missed tick after the machine was asleep. Clone the pair with
`refresh --limit 5 --min-age-days 30` and `OnCalendar=weekly` for the refresh half.

### Windows Task Scheduler

Use the portable invocation (`uv run python -m citadel …` — see the README's note on why the
`.exe` shim is best avoided on Windows):

```powershell
schtasks /Create /SC DAILY /ST 03:00 /TN "citadel ingest" `
  /TR "cmd /c cd /d C:\Users\me\knowledge && uv run python -m citadel ingest --quiet >> citadel-cron.log 2>&1"
schtasks /Create /SC WEEKLY /D SUN /ST 04:00 /TN "citadel refresh" `
  /TR "cmd /c cd /d C:\Users\me\knowledge && uv run python -m citadel refresh --limit 5 --min-age-days 30 >> citadel-cron.log 2>&1"
```

### A scheduled agent instead of cron ("smart cron")

The cron line is the baseline; a **scheduled coding-agent session** (a Claude Code Routine, or
any scheduler that can run an agent) adds judgment on top for the cost of one extra session: it
runs the same two commands, then *reads the outcome* and acts on it. A prompt that works:

> In `/home/me/knowledge`, run `citadel ingest --quiet`, then
> `citadel refresh --limit 5 --min-age-days 30`. Read both run reports and `citadel status`.
> If any source failed, investigate the reason (see `citadel doctor` and the failures listed in
> status) and summarize what's wrong; otherwise summarize in two sentences what the wiki learned
> tonight (the run report names created/updated pages).

This is the autonomous nightly fold-in as a recipe. The nesting is clean by design: ingest's own
sub-sessions run hermetically (`CITADEL_HERMETIC`, claude's `--bare`), so the outer agent's
configuration never leaks into the wiki-building sessions.

### No watch mode, on purpose

Citadel ships no file-watcher daemon. Sha-idempotent ingest makes polling essentially free, so a
schedule beats a watcher: no long-lived process, no missed-event edge cases, no racing files that
are still being written or synced — whatever `raw/` holds at tick N is folded in complete, and
anything that settles later is picked up at tick N+1.
