"""Read-only state database audit helpers ported from ``codex-state/src/audit.rs``."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class ThreadStateAuditRow:
    id: str
    rollout_path: Path
    archived: bool
    source: str
    model_provider: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", _required_str(self.id, "id"))
        object.__setattr__(self, "rollout_path", _path(self.rollout_path, "rollout_path"))
        if not isinstance(self.archived, bool):
            raise TypeError("archived must be a bool")
        object.__setattr__(self, "source", _required_str(self.source, "source"))
        object.__setattr__(self, "model_provider", _required_str(self.model_provider, "model_provider"))


async def read_thread_state_audit_rows(path: Path | str) -> list[ThreadStateAuditRow]:
    db_path = _path(path, "path")
    return await asyncio.to_thread(_read_thread_state_audit_rows_sync, db_path)


def _read_thread_state_audit_rows_sync(path: Path) -> list[ThreadStateAuditRow]:
    if not path.exists():
        raise FileNotFoundError(path)
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute(
            """
SELECT id, rollout_path, archived, source, model_provider
FROM threads
            """
        ).fetchall()
    finally:
        connection.close()
    return [
        ThreadStateAuditRow(
            id=_required_str(row[0], "id"),
            rollout_path=_required_str(row[1], "rollout_path"),
            archived=bool(_required_i64(row[2], "archived")),
            source=_required_str(row[3], "source"),
            model_provider=_required_str(row[4], "model_provider"),
        )
        for row in rows
    ]


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


__all__ = ["ThreadStateAuditRow", "read_thread_state_audit_rows"]
