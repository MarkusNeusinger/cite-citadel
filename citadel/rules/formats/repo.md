# repo — a git repository ingested as ONE source

Applies when the run instruction says the source is a **git repository**: a folder under raw/
holding a `.git/` — or carrying an opt-in empty `.citadelsource` marker for a git-less snapshot —
ingested as **one source**, never file by file.

- The system pre-built a deterministic **digest** of the repo's high-signal files (README,
  dependency manifests, the connection/config layer, the data-transform/pipeline core, entry
  points; `.gitignore` honored, lockfiles / `node_modules` / build output dropped, capped to a
  budget). The run instruction names where it was written — **read the digest** for the content.
- The repo **folder** is the source of record: set `resource:` to the folder path (e.g.
  `raw/acme-etl`) and link every `[^sN]` definition to the folder — never to the digest file.

## What to capture — assume ~99% of the code is irrelevant

For the repo, capture only, each as a normal cited fact:

- **How to use it** — how to run/call it, how to connect to the API/service/DB, the key
  command(s) to transform the data, the env vars / config it needs.
- **What it does** — its purpose.
- **How it does it** — the data flow / pipeline steps at a readable level (not line by line, not
  one note per function).
- **What comes out** — the output / result form.

A **short verbatim code excerpt** (a few lines) is allowed here when the code itself **is** the
fact — a connection/auth call, the key transform command, an env var, a SQL query — cited like
any fact. This is the one relaxation of `core.md`'s "never paste a block of code"; keep it short
and usage-oriented, never a transcription.

## External systems

For every **external system** the repo touches — a database, API, queue, service, or tool (SAP,
PLM, Postgres) — create or extend a `type: System` page (routing: `schema.md`) describing the
system and how THIS repo uses it (tables/endpoints, access method, auth), with tags marking its
kind (database/api/service/tool). System pages **accumulate** across sources — search for an
existing one and extend it before creating a new one. Link the repo's pages to them.

## Repo changes over time

A repo is versioned by its **HEAD commit**. When the run instruction says the repo CHANGED since
it was last ingested (new commits), this is a re-ingest under `tasks/reconcile.md`, scoped by the
digest: its **"What changed"** section lists the changed files. UPDATE the facts those changes
affect (a changed command, mapping, table, or output), remove facts the repo no longer supports,
and leave unaffected facts — and facts from OTHER sources — intact; do not merely append. (A
renamed repo folder has its citations repointed mechanically, and a deleted folder is reconciled
out like any deleted source — neither reaches you as a repo session.)
