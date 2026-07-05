"""Notification channel (Tier 5): how a surfaced notice reaches you.

Decided, not "pick later": every notice the heartbeat judges worth surfacing goes out
as an SMS to your phone (Twilio by default) — no laptop-only notices. Dry-run logs the
message instead of sending, so Tiers 5–6 can be developed without real texts going out
or costing money; flip config heartbeat.dry_run=false once TWILIO_* is in .env.
"""
from __future__ import annotations

import os
from typing import Protocol


class Channel(Protocol):
    def send(self, text: str) -> str:
        """Deliver the text. Returns a short status string for the log."""
        ...


class TwilioSms:
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.from_ = os.environ.get("TWILIO_FROM_NUMBER")
        self.to = os.environ.get("NOTIFY_TO_NUMBER")

    def send(self, text: str) -> str:
        # Dry-run OR missing creds -> log, never crash the loop over a config gap.
        if self.dry_run or not all((self.sid, self.token, self.from_, self.to)):
            why = "dry_run" if self.dry_run else "missing TWILIO_* / NOTIFY_TO_NUMBER"
            print(f"[heartbeat/sms {why}] would text: {text!r}")
            return f"logged ({why})"
        try:
            import requests  # lazy
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pip install requests to send SMS") from exc
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json",
            data={"From": self.from_, "To": self.to, "Body": text},
            auth=(self.sid, self.token),
            timeout=20,
        )
        resp.raise_for_status()
        return "sent"


class FakeChannel:
    """Test/dev double: records what would have been sent."""
    def __init__(self):
        self.sent: list[str] = []

    def send(self, text: str) -> str:
        self.sent.append(text)
        return "sent(fake)"
