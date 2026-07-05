"""Persistent heartbeat state (Tier 5): when each check is next due, and the notices
it has surfaced.

Persisting next-due times is what stops a restart from refiring everything or
resetting every timer. Persisting notices is what makes "hold it and show me when
I'm back" true across a restart — nothing is fire-and-forget.

Plain JSON, same spirit as the memory store: human-readable, git-ignored, atomic
writes. Not a database — a personal assistant's heartbeat doesn't need one.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parent / "state.json"


class HeartbeatState:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else _DEFAULT_PATH
        self._data: dict[str, Any] = {"next_due": {}, "notices": []}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8").strip()
            if raw:
                try:
                    data = json.loads(raw)
                    self._data["next_due"] = data.get("next_due", {})
                    self._data["notices"] = data.get("notices", [])
                except json.JSONDecodeError:
                    self.path.replace(self.path.with_suffix(".json.corrupt"))

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._data, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # --- next-due schedule ----------------------------------------------------
    def get_next_due(self, check: str) -> float | None:
        return self._data["next_due"].get(check)

    def set_next_due(self, check: str, when: float) -> None:
        self._data["next_due"][check] = when
        self._save()

    # --- notices --------------------------------------------------------------
    def add_notice(self, notice: dict[str, Any]) -> None:
        self._data["notices"].append(notice)
        self._save()

    def update_notice(self, notice_id: str, **changes: Any) -> None:
        for n in self._data["notices"]:
            if n["id"] == notice_id:
                n.update(changes)
        self._save()

    def notices(self) -> list[dict[str, Any]]:
        return list(self._data["notices"])
