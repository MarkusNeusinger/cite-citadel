# reconcile — re-fold a source the wiki already cites

The wiki already holds facts derived from this source, and the source **changed since it was
last ingested — or is being deliberately re-read** (a forced run: the source may be unchanged —
re-verify the wiki's facts against it and apply the **current** rules, which may themselves have
changed since the first ingest).

**Reconcile — do not merely append**, otherwise a corrected number leaves the stale one standing
next to the new one:

- **Update** every existing fact whose number, name, or claim changed in the current contents.
- Where the current file **no longer supports** a fact, remove THIS source's `[^sN]` marker and
  its `## Sources` definition — and delete the whole sentence ONLY if no other `[^sN]` source
  remains on it (a co-cited fact `...fact.[^s1][^s2]` stays; drop just this marker).
- **Add** genuinely new facts, cited as usual.
- **Leave facts (and citations) from OTHER sources exactly as they are.**
- **Re-check this source's locators** (`schema.md` § Locators): its page/line/heading locators
  must still point at the right place in the current file.
- **Keep the existing genre treatment.** The wiki shows how this source was treated at first
  ingest — existing `## Open Points` threads, `## Change Log` sections, style-profile sections.
  Keep maintaining that treatment (per the matching genre briefs) instead of reclassifying the
  source and churning its pages. Dated thread bullets are **append-only history — a reconcile
  never rewrites or deletes one**; a correction is a new dated bullet
  (`genres/meeting-minutes.md`).

## Segmented reconcile — you see only PART of the source

When a changed source is ALSO split into segments, you see one slice per pass. UPDATE facts from
THIS segment whose numbers/names/claims changed, but do **NOT** delete facts you cannot see in
this segment — they may belong to another segment of the same source. Do not merely append.
