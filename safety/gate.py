"""The confirmation gate (Tier 2 stub).

Minimum viable: any `consequential` tool call stops, states plainly what it is about
to do, and waits for an explicit yes before running. Crude on purpose — Tier 6 adds
the audit log, kill switch, spending ceiling, and injection handling. But the gate
itself is here from the first tool, and the SAME gate is reused by every entry point
(text, voice, heartbeat) so none of them gets a side door around confirmation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass
class Decision:
    approved: bool
    reason: str = ""


class ConfirmationRequired(Exception):
    """Raised when a consequential action needs approval and no approver is wired.

    Carries a human-readable description so any front-end can render the prompt.
    """
    def __init__(self, description: str):
        super().__init__(description)
        self.description = description


# An approver takes the plain-language description of what's about to happen and
# returns a Decision. The CLI wires a stdin y/N approver; voice wires a spoken one;
# the heartbeat wires one that times out into "do nothing, leave a note" (Tier 5).
Approver = Callable[[str], Decision]


class ConfirmationGate:
    def __init__(self, approver: Approver | None = None):
        self._approver = approver

    def with_approver(self, approver: Approver) -> "ConfirmationGate":
        self._approver = approver
        return self

    def check(self, *, consequential: bool, description: str) -> Decision:
        """Gate a single action. Safe actions pass straight through. Consequential
        actions require an explicit approval; approving one never pre-authorizes
        the next (Tier 6 keeps this property when hardened)."""
        if not consequential:
            return Decision(approved=True, reason="safe action")
        if self._approver is None:
            raise ConfirmationRequired(description)
        return self._approver(description)
