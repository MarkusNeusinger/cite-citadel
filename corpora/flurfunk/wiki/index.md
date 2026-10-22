# Wiki Index

The wiki's home index: every page grouped by type (with backlinks), plus tags and the source/open-point catalogs. Generated — do not edit.

See also: [concepts](concepts/index.md) · [organizations](organizations/index.md) · [persons](persons/index.md) · [systems](systems/index.md) · [sources](sources/index.md) · [open points](open-points/index.md)

## Concept
- [Platform team retro — Q1 2026](concepts/platform-team-retro-q1-2026.md) — What the reconstructed Q1 2026 platform team retro records about the CI speed-up, the Friday demo slot, the lost coverage reporting and a coverage check.
- [Platform team retro — Q3 2025](concepts/platform-team-retro-q3-2025.md) — What the reconstructed Q3 2025 platform team retro records about on-call, runbooks and flaky tests.
  - ↳ referenced by: [Platform team retro — Q4 2025](concepts/platform-team-retro-q4-2025.md), [Platform team retros](concepts/platform-team-retros.md)
- [Platform team retro — Q4 2025](concepts/platform-team-retro-q4-2025.md) — What the reconstructed Q4 2025 platform team retro records about flaky tests, the 14 November ingestion outage, postmortems, staging disk and CI speed.
  - ↳ referenced by: [Platform team retro — Q1 2026](concepts/platform-team-retro-q1-2026.md), [Platform team retros](concepts/platform-team-retros.md)
- [Platform team retros](concepts/platform-team-retros.md) — Provenance of the quarterly platform team retro summaries — reconstructed from chat history and unconfirmed by the team.
  - ↳ referenced by: [Platform team retro — Q1 2026](concepts/platform-team-retro-q1-2026.md), [Platform team retro — Q3 2025](concepts/platform-team-retro-q3-2025.md), [Platform team retro — Q4 2025](concepts/platform-team-retro-q4-2025.md)
- [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md) — The default time range of dashboards in new Skylight workspaces — kept at last 24 hours after a briefly adopted switch to 7 days was scrapped.
  - ↳ referenced by: [Skylight event retention default](concepts/skylight-event-retention-default.md), [Tom Alvarez](persons/tom-alvarez.md), [Wei Chen](persons/wei-chen.md), [Skylight](systems/skylight.md)
- [Skylight dashboard stale after timezone change](concepts/skylight-dashboard-stale-after-timezone-change.md) — Forum case of Skylight dashboards freezing after an org changed timezone, and the SKYLIGHT_TZ plus janitor restart fix.
  - ↳ referenced by: [Sofia Ruiz](persons/sofia-ruiz.md), [janitor](systems/janitor.md), [Skylight](systems/skylight.md)
- [Skylight event retention default](concepts/skylight-event-retention-default.md) — How long Skylight keeps events by default — currently 30 days, after a 7-day default was set and reverted in February 2026.
  - ↳ referenced by: [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md), [Larkspur](organizations/larkspur.md), [Northwind](organizations/northwind.md), [Sofia Ruiz](persons/sofia-ruiz.md), [Tom Alvarez](persons/tom-alvarez.md), [Wei Chen](persons/wei-chen.md), [Skylight](systems/skylight.md)

## Organization
- [Larkspur](organizations/larkspur.md) — Company behind the Skylight real-time analytics dashboard, founded in Lisbon in 2021.
  - ↳ referenced by: [Northwind](organizations/northwind.md), [Dana Kessler](persons/dana-kessler.md), [@marcusfeld](persons/marcusfeld.md), [Priya Nadkarni](persons/priya-nadkarni.md), [Sofia Ruiz](persons/sofia-ruiz.md), [Skylight](systems/skylight.md)
- [Northwind](organizations/northwind.md) — Skylight customer that lost event history needed for a compliance audit under the short-lived 7-day retention default.
  - ↳ referenced by: [Skylight event retention default](concepts/skylight-event-retention-default.md), [Sofia Ruiz](persons/sofia-ruiz.md), [Skylight](systems/skylight.md)

## Person
- [Dana Kessler](persons/dana-kessler.md) — Platform engineer based in Amsterdam who applied to Larkspur as Senior Platform Engineer in March 2026 (self-reported background).
  - ↳ referenced by: [Larkspur](organizations/larkspur.md), [Skylight](systems/skylight.md)
- [@marcusfeld](persons/marcusfeld.md) — X account that posted the Skylight sub-second refresh launch thread on 2026-02-12; real name not given in the source.
  - ↳ referenced by: [Skylight](systems/skylight.md)
- [Priya Nadkarni](persons/priya-nadkarni.md) — Founder and CEO of Larkspur, who previously worked on analytics infrastructure at larger companies.
  - ↳ referenced by: [Larkspur](organizations/larkspur.md), [Skylight](systems/skylight.md)
- [Sofia Ruiz](persons/sofia-ruiz.md) — Larkspur Support staff member who answered a Skylight timezone question on the community forum.
  - ↳ referenced by: [Skylight dashboard stale after timezone change](concepts/skylight-dashboard-stale-after-timezone-change.md), [Skylight event retention default](concepts/skylight-event-retention-default.md), [Larkspur](organizations/larkspur.md), [Northwind](organizations/northwind.md), [Tom Alvarez](persons/tom-alvarez.md), [Wei Chen](persons/wei-chen.md), [janitor](systems/janitor.md)
- [Tom Alvarez](persons/tom-alvarez.md) — Participant in Larkspur's
  - ↳ referenced by: [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md), [Skylight event retention default](concepts/skylight-event-retention-default.md), [Larkspur](organizations/larkspur.md), [Sofia Ruiz](persons/sofia-ruiz.md), [Wei Chen](persons/wei-chen.md), [janitor](systems/janitor.md)
- [Wei Chen](persons/wei-chen.md) — Participant in Larkspur's
  - ↳ referenced by: [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md), [Skylight event retention default](concepts/skylight-event-retention-default.md), [Larkspur](organizations/larkspur.md), [Sofia Ruiz](persons/sofia-ruiz.md), [Tom Alvarez](persons/tom-alvarez.md)

## System
- [janitor](systems/janitor.md) — Skylight service that buckets incoming events into time windows using the org's UTC offset, cached at startup.
  - ↳ referenced by: [Skylight dashboard stale after timezone change](concepts/skylight-dashboard-stale-after-timezone-change.md), [Sofia Ruiz](persons/sofia-ruiz.md), [Tom Alvarez](persons/tom-alvarez.md), [Wei Chen](persons/wei-chen.md), [Skylight](systems/skylight.md)
- [Skylight](systems/skylight.md) — Larkspur's real-time analytics dashboard, with release 2.0 generally available in three regions since 1 April 2026.
  - ↳ referenced by: [Platform team retros](concepts/platform-team-retros.md), [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md), [Skylight dashboard stale after timezone change](concepts/skylight-dashboard-stale-after-timezone-change.md), [Skylight event retention default](concepts/skylight-event-retention-default.md), [Larkspur](organizations/larkspur.md), [Northwind](organizations/northwind.md), [Dana Kessler](persons/dana-kessler.md), [@marcusfeld](persons/marcusfeld.md), [Priya Nadkarni](persons/priya-nadkarni.md), [Tom Alvarez](persons/tom-alvarez.md), [janitor](systems/janitor.md)

## Tags

### analytics (2)
- [Larkspur](organizations/larkspur.md)
- [Skylight](systems/skylight.md)

### application (1)
- [Dana Kessler](persons/dana-kessler.md)

### ci (1)
- [Platform team retro — Q1 2026](concepts/platform-team-retro-q1-2026.md)

### customer (1)
- [Northwind](organizations/northwind.md)

### dashboard (2)
- [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md)
- [Skylight](systems/skylight.md)

### data-engineering (1)
- [Dana Kessler](persons/dana-kessler.md)

### decision (2)
- [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md)
- [Skylight event retention default](concepts/skylight-event-retention-default.md)

### incidents (1)
- [Platform team retro — Q4 2025](concepts/platform-team-retro-q4-2025.md)

### interview (1)
- [Priya Nadkarni](persons/priya-nadkarni.md)

### larkspur (7)
- [Larkspur](organizations/larkspur.md)
- [Dana Kessler](persons/dana-kessler.md)
- [Priya Nadkarni](persons/priya-nadkarni.md)
- [Sofia Ruiz](persons/sofia-ruiz.md)
- [Tom Alvarez](persons/tom-alvarez.md)
- [Wei Chen](persons/wei-chen.md)
- [Skylight](systems/skylight.md)

### launch (1)
- [@marcusfeld](persons/marcusfeld.md)

### leadership (1)
- [Priya Nadkarni](persons/priya-nadkarni.md)

### on-call (1)
- [Platform team retro — Q3 2025](concepts/platform-team-retro-q3-2025.md)

### platform (4)
- [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md)
- [Skylight event retention default](concepts/skylight-event-retention-default.md)
- [Tom Alvarez](persons/tom-alvarez.md)
- [Wei Chen](persons/wei-chen.md)

### platform-team (4)
- [Platform team retro — Q1 2026](concepts/platform-team-retro-q1-2026.md)
- [Platform team retro — Q3 2025](concepts/platform-team-retro-q3-2025.md)
- [Platform team retro — Q4 2025](concepts/platform-team-retro-q4-2025.md)
- [Platform team retros](concepts/platform-team-retros.md)

### provenance (1)
- [Platform team retros](concepts/platform-team-retros.md)

### retention (2)
- [Skylight event retention default](concepts/skylight-event-retention-default.md)
- [Northwind](organizations/northwind.md)

### retros (4)
- [Platform team retro — Q1 2026](concepts/platform-team-retro-q1-2026.md)
- [Platform team retro — Q3 2025](concepts/platform-team-retro-q3-2025.md)
- [Platform team retro — Q4 2025](concepts/platform-team-retro-q4-2025.md)
- [Platform team retros](concepts/platform-team-retros.md)

### skylight (6)
- [Skylight dashboard default time range](concepts/skylight-dashboard-default-time-range.md)
- [Skylight dashboard stale after timezone change](concepts/skylight-dashboard-stale-after-timezone-change.md)
- [Skylight event retention default](concepts/skylight-event-retention-default.md)
- [Northwind](organizations/northwind.md)
- [@marcusfeld](persons/marcusfeld.md)
- [janitor](systems/janitor.md)

### social (1)
- [@marcusfeld](persons/marcusfeld.md)

### support (1)
- [Sofia Ruiz](persons/sofia-ruiz.md)

### testing (3)
- [Platform team retro — Q1 2026](concepts/platform-team-retro-q1-2026.md)
- [Platform team retro — Q3 2025](concepts/platform-team-retro-q3-2025.md)
- [Platform team retro — Q4 2025](concepts/platform-team-retro-q4-2025.md)

### timezone (2)
- [Skylight dashboard stale after timezone change](concepts/skylight-dashboard-stale-after-timezone-change.md)
- [janitor](systems/janitor.md)

### troubleshooting (2)
- [Skylight dashboard stale after timezone change](concepts/skylight-dashboard-stale-after-timezone-change.md)
- [janitor](systems/janitor.md)

## Sources

11 ingested raw source(s) — full catalog with the importing model in [sources/index.md](sources/index.md).

- [raw/announcement.md](../raw/announcement.md) — cited by 3 pages
- [raw/application-cover-letter.md](../raw/application-cover-letter.md) — cited by 3 pages
- [raw/cv.md](../raw/cv.md) — cited by 1 page
- [raw/forum-support-thread.md](../raw/forum-support-thread.md) — cited by 4 pages
- [raw/interview-transcript-founder.md](../raw/interview-transcript-founder.md) — cited by 3 pages
- [raw/retros/2025-q3.md](../raw/retros/2025-q3.md) — cited by 1 page
- [raw/retros/2025-q4.md](../raw/retros/2025-q4.md) — cited by 1 page
- [raw/retros/2026-q1.md](../raw/retros/2026-q1.md) — cited by 2 pages
- [raw/retros/README.md](../raw/retros/README.md) — cited by 4 pages
- [raw/slack-export-platform-team.txt](../raw/slack-export-platform-team.txt) — cited by 9 pages
- [raw/tweet-thread.md](../raw/tweet-thread.md) — cited by 2 pages

## Open Points

5 tracked open point(s), 5 still open — full timeline in [open-points/index.md](open-points/index.md).
