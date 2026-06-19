"""Log model types ported from ``codex-state/src/model/log.rs``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class LogEntry:
    ts: int
    ts_nanos: int
    level: str
    target: str
    message: str | None = None
    feedback_log_body: str | None = None
    thread_id: str | None = None
    process_uuid: str | None = None
    module_path: str | None = None
    file: str | None = None
    line: int | None = None

    def __post_init__(self) -> None:
        _ensure_i64(self.ts, "ts")
        _ensure_i64(self.ts_nanos, "ts_nanos")
        object.__setattr__(self, "level", _required_str(self.level, "level"))
        object.__setattr__(self, "target", _required_str(self.target, "target"))
        object.__setattr__(self, "message", _optional_str(self.message, "message"))
        object.__setattr__(self, "feedback_log_body", _optional_str(self.feedback_log_body, "feedback_log_body"))
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "process_uuid", _optional_str(self.process_uuid, "process_uuid"))
        object.__setattr__(self, "module_path", _optional_str(self.module_path, "module_path"))
        object.__setattr__(self, "file", _optional_str(self.file, "file"))
        if self.line is not None:
            _ensure_i64(self.line, "line")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "ts": self.ts,
            "ts_nanos": self.ts_nanos,
            "level": self.level,
            "target": self.target,
            "message": self.message,
            "feedback_log_body": self.feedback_log_body,
            "thread_id": self.thread_id,
            "process_uuid": self.process_uuid,
            "module_path": self.module_path,
            "file": self.file,
            "line": self.line,
        }


@dataclass(frozen=True)
class LogRow:
    id: int
    ts: int
    ts_nanos: int
    level: str
    target: str
    message: str | None = None
    thread_id: str | None = None
    process_uuid: str | None = None
    file: str | None = None
    line: int | None = None

    def __post_init__(self) -> None:
        _ensure_i64(self.id, "id")
        _ensure_i64(self.ts, "ts")
        _ensure_i64(self.ts_nanos, "ts_nanos")
        object.__setattr__(self, "level", _required_str(self.level, "level"))
        object.__setattr__(self, "target", _required_str(self.target, "target"))
        object.__setattr__(self, "message", _optional_str(self.message, "message"))
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "process_uuid", _optional_str(self.process_uuid, "process_uuid"))
        object.__setattr__(self, "file", _optional_str(self.file, "file"))
        if self.line is not None:
            _ensure_i64(self.line, "line")

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "LogRow":
        return cls(
            id=_required_i64(value.get("id"), "id"),
            ts=_required_i64(value.get("ts"), "ts"),
            ts_nanos=_required_i64(value.get("ts_nanos"), "ts_nanos"),
            level=_required_str(value.get("level"), "level"),
            target=_required_str(value.get("target"), "target"),
            message=_optional_str(value.get("message"), "message"),
            thread_id=_optional_str(value.get("thread_id"), "thread_id"),
            process_uuid=_optional_str(value.get("process_uuid"), "process_uuid"),
            file=_optional_str(value.get("file"), "file"),
            line=_optional_i64(value.get("line"), "line"),
        )


@dataclass(frozen=True)
class LogQuery:
    levels_upper: tuple[str, ...] = field(default_factory=tuple)
    from_ts: int | None = None
    to_ts: int | None = None
    module_like: tuple[str, ...] = field(default_factory=tuple)
    file_like: tuple[str, ...] = field(default_factory=tuple)
    thread_ids: tuple[str, ...] = field(default_factory=tuple)
    search: str | None = None
    include_threadless: bool = False
    after_id: int | None = None
    limit: int | None = None
    descending: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "levels_upper", _string_tuple(self.levels_upper, "levels_upper"))
        object.__setattr__(self, "from_ts", _optional_i64(self.from_ts, "from_ts"))
        object.__setattr__(self, "to_ts", _optional_i64(self.to_ts, "to_ts"))
        object.__setattr__(self, "module_like", _string_tuple(self.module_like, "module_like"))
        object.__setattr__(self, "file_like", _string_tuple(self.file_like, "file_like"))
        object.__setattr__(self, "thread_ids", _string_tuple(self.thread_ids, "thread_ids"))
        object.__setattr__(self, "search", _optional_str(self.search, "search"))
        if not isinstance(self.include_threadless, bool):
            raise TypeError("include_threadless must be a bool")
        object.__setattr__(self, "after_id", _optional_i64(self.after_id, "after_id"))
        if self.limit is not None:
            _ensure_usize(self.limit, "limit")
        if not isinstance(self.descending, bool):
            raise TypeError("descending must be a bool")


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _required_str(value, name)


def _required_i64(value: JsonValue, name: str) -> int:
    _ensure_i64(value, name)
    return value


def _optional_i64(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    return _required_i64(value, name)


def _string_tuple(value: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence of strings")
    return tuple(_required_str(item, f"{name} item") for item in value)


def _ensure_i64(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _ensure_usize(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


__all__ = ["LogEntry", "LogQuery", "LogRow"]
