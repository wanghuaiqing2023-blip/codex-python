from __future__ import annotations

from datetime import datetime, timezone

from pycodex.cloud_tasks_client.api import (
    ApplyOutcome,
    ApplyStatus,
    AttemptStatus,
    CloudTaskError,
    CreatedTask,
    DiffSummary,
    TaskId,
    TaskListPage,
    TaskStatus,
    TaskSummary,
    TaskText,
    TurnAttempt,
)


def test_api_rs_error_display_contract() -> None:
    # Rust crate: codex-cloud-tasks-client, module: src/api.rs.
    assert str(CloudTaskError.unimplemented("cloud task backend")) == (
        "unimplemented: cloud task backend"
    )
    assert str(CloudTaskError.http("request failed")) == "http error: request failed"
    assert str(CloudTaskError.io("read failed")) == "io error: read failed"
    assert str(CloudTaskError.msg("plain message")) == "plain message"


def test_api_rs_status_serialized_values_and_defaults() -> None:
    assert [status.value for status in TaskStatus] == [
        "pending",
        "ready",
        "applied",
        "error",
    ]
    assert [status.value for status in ApplyStatus] == ["success", "partial", "error"]
    assert AttemptStatus.UNKNOWN.value == "unknown"

    assert DiffSummary() == DiffSummary(files_changed=0, lines_added=0, lines_removed=0)
    assert TaskText() == TaskText(
        prompt=None,
        messages=[],
        turn_id=None,
        sibling_turn_ids=[],
        attempt_placement=None,
        attempt_status=AttemptStatus.UNKNOWN,
    )
    assert ApplyOutcome(True, ApplyStatus.SUCCESS, "ok").skipped_paths == []
    assert ApplyOutcome(True, ApplyStatus.SUCCESS, "ok").conflict_paths == []


def test_api_rs_value_shapes() -> None:
    task_id = TaskId("task_123")
    now = datetime(2026, 6, 19, tzinfo=timezone.utc)
    summary = TaskSummary(
        id=task_id,
        title="Review patch",
        status=TaskStatus.READY,
        updated_at=now,
        environment_id=None,
        environment_label=None,
        summary=DiffSummary(files_changed=1, lines_added=2, lines_removed=3),
    )
    attempt = TurnAttempt(
        turn_id="turn_1",
        attempt_placement=None,
        created_at=None,
        status=AttemptStatus.UNKNOWN,
        diff=None,
        messages=[],
    )

    assert task_id.value == "task_123"
    assert str(task_id) == "task_123"
    assert summary.is_review is False
    assert summary.attempt_total is None
    assert TaskListPage(tasks=[summary]).cursor is None
    assert CreatedTask(id=task_id).id == task_id
    assert attempt.messages == []
