"""Agent job model types ported from ``codex-state/src/model/agent_job.rs``."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

JsonValue = Any


class AgentJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

    def as_str(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: str) -> "AgentJobStatus":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"invalid agent job status: {value}") from exc

    def is_final(self) -> bool:
        return self in {self.COMPLETED, self.FAILED, self.CANCELLED}


class AgentJobItemStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    def as_str(self) -> str:
        return self.value

    @classmethod
    def parse(cls, value: str) -> "AgentJobItemStatus":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"invalid agent job item status: {value}") from exc


@dataclass(frozen=True)
class AgentJob:
    id: str
    name: str
    status: AgentJobStatus
    instruction: str
    auto_export: bool
    max_runtime_seconds: int | None
    output_schema_json: JsonValue | None
    input_headers: tuple[str, ...]
    input_csv_path: str
    output_csv_path: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_str(self.id, "id"))
        object.__setattr__(self, "name", _required_str(self.name, "name"))
        if not isinstance(self.status, AgentJobStatus):
            object.__setattr__(self, "status", AgentJobStatus.parse(str(self.status)))
        object.__setattr__(self, "instruction", _required_str(self.instruction, "instruction"))
        if not isinstance(self.auto_export, bool):
            raise TypeError("auto_export must be a bool")
        object.__setattr__(self, "max_runtime_seconds", _optional_u64(self.max_runtime_seconds, "max_runtime_seconds"))
        object.__setattr__(self, "input_headers", _string_tuple(self.input_headers, "input_headers"))
        object.__setattr__(self, "input_csv_path", _required_str(self.input_csv_path, "input_csv_path"))
        object.__setattr__(self, "output_csv_path", _required_str(self.output_csv_path, "output_csv_path"))
        object.__setattr__(self, "created_at", _datetime_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _datetime_utc(self.updated_at, "updated_at"))
        object.__setattr__(self, "started_at", _optional_datetime_utc(self.started_at, "started_at"))
        object.__setattr__(self, "completed_at", _optional_datetime_utc(self.completed_at, "completed_at"))
        object.__setattr__(self, "last_error", _optional_str(self.last_error, "last_error"))


@dataclass(frozen=True)
class AgentJobItem:
    job_id: str
    item_id: str
    row_index: int
    source_id: str | None
    row_json: JsonValue
    status: AgentJobItemStatus
    assigned_thread_id: str | None
    attempt_count: int
    result_json: JsonValue | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    reported_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "job_id", _required_str(self.job_id, "job_id"))
        object.__setattr__(self, "item_id", _required_str(self.item_id, "item_id"))
        _ensure_i64(self.row_index, "row_index")
        object.__setattr__(self, "source_id", _optional_str(self.source_id, "source_id"))
        if not isinstance(self.status, AgentJobItemStatus):
            object.__setattr__(self, "status", AgentJobItemStatus.parse(str(self.status)))
        object.__setattr__(self, "assigned_thread_id", _optional_str(self.assigned_thread_id, "assigned_thread_id"))
        _ensure_i64(self.attempt_count, "attempt_count")
        object.__setattr__(self, "last_error", _optional_str(self.last_error, "last_error"))
        object.__setattr__(self, "created_at", _datetime_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _datetime_utc(self.updated_at, "updated_at"))
        object.__setattr__(self, "completed_at", _optional_datetime_utc(self.completed_at, "completed_at"))
        object.__setattr__(self, "reported_at", _optional_datetime_utc(self.reported_at, "reported_at"))


@dataclass(frozen=True)
class AgentJobProgress:
    total_items: int
    pending_items: int
    running_items: int
    completed_items: int
    failed_items: int

    def __post_init__(self) -> None:
        for name in ("total_items", "pending_items", "running_items", "completed_items", "failed_items"):
            _ensure_usize(getattr(self, name), name)


@dataclass(frozen=True)
class AgentJobCreateParams:
    id: str
    name: str
    instruction: str
    auto_export: bool
    max_runtime_seconds: int | None
    output_schema_json: JsonValue | None
    input_headers: tuple[str, ...]
    input_csv_path: str
    output_csv_path: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_str(self.id, "id"))
        object.__setattr__(self, "name", _required_str(self.name, "name"))
        object.__setattr__(self, "instruction", _required_str(self.instruction, "instruction"))
        if not isinstance(self.auto_export, bool):
            raise TypeError("auto_export must be a bool")
        object.__setattr__(self, "max_runtime_seconds", _optional_u64(self.max_runtime_seconds, "max_runtime_seconds"))
        object.__setattr__(self, "input_headers", _string_tuple(self.input_headers, "input_headers"))
        object.__setattr__(self, "input_csv_path", _required_str(self.input_csv_path, "input_csv_path"))
        object.__setattr__(self, "output_csv_path", _required_str(self.output_csv_path, "output_csv_path"))


@dataclass(frozen=True)
class AgentJobItemCreateParams:
    item_id: str
    row_index: int
    source_id: str | None
    row_json: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "item_id", _required_str(self.item_id, "item_id"))
        _ensure_i64(self.row_index, "row_index")
        object.__setattr__(self, "source_id", _optional_str(self.source_id, "source_id"))


@dataclass(frozen=True)
class AgentJobRow:
    id: str
    name: str
    status: str
    instruction: str
    auto_export: int
    max_runtime_seconds: int | None
    output_schema_json: str | None
    input_headers_json: str
    input_csv_path: str
    output_csv_path: str
    created_at: int
    updated_at: int
    started_at: int | None = None
    completed_at: int | None = None
    last_error: str | None = None

    def to_agent_job(self) -> AgentJob:
        max_runtime_seconds = _optional_u64_from_i64(self.max_runtime_seconds, "max_runtime_seconds")
        return AgentJob(
            id=self.id,
            name=self.name,
            status=AgentJobStatus.parse(self.status),
            instruction=self.instruction,
            auto_export=self.auto_export != 0,
            max_runtime_seconds=max_runtime_seconds,
            output_schema_json=json.loads(self.output_schema_json) if self.output_schema_json is not None else None,
            input_headers=tuple(json.loads(self.input_headers_json)),
            input_csv_path=self.input_csv_path,
            output_csv_path=self.output_csv_path,
            created_at=epoch_seconds_to_datetime(self.created_at),
            updated_at=epoch_seconds_to_datetime(self.updated_at),
            started_at=epoch_seconds_to_datetime(self.started_at) if self.started_at is not None else None,
            completed_at=epoch_seconds_to_datetime(self.completed_at) if self.completed_at is not None else None,
            last_error=self.last_error,
        )


@dataclass(frozen=True)
class AgentJobItemRow:
    job_id: str
    item_id: str
    row_index: int
    source_id: str | None
    row_json: str
    status: str
    assigned_thread_id: str | None
    attempt_count: int
    result_json: str | None
    last_error: str | None
    created_at: int
    updated_at: int
    completed_at: int | None = None
    reported_at: int | None = None

    def to_agent_job_item(self) -> AgentJobItem:
        return AgentJobItem(
            job_id=self.job_id,
            item_id=self.item_id,
            row_index=self.row_index,
            source_id=self.source_id,
            row_json=json.loads(self.row_json),
            status=AgentJobItemStatus.parse(self.status),
            assigned_thread_id=self.assigned_thread_id,
            attempt_count=self.attempt_count,
            result_json=json.loads(self.result_json) if self.result_json is not None else None,
            last_error=self.last_error,
            created_at=epoch_seconds_to_datetime(self.created_at),
            updated_at=epoch_seconds_to_datetime(self.updated_at),
            completed_at=epoch_seconds_to_datetime(self.completed_at) if self.completed_at is not None else None,
            reported_at=epoch_seconds_to_datetime(self.reported_at) if self.reported_at is not None else None,
        )


def epoch_seconds_to_datetime(secs: int) -> datetime:
    if isinstance(secs, bool) or not isinstance(secs, int):
        raise TypeError("secs must be an integer")
    try:
        return datetime.fromtimestamp(secs, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"invalid unix timestamp: {secs}") from exc


def _datetime_utc(value: JsonValue, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _optional_datetime_utc(value: JsonValue, name: str) -> datetime | None:
    if value is None:
        return None
    return _datetime_utc(value, name)


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _required_str(value, name)


def _string_tuple(value: Sequence[str], name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{name} must be a sequence of strings")
    return tuple(_required_str(item, f"{name} item") for item in value)


def _ensure_i64(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _ensure_u64(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0 or value > 2**64 - 1:
        raise ValueError(f"{name} must fit in an unsigned 64-bit integer")


def _ensure_usize(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def _optional_u64(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    _ensure_u64(value, name)
    return value


def _optional_u64_from_i64(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    _ensure_i64(value, name)
    if value < 0:
        raise ValueError("invalid max_runtime_seconds value")
    return value


__all__ = [
    "AgentJob",
    "AgentJobCreateParams",
    "AgentJobItem",
    "AgentJobItemCreateParams",
    "AgentJobItemRow",
    "AgentJobItemStatus",
    "AgentJobProgress",
    "AgentJobRow",
    "AgentJobStatus",
    "epoch_seconds_to_datetime",
]
