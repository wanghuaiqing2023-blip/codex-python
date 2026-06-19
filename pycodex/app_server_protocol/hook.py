"""Hook protocol types ported from ``protocol/v2/hook.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


class HookEventName(_StringEnum):
    PRE_TOOL_USE = "preToolUse"
    PERMISSION_REQUEST = "permissionRequest"
    POST_TOOL_USE = "postToolUse"
    PRE_COMPACT = "preCompact"
    POST_COMPACT = "postCompact"
    SESSION_START = "sessionStart"
    USER_PROMPT_SUBMIT = "userPromptSubmit"
    SUBAGENT_START = "subagentStart"
    SUBAGENT_STOP = "subagentStop"
    STOP = "stop"


class HookHandlerType(_StringEnum):
    COMMAND = "command"
    PROMPT = "prompt"
    AGENT = "agent"


class HookExecutionMode(_StringEnum):
    SYNC = "sync"
    ASYNC = "async"


class HookScope(_StringEnum):
    THREAD = "thread"
    TURN = "turn"


class HookSource(_StringEnum):
    SYSTEM = "system"
    USER = "user"
    PROJECT = "project"
    MDM = "mdm"
    SESSION_FLAGS = "sessionFlags"
    PLUGIN = "plugin"
    CLOUD_REQUIREMENTS = "cloudRequirements"
    LEGACY_MANAGED_CONFIG_FILE = "legacyManagedConfigFile"
    LEGACY_MANAGED_CONFIG_MDM = "legacyManagedConfigMdm"
    UNKNOWN = "unknown"


class HookTrustStatus(_StringEnum):
    MANAGED = "managed"
    UNTRUSTED = "untrusted"
    TRUSTED = "trusted"
    MODIFIED = "modified"


class HookRunStatus(_StringEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    STOPPED = "stopped"


class HookOutputEntryKind(_StringEnum):
    WARNING = "warning"
    STOP = "stop"
    FEEDBACK = "feedback"
    CONTEXT = "context"
    ERROR = "error"


@dataclass(frozen=True)
class HookOutputEntry:
    kind: HookOutputEntryKind | str
    text: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", HookOutputEntryKind.parse(self.kind))
        object.__setattr__(self, "text", _ensure_str(self.text, "text"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HookOutputEntry":
        _ensure_mapping(value, "HookOutputEntry")
        return cls(kind=HookOutputEntryKind.parse(value["kind"]), text=_ensure_str(value["text"], "text"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"kind": self.kind.value, "text": self.text}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class HookRunSummary:
    id: str
    event_name: HookEventName | str
    handler_type: HookHandlerType | str
    execution_mode: HookExecutionMode | str
    scope: HookScope | str
    source_path: Path | str
    display_order: int
    status: HookRunStatus | str
    started_at: int
    entries: tuple[HookOutputEntry, ...]
    source: HookSource | str = HookSource.UNKNOWN
    status_message: str | None = None
    completed_at: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "event_name", HookEventName.parse(self.event_name))
        object.__setattr__(self, "handler_type", HookHandlerType.parse(self.handler_type))
        object.__setattr__(self, "execution_mode", HookExecutionMode.parse(self.execution_mode))
        object.__setattr__(self, "scope", HookScope.parse(self.scope))
        object.__setattr__(self, "source_path", _absolute_path(self.source_path, "source_path"))
        object.__setattr__(self, "source", HookSource.parse(self.source))
        object.__setattr__(self, "display_order", _ensure_i64(self.display_order, "display_order"))
        object.__setattr__(self, "status", HookRunStatus.parse(self.status))
        object.__setattr__(self, "status_message", _optional_str(self.status_message, "status_message"))
        object.__setattr__(self, "started_at", _ensure_i64(self.started_at, "started_at"))
        object.__setattr__(self, "completed_at", _optional_i64(self.completed_at, "completed_at"))
        object.__setattr__(self, "duration_ms", _optional_i64(self.duration_ms, "duration_ms"))
        object.__setattr__(self, "entries", _entry_tuple(self.entries, "entries"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HookRunSummary":
        _ensure_mapping(value, "HookRunSummary")
        return cls(
            id=_ensure_str(value["id"], "id"),
            event_name=HookEventName.parse(_pick(value, "event_name", "eventName")),
            handler_type=HookHandlerType.parse(_pick(value, "handler_type", "handlerType")),
            execution_mode=HookExecutionMode.parse(_pick(value, "execution_mode", "executionMode")),
            scope=HookScope.parse(value["scope"]),
            source_path=_absolute_path(_pick(value, "source_path", "sourcePath"), "source_path"),
            source=HookSource.parse(_pick(value, "source", default=HookSource.UNKNOWN.value)),
            display_order=_ensure_i64(_pick(value, "display_order", "displayOrder"), "display_order"),
            status=HookRunStatus.parse(value["status"]),
            status_message=_optional_str(_pick(value, "status_message", "statusMessage"), "status_message"),
            started_at=_ensure_i64(_pick(value, "started_at", "startedAt"), "started_at"),
            completed_at=_optional_i64(_pick(value, "completed_at", "completedAt"), "completed_at"),
            duration_ms=_optional_i64(_pick(value, "duration_ms", "durationMs"), "duration_ms"),
            entries=_entry_tuple(value["entries"], "entries"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "event_name": self.event_name.value,
            "handler_type": self.handler_type.value,
            "execution_mode": self.execution_mode.value,
            "scope": self.scope.value,
            "source_path": str(self.source_path),
            "source": self.source.value,
            "display_order": self.display_order,
            "status": self.status.value,
            "status_message": self.status_message,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "entries": [entry.to_mapping() for entry in self.entries],
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "eventName": self.event_name.value,
            "handlerType": self.handler_type.value,
            "executionMode": self.execution_mode.value,
            "scope": self.scope.value,
            "sourcePath": str(self.source_path),
            "source": self.source.value,
            "displayOrder": self.display_order,
            "status": self.status.value,
            "statusMessage": self.status_message,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "durationMs": self.duration_ms,
            "entries": [entry.to_camel_mapping() for entry in self.entries],
        }


@dataclass(frozen=True)
class HookStartedNotification:
    thread_id: str
    turn_id: str | None
    run: HookRunSummary | Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _optional_str(self.turn_id, "turn_id"))
        object.__setattr__(self, "run", _run_summary(self.run, "run"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HookStartedNotification":
        _ensure_mapping(value, "HookStartedNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            turn_id=_optional_str(_pick(value, "turn_id", "turnId"), "turn_id"),
            run=_run_summary(value["run"], "run"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "turn_id": self.turn_id, "run": self.run.to_mapping()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "turnId": self.turn_id, "run": self.run.to_camel_mapping()}


@dataclass(frozen=True)
class HookCompletedNotification(HookStartedNotification):
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "HookCompletedNotification":
        _ensure_mapping(value, "HookCompletedNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            turn_id=_optional_str(_pick(value, "turn_id", "turnId"), "turn_id"),
            run=_run_summary(value["run"], "run"),
        )


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_i64(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < -(2**63) or value > 2**63 - 1:
        raise TypeError(f"{field_name} must be a signed 64-bit integer")
    return value


def _optional_i64(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    return _ensure_i64(value, field_name)


def _absolute_path(value: JsonValue, field_name: str) -> Path:
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str):
        path = Path(value)
    else:
        raise TypeError(f"{field_name} must be a path string or Path")
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return path


def _entry_tuple(value: JsonValue, field_name: str) -> tuple[HookOutputEntry, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable")
    result = []
    for item in value:
        if isinstance(item, HookOutputEntry):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(HookOutputEntry.from_mapping(item))
        else:
            raise TypeError(f"{field_name} item must be HookOutputEntry or mapping")
    return tuple(result)


def _run_summary(value: JsonValue, field_name: str) -> HookRunSummary:
    if isinstance(value, HookRunSummary):
        return value
    if isinstance(value, Mapping):
        return HookRunSummary.from_mapping(value)
    raise TypeError(f"{field_name} must be HookRunSummary or mapping")


__all__ = [
    "HookCompletedNotification",
    "HookEventName",
    "HookExecutionMode",
    "HookHandlerType",
    "HookOutputEntry",
    "HookOutputEntryKind",
    "HookRunStatus",
    "HookRunSummary",
    "HookScope",
    "HookSource",
    "HookStartedNotification",
    "HookTrustStatus",
]
