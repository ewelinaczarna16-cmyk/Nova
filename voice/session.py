"""The voice session: wrap the existing Agent, change only the two ends of a turn.

Flow of one spoken turn:
  1. capture audio (push-to-talk)            ── voice/audio.py
  2. the instant capture ends, signal life   ── so silence never reads as "broken"
  3. transcribe                              ── voice/stt.py  (show the transcript!)
  4. run THE SAME brain                      ── core/agent.Agent.turn()
  5. stream the reply into speech            ── voice/tts.py, sentence by sentence

The transcript is always surfaced next to the reply (transcription mishears; you
need to see what it heard). The typed interface (core/cli.py) stays alive forever as
the debug path and fallback. Confirmation prompts from Tier 2 run through the SAME
gate here — consequential actions are gated over voice exactly as over text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from core.agent import Agent

from .stt import Transcriber
from .tts import Speaker

_SENTENCE_END = re.compile(r"(.+?[.!?\n]+)", re.S)


@dataclass
class VoiceSession:
    agent: Agent
    transcriber: Transcriber
    speaker: Speaker
    on_status: Callable[[str], None] = print   # latency/transcript breadcrumbs
    speak_system_breadcrumbs: bool = False      # don't read tool-trace lines aloud
    last: dict = field(default_factory=dict)

    def handle_audio(self, audio: bytes) -> dict:
        """Run one spoken turn from captured audio. Returns transcript + reply +
        the list of phrases spoken (handy for tests and the on-screen transcript)."""
        # 2. signal the instant capture ends — never let silence read as broken.
        self.on_status("…heard you, thinking…")

        # 3. transcribe, and ALWAYS show what it heard.
        transcript = self.transcriber.transcribe(audio)
        self.on_status(f"you (heard): {transcript!r}")
        if not transcript.strip():
            self.on_status("(didn't catch that)")
            self.last = {"transcript": "", "reply": "", "spoken": []}
            return self.last

        # 4–5. same brain, stream reply into speech sentence-by-sentence.
        reply, spoken, buf = "", [], ""
        for chunk in self.agent.turn(transcript):
            if chunk.kind == "text":
                reply += chunk.text
                buf += chunk.text
                buf = self._flush_sentences(buf, spoken)
            else:  # system breadcrumb (tool ran / model down)
                self.on_status(chunk.text.strip())
                if self.speak_system_breadcrumbs and chunk.text.strip():
                    self._say(chunk.text.strip(), spoken)
        if buf.strip():
            self._say(buf.strip(), spoken)

        self.last = {"transcript": transcript, "reply": reply, "spoken": spoken}
        return self.last

    def _flush_sentences(self, buf: str, spoken: list[str]) -> str:
        """Speak any complete sentences in buf as soon as they're ready (low latency),
        keep the trailing partial for next time."""
        last_end = 0
        for m in _SENTENCE_END.finditer(buf):
            phrase = m.group(1).strip()
            if phrase:
                self._say(phrase, spoken)
            last_end = m.end()
        return buf[last_end:]

    def _say(self, text: str, spoken: list[str]) -> None:
        spoken.append(text)
        self.speaker.speak(text)

    def interrupt(self) -> None:
        """Barge-in: stop speaking and listen. Wired to a keypress in run()."""
        self.speaker.stop()

    def run(self, record: Callable[[], bytes]) -> None:
        """Live push-to-talk loop. `record` returns captured audio (voice/audio.py).
        The typed interface remains available separately as the fallback."""
        self.on_status("Nova (voice mode). Ctrl-C to quit. The typed interface still works.")
        try:
            while True:
                audio = record()
                self.handle_audio(audio)
        except (KeyboardInterrupt, EOFError):
            self.on_status("bye 👋")
