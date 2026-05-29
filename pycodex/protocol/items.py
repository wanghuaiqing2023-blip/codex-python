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


def _changes_to_mapping(changes: Mapping[Path, FileChange]) -> dict[str, JsonValue]:
    return {str(path): _file_change_to_mapping(change) for path, change in changes.items()}


def _changes_from_mapping(value: JsonValue) -> dict[Path, FileChange]:
    data = _mapping(value, "file changes")
    return {Path(str(path)): _file_change_from_mapping(change) for path, change in data.items()}


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


class McpToolCallStatus(str):
    IN_PROGRESS = "inProgress"
    COMPLETED = "completed"
    FAILED = "failed"


_MCP_TOOL_CALL_STATUS_VALUES = {
    McpToolCallStatus.IN_PROGRESS,
    McpToolCallStatus.COMPLETED,
    McpToolCallStatus.FAILED,
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
        item_type = _required_str(data, "type")
        payload = {key: item for key, item in data.items() if key != "type"}
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
    def reasoning(cls, item: ReasoningItem) -> "TurnItem":
        return cls("Reasoning", item)

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
    def context_compaction(cls, item: ContextCompactionItem) -> "TurnItem":
        return cls("ContextCompaction", item)

    def id(self) -> str:
        return self.item.id

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
        if self.type == "Reasoning":
            return self.item.as_legacy_events(show_raw_agent_reasoning)
        if self.type == "ContextCompaction":
            return [self.item.as_legacy_event()]
        return []


def _agent_message_item(data: Mapping[str, JsonValue]) -> AgentMessageItem:
    return AgentMessageItem.from_mapping(data)


def _plan_item(data: Mapping[str, JsonValue]) -> PlanItem:
    return PlanItem(id=_required_str(data, "id"), text=_required_str(data, "text"))


def _reasoning_item(data: Mapping[str, JsonValue]) -> ReasoningItem:
    return ReasoningItem(
        id=_required_str(data, "id"),
        summary_text=_required_value(data, "summary_text"),
        raw_content=data.get("raw_content", ()),
    )


def _web_search_item(data: Mapping[str, JsonValue]) -> WebSearchItem:
    action = _required_value(data, "action")
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
        revised_prompt=_optional_str(data, "revised_prompt"),
        result=_required_str(data, "result"),
        saved_path=data.get("saved_path"),
    )


def _file_change_item(data: Mapping[str, JsonValue]) -> FileChangeItem:
    return FileChangeItem(
        id=_required_str(data, "id"),
        changes=_changes_from_mapping(_required_value(data, "changes")),
        status=data.get("status"),
        auto_approved=data.get("auto_approved"),
        stdout=_optional_str(data, "stdout"),
        stderr=_optional_str(data, "stderr"),
    )


def _call_tool_result_from_value(value: JsonValue) -> CallToolResult | None:
    if value is None:
        return None
    return CallToolResult.from_mapping(_mapping(value, "mcp tool call result"))


def _mcp_tool_call_error_from_value(value: JsonValue) -> McpToolCallError | None:
    if value is None:
        return None
    data = _mapping(value, "mcp tool call error")
    return McpToolCallError(_required_str(data, "message"))


def _mcp_tool_call_item(data: Mapping[str, JsonValue]) -> McpToolCallItem:
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
        duration=data.get("duration"),
    )


def _context_compaction_item(data: Mapping[str, JsonValue]) -> ContextCompactionItem:
    return ContextCompactionItem(id=_required_str(data, "id"))


_TURN_ITEM_PARSERS = {
    "UserMessage": UserMessageItem.from_mapping,
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
    "ContextCompaction": ContextCompactionItem,
}
