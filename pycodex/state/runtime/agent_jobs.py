"""Agent job runtime store ported from ``codex-state/src/runtime/agent_jobs.rs``."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..model.agent_job import (
    AgentJob,
    AgentJobCreateParams,
    AgentJobItem,
    AgentJobItemCreateParams,
    AgentJobItemRow,
    AgentJobItemStatus,
    AgentJobProgress,
    AgentJobRow,
    AgentJobStatus,
)

JsonValue = Any


class AgentJobStore:
    def __init__(self, db: sqlite3.Connection | Path | str):
        self._db = db

    async def create_agent_job(
        self,
        params: AgentJobCreateParams,
        items: list[AgentJobItemCreateParams] | tuple[AgentJobItemCreateParams, ...],
        *,
        now: int | None = None,
    ) -> AgentJob:
        return await _call(self._db, _create_agent_job_sync, params, items, now=now)

    async def get_agent_job(self, job_id: str) -> AgentJob | None:
        return await _call(self._db, _get_agent_job_sync, _required_str(job_id, "job_id"))

    async def list_agent_job_items(
        self,
        job_id: str,
        status: AgentJobItemStatus | None = None,
        limit: int | None = None,
    ) -> list[AgentJobItem]:
        return await _call(
            self._db,
            _list_agent_job_items_sync,
            _required_str(job_id, "job_id"),
            _item_status(status) if status is not None else None,
            _optional_usize(limit, "limit"),
        )

    async def get_agent_job_item(self, job_id: str, item_id: str) -> AgentJobItem | None:
        return await _call(self._db, _get_agent_job_item_sync, _required_str(job_id, "job_id"), _required_str(item_id, "item_id"))

    async def mark_agent_job_running(self, job_id: str, *, now: int | None = None) -> None:
        await _call(self._db, _mark_agent_job_running_sync, _required_str(job_id, "job_id"), now=now)

    async def mark_agent_job_completed(self, job_id: str, *, now: int | None = None) -> None:
        await _call(self._db, _mark_agent_job_completed_sync, _required_str(job_id, "job_id"), now=now)

    async def mark_agent_job_failed(self, job_id: str, error_message: str, *, now: int | None = None) -> None:
        await _call(
            self._db,
            _mark_agent_job_failed_sync,
            _required_str(job_id, "job_id"),
            _required_str(error_message, "error_message"),
            now=now,
        )

    async def mark_agent_job_cancelled(self, job_id: str, reason: str, *, now: int | None = None) -> bool:
        return await _call(
            self._db,
            _mark_agent_job_cancelled_sync,
            _required_str(job_id, "job_id"),
            _required_str(reason, "reason"),
            now=now,
        )

    async def is_agent_job_cancelled(self, job_id: str) -> bool:
        return await _call(self._db, _is_agent_job_cancelled_sync, _required_str(job_id, "job_id"))

    async def mark_agent_job_item_running(self, job_id: str, item_id: str, *, now: int | None = None) -> bool:
        return await _call(self._db, _mark_agent_job_item_running_sync, job_id, item_id, None, now=now)

    async def mark_agent_job_item_running_with_thread(
        self,
        job_id: str,
        item_id: str,
        thread_id: str,
        *,
        now: int | None = None,
    ) -> bool:
        return await _call(
            self._db,
            _mark_agent_job_item_running_sync,
            job_id,
            item_id,
            _required_str(thread_id, "thread_id"),
            now=now,
        )

    async def mark_agent_job_item_pending(
        self,
        job_id: str,
        item_id: str,
        error_message: str | None,
        *,
        now: int | None = None,
    ) -> bool:
        return await _call(self._db, _mark_agent_job_item_pending_sync, job_id, item_id, error_message, now=now)

    async def set_agent_job_item_thread(self, job_id: str, item_id: str, thread_id: str, *, now: int | None = None) -> bool:
        return await _call(self._db, _set_agent_job_item_thread_sync, job_id, item_id, thread_id, now=now)

    async def report_agent_job_item_result(
        self,
        job_id: str,
        item_id: str,
        reporting_thread_id: str,
        result_json: JsonValue,
        *,
        now: int | None = None,
    ) -> bool:
        return await _call(
            self._db,
            _report_agent_job_item_result_sync,
            job_id,
            item_id,
            reporting_thread_id,
            result_json,
            now=now,
        )

    async def mark_agent_job_item_completed(self, job_id: str, item_id: str, *, now: int | None = None) -> bool:
        return await _call(self._db, _mark_agent_job_item_completed_sync, job_id, item_id, now=now)

    async def mark_agent_job_item_failed(self, job_id: str, item_id: str, error_message: str, *, now: int | None = None) -> bool:
        return await _call(self._db, _mark_agent_job_item_failed_sync, job_id, item_id, error_message, now=now)

    async def get_agent_job_progress(self, job_id: str) -> AgentJobProgress:
        return await _call(self._db, _get_agent_job_progress_sync, _required_str(job_id, "job_id"))


def _create_agent_job_sync(
    connection: sqlite3.Connection,
    params: AgentJobCreateParams,
    items: list[AgentJobItemCreateParams] | tuple[AgentJobItemCreateParams, ...],
    *,
    now: int | None = None,
) -> AgentJob:
    if not isinstance(params, AgentJobCreateParams):
        raise TypeError("params must be AgentJobCreateParams")
    timestamp = _timestamp(now)
    with connection:
        connection.execute(
            """
INSERT INTO agent_jobs (
    id, name, status, instruction, auto_export, max_runtime_seconds,
    output_schema_json, input_headers_json, input_csv_path, output_csv_path,
    created_at, updated_at, started_at, completed_at, last_error
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)
            """,
            (
                params.id,
                params.name,
                AgentJobStatus.PENDING.as_str(),
                params.instruction,
                int(params.auto_export),
                params.max_runtime_seconds,
                json.dumps(params.output_schema_json, separators=(",", ":")) if params.output_schema_json is not None else None,
                json.dumps(list(params.input_headers), separators=(",", ":")),
                params.input_csv_path,
                params.output_csv_path,
                timestamp,
                timestamp,
            ),
        )
        for item in items:
            if not isinstance(item, AgentJobItemCreateParams):
                raise TypeError("items must contain AgentJobItemCreateParams")
            connection.execute(
                """
INSERT INTO agent_job_items (
    job_id, item_id, row_index, source_id, row_json, status,
    assigned_thread_id, attempt_count, result_json, last_error,
    created_at, updated_at, completed_at, reported_at
) VALUES (?, ?, ?, ?, ?, ?, NULL, 0, NULL, NULL, ?, ?, NULL, NULL)
                """,
                (
                    params.id,
                    item.item_id,
                    item.row_index,
                    item.source_id,
                    json.dumps(item.row_json, separators=(",", ":")),
                    AgentJobItemStatus.PENDING.as_str(),
                    timestamp,
                    timestamp,
                ),
            )
    job = _get_agent_job_sync(connection, params.id)
    if job is None:
        raise LookupError(f"failed to load created agent job {params.id}")
    return job


def _get_agent_job_sync(connection: sqlite3.Connection, job_id: str) -> AgentJob | None:
    row = connection.execute(
        """
SELECT id, name, status, instruction, auto_export, max_runtime_seconds,
       output_schema_json, input_headers_json, input_csv_path, output_csv_path,
       created_at, updated_at, started_at, completed_at, last_error
FROM agent_jobs
WHERE id = ?
        """,
        (job_id,),
    ).fetchone()
    return _job_from_row(row) if row is not None else None


def _list_agent_job_items_sync(
    connection: sqlite3.Connection,
    job_id: str,
    status: AgentJobItemStatus | None,
    limit: int | None,
) -> list[AgentJobItem]:
    sql = """
SELECT job_id, item_id, row_index, source_id, row_json, status, assigned_thread_id,
       attempt_count, result_json, last_error, created_at, updated_at, completed_at, reported_at
FROM agent_job_items
WHERE job_id = ?
    """
    params: list[Any] = [job_id]
    if status is not None:
        sql += " AND status = ?"
        params.append(status.as_str())
    sql += " ORDER BY row_index ASC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return [_item_from_row(row) for row in connection.execute(sql, params).fetchall()]


def _get_agent_job_item_sync(connection: sqlite3.Connection, job_id: str, item_id: str) -> AgentJobItem | None:
    row = connection.execute(
        """
SELECT job_id, item_id, row_index, source_id, row_json, status, assigned_thread_id,
       attempt_count, result_json, last_error, created_at, updated_at, completed_at, reported_at
FROM agent_job_items
WHERE job_id = ? AND item_id = ?
        """,
        (job_id, item_id),
    ).fetchone()
    return _item_from_row(row) if row is not None else None


def _mark_agent_job_running_sync(connection: sqlite3.Connection, job_id: str, *, now: int | None = None) -> None:
    timestamp = _timestamp(now)
    connection.execute(
        """
UPDATE agent_jobs
SET status = ?, updated_at = ?, started_at = COALESCE(started_at, ?), completed_at = NULL, last_error = NULL
WHERE id = ?
        """,
        (AgentJobStatus.RUNNING.as_str(), timestamp, timestamp, job_id),
    )
    connection.commit()


def _mark_agent_job_completed_sync(connection: sqlite3.Connection, job_id: str, *, now: int | None = None) -> None:
    timestamp = _timestamp(now)
    connection.execute(
        "UPDATE agent_jobs SET status = ?, updated_at = ?, completed_at = ?, last_error = NULL WHERE id = ?",
        (AgentJobStatus.COMPLETED.as_str(), timestamp, timestamp, job_id),
    )
    connection.commit()


def _mark_agent_job_failed_sync(connection: sqlite3.Connection, job_id: str, error_message: str, *, now: int | None = None) -> None:
    timestamp = _timestamp(now)
    connection.execute(
        "UPDATE agent_jobs SET status = ?, updated_at = ?, completed_at = ?, last_error = ? WHERE id = ?",
        (AgentJobStatus.FAILED.as_str(), timestamp, timestamp, error_message, job_id),
    )
    connection.commit()


def _mark_agent_job_cancelled_sync(connection: sqlite3.Connection, job_id: str, reason: str, *, now: int | None = None) -> bool:
    timestamp = _timestamp(now)
    cursor = connection.execute(
        """
UPDATE agent_jobs
SET status = ?, updated_at = ?, completed_at = ?, last_error = ?
WHERE id = ? AND status IN (?, ?)
        """,
        (
            AgentJobStatus.CANCELLED.as_str(),
            timestamp,
            timestamp,
            reason,
            job_id,
            AgentJobStatus.PENDING.as_str(),
            AgentJobStatus.RUNNING.as_str(),
        ),
    )
    connection.commit()
    return int(cursor.rowcount) > 0


def _is_agent_job_cancelled_sync(connection: sqlite3.Connection, job_id: str) -> bool:
    row = connection.execute("SELECT status FROM agent_jobs WHERE id = ?", (job_id,)).fetchone()
    return row is not None and AgentJobStatus.parse(row[0]) is AgentJobStatus.CANCELLED


def _mark_agent_job_item_running_sync(
    connection: sqlite3.Connection,
    job_id: str,
    item_id: str,
    thread_id: str | None,
    *,
    now: int | None = None,
) -> bool:
    cursor = connection.execute(
        """
UPDATE agent_job_items
SET status = ?, assigned_thread_id = ?, attempt_count = attempt_count + 1,
    updated_at = ?, last_error = NULL
WHERE job_id = ? AND item_id = ? AND status = ?
        """,
        (
            AgentJobItemStatus.RUNNING.as_str(),
            thread_id,
            _timestamp(now),
            _required_str(job_id, "job_id"),
            _required_str(item_id, "item_id"),
            AgentJobItemStatus.PENDING.as_str(),
        ),
    )
    connection.commit()
    return int(cursor.rowcount) > 0


def _mark_agent_job_item_pending_sync(connection: sqlite3.Connection, job_id: str, item_id: str, error_message: str | None, *, now: int | None = None) -> bool:
    cursor = connection.execute(
        """
UPDATE agent_job_items
SET status = ?, assigned_thread_id = NULL, updated_at = ?, last_error = ?
WHERE job_id = ? AND item_id = ? AND status = ?
        """,
        (AgentJobItemStatus.PENDING.as_str(), _timestamp(now), _optional_str(error_message, "error_message"), job_id, item_id, AgentJobItemStatus.RUNNING.as_str()),
    )
    connection.commit()
    return int(cursor.rowcount) > 0


def _set_agent_job_item_thread_sync(connection: sqlite3.Connection, job_id: str, item_id: str, thread_id: str, *, now: int | None = None) -> bool:
    cursor = connection.execute(
        """
UPDATE agent_job_items
SET assigned_thread_id = ?, updated_at = ?
WHERE job_id = ? AND item_id = ? AND status = ?
        """,
        (_required_str(thread_id, "thread_id"), _timestamp(now), job_id, item_id, AgentJobItemStatus.RUNNING.as_str()),
    )
    connection.commit()
    return int(cursor.rowcount) > 0


def _report_agent_job_item_result_sync(
    connection: sqlite3.Connection,
    job_id: str,
    item_id: str,
    reporting_thread_id: str,
    result_json: JsonValue,
    *,
    now: int | None = None,
) -> bool:
    timestamp = _timestamp(now)
    cursor = connection.execute(
        """
UPDATE agent_job_items
SET status = ?, result_json = ?, reported_at = ?, completed_at = ?, updated_at = ?,
    last_error = NULL, assigned_thread_id = NULL
WHERE job_id = ? AND item_id = ? AND status = ? AND assigned_thread_id = ?
        """,
        (
            AgentJobItemStatus.COMPLETED.as_str(),
            json.dumps(result_json, separators=(",", ":")),
            timestamp,
            timestamp,
            timestamp,
            job_id,
            item_id,
            AgentJobItemStatus.RUNNING.as_str(),
            reporting_thread_id,
        ),
    )
    connection.commit()
    return int(cursor.rowcount) > 0


def _mark_agent_job_item_completed_sync(connection: sqlite3.Connection, job_id: str, item_id: str, *, now: int | None = None) -> bool:
    timestamp = _timestamp(now)
    cursor = connection.execute(
        """
UPDATE agent_job_items
SET status = ?, completed_at = ?, updated_at = ?, assigned_thread_id = NULL
WHERE job_id = ? AND item_id = ? AND status = ? AND result_json IS NOT NULL
        """,
        (AgentJobItemStatus.COMPLETED.as_str(), timestamp, timestamp, job_id, item_id, AgentJobItemStatus.RUNNING.as_str()),
    )
    connection.commit()
    return int(cursor.rowcount) > 0


def _mark_agent_job_item_failed_sync(connection: sqlite3.Connection, job_id: str, item_id: str, error_message: str, *, now: int | None = None) -> bool:
    timestamp = _timestamp(now)
    cursor = connection.execute(
        """
UPDATE agent_job_items
SET status = ?, completed_at = ?, updated_at = ?, last_error = ?, assigned_thread_id = NULL
WHERE job_id = ? AND item_id = ? AND status = ?
        """,
        (AgentJobItemStatus.FAILED.as_str(), timestamp, timestamp, _required_str(error_message, "error_message"), job_id, item_id, AgentJobItemStatus.RUNNING.as_str()),
    )
    connection.commit()
    return int(cursor.rowcount) > 0


def _get_agent_job_progress_sync(connection: sqlite3.Connection, job_id: str) -> AgentJobProgress:
    row = connection.execute(
        """
SELECT
    COUNT(*) AS total_items,
    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS pending_items,
    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS running_items,
    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS completed_items,
    SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS failed_items
FROM agent_job_items
WHERE job_id = ?
        """,
        (
            AgentJobItemStatus.PENDING.as_str(),
            AgentJobItemStatus.RUNNING.as_str(),
            AgentJobItemStatus.COMPLETED.as_str(),
            AgentJobItemStatus.FAILED.as_str(),
            job_id,
        ),
    ).fetchone()
    return AgentJobProgress(
        total_items=max(int(row[0] or 0), 0),
        pending_items=max(int(row[1] or 0), 0),
        running_items=max(int(row[2] or 0), 0),
        completed_items=max(int(row[3] or 0), 0),
        failed_items=max(int(row[4] or 0), 0),
    )


def _job_from_row(row) -> AgentJob:
    return AgentJobRow(*row).to_agent_job()


def _item_from_row(row) -> AgentJobItem:
    return AgentJobItemRow(*row).to_agent_job_item()


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


def _timestamp(value: int | None) -> int:
    return int(time.time()) if value is None else _required_i64(value, "now")


def _item_status(value: AgentJobItemStatus) -> AgentJobItemStatus:
    if not isinstance(value, AgentJobItemStatus):
        return AgentJobItemStatus.parse(str(value))
    return value


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


def _optional_usize(value: JsonValue, name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


__all__ = ["AgentJobStore"]
