"""Notification center (Tier 5): the discipline around surfacing a notice.

Rules it enforces (from the spec):
  - Quiet hours: HOLD a notice instead of sending it; deliver when quiet hours end.
    Never fire-and-forget — held notices are persisted, so a restart still delivers.
  - Every surfaced item is dismissible and stays in the pending list until dismissed.
  - Most checks produce nothing; only real notices come through here. Everything else
    stays a calm log at the scheduler level.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from .store import HeartbeatState


def _hhmm(epoch: float) -> str:
    t = time.localtime(epoch)
    return f"{t.tm_hour:02d}:{t.tm_min:02d}"


def _in_window(now_hhmm: str, start: str, end: str) -> bool:
    """True if now is within [start, end), handling a window that wraps midnight
    (e.g. 22:00 -> 08:00)."""
    if start == end:
        return False
    if start < end:
        return start <= now_hhmm < end
    return now_hhmm >= start or now_hhmm < end   # wraps midnight


@dataclass
class NotificationCenter:
    state: HeartbeatState
    channel: object                 # Channel
    quiet_start: str = "22:00"
    quiet_end: str = "08:00"

    def in_quiet_hours(self, now: float | None = None) -> bool:
        return _in_window(_hhmm(now if now is not None else time.time()),
                          self.quiet_start, self.quiet_end)

    def surface(self, text: str, now: float | None = None) -> dict:
        """Bring a notice into being. Deliver now unless we're in quiet hours, in
        which case hold it (persisted) for delivery when quiet hours end."""
        now = time.time() if now is None else now
        notice = {
            "id": uuid.uuid4().hex[:12],
            "text": text,
            "created": now,
            "delivered": False,
            "held": False,
            "dismissed": False,
        }
        if self.in_quiet_hours(now):
            notice["held"] = True
            self.state.add_notice(notice)
        else:
            self.state.add_notice(notice)
            self._deliver(notice)
        return notice

    def flush_held(self, now: float | None = None) -> int:
        """Deliver any held, undismissed notices once we're out of quiet hours.
        Called every tick. Returns how many were delivered."""
        now = time.time() if now is None else now
        if self.in_quiet_hours(now):
            return 0
        n = 0
        for notice in self.state.notices():
            if notice["held"] and not notice["delivered"] and not notice["dismissed"]:
                self._deliver(notice)
                n += 1
        return n

    def _deliver(self, notice: dict) -> None:
        status = self.channel.send(notice["text"])
        self.state.update_notice(notice["id"], delivered=True, held=False, status=status)

    def pending(self) -> list[dict]:
        """Notices you haven't dismissed yet (what you'd see on return)."""
        return [n for n in self.state.notices() if not n["dismissed"]]

    def dismiss(self, notice_id: str) -> bool:
        if any(n["id"] == notice_id for n in self.state.notices()):
            self.state.update_notice(notice_id, dismissed=True)
            return True
        return False
