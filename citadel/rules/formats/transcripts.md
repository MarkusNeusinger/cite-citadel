# transcripts — audio/video sources, machine-transcribed

Applies when the run instruction says the source is an **audio or video recording**
(`.mp3`/`.wav`/`.m4a`/`.mp4`/…) — which you cannot listen to.

- The system **transcribed it** with a local whisper-class tool and wrote the transcript to a
  temporary text file; the run instruction names it. **Read that** for the content. Each line is
  one utterance: `[HH:MM:SS] spoken text`, the timestamp counting from the recording's start.
- Cite the **original audio/video file** as the source of record: `resource:` and every `[^sN]`
  definition name the original recording, never the transcript temp file.
- Every citation into a transcribed source **requires a locator**: `, lines A-B` — the
  transcript's own line numbers. The system serves the SAME cached transcript for offline
  verification, so line locators into the recording stay checkable; `p. N` and `§ …` can never
  resolve (a transcript has neither pages nor headings), and there is no timestamp locator form —
  do not invent one (`schema.md` § Locators lists the only valid forms). When the moment matters,
  name it in prose instead: "At 00:14:32, X said …"[^sN].
- **Machine transcription is imperfect — write accordingly.** There are no speaker labels (the
  transcriber does not diarize): an unlabeled voice stays a role ("the interviewer", "a
  participant") per `genres/transcript.md`, never a guessed identity. Proper nouns and figures
  may be mis-heard: prefer spellings and numbers corroborated by other sources, keep the
  speaker's hedges hedged, and when a garbled passage is load-bearing, record the uncertainty
  rather than a guess.
- Judge the genre from the content as usual: a multi-voice recording composes with
  `genres/transcript.md`, a single-voice memo or dictation with `genres/first-person.md`.
- If the transcript holds no usable content, make no edits and stop.
