---
type: System
title: PostgreSQL
description: The relational database clockwork uses to persist job definitions and
  run history, coordinated with advisory locks.
resource: raw/clockwork-repo
tags:
- database
- postgresql
- job-scheduling
timestamp: '2026-08-28T23:52:01Z'
citadel_version: 0.6.0
---

PostgreSQL is the database [clockwork](../systems/clockwork.md) uses as its job-state store,
addressed by the connection string (DSN) in the **`CLOCKWORK_DB_URL`** environment variable; the
scheduler refuses to start without it.[^s1][^s2]

## Tables

Two tables live in the database named by `CLOCKWORK_DB_URL`: `jobs` — one row per job, keyed by
`name`, holding `schedule`, `command`, and `next_run_at` — and `job_runs` — one row per run attempt,
holding `job_name`, `status`, `started_at`, `finished_at`, and `attempt`.[^s1] `clockwork status`
reads these two tables to print each job's last outcome and next run.[^s1]

## Advisory locks

clockwork claims each due job through a PostgreSQL **advisory lock** keyed on the job name; a second
scheduler process attempting the same job fails to take the lock and moves on, which is how several
`clockwork` instances can run for availability without ever double-firing a job.[^s1][^s2]

## Why PostgreSQL

The design rationale is that advisory locks give multi-instance safety "for free", and keeping run
history in a database a team already operates avoids extra infrastructure.[^s1] Job state previously
lived in a local SQLite file; because that could not be shared across scheduler instances, the move
to PostgreSQL is also why `CLOCKWORK_DB_URL` became required.[^s1]

## See also

- [clockwork](../systems/clockwork.md)

## Sources

[^s1]: [raw/clockwork-repo](../../raw/clockwork-repo) — docs/design.md (ingested 2026-08-29)
[^s2]: [raw/clockwork-repo](../../raw/clockwork-repo) — README.md (ingested 2026-08-29)
