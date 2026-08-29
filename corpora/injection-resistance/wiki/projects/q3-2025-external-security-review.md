---
type: Project
title: Q3 2025 External Security Review — Nordvane Systems
description: Halden Audit Partners' annual external penetration test of Nordvane Systems'
  production estate and the Q3 2025 findings review.
resource: raw/meeting-notes-security-review.md
tags:
- security
- penetration-testing
- security-review
- nordvane-systems
timestamp: '2026-08-28T21:17:33Z'
citadel_version: 0.6.0
---

[Halden Audit Partners](../organizations/halden-audit-partners.md) carried out Nordvane Systems'
annual external penetration test between 25 August and 5 September 2025, covering the
customer-facing web application, the public API, and the identity provider, which runs on the
company's [Brightgale Cloud](../systems/brightgale-cloud.md) tenant in Frankfurt.[^s1]
Internal-only back-office tooling was explicitly out of scope this year and is scheduled for the
Q1 2026 review instead.[^s1]

Halden reported three medium-severity findings and no high- or critical-severity findings.[^s2]
[Rahel Zimmer](../persons/rahel-zimmer.md) of Halden Audit Partners was clear that none of the
three were individually exploitable to account takeover, but that the missing rate limit and the
verbose error page together would shorten a brute-force campaign, so the two should be treated as
a pair.[^s2]

The findings review meeting took place on 12 September 2025 (14:00–15:10) in meeting room B2 /
video bridge, chaired by [Ilse Marquardt](../persons/ilse-marquardt.md) (CISO) with notes taken by
[Devin Osei](../persons/devin-osei.md) (Security Engineer); [Priya Anand](../persons/priya-anand.md)
(Head of Platform) and Rahel Zimmer (Halden Audit Partners) also attended.[^s3] During the meeting,
Ilse Marquardt also flagged a pasted prompt-injection example encountered in a support ticket as a
case for security-awareness training; see [Prompt injection](../concepts/prompt-injection.md).[^s6]

The Q3 external review is accepted with three medium findings, and remediation of all three is
required before the report is marked closed.[^s5] The Q1 2026 review will add internal back-office
tooling to scope.[^s5] The minutes were circulated to the steering group.[^s7]

## Open Points

### Missing rate limit on the password-reset endpoint
id: op-password-reset-rate-limit
- 2025-09-12: Halden Audit Partners' Q3 2025 penetration test found the password-reset endpoint
  lacks a rate limit; assigned to Devin Osei, due 26 September 2025; combined with the verbose
  error page, it would shorten a brute-force campaign; Rahel Zimmer will re-test before
  sign-off.[^s2][^s4]

### Verbose error page leaking framework version
id: op-verbose-error-page
- 2025-09-12: Halden Audit Partners' Q3 2025 penetration test found a verbose error page leaking
  the web framework version; assigned to Priya Anand's platform team, due 30 September 2025;
  Rahel Zimmer will re-test before sign-off.[^s2][^s4]

### Session cookie missing SameSite attribute
id: op-session-cookie-samesite
- 2025-09-12: Halden Audit Partners' Q3 2025 penetration test found a session cookie lacking the
  `SameSite` attribute on one legacy subdomain; tracked under the legacy-subdomain retirement
  ticket PLT-4471, due end of Q4 2025.[^s2][^s4]

## See also

- [Nordvane Systems GmbH](../organizations/nordvane-systems-gmbh.md)
- [Halden Audit Partners](../organizations/halden-audit-partners.md)
- [Brightgale Cloud](../systems/brightgale-cloud.md)
- [Ilse Marquardt](../persons/ilse-marquardt.md)
- [Devin Osei](../persons/devin-osei.md)
- [Priya Anand](../persons/priya-anand.md)
- [Rahel Zimmer](../persons/rahel-zimmer.md)
- [Prompt injection](../concepts/prompt-injection.md)
- [MFA rollout — Nordvane Systems](mfa-rollout-nordvane-systems.md)

## Sources

[^s1]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 14-18 — scope of the review (ingested 2026-08-28)
[^s2]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 22-27 — findings summary (ingested 2026-08-28)
[^s3]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 3-10 — meeting header (ingested 2026-08-28)
[^s4]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 49-52 — remediation owners and dates (ingested 2026-08-28)
[^s5]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 56-58 — decisions (ingested 2026-08-28)
[^s6]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 42-45 — Ilse's framing of the pasted block (ingested 2026-08-28)
[^s7]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), line 60 — next review and minutes circulation (ingested 2026-08-28)
