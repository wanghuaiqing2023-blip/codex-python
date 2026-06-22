from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import (
    CodeTaskDetailsResponse,
    TaskResponse,
)


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/code_task_details_response.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/code_task_details_response.rs
    # Contract: CodeTaskDetailsResponse::new assigns task and leaves optional turn maps unset.
    task = TaskResponse.new("task-id", "Task title", False, [])
    response = CodeTaskDetailsResponse.new(task)

    assert response.task == task
    assert response.current_user_turn is None
    assert response.current_assistant_turn is None
    assert response.current_diff_task_turn is None
    assert response.to_json_dict() == {
        "task": {
            "id": "task-id",
            "title": "Task title",
            "archived": False,
            "external_pull_requests": [],
        }
    }


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default initializes task default and optional turn maps to None.
    assert CodeTaskDetailsResponse() == CodeTaskDetailsResponse(
        TaskResponse(),
        None,
        None,
        None,
    )


def test_from_mapping_uses_rust_serde_field_names() -> None:
    # Rust contract: serde names are task, current_user_turn, current_assistant_turn, and current_diff_task_turn.
    response = CodeTaskDetailsResponse.from_mapping(
        {
            "task": {
                "id": "task-id",
                "title": "Task title",
                "archived": True,
                "external_pull_requests": [],
            },
            "current_user_turn": {"id": "user-turn"},
            "current_assistant_turn": {"id": "assistant-turn"},
            "current_diff_task_turn": {"id": "diff-turn"},
        }
    )

    assert response.to_json_dict() == {
        "task": {
            "id": "task-id",
            "title": "Task title",
            "archived": True,
            "external_pull_requests": [],
        },
        "current_user_turn": {"id": "user-turn"},
        "current_assistant_turn": {"id": "assistant-turn"},
        "current_diff_task_turn": {"id": "diff-turn"},
    }


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: task must be an object and optional turn maps must be JSON objects.
    with pytest.raises(TypeError, match="expected task mapping"):
        CodeTaskDetailsResponse.from_mapping({"task": "not-an-object"})
    with pytest.raises(TypeError, match="expected object"):
        CodeTaskDetailsResponse.from_mapping({"current_user_turn": []})
    with pytest.raises(TypeError, match="expected string object key"):
        CodeTaskDetailsResponse.from_mapping({"current_assistant_turn": {1: "bad"}})
