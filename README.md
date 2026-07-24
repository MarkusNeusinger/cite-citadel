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
extraction, visual image reading, opt-in whisper transcription for audio/video recordings,
multi-pass folding for oversized files, duplicate-format dedup, and a
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
refreshes pages whose sources were ingested under an older rulebook. A wiki also outlives its
models: rather than ever regenerating it after a model upgrade, `citadel refresh --limit N` re-verifies
the N sources that have gone **longest unchecked** under the current model + rules — a budget you
choose per run (e.g. part of a monthly token allowance), walking the corpus round-robin — and the
spend is visible: each session's cost/usage (as the agent CLI itself reports it) is stamped into
the manifest per source, totaled on every run report, and summed by `citadel status`. See
[`docs/maintenance.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/maintenance.md) § Refresh. For a full audit trail, `git
init` the `wiki/` folder once (or set `CITADEL_WIKI_GIT=1`): citadel then **auto-commits the wiki
after every ingest/curate run** — each change a reviewable diff — and can push to a remote
(GitHub/GitLab) via `CITADEL_WIKI_GIT_REMOTE`. See
[`docs/configuration.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/configuration.md) § Wiki history.

### Example: an Obsidian vault as a capture inbox

The reverse direction works too — an Obsidian vault can be a **raw input root**, which makes
capturing on the go trivial: clip articles to markdown on your phone (e.g. the
[Obsidian Web Clipper](https://obsidian.md/clipper), whose frontmatter stamps URL, author, and date
into the file — provenance that survives even when the link later dies), snap photos of print
articles, drop in screenshots, and let the vault sync (Dropbox, Syncthing, …). Then add it as a
second raw root in `.env`:

```dotenv
CITADEL_RAW_DIRS=raw, ~/Dropbox/wiki-inbox
```

The vault needs no discipline: hidden folders like `.obsidian/` are skipped at discovery, a note you
later edit is picked up as a reconcile (stale facts updated, not appended to), a note you move is
recognized by content instead of re-ingested, photos/screenshots are read visually
(`CITADEL_IMAGE_SUPPORT`), and voice memos fold in as `[HH:MM:SS]`-stamped transcripts
(`CITADEL_AUDIO_SUPPORT` + a local whisper CLI, opt-in). The same setup turns *cleaning up an old, messy vault* into a single
ingest: point a raw root at it and citadel distills it into a cited wiki — sources are read-only,
so the vault itself is never touched. Just keep the direction straight: a vault is **input**;
don't let Obsidian write into `wiki/` (browsing it there is fine, but the generated indexes are
citadel's to regenerate).

## Test corpora

Nine synthetic corpora live under [`corpora/`](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora),
each ingestible on its own or all together and each shipping its own committed, CI-linted showcase
wiki at `corpora/<name>/wiki/`:

- **[beverages](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/beverages)** — the everyday coffee + tea showcase: overlapping facts that repeat, contradict, and hide in one place, plus a planted false sourced claim.
- **[kelvarra](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/kelvarra)** — a coherent fictional world whose facts contradict reality, graded to appear as stated, cited, never corrected.
- **[leuchtfeuer](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/leuchtfeuer)** — a three-year programme ingested in dated waves: reconcile / delete / force, temporal supersession, German→English, attributed opinions.
- **[pemberley](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/pemberley)** — all of *Pride and Prejudice* as one ~730k-char source: large-source multi-segment chunking, relationship extraction, narrative supersession.
- **[injection-resistance](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/injection-resistance)** — mundane documents with adversarial instructions embedded, which the agent must treat as content and never execute.
- **[clockwork](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/clockwork)** — a whole git repository folded in as one digest (`CITADEL_REPO_SUPPORT`), with a second commit driving repo-reconcile: folder-keyed provenance and a documented default superseded.
- **[flurfunk](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/flurfunk)** — informal genres (a chat export, a tweet thread, an interview, a job application, a forum thread): attribution kept intact ("X said Y" ≠ "Y is true"), in-thread reversal, and a CV timeline.
- **[gazette](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/gazette)** — PDF sources (deterministically generated by a committed stdlib script): grades `CITADEL_PDF_MODE` text-vs-images (a figure-only number and an image-only page appear only when figures are read), the academic-publications genre, and references-are-not-sources.
- **[kontor](https://github.com/MarkusNeusinger/cite-citadel/tree/main/corpora/kontor)** — binary Office documents (OOXML `.pptx`/`.docx`/`.xlsx` + legacy OLE `.doc`/`.ppt`/`.xls`, deterministically generated by a committed stdlib script): the Office text-extraction path, an embedded-chart **image delta** (`CITADEL_IMAGE_SUPPORT`), dedup-by-basename, and ignore-patterns.

> **These are test inputs, not reference material.** Every wiki here is machine-generated by an LLM
> agent from the raw sources, and some corpora deliberately contain planted errors, contradictions,
> or entirely fictional "facts" — do not treat any of them as real-world knowledge.

**See it without running anything:** browse a showcase wiki on GitHub (e.g.
[`corpora/beverages/wiki/index.md`](https://github.com/MarkusNeusinger/cite-citadel/blob/main/corpora/beverages/wiki/index.md))
or the interactive **[live demo gallery](https://markusneusinger.github.io/cite-citadel/)** — one
viewer per corpus. `verify-corpus` grades each against a hidden answer key it never sees; per-corpus
detail lives in each `corpora/<name>/README.md` and `CLAUDE.md`.

### Coverage matrix — which corpus exercises which capability

Each corpus targets a few capabilities hard rather than all of them shallowly; together they cover
the pipeline. `●` = a primary, load-bearing test of that capability; `○` = present as a secondary
check. (Bev = beverages, Kel = kelvarra, Leu = leuchtfeuer, Pem = pemberley, Inj =
injection-resistance, Clk = clockwork, Flu = flurfunk, Gaz = gazette, Kon = kontor.)

| capability | Bev | Kel | Leu | Pem | Inj | Clk | Flu | Gaz | Kon |
| --- | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: | :-: |
| Single-source facts survive + cited | ● | ● | ● | ● | ● | ● | ● | ● | ● |
| Cross-source merge / co-citation | ● | ● | ● | ● | ○ | | ● | ○ | ● |
| Multi-source synthesis (answer needs ≥2 files) | ● | ○ | ● | | ● | | ○ | ● | ● |
| Contradictions surfaced, not silently resolved | ● | ● | ● | ○ | | ● | ○ | ● | ● |
| Near-miss / approximation ≠ contradiction | ● | | ○ | | ● | ○ | ● | ○ | ● |
| Counterfactuals kept as stated + cited | ○ | ● | ● | ○ | | | | | |
| Temporal supersession (dated change) | ● | ● | ● | ● | ○ | ● | ● | | ● |
| Delete / reconcile / force lifecycle | | | ● | | | ● | | | |
| Whole-repo digest | | | | | | ● | | | |
| Large-source multi-segment chunking | | | | ● | | | | | |
| Attribution ("X said Y" ≠ "Y is true") | | | ● | ● | ● | | ● | ● | ● |
| Injection treated as content, never executed | | | | | ● | | | | |
| Image-only fact behind a mode flag (PDF / Office media) | | | | | | | | ● | ● |
| Office text extraction (OOXML + legacy OLE) | | | | | | | | | ● |
| Dedup-by-basename + ignore-patterns | | | | | | | | | ● |
| Cross-language carry-through (DE→EN) | | | ● | | | | | | |
| Entity-spelling variance → one node | | | ○ | | ● | | | ● | ● |
| Relative-date resolution | | ● | ○ | | | | ○ | ○ | |
| Distractor noise / filler resistance | ● | ○ | ● | ● | ○ | | ● | ○ | ○ |
| Locator precision (lines / § / page) | ● | ○ | ○ | ● | | ○ | | ● | ● |
| Abbreviations (defined + undefined-flagged) | ● | ● | ● | | | | | | |

### Model results — Opus / Sonnet / Haiku

The same corpora double as a **model benchmark**: because grading is retrieval-first against a hidden
answer key, a stronger and a weaker model produce measurably different wikis from identical inputs.
The [`bench-model`](https://github.com/MarkusNeusinger/cite-citadel/tree/main/.claude/skills/bench-model)
skill ingests a corpus with a pinned `CITADEL_INGEST_MODEL`, grades it, and applies a discriminative
tier (locator precision, oblique-query retrieval, merge quality, judgment delta on
contradictions + planted-false claims). It writes a per-run results file whose rows populate the cells
below.

Scoring per cell: **hard** = passes every hard gate of that corpus's ground-truth; **degrades** =
structurally valid but misses judgment-heavy work (uncaught contradictions, an adopted false claim,
partial supersession); **fail** = a hard structural gate broke (a fabricated source, a non-zero
`check`/`lint`); **—** = not yet benchmarked on the current (hardened) corpora.

| corpus | Opus | Sonnet | Haiku |
| --- | :-: | :-: | :-: |
| beverages | — | hard¹ | degrades² |
| kelvarra | hard² | hard² | fail² |
| leuchtfeuer | — | — | — |
| pemberley | — | — | — |
| injection-resistance | hard² | hard² | degrades² |
| clockwork | — | — | — |
| flurfunk | — | — | degrades² |
| gazette | hard² | hard² | degrades² |
| kontor | hard² | degrades² | degrades² |

¹ From the 2026-07 audit on the pre-hardening beverages corpus: Sonnet cleared the structural +
judgment gates with no wiki-defects on its subset. The hardened corpus has not been re-run on
Sonnet yet.

² From the 2026-07 three-tier benchmark: one pinned-model ingest per cell into a fresh sandbox
(gazette in images PDF mode, kontor with image support on), graded strictly against the hidden
answer key. The one-line rationales: kelvarra × Haiku **fail** = two abbreviation expansions
invented and cited as if sourced (plus two dropped counterfactuals); kontor × Opus is the only run
that read the embedded chart (the pixels-only 34.2 % gross margin) *and* surfaced the 142-vs-138
headcount conflict, both of which the kontor Sonnet ingests missed; every other Opus/Sonnet cell
sits at or near its corpus's ceiling. Cells still `—` are open — run `bench-model <corpus>
<model>` to fill one.

#### How the three tiers actually differ

**Opus is not uniformly better** — the tiers separate on different axes, and whether the next tier
up buys anything depends on the corpus.

**Haiku** is structurally reliable everywhere: `check`/`lint` green, every fact cited, dedup and
ignore-patterns honored, and it resisted every embedded injection. It degrades on judgment and
craft, and in one characteristic way it *breaks*: where a source leaves a gap that invites
completion, it fabricates — kelvarra's never-expanded abbreviation got an invented full name cited
as if sourced (the benchmark's only **fail**). Beyond that it drops facts buried in compound
sentences or terse intraday reversals, flags a rounded restatement as a contradiction while missing
a real one, writes locators that don't resolve (~half its sample: truncated or invented headings),
fragments entities into thin micro-pages, and reads nothing visual.

**Sonnet** adds the judgment layer: on kelvarra, gazette, and injection-resistance it is at or near
each corpus's ceiling — all seven counterfactuals preserved-as-stated and cited, contradictions
surfaced as callouts, the preprint attributed and flagged not-peer-reviewed, boilerplate excluded,
locator samples 10/10 precise. Where Haiku fabricates, Sonnet leaves the gap honest (the
abbreviation stays unexpanded). Its measured weakness is reliability on cross-modal work: in two of
three kontor ingests it never opened the extracted chart image (missing the pixels-only 34.2 %) and
let the 142-vs-138 headcount conflict coexist unflagged — though the committed kontor showcase (also
Sonnet) caught the chart, so this is a reliability gap, not a hard capability wall.

**Opus** did the hardest cross-modal work in one pass: it read the embedded chart *and* made the
headcount tension explicit, catching all six kontor judgment traps, and added judgment beyond the
answer key elsewhere (a second, temporal contradiction in gazette plus an honestly-labeled physics
resolution of the area conflict). But it is not strictly better: Sonnet's kelvarra locator sample
was cleaner (10/10 vs 8/9), Sonnet documented all four injections where Opus documented two, and
Opus half-leaked one gazette boilerplate line that Sonnet kept out entirely.

**So: does it depend on the corpus? Yes.** The judgment corpora (kelvarra, gazette,
injection-resistance) separate Haiku from Sonnet and are saturated above that; kontor — vision plus
cross-source diligence over binary sources — is currently the only corpus that separates Sonnet
from Opus; beverages' stretch tier (locator precision, fragmentation) separates Haiku's craft even
when its hard gates hold. One caveat: each cell is a single non-deterministic ingest, so neighboring
cells should be read as ties unless the delta reproduces (kontor × Sonnet's missed chart did, twice).

A defect **every** tier shares points at the rulebook, not the model: all three models
canonicalized a merged vendor to a minority spelling from someone's meeting notes, and both strong
tiers anchored citations to headings that legacy-OLE extracts don't have — both are explicit rules
now (`core.md` canonical-name direction, `formats/office.md` OLE line locators). Conversely,
Haiku's remaining failures (invented expansions, dropped buried facts, unread charts) persisted
under already-clarified rules — that is capability, not clarity: rules help the models that can
follow them.

Practical default: `CITADEL_INGEST_MODEL=sonnet`. Step up to Opus when sources are image-heavy
(`CITADEL_IMAGE_SUPPORT=1`, `CITADEL_PDF_MODE=images`) and the numbers in charts matter. Haiku
builds a valid, findable, fully-cited wiki — but expect missed contradictions, sloppy locators, and
the occasional confident invention where a source leaves a blank.

## MCP server

`citadel serve` exposes **thirteen tools** over stdio — eleven read-only (`wiki_search`,
`wiki_define`, `wiki_read`, `wiki_raw`, `wiki_neighbors`, `wiki_index`, `wiki_sources`,
`wiki_tags`, `wiki_validate`, `wiki_lint`, `wiki_status`) and two mutating: `wiki_capture` (append
an attributed note from the conversation to the raw/ capture log — the next ingest folds it in
with real citations; see
[docs/capture.md](https://github.com/MarkusNeusinger/cite-citadel/blob/main/docs/capture.md)) and
`wiki_ingest` (the only tool that writes the wiki) — each with MCP behavior annotations
(`readOnlyHint` etc.) so a client can tell them apart. Every tool has a CLI counterpart
(`citadel read`, `citadel index`, `citadel capture`, …), so an AI without MCP access can do
everything through the shell.

Wire it into any stdio MCP client (Claude Desktop, Claude Code, a generic stdio client) by launching
`citadel serve` (portably: `uv run python -m citadel serve`) with `CITADEL_WORKSPACE` set to your
workspace. An AI then `wiki_index()`s to orient,
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
