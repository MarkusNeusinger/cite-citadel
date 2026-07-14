# social — social-media posts and threads

Applies when the source reads like social-media material: posts, a thread, or an export from
X/Mastodon/Bluesky/LinkedIn or a forum — short public messages with handles, timestamps, and
reshares.

- **Attribute every claim to its author, date, and platform.** "@handle posted on X on
  2026-03-02 that …"[^sN] — a post is a person speaking, never the wiki's own voice. Map a
  handle to a real name only when the source itself establishes the mapping; otherwise keep the
  handle.
- **Thread order matters.** A thread is one document read in sequence — later posts qualify,
  retract, or ironize earlier ones; never ingest an early post without reading to the end. Date
  each claim from its own post's timestamp.
- **Engagement numbers are point-in-time.** Likes, reposts, and view counts change hourly — when
  reach is itself the fact, record it as a dated snapshot ("had ~40k likes as of
  2026-03-02"[^sN]); otherwise skip them.
- **Irony and jokes are not facts.** A sarcastic or joke post asserts nothing — skip it, or if
  it is load-bearing, write what happened attributed ("X joked that …"[^sN]). When you cannot
  tell whether a post is serious, attribute it; never launder it into a world fact.
- **A quote-post carries TWO voices.** Attribute the quoted claim to its ORIGINAL author and
  date, and the commentary to the quoting author — the quote-chain rule of `genres/email.md`
  applies.
- **Promotional accounts are quarantined.** A brand's or influencer's claim about itself gets
  the mandatory quarantine treatment (`schema.md` § Grounding): attributed voice + `[^llmN]`
  conflict note, compared per the cross-source sweep.
