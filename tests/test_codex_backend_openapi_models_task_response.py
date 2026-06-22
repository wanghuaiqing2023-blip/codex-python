from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import (
    ExternalPullRequestResponse,
    GitPullRequest,
    TaskResponse,
)


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/task_response.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/task_response.rs
    # Contract: TaskResponse::new assigns required fields and leaves optional fields unset.
    pull_request = ExternalPullRequestResponse.new(
        "response-id",
        "turn-id",
        GitPullRequest.new(12, "https://example.test/pulls/12", "open", False, True),
    )
    task = TaskResponse.new("task-id", "Task title", True, [pull_request])

    assert task.id == "task-id"
    assert task.title == "Task title"
    assert task.archived is True
    assert task.external_pull_requests == [pull_request]
    assert task.created_at is None
    assert task.has_generated_title is None
    assert task.current_turn_id is None
    assert task.has_unread_turn is None
    assert task.denormalized_metadata is None
    assert task.to_json_dict() == {
        "id": "task-id",
        "title": "Task title",
        "archived": True,
        "external_pull_requests": [
            {
                "id": "response-id",
                "assistant_turn_id": "turn-id",
                "pull_request": {
                    "number": 12,
                    "url": "https://example.test/pulls/12",
                    "state": "open",
                    "merged": False,
                    "mergeable": True,
                },
            }
        ],
    }


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default initializes strings empty, bool false, options None, and vec empty.
    assert TaskResponse() == TaskResponse(
        "",
        None,
        "",
        None,
        None,
        None,
        None,
        False,
        [],
    )


def test_from_mapping_uses_rust_serde_field_names() -> None:
    # Rust contract: serde names include current_turn_id, denormalized_metadata, and external_pull_requests.
    task = TaskResponse.from_mapping(
        {
            "id": "task-id",
            "created_at": 12,
            "title": "Task title",
            "has_generated_title": False,
            "current_turn_id": "turn-id",
            "has_unread_turn": True,
            "denormalized_metadata": {"branch": "main"},
            "archived": False,
            "external_pull_requests": [
                {
                    "id": "response-id",
                    "assistant_turn_id": "assistant-turn-id",
                    "pull_request": {
                        "number": 7,
                        "url": "url",
                        "state": "closed",
                        "merged": True,
                        "mergeable": False,
                    },
                    "codex_updated_sha": "updated-sha",
                }
            ],
        }
    )

    assert task.to_json_dict() == {
        "id": "task-id",
        "title": "Task title",
        "archived": False,
        "external_pull_requests": [
            {
                "id": "response-id",
                "assistant_turn_id": "assistant-turn-id",
                "pull_request": {
                    "number": 7,
                    "url": "url",
                    "state": "closed",
                    "merged": True,
                    "mergeable": False,
                },
                "codex_updated_sha": "updated-sha",
            }
        ],
        "created_at": 12.0,
        "has_generated_title": False,
        "current_turn_id": "turn-id",
        "has_unread_turn": True,
        "denormalized_metadata": {"branch": "main"},
    }


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: typed scalar fields, metadata object, and PR list must deserialize from matching JSON types.
    with pytest.raises(TypeError, match="expected string"):
        TaskResponse.from_mapping({"id": 123})
    with pytest.raises(TypeError, match="expected number"):
        TaskResponse.from_mapping({"created_at": "12"})
    with pytest.raises(TypeError, match="expected bool"):
        TaskResponse.from_mapping({"archived": "false"})
    with pytest.raises(TypeError, match="expected object"):
        TaskResponse.from_mapping({"denormalized_metadata": []})
    with pytest.raises(TypeError, match="expected external_pull_requests list"):
        TaskResponse.from_mapping({"external_pull_requests": {}})
