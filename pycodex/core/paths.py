"""Codex home and runtime database paths.

Ported from:

- ``codex/codex-rs/utils/home-dir/src/lib.rs``
- ``codex/codex-rs/state/src/lib.rs``
- ``codex/codex-rs/state/src/runtime.rs``
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


CODEX_HOME_ENV = "CODEX_HOME"
STATE_DB_FILENAME = "state_5.sqlite"
LOGS_DB_FILENAME = "logs_2.sqlite"
GOALS_DB_FILENAME = "goals_1.sqlite"


@dataclass(frozen=True)
class RuntimeDbPath:
    label: str
    path: Path


def find_codex_home(env: dict[str, str] | None = None, home: Path | None = None) -> Path:
    """Return ``CODEX_HOME`` or ``~/.codex`` using upstream validation rules."""

    environ = os.environ if env is None else env
    raw = environ.get(CODEX_HOME_ENV)
    if raw:
        path = Path(raw)
        if not path.exists():
            raise FileNotFoundError(f"CODEX_HOME points to {raw!r}, but that path does not exist")
        if not path.is_dir():
            raise NotADirectoryError(f"CODEX_HOME points to {raw!r}, but that path is not a directory")
        return path.resolve()

    base_home = Path.home() if home is None else Path(home)
    return base_home / ".codex"


def state_db_path(codex_home: Path) -> Path:
    return Path(codex_home) / STATE_DB_FILENAME


def logs_db_path(codex_home: Path) -> Path:
    return Path(codex_home) / LOGS_DB_FILENAME


def goals_db_path(codex_home: Path) -> Path:
    return Path(codex_home) / GOALS_DB_FILENAME


def runtime_db_paths(codex_home: Path) -> list[RuntimeDbPath]:
    root = Path(codex_home)
    return [
        RuntimeDbPath("state DB", root / STATE_DB_FILENAME),
        RuntimeDbPath("log DB", root / LOGS_DB_FILENAME),
        RuntimeDbPath("goals DB", root / GOALS_DB_FILENAME),
    ]
