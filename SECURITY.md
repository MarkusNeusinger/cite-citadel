# Security Policy

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** — do not open a public issue for a security
problem. Use GitHub's [private vulnerability reporting](https://github.com/MarkusNeusinger/cite-citadel/security/advisories/new)
(Security → Report a vulnerability). Include a description, reproduction steps, and the impact you
see. You'll get an acknowledgement, and a fix or mitigation will be coordinated before any public
disclosure.

## Supported versions

cite-citadel is pre-1.0; only the latest released version on PyPI is supported. Please upgrade before
reporting.

## How ingest handles your data

cite-citadel has a small, honest data-flow surface — understanding it is the best defense:

- **cite-citadel spawns *your* CLI as a subprocess in the workspace.** Ingest does
  `shutil.which(<cli>)` + `subprocess` on the official coding-agent binary you installed and logged
  in (`claude` / `copilot` / `gemini`). It bundles no provider code, embeds no credentials, and
  **reads, logs, or transmits no secret or token itself.**
- **Raw content travels wherever your provider's terms say.** Your CLI reads the files under `raw/`
  under *your* account; where that content then goes (and whether prompts/logs are retained) is
  governed by that provider's terms, not by cite-citadel. See the README's
  [License & third-party tools](https://github.com/MarkusNeusinger/cite-citadel#license--third-party-tools)
  section for the linked provider terms.
- **Data-governance caveat.** Because ingest sends raw content to your CLI/provider, do **not** ingest
  confidential or regulated material on a plan whose terms permit training on inputs. Pick the
  plan/tier appropriate to your data sensitivity.
- **Transcript privacy.** A `CITADEL_LLM_LOG_DIR` transcript (prompt + full CLI stdout/stderr) can
  contain source content. It is written **local-only** — keep it out of version control and off
  shared locations. The generated `wiki/.citadel_failures.json` is likewise per-machine derived state
  and is gitignored. The same applies to the audio transcript cache (`CITADEL_AUDIO_SUPPORT`):
  `.citadel_transcripts/` next to the wiki dir holds each recording's spoken content as plaintext —
  and to the PDF text-layer cache (`.citadel_pdftext/`, written whenever the pypdf pre-pass runs —
  i.e. by default, unless `CITADEL_PDF_TEXT=0` or pypdf was force-removed), which holds each PDF's
  extracted text the same way —
  transcription itself runs fully locally (a whisper-class CLI on your machine), but treat the
  cache like the raw recordings themselves.
- **Billing shadow.** If a provider API key sits in your environment while `CITADEL_LLM_CLI=claude`,
  the CLI may bill the metered API instead of your subscription. `citadel doctor` warns about this;
  the same subscription-vs-API story is covered in the terms note above.
