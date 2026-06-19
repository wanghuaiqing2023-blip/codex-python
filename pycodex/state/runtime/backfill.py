"""Backfill state runtime helpers ported from ``codex-state/src/runtime/backfill.rs``."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any

from ..model.backfill_state import BackfillState, BackfillStatus

JsonValue = Any


async def get_backfill_state(db: sqlite3.Connection | Path | str) -> BackfillState:
    if isinstance(db, sqlite3.Connection):
        return _get_backfill_state_sync(db)
    return await asyncio.to_thread(_with_connection, _path(db, "db"), _get_backfill_state_sync)


async def try_claim_backfill(
    db: sqlite3.Connection | Path | str,
    lease_seconds: int,
    *,
    now: int | None = None,
) -> bool:
    if isinstance(db, sqlite3.Connection):
        return _try_claim_backfill_sync(db, lease_seconds, now=now)
    return await asyncio.to_thread(
        _with_connection,
        _path(db, "db"),
        _try_claim_backfill_sync,
        lease_seconds,
        now=now,
    )


async def mark_backfill_running(db: sqlite3.Connection | Path | str, *, now: int | None = None) -> None:
    if isinstance(db, sqlite3.Connection):
        _mark_backfill_running_sync(db, now=now)
        return
    await asyncio.to_thread(_with_connection, _path(db, "db"), _mark_backfill_running_sync, now=now)


async def checkpoint_backfill(
    db: sqlite3.Connection | Path | str,
    watermark: str,
    *,
    now: int | None = None,
) -> None:
    if isinstance(db, sqlite3.Connection):
        _checkpoint_backfill_sync(db, watermark, now=now)
        return
    await asyncio.to_thread(
        _with_connection,
        _path(db, "db"),
        _checkpoint_backfill_sync,
        watermark,
        now=now,
    )


async def mark_backfill_complete(
    db: sqlite3.Connection | Path | str,
    last_watermark: str | None,
    *,
    now: int | None = None,
) -> None:
    if isinstance(db, sqlite3.Connection):
        _mark_backfill_complete_sync(db, last_watermark, now=now)
        return
    await asyncio.to_thread(
        _with_connection,
        _path(db, "db"),
        _mark_backfill_complete_sync,
        last_watermark,
        now=now,
    )


def ensure_backfill_state_row(connection: sqlite3.Connection, *, now: int | None = None) -> None:
    timestamp = _timestamp(now)
    connection.execute(
        """
INSERT INTO backfill_state (id, status, last_watermark, last_success_at, updated_at)
VALUES (1, ?, NULL, NULL, ?)
ON CONFLICT(id) DO NOTHING
        """,
        (BackfillStatus.PENDING.as_str(), timestamp),
    )
    connection.commit()


def _get_backfill_state_sync(connection: sqlite3.Connection) -> BackfillState:
    ensure_backfill_state_row(connection)
    row = connection.execute(
        """
SELECT status, last_watermark, last_success_at
FROM backfill_state
WHERE id = 1
        """
    ).fetchone()
    if row is None:
        raise LookupError("backfill_state row was not created")
    return BackfillState.try_from_row(
        {
            "status": row[0],
            "last_watermark": row[1],
            "last_success_at": row[2],
        }
    )


def _try_claim_backfill_sync(
    connection: sqlite3.Connection,
    lease_seconds: int,
    *,
    now: int | None = None,
) -> bool:
    ensure_backfill_state_row(connection, now=now)
    timestamp = _timestamp(now)
    lease = _required_i64(lease_seconds, "lease_seconds")
    lease_cutoff = _saturating_sub(timestamp, max(lease, 0))
    cursor = connection.execute(
        """
UPDATE backfill_state
SET status = ?, updated_at = ?
WHERE id = 1
  AND status != ?
  AND (status != ? OR updated_at <= ?)
        """,
        (
            BackfillStatus.RUNNING.as_str(),
            timestamp,
            BackfillStatus.COMPLETE.as_str(),
            BackfillStatus.RUNNING.as_str(),
            lease_cutoff,
        ),
    )
    connection.commit()
    return int(cursor.rowcount) == 1


def _mark_backfill_running_sync(connection: sqlite3.Connection, *, now: int | None = None) -> None:
    ensure_backfill_state_row(connection, now=now)
    connection.execute(
        """
UPDATE backfill_state
SET status = ?, updated_at = ?
WHERE id = 1
        """,
        (BackfillStatus.RUNNING.as_str(), _timestamp(now)),
    )
    connection.commit()


def _checkpoint_backfill_sync(
    connection: sqlite3.Connection,
    watermark: str,
    *,
    now: int | None = None,
) -> None:
    ensure_backfill_state_row(connection, now=now)
    connection.execute(
        """
UPDATE backfill_state
SET status = ?, last_watermark = ?, updated_at = ?
WHERE id = 1
        """,
        (BackfillStatus.RUNNING.as_str(), _required_str(watermark, "watermark"), _timestamp(now)),
    )
    connection.commit()


def _mark_backfill_complete_sync(
    connection: sqlite3.Connection,
    last_watermark: str | None,
    *,
    now: int | None = None,
) -> None:
    ensure_backfill_state_row(connection, now=now)
    timestamp = _timestamp(now)
    connection.execute(
        """
UPDATE backfill_state
SET
    status = ?,
    last_watermark = COALESCE(?, last_watermark),
    last_success_at = ?,
    updated_at = ?
WHERE id = 1
        """,
        (
            BackfillStatus.COMPLETE.as_str(),
            _optional_str(last_watermark, "last_watermark"),
            timestamp,
            timestamp,
        ),
    )
    connection.commit()


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


def _timestamp(value: int | None) -> int:
    return int(time.time()) if value is None else _required_i64(value, "now")


def _saturating_sub(value: int, amount: int) -> int:
    return max(-(2**63), value - amount)


__all__ = [
    "checkpoint_backfill",
    "ensure_backfill_state_row",
    "get_backfill_state",
    "mark_backfill_complete",
    "mark_backfill_running",
    "try_claim_backfill",
]
