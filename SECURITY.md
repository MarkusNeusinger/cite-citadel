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
  cache like the raw recordings themselves. Resume checkpoints (`CITADEL_RESUME`, on by default)
  are the same class of derived state: `.citadel_resume/` next to the wiki dir banks the wiki pages
  a chunked source's completed segments produced, in plaintext, until that source finishes (or an
  age sweep clears it). It only ever materializes for a large source whose run was interrupted;
  `CITADEL_RESUME=0` turns it off entirely, at the cost of re-paying for those segments.
- **Serving is local by default; HTTP is opt-in and authenticated.** `citadel serve` speaks stdio —
  the client spawns it, nothing listens on a socket. `citadel serve --http` additionally binds a
  port (MCP Streamable HTTP) and is the one network surface citadel has. It refuses to start
  without `CITADEL_HTTP_TOKEN` (≥16 characters); every request must carry
  `Authorization: Bearer <token>`, compared in constant time (both sides are hashed first, so not
  even the presented token's length shows up in the timing), and an unauthenticated request is
  answered 401 before it reaches a tool or a session. The bind defaults to loopback, and
  DNS-rebinding protection is on: a request's `Host` must be a name the server accepts — derived
  from the bind address, or named in `CITADEL_HTTP_ALLOWED_HOSTS` for a tunnel/proxy (a `0.0.0.0`
  bind refuses to start without it, rather than accepting any name) — and a request carrying a
  browser `Origin` is refused unless `CITADEL_HTTP_ALLOWED_ORIGINS` admits it. The transport itself
  is **plain HTTP**: put a TLS-terminating tunnel (cloudflared / tailscale / `ssh -R`) in front of
  it rather than binding a public interface, and prefer `--read-only`
  (`CITADEL_HTTP_READ_ONLY=1`) for anything reachable beyond your own machine — it disables
  `wiki_capture` and `wiki_ingest` (they stay listed but answer with a refusal), the latter of which
  spawns your coding-agent CLI on the serving host. Treat the token like a password to the whole
  workspace: it is the only credential, and rotating it is just editing `.env` and restarting.
- **Billing shadow.** If a provider API key sits in your environment while `CITADEL_LLM_CLI=claude`,
  the CLI may bill the metered API instead of your subscription. `citadel doctor` warns about this;
  the same subscription-vs-API story is covered in the terms note above.
