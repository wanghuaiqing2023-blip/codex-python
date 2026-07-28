"""Rust-aligned models from ``codex-backend-client/src/types.rs``."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.codex_backend_openapi_models.models import ConfigFileResponse
from pycodex.codex_backend_openapi_models.models import CreditStatusDetails
from pycodex.codex_backend_openapi_models.models import PaginatedListTaskListItem
from pycodex.codex_backend_openapi_models.models import PlanType
from pycodex.codex_backend_openapi_models.models import RateLimitReachedKind
from pycodex.codex_backend_openapi_models.models import RateLimitStatusDetails
from pycodex.codex_backend_openapi_models.models import RateLimitStatusPayload
from pycodex.codex_backend_openapi_models.models import RateLimitWindowSnapshot
from pycodex.codex_backend_openapi_models.models import TaskListItem

JsonValue = Any


@dataclass(frozen=True)
class ContentFragment:
    value: JsonValue

    def text(self) -> str | None:
        if isinstance(self.value, str):
            return None if self.value.strip() == "" else self.value
        if isinstance(self.value, Mapping):
            content_type = self.value.get("content_type")
            if isinstance(content_type, str) and content_type.lower() == "text":
                text = self.value.get("text")
                if isinstance(text, str) and text != "":
                    return text
        return None


@dataclass(frozen=True)
class TurnItem:
    kind: str = ""
    role: str | None = None
    content: tuple[ContentFragment, ...] = ()
    diff: str | None = None
    output_diff: Mapping[str, JsonValue] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnItem":
        raw_content = value.get("content") or []
        if not isinstance(raw_content, list):
            raw_content = []
        output_diff = value.get("output_diff")
        return cls(
            kind=_optional_str(value.get("type")) or "",
            role=_optional_str(value.get("role")),
            content=tuple(ContentFragment(item) for item in raw_content),
            diff=_optional_str(value.get("diff")),
            output_diff=output_diff if isinstance(output_diff, Mapping) else None,
        )

    def text_values(self) -> list[str]:
        return [text for fragment in self.content if (text := fragment.text()) is not None]

    def diff_text(self) -> str | None:
        if self.kind == "output_diff" and self.diff:
            return self.diff
        if self.kind == "pr" and self.output_diff is not None:
            diff = self.output_diff.get("diff")
            if isinstance(diff, str) and diff:
                return diff
        return None


@dataclass(frozen=True)
class TurnError:
    code: str | None = None
    message: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "TurnError":
        return cls(_optional_str(value.get("code")), _optional_str(value.get("message")))

    def summary(self) -> str | None:
        code = self.code or ""
        message = self.message or ""
        if not code and not message:
            return None
        if code and not message:
            return code
        if message and not code:
            return message
        return f"{code}: {message}"


@dataclass(frozen=True)
class WorklogMessage:
    author_role: str | None = None
    parts: tuple[ContentFragment, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WorklogMessage":
        author = value.get("author")
        content = value.get("content")
        parts: list[JsonValue] = []
        if isinstance(content, Mapping) and isinstance(content.get("parts"), list):
            parts = list(content["parts"])
        role = author.get("role") if isinstance(author, Mapping) else None
        return cls(_optional_str(role), tuple(ContentFragment(part) for part in parts))

    def is_assistant(self) -> bool:
        return self.author_role is not None and self.author_role.lower() == "assistant"

    def text_values(self) -> list[str]:
        return [text for fragment in self.parts if (text := fragment.text()) is not None]


@dataclass(frozen=True)
class Worklog:
    messages: tuple[WorklogMessage, ...] = ()

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Worklog":
        messages = value.get("messages") or []
        if not isinstance(messages, list):
            messages = []
        return cls(
            tuple(
                WorklogMessage.from_mapping(item)
                for item in messages
                if isinstance(item, Mapping)
            )
        )


@dataclass(frozen=True)
class Turn:
    id: str | None = None
    attempt_placement: int | None = None
    turn_status: str | None = None
    sibling_turn_ids: tuple[str, ...] = ()
    input_items: tuple[TurnItem, ...] = ()
    output_items: tuple[TurnItem, ...] = ()
    worklog: Worklog | None = None
    error: TurnError | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "Turn":
        return cls(
            id=_optional_str(value.get("id")),
            attempt_placement=_optional_int(value.get("attempt_placement")),
            turn_status=_optional_str(value.get("turn_status")),
            sibling_turn_ids=tuple(
                item
                for item in _list_or_empty(value.get("sibling_turn_ids"))
                if isinstance(item, str)
            ),
            input_items=tuple(
                TurnItem.from_mapping(item)
                for item in _list_or_empty(value.get("input_items"))
                if isinstance(item, Mapping)
            ),
            output_items=tuple(
                TurnItem.from_mapping(item)
                for item in _list_or_empty(value.get("output_items"))
                if isinstance(item, Mapping)
            ),
            worklog=(
                Worklog.from_mapping(value["worklog"])
                if isinstance(value.get("worklog"), Mapping)
                else None
            ),
            error=(
                TurnError.from_mapping(value["error"])
                if isinstance(value.get("error"), Mapping)
                else None
            ),
        )

    def unified_diff(self) -> str | None:
        for item in self.output_items:
            if diff := item.diff_text():
                return diff
        return None

    def message_texts(self) -> list[str]:
        values: list[str] = []
        for item in self.output_items:
            if item.kind == "message":
                values.extend(item.text_values())
        if self.worklog is not None:
            for message in self.worklog.messages:
                if message.is_assistant():
                    values.extend(message.text_values())
        return values

    def user_prompt(self) -> str | None:
        parts: list[str] = []
        for item in self.input_items:
            if item.kind == "message" and (
                item.role is None or item.role.lower() == "user"
            ):
                parts.extend(item.text_values())
        if not parts:
            return None
        return "\n\n".join(parts)

    def error_summary(self) -> str | None:
        return None if self.error is None else self.error.summary()


@dataclass(frozen=True)
class CodeTaskDetailsResponse:
    current_user_turn: Turn | None = None
    current_assistant_turn: Turn | None = None
    current_diff_task_turn: Turn | None = None

    @classmethod
    def from_json(cls, text: str) -> "CodeTaskDetailsResponse":
        return cls.from_mapping(json.loads(text))

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue]
    ) -> "CodeTaskDetailsResponse":
        return cls(
            current_user_turn=_turn_or_none(value.get("current_user_turn")),
            current_assistant_turn=_turn_or_none(value.get("current_assistant_turn")),
            current_diff_task_turn=_turn_or_none(value.get("current_diff_task_turn")),
        )

    def unified_diff(self) -> str | None:
        for turn in (self.current_diff_task_turn, self.current_assistant_turn):
            if turn is not None and (diff := turn.unified_diff()):
                return diff
        return None

    def assistant_text_messages(self) -> list[str]:
        values: list[str] = []
        for turn in (self.current_diff_task_turn, self.current_assistant_turn):
            if turn is not None:
                values.extend(turn.message_texts())
        return values

    def user_text_prompt(self) -> str | None:
        return (
            None
            if self.current_user_turn is None
            else self.current_user_turn.user_prompt()
        )

    def assistant_error_message(self) -> str | None:
        return (
            None
            if self.current_assistant_turn is None
            else self.current_assistant_turn.error_summary()
        )


# Rust exposes these methods through CodeTaskDetailsResponseExt. Python keeps
# them directly on the response type rather than adding a second nominal type.
CodeTaskDetailsResponseExt = CodeTaskDetailsResponse


@dataclass(frozen=True)
class TurnAttemptsSiblingTurnsResponse:
    sibling_turns: tuple[Mapping[str, JsonValue], ...] = ()

    @classmethod
    def from_mapping(
        cls, value: Mapping[str, JsonValue]
    ) -> "TurnAttemptsSiblingTurnsResponse":
        raw = value.get("sibling_turns") or []
        if not isinstance(raw, list):
            raw = []
        return cls(tuple(item for item in raw if isinstance(item, Mapping)))


def _turn_or_none(value: JsonValue) -> Turn | None:
    if isinstance(value, Mapping):
        return Turn.from_mapping(value)
    return None


def _list_or_empty(value: JsonValue) -> list[JsonValue]:
    return list(value) if isinstance(value, list) else []


def _optional_str(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: JsonValue) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


__all__ = [
    "CodeTaskDetailsResponse",
    "CodeTaskDetailsResponseExt",
    "ConfigFileResponse",
    "ContentFragment",
    "CreditStatusDetails",
    "PaginatedListTaskListItem",
    "PlanType",
    "RateLimitReachedKind",
    "RateLimitStatusDetails",
    "RateLimitStatusPayload",
    "RateLimitWindowSnapshot",
    "TaskListItem",
    "Turn",
    "TurnAttemptsSiblingTurnsResponse",
    "TurnError",
    "TurnItem",
    "Worklog",
    "WorklogMessage",
]
