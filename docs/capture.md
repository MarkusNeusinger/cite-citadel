# Capture: from conversation to cited wiki

Citadel's wiki normally grows from files you drop into `raw/`. The **capture bridge** closes the
other lane: knowledge that surfaces *while you chat with an AI* — a decision, a fact about your
world, a "remember that …" — without ever compromising the provenance guarantees. Nothing here
writes the wiki directly; both lanes below produce ordinary **raw sources**, so every captured
statement enters the wiki through the same staged, validated ingest lifecycle, cited with real
`[^sN]` line locators.

## Lane 1 — single notes: `wiki_capture` / `citadel capture`

For one statement worth keeping, mid-conversation. The MCP tool (and its CLI twin) appends a
dated, attributed entry to a monthly capture log under the primary raw root:

```
raw/captures/2026-07.md
```

```bash
citadel capture "Prod is on version 12." --from "Kim, chat 2026-07-24" --topic "prod version"
# or pipe it:
echo "Prod is on version 12." | citadel capture - --from Kim
```

Over MCP, an AI client calls `wiki_capture(text, source, topic)` — e.g. when you tell it
"remember that we decided X". The tool reports the log's source key and the appended **line
range** (the future citation locator), then reminds you to ingest:

```
Captured to raw/captures/2026-07.md (lines 12-16).
Run `citadel ingest` (or the wiki_ingest MCP tool) to fold it into the wiki.
```

Properties, by design:

- **Append-only.** Entries only accumulate; nothing edits or deletes. An appended entry changes
  the log's sha, so the next ingest run **reconciles** the log (update, don't re-append) —
  exactly the changed-source lifecycle.
- **Attributed claims, not facts.** Each entry carries its timestamp and a `From:` attribution.
  The ingest rules treat it like chat content: the wiki records "Kim said on 2026-07-24 that
  prod is on version 12"[^sN] — "X said Y" is never flattened into "Y is true".
- **The wiki stays LLM-owned.** Capture writes only under `raw/`; the wiki is written exclusively
  by the staged agent session, behind the validation gate. Citations into the log verify offline
  (`citadel lint`, `wiki_raw`) like any text source.
- **Bounded.** A capture is one note (refused above 100k chars). Whole transcripts go through
  lane 2.

## Lane 2 — whole conversations: transcript files in `raw/`

For a conversation worth keeping in full, export/save the transcript as its **own file** under a
raw root, e.g.:

```
raw/conversations/2026-07-24-claude-search-design.md
```

Use one file per conversation and put the date + participants in the filename or the first lines
— that is what the agent will attribute claims to. Any plain-text export format works (markdown,
a copy-pasted chat log, a `[HH:MM:SS]`-stamped meeting transcript); the agent-judged genre briefs
(`genres/chat.md`, `genres/transcript.md`, `genres/meeting-minutes.md`) already govern how such
sources are read: claims attributed to their speaker, threads read to their **end state** (a
mid-thread reversal never passes as current), hedges kept hedged.

Then ingest as usual — `citadel ingest`, or let the AI call `wiki_ingest`. Recordings of
meetings/voice notes are the same pattern one format earlier: drop the audio file into `raw/`
with [`CITADEL_AUDIO_SUPPORT=1`](configuration.md).

## Which lane when?

| Situation | Lane |
|-----------|------|
| "Remember that …" / one decision or fact stated in chat | `wiki_capture` / `citadel capture` |
| A design discussion worth keeping end-to-end | save the transcript under `raw/conversations/` |
| A meeting recording | drop the audio file in `raw/` (audio support) |

## Notes

- The log lands under the **primary** raw root (`CITADEL_RAW_DIR`). If you replaced the walk
  list via `CITADEL_RAW_DIRS` without including the primary root, capture still works but warns
  you: ingest the log explicitly (`citadel ingest raw/captures/2026-07.md`) or add the root.
- Capture logs are ordinary sources in every view: `citadel status` shows them pending until
  ingested, `sources/index.md` lists them with the pages citing them.
- Captured entries are **claims by their stated speaker**. If a captured statement later turns
  out wrong, capture the correction — the reconcile pass folds the arc in as dated history,
  the same way a chat thread's reversal is handled.
