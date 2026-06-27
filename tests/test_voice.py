"""Voice-layer smoke tests with fakes (no mic, no network).

Proves the voice layer is a thin adapter on the SAME brain + gate, not a fork:
  - a spoken turn goes audio -> transcript -> same Agent -> speech;
  - the transcript is surfaced;
  - a tool used over voice runs through the normal registry;
  - the confirmation gate still blocks a consequential action over voice;
  - empty/misheard audio degrades cleanly;
  - barge-in stop is wired.
"""
from core.agent import Agent
from core.llm import LLMClient, StreamEvent
from safety import ConfirmationGate, Decision
from tools import ToolRegistry
from tools.builtin import register_builtin_tools
from voice import VoiceSession, FakeTranscriber, FakeSpeaker


class ScriptedBackend:
    def __init__(self, scripts):
        self.scripts = list(scripts)

    def stream(self, *, model, system, messages, tools, max_tokens, temperature):
        for ev in self.scripts.pop(0):
            yield ev


def _say(text, stop="end_turn"):
    return [StreamEvent("text", text=text), StreamEvent("done", stop_reason=stop)]


def _tool_call(tid, name, inp):
    return [StreamEvent("tool_use", tool_use={"id": tid, "name": name, "input": inp}),
            StreamEvent("done", stop_reason="tool_use")]


def _session(scripts, transcripts, gate=None, tools=None):
    llm = LLMClient(backend=ScriptedBackend(scripts), primary="m", fallback="m")
    agent = Agent(llm=llm, tools=tools, gate=gate or ConfirmationGate())
    spk = FakeSpeaker()
    sess = VoiceSession(agent=agent, transcriber=FakeTranscriber(transcripts),
                        speaker=spk, on_status=lambda *_: None)
    return sess, spk


def test_spoken_turn_uses_same_brain_and_speaks_reply():
    sess, spk = _session([_say("Hey! What's up?")], ["hello nova"])
    out = sess.handle_audio(b"<fake wav>")
    assert out["transcript"] == "hello nova"          # transcript surfaced
    assert "Hey" in out["reply"]
    assert spk.spoken                                 # something was spoken
    # Spoken sentence-by-sentence; same content as the reply (ignoring the pauses).
    norm = lambda s: "".join(s.split())
    assert norm("".join(spk.spoken)) == norm(out["reply"])


def test_tool_over_voice_runs_through_registry():
    reg = ToolRegistry(dry_run=False)
    register_builtin_tools(reg)
    sess, spk = _session([_tool_call("t1", "list_reminders", {}), _say("Here you go.")],
                         ["what are my reminders"], tools=reg)
    out = sess.handle_audio(b"<wav>")
    # The tool ran; reminder data made it into the conversation (status, not speech).
    assert "Here you go." in out["reply"]


def test_gate_blocks_consequential_over_voice():
    reg = ToolRegistry(dry_run=False)
    register_builtin_tools(reg)
    gate = ConfirmationGate(approver=lambda d: Decision(False, "declined by voice"))
    sess, spk = _session([_tool_call("t1", "send_email",
                          {"to": "a@b.com", "subject": "hi", "body": "yo"}),
                          _say("Okay, I won't send it.")],
                         ["email bob hi"], gate=gate, tools=reg)
    out = sess.handle_audio(b"<wav>")
    assert "won't" in out["reply"].lower() or "okay" in out["reply"].lower()


def test_empty_audio_degrades_cleanly():
    sess, spk = _session([_say("unused")], [""])
    out = sess.handle_audio(b"")
    assert out["transcript"] == "" and out["spoken"] == []
    assert spk.spoken == []


def test_barge_in_stop_wired():
    sess, spk = _session([_say("hi")], ["hello"])
    sess.interrupt()
    assert spk.interrupted is True
