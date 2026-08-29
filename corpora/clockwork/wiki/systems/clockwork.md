---
type: System
title: clockwork
description: A lightweight Python job scheduler that runs cron-style YAML jobs and
  persists their state to PostgreSQL so missed runs are caught up.
resource: raw/clockwork-repo
tags:
- scheduler
- python
- job-scheduling
- postgresql
aliases:
- clockwork-scheduler
timestamp: '2026-08-28T23:54:23Z'
citadel_version: 0.6.0
---

`clockwork` is a lightweight Python job scheduler: it runs recurring jobs defined in a single YAML
file and persists every job's state to PostgreSQL, so a scheduler that was down catches up the runs
it missed instead of silently skipping them.[^s1] The design is deliberately small — one poll loop,
one Postgres table pair, no message broker.[^s2]

## Install and run

Install with `pip install clockwork-scheduler`.[^s1] Jobs are defined in a YAML file (default
`clockwork.yml`), each with a `name`, a cron-syntax `schedule`, and a `command` to run.[^s1] The
Postgres connection string is read from the **`CLOCKWORK_DB_URL`** environment variable (a
`postgresql://user:pass@host/dbname` DSN); `clockwork` refuses to start if it is unset.[^s1][^s3]
The scheduler is started with `clockwork run --config clockwork.yml`.[^s1]

## CLI

Besides `run`, `clockwork` offers `add --name NAME --schedule CRON --command CMD` to register a job
without editing the YAML file, and `status`, which prints each job's last run, next run, and last
outcome.[^s1]

## How it works

On start, the scheduler loads `clockwork.yml` and upserts each job into a `jobs` table (`clockwork
add` writes the same rows), then computes each job's next run time from its cron expression with
the `croniter` library.[^s2][^s4] Every `poll_interval` seconds (default 30 since version 0.4.0;
was 60) the poll loop selects jobs whose next run time has passed — including runs missed while the
scheduler was down, which is how catch-up works.[^s1][^s2][^s3][^s6] Each due job is claimed through
a **PostgreSQL advisory lock** keyed on the job name before it runs, so several `clockwork`
processes can run for availability without ever double-firing the same job.[^s1][^s2] A failed job
is retried up to `max_retries` times (default 5 since version 0.4.0; was 3) with exponential backoff
(`backoff_base ** attempt` seconds, `backoff_base` default 2.0).[^s1][^s3][^s6] Every attempt — job
name, status, start/finish time, attempt number — is written to the
[PostgreSQL](../systems/postgresql.md) `job_runs` table.[^s1][^s2]

Job state used to live in a local SQLite file; because that could not be shared across scheduler
instances, state moved to [PostgreSQL](../systems/postgresql.md) before version 0.3.0, which is also
when `CLOCKWORK_DB_URL` became required.[^s2]

## Version and requirements

The current release is **0.4.0**.[^s4] `clockwork` is licensed under the MIT License.[^s5]

> [!CONTRADICTION]
> The README states `clockwork` requires Python 3.11 or newer[^s1], but `pyproject.toml` declares
> `requires-python = ">=3.10"`[^s4]. Nothing in the repository dates or resolves the discrepancy.

## Change Log

- 2026-02-17: `poll_interval` default lowered from 60 to 30 seconds, so short cron schedules fire
  closer to their nominal time.[^s3][^s6]
- 2026-02-17: `max_retries` default raised from 3 to 5, after production users found transient
  downstream outages routinely outlasted three attempts.[^s3][^s6]

## Release history

The first release, 0.1.0 (2025-06-30), provided cron-syntax YAML job definitions with a single
poller and a `clockwork run` entry point.[^s6] Version 0.2.0 (2025-08-19) added catch-up for missed
runs and exponential retry backoff.[^s6] Version 0.3.0 (2025-11-04) added the `status` subcommand and
PostgreSQL advisory-lock claiming, and moved job state from SQLite to PostgreSQL.[^s6] Version 0.4.0
(2026-02-17) lowered the default `poll_interval` from 60 to 30 seconds and raised the default
`max_retries` from 3 to 5.[^s6]

## See also

- [PostgreSQL](../systems/postgresql.md)

## Sources

[^s1]: [raw/clockwork-repo](../../raw/clockwork-repo) — README.md (ingested 2026-08-29)
[^s2]: [raw/clockwork-repo](../../raw/clockwork-repo) — docs/design.md (ingested 2026-08-29)
[^s3]: [raw/clockwork-repo](../../raw/clockwork-repo) — src/scheduler.py (ingested 2026-08-29)
[^s4]: [raw/clockwork-repo](../../raw/clockwork-repo) — pyproject.toml (ingested 2026-08-29)
[^s5]: [raw/clockwork-repo](../../raw/clockwork-repo) — LICENSE (ingested 2026-08-29)
[^s6]: [raw/clockwork-repo](../../raw/clockwork-repo) — CHANGELOG.md (ingested 2026-08-29)
