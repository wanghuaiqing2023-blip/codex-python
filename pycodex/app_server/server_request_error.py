"""Helpers ported from ``codex-app-server/src/server_request_error.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON = "turnTransition"


def is_turn_transition_server_request_error(error: Any) -> bool:
    """Return whether a JSON-RPC error carries Rust's turn-transition marker."""

    data = _field(error, "data")
    if not isinstance(data, Mapping):
        return False
    return data.get("reason") == TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


__all__ = [
    "TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON",
    "is_turn_transition_server_request_error",
]
