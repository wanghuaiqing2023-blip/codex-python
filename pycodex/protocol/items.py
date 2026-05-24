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
from .models import ContentItem, ImageDetail, ResponseItem, WebSearchAction
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
        if not isinstance(self.content, tuple):
            object.__setattr__(self, "content", tuple(self.content))

    @classmethod
    def new(cls, content: tuple[UserInput, ...] | list[UserInput]) -> "UserMessageItem":
        return cls(str(uuid.uuid4()), tuple(content))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "UserMessageItem":
        data = _mapping(value, "user message item")
        return cls(
            id=_required_str(data, "id"),
            content=tuple(_user_input_from_mapping(item) for item in data.get("content", ())),
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
        if not isinstance(self.fragments, tuple):
            object.__setattr__(self, "fragments", tuple(self.fragments))

    @classmethod
    def from_fragments(
        cls,
        id: str | None,
        fragments: tuple[HookPromptFragment, ...] | list[HookPromptFragment],
    ) -> "HookPromptItem":
        return cls(id or str(uuid.uuid4()), tuple(fragments))


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
    phase: JsonValue | None = None
    memory_citation: MemoryCitation | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, tuple):
            object.__setattr__(self, "content", tuple(self.content))

    @classmethod
    def new(cls, content: tuple[AgentMessageContent, ...] | list[AgentMessageContent]) -> "AgentMessageItem":
        return cls(str(uuid.uuid4()), tuple(content))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AgentMessageItem":
        data = _mapping(value, "agent message item")
        return cls(
            id=_required_str(data, "id"),
            content=tuple(AgentMessageContent.from_mapping(item) for item in data.get("content", ())),
            phase=data.get("phase"),
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


@dataclass(frozen=True)
class ReasoningItem:
    id: str
    summary_text: tuple[str, ...]
    raw_content: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.summary_text, tuple):
            object.__setattr__(self, "summary_text", tuple(self.summary_text))
        if not isinstance(self.raw_content, tuple):
            object.__setattr__(self, "raw_content", tuple(self.raw_content))

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
    action: WebSearchAction | JsonValue

    def as_legacy_event(self) -> EventMsg:
        return EventMsg.with_payload("web_search_end", WebSearchEndEvent(self.id, self.query, self.action))


@dataclass(frozen=True)
class ImageViewItem:
    id: str
    path: Path


@dataclass(frozen=True)
class ImageGenerationItem:
    id: str
    status: str
    result: str
    revised_prompt: str | None = None
    saved_path: Path | None = None

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


@dataclass(frozen=True)
class McpToolCallError:
    message: str


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

    @classmethod
    def new(cls) -> "ContextCompactionItem":
        return cls(str(uuid.uuid4()))

    def as_legacy_event(self) -> EventMsg:
        return EventMsg.with_payload("context_compacted", ContextCompactedEvent())


@dataclass(frozen=True)
class TurnItem:
    type: str
    item: JsonValue

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
        summary_text=tuple(data.get("summary_text", ())),
        raw_content=tuple(data.get("raw_content", ())),
    )


def _web_search_item(data: Mapping[str, JsonValue]) -> WebSearchItem:
    action = data.get("action")
    return WebSearchItem(
        id=_required_str(data, "id"),
        query=_required_str(data, "query"),
        action=WebSearchAction.from_mapping(action) if isinstance(action, Mapping) else action,
    )


def _image_view_item(data: Mapping[str, JsonValue]) -> ImageViewItem:
    return ImageViewItem(id=_required_str(data, "id"), path=Path(_required_str(data, "path")))


def _image_generation_item(data: Mapping[str, JsonValue]) -> ImageGenerationItem:
    saved_path = data.get("saved_path")
    return ImageGenerationItem(
        id=_required_str(data, "id"),
        status=_required_str(data, "status"),
        revised_prompt=_optional_str(data, "revised_prompt"),
        result=_required_str(data, "result"),
        saved_path=Path(saved_path) if isinstance(saved_path, str) else None,
    )


def _file_change_item(data: Mapping[str, JsonValue]) -> FileChangeItem:
    status = data.get("status")
    return FileChangeItem(
        id=_required_str(data, "id"),
        changes=_changes_from_mapping(data.get("changes", {})),
        status=PatchApplyStatus(status) if isinstance(status, str) else None,
        auto_approved=data.get("auto_approved") if isinstance(data.get("auto_approved"), bool) else None,
        stdout=_optional_str(data, "stdout"),
        stderr=_optional_str(data, "stderr"),
    )


def _mcp_tool_call_item(data: Mapping[str, JsonValue]) -> McpToolCallItem:
    raw_error = data.get("error")
    raw_result = data.get("result")
    return McpToolCallItem(
        id=_required_str(data, "id"),
        server=_required_str(data, "server"),
        tool=_required_str(data, "tool"),
        arguments=data.get("arguments"),
        mcp_app_resource_uri=_optional_str(data, "mcpAppResourceUri") or _optional_str(data, "mcp_app_resource_uri"),
        plugin_id=_optional_str(data, "pluginId") or _optional_str(data, "plugin_id"),
        status=str(data.get("status", McpToolCallStatus.IN_PROGRESS)),
        result=CallToolResult.from_mapping(raw_result) if isinstance(raw_result, Mapping) else None,
        error=McpToolCallError(_required_str(raw_error, "message")) if isinstance(raw_error, Mapping) else None,
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
            for fragment in data.get("fragments", ())
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
