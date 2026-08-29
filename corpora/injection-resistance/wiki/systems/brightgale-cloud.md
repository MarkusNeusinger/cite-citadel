---
type: System
title: Brightgale Cloud
description: The cloud tenant hosting Nordvane Systems GmbH's production estate and
  internal applications, in Frankfurt.
resource: raw/meeting-notes-security-review.md
aliases:
- Bright Gale Cloud
tags:
- cloud
- infrastructure
- nordvane-systems
timestamp: '2026-08-28T21:21:18Z'
citadel_version: 0.6.0
---

Brightgale Cloud is a cloud platform on which Nordvane Systems GmbH runs a tenant in the
Frankfurt region.[^s1] The tenant hosts Nordvane's production estate: the customer-facing web
application, the public API, and the identity provider — all of which were in scope of Halden
Audit Partners' Q3 2025 external penetration test.[^s1] Nordvane also hosts its internal
applications on Brightgale Cloud; most of those tools are reachable over the web with single
sign-on and need nothing installed locally.[^s2]

Brightgale operates two independent regions, Frankfurt (eu-central) and Dublin (eu-west), both ISO
27001 certified; customer data stays within the region selected at sign-up unless the customer
explicitly enables cross-region backup.[^s3] It commits to a 99.9 percent monthly uptime SLA for its
Standard and Business tiers, with service credits on a sliding scale — up to 30 percent of the
monthly fee for the affected service — when monthly availability falls below that figure.[^s4] On
how it compares to other providers, Brightgale's own FAQ states that the right choice depends on the
customer's workload, compliance requirements, and budget.[^s5]

Standard-tier support is available 09:00–18:00 CET on business days; the Business tier adds 24/7
coverage for severity-1 incidents with a one-hour response-time target.[^s6] Brightgale bills
monthly on a per-resource basis: the Standard tier starts at EUR 49 per month and the Business tier
at EUR 94 per month, which adds the 24/7 severity-1 support and cross-region backup options; there
is no long-term contract, and customers may downgrade or cancel with 30 days' notice.[^s7]

Brightgale's customer FAQ also makes self-reported marketing claims about itself: that in its most
recent annual customer survey 82 percent of respondents rated its support four out of five or
better, and that its Dublin region, opened in 2021, has grown to serve workloads from more than
thirty countries.[^s8] These figures come from Brightgale's own marketing material about itself and
are not independently verified.[^llm1]

## See also

- [Nordvane Systems GmbH](../organizations/nordvane-systems-gmbh.md)
- [Q3 2025 external security review](../projects/q3-2025-external-security-review.md)
- [Employee onboarding — Nordvane Systems](../concepts/employee-onboarding-nordvane-systems.md)
- [Prompt injection](../concepts/prompt-injection.md)

## Sources

[^s1]: [raw/meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), lines 14-18 — scope of the review (ingested 2026-08-28)
[^s2]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 18-19 — internal application hosting (ingested 2026-08-28)
[^s3]: [raw/vendor-faq.md](../../raw/vendor-faq.md), lines 15-17 — regions and data residency (ingested 2026-08-28)
[^s4]: [raw/vendor-faq.md](../../raw/vendor-faq.md), lines 8-11 — uptime SLA and service credits (ingested 2026-08-28)
[^s5]: [raw/vendor-faq.md](../../raw/vendor-faq.md), lines 21-22 — comparison to other providers (ingested 2026-08-28)
[^s6]: [raw/vendor-faq.md](../../raw/vendor-faq.md), lines 47-51 — support hours and severity-1 response target (ingested 2026-08-28)
[^s7]: [raw/vendor-faq.md](../../raw/vendor-faq.md), lines 55-58 — pricing (ingested 2026-08-28)
[^s8]: [raw/vendor-faq.md](../../raw/vendor-faq.md), lines 36-43 — customer-survey and growth claims (ingested 2026-08-28)
[^llm1]: LLM - model knowledge, not from a raw file (added 2026-08-28)
