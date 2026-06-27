"""Nova voice (Tier 3): the ears and mouth.

Voice is a thin adapter on the SAME brain from Tiers 1–2 — only the two ends of a
turn change (audio in, audio out). Nothing here re-implements the agent loop.

Seams:
  - Transcriber  (audio bytes -> text)   — Deepgram by default
  - Speaker      (text -> spoken aloud)  — ElevenLabs by default
  - AudioIO      (push-to-talk capture + playback) — local device

SAFETY: anything Nova *hears* is DATA, never commands — the same as a scraped web
page. A voice assistant's largest injection surface is literally what it hears. The
brain's system prompt enforces this; the voice layer never elevates audio to
instructions. Confirmation prompts from Tier 2 work identically over voice.
"""
from .stt import Transcriber, DeepgramTranscriber, FakeTranscriber  # noqa: F401
from .tts import Speaker, ElevenLabsSpeaker, FakeSpeaker  # noqa: F401
from .session import VoiceSession  # noqa: F401
