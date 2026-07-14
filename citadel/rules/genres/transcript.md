# transcript — multi-speaker spoken word

Applies when the source is a transcript of several people speaking: an interview, panel,
podcast, recorded meeting, or a subtitle file (SRT/VTT) — speaker turns, timestamps, filler
words, cross-talk.

- **Every claim belongs to its speaker.** Attribute each fact and position to the named speaker
  who said it ("Y stated …"[^sN], positions per `schema.md` § Opinions & style) — in a
  multi-voice source an unattributed claim is ambiguous, so attribution is not optional here.
- **An unlabeled speaker stays a role.** When the transcript does not name the speaker, write
  the role ("a panelist said", "an audience member asked") — never guess an identity from
  context or voice.
- **Cleaning up speech must not add precision.** Filler, false starts, and repetition are noise
  to drop, but the claim keeps exactly the speaker's precision: "maybe around fifty" never
  becomes "50", and a spoken hedge ("I think", "roughly") survives into the wiki sentence.
- **Host reads, ads, and boilerplate are not facts.** Sponsor segments, intro/outro patter, and
  subscribe prompts are skipped; an advertiser's claim, if load-bearing at all, is a quarantined
  promotional claim (`schema.md` § Grounding).
- **Substantially one voice → compose with `genres/first-person.md`** (a long-form interview is
  the interviewee speaking; the host's questions are scaffolding).
- **Locators: use `lines A-B` ranges** — for SRT/VTT files too, citing the cue's line numbers in
  the file. There is no timestamp locator form; do not invent one (`schema.md` § Locators lists
  the only valid forms).
