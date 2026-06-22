from __future__ import annotations

import pytest

from pycodex.codex_backend_openapi_models.models import (
    PaginatedListTaskListItem,
    TaskListItem,
)


def test_new_matches_rust_constructor_defaults() -> None:
    # Source: codex/codex-rs/codex-backend-openapi-models/src/models/paginated_list_task_list_item_.rs
    # Rust crate: codex-backend-openapi-models
    # Rust module: src/models/paginated_list_task_list_item_.rs
    # Contract: PaginatedListTaskListItem::new assigns items and leaves cursor unset.
    item = TaskListItem.new("task-id", "Task title", None, False, True)
    page = PaginatedListTaskListItem.new([item])

    assert page.items == [item]
    assert page.cursor is None
    assert page.to_json_dict() == {
        "items": [
            {
                "id": "task-id",
                "title": "Task title",
                "archived": False,
                "has_unread_turn": True,
            }
        ]
    }


def test_default_matches_derived_default() -> None:
    # Rust contract: derived Default initializes items as an empty vec and cursor to None.
    assert PaginatedListTaskListItem() == PaginatedListTaskListItem([], None)


def test_from_mapping_uses_rust_serde_field_names() -> None:
    # Rust contract: serde names are items and cursor, with cursor skipped when None.
    page = PaginatedListTaskListItem.from_mapping(
        {
            "items": [
                {
                    "id": "task-id",
                    "title": "Task title",
                    "archived": True,
                    "has_unread_turn": False,
                }
            ],
            "cursor": "next-cursor",
        }
    )

    assert page.to_json_dict() == {
        "items": [
            {
                "id": "task-id",
                "title": "Task title",
                "archived": True,
                "has_unread_turn": False,
            }
        ],
        "cursor": "next-cursor",
    }


def test_from_mapping_rejects_wrong_field_types() -> None:
    # Rust serde contract: items must be a list of TaskListItem objects and cursor must be a string.
    with pytest.raises(TypeError, match="expected items list"):
        PaginatedListTaskListItem.from_mapping({"items": {}})
    with pytest.raises(TypeError, match="expected task_list_item mapping"):
        PaginatedListTaskListItem.from_mapping({"items": ["bad"]})
    with pytest.raises(TypeError, match="expected string"):
        PaginatedListTaskListItem.from_mapping({"cursor": 123})


def test_items_accepts_model_instances() -> None:
    # Rust contract: items is a vector of TaskListItem values.
    item = TaskListItem.new("task-id", "Task title", True, False, False)

    page = PaginatedListTaskListItem.from_mapping({"items": [item]})

    assert page.items == [item]
