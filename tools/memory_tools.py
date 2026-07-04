"""Memory tools (Tier 4): how the model reads and corrects durable facts in-conversation.

These back the live-correction phrases ("remember I like X", "no I meant Y",
"forget that") so fixing a wrong fact happens in the flow, not by editing a file.

Classification:
  - remember_fact / list_facts are SAFE (recording/reading background knowledge).
  - forget_fact is SAFE too — it edits Nova's OWN memory (self-correction the spec
    explicitly wants to be frictionless), and every write leaves a .bak, so a wrong
    'forget' is recoverable. This is deliberately distinct from the Tier 0 'delete'
    guardrail, which is about deleting the USER's external data (files, events).
"""
from __future__ import annotations

from memory import MemoryStore

from .registry import Tool, ToolRegistry, ToolError


def register_memory_tools(registry: ToolRegistry, store: MemoryStore) -> None:
    def remember_fact(key: str, value: str) -> str:
        try:
            return store.remember(key, value)
        except ValueError as exc:
            raise ToolError(str(exc))

    def forget_fact(key: str) -> str:
        try:
            return store.forget(key)
        except KeyError as exc:
            raise ToolError(str(exc))

    def list_facts() -> str:
        facts = store.all()
        if not facts:
            return "I don't have any saved facts about you yet."
        return "Here's what I remember:\n" + "\n".join(f"- {k}: {v}" for k, v in facts.items())

    registry.register(Tool(
        name="remember_fact",
        description="Save or update ONE durable fact about the user (name, a "
                    "preference, a decision). Use a short stable key like 'name' or "
                    "'coffee_order'. Re-using a key overwrites it — that's how you "
                    "correct a fact when the user says 'no, I meant ...'.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "short stable identifier, e.g. 'name'"},
                "value": {"type": "string", "description": "the fact as one plain statement"},
            },
            "required": ["key", "value"],
        },
        handler=remember_fact,
        consequential=False,
    ))
    registry.register(Tool(
        name="forget_fact",
        description="Delete one saved fact by its key. Use when the user says to "
                    "forget something. Recoverable from the .bak file if needed.",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
        handler=forget_fact,
        consequential=False,
    ))
    registry.register(Tool(
        name="list_facts",
        description="List everything Nova currently remembers about the user.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=list_facts,
        consequential=False,
    ))
