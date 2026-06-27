"""The LLM seam — the ONLY thing in Nova that touches a provider SDK directly.

Everything upstream (the agent loop, voice, heartbeat) talks to `LLMClient`, never
to `anthropic` directly. That's what makes the model swappable and what lets tests
inject a fake. It also gives us one place to put the fallback: when the primary is
genuinely *down* (not just slow), retry the request against a secondary model.

Contract:
    client.stream(system, messages, tools=None) -> iterator of StreamEvent

A StreamEvent is one of:
    ("text", str)        incremental text to show/speak
    ("tool_use", dict)   a complete tool call: {"id","name","input"}
    ("done", StopReason) end of the assistant turn

This keeps the same shape whether the turn ends in text or a tool request, so the
agent loop (Tier 1) and the tool runner (Tier 2) consume one stream type.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterator, Protocol

import config


@dataclass
class StreamEvent:
    kind: str                      # "text" | "tool_use" | "done"
    text: str = ""                 # for kind == "text"
    tool_use: dict[str, Any] | None = None   # for kind == "tool_use"
    stop_reason: str | None = None           # for kind == "done"


class LLMError(RuntimeError):
    """Raised when a model call fails in a way the agent loop should surface."""


class _Backend(Protocol):
    def stream(
        self, *, model: str, system: str, messages: list[dict],
        tools: list[dict] | None, max_tokens: int, temperature: float,
    ) -> Iterator[StreamEvent]: ...


class AnthropicBackend:
    """Concrete backend over the official Anthropic SDK. Imported lazily so the
    rest of Nova (and the test suite) loads without the package or a key."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = None

    def _ensure(self):
        if self._client is None:
            if not self._api_key:
                raise LLMError("ANTHROPIC_API_KEY is not set (see .env.example).")
            try:
                import anthropic  # lazy
            except ImportError as exc:  # pragma: no cover
                raise LLMError("anthropic package not installed: pip install -r requirements.txt") from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def stream(self, *, model, system, messages, tools, max_tokens, temperature):
        client = self._ensure()
        kwargs: dict[str, Any] = dict(
            model=model, system=system, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
        )
        if tools:
            kwargs["tools"] = tools
        try:
            with client.messages.stream(**kwargs) as stream:
                # Emit text incrementally; collect tool_use blocks as they finalize.
                for text in stream.text_stream:
                    yield StreamEvent("text", text=text)
                final = stream.get_final_message()
                for block in final.content:
                    if getattr(block, "type", None) == "tool_use":
                        yield StreamEvent("tool_use", tool_use={
                            "id": block.id, "name": block.name, "input": block.input,
                        })
                yield StreamEvent("done", stop_reason=final.stop_reason)
        except Exception as exc:  # network, 5xx, overload, etc.
            raise LLMError(str(exc)) from exc


@dataclass
class LLMClient:
    """Provider-agnostic client with primary→fallback behaviour.

    If `backend` is supplied it is used verbatim (tests inject a fake). Otherwise a
    real AnthropicBackend is built from config + env.
    """
    backend: _Backend | None = None
    primary: str = field(default_factory=lambda: config.get("model", "primary", default="claude-opus-4-8"))
    fallback: str = field(default_factory=lambda: config.get("model", "fallback", default="claude-haiku-4-5-20251001"))
    max_tokens: int = field(default_factory=lambda: config.get("model", "max_tokens", default=1024))
    temperature: float = field(default_factory=lambda: config.get("model", "temperature", default=0.7))

    def __post_init__(self):
        if self.backend is None:
            self.backend = AnthropicBackend()

    def stream(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> Iterator[StreamEvent]:
        """Stream a turn. On a hard failure of the primary model, fall back to the
        secondary model *once* before giving up. A fallback means it didn't stop
        working — 'apologizes nicely' still means it stopped."""
        try:
            yield from self._attempt(self.primary, system, messages, tools)
            return
        except LLMError as primary_exc:
            if not self.fallback or self.fallback == self.primary:
                raise
            try:
                yield from self._attempt(self.fallback, system, messages, tools)
                return
            except LLMError as fallback_exc:
                raise LLMError(
                    f"both primary ({self.primary}) and fallback ({self.fallback}) failed: "
                    f"{primary_exc} | {fallback_exc}"
                ) from fallback_exc

    def _attempt(self, model, system, messages, tools) -> Iterator[StreamEvent]:
        # Buffer the first chunk so a connection error surfaces *before* we've
        # streamed half a reply to the user; after first success we pass through.
        gen = self.backend.stream(
            model=model, system=system, messages=messages, tools=tools,
            max_tokens=self.max_tokens, temperature=self.temperature,
        )
        first = next(gen)   # may raise LLMError -> caller can still fall back
        yield first
        yield from gen
