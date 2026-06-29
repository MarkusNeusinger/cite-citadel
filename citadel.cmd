@echo off
rem AV-safe Windows wrapper for the CLI. Runs via `python -m` so there is NO
rem citadel.exe launcher stub for Windows Defender to quarantine (which makes
rem `uv run citadel` fail with "failed to spawn citadel: program not found").
rem Usage from the repo root:  .\citadel ingest   /   .\citadel view   etc.
uv run python -m citadel %*
