---
type: Project
title: clockwork
description: A lightweight Python job scheduler that persists job state to PostgreSQL
  so a scheduler that was down catches up missed runs.
resource: raw/clockwork-repo
tags:
- job-scheduler
- python
- postgresql
- cron
- open-source
aliases:
- clockwork-scheduler
timestamp: '2026-07-14T12:26:21Z'
citadel_version: 0.3.0
---

# clockwork

`clockwork` is a lightweight Python job scheduler that runs recurring jobs defined in a plain
YAML file and persists every job's state to PostgreSQL, so a scheduler that was down catches up
the runs it missed instead of silently skipping them.[^s1] The design is deliberately small: one
poll loop over a PostgreSQL-backed job table, with no message broker and no worker pool — the
stated design goal is "boring and catch-up-correct" over "fast."[^s2]

It is released under the MIT license, copyright (c) 2025 The clockwork authors.[^s1][^s6]

## Install and configure

The package installs from PyPI as `clockwork-scheduler` (`pip install clockwork-scheduler`).[^s1]
Jobs are defined in a single YAML file, `clockwork.yml` by default, each entry giving a `name`, a
cron-syntax `schedule`, and a `command` to run.[^s1] For example:

```yaml
- name: nightly-export
  schedule: "0 2 * * *"
  command: "python -m exports.nightly"
```

The [PostgreSQL](../systems/postgresql.md) connection string is read from the **`CLOCKWORK_DB_URL`**
environment variable (a standard `postgresql://user:pass@host/dbname` DSN); it is required, and
`clockwork` refuses to start without it — enforced by a check that raises
`RuntimeError("CLOCKWORK_DB_URL is required")` when the variable is unset.[^s1][^s4]

## Running it

The scheduler is started with `clockwork run --config clockwork.yml` (after exporting
`CLOCKWORK_DB_URL`).[^s1] Two further subcommands round out the CLI: `clockwork add --name NAME
--schedule CRON --command CMD` registers a job without editing the YAML file, and `clockwork
status` prints each job's last run, next run, and last outcome.[^s1] The `clockwork` command is
the entry point declared for the `scheduler:main` function.[^s3]

## How it works

The scheduler runs a single poll loop with five steps, repeated forever:[^s2]

1. **Load.** On start, it reads `clockwork.yml` and upserts each job into the `jobs` table (name,
   cron schedule, command); YAML is the source of truth, and `clockwork add` writes the same
   rows.[^s2]
2. **Compute.** For each job, the next run time is computed from its cron expression (via the
   `croniter` library) and stored on the row.[^s2][^s3]
3. **Poll.** Every `poll_interval` seconds (default 60) the loop selects jobs whose next run time
   has passed — including runs missed while the scheduler was down, which is how catch-up
   works.[^s1][^s2][^s4]
4. **Claim.** Each due job is claimed with a PostgreSQL advisory lock keyed on the job name; a
   second scheduler process trying the same job fails to take the lock and moves on, so several
   instances can run for availability without double-firing.[^s1][^s2]
5. **Run + retry.** The claimed command runs; on failure it is retried up to `max_retries` times
   with exponential backoff (`backoff_base ** attempt` seconds, `backoff_base` default
   2.0).[^s1][^s2][^s4] `max_retries` defaults to 5 as of version 0.4.0 (raised from 3 after
   production users found transient outages routinely outlasted three attempts); set it
   explicitly to keep the old behaviour.[^s1][^s4][^s5] Every attempt — job name, status,
   `started_at`, `finished_at`, attempt number — is written to the `job_runs` table.[^s1][^s2][^s4]

`clockwork status` reads the `jobs` and `job_runs` tables to print each job's last outcome and
next run.[^s2] Job state and run history are stored in [PostgreSQL](../systems/postgresql.md).[^s2]

## Dependencies

`clockwork` requires Python 3.10+ and depends on three libraries: `psycopg[binary]>=3.1` (the
PostgreSQL driver backing the job store), `croniter>=2.0` (cron-syntax schedule parsing), and
`pyyaml>=6.0` (parsing `clockwork.yml`).[^s3]

## Version history

`clockwork` follows Semantic Versioning.[^s5] Version **0.4.0** (2026-02-17) raised the default
`max_retries` from 3 to 5, after production users reported that transient downstream outages
routinely outlasted three attempts — five retries with the existing exponential backoff clears
almost all of them; set `max_retries` explicitly to keep the old behaviour.[^s4][^s5] Job state
used to live in a local SQLite file; that could not be shared across scheduler instances, so
version 0.3.0 (2025-11-04) moved it to PostgreSQL (the `jobs` and `job_runs` tables) and made
`CLOCKWORK_DB_URL` required, alongside
adding the `clockwork status` subcommand and PostgreSQL advisory-lock claiming.[^s2][^s5] Version
0.2.0 (2025-08-19) added catch-up replay and exponential backoff between retries (`backoff_base`,
default 2.0).[^s5] Version 0.1.0 (2025-06-30) was the first release: cron-syntax job definitions
in YAML, a single poller, and the `clockwork run` entry point.[^s5]

## See also

- [PostgreSQL](../systems/postgresql.md)

## Sources

[^s1]: [raw/clockwork-repo](../../raw/clockwork-repo), README.md — overview, install, configure, run, behaviour (ingested 2026-07-14)
[^s2]: [raw/clockwork-repo](../../raw/clockwork-repo), docs/design.md — architecture and data flow (ingested 2026-07-14)
[^s3]: [raw/clockwork-repo](../../raw/clockwork-repo), pyproject.toml — package metadata and dependencies (ingested 2026-07-14)
[^s4]: [raw/clockwork-repo](../../raw/clockwork-repo), src/scheduler.py — Scheduler implementation (ingested 2026-07-14)
[^s5]: [raw/clockwork-repo](../../raw/clockwork-repo), CHANGELOG.md — version history (ingested 2026-07-14)
[^s6]: [raw/clockwork-repo](../../raw/clockwork-repo), LICENSE — MIT license text (ingested 2026-07-14)
