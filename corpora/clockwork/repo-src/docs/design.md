# clockwork — design

`clockwork` is one poll loop over a PostgreSQL-backed job table. There is no message broker
and no worker pool; the design goal is "boring and catch-up-correct" over "fast."

## Data flow

1. **Load.** On start, the scheduler reads `clockwork.yml` and upserts each job into the
   `jobs` table (name, cron schedule, command). YAML is the source of truth; `clockwork add`
   writes the same rows.
2. **Compute.** For each job, the next run time is computed from its cron expression with
   `croniter` and stored on the row.
3. **Poll.** Every `poll_interval` seconds (default 60) the loop selects jobs whose next run
   time has passed — including runs missed while the scheduler was down, which is how catch-up
   works.
4. **Claim.** Each due job is claimed with a **PostgreSQL advisory lock** keyed on the job
   name. A second scheduler process trying the same job fails to take the lock and moves on,
   so several instances can run for availability with no double-firing.
5. **Run + retry.** The claimed command is executed. On failure it is retried up to
   `max_retries` times with exponential backoff (`backoff_base ** attempt` seconds); the
   default `max_retries` is documented in `src/scheduler.py` and the README.
6. **Record.** Every attempt is written to the `job_runs` table: the job name, status
   (`success` / `failed`), `started_at`, `finished_at`, and the attempt number.

## Storage

Two tables, both in the database named by `CLOCKWORK_DB_URL`:

- `jobs` — one row per job: `name` (primary key), `schedule`, `command`, `next_run_at`.
- `job_runs` — one row per attempt: `job_name`, `status`, `started_at`, `finished_at`,
  `attempt`.

`clockwork status` reads these two tables to print each job's last outcome and next run.

## Why PostgreSQL

The advisory locks give multi-instance safety for free, and putting run history in the same
database a team already operates means no extra infrastructure. Job state used to live in a
local SQLite file (before 0.3.0); that could not be shared across instances, which is why the
move to Postgres also made `CLOCKWORK_DB_URL` required.
