import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta

import pycodex.state.runtime.logs as logs_module
from pycodex.state.model import LogEntry, LogQuery
from pycodex.state.runtime.logs import RuntimeLogStore, format_feedback_log_line


def _run(coro):
    return asyncio.run(coro)


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts INTEGER NOT NULL,
    ts_nanos INTEGER NOT NULL,
    level TEXT NOT NULL,
    target TEXT NOT NULL,
    feedback_log_body TEXT,
    module_path TEXT,
    file TEXT,
    line INTEGER,
    thread_id TEXT,
    process_uuid TEXT,
    estimated_bytes INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_logs_ts ON logs(ts DESC, ts_nanos DESC, id DESC);
CREATE INDEX idx_logs_thread_id ON logs(thread_id);
CREATE INDEX idx_logs_thread_id_ts ON logs(thread_id, ts DESC, ts_nanos DESC, id DESC);
CREATE INDEX idx_logs_process_uuid_threadless_ts ON logs(process_uuid, ts DESC, ts_nanos DESC, id DESC)
WHERE thread_id IS NULL;
        """
    )
    return connection


def _entry(
    ts: int,
    body: str,
    *,
    level: str = "INFO",
    thread_id: str | None = "thread-1",
    process_uuid: str | None = "process-1",
    target: str = "codex",
    module_path: str | None = "codex.state",
    file: str | None = "state.py",
) -> LogEntry:
    return LogEntry(
        ts=ts,
        ts_nanos=ts,
        level=level,
        target=target,
        message=f"message {body}",
        feedback_log_body=body,
        thread_id=thread_id,
        process_uuid=process_uuid,
        module_path=module_path,
        file=file,
        line=ts,
    )


def test_insert_query_search_and_max_log_id() -> None:
    # Rust crate: codex-state
    # Rust module/tests:
    # src/runtime/logs.rs::insert_logs_use_dedicated_log_database
    # src/runtime/logs.rs::query_logs_with_search_matches_rendered_body_substring
    # src/runtime/logs.rs::query_logs_filters_level_set_without_rewriting_stored_level
    # Behavior contract: insertion stores feedback-body fallback/search data,
    # query filters compose without rewriting levels, and max id honors filters.
    store = RuntimeLogStore(_connection())

    _run(
        store.insert_logs(
            [
                LogEntry(ts=10, ts_nanos=0, level="info", target="codex", message="fallback body", thread_id="thread-1"),
                _entry(11, "needle body", level="WARN", file="worker.py"),
                _entry(12, "other body", level="ERROR", thread_id=None, process_uuid="process-1"),
            ]
        )
    )

    search_rows = _run(store.query_logs(LogQuery(search="needle", thread_ids=("thread-1",))))
    warn_rows = _run(store.query_logs(LogQuery(levels_upper=("WARN",), file_like=("worker",), descending=True)))
    max_warn = _run(store.max_log_id(LogQuery(levels_upper=("WARN",))))

    assert [row.message for row in search_rows] == ["needle body"]
    assert [row.level for row in warn_rows] == ["WARN"]
    assert max_warn == warn_rows[0].id
    assert _run(store.max_log_id(LogQuery(search="missing"))) == 0


def test_format_feedback_log_line_matches_rust_shape() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime/logs.rs::format_feedback_log_line
    # Behavior contract: feedback lines use UTC RFC3339 microseconds, padded
    # level text, body text, and exactly one trailing newline.
    assert format_feedback_log_line(1_700_000_000, 123_456_789, "INFO", "hello").endswith("  INFO hello\n")
    assert format_feedback_log_line(1_700_000_000, 0, "WARN", "already\n").endswith("  WARN already\n")


def test_query_feedback_logs_includes_latest_process_threadless_rows() -> None:
    # Rust crate: codex-state
    # Rust module/tests:
    # query_feedback_logs_includes_threadless_rows_from_same_process
    # query_feedback_logs_excludes_threadless_rows_from_prior_processes
    # Behavior contract: feedback export includes requested thread rows plus
    # threadless rows from the latest process UUID observed for that thread.
    store = RuntimeLogStore(_connection())
    _run(
        store.insert_logs(
            [
                _entry(10, "old process thread", process_uuid="old"),
                _entry(11, "old process threadless", thread_id=None, process_uuid="old"),
                _entry(20, "new process thread", process_uuid="new"),
                _entry(21, "new process threadless", thread_id=None, process_uuid="new"),
            ]
        )
    )

    exported = _run(store.query_feedback_logs("thread-1")).decode()

    assert "old process thread\n" in exported
    assert "new process thread\n" in exported
    assert "new process threadless\n" in exported
    assert "old process threadless" not in exported


def test_query_feedback_logs_for_threads_returns_empty_for_empty_thread_list() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/runtime/logs.rs::query_feedback_logs_for_threads_returns_empty_for_empty_thread_list
    store = RuntimeLogStore(_connection())

    assert _run(store.query_feedback_logs_for_threads([])) == b""


def test_startup_maintenance_deletes_old_logs_and_checkpoints() -> None:
    # Rust crate: codex-state
    # Rust module/items: delete_logs_before and run_logs_startup_maintenance
    # Behavior contract: startup maintenance deletes rows older than the
    # retention window and issues a passive WAL checkpoint.
    connection = _connection()
    store = RuntimeLogStore(connection)
    now = datetime(2026, 1, 20, tzinfo=UTC)
    old_ts = int((now - timedelta(days=logs_module.LOG_RETENTION_DAYS + 1)).timestamp())
    fresh_ts = int((now - timedelta(days=1)).timestamp())
    _run(store.insert_logs([_entry(old_ts, "old"), _entry(fresh_ts, "fresh")]))

    _run(store.run_logs_startup_maintenance(now=now))

    rows = _run(store.query_logs())
    assert [row.message for row in rows] == ["fresh"]


def test_insert_logs_prunes_thread_partition_by_row_limit(monkeypatch) -> None:
    # Rust crate: codex-state
    # Rust module/test: insert_logs_prunes_old_rows_when_thread_exceeds_row_limit
    # Behavior contract: pruning keeps newest rows in a thread partition by
    # ts/ts_nanos/id ordering.
    monkeypatch.setattr(logs_module, "LOG_PARTITION_ROW_LIMIT", 2)
    store = RuntimeLogStore(_connection())

    _run(store.insert_logs([_entry(1, "old"), _entry(2, "middle"), _entry(3, "new")]))

    rows = _run(store.query_logs(LogQuery(thread_ids=("thread-1",))))
    assert [row.message for row in rows] == ["middle", "new"]


def test_insert_logs_prunes_threadless_rows_per_process_uuid_only(monkeypatch) -> None:
    # Rust crate: codex-state
    # Rust module/test: insert_logs_prunes_threadless_rows_per_process_uuid_only
    # Behavior contract: threadless pruning is partitioned by process UUID and
    # does not delete rows from neighboring process partitions.
    monkeypatch.setattr(logs_module, "LOG_PARTITION_ROW_LIMIT", 1)
    store = RuntimeLogStore(_connection())

    _run(
        store.insert_logs(
            [
                _entry(1, "p1-old", thread_id=None, process_uuid="p1"),
                _entry(2, "p1-new", thread_id=None, process_uuid="p1"),
                _entry(1, "p2-only", thread_id=None, process_uuid="p2"),
            ]
        )
    )

    rows = _run(store.query_logs(LogQuery(include_threadless=True)))
    assert [row.message for row in rows] == ["p1-new", "p2-only"]
