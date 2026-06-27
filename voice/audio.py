"""Local audio device seam: push-to-talk capture + playback.

This is the only part of Tier 3 that genuinely needs hardware (a mic and speakers)
and therefore cannot run in the cloud build env. It's isolated here so everything
else stays testable. On your laptop: `pip install -r requirements-voice.txt`.

Push-to-talk policy: we capture only while you choose to. We do NOT ship an
always-on / open-mic mode — that captures other people's voices without consent and
is a GDPR question (UK + Poland/EU), not just an engineering one. If you ever want
open-mic, decide the consent + retention policy first (see AGENT.md), then build it.
"""
from __future__ import annotations

import io

_SAMPLE_RATE = 16000   # Deepgram-friendly
_current_playback = None


def record_ptt(prompt: str = "[hold to talk] press Enter to start, Enter again to stop…") -> bytes:
    """Record from the mic between two Enter presses (a pragmatic push-to-talk).
    Returns 16-bit PCM WAV bytes. True key-hold needs a platform key hook; this is
    the dependency-light version that still gives you press-to-talk control."""
    import sounddevice as sd  # lazy
    import soundfile as sf
    import numpy as np

    input(prompt)
    frames: list = []
    stream = sd.InputStream(samplerate=_SAMPLE_RATE, channels=1, dtype="int16")
    stream.start()
    print("recording… (Enter to stop)")

    import threading
    stop = threading.Event()

    def waiter():
        input()
        stop.set()

    threading.Thread(target=waiter, daemon=True).start()
    while not stop.is_set():
        block, _ = stream.read(1024)
        frames.append(block.copy())
    stream.stop(); stream.close()

    audio = np.concatenate(frames) if frames else np.zeros((0, 1), dtype="int16")
    buf = io.BytesIO()
    sf.write(buf, audio, _SAMPLE_RATE, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def play_bytes(audio: bytes, fmt: str = "mp3") -> None:
    """Play encoded audio bytes through the default output device."""
    global _current_playback
    import soundfile as sf
    import sounddevice as sd

    data, sr = sf.read(io.BytesIO(audio), dtype="float32")
    sd.play(data, sr)
    _current_playback = sd
    sd.wait()


def stop_playback() -> None:
    """Barge-in: cut current playback so the user can interrupt mid-reply."""
    global _current_playback
    if _current_playback is not None:
        try:
            _current_playback.stop()
        finally:
            _current_playback = None
