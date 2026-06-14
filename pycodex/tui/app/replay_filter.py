"""Replay filtering helpers for buffered thread events.

Rust reference: codex-rs/tui/src/app/replay_filter.rs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="app::replay_filter", source="codex/codex-rs/tui/src/app/replay_filter.rs")

PENDING_INTERACTIVE_REQUEST_KINDS = {
    "CommandExecutionRequestApproval",
    "FileChangeRequestApproval",
    "McpServerElicitationRequest",
    "PermissionsRequestApproval",
    "ToolRequestUserInput",
}

NOTICE_NOTIFICATION_KINDS = {
    "Warning",
    "GuardianWarning",
    "ConfigWarning",
}


@dataclass(frozen=True)
class ThreadBufferedEvent:
    kind: str
    payload: Any = None

    @classmethod
    def request(cls, request: Any) -> "ThreadBufferedEvent":
        return cls("Request", request)

    @classmethod
    def notification(cls, notification: Any) -> "ThreadBufferedEvent":
        return cls("Notification", notification)


@dataclass(frozen=True)
class ThreadEventSnapshot:
    events: list[Any] = field(default_factory=list)


def snapshot_has_pending_interactive_request(snapshot: ThreadEventSnapshot | dict[str, Any] | Any) -> bool:
    return any(_event_is_pending_interactive_request(event) for event in _snapshot_events(snapshot))


def event_is_notice(event: ThreadBufferedEvent | dict[str, Any] | Any) -> bool:
    event = _coerce_event(event)
    return event.kind == "Notification" and _variant_name(event.payload) in NOTICE_NOTIFICATION_KINDS


def _event_is_pending_interactive_request(event: ThreadBufferedEvent | dict[str, Any] | Any) -> bool:
    event = _coerce_event(event)
    return event.kind == "Request" and _variant_name(event.payload) in PENDING_INTERACTIVE_REQUEST_KINDS


def _snapshot_events(snapshot: ThreadEventSnapshot | dict[str, Any] | Any) -> Iterable[Any]:
    if isinstance(snapshot, ThreadEventSnapshot):
        return snapshot.events
    if isinstance(snapshot, dict):
        return snapshot.get("events", [])
    return getattr(snapshot, "events", [])


def _coerce_event(event: ThreadBufferedEvent | dict[str, Any] | Any) -> ThreadBufferedEvent:
    if isinstance(event, ThreadBufferedEvent):
        return event
    if isinstance(event, dict):
        kind = str(event.get("kind") or event.get("type") or "")
        payload = event.get("payload", event.get("request", event.get("notification")))
        return ThreadBufferedEvent(kind, payload)
    kind = str(getattr(event, "kind", getattr(event, "type", event.__class__.__name__)))
    payload = getattr(event, "payload", getattr(event, "request", getattr(event, "notification", None)))
    return ThreadBufferedEvent(kind, payload)


def _variant_name(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("kind") or value.get("type") or value.get("variant") or "")
    return str(getattr(value, "kind", getattr(value, "type", getattr(value, "variant", value.__class__.__name__))))


__all__ = [
    "NOTICE_NOTIFICATION_KINDS",
    "PENDING_INTERACTIVE_REQUEST_KINDS",
    "RUST_MODULE",
    "ThreadBufferedEvent",
    "ThreadEventSnapshot",
    "event_is_notice",
    "snapshot_has_pending_interactive_request",
]
