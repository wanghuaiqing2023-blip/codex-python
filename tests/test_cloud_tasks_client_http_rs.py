from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from pycodex.cloud_tasks_client import ApplyStatus, HttpClient, TaskId, TaskStatus
from pycodex.cloud_tasks_client.http import (
    ApplyGitRequest,
    ApplyGitResult,
    assistant_error_message,
    assistant_text_messages,
    attempt_status_from_str,
    details_path,
    diff_summary_from_diff,
    extract_assistant_messages_from_body,
    is_unified_diff,
    map_status,
    summarize_patch_for_logging,
    tail,
    unified_diff,
    user_text_prompt,
)


class FakeBackend:
    def __init__(self) -> None:
        self.list_args = None
        self.created_body = None
        self.details = {
            "current_user_turn": {
                "input_items": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": ["First line", {"content_type": "text", "text": "Second line"}],
                    }
                ]
            },
            "current_diff_task_turn": {
                "output_items": [
                    {
                        "type": "output_diff",
                        "diff": "diff --git a/lib.rs b/lib.rs\n--- a/lib.rs\n+++ b/lib.rs\n@@ -1 +1 @@\n-old\n+new\n",
                    }
                ]
            },
            "current_assistant_turn": {
                "id": "turn-2",
                "attempt_placement": 2,
                "turn_status": "completed",
                "sibling_turn_ids": ["turn-1"],
                "output_items": [
                    {
                        "type": "message",
                        "content": [{"content_type": "text", "text": "Assistant response"}],
                    }
                ],
                "worklog": {
                    "messages": [
                        {
                            "author": {"role": "assistant"},
                            "content": {"parts": ["Worklog response"]},
                        }
                    ]
                },
            },
        }
        self.body = json.dumps(
            {
                "task": {
                    "title": "Task title",
                    "updated_at": 1_700_000_000.25,
                    "environment_id": "env-1",
                    "is_review": True,
                },
                "task_status_display": {
                    "environment_label": "Env 1",
                    "latest_turn_status_display": {
                        "turn_status": "completed",
                        "diff_stats": {
                            "files_modified": 2,
                            "lines_added": 3,
                            "lines_removed": 4,
                        },
                        "sibling_turn_ids": ["turn-1"],
                    },
                },
            }
        )

    async def list_tasks(self, limit, task_filter, environment_id, cursor):
        self.list_args = (limit, task_filter, environment_id, cursor)
        return {
            "items": [
                {
                    "id": "task-1",
                    "title": "Task one",
                    "updated_at": 1_700_000_000.0,
                    "pull_requests": [{"id": 1}],
                    "task_status_display": {
                        "environment_label": "Env",
                        "latest_turn_status_display": {
                            "turn_status": "failed",
                            "diff_stats": {
                                "files_modified": -1,
                                "lines_added": 2,
                                "lines_removed": 1,
                            },
                            "sibling_turn_ids": ["a", "b"],
                        },
                    },
                }
            ],
            "cursor": "next",
        }

    async def get_task_details_with_body(self, task_id):
        assert task_id == "task-1"
        return self.details, self.body, "application/json"

    async def get_task_details(self, task_id):
        assert task_id == "task-1"
        return self.details

    async def list_sibling_turns(self, task_id, turn_id):
        assert (task_id, turn_id) == ("task-1", "turn-2")
        return {
            "sibling_turns": [
                {
                    "id": "late",
                    "created_at": 3.0,
                    "turn_status": "failed",
                    "output_items": [],
                },
                {
                    "id": "first",
                    "attempt_placement": 0,
                    "turn_status": "completed",
                    "output_items": [
                        {
                            "type": "pr",
                            "output_diff": {"diff": "diff --git a/a b/a\n"},
                        },
                        {
                            "type": "message",
                            "content": [{"content_type": "text", "text": "attempt msg"}],
                        },
                    ],
                },
            ]
        }

    async def create_task(self, body):
        self.created_body = body
        return "created-1"


def test_http_rs_helper_mappings() -> None:
    # Rust crate: codex-cloud-tasks-client, module: src/http.rs.
    assert details_path("https://host/backend-api", "T") == "https://host/backend-api/wham/tasks/T"
    assert details_path("https://host/api/codex", "T") == "https://host/api/codex/tasks/T"
    assert details_path("https://host/other", "T") is None
    assert map_status({"state": "applied"}) is TaskStatus.APPLIED
    assert map_status({"latest_turn_status_display": {"turn_status": "failed"}}) is TaskStatus.ERROR
    assert attempt_status_from_str("unknown") .value == "pending"
    assert is_unified_diff("diff --git a/a b/a\n")
    assert is_unified_diff("x\n--- a\n+++ b\n@@ -1 +1 @@\n-a\n+b\n")
    assert not is_unified_diff("*** Begin Patch\n*** End Patch")
    assert tail("abcdef", 3) == "def"
    assert "kind=codex-patch" in summarize_patch_for_logging("*** Begin Patch\n*** End Patch")


def test_http_rs_detail_extension_helpers() -> None:
    backend = FakeBackend()
    assert "diff --git" in unified_diff(backend.details)
    assert assistant_text_messages(backend.details) == ["Assistant response", "Worklog response"]
    assert user_text_prompt(backend.details) == "First line\n\nSecond line"
    assert assistant_error_message({"current_assistant_turn": {"error": {"code": "X", "message": "Y"}}}) == "X: Y"
    assert diff_summary_from_diff("diff --git a/a b/a\n--- a/a\n+++ b/a\n@@\n-old\n+new\n").files_changed == 1
    body = json.dumps(
        {
            "current_assistant_turn": {
                "worklog": {
                    "messages": [
                        {
                            "author": {"role": "assistant"},
                            "content": {"parts": ["hello", {"content_type": "text", "text": "world"}]},
                        }
                    ]
                }
            }
        }
    )
    assert extract_assistant_messages_from_body(body) == ["hello", "world"]


@pytest.mark.asyncio
async def test_http_client_lists_and_projects_summaries() -> None:
    backend = FakeBackend()
    client = HttpClient("https://host/api/codex", backend=backend)

    page = await client.list_tasks("env-1", 10, "cur")

    assert backend.list_args == (10, "current", "env-1", "cur")
    assert page.cursor == "next"
    assert page.tasks[0].id.value == "task-1"
    assert page.tasks[0].status is TaskStatus.ERROR
    assert page.tasks[0].environment_label == "Env"
    assert page.tasks[0].summary.lines_added == 2
    assert page.tasks[0].is_review is True
    assert page.tasks[0].attempt_total == 3


@pytest.mark.asyncio
async def test_http_client_details_text_and_sibling_attempts() -> None:
    client = HttpClient("https://host/api/codex", backend=FakeBackend())

    summary = await client.get_task_summary(TaskId("task-1"))
    assert summary.title == "Task title"
    assert summary.status is TaskStatus.READY
    assert summary.updated_at == datetime.fromtimestamp(1_700_000_000.25, timezone.utc)
    assert summary.environment_id == "env-1"
    assert summary.summary.files_changed == 2

    assert await client.get_task_diff(TaskId("task-1")) is not None
    assert await client.get_task_messages(TaskId("task-1")) == [
        "Assistant response",
        "Worklog response",
    ]
    text = await client.get_task_text(TaskId("task-1"))
    assert text.prompt == "First line\n\nSecond line"
    assert text.turn_id == "turn-2"
    assert text.sibling_turn_ids == ["turn-1"]

    attempts = await client.list_sibling_attempts(TaskId("task-1"), "turn-2")
    assert [attempt.turn_id for attempt in attempts] == ["first", "late"]
    assert attempts[0].diff == "diff --git a/a b/a\n"
    assert attempts[0].messages == ["attempt msg"]


@pytest.mark.asyncio
async def test_http_client_apply_status_messages_and_create(monkeypatch) -> None:
    backend = FakeBackend()
    seen: list[ApplyGitRequest] = []

    def fake_apply(req: ApplyGitRequest) -> ApplyGitResult:
        seen.append(req)
        return ApplyGitResult(exit_code=0, applied_paths=["lib.rs"], cmd_for_log="git apply --check")

    client = HttpClient("https://host/api/codex", backend=backend, apply_git_patch=fake_apply)

    preflight = await client.apply_task_preflight(TaskId("task-1"))
    assert preflight.applied is False
    assert preflight.status is ApplyStatus.SUCCESS
    assert preflight.message == "Preflight passed for task task-1 (applies cleanly)"
    assert seen[-1].preflight is True

    applied = await client.apply_task(TaskId("task-1"))
    assert applied.applied is True
    assert applied.message == "Applied task task-1 locally (1 files)"
    assert seen[-1].preflight is False

    bad = await client.apply_task(TaskId("task-1"), "not a diff")
    assert bad.status is ApplyStatus.ERROR
    assert bad.applied is False

    monkeypatch.setenv("CODEX_STARTING_DIFF", "diff --git a/a b/a\n")
    created = await client.create_task("env-1", "prompt", "main", True, 3)
    assert created.id.value == "created-1"
    assert backend.created_body["new_task"]["environment_id"] == "env-1"
    assert backend.created_body["metadata"] == {"best_of_n": 3}
    assert backend.created_body["input_items"][1]["type"] == "pre_apply_patch"
