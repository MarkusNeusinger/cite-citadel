# Launch thread

**@marcusfeld** · Feb 12, 2026

1/ Big day. Skylight dashboards now refresh in UNDER ONE SECOND. ⚡

If you've used us before you know refresh used to take ~5 seconds. That number always bugged me. Today it's sub-second. Here's how we got there 🧵

---

2/ The old pipeline recomputed the whole aggregate on every refresh. Fine at small scale, painful once a customer had millions of events streaming in. ~5s felt like an eternity when you're staring at a live ops dashboard.

---

3/ We rewrote the aggregation layer to do incremental updates — only the deltas since the last frame get folded in. No full recompute. That's the whole trick, honestly.

---

4/ Result: p95 refresh is now well under 1 second on the same hardware. Real-time actually feels real-time. Ship it. 🚀

---

5/ Predictably, someone had feelings 🙃

> **@dataskeptic** · Feb 12, 2026
> cute launch but Skylight silently DROPS any event larger than 1MB. buyer beware.

---

6/ Ok let's clear this up because it's just not true. Skylight does NOT drop events over 1MB. Large events are QUEUED and processed within the retention window — never dropped. It's in the docs, been that way for months: skylight.example/docs/large-events 📄

---

7/ Could you *misconfigure* a source to reject oversized payloads upstream? Sure, that's on your side. But the platform itself queues them and works them off. "Silently drops" is just wrong.

---

8/ Anyway — go poke the new sub-second refresh and tell me it doesn't feel great. Proud of the team. More soon. 💙

#Skylight #Larkspur
