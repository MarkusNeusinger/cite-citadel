---
type: Person
title: '@marcusfeld'
description: X account that posted Larkspur's Skylight sub-second-refresh launch thread
  and disputed a critic's claim about dropped events.
tags:
- skylight
- larkspur
- social-media
resource: raw/tweet-thread.md
timestamp: '2026-08-29T00:23:58Z'
citadel_version: 0.6.0
---

@marcusfeld posted a launch thread on 2026-02-12 announcing that [Skylight](../systems/skylight.md)
dashboards now refresh in under one second, opening with "Big day."[^s1] Writing in the first person
plural, they said refresh previously took around five seconds under the old pipeline, which
recomputed the whole aggregate on every refresh — workable at small scale but painful once a
customer had millions of events streaming in.[^s2][^s3] They said the team rewrote Skylight's
aggregation layer to apply incremental updates instead, folding in only the deltas since the last
frame, and reported the resulting p95 refresh time as well under one second on the same
hardware.[^s4][^s5]

When X user @dataskeptic replied to the thread claiming Skylight "silently DROPS any event larger
than 1MB,"[^s6] @marcusfeld disputed the claim directly: large events are queued and processed within
the retention window rather than dropped, they said, pointing to Skylight's documentation as
confirming that behavior; they allowed that a source could be misconfigured to reject oversized
payloads upstream, but called that a customer-side problem rather than a platform one (see
Skylight's Known issues).[^s7][^s8]

They closed the thread saying they were proud of the team.[^s9]

## Style profile

- Opens with a short, punchy fragment before the substance: "Big day."[^s1]
- Casually downplays a nontrivial technical rewrite: "That's the whole trick, honestly."[^s4]
- Meets a critical reply with a wry, dismissive aside before rebutting it: "Predictably, someone had
  feelings 🙃"[^s10]
- Rebuts a criticism head-on and bluntly: "Ok let's clear this up because it's just not true."[^s7]
- Closes with a short exclamation and team credit rather than a sign-off: "Ship it. 🚀" ... "Proud of
  the team. More soon. 💙"[^s5][^s9]

## See also
- [Skylight](../systems/skylight.md)
- [Larkspur](../organizations/larkspur.md)

## Sources
[^s1]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 3-5 — @marcusfeld, 2026-02-12: "Big day," Skylight dashboards now refresh in under one second (ingested 2026-08-29)
[^s2]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 7 — refresh previously took ~5 seconds (ingested 2026-08-29)
[^s3]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 11 — old pipeline recomputed the whole aggregate every refresh, painful once a customer had millions of events streaming in (ingested 2026-08-29)
[^s4]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 15 — rewrote the aggregation layer for incremental updates, only deltas since the last frame, no full recompute, "the whole trick, honestly" (ingested 2026-08-29)
[^s5]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 19 — result: p95 refresh well under 1 second on the same hardware, "Ship it." (ingested 2026-08-29)
[^s6]: [raw/tweet-thread.md](../../raw/tweet-thread.md), lines 25-26 — @dataskeptic, 2026-02-12: claims Skylight silently drops events over 1MB (ingested 2026-08-29)
[^s7]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 30 — @marcusfeld rebuts the claim: events over 1MB are queued and processed within the retention window, never dropped (ingested 2026-08-29)
[^s8]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 34 — misconfiguration acknowledgment framed as customer-side; "silently drops is just wrong" (ingested 2026-08-29)
[^s9]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 38 — closing line: "Proud of the team. More soon." (ingested 2026-08-29)
[^s10]: [raw/tweet-thread.md](../../raw/tweet-thread.md), line 23 — "Predictably, someone had feelings" (ingested 2026-08-29)
