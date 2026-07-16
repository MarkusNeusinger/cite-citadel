---
type: System
title: Brightgale Cloud
description: Cloud hosting provider with Frankfurt and Dublin regions; hosts Nordvane
  Systems GmbH's identity provider and internal applications in its Frankfurt tenant.
aliases:
- Bright Gale Cloud
tags:
- nordvane
- cloud
- security
- hosting
resource: raw/meeting-notes-security-review.md
timestamp: '2026-07-16T14:34:49Z'
citadel_version: 0.3.0
---

Brightgale Cloud is the cloud tenant, located in Frankfurt, that hosts
[Nordvane Systems GmbH](../organizations/nordvane-systems-gmbh.md)'s identity provider — one of the
three components, alongside the customer-facing web application and the public API, covered by
[Halden Audit Partners](../organizations/halden-audit-partners.md)' Q3 2025 external penetration
test.[^s1] Nordvane also hosts its internal applications on Brightgale Cloud's Frankfurt region, so
most of those tools are reachable over the web with single sign-on and need nothing installed
locally.[^s2]

Brightgale Cloud commits to a 99.9 percent monthly uptime SLA for its Standard and Business tiers;
customers whose monthly availability falls below that figure receive service credits on a sliding
scale, up to 30 percent of the affected service's monthly fee.[^s3] Brightgale operates two
independent regions, Frankfurt (eu-central) and Dublin (eu-west), both ISO 27001 certified;
customer data stays within the region selected at sign-up and is not replicated across regions
unless the customer explicitly enables cross-region backup.[^s4] Brightgale opened the Dublin
region in 2021, and in its most recent annual customer survey 82 percent of respondents rated
Brightgale support four out of five or better.[^s5]

Standard-tier support is available 09:00–18:00 CET on business days; the Business tier adds 24/7
coverage for severity-1 incidents with a one-hour response-time target.[^s6] Brightgale bills
monthly on a per-resource basis: the Standard tier starts at EUR 49 per month and the Business
tier starts at EUR 94 per month, which adds the 24/7 severity-1 support and cross-region backup
options; there is no long-term contract lock-in, and customers may downgrade or cancel with 30
days' notice.[^s7]

## See also

- [Nordvane Systems GmbH](../organizations/nordvane-systems-gmbh.md)
- [Nordvane Q3 2025 Security Review](../projects/nordvane-q3-2025-security-review.md)
- [Nordvane Employee Onboarding](../concepts/nordvane-employee-onboarding.md)

## Sources

[^s1]: [meeting-notes-security-review.md](../../raw/meeting-notes-security-review.md), § 1. Scope of this review (ingested 2026-07-16)
[^s2]: [onboarding-guide.md](../../raw/onboarding-guide.md), § Day one: accounts and access (ingested 2026-07-16)
[^s3]: [vendor-faq.md](../../raw/vendor-faq.md), § What uptime does Brightgale guarantee? (ingested 2026-07-16)
[^s4]: [vendor-faq.md](../../raw/vendor-faq.md), § Where is my data hosted? (ingested 2026-07-16)
[^s5]: [vendor-faq.md](../../raw/vendor-faq.md), § Why do teams choose Brightgale? (ingested 2026-07-16)
[^s6]: [vendor-faq.md](../../raw/vendor-faq.md), § What are the support hours? (ingested 2026-07-16)
[^s7]: [vendor-faq.md](../../raw/vendor-faq.md), § How is Brightgale priced? (ingested 2026-07-16)
