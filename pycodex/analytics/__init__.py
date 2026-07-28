"""Rust-aligned public interface for ``codex-analytics``."""

from __future__ import annotations

import time
from enum import Enum
from typing import Any

def now_unix_seconds() -> int:
    return int(time.time())

def now_unix_millis() -> int:
    return int(time.time() * 1000)

def _enum_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    return value

def _non_negative_int_or_none(value: int) -> int | None:
    return value if value >= 0 else None

def _json_value(value: Any) -> Any:
    value = _enum_value(value)
    if isinstance(value, dict):
        return {str(key): _json_value(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(inner) for inner in value]
    return value


from .accepted_lines import *
from .client import *
from .events import *
from .facts import *
from .reducer import *

__all__ = [name for name in globals() if not name.startswith("_")]
