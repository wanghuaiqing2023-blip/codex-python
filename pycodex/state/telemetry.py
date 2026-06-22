"""SQLite telemetry helpers ported from ``codex-state/src/telemetry.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from threading import Lock
from typing import Any, Protocol, runtime_checkable

from . import DB_FALLBACK_METRIC, DB_INIT_DURATION_METRIC, DB_INIT_METRIC

Tag = tuple[str, str]


@runtime_checkable
class DbTelemetry(Protocol):
    def counter(self, name: str, inc: int, tags: tuple[Tag, ...]) -> None: ...

    def record_duration(self, name: str, duration: timedelta, tags: tuple[Tag, ...]) -> None: ...


DbTelemetryHandle = DbTelemetry


_PROCESS_DB_TELEMETRY: DbTelemetryHandle | None = None
_PROCESS_DB_TELEMETRY_LOCK = Lock()


def install_process_db_telemetry(telemetry: DbTelemetryHandle) -> bool:
    global _PROCESS_DB_TELEMETRY
    if not isinstance(telemetry, DbTelemetry):
        raise TypeError("telemetry must implement DbTelemetry")
    with _PROCESS_DB_TELEMETRY_LOCK:
        if _PROCESS_DB_TELEMETRY is not None:
            return False
        _PROCESS_DB_TELEMETRY = telemetry
        return True


class DbKind(str, Enum):
    STATE = "state"
    LOGS = "logs"
    GOALS = "goals"
    MEMORIES = "memories"

    def as_str(self) -> str:
        return self.value


@dataclass(frozen=True)
class DbOutcomeTags:
    status: str
    error: str

    @classmethod
    def from_result(cls, result: Any) -> "DbOutcomeTags":
        if result is None or result is True:
            return cls(status="success", error="none")
        if isinstance(result, BaseException):
            return cls(status="failed", error=classify_error(result))
        return cls(status="success", error="none")


def record_init_result(
    telemetry: DbTelemetry | None,
    db: DbKind,
    phase: str,
    duration: timedelta | float | int,
    result: Any,
) -> None:
    if not isinstance(db, DbKind):
        db = DbKind(str(db))
    outcome = DbOutcomeTags.from_result(result)
    tags: tuple[Tag, ...] = (
        ("status", outcome.status),
        ("phase", phase),
        ("db", db.as_str()),
        ("error", outcome.error),
    )
    record_counter(telemetry, DB_INIT_METRIC, tags)
    record_duration(telemetry, DB_INIT_DURATION_METRIC, _duration(duration), tags)


def record_backfill_gate(telemetry: DbTelemetry | None, duration: timedelta | float | int, result: Any) -> None:
    record_init_result(telemetry, DbKind.STATE, "backfill_gate", duration, result)


def record_fallback(caller: str, reason: str, telemetry_override: DbTelemetry | None = None) -> None:
    record_counter(telemetry_override, DB_FALLBACK_METRIC, (("caller", caller), ("reason", reason)))


def record_counter(telemetry: DbTelemetry | None, name: str, tags: tuple[Tag, ...]) -> None:
    sink = resolve_telemetry(telemetry)
    if sink is not None:
        sink.counter(name, 1, tags)


def record_duration(
    telemetry: DbTelemetry | None,
    name: str,
    duration: timedelta,
    tags: tuple[Tag, ...],
) -> None:
    sink = resolve_telemetry(telemetry)
    if sink is not None:
        sink.record_duration(name, duration, tags)


def resolve_telemetry(telemetry: DbTelemetry | None) -> DbTelemetry | None:
    return telemetry if telemetry is not None else _PROCESS_DB_TELEMETRY


def classify_error(err: BaseException) -> str:
    for cause in _exception_chain(err):
        if _is_json_error(cause):
            return "serde"
        if isinstance(cause, OSError):
            return "io"
        code = _sqlite_code(cause)
        if code is not None:
            return classify_sqlite_code(str(code))
        name = cause.__class__.__name__.lower()
        module = cause.__class__.__module__.lower()
        if "migrate" in name or "migrate" in module:
            return "migration"
        if "pooltimedout" in name or "pool_timeout" in name:
            return "pool_timeout"
    return "unknown"


def classify_sqlite_code(code: str) -> str:
    try:
        primary_code = int(code) & 0xFF
    except ValueError:
        return "unknown"
    return {
        5: "busy",
        6: "locked",
        8: "readonly",
        10: "io",
        11: "corrupt",
        13: "full",
        14: "cantopen",
        17: "schema",
        19: "constraint",
    }.get(primary_code, "unknown")


def _duration(value: timedelta | float | int) -> timedelta:
    if isinstance(value, timedelta):
        return value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("duration must be a timedelta or seconds value")
    return timedelta(seconds=value)


def _exception_chain(err: BaseException) -> tuple[BaseException, ...]:
    causes: list[BaseException] = []
    current: BaseException | None = err
    while current is not None and current not in causes:
        causes.append(current)
        current = current.__cause__ or current.__context__
    return tuple(causes)


def _is_json_error(err: BaseException) -> bool:
    import json

    return isinstance(err, json.JSONDecodeError)


def _sqlite_code(err: BaseException) -> int | str | None:
    for attr in ("sqlite_errorcode", "code"):
        value = getattr(err, attr, None)
        if value is not None:
            return value
    return None


__all__ = [
    "DbKind",
    "DbOutcomeTags",
    "DbTelemetry",
    "DbTelemetryHandle",
    "classify_error",
    "classify_sqlite_code",
    "install_process_db_telemetry",
    "record_backfill_gate",
    "record_counter",
    "record_duration",
    "record_fallback",
    "record_init_result",
    "resolve_telemetry",
]
