# email — correspondence and threads

Applies when the source reads like email or message correspondence: a single mail, a reply
thread, or a forwarded chain — anything with senders, recipients, dates, and quoted earlier
messages. (An exported group/workplace CHAT log — many short timestamped turns, no quoting
structure — is `genres/chat.md`'s job, with its own per-speaker, end-state attribution model.)

- **Attribute facts and positions to the ORIGINAL author, never the quoter.** In a thread, later
  mails quote earlier ones; a claim inside quoted text belongs to the person who originally wrote
  it — and carries THAT message's date — not to the sender who quoted or forwarded it.
- **Deduplicate across the quote chain.** The same sentence reappears in every later reply —
  ingest it once, at its original author and date.
- **Who said what, when, to whom can itself be the fact.** Decisions, commitments ("I'll ship it
  Friday"), and disagreements are attributed, dated, cited statements; positions follow
  `schema.md` § Opinions & style.
- **A status mail is tracking material.** A mail reporting progress on open items is ALSO a
  time-anchored tracking artifact — apply `genres/meeting-minutes.md` on top (genres compose).
- **Ignore boilerplate**: signatures, legal disclaimers, and greetings are not facts.
