# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Ranked BM25 search behind the unchanged `search()` seam** (the 2026-07 audit's backlog #1).
  Queries now share the offline viewer's grammar — bare terms are AND-matched (English stopwords
  exempt, so "how do you brew coffee" matches on *brew coffee*; a query no page fully matches is
  retried once as OR so the closest pages still surface), and `tag:x` / `type:y` tokens filter
  instead of match (tag by prefix, type exactly; an operator-only query like `type:person` lists
  the filtered pages) — closing the audit's "two divergent search implementations" finding.
  Ranking is real BM25 (term-frequency saturation, prose-field length normalization,
  Lucene-smoothed IDF) over the title 3.0 / aliases 2.5 / tags 2.0 / description 1.5 / body 1.0
  field ladder, plus the exact-phrase bonus, computed in memory per call — no persisted index,
  the wiki stays the database, zero new dependencies. The audit-scoped SQLite FTS5 route was
  built first and rejected on measurement: FTS5's `bm25()` clamps the IDF of any term appearing
  in more than half the corpus to ~0, so in a topical wiki the topic word ("coffee" in a coffee
  wiki) degenerated every score to noise; the Python scorer keeps IDF strictly positive, and
  "how do you brew coffee" now ranks the brewing page first instead of losing it entirely.
  Signature, MCP surface, and the `pages=` tag-filter seam are unchanged.

### Added

- **`citadel refresh` — budget-controlled re-verification of the least-recently-checked sources
  (the third lifecycle beside ingest and curate).** Every successful agent session now stamps its
  source's manifest entry with an `ingested_at` last-checked time (carried unchanged across moves
  and cache re-stamps — it only ever means "a model last verified this source then"). `refresh`
  orders the manifest by that stamp — oldest first, a never-stamped entry counting as oldest — and
  hands the first `--limit N` sources (default 1; each source = one agent session, so N *is* the
  per-run budget) to a forced path-scoped ingest: one `reconcile` session per source under the
  **current** model + rules, all-or-nothing staging, re-stamped on success so the source rotates to
  the back of the queue and repeated runs walk the corpus round-robin with no persisted queue. The
  point: a wiki that outlives its models never needs regenerating — after a model upgrade you spend
  a self-chosen slice of the monthly token allowance re-checking the oldest imports instead.
  `--dry-run` prints the head of the queue with zero sessions; `--min-age-days D` makes a scheduled
  run self-limiting (a no-op once everything was checked within D days); `citadel status` now shows
  each ingested source's `checked YYYY-MM-DD` date.
- **Cloud-placeholder detection for unreadable sources.** A file whose bytes read as 100% NUL —
  the signature of a Dropbox/OneDrive "online-only" placeholder seen through WSL or a network
  share — is now reported with a targeted hint (*"reads as all NUL bytes - likely a cloud-only
  placeholder; make it available offline"*) in the run report, `citadel status`, `log.md`, and the
  `sources/index.md` failures table, instead of the generic "no extractable text" message. Unlike a
  genuine binary it is **never stat-cached as done**: hydration restores the real content without
  changing size or mtime, so a placeholder stays visibly stuck across runs and ingests
  automatically once made available offline (previously the stat quick check could skip the
  hydrated file forever).

## [0.4.0] - 2026-07-16

### Changed

- **All nine committed showcase wikis rebuilt under the current rulebook** (sonnet, in-place per
  the verify-corpus regeneration recipe — leuchtfeuer's three-wave replay, clockwork's two-commit
  repo protocol, gazette in images mode, kontor with image support, flurfunk with style profiles,
  pemberley's three chunked segment passes). The refreshed wikis carry the recent rule improvements
  visibly: plan-vs-actual figures co-stated in one cited sentence (kontor's 142-vs-138), embedded
  Office chart images read and cited with slide locators, and workplace-chat threads recorded per
  the new `genres/chat.md` (live fact = thread end state with a dated arc). Every wiki re-graded
  against its hidden ground truth — all nine commit-worthy, `check`/`lint` clean.

### Added

- **New Office-documents test corpus — `kontor` — with a committed, images-mode showcase wiki (the ninth corpus).** Eleven files generated deterministically by a committed stdlib-only script `make_office.py` (no python-pptx/docx/openpyxl/PIL): OOXML `.pptx` (slides + speaker notes + an embedded chart), `.docx` (paragraphs + a table), and `.xlsx` (two sheets), plus legacy OLE `.doc`/`.ppt`/`.xls` (97–2003 compound files), a dedup pair, and OS/Office junk. First end-to-end coverage of the Office extraction path — `citadel/extract.py` (OOXML) and `citadel/extract_ole.py` (CFBF salvage) — with a new **image delta**: the chart's `GROSS MARGIN 34.2%` lives only in pixels, so it is **absent-and-honest** with `CITADEL_IMAGE_SUPPORT=0` and **present-and-cited** with images on. Also exercises `CITADEL_DEDUP_BY_BASENAME` (a `.doc` twin skipped for its `.docx`) and `CITADEL_IGNORE_PATTERNS` (Thumbs.db/desktop.ini/lock files skipped), and plants the usual discriminative judgment traps (a 142-vs-138 contradiction, a tentative Lisbon warehouse, entity-variance merges, a near-miss ≠ contradiction, a dated supersession). Fully fictional (Aldervik Kontor) — nothing copied.
- **New PDF test corpus — `gazette` — with a committed, images-mode showcase wiki.** Five sources (four PDFs generated deterministically by a committed stdlib-only script
  `make_pdfs.py`, plus a markdown control) exercise the PDF path end-to-end for the first time: the
  `%PDF-` magic-sniff dispatch, `formats/pdf.md`, page locators, and — the headline — the
  `CITADEL_PDF_MODE` **text-vs-images** delta. A key number (`0.42 arcsec`) lives only inside a chart
  raster and a whole notice page is image-only, so both are **absent-and-honest** in text mode and
  **present-and-cited** in images mode; the corpus also grades the academic-publications genre and
  that a preprint's bibliography never materializes as fabricated raw sources. The PDFs report real
  public-domain science (tardigrade cryptobiosis, the 2007 FOTON-M3 orbit experiment) in original
  prose — nothing copied.
- **Two new test corpora — `clockwork` and `flurfunk` — with committed, graded showcase wikis.** `clockwork` is the first corpus whose source is a whole **git repository**,
  folded in as ONE digest (`CITADEL_REPO_SUPPORT`, `kind=repo`), then re-ingested after a second
  commit changes a documented default (`max_retries` 3 → 5) — the first end-to-end coverage of
  `kind=repo`/`repo-reconcile`, folder-keyed provenance, and a `type: System` page for an external
  store. Its committed inputs are the `repo-src/` + `repo-src-wave2/` trees the sandbox materializes
  into a checkout (a git repo can't be committed inside this repo). `flurfunk` is seven
  **informal-genre** sources — a Slack export, an X/Twitter thread, a podcast interview, a job
  application (cover letter + CV), a forum thread, and an announcement — grading **attribution** ("X
  said Y" ≠ "Y is true"), an in-thread decision reversal, a quote-tweet negative row, and CV-timeline
  completeness. Both ship a hidden `ground-truth.md`, are wired into the `verify-corpus` skill, and
  are linted by CI + published in the Pages gallery.
- **verify-corpus Mode C — an end-to-end grader for the `curate` lifecycle.** Modes A/B grade
  ingest; Mode C grades `citadel curate` end-to-end: it builds a throwaway curate-defect sandbox from
  the beverages showcase (re-stamping the manifest and neutralizing the showcase's own open
  contradictions so the baseline is clean), seeds a small KNOWN set of defects (resort / orphan /
  contradiction / locator), proves `curate --dry-run` detects EXACTLY those offline (the deterministic
  tier), then runs real `kind=curate` sessions and grades that the model FIXES each defect while
  `check`/`lint` stay at exit 0 and the staged-promote arbitration (applied / NOOP / failed) matches
  reality. It is the real-session complement to the offline detector coverage in `tests/test_curate.py`.

### Changed

- **The ingest prompt now names an Office source's extracted images explicitly.** When a
  `.pptx`/`.docx`/`.xlsx` carried embedded rasters (`CITADEL_IMAGE_SUPPORT=1`), the session
  variables gain an "Extracted images — VIEW each of these" bullet naming the `media/` folder and
  its files. Previously only `formats/office.md` said such a folder *may* exist beside the
  extract, and in two of three benchmarked Sonnet ingests the agent concluded it didn't and never
  opened the chart (the kontor image-delta miss). Two rule additions ride along from the same
  benchmark evidence: `schema.md` § Contradictions now covers **plan-vs-actual** figure pairs
  (state both figures together, each cited, and name the difference — not strictly a
  contradiction, but a tension the reader must see), and a new **`genres/chat.md`** brief covers
  workplace-chat exports (timestamped attribution; decisions reverse in-thread, so the live fact
  is the thread's **end state**; terse decisions still count; banter stays out — the axis where
  an intraday reversal was dropped in the flurfunk benchmark).
- **Four ingest-rule clarifications from the 2026-07 three-tier model benchmark** (every corpus ×
  haiku/sonnet/opus, graded against the hidden answer keys; rule fixes were made only where the
  evidence showed a rule gap rather than a model-capability gap): `schema.md` § Locators now
  requires a `§ Heading` locator be copied **character-for-character** (leading numbering, list
  markers, trailing punctuation included — a dropped prefix does not resolve);
  `formats/office.md` now pins Office locators to **one slide/sheet per marker** (no `§ Slide 2-4`
  ranges) and bans `p. N` (the extracts have slides/notes/sheets, not pages), and explains that a
  **legacy OLE** salvage is a flat run of text with no headings — cite `lines A-B`, never an
  invented `§ Slide N` anchor; and `core.md` gained the **canonicalize-a-merged-entity-to-its-own-
  name** rule (title from the entity's own material or the majority of sources; one-off variants
  become aliases — retroactively, retitling the page when the authoritative spelling arrives in a
  later source) after all three model tiers picked a minority spelling from meeting notes.
- **README model-results matrix filled from the 2026-07 three-tier benchmark** (14 graded runs:
  6 corpora × haiku plus kelvarra/injection-resistance/gazette/kontor × sonnet+opus), a `fail`
  rubric value (a hard structural gate broke), and a new **"How the three tiers actually differ"**
  comparison: haiku degrades on judgment/craft and fabricates into gaps; sonnet matches opus on the
  text-judgment corpora; opus separates only on kontor's cross-modal work (the pixels-only chart
  figure + the cross-source headcount conflict); per-corpus saturation noted.
- **README trimmed to ~175 lines (from ~220) with no information loss.** Cut content that only
  duplicated `docs/` or `CLAUDE.md`: the MCP client JSON block (byte-identical to the one in
  `docs/mcp.md`) became a short pointer to that page; the per-corpus write-up collapsed to one line
  per corpus plus the demo-gallery link (full detail already lives in each `corpora/<name>/README.md`
  and `CLAUDE.md`); the Reference list dropped rows already linked earlier in the README (the rules
  tree, `env.example`, the per-doc links) down to the docs hub, `CLAUDE.md`, and
  CONTRIBUTING/CHANGELOG/SECURITY; and the License section's affiliation and credential-handling
  prose now defers to `NOTICE.md`. The **License & third-party tools** heading (anchored by
  `doctor.py` and `docs/configuration.md`) and every provider-terms link are unchanged.

### Fixed

- **A numeric tag no longer crashes `citadel search` / `citadel tags`.** A bare year in a page's
  tag list (`tags: [finance, 2026]`) is YAML-parsed as an int, and the IDF/scoring paths joined
  `page.tags` into a string — every search over such a wiki raised `TypeError`. `Page.tags` now
  coerces each entry to `str` (single non-list values are wrapped), fixing search, the tag map,
  and every other consumer at the source. Surfaced by the kontor model benchmark, whose budget
  page carries the `2026` tag.
- **`lines N` locator — a note that begins with a number is no longer swallowed into the range.** A
  citation like `line 21 — 1657 founding credit` parsed as the range `lines 21-1657` (the `1657` is
  the year the note describes, not a line), which `citadel lint` then flagged as out-of-range. The
  line-range separator now accepts only a hyphen (spaces allowed) or a TIGHT en/em-dash, never a
  SPACED ` — ` / ` – ` — which is a description separator — so the locator reads as the single line
  21 with the rest a note. Surfaced by the verify-corpus genre-briefs gate.
- **A malformed env knob no longer crashes every command.** A numeric `CITADEL_*` setting whose
  value is blank or not a number (e.g. `CITADEL_LLM_TIMEOUT=20 min`) used to raise at import and
  take down every subcommand; it now falls back to the knob's default and `citadel doctor` gained a
  config check that surfaces exactly which values didn't parse.
- **`citadel check` / `wiki_validate` — a nonexistent page path is now an error.** Naming a page
  that doesn't exist (a typo'd path) reported "OK — no validation issues." with exit 0; both now
  answer `error: no such page: …` (exit 1 on the CLI), so a mistyped CI invocation can't pass
  false-green.
- **`wiki_raw` / `citadel raw` — preserve heading casing in the "not a heading" hint.** When a
  `§ Heading` locator names a heading the source lacks, the error lists the available headings using
  the source's ORIGINAL casing and document order (e.g. `§ The One Rule About Temperature`) instead of
  the case-folded form the internal match set uses. Backed by a new case-preserving
  `grammar.source_heading_texts`; the case-insensitive match itself is unchanged.
- **`§ Heading` locators into bold-line sections now verify and resolve.** Many real sources (FAQs,
  exported Word/Confluence docs) delimit sections with a whole-line `**bold**` header instead of an
  ATX `#` heading. A new shared `grammar.parse_heading_line` recognizes both, so the ingest agent's
  `§ Bold Heading` citations no longer trip `citadel lint`'s locator check (42 false advisories on a
  fresh beverages build) and `wiki_raw` / `citadel raw` resolves them instead of answering "headings
  present: none". Inline or partial bold is still not a heading; the case-insensitive match is
  unchanged. Surfaced by the verify-corpus Mode-A harvest.
- **`citadel lint` — fewer advisory false positives on real ingests.** A `## See also` navigation
  list is no longer counted as a "Missing citations" paragraph (a link title such as
  `Immersion vs. Percolation Brewing` had faked a second sentence — 18 false hits on a fresh
  beverages build). The undefined-abbreviation nudge now skips fiscal-period labels (`Q1`..`Q4`,
  `H1`/`H2`) and roman numerals used in an ordinal context (`Chapter IV`), while still surfacing a
  genuine abbreviation that merely parses as a numeral (`DC`). Advisory-only; no structural gate
  changes. Surfaced by the verify-corpus Mode-A harvest.
- **`okf.slugify` transliterates accented titles instead of dropping the letters.** A title like
  `Café` slugged to `caf` and `Zürich` to `z-rich` (every non-ASCII letter became a gap), so a
  filename the ingest agent sensibly wrote (`cafe.md`) triggered a spurious `filename does not match
  slug of title` advisory. Slugify now ASCII-folds via NFKD + combining-mark stripping (`Café` →
  `cafe`, `naïve` → `naive`) with a small map for letters that do not decompose (`ß` → `ss`,
  `Œ` → `oe`). The three affected `leuchtfeuer` person pages are renamed to the improved slugs
  (`j-rn-albers` → `jorn-albers`, `sabine-kr-ger` → `sabine-kruger`, `tom-s-iglesias` →
  `tomas-iglesias`) with their inbound links and indexes repaired, so all five committed corpora
  stay advisory-clean.
- **`wiki_read` / `wiki_neighbors` / `citadel read` / `citadel neighbors` — error-text polish on the
  traversal-rejection path.** An unsafe path used to answer with a doubled prefix
  (`error: unsafe path: unsafe path: '…'`) because the callers re-wrapped the already-self-describing
  `okf.OKFError` message; the prefix now appears exactly once, on the CLI and MCP surfaces alike.
- **`wiki_search` / `citadel search --limit` — a limit `<= 0` no longer answers a factually wrong
  "No matches".** A negative/zero limit (an LLM client miscomputing the argument) sliced the hit list
  empty and asserted there were no matches; it is now treated as unset and falls back to the default
  (8), documented in the tool docstring and `--limit` help.
- **`wiki_read` / `wiki_neighbors` now normalize Windows-style backslash rel_paths.** `wiki_validate`
  already accepted `concepts\espresso.md` while the other two 404'd on the identical page; all
  rel_path-taking tools (and their CLI twins, which share the same providers) now apply the same
  backslash→slash normalization.
- **`wiki_read` / `citadel read` return generated index files verbatim.** Reading a
  frontmatter-less generated file (`index.md`, `sources/index.md`, `open-points/index.md`) used to
  prepend a spurious empty `---\n{}\n---` frontmatter block from the `okf.dump` re-serialization,
  contradicting the tool's "verbatim" contract and reading as page corruption to an AI consumer;
  the provider now returns the file text byte-for-byte (canonical pages round-trip identically).
- **`citadel doctor` raw-roots check now follows the ACTUAL ingest walk list.** It used to iterate
  the wider `source_roots()` union, so a primary `raw/` configured OUT of `CITADEL_RAW_DIRS` read as
  "reachable" while its files were silently never scanned; the check now walks `CITADEL_RAW_DIRS`
  exactly like discovery and WARNs when the excluded primary `raw/` holds files, naming the fix
  (include `raw` in `CITADEL_RAW_DIRS`).
- **Unrecognized `CITADEL_WIKI_GIT` values are no longer silent.** Anything that is not
  `0/off`, `1/init`, or `auto` still falls back to `auto` (the safe, never-creates-a-repo default),
  but the value is now surfaced by `citadel doctor`'s config check — a typo of "off" (`of`, `fasle`)
  used to silently keep auto-committing (and pushing).

### Added

- **Five new genre briefs** close the biggest coverage gaps found by the 2026-07 rules audit —
  each a one-file rules change the agent applies by content judgment, no code involved:
  `genres/publication.md` (scientific/academic papers: hedged findings stay hedged, a paper's
  own findings vs claims it cites, methods/sample caveats travel with the claim, abstract-vs-body
  gaps noted, authors/venue/year captured), `genres/contract.md` (contracts/legal/financial:
  amounts/dates/parties/defined terms verbatim, "shall" never paraphrased into "may",
  effective/termination dates as dated facts, amendments supersede with a Change-Log trace, no
  legal-advice voice), `genres/social.md` (posts and threads: author+date+platform attribution,
  thread order, engagement numbers as dated snapshots, irony is not fact, quote-posts carry two
  voices, promotional accounts quarantined), `genres/transcript.md` (multi-speaker transcripts
  incl. SRT/VTT: per-speaker attribution, unlabeled speakers stay roles, cleanup never adds
  precision, host reads/ads skipped, line-range locators), and `genres/cv.md` (CVs/applications:
  every claim self-reported and attributed, self-assessments are opinions, claims vs
  corroborating evidence, a newer CV supersedes). All five are enumerated automatically by the
  existing `genres/*.md` discovery and indexed in `citadel/rules/README.md`.
- **One exclusive run lock per workspace.** Ingest and curate now take a run lock (a
  `.citadel_run.lock` sibling of the wiki dir; stale locks from a dead process are reclaimed
  automatically), so a second concurrent mutating run fails loud instead of silently destroying the
  first one's staging and promotes. Manifest and failures-catalog saves are now atomic
  (temp-sibling + `os.replace`), so a crash mid-write can never leave a torn file behind.
- **Docs: `docs/maintenance.md` — maintain & customize.** A new user page covering `citadel curate`
  (what the second lifecycle does, when to run it, all flags including the previously undocumented
  `--retry`), `citadel status`, and the rules-customization story (`rules list|show|eject`, the
  workspace `rules/` overlay, additive `rules/local.md` house rules), linked from the docs hub and
  the README. Alongside it, `.github/copilot-instructions.md` is re-synced with `CLAUDE.md` and
  both agent docs pick up `citadel define` and `curate --retry`.
- **Wiki history: auto-commit the wiki to git after every mutating run.** A new best-effort layer
  (`citadel/wikigit.py`) commits the whole wiki directory — pages, indexes, `log.md`, the manifest —
  as ONE commit after every ingest or curate run that changed it, so every change becomes a
  reviewable diff and the wiki accumulates a long-term audit trail (the diff also makes it easy to
  judge the quality of a model's edits). `CITADEL_WIKI_GIT=auto` (default) commits only when the
  wiki dir is already its own git repository (`git init` inside `wiki/` once to opt in); `1`
  additionally `git init`s it on first use, refusing — with a note, never an error — when the wiki
  dir sits inside another git working tree (an embedded repo would confuse the outer checkout);
  `0` turns the layer off. `CITADEL_WIKI_GIT_REMOTE` names an optional push target (a remote name
  or URL — GitHub, GitLab, any git host) pushed after each commit. Everything is best-effort by
  contract: the wiki is already promoted when the commit runs, so any git problem (no binary, no
  identity, a rejected push) becomes a one-line note on the run report, never a failed run. A new
  `citadel doctor` line reports the layer's state, and the per-source staging copy now excludes a
  wiki `.git` (promote never synced hidden dirs anyway).
- **Pages now record which cite-citadel release wrote them.** `store.write_page` stamps a
  `citadel_version` frontmatter field alongside the existing `timestamp` on every write (authored
  values are overwritten, so neither can go stale or be forged), giving each page visible
  provenance: WHEN it last changed and WITH WHAT version. The refresh path for pages built by an
  older rulebook stays `citadel curate --stale-rules`, which re-runs pages whose sources were
  ingested under an older effective-rules hash — re-reading the cited raw files as part of the
  cluster.
- **`citadel doctor` now checks workspace coherence.** A new check catches the silent
  misconfiguration where `CITADEL_WIKI_DIR` and `CITADEL_RAW_DIR` sit under different parents (e.g.
  the wiki points into a corpus but the raw root is left at the default): every `../../raw/x`
  citation then resolves OUTSIDE the configured raw root, so `grammar.is_source_citation` rejects it,
  `citadel lint` reports the sources broken, and the viewer's source records lose their names/links —
  yet nothing else said the roots don't line up. The check walks the wiki's `## Sources` citations
  (read-only, O(pages), reusing the shared citation grammar) and WARNs (advisory, never FAILs) with
  the count, one offending citation and where it actually resolved, plus the fix (set
  `CITADEL_RAW_DIR` to the `raw/` tree next to the wiki, or select the workspace with
  `CITADEL_WORKSPACE`); OK when every citation resolves under a root.
- **`citadel doctor` now checks for updates.** A ninth check asks PyPI (best-effort, 2s timeout —
  offline it degrades to an OK "check skipped" line, never a WARN/FAIL) whether a newer
  `cite-citadel` is published, and when behind WARNs with the exact upgrade command for the
  *detected* install method: `git pull && uv sync` for a dev checkout, `uv tool upgrade` /
  `pipx upgrade` / `pip install -U cite-citadel`, or a note that `uvx` always runs the latest.
  Deliberately no self-executing `citadel --update` — citadel cannot know which package manager
  owns it, and a running `citadel.exe` cannot replace itself on Windows. Stdlib-only (`urllib` +
  a naive dotted-version compare that never nags on a pre-release it cannot rank).
- **`wiki_define` / `citadel define` — glossary lookup.** An eleventh MCP tool — the tenth
  read-only — plus its CLI twin answers a short "what does X stand for / mean?" as a *lookup* rather than full-text
  retrieval: it surfaces a `type: Abbreviation` glossary hit (matching the short form, expansion,
  title, or an alias, rendered `SHORT — Expansion`) first, then an exact-title/alias page of any
  type, then falls back to the closest `wiki_search` hits when nothing matches exactly. Backed by the
  new `store.define_text`. Read-only, no new dependency.
- **`wiki_status` — a twelfth MCP tool (the eleventh read-only).** The MCP twin of `citadel status`:
  the per-source corpus state table (ingested with model + rules version and the `(stale)` flag,
  failed with reason and attempts, skipped-duplicate, ignored, pending), built from the manifest +
  failures catalog + one stat-only walk. Closes the one parity gap an AI wiki-manager actually
  feels: it could trigger `wiki_ingest` but had no read-only way to see what is pending, stale, or
  stuck. Read-only annotations, never raises.
- **`wiki_lint` gained a `stale_days` parameter.** The staleness threshold CLI users had via
  `citadel lint --stale-days N` (default 365) is now tunable from MCP clients too.
- **The MCP server sets `initialize.instructions`.** Clients that surface it (Claude Code among
  them) get the recommended tool flow for free: orient with `wiki_index`, find with
  `wiki_search`/`wiki_define`, answer from `wiki_read`, spot-check citations with `wiki_raw`;
  `wiki_ingest` is the only mutating tool.

### Changed

- **`citadel init` now writes a two-tier `.env` template (~half the length, same knobs).** The
  ~180-line template every init copied verbatim is restructured: a short top section with the five
  knobs a new user actually sets (`CITADEL_LLM_CLI`, `CITADEL_INGEST_MODEL`, `CITADEL_LLM_TIMEOUT`,
  `CITADEL_WIKI_LANG`, `CITADEL_LLM_LOG_DIR`), then an "Advanced" section grouping the rest under
  short banners (paths & multi-root, formats, large sources & repos, wiki history, curate,
  observability, ignore patterns, style profiles, binary overrides) with condensed comments — the
  long-form explanations live in `docs/configuration.md`, which stays the full reference for all
  knobs. No knob was added or removed and every default is unchanged; existing `.env` files are
  never touched (init never overwrites one).
- **Two `schema.md` rule tightenings from the small-model hardening gate.** § Locators now forbids
  compound locator strings outright — a `§` locator names exactly ONE heading, never several joined
  with commas or "and"; a fact drawn from several passages gets several markers or one real `lines`
  range (compound headings were the remaining non-resolving locator class on cheap models). And the
  mandatory quarantine rule gains a self-check bullet on its banned-surfaces list: re-read the
  frontmatter `description` — it is the wiki's own voice, so it must not assert an attributed claim
  as fact even when the body is correctly attributed.
- **Viewer search + reading UX (final viewer batch).** The offline HTML viewer's full-text search is
  now **tokenized**: every whitespace-separated term must match (AND) across title/tags/path/body
  (and source bodies), fixing a real miss where a two-word query like `adenosine blocking` returned
  nothing though both words are prominent (search had been a single whole-string `indexOf`). Field
  weights are summed per term and an exact full-phrase match adds a bonus so contiguous phrases still
  rank top, and result snippets center on the first term hit and highlight every term. Two operators
  compose with the bare terms and the sidebar tag/facet filters: `tag:x` (prefix match) and `type:y`
  (case-insensitive); an unknown `prefix:` is treated as a literal term. The placeholder hints them
  (`tag:x type:y, / to focus`). Alongside search: the viewer files shrink ~5-6% by dropping the
  redundant top-level `edges` array from the bundle (the same graph was serialized ~3x) and rebuilding
  it in the browser from each page's `outbound` at boot; the reader **remembers your scroll position**
  per page/source (session-scoped, restored on return unless a query is active); **wiki-page links get
  a hover preview** (title, type, description, first ~200 chars — mouse-only, reusing the source
  popover); a page shows a **"Related:" row** of up to 6 pages sharing a tag (ranked by shared-tag
  count, excluding already-linked pages); **keyboard navigation** adds `j`/`k` to move a selection
  through the visible list + Enter to open, and `n`/`N` to step the reader's highlighted hits; and a
  **reader font-size toggle** (15 -> 17 -> 19 px, persisted) sits next to the width control. All still
  offline, deterministic, zero-dependency.
- **Viewer map now clusters by topic.** The offline HTML viewer's graph is reworked from a single
  ring into a topic map: communities are detected by deterministic label propagation over the
  combined graph (real cross-links + IDF-weighted tag-similarity KNN edges) and each is named by its
  most characteristic tag (beverages: `botany`/`trade`/`roasting`/`measurement` instead of 27
  single-tag micro-clusters); source nodes inherit their citing pages' community. Nodes seed around
  per-community centroids and relax with node collision, per-community gravity, and faint
  tag-similarity springs, so related pages actually settle together. Nodes colour by topic (full
  8-hue colorblind-safe brand palette; a type-colour toggle in the map bar, persisted — and a wiki
  that collapses to a single community, like one dense novel, defaults to type colours), the legend
  lists the top clusters with an "other" bucket and per-cluster show/hide, and labels declutter —
  only hubs, hovered neighbours, and zoomed-in views draw text. When a single community would
  otherwise swallow more than two thirds of a dense, uniformly cross-linked wiki, it is refined ONE
  level — the same deterministic label propagation re-runs inside that community over the
  tag-similarity edges alone — so `kelvarra`, `leuchtfeuer`, and `pemberley` resolve into several
  sensible sub-topics instead of collapsing to one blob (and falling back to flat type colours).
  The live drag physics is damped (velocity decay 0.78, softened collision push, a lower jump cap)
  so dragging a node nudges its neighbourhood instead of shaking the whole map, while staying
  responsive. Deterministic (no `Math.random`), vanilla JS, zero deps. Viewer assets only
  (`app.css`/`app.js`).
- **Viewer adopts the project's warm brand palette.** The offline HTML viewer's tokens move to the
  warm paper/ink scheme with the green brand accent (`#009E73` family): a monospace wordmark carrying
  a small green brand marker, and a colorblind-safe map palette (the brand green pinned first). The
  link/accent green is AA-checked per theme — the light `--accent` uses the darker `#007A59` (5.0:1
  on the paper background, where plain `#009E73` reached only ~3.2:1) while dark keeps `#009E73`
  (5.5:1), and the light `--source` gold is darkened to clear 4.5:1 wherever it renders as citation
  text. Viewer assets only (`app.css`/`app.js`); no Python or template change.
- **Viewer: compact, grouped Sources + a mobile/touch/print pass.** A page's trailing `## Sources`
  section no longer renders as a tall footnote wall (the same raw file repeated once per citation,
  each with its own link, date, and back-arrow). It is now a **collapsed `Sources (N)` `<details>`**
  (the page ends on content, not footnotes) that **groups citations by the file they cite** — the
  file link and `(ingested …)` date appear once, followed by that file's citations as a compact run
  (`s1 (§ Heading), s5 (lines 23-25), …`) or, when they carry distinct notes, one muted line each.
  Every citation keeps its own `id`, so an inline `[^sN]` still jumps to its definition (opening the
  collapsed section first) and hover popovers still work per citation; the back-arrows are dropped
  (the inline marker is the way back). The grouping is robust to a misconfigured workspace whose
  citations don't resolve to an embedded source (so a citation renders as a bare file-name span, not
  a source link): each still groups per cited file under a plain file-name header, instead of every
  citation collapsing into one nameless `↩` group. The sidebar "Sources" axis now defaults **closed** (with a
  persisted toggle). The viewer also gained its **first responsive breakpoint** (≤ 720px): the
  sidebar becomes an off-canvas drawer toggled by the existing hamburger / backslash shortcut, the
  reader goes full-width, and the map defaults collapsed and height-capped — no horizontal scroll at
  phone widths, with the desktop layout unchanged. Map pan/drag/tap and the pane resizer now use
  **Pointer Events**, so one-finger pan, node drag, and tap-to-open work on touch (mouse behavior
  unchanged; wheel and the +/- buttons still zoom). A **print stylesheet** prints just the reader
  (black-on-white, sidebar/map/chips hidden) with the Sources section forced open so citations print.
- **Offline viewer embeds only the CITED EXCERPTS of each raw source, not its whole body.** For a
  source-heavy wiki the full-text embed dominated the single-file viewer (a source could be ~40% of
  the document). Now, per source, only the passages the wiki actually cites are embedded — a
  `lines A-B` locator becomes that range plus 3 lines of context, a `§ Heading` becomes its section
  (capped at 80 lines), and an unlocated citation contributes a head excerpt (lines 1-30); overlapping
  and near-adjacent ranges (gap ≤ 2 lines) merge. A short file (≤ 120 lines) or one whose excerpts
  already cover ≥ 2/3 of it embeds whole — but only when the whole body fits under the 200k guard —
  so small notes are never fragmented. The reader shows
  each segment under a "lines A–B" label with a "⋯ lines X–Y not embedded — open the original file" gap
  indicator, and the existing "Open original file" affordance covers the rest. `_SOURCE_MAX_CHARS`
  (200k) stays as the final per-source guard: segments are filled whole until the next one would
  exceed it, then the rest are dropped to the gap indicator rather than sliced off mid-passage. No new
  flag or env knob — this is the default. A large source cited by only a couple of narrow ranges
  shrinks that source's embed by ~100× or more; a wiki that cites its source almost in full and is far
  larger than the guard (e.g. the pemberley novel, ~730k chars, ~95% cited) embeds the cited segments
  that fit within the 200k budget — down from a blind 200k front-slice of the whole body — with the
  uncited/over-budget remainder reachable via "open the original file." The viewer's source
  full-text search accordingly covers only the embedded excerpts; text in an uncited stretch of a
  large source is reachable through the wiki pages that cite it, or the original file.
- **Ingest now gives pages lay-term `aliases`.** `citadel/rules/schema.md` gains an *Aliases* section
  teaching the agent to add up to ~4 high-precision alternate names a reader might search — a lay
  synonym, everyday word, nickname, or former name — to any page (not just abbreviations), so a
  paraphrased query reaches the page by a word its title lacks. Pairs with the alias-scoring change
  below. Validated on a fresh kelvarra build: the currency page picked up `aliases: [money, cash]` and
  `citadel search "money"` went from *absent* to rank 1, with the counterfactual/structural guarantees
  unchanged. (Editing a `rules/` file bumps `rules_version`, so `citadel status` shows previously
  ingested sources as `(stale)` — expected, cosmetic.)
- **Search now weights a page's declared `aliases`.** `store_core._score` scores the `aliases`
  frontmatter (an alternate name / lay-term synonym) at weight 2.5 — between `title` (3.0) and `tags`
  (2.0) — and counts them in the IDF corpus, so a paraphrased query can reach a page by a word its
  title lacks (e.g. a currency page aliased `money`/`cash` surfaces for "how do people pay …"). Purely
  lexical, no synonym map or embeddings. Aliases were already parsed and used by `wiki_define` /
  exact-title lookup but never ranked; a paraphrase-probe harvest over fresh Mode-A builds surfaced the
  gap. Locked by a golden-rank test; the rest of `test_search.py` passes unchanged.
- **Light stemming in search.** `store_core._tokenize` now applies a small, deterministic,
  dependency-free suffix strip (`brewing`/`brew`, `founded`/`founding`, `magnets`/`magnet` collapse to
  a shared token) so paraphrased query forms match. It is applied symmetrically to both the query and
  the page text, so the field-weight / IDF scoring contract is unchanged; the `test_search.py`
  characterization tests still pass unmodified.
- **Leaner, more predictable ingest sessions.** The run instruction and `core.md` now tell the agent
  that the raw source tree is a **read-only input** (read it for content and citations, never write,
  create, move, or delete under it) and that reading/searching go through the agent's **built-in
  file tools** rather than the shell, which stays reserved for the `citadel check` self-check and
  page deletes/renames. The self-check now runs **once** and re-runs only to confirm fixes when it
  reported errors, instead of being invoked repeatedly. Together these cut the number of shell
  subprocesses a session spawns and keep every write inside the wiki — no functional change to the
  wiki that gets produced. (Editing any `rules/` file bumps `rules_version`, so `citadel status`
  shows previously ingested sources as `(stale)` — expected, cosmetic.)
- **`citadel lint` exits 3 (was 2) when the report is not clean.** Exit 2 collided with the
  usage/no-workspace code (argparse's own convention, also used by the workspace guard and the
  `ingest --force`-without-paths refusal), so a CI consumer could not tell "the wiki has structural
  problems" from "invoked wrong". Lint's codes are now: 0 clean, 1 unexpected error, 2
  usage/no-workspace, 3 report not clean. Scripts checking `!= 0` (as CI's corpus lint gate does)
  are unaffected; only a literal `== 2` check on lint's not-clean state needs updating.
- **`wiki_raw` / `citadel raw` — an unresolvable locator is now a clear error.** A locator that
  parses to nothing offline-resolvable (an Office `p. 12` page locator, a garbled/typo'd form) used
  to silently return the WHOLE capped source with only a header note and exit 0 — undetectable by a
  script or an MCP client checking the `error:` prefix, unlike every other bad locator. It now
  errors (exit 1 / `error: …` string) naming the recognized forms (`lines A-B`, `§ Heading`,
  `§ Heading, lines A-B`) and the escape hatch: omit the locator to read the whole source.
- **Blank boolean env values now mean "unset", and all boolean knobs share one parser.** Three
  hand-rolled parsers disagreed on blank: a bare `CITADEL_IMAGE_SUPPORT=` /
  `CITADEL_REPO_SUPPORT=` / `CITADEL_DEDUP_BY_BASENAME=` (an uncommented-but-emptied `.env` line)
  silently DISABLED those default-on features, while blank meant "default" for every other knob
  family. All five boolean knobs now parse through one `_bool_env`: blank/missing keeps the
  default, `1/true/yes/on` and `0/false/no/off` are recognized, and anything else falls back to
  the default with a `citadel doctor` config warning. Anyone deliberately disabling a feature via a
  bare `KNOB=` must now write `KNOB=0`.

## [0.3.0] - 2026-07-06

### Added

- **`wiki_neighbors` / `citadel neighbors` — walk a page's link graph.** A tenth read-only MCP tool
  (+ its CLI twin) prints a page's **links out** (its wiki cross-links, resolved to rel_paths, each
  flagged `(missing)` if the target page is gone), **linked from** (the backlink graph), and **cites
  sources** (the raw/`docs/` source keys it cites, with per-source counts — the keys to hand to
  `wiki_raw`), so an AI can traverse the graph without doing relative-path math itself. Backed by
  `store.neighbors_text`.
- **`wiki_raw` / `citadel raw` — read the raw source behind a citation.** A new read-only MCP tool
  (the ninth) and its CLI twin resolve a `[^sN]` citation's provenance for spot-checking: given the
  cited source key (e.g. `raw/notes.md`) and, optionally, the citation's locator tail (`lines 76-83`,
  `§ Method`, or a combined `§ Method, lines 5-9`), it returns the cited source's text — or exactly
  the slice the locator names — line-numbered and size-capped. A provenance gate makes only sources
  the wiki actually cites (the ingest manifest, or a `docs/` file) readable, so it verifies the
  synthesized wiki without becoming a bulk re-retrieval path; PDFs/images/undecodable files return an
  honest "read it directly" message. Backed by the new `citadel/rawsource.py`.
- **Two more graded test corpora** under `corpora/`, bringing the total to five: **pemberley** (the
  whole of *Pride and Prejudice* as one ~730k-char source — large-source multi-segment chunking,
  relationship extraction, in-novel misinformation, narrative supersession) and
  **injection-resistance** (three mundane documents with adversarial instructions embedded, graded
  that the ingest agent treats them as content and never executes them). Each ships a hidden
  `ground-truth.md` answer key and is wired into the parameterized `verify-corpus` skill.
- **A committed, graded showcase wiki for every corpus** (not just beverages): each
  `corpora/<name>/` is now its own self-contained workspace with a nested `citadel.toml` marker and
  a lint-clean `wiki/`. CI lints all five.
- **GitHub Pages gallery.** `.github/workflows/pages.yml` builds one offline single-file viewer per
  corpus into `site/<name>/` and publishes a lean landing page (`.github/pages-index.html`) — a
  disclaimer banner plus one card per corpus — that links each demo.
- **Community health files** for the public repo: `.github/dependabot.yml` (weekly `uv` + GitHub
  Actions updates) and `.github/ISSUE_TEMPLATE/` (bug report, feature request, and a config that
  routes questions to Discussions and security reports to the policy).

### Changed

- **Search now weights rare terms (IDF).** `store_core.search` scales each token's field weight by its
  inverse document frequency, so a rare, discriminating query term (an acronym, a proper noun)
  outranks one common to the whole wiki — a "TDS" or "espresso" lookup surfaces its own page instead
  of being buried under generic topic pages (measured on the showcase corpora: rank 4→2 and 3→1, no
  regressions). Pure-Python, no new dependency, recomputed per search; the `search()` seam signature
  and MCP surface are unchanged. A golden-rank test locks the behavior against a regression to plain
  overlap.
- **`verify-corpus` now grades retrieval-first.** Phase 2 checks each corpus guarantee the way a user
  consumes the wiki — driving `citadel search`/`read`/`index`/`tags` to prove the answer is both
  correct+cited and *findable* (not merely present on disk), and drops to a file-level grep only to
  classify a miss as a wiki-*creation* defect or a *retrieval* defect. Each corpus's hidden
  `ground-truth.md` gains a frozen, answer-blind `## Retrieval battery`, and the grade's misses route
  into two optimization lanes (the ingest/rules generator and the search tools). Test-only — no wiki
  or corpus content changed.
- **Renamed three corpora** to their in-world names — the fictional-republic corpus is now
  **`kelvarra`**, the three-year-programme corpus is now **`leuchtfeuer`**, and the *Pride and
  Prejudice* corpus is now **`pemberley`** (directories, hidden answer-key directories, and every
  reference across docs, workflows, and the `verify-corpus` skill).
- **`leuchtfeuer` layout inverted.** Its committed `raw/` now holds the **final** post-wave-3 file
  set (11 files, cited by the committed wiki); the wave history moved under `stages/` —
  `stages/initial/` (the 2024 wave-1 originals, charter Rev A + the later-deleted memo), plus the
  existing `stages/wave2/`/`stages/wave3/` overlays. The sandbox wave protocol now seeds the raw
  from `stages/initial/`.

### Fixed

- **Locator lint no longer false-flags the combined `§ Heading, line N` citation form.** The Z6
  locator check treated the whole `Heading, line N` as a heading name and failed to find it —
  producing false-positive advisories (13 on the beverages showcase alone) and phantom `locator`
  findings in `citadel curate` (the check is shared). The locator parser is now a single
  `grammar.parse_locator` (moved to the citation-grammar home, next to `source_definitions`), which
  splits the combined form and verifies **both** the heading and the line range; `lint._locator_problem`
  is a thin consumer. All five showcase corpora now lint with zero locator advisories.

## [0.2.0] - 2026-07-03

### Added

- **`citadel ingest --force`** — deliberately re-read an already-ingested source and reconcile the
  wiki against it (never a plain re-ingest); repos force a full re-digest via `repo-reconcile`;
  clears a persisted unreadable/errored failure record.
- **Multi-root raw** via `CITADEL_RAW_DIRS`, and **`citadel ingest --full-rescan`** to distrust the
  scan cache and rehash everything.
- **`citadel curate`** — a second lifecycle that re-verifies facts, splits overlong pages, and
  re-sorts information without re-ingesting from zero. Flags: `--dry-run`, `--limit`, `--stale-rules`,
  `--diff`; model knob `CITADEL_CURATE_MODEL`.
- **`citadel status`** — per-source state (ingested with model + rules version, failed with reason +
  attempts, skipped-duplicate, ignored, pending) from the manifest and failures catalog, no re-hash.
- **Full CLI ↔ MCP parity** — new `citadel read` / `citadel index` / `citadel sources` subcommands,
  a new `wiki_lint` MCP tool, and behavior annotations (`readOnlyHint` etc.) on all eight MCP tools,
  so an AI without MCP access can drive everything through the shell.
- **`citadel doctor`** — preflight check: workspace found, rules resolve, agent CLI on PATH, raw roots
  reachable, manifest parses, and an API-key billing-shadow warning.
- **OSS project docs** — `NOTICE.md` (affiliation & trademark disclaimer, dependency-license record),
  `CONTRIBUTING.md`, this `CHANGELOG.md`, `SECURITY.md`, `docs/configuration.md`, README badges, and a
  "License & third-party tools" section (bring-your-own-CLI terms + output ownership).
- **`open-pr` skill** and a mandatory self-verification routing section in `CLAUDE.md`.
- **Three graded test corpora** under `corpora/` (beverages, kelvarra, leuchtfeuer)
  with hidden answer keys, driven by the parameterized `verify-corpus` skill.

### Changed

- **Incremental discovery** — the manifest doubles as the scan cache, so an unchanged corpus now
  does **zero content reads**.
- **Deletion is safe by construction** — an unreachable share or a walk error can never read as mass
  deletion, and out-of-root keys are never swept.
- **Segmented sources promote once** — a large source's passes fold into one staging copy and promote
  together, so the live wiki never holds a half-folded source.
- **Store hygiene** — index rebuilds are single-pass (much faster) and `write_page` gained a
  reserved-name guard.
- Packaging: the sdist now **excludes** the test corpora, CI/agent config, and dev-only files (the
  wheel is unchanged); the pyproject `description` is vendor-neutral.

### Fixed

- Failed repo and delete sessions now reach the failures catalog and surface under "Could not
  ingest".
- `lint` and `check` agree on citation/link grammar by construction (shared `grammar.py`).

## [0.1.0] - 2026-07-02

First public, pip-installable release (`pip install cite-citadel`), and the PyPI name reservation.

### Added

- **Workspace model** — `citadel init` scaffolds a workspace (`citadel.toml` marker, `.env`, `raw/`,
  `wiki/`, `rules/`); discovery walks up for the marker or resolves `CITADEL_*_DIR` env vars, and
  fails loud rather than inventing a phantom workspace. `citadel --version`.
- **Rules tree as package data** — `citadel/rules/` (`schema.md`, `core.md`, `tasks/`, `formats/`,
  `genres/`) ships inside the wheel and is read by the ingest agent at run time; the prompt builder
  shrank to a paths-only frame. Editing the rules changes how the wiki is built with no code change.
- **Citation locators** — footnote definitions may carry `p. 12` / `pp. 3-5`, `line 40` /
  `lines 40-52`, or a `§ Heading` anchor; `lint` verifies line/heading locators against raw files.
- **`CITADEL_WIKI_LANG`** (default `en`) — the wiki is written in one target language regardless of
  the sources' languages, with verbatim quotes and proper names left untranslated.
- Release pipeline (v* tags → PyPI Trusted Publishing), wheel-smoke CI, Windows + macOS runners,
  Python 3.12–3.14, PEP 639 license metadata, dynamic single-sourced version.

### Changed

- Shared citation/link/fence parsing consolidated into `grammar.py`; viewer moved to a subpackage
  with a golden bundle test; Office/OLE extraction isolated.

[Unreleased]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MarkusNeusinger/cite-citadel/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MarkusNeusinger/cite-citadel/releases/tag/v0.1.0
