"""Heartbeat checks (Tier 5): the things Nova does unprompted.

A check runs on a schedule and returns either a notice string (worth surfacing) or
None (nothing this time — most checks, most of the time). Checks never send notices
themselves; they hand a string back and the scheduler routes it through the same
quiet-hours / hold / dismiss discipline.

The first check is the daily digest — a "here's your day" text that proves the
channel and the tier end to end. It's built deterministically from calendar +
reminders (model = "none"): no LLM, no spend. Model-backed checks get their model
from config per the cost-discipline rule.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from tools import ToolRegistry


@dataclass
class CheckContext:
    tools: ToolRegistry | None
    now: float
    # Route a would-be consequential action through the gate with a timeout; the
    # heartbeat binds this. Safe checks never call it.
    request_action: Callable[..., bool] | None = None


# A check: name, the function, schedule dict from config, model, enabled.
@dataclass
class Check:
    name: str
    run: Callable[[CheckContext], Optional[str]]
    schedule: dict            # {"at": "08:00"} or {"every_seconds": N}
    enabled: bool = True
    model: str = "none"


def daily_digest(ctx: CheckContext) -> Optional[str]:
    """Deterministic 'here's your day' from calendar + reminders."""
    if ctx.tools is None:
        return None
    cal = ctx.tools.call("read_calendar", {"day": "today"}).content
    rem = ctx.tools.call("list_reminders", {}).content
    return f"☀️ Morning! Here's your day:\n\n{cal}\n\n{rem}"


# Map config `type` -> check function, so checks are defined in config, not code.
CHECK_TYPES: dict[str, Callable[[CheckContext], Optional[str]]] = {
    "daily_digest": daily_digest,
}
