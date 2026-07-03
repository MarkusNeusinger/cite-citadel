---
name: open-pr
description: Use when asked to open or create a PR, commit and push, ship a change, or finish up a change — even if they do not say the word skill. Runs the hard local gates (pytest, ruff check, ruff format --check, and the beverages-workspace lint), routes ingest/llm/rules changes through verify-corpus first, branches claude/<topic>-<slug> off main, opens a ready (non-draft) PR with the Claude Code footer, requests the Copilot review, then watches CI and resolves review threads. Stops at green + resolved with the PR URL; never merges.
---

# Open a PR

The one path from "the change is done" to "a green PR waiting on the human". **Gate locally first,
then push once.** Every step below is runnable bash with an `Expected:` baseline so the first line
that does not match names what broke. **You never merge** — you stop at green + resolved and hand the
URL back.

## 0. Preconditions

- Work from the repo checkout on a feature branch (never commit to `main`).
- `gh` is authenticated (`gh auth status`) and `uv sync` has been run.
- Know the one-line topic of the change — it becomes the branch slug and the PR title.

## 1. Branch off main

Branch name is `claude/<topic>-<slug>` (kebab-case, no spaces). If you are already on such a branch
with your work, skip the checkout.

```bash
git fetch origin
git checkout -b claude/doctor-billing-warning origin/main   # <topic>-<slug>, based on fresh main
```

Expected: `Switched to a new branch 'claude/doctor-billing-warning'`.

## 2. Route the diff (verify-corpus BEFORE the gates)

Look at what the diff touches — `git diff --name-only origin/main...HEAD` — and run the matching
corpus verification **before** the local gates, because the offline suite does NOT exercise a real
ingest:

| The diff touches… | Run first |
| ----------------- | --------- |
| `citadel/ingest.py`, `citadel/llm.py`, or `citadel/rules/**` | `/verify-corpus <affected-corpus>` — minimally the corpus that stresses the change (see the table in that skill); `all` for a broad rules/ingest change |
| anything else (cli, store, viewer, docs, tests) | nothing extra — the offline suite covers it |

verify-corpus spends a real ingest (minutes, your subscription), so scope it to the affected corpus,
not `all`, unless the change is broad. A hard-gate failure there is a finding — fix it before pushing.

Expected: verify-corpus ends with a per-corpus PASS verdict (its hard gates hold).

## 3. Local gates (all four must pass)

Run them one at a time so a red one stops you immediately. **Do not pipe `pytest` through `tail`
inside an `&&` chain** — the pipe swallows pytest's exit code and a failing run looks green.

```bash
uv run pytest -q
```
Expected: last line `NNN passed in …s` (no `failed`, no `errors`).

```bash
uv run ruff check .
```
Expected: `All checks passed!`

```bash
uv run ruff format --check .
```
Expected: `N files already formatted` (if it reports files that WOULD reformat, run `uv run ruff
format .` and re-stage).

```bash
CITADEL_WORKSPACE=corpora/beverages uv run python -m citadel lint
```
Expected: final line `OK`. This mirrors ci.yml's "Lint the showcase wiki" step exactly — the
checkout-root marker only wins from the root, so the env override selects the nested beverages
workspace.

## 4. Commit and push

Stage intentionally (`git add -p` or explicit paths), then one focused commit. End the message with
the repo's co-author trailer.

```bash
git add citadel/ tests/ CLAUDE.md .github/copilot-instructions.md
git commit -m "$(cat <<'EOF'
doctor: warn on the ANTHROPIC_API_KEY billing shadow

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>
EOF
)"
git push -u origin HEAD
```

Expected: `Branch 'claude/…' set up to track 'origin/…'` and a `remote:` line offering a compare URL.
A `warning: … LF will be replaced by CRLF` line is noise — ignore it.

## 5. Open the PR (ready, not draft)

```bash
gh pr create --base main --head "$(git branch --show-current)" \
  --title "doctor: warn on the ANTHROPIC_API_KEY billing shadow" \
  --body "$(cat <<'EOF'
## What

One-paragraph summary of the change and why.

## Testing

- `uv run pytest -q` — green
- `uv run ruff check .` / `ruff format --check .` — clean
- `CITADEL_WORKSPACE=corpora/beverages uv run python -m citadel lint` — OK
- verify-corpus <corpus> (if ingest/llm/rules changed)

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: the new PR URL on stdout (`https://github.com/MarkusNeusinger/cite-citadel/pull/NN`).
`gh pr create` opens a **ready** PR by default — do not pass `--draft`.

## 6. Request the Copilot review

Request the Copilot reviewer explicitly (it is a bot, so `--reviewer` on `gh pr create` cannot add
it — use the API with the bot's exact login):

```bash
PR=$(gh pr view --json number -q .number)
gh api --method POST "repos/{owner}/{repo}/pulls/$PR/requested_reviewers" \
  -f "reviewers[]=copilot-pull-request-reviewer[bot]"
```

Expected: a JSON blob echoing the PR with `copilot-pull-request-reviewer[bot]` under
`requested_reviewers` (HTTP 201). Copilot posts its review within a minute or two.

## 7. Watch CI, then address the review

**Wait for the checks to REGISTER before watching** — for a few seconds right after a push the PR has
zero checks and `--watch` exits immediately reporting success on an empty set. Poll until at least one
check exists, then watch:

```bash
until gh pr checks "$PR" 2>/dev/null | grep -q .; do sleep 5; done   # wait for checks to appear
gh pr checks "$PR" --watch                                            # blocks until they finish
```
Expected: every row ends `pass` (`gh pr checks` exits 0). `gh pr checks` has **no** `--json` flag; for
machine-readable status use `gh pr view "$PR" --json statusCheckRollup`.

Then pull the Copilot (and any human) review and act on each thread:

```bash
gh pr view "$PR" --comments                                          # read the review comments
```

For every comment: either fix it in a follow-up commit (`git commit … && git push`) or reply on the
thread explaining why it is intentional. Re-run the section-3 gates after any code fix, then re-watch
CI. Resolve each thread once addressed.

## 8. Stop condition — hand it back, never merge

Stop when **all** hold, and report the PR URL:

- section-3 gates green locally,
- `gh pr checks "$PR"` all `pass`,
- every review thread resolved (fixed or answered).

Then STOP. **Never `gh pr merge`** — merging is the human's call. Your final message is the PR URL
plus a one-line status ("CI green, Copilot review addressed, ready for review").

## Gotchas (real incidents from this refactor)

- **`gh pr checks` has no `--json`.** Parse its table, or switch to `gh pr view --json
  statusCheckRollup` for structured status.
- **The beverages lint needs its own workspace.** Plain `citadel lint` from the checkout root lints
  the dev workspace, not the showcase; `CITADEL_WORKSPACE=corpora/beverages` selects the nested
  marker, matching CI.
