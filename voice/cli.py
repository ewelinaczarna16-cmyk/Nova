"""Voice entry point:  python main.py --voice

Builds the SAME registry + gate as the text CLI, but wires a *spoken* confirmation
approver so consequential actions are confirmed by voice. Runs on your laptop (needs
mic, speakers, and reachable Deepgram/ElevenLabs); the typed CLI stays as fallback.
"""
from __future__ import annotations

from core.agent import Agent
from safety import ConfirmationGate, Decision
from tools import ToolRegistry
from tools.builtin import register_builtin_tools

from .audio import record_ptt
from .session import VoiceSession
from .stt import DeepgramTranscriber
from .tts import ElevenLabsSpeaker


def build_voice_session() -> tuple[VoiceSession, "callable"]:
    transcriber = DeepgramTranscriber()
    speaker = ElevenLabsSpeaker()

    def voice_approver(description: str) -> Decision:
        # Same gate, spoken prompt. Asks out loud, then captures a yes/no.
        speaker.speak(f"This will {description}. Should I go ahead? Say yes or no.")
        audio = record_ptt("[confirm] press Enter, say yes or no, Enter to stop…")
        answer = transcriber.transcribe(audio).lower()
        ok = "yes" in answer or "go ahead" in answer or "confirm" in answer
        return Decision(approved=ok, reason="" if ok else f"declined (heard: {answer!r})")

    registry = ToolRegistry()
    register_builtin_tools(registry)
    gate = ConfirmationGate(approver=voice_approver)
    agent = Agent(tools=registry, gate=gate)
    return VoiceSession(agent=agent, transcriber=transcriber, speaker=speaker), record_ptt


def main() -> None:
    session, record = build_voice_session()
    session.run(record)


if __name__ == "__main__":
    main()
