# clockwork

A lightweight Python job scheduler. `clockwork` runs recurring jobs defined in a
plain YAML file and **persists every job's state to PostgreSQL**, so a scheduler that
was down catches up the runs it missed instead of silently skipping them.

It is deliberately small: one poller, one Postgres table pair, no message broker.

## Install

```
pip install clockwork-scheduler
```

## Configure

Jobs live in a single YAML file (default `clockwork.yml`):

```yaml
jobs:
  - name: nightly-export
    schedule: "0 2 * * *"      # cron syntax
    command: "python -m exports.nightly"
  - name: heartbeat
    schedule: "*/5 * * * *"
    command: "curl -fsS https://example.test/ping"
```

The Postgres connection string is read from the **`CLOCKWORK_DB_URL`** environment
variable (a standard `postgresql://user:pass@host/dbname` DSN). It is required —
`clockwork` refuses to start without it.

## Run

```
export CLOCKWORK_DB_URL=postgresql://clockwork@localhost/clockwork
clockwork run --config clockwork.yml
```

Other subcommands:

- `clockwork add --name NAME --schedule CRON --command CMD` — register a job without editing YAML.
- `clockwork status` — print each job's last run, next run, and last outcome.

## Behaviour

- The poller wakes every **`poll_interval` seconds (default 60)** and claims any job whose
  next run time has passed.
- Only one scheduler instance ever runs a given job at a time — jobs are claimed through a
  **PostgreSQL advisory lock**, so you can run several `clockwork` processes for availability
  without double-firing.
- A failed job is retried up to **`max_retries` times (default 5 since 0.4.0)** with
  exponential backoff.
- Every attempt is written to the `job_runs` table (status, start/finish, attempt number).

See [docs/design.md](docs/design.md) for the architecture.

## License

MIT — see [LICENSE](LICENSE).
