from __future__ import annotations

import pytest

from pycodex.cloud_tasks_mock_client import (
    ApplyStatus,
    AttemptStatus,
    CloudTaskError,
    MockClient,
    TaskId,
    TaskStatus,
    count_from_unified,
    mock_diff_for,
)


@pytest.mark.asyncio
async def test_list_tasks_default_rows_and_diff_summaries() -> None:
    # Rust crate/module: codex-cloud-tasks-mock-client src/mock.rs. Behavior
    # contract: default list_tasks returns the three global mock tasks with
    # derived one-file diff summaries and T-1000 attempt_total=2.
    page = await MockClient().list_tasks()

    assert page.cursor is None
    assert [task.id.value for task in page.tasks] == ["T-1000", "T-1001", "T-1002"]
    assert [task.title for task in page.tasks] == [
        "Update README formatting",
        "Fix clippy warnings in core",
        "Add contributing guide",
    ]
    assert [task.status for task in page.tasks] == [
        TaskStatus.READY,
        TaskStatus.PENDING,
        TaskStatus.READY,
    ]
    assert [task.environment_id for task in page.tasks] == [None, None, None]
    assert [task.environment_label for task in page.tasks] == ["Global", "Global", "Global"]
    assert [task.summary.lines_added for task in page.tasks] == [2, 0, 3]
    assert [task.summary.lines_removed for task in page.tasks] == [1, 1, 0]
    assert [task.summary.files_changed for task in page.tasks] == [1, 1, 1]
    assert [task.is_review for task in page.tasks] == [False, False, False]
    assert [task.attempt_total for task in page.tasks] == [2, 1, 1]


@pytest.mark.asyncio
async def test_list_tasks_varies_by_environment() -> None:
    # Rust crate/module: codex-cloud-tasks-mock-client src/mock.rs. Behavior
    # contract: env-A/env-B/custom envs vary rows and environment labels.
    client = MockClient()

    env_a = await client.list_tasks("env-A")
    env_b = await client.list_tasks("env-B")
    other = await client.list_tasks("preview")

    assert [(task.id.value, task.title, task.status) for task in env_a.tasks] == [
        ("T-2000", "A: First", TaskStatus.READY)
    ]
    assert [task.environment_label for task in env_a.tasks] == ["Env A"]
    assert [task.environment_id for task in env_a.tasks] == ["env-A"]

    assert [(task.id.value, task.title, task.status) for task in env_b.tasks] == [
        ("T-3000", "B: One", TaskStatus.READY),
        ("T-3001", "B: Two", TaskStatus.PENDING),
    ]
    assert [task.environment_label for task in env_b.tasks] == ["Env B", "Env B"]
    assert [task.environment_id for task in env_b.tasks] == ["env-B", "env-B"]

    assert [task.environment_label for task in other.tasks] == ["preview"] * 3
    assert [task.environment_id for task in other.tasks] == ["preview"] * 3


@pytest.mark.asyncio
async def test_task_summary_diff_messages_and_text() -> None:
    # Rust crate/module: codex-cloud-tasks-mock-client src/mock.rs. Behavior
    # contract: lookup, diff, messages, and text responses match the mock.
    client = MockClient()

    summary = await client.get_task_summary(TaskId("T-1000"))
    assert summary.title == "Update README formatting"

    with pytest.raises(CloudTaskError, match="Task missing not found \\(mock\\)"):
        await client.get_task_summary(TaskId("missing"))

    assert await client.get_task_diff(TaskId("T-1001")) == mock_diff_for(TaskId("T-1001"))
    assert await client.get_task_messages(TaskId("T-1000")) == [
        "Mock assistant output: this task contains no diff."
    ]

    text = await client.get_task_text(TaskId("T-1000"))
    assert text.prompt == "Why is there no diff?"
    assert text.messages == ["Mock assistant output: this task contains no diff."]
    assert text.turn_id == "mock-turn"
    assert text.sibling_turn_ids == []
    assert text.attempt_placement == 0
    assert text.attempt_status == AttemptStatus.COMPLETED


@pytest.mark.asyncio
async def test_apply_preflight_sibling_attempts_and_create_task() -> None:
    # Rust crate/module: codex-cloud-tasks-mock-client src/mock.rs. Behavior
    # contract: apply/preflight return fixed success outcomes, T-1000 has one
    # sibling attempt, other tasks have none, and create_task returns a local id.
    client = MockClient()

    applied = await client.apply_task(TaskId("T-1000"))
    assert applied.applied is True
    assert applied.status == ApplyStatus.SUCCESS
    assert applied.message == "Applied task T-1000 locally (mock)"
    assert applied.skipped_paths == []
    assert applied.conflict_paths == []

    preflight = await client.apply_task_preflight(TaskId("T-1001"))
    assert preflight.applied is False
    assert preflight.status == ApplyStatus.SUCCESS
    assert preflight.message == "Preflight passed for task T-1001 (mock)"
    assert preflight.skipped_paths == []
    assert preflight.conflict_paths == []

    attempts = await client.list_sibling_attempts(TaskId("T-1000"), "turn")
    assert len(attempts) == 1
    assert attempts[0].turn_id == "T-1000-attempt-2"
    assert attempts[0].attempt_placement == 1
    assert attempts[0].status == AttemptStatus.COMPLETED
    assert attempts[0].diff == mock_diff_for(TaskId("T-1000"))
    assert attempts[0].messages == ["Mock alternate attempt"]

    assert await client.list_sibling_attempts(TaskId("T-1001"), "turn") == []

    created = await client.create_task("env", "prompt", "main", False, 1)
    assert created.id.value.startswith("task_local_")


def test_mock_diff_for_and_count_from_unified() -> None:
    # Rust crate/module: codex-cloud-tasks-mock-client src/mock.rs. Behavior
    # contract: mock_diff_for has special T-1000/T-1001 diffs and a default
    # CONTRIBUTING diff; count_from_unified ignores diff/hunk headers.
    assert "README.md" in mock_diff_for(TaskId("T-1000"))
    assert "core/src/lib.rs" in mock_diff_for(TaskId("T-1001"))
    assert "CONTRIBUTING.md" in mock_diff_for(TaskId("unknown"))

    assert count_from_unified(mock_diff_for(TaskId("T-1000"))) == (2, 1)
    assert count_from_unified(mock_diff_for(TaskId("T-1001"))) == (0, 1)
    assert count_from_unified(mock_diff_for(TaskId("unknown"))) == (3, 0)
    assert count_from_unified("--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n") == (1, 1)
