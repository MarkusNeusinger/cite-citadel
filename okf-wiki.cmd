@echo off
rem AV-safe Windows wrapper for the CLI. Runs via `python -m` so there is NO
rem okf-wiki.exe launcher stub for Windows Defender to quarantine (which makes
rem `uv run okf-wiki` fail with "failed to spawn okf-wiki: program not found").
rem Usage from the repo root:  .\okf-wiki ingest   /   .\okf-wiki view   etc.
uv run python -m okf_wiki %*
