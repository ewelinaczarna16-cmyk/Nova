"""Browser voice front-end (Chromebook-friendly Tier 3 entry point).

The browser is the ears and mouth; the SAME core.Agent is the brain. Chrome captures
the mic (a clean, reliable permission prompt — no PortAudio), POSTs the audio here,
and this local server runs: Deepgram STT -> the same Agent (tools + memory + gate) ->
ElevenLabs TTS, then returns the transcript, the reply text, and the spoken audio.

Run it inside Linux/Crostini on the Chromebook:
    python main.py --serve
then open http://localhost:8760 in Chrome and allow the microphone.

Keys stay server-side (never shipped to the browser). The turn logic lives in
`run_turn()` as a plain function so it's unit-testable without HTTP, audio, or network.
"""
from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from core.agent import Agent

from .stt import Transcriber, DeepgramTranscriber
from .tts import Speaker, ElevenLabsSpeaker

_PAGE = Path(__file__).resolve().parent / "web" / "index.html"


def run_turn(agent: Agent, transcriber: Transcriber, synth, audio: bytes,
             content_type: str = "audio/webm") -> dict:
    """One browser turn: audio -> transcript -> same brain -> reply text + audio.

    `synth` is a callable(text)->bytes (ElevenLabsSpeaker.synthesize, or a fake).
    Returns a JSON-able dict; never raises into the HTTP layer.
    """
    try:
        transcript = transcriber.transcribe(audio, content_type=content_type)
    except Exception as exc:  # STT down / bad audio — report, don't crash the server
        return {"transcript": "", "reply": f"(couldn't transcribe: {exc})", "audio_b64": "", "ok": False}

    if not transcript.strip():
        return {"transcript": "", "reply": "(didn't catch that — try again)", "audio_b64": "", "ok": True}

    reply = ""
    for chunk in agent.turn(transcript):
        if chunk.kind == "text":
            reply += chunk.text
    reply = reply.strip() or "(no reply)"

    audio_b64 = ""
    try:
        spoken = synth(reply)
        audio_b64 = base64.b64encode(spoken).decode("ascii")
    except Exception as exc:                       # TTS down — still return the text
        reply += f"  [voice unavailable: {exc}]"
    return {"transcript": transcript, "reply": reply, "audio_b64": audio_b64, "ok": True}


def _make_handler(agent, transcriber, synth):
    lock = threading.Lock()   # single user, but serialize turns so history is coherent

    class NovaHandler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # quieter console
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = _PAGE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/turn":
                self.send_error(404); return
            length = int(self.headers.get("Content-Length", 0))
            audio = self.rfile.read(length)
            ctype = self.headers.get("X-Audio-Type", "audio/webm")
            with lock:
                result = run_turn(agent, transcriber, synth, audio, content_type=ctype)
            body = json.dumps(result).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return NovaHandler


def build_and_serve(host: str = "127.0.0.1", port: int = 8760) -> None:
    # Same registry + memory + gate as the other entry points. No approver wired here
    # yet, so consequential actions safely refuse ("needs confirmation") rather than
    # run — a browser confirmation UI is the follow-up. The gate still holds.
    from memory import MemoryStore
    from tools import ToolRegistry
    from tools.builtin import register_builtin_tools
    from tools.memory_tools import register_memory_tools

    registry = ToolRegistry()
    register_builtin_tools(registry)
    store = MemoryStore()
    register_memory_tools(registry, store)
    agent = Agent(tools=registry, memory=store)

    transcriber = DeepgramTranscriber()
    speaker = ElevenLabsSpeaker()
    handler = _make_handler(agent, transcriber, speaker.synthesize)

    httpd = ThreadingHTTPServer((host, port), handler)
    print(f"Nova voice server on http://{host}:{port}  — open it in Chrome, allow the mic.")
    print("The typed interface (python main.py) still works as your fallback. Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nbye 👋")
        httpd.shutdown()
