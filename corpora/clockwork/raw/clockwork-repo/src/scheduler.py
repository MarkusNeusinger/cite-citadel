"""clockwork — a small PostgreSQL-backed job scheduler.

The :class:`Scheduler` reads job definitions from a YAML file, computes each job's next
run time from its cron expression, and runs a single poll loop that claims and executes
due jobs. State (the ``jobs`` and ``job_runs`` tables) lives in PostgreSQL, addressed by
the ``CLOCKWORK_DB_URL`` connection string, so a scheduler that was offline catches up the
runs it missed rather than skipping them.

Concurrency is safe by construction: a job is claimed through a PostgreSQL *advisory lock*
keyed on the job name, so multiple ``clockwork`` processes can run for availability without
ever double-firing a job.
"""

from __future__ import annotations

import os

# Poll cadence, in seconds: how often the loop wakes to look for due jobs.
DEFAULT_POLL_INTERVAL = 60

# How many times a failing job is retried before it is recorded as failed. Raised from 3
# to 5 in 0.4.0 after production users found transient outages routinely outlasted three
# attempts.
DEFAULT_MAX_RETRIES = 5

# Exponential-backoff base between retries: wait backoff_base ** attempt seconds.
DEFAULT_BACKOFF_BASE = 2.0


class Scheduler:
    """Run recurring jobs defined in ``config_path`` against the Postgres store.

    :param config_path: path to the YAML job file (default ``clockwork.yml``).
    :param poll_interval: seconds between poll cycles. Defaults to
        :data:`DEFAULT_POLL_INTERVAL` (60).
    :param max_retries: attempts before a job is marked failed. Defaults to
        :data:`DEFAULT_MAX_RETRIES` (5 since 0.4.0; was 3). Each retry waits
        ``backoff_base ** attempt`` seconds.

    The connection string is taken from the ``CLOCKWORK_DB_URL`` environment variable;
    the scheduler refuses to start if it is unset.
    """

    def __init__(
        self,
        config_path: str = "clockwork.yml",
        poll_interval: int = DEFAULT_POLL_INTERVAL,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
    ) -> None:
        db_url = os.environ.get("CLOCKWORK_DB_URL")
        if not db_url:
            raise RuntimeError("CLOCKWORK_DB_URL is required")
        self.db_url = db_url
        self.config_path = config_path
        self.poll_interval = poll_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    def run(self) -> None:
        """Poll forever: claim due jobs via an advisory lock, run them, record each attempt."""
        while True:
            for job in self._due_jobs():
                if self._claim(job):        # Postgres advisory lock on job.name
                    self._run_with_retries(job)
            self._sleep(self.poll_interval)

    # ... _due_jobs / _claim / _run_with_retries / _sleep omitted for brevity ...


def main() -> None:
    """CLI entry point backing the ``clockwork`` command (run / add / status)."""
    ...
