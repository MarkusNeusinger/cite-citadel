# NOTICE

## Affiliation & trademark disclaimer

cite-citadel is an independent open-source project. It is **not affiliated with, endorsed by, or
sponsored by** Anthropic, GitHub, Microsoft, or Google.

cite-citadel ships **no** provider code and **no** LLM SDK. Ingest works by shelling out to a
coding-agent CLI that *you* have already installed and logged in (`shutil.which(<cli>)` +
`subprocess` on the official binary). The project embeds no credentials, reimplements no backend
endpoint, and never reads or forwards an authentication token.

The names below are used **only to identify the user-supplied CLI** cite-citadel can drive. They are
the trademarks of their respective owners:

- **Claude** and **Claude Code** — trademarks of Anthropic, PBC.
- **GitHub Copilot** — a trademark of GitHub, Inc. / Microsoft Corporation.
- **Gemini** — a trademark of Google LLC.

Use of these names does not imply any endorsement, sponsorship, or affiliation. Each provider's
software is governed by that provider's own license and terms — see the README's
[License & third-party tools](https://github.com/MarkusNeusinger/cite-citadel#license--third-party-tools)
section.

## License

cite-citadel itself is licensed under the [MIT License](LICENSE). The generated `wiki/` content is
yours; the project claims nothing over it.

## Bundled test data

The `corpora/literature/` test corpus contains the full text of Jane Austen's *Pride and Prejudice*
(1813), a **public-domain** work, derived from Project Gutenberg eBook #1342 with all Project
Gutenberg boilerplate (the `*** START/END OF …***` markers and any surrounding trademark/licence
text) removed; Project Gutenberg is not affiliated with this project.

## Dependency licenses

The distributed wheel contains only cite-citadel's own MIT-licensed code — it bundles no third-party
source. Its declared dependencies are permissive, so nothing copyleft rides along under the MIT
wheel:

| Dependency | Scope | License |
|------------|-------|---------|
| `mcp` | runtime | MIT |
| `pyyaml` | runtime | MIT |
| `pytest` | dev only | MIT |
| `ruff` | dev only | MIT |

`mcp` is the **open** Model Context Protocol SDK, not a proprietary Anthropic client — depending on
it creates no vendor-terms tie. (Verified against the installed distribution metadata on
2026-07-03; transitive dependencies are resolved by pip at install time and are not bundled in the
wheel.)

---

*This notice is informational and is **not legal advice**. Definitive licensing and trademark
conclusions across jurisdictions are for counsel, not this document.*
