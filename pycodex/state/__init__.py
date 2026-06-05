"""State runtime path helpers.

Ported from the runtime path pieces of:

- ``codex/codex-rs/state/src/lib.rs``
- ``codex/codex-rs/state/src/runtime.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STATE_DB_FILENAME = "state_5.sqlite"
LOGS_DB_FILENAME = "logs_2.sqlite"
GOALS_DB_FILENAME = "goals_1.sqlite"
MEMORIES_DB_FILENAME = "memories_1.sqlite"


@dataclass(frozen=True)
class RuntimeDbPath:
    label: str
    path: Path


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


__all__ = [
    "GOALS_DB_FILENAME",
    "LOGS_DB_FILENAME",
    "MEMORIES_DB_FILENAME",
    "RuntimeDbPath",
    "STATE_DB_FILENAME",
    "goals_db_path",
    "logs_db_path",
    "memories_db_path",
    "runtime_db_paths",
    "state_db_path",
]