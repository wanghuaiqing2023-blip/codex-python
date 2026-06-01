"""Turn item protocol models.

Ported from ``codex/codex-rs/protocol/src/items.rs``.
"""

from __future__ import annotations

import uuid
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .approvals import FileChange
from .config_types import ReasoningEffort
from .memory_citation import MemoryCitation
from .mcp import CallToolResult
from .models import ContentItem, ImageDetail, MessagePhase, ResponseItem, WebSearchAction
from .protocol import (
    AgentMessageEvent,
    AgentReasoningEvent,
    AgentReasoningRawContentEvent,
    ContextCompactedEvent,
    EventMsg,
    ImageGenerationBeginEvent,
    ImageGenerationEndEvent,
    McpInvocation,
    McpToolCallBeginEvent,
    McpToolCallEndEvent,
    PatchApplyBeginEvent,
    PatchApplyEndEvent,
    PatchApplyStatus,
    UserMessageEvent,
    ViewImageToolCallEvent,
    WebSearchBeginEvent,
    WebSearchEndEvent,
)
from .user_input import ByteRange, TextElement, UserInput

JsonValue = Any
I32_MIN = -(2**31)
I32_MAX = 2**31 - 1
I64_MIN = -(2**63)
I64_MAX = 2**63 - 1
_TURN_ITEMS_VIEW_VALUES = {"notLoaded", "summary", "full"}
_TURN_STATUS_VALUES = {"completed", "interrupted", "failed", "inProgress"}


def _mapping(value: JsonValue, label: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: Mapping[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: Mapping[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str_alias(value: Mapping[str, JsonValue], primary: str, fallback: str) -> str | None:
    if primary in value:
        return _optional_str(value, primary)
    return _optional_str(value, fallback)


def _optional_message_phase(value: JsonValue) -> MessagePhase | None:
    if value is None:
        return None
    if isinstance(value, MessagePhase):
        return value
    if isinstance(value, str):
        return MessagePhase(value)
    raise TypeError("phase must be a MessagePhase, string, or None")


def _required_value(value: Mapping[str, JsonValue], key: str) -> JsonValue:
    if key not in value:
        raise KeyError(key)
    return value[key]


def _optional_non_negative_number(value: JsonValue, label: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be a number or None")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


def _optional_turn_error(value: JsonValue) -> dict[str, JsonValue] | None:
    if value is None:
        return None
    data = _mapping(value, "turn error")
    return {
        "message": _required_str(data, "message"),
        "codexErrorInfo": data.get("codexErrorInfo"),
        "additionalDetails": data.get("additionalDetails"),
    }


def turn_to_app_server_mapping(
    turn_id: str,
    items: tuple["TurnItem", ...] | list["TurnItem"],
    *,
    status: str = "completed",
    items_view: str = "full",
    error: JsonValue = None,
    started_at: int | float | None = None,
    completed_at: int | float | None = None,
    duration_ms: int | float | None = None,
) -> dict[str, JsonValue]:
    if not isinstance(turn_id, str):
        raise TypeError("turn_id must be a string")
    if status not in _TURN_STATUS_VALUES:
        raise ValueError(f"unknown turn status: {status}")
    if items_view not in _TURN_ITEMS_VIEW_VALUES:
        raise ValueError(f"unknown turn items view: {items_view}")
    if isinstance(items, TurnItem):
        raise TypeError("items must be a list or tuple")
    if not isinstance(items, (list, tuple)):
        raise TypeError("items must be a list or tuple")
    if not all(isinstance(item, TurnItem) for item in items):
        raise TypeError("items entries must be TurnItem")
    return {
        "id": turn_id,
        "items": [item.to_app_server_mapping() for item in items],
        "itemsView": items_view,
        "status": status,
        "error": _optional_turn_error(error),
        "startedAt": _optional_non_negative_number(started_at, "started_at"),
        "completedAt": _optional_non_negative_number(completed_at, "completed_at"),
        "durationMs": _optional_non_negative_number(duration_ms, "duration_ms"),
    }


def turn_started_notification(
    thread_id: str,
    turn_id: str,
    items: tuple["TurnItem", ...] | list["TurnItem"] = (),
    *,
    items_view: str = "full",
    started_at: int | float | None = None,
) -> dict[str, JsonValue]:
    if not isinstance(thread_id, str):
        raise TypeError("thread_id must be a string")
    return {
        "method": "turn/started",
        "params": {
            "threadId": thread_id,
            "turn": turn_to_app_server_mapping(
                turn_id,
                items,
                status="inProgress",
                items_view=items_view,
                started_at=started_at,
            ),
        },
    }


def turn_completed_notification(
    thread_id: str,
    turn_id: str,
    items: tuple["TurnItem", ...] | list["TurnItem"],
    *,
    status: str = "completed",
    items_view: str = "full",
    error: JsonValue = None,
    started_at: int | float | None = None,
    completed_at: int | float | None = None,
    duration_ms: int | float | None = None,
) -> dict[str, JsonValue]:
    if not isinstance(thread_id, str):
        raise TypeError("thread_id must be a string")
    if status == "inProgress":
        raise ValueError("completed turn status must be terminal")
    return {
        "method": "turn/completed",
        "params": {
            "threadId": thread_id,
            "turn": turn_to_app_server_mapping(
                turn_id,
                items,
                status=status,
                items_view=items_view,
                error=error,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
            ),
        },
    }


def _user_input_from_mapping(value: JsonValue) -> UserInput:
    data = _mapping(value, "user input")
    input_type = _required_str(data, "type")
    detail = _image_detail(data.get("detail"))
    if input_type == "text":
        return UserInput.text_input(
            _required_str(data, "text"),
            tuple(_text_element_from_mapping(item) for item in data.get("text_elements", ())),
        )
    if input_type == "image":
        return UserInput.image(_required_str(data, "image_url"), detail=detail)
    if input_type == "local_image":
        return UserInput.local_image(Path(_required_str(data, "path")), detail=detail)
    if input_type == "skill":
        return UserInput.skill(_required_str(data, "name"), Path(_required_str(data, "path")))
    if input_type == "mention":
        return UserInput.mention(_required_str(data, "name"), _required_str(data, "path"))
    raise ValueError(f"unknown user input type: {input_type}")


def _image_detail(value: JsonValue) -> ImageDetail | None:
    if value is None:
        return None
    if isinstance(value, ImageDetail):
        return value
    return ImageDetail(value)


def _text_element_from_mapping(value: JsonValue) -> TextElement:
    data = _mapping(value, "text element")
    raw_range = _mapping(data["byte_range"], "byte range")
    return TextElement.new(
        ByteRange(int(raw_range["start"]), int(raw_range["end"])),
        data.get("placeholder") if isinstance(data.get("placeholder"), str) else None,
    )


def _file_change_to_mapping(change: FileChange) -> dict[str, JsonValue]:
    data: dict[str, JsonValue] = {"type": change.type}
    if change.content is not None:
        data["content"] = change.content
    if change.unified_diff is not None:
        data["unified_diff"] = change.unified_diff
    if change.move_path is not None:
        data["move_path"] = str(change.move_path)
    return data


def _file_change_from_mapping(value: JsonValue) -> FileChange:
    data = _mapping(value, "file change")
    change_type = _required_str(data, "type")
    if change_type == "add":
        return FileChange.add(_required_str(data, "content"))
    if change_type == "delete":
        return FileChange.delete(_required_str(data, "content"))
    if change_type == "update":
        move_path = data.get("move_path")
        return FileChange.update(
            _required_str(data, "unified_diff"),
            move_path=Path(move_path) if isinstance(move_path, str) else None,
        )
    raise ValueError(f"unknown file change type: {change_type}")


def _path_to_protocol(value: Path) -> str:
    return value.as_posix()


def _changes_to_mapping(changes: Mapping[Path, FileChange]) -> dict[str, JsonValue]:
    return {_path_to_protocol(path): _file_change_to_mapping(change) for path, change in changes.items()}


def _changes_from_mapping(value: JsonValue) -> dict[Path, FileChange]:
    data = _mapping(value, "file changes")
    return {Path(str(path)): _file_change_from_mapping(change) for path, change in data.items()}


def _changes_from_any_mapping(value: JsonValue) -> dict[Path, FileChange]:
    if isinstance(value, Mapping):
        return _changes_from_mapping(value)
    if isinstance(value, (list, tuple)):
        return {_app_server_file_change_path(item): _app_server_file_change(item) for item in value}
    raise TypeError("changes must be a mapping or list")


def _app_server_file_change_path(value: JsonValue) -> Path:
    data = _mapping(value, "file update change")
    return Path(_required_str(data, "path"))


def _app_server_file_change(value: JsonValue) -> FileChange:
    data = _mapping(value, "file update change")
    kind = data.get("kind")
    diff = _required_str(data, "diff")
    if isinstance(kind, Mapping):
        kind_type = _required_str(kind, "type")
        if kind_type == "add":
            return FileChange.add(diff)
        if kind_type == "delete":
            return FileChange.delete(diff)
        if kind_type == "update":
            move_path = kind.get("move_path", kind.get("movePath"))
            return FileChange.update(
                _strip_app_server_move_suffix(diff, move_path),
                move_path=Path(move_path) if isinstance(move_path, str) else None,
            )
    if kind == "add":
        return FileChange.add(diff)
    if kind == "delete":
        return FileChange.delete(diff)
    raise ValueError(f"unknown file update change kind: {kind}")


def _strip_app_server_move_suffix(diff: str, move_path: JsonValue) -> str:
    if not isinstance(move_path, str):
        return diff
    suffix = f"\n\nMoved to: {move_path}"
    if diff.endswith(suffix):
        return diff[: -len(suffix)]
    return diff


def _patch_change_kind_to_app_server(change: FileChange) -> JsonValue:
    if change.type == "add":
        return {"type": "add"}
    if change.type == "delete":
        return {"type": "delete"}
    if change.type == "update":
        data: dict[str, JsonValue] = {"type": "update"}
        if change.move_path is not None:
            data["move_path"] = str(change.move_path)
        return data
    raise ValueError(f"unknown file change type: {change.type}")


def _file_change_diff(change: FileChange) -> str:
    if change.type in {"add", "delete"}:
        return change.content or ""
    if change.type == "update":
        diff = change.unified_diff or ""
        if change.move_path is not None:
            return f"{diff}\n\nMoved to: {change.move_path}"
        return diff
    raise ValueError(f"unknown file change type: {change.type}")


def _file_changes_to_app_server_entries(changes: Mapping[Path, FileChange]) -> list[dict[str, JsonValue]]:
    entries = [
        {
            "path": _path_to_protocol(path),
            "kind": _patch_change_kind_to_app_server(change),
            "diff": _file_change_diff(change),
        }
        for path, change in changes.items()
    ]
    entries.sort(key=lambda item: str(item["path"]))
    return entries


_APP_SERVER_TURN_ITEM_TYPES = {
    "agentMessage": "AgentMessage",
    "commandExecution": "CommandExecution",
    "contextCompaction": "ContextCompaction",
    "fileChange": "FileChange",
    "hookPrompt": "HookPrompt",
    "imageGeneration": "ImageGeneration",
    "imageView": "ImageView",
    "mcpToolCall": "McpToolCall",
    "dynamicToolCall": "DynamicToolCall",
    "collabAgentToolCall": "CollabAgentToolCall",
    "enteredReviewMode": "EnteredReviewMode",
    "exitedReviewMode": "ExitedReviewMode",
    "plan": "Plan",
    "reasoning": "Reasoning",
    "userMessage": "UserMessage",
    "webSearch": "WebSearch",
}


def _turn_item_type(value: str) -> str:
    return _APP_SERVER_TURN_ITEM_TYPES.get(value, value)


def _memory_citation_to_app_server(value: MemoryCitation) -> dict[str, JsonValue]:
    data = value.to_mapping()
    return {
        "entries": data["entries"],
        "threadIds": data["rolloutIds"],
    }


def _memory_citation_from_app_server(value: JsonValue) -> MemoryCitation:
    data = _mapping(value, "memory citation")
    return MemoryCitation.from_mapping(
        {
            "entries": data.get("entries", []),
            "rolloutIds": data.get("threadIds", data.get("rolloutIds", [])),
        }
    )


def _text_element_to_app_server(element: TextElement) -> dict[str, JsonValue]:
    return {
        "byteRange": element.byte_range.to_mapping(),
        "placeholder": element.placeholder_for_conversion_only(),
    }


def _text_element_from_app_server(value: JsonValue) -> TextElement:
    data = _mapping(value, "text element")
    raw_range = data.get("byteRange", data.get("byte_range"))
    return TextElement.new(
        ByteRange.from_mapping(raw_range),
        data.get("placeholder") if isinstance(data.get("placeholder"), str) else None,
    )


def _user_input_to_app_server(item: UserInput) -> dict[str, JsonValue]:
    if item.type == "text":
        return {
            "type": "text",
            "text": item.text,
            "text_elements": [_text_element_to_app_server(element) for element in item.text_elements],
        }
    if item.type == "image":
        data: dict[str, JsonValue] = {"type": "image", "url": item.image_url}
        if item.detail is not None:
            data["detail"] = item.detail.value
        return data
    if item.type == "local_image":
        data = {"type": "localImage", "path": _path_to_protocol(Path(item.path))}
        if item.detail is not None:
            data["detail"] = item.detail.value
        return data
    if item.type == "skill":
        return {"type": "skill", "name": item.name, "path": _path_to_protocol(Path(item.path))}
    if item.type == "mention":
        return {"type": "mention", "name": item.name, "path": item.path}
    raise ValueError(f"unknown user input type: {item.type}")


def _user_input_from_app_server(value: JsonValue) -> UserInput:
    data = _mapping(value, "user input")
    input_type = _required_str(data, "type")
    if input_type == "text":
        text_elements = data.get("text_elements", ())
        if isinstance(text_elements, str) or not isinstance(text_elements, (list, tuple)):
            raise TypeError("text_elements must be a list")
        return UserInput.text_input(
            _required_str(data, "text"),
            tuple(_text_element_from_app_server(item) for item in text_elements),
        )
    if input_type == "image":
        detail = _image_detail(data.get("detail"))
        return UserInput.image(_required_str(data, "url"), detail=detail)
    if input_type == "localImage":
        detail = _image_detail(data.get("detail"))
        return UserInput.local_image(Path(_required_str(data, "path")), detail=detail)
    if input_type == "skill":
        return UserInput.skill(_required_str(data, "name"), Path(_required_str(data, "path")))
    if input_type == "mention":
        return UserInput.mention(_required_str(data, "name"), _required_str(data, "path"))
    return _user_input_from_mapping(data)


def _user_input_from_any_mapping(value: JsonValue) -> UserInput:
    data = _mapping(value, "user input")
    input_type = _required_str(data, "type")
    if input_type in {"text", "image", "skill", "mention"} and "url" not in data:
        if input_type != "text" or not any(
            isinstance(element, Mapping) and "byteRange" in element
            for element in data.get("text_elements", ())
        ):
            return _user_input_from_mapping(data)
    return _user_input_from_app_server(data)


def _web_search_action_to_app_server(action: WebSearchAction) -> dict[str, JsonValue]:
    if action.type == "search":
        return {
            "type": "search",
            "query": action.query,
            "queries": list(action.queries) if action.queries is not None else None,
        }
    if action.type == "open_page":
        return {"type": "openPage", "url": action.url}
    if action.type == "find_in_page":
        return {"type": "findInPage", "url": action.url, "pattern": action.pattern}
    if action.type == "other":
        return {"type": "other"}
    raise ValueError(f"unknown web search action type: {action.type}")


def _web_search_action_from_app_server(value: JsonValue) -> WebSearchAction:
    data = _mapping(value, "web search action")
    action_type = _required_str(data, "type")
    if action_type == "search":
        return WebSearchAction.search(
            query=_optional_str(data, "query"),
            queries=data.get("queries"),
        )
    if action_type == "openPage":
        return WebSearchAction.open_page(_optional_str(data, "url"))
    if action_type == "findInPage":
        return WebSearchAction.find_in_page(
            url=_optional_str(data, "url"),
            pattern=_optional_str(data, "pattern"),
        )
    if action_type == "other":
        return WebSearchAction.other()
    return WebSearchAction.from_mapping(data)


def _trim_trailing_default_image_details(details: list[ImageDetail | None]) -> tuple[ImageDetail | None, ...]:
    while details and details[-1] is None:
        details.pop()
    return tuple(details)


@dataclass(frozen=True)
class UserMessageItem:
    id: str
    content: tuple[UserInput, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.content, (list, tuple)):
            raise TypeError("content must be a list or tuple")
        if not isinstance(self.content, tuple):
            object.__setattr__(self, "content", tuple(self.content))
        if not all(isinstance(item, UserInput) for item in self.content):
            raise TypeError("content entries must be UserInput")

    @classmethod
    def new(cls, content: tuple[UserInput, ...] | list[UserInput]) -> "UserMessageItem":
        return cls(str(uuid.uuid4()), tuple(content))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "UserMessageItem":
        data = _mapping(value, "user message item")
        return cls(
            id=_required_str(data, "id"),
            content=tuple(_user_input_from_mapping(item) for item in _required_value(data, "content")),
        )

    def message(self) -> str:
        return "".join(item.text or "" for item in self.content if item.type == "text")

    def text_elements(self) -> tuple[TextElement, ...]:
        out: list[TextElement] = []
        offset = 0
        for item in self.content:
            if item.type != "text":
                continue
            text = item.text or ""
            for element in item.text_elements:
                byte_range = ByteRange(
                    start=offset + element.byte_range.start,
                    end=offset + element.byte_range.end,
                )
                out.append(TextElement.new(byte_range, element.placeholder(text)))
            offset += len(text.encode("utf-8"))
        return tuple(out)

    def image_urls(self) -> tuple[str, ...]:
        return tuple(item.image_url or "" for item in self.content if item.type == "image")

    def image_details(self) -> tuple[ImageDetail | None, ...]:
        return _trim_trailing_default_image_details([item.detail for item in self.content if item.type == "image"])

    def local_image_paths(self) -> tuple[Path, ...]:
        return tuple(Path(item.path) for item in self.content if item.type == "local_image" and item.path is not None)

    def local_image_details(self) -> tuple[ImageDetail | None, ...]:
        return _trim_trailing_default_image_details([item.detail for item in self.content if item.type == "local_image"])

    def as_legacy_event(self) -> EventMsg:
        return EventMsg.with_payload(
            "user_message",
            UserMessageEvent(
                message=self.message(),
                images=self.image_urls(),
                image_details=self.image_details(),
                local_images=self.local_image_paths(),
                local_image_details=self.local_image_details(),
                text_elements=self.text_elements(),
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "content": [item.to_mapping() for item in self.content]}


@dataclass(frozen=True)
class HookPromptFragment:
    text: str
    hook_run_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not isinstance(self.hook_run_id, str):
            raise TypeError("hook_run_id must be a string")

    @classmethod
    def from_single_hook(cls, text: str, hook_run_id: str) -> "HookPromptFragment":
        return cls(text=text, hook_run_id=hook_run_id)

    def to_mapping(self) -> dict[str, str]:
        return {"text": self.text, "hookRunId": self.hook_run_id}


@dataclass(frozen=True)
class HookPromptItem:
    id: str
    fragments: tuple[HookPromptFragment, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.fragments, (list, tuple)):
            raise TypeError("fragments must be a list or tuple")
        if not isinstance(self.fragments, tuple):
            object.__setattr__(self, "fragments", tuple(self.fragments))
        if not all(isinstance(fragment, HookPromptFragment) for fragment in self.fragments):
            raise TypeError("fragments entries must be HookPromptFragment")

    @classmethod
    def from_fragments(
        cls,
        id: str | None,
        fragments: tuple[HookPromptFragment, ...] | list[HookPromptFragment],
    ) -> "HookPromptItem":
        return cls(str(uuid.uuid4()) if id is None else id, tuple(fragments))


def serialize_hook_prompt_fragment(text: str, hook_run_id: str) -> str | None:
    if hook_run_id.strip() == "":
        return None
    element = ET.Element("hook_prompt", {"hook_run_id": hook_run_id})
    element.text = text
    return ET.tostring(element, encoding="unicode", short_empty_elements=False)


def parse_hook_prompt_fragment(text: str) -> HookPromptFragment | None:
    try:
        element = ET.fromstring(text.strip())
    except ET.ParseError:
        return None
    if element.tag != "hook_prompt":
        return None
    hook_run_id = element.attrib.get("hook_run_id", "")
    if hook_run_id.strip() == "":
        return None
    return HookPromptFragment(text=element.text or "", hook_run_id=hook_run_id)


def build_hook_prompt_message(fragments: tuple[HookPromptFragment, ...] | list[HookPromptFragment]) -> ResponseItem | None:
    content = []
    for fragment in fragments:
        serialized = serialize_hook_prompt_fragment(fragment.text, fragment.hook_run_id)
        if serialized is not None:
            content.append(ContentItem.input_text(serialized))
    if not content:
        return None
    return ResponseItem.message("user", tuple(content), id=str(uuid.uuid4()))


def parse_hook_prompt_message(id: str | None, content: tuple[JsonValue, ...] | list[JsonValue]) -> HookPromptItem | None:
    fragments: list[HookPromptFragment] = []
    for item in content:
        if isinstance(item, ContentItem):
            if item.type != "input_text":
                return None
            text = item.text or ""
        else:
            data = _mapping(item, "content item")
            if data.get("type") not in {"input_text", "InputText"}:
                return None
            text = _required_str(data, "text")
        fragment = parse_hook_prompt_fragment(text)
        if fragment is None:
            return None
        fragments.append(fragment)
    if not fragments:
        return None
    return HookPromptItem.from_fragments(id, tuple(fragments))


@dataclass(frozen=True)
class AgentMessageContent:
    type: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type != "Text":
            raise ValueError(f"unknown agent message content type: {self.type}")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    @classmethod
    def text_content(cls, text: str) -> "AgentMessageContent":
        return cls("Text", text)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AgentMessageContent":
        data = _mapping(value, "agent message content")
        content_type = _required_str(data, "type")
        if content_type != "Text":
            raise ValueError(f"unknown agent message content type: {content_type}")
        return cls.text_content(_required_str(data, "text"))

    def to_mapping(self) -> dict[str, str]:
        return {"type": self.type, "text": self.text}


@dataclass(frozen=True)
class AgentMessageItem:
    id: str
    content: tuple[AgentMessageContent, ...]
    phase: MessagePhase | None = None
    memory_citation: MemoryCitation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.content, (list, tuple)):
            raise TypeError("content must be a list or tuple")
        if not isinstance(self.content, tuple):
            object.__setattr__(self, "content", tuple(self.content))
        if not all(isinstance(item, AgentMessageContent) for item in self.content):
            raise TypeError("content entries must be AgentMessageContent")
        object.__setattr__(self, "phase", _optional_message_phase(self.phase))
        if self.memory_citation is not None and not isinstance(self.memory_citation, MemoryCitation):
            raise TypeError("memory_citation must be a MemoryCitation or None")

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AgentMessageItem):
            return NotImplemented
        return (
            self.id == other.id
            and "".join(content.text for content in self.content)
            == "".join(content.text for content in other.content)
            and self.phase == other.phase
            and self.memory_citation == other.memory_citation
        )

    @classmethod
    def new(cls, content: tuple[AgentMessageContent, ...] | list[AgentMessageContent]) -> "AgentMessageItem":
        return cls(str(uuid.uuid4()), tuple(content))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AgentMessageItem":
        data = _mapping(value, "agent message item")
        return cls(
            id=_required_str(data, "id"),
            content=tuple(AgentMessageContent.from_mapping(item) for item in _required_value(data, "content")),
            phase=_optional_message_phase(data.get("phase")),
            memory_citation=(
                MemoryCitation.from_mapping(data["memory_citation"])
                if data.get("memory_citation") is not None
                else None
            ),
        )

    def as_legacy_events(self) -> list[EventMsg]:
        return [
            EventMsg.with_payload(
                "agent_message",
                AgentMessageEvent(message=content.text, phase=self.phase, memory_citation=self.memory_citation),
            )
            for content in self.content
        ]


@dataclass(frozen=True)
class PlanItem:
    id: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")


@dataclass(frozen=True)
class ReasoningItem:
    id: str
    summary_text: tuple[str, ...]
    raw_content: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if isinstance(self.summary_text, str) or not isinstance(self.summary_text, (list, tuple)):
            raise TypeError("summary_text must be a list or tuple of strings")
        if isinstance(self.raw_content, str) or not isinstance(self.raw_content, (list, tuple)):
            raise TypeError("raw_content must be a list or tuple of strings")
        if not isinstance(self.summary_text, tuple):
            object.__setattr__(self, "summary_text", tuple(self.summary_text))
        if not isinstance(self.raw_content, tuple):
            object.__setattr__(self, "raw_content", tuple(self.raw_content))
        if not all(isinstance(item, str) for item in self.summary_text):
            raise TypeError("summary_text entries must be strings")
        if not all(isinstance(item, str) for item in self.raw_content):
            raise TypeError("raw_content entries must be strings")

    def as_legacy_events(self, show_raw_agent_reasoning: bool) -> list[EventMsg]:
        events = [EventMsg.with_payload("agent_reasoning", AgentReasoningEvent(summary)) for summary in self.summary_text]
        if show_raw_agent_reasoning:
            events.extend(
                EventMsg.with_payload("agent_reasoning_raw_content", AgentReasoningRawContentEvent(entry))
                for entry in self.raw_content
            )
        return events


@dataclass(frozen=True)
class WebSearchItem:
    id: str
    query: str
    action: WebSearchAction

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.query, str):
            raise TypeError("query must be a string")
        if isinstance(self.action, Mapping):
            if not self.action:
                object.__setattr__(self, "action", WebSearchAction.other())
            else:
                object.__setattr__(self, "action", WebSearchAction.from_mapping(self.action))
        if not isinstance(self.action, WebSearchAction):
            raise TypeError("action must be a WebSearchAction or mapping")

    def as_legacy_event(self) -> EventMsg:
        return EventMsg.with_payload("web_search_end", WebSearchEndEvent(self.id, self.query, self.action))


@dataclass(frozen=True)
class ImageViewItem:
    id: str
    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.path, (str, Path)):
            raise TypeError("path must be a string or Path")
        if not isinstance(self.path, Path):
            object.__setattr__(self, "path", Path(self.path))


@dataclass(frozen=True)
class ImageGenerationItem:
    id: str
    status: str
    result: str
    revised_prompt: str | None = None
    saved_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if not isinstance(self.result, str):
            raise TypeError("result must be a string")
        if self.revised_prompt is not None and not isinstance(self.revised_prompt, str):
            raise TypeError("revised_prompt must be a string or None")
        if self.saved_path is not None and not isinstance(self.saved_path, (str, Path)):
            raise TypeError("saved_path must be a string, Path, or None")
        if self.saved_path is not None and not isinstance(self.saved_path, Path):
            object.__setattr__(self, "saved_path", Path(self.saved_path))

    def as_legacy_event(self) -> EventMsg:
        return EventMsg.with_payload(
            "image_generation_end",
            ImageGenerationEndEvent(self.id, self.status, self.result, self.revised_prompt, self.saved_path),
        )


@dataclass(frozen=True)
class FileChangeItem:
    id: str
    changes: dict[Path, FileChange]
    status: PatchApplyStatus | None = None
    auto_approved: bool | None = None
    stdout: str | None = None
    stderr: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.changes, Mapping):
            raise TypeError("changes must be a mapping")
        normalized_changes: dict[Path, FileChange] = {}
        for path, change in self.changes.items():
            if not isinstance(path, (str, Path)):
                raise TypeError("changes keys must be strings or Path")
            if not isinstance(change, FileChange):
                raise TypeError("changes values must be FileChange")
            normalized_changes[Path(path)] = change
        object.__setattr__(self, "changes", normalized_changes)
        if self.status == "inProgress":
            object.__setattr__(self, "status", None)
        if self.status is not None and not isinstance(self.status, PatchApplyStatus):
            object.__setattr__(self, "status", PatchApplyStatus(self.status))
        if self.auto_approved is not None and not isinstance(self.auto_approved, bool):
            raise TypeError("auto_approved must be a bool or None")
        if self.stdout is not None and not isinstance(self.stdout, str):
            raise TypeError("stdout must be a string or None")
        if self.stderr is not None and not isinstance(self.stderr, str):
            raise TypeError("stderr must be a string or None")

    def as_legacy_begin_event(self, turn_id: str) -> EventMsg:
        return EventMsg.with_payload(
            "patch_apply_begin",
            PatchApplyBeginEvent(self.id, self.auto_approved or False, self.changes, turn_id=turn_id),
        )

    def as_legacy_end_event(self, turn_id: str) -> EventMsg | None:
        if self.status is None:
            return None
        return EventMsg.with_payload(
            "patch_apply_end",
            PatchApplyEndEvent(
                self.id,
                self.stdout or "",
                self.stderr or "",
                self.status is PatchApplyStatus.COMPLETED,
                self.status,
                turn_id=turn_id,
                changes=self.changes,
            ),
        )

    def to_app_server_mapping(self) -> dict[str, JsonValue]:
        return {
            "type": "fileChange",
            "id": self.id,
            "changes": _file_changes_to_app_server_entries(self.changes),
            "status": getattr(self.status, "value", self.status) if self.status is not None else "inProgress",
        }


class McpToolCallStatus(str):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


_MCP_TOOL_CALL_STATUS_VALUES = {
    McpToolCallStatus.IN_PROGRESS,
    McpToolCallStatus.COMPLETED,
    McpToolCallStatus.FAILED,
}


class CommandExecutionStatus(str):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"


_COMMAND_EXECUTION_STATUS_VALUES = {
    CommandExecutionStatus.IN_PROGRESS,
    CommandExecutionStatus.COMPLETED,
    CommandExecutionStatus.FAILED,
    CommandExecutionStatus.DECLINED,
}


class CommandExecutionSource(str):
    AGENT = "agent"
    USER_SHELL = "userShell"
    UNIFIED_EXEC_STARTUP = "unifiedExecStartup"
    UNIFIED_EXEC_INTERACTION = "unifiedExecInteraction"


_COMMAND_EXECUTION_SOURCE_VALUES = {
    CommandExecutionSource.AGENT,
    CommandExecutionSource.USER_SHELL,
    CommandExecutionSource.UNIFIED_EXEC_STARTUP,
    CommandExecutionSource.UNIFIED_EXEC_INTERACTION,
}


class DynamicToolCallStatus(str):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


_DYNAMIC_TOOL_CALL_STATUS_VALUES = {
    DynamicToolCallStatus.IN_PROGRESS,
    DynamicToolCallStatus.COMPLETED,
    DynamicToolCallStatus.FAILED,
}


class CollabAgentToolCallStatus(str):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


_COLLAB_AGENT_TOOL_CALL_STATUS_VALUES = {
    CollabAgentToolCallStatus.IN_PROGRESS,
    CollabAgentToolCallStatus.COMPLETED,
    CollabAgentToolCallStatus.FAILED,
}


class CollabAgentTool(str):
    SPAWN_AGENT = "spawnAgent"
    SEND_INPUT = "sendInput"
    RESUME_AGENT = "resumeAgent"
    WAIT = "wait"
    CLOSE_AGENT = "closeAgent"


_COLLAB_AGENT_TOOL_VALUES = {
    CollabAgentTool.SPAWN_AGENT,
    CollabAgentTool.SEND_INPUT,
    CollabAgentTool.RESUME_AGENT,
    CollabAgentTool.WAIT,
    CollabAgentTool.CLOSE_AGENT,
}


class CollabAgentStatus(str):
    PENDING_INIT = "pendingInit"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    ERRORED = "errored"
    SHUTDOWN = "shutdown"
    NOT_FOUND = "notFound"


_COLLAB_AGENT_STATUS_VALUES = {
    CollabAgentStatus.PENDING_INIT,
    CollabAgentStatus.RUNNING,
    CollabAgentStatus.INTERRUPTED,
    CollabAgentStatus.COMPLETED,
    CollabAgentStatus.ERRORED,
    CollabAgentStatus.SHUTDOWN,
    CollabAgentStatus.NOT_FOUND,
}


@dataclass(frozen=True)
class McpToolCallError:
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.message, str):
            raise TypeError("message must be a string")


@dataclass(frozen=True)
class McpToolCallItem:
    id: str
    server: str
    tool: str
    arguments: JsonValue
    status: str
    mcp_app_resource_uri: str | None = None
    plugin_id: str | None = None
    result: CallToolResult | None = None
    error: McpToolCallError | None = None
    duration: JsonValue | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.server, str):
            raise TypeError("server must be a string")
        if not isinstance(self.tool, str):
            raise TypeError("tool must be a string")
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if self.status not in _MCP_TOOL_CALL_STATUS_VALUES:
            raise ValueError(f"unknown mcp tool call status: {self.status}")
        if self.mcp_app_resource_uri is not None and not isinstance(self.mcp_app_resource_uri, str):
            raise TypeError("mcp_app_resource_uri must be a string or None")
        if self.plugin_id is not None and not isinstance(self.plugin_id, str):
            raise TypeError("plugin_id must be a string or None")
        if self.result is not None and not isinstance(self.result, CallToolResult):
            raise TypeError("result must be a CallToolResult or None")
        if self.error is not None and not isinstance(self.error, McpToolCallError):
            raise TypeError("error must be a McpToolCallError or None")

    def _legacy_invocation(self) -> McpInvocation:
        return McpInvocation(self.server, self.tool, None if self.arguments is None else self.arguments)

    def as_legacy_begin_event(self) -> EventMsg:
        return EventMsg.with_payload(
            "mcp_tool_call_begin",
            McpToolCallBeginEvent(
                call_id=self.id,
                invocation=self._legacy_invocation(),
                mcp_app_resource_uri=self.mcp_app_resource_uri,
                plugin_id=self.plugin_id,
            ),
        )

    def as_legacy_end_event(self) -> EventMsg | None:
        if self.duration is None:
            return None
        if self.result is not None:
            result: CallToolResult | str = self.result
        elif self.error is not None:
            result = self.error.message
        else:
            return None
        return EventMsg.with_payload(
            "mcp_tool_call_end",
            McpToolCallEndEvent(
                call_id=self.id,
                invocation=self._legacy_invocation(),
                mcp_app_resource_uri=self.mcp_app_resource_uri,
                plugin_id=self.plugin_id,
                duration=self.duration,
                result=result,
            ),
        )

    def to_app_server_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "type": "mcpToolCall",
            "id": self.id,
            "server": self.server,
            "tool": self.tool,
            "status": self.status,
            "arguments": self.arguments,
            "pluginId": self.plugin_id,
            "result": _mcp_tool_call_result_to_app_server(self.result) if self.result is not None else None,
            "error": {"message": self.error.message} if self.error is not None else None,
            "durationMs": _duration_to_app_server_millis(self.duration),
        }
        if self.mcp_app_resource_uri is not None:
            data["mcpAppResourceUri"] = self.mcp_app_resource_uri
        return data


@dataclass(frozen=True)
class CommandExecutionItem:
    id: str
    command: str
    cwd: Path
    status: str
    process_id: str | None = None
    source: str = "agent"
    command_actions: tuple[JsonValue, ...] = ()
    aggregated_output: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")
        if not isinstance(self.cwd, (str, Path)):
            raise TypeError("cwd must be a string or Path")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if self.status not in _COMMAND_EXECUTION_STATUS_VALUES:
            raise ValueError(f"unknown command execution status: {self.status}")
        if self.process_id is not None and not isinstance(self.process_id, str):
            raise TypeError("process_id must be a string or None")
        if not isinstance(self.source, str):
            raise TypeError("source must be a string")
        if self.source not in _COMMAND_EXECUTION_SOURCE_VALUES:
            raise ValueError(f"unknown command execution source: {self.source}")
        if not isinstance(self.command_actions, (list, tuple)):
            raise TypeError("command_actions must be a list or tuple")
        if not isinstance(self.command_actions, tuple):
            object.__setattr__(self, "command_actions", tuple(self.command_actions))
        if self.aggregated_output is not None and not isinstance(self.aggregated_output, str):
            raise TypeError("aggregated_output must be a string or None")
        if self.exit_code is not None and (isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int)):
            raise TypeError("exit_code must be an int or None")
        if self.exit_code is not None and not I32_MIN <= self.exit_code <= I32_MAX:
            raise ValueError("exit_code must fit in i32")
        if self.duration_ms is not None and (isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int)):
            raise TypeError("duration_ms must be an int or None")
        if self.duration_ms is not None and not I64_MIN <= self.duration_ms <= I64_MAX:
            raise ValueError("duration_ms must fit in i64")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "command": self.command,
            "cwd": _path_to_protocol(self.cwd),
            "processId": self.process_id,
            "source": self.source,
            "status": self.status,
            "commandActions": list(self.command_actions),
            "aggregatedOutput": self.aggregated_output,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
        }


@dataclass(frozen=True)
class DynamicToolCallItem:
    id: str
    namespace: str | None
    tool: str
    arguments: JsonValue
    status: str
    content_items: tuple[JsonValue, ...] | None = None
    success: bool | None = None
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if self.namespace is not None and not isinstance(self.namespace, str):
            raise TypeError("namespace must be a string or None")
        if not isinstance(self.tool, str):
            raise TypeError("tool must be a string")
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if self.status not in _DYNAMIC_TOOL_CALL_STATUS_VALUES:
            raise ValueError(f"unknown dynamic tool call status: {self.status}")
        if self.content_items is not None and not isinstance(self.content_items, (list, tuple)):
            raise TypeError("content_items must be a list, tuple, or None")
        if self.content_items is not None and not isinstance(self.content_items, tuple):
            object.__setattr__(self, "content_items", tuple(self.content_items))
        if self.success is not None and not isinstance(self.success, bool):
            raise TypeError("success must be a bool or None")
        if self.duration_ms is not None and (isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int)):
            raise TypeError("duration_ms must be an int or None")
        if self.duration_ms is not None and not I64_MIN <= self.duration_ms <= I64_MAX:
            raise ValueError("duration_ms must fit in i64")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "tool": self.tool,
            "arguments": self.arguments,
            "status": self.status,
            "content_items": list(self.content_items) if self.content_items is not None else None,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }

    def to_app_server_mapping(self) -> dict[str, JsonValue]:
        return {
            "type": "dynamicToolCall",
            "id": self.id,
            "namespace": self.namespace,
            "tool": self.tool,
            "arguments": self.arguments,
            "status": self.status,
            "contentItems": list(self.content_items) if self.content_items is not None else None,
            "success": self.success,
            "durationMs": self.duration_ms,
        }


@dataclass(frozen=True)
class CollabAgentState:
    status: str
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if self.status not in _COLLAB_AGENT_STATUS_VALUES:
            raise ValueError(f"unknown collab agent status: {self.status}")
        if self.message is not None and not isinstance(self.message, str):
            raise TypeError("message must be a string or None")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CollabAgentState":
        data = _mapping(value, "collab agent state")
        return cls(status=_required_str(data, "status"), message=_optional_str(data, "message"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"status": self.status, "message": self.message}


@dataclass(frozen=True)
class CollabAgentToolCallItem:
    id: str
    tool: str
    status: str
    sender_thread_id: str
    receiver_thread_ids: tuple[str, ...]
    prompt: str | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort | None = None
    agents_states: dict[str, CollabAgentState] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.tool, str):
            raise TypeError("tool must be a string")
        if self.tool not in _COLLAB_AGENT_TOOL_VALUES:
            raise ValueError(f"unknown collab agent tool: {self.tool}")
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if self.status not in _COLLAB_AGENT_TOOL_CALL_STATUS_VALUES:
            raise ValueError(f"unknown collab agent tool call status: {self.status}")
        if not isinstance(self.sender_thread_id, str):
            raise TypeError("sender_thread_id must be a string")
        if isinstance(self.receiver_thread_ids, str) or not isinstance(self.receiver_thread_ids, (list, tuple)):
            raise TypeError("receiver_thread_ids must be a list or tuple of strings")
        if not all(isinstance(thread_id, str) for thread_id in self.receiver_thread_ids):
            raise TypeError("receiver_thread_ids entries must be strings")
        if not isinstance(self.receiver_thread_ids, tuple):
            object.__setattr__(self, "receiver_thread_ids", tuple(self.receiver_thread_ids))
        if self.prompt is not None and not isinstance(self.prompt, str):
            raise TypeError("prompt must be a string or None")
        if self.model is not None and not isinstance(self.model, str):
            raise TypeError("model must be a string or None")
        if self.reasoning_effort is not None and not isinstance(self.reasoning_effort, ReasoningEffort):
            if not isinstance(self.reasoning_effort, str):
                raise TypeError("reasoning_effort must be a ReasoningEffort, string, or None")
            object.__setattr__(self, "reasoning_effort", ReasoningEffort.parse(self.reasoning_effort))
        if self.agents_states is None:
            object.__setattr__(self, "agents_states", {})
        elif not isinstance(self.agents_states, Mapping):
            raise TypeError("agents_states must be a mapping or None")
        else:
            states: dict[str, CollabAgentState] = {}
            for key, value in self.agents_states.items():
                if not isinstance(key, str):
                    raise TypeError("agents_states keys must be strings")
                states[key] = value if isinstance(value, CollabAgentState) else CollabAgentState.from_mapping(value)
            object.__setattr__(self, "agents_states", states)

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "id": self.id,
            "tool": self.tool,
            "status": self.status,
            "sender_thread_id": self.sender_thread_id,
            "receiver_thread_ids": list(self.receiver_thread_ids),
            "prompt": self.prompt,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort.value if self.reasoning_effort is not None else None,
            "agents_states": {key: value.to_mapping() for key, value in self.agents_states.items()},
        }

    def to_app_server_mapping(self) -> dict[str, JsonValue]:
        return {
            "type": "collabAgentToolCall",
            "id": self.id,
            "tool": self.tool,
            "status": self.status,
            "senderThreadId": self.sender_thread_id,
            "receiverThreadIds": list(self.receiver_thread_ids),
            "prompt": self.prompt,
            "model": self.model,
            "reasoningEffort": self.reasoning_effort.value if self.reasoning_effort is not None else None,
            "agentsStates": {key: value.to_mapping() for key, value in self.agents_states.items()},
        }


@dataclass(frozen=True)
class ReviewModeItem:
    id: str
    review: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if not isinstance(self.review, str):
            raise TypeError("review must be a string")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"id": self.id, "review": self.review}


@dataclass(frozen=True)
class ContextCompactionItem:
    id: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")

    @classmethod
    def new(cls) -> "ContextCompactionItem":
        return cls(str(uuid.uuid4()))

    def as_legacy_event(self) -> EventMsg:
        return EventMsg.with_payload("context_compacted", ContextCompactedEvent())


@dataclass(frozen=True)
class TurnItem:
    type: str
    item: JsonValue

    def __post_init__(self) -> None:
        expected_type = _TURN_ITEM_TYPES.get(self.type)
        if expected_type is None:
            raise ValueError(f"unknown turn item type: {self.type}")
        if not isinstance(self.item, expected_type):
            raise TypeError(f"{self.type} item must be {expected_type.__name__}")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TurnItem":
        data = _mapping(value, "turn item")
        raw_item_type = _required_str(data, "type")
        item_type = _turn_item_type(raw_item_type)
        payload = {key: item for key, item in data.items() if key != "type"}
        if raw_item_type == "webSearch" and "action" not in payload:
            payload["action"] = None
        parser = _TURN_ITEM_PARSERS.get(item_type)
        if parser is None:
            raise ValueError(f"unknown turn item type: {item_type}")
        return cls(item_type, parser(payload))

    @classmethod
    def user_message(cls, item: UserMessageItem) -> "TurnItem":
        return cls("UserMessage", item)

    @classmethod
    def hook_prompt(cls, item: HookPromptItem) -> "TurnItem":
        return cls("HookPrompt", item)

    @classmethod
    def agent_message(cls, item: AgentMessageItem) -> "TurnItem":
        return cls("AgentMessage", item)

    @classmethod
    def plan(cls, item: PlanItem) -> "TurnItem":
        return cls("Plan", item)

    @classmethod
    def reasoning(
        cls,
        item: ReasoningItem | str,
        summary_text: tuple[str, ...] | list[str] = (),
        raw_content: tuple[str, ...] | list[str] = (),
    ) -> "TurnItem":
        if isinstance(item, ReasoningItem):
            return cls("Reasoning", item)
        return cls("Reasoning", ReasoningItem(item, tuple(summary_text), tuple(raw_content)))

    @classmethod
    def web_search(cls, item: WebSearchItem) -> "TurnItem":
        return cls("WebSearch", item)

    @classmethod
    def image_view(cls, item: ImageViewItem) -> "TurnItem":
        return cls("ImageView", item)

    @classmethod
    def image_generation(cls, item: ImageGenerationItem) -> "TurnItem":
        return cls("ImageGeneration", item)

    @classmethod
    def file_change(cls, item: FileChangeItem) -> "TurnItem":
        return cls("FileChange", item)

    @classmethod
    def mcp_tool_call(cls, item: McpToolCallItem) -> "TurnItem":
        return cls("McpToolCall", item)

    @classmethod
    def command_execution(cls, item: CommandExecutionItem) -> "TurnItem":
        return cls("CommandExecution", item)

    @classmethod
    def dynamic_tool_call(cls, item: DynamicToolCallItem) -> "TurnItem":
        return cls("DynamicToolCall", item)

    @classmethod
    def collab_agent_tool_call(cls, item: CollabAgentToolCallItem) -> "TurnItem":
        return cls("CollabAgentToolCall", item)

    @classmethod
    def entered_review_mode(cls, item: ReviewModeItem) -> "TurnItem":
        return cls("EnteredReviewMode", item)

    @classmethod
    def exited_review_mode(cls, item: ReviewModeItem) -> "TurnItem":
        return cls("ExitedReviewMode", item)

    @classmethod
    def context_compaction(cls, item: ContextCompactionItem) -> "TurnItem":
        return cls("ContextCompaction", item)

    def id(self) -> str:
        return self.item.id

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "UserMessage":
            return {"type": self.type, **self.item.to_mapping()}
        if self.type == "HookPrompt":
            return {"type": self.type, "id": self.item.id, "fragments": [fragment.to_mapping() for fragment in self.item.fragments]}
        if self.type == "AgentMessage":
            data: dict[str, JsonValue] = {"type": self.type, "id": self.item.id, "content": [content.to_mapping() for content in self.item.content]}
            if self.item.phase is not None:
                data["phase"] = self.item.phase.value
            if self.item.memory_citation is not None:
                data["memory_citation"] = self.item.memory_citation.to_mapping()
            return data
        if self.type == "Plan":
            return {"type": self.type, "id": self.item.id, "text": self.item.text}
        if self.type == "Reasoning":
            return {"type": self.type, "id": self.item.id, "summary_text": list(self.item.summary_text), "raw_content": list(self.item.raw_content)}
        if self.type == "WebSearch":
            action = self.item.action.to_mapping() if hasattr(self.item.action, "to_mapping") else self.item.action
            return {"type": self.type, "id": self.item.id, "query": self.item.query, "action": action}
        if self.type == "ImageView":
            return {"type": self.type, "id": self.item.id, "path": str(self.item.path)}
        if self.type == "ImageGeneration":
            data = {"type": self.type, "id": self.item.id, "status": self.item.status, "result": self.item.result}
            if self.item.revised_prompt is not None:
                data["revised_prompt"] = self.item.revised_prompt
            if self.item.saved_path is not None:
                data["saved_path"] = str(self.item.saved_path)
            return data
        if self.type == "FileChange":
            data = {"type": self.type, "id": self.item.id, "changes": _changes_to_mapping(self.item.changes)}
            if self.item.status is not None:
                data["status"] = getattr(self.item.status, "value", self.item.status)
            if self.item.auto_approved is not None:
                data["auto_approved"] = self.item.auto_approved
            if self.item.stdout is not None:
                data["stdout"] = self.item.stdout
            if self.item.stderr is not None:
                data["stderr"] = self.item.stderr
            return data
        if self.type == "McpToolCall":
            data = {
                "type": self.type,
                "id": self.item.id,
                "server": self.item.server,
                "tool": self.item.tool,
                "arguments": self.item.arguments,
                "status": self.item.status,
            }
            if self.item.mcp_app_resource_uri is not None:
                data["mcpAppResourceUri"] = self.item.mcp_app_resource_uri
            if self.item.plugin_id is not None:
                data["pluginId"] = self.item.plugin_id
            if self.item.result is not None:
                data["result"] = self.item.result.to_mapping()
            if self.item.error is not None:
                data["error"] = {"message": self.item.error.message}
            if self.item.duration is not None:
                data["duration"] = self.item.duration
            return data
        if self.type == "CommandExecution":
            return {"type": self.type, **self.item.to_mapping()}
        if self.type == "DynamicToolCall":
            return {"type": self.type, **self.item.to_mapping()}
        if self.type == "CollabAgentToolCall":
            return {"type": self.type, **self.item.to_mapping()}
        if self.type in {"EnteredReviewMode", "ExitedReviewMode"}:
            return {"type": self.type, **self.item.to_mapping()}
        if self.type == "ContextCompaction":
            return {"type": self.type, "id": self.item.id}
        raise ValueError(f"unknown turn item type: {self.type}")

    def to_app_server_mapping(self) -> dict[str, JsonValue]:
        if self.type == "CommandExecution":
            return {"type": "commandExecution", **self.item.to_mapping()}
        if self.type == "FileChange":
            data = self.item.to_app_server_mapping()
            data["type"] = "fileChange"
            return data
        if self.type == "McpToolCall":
            return self.item.to_app_server_mapping()
        if self.type == "AgentMessage":
            return {
                "type": "agentMessage",
                "id": self.item.id,
                "text": "".join(content.text for content in self.item.content),
                "phase": self.item.phase.value if self.item.phase is not None else None,
                "memoryCitation": (
                    _memory_citation_to_app_server(self.item.memory_citation)
                    if self.item.memory_citation is not None
                    else None
                ),
            }
        if self.type == "Reasoning":
            return {
                "type": "reasoning",
                "id": self.item.id,
                "summary": list(self.item.summary_text),
                "content": list(self.item.raw_content),
            }
        if self.type == "Plan":
            return {
                "type": "plan",
                "id": self.item.id,
                "text": self.item.text,
            }
        if self.type == "ContextCompaction":
            return {
                "type": "contextCompaction",
                "id": self.item.id,
            }
        if self.type == "UserMessage":
            return {
                "type": "userMessage",
                "id": self.item.id,
                "content": [_user_input_to_app_server(item) for item in self.item.content],
            }
        if self.type == "HookPrompt":
            return {
                "type": "hookPrompt",
                "id": self.item.id,
                "fragments": [fragment.to_mapping() for fragment in self.item.fragments],
            }
        if self.type == "WebSearch":
            return {
                "type": "webSearch",
                "id": self.item.id,
                "query": self.item.query,
                "action": _web_search_action_to_app_server(self.item.action),
            }
        if self.type == "ImageView":
            return {
                "type": "imageView",
                "id": self.item.id,
                "path": str(self.item.path),
            }
        if self.type == "ImageGeneration":
            data = {
                "type": "imageGeneration",
                "id": self.item.id,
                "status": self.item.status,
                "revisedPrompt": self.item.revised_prompt,
                "result": self.item.result,
            }
            if self.item.saved_path is not None:
                data["savedPath"] = str(self.item.saved_path)
            return data
        if self.type == "DynamicToolCall":
            return self.item.to_app_server_mapping()
        if self.type == "CollabAgentToolCall":
            return self.item.to_app_server_mapping()
        if self.type == "EnteredReviewMode":
            return {"type": "enteredReviewMode", "id": self.item.id, "review": self.item.review}
        if self.type == "ExitedReviewMode":
            return {"type": "exitedReviewMode", "id": self.item.id, "review": self.item.review}
        raise ValueError(f"app-server mapping is not implemented for {self.type}")

    def as_legacy_events(self, show_raw_agent_reasoning: bool) -> list[EventMsg]:
        if self.type == "UserMessage":
            return [self.item.as_legacy_event()]
        if self.type == "HookPrompt":
            return []
        if self.type == "AgentMessage":
            return self.item.as_legacy_events()
        if self.type == "Plan":
            return []
        if self.type == "WebSearch":
            return [self.item.as_legacy_event()]
        if self.type == "ImageView":
            return [EventMsg.with_payload("view_image_tool_call", ViewImageToolCallEvent(self.item.id, self.item.path))]
        if self.type == "ImageGeneration":
            return [self.item.as_legacy_event()]
        if self.type == "FileChange":
            event = self.item.as_legacy_end_event("")
            return [event] if event is not None else []
        if self.type == "McpToolCall":
            event = self.item.as_legacy_end_event()
            return [event] if event is not None else []
        if self.type == "CommandExecution":
            return []
        if self.type in {"DynamicToolCall", "CollabAgentToolCall", "EnteredReviewMode", "ExitedReviewMode"}:
            return []
        if self.type == "Reasoning":
            return self.item.as_legacy_events(show_raw_agent_reasoning)
        if self.type == "ContextCompaction":
            return [self.item.as_legacy_event()]
        return []


def _agent_message_item(data: Mapping[str, JsonValue]) -> AgentMessageItem:
    if "text" in data and "content" not in data:
        memory_citation = data.get("memoryCitation", data.get("memory_citation"))
        return AgentMessageItem(
            id=_required_str(data, "id"),
            content=(AgentMessageContent.text_content(_required_str(data, "text")),),
            phase=_optional_message_phase(data.get("phase")),
            memory_citation=(
                _memory_citation_from_app_server(memory_citation)
                if memory_citation is not None
                else None
            ),
        )
    return AgentMessageItem.from_mapping(data)


def _plan_item(data: Mapping[str, JsonValue]) -> PlanItem:
    return PlanItem(id=_required_str(data, "id"), text=_required_str(data, "text"))


def _reasoning_item(data: Mapping[str, JsonValue]) -> ReasoningItem:
    if "summary" in data and "summary_text" not in data:
        return ReasoningItem(
            id=_required_str(data, "id"),
            summary_text=_required_value(data, "summary"),
            raw_content=data.get("content", ()),
        )
    return ReasoningItem(
        id=_required_str(data, "id"),
        summary_text=_required_value(data, "summary_text"),
        raw_content=data.get("raw_content", ()),
    )


def _web_search_item(data: Mapping[str, JsonValue]) -> WebSearchItem:
    action = _required_value(data, "action")
    if action is None:
        action = WebSearchAction.other()
    if isinstance(action, Mapping) and action.get("type") in {"openPage", "findInPage"}:
        action = _web_search_action_from_app_server(action)
    return WebSearchItem(
        id=_required_str(data, "id"),
        query=_required_str(data, "query"),
        action=action,
    )


def _image_view_item(data: Mapping[str, JsonValue]) -> ImageViewItem:
    return ImageViewItem(id=_required_str(data, "id"), path=Path(_required_str(data, "path")))


def _image_generation_item(data: Mapping[str, JsonValue]) -> ImageGenerationItem:
    return ImageGenerationItem(
        id=_required_str(data, "id"),
        status=_required_str(data, "status"),
        revised_prompt=_optional_str_alias(data, "revisedPrompt", "revised_prompt"),
        result=_required_str(data, "result"),
        saved_path=data.get("savedPath", data.get("saved_path")),
    )


def _file_change_item(data: Mapping[str, JsonValue]) -> FileChangeItem:
    return FileChangeItem(
        id=_required_str(data, "id"),
        changes=_changes_from_any_mapping(_required_value(data, "changes")),
        status=data.get("status"),
        auto_approved=data.get("auto_approved"),
        stdout=_optional_str(data, "stdout"),
        stderr=_optional_str(data, "stderr"),
    )


def _call_tool_result_from_value(value: JsonValue) -> CallToolResult | None:
    if value is None:
        return None
    return CallToolResult.from_mapping(_mapping(value, "mcp tool call result"))


def _mcp_tool_call_result_to_app_server(value: CallToolResult) -> dict[str, JsonValue]:
    data = value.to_mapping()
    result: dict[str, JsonValue] = {"content": data.get("content", [])}
    if "structuredContent" in data:
        result["structuredContent"] = data["structuredContent"]
    if "_meta" in data:
        result["_meta"] = data["_meta"]
    return result


def _duration_to_app_server_millis(value: JsonValue) -> JsonValue | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise TypeError("duration must be a duration mapping, integer milliseconds, or None")
    if isinstance(value, int):
        if not I64_MIN <= value <= I64_MAX:
            raise ValueError("durationMs must fit in i64")
        return value
    if isinstance(value, Mapping):
        secs = value.get("secs")
        nanos = value.get("nanos")
        if isinstance(secs, bool) or isinstance(nanos, bool) or not isinstance(secs, int) or not isinstance(nanos, int):
            return None
        millis = secs * 1000 + nanos // 1_000_000
        return millis if I64_MIN <= millis <= I64_MAX else None
    raise TypeError("duration must be a duration mapping, integer milliseconds, or None")


def _mcp_tool_call_error_from_value(value: JsonValue) -> McpToolCallError | None:
    if value is None:
        return None
    data = _mapping(value, "mcp tool call error")
    return McpToolCallError(_required_str(data, "message"))


def _mcp_tool_call_item(data: Mapping[str, JsonValue]) -> McpToolCallItem:
    duration = data.get("duration") if "duration" in data else _optional_int_alias(data, "durationMs", "duration_ms")
    return McpToolCallItem(
        id=_required_str(data, "id"),
        server=_required_str(data, "server"),
        tool=_required_str(data, "tool"),
        arguments=_required_value(data, "arguments"),
        mcp_app_resource_uri=_optional_str_alias(data, "mcpAppResourceUri", "mcp_app_resource_uri"),
        plugin_id=_optional_str_alias(data, "pluginId", "plugin_id"),
        status=_required_str(data, "status"),
        result=_call_tool_result_from_value(data.get("result")),
        error=_mcp_tool_call_error_from_value(data.get("error")),
        duration=duration,
    )


def _optional_int_alias(value: Mapping[str, JsonValue], primary: str, fallback: str) -> int | None:
    raw = value.get(primary) if primary in value else value.get(fallback)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{primary} must be an int or None")
    return raw


def _command_actions_from_mapping(value: Mapping[str, JsonValue]) -> tuple[JsonValue, ...]:
    raw = value.get("commandActions", value.get("command_actions", ()))
    if not isinstance(raw, (list, tuple)):
        raise TypeError("commandActions must be a list or tuple")
    return tuple(raw)


def _command_execution_item(data: Mapping[str, JsonValue]) -> CommandExecutionItem:
    return CommandExecutionItem(
        id=_required_str(data, "id"),
        command=_required_str(data, "command"),
        cwd=Path(_required_str(data, "cwd")),
        process_id=_optional_str_alias(data, "processId", "process_id"),
        source=_required_str(data, "source") if "source" in data else "agent",
        status=_required_str(data, "status"),
        command_actions=_command_actions_from_mapping(data),
        aggregated_output=_optional_str_alias(data, "aggregatedOutput", "aggregated_output"),
        exit_code=_optional_int_alias(data, "exitCode", "exit_code"),
        duration_ms=_optional_int_alias(data, "durationMs", "duration_ms"),
    )


def _dynamic_tool_call_item(data: Mapping[str, JsonValue]) -> DynamicToolCallItem:
    return DynamicToolCallItem(
        id=_required_str(data, "id"),
        namespace=_optional_str(data, "namespace"),
        tool=_required_str(data, "tool"),
        arguments=_required_value(data, "arguments"),
        status=_required_str(data, "status"),
        content_items=data.get("contentItems", data.get("content_items")),
        success=data.get("success"),
        duration_ms=_optional_int_alias(data, "durationMs", "duration_ms"),
    )


def _collab_agent_tool_call_item(data: Mapping[str, JsonValue]) -> CollabAgentToolCallItem:
    raw_receiver_thread_ids = data.get("receiverThreadIds", data.get("receiver_thread_ids"))
    if raw_receiver_thread_ids is None:
        raw_receiver_thread_ids = ()
    raw_reasoning_effort = data.get("reasoningEffort", data.get("reasoning_effort"))
    return CollabAgentToolCallItem(
        id=_required_str(data, "id"),
        tool=_required_str(data, "tool"),
        status=_required_str(data, "status"),
        sender_thread_id=_required_str(data, "senderThreadId") if "senderThreadId" in data else _required_str(data, "sender_thread_id"),
        receiver_thread_ids=raw_receiver_thread_ids,
        prompt=_optional_str(data, "prompt"),
        model=_optional_str(data, "model"),
        reasoning_effort=(ReasoningEffort.parse(raw_reasoning_effort) if raw_reasoning_effort is not None else None),
        agents_states=data.get("agentsStates", data.get("agents_states", {})),
    )


def _review_mode_item(data: Mapping[str, JsonValue]) -> ReviewModeItem:
    return ReviewModeItem(id=_required_str(data, "id"), review=_required_str(data, "review"))


def _context_compaction_item(data: Mapping[str, JsonValue]) -> ContextCompactionItem:
    return ContextCompactionItem(id=_required_str(data, "id"))


_TURN_ITEM_PARSERS = {
    "UserMessage": lambda data: UserMessageItem(
        id=_required_str(data, "id"),
        content=tuple(_user_input_from_any_mapping(item) for item in _required_value(data, "content")),
    ),
    "HookPrompt": lambda data: HookPromptItem.from_fragments(
        _required_str(data, "id"),
        tuple(
            HookPromptFragment(
                text=_required_str(fragment, "text"),
                hook_run_id=_required_str(fragment, "hookRunId") if "hookRunId" in fragment else _required_str(fragment, "hook_run_id"),
            )
            for fragment in _required_value(data, "fragments")
        ),
    ),
    "AgentMessage": _agent_message_item,
    "Plan": _plan_item,
    "Reasoning": _reasoning_item,
    "WebSearch": _web_search_item,
    "ImageView": _image_view_item,
    "ImageGeneration": _image_generation_item,
    "FileChange": _file_change_item,
    "McpToolCall": _mcp_tool_call_item,
    "CommandExecution": _command_execution_item,
    "DynamicToolCall": _dynamic_tool_call_item,
    "CollabAgentToolCall": _collab_agent_tool_call_item,
    "EnteredReviewMode": _review_mode_item,
    "ExitedReviewMode": _review_mode_item,
    "ContextCompaction": _context_compaction_item,
}

_TURN_ITEM_TYPES = {
    "UserMessage": UserMessageItem,
    "HookPrompt": HookPromptItem,
    "AgentMessage": AgentMessageItem,
    "Plan": PlanItem,
    "Reasoning": ReasoningItem,
    "WebSearch": WebSearchItem,
    "ImageView": ImageViewItem,
    "ImageGeneration": ImageGenerationItem,
    "FileChange": FileChangeItem,
    "McpToolCall": McpToolCallItem,
    "CommandExecution": CommandExecutionItem,
    "DynamicToolCall": DynamicToolCallItem,
    "CollabAgentToolCall": CollabAgentToolCallItem,
    "EnteredReviewMode": ReviewModeItem,
    "ExitedReviewMode": ReviewModeItem,
    "ContextCompaction": ContextCompactionItem,
}
