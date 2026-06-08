"""Turn lifecycle contributor dispatch ported from ``codex-core::tasks::lifecycle``."""

from __future__ import annotations

import inspect
from collections.abc import Mapping
from typing import Any

from pycodex.extension_api import (
    TurnAbortInput,
    TurnErrorInput,
    TurnStartInput,
    TurnStopInput,
)


async def emit_turn_start_lifecycle(
    session: Any,
    turn_context: Any,
    token_usage_at_turn_start: Any,
) -> None:
    for contributor in _turn_lifecycle_contributors(session):
        await _call_contributor(
            contributor,
            "on_turn_start",
            TurnStartInput(
                {
                    "turn_id": _turn_id(turn_context),
                    "collaboration_mode": _field(turn_context, "collaboration_mode"),
                    "token_usage_at_turn_start": token_usage_at_turn_start,
                    **_store_fields(session, _turn_store(turn_context)),
                }
            ),
        )


async def emit_turn_stop_lifecycle(session: Any, turn_store: Any) -> None:
    for contributor in _turn_lifecycle_contributors(session):
        await _call_contributor(
            contributor,
            "on_turn_stop",
            TurnStopInput(_store_fields(session, turn_store)),
        )


async def emit_turn_abort_lifecycle(session: Any, reason: Any, turn_store: Any) -> None:
    for contributor in _turn_lifecycle_contributors(session):
        await _call_contributor(
            contributor,
            "on_turn_abort",
            TurnAbortInput({"reason": reason, **_store_fields(session, turn_store)}),
        )


async def emit_turn_error_lifecycle(session: Any, turn_context: Any, error: Any) -> None:
    for contributor in _turn_lifecycle_contributors(session):
        await _call_contributor(
            contributor,
            "on_turn_error",
            TurnErrorInput(
                {
                    "turn_id": _turn_id(turn_context),
                    "error": error,
                    **_store_fields(session, _turn_store(turn_context)),
                }
            ),
        )


def _turn_lifecycle_contributors(session: Any) -> tuple[Any, ...]:
    services = _field(session, "services")
    extensions = _field(services, "extensions")
    getter = _field(extensions, "turn_lifecycle_contributors")
    if not callable(getter):
        return ()
    contributors = getter()
    if contributors is None:
        return ()
    if isinstance(contributors, (str, bytes)):
        raise TypeError("turn_lifecycle_contributors must return an iterable")
    return tuple(contributors)


async def _call_contributor(contributor: Any, method_name: str, value: Any) -> None:
    callback = _field(contributor, method_name)
    if not callable(callback):
        return
    result = callback(value)
    if inspect.isawaitable(result):
        await result


def _store_fields(session: Any, turn_store: Any) -> dict[str, Any]:
    services = _field(session, "services")
    return {
        "session_store": _field(services, "session_extension_data"),
        "thread_store": _field(services, "thread_extension_data"),
        "turn_store": turn_store,
    }


def _turn_id(turn_context: Any) -> str:
    raw = _field(turn_context, "sub_id")
    if raw is None:
        raw = _field(turn_context, "turn_id")
    return str(raw)


def _turn_store(turn_context: Any) -> Any:
    extension_data = _field(turn_context, "extension_data")
    as_ref = _field(extension_data, "as_ref")
    return as_ref() if callable(as_ref) else extension_data


def _field(value: Any, name: str) -> Any:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)


__all__ = [
    "emit_turn_abort_lifecycle",
    "emit_turn_error_lifecycle",
    "emit_turn_start_lifecycle",
    "emit_turn_stop_lifecycle",
]
