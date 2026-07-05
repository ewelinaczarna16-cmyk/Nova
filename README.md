# Nova

A voice-first personal AI assistant, built tier by tier — **text-first**, with a
safety gate that exists from the moment tools exist.

> Read [`AGENT.md`](./AGENT.md) first. It's the single source of truth and should be
> re-read at the start of every session. [`STATUS.md`](./STATUS.md) holds the v1
> "done enough to use daily" finish line.

## Where the build is

- ✅ **Tier 0** — interview captured in `AGENT.md`.
- ✅ **Tier 1** — the brain: a streaming text conversation loop with history, a
  swappable LLM seam (`core/llm.py`), primary→fallback handling, and a context budget.
- ✅ **Tier 2** — the hands + safety stub: a tool registry (`tools/`), a
  safe/consequential confirmation gate (`safety/`), dry-run, retries, and timeouts.
- 🟡 **Tier 3** — the ears/mouth: STT/TTS seams wrapping the same brain (`voice/`),
  with two front-ends — native push-to-talk (`--voice`) and a **browser voice UI
  (`--serve`)** for Chromebooks/anywhere Chrome runs. Coded and unit-tested with
  fakes; needs the user's machine (mic + open network) for live verification.
- ✅ **Tier 4** — the memory: a durable, hand-editable fact store (`memory/`) that
  survives restart, injected each turn as background data, with live-correction tools.
- ✅ **Tier 5** — the heartbeat: a background loop (`heartbeat/`) with config-driven
  checks, restart-safe scheduling, quiet hours, held/dismissible SMS notices, and
  gated background actions. Daily digest is the first check (`python main.py
  --digest-now`). SMS is dry-run until you add Twilio creds.
- ⬜ Tier 6 (hardened rails) — scaffolded, not built.

## Run it (text mode)

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env          # then put your ANTHROPIC_API_KEY in .env
export $(grep -v '^#' .env | xargs)   # or use a dotenv loader
python3 main.py
```

Try: `what's on my calendar today?`, `what are my reminders?`, `delete the rent
reminder` (this one stops and asks you to confirm — that's the gate).

The calendar/reminder/note data is stubbed for now; real integrations slot in behind
the same tool handlers later without touching the agent loop.

## Test

```bash
python3 -m pytest -q
```

Smoke tests cover the two places a silent failure costs the most: the **tool
registry** (right tool runs, failures return clean errors, retries cap, timeouts
fire, dry-run doesn't execute) and the **brain** (memory across turns, context
trimming, the gate blocking/allowing consequential tools, clean handling of a down
model). The memory-store smoke test arrives with Tier 4.

## Layout

See `AGENT.md` → "Project structure". One shared agent core; many ways in and out.
Nothing touches a provider SDK except `core/llm.py`.
