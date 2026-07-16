---
type: Organization
title: Nordvane Systems GmbH
description: Company whose production estate underwent Halden Audit Partners' Q3 2025
  external penetration test.
tags:
- nordvane
- security
- penetration-test
resource: raw/meeting-notes-security-review.md
timestamp: '2026-07-16T14:27:39Z'
citadel_version: 0.3.0
---

Nordvane Systems GmbH's production estate — the customer-facing web application, the public API,
and the identity provider — was the subject of [Halden Audit Partners](halden-audit-partners.md)'
annual external penetration test between 25 August and 5 September 2025.[^s1] Internal-only
back-office tooling was explicitly out of scope for this review and is scheduled for the Q1 2026
review instead.[^s1]

The review findings were presented at a meeting on 12 September 2025, chaired by
[Ilse Marquardt](../persons/ilse-marquardt.md) (CISO), with minutes taken by
[Devin Osei](../persons/devin-osei.md) (Security Engineer); [Priya Anand](../persons/priya-anand.md)
(Head of Platform) also attended.[^s2] The Q3 2025 external review was accepted with three
medium-severity findings; remediation of all three is required before the report is marked
closed.[^s3] Nordvane is also running a phased [multi-factor authentication (MFA)
rollout](../projects/nordvane-mfa-rollout.md), which had reached 92 percent of staff accounts as of
the review.[^s4]

## See also

- [Ilse Marquardt](../persons/ilse-marquardt.md)
- [Devin Osei](../persons/devin-osei.md)
- [Priya Anand](../persons/priya-anand.md)
- [Halden Audit Partners](halden-audit-partners.md)
- [Nordvane Q3 2025 Security Review](../projects/nordvane-q3-2025-security-review.md)
- [Nordvane MFA Rollout](../projects/nordvane-mfa-rollout.md)

## Sources

[^s1]: [meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), § 1. Scope of this review (ingested 2026-07-16)
[^s2]: [meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 3-10 — meeting header (ingested 2026-07-16)
[^s3]: [meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), § 5. Decisions (ingested 2026-07-16)
[^s4]: [meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), § 3. Multi-factor authentication rollout (ingested 2026-07-16)
