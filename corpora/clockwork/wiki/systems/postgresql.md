---
type: System
title: PostgreSQL
description: The relational database clockwork uses to persist job definitions, schedule
  state, and run history.
resource: raw/clockwork-repo
tags:
- database
- postgresql
- advisory-lock
- job-scheduler
aliases:
- Postgres
timestamp: '2026-07-16T15:34:02Z'
citadel_version: 0.3.0
---

# PostgreSQL

PostgreSQL is the persistent store behind [clockwork](../projects/clockwork.md): the scheduler is
deliberately built as "one poller, one Postgres table pair, no message broker," rather than adding
a queue or worker pool.[^s1][^s2]

## How clockwork connects

clockwork reads its connection string from the **`CLOCKWORK_DB_URL`** environment variable — a
standard `postgresql://user:pass@host/dbname` DSN — and refuses to start if it is unset.[^s2][^s4]
It connects using the `psycopg` driver (`psycopg[binary]>=3.1`).[^s3]

## Schema

Two tables live in the database named by `CLOCKWORK_DB_URL`:[^s1]

- **`jobs`** — one row per job: `name` (primary key), `schedule`, `command`, `next_run_at`.[^s1]
- **`job_runs`** — one row per run attempt: `job_name`, `status` (`success`/`failed`),
  `started_at`, `finished_at`, `attempt`.[^s1]

`clockwork status` reads both tables to print each job's last outcome and next run.[^s1]

## Advisory locks for multi-instance safety

clockwork claims each due job through a PostgreSQL **advisory lock** keyed on the job name before
running it; a second `clockwork` process attempting the same job fails to take the lock and moves
on, so several scheduler instances can run concurrently for availability without ever
double-firing a job.[^s1][^s2][^s4]

## Why PostgreSQL

The design rationale given is that advisory locks provide multi-instance safety "for free," and
keeping run history in a database a team already operates avoids extra infrastructure.[^s1] Job
state previously lived in a local SQLite file, which could not be shared across scheduler
instances; version 0.3.0 (2025-11-04) moved it to PostgreSQL and made `CLOCKWORK_DB_URL`
required.[^s1][^s5]

## See also

- [clockwork](../projects/clockwork.md)

## Sources

[^s1]: [raw/clockwork-repo](../../raw/clockwork-repo), docs/design.md — data flow, storage schema, and Postgres rationale (ingested 2026-07-16)
[^s2]: [raw/clockwork-repo](../../raw/clockwork-repo), README.md — overview and behaviour (ingested 2026-07-16)
[^s3]: [raw/clockwork-repo](../../raw/clockwork-repo), pyproject.toml — dependencies (ingested 2026-07-16)
[^s4]: [raw/clockwork-repo](../../raw/clockwork-repo), src/scheduler.py — connection-string guard (ingested 2026-07-16)
[^s5]: [raw/clockwork-repo](../../raw/clockwork-repo), CHANGELOG.md — 0.3.0 migration from SQLite (ingested 2026-07-16)
