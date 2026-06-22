#!/usr/bin/env pwsh
# AV-safe PowerShell wrapper for the CLI. Runs via `python -m` so there is NO
# okf-wiki.exe launcher stub for Windows Defender to quarantine (which makes
# `uv run okf-wiki` fail with "failed to spawn okf-wiki: program not found").
# Usage from the repo root:  .\okf-wiki.ps1 ingest   /   .\okf-wiki.ps1 view   etc.
uv run python -m okf_wiki @args
exit $LASTEXITCODE
