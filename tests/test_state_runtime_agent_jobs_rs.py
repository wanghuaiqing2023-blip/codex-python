import asyncio
import sqlite3
from pathlib import Path

from pycodex.state.model.agent_job import (
    AgentJobCreateParams,
    AgentJobItemCreateParams,
    AgentJobItemStatus,
    AgentJobProgress,
    AgentJobStatus,
)
from pycodex.state.runtime.agent_jobs import AgentJobStore


def _run(coro):
    return asyncio.run(coro)


def _connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
CREATE TABLE agent_jobs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL,
    instruction TEXT NOT NULL,
    output_schema_json TEXT,
    input_headers_json TEXT NOT NULL,
    input_csv_path TEXT NOT NULL,
    output_csv_path TEXT NOT NULL,
    auto_export INTEGER NOT NULL DEFAULT 1,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    started_at INTEGER,
    completed_at INTEGER,
    last_error TEXT,
    max_runtime_seconds INTEGER
);

CREATE TABLE agent_job_items (
    job_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    row_index INTEGER NOT NULL,
    source_id TEXT,
    row_json TEXT NOT NULL,
    status TEXT NOT NULL,
    assigned_thread_id TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    result_json TEXT,
    last_error TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    completed_at INTEGER,
    reported_at INTEGER,
    PRIMARY KEY (job_id, item_id),
    FOREIGN KEY(job_id) REFERENCES agent_jobs(id) ON DELETE CASCADE
);

CREATE INDEX idx_agent_jobs_status ON agent_jobs(status, updated_at DESC);
CREATE INDEX idx_agent_job_items_status ON agent_job_items(job_id, status, row_index ASC);
        """
    )
    return connection


def _params() -> AgentJobCreateParams:
    return AgentJobCreateParams(
        id="job-1",
        name="job",
        instruction="do work",
        auto_export=True,
        max_runtime_seconds=120,
        output_schema_json={"type": "object"},
        input_headers=("name", "city"),
        input_csv_path="input.csv",
        output_csv_path="output.csv",
    )


def _items() -> list[AgentJobItemCreateParams]:
    return [
        AgentJobItemCreateParams(
            item_id="item-1",
            row_index=0,
            source_id="source-1",
            row_json={"name": "Ada", "city": "London"},
        )
    ]


def _create_running_single_item_job(store: AgentJobStore) -> None:
    _run(store.create_agent_job(_params(), _items(), now=100))
    _run(store.mark_agent_job_running("job-1", now=101))
    assert _run(store.mark_agent_job_item_running_with_thread("job-1", "item-1", "thread-1", now=102))


def test_create_agent_job_persists_job_and_initial_items() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime/agent_jobs.rs::create_agent_job
    # Behavior contract: creating a job inserts the job and pending items in
    # one runtime-store surface using JSON fields and epoch-second timestamps.
    store = AgentJobStore(_connection())

    job = _run(store.create_agent_job(_params(), _items(), now=100))
    items = _run(store.list_agent_job_items("job-1"))

    assert job.id == "job-1"
    assert job.status is AgentJobStatus.PENDING
    assert job.max_runtime_seconds == 120
    assert job.output_schema_json == {"type": "object"}
    assert job.input_headers == ("name", "city")
    assert job.created_at.timestamp() == 100
    assert len(items) == 1
    assert items[0].status is AgentJobItemStatus.PENDING
    assert items[0].row_json == {"name": "Ada", "city": "London"}
    assert items[0].attempt_count == 0


def test_report_agent_job_item_result_completes_item_atomically() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/runtime/agent_jobs.rs::report_agent_job_item_result_completes_item_atomically
    # Behavior contract: a report from the assigned running thread stores the
    # result, clears assignment/error fields, completes the item, and updates
    # progress in the same accepted transition.
    store = AgentJobStore(_connection())
    _create_running_single_item_job(store)

    accepted = _run(store.report_agent_job_item_result("job-1", "item-1", "thread-1", {"ok": True}, now=103))

    item = _run(store.get_agent_job_item("job-1", "item-1"))
    progress = _run(store.get_agent_job_progress("job-1"))
    assert accepted is True
    assert item is not None
    assert item.status is AgentJobItemStatus.COMPLETED
    assert item.result_json == {"ok": True}
    assert item.assigned_thread_id is None
    assert item.last_error is None
    assert item.reported_at is not None
    assert item.completed_at is not None
    assert progress == AgentJobProgress(
        total_items=1,
        pending_items=0,
        running_items=0,
        completed_items=1,
        failed_items=0,
    )


def test_report_agent_job_item_result_rejects_late_reports() -> None:
    # Rust crate: codex-state
    # Rust module/test:
    # src/runtime/agent_jobs.rs::report_agent_job_item_result_rejects_late_reports
    # Behavior contract: a late report after a running item has failed is
    # rejected and does not overwrite the failure state or result.
    store = AgentJobStore(_connection())
    _create_running_single_item_job(store)

    assert _run(store.mark_agent_job_item_failed("job-1", "item-1", "missing report", now=103))
    accepted = _run(store.report_agent_job_item_result("job-1", "item-1", "thread-1", {"late": True}, now=104))

    item = _run(store.get_agent_job_item("job-1", "item-1"))
    assert accepted is False
    assert item is not None
    assert item.status is AgentJobItemStatus.FAILED
    assert item.result_json is None
    assert item.last_error == "missing report"


def test_agent_job_runtime_transitions_and_filters() -> None:
    # Rust crate: codex-state
    # Rust module/items: src/runtime/agent_jobs.rs job and item status helpers
    # Behavior contract: job cancellation is limited to pending/running jobs,
    # item list filters use Rust status names, and invalid limits are rejected.
    store = AgentJobStore(_connection())
    _run(store.create_agent_job(_params(), _items(), now=100))

    assert _run(store.mark_agent_job_cancelled("job-1", "user requested", now=101)) is True
    assert _run(store.is_agent_job_cancelled("job-1")) is True
    assert _run(store.mark_agent_job_cancelled("job-1", "again", now=102)) is False
    cancelled = _run(store.get_agent_job("job-1"))
    pending_items = _run(store.list_agent_job_items("job-1", AgentJobItemStatus.PENDING, limit=1))

    assert cancelled is not None
    assert cancelled.status is AgentJobStatus.CANCELLED
    assert cancelled.last_error == "user requested"
    assert len(pending_items) == 1


def test_agent_job_store_accepts_database_path(tmp_path: Path) -> None:
    # Rust crate: codex-state
    # Rust module/item: src/runtime/agent_jobs.rs StateRuntime persistence path
    # Behavior contract: the Python store can reopen a SQLite path-backed DB
    # while preserving the same row conversion surface.
    db_path = tmp_path / "state.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript("".join(line for line in _connection().iterdump()))
    finally:
        connection.close()

    store = AgentJobStore(db_path)
    job = _run(store.create_agent_job(_params(), _items(), now=100))

    assert job.id == "job-1"
