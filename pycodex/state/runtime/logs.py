"""Runtime log store ported from ``codex-state/src/runtime/logs.rs``."""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..model import LogEntry, LogQuery, LogRow

LOG_RETENTION_DAYS = 10
LOG_PARTITION_SIZE_LIMIT_BYTES = 10 * 1024 * 1024
LOG_PARTITION_ROW_LIMIT = 1_000

JsonValue = Any


class RuntimeLogStore:
    def __init__(self, db: sqlite3.Connection | Path | str):
        self._db = db

    async def insert_log(self, entry: LogEntry) -> None:
        await self.insert_logs([entry])

    async def insert_logs(self, entries: Sequence[LogEntry]) -> None:
        await _call(self._db, _insert_logs_sync, list(entries))

    async def delete_logs_before(self, cutoff_ts: int) -> int:
        return await _call(self._db, _delete_logs_before_sync, _required_i64(cutoff_ts, "cutoff_ts"))

    async def run_logs_startup_maintenance(self, *, now: datetime | None = None) -> None:
        await _call(self._db, _run_logs_startup_maintenance_sync, now)

    async def query_logs(self, query: LogQuery | None = None) -> list[LogRow]:
        return await _call(self._db, _query_logs_sync, query or LogQuery())

    async def query_feedback_logs_for_threads(self, thread_ids: Sequence[str]) -> bytes:
        return await _call(self._db, _query_feedback_logs_for_threads_sync, [_required_str(item, "thread_id") for item in thread_ids])

    async def query_feedback_logs(self, thread_id: str) -> bytes:
        return await self.query_feedback_logs_for_threads([_required_str(thread_id, "thread_id")])

    async def max_log_id(self, query: LogQuery | None = None) -> int:
        return await _call(self._db, _max_log_id_sync, query or LogQuery())


def insert_log(db: sqlite3.Connection | Path | str, entry: LogEntry) -> None:
    if isinstance(db, sqlite3.Connection):
        _insert_logs_sync(db, [entry])
        return
    _with_connection(_path(db, "db"), _insert_logs_sync, [entry])


def format_feedback_log_line(ts: int, ts_nanos: int, level: str, feedback_log_body: str) -> str:
    nanos = ts_nanos if 0 <= ts_nanos <= 999_999_999 else 0
    try:
        dt = datetime.fromtimestamp(ts + nanos / 1_000_000_000, tz=UTC)
        timestamp = dt.isoformat(timespec="microseconds").replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        timestamp = f"{ts}.{ts_nanos:09}Z"
    line = f"{timestamp} {level:>5} {feedback_log_body}"
    if not line.endswith("\n"):
        line += "\n"
    return line


def _insert_logs_sync(connection: sqlite3.Connection, entries: Sequence[LogEntry]) -> None:
    if not entries:
        return
    rows = []
    for entry in entries:
        feedback_log_body = entry.feedback_log_body if entry.feedback_log_body is not None else entry.message
        rows.append(
            (
                entry.ts,
                entry.ts_nanos,
                entry.level,
                entry.target,
                feedback_log_body,
                entry.thread_id,
                entry.process_uuid,
                entry.module_path,
                entry.file,
                entry.line,
                _estimated_bytes(entry, feedback_log_body),
            )
        )
    with connection:
        connection.executemany(
            """
            INSERT INTO logs (
                ts, ts_nanos, level, target, feedback_log_body, thread_id,
                process_uuid, module_path, file, line, estimated_bytes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        _prune_logs_after_insert(connection, entries)


def _prune_logs_after_insert(connection: sqlite3.Connection, entries: Sequence[LogEntry]) -> None:
    thread_ids = sorted({entry.thread_id for entry in entries if entry.thread_id is not None})
    for thread_id in thread_ids:
        _prune_partition(connection, "thread_id = ?", (thread_id,))

    process_uuids = sorted(
        {
            entry.process_uuid
            for entry in entries
            if entry.thread_id is None and entry.process_uuid is not None
        }
    )
    for process_uuid in process_uuids:
        _prune_partition(connection, "thread_id IS NULL AND process_uuid = ?", (process_uuid,))

    if any(entry.thread_id is None and entry.process_uuid is None for entry in entries):
        _prune_partition(connection, "thread_id IS NULL AND process_uuid IS NULL", ())


def _prune_partition(connection: sqlite3.Connection, where_sql: str, params: tuple[JsonValue, ...]) -> None:
    rows = connection.execute(
        f"""
        SELECT id, estimated_bytes
        FROM logs
        WHERE {where_sql}
        ORDER BY ts DESC, ts_nanos DESC, id DESC
        """,
        params,
    ).fetchall()
    cumulative = 0
    delete_ids: list[int] = []
    for idx, row in enumerate(rows, start=1):
        cumulative += int(row[1] or 0)
        if cumulative > LOG_PARTITION_SIZE_LIMIT_BYTES or idx > LOG_PARTITION_ROW_LIMIT:
            delete_ids.append(int(row[0]))
    if delete_ids:
        placeholders = ", ".join("?" for _ in delete_ids)
        connection.execute(f"DELETE FROM logs WHERE id IN ({placeholders})", delete_ids)


def _delete_logs_before_sync(connection: sqlite3.Connection, cutoff_ts: int) -> int:
    with connection:
        cursor = connection.execute("DELETE FROM logs WHERE ts < ?", (cutoff_ts,))
        return int(cursor.rowcount if cursor.rowcount is not None else 0)


def _run_logs_startup_maintenance_sync(connection: sqlite3.Connection, now: datetime | None = None) -> None:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    cutoff = int((current.astimezone(UTC) - timedelta(days=LOG_RETENTION_DAYS)).timestamp())
    _delete_logs_before_sync(connection, cutoff)
    connection.execute("PRAGMA wal_checkpoint(PASSIVE)")


def _query_logs_sync(connection: sqlite3.Connection, query: LogQuery) -> list[LogRow]:
    where_sql, params = _log_filters(query)
    order = "DESC" if query.descending else "ASC"
    sql = (
        "SELECT id, ts, ts_nanos, level, target, feedback_log_body AS message, "
        "thread_id, process_uuid, file, line FROM logs WHERE 1 = 1"
        + where_sql
        + f" ORDER BY id {order}"
    )
    if query.limit is not None:
        sql += " LIMIT ?"
        params.append(query.limit)
    return [LogRow.from_mapping(dict(row)) for row in _rows(connection, sql, params)]


def _query_feedback_logs_for_threads_sync(connection: sqlite3.Connection, thread_ids: Sequence[str]) -> bytes:
    if not thread_ids:
        return b""

    latest_processes: set[str] = set()
    for thread_id in thread_ids:
        row = connection.execute(
            """
            SELECT process_uuid
            FROM logs
            WHERE thread_id = ? AND process_uuid IS NOT NULL
            ORDER BY ts DESC, ts_nanos DESC, id DESC
            LIMIT 1
            """,
            (thread_id,),
        ).fetchone()
        if row and row[0] is not None:
            latest_processes.add(str(row[0]))

    clauses: list[str] = []
    params: list[JsonValue] = []
    if thread_ids:
        clauses.append(f"thread_id IN ({', '.join('?' for _ in thread_ids)})")
        params.extend(thread_ids)
    if latest_processes:
        processes = sorted(latest_processes)
        clauses.append(f"(thread_id IS NULL AND process_uuid IN ({', '.join('?' for _ in processes)}))")
        params.extend(processes)
    where = " OR ".join(clauses)
    rows = connection.execute(
        f"""
        SELECT ts, ts_nanos, level, feedback_log_body, estimated_bytes, id
        FROM logs
        WHERE feedback_log_body IS NOT NULL AND ({where})
        ORDER BY ts DESC, ts_nanos DESC, id DESC
        """,
        params,
    ).fetchall()

    lines: list[str] = []
    cumulative_estimated = 0
    total_line_bytes = 0
    for row in rows:
        cumulative_estimated += int(row[4] or 0)
        if cumulative_estimated > LOG_PARTITION_SIZE_LIMIT_BYTES:
            break
        line = format_feedback_log_line(int(row[0]), int(row[1]), str(row[2]), str(row[3]))
        line_bytes = len(line.encode())
        if total_line_bytes + line_bytes > LOG_PARTITION_SIZE_LIMIT_BYTES:
            break
        total_line_bytes += line_bytes
        lines.append(line)
    return "".join(reversed(lines)).encode()


def _max_log_id_sync(connection: sqlite3.Connection, query: LogQuery) -> int:
    where_sql, params = _log_filters(query)
    row = connection.execute("SELECT MAX(id) AS max_id FROM logs WHERE 1 = 1" + where_sql, params).fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _log_filters(query: LogQuery) -> tuple[str, list[JsonValue]]:
    clauses: list[str] = []
    params: list[JsonValue] = []
    if query.levels_upper:
        clauses.append(f"UPPER(level) IN ({', '.join('?' for _ in query.levels_upper)})")
        params.extend(query.levels_upper)
    if query.from_ts is not None:
        clauses.append("ts >= ?")
        params.append(query.from_ts)
    if query.to_ts is not None:
        clauses.append("ts <= ?")
        params.append(query.to_ts)
    _push_like_filters(clauses, params, "module_path", query.module_like)
    _push_like_filters(clauses, params, "file", query.file_like)
    if query.thread_ids or query.include_threadless:
        thread_clauses = []
        for thread_id in query.thread_ids:
            thread_clauses.append("thread_id = ?")
            params.append(thread_id)
        if query.include_threadless:
            thread_clauses.append("thread_id IS NULL")
        clauses.append("(" + " OR ".join(thread_clauses) + ")")
    if query.after_id is not None:
        clauses.append("id > ?")
        params.append(query.after_id)
    if query.search is not None:
        clauses.append("INSTR(COALESCE(feedback_log_body, ''), ?) > 0")
        params.append(query.search)
    if not clauses:
        return "", params
    return "".join(" AND " + clause for clause in clauses), params


def _push_like_filters(clauses: list[str], params: list[JsonValue], column: str, filters: Sequence[str]) -> None:
    if not filters:
        return
    clauses.append("(" + " OR ".join(f"{column} LIKE '%' || ? || '%'" for _ in filters) + ")")
    params.extend(filters)


def _estimated_bytes(entry: LogEntry, feedback_log_body: str | None) -> int:
    return (
        _byte_len(feedback_log_body)
        + _byte_len(entry.level)
        + _byte_len(entry.target)
        + _byte_len(entry.module_path)
        + _byte_len(entry.file)
    )


def _byte_len(value: str | None) -> int:
    return 0 if value is None else len(value.encode())


def _rows(connection: sqlite3.Connection, sql: str, params: Sequence[JsonValue]) -> list[sqlite3.Row]:
    old_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(sql, params).fetchall()
    finally:
        connection.row_factory = old_factory


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


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _required_i64(value: JsonValue, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < -(2**63) or value > 2**63 - 1:
        raise ValueError(f"{name} must fit in a signed 64-bit integer")
    return value


__all__ = [
    "LOG_PARTITION_ROW_LIMIT",
    "LOG_PARTITION_SIZE_LIMIT_BYTES",
    "LOG_RETENTION_DAYS",
    "RuntimeLogStore",
    "format_feedback_log_line",
    "insert_log",
]
