"""State runtime path helpers.

Ported from the runtime path pieces of:

- ``codex/codex-rs/state/src/lib.rs``
- ``codex/codex-rs/state/src/runtime.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pycodex.protocol import ThreadId

STATE_DB_FILENAME = "state_5.sqlite"
LOGS_DB_FILENAME = "logs_2.sqlite"
GOALS_DB_FILENAME = "goals_1.sqlite"
MEMORIES_DB_FILENAME = "memories_1.sqlite"


@dataclass(frozen=True)
class RuntimeDbPath:
    label: str
    path: Path


class ThreadGoalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    BLOCKED = "blocked"
    USAGE_LIMITED = "usage_limited"
    BUDGET_LIMITED = "budget_limited"
    COMPLETE = "complete"

    def is_active(self) -> bool:
        return self is ThreadGoalStatus.ACTIVE

    def is_terminal(self) -> bool:
        return self in (ThreadGoalStatus.BUDGET_LIMITED, ThreadGoalStatus.COMPLETE)


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
        if not isinstance(self.goal_id, str):
            raise TypeError("goal_id must be a string")
        if not isinstance(self.objective, str):
            raise TypeError("objective must be a string")
        if not isinstance(self.status, ThreadGoalStatus):
            object.__setattr__(self, "status", ThreadGoalStatus(self.status))
        if self.token_budget is not None:
            _ensure_i64(self.token_budget, "token_budget")
        _ensure_i64(self.tokens_used, "tokens_used")
        _ensure_i64(self.time_used_seconds, "time_used_seconds")
        object.__setattr__(self, "created_at", _datetime_utc(self.created_at, "created_at"))
        object.__setattr__(self, "updated_at", _datetime_utc(self.updated_at, "updated_at"))


def state_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / STATE_DB_FILENAME


def logs_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / LOGS_DB_FILENAME


def goals_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / GOALS_DB_FILENAME


def memories_db_path(codex_home: Path | str) -> Path:
    return _path(codex_home, "codex_home") / MEMORIES_DB_FILENAME


def runtime_db_paths(codex_home: Path | str) -> list[RuntimeDbPath]:
    root = _path(codex_home, "codex_home")
    return [
        RuntimeDbPath("state DB", root / STATE_DB_FILENAME),
        RuntimeDbPath("log DB", root / LOGS_DB_FILENAME),
        RuntimeDbPath("goals DB", root / GOALS_DB_FILENAME),
        RuntimeDbPath("memories DB", root / MEMORIES_DB_FILENAME),
    ]


def _path(value: Path | str, label: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{label} must be a string or Path")
    return Path(value)


def _ensure_i64(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")


def _datetime_utc(value: object, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


__all__ = [
    "GOALS_DB_FILENAME",
    "LOGS_DB_FILENAME",
    "MEMORIES_DB_FILENAME",
    "RuntimeDbPath",
    "STATE_DB_FILENAME",
    "ThreadGoal",
    "ThreadGoalStatus",
    "goals_db_path",
    "logs_db_path",
    "memories_db_path",
    "runtime_db_paths",
    "state_db_path",
]
