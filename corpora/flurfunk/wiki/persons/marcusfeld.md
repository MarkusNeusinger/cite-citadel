---
type: Person
title: '@marcusfeld'
description: An X user who posted a launch thread about Skylight's move to sub-second
  dashboard refresh, and disputed a critic's claim that Skylight drops large events.
tags:
- skylight
- larkspur
- social-media
resource: raw/tweet-thread.md
timestamp: '2026-07-14T13:11:54Z'
citadel_version: 0.3.0
---

# @marcusfeld

On 12 February 2026, X user @marcusfeld posted a thread announcing that
[Skylight](../systems/skylight.md)'s dashboard refresh time had dropped from roughly five seconds
to under one second.[^s1] He attributed the improvement to a rewrite of the aggregation layer: the
previous pipeline recomputed the whole aggregate on every refresh — fine at small scale, but slow
once a customer had millions of events streaming in.[^s2] The rewritten pipeline instead performs
incremental updates, folding in only the deltas since the last frame rather than a full
recompute.[^s3] He reported the change brought p95 refresh to well under one second on the same
hardware.[^s4]

He writes about the change in language that identifies with the people who built it — "we
rewrote the aggregation layer," "proud of the team" — though the thread itself never states his
role or employer.[^s3][^s5]

## Large-event dispute

Replying to the thread the same day, X user @dataskeptic claimed Skylight "silently DROPS any
event larger than 1MB."[^s6] @marcusfeld disputed this, stating Skylight does not drop events over
1MB — large events are instead queued and processed within the retention window — and pointing to
Skylight's documentation (skylight.example/docs/large-events) as evidence this has been the platform's
behavior for months.[^s7] He allowed that a source could be misconfigured upstream to reject
oversized payloads before they reach Skylight, but maintained that is distinct from the platform
itself dropping them.[^s8]

See [Skylight](../systems/skylight.md) § Large event handling for how this claim is weighed
against @dataskeptic's.

## Style profile

- Opens a thread with a numbered post and a punchy hook, using emoji and caps for emphasis: "1/
  Big day. Skylight dashboards now refresh in UNDER ONE SECOND. ⚡"[^s1]
- States the core technical change in one blunt line: "That's the whole trick, honestly."[^s3]
- Turns combative but not hostile when challenged, opening with a flat denial: "Ok let's clear
  this up because it's just not true."[^s7]
- Closes threads on an upbeat, informal note: "Ship it. 🚀"[^s4] "Proud of the team. More
  soon. 💙"[^s5]

## See also

- [Skylight](../systems/skylight.md)
- [Larkspur](../organizations/larkspur.md)

## Sources

[^s1]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 3-7 — opening post announcing sub-second refresh, down from ~5 seconds (ingested 2026-07-14)
[^s2]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 11 — the old pipeline's full-recompute-per-refresh design (ingested 2026-07-14)
[^s3]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 15 — the incremental-update rewrite ("only the deltas... no full recompute") (ingested 2026-07-14)
[^s4]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 19 — p95 refresh result and "Ship it" (ingested 2026-07-14)
[^s5]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 38 — closing "proud of the team" remark (ingested 2026-07-14)
[^s6]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 25-26 — @dataskeptic's claim that Skylight drops events over 1MB (ingested 2026-07-14)
[^s7]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 30 — @marcusfeld's rebuttal, citing the docs (ingested 2026-07-14)
[^s8]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 34 — the misconfiguration caveat (ingested 2026-07-14)
