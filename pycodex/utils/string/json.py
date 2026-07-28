"""ASCII-safe JSON serialization from ``codex-utils-string::json``."""

from __future__ import annotations

import json
from typing import Any


def to_ascii_json_string(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


__all__ = ["to_ascii_json_string"]
