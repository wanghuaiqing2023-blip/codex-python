"""Log sink helpers ported from ``codex-state/src/log_db.rs``.

The Rust module is a ``tracing_subscriber`` layer backed by a Tokio task.  This
Python module keeps the same data-shaping contract with a small standard-library
queue facade: events become ``LogEntry`` values, span contexts contribute the
feedback-log body and thread id, accepted entries flush through ``insert_logs``.
"""

from __future__ import annotations

import inspect
import os
import time
import uuid
from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any, Protocol

from .model import LogEntry

LOG_QUEUE_CAPACITY = 512
LOG_BATCH_SIZE = 128
LOG_FLUSH_INTERVAL_SECONDS = 2.0

JsonValue = Any
FieldItems = Mapping[str, JsonValue] | Iterable[tuple[str, JsonValue]]

_PROCESS_LOG_UUID: str | None = None
_PROCESS_LOG_UUID_LOCK = Lock()


class LogInsertSink(Protocol):
    def insert_logs(self, entries: Sequence[LogEntry]) -> object:
        ...


@dataclass(frozen=True)
class LogSinkQueueConfig:
    queue_capacity: int = LOG_QUEUE_CAPACITY
    batch_size: int = LOG_BATCH_SIZE
    flush_interval: float = LOG_FLUSH_INTERVAL_SECONDS

    def normalized(self) -> "LogSinkQueueConfig":
        flush_interval = self.flush_interval
        if flush_interval == 0:
            flush_interval = LOG_FLUSH_INTERVAL_SECONDS
        if flush_interval < 0:
            raise ValueError("flush_interval must be non-negative")
        return LogSinkQueueConfig(
            queue_capacity=max(1, _usize(self.queue_capacity, "queue_capacity")),
            batch_size=max(1, _usize(self.batch_size, "batch_size")),
            flush_interval=flush_interval,
        )


@dataclass(frozen=True)
class SpanLogContext:
    name: str
    formatted_fields: str = ""
    thread_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("name must be a non-empty string")
        if not isinstance(self.formatted_fields, str):
            raise TypeError("formatted_fields must be a string")
        if self.thread_id is not None and not isinstance(self.thread_id, str):
            raise TypeError("thread_id must be a string or None")

    @classmethod
    def from_fields(cls, name: str, fields: FieldItems) -> "SpanLogContext":
        visitor = SpanFieldVisitor()
        visitor.record_fields(fields)
        return cls(name=name, formatted_fields=format_fields(fields), thread_id=visitor.thread_id)


@dataclass
class MessageVisitor:
    message: str | None = None
    thread_id: str | None = None

    def record_field(self, name: str, value: JsonValue) -> None:
        formatted = _field_value_to_string(value)
        if name == "message" and self.message is None:
            self.message = formatted
        if name == "thread_id" and self.thread_id is None:
            self.thread_id = formatted

    def record_fields(self, fields: FieldItems) -> None:
        for name, value in _field_items(fields):
            self.record_field(name, value)


@dataclass
class SpanFieldVisitor:
    thread_id: str | None = None

    def record_field(self, name: str, value: JsonValue) -> None:
        if name == "thread_id" and self.thread_id is None:
            self.thread_id = _field_value_to_string(value)

    def record_fields(self, fields: FieldItems) -> None:
        for name, value in _field_items(fields):
            self.record_field(name, value)


class LogDbLayer:
    """Bounded log sink compatible with Rust ``LogDbLayer`` call sites."""

    def __init__(
        self,
        state_db: LogInsertSink,
        config: LogSinkQueueConfig | None = None,
        *,
        process_uuid: str | None = None,
    ) -> None:
        self.state_db = state_db
        self.config = (config or LogSinkQueueConfig()).normalized()
        self.process_uuid = process_uuid or current_process_log_uuid()
        self._queue: deque[LogEntry] = deque()

    @classmethod
    def start(cls, state_db: LogInsertSink) -> "LogDbLayer":
        return cls(state_db)

    @classmethod
    def start_with_config(
        cls,
        state_db: LogInsertSink,
        config: LogSinkQueueConfig,
    ) -> "LogDbLayer":
        return cls(state_db, config)

    def try_send(self, entry: LogEntry) -> bool:
        if len(self._queue) >= self.config.queue_capacity:
            return False
        self._queue.append(entry)
        return True

    def emit_event(
        self,
        *,
        level: str,
        target: str,
        fields: FieldItems,
        span_contexts: Sequence[SpanLogContext] = (),
        module_path: str | None = None,
        file: str | None = None,
        line: int | None = None,
    ) -> bool:
        return self.try_send(
            log_entry_from_event(
                level=level,
                target=target,
                fields=fields,
                span_contexts=span_contexts,
                module_path=module_path,
                file=file,
                line=line,
                process_uuid=self.process_uuid,
            )
        )

    async def flush(self) -> None:
        if not self._queue:
            return
        entries = list(self._queue)
        self._queue.clear()
        result = self.state_db.insert_logs(entries)
        if inspect.isawaitable(result):
            await result


def start(state_db: LogInsertSink) -> LogDbLayer:
    return LogDbLayer.start(state_db)


def log_entry_from_event(
    *,
    level: str,
    target: str,
    fields: FieldItems,
    span_contexts: Sequence[SpanLogContext] = (),
    module_path: str | None = None,
    file: str | None = None,
    line: int | None = None,
    process_uuid: str | None = None,
    ts: int | None = None,
    ts_nanos: int | None = None,
) -> LogEntry:
    visitor = MessageVisitor()
    visitor.record_fields(fields)
    seconds, nanos = _event_timestamp(ts, ts_nanos)
    return LogEntry(
        ts=seconds,
        ts_nanos=nanos,
        level=_required_str(level, "level"),
        target=_required_str(target, "target"),
        message=visitor.message,
        feedback_log_body=format_feedback_log_body(fields, span_contexts),
        thread_id=visitor.thread_id or event_thread_id(span_contexts),
        process_uuid=process_uuid or current_process_log_uuid(),
        module_path=module_path,
        file=file,
        line=line,
    )


def event_thread_id(span_contexts: Sequence[SpanLogContext]) -> str | None:
    thread_id = None
    for context in span_contexts:
        if context.thread_id is not None:
            thread_id = context.thread_id
    return thread_id


def format_feedback_log_body(fields: FieldItems, span_contexts: Sequence[SpanLogContext] = ()) -> str:
    prefix = ""
    for context in span_contexts:
        prefix += context.name
        if context.formatted_fields:
            prefix += "{" + context.formatted_fields + "}"
        prefix += ":"
    formatted = format_fields(fields)
    if prefix:
        return f"{prefix} {formatted}"
    return formatted


def format_fields(fields: FieldItems) -> str:
    parts: list[str] = []
    for name, value in _field_items(fields):
        if name == "message":
            parts.append(_field_value_to_string(value))
        else:
            parts.append(f"{name}={_format_field_value(value)}")
    return " ".join(parts)


def append_fields(existing: str, values: FieldItems) -> str:
    if not isinstance(existing, str):
        raise TypeError("existing must be a string")
    extra = format_fields(values)
    if not existing:
        return extra
    if not extra:
        return existing
    return f"{existing} {extra}"


def current_process_log_uuid() -> str:
    global _PROCESS_LOG_UUID
    with _PROCESS_LOG_UUID_LOCK:
        if _PROCESS_LOG_UUID is None:
            _PROCESS_LOG_UUID = f"pid:{os.getpid()}:{uuid.uuid4()}"
        return _PROCESS_LOG_UUID


def _field_items(fields: FieldItems) -> list[tuple[str, JsonValue]]:
    if isinstance(fields, Mapping):
        items = list(fields.items())
    else:
        items = list(fields)
    result: list[tuple[str, JsonValue]] = []
    for name, value in items:
        result.append((_required_str(name, "field name"), value))
    return result


def _format_field_value(value: JsonValue) -> str:
    if isinstance(value, str):
        return repr(value)
    return _field_value_to_string(value)


def _field_value_to_string(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, BaseException):
        return str(value)
    return str(value)


def _event_timestamp(ts: int | None, ts_nanos: int | None) -> tuple[int, int]:
    if ts is not None:
        seconds = _i64(ts, "ts")
        nanos = 0 if ts_nanos is None else _i64(ts_nanos, "ts_nanos")
        return seconds, nanos
    now = time.time_ns()
    return now // 1_000_000_000, now % 1_000_000_000


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _i64(value: JsonValue, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")
    return value


def _usize(value: JsonValue, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


__all__ = [
    "LOG_BATCH_SIZE",
    "LOG_FLUSH_INTERVAL_SECONDS",
    "LOG_QUEUE_CAPACITY",
    "LogDbLayer",
    "LogInsertSink",
    "LogSinkQueueConfig",
    "MessageVisitor",
    "SpanFieldVisitor",
    "SpanLogContext",
    "append_fields",
    "current_process_log_uuid",
    "event_thread_id",
    "format_feedback_log_body",
    "format_fields",
    "log_entry_from_event",
    "start",
]
