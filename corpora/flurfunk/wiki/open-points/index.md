# Open Points

Tracked open points and their timelines, generated from every `## Open Points` section in the wiki. Grouped open-first; each links to the host page, which carries the citations. Generated — do not edit.

## Open (1)

### Rename retention-svc to janitor
host: [Skylight](../systems/skylight.md) · updated 2026-02-11 · id: op-rename-retention-svc-to-janitor
- 2026-02-09: during the event-retention discussion, Sofia Ruiz remarked the `retention-svc` service was "basically a janitor at this point," and Tom Alvarez proposed renaming it `retention-svc` to `janitor`, noting it had grown to run about four unrelated cleanup jobs; the team agreed, and Alvarez filed a low-priority rename ticket.
- 2026-02-11: still open; the rename ticket exists but remains low priority and undone. Sofia Ruiz volunteered to pick it up.

## Done (1)

### Dashboards stale after a timezone change
host: [Skylight](../systems/skylight.md) · updated 2026-02-19 · id: op-dashboards-stale-after-timezone-change
- 2026-02-18: raised by gridlock_92 in the Larkspur community forum: after moving their org from US/Eastern to Europe/Berlin, Skylight dashboards froze on old data even though new events kept landing; a browser-cache cause and an ingestion outage were both ruled out.
- 2026-02-19: root-caused and fixed by Sofia Ruiz of Larkspur Support: `janitor` was bucketing events with the org's stale, cached UTC offset; the fix is to set `SKYLIGHT_TZ` to the org's IANA timezone and restart `janitor`.
- 2026-02-19: resolved; gridlock_92 confirmed the dashboards resumed rolling forward within a minute of applying the fix.
