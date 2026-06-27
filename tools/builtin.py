"""The first concrete tools (Tier 2).

These are deliberately backed by in-memory/stub data for now — real calendar,
reminder, and email integrations slot in behind the same handler signatures later
without touching the registry or the agent loop. What matters at this tier is that:
  - safe tools (calendar/reminders/notes reads + adds) just run;
  - consequential tools (email send, delete) are MARKED consequential so the gate
    stops them until an explicit yes (and dry-run logs them meanwhile).
"""
from __future__ import annotations

from datetime import date

from .registry import Tool, ToolRegistry, ToolError

# --- stub data stores (replaced by real integrations later) ---
_CALENDAR = [
    {"time": "09:30", "title": "Standup"},
    {"time": "13:00", "title": "Lunch with Sam"},
    {"time": "16:00", "title": "Dentist"},
]
_REMINDERS = ["Pay rent", "Call mum back", "Renew passport"]
_NOTES: dict[str, str] = {}


def _read_calendar(day: str = "today") -> str:
    when = date.today().isoformat() if day == "today" else day
    if not _CALENDAR:
        return f"Nothing on the calendar for {when}."
    lines = [f"{e['time']} — {e['title']}" for e in _CALENDAR]
    return f"Calendar for {when}:\n" + "\n".join(lines)


def _list_reminders() -> str:
    if not _REMINDERS:
        return "No reminders right now."
    return "Reminders:\n" + "\n".join(f"- {r}" for r in _REMINDERS)


def _add_reminder(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ToolError("reminder text was empty")
    _REMINDERS.append(text)
    return f"Added reminder: {text}"


def _delete_reminder(text: str) -> str:           # consequential: delete
    for i, r in enumerate(_REMINDERS):
        if r.lower() == (text or "").strip().lower():
            _REMINDERS.pop(i)
            return f"Deleted reminder: {text}"
    raise ToolError(f"no reminder matching '{text}'")


def _save_note(key: str, value: str) -> str:
    _NOTES[key] = value
    return f"Saved note '{key}'."


def _recall_note(key: str) -> str:
    if key not in _NOTES:
        return f"No note saved under '{key}'."
    return f"{key}: {_NOTES[key]}"


def _send_email(to: str, subject: str, body: str) -> str:   # consequential: send
    # Real send wired later; under dry-run this handler is never reached.
    return f"Sent email to {to} (subject: {subject})."


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register Nova's starter tool set. Calendar + reminders + notes are the
    concrete first capabilities; email-send and delete are the gated examples."""
    registry.register(Tool(
        name="read_calendar",
        description="Read the user's calendar for a given day. Use this to tell the "
                    "user what's on today or on a named date.",
        input_schema={
            "type": "object",
            "properties": {"day": {"type": "string", "description": "'today' or an ISO date like 2026-06-27"}},
            "required": [],
        },
        handler=_read_calendar,
        consequential=False,
    ))
    registry.register(Tool(
        name="list_reminders",
        description="List the user's current reminders / to-dos and read them back.",
        input_schema={"type": "object", "properties": {}, "required": []},
        handler=_list_reminders,
        consequential=False,
    ))
    registry.register(Tool(
        name="add_reminder",
        description="Add a new reminder / to-do for the user.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "what to be reminded about"}},
            "required": ["text"],
        },
        handler=_add_reminder,
        consequential=False,
    ))
    registry.register(Tool(
        name="delete_reminder",
        description="Delete an existing reminder by its exact text. Consequential: "
                    "removes data, so it must be confirmed first.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "exact text of the reminder to delete"}},
            "required": ["text"],
        },
        handler=_delete_reminder,
        consequential=True,
    ))
    registry.register(Tool(
        name="save_note",
        description="Save a short freeform note under a key for later recall.",
        input_schema={
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
        handler=_save_note,
        consequential=False,
    ))
    registry.register(Tool(
        name="recall_note",
        description="Recall a previously saved note by its key.",
        input_schema={
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
        handler=_recall_note,
        consequential=False,
    ))
    registry.register(Tool(
        name="send_email",
        description="Send an email on the user's behalf. Consequential: this sends "
                    "something, so it must be confirmed first.",
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
        handler=_send_email,
        consequential=True,
    ))
