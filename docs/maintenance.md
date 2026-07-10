# Maintain & customize

Ingest builds the wiki; this page covers everything after that: `citadel curate` (the second
lifecycle, which improves pages that already exist), `citadel status` (the read-only view of what
has been ingested), and customizing the rules the ingest agent follows — without touching any code.

## Curate

`citadel curate` improves **existing** pages: it re-sorts a page whose `type` doesn't match its
folder, splits pages that grew too long, re-grounds facts against their cited sources, resolves
contradictions, connects orphans, and fixes citation locators. There is no persisted queue — the
plan is recomputed from offline detectors on every run (the wiki *is* the database), so running it
is always safe and idempotent. Each planned page (plus its cited raw files and link neighbors)
gets one agent session against a staging copy of the wiki, exactly like ingest: a clean result is
promoted, anything else is rolled back — the live wiki is never left half-edited.

When to run it:

- **After editing the rules** (see below): `citadel curate --stale-rules` refreshes pages whose
  sources were ingested under an older rulebook (`citadel status` marks them `(stale)`).
- **Periodically on a growing wiki**: after many ingest runs, `citadel lint` tends to accumulate
  advisories (contradictions, orphans, locator issues) — curate works through them.
- **Preview first**: `citadel curate --dry-run` prints the plan and runs zero agent sessions.

Flags:

| Flag | What it does |
|------|--------------|
| `--dry-run` | Recompute and print the plan only; run zero agent sessions, leave the wiki untouched. |
| `--limit N` | Curate at most the first N clusters of the plan. |
| `--stale-rules` | Restrict the plan to pages whose source was ingested under an older rulebook. |
| `--diff PATH` | Write a per-page change report (unified diffs) for this run to PATH. |
| `--retry` | Include attempt-capped clusters in this run (see below). |

A cluster that fails is recorded with an `attempts` counter and retried on the next run — but only
up to **2 attempts**; after that it is skipped ("attempt-capped") so one stubborn page can't burn
agent sessions forever. `--retry` is the explicit override that puts capped clusters back into the
plan. Curate sessions use `CITADEL_CURATE_MODEL` when set (a cheaper/faster model is often fine
here), falling back to the ingest model — see [configuration.md](configuration.md).

## Status

`citadel status` is the read-only answer to "what state is my corpus in?": one table row per
source — **ingested** (with the importing model and rules version, plus `(stale)` when the source
was ingested under an older rulebook than the current one), **failed** (with the reason and attempt
count), **skipped-duplicate**, **ignored** (which pattern matched), or **pending** (not yet
ingested — the next `citadel ingest` will pick it up). It never runs an agent and never re-hashes
sources, so it is always cheap to run.

## Rules

The wiki is built by rules files the ingest agent reads at run time — `schema.md` (the format
contract), `core.md` (agent behavior), plus per-lifecycle `tasks/`, per-file-type `formats/`, and
`genres/` briefs. **Editing them changes how the wiki is built with no code change.** They ship
inside the package, and three subcommands make them yours:

```bash
citadel rules list              # every effective rules file: name, layer (packaged|workspace), description
citadel rules show core.md      # print one effective rules file
citadel rules eject core.md     # copy a packaged file into <workspace>/rules/ for editing
```

Two customization mechanisms, from lightest to heaviest:

- **`rules/local.md` — additive house rules.** Create `<workspace>/rules/local.md` and write your
  own instructions in it (preferred page style, domain glossary, "always tag X as Y", …). It is
  appended to every session's rules list on top of the packaged defaults, so it survives package
  upgrades untouched. This is the right home for most customization.
- **`rules eject` — fork a packaged file.** `citadel rules eject <name>` copies the packaged file
  to `<workspace>/rules/<name>`; a workspace file **shadows** the packaged one with the same
  tree-relative name (first-hit-wins per filename — `citadel rules list` shows which layer wins).
  The copy is yours to edit, refuses to be overwritten by a re-eject, and **no longer updates with
  pip** — prefer `local.md` unless you need to change what a default file says. You can also drop a
  brand-new genre brief in `<workspace>/rules/genres/<name>.md`; it participates automatically.

Any edit to an effective rules file changes the rules version stamped per source, so
`citadel status` shows previously ingested sources as `(stale)` — that is expected, and
`citadel curate --stale-rules` is the command that brings those pages up to the new rules.
