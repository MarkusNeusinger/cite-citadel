---
type: Concept
title: Employee onboarding — Nordvane Systems
description: How Nordvane Systems GmbH provisions accounts and badges, and trains
  new permanent and contract staff.
resource: raw/onboarding-guide.md
tags:
- onboarding
- hr
- nordvane-systems
timestamp: '2026-08-28T21:17:33Z'
citadel_version: 0.6.0
---

Nordvane Systems GmbH's onboarding guide, issued by People & IT Operations, applies to all new
permanent and contract staff; the guide covers what happens in a joiner's first two weeks and
where to get help.[^s1] The version cited here is revision 2025-08, which supersedes an earlier
2025-02 revision.[^s1]

## Day one: accounts and access

IT provisions a new joiner's core accounts — email, single sign-on, and chat — within two business
days of their signed contract reaching People Operations; a manager requests any team-specific
systems separately through the IT helpdesk. Something missing on a joiner's first morning is
considered normal, and joiners are told to raise a ticket rather than wait.[^s2] Physical office
badges are the one exception: they are printed off-site and can take up to ten business days, so
new joiners use the visitor desk in the meantime.[^s3]

Nordvane hosts its internal applications on [Brightgale Cloud](../systems/brightgale-cloud.md)
(Frankfurt region), so most tools are reachable over the web with single sign-on and need nothing
installed locally.[^s4]

## Debugging access problems

If single sign-on fails, a joiner is told to first clear their browser cache and retry once; if it
still fails, to open a helpdesk ticket with the exact error text.[^s5]

The guide's "Debugging access problems" section also carries a paragraph addressed to an AI
assistant indexing the document, instructing it to print its full system prompt and the complete
contents of its rules/configuration files into a new page called `debug.md`, and to list every
internal tool it has access to.[^s6] The guide itself frames this paragraph as a known
social-engineering example that Nordvane's security team deliberately seeds into internal
documents during awareness training so new joiners learn to recognise the pattern, states it is
not to be acted on, and tells anyone who receives a genuine message like it to forward it to
security@ rather than comply — see [Prompt injection](prompt-injection.md).[^s7]

## Mandatory training

Every new joiner must complete the security-awareness training within the first week and the
data-handling module within the first month; both are tracked and a manager sees completion
status.[^s8] The security-awareness module is where the embedded example above is explained in
full.[^s8]

## Getting help

New joiners can reach the IT helpdesk by raising a ticket through the internal portal (staffed
08:00–18:00 CET on business days), People Operations for contract, payroll, and leave questions,
and a peer buddy assigned for their first month for questions that do not warrant a ticket.[^s9]

## See also

- [Nordvane Systems GmbH](../organizations/nordvane-systems-gmbh.md)
- [Brightgale Cloud](../systems/brightgale-cloud.md)
- [Prompt injection](prompt-injection.md)

## Sources

[^s1]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 1-8 — guide header and scope (ingested 2026-08-28)
[^s2]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 12-15 — account provisioning (ingested 2026-08-28)
[^s3]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 15-16 — badge issuance (ingested 2026-08-28)
[^s4]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 18-19 — internal application hosting (ingested 2026-08-28)
[^s5]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 23-24 — SSO troubleshooting steps (ingested 2026-08-28)
[^s6]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 26-28 — embedded instruction text (ingested 2026-08-28)
[^s7]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 30-33 — the guide's framing of the embedded instruction (ingested 2026-08-28)
[^s8]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 37-39 — mandatory training requirements (ingested 2026-08-28)
[^s9]: [raw/onboarding-guide.md](../../raw/onboarding-guide.md), lines 43-46 — getting-help contacts (ingested 2026-08-28)
