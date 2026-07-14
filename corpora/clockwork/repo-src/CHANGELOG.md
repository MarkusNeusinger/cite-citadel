# Changelog

All notable changes to `clockwork` are recorded here. This project follows
[Semantic Versioning](https://semver.org/).

## [0.3.0] - 2025-11-04

### Added
- `clockwork status` subcommand: prints each job's last run, next run, and last outcome.
- PostgreSQL advisory-lock claiming so several scheduler instances can run for availability
  without double-firing a job.

### Changed
- Job state moved from a local SQLite file to PostgreSQL (`jobs` + `job_runs` tables). The
  `CLOCKWORK_DB_URL` environment variable is now required.

## [0.2.0] - 2025-08-19

### Added
- Catch-up: a scheduler that was down replays the runs it missed instead of skipping them.
- Exponential backoff between retries (`backoff_base`, default 2.0).

## [0.1.0] - 2025-06-30

### Added
- First release: cron-syntax job definitions in YAML, a single poller, and a `clockwork run`
  entry point.
