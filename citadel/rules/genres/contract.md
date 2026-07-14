# contract — contracts, legal, and financial documents

Applies when the source is an operative legal or financial document: a contract, agreement,
policy, terms of service, invoice, purchase order, or financial statement — text whose exact
wording has binding effect.

- **Exactness IS the genre.** Amounts, dates, durations, percentages, party names, and
  jurisdictions are copied exactly — never rounded, normalized, or approximated. Where the
  exact original phrasing matters, quote it verbatim in its original language with a
  translation beside it (`schema.md` § Wiki language).
- **A defined term is a proper noun.** "the Supplier", "the Effective Date", "Confidential
  Information" mean exactly what the definitions section says — keep the capitalized term
  verbatim and state which named party/date it resolves to, cited to the defining clause.
- **Obligation strength is meaning.** "shall" (a duty), "may" (an option), "will", "must" are
  never paraphrased into each other — "may terminate" written as "will terminate" invents an
  obligation the document does not contain.
- **Effective, termination, and renewal dates are dated facts.** Record when the document takes
  effect, expires, renews, or can be terminated as explicit dated, cited facts — deadlines are
  what a reader most needs to retrieve.
- **An amendment supersedes with a trace.** A later amendment or version changing a term is a
  supersession, not a contradiction: keep the current value live and the prior value as a dated
  `## Change Log` line, never dropped (see `genres/meeting-minutes.md`; a changed source file
  re-runs under `tasks/reconcile.md`).
- **No legal-advice voice.** The wiki records what the document says ("the contract provides
  …"[^sN]) — never what anyone should do about it, and never an interpretation of
  enforceability or risk.
