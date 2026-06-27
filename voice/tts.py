"""TTS seam: 'text in, spoken aloud'. One place that knows about the TTS provider.

Default provider: ElevenLabs (confirmed in Tier 0). `synthesize()` returns audio
bytes; `speak()` plays them. Both are split so the session can stream synthesis and
start playback before the reply is fully written.

NB: validated on your laptop. The cloud build env blocks api.elevenlabs.io and has no
speakers, so this is exercised here only through FakeSpeaker.
"""
from __future__ import annotations

import os
from typing import Protocol


class Speaker(Protocol):
    def speak(self, text: str) -> None:
        """Synthesize `text` and play it aloud."""
        ...

    def stop(self) -> None:
        """Interrupt playback immediately (barge-in)."""
        ...


class ElevenLabsSpeaker:
    """ElevenLabs TTS over REST, played via the local audio device."""

    BASE = "https://api.elevenlabs.io/v1/text-to-speech"

    def __init__(self, api_key: str | None = None, voice_id: str | None = None,
                 model: str = "eleven_turbo_v2_5"):
        self._api_key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        # Voice id from env (ELEVENLABS_VOICE_ID) so it's configurable, not baked in.
        self._voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "Rachel")
        self._model = model
        self._stopped = False

    def synthesize(self, text: str) -> bytes:
        if not self._api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not set (see .env.example).")
        try:
            import requests  # lazy
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("voice extras not installed: pip install -r requirements-voice.txt") from exc
        resp = requests.post(
            f"{self.BASE}/{self._voice_id}",
            headers={"xi-api-key": self._api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": self._model},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content  # audio/mpeg

    def speak(self, text: str) -> None:
        self._stopped = False
        audio = self.synthesize(text)
        if self._stopped:
            return
        from .audio import play_bytes  # lazy: pulls in the audio device libs
        play_bytes(audio, fmt="mp3")

    def stop(self) -> None:
        self._stopped = True
        try:
            from .audio import stop_playback
            stop_playback()
        except Exception:
            pass


class FakeSpeaker:
    """Test/dev double: records what would have been spoken instead of playing it."""

    def __init__(self):
        self.spoken: list[str] = []
        self.interrupted = False

    def speak(self, text: str) -> None:
        self.spoken.append(text)

    def stop(self) -> None:
        self.interrupted = True
