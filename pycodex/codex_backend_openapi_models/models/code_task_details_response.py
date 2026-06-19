"""Port of Rust ``codex-backend-openapi-models::models::code_task_details_response``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/code_task_details_response.rs``
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .task_response import TaskResponse


@dataclass(frozen=True)
class CodeTaskDetailsResponse:
    task: TaskResponse = field(default_factory=TaskResponse)
    current_user_turn: dict[str, Any] | None = None
    current_assistant_turn: dict[str, Any] | None = None
    current_diff_task_turn: dict[str, Any] | None = None

    @classmethod
    def new(cls, task: TaskResponse) -> "CodeTaskDetailsResponse":
        return cls(task=task)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CodeTaskDetailsResponse":
        return cls(
            task=_decode_task(value.get("task", {})),
            current_user_turn=_optional_string_key_mapping(
                value.get("current_user_turn")
            ),
            current_assistant_turn=_optional_string_key_mapping(
                value.get("current_assistant_turn")
            ),
            current_diff_task_turn=_optional_string_key_mapping(
                value.get("current_diff_task_turn")
            ),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"task": self.task.to_json_dict()}
        _put_optional(result, "current_user_turn", self.current_user_turn)
        _put_optional(result, "current_assistant_turn", self.current_assistant_turn)
        _put_optional(result, "current_diff_task_turn", self.current_diff_task_turn)
        return result


def _put_optional(result: dict[str, Any], key: str, value: Any | None) -> None:
    if value is not None:
        result[key] = value


def _decode_task(value: Any) -> TaskResponse:
    if isinstance(value, TaskResponse):
        return value
    if isinstance(value, Mapping):
        return TaskResponse.from_mapping(value)
    raise TypeError("expected task mapping")


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


__all__ = ["CodeTaskDetailsResponse"]
