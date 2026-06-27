"""Tool registry (Tier 2): the hands.

Each tool has a name, a description written for a *reader* (the model), a typed
JSON-schema for its inputs, a safe/consequential classification, and a handler. The
whole registry is handed to the model each turn; the model may chain several calls
before answering.

Reliability built in here, not sprinkled around callers:
  - inputs are validated against the schema before the handler runs;
  - handler exceptions become a clean, plain-language error returned to the model
    (it does not crash the turn);
  - each call has a timeout so one hanging tool can't freeze a whole turn;
  - the runner caps retries (config: safety.max_tool_retries) — three strikes on the
    same call and it gives up and tells the user instead of looping.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Callable

import config


class ToolError(Exception):
    """A tool failed in a way worth reporting back to the model as a clean error."""


@dataclass
class ToolResult:
    ok: bool
    content: str
    dry_run: bool = False


# A handler takes validated kwargs and returns a string (or raises ToolError).
Handler = Callable[..., str]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]          # JSON schema, properties + required
    handler: Handler
    consequential: bool = False           # marked at registration, from Tier 0 list

    def to_model_schema(self) -> dict[str, Any]:
        """The shape the model expects (Anthropic tool schema)."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def _validate(schema: dict[str, Any], args: dict[str, Any]) -> None:
    """Tiny dependency-free validator: required keys present, declared types match.
    Enough to catch the model handing a tool the wrong shape; not a full JSON-schema
    engine."""
    props = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in args:
            raise ToolError(f"missing required argument '{key}'")
    type_map = {
        "string": str, "integer": int, "number": (int, float),
        "boolean": bool, "array": list, "object": dict,
    }
    for key, value in args.items():
        spec = props.get(key)
        if not spec:
            continue
        expected = type_map.get(spec.get("type"))
        if expected and not isinstance(value, expected):
            raise ToolError(f"argument '{key}' should be {spec.get('type')}")


def _run_with_timeout(fn: Callable[[], str], seconds: float) -> str:
    """Run fn in a worker thread; raise ToolError if it overruns. (Thread, not
    signal, so it works off the main thread — e.g. the heartbeat in Tier 5.)"""
    box: dict[str, Any] = {}

    def target():
        try:
            box["result"] = fn()
        except Exception as exc:  # noqa: BLE001 — funnelled into ToolError below
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive():
        raise ToolError(f"tool timed out after {seconds:g}s")
    if "error" in box:
        raise ToolError(str(box["error"]))
    return box.get("result", "")


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)
    dry_run: bool = field(default_factory=lambda: config.get("safety", "dry_run", default=True))
    max_retries: int = field(default_factory=lambda: config.get("safety", "max_tool_retries", default=3))
    timeout: float = field(default_factory=lambda: config.get("safety", "tool_timeout_seconds", default=30))

    def register(self, tool: Tool) -> None:
        if tool.name in self.tools:
            raise ValueError(f"tool '{tool.name}' already registered")
        self.tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)

    def model_schemas(self) -> list[dict[str, Any]]:
        return [t.to_model_schema() for t in self.tools.values()]

    def call(self, name: str, args: dict[str, Any]) -> ToolResult:
        """Validate + run a tool with retries and a timeout. Always returns a
        ToolResult (ok or a clean error) — never raises into the turn loop.

        Note: this does NOT enforce the confirmation gate. The agent loop checks the
        gate *before* calling, so the gate sits at the same layer for every entry
        point and a tool author can't accidentally skip it.
        """
        tool = self.tools.get(name)
        if tool is None:
            return ToolResult(ok=False, content=f"no such tool: {name}")

        try:
            _validate(tool.input_schema, args)
        except ToolError as exc:
            return ToolResult(ok=False, content=f"invalid input: {exc}")

        # Dry-run: consequential tools log what they WOULD do, do not execute.
        if tool.consequential and self.dry_run:
            return ToolResult(
                ok=True, dry_run=True,
                content=f"[dry-run] would run {name}({args}); no real action taken.",
            )

        last_err = ""
        for attempt in range(1, self.max_retries + 1):
            try:
                out = _run_with_timeout(lambda: tool.handler(**args), self.timeout)
                return ToolResult(ok=True, content=out)
            except ToolError as exc:
                last_err = str(exc)
        return ToolResult(
            ok=False,
            content=f"tool '{name}' failed {self.max_retries} times and gave up: {last_err}",
        )
