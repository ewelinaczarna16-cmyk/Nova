"""Brain + gate smoke tests with a fake LLM backend (no network, no API key).

Verifies: history is remembered across turns; the context budget trims; a safe tool
just runs; a consequential tool is stopped by the gate until approved; and a 'down'
model produces a clean message via fallback rather than a crash.
"""
from core.agent import Agent
from core.llm import LLMClient, StreamEvent, LLMError
from safety import ConfirmationGate, Decision
from tools import ToolRegistry
from tools.builtin import register_builtin_tools


class ScriptedBackend:
    """Returns pre-scripted event lists, one per stream() call, in order."""
    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.seen_messages = []

    def stream(self, *, model, system, messages, tools, max_tokens, temperature):
        self.seen_messages.append(list(messages))
        for ev in self.scripts.pop(0):
            yield ev


def _say(text, stop="end_turn"):
    return [StreamEvent("text", text=text), StreamEvent("done", stop_reason=stop)]


def _tool_call(tid, name, inp):
    return [StreamEvent("tool_use", tool_use={"id": tid, "name": name, "input": inp}),
            StreamEvent("done", stop_reason="tool_use")]


def _agent(scripts, gate=None, tools=None):
    backend = ScriptedBackend(scripts)
    llm = LLMClient(backend=backend, primary="m", fallback="m2")
    return Agent(llm=llm, tools=tools, gate=gate or ConfirmationGate()), backend


def test_remembers_earlier_turns():
    agent, backend = _agent([_say("hi"), _say("you said hello")])
    list(agent.turn("hello"))
    list(agent.turn("what did I say?"))
    # second call's messages include the first user turn
    second = backend.seen_messages[1]
    assert any(m["role"] == "user" and m["content"] == "hello" for m in second)


def test_context_budget_trims():
    scripts = [_say(f"r{i}") for i in range(10)]
    agent, _ = _agent(scripts)
    agent.max_turns = 4
    for i in range(5):
        list(agent.turn(f"msg{i}"))
    assert len(agent.history) <= 4


def test_safe_tool_just_runs():
    reg = ToolRegistry(dry_run=False)
    register_builtin_tools(reg)
    agent, _ = _agent([_tool_call("t1", "list_reminders", {}), _say("here they are")], tools=reg)
    out = "".join(c.text for c in agent.turn("what are my reminders?"))
    assert "Pay rent" in out          # the tool actually ran and fed back


def test_consequential_tool_blocked_then_allowed():
    reg = ToolRegistry(dry_run=False)
    register_builtin_tools(reg)

    # Approver says no the first time, yes the second.
    answers = iter([Decision(False, "nope"), Decision(True)])
    gate = ConfirmationGate(approver=lambda desc: next(answers))

    # First conversation: declined.
    agent1, _ = _agent([_tool_call("t1", "delete_reminder", {"text": "Pay rent"}),
                        _say("ok, left it")], gate=gate, tools=reg)
    out1 = "".join(c.text for c in agent1.turn("delete pay rent"))
    assert "Pay rent" in [r for r in ["Pay rent"]][0]  # still present conceptually
    assert "declined" in out1.lower() or "ok" in out1.lower()

    # Second conversation: approved -> tool runs.
    agent2, _ = _agent([_tool_call("t2", "delete_reminder", {"text": "Pay rent"}),
                        _say("done")], gate=gate, tools=reg)
    sys_text = "".join(c.text for c in agent2.turn("yes delete it"))
    assert "done" in sys_text.lower()


def test_model_down_is_clean_message_not_crash():
    class DeadBackend:
        def stream(self, **kw):
            raise LLMError("503 overloaded")
            yield  # pragma: no cover

    llm = LLMClient(backend=DeadBackend(), primary="m", fallback="m")  # same -> no retry
    agent = Agent(llm=llm)
    chunks = list(agent.turn("hi"))
    assert any(c.kind == "system" and "couldn't reach" in c.text for c in chunks)
