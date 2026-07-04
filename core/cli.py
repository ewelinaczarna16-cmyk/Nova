"""Text REPL — Nova's first (and forever) interface and debug path.

Voice (Tier 3) wraps the same Agent; this typed loop never goes away. It also wires
a stdin y/N approver into the confirmation gate so consequential tools prompt here.
"""
from __future__ import annotations

import sys

from memory import MemoryStore
from safety import ConfirmationGate, Decision
from tools import ToolRegistry
from tools.builtin import register_builtin_tools
from tools.memory_tools import register_memory_tools

from .agent import Agent


def _stdin_approver(description: str) -> Decision:
    print(f"\n[confirm] About to: {description}\n  Allow? [y/N] ", end="", flush=True)
    answer = sys.stdin.readline().strip().lower()
    return Decision(approved=answer in ("y", "yes"),
                    reason="" if answer in ("y", "yes") else "declined at prompt")


def build_agent() -> Agent:
    registry = ToolRegistry()
    register_builtin_tools(registry)
    store = MemoryStore()                       # loads durable facts from disk
    register_memory_tools(registry, store)
    gate = ConfirmationGate(approver=_stdin_approver)
    return Agent(tools=registry, gate=gate, memory=store)


def main() -> None:
    agent = build_agent()
    print("Nova (text mode). Ctrl-C to quit.\n")
    try:
        while True:
            user = input("you › ").strip()
            if not user:
                continue
            print("nova › ", end="", flush=True)
            for chunk in agent.turn(user):
                if chunk.kind == "text":
                    print(chunk.text, end="", flush=True)
                else:  # system breadcrumb (tool ran / error / model down)
                    print(chunk.text, end="", flush=True)
            print()
    except (KeyboardInterrupt, EOFError):
        print("\nbye 👋")


if __name__ == "__main__":
    main()
