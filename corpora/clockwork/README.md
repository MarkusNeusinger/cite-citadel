# clockwork — a git repository folded in as one source (repo ingest + reconcile)

> **SOURCE / provenance:** Everything in this corpus is **synthetic** and was authored by hand for
> testing cite-citadel. `clockwork` is a **fictional** Python job scheduler; the people, versions,
> and history are invented. Any resemblance to a real project is accidental. Safe to publish.

The only corpus whose source is a **whole git repository**, ingested as **one digest** rather than
file by file (`CITADEL_REPO_SUPPORT=1`, `kind=repo`), and the only one that exercises
`kind=repo-reconcile` — a second ingest after the repo gains a commit. `clockwork` is a small,
believable software project: a README, a CHANGELOG, a `pyproject.toml`, a `src/scheduler.py` whose
docstrings carry the load-bearing facts, a `docs/design.md`, and a LICENSE.

## Layout and the two-commit protocol

A git repository cannot be committed *inside* this repository, so the corpus ships the repo's files
as plain trees and the sandbox **materializes** them into a real git checkout:

- [`repo-src/`](repo-src/) — the repo at **v0.3.0** (the wave-1 state).
- [`repo-src-wave2/`](repo-src-wave2/) — the **overlay** that lands **v0.4.0**: it changes two
  documented defaults — the scheduler's `max_retries` **3 → 5** and `poll_interval` **60 → 30** —
  in `src/scheduler.py` and the README, and appends the v0.4.0 CHANGELOG entries. Unchanged files
  (design, LICENSE) are not repeated — **deliberately including `docs/design.md`, which still says
  "default 60"**: realistic documentation drift the ingest must resolve by the dated CHANGELOG, not
  by counting mentions. Independently of the waves, the repo also contradicts itself about its
  Python requirement (README "3.11 or newer" vs `pyproject.toml` `>=3.10`) with no dated resolution.
- [`raw/clockwork-repo/`](raw/clockwork-repo/) — the **final** post-wave-2 materialized tree the
  committed [`wiki/`](wiki/) is built from and cites (carries a `.citadelsource` marker so it is
  recognized as one repo source without a live `.git`).

The sandbox protocol (see `.claude/skills/verify-corpus/SKILL.md`, the clockwork note) rebuilds the
history in a scratch workspace:

| step | action | what it exercises |
| ---- | ------ | ----------------- |
| wave 1 | `cp repo-src/*` into `$SANDBOX/raw/clockwork-repo/`, `git init` + commit, then ingest | whole-repo digest, `kind=repo`, one manifest entry keyed by HEAD commit, a `type: System` page for PostgreSQL |
| wave 2 | apply `repo-src-wave2/` over it, `git commit`, then ingest | changed-repo **reconcile** (`kind=repo-reconcile`): the changed default is **superseded (dated), not duplicated** |
| after | re-run ingest with no new commit | idempotency — a **NOOP** |

`repo-src/` and `repo-src-wave2/` are never pointed at the agent directly — only the materialized
`raw/clockwork-repo/` checkout is.

## What it exercises

Repo ingest end-to-end: the deterministic digest (`repo.py`), folder-keyed provenance
(`resource: raw/clockwork-repo`, every `[^sN]` to the folder, never to per-file sources), the
`formats/repo.md` "capture usage not code" brief, an accumulating `type: System` page for the external
PostgreSQL store, and — across the two commits — temporal supersession of two changed defaults under
`kind=repo-reconcile`: one clean (every mention updated) and one against **stale documentation**
(`docs/design.md` keeps the old value). Plus a doc-vs-metadata **contradiction** inside one source
(the Python requirement) that must be surfaced, not silently resolved, and a version-history mapping
(which release added catch-up vs the Postgres move vs the defaults change) that punishes conflation.

## Grading

The answer key is `.claude/skills/verify-corpus/clockwork/ground-truth.md` — kept outside this
directory on purpose, so the ingest agent can never see it. Do not add grading material, expected
values, or answer notes anywhere under `corpora/clockwork/`.
