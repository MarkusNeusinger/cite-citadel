# Contributing to cite-citadel

Thanks for helping out. cite-citadel is KISS, pure-Python 3.12, and its whole test suite is offline
— no CLI or network is ever spawned. Keep it that way.

## Dev setup

```bash
uv sync                 # creates .venv, installs runtime + dev deps + the `citadel` script
```

Use the **portable** invocation everywhere — it works identically on Linux/macOS/Windows and needs
no `.exe` (the `uv run citadel …` shorthand can break on Windows, where antivirus quarantines uv's
generated `citadel.exe`):

```bash
uv run python -m citadel <subcommand>
```

## Gates (CI runs all of these; run them before you push)

```bash
uv run pytest -q              # whole offline suite (~3s)
uv run ruff check .           # lint
uv run ruff format --check .  # format (use `ruff format .` to auto-fix)
uv run python -m citadel lint # structural health check
```

If you touch `ingest.py`, `llm.py`, the rules tree (`citadel/rules/`), the ingest prompts, or the
store, also run the end-to-end corpus grader before opening the PR:

```bash
# via the verify-corpus skill; grades a corpus in a throwaway sandbox against its hidden answer key
verify-corpus beverages
```

## Conventions that matter

These are load-bearing — a change that breaks one usually breaks tests or the pip-installed package:

- **`config.*` is read at call time** (`from . import config` then `config.WIKI_DIR`), never imported
  by value. Tests monkeypatch `config.*` to redirect the whole filesystem layout to `tmp_path`.
- **Tests stay offline.** No test spawns a real CLI; `llm.run_ingest_session` is the single seam a
  fake replaces. Follow the `tmp_citadel` conftest fixture and the `fake_agent` factory.
- **The rules tree is part of the program.** `citadel/rules/*.md` (schema, core, tasks, formats,
  genres) is read by the ingest agent at run time — editing it changes how the wiki is built with no
  code change. Prompts stay **paths-only** (they reference files by path, never embed content).
- **Never hand-edit generated files** — `index.md`, `log.md`, every `*/index.md`, `sources/index.md`,
  and `.citadel_ingested.json` are regenerated.
- **Provenance grammar is load-bearing.** Raw facts cite `[^sN]` → a real `raw/` file; model-supplied
  facts use `[^llmN]`. Never disguise one as the other.
- **Cross-platform robustness is intentional**, not over-engineering (UTF-8 forcing, ASCII-only
  progress, read-only-bit clearing, network-share retry loops). Don't simplify it away.

## PR flow

- Branch off `main` (e.g. `claude/<topic>-<slug>`); keep PRs focused.
- All gates green, then open a PR — ready, not draft. Don't self-merge.
- Update `CHANGELOG.md` (the `Unreleased` section) when a change is user-visible.

## Inbound = outbound

By contributing, you agree that your contributions are licensed under the project's
[MIT License](LICENSE) — the same license as the rest of cite-citadel. No CLA. A
`Signed-off-by:` line (DCO, `git commit -s`) is welcome but not required.
