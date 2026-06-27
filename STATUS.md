# STATUS.md — Nova's v1 finish line

> Pinned **before** the build got deep, so "done enough to actually use daily" is a
> fixed bar — not something to re-decide from scratch after a week away. A working
> text loop in Tier 1 gives a hundred legitimate-sounding reasons to keep refining
> instead of shipping; this file is the antidote.

## v1 = "done enough to use daily" when ALL of these are true

- [ ] **Push-to-talk works** — hold a key, speak, hear a spoken reply that used the
      same brain + tools as text. Typed interface still works as the debug path.
- [ ] **It can check my calendar** and read back what's on today.
- [ ] **It can read my reminders** back to me, and add one.
- [ ] **It remembers at least three facts about me** across a restart.
- [ ] **The safety gate holds** — nothing that sends/spends/deletes/changes-settings
      runs without an explicit yes, over text *and* voice.
- [ ] **The daily digest lands as a text message** (heartbeat proves the channel).
- [ ] **A kill switch** stops all proactive behavior while I can still talk to it.

Anything beyond this list (more tools, sub-agents / managing other agents, a visual
panel, an always-on host) is **post-v1**. Ship first.

## Per-tier log

- Tier 0 done, 2026-06-27 — interview complete, `AGENT.md` written.
- Tier 1 done, 2026-06-27 — streaming text loop with LLM seam, fallback, context budget.
- Tier 2 done, 2026-06-27 — tool registry + safe/consequential gate + dry-run + retries/timeouts.
- Tier 3 built, 2026-06-27 — voice seams (Deepgram STT / ElevenLabs TTS) + push-to-talk loop wrapping the same brain + spoken confirmation gate. Tested with fakes; awaiting live laptop run (needs mic/speakers + ElevenLabs key + open network).
