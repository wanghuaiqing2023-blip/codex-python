"""Thread goal store helpers ported from ``codex-state/src/runtime/goals.rs``."""

from __future__ import annotations

import asyncio
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.protocol import ThreadId

from ..model.thread_goal import ThreadGoal, ThreadGoalRow, ThreadGoalStatus

JsonValue = Any
TOKEN_BUDGET_UNCHANGED = object()


class GoalAccountingMode(str, Enum):
    ACTIVE_STATUS_ONLY = "active_status_only"
    ACTIVE_ONLY = "active_only"
    ACTIVE_OR_COMPLETE = "active_or_complete"
    ACTIVE_OR_STOPPED = "active_or_stopped"


@dataclass(frozen=True)
class GoalUpdate:
    objective: str | None = None
    status: ThreadGoalStatus | None = None
    token_budget: int | None | object = TOKEN_BUDGET_UNCHANGED
    expected_goal_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective", _optional_str(self.objective, "objective"))
        if self.status is not None and not isinstance(self.status, ThreadGoalStatus):
            object.__setattr__(self, "status", ThreadGoalStatus.parse(str(self.status)))
        if self.token_budget is not TOKEN_BUDGET_UNCHANGED:
            object.__setattr__(self, "token_budget", _optional_i64(self.token_budget, "token_budget"))
        object.__setattr__(self, "expected_goal_id", _optional_str(self.expected_goal_id, "expected_goal_id"))


@dataclass(frozen=True)
class GoalAccountingOutcome:
    goal: ThreadGoal | None
    updated: bool

    @classmethod
    def unchanged(cls, goal: ThreadGoal | None) -> "GoalAccountingOutcome":
        return cls(goal=goal, updated=False)

    @classmethod
    def updated_goal(cls, goal: ThreadGoal) -> "GoalAccountingOutcome":
        return cls(goal=goal, updated=True)


class GoalStore:
    def __init__(self, db: sqlite3.Connection | Path | str):
        self._db = db

    async def get_thread_goal(self, thread_id: ThreadId | str) -> ThreadGoal | None:
        return await _call(self._db, _get_thread_goal_sync, _thread_id_str(thread_id))

    async def replace_thread_goal(
        self,
        thread_id: ThreadId | str,
        objective: str,
        status: ThreadGoalStatus,
        token_budget: int | None,
        *,
        now_ms: int | None = None,
        goal_id: str | None = None,
    ) -> ThreadGoal:
        return await _call(
            self._db,
            _replace_thread_goal_sync,
            _thread_id_str(thread_id),
            _required_str(objective, "objective"),
            _status(status),
            _optional_i64(token_budget, "token_budget"),
            now_ms=now_ms,
            goal_id=goal_id,
        )

    async def insert_thread_goal(
        self,
        thread_id: ThreadId | str,
        objective: str,
        status: ThreadGoalStatus,
        token_budget: int | None,
        *,
        now_ms: int | None = None,
        goal_id: str | None = None,
    ) -> ThreadGoal | None:
        return await _call(
            self._db,
            _insert_thread_goal_sync,
            _thread_id_str(thread_id),
            _required_str(objective, "objective"),
            _status(status),
            _optional_i64(token_budget, "token_budget"),
            now_ms=now_ms,
            goal_id=goal_id,
        )

    async def update_thread_goal(
        self,
        thread_id: ThreadId | str,
        update: GoalUpdate,
        *,
        now_ms: int | None = None,
    ) -> ThreadGoal | None:
        if not isinstance(update, GoalUpdate):
            raise TypeError("update must be GoalUpdate")
        return await _call(self._db, _update_thread_goal_sync, _thread_id_str(thread_id), update, now_ms=now_ms)

    async def pause_active_thread_goal(self, thread_id: ThreadId | str, *, now_ms: int | None = None) -> ThreadGoal | None:
        return await _call(
            self._db,
            _update_active_thread_goal_status_sync,
            _thread_id_str(thread_id),
            ThreadGoalStatus.PAUSED,
            now_ms=now_ms,
        )

    async def usage_limit_active_thread_goal(self, thread_id: ThreadId | str, *, now_ms: int | None = None) -> ThreadGoal | None:
        return await _call(
            self._db,
            _update_active_thread_goal_status_sync,
            _thread_id_str(thread_id),
            ThreadGoalStatus.USAGE_LIMITED,
            now_ms=now_ms,
        )

    async def delete_thread_goal(self, thread_id: ThreadId | str) -> bool:
        return await _call(self._db, _delete_thread_goal_sync, _thread_id_str(thread_id))

    async def account_thread_goal_usage(
        self,
        thread_id: ThreadId | str,
        time_delta_seconds: int,
        token_delta: int,
        mode: GoalAccountingMode,
        expected_goal_id: str | None = None,
        *,
        now_ms: int | None = None,
    ) -> GoalAccountingOutcome:
        return await _call(
            self._db,
            _account_thread_goal_usage_sync,
            _thread_id_str(thread_id),
            _required_i64(time_delta_seconds, "time_delta_seconds"),
            _required_i64(token_delta, "token_delta"),
            _mode(mode),
            _optional_str(expected_goal_id, "expected_goal_id"),
            now_ms=now_ms,
        )


def _get_thread_goal_sync(connection: sqlite3.Connection, thread_id: str) -> ThreadGoal | None:
    row = _fetch_goal_row(connection, thread_id)
    return _thread_goal_from_row(row) if row is not None else None


def _replace_thread_goal_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    objective: str,
    status: ThreadGoalStatus,
    token_budget: int | None,
    *,
    now_ms: int | None = None,
    goal_id: str | None = None,
) -> ThreadGoal:
    timestamp = _timestamp_ms(now_ms)
    next_goal_id = _goal_id(goal_id)
    next_status = _status_after_budget_limit(status, 0, token_budget)
    connection.execute(
        """
INSERT INTO thread_goals (
    thread_id, goal_id, objective, status, token_budget, tokens_used,
    time_used_seconds, created_at_ms, updated_at_ms
) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
ON CONFLICT(thread_id) DO UPDATE SET
    goal_id = excluded.goal_id,
    objective = excluded.objective,
    status = excluded.status,
    token_budget = excluded.token_budget,
    tokens_used = 0,
    time_used_seconds = 0,
    created_at_ms = excluded.created_at_ms,
    updated_at_ms = excluded.updated_at_ms
        """,
        (thread_id, next_goal_id, objective, next_status.as_str(), token_budget, timestamp, timestamp),
    )
    connection.commit()
    goal = _get_thread_goal_sync(connection, thread_id)
    if goal is None:
        raise LookupError("thread goal replacement did not return a row")
    return goal


def _insert_thread_goal_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    objective: str,
    status: ThreadGoalStatus,
    token_budget: int | None,
    *,
    now_ms: int | None = None,
    goal_id: str | None = None,
) -> ThreadGoal | None:
    timestamp = _timestamp_ms(now_ms)
    next_status = _status_after_budget_limit(status, 0, token_budget)
    cursor = connection.execute(
        """
INSERT OR IGNORE INTO thread_goals (
    thread_id, goal_id, objective, status, token_budget, tokens_used,
    time_used_seconds, created_at_ms, updated_at_ms
) VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
        """,
        (thread_id, _goal_id(goal_id), objective, next_status.as_str(), token_budget, timestamp, timestamp),
    )
    connection.commit()
    if int(cursor.rowcount) == 0:
        return None
    return _get_thread_goal_sync(connection, thread_id)


def _update_thread_goal_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    update: GoalUpdate,
    *,
    now_ms: int | None = None,
) -> ThreadGoal | None:
    current = _get_thread_goal_sync(connection, thread_id)
    if current is None:
        return None
    if update.expected_goal_id is not None and current.goal_id != update.expected_goal_id:
        return None
    if update.objective is None and update.status is None and update.token_budget is TOKEN_BUDGET_UNCHANGED:
        return current

    token_budget = current.token_budget if update.token_budget is TOKEN_BUDGET_UNCHANGED else update.token_budget
    status = _updated_status(current.status, update.status, current.tokens_used, token_budget)
    objective = current.objective if update.objective is None else update.objective
    timestamp = _timestamp_ms(now_ms)
    connection.execute(
        """
UPDATE thread_goals
SET objective = ?, status = ?, token_budget = ?, updated_at_ms = ?
WHERE thread_id = ? AND (? IS NULL OR goal_id = ?)
        """,
        (objective, status.as_str(), token_budget, timestamp, thread_id, update.expected_goal_id, update.expected_goal_id),
    )
    connection.commit()
    return _get_thread_goal_sync(connection, thread_id)


def _update_active_thread_goal_status_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    status: ThreadGoalStatus,
    *,
    now_ms: int | None = None,
) -> ThreadGoal | None:
    if status not in (ThreadGoalStatus.PAUSED, ThreadGoalStatus.USAGE_LIMITED):
        raise ValueError("active goal status update must be paused or usage_limited")
    allowed = [ThreadGoalStatus.ACTIVE.as_str()]
    if status is ThreadGoalStatus.USAGE_LIMITED:
        allowed.append(ThreadGoalStatus.BUDGET_LIMITED.as_str())
    placeholders = ", ".join("?" for _ in allowed)
    cursor = connection.execute(
        f"""
UPDATE thread_goals
SET status = ?, updated_at_ms = ?
WHERE thread_id = ? AND status IN ({placeholders})
        """,
        (status.as_str(), _timestamp_ms(now_ms), thread_id, *allowed),
    )
    connection.commit()
    if int(cursor.rowcount) == 0:
        return None
    return _get_thread_goal_sync(connection, thread_id)


def _delete_thread_goal_sync(connection: sqlite3.Connection, thread_id: str) -> bool:
    cursor = connection.execute("DELETE FROM thread_goals WHERE thread_id = ?", (thread_id,))
    connection.commit()
    return int(cursor.rowcount) > 0


def _account_thread_goal_usage_sync(
    connection: sqlite3.Connection,
    thread_id: str,
    time_delta_seconds: int,
    token_delta: int,
    mode: GoalAccountingMode,
    expected_goal_id: str | None,
    *,
    now_ms: int | None = None,
) -> GoalAccountingOutcome:
    time_delta_seconds = max(time_delta_seconds, 0)
    token_delta = max(token_delta, 0)
    if time_delta_seconds == 0 and token_delta == 0:
        return GoalAccountingOutcome.unchanged(_get_thread_goal_sync(connection, thread_id))

    current = _get_thread_goal_sync(connection, thread_id)
    if current is None or (expected_goal_id is not None and current.goal_id != expected_goal_id):
        return GoalAccountingOutcome.unchanged(current)
    if not _accounting_status_matches(current.status, mode):
        return GoalAccountingOutcome.unchanged(current)

    tokens_used = current.tokens_used + token_delta
    time_used_seconds = current.time_used_seconds + time_delta_seconds
    status = current.status
    if _budget_limit_status_matches(current.status, mode) and current.token_budget is not None and tokens_used >= current.token_budget:
        status = ThreadGoalStatus.BUDGET_LIMITED
    connection.execute(
        """
UPDATE thread_goals
SET time_used_seconds = ?, tokens_used = ?, status = ?, updated_at_ms = ?
WHERE thread_id = ? AND (? IS NULL OR goal_id = ?)
        """,
        (time_used_seconds, tokens_used, status.as_str(), _timestamp_ms(now_ms), thread_id, expected_goal_id, expected_goal_id),
    )
    connection.commit()
    updated = _get_thread_goal_sync(connection, thread_id)
    if updated is None:
        return GoalAccountingOutcome.unchanged(None)
    return GoalAccountingOutcome.updated_goal(updated)


def _fetch_goal_row(connection: sqlite3.Connection, thread_id: str):
    return connection.execute(
        """
SELECT
    thread_id, goal_id, objective, status, token_budget, tokens_used,
    time_used_seconds, created_at_ms, updated_at_ms
FROM thread_goals
WHERE thread_id = ?
        """,
        (thread_id,),
    ).fetchone()


def _thread_goal_from_row(row) -> ThreadGoal:
    return ThreadGoalRow.from_mapping(
        {
            "thread_id": row[0],
            "goal_id": row[1],
            "objective": row[2],
            "status": row[3],
            "token_budget": row[4],
            "tokens_used": row[5],
            "time_used_seconds": row[6],
            "created_at_ms": row[7],
            "updated_at_ms": row[8],
        }
    ).to_thread_goal()


def _status_after_budget_limit(
    status: ThreadGoalStatus,
    tokens_used: int,
    token_budget: int | None,
) -> ThreadGoalStatus:
    if status is ThreadGoalStatus.ACTIVE and token_budget is not None and tokens_used >= token_budget:
        return ThreadGoalStatus.BUDGET_LIMITED
    return status


def _updated_status(
    current_status: ThreadGoalStatus,
    requested_status: ThreadGoalStatus | None,
    tokens_used: int,
    token_budget: int | None,
) -> ThreadGoalStatus:
    if requested_status is None:
        if current_status is ThreadGoalStatus.ACTIVE and token_budget is not None and tokens_used >= token_budget:
            return ThreadGoalStatus.BUDGET_LIMITED
        return current_status
    if current_status is ThreadGoalStatus.BUDGET_LIMITED and requested_status in (ThreadGoalStatus.PAUSED, ThreadGoalStatus.BLOCKED):
        return current_status
    return _status_after_budget_limit(requested_status, tokens_used, token_budget)


def _accounting_status_matches(status: ThreadGoalStatus, mode: GoalAccountingMode) -> bool:
    if mode is GoalAccountingMode.ACTIVE_STATUS_ONLY:
        return status is ThreadGoalStatus.ACTIVE
    if mode is GoalAccountingMode.ACTIVE_ONLY:
        return status in (ThreadGoalStatus.ACTIVE, ThreadGoalStatus.BUDGET_LIMITED)
    if mode is GoalAccountingMode.ACTIVE_OR_COMPLETE:
        return status in (ThreadGoalStatus.ACTIVE, ThreadGoalStatus.BUDGET_LIMITED, ThreadGoalStatus.COMPLETE)
    if mode is GoalAccountingMode.ACTIVE_OR_STOPPED:
        return status in (
            ThreadGoalStatus.ACTIVE,
            ThreadGoalStatus.PAUSED,
            ThreadGoalStatus.BLOCKED,
            ThreadGoalStatus.USAGE_LIMITED,
            ThreadGoalStatus.BUDGET_LIMITED,
        )
    raise AssertionError("unreachable accounting mode")


def _budget_limit_status_matches(status: ThreadGoalStatus, mode: GoalAccountingMode) -> bool:
    if mode is GoalAccountingMode.ACTIVE_OR_STOPPED:
        return _accounting_status_matches(status, mode)
    return status is ThreadGoalStatus.ACTIVE


async def _call(db: sqlite3.Connection | Path | str, fn, *args, **kwargs):
    if isinstance(db, sqlite3.Connection):
        return fn(db, *args, **kwargs)
    return await asyncio.to_thread(_with_connection, _path(db, "db"), fn, *args, **kwargs)


def _with_connection(path: Path, fn, *args, **kwargs):
    connection = sqlite3.connect(path)
    try:
        return fn(connection, *args, **kwargs)
    finally:
        connection.close()


def _path(value: JsonValue, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a string or Path")
    return Path(value)


def _thread_id_str(value: ThreadId | str) -> str:
    if isinstance(value, ThreadId):
        return str(value)
    return _required_str(value, "thread_id")


def _goal_id(value: str | None) -> str:
    if value is None:
        return str(uuid.uuid4())
    return _required_str(value, "goal_id")


def _status(value: ThreadGoalStatus) -> ThreadGoalStatus:
    if not isinstance(value, ThreadGoalStatus):
        return ThreadGoalStatus.parse(str(value))
    return value


def _mode(value: GoalAccountingMode) -> GoalAccountingMode:
    if not isinstance(value, GoalAccountingMode):
        return GoalAccountingMode(str(value))
    return value


def _timestamp_ms(value: int | None) -> int:
    return int(time.time() * 1000) if value is None else _required_i64(value, "now_ms")


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _optional_str(value: JsonValue, name: str) -> str | None:
    if value is None:
        return None
    return _required_str(value, name)


def _required_i64(value: JsonValue, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")
    return value


def _optional_i64(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    return _required_i64(value, name)


__all__ = [
    "GoalAccountingMode",
    "GoalAccountingOutcome",
    "GoalStore",
    "GoalUpdate",
    "TOKEN_BUDGET_UNCHANGED",
]
