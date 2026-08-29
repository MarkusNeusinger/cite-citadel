---
type: System
title: Skylight
description: Larkspur's real-time analytics dashboard, available in three regions
  as of the 2.0 release.
tags:
- analytics
- dashboard
- saas
resource: raw/announcement.md
timestamp: '2026-08-29T00:23:58Z'
citadel_version: 0.6.0
---

Skylight is [Larkspur](../organizations/larkspur.md)'s real-time analytics dashboard.[^s1] Skylight
2.0, the latest release, reached general availability on 1 April 2026.[^s1]

In a podcast interview, [Priya Nadkarni](../persons/priya-nadkarni.md) described Skylight as a
dashboard a user points at their event stream to get live views that update as things happen,
rather than after a delay.[^s12]

As of the 2.0 release, Skylight is offered in three regions: EU (Frankfurt), US (Virginia), and
APAC (Singapore).[^s2] Deploying in the region closest to a customer's data keeps latency low and
helps teams meet regional data-residency requirements.[^s3] Existing customers can select their
region from workspace settings; new workspaces are prompted to choose a region during setup.[^s3]

[Priya Nadkarni](../persons/priya-nadkarni.md), Larkspur's founder and CEO, said Skylight 2.0 is
"the version we always wanted to ship" and that bringing it to three regions means teams around the
world get the same real-time experience close to home.[^s4]

In the same interview, Nadkarni said "we're the only ones who do it right" and that Larkspur "is
the only real-time analytics platform with true sub-second refresh," arguing rival products are
"doing polling and calling it streaming."[^s13][^s14] This is the founder's own competitive claim
about her company's product: there are multiple established real-time analytics and dashboarding
platforms on the market, so being the sole one with genuine sub-second refresh is not independently
verified anywhere in this wiki, and the claim doubles as marketing for Skylight against named and
unnamed competitors.[^llm1]

Nadkarni said Larkspur had recently cut Skylight's dashboard refresh time to under one second, and
that the response to the change had been "incredible."[^s15] She said the team's next priorities are
scaling and expanding Skylight's regional footprint to bring it closer to customers worldwide,
while keeping genuine real-time performance — "real-time that's actually real-time" — as the
product's guiding goal.[^s15]

Skylight's event-cleanup service was originally named `retention-svc`. On 2026-02-09, in Larkspur's
internal #platform Slack channel, [Tom Alvarez](../persons/tom-alvarez.md) asked why the service was
still called that when it now ran four unrelated cleanup jobs.[^s16] [Sofia Ruiz](../persons/sofia-ruiz.md)
said it was "basically a janitor at this point," and the team agreed informally to rename it
`janitor`, with Alvarez opening a low-priority rename ticket to make it official (see Open
Points).[^s17]

As of 2026-02-11, Skylight's default event-retention window is 30 days, and the default dashboard
time range for new workspaces is last 24 hours; both defaults changed more than once in February
2026 (see Change Log).[^s25][^s28]

In a launch thread posted on 2026-02-12, [@marcusfeld](../persons/marcusfeld.md) gave more detail on
how Skylight's dashboard refresh was sped up. The previous pipeline recomputed the whole aggregate on
every refresh, which was workable at small scale but painful once a customer had millions of events
streaming in, with refresh previously taking around five seconds.[^s30][^s31] The team rewrote the
aggregation layer to apply incremental updates instead — folding in only the deltas since the last
frame rather than doing a full recompute — and reported the resulting p95 refresh time as well under
one second on the same hardware.[^s32][^s33]

## Known issues

### Dashboards frozen after an org timezone change

On 2026-02-18, a Larkspur Community Forum user reported that after moving their org from
US/Eastern to Europe/Berlin, Skylight dashboards froze on old data even though new events were
still visible in the raw event log.[^s5] They ruled out a browser-side cause — a hard refresh, a
full cache clear, an incognito window, and a different machine all showed the same stale
numbers — and confirmed the ingestion status page showed ingestion running normally, with events
landing but dashboards not rolling forward past the timezone switch.[^s6][^s7]

On 2026-02-19, [Sofia Ruiz](../persons/sofia-ruiz.md) of Larkspur Support explained the cause: the
`janitor` service caches an org's UTC offset when it starts, and uses that cached offset to bucket
incoming events into time windows; when an org's timezone changes, `janitor` keeps bucketing
against the old cached offset, so new events land in the wrong windows and dashboards appear
frozen on stale data.[^s8] The fix is to set the `SKYLIGHT_TZ` environment variable to the org's
IANA timezone and restart the `janitor` service so it re-reads the timezone and recomputes the
offset; dashboards may take one refresh cycle to catch up afterward.[^s9] Applying this fix
(`SKYLIGHT_TZ=Europe/Berlin`, restarting `janitor`) resolved the reporting customer's dashboards
within a minute.[^s10]

Separately, another forum user said they had hit a similar-looking issue once after a DST change,
never root-caused it, and worked around it by rebuilding the dashboard and copying its
configuration over.[^s11]

### Disputed claim: events larger than 1MB

> [!CONTRADICTION]
> On 2026-02-12, X user @dataskeptic replied to the launch thread claiming Skylight "silently DROPS
> any event larger than 1MB."[^s34] [@marcusfeld](../persons/marcusfeld.md) responded that this is
> not true: events over 1MB are queued and processed within the retention window and are never
> dropped, pointing to Skylight's own documentation as confirming this has been the behavior for
> months.[^s35]

@marcusfeld added that a data source could be misconfigured to reject oversized payloads upstream
before they reach Skylight, but characterized that as a customer-side issue rather than a platform
one, maintaining that the platform itself queues and works off large events rather than dropping
them.[^s36] This is a self-report from the account that announced Skylight's launch, rebutting a
critic's claim about the product's own event-handling behavior; it is not independently verified
anywhere else in this wiki.[^llm2]

## Change Log

### Default event-retention window
- Before 2026-02-09, Skylight had no default event-retention window, and staging events accumulated
  indefinitely under the missing default.[^s18]
- 2026-02-09: Larkspur's platform team set the default event-retention window to 7 days, reasoning
  that most dashboards only look at the last few days and that the window could be raised per
  customer if needed; the change was merged and rolled out to production on 2026-02-10.[^s19][^s20]
- 2026-02-10: a customer, Northwind, opened a ticket reporting empty dashboards for ranges 10-12
  days back, which the team attributed to the 7-day window working as designed.[^s21]
- 2026-02-11: the team learned Northwind could not retrieve 3 weeks of event history needed for a
  compliance audit because it had aged out under the 7-day window.[^s22] Concluding the 7-day
  default had been too aggressive — optimized for disk usage rather than for customers — the team
  changed the default to 30 days, reverting the 7-day default; Sofia Ruiz owned the change and its
  changelog note, which also advises customers on audit-heavy plans to confirm their retention
  window explicitly.[^s23][^s24] The change was merged and rolled out the same day; the current
  default is 30 days.[^s25]

### Default dashboard time range for new workspaces
- New workspaces defaulted to a "last 24 hours" dashboard time range, which was generating "where's
  my data" support tickets from users who expected to see a week of data.[^s26]
- 2026-02-10: the team changed the default to "last 7 days" for new workspaces.[^s27]
- 2026-02-10, later the same day: the team reverted the default back to "last 24 hours" after
  recognizing that a 7-day dashboard default would show a half-empty chart once the (then 7-day)
  event-retention window pruned anything older; they noted they would revisit once retention was
  "sorted." The current default is last 24 hours.[^s28]

## Open Points

### Rename retention-svc to janitor
id: op-rename-retention-svc
- 2026-02-09: proposed and agreed informally in Larkspur's #platform channel, after the service was
  noted to run several unrelated cleanup jobs beyond retention; Tom Alvarez said he would add a
  rename ticket, marked low priority.[^s17]
- 2026-02-11: the ticket still existed and was still low priority; Sofia Ruiz said she would pick
  it up.[^s29]

## See also
- [Larkspur](../organizations/larkspur.md)
- [Priya Nadkarni](../persons/priya-nadkarni.md)
- [Sofia Ruiz](../persons/sofia-ruiz.md)
- [Tom Alvarez](../persons/tom-alvarez.md)
- [Wei Chen](../persons/wei-chen.md)
- [@marcusfeld](../persons/marcusfeld.md)

## Sources
[^s1]: [raw/announcement.md](../../raw/announcement.md), lines 5-7 — Skylight 2.0 general availability, 1 April 2026 (ingested 2026-08-29)
[^s2]: [raw/announcement.md](../../raw/announcement.md), lines 9-13 — three regions: EU Frankfurt, US Virginia, APAC Singapore (ingested 2026-08-29)
[^s3]: [raw/announcement.md](../../raw/announcement.md), lines 15-17 — latency/data-residency rationale and region selection (ingested 2026-08-29)
[^s4]: [raw/announcement.md](../../raw/announcement.md), lines 19-21 — Priya Nadkarni quote on the 2.0 release and three-region launch (ingested 2026-08-29)
[^s5]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 9-13 — gridlock_92, 2026-02-18: org moved from US/Eastern to Europe/Berlin, dashboards froze on old data, new events still visible in the raw event log (ingested 2026-08-29)
[^s6]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 26-27 — gridlock_92, 2026-02-18: hard refresh, full cache clear, incognito window, and a different machine all showed the same stale numbers, ruling out a browser cause (ingested 2026-08-29)
[^s7]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 40-41 — gridlock_92, 2026-02-18: ingestion status green, events landing, dashboards not rolling forward past the timezone switch (ingested 2026-08-29)
[^s8]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 59-62 — Sofia Ruiz, 2026-02-19: the janitor service caches an org's UTC offset at boot and uses it to bucket events into time windows, causing frozen dashboards after a timezone change (ingested 2026-08-29)
[^s9]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 66-72 — Sofia Ruiz, 2026-02-19: fix — set SKYLIGHT_TZ to the org's IANA timezone and restart janitor; buckets may take one refresh cycle to catch up (ingested 2026-08-29)
[^s10]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 80-82 — gridlock_92, 2026-02-19: fix confirmed working, dashboards resumed within a minute (ingested 2026-08-29)
[^s11]: [raw/forum-support-thread.md](../../raw/forum-support-thread.md), lines 47-48 — mattb, 2026-02-18: similar-looking issue once after a DST change, unconfirmed cause, workaround of rebuilding the dashboard and copying its config (ingested 2026-08-29)
[^s12]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 17 — Nadkarni: Skylight description, point your event stream at it, live views update as things happen (ingested 2026-08-29)
[^s13]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 25 — Nadkarni: "only ones who do it right," "only real-time analytics platform with true sub-second refresh" (ingested 2026-08-29)
[^s14]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 29 — Nadkarni reaffirms the claim: competitors "doing polling and calling it streaming" (ingested 2026-08-29)
[^llm1]: LLM - a self-reported "only true sub-second refresh" competitive claim by the company's own founder; multiple established real-time analytics/dashboarding platforms exist, so exclusivity is not independently verifiable from this wiki, and the claim doubles as marketing for Skylight against unnamed competitors (added 2026-08-29)
[^s15]: [raw/interview-transcript-founder.md](../../raw/interview-transcript-founder.md), line 41 — Nadkarni: recent dashboard refresh cut to under a second, response "incredible," next priorities scale and regions, "real-time that's actually real-time" (ingested 2026-08-29)
[^s16]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 19 — Tom Alvarez, 2026-02-09 09:31: asks why retention-svc is named that when it runs four unrelated cleanup jobs (ingested 2026-08-29)
[^s17]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 21-25 — Sofia Ruiz calls it "basically a janitor," the team agrees to rename retention-svc to janitor, Tom Alvarez opens a low-priority rename ticket (ingested 2026-08-29)
[^s18]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 9 — Tom Alvarez, 2026-02-09 09:11: no default event-retention window, staging hoarding events forever (ingested 2026-08-29)
[^s19]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 13-17 — Tom Alvarez proposes and the team decides on a 7-day default event-retention window (ingested 2026-08-29)
[^s20]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 33 — Wei Chen, 2026-02-10 10:04: 7-day retention default PR merged and rolled to prod (ingested 2026-08-29)
[^s21]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 35-38 — Sofia Ruiz relays Northwind's ticket about empty dashboards for ranges 10-12 days back (ingested 2026-08-29)
[^s22]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 55 — Sofia Ruiz, 2026-02-11 08:51: Northwind needed 3 weeks of event history for a compliance audit that aged out under the 7-day window (ingested 2026-08-29)
[^s23]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 57-62 — the team concludes the 7-day default was too aggressive and decides to bump the default to 30 days, reverting the 7-day default (ingested 2026-08-29)
[^s24]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 64 — Sofia Ruiz, 2026-02-11 09:20: changelog note advising customers on audit-heavy plans to confirm their retention window explicitly (ingested 2026-08-29)
[^s25]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 66 — Sofia Ruiz, 2026-02-11 09:40: 30-day retention default merged and rolled out (ingested 2026-08-29)
[^s26]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), line 41 — Wei Chen, 2026-02-10 14:02: new workspaces default the dashboard time range to 24 hours, causing "where's my data" tickets (ingested 2026-08-29)
[^s27]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 42-44 — Tom Alvarez proposes and announces a last-7-days dashboard default for new workspaces (ingested 2026-08-29)
[^s28]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 45-47 — Wei Chen catches that a 7-day dashboard default would look half-empty under the 7-day retention window; the team reverts to 24 hours (ingested 2026-08-29)
[^s29]: [raw/slack-export-platform-team.txt](../../raw/slack-export-platform-team.txt), lines 71-72 — Tom Alvarez confirms the janitor rename ticket is still open and low priority; Sofia Ruiz says she will pick it up (ingested 2026-08-29)
[^s30]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 7 — @marcusfeld, 2026-02-12: refresh previously took ~5 seconds (ingested 2026-08-29)
[^s31]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 11 — @marcusfeld: old pipeline recomputed the whole aggregate every refresh, painful once a customer had millions of events streaming in (ingested 2026-08-29)
[^s32]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 15 — @marcusfeld: rewrote the aggregation layer for incremental updates, only deltas since the last frame, no full recompute (ingested 2026-08-29)
[^s33]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 19 — @marcusfeld: result, p95 refresh well under 1 second on the same hardware (ingested 2026-08-29)
[^s34]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 25-26 — @dataskeptic, 2026-02-12: claims Skylight silently drops events over 1MB (ingested 2026-08-29)
[^s35]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 30 — @marcusfeld rebuts the claim: events over 1MB are queued and processed within the retention window, never dropped, cites docs (ingested 2026-08-29)
[^s36]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 34 — @marcusfeld: a misconfigured upstream source is a customer-side issue; the platform itself queues and works off large events, "silently drops is just wrong" (ingested 2026-08-29)
[^llm2]: LLM - a self-report from the account that announced Skylight's launch, rebutting a critic's claim about the product's own event-handling behavior; not independently verified elsewhere in this wiki (added 2026-08-29)
