import asyncio
import sqlite3
from pathlib import Path

from pycodex.state import (
    MEMORIES_DB_FILENAME,
    STATE_DB_FILENAME,
    StateRuntime,
    open_memories_sqlite,
    open_state_sqlite,
    open_sqlite,
    runtime_db_paths,
    sqlite_integrity_check,
)


def _run(coro):
    return asyncio.run(coro)


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    return {
        int(row[0])
        for row in connection.execute(
            "SELECT version FROM _sqlx_migrations WHERE success = 1"
        )
    }


def test_state_runtime_init_applies_rust_runtime_migrations(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/test: src/runtime.rs::init_records_successful_sqlite_init_phases_to_explicit_telemetry
    # Behavior contract: StateRuntime::init opens all runtime DBs, runs their migrators,
    # seeds backfill state, and can be called again on already-migrated DBs.
    async def scenario() -> None:
        first = await StateRuntime.init(tmp_path, "openai")
        await first.close()

        runtime = await StateRuntime.init(tmp_path, "openai")
        try:
            assert [(p.label, p.path.name) for p in runtime_db_paths(tmp_path)] == [
                ("state DB", "state_5.sqlite"),
                ("log DB", "logs_2.sqlite"),
                ("goals DB", "goals_1.sqlite"),
                ("memories DB", "memories_1.sqlite"),
            ]
            assert {"threads", "backfill_state", "_sqlx_migrations"} <= _table_names(
                runtime.state_db
            )
            assert {"logs", "_sqlx_migrations"} <= _table_names(runtime.logs_db)
            assert {"thread_goals", "_sqlx_migrations"} <= _table_names(runtime.goals_db)
            assert {"stage1_outputs", "jobs", "_sqlx_migrations"} <= _table_names(
                runtime.memories_db
            )
            assert max(_applied_versions(runtime.state_db)) >= 35
            assert max(_applied_versions(runtime.logs_db)) >= 2
            assert _applied_versions(runtime.goals_db) == {1}
            assert _applied_versions(runtime.memories_db) == {1}
            assert [
                row[0]
                for row in runtime.state_db.execute(
                    "SELECT status FROM backfill_state WHERE id = 1"
                )
            ] == ["pending"]
        finally:
            await runtime.close()

    _run(scenario())


def test_open_state_sqlite_tolerates_newer_applied_migrations(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/test: src/runtime.rs::open_state_sqlite_tolerates_newer_applied_migrations
    # Behavior contract: runtime migrators tolerate newer applied migration rows.
    async def scenario() -> None:
        state_path = tmp_path / STATE_DB_FILENAME
        connection = await open_state_sqlite(state_path)
        try:
            connection.execute(
                """
INSERT INTO _sqlx_migrations
    (version, description, success, checksum, execution_time)
VALUES (?, ?, ?, ?, ?)
                """,
                (9999, "future migration", True, b"\x01\x02\x03\x04", 1),
            )
            connection.commit()
        finally:
            connection.close()

        reopened = await open_state_sqlite(state_path)
        try:
            assert 9999 in _applied_versions(reopened)
            assert "threads" in _table_names(reopened)
        finally:
            reopened.close()

    _run(scenario())


def test_sqlite_integrity_check_reports_ok_for_valid_db(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/test: src/runtime.rs::sqlite_integrity_check_reports_ok_for_valid_db
    # Behavior contract: sqlite_integrity_check opens an existing DB read-only and returns rows.
    async def scenario() -> None:
        db_path = tmp_path / "sample.sqlite"
        connection = await open_sqlite(db_path)
        try:
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()

        assert await sqlite_integrity_check(db_path) == ["ok"]

    _run(scenario())


def test_clear_memory_data_in_sqlite_home_clears_memory_tables(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime.rs::StateRuntime::clear_memory_data_in_sqlite_home
    # Behavior contract: clearing an existing memories DB removes memory rows and
    # returns false when the DB does not exist.
    async def scenario() -> None:
        missing_home = tmp_path / "missing"
        assert await StateRuntime.clear_memory_data_in_sqlite_home(missing_home) is False

        runtime = await StateRuntime.init(tmp_path, "openai")
        await runtime.close()

        memories_path = tmp_path / MEMORIES_DB_FILENAME
        connection = await open_memories_sqlite(memories_path)
        try:
            connection.execute(
                """
INSERT INTO stage1_outputs
    (thread_id, source_updated_at, raw_memory, rollout_summary, generated_at)
VALUES (?, ?, ?, ?, ?)
                """,
                ("thread-1", 1, "memory", "summary", 2),
            )
            connection.execute(
                """
INSERT INTO jobs (kind, job_key, status, retry_remaining)
VALUES (?, ?, ?, ?)
                """,
                ("memory_consolidate_global", "singleton", "pending", 3),
            )
            connection.commit()
        finally:
            connection.close()

        assert await StateRuntime.clear_memory_data_in_sqlite_home(tmp_path) is True

        reopened = await open_memories_sqlite(memories_path)
        try:
            assert reopened.execute("SELECT COUNT(*) FROM stage1_outputs").fetchone()[0] == 0
            assert reopened.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
        finally:
            reopened.close()

    _run(scenario())
