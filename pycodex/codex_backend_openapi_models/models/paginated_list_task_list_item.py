"""Port of Rust ``codex-backend-openapi-models::models::paginated_list_task_list_item_``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/paginated_list_task_list_item_.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .task_list_item import TaskListItem


@dataclass(frozen=True)
class PaginatedListTaskListItem:
    items: list[TaskListItem] = field(default_factory=list)
    cursor: str | None = None

    @classmethod
    def new(cls, items: list[TaskListItem]) -> "PaginatedListTaskListItem":
        return cls(items=list(items))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PaginatedListTaskListItem":
        return cls(
            items=_decode_items(value.get("items", [])),
            cursor=_optional_str(value.get("cursor")),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "items": [item.to_json_dict() for item in self.items],
        }
        if self.cursor is not None:
            result["cursor"] = self.cursor
        return result


def _decode_item(value: Any) -> TaskListItem:
    if isinstance(value, TaskListItem):
        return value
    if isinstance(value, Mapping):
        return TaskListItem.from_mapping(value)
    raise TypeError("expected task_list_item mapping")


def _decode_items(value: Any) -> list[TaskListItem]:
    if not isinstance(value, list):
        raise TypeError("expected items list")
    return [_decode_item(item) for item in value]


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return _expect_str(value)


__all__ = ["PaginatedListTaskListItem"]
