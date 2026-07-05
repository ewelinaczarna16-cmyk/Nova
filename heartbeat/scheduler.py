"""The heartbeat loop (Tier 5): a separate background loop that lets Nova act without
being spoken to — quiet by default, earning its interruptions.

What it guarantees:
  - Checks are defined in CONFIG, not code (config.heartbeat.checks.*).
  - Next-due times are PERSISTED, so a restart resumes the schedule and doesn't
    refire everything or reset timers.
  - A check still running when its next turn comes due is SKIPPED, never stacked.
  - A consequential background action goes through the SAME safety gate, and if no
    approval arrives within the timeout it TIMES OUT into "do nothing, leave a note"
    — the heartbeat gets no side door around confirmation.
  - Surfacing is routed through NotificationCenter (quiet hours / hold / dismiss).

Relocatable by design: the loop only touches config + state + tools + the notifier,
so moving it to an always-on host later is a relocation, not a rewrite.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta

import config

from .center import NotificationCenter
from .checks import Check, CheckContext, CHECK_TYPES
from .store import HeartbeatState


def _next_at(now: float, hhmm: str) -> float:
    """Epoch of the next local HH:MM strictly after `now`."""
    hour, minute = (int(x) for x in hhmm.split(":"))
    base = datetime.fromtimestamp(now)
    cand = base.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if cand.timestamp() <= now:
        cand += timedelta(days=1)
    return cand.timestamp()


class Heartbeat:
    def __init__(self, checks: list[Check], center: NotificationCenter,
                 state: HeartbeatState, tools=None, approval_timeout: float = 1800,
                 background_approver=None, log=print):
        self.checks = checks
        self.center = center
        self.state = state
        self.tools = tools
        self.approval_timeout = approval_timeout
        self.background_approver = background_approver   # None -> everything times out to a note
        self.log = log
        self._running: set[str] = set()
        self._lock = threading.Lock()

    # --- scheduling -----------------------------------------------------------
    def _compute_next(self, check: Check, now: float) -> float:
        if "every_seconds" in check.schedule:
            return now + float(check.schedule["every_seconds"])
        if "at" in check.schedule:
            return _next_at(now, check.schedule["at"])
        return now + 3600.0   # sane fallback

    def tick(self, now: float | None = None) -> None:
        """One pass of the loop. Cheap: usually does nothing but flush held notices."""
        now = time.time() if now is None else now
        self.center.flush_held(now)
        for check in self.checks:
            if not check.enabled:
                continue
            if check.name in self._running:      # still running from a prior tick -> skip
                self.log(f"[heartbeat] {check.name} still running; skipping")
                continue
            due = self.state.get_next_due(check.name)
            if due is None:
                # First time we've seen this check: schedule it forward, don't fire
                # immediately (so enabling it doesn't dump a notice on you at once).
                self.state.set_next_due(check.name, self._compute_next(check, now))
                continue
            if now >= due:
                self._run(check, now)
                self.state.set_next_due(check.name, self._compute_next(check, now))

    def trigger(self, name: str, now: float | None = None) -> str | None:
        """Force-run a check once, ignoring its schedule (for the verify step / manual
        'digest now'). Returns the surfaced text, or None."""
        now = time.time() if now is None else now
        check = next((c for c in self.checks if c.name == name), None)
        if check is None:
            return None
        return self._run(check, now)

    def _run(self, check: Check, now: float) -> str | None:
        with self._lock:
            if check.name in self._running:
                return None
            self._running.add(check.name)
        try:
            ctx = CheckContext(tools=self.tools, now=now, request_action=self._request_action)
            result = check.run(ctx)
        except Exception as exc:                 # a broken check must not kill the loop
            self.log(f"[heartbeat] {check.name} errored: {exc}")
            return None
        finally:
            self._running.discard(check.name)
        if result:
            self.center.surface(result, now)     # worth surfacing
            return result
        self.log(f"[heartbeat] {check.name}: nothing to surface")  # calm log
        return None

    # --- consequential background actions -------------------------------------
    def _request_action(self, description: str, *, consequential: bool, do_it) -> bool:
        """Gate a background action. Safe -> just do it. Consequential -> needs
        approval within the timeout, else leave a note and do nothing."""
        if not consequential:
            do_it()
            return True
        approved = False
        if self.background_approver is not None:
            approved = bool(self.background_approver(description, self.approval_timeout))
        if approved:
            do_it()
            return True
        self.center.surface(f"⏸ Skipped (needed your OK, none came): {description}")
        return False

    # --- the actual loop ------------------------------------------------------
    def run_forever(self, tick_seconds: float = 30.0, stop: threading.Event | None = None) -> None:
        self.log("[heartbeat] running. Quiet by default; Ctrl-C to stop.")
        try:
            while not (stop and stop.is_set()):
                self.tick()
                time.sleep(tick_seconds)
        except KeyboardInterrupt:
            self.log("\n[heartbeat] stopped.")


# --- assembly from config -----------------------------------------------------
def build_from_config(tools=None, state: HeartbeatState | None = None,
                      channel=None) -> Heartbeat:
    from .notify import TwilioSms

    state = state or HeartbeatState()
    hb_cfg = config.get("heartbeat", default={}) or {}
    dry_run = hb_cfg.get("dry_run", True)
    channel = channel or TwilioSms(dry_run=dry_run)
    center = NotificationCenter(
        state=state, channel=channel,
        quiet_start=hb_cfg.get("quiet_hours_start", "22:00"),
        quiet_end=hb_cfg.get("quiet_hours_end", "08:00"),
    )
    checks: list[Check] = []
    for name, spec in (hb_cfg.get("checks", {}) or {}).items():
        fn = CHECK_TYPES.get(spec.get("type", name))
        if fn is None:
            continue
        schedule = {}
        if "every_seconds" in spec:
            schedule["every_seconds"] = spec["every_seconds"]
        elif "at" in spec:
            schedule["at"] = spec["at"]
        checks.append(Check(name=name, run=fn, schedule=schedule,
                            enabled=spec.get("enabled", True), model=spec.get("model", "none")))
    return Heartbeat(checks, center, state, tools=tools,
                     approval_timeout=hb_cfg.get("approval_timeout_seconds", 1800))
