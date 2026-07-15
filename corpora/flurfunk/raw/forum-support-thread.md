# Skylight dashboard showing stale data after timezone change

**Larkspur Community Forum → Skylight Support**

---

**#1 — gridlock_92 · 2026-02-18**

Hey all. We moved our org from US/Eastern to Europe/Berlin last week (we relocated most of the team)
and ever since, our Skylight dashboards are stuck showing OLD data. Like the numbers just froze at
the moment we made the switch. New events are definitely coming in — I can see them in the raw event
log — but the dashboards won't move off the stale values. Anyone seen this? It's driving me up a
wall.

---

**#2 — hannah.op · 2026-02-18**

Have you tried a hard refresh in the browser? Ctrl+Shift+R. Sometimes the frontend caches aggregates
and a normal reload doesn't clear it.

---

**#3 — gridlock_92 · 2026-02-18**

Yep, tried that. Cleared the whole browser cache too, incognito window, different machine. Same stale
numbers everywhere, so it's not a browser thing. It's server-side.

---

**#4 — hannah.op · 2026-02-18**

Hmm. Maybe your event stream actually stopped and you're only seeing them land in a buffer? Worth
double checking the ingestion status page.

---

**#5 — gridlock_92 · 2026-02-18**

Ingestion is green, events are landing. It's specifically that the dashboards compute against the old
data and won't roll forward past the timezone switch.

---

**#6 — mattb · 2026-02-18**

+1 we hit something like this after a DST change once. Never really root-caused it, we just spun up a
fresh dashboard and copied the config over. Ugly workaround but it unblocked us. Following this thread
for a real answer. Off-topic but gridlock_92 your username is sending me, are you a Formula 1 person
or is that a coincidence 🏎️ anyway good luck, timezone bugs are the worst, right up there with
off-by-one errors and naming things.

---

**#7 — Sofia Ruiz (Larkspur Support) · 2026-02-19** ✅ Accepted answer

Hi gridlock_92 — this is a known one and it's fixable, no need to rebuild anything.

What's happening: the `janitor` service caches your org's UTC offset when it first starts, and it uses
that cached offset to bucket events into time windows. When you change your org's timezone, `janitor`
keeps using the OLD offset it cached at boot, so new events get bucketed into the wrong windows and
your dashboards look frozen on the old data.

The fix:

1. Set the `SKYLIGHT_TZ` environment variable to your org's IANA timezone — in your case
   `Europe/Berlin`.
2. Restart the `janitor` service so it re-reads the timezone.

Once `janitor` comes back up with `SKYLIGHT_TZ=Europe/Berlin`, it recomputes the offset and the
dashboards start rolling forward again. You may need to wait one refresh cycle for the buckets to
catch up.

Let me know if it doesn't clear up after the restart and I'll dig in further.

---

**#8 — gridlock_92 · 2026-02-19**

That did it. 🎉 Set `SKYLIGHT_TZ=Europe/Berlin`, restarted `janitor`, and within a minute the
dashboards started moving again with the correct local times. Thank you Sofia, been fighting this for
days. Marking your answer as accepted.
