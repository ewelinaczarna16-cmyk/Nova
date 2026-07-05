"""Smoke tests for the browser voice turn handler (no HTTP, no audio, no network).

Proves the browser front-end reuses the SAME brain + tools + memory and degrades
cleanly when STT or TTS misbehaves."""
import base64

from core.agent import Agent
from core.llm import LLMClient, StreamEvent
from memory import MemoryStore
from tools import ToolRegistry
from tools.builtin import register_builtin_tools
from voice import FakeTranscriber
from voice.webserver import run_turn


class Scripted:
    def __init__(self, scripts): self.scripts = list(scripts)
    def stream(self, *, model, system, messages, tools, max_tokens, temperature):
        for ev in self.scripts.pop(0):
            yield ev


def _agent(scripts, tools=None, memory=None):
    return Agent(llm=LLMClient(backend=Scripted(scripts), primary="m", fallback="m"),
                 tools=tools, memory=memory)


def _say(t):
    return [StreamEvent("text", text=t), StreamEvent("done", stop_reason="end_turn")]


def _fake_synth(text):            # pretend-TTS: bytes that encode the text
    return text.encode("utf-8")


def test_browser_turn_uses_same_brain_and_returns_audio():
    agent = _agent([_say("Hey there!")])
    out = run_turn(agent, FakeTranscriber(["hello nova"]), _fake_synth, b"<audio>")
    assert out["ok"] and out["transcript"] == "hello nova"
    assert "Hey there!" in out["reply"]
    assert base64.b64decode(out["audio_b64"]).decode() == "Hey there!"


def test_browser_turn_runs_tools_and_memory():
    reg = ToolRegistry(dry_run=False)
    register_builtin_tools(reg)
    agent = _agent([[StreamEvent("tool_use", tool_use={"id": "1", "name": "list_reminders", "input": {}}),
                     StreamEvent("done", stop_reason="tool_use")],
                    _say("There you go.")], tools=reg)
    out = run_turn(agent, FakeTranscriber(["my reminders"]), _fake_synth, b"<audio>")
    assert "There you go." in out["reply"]


def test_empty_transcript_degrades_cleanly():
    agent = _agent([_say("unused")])
    out = run_turn(agent, FakeTranscriber([""]), _fake_synth, b"")
    assert out["ok"] and out["transcript"] == "" and out["audio_b64"] == ""


def test_tts_failure_still_returns_text():
    agent = _agent([_say("I can still be read on screen.")])

    def boom(text): raise RuntimeError("tts down")
    out = run_turn(agent, FakeTranscriber(["hi"]), boom, b"<audio>")
    assert out["ok"] and "read on screen" in out["reply"]
    assert "voice unavailable" in out["reply"] and out["audio_b64"] == ""


def test_stt_failure_reported_not_crash():
    class BoomSTT:
        def transcribe(self, audio, *, content_type="audio/webm"): raise RuntimeError("stt down")
    agent = _agent([_say("unused")])
    out = run_turn(agent, BoomSTT(), _fake_synth, b"<audio>")
    assert out["ok"] is False and "couldn't transcribe" in out["reply"]
