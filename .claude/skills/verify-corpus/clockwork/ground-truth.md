# Ground truth — the clockwork corpus

This is the **answer key** for the `clockwork` corpus (`corpora/clockwork/`). It lives under
`.claude/` (outside the corpus, outside `raw/`/`wiki/`/`docs/`), so the ingest pipeline can never
see it. The verify-corpus skill reads it to grade the wiki the pipeline produced.

`clockwork` is the only corpus whose source is a **whole git repository**, folded in as **one
digest** (`CITADEL_REPO_SUPPORT=1`, `kind=repo`), and the only one that also exercises
`kind=repo-reconcile`: a second ingest after the repo gains a commit that **changes one documented
default**. It grades that a repo becomes a small, correct, folder-cited page cluster — and that the
changed default is **superseded (dated), not duplicated**.

> Everything is **fictional by design** (the `clockwork` scheduler, its versions, its history). The
> real-world software facts it happens to state (cron syntax, PostgreSQL advisory locks) are true;
> the wiki must record the repo faithfully as the digest states it.

## The source and the two-commit protocol

The corpus ships the repo as plain trees (a git repo cannot be committed inside this repo):

| tree | role |
| ---- | ---- |
| `repo-src/` | the repo at **v0.3.0** (wave-1 state): `README.md`, `CHANGELOG.md`, `pyproject.toml`, `src/scheduler.py`, `docs/design.md`, `LICENSE` |
| `repo-src-wave2/` | the **overlay** landing **v0.4.0**: changes **two** documented defaults — `max_retries` **3 → 5** and `poll_interval` **60 → 30** (in `src/scheduler.py` and `README.md`) — and appends the v0.4.0 `CHANGELOG.md` entries. `docs/design.md` is **deliberately not updated** (it still says "default 60"): realistic documentation drift the reconcile must resolve by the dated CHANGELOG, not by majority-of-mentions |
| `raw/clockwork-repo/` | the committed **final** materialized tree the showcase `wiki/` cites (a `.citadelsource` marker makes it one repo source without a live `.git`) |

**Sandbox protocol** (Mode A; a scratch workspace, never a live wiki — neither `repo-src/` nor
`repo-src-wave2/` is pointed at the agent, only the materialized checkout):

```bash
REPO="$(git rev-parse --show-toplevel)"
SANDBOX="$(mktemp -d)/verify-clockwork"
uv run python -m citadel init "$SANDBOX"
export CITADEL_WORKSPACE="$SANDBOX" CITADEL_WIKI_DIR="$SANDBOX/wiki"
export CITADEL_RAW_DIR="$SANDBOX/raw"; RAW="$CITADEL_RAW_DIR"; WIKI="$SANDBOX/wiki"
export CITADEL_INGEST_MODEL=sonnet CITADEL_REPO_SUPPORT=1
SRC="$REPO/corpora/clockwork"

# wave 1 — materialize the repo at v0.3.0, real git checkout, then ingest (kind=repo)
mkdir -p "$RAW/clockwork-repo" && cp -r "$SRC/repo-src/." "$RAW/clockwork-repo/"
( cd "$RAW/clockwork-repo" && git init -q && git add -A && git -c user.email=t@e.test -c user.name=t commit -qm "clockwork v0.3.0" )
uv run python -m citadel ingest

# wave 2 — apply the overlay, new commit → reconcile (kind=repo-reconcile)
cp -r "$SRC/repo-src-wave2/." "$RAW/clockwork-repo/"
( cd "$RAW/clockwork-repo" && git add -A && git -c user.email=t@e.test -c user.name=t commit -qm "clockwork v0.4.0" )
uv run python -m citadel ingest

# idempotency — no new commit → NOOP (zero sessions)
uv run python -m citadel ingest
```

Expected session kinds: wave 1 = **one** `repo` session; wave 2 = **one** `repo-reconcile` session
(the digest's "What changed" names `scheduler.py`/`README.md`/`CHANGELOG.md`); the final re-run is a
**NOOP**.

## Expected state after wave 1

- A page for the **clockwork** tool (name LLM-chosen; type is agent-judged — `System` per the
  routing "a library/tool is a System", or `Object`/`Project` — accept any, judge by content), and a
  **`type: System`** page for **PostgreSQL** (the external store).
- The tool page is built from the digest and answers the repo brief's four questions: **what it does**
  (a job scheduler running recurring YAML jobs), **how to use it** (`pip install clockwork-scheduler`;
  `clockwork run --config clockwork.yml`; the `CLOCKWORK_DB_URL` env var), **how it does it** (poll
  loop → advisory-lock claim → run → retry → record), **what comes out** (`job_runs` rows).
- Current values as of wave 1: default `max_retries` **3**; `poll_interval` **60 s**; `backoff_base`
  **2.0**.
- **In-repo contradiction, present from wave 1** (`X1`): the README states `clockwork` "requires
  Python **3.11 or newer**" while `pyproject.toml` declares `requires-python = ">=3.10"`. There is
  no dated resolution anywhere in the repo — this is a genuine doc-vs-metadata conflict, NOT a
  supersession. The wiki must not silently assert one side as the requirement: either both values
  appear cited with the discrepancy noted, or a contradiction callout flags it. Asserting "3.10"
  or "3.11" alone, uncaveated, is a FAIL.

## Expected state after wave 2 (the reconcile wave — the temporal trap)

The overlay changed exactly two documented defaults. The reconcile must **update, not append** —
and the two changes differ in difficulty on purpose:

| fact | expected | detail |
| ---- | -------- | ------ |
| default `max_retries` | **UPDATE** (the clean one) | current value becomes **5** (v0.4.0), cited to the repo — every file that states it was updated. The old **3** survives **only** as a dated, superseded statement (a change-log/history bullet: "raised from 3 to 5 in 0.4.0") — never as the current default. `max_retries` default presented as **3** = FAIL. Both 3 and 5 shown as the current default (no supersession) = FAIL. |
| default `poll_interval` | **UPDATE against doc drift** (the hard one) | current value becomes **30** (v0.4.0): `src/scheduler.py`, the README, and the dated CHANGELOG all say 30 — but **`docs/design.md` still says 60** (deliberately stale). The wiki's current value must be **30**; **60** survives only as the dated prior default. A wiki that quotes the stale design doc's 60 as current — or presents both as live because "the files disagree" — failed the trap: the CHANGELOG *dates* the change, so this is supersession-plus-drift, not a contradiction. |
| everything else | **NOOP** | `backoff_base` 2.0, the Postgres design, install/run/CLI facts, and the `X1` Python-requirement conflict are unchanged — the reconcile must not churn or duplicate them (and must not "resolve" `X1`, which no wave dates). |

## A · Load-bearing facts that MUST appear in the final wiki (cited to the repo)

Each present as a normal cited fact, `[^sN]` → the repo folder (`raw/clockwork-repo`), never a
per-file source, never the digest file.

| id | fact | source of record |
| -- | ---- | ---------------- |
| `F1` | clockwork is a lightweight Python **job scheduler** that runs recurring jobs defined in a YAML file | README |
| `F2` | it **persists job state to PostgreSQL** so a scheduler that was down **catches up** missed runs | README / design |
| `F3` | install `pip install clockwork-scheduler`; run `clockwork run --config clockwork.yml` | README |
| `F4` | the Postgres DSN is read from **`CLOCKWORK_DB_URL`** and is **required** (refuses to start without it) | README / scheduler.py |
| `F5` | CLI subcommands **`run` / `add` / `status`** (`clockwork status` prints last/next run + outcome) | README |
| `F6` | jobs are claimed via a **PostgreSQL advisory lock** so multiple instances never double-fire | README / design |
| `F7` | state lives in two tables, **`jobs`** and **`job_runs`** (one row per attempt) | design |
| `F8` | the poller wakes every **`poll_interval` seconds (final default 30; 60 only as the dated prior)** | scheduler.py / README / CHANGELOG (design.md is stale) |
| `F9` | a failed job retries up to **`max_retries` (final default 5)** with **exponential backoff** (`backoff_base` 2.0) | scheduler.py / README / CHANGELOG |
| `F10` | the Python requirement is **conflicting in-repo**: README says **3.11+**, `pyproject.toml` says **>=3.10** — both cited, discrepancy surfaced, neither silently asserted | README vs pyproject.toml (`X1`) |

## B · One digest — NOT one page per file, cited to the folder

- The whole repo is **one source**: exactly **one** manifest entry (`.citadel_ingested.json`) for
  `raw/clockwork-repo`, keyed by the HEAD **commit** (`identity()`), model recorded. **NOT** one
  entry per repo file. → §G.
- `resource:` on the tool page = `raw/clockwork-repo` (the folder). Every `[^sN]` definition targets
  the **folder** (`../../raw/clockwork-repo`) — never `.../clockwork-repo/README.md` as if each file
  were its own source, and **never the digest file** (which lives outside `raw/`). A `[^sN]` to a
  nonexistent path = lint fabricated-source FAIL.
- The repo should fold into a **small** cluster (≈ the tool page + the PostgreSQL system page, maybe
  a Concept for catch-up/advisory-locking) — not a page per source file. Per-file fragmentation is a
  soft creation defect.

## C · External system — PostgreSQL (accumulating System page)

- A **`type: System`** page for **PostgreSQL** exists, describing it as clockwork's job-state store
  and **how clockwork uses it**: the `jobs` + `job_runs` tables, **advisory locks** for claiming,
  addressed by `CLOCKWORK_DB_URL`. Tagged as a database.
- The tool page and the PostgreSQL page **cross-link**. A wiki that mentions Postgres only inline,
  with no System page, is a soft miss; one that never records the advisory-lock/tables relationship
  is a creation defect.

## D · Subtle must-not-be-dropped facts

- `D1` — **catch-up**: a scheduler that was offline **replays missed runs** rather than skipping
  them (the whole reason state is in Postgres). Must survive.
- `D2` — **multi-instance safety**: several `clockwork` processes can run for availability **without
  double-firing**, via the advisory lock. Must survive (it is the repo's headline design claim).
- `D3` — the SQLite→PostgreSQL move (before 0.3.0) is why `CLOCKWORK_DB_URL` became required — nice
  history to keep, not required.

## E · The one thing that must NOT happen — code transcription

The repo brief allows a **short** verbatim excerpt only when the code itself **is** the fact (a
connection call, an env var, the key command). A page that pastes the `Scheduler.__init__` body, the
`run()` loop, or reproduces `scheduler.py` block-by-block is a creation defect (violates
`formats/repo.md` / `core.md`). Capture **usage**, not a transcription.

## F · Structural gates (hard pass/fail — pure code, no judgement)

- `citadel check` → "OK — no validation issues." (0 errors), after each wave.
- `citadel lint` → exit 0 (no missing type, no broken link, **no fabricated source**, no
  `[[wikilink]]`). The folder citation `raw/clockwork-repo` resolves (a directory is valid
  provenance); a `[^sN]` to a per-file path that is not present, or to the digest, fails here.
- Manifest holds **exactly one** source entry for the repo (`raw/clockwork-repo`), not N per-file
  entries.

## Retrieval battery — find the knowledge like a user (Tier 2)

Run each `query` **verbatim** through `citadel search`, read the top hits, grade (a) the `expect`
answer is present + correctly cited on a surfaced page and (b) it was findable within the `find`
band. Queries are answer-blind. `→§X` points at the section whose grep settles a miss. The temporal
row (`rb-retries`) demands the **live** value and rejects the superseded one.

| id | query | expect | find |
| -- | ----- | ------ | ---- |
| `rb-what` | what is clockwork and what does it do | a **Python job scheduler** that runs recurring YAML-defined jobs and persists state to PostgreSQL with catch-up →§A·F1/F2 | rank 1, 1 read |
| `rb-run` | how do I run clockwork | `pip install clockwork-scheduler` then `clockwork run --config clockwork.yml`; needs `CLOCKWORK_DB_URL` set →§A·F3/F4 | rank 1, 1 read |
| `rb-db` | where does clockwork keep its job state | **PostgreSQL** — the `jobs` and `job_runs` tables →§A·F7, §C | rank≤2, 1 read |
| `rb-dburl` | which environment variable configures clockwork's database connection | **`CLOCKWORK_DB_URL`** (a required Postgres DSN) →§A·F4 | rank 1, 1 read |
| `rb-retries` | how many times does clockwork retry a failed job by default | **5** (current default, v0.4.0); **3** appears only as the dated prior default it superseded, never as current →§Reconcile, §A·F9 | rank 1, 1 read |
| `rb-lock` | how does clockwork stop two schedulers from running the same job twice | a **PostgreSQL advisory lock** keyed on the job name — multiple instances can run for availability without double-firing →§A·F6, §D·D2 | rank≤2, 1 read |
| `rb-poll` | how often does clockwork check for jobs that are due | every **`poll_interval` seconds, default 30** (v0.4.0); **60** appears only as the dated prior — a current 60 means the stale `docs/design.md` won over the dated CHANGELOG →§Reconcile, §A·F8 | rank≤2, 1 read |
| `rb-python` | which Python version do I need to run clockwork | the repo **conflicts with itself**: README says 3.11+, `pyproject.toml` says >=3.10 — the surfaced page must show both cited (or a contradiction flag), never a single uncaveated value →§A·F10 (`X1`) | rank≤3, ≤2 reads |
| `rb-catchup-since` | since which release does clockwork replay runs it missed while down | **0.2.0** (the CHANGELOG's catch-up entry) — NOT 0.3.0 (that was the SQLite→PostgreSQL move) and NOT 0.4.0 (the defaults change); a wiki answering 0.3.0 conflated the version history →§A·F2, §D·D3 | rank≤3, ≤2 reads |

## Scoring

**Hard gates** (must all hold): §F structural after each wave; **exactly one** repo manifest entry
(digest, not per-file); provenance folder-keyed (`raw/clockwork-repo`, no fabricated per-file or
digest citation); the `max_retries` **3 → 5** supersession (5 current, 3 only dated — never both
live, never 3 as current); the `poll_interval` **60 → 30** supersession **against the stale
design.md** (30 current, 60 only dated — the drifted doc must not win); the `X1` Python-requirement
conflict never silently one-sided (§A·F10); every §A `F*` fact present-and-cited; a `type: System`
PostgreSQL page exists (§C) recording the tables + advisory-lock relationship.

**Soft / probabilistic** (report caught / partial / missed; don't hard-fail a single miss): the repo
folds into a **small** cluster rather than one-page-per-file (§B); a tidy dated history for both
default changes; an explicit contradiction callout (vs. merely dual-citing) for `X1`; the correct
version mapping in `rb-catchup-since` (0.2.0 catch-up vs 0.3.0 Postgres vs 0.4.0 defaults); the
tool↔PostgreSQL cross-link; `D1` catch-up and `D3` SQLite→Postgres history kept; no
code-transcription (§E).

**Findability** (Retrieval battery — report per row, don't hard-fail a soft rank miss): each row's
answer surfaces on a correct, correctly-cited page within its `find` band in ≤2 reads; `rb-retries`
must return the **live 5**, never 3. **Hard floor:** a row unfindable by search *and* `index` *and*
`tags` is a hard miss. Route each miss — present-but-unranked → *retrieval* defect (search lane);
absent / per-file-fragmented / mis-cited / a superseded value surfacing as current → *creation*
defect (wiki-generation lane: `citadel/rules/formats/repo.md`, the ingest prompts).
