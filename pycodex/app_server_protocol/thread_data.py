"""Thread data protocol types ported from ``protocol/v2/thread_data.rs``."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, fields
from enum import Enum
from pathlib import Path
from typing import Any

from .item import ThreadItem

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

    def to_mapping(self) -> str:
        return self.value


class ThreadSource(_StringEnum):
    USER = "user"
    SUBAGENT = "subagent"
    MEMORY_CONSOLIDATION = "memory_consolidation"


class TurnItemsView(_StringEnum):
    NOT_LOADED = "notLoaded"
    SUMMARY = "summary"
    FULL = "full"


@dataclass(frozen=True)
class SessionSource:
    variant: str = "vscode"
    value: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "variant", _ensure_str(self.variant, "variant"))
        if self.variant not in {"cli", "vscode", "exec", "appServer", "custom", "subAgent", "unknown"}:
            raise ValueError(f"unknown session source: {self.variant}")
        if self.variant == "custom":
            object.__setattr__(self, "value", _ensure_str(self.value, "custom source"))

    @classmethod
    def cli(cls) -> "SessionSource":
        return cls("cli")

    @classmethod
    def vscode(cls) -> "SessionSource":
        return cls("vscode")

    @classmethod
    def exec(cls) -> "SessionSource":
        return cls("exec")

    @classmethod
    def app_server(cls) -> "SessionSource":
        return cls("appServer")

    @classmethod
    def custom(cls, source: str) -> "SessionSource":
        return cls("custom", source)

    @classmethod
    def sub_agent(cls, source: JsonValue) -> "SessionSource":
        return cls("subAgent", copy.deepcopy(source))

    @classmethod
    def unknown(cls) -> "SessionSource":
        return cls("unknown")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SessionSource":
        if isinstance(value, SessionSource):
            return value
        if isinstance(value, str):
            if value == "mcp":
                return cls.app_server()
            if value == "VSCode":
                return cls.vscode()
            return cls(value)
        if isinstance(value, Mapping):
            if len(value) != 1:
                raise TypeError("SessionSource mapping must contain exactly one variant")
            variant, payload = next(iter(value.items()))
            if variant == "custom":
                return cls.custom(_ensure_str(payload, "custom"))
            if variant == "subAgent":
                return cls.sub_agent(payload)
            return cls(_ensure_str(variant, "variant"), copy.deepcopy(payload))
        raise TypeError("SessionSource must be a string or single-variant mapping")

    def to_mapping(self) -> JsonValue:
        if self.variant in {"custom", "subAgent"}:
            return {self.variant: copy.deepcopy(self.value)}
        return self.variant

    def to_core(self) -> JsonValue:
        if self.variant == "appServer":
            return "mcp"
        return self.to_mapping()


@dataclass(frozen=True)
class GitInfo:
    sha: str | None = None
    branch: str | None = None
    origin_url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "sha", _optional_str(self.sha, "sha"))
        object.__setattr__(self, "branch", _optional_str(self.branch, "branch"))
        object.__setattr__(self, "origin_url", _optional_str(self.origin_url, "origin_url"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GitInfo":
        data = _mapping(value, "GitInfo")
        return cls(
            sha=_optional_str(data.get("sha"), "sha"),
            branch=_optional_str(data.get("branch"), "branch"),
            origin_url=_optional_str(_pick(data, "origin_url", "originUrl"), "origin_url"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class Thread:
    id: str
    session_id: str
    forked_from_id: str | None
    preview: str
    ephemeral: bool
    model_provider: str
    created_at: int
    updated_at: int
    status: JsonValue
    path: Path | str | None
    cwd: Path | str
    cli_version: str
    source: SessionSource | JsonValue = None  # type: ignore[assignment]
    thread_source: ThreadSource | str | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    git_info: GitInfo | Mapping[str, JsonValue] | None = None
    name: str | None = None
    turns: tuple["Turn", ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "session_id", _ensure_str(self.session_id, "session_id"))
        object.__setattr__(self, "forked_from_id", _optional_str(self.forked_from_id, "forked_from_id"))
        object.__setattr__(self, "preview", _ensure_str(self.preview, "preview"))
        object.__setattr__(self, "ephemeral", _ensure_bool(self.ephemeral, "ephemeral"))
        object.__setattr__(self, "model_provider", _ensure_str(self.model_provider, "model_provider"))
        object.__setattr__(self, "created_at", _i64(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _i64(self.updated_at, "updated_at"))
        object.__setattr__(self, "path", _optional_path_str(self.path, "path"))
        object.__setattr__(self, "cwd", _path_str(self.cwd, "cwd"))
        object.__setattr__(self, "cli_version", _ensure_str(self.cli_version, "cli_version"))
        object.__setattr__(self, "source", SessionSource.from_mapping(self.source) if self.source is not None else SessionSource.vscode())
        object.__setattr__(self, "thread_source", ThreadSource.parse(self.thread_source) if self.thread_source is not None else None)
        object.__setattr__(self, "agent_nickname", _optional_str(self.agent_nickname, "agent_nickname"))
        object.__setattr__(self, "agent_role", _optional_str(self.agent_role, "agent_role"))
        object.__setattr__(self, "git_info", _git_info(self.git_info) if self.git_info is not None else None)
        object.__setattr__(self, "name", _optional_str(self.name, "name"))
        object.__setattr__(self, "turns", tuple(_turn(turn) for turn in self.turns))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Thread":
        data = _mapping(value, "Thread")
        return cls(
            id=_ensure_str(data["id"], "id"),
            session_id=_ensure_str(_pick(data, "session_id", "sessionId"), "session_id"),
            forked_from_id=_optional_str(_pick(data, "forked_from_id", "forkedFromId"), "forked_from_id"),
            preview=_ensure_str(data["preview"], "preview"),
            ephemeral=_ensure_bool(data["ephemeral"], "ephemeral"),
            model_provider=_ensure_str(_pick(data, "model_provider", "modelProvider"), "model_provider"),
            created_at=_i64(_pick(data, "created_at", "createdAt"), "created_at"),
            updated_at=_i64(_pick(data, "updated_at", "updatedAt"), "updated_at"),
            status=copy.deepcopy(data["status"]),
            path=_pick(data, "path"),
            cwd=_pick(data, "cwd"),
            cli_version=_ensure_str(_pick(data, "cli_version", "cliVersion"), "cli_version"),
            source=SessionSource.from_mapping(data.get("source", "vscode")),
            thread_source=_pick(data, "thread_source", "threadSource"),
            agent_nickname=_optional_str(_pick(data, "agent_nickname", "agentNickname"), "agent_nickname"),
            agent_role=_optional_str(_pick(data, "agent_role", "agentRole"), "agent_role"),
            git_info=GitInfo.from_mapping(_pick(data, "git_info", "gitInfo")) if _pick(data, "git_info", "gitInfo") is not None else None,
            name=_optional_str(data.get("name"), "name"),
            turns=tuple(Turn.from_mapping(item) for item in _list(data.get("turns", []), "turns")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class Turn:
    id: str
    items: tuple[ThreadItem, ...]
    status: JsonValue
    items_view: TurnItemsView | str = TurnItemsView.FULL
    error: "TurnError | Mapping[str, JsonValue] | None" = None
    started_at: int | None = None
    completed_at: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _ensure_str(self.id, "id"))
        object.__setattr__(self, "items", tuple(_thread_item(item) for item in self.items))
        object.__setattr__(self, "items_view", TurnItemsView.parse(self.items_view))
        object.__setattr__(self, "error", _turn_error(self.error) if self.error is not None else None)
        object.__setattr__(self, "started_at", _optional_i64(self.started_at, "started_at"))
        object.__setattr__(self, "completed_at", _optional_i64(self.completed_at, "completed_at"))
        object.__setattr__(self, "duration_ms", _optional_i64(self.duration_ms, "duration_ms"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Turn":
        data = _mapping(value, "Turn")
        return cls(
            id=_ensure_str(data["id"], "id"),
            items=tuple(ThreadItem.from_mapping(item) for item in _list(data.get("items", []), "items")),
            items_view=TurnItemsView.parse(_pick(data, "items_view", "itemsView", default="full")),
            status=copy.deepcopy(data["status"]),
            error=TurnError.from_mapping(data["error"]) if data.get("error") is not None else None,
            started_at=_optional_i64(_pick(data, "started_at", "startedAt"), "started_at"),
            completed_at=_optional_i64(_pick(data, "completed_at", "completedAt"), "completed_at"),
            duration_ms=_optional_i64(_pick(data, "duration_ms", "durationMs"), "duration_ms"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


@dataclass(frozen=True)
class TurnError(Exception):
    message: str
    codex_error_info: JsonValue | None = None
    additional_details: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))
        object.__setattr__(self, "additional_details", _optional_str(self.additional_details, "additional_details"))

    def __str__(self) -> str:
        return self.message

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnError":
        data = _mapping(value, "TurnError")
        return cls(
            message=_ensure_str(data["message"], "message"),
            codex_error_info=copy.deepcopy(_pick(data, "codex_error_info", "codexErrorInfo")),
            additional_details=_optional_str(_pick(data, "additional_details", "additionalDetails"), "additional_details"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return _to_mapping(self)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _to_camel_mapping(self)


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


def _i64(value: JsonValue, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < -(2**63) or value > 2**63 - 1:
        raise TypeError(f"{field_name} must be a signed 64-bit integer")
    return value


def _optional_i64(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    return _i64(value, field_name)


def _list(value: JsonValue, field_name: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _path_str(value: Path | str, field_name: str) -> str:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    raise TypeError(f"{field_name} must be a path string")


def _optional_path_str(value: Path | str | None, field_name: str) -> str | None:
    if value is None:
        return None
    return _path_str(value, field_name)


def _git_info(value: GitInfo | Mapping[str, JsonValue]) -> GitInfo:
    if isinstance(value, GitInfo):
        return value
    return GitInfo.from_mapping(value)


def _thread_item(value: ThreadItem | Mapping[str, JsonValue]) -> ThreadItem:
    if isinstance(value, ThreadItem):
        return value
    return ThreadItem.from_mapping(value)


def _turn(value: Turn | Mapping[str, JsonValue]) -> Turn:
    if isinstance(value, Turn):
        return value
    return Turn.from_mapping(value)


def _turn_error(value: TurnError | Mapping[str, JsonValue]) -> TurnError:
    if isinstance(value, TurnError):
        return value
    return TurnError.from_mapping(value)


def _serialize(value: JsonValue) -> JsonValue:
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


def _to_mapping(value: JsonValue) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for field in fields(value):
        result[field.name] = _serialize(getattr(value, field.name))
    return result


def _to_camel_mapping(value: JsonValue) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for field in fields(value):
        key = field.name
        item = getattr(value, key)
        if key == "source" and isinstance(item, SessionSource):
            result[key] = item.to_mapping()
        else:
            result[_snake_to_camel(key)] = _serialize_camel(item)
    return result


def _serialize_camel(value: JsonValue) -> JsonValue:
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


__all__ = [
    "GitInfo",
    "SessionSource",
    "Thread",
    "ThreadSource",
    "Turn",
    "TurnError",
    "TurnItemsView",
]
