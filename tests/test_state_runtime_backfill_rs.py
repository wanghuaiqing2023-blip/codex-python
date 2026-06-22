import asyncio
import sqlite3
from datetime import datetime, timezone

from pycodex.state.model.backfill_state import BackfillState, BackfillStatus
from pycodex.state.runtime.backfill import (
    checkpoint_backfill,
    get_backfill_state,
    mark_backfill_complete,
    mark_backfill_running,
    try_claim_backfill,
)


def _create_backfill_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
CREATE TABLE backfill_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL,
    last_watermark TEXT,
    last_success_at INTEGER,
    updated_at INTEGER NOT NULL
)
        """
    )
    connection.commit()


def test_backfill_state_persists_progress_and_completion() -> None:
    # Rust: codex-state/src/runtime/backfill.rs
    # Test: backfill_state_persists_progress_and_completion
    connection = sqlite3.connect(":memory:")
    _create_backfill_schema(connection)

    initial = asyncio.run(get_backfill_state(connection))
    assert initial == BackfillState(
        status=BackfillStatus.PENDING,
        last_watermark=None,
        last_success_at=None,
    )

    asyncio.run(mark_backfill_running(connection, now=1_700_000_001))
    asyncio.run(
        checkpoint_backfill(
            connection,
            "sessions/2026/01/27/rollout-a.jsonl",
            now=1_700_000_002,
        )
    )

    running = asyncio.run(get_backfill_state(connection))
    assert running == BackfillState(
        status=BackfillStatus.RUNNING,
        last_watermark="sessions/2026/01/27/rollout-a.jsonl",
        last_success_at=None,
    )

    asyncio.run(
        mark_backfill_complete(
            connection,
            "sessions/2026/01/28/rollout-b.jsonl",
            now=1_700_000_003,
        )
    )
    completed = asyncio.run(get_backfill_state(connection))
    assert completed == BackfillState(
        status=BackfillStatus.COMPLETE,
        last_watermark="sessions/2026/01/28/rollout-b.jsonl",
        last_success_at=datetime.fromtimestamp(1_700_000_003, tz=timezone.utc),
    )


def test_backfill_claim_is_singleton_until_stale_and_blocked_when_complete() -> None:
    # Rust: codex-state/src/runtime/backfill.rs
    # Test: backfill_claim_is_singleton_until_stale_and_blocked_when_complete
    connection = sqlite3.connect(":memory:")
    _create_backfill_schema(connection)

    assert asyncio.run(try_claim_backfill(connection, 3600, now=20_000)) is True
    assert asyncio.run(try_claim_backfill(connection, 3600, now=20_100)) is False

    connection.execute(
        """
UPDATE backfill_state
SET status = ?, updated_at = ?
WHERE id = 1
        """,
        (BackfillStatus.RUNNING.as_str(), 10_000),
    )
    connection.commit()

    assert asyncio.run(try_claim_backfill(connection, 10, now=20_000)) is True

    asyncio.run(mark_backfill_complete(connection, None, now=20_001))
    assert asyncio.run(try_claim_backfill(connection, 3600, now=20_002)) is False


def test_mark_complete_without_watermark_preserves_previous_watermark() -> None:
    # Rust: mark_backfill_complete uses COALESCE(?, last_watermark).
    connection = sqlite3.connect(":memory:")
    _create_backfill_schema(connection)

    asyncio.run(checkpoint_backfill(connection, "rollout-before-complete", now=1_000))
    asyncio.run(mark_backfill_complete(connection, None, now=1_001))

    assert asyncio.run(get_backfill_state(connection)) == BackfillState(
        status=BackfillStatus.COMPLETE,
        last_watermark="rollout-before-complete",
        last_success_at=datetime.fromtimestamp(1_001, tz=timezone.utc),
    )


def test_negative_lease_seconds_behaves_like_zero_lease() -> None:
    # Rust clamps lease_seconds with lease_seconds.max(0) before cutoff math.
    connection = sqlite3.connect(":memory:")
    _create_backfill_schema(connection)

    assert asyncio.run(try_claim_backfill(connection, -10, now=100)) is True
    assert asyncio.run(try_claim_backfill(connection, -10, now=100)) is True


def test_path_database_mode_preserves_backfill_contract(tmp_path) -> None:
    # Python compatibility shim: async helpers may open a SQLite path directly
    # while keeping Rust's singleton row and lifecycle SQL behavior.
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    try:
        _create_backfill_schema(connection)
    finally:
        connection.close()

    assert asyncio.run(try_claim_backfill(db_path, 3600, now=2_000)) is True
    asyncio.run(checkpoint_backfill(db_path, "path-mode-watermark", now=2_001))

    assert asyncio.run(get_backfill_state(db_path)) == BackfillState(
        status=BackfillStatus.RUNNING,
        last_watermark="path-mode-watermark",
        last_success_at=None,
    )
