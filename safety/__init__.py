"""Nova safety: the confirmation gate, audit log, kill switch.

Tier 2 ships the minimum-viable gate (stub). Tier 6 hardens it (audit trail,
spending ceiling, injection handling, kill switch). The gate exists from the first
tool ever added, so there is never a window where consequential actions are ungated.
"""
from .gate import ConfirmationGate, ConfirmationRequired, Decision  # noqa: F401
