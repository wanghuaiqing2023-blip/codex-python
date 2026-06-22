from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import (
    ExternalPullRequestResponse,
    GitPullRequest,
    TaskListItem,
)


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/task_list_item.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/task_list_item.rs
    # Contract: TaskListItem::new assigns required fields and leaves other optional fields unset.
    item = TaskListItem.new("task-id", "Task title", False, True, False)

    assert item.id == "task-id"
    assert item.title == "Task title"
    assert item.has_generated_title is False
    assert item.archived is True
    assert item.has_unread_turn is False
    assert item.updated_at is None
    assert item.created_at is None
    assert item.task_status_display is None
    assert item.pull_requests is None
    assert item.to_json_dict() == {
        "id": "task-id",
        "title": "Task title",
        "archived": True,
        "has_unread_turn": False,
        "has_generated_title": False,
    }


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default initializes strings empty, bool false, and options None.
    assert TaskListItem() == TaskListItem(
        "",
        "",
        None,
        None,
        None,
        None,
        False,
        False,
        None,
    )


def test_from_mapping_uses_rust_serde_field_names() -> None:
    # Rust contract: serde names include task_status_display and pull_requests.
    item = TaskListItem.from_mapping(
        {
            "id": "task-id",
            "title": "Task title",
            "has_generated_title": True,
            "updated_at": 20,
            "created_at": 10,
            "task_status_display": {"status": "done"},
            "archived": False,
            "has_unread_turn": True,
            "pull_requests": [
                {
                    "id": "response-id",
                    "assistant_turn_id": "turn-id",
                    "pull_request": {
                        "number": 7,
                        "url": "url",
                        "state": "closed",
                        "merged": True,
                        "mergeable": False,
                    },
                }
            ],
        }
    )

    assert item.to_json_dict() == {
        "id": "task-id",
        "title": "Task title",
        "archived": False,
        "has_unread_turn": True,
        "has_generated_title": True,
        "updated_at": 20.0,
        "created_at": 10.0,
        "task_status_display": {"status": "done"},
        "pull_requests": [
            {
                "id": "response-id",
                "assistant_turn_id": "turn-id",
                "pull_request": {
                    "number": 7,
                    "url": "url",
                    "state": "closed",
                    "merged": True,
                    "mergeable": False,
                },
            }
        ],
    }


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: scalar fields, status object, and pull_requests list must deserialize from matching JSON types.
    with pytest.raises(TypeError, match="expected string"):
        TaskListItem.from_mapping({"id": 123})
    with pytest.raises(TypeError, match="expected bool"):
        TaskListItem.from_mapping({"has_unread_turn": "false"})
    with pytest.raises(TypeError, match="expected number"):
        TaskListItem.from_mapping({"updated_at": "20"})
    with pytest.raises(TypeError, match="expected object"):
        TaskListItem.from_mapping({"task_status_display": []})
    with pytest.raises(TypeError, match="expected pull_requests list"):
        TaskListItem.from_mapping({"pull_requests": {}})
    with pytest.raises(TypeError, match="expected external_pull_request mapping"):
        TaskListItem.from_mapping({"pull_requests": ["bad"]})


def test_pull_requests_accepts_model_instances() -> None:
    # Rust contract: pull_requests is a vector of ExternalPullRequestResponse values.
    pull_request = ExternalPullRequestResponse.new(
        "response-id",
        "turn-id",
        GitPullRequest.new(1, "url", "open", False, True),
    )

    item = TaskListItem.from_mapping({"pull_requests": [pull_request]})

    assert item.pull_requests == [pull_request]
