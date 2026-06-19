"""Thread goal model types ported from ``codex-state/src/model/thread_goal.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pycodex.protocol import ThreadId

JsonValue = Any


class ThreadGoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    USAGE_LIMITED = "usage_limited"
    BUDGET_LIMITED = "budget_limited"
    COMPLETE = "complete"

    def as_str(self) -> str:
        return self.value

    def is_active(self) -> bool:
        return self is ThreadGoalStatus.ACTIVE

    def is_terminal(self) -> bool:
        return self in (ThreadGoalStatus.BUDGET_LIMITED, ThreadGoalStatus.COMPLETE)

    @classmethod
    def parse(cls, value: str) -> "ThreadGoalStatus":
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"unknown thread goal status `{value}`") from exc


@dataclass(frozen=True)
class ThreadGoal:
    thread_id: ThreadId
    goal_id: str
    objective: str
    status: ThreadGoalStatus
    token_budget: int | None
    tokens_used: int
    time_used_seconds: int
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.thread_id, ThreadId):
            raise TypeError("thread_id must be a ThreadId")
        object.__setattr__(self, "goal_id", _required_str(self.goal_id, "goal_id"))
        object.__setattr__(self, "objective", _required_str(self.objective, "objective"))
        if not isinstance(self.status, ThreadGoalStatus):
            object.__setattr__(self, "status", ThreadGoalStatus.parse(str(self.status)))
        object.__setattr__(self, "token_budget", _optional_i64(self.token_budget, "token_budget"))
        _ensure_i64(self.tokens_used, "tokens_used")
        _ensure_i64(self.time_used_seconds, "time_used_seconds")
        object.__setattr__(self, "created_at", _datetime_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _datetime_utc(self.updated_at, "updated_at"))


@dataclass(frozen=True)
class ThreadGoalRow:
    thread_id: str
    goal_id: str
    objective: str
    status: str
    token_budget: int | None
    tokens_used: int
    time_used_seconds: int
    created_at_ms: int
    updated_at_ms: int

    @classmethod
    def from_mapping(cls, row: Mapping[str, JsonValue]) -> "ThreadGoalRow":
        return cls(
            thread_id=_required_str(row.get("thread_id"), "thread_id"),
            goal_id=_required_str(row.get("goal_id"), "goal_id"),
            objective=_required_str(row.get("objective"), "objective"),
            status=_required_str(row.get("status"), "status"),
            token_budget=_optional_i64(row.get("token_budget"), "token_budget"),
            tokens_used=_required_i64(row.get("tokens_used"), "tokens_used"),
            time_used_seconds=_required_i64(row.get("time_used_seconds"), "time_used_seconds"),
            created_at_ms=_required_i64(row.get("created_at_ms"), "created_at_ms"),
            updated_at_ms=_required_i64(row.get("updated_at_ms"), "updated_at_ms"),
        )

    def to_thread_goal(self) -> ThreadGoal:
        return ThreadGoal(
            thread_id=ThreadId.from_string(self.thread_id),
            goal_id=self.goal_id,
            objective=self.objective,
            status=ThreadGoalStatus.parse(self.status),
            token_budget=self.token_budget,
            tokens_used=self.tokens_used,
            time_used_seconds=self.time_used_seconds,
            created_at=epoch_millis_to_datetime(self.created_at_ms),
            updated_at=epoch_millis_to_datetime(self.updated_at_ms),
        )


def epoch_millis_to_datetime(ms: int) -> datetime:
    if isinstance(ms, bool) or not isinstance(ms, int):
        raise TypeError("ms must be an integer")
    seconds, millis = divmod(ms, 1000)
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(microsecond=millis * 1000)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"invalid unix timestamp millis: {ms}") from exc


def _datetime_utc(value: JsonValue, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _ensure_i64(value: JsonValue, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _required_i64(value: JsonValue, name: str) -> int:
    _ensure_i64(value, name)
    return value


def _optional_i64(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    return _required_i64(value, name)


__all__ = ["ThreadGoal", "ThreadGoalRow", "ThreadGoalStatus", "epoch_millis_to_datetime"]
