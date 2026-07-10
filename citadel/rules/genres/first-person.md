# first-person — one person speaking (interviews, memos, letters, diaries)

Applies when the source is first-person material in one identifiable person's voice: an interview
transcript, a voice-memo transcript, letters, personal emails, a diary or journal.

## Always — whether or not style profiling is on

- **Facts fold out as usual.** World facts the person states are normal cited facts on the right
  topic pages — the grounding contract (`schema.md`) is unchanged.
- **Positions are attributed, never world facts.** Where the person's stance IS the fact ("X
  decided to drop the vendor", "X argued the schema was wrong"), write it attributed and cited
  per `schema.md` § Opinions & style — on the relevant topic pages and, when the person carries a
  `persons/` page, linked from there. An opinion presented as an unattributed world fact is a
  hard error.
- **Quarantine, sweep, and locators still apply.** A claim in the person's voice that conflicts
  with well-established knowledge, or promotes the person or their organization, must be written
  as an attributed claim + `[^llmN]`-flagged (mandatory — `schema.md` § Grounding) and compared
  against the same attribute elsewhere on the wiki (`schema.md` § Contradictions, cross-source
  sweep). Self-verify locators: a diary's date line is NOT a heading (`schema.md` § Locators).

## Style profile — ONLY when your run instruction says style profiling is ON

> Skip this whole section unless the run instruction explicitly enables style profiling. When it
> is off (the default), do NOT create style sections or style observations — in a many-person
> corpus every second document has a different, irrelevant style. Capture the facts and the
> load-bearing attributed positions above, nothing more.

With style profiling enabled, additionally build the person's profile on their `persons/` page:

- **Opinions and preferences** — extracted as attributed, **dated**, cited statements
  ("2026-03-02: X prefers boring technology for infrastructure. [^s2]"), routed onto the
  person's `persons/` page (and cross-linked from the topic pages they concern).
- **Writing-style observations** — voice, register, formality, idiom, recurring phrases, sentence
  rhythm, languages used — collected in a `## Style profile` section on that person's `persons/`
  page. Back **every** observation with a short **verbatim, cited example** from the source
  (verbatim quotes stay in their original language — `schema.md` § Wiki language).
- The goal: an LLM reading the person's pages can answer and write **in that person's voice, with
  their background knowledge** — so prefer the observations and examples that would actually let
  it do that.
