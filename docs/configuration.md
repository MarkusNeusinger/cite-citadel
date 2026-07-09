# Configuration reference

Every cite-citadel setting is a `CITADEL_*` (or provider) environment variable. `citadel init`
scaffolds a workspace `.env` that is auto-loaded (process env > workspace `.env` > packaged
defaults). This page is the reference for pip users who never see the template file.

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
| `CITADEL_LLM_CLI` | `claude` | Which CLI ingest shells out to: `claude` \| `copilot` \| `gemini`. Run agentically (claude with acceptEdits + allowlist, copilot `--allow-all-tools`, gemini `--approval-mode yolo`); the CLI must be installed and logged in. |
| `CITADEL_INGEST_MODEL` | `sonnet` | Model for the `claude` backend — an alias (`sonnet`/`opus`/`haiku`) or full id. copilot/gemini use their own default. |
| `CITADEL_CURATE_MODEL` | (reuses ingest model) | Cheaper/faster model for `citadel curate` sessions (claude backend, via `--model`). |
| `CLAUDE_CODE_PATH` / `COPILOT_CLI_PATH` / `GEMINI_CLI_PATH` | (PATH lookup) | Override the CLI binary path when it isn't on `PATH`. |
| `COPILOT_MODEL` / `GEMINI_MODEL` | (unset) | Concrete model id recorded per source for those backends (also covers a local/Ollama model). |

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

**GitHub Copilot → local model.** OpenAI-compatible surface — note the `/v1`. citadel's copilot path
passes no `--model`, so **`COPILOT_MODEL` is the selector** (`CITADEL_INGEST_MODEL` is ignored here);
this is proven for the non-interactive `copilot -p` that citadel spawns:

```sh
COPILOT_PROVIDER_BASE_URL=http://<host>:11434/v1
COPILOT_PROVIDER_API_KEY=ollama
COPILOT_PROVIDER_WIRE_API=completions
COPILOT_MODEL=qwen3.6:27b
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
$env:COPILOT_MODEL = "qwen3.6:27b"
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
- The Gemini CLI has no first-party local-model path today, so it is not offered here.

## Sessions & observability

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_LLM_TIMEOUT` | `1200` | Per-call CLI timeout in seconds. Raise it for opus or large raw files. |
| `CITADEL_LLM_LOG_DIR` | (off) | Write one transcript per source (prompt + full CLI stdout/stderr + exit code + duration). Relative paths resolve under the workspace root. **Local-only — keep out of VCS** (transcripts can contain source content). CLI flag: `--log-dir`. |
| `CITADEL_LLM_VERBOSE` | `0` | `1`/`true` streams each session's output live. CLI flag: `-v`. |

## What gets ingested

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_WIKI_LANG` | `en` | Target language for all wiki prose, titles, headings, tags — regardless of the sources' languages. Verbatim quotes and proper nouns stay in the original. |
| `CITADEL_IMAGE_SUPPORT` | `1` | Read recognized images (`.png`/`.jpg`/…) visually instead of rejecting them as binary. `0` keeps images out of the wiki. |
| `CITADEL_PDF_MODE` | `text` | `text` ingests body text only; `images` also has the agent look at figures/diagrams/charts (needs a backend whose reader renders PDF pages). |
| `CITADEL_STYLE_PROFILES` | `0` | When `1`, first-person sources also yield attributed, dated, cited opinions + a per-person writing-style profile. Leave off for many-person corpora. |
| `CITADEL_MAX_SOURCE_CHARS` | `300000` | A source longer than this is ingested over several sequential passes that merge into earlier pages. `0` disables chunking. PDFs/images are never chunked. |
| `CITADEL_DEDUP_BY_BASENAME` | `1` | When several same-folder files share a basename and are all export formats (e.g. `report.pptx` + `report.pdf`), ingest one (PDF → modern Office → legacy) and record the rest as skipped duplicates. |
| `CITADEL_IGNORE_PATTERNS` | (built-in OS/junk globs) | Case-insensitive globs skipped at discovery (`Thumbs.db`, `.DS_Store`, `~$` locks, editor swap/backup files). A comma/newline list **replaces** the defaults; a `+` prefix **extends** them. |

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
| `CITADEL_WIKI_GIT` | `auto` | `auto` commits only when the wiki dir is already **its own** git repository (run `git init` inside `wiki/` once to opt in). `1` additionally `git init`s the wiki dir on first use — refused (with a note) when the wiki dir sits inside another git working tree, e.g. a project checkout; `git init` it yourself to overrule. `0` never touches git. |
| `CITADEL_WIKI_GIT_REMOTE` | (off) | Push target for the wiki-history commits: a remote NAME (e.g. `origin`) or URL (GitHub, GitLab, any git host), passed verbatim to `git push <value> HEAD` after each commit. Empty = commit locally only. A failed push is a report note, never a failed run. |

`citadel doctor` reports the layer's state (mode, whether the wiki dir is a repo, the push target).

## Paths & multi-root

Relative values resolve against the **workspace root** (not your shell's CWD); absolute values are
used as-is, so `wiki/`, `raw/`, `docs/` can live outside the workspace (e.g. a mounted network
drive). Keep `wiki/` and `raw/` under a common parent so the `## Sources` citation links stay valid.

| Variable | Default | What it does |
|----------|---------|--------------|
| `CITADEL_WIKI_DIR` | `wiki` | The wiki bundle (the "database"). |
| `CITADEL_RAW_DIR` | `raw` | The primary raw root the agent prompt names. |
| `CITADEL_DOCS_DIR` | `docs` | Reference docs. |
| `CITADEL_RAW_DIRS` | (single `raw/`) | Comma/newline-separated list of raw roots, each walked by ingest. **Replaces** the walk list (include `raw` to keep the workspace root). A page citing a source in a non-sibling root cites it by absolute posix path. Deletion detection is scoped per root — an unmounted root never reads as deleted sources. |
| `CITADEL_WORKSPACE` | (walk up for `citadel.toml`) | Force the workspace root (useful for `citadel serve` launched from an arbitrary CWD). |
