"""Remote-control enrollment store helpers ported from ``codex-state/src/runtime/remote_control.rs``."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonValue = Any

REMOTE_CONTROL_APP_SERVER_CLIENT_NAME_NONE = ""


@dataclass(frozen=True)
class RemoteControlEnrollmentRecord:
    websocket_url: str
    account_id: str
    app_server_client_name: str | None
    server_id: str
    environment_id: str
    server_name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "websocket_url", _required_str(self.websocket_url, "websocket_url"))
        object.__setattr__(self, "account_id", _required_str(self.account_id, "account_id"))
        object.__setattr__(
            self,
            "app_server_client_name",
            _optional_str(self.app_server_client_name, "app_server_client_name"),
        )
        object.__setattr__(self, "server_id", _required_str(self.server_id, "server_id"))
        object.__setattr__(self, "environment_id", _required_str(self.environment_id, "environment_id"))
        object.__setattr__(self, "server_name", _required_str(self.server_name, "server_name"))


def remote_control_app_server_client_name_key(app_server_client_name: str | None) -> str:
    return REMOTE_CONTROL_APP_SERVER_CLIENT_NAME_NONE if app_server_client_name is None else _required_str(app_server_client_name, "app_server_client_name")


def app_server_client_name_from_key(app_server_client_name: str) -> str | None:
    app_server_client_name = _required_str(app_server_client_name, "app_server_client_name")
    return None if app_server_client_name == "" else app_server_client_name


async def get_remote_control_enrollment(
    db: sqlite3.Connection | Path | str,
    websocket_url: str,
    account_id: str,
    app_server_client_name: str | None,
) -> RemoteControlEnrollmentRecord | None:
    if isinstance(db, sqlite3.Connection):
        return _get_remote_control_enrollment_sync(db, websocket_url, account_id, app_server_client_name)
    return await asyncio.to_thread(
        _with_connection,
        _path(db, "db"),
        _get_remote_control_enrollment_sync,
        websocket_url,
        account_id,
        app_server_client_name,
    )


async def upsert_remote_control_enrollment(
    db: sqlite3.Connection | Path | str,
    enrollment: RemoteControlEnrollmentRecord,
    *,
    updated_at: int | None = None,
) -> None:
    if isinstance(db, sqlite3.Connection):
        _upsert_remote_control_enrollment_sync(db, enrollment, updated_at=updated_at)
        return
    await asyncio.to_thread(
        _with_connection,
        _path(db, "db"),
        _upsert_remote_control_enrollment_sync,
        enrollment,
        updated_at=updated_at,
    )


async def delete_remote_control_enrollment(
    db: sqlite3.Connection | Path | str,
    websocket_url: str,
    account_id: str,
    app_server_client_name: str | None,
) -> int:
    if isinstance(db, sqlite3.Connection):
        return _delete_remote_control_enrollment_sync(db, websocket_url, account_id, app_server_client_name)
    return await asyncio.to_thread(
        _with_connection,
        _path(db, "db"),
        _delete_remote_control_enrollment_sync,
        websocket_url,
        account_id,
        app_server_client_name,
    )


def _get_remote_control_enrollment_sync(
    connection: sqlite3.Connection,
    websocket_url: str,
    account_id: str,
    app_server_client_name: str | None,
) -> RemoteControlEnrollmentRecord | None:
    row = connection.execute(
        """
SELECT websocket_url, account_id, app_server_client_name, server_id, environment_id, server_name
FROM remote_control_enrollments
WHERE websocket_url = ? AND account_id = ? AND app_server_client_name = ?
        """,
        (
            _required_str(websocket_url, "websocket_url"),
            _required_str(account_id, "account_id"),
            remote_control_app_server_client_name_key(app_server_client_name),
        ),
    ).fetchone()
    if row is None:
        return None
    return RemoteControlEnrollmentRecord(
        websocket_url=_required_str(row[0], "websocket_url"),
        account_id=_required_str(row[1], "account_id"),
        app_server_client_name=app_server_client_name_from_key(row[2]),
        server_id=_required_str(row[3], "server_id"),
        environment_id=_required_str(row[4], "environment_id"),
        server_name=_required_str(row[5], "server_name"),
    )


def _upsert_remote_control_enrollment_sync(
    connection: sqlite3.Connection,
    enrollment: RemoteControlEnrollmentRecord,
    *,
    updated_at: int | None = None,
) -> None:
    if not isinstance(enrollment, RemoteControlEnrollmentRecord):
        raise TypeError("enrollment must be RemoteControlEnrollmentRecord")
    timestamp = int(time.time()) if updated_at is None else _required_i64(updated_at, "updated_at")
    connection.execute(
        """
INSERT INTO remote_control_enrollments (
    websocket_url,
    account_id,
    app_server_client_name,
    server_id,
    environment_id,
    server_name,
    updated_at
) VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(websocket_url, account_id, app_server_client_name) DO UPDATE SET
    server_id = excluded.server_id,
    environment_id = excluded.environment_id,
    server_name = excluded.server_name,
    updated_at = excluded.updated_at
        """,
        (
            enrollment.websocket_url,
            enrollment.account_id,
            remote_control_app_server_client_name_key(enrollment.app_server_client_name),
            enrollment.server_id,
            enrollment.environment_id,
            enrollment.server_name,
            timestamp,
        ),
    )
    connection.commit()


def _delete_remote_control_enrollment_sync(
    connection: sqlite3.Connection,
    websocket_url: str,
    account_id: str,
    app_server_client_name: str | None,
) -> int:
    cursor = connection.execute(
        """
DELETE FROM remote_control_enrollments
WHERE websocket_url = ? AND account_id = ? AND app_server_client_name = ?
        """,
        (
            _required_str(websocket_url, "websocket_url"),
            _required_str(account_id, "account_id"),
            remote_control_app_server_client_name_key(app_server_client_name),
        ),
    )
    connection.commit()
    return int(cursor.rowcount)


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


__all__ = [
    "REMOTE_CONTROL_APP_SERVER_CLIENT_NAME_NONE",
    "RemoteControlEnrollmentRecord",
    "app_server_client_name_from_key",
    "delete_remote_control_enrollment",
    "get_remote_control_enrollment",
    "remote_control_app_server_client_name_key",
    "upsert_remote_control_enrollment",
]
