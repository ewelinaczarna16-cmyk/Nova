"""STT seam: 'audio in, text out'. One place that knows about the STT provider.

Default provider: Deepgram (confirmed in Tier 0). The real adapter calls Deepgram's
prerecorded REST endpoint; it's imported/exercised only when you actually speak, so
the rest of Nova (and the test suite) loads without `requests`, a key, or a network.

NB: this is validated on your laptop, not in the cloud build env — that env's network
policy blocks api.deepgram.com and it has no microphone.
"""
from __future__ import annotations

import os
from typing import Protocol


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, *, content_type: str = "audio/wav") -> str:
        """Turn a chunk of recorded audio into text. Empty string if nothing heard."""
        ...


class DeepgramTranscriber:
    """Deepgram prerecorded transcription over REST."""

    ENDPOINT = "https://api.deepgram.com/v1/listen"

    def __init__(self, api_key: str | None = None, model: str = "nova-2"):
        self._api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        self._model = model

    def transcribe(self, audio: bytes, *, content_type: str = "audio/wav") -> str:
        if not self._api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set (see .env.example).")
        try:
            import requests  # lazy — only needed when actually transcribing
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("voice extras not installed: pip install -r requirements-voice.txt") from exc
        resp = requests.post(
            self.ENDPOINT,
            params={"model": self._model, "smart_format": "true"},
            headers={"Authorization": f"Token {self._api_key}", "Content-Type": content_type},
            data=audio,
            timeout=30,
        )
        resp.raise_for_status()
        j = resp.json()
        try:
            return j["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
        except (KeyError, IndexError):
            return ""


class FakeTranscriber:
    """Test/dev double: returns a queued transcript, ignores the audio bytes.
    Lets the whole voice loop be exercised with no microphone and no network."""

    def __init__(self, transcripts: list[str] | str):
        self._queue = [transcripts] if isinstance(transcripts, str) else list(transcripts)

    def transcribe(self, audio: bytes, *, content_type: str = "audio/wav") -> str:
        return self._queue.pop(0) if self._queue else ""
