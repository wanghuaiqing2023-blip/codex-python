"""Port of Rust ``codex-backend-openapi-models::models::task_list_item``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/task_list_item.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .external_pull_request_response import ExternalPullRequestResponse


@dataclass(frozen=True)
class TaskListItem:
    id: str = ""
    title: str = ""
    has_generated_title: bool | None = None
    updated_at: float | None = None
    created_at: float | None = None
    task_status_display: dict[str, Any] | None = None
    archived: bool = False
    has_unread_turn: bool = False
    pull_requests: list[ExternalPullRequestResponse] | None = None

    @classmethod
    def new(
        cls,
        id: str,
        title: str,
        has_generated_title: bool | None,
        archived: bool,
        has_unread_turn: bool,
    ) -> "TaskListItem":
        return cls(
            id=id,
            title=title,
            has_generated_title=has_generated_title,
            archived=archived,
            has_unread_turn=has_unread_turn,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaskListItem":
        return cls(
            id=_expect_str(value.get("id", "")),
            title=_expect_str(value.get("title", "")),
            has_generated_title=_optional_bool(value.get("has_generated_title")),
            updated_at=_optional_float(value.get("updated_at")),
            created_at=_optional_float(value.get("created_at")),
            task_status_display=_optional_string_key_mapping(
                value.get("task_status_display")
            ),
            archived=_expect_bool(value.get("archived", False)),
            has_unread_turn=_expect_bool(value.get("has_unread_turn", False)),
            pull_requests=_optional_external_pull_requests(value.get("pull_requests")),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "archived": self.archived,
            "has_unread_turn": self.has_unread_turn,
        }
        _put_optional(result, "has_generated_title", self.has_generated_title)
        _put_optional(result, "updated_at", self.updated_at)
        _put_optional(result, "created_at", self.created_at)
        _put_optional(result, "task_status_display", self.task_status_display)
        if self.pull_requests is not None:
            result["pull_requests"] = [
                pull_request.to_json_dict() for pull_request in self.pull_requests
            ]
        return result


def _put_optional(result: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None:
        result[key] = value


def _decode_external_pull_request(value: Any) -> ExternalPullRequestResponse:
    if isinstance(value, ExternalPullRequestResponse):
        return value
    if isinstance(value, Mapping):
        return ExternalPullRequestResponse.from_mapping(value)
    raise TypeError("expected external_pull_request mapping")


def _expect_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise TypeError("expected bool")


def _expect_float(value: Any) -> float:
    if isinstance(value, bool):
        raise TypeError("expected number")
    if isinstance(value, int | float):
        return float(value)
    raise TypeError("expected number")


def _expect_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    raise TypeError("expected string")


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return _expect_bool(value)


def _optional_external_pull_requests(
    value: Any,
) -> list[ExternalPullRequestResponse] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise TypeError("expected pull_requests list")
    return [_decode_external_pull_request(item) for item in value]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return _expect_float(value)


def _optional_string_key_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("expected object")
    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("expected string object key")
        result[key] = item
    return result


__all__ = ["TaskListItem"]
