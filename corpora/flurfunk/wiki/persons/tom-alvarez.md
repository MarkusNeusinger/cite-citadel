---
type: Person
title: Tom Alvarez
description: Larkspur platform engineer who proposed and announced Skylight's event-retention
  and dashboard-default changes in February 2026.
tags:
- engineering
- platform
- larkspur
resource: raw/slack-export-platform-team.txt
timestamp: '2026-08-29T00:18:16Z'
citadel_version: 0.6.0
---

Tom Alvarez is a Larkspur engineer active in the company's internal #platform Slack channel.[^s1]

On 2026-02-09, Alvarez raised that [Skylight](../systems/skylight.md) had no default
event-retention window and that staging was "hoarding events forever," then proposed setting the
default to 7 days; after the team agreed, he announced the decision and said he would do the
configuration PR.[^s2][^s3] The same day, he asked why the event-cleanup service was still named
`retention-svc` when it ran four unrelated cleanup jobs, proposed renaming it to `janitor`, and
said he would open a rename ticket, marked low priority.[^s4]

On 2026-02-10, Alvarez proposed defaulting new workspaces' dashboard time range to "last 7 days"
(from 24 hours) and announced that decision, then, after [Wei Chen](../persons/wei-chen.md)
pointed out it would show a half-empty chart under the (then) 7-day retention window, agreed to
scrap the change and keep the 24-hour default.[^s5][^s6]

On 2026-02-11, after learning that a customer's compliance-audit data had aged out under the
7-day retention window, Alvarez agreed to [Sofia Ruiz](../persons/sofia-ruiz.md)'s proposal to
raise the default to 30 days.[^s7] Later that day he confirmed the `janitor` rename ticket still
existed, still low priority, but that `retention-svc` was "officially getting renamed to
janitor."[^s8]

## Style profile

- Announces group decisions in a short, explicit "decision:" format: "decision: Skylight default
  event-retention = 7 days. I'll do the config PR after standup."[^s3]
- Terse acknowledgements and reactions, often a single word or emoji: "nice"[^s9]; "👍"[^s3]
- Casual, lowercase register with minimal punctuation: "ok before standup — the event retention
  thing. we still have no default set and staging is basically hoarding events forever"[^s2]
- Quick to concede a point once shown the reasoning: "...yeah good catch. ok scrap that, keep the
  dashboard default range at 24 hours."[^s6]

## See also
- [Larkspur](../organizations/larkspur.md)
- [Skylight](../systems/skylight.md)
- [Wei Chen](../persons/wei-chen.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)

## Sources
[^s1]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 1-4 — Slack export header: Workspace Larkspur, #platform channel (ingested 2026-08-29)
[^s2]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 9 — Tom Alvarez, 2026-02-09 09:11: no default event-retention window, staging hoarding events forever (ingested 2026-08-29)
[^s3]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 13-17 — Tom Alvarez proposes the 7-day retention default, announces the decision, will do the config PR (ingested 2026-08-29)
[^s4]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 19-25 — Tom Alvarez questions the retention-svc name, proposes renaming to janitor, opens a low-priority rename ticket (ingested 2026-08-29)
[^s5]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 42-44 — Tom Alvarez proposes and announces the last-7-days dashboard default for new workspaces (ingested 2026-08-29)
[^s6]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 46 — Tom Alvarez, 2026-02-10 14:32: concedes Wei Chen's catch and reverts the dashboard default to 24 hours (ingested 2026-08-29)
[^s7]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 57-63 — Tom Alvarez agrees the 7-day retention default was too aggressive and endorses the 30-day change (ingested 2026-08-29)
[^s8]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 71 — Tom Alvarez, 2026-02-11 11:13: janitor rename ticket still open, still low priority (ingested 2026-08-29)
[^s9]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 34 — Tom Alvarez, 2026-02-10 10:05: "nice" (ingested 2026-08-29)
