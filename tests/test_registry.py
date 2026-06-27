"""Smoke tests for the tool registry — one of the two places a silent failure is
most expensive. Verifies: the right tool gets called; a failed tool returns a clean
error instead of crashing; retries are capped; a hanging tool times out; bad input
is rejected; consequential tools are dry-run logged rather than executed."""
import time

from tools.registry import Tool, ToolRegistry, ToolError


def _reg(**kw) -> ToolRegistry:
    # Explicit knobs so tests don't depend on config file values.
    defaults = dict(max_retries=3, timeout=1.0, dry_run=False)
    defaults.update(kw)
    return ToolRegistry(**defaults)


def test_right_tool_runs_and_returns_value():
    reg = _reg()
    reg.register(Tool("echo", "echo back", {"type": "object",
                 "properties": {"x": {"type": "string"}}, "required": ["x"]},
                 handler=lambda x: f"got {x}"))
    res = reg.call("echo", {"x": "hi"})
    assert res.ok and res.content == "got hi"


def test_unknown_tool_is_clean_error_not_crash():
    res = _reg().call("nope", {})
    assert not res.ok and "no such tool" in res.content


def test_failing_tool_gives_up_after_max_retries():
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise ToolError("kaboom")

    reg = _reg()
    reg.register(Tool("boom", "always fails", {"type": "object", "properties": {}, "required": []}, handler=boom))
    res = reg.call("boom", {})
    assert not res.ok
    assert calls["n"] == 3                     # capped, did not loop forever
    assert "gave up" in res.content


def test_hanging_tool_times_out():
    reg = _reg(timeout=0.2)

    def hang():
        time.sleep(5)
        return "never"

    reg.register(Tool("hang", "hangs", {"type": "object", "properties": {}, "required": []}, handler=hang))
    res = reg.call("hang", {})
    assert not res.ok and "timed out" in res.content


def test_bad_input_rejected_before_handler():
    ran = {"yes": False}

    def h(x):
        ran["yes"] = True
        return "ok"

    reg = _reg()
    reg.register(Tool("needs_x", "needs x", {"type": "object",
                 "properties": {"x": {"type": "string"}}, "required": ["x"]}, handler=h))
    res = reg.call("needs_x", {})              # missing required 'x'
    assert not res.ok and "missing required" in res.content
    assert ran["yes"] is False


def test_consequential_dry_run_does_not_execute():
    ran = {"yes": False}

    def send(to):
        ran["yes"] = True
        return "sent"

    reg = _reg(dry_run=True)
    reg.register(Tool("send", "sends", {"type": "object",
                 "properties": {"to": {"type": "string"}}, "required": ["to"]},
                 handler=send, consequential=True))
    res = reg.call("send", {"to": "a@b.com"})
    assert res.ok and res.dry_run and ran["yes"] is False
    assert "[dry-run]" in res.content


def test_duplicate_registration_rejected():
    reg = _reg()
    t = Tool("dup", "d", {"type": "object", "properties": {}, "required": []}, handler=lambda: "x")
    reg.register(t)
    try:
        reg.register(t)
    except ValueError:
        return
    raise AssertionError("expected duplicate registration to raise")
