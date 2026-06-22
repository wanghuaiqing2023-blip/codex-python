from datetime import datetime, timezone

import pytest

from pycodex.state import (
    AgentJobCreateParams,
    AgentJobItemCreateParams,
    AgentJobItemRow,
    AgentJobItemStatus,
    AgentJobProgress,
    AgentJobRow,
    AgentJobStatus,
)
from pycodex.state.model.agent_job import epoch_seconds_to_datetime


def test_agent_job_status_wire_values_parse_and_finality() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/agent_job.rs::AgentJobStatus
    # Behavior contract: persisted job statuses and final-status predicate.
    assert AgentJobStatus.PENDING.as_str() == "pending"
    assert AgentJobStatus.RUNNING.as_str() == "running"
    assert AgentJobStatus.COMPLETED.as_str() == "completed"
    assert AgentJobStatus.FAILED.as_str() == "failed"
    assert AgentJobStatus.CANCELLED.as_str() == "cancelled"
    assert AgentJobStatus.parse("pending") is AgentJobStatus.PENDING
    assert AgentJobStatus.parse("cancelled") is AgentJobStatus.CANCELLED
    assert AgentJobStatus.PENDING.is_final() is False
    assert AgentJobStatus.RUNNING.is_final() is False
    assert AgentJobStatus.COMPLETED.is_final() is True
    assert AgentJobStatus.FAILED.is_final() is True
    assert AgentJobStatus.CANCELLED.is_final() is True


def test_agent_job_status_parse_rejects_unknown() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/agent_job.rs::{AgentJobStatus,AgentJobItemStatus}::parse
    # Behavior contract: unknown persisted status strings fail parsing.
    with pytest.raises(ValueError, match="invalid agent job status: paused"):
        AgentJobStatus.parse("paused")
    with pytest.raises(ValueError, match="invalid agent job item status: skipped"):
        AgentJobItemStatus.parse("skipped")


def test_agent_job_item_status_wire_values_and_parse() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/agent_job.rs::AgentJobItemStatus
    # Behavior contract: persisted item statuses are pending/running/completed/failed.
    assert AgentJobItemStatus.PENDING.as_str() == "pending"
    assert AgentJobItemStatus.RUNNING.as_str() == "running"
    assert AgentJobItemStatus.COMPLETED.as_str() == "completed"
    assert AgentJobItemStatus.FAILED.as_str() == "failed"
    assert AgentJobItemStatus.parse("completed") is AgentJobItemStatus.COMPLETED


def test_agent_job_row_converts_json_time_bool_and_u64_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/agent_job.rs::TryFrom<AgentJobRow> for AgentJob
    # Behavior contract: row-shaped strings/integers hydrate the domain model.
    job = AgentJobRow(
        id="job-1",
        name="Batch",
        status="running",
        instruction="Do it",
        auto_export=2,
        max_runtime_seconds=3600,
        output_schema_json='{"type":"object"}',
        input_headers_json='["id","prompt"]',
        input_csv_path="input.csv",
        output_csv_path="output.csv",
        created_at=1_700_000_000,
        updated_at=1_700_000_001,
        started_at=1_700_000_002,
        completed_at=None,
        last_error=None,
    ).to_agent_job()

    assert job.id == "job-1"
    assert job.status is AgentJobStatus.RUNNING
    assert job.auto_export is True
    assert job.max_runtime_seconds == 3600
    assert job.output_schema_json == {"type": "object"}
    assert job.input_headers == ("id", "prompt")
    assert job.created_at == datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
    assert job.updated_at == datetime.fromtimestamp(1_700_000_001, tz=timezone.utc)
    assert job.started_at == datetime.fromtimestamp(1_700_000_002, tz=timezone.utc)
    assert job.completed_at is None


def test_agent_job_row_rejects_invalid_row_data() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/agent_job.rs::TryFrom<AgentJobRow> for AgentJob
    # Behavior contract: invalid persisted status, JSON, u64 conversion, and
    # timestamps fail conversion.
    base = dict(
        id="job-1",
        name="Batch",
        status="pending",
        instruction="Do it",
        auto_export=0,
        max_runtime_seconds=None,
        output_schema_json=None,
        input_headers_json='["id"]',
        input_csv_path="input.csv",
        output_csv_path="output.csv",
        created_at=1,
        updated_at=2,
        started_at=None,
        completed_at=None,
        last_error=None,
    )
    with pytest.raises(ValueError, match="invalid agent job status"):
        AgentJobRow(**{**base, "status": "paused"}).to_agent_job()
    with pytest.raises(ValueError, match="invalid max_runtime_seconds value"):
        AgentJobRow(**{**base, "max_runtime_seconds": -1}).to_agent_job()
    with pytest.raises(ValueError, match="invalid unix timestamp"):
        AgentJobRow(**{**base, "created_at": 10**30}).to_agent_job()
    with pytest.raises(TypeError, match="input_headers item must be a string"):
        AgentJobRow(**{**base, "input_headers_json": '["id", 3]'}).to_agent_job()


def test_agent_job_item_row_converts_json_status_and_time_fields() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/agent_job.rs::TryFrom<AgentJobItemRow> for AgentJobItem
    # Behavior contract: item rows decode row/result JSON and optional timestamps.
    item = AgentJobItemRow(
        job_id="job-1",
        item_id="item-1",
        row_index=4,
        source_id="source",
        row_json='{"id":"1"}',
        status="completed",
        assigned_thread_id="thread",
        attempt_count=2,
        result_json='{"ok":true}',
        last_error=None,
        created_at=1_700_000_000,
        updated_at=1_700_000_001,
        completed_at=1_700_000_002,
        reported_at=1_700_000_003,
    ).to_agent_job_item()

    assert item.job_id == "job-1"
    assert item.row_json == {"id": "1"}
    assert item.status is AgentJobItemStatus.COMPLETED
    assert item.assigned_thread_id == "thread"
    assert item.attempt_count == 2
    assert item.result_json == {"ok": True}
    assert item.completed_at == datetime.fromtimestamp(1_700_000_002, tz=timezone.utc)
    assert item.reported_at == datetime.fromtimestamp(1_700_000_003, tz=timezone.utc)


def test_progress_and_create_params_validate_integer_and_string_domains() -> None:
    # Rust crate: codex-state
    # Rust module/items: AgentJobProgress, AgentJobCreateParams, AgentJobItemCreateParams
    # Behavior contract: Rust usize/u64/i64 and string-vector fields are bounded.
    assert AgentJobProgress(1, 1, 0, 0, 0).total_items == 1
    with pytest.raises(ValueError, match="total_items must be non-negative"):
        AgentJobProgress(-1, 0, 0, 0, 0)
    with pytest.raises(TypeError, match="auto_export must be a bool"):
        AgentJobCreateParams(
            id="job",
            name="name",
            instruction="instruction",
            auto_export=1,  # type: ignore[arg-type]
            max_runtime_seconds=None,
            output_schema_json=None,
            input_headers=("id",),
            input_csv_path="in.csv",
            output_csv_path="out.csv",
        )
    with pytest.raises(ValueError, match="max_runtime_seconds must fit in an unsigned"):
        AgentJobCreateParams(
            id="job",
            name="name",
            instruction="instruction",
            auto_export=False,
            max_runtime_seconds=-1,
            output_schema_json=None,
            input_headers=("id",),
            input_csv_path="in.csv",
            output_csv_path="out.csv",
        )
    with pytest.raises(ValueError, match="row_index must fit in a signed"):
        AgentJobItemCreateParams("item", 2**63, None, {})


def test_epoch_seconds_to_datetime_rejects_invalid_timestamp() -> None:
    # Rust crate: codex-state
    # Rust module/item: src/model/agent_job.rs::epoch_seconds_to_datetime
    # Behavior contract: invalid Unix timestamps fail.
    with pytest.raises(ValueError, match="invalid unix timestamp"):
        epoch_seconds_to_datetime(10**30)
