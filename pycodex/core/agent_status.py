"""Agent status helpers ported from ``core/src/agent/status.rs``."""

from __future__ import annotations

from typing import Any

from pycodex.protocol import (
    AgentStatus,
    ErrorEvent,
    EventMsg,
    TurnAbortReason,
    TurnAbortedEvent,
    TurnCompleteEvent,
)


def agent_status_from_event(msg: EventMsg | dict[str, Any]) -> AgentStatus | None:
    """Derive the next tracked agent status from a single event."""

    event = EventMsg.from_mapping(msg) if isinstance(msg, dict) else msg
    event_type = event.type
    payload = event.payload

    if event_type in {"task_started", "turn_started"}:
        return AgentStatus.running()
    if event_type in {"task_complete", "turn_complete"}:
        return AgentStatus.completed(_last_agent_message(payload))
    if event_type == "turn_aborted":
        reason = _turn_abort_reason(payload)
        if reason in {TurnAbortReason.INTERRUPTED, TurnAbortReason.BUDGET_LIMITED}:
            return AgentStatus.interrupted()
        return AgentStatus.errored(_debug_turn_abort_reason(reason))
    if event_type == "error":
        return AgentStatus.errored(_event_error_message(payload))
    if event_type == "shutdown_complete":
        return AgentStatus.shutdown()
    return None


def agent_status_is_final(status: AgentStatus | str | dict[str, Any]) -> bool:
    """Return whether an agent status is terminal."""

    parsed_status = AgentStatus.from_mapping(status)
    return parsed_status.type not in {"pending_init", "running", "interrupted"}


def is_final(status: AgentStatus | str | dict[str, Any]) -> bool:
    """Alias matching the upstream helper name."""

    return agent_status_is_final(status)


def _last_agent_message(payload: Any) -> str | None:
    if isinstance(payload, TurnCompleteEvent):
        return payload.last_agent_message
    if isinstance(payload, dict):
        value = payload.get("last_agent_message")
        return value if isinstance(value, str) else None
    return getattr(payload, "last_agent_message", None)


def _turn_abort_reason(payload: Any) -> TurnAbortReason:
    if isinstance(payload, TurnAbortedEvent):
        return payload.reason
    if isinstance(payload, dict):
        return TurnAbortReason(str(payload.get("reason")))
    reason = getattr(payload, "reason", payload)
    if isinstance(reason, TurnAbortReason):
        return reason
    return TurnAbortReason(str(reason))


def _debug_turn_abort_reason(reason: TurnAbortReason) -> str:
    return "".join(part.title() for part in reason.value.split("_"))


def _event_error_message(payload: Any) -> str:
    if isinstance(payload, ErrorEvent):
        return payload.message
    if isinstance(payload, dict):
        value = payload.get("message")
        return value if isinstance(value, str) else ""
    value = getattr(payload, "message", "")
    return value if isinstance(value, str) else ""


__all__ = [
    "agent_status_from_event",
    "agent_status_is_final",
    "is_final",
]
