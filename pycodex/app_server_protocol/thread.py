"""Thread API protocol types ported from ``protocol/v2/thread.rs``.

This module mirrors the app-server thread RPC payload layer. It intentionally
does not implement thread storage, session management, or rollout runtime
behavior.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from enum import Enum
from pathlib import Path
from typing import Any

from .item import ThreadItem
from .thread_data import Thread
from .thread_data import ThreadSource
from .thread_data import Turn
from .thread_data import TurnItemsView
from .turn import TurnEnvironmentParams
from .turn import UNSET

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


class ThreadStartSource(_StringEnum):
    STARTUP = "startup"
    CLEAR = "clear"


class ThreadUnsubscribeStatus(_StringEnum):
    NOT_LOADED = "notLoaded"
    NOT_SUBSCRIBED = "notSubscribed"
    UNSUBSCRIBED = "unsubscribed"


class ThreadGoalStatus(_StringEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    USAGE_LIMITED = "usageLimited"
    BUDGET_LIMITED = "budgetLimited"
    COMPLETE = "complete"


class ThreadMemoryMode(_StringEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"

    def as_str(self) -> str:
        return self.value

    def to_core(self) -> str:
        return self.value


class ThreadSourceKind(_StringEnum):
    CLI = "cli"
    VSCODE = "vscode"
    EXEC = "exec"
    APP_SERVER = "appServer"
    SUB_AGENT = "subAgent"
    SUB_AGENT_REVIEW = "subAgentReview"
    SUB_AGENT_COMPACT = "subAgentCompact"
    SUB_AGENT_THREAD_SPAWN = "subAgentThreadSpawn"
    SUB_AGENT_OTHER = "subAgentOther"
    UNKNOWN = "unknown"


class ThreadSortKey(_StringEnum):
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


class SortDirection(_StringEnum):
    ASC = "asc"
    DESC = "desc"


class ThreadActiveFlag(_StringEnum):
    WAITING_ON_APPROVAL = "waitingOnApproval"
    WAITING_ON_USER_INPUT = "waitingOnUserInput"


class ThreadListCwdFilter:
    def __init__(self, value: str | Iterable[str]):
        if isinstance(value, str):
            self.value: str | tuple[str, ...] = value
        elif isinstance(value, Iterable):
            self.value = tuple(_ensure_str(item, "cwd") for item in value)
        else:
            raise TypeError("ThreadListCwdFilter must be a string or iterable of strings")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ThreadListCwdFilter":
        return cls(value)

    def to_mapping(self) -> JsonValue:
        if isinstance(self.value, tuple):
            return list(self.value)
        return self.value


class ThreadStatus:
    def __init__(self, type: str, active_flags: Iterable[ThreadActiveFlag | str] | None = None):
        self.type = _ensure_str(type, "type")
        if self.type == "active":
            self.active_flags = tuple(ThreadActiveFlag.parse(flag) for flag in (active_flags or ()))
        else:
            self.active_flags = tuple()
        if self.type not in {"notLoaded", "idle", "systemError", "active"}:
            raise ValueError(f"unknown ThreadStatus type: {self.type}")

    @classmethod
    def not_loaded(cls) -> "ThreadStatus":
        return cls("notLoaded")

    @classmethod
    def idle(cls) -> "ThreadStatus":
        return cls("idle")

    @classmethod
    def system_error(cls) -> "ThreadStatus":
        return cls("systemError")

    @classmethod
    def active(cls, active_flags: Iterable[ThreadActiveFlag | str] = ()) -> "ThreadStatus":
        return cls("active", active_flags)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | str) -> "ThreadStatus":
        if isinstance(value, str):
            return cls(value)
        data = _mapping(value, "ThreadStatus")
        return cls(_ensure_str(data["type"], "type"), _pick(data, "active_flags", "activeFlags", default=()))

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "active":
            result["active_flags"] = [flag.value for flag in self.active_flags]
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {"type": self.type}
        if self.type == "active":
            result["activeFlags"] = [flag.value for flag in self.active_flags]
        return result


class _Record:
    _omit_false: frozenset[str] = frozenset()
    _double_option: frozenset[str] = frozenset()
    _coercers: dict[str, Any] = {}

    def __init__(self, **fields: JsonValue):
        normalized: dict[str, JsonValue] = {}
        for key, value in fields.items():
            snake = _camel_to_snake(key)
            if snake in self._coercers and value is not UNSET:
                value = self._coercers[snake](value)
            normalized[snake] = value
        self._fields = normalized

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]):
        data = _mapping(value, cls.__name__)
        return cls(**{_camel_to_snake(key): copy.deepcopy(item) for key, item in data.items()})

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            key: _serialize(value)
            for key, value in self._fields.items()
            if not (value is UNSET or (key in self._omit_false and value is False))
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            _snake_to_camel(key): _serialize_camel(value)
            for key, value in self._fields.items()
            if not (value is UNSET or (key in self._omit_false and value is False))
        }

    def __getattr__(self, name: str) -> JsonValue:
        try:
            return self._fields[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __eq__(self, other: object) -> bool:
        return isinstance(other, self.__class__) and self._fields == other._fields

    def __repr__(self) -> str:
        args = ", ".join(f"{key}={value!r}" for key, value in self._fields.items())
        return f"{self.__class__.__name__}({args})"


def _record_class(name: str, *, omit_false: Iterable[str] = (), coercers: Mapping[str, Any] | None = None):
    return type(
        name,
        (_Record,),
        {
            "_omit_false": frozenset(omit_false),
            "_coercers": dict(coercers or {}),
            "__module__": __name__,
        },
    )


def _empty_record_class(name: str):
    class Empty(_Record):
        def __init__(self, **fields: JsonValue):
            if fields:
                super().__init__(**fields)
            else:
                super().__init__()

        @classmethod
        def from_mapping(cls, value: Mapping[str, JsonValue] | None = None):
            if value is not None:
                _mapping(value, name)
            return cls()

    Empty.__name__ = name
    Empty.__qualname__ = name
    Empty.__module__ = __name__
    return Empty


def _thread(value: JsonValue) -> Thread:
    if isinstance(value, Thread):
        return value
    return Thread.from_mapping(value)


def _turn(value: JsonValue) -> Turn:
    if isinstance(value, Turn):
        return value
    return Turn.from_mapping(value)


def _thread_item(value: JsonValue) -> ThreadItem:
    if isinstance(value, ThreadItem):
        return value
    return ThreadItem.from_mapping(value)


def _thread_source(value: JsonValue) -> ThreadSource:
    if isinstance(value, ThreadSource):
        return value
    return ThreadSource.parse(value)


def _turn_environment(value: JsonValue) -> TurnEnvironmentParams:
    if isinstance(value, TurnEnvironmentParams):
        return value
    return TurnEnvironmentParams.from_mapping(value)


def _dynamic_tool_spec_field(value: JsonValue) -> JsonValue:
    return copy.deepcopy(value)


def _thread_status(value: JsonValue) -> ThreadStatus:
    if isinstance(value, ThreadStatus):
        return value
    return ThreadStatus.from_mapping(value)


def _thread_goal(value: JsonValue) -> "ThreadGoal":
    if isinstance(value, ThreadGoal):
        return value
    return ThreadGoal.from_mapping(value)


def _token_usage(value: JsonValue) -> "ThreadTokenUsage":
    if isinstance(value, ThreadTokenUsage):
        return value
    return ThreadTokenUsage.from_mapping(value)


def _token_usage_breakdown(value: JsonValue) -> "TokenUsageBreakdown":
    if isinstance(value, TokenUsageBreakdown):
        return value
    return TokenUsageBreakdown.from_mapping(value)


class DynamicToolSpec(_Record):
    _omit_false = frozenset({"defer_loading"})

    def __init__(
        self,
        namespace: str | None = None,
        name: str | None = None,
        description: str | None = None,
        input_schema: JsonValue = None,
        defer_loading: bool | None = None,
        expose_to_context: bool | None = None,
        **extra: JsonValue,
    ):
        if defer_loading is None:
            defer_loading = (not expose_to_context) if expose_to_context is not None else False
        super().__init__(
            namespace=_optional_str(namespace, "namespace"),
            name=_ensure_str(name, "name"),
            description=_ensure_str(description, "description"),
            input_schema=copy.deepcopy(input_schema),
            defer_loading=_ensure_bool(defer_loading, "defer_loading"),
            **extra,
        )


ThreadStartParams = _record_class(
    "ThreadStartParams",
    omit_false=("experimental_raw_events", "persist_extended_history"),
    coercers={
        "session_start_source": ThreadStartSource.parse,
        "thread_source": _thread_source,
        "environments": lambda v: tuple(_turn_environment(item) for item in v) if v is not None else None,
        "dynamic_tools": lambda v: tuple(DynamicToolSpec.from_mapping(item) if isinstance(item, Mapping) else item for item in v) if v is not None else None,
    },
)
MockExperimentalMethodParams = _record_class("MockExperimentalMethodParams")
MockExperimentalMethodResponse = _record_class("MockExperimentalMethodResponse")
ThreadStartResponse = _record_class("ThreadStartResponse", coercers={"thread": _thread})

ThreadSettingsUpdateParams = _record_class("ThreadSettingsUpdateParams")
ThreadSettingsUpdateResponse = _empty_record_class("ThreadSettingsUpdateResponse")
ThreadSettings = _record_class("ThreadSettings")
ThreadSettingsUpdatedNotification = _record_class("ThreadSettingsUpdatedNotification")

ThreadResumeParams = _record_class("ThreadResumeParams", omit_false=("exclude_turns", "persist_extended_history"))
ThreadResumeResponse = _record_class("ThreadResumeResponse", coercers={"thread": _thread})
ThreadForkParams = _record_class("ThreadForkParams", omit_false=("ephemeral", "exclude_turns", "persist_extended_history"))
ThreadForkResponse = _record_class("ThreadForkResponse", coercers={"thread": _thread})

ThreadArchiveParams = _record_class("ThreadArchiveParams")
ThreadArchiveResponse = _empty_record_class("ThreadArchiveResponse")
ThreadUnsubscribeParams = _record_class("ThreadUnsubscribeParams")
ThreadUnsubscribeResponse = _record_class("ThreadUnsubscribeResponse", coercers={"status": ThreadUnsubscribeStatus.parse})
ThreadIncrementElicitationParams = _record_class("ThreadIncrementElicitationParams")
ThreadIncrementElicitationResponse = _record_class("ThreadIncrementElicitationResponse")
ThreadDecrementElicitationParams = _record_class("ThreadDecrementElicitationParams")
ThreadDecrementElicitationResponse = _record_class("ThreadDecrementElicitationResponse")
ThreadSetNameParams = _record_class("ThreadSetNameParams")
ThreadSetNameResponse = _empty_record_class("ThreadSetNameResponse")
ThreadUnarchiveParams = _record_class("ThreadUnarchiveParams")
ThreadUnarchiveResponse = _record_class("ThreadUnarchiveResponse", coercers={"thread": _thread})

ThreadGoal = _record_class("ThreadGoal", coercers={"status": ThreadGoalStatus.parse})
ThreadGoalSetParams = _record_class("ThreadGoalSetParams", coercers={"status": lambda v: ThreadGoalStatus.parse(v) if v is not None else None})
ThreadGoalSetResponse = _record_class("ThreadGoalSetResponse", coercers={"goal": _thread_goal})
ThreadGoalGetParams = _record_class("ThreadGoalGetParams")
ThreadGoalGetResponse = _record_class("ThreadGoalGetResponse", coercers={"goal": lambda v: _thread_goal(v) if v is not None else None})
ThreadGoalClearParams = _record_class("ThreadGoalClearParams")
ThreadGoalClearResponse = _record_class("ThreadGoalClearResponse")
ThreadMetadataGitInfoUpdateParams = _record_class("ThreadMetadataGitInfoUpdateParams")
ThreadMetadataUpdateParams = _record_class("ThreadMetadataUpdateParams")
ThreadMetadataUpdateResponse = _record_class("ThreadMetadataUpdateResponse", coercers={"thread": _thread})

ThreadMemoryModeSetParams = _record_class("ThreadMemoryModeSetParams", coercers={"mode": ThreadMemoryMode.parse})
ThreadMemoryModeSetResponse = _empty_record_class("ThreadMemoryModeSetResponse")
MemoryResetResponse = _empty_record_class("MemoryResetResponse")

ThreadCompactStartParams = _record_class("ThreadCompactStartParams")
ThreadCompactStartResponse = _empty_record_class("ThreadCompactStartResponse")
ThreadShellCommandParams = _record_class("ThreadShellCommandParams")
ThreadShellCommandResponse = _empty_record_class("ThreadShellCommandResponse")
ThreadApproveGuardianDeniedActionParams = _record_class("ThreadApproveGuardianDeniedActionParams")
ThreadApproveGuardianDeniedActionResponse = _empty_record_class("ThreadApproveGuardianDeniedActionResponse")
ThreadBackgroundTerminalsCleanParams = _record_class("ThreadBackgroundTerminalsCleanParams")
ThreadBackgroundTerminalsCleanResponse = _empty_record_class("ThreadBackgroundTerminalsCleanResponse")
ThreadRollbackParams = _record_class("ThreadRollbackParams")
ThreadRollbackResponse = _record_class("ThreadRollbackResponse", coercers={"thread": _thread})

ThreadListParams = _record_class(
    "ThreadListParams",
    omit_false=("use_state_db_only",),
    coercers={
        "sort_key": lambda v: ThreadSortKey.parse(v) if v is not None else None,
        "sort_direction": lambda v: SortDirection.parse(v) if v is not None else None,
        "source_kinds": lambda v: tuple(ThreadSourceKind.parse(item) for item in v) if v is not None else None,
        "cwd": lambda v: ThreadListCwdFilter(v) if v is not None else None,
    },
)
ThreadSearchParams = _record_class(
    "ThreadSearchParams",
    coercers={
        "sort_key": lambda v: ThreadSortKey.parse(v) if v is not None else None,
        "sort_direction": lambda v: SortDirection.parse(v) if v is not None else None,
        "source_kinds": lambda v: tuple(ThreadSourceKind.parse(item) for item in v) if v is not None else None,
    },
)
ThreadListResponse = _record_class("ThreadListResponse", coercers={"data": lambda v: tuple(_thread(item) for item in v)})
ThreadSearchResult = _record_class("ThreadSearchResult", coercers={"thread": _thread})
ThreadSearchResponse = _record_class("ThreadSearchResponse", coercers={"data": lambda v: tuple(ThreadSearchResult.from_mapping(item) if isinstance(item, Mapping) else item for item in v)})
ThreadLoadedListParams = _record_class("ThreadLoadedListParams")
ThreadLoadedListResponse = _record_class("ThreadLoadedListResponse")
ThreadReadParams = _record_class("ThreadReadParams", omit_false=("include_turns",))
ThreadReadResponse = _record_class("ThreadReadResponse", coercers={"thread": _thread})
ThreadInjectItemsParams = _record_class("ThreadInjectItemsParams")
ThreadInjectItemsResponse = _empty_record_class("ThreadInjectItemsResponse")
ThreadTurnsListParams = _record_class(
    "ThreadTurnsListParams",
    coercers={
        "sort_direction": lambda v: SortDirection.parse(v) if v is not None else None,
        "items_view": lambda v: TurnItemsView.parse(v) if v is not None else None,
    },
)
ThreadTurnsListResponse = _record_class("ThreadTurnsListResponse", coercers={"data": lambda v: tuple(_turn(item) for item in v)})
ThreadTurnsItemsListParams = _record_class("ThreadTurnsItemsListParams", coercers={"sort_direction": lambda v: SortDirection.parse(v) if v is not None else None})
ThreadTurnsItemsListResponse = _record_class("ThreadTurnsItemsListResponse", coercers={"data": lambda v: tuple(_thread_item(item) for item in v)})

TokenUsageBreakdown = _record_class("TokenUsageBreakdown")
ThreadTokenUsage = _record_class(
    "ThreadTokenUsage",
    coercers={"total": _token_usage_breakdown, "last": _token_usage_breakdown},
)
ThreadTokenUsageUpdatedNotification = _record_class("ThreadTokenUsageUpdatedNotification", coercers={"token_usage": _token_usage})

ThreadStartedNotification = _record_class("ThreadStartedNotification", coercers={"thread": _thread})
ThreadStatusChangedNotification = _record_class("ThreadStatusChangedNotification", coercers={"status": _thread_status})
ThreadArchivedNotification = _record_class("ThreadArchivedNotification")
ThreadUnarchivedNotification = _record_class("ThreadUnarchivedNotification")
ThreadClosedNotification = _record_class("ThreadClosedNotification")
ThreadNameUpdatedNotification = _record_class("ThreadNameUpdatedNotification")
ThreadGoalUpdatedNotification = _record_class("ThreadGoalUpdatedNotification", coercers={"goal": _thread_goal})
ThreadGoalClearedNotification = _record_class("ThreadGoalClearedNotification")
ContextCompactedNotification = _record_class("ContextCompactedNotification")


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _pick(data: Mapping[str, JsonValue], *keys: str, default: JsonValue = None) -> JsonValue:
    for key in keys:
        if key in data:
            return data[key]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _serialize(value: JsonValue) -> JsonValue:
    if value is UNSET:
        return UNSET
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _serialize_camel(value: JsonValue) -> JsonValue:
    if value is UNSET:
        return UNSET
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, tuple):
        return [_serialize_camel(item) for item in value]
    if isinstance(value, list):
        return [_serialize_camel(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_camel(item) for key, item in value.items()}
    return copy.deepcopy(value)


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _camel_to_snake(value: str) -> str:
    result: list[str] = []
    for char in value:
        if char.isupper():
            result.append("_")
            result.append(char.lower())
        else:
            result.append(char)
    return "".join(result).lstrip("_")


__all__ = [
    "ContextCompactedNotification",
    "DynamicToolSpec",
    "MemoryResetResponse",
    "MockExperimentalMethodParams",
    "MockExperimentalMethodResponse",
    "SortDirection",
    "ThreadActiveFlag",
    "ThreadApproveGuardianDeniedActionParams",
    "ThreadApproveGuardianDeniedActionResponse",
    "ThreadArchiveParams",
    "ThreadArchiveResponse",
    "ThreadArchivedNotification",
    "ThreadBackgroundTerminalsCleanParams",
    "ThreadBackgroundTerminalsCleanResponse",
    "ThreadClosedNotification",
    "ThreadCompactStartParams",
    "ThreadCompactStartResponse",
    "ThreadDecrementElicitationParams",
    "ThreadDecrementElicitationResponse",
    "ThreadForkParams",
    "ThreadForkResponse",
    "ThreadGoal",
    "ThreadGoalClearParams",
    "ThreadGoalClearResponse",
    "ThreadGoalClearedNotification",
    "ThreadGoalGetParams",
    "ThreadGoalGetResponse",
    "ThreadGoalSetParams",
    "ThreadGoalSetResponse",
    "ThreadGoalStatus",
    "ThreadGoalUpdatedNotification",
    "ThreadIncrementElicitationParams",
    "ThreadIncrementElicitationResponse",
    "ThreadInjectItemsParams",
    "ThreadInjectItemsResponse",
    "ThreadListCwdFilter",
    "ThreadListParams",
    "ThreadListResponse",
    "ThreadLoadedListParams",
    "ThreadLoadedListResponse",
    "ThreadMemoryMode",
    "ThreadMemoryModeSetParams",
    "ThreadMemoryModeSetResponse",
    "ThreadMetadataGitInfoUpdateParams",
    "ThreadMetadataUpdateParams",
    "ThreadMetadataUpdateResponse",
    "ThreadNameUpdatedNotification",
    "ThreadReadParams",
    "ThreadReadResponse",
    "ThreadResumeParams",
    "ThreadResumeResponse",
    "ThreadRollbackParams",
    "ThreadRollbackResponse",
    "ThreadSearchParams",
    "ThreadSearchResponse",
    "ThreadSearchResult",
    "ThreadSetNameParams",
    "ThreadSetNameResponse",
    "ThreadSettings",
    "ThreadSettingsUpdateParams",
    "ThreadSettingsUpdateResponse",
    "ThreadSettingsUpdatedNotification",
    "ThreadShellCommandParams",
    "ThreadShellCommandResponse",
    "ThreadSortKey",
    "ThreadSourceKind",
    "ThreadStartParams",
    "ThreadStartResponse",
    "ThreadStartSource",
    "ThreadStartedNotification",
    "ThreadStatus",
    "ThreadStatusChangedNotification",
    "ThreadTokenUsage",
    "ThreadTokenUsageUpdatedNotification",
    "ThreadTurnsItemsListParams",
    "ThreadTurnsItemsListResponse",
    "ThreadTurnsListParams",
    "ThreadTurnsListResponse",
    "ThreadUnarchiveParams",
    "ThreadUnarchiveResponse",
    "ThreadUnarchivedNotification",
    "ThreadUnsubscribeParams",
    "ThreadUnsubscribeResponse",
    "ThreadUnsubscribeStatus",
    "TokenUsageBreakdown",
]
