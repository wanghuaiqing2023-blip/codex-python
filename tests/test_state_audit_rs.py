import asyncio
import sqlite3
from pathlib import Path

import pytest

from pycodex.state import ThreadStateAuditRow, read_thread_state_audit_rows


def _create_state_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
CREATE TABLE threads (
    id TEXT NOT NULL,
    rollout_path TEXT NOT NULL,
    archived INTEGER NOT NULL,
    source TEXT NOT NULL,
    model_provider TEXT NOT NULL
)
            """
        )
        connection.executemany(
            """
INSERT INTO threads (id, rollout_path, archived, source, model_provider)
VALUES (?, ?, ?, ?, ?)
            """,
            [
                ("thread-1", "/tmp/rollout-1.jsonl", 0, "cli", "openai"),
                ("thread-2", "/tmp/rollout-2.jsonl", 2, "exec", "test-provider"),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_thread_state_audit_row_validates_and_normalizes_path() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/audit.rs::ThreadStateAuditRow
    # Behavior contract: audit rows contain id, rollout path, archived bool,
    # source, and model provider.
    row = ThreadStateAuditRow(
        id="thread-1",
        rollout_path="/tmp/rollout.jsonl",
        archived=True,
        source="cli",
        model_provider="openai",
    )

    assert row.rollout_path == Path("/tmp/rollout.jsonl")
    assert row.archived is True


def test_read_thread_state_audit_rows_selects_rust_columns_and_archived_bool(tmp_path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/audit.rs::read_thread_state_audit_rows
    # Behavior contract: read-only audit query selects id/rollout_path/archived/
    # source/model_provider and converts archived integer values to bool.
    db_path = tmp_path / "state_5.sqlite"
    _create_state_db(db_path)

    rows = asyncio.run(read_thread_state_audit_rows(db_path))

    assert rows == [
        ThreadStateAuditRow(
            id="thread-1",
            rollout_path=Path("/tmp/rollout-1.jsonl"),
            archived=False,
            source="cli",
            model_provider="openai",
        ),
        ThreadStateAuditRow(
            id="thread-2",
            rollout_path=Path("/tmp/rollout-2.jsonl"),
            archived=True,
            source="exec",
            model_provider="test-provider",
        ),
    ]


def test_read_thread_state_audit_rows_does_not_create_missing_db(tmp_path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/audit.rs::read_thread_state_audit_rows
    # Behavior contract: the audit reader opens without create/migrate/repair.
    missing = tmp_path / "missing.sqlite"

    with pytest.raises(FileNotFoundError):
        asyncio.run(read_thread_state_audit_rows(missing))

    assert not missing.exists()


def test_read_thread_state_audit_rows_rejects_invalid_storage_types(tmp_path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/audit.rs::read_thread_state_audit_rows
    # Behavior contract: row conversion requires string columns and an integer
    # archived column rather than silently accepting incompatible storage data.
    db_path = tmp_path / "state_5.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            """
CREATE TABLE threads (
    id TEXT,
    rollout_path TEXT,
    archived TEXT,
    source TEXT,
    model_provider TEXT
)
            """
        )
        connection.execute(
            """
INSERT INTO threads (id, rollout_path, archived, source, model_provider)
VALUES ('thread-1', '/tmp/rollout.jsonl', 'yes', 'cli', 'openai')
            """
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(TypeError, match="archived must be an integer"):
        asyncio.run(read_thread_state_audit_rows(db_path))
