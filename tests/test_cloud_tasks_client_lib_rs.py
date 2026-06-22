from __future__ import annotations

from datetime import datetime, timezone

import pycodex.cloud_tasks_client as cloud_tasks_client
from pycodex.cloud_tasks_client import (
    ApplyOutcome,
    ApplyStatus,
    AttemptStatus,
    CloudTaskError,
    CreatedTask,
    DiffSummary,
    HttpClient,
    TaskId,
    TaskListPage,
    TaskStatus,
    TaskSummary,
    TaskText,
    TurnAttempt,
)


def test_lib_rs_reexports_match_rust_pub_use_surface() -> None:
    # Rust crate: codex-cloud-tasks-client, module: src/lib.rs.
    expected = {
        "ApplyOutcome",
        "ApplyStatus",
        "AttemptStatus",
        "CloudBackend",
        "CloudTaskError",
        "CreatedTask",
        "DiffSummary",
        "HttpClient",
        "Result",
        "TaskId",
        "TaskListPage",
        "TaskStatus",
        "TaskSummary",
        "TaskText",
        "TurnAttempt",
    }
    assert set(cloud_tasks_client.__all__) == expected
    for name in expected:
        assert hasattr(cloud_tasks_client, name)


def test_public_value_types_cover_lib_rs_reexported_api_shapes() -> None:
    task_id = TaskId("task-1")
    summary = TaskSummary(
        id=task_id,
        title="Title",
        status=TaskStatus.READY,
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        environment_id="env-1",
        environment_label="Env 1",
        summary=DiffSummary(files_changed=2, lines_added=3, lines_removed=1),
        is_review=True,
        attempt_total=4,
    )
    page = TaskListPage(tasks=[summary], cursor="next")
    text = TaskText(prompt="p", messages=["m"], turn_id="turn")
    attempt = TurnAttempt(
        turn_id="turn",
        attempt_placement=1,
        created_at=summary.updated_at,
        status=AttemptStatus.COMPLETED,
        diff="diff",
        messages=["message"],
    )

    assert str(task_id) == "task-1"
    assert task_id.id == "task-1"
    assert page.tasks == [summary]
    assert text.attempt_status is AttemptStatus.UNKNOWN
    assert attempt.status is AttemptStatus.COMPLETED
    assert CreatedTask(id=task_id).id == task_id
    assert ApplyOutcome(True, ApplyStatus.SUCCESS, "ok").conflict_paths == []


def test_status_and_error_strings_match_rust_serialized_forms() -> None:
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.READY.value == "ready"
    assert TaskStatus.APPLIED.value == "applied"
    assert TaskStatus.ERROR.value == "error"
    assert ApplyStatus.SUCCESS.value == "success"
    assert ApplyStatus.PARTIAL.value == "partial"
    assert ApplyStatus.ERROR.value == "error"

    assert str(CloudTaskError.unimplemented("api")) == "unimplemented: api"
    assert str(CloudTaskError.http("boom")) == "http error: boom"
    assert str(CloudTaskError.io("disk")) == "io error: disk"


def test_http_client_builder_surface_is_available_from_crate_root() -> None:
    client = (
        HttpClient.new("https://example.test")
        .with_user_agent("pycodex-test")
        .with_auth_provider(object())
        .with_chatgpt_account_id("acct")
    )

    assert client.base_url == "https://example.test"
    assert client.user_agent == "pycodex-test"
    assert client.auth_provider is not None
    assert client.chatgpt_account_id == "acct"
