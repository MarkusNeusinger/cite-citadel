# chat — workplace-chat exports

Applies when the source reads like an exported chat log — a Slack/Teams/Discord/IRC channel or
group thread: short timestamped messages between named coworkers, mixing real decisions with
banter.

- **Attribute, with timestamps.** Every claim is a person speaking at a moment ("At 14:05 on
  2026-02-10, Kim wrote that …"[^sN]) — chat is never the wiki's own voice. A display name or
  handle maps to a real person only when the export itself establishes the mapping.
- **Read the WHOLE thread before recording any decision — chat is where plans reverse.** A value
  proposed in the morning can be adopted by noon and reverted the same afternoon, three terse
  messages apart. The wiki's live fact is the thread's **end state**; record the arc as dated
  history (an `## Open Points` thread or `## Change Log` line per `genres/meeting-minutes.md`),
  and never let a mid-thread state pass as current.
- **Terse ≠ unimportant.** A two-line exchange ("let's raise the upload cap to 250 MB" / "done")
  is a real, dated decision carrying the same weight as a documented one — extract it; don't let
  its brevity or its position between jokes bury it.
- **Noise stays out.** Greetings, emoji, reactions, memes, lunch plans, and link-only messages
  carry no facts — extract nothing from them, and never let their wording leak into factual
  prose.
- **Action items have owners and dates.** "@Lee will update the runbook by Friday" is an
  attributed, dated commitment — a natural `## Open Points` entry, resolved only when a later
  message actually says so.
- **Hedges stay hedged.** "I think prod is still on version 12?" is a guess — attribute it as
  one; never flatten it into a fact.
