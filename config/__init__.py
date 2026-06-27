"""Config loader. Reads config/config.toml once and exposes it as a dict.

Nothing else in Nova hardcodes thresholds, intervals, model names, or which tools
are consequential — they all come from here. (config over hardcoding)
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

_CONFIG_PATH = Path(__file__).resolve().parent / "config.toml"
_cache: dict[str, Any] | None = None


def load(path: Path | None = None) -> dict[str, Any]:
    """Load (and cache) the config. Pass a path to override (used in tests)."""
    global _cache
    if path is not None:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    if _cache is None:
        with open(_CONFIG_PATH, "rb") as fh:
            _cache = tomllib.load(fh)
    return _cache


def get(*keys: str, default: Any = None) -> Any:
    """Dotted-path getter: get('model', 'primary')."""
    node: Any = load()
    for key in keys:
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return node
