"""Turn lifecycle inputs owned by the Rust extension API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..state import ExtensionData


@dataclass(frozen=True)
class TurnStartInput:
    turn_id: str
    collaboration_mode: Any
    token_usage_at_turn_start: Any
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


@dataclass(frozen=True)
class TurnStopInput:
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


@dataclass(frozen=True)
class TurnAbortInput:
    reason: Any
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


@dataclass(frozen=True)
class TurnErrorInput:
    turn_id: str
    error: Any
    session_store: ExtensionData
    thread_store: ExtensionData
    turn_store: ExtensionData


__all__ = ["TurnAbortInput", "TurnErrorInput", "TurnStartInput", "TurnStopInput"]
