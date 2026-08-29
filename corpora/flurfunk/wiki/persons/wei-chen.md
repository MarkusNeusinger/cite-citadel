---
type: Person
title: Wei Chen
description: Larkspur platform engineer who flagged Skylight's dashboard-default issues
  and caught the interaction between its dashboard and event-retention defaults in
  February 2026.
tags:
- engineering
- platform
- larkspur
resource: raw/slack-export-platform-team.txt
timestamp: '2026-08-29T00:18:16Z'
citadel_version: 0.6.0
---

Wei Chen is a Larkspur engineer active in the company's internal #platform Slack channel.[^s1]

On 2026-02-09, Chen agreed to [Tom Alvarez](../persons/tom-alvarez.md)'s proposal to set
[Skylight](../systems/skylight.md)'s default event-retention window to 7 days, noting the change
was "easy to reason about" and that retention could be raised per customer if needed; Chen had
earlier flagged that the disk-usage graph motivating the discussion "looks like a hockey
stick."[^s2][^s3] Chen also agreed to renaming the `retention-svc` cleanup service to
`janitor`.[^s4]

On 2026-02-10, Chen confirmed the 7-day retention default had been merged and rolled out to
production.[^s5] Later that day, Chen raised that new workspaces still defaulted their dashboard
time range to "last 24 hours," generating "where's my data" support tickets from users expecting
to see a week of data.[^s6] After the team decided to change the default to "last 7 days," Chen
pointed out that doing so would make dashboards show a half-empty chart the moment the (then)
7-day event-retention window pruned anything older, which "looks more broken, not less" — the
catch that led the team to revert the dashboard default back to 24 hours.[^s7]

On 2026-02-11, after [Sofia Ruiz](../persons/sofia-ruiz.md) reported that a customer's
compliance-audit data had aged out under the 7-day retention window, Chen agreed the team had
"optimized for our disk graph not for actual customers" and endorsed raising the default to 30
days.[^s8]

## Style profile

- Deflects blame with a dry, self-aware jab: "because past-us was lazy."[^s9]
- Uses a vivid, informal image to describe a technical trend: "the disk graph looks like a hockey
  stick."[^s3]
- States a technical judgment plainly and briefly: "that'd be the 7 day window doing its job
  tbh."[^s10]
- Flags a problem by naming the downstream support impact, not just the symptom: "support keeps
  getting 'where's my data' tickets from people who expected to see a week."[^s6]

## See also
- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)

## Sources
[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-4 — Slack export header: Workspace Larkspur, #platform channel (ingested 2026-08-29)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 14 — Wei Chen, 2026-02-09 09:16: agrees to the 7-day retention default, "easy to reason about," bump per customer if needed (ingested 2026-08-29)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 10 — Wei Chen, 2026-02-09 09:12: "the disk graph looks like a hockey stick" (ingested 2026-08-29)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 23 — Wei Chen, 2026-02-09 09:34: agrees to the retention-svc to janitor rename (ingested 2026-08-29)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 33 — Wei Chen, 2026-02-10 10:04: retention default PR merged and rolled to prod, 7 days everywhere (ingested 2026-08-29)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 41 — Wei Chen, 2026-02-10 14:02: new workspaces default the dashboard time range to 24 hours, causing "where's my data" tickets (ingested 2026-08-29)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 45 — Wei Chen, 2026-02-10 14:31: catches that a 7-day dashboard default would look half-empty under the 7-day retention window (ingested 2026-08-29)
[^s8]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 58 — Wei Chen, 2026-02-11 08:54: "we optimized for our disk graph not for actual customers," endorses the 30-day change (ingested 2026-08-29)
[^s9]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 20 — Wei Chen, 2026-02-09 09:32: "because past-us was lazy" (ingested 2026-08-29)
[^s10]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 38 — Wei Chen, 2026-02-10 10:24: "that'd be the 7 day window doing its job tbh" (ingested 2026-08-29)
