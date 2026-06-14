"""Recent auto-review denial storage and action summaries.

Rust reference: codex-rs/tui/src/auto_review_denials.rs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import shlex
from typing import Any, Iterable, Iterator

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="auto_review_denials", source="codex/codex-rs/tui/src/auto_review_denials.rs")

MAX_RECENT_DENIALS = 10


class GuardianAssessmentStatus(str, Enum):
    DENIED = "Denied"
    APPROVED = "Approved"
    ALLOWED = "Allowed"
    PENDING = "Pending"


@dataclass(frozen=True)
class GuardianAssessmentEvent:
    id: str
    status: str | GuardianAssessmentStatus
    action: Any
    target_item_id: str | None = None
    turn_id: str = ""
    started_at_ms: int = 0
    completed_at_ms: int | None = None
    risk_level: Any = None
    user_authorization: Any = None
    rationale: str | None = None
    decision_source: Any = None


@dataclass(frozen=True)
class GuardianAssessmentAction:
    kind: str
    command: str | None = None
    program: str | None = None
    argv: tuple[str, ...] = ()
    files: tuple[str | Path, ...] = ()
    target: str | None = None
    server: str | None = None
    tool_name: str | None = None
    connector_name: str | None = None
    reason: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def command_action(cls, command: str) -> "GuardianAssessmentAction":
        return cls(kind="Command", command=command)

    @classmethod
    def execve(cls, program: str, argv: Iterable[str] = ()) -> "GuardianAssessmentAction":
        return cls(kind="Execve", program=program, argv=tuple(argv))

    @classmethod
    def apply_patch(cls, files: Iterable[str | Path]) -> "GuardianAssessmentAction":
        return cls(kind="ApplyPatch", files=tuple(files))

    @classmethod
    def network_access(cls, target: str) -> "GuardianAssessmentAction":
        return cls(kind="NetworkAccess", target=target)

    @classmethod
    def mcp_tool_call(cls, server: str, tool_name: str, connector_name: str | None = None) -> "GuardianAssessmentAction":
        return cls(kind="McpToolCall", server=server, tool_name=tool_name, connector_name=connector_name)

    @classmethod
    def request_permissions(cls, reason: str | None = None) -> "GuardianAssessmentAction":
        return cls(kind="RequestPermissions", reason=reason)


@dataclass
class RecentAutoReviewDenials:
    """Deque-backed port of Rust ``RecentAutoReviewDenials``."""

    _entries: deque[GuardianAssessmentEvent] = field(default_factory=deque)

    def push(self, event: GuardianAssessmentEvent | dict[str, Any] | Any) -> None:
        event = _coerce_event(event)
        if not _is_denied(event.status):
            return
        self._entries = deque(entry for entry in self._entries if entry.id != event.id)
        self._entries.appendleft(event)
        while len(self._entries) > MAX_RECENT_DENIALS:
            self._entries.pop()

    def is_empty(self) -> bool:
        return not self._entries

    def entries(self) -> Iterator[GuardianAssessmentEvent]:
        return iter(tuple(self._entries))

    def take(self, id: str) -> GuardianAssessmentEvent | None:
        for index, entry in enumerate(self._entries):
            if entry.id == id:
                del self._entries[index]
                return entry
        return None


def action_summary(action: GuardianAssessmentAction | dict[str, Any] | Any) -> str:
    action = _coerce_action(action)
    kind = action.kind
    if kind == "Command":
        return action.command or ""
    if kind == "Execve":
        command = list(action.argv) if action.argv else [action.program or ""]
        try:
            return shlex.join([str(part) for part in command])
        except Exception:
            return " ".join(str(part) for part in command)
    if kind == "ApplyPatch":
        files = list(action.files)
        if len(files) == 1:
            return f"apply_patch touching {files[0]}"
        return f"apply_patch touching {len(files)} files"
    if kind == "NetworkAccess":
        return f"network access to {action.target}"
    if kind == "McpToolCall":
        label = action.connector_name or action.server or ""
        return f"MCP {action.tool_name} on {label}"
    if kind == "RequestPermissions":
        if action.reason:
            return f"permission request: {action.reason}"
        return "permission request"
    return str(kind)


def denied_event(id: int | str) -> GuardianAssessmentEvent:
    """Rust-test-shaped helper for parity tests."""

    return GuardianAssessmentEvent(
        id=f"review-{id}",
        target_item_id=None,
        turn_id="turn-1",
        started_at_ms=0,
        completed_at_ms=1,
        status=GuardianAssessmentStatus.DENIED,
        rationale=f"rationale {id}",
        action=GuardianAssessmentAction.command_action(f"rm -rf /tmp/test-{id}"),
    )


def keeps_only_ten_most_recent_denials() -> list[str]:
    """Return the same id order asserted by Rust's unit test."""

    denials = RecentAutoReviewDenials()
    for id in range(12):
        denials.push(denied_event(id))
    return [entry.id for entry in denials.entries()]


def _is_denied(status: str | GuardianAssessmentStatus | Any) -> bool:
    if isinstance(status, GuardianAssessmentStatus):
        return status is GuardianAssessmentStatus.DENIED
    return str(status).split(".")[-1] == "Denied"


def _coerce_event(event: GuardianAssessmentEvent | dict[str, Any] | Any) -> GuardianAssessmentEvent:
    if isinstance(event, GuardianAssessmentEvent):
        return event
    if isinstance(event, dict):
        return GuardianAssessmentEvent(
            id=str(event.get("id", "")),
            status=event.get("status"),
            action=event.get("action"),
            target_item_id=event.get("target_item_id"),
            turn_id=str(event.get("turn_id", "")),
            started_at_ms=int(event.get("started_at_ms", 0)),
            completed_at_ms=event.get("completed_at_ms"),
            risk_level=event.get("risk_level"),
            user_authorization=event.get("user_authorization"),
            rationale=event.get("rationale"),
            decision_source=event.get("decision_source"),
        )
    return GuardianAssessmentEvent(id=str(getattr(event, "id")), status=getattr(event, "status"), action=getattr(event, "action"))


def _coerce_action(action: GuardianAssessmentAction | dict[str, Any] | Any) -> GuardianAssessmentAction:
    if isinstance(action, GuardianAssessmentAction):
        return action
    if isinstance(action, dict):
        kind = str(action.get("kind") or action.get("type") or action.get("variant") or "")
        return GuardianAssessmentAction(
            kind=kind,
            command=action.get("command"),
            program=action.get("program"),
            argv=tuple(action.get("argv") or ()),
            files=tuple(action.get("files") or ()),
            target=action.get("target"),
            server=action.get("server"),
            tool_name=action.get("tool_name"),
            connector_name=action.get("connector_name"),
            reason=action.get("reason"),
            extra={key: value for key, value in action.items() if key not in {"kind", "type", "variant", "command", "program", "argv", "files", "target", "server", "tool_name", "connector_name", "reason"}},
        )
    kind = str(getattr(action, "kind", getattr(action, "type", action.__class__.__name__)))
    return GuardianAssessmentAction(
        kind=kind,
        command=getattr(action, "command", None),
        program=getattr(action, "program", None),
        argv=tuple(getattr(action, "argv", ()) or ()),
        files=tuple(getattr(action, "files", ()) or ()),
        target=getattr(action, "target", None),
        server=getattr(action, "server", None),
        tool_name=getattr(action, "tool_name", None),
        connector_name=getattr(action, "connector_name", None),
        reason=getattr(action, "reason", None),
    )


__all__ = [
    "GuardianAssessmentAction",
    "GuardianAssessmentEvent",
    "GuardianAssessmentStatus",
    "MAX_RECENT_DENIALS",
    "RUST_MODULE",
    "RecentAutoReviewDenials",
    "action_summary",
    "denied_event",
    "keeps_only_ten_most_recent_denials",
]
