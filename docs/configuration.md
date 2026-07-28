# Configuration reference

Every cite-citadel setting is a `CITADEL_*` (or provider) environment variable. `citadel init`
scaffolds a workspace `.env` that is auto-loaded (process env > workspace `.env` > packaged
defaults). This page is the reference for pip users who never see the template file. The
template's top section is all most setups need — everything under its "Advanced" line is optional
tuning whose defaults suit most workspaces, documented in full here.

Parsing is tolerant across every knob family: a **blank** value (an uncommented-but-emptied `.env`
line) means "unset" and keeps the default, and a value that doesn't parse (a non-integer number, an
unrecognized boolean/mode token) falls back to the default — `citadel doctor`'s config check names
every such fallback. Booleans accept `1/true/yes/on` and `0/false/no/off`.

> **Source of truth:** [`citadel/templates/env.example`](../citadel/templates/env.example) — the
> commented template `citadel init` writes. Keep this page in sync with it when a knob changes.

## Bring your own CLI — your account, your provider's terms

Ingest runs *your* authenticated coding-agent CLI under *your* account, governed by **that
provider's** terms. The full note (provider-terms links, credential handling, subscription-vs-API)
lives once in the README:
[License & third-party tools](https://github.com/MarkusNeusinger/cite-citadel/blob/main/README.md#license--third-party-tools).

## Backend selection

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_LLM_CLI` | `claude` | Which CLI ingest shells out to: `claude` \| `copilot` \| `agy` (Google's Antigravity CLI, successor to the retired `gemini` CLI — setting `gemini` now fails with a migration hint). Run agentically (claude with acceptEdits + allowlist, copilot `--allow-all-tools`, agy `--dangerously-skip-permissions`); the CLI must be installed and logged in. If your workspace is a git checkout, run ingest on a clean working tree so any stray edit shows up (git is optional otherwise). |
| `CITADEL_INGEST_MODEL` | *(unset)* | Model for **every** backend — passed through as `--model` to `claude`, `copilot` and `agy` alike. claude takes an alias (`sonnet`/`opus`/`haiku`) or a full id, copilot a model name (or `auto`), agy an id from `agy models`. Unset means "run the CLI's own default". This knob is only the *request*: the manifest, `citadel status` and the viewer record the model the backend actually **reported** for the session, falling back to this label only when the backend named none. |
| `CITADEL_CURATE_MODEL` | (reuses ingest model) | Cheaper/faster model for `citadel curate` sessions, passed as `--model` on any backend. |
| `CLAUDE_CODE_PATH` / `COPILOT_CLI_PATH` / `AGY_CLI_PATH` | (PATH lookup) | Override the CLI binary path when it isn't on `PATH`. |

## Local models (Ollama)

Run ingest **fully on your own machine or LAN**, so a private wiki's content never leaves it. Point
the *same* agent CLI at a local [Ollama](https://ollama.com) model — do **not** call the Ollama API
directly, which would lose the agentic file-reading loop citadel is built on. Both recipes below can
live entirely in the workspace `.env` (the loader fills in any unset variable) — except that an
already-**exported** real key is never overridden, so unset it first.

**Claude Code → local model.** Ollama ≥ 0.14 serves a native Anthropic-compatible surface on
`:11434` (no `/v1`):

```sh
ANTHROPIC_BASE_URL=http://localhost:11434   # or http://<host>:11434 for a LAN server
ANTHROPIC_AUTH_TOKEN=ollama
ANTHROPIC_API_KEY=""                          # empty — and unset any real exported key first
CITADEL_LLM_CLI=claude
CITADEL_INGEST_MODEL=qwen3.6:27b              # the exact `ollama list` tag
```

**GitHub Copilot → local model.** OpenAI-compatible surface — note the `/v1`. Select the model
with `CITADEL_INGEST_MODEL` (citadel passes it through as `--model`); this is proven for the
non-interactive `copilot -p` that citadel spawns:

```sh
COPILOT_PROVIDER_BASE_URL=http://<host>:11434/v1
COPILOT_PROVIDER_API_KEY=ollama
COPILOT_PROVIDER_WIRE_API=completions
CITADEL_INGEST_MODEL=qwen3.6:27b
COPILOT_PROVIDER_MAX_PROMPT_TOKENS=120000
COPILOT_PROVIDER_MAX_OUTPUT_TOKENS=8000
NO_PROXY=<host>                               # when a proxy is set in the environment
CITADEL_LLM_CLI=copilot
```

The same in PowerShell:

```powershell
$env:COPILOT_PROVIDER_BASE_URL = "http://<host>:11434/v1"
$env:COPILOT_PROVIDER_API_KEY = "ollama"
$env:COPILOT_PROVIDER_WIRE_API = "completions"
$env:CITADEL_INGEST_MODEL = "qwen3.6:27b"
$env:COPILOT_PROVIDER_MAX_PROMPT_TOKENS = "120000"
$env:COPILOT_PROVIDER_MAX_OUTPUT_TOKENS = "8000"
$env:NO_PROXY = "<host>"
$env:CITADEL_LLM_CLI = "copilot"
```

**Caveats.**

- Raise the model's context window (`OLLAMA_CONTEXT_LENGTH`, or `num_ctx` in a Modelfile) — ≥ 32k is
  realistic for ingest.
- Tool-calling-capable models only (the agent CLI drives file tools).
- Expect a coder-class model of ~27B or larger; owner-tested floor is `qwen3.6:27b`.
- `CITADEL_PDF_MODE=images` additionally needs a **vision**-capable local model.
- The Antigravity CLI (`agy`) has no first-party local-model path today, so it is not offered here.
- A local/proxy backend usually reports no model id of its own, so the per-source stamp falls back
  to the `CITADEL_INGEST_MODEL` label you configured — which is exactly the model you selected.

## Sessions & observability

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_LLM_TIMEOUT` | `1200` | Per-call CLI timeout in seconds. Raise it for opus or large raw files. |
| `CITADEL_HERMETIC` | `1` | Hermetic agent sessions: append the backend's session-isolation flag (claude `--bare` — skips user hooks/`CLAUDE.md`/MCP discovery) so your personal agent config never leaks into ingest. Only passed when the installed binary advertises the flag in `--help` (older CLIs run unchanged); `0` deliberately runs sessions with your personal config. copilot/agy have no such flag today. An auth-shaped failure under hermetic mode is retried once
automatically without the flag, so this knob is a way to skip that retry rather than a hard
prerequisite. **Set it to `0` if every session fails on authentication while the CLI works interactively** — on some setups (managed containers, an `apiKeyHelper`) the skipped personal config is where the credentials live; see [troubleshooting](troubleshooting.md#every-session-fails-with-an-authentication-error-but-the-cli-works-when-i-run-it-myself). |
| `CITADEL_LLM_LOG_DIR` | (off) | Write one transcript per source (prompt + full CLI stdout/stderr + exit code + duration). Relative paths resolve under the workspace root. **Local-only — keep out of VCS** (transcripts can contain source content). CLI flag: `--log-dir`. |
| `CITADEL_LLM_VERBOSE` | `0` | `1`/`true` streams each session's output live. CLI flag: `-v`. |

## Serving (MCP)

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_HTTP_TOKEN` | (none) | The bearer token `citadel serve --http` requires. It refuses to start without one (or with fewer than 16 characters), and every request must send `Authorization: Bearer <token>` — there is no unauthenticated HTTP mode. Generate one: `python -c "import secrets; print(secrets.token_urlsafe(32))"`. Unused by the stdio server. |
| `CITADEL_HTTP_HOST` | `127.0.0.1` | Bind address for `--http`. A non-loopback bind warns: the transport is plain HTTP, so prefer a loopback bind behind a TLS-terminating tunnel (cloudflared / tailscale / `ssh -R`). CLI flag: `--host`. |
| `CITADEL_HTTP_PORT` | `8765` | Bind port for `--http`. CLI flag: `--port`. |
| `CITADEL_HTTP_PATH` | `/mcp` | MCP endpoint path for `--http`. CLI flag: `--path`. |
| `CITADEL_HTTP_READ_ONLY` | `0` | `1` disables the two mutating tools (`wiki_capture`, `wiki_ingest`) on the HTTP server — the eleven readers stay, and the writers answer with a refusal string. CLI flag: `--read-only`. |
| `CITADEL_HTTP_ALLOWED_HOSTS` | (derived) | The `Host` header values the HTTP server accepts (DNS-rebinding protection). Unset derives them from the bind address — right for a direct loopback bind, wrong as soon as a name is in front of it: a tunnel forwards its own hostname, so name it here (`your-tunnel.example.com`) or every request is answered `421`. A wildcard bind (`0.0.0.0`/`::`) derives nothing and **refuses to start** until this is set. `*` accepts any `Host`, for when a proxy already filters it. |
| `CITADEL_HTTP_ALLOWED_ORIGINS` | (none) | Browser `Origin` values the HTTP server admits. Unset means a request carrying ANY `Origin` is refused (`403`) — the MCP clients this serves are not browsers, so an `Origin` means a web page is driving it. Name one (`https://claude.ai`) or `*` to admit a browser-based client. |
| `CITADEL_PAGE_CACHE` | `auto` | In-memory page cache for the long-lived reader. `citadel serve` otherwise re-walks and re-parses the whole wiki on **every** MCP call; with the cache it keeps the last load and re-checks it with a stat-only walk (~4 ms vs ~700 ms at 1000 pages), and search reuses that snapshot's term-frequency tables (a 1000-page `wiki_search` drops from ~1.4 s to ~50 ms). Nothing is persisted — the wiki stays the database, the filesystem is consulted on every call, and any change (edit, add, delete, rename, or a same-length rewrite) re-reads. `auto` = on in `citadel serve` only; `1` = on wherever citadel reads the wiki; `0` = never. Ingest and curate always read from disk, whatever this says. |

## What gets ingested

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_WIKI_LANG` | `en` | Target language for all wiki prose, titles, headings, tags — regardless of the sources' languages. Verbatim quotes and proper nouns stay in the original. |
| `CITADEL_IMAGE_SUPPORT` | `1` | Read recognized images (`.png`/`.jpg`/…) visually instead of rejecting them as binary. `0` keeps images out of the wiki. |
| `CITADEL_PDF_MODE` | `text` | `text` ingests body text only; `images` also has the agent look at figures/diagrams/charts (needs a backend whose reader renders PDF pages). |
| `CITADEL_PDF_TEXT` | `auto` | The pypdf text-layer pre-pass (pypdf ships as a bundled runtime dep — no extra install): PDFs ingest via an extracted, content-addressed cached text layer (`.citadel_pdftext/` next to the wiki), giving real `lines A-B` locators that `lint`/`wiki_raw`/the viewer verify offline — and letting large PDFs chunk. `auto` uses it when [pypdf](https://pypi.org/project/pypdf/) imports (it does by default); `1` forces it (per-source fallback + `doctor` WARN if pypdf was force-removed); `0` forces agent-native PDF reading (`p. N` locators, agent-verified). Scanned/encrypted/unparsable PDFs always fall back to agent-native reading. |
| `CITADEL_STYLE_PROFILES` | `0` | When `1`, first-person sources also yield attributed, dated, cited opinions + a per-person writing-style profile. Leave off for many-person corpora. |
| `CITADEL_JOBS` | `1` | How many sources ingest folds in **concurrently** (`citadel ingest --jobs N` overrides it per run). `1` is the serial behavior citadel has always had. Above 1, each source still gets its own staging copy and its own all-or-nothing promote — promotes are serialized and checked against the wiki state the source was cloned from, and a source that raced another over the same page is re-run serially before the run ends (reported as *Re-run serially*). The cost is **cross-linking**, not safety: concurrent sessions cannot see each other's new pages, so they link less richly and can create two pages for one topic (a later `citadel curate` pass is the designed cleanup). Best on a large backlog of unrelated sources; keep `1` when the corpus is one connected topic. Both `citadel ingest --jobs N` and `citadel refresh --jobs N` override it per run; `curate` is always serial — its clusters share pages by construction, so nearly every pair would race. |
| `CITADEL_MAX_SOURCE_CHARS` | `300000` | A source longer than this is ingested over several sequential passes that merge into earlier pages. `0` disables chunking. Images — and PDFs without an extracted text layer — are never chunked. |
| `CITADEL_RESUME` | `1` | Resume checkpoints for those chunked sources: each completed segment banks the delta it produced (`.citadel_resume/` next to the wiki), so a run that dies at segment N continues there next time instead of re-buying segments 1…N-1. Promotion stays all-or-nothing — nothing partial ever reaches the wiki — and every guard (changed source/model/rules/knobs, a page changed underneath, a replay that no longer validates) falls back to a full restart. `0` turns it off; only chunked sources ever write one. |
| `CITADEL_DEDUP_BY_BASENAME` | `1` | When several same-folder files share a basename and are all export formats (e.g. `report.pptx` + `report.pdf`), ingest one (PDF → modern Office → legacy) and record the rest as skipped duplicates. |
| `CITADEL_IGNORE_PATTERNS` | (built-in OS/junk globs) | Case-insensitive globs skipped at discovery (`Thumbs.db`, `.DS_Store`, `~$` locks, editor swap/backup files). A comma/newline list **replaces** the defaults; a `+` prefix **extends** them. |
| `CITADEL_MAX_SOURCE_BYTES` | `0` (no limit) | Discovery **size** ceiling, in bytes — the complement to the name-matching patterns above. A raw file over it is skipped from the walk's own stat: never opened, never hashed, never ingested, and never recorded in the manifest or the failures catalog. It is *reported*, though — the run report's *Oversized* section and `citadel status`' *Oversized* bucket — so nothing is dropped silently. Set it when a raw root also holds machine data (a folder of multi-GB `.tdms` sensor dumps is useless to a wiki but expensive to scan: every untracked candidate is stream-hashed in full before anything can classify it as unreadable binary). Off by default, because silently skipping a large-but-legitimate source (a 2 GB lecture recording, a scanned archive PDF) would be worse than a slow scan. An explicitly named path (`citadel ingest big.tdms`) bypasses it — explicit always wins — and an already-ingested source that later crosses the ceiling stays in the wiki, it just stops being re-checked. |

## Audio/video sources (whisper)

Opt-in transcript ingest: a recognized recording (`.mp3`/`.wav`/`.m4a`/`.mp4`/`.mkv`/…) is
transcribed **once** through a local whisper-class CLI — a shell-out seam exactly like the agent
CLI, no SDK and no API key — and the agent session reads the `[HH:MM:SS]`-stamped transcript while
citing the original media file. The transcript is cached content-addressed (by the file's sha256)
in `.citadel_transcripts/` next to the wiki dir, and doubles as the offline verification text:
`citadel lint` and `wiki_raw`/`citadel raw` resolve a citation's `lines A-B` locator against it.
The binary must speak the openai-whisper flag convention (`<file> --output_format srt
--output_dir <dir>`) — [openai-whisper](https://github.com/openai/whisper),
[whisper-ctranslate2](https://github.com/Softcatala/whisper-ctranslate2), and
[mlx_whisper](https://pypi.org/project/mlx-whisper/) qualify as-is; whisper.cpp needs a small
wrapper script that maps the flags. `citadel doctor` warns when the knob is on but the binary is
missing.

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_AUDIO_SUPPORT` | `0` | `1` transcribes recognized audio/video files and ingests the transcript. Off, they are recorded as unreadable (like images with `CITADEL_IMAGE_SUPPORT=0`). |
| `CITADEL_WHISPER_CLI` | `whisper` | The whisper-class binary: a PATH name or an absolute path (this one knob is both selector and override). |
| `CITADEL_WHISPER_MODEL` | (CLI default) | Passed as `--model` (e.g. `turbo` \| `small` \| `large-v3`). Switching models does not invalidate the cache — delete the `.citadel_transcripts/` entry and `ingest --force` the file to re-transcribe. |
| `CITADEL_WHISPER_TIMEOUT` | `3600` | Per-file transcription timeout in seconds (separate from `CITADEL_LLM_TIMEOUT` — CPU transcription of long recordings is slow). |

## Git-repository sources

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_REPO_SUPPORT` | `1` | A `raw/` sub-folder that is a git checkout (or carries a `.citadelsource` marker) is ingested as ONE source: a size-capped digest of its high-signal files, tracked by HEAD commit. `0` falls back to per-file ingest. |
| `CITADEL_REPO_DIGEST_MAX_CHARS` | `120000` | Total character budget for one repo digest. |
| `CITADEL_REPO_PER_FILE_MAX_CHARS` | `8000` | Per-file cap inside a digest (longer files are truncated with a marker). |

## Wiki history (git)

After every run that changed the wiki (ingest or curate), citadel can commit the whole wiki
directory — pages, indexes, `log.md`, the manifest — so every change is a reviewable diff and the
wiki accumulates a long-term audit trail (much richer than `log.md`'s one-line entries: the diff
shows exactly what changed in which page, which also makes it easy to judge the quality of a
model's edits). Commits are best-effort by design: any git problem becomes a one-line note on the
run report, never a failed run. They are also always **unsigned** (`--no-gpg-sign`) — a
`commit.gpgsign=true` machine would otherwise stall every run on an interactive pinentry.

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_WIKI_GIT` | `auto` | `auto` commits only when the wiki dir is already **its own** git repository (run `git init` inside `wiki/` once to opt in). `1` additionally `git init`s the wiki dir on first use — refused (with a note) when the wiki dir sits inside another git working tree, e.g. a project checkout; `git init` it yourself to overrule. `0` never touches git. An unrecognized value falls back to `auto` and `citadel doctor`'s config check flags it (so a typo of "off" can't silently keep committing). |
| `CITADEL_WIKI_GIT_REMOTE` | (off) | Push target for the wiki-history commits: a remote NAME (e.g. `origin`) or URL (GitHub, GitLab, any git host), passed verbatim to `git push <value> HEAD` after each commit. Empty = commit locally only. A failed push is a report note, never a failed run. |

`citadel doctor` reports the layer's state (mode, whether the wiki dir is a repo, the push target).

## Paths & multi-root

Relative values resolve against the **workspace root** (not your shell's CWD); absolute values are
used as-is, so `wiki/`, `raw/`, `docs/` can live outside the workspace (e.g. a mounted network
drive). Keep `wiki/` and `raw/` under a common parent so the `## Sources` citation links stay valid.

A popular use of `CITADEL_RAW_DIRS` is a **mobile capture inbox**: a phone-synced folder (e.g. an
Obsidian vault in Dropbox) added as a second root, so clipped articles, photos of print pieces, and
screenshots land there on the go and the next `citadel ingest` folds them in. Hidden folders such
as `.obsidian/` are skipped at discovery, so a living vault is a clean source — see the README's
"Obsidian vault as a capture inbox" example.

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_WIKI_DIR` | `wiki` | The wiki bundle (the "database"). |
| `CITADEL_RAW_DIR` | `raw` | The primary raw root the agent prompt names. |
| `CITADEL_DOCS_DIR` | `docs` | Reference docs. |
| `CITADEL_RAW_DIRS` | (single `raw/`) | Comma/newline-separated list of raw roots, each walked by ingest. **Replaces** the walk list (include `raw` to keep the workspace root — `citadel doctor` warns when the primary `raw/` holds files but is missing from the list). A page citing a source in a non-sibling root cites it by absolute posix path. Deletion detection is scoped per root — an unmounted root never reads as deleted sources. |
| `CITADEL_WORKSPACE` | (walk up for `citadel.toml`) | Force the workspace root (useful for `citadel serve` launched from an arbitrary CWD). |

### The wiki is never one of its own sources

A raw root may sit **above** the wiki — `CITADEL_RAW_DIRS=T:\` with the wiki at
`T:\llmWiki\data-science\wiki` is a normal way to say "scan this whole drive". Discovery prunes the
wiki directory out of that walk (it is generated output, never a source), announces the exclusion
once per run, and sweeps any page an earlier run had already self-ingested out of the manifest and
the failures catalog. No `CITADEL_IGNORE_PATTERNS` entry is needed. `citadel doctor`'s **wiki
placement** check still WARNs about the nesting, because it costs clarity: with the wiki inside a
source tree, a stray citation *into* the wiki looks like legal provenance.

### Windows mapped drives (`T:\…`) and UNC paths

Every configured path is `resolve()`-d — that is what makes path identity (manifest keys, root
containment) unambiguous. On Windows, resolving a **mapped network drive** rewrites it into its UNC
form: `T:\team-wiki` becomes `\\fileserver\share\team-wiki`, whether your `.env` named the drive
letter or the share. That resolved path is fine as an identity, but it is a bad thing to hand a
child process: some agent CLIs refuse to run at all with a UNC working directory ("environment
blocks UNC/network paths"), and git treats the two spellings as different repositories
(`safe.directory` / `core.filemode` complaints).

So citadel remembers the spelling you actually used — the `.env` value, or the drive your shell was
on — and hands **that** to the agent CLI (`cwd` and its directory grants) and to git, while the
resolved form stays the one identity everywhere else. The alias covers the whole **subtree**, so a
default `wiki/`, `raw/`, or a relative `CITADEL_WIKI_DIR=wiki` inherits it without needing its own
entry (if `\\fileserver\share\team-wiki` and `T:\team-wiki` are the same directory, so are their
children). Nothing is guessed: an alias is only recorded when citadel already holds both spellings
of the same directory, and only when resolution turned a non-UNC path into a UNC one — on POSIX,
and for ordinary Windows paths, nothing changes at all.
`citadel doctor`'s **child paths** check names the working directory sessions will actually use, and
WARNs when only a UNC spelling is known (map the share to a drive letter and point
`CITADEL_WORKSPACE` at it, or run citadel from that drive).
