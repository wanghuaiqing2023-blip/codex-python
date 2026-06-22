"""StateRuntime facade ported from ``codex-state/src/runtime.rs``."""

from __future__ import annotations

import asyncio
import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .migrations import (
    Migrator,
    runtime_goals_migrator,
    runtime_logs_migrator,
    runtime_memories_migrator,
    runtime_state_migrator,
)
from .runtime import (
    AgentJobStore,
    GoalStore,
    MemoryStore,
    RuntimeLogStore,
    RuntimeThreadStore,
)
from .runtime.backfill import ensure_backfill_state_row
from .runtime.memories import clear_memory_data_in_connection

JsonValue = Any
STATE_DB_FILENAME = "state_5.sqlite"
LOGS_DB_FILENAME = "logs_2.sqlite"
GOALS_DB_FILENAME = "goals_1.sqlite"
MEMORIES_DB_FILENAME = "memories_1.sqlite"


@dataclass(frozen=True)
class RuntimeDbSpec:
    label: str
    filename: str
    kind: str
    open_phase: str
    migrate_phase: str

    def path(self, codex_home: Path | str) -> Path:
        return _path(codex_home, "codex_home") / self.filename


STATE_DB = RuntimeDbSpec("state DB", STATE_DB_FILENAME, "state", "open_state", "migrate_state")
LOGS_DB = RuntimeDbSpec("log DB", LOGS_DB_FILENAME, "logs", "open_logs", "migrate_logs")
GOALS_DB = RuntimeDbSpec("goals DB", GOALS_DB_FILENAME, "goals", "open_goals", "migrate_goals")
MEMORIES_DB = RuntimeDbSpec("memories DB", MEMORIES_DB_FILENAME, "memories", "open_memories", "migrate_memories")
RUNTIME_DBS = (STATE_DB, LOGS_DB, GOALS_DB, MEMORIES_DB)


@dataclass(frozen=True)
class RuntimeDbPath:
    label: str
    path: Path


class StateRuntime:
    """Dependency-light runtime container for the four codex-state SQLite DBs."""

    def __init__(
        self,
        *,
        codex_home: Path,
        default_provider: str,
        state_db: sqlite3.Connection,
        logs_db: sqlite3.Connection,
        goals_db: sqlite3.Connection,
        memories_db: sqlite3.Connection,
        thread_updated_at_millis: int = 0,
    ):
        self._codex_home = codex_home
        self.default_provider = _required_str(default_provider, "default_provider")
        self.state_db = state_db
        self.logs_db = logs_db
        self.goals_db = goals_db
        self.memories_db = memories_db
        self.thread_goals = GoalStore(goals_db)
        self.memories = MemoryStore(memories_db, state_db)
        self.logs = RuntimeLogStore(logs_db)
        self.threads = RuntimeThreadStore(
            state_db,
            default_provider=self.default_provider,
            memories=self.memories,
            thread_goals=self.thread_goals,
        )
        self.threads._thread_updated_at_millis = thread_updated_at_millis
        self.agent_jobs = AgentJobStore(state_db)

    @classmethod
    async def init(cls, codex_home: Path | str, default_provider: str) -> "StateRuntime":
        root = _path(codex_home, "codex_home")
        await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
        state_db = await open_state_sqlite(STATE_DB.path(root))
        logs_db = await open_logs_sqlite(LOGS_DB.path(root))
        goals_db = await open_goals_sqlite(GOALS_DB.path(root))
        memories_db = await open_memories_sqlite(MEMORIES_DB.path(root))
        ensure_backfill_state_row(state_db)
        thread_updated_at_millis = _max_thread_updated_at_millis(state_db)
        runtime = cls(
            codex_home=root,
            default_provider=default_provider,
            state_db=state_db,
            logs_db=logs_db,
            goals_db=goals_db,
            memories_db=memories_db,
            thread_updated_at_millis=thread_updated_at_millis,
        )
        try:
            await runtime.logs.run_logs_startup_maintenance()
        except sqlite3.Error:
            pass
        return runtime

    def codex_home(self) -> Path:
        return self._codex_home

    async def close(self) -> None:
        for connection in (self.state_db, self.logs_db, self.goals_db, self.memories_db):
            await asyncio.to_thread(connection.close)

    @staticmethod
    async def clear_memory_data_in_sqlite_home(sqlite_home: Path | str) -> bool:
        root = _path(sqlite_home, "sqlite_home")
        memories_path = MEMORIES_DB.path(root)
        if not memories_path.exists():
            return False
        connection = await open_memories_sqlite(memories_path)
        try:
            clear_memory_data_in_connection(connection)
            connection.commit()
        finally:
            connection.close()
        return True


async def open_state_sqlite(path: Path | str) -> sqlite3.Connection:
    return await open_sqlite(path, runtime_state_migrator())


async def open_logs_sqlite(path: Path | str) -> sqlite3.Connection:
    return await open_sqlite(path, runtime_logs_migrator())


async def open_goals_sqlite(path: Path | str) -> sqlite3.Connection:
    return await open_sqlite(path, runtime_goals_migrator())


async def open_memories_sqlite(path: Path | str) -> sqlite3.Connection:
    return await open_sqlite(path, runtime_memories_migrator())


async def open_sqlite(path: Path | str, migrator: Migrator | None = None) -> sqlite3.Connection:
    if migrator is not None and not isinstance(migrator, Migrator):
        raise TypeError("migrator must be a Migrator or None")
    return await asyncio.to_thread(_open_sqlite_sync, _path(path, "path"), migrator)


def state_db_path(codex_home: Path | str) -> Path:
    return STATE_DB.path(codex_home)


def logs_db_path(codex_home: Path | str) -> Path:
    return LOGS_DB.path(codex_home)


def goals_db_path(codex_home: Path | str) -> Path:
    return GOALS_DB.path(codex_home)


def memories_db_path(codex_home: Path | str) -> Path:
    return MEMORIES_DB.path(codex_home)


def runtime_db_paths(codex_home: Path | str) -> list[RuntimeDbPath]:
    root = _path(codex_home, "codex_home")
    return [RuntimeDbPath(spec.label, spec.path(root)) for spec in RUNTIME_DBS]


async def sqlite_integrity_check(path: Path | str) -> list[str]:
    db_path = _path(path, "path")
    return await asyncio.to_thread(_sqlite_integrity_check_sync, db_path)


def _open_sqlite_sync(path: Path, migrator: Migrator | None = None) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA auto_vacuum=INCREMENTAL")
    if migrator is not None:
        _run_sql_migrations(connection, migrator)
    return connection


def _run_sql_migrations(connection: sqlite3.Connection, migrator: Migrator) -> None:
    source_dir = _resolve_migration_dir(migrator)
    if source_dir is None:
        if migrator.ignore_missing:
            return
        raise FileNotFoundError(f"migration directory not found: {migrator.migrations_path}")
    table = migrator.table_name
    connection.execute(
        f"""
CREATE TABLE IF NOT EXISTS {table} (
    version BIGINT PRIMARY KEY,
    description TEXT NOT NULL,
    installed_on TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    success BOOLEAN NOT NULL,
    checksum BLOB NOT NULL,
    execution_time BIGINT NOT NULL
)
        """
    )
    applied = {
        int(row[0])
        for row in connection.execute(f"SELECT version FROM {table} WHERE success = 1").fetchall()
    }
    migrations = sorted(source_dir.glob("*.sql"))
    for migration in migrations:
        parsed = _parse_migration_filename(migration)
        if parsed is None:
            continue
        version, description = parsed
        if version in applied:
            continue
        sql = migration.read_text(encoding="utf-8-sig")
        checksum = hashlib.sha384(sql.encode("utf-8")).digest()
        with connection:
            connection.executescript(sql)
            connection.execute(
                f"""
INSERT OR REPLACE INTO {table}
    (version, description, success, checksum, execution_time)
VALUES (?, ?, ?, ?, ?)
                """,
                (version, description, True, checksum, 0),
            )
        applied.add(version)


def _resolve_migration_dir(migrator: Migrator) -> Path | None:
    relative = migrator.migrations_path.removeprefix("./")
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "codex" / "codex-rs" / "state" / relative
        if candidate.is_dir():
            return candidate
    return None


def _parse_migration_filename(path: Path) -> tuple[int, str] | None:
    match = re.match(r"^(\d+)_(.+)\.sql$", path.name)
    if match is None:
        return None
    return int(match.group(1)), match.group(2).replace("_", " ")


def _sqlite_integrity_check_sync(path: Path) -> list[str]:
    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        return [str(row[0]) for row in connection.execute("PRAGMA integrity_check").fetchall()]
    finally:
        connection.close()


def _max_thread_updated_at_millis(connection: sqlite3.Connection) -> int:
    try:
        row = connection.execute("SELECT MAX(threads.updated_at_ms) FROM threads").fetchone()
    except sqlite3.Error:
        return 0
    return 0 if row is None or row[0] is None else int(row[0])


def _path(value: JsonValue, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} must be a string or Path")
    return Path(value)


def _required_str(value: JsonValue, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


__all__ = [
    "GOALS_DB",
    "LOGS_DB",
    "MEMORIES_DB",
    "RUNTIME_DBS",
    "RuntimeDbPath",
    "RuntimeDbSpec",
    "STATE_DB",
    "StateRuntime",
    "goals_db_path",
    "logs_db_path",
    "memories_db_path",
    "open_goals_sqlite",
    "open_logs_sqlite",
    "open_memories_sqlite",
    "open_sqlite",
    "open_state_sqlite",
    "runtime_db_paths",
    "sqlite_integrity_check",
    "state_db_path",
]
