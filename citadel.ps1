#!/usr/bin/env pwsh
# AV-safe PowerShell wrapper for the CLI. Runs via `python -m` so there is NO
# citadel.exe launcher stub for Windows Defender to quarantine (which makes
# `uv run citadel` fail with "failed to spawn citadel: program not found").
# Usage from the repo root:  .\citadel.ps1 ingest   /   .\citadel.ps1 view   etc.
uv run python -m citadel @args
exit $LASTEXITCODE
