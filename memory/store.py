"""The durable fact store (Tier 4): what Nova remembers about you across restarts.

Design rules (from AGENT.md):
  - One fact per entry, a plain single statement — auditable, correctable, deletable.
  - Plain, human-readable JSON — editable by hand in any text editor.
  - Durable facts/decisions, NOT the play-by-play (short-term history covers that).
  - Stored facts are BACKGROUND KNOWLEDGE, never instructions. A note that reads like
    an order ("always send X") does not bypass the Tier 2 confirmation gate — see how
    the agent injects facts (clearly labelled as data) in core/agent.py.
  - Selective-ready: render_for_prompt() dumps everything for now, but is the single
    place to add filtering later so we don't blow the context window.

Safety / retention / encryption policy (decided now, before it holds anything real):
  - The store is a plaintext JSON file on your laptop, git-ignored, so it never leaves
    the machine via the repo. Nothing here is uploaded anywhere.
  - Voice audio and raw transcripts are NOT persisted to disk (Tier 3 keeps them in
    memory for the turn only) — only distilled durable facts land here.
  - Encryption at rest: rely on full-disk encryption (FileVault / BitLocker / LUKS)
    for v1; an app-level encrypted store is a later option. Do not store secrets here.
  - Backups: every write leaves a .bak beside the file; you are responsible for
    syncing the store off the one laptop (a spilled coffee shouldn't erase everything
    Nova has learned). See AGENT.md → retention/backup.
  - Live correction: "remember X", "no I meant Y", "forget that" edit this store in
    conversation via the memory tools — hand-editing the file is the emergency hatch,
    not the everyday path.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_DEFAULT_PATH = Path(__file__).resolve().parent / "store.json"


class MemoryStore:
    def __init__(self, path: str | os.PathLike | None = None):
        self.path = Path(path) if path else _DEFAULT_PATH
        self._facts: dict[str, dict[str, Any]] = {}
        self.load()

    # --- persistence ----------------------------------------------------------
    def load(self) -> dict[str, dict[str, Any]]:
        """(Re)load from disk. Called at construction, so a fresh process — i.e. a
        restart — picks up whatever is on disk, including hand edits."""
        if self.path.exists():
            raw = self.path.read_text(encoding="utf-8").strip()
            if not raw:
                self._facts = {}
            else:
                try:
                    data = json.loads(raw)
                    # Accept the human-editable shape: {key: "value"} OR {key: {value,...}}
                    self._facts = {
                        k: (v if isinstance(v, dict) else {"value": v})
                        for k, v in data.items()
                    }
                except json.JSONDecodeError:
                    # Don't crash on a corrupt/half-edited file; quarantine it and
                    # start empty so a typo never bricks the assistant.
                    self.path.replace(self.path.with_suffix(".json.corrupt"))
                    self._facts = {}
        else:
            self._facts = {}
        return self._facts

    def _save(self) -> None:
        """Atomic write + a .bak of the previous version (the off-file safety net)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            # keep the last-good copy before overwriting
            self.path.replace(self.path.with_suffix(".json.bak"))
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._facts, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # --- operations (one plain fact per entry) --------------------------------
    def remember(self, key: str, value: str) -> str:
        """Add or update a single fact. Upsert so 'no, I meant Y' just overwrites."""
        key = (key or "").strip()
        value = (value or "").strip()
        if not key:
            raise ValueError("fact key was empty")
        if not value:
            raise ValueError("fact value was empty")
        existed = key in self._facts
        self._facts[key] = {"value": value, "updated": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self._save()
        return f"{'Updated' if existed else 'Remembered'}: {key} — {value}"

    def forget(self, key: str) -> str:
        key = (key or "").strip()
        if key not in self._facts:
            raise KeyError(f"no fact called '{key}'")
        self._facts.pop(key)
        self._save()
        return f"Forgot: {key}"

    def get(self, key: str) -> str | None:
        entry = self._facts.get((key or "").strip())
        return entry["value"] if entry else None

    def all(self) -> dict[str, str]:
        return {k: v["value"] for k, v in self._facts.items()}

    # --- prompt rendering (the ONE place to get selective later) --------------
    def render_for_prompt(self, query: str | None = None, limit: int | None = None) -> str:
        """Turn facts into a compact block for the system prompt. `query`/`limit` are
        hooks for future selective recall; today it returns everything."""
        facts = self.all()
        if not facts:
            return ""
        items = list(facts.items())
        if limit is not None:
            items = items[:limit]
        return "\n".join(f"- {k}: {v}" for k, v in items)
