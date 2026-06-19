"""Port of Rust ``codex-backend-openapi-models::models::task_response``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/task_response.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .external_pull_request_response import ExternalPullRequestResponse


@dataclass(frozen=True)
class TaskResponse:
    id: str = ""
    created_at: float | None = None
    title: str = ""
    has_generated_title: bool | None = None
    current_turn_id: str | None = None
    has_unread_turn: bool | None = None
    denormalized_metadata: dict[str, Any] | None = None
    archived: bool = False
    external_pull_requests: list[ExternalPullRequestResponse] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        id: str,
        title: str,
        archived: bool,
        external_pull_requests: list[ExternalPullRequestResponse],
    ) -> "TaskResponse":
        return cls(
            id=id,
            title=title,
            archived=archived,
            external_pull_requests=list(external_pull_requests),
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TaskResponse":
        return cls(
            id=_expect_str(value.get("id", "")),
            created_at=_optional_float(value.get("created_at")),
            title=_expect_str(value.get("title", "")),
            has_generated_title=_optional_bool(value.get("has_generated_title")),
            current_turn_id=_optional_str(value.get("current_turn_id")),
            has_unread_turn=_optional_bool(value.get("has_unread_turn")),
            denormalized_metadata=_optional_string_key_mapping(
                value.get("denormalized_metadata")
            ),
            archived=_expect_bool(value.get("archived", False)),
            external_pull_requests=_decode_external_pull_requests(
                value.get("external_pull_requests", [])
            ),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "archived": self.archived,
            "external_pull_requests": [
                pull_request.to_json_dict()
                for pull_request in self.external_pull_requests
            ],
        }
        _put_optional(result, "created_at", self.created_at)
        _put_optional(result, "has_generated_title", self.has_generated_title)
        _put_optional(result, "current_turn_id", self.current_turn_id)
        _put_optional(result, "has_unread_turn", self.has_unread_turn)
        _put_optional(result, "denormalized_metadata", self.denormalized_metadata)
        return result


def _put_optional(result: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None:
        result[key] = value


def _decode_external_pull_requests(value: Any) -> list[ExternalPullRequestResponse]:
    if not isinstance(value, list):
        raise TypeError("expected external_pull_requests list")
    result: list[ExternalPullRequestResponse] = []
    for item in value:
        if isinstance(item, ExternalPullRequestResponse):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(ExternalPullRequestResponse.from_mapping(item))
        else:
            raise TypeError("expected external_pull_request mapping")
    return result


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


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return _expect_float(value)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return _expect_str(value)


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


__all__ = ["TaskResponse"]
