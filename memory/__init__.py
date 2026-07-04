"""Nova memory (Tier 4): durable facts that survive a restart.

Long-term memory. Short-term conversation history lives in the Agent; this is the
stuff worth keeping — name, preferences, decisions. Background knowledge, never
instructions (a stored note can't become a backdoor around the confirmation gate).
"""
from .store import MemoryStore  # noqa: F401
