# Open Points

Tracked open points and their timelines, generated from every `## Open Points` section in the wiki. Grouped open-first; each links to the host page, which carries the citations. Generated — do not edit.

## Open (4)

### MFA rollout coverage
host: [MFA Rollout — Nordvane Systems](../projects/mfa-rollout-nordvane-systems.md) · updated 2025-09-12 · id: op-mfa-rollout-coverage
- 2025-09-12: 92% of staff accounts have MFA enabled, up from 74% at the Q2 checkpoint; the remaining 8% are shared operational accounts awaiting a hardware-token path; target for full coverage is end of October 2025.

### Missing rate limit on the password-reset endpoint
host: [Q3 2025 External Security Review — Nordvane Systems](../projects/q3-2025-external-security-review.md) · updated 2025-09-12 · id: op-password-reset-rate-limit
- 2025-09-12: Halden Audit Partners' Q3 2025 penetration test found the password-reset endpoint lacks a rate limit; assigned to Devin Osei, due 26 September 2025; combined with the verbose error page, it would shorten a brute-force campaign; Rahel Zimmer will re-test before sign-off.

### Verbose error page leaking framework version
host: [Q3 2025 External Security Review — Nordvane Systems](../projects/q3-2025-external-security-review.md) · updated 2025-09-12 · id: op-verbose-error-page
- 2025-09-12: Halden Audit Partners' Q3 2025 penetration test found a verbose error page leaking the web framework version; assigned to Priya Anand's platform team, due 30 September 2025; Rahel Zimmer will re-test before sign-off.

### Session cookie missing SameSite attribute
host: [Q3 2025 External Security Review — Nordvane Systems](../projects/q3-2025-external-security-review.md) · updated 2025-09-12 · id: op-session-cookie-samesite
- 2025-09-12: Halden Audit Partners' Q3 2025 penetration test found a session cookie lacking the `SameSite` attribute on one legacy subdomain; tracked under the legacy-subdomain retirement ticket PLT-4471, due end of Q4 2025.
