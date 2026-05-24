"""Small shared model protocol types.

Ported in slices from ``codex/codex-rs/protocol/src/models.rs``.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


JsonValue = Any
PROTECTED_METADATA_GIT_PATH_NAME = ".git"
PROTECTED_METADATA_AGENTS_PATH_NAME = ".agents"
PROTECTED_METADATA_CODEX_PATH_NAME = ".codex"
PROTECTED_METADATA_PATH_NAMES = (
    PROTECTED_METADATA_GIT_PATH_NAME,
    PROTECTED_METADATA_AGENTS_PATH_NAME,
    PROTECTED_METADATA_CODEX_PATH_NAME,
)
PROJECT_ROOTS_GLOB_PATTERN_PREFIX = "codex-project-roots://"


class ImageDetail(str, Enum):
    HIGH = "high"
    ORIGINAL = "original"

    def to_json(self) -> str:
        return str(self.value)


DEFAULT_IMAGE_DETAIL = ImageDetail.HIGH


class MessagePhase(str, Enum):
    COMMENTARY = "commentary"
    FINAL_ANSWER = "final_answer"


@dataclass(frozen=True)
class ContentItem:
    type: str
    text: str | None = None
    image_url: str | None = None
    detail: ImageDetail | None = None

    @classmethod
    def input_text(cls, text: str) -> "ContentItem":
        return cls(type="input_text", text=text)

    @classmethod
    def input_image(cls, image_url: str, detail: ImageDetail | None = None) -> "ContentItem":
        return cls(type="input_image", image_url=image_url, detail=detail)

    @classmethod
    def output_text(cls, text: str) -> "ContentItem":
        return cls(type="output_text", text=text)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ContentItem":
        if not isinstance(value, dict):
            raise TypeError("content item must be a mapping")
        item_type = _required_str(value, "type")
        if item_type == "input_text":
            return cls.input_text(_required_str(value, "text"))
        if item_type == "input_image":
            detail = value.get("detail")
            return cls.input_image(
                _required_str(value, "image_url"),
                detail=ImageDetail(detail) if isinstance(detail, str) else None,
            )
        if item_type == "output_text":
            return cls.output_text(_required_str(value, "text"))
        raise ValueError(f"unknown content item type: {item_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.type in {"input_text", "output_text"}:
            data["text"] = self.text or ""
        elif self.type == "input_image":
            data["image_url"] = self.image_url or ""
            if self.detail is not None:
                data["detail"] = self.detail.value
        return data


@dataclass(frozen=True)
class FunctionCallOutputContentItem:
    type: str
    text: str | None = None
    image_url: str | None = None
    detail: ImageDetail | None = None
    encrypted_content: str | None = None

    @classmethod
    def input_text(cls, text: str) -> "FunctionCallOutputContentItem":
        return cls(type="input_text", text=text)

    @classmethod
    def input_image(
        cls,
        image_url: str,
        detail: ImageDetail | None = None,
    ) -> "FunctionCallOutputContentItem":
        return cls(type="input_image", image_url=image_url, detail=detail)

    @classmethod
    def encrypted(cls, encrypted_content: str) -> "FunctionCallOutputContentItem":
        return cls(type="encrypted_content", encrypted_content=encrypted_content)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FunctionCallOutputContentItem":
        if isinstance(value, FunctionCallOutputContentItem):
            return value
        data = _as_mapping(value, "function call output content item")
        item_type = _required_str(data, "type")
        if item_type == "input_text":
            return cls.input_text(_required_str(data, "text"))
        if item_type == "input_image":
            detail = data.get("detail")
            return cls.input_image(
                _required_str(data, "image_url"),
                detail=ImageDetail(detail) if isinstance(detail, str) else None,
            )
        if item_type == "encrypted_content":
            return cls.encrypted(_required_str(data, "encrypted_content"))
        raise ValueError(f"unknown function call output content item type: {item_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "input_text":
            return {"type": "input_text", "text": self.text or ""}
        if self.type == "input_image":
            data: dict[str, JsonValue] = {"type": "input_image", "image_url": self.image_url or ""}
            if self.detail is not None:
                data["detail"] = self.detail.value
            return data
        if self.type == "encrypted_content":
            return {"type": "encrypted_content", "encrypted_content": self.encrypted_content or ""}
        return {"type": self.type}


def function_call_output_content_items_to_text(
    content_items: tuple[FunctionCallOutputContentItem, ...] | list[FunctionCallOutputContentItem],
) -> str | None:
    segments = [
        item.text or ""
        for item in content_items
        if item.type == "input_text" and (item.text or "").strip()
    ]
    if not segments:
        return None
    return "\n".join(segments)


@dataclass(frozen=True)
class FunctionCallOutputBody:
    type: str = "text"
    text: str | None = ""
    content_items: tuple[FunctionCallOutputContentItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.content_items, tuple):
            object.__setattr__(
                self,
                "content_items",
                tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
            )
        else:
            object.__setattr__(
                self,
                "content_items",
                tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
            )

    @classmethod
    def text_body(cls, text: str) -> "FunctionCallOutputBody":
        return cls(type="text", text=text)

    @classmethod
    def content_items_body(
        cls,
        content_items: tuple[FunctionCallOutputContentItem | JsonValue, ...] | list[FunctionCallOutputContentItem | JsonValue],
    ) -> "FunctionCallOutputBody":
        return cls(
            type="content_items",
            text=None,
            content_items=tuple(FunctionCallOutputContentItem.from_mapping(item) for item in content_items),
        )

    @classmethod
    def from_value(cls, value: JsonValue) -> "FunctionCallOutputBody":
        if isinstance(value, str):
            return cls.text_body(value)
        if isinstance(value, list | tuple):
            return cls.content_items_body(tuple(value))
        raise TypeError("function call output body must be a string or content item list")

    def to_text(self) -> str | None:
        if self.type == "text":
            return self.text or ""
        return function_call_output_content_items_to_text(self.content_items)

    def to_json(self) -> JsonValue:
        if self.type == "content_items":
            return [item.to_mapping() for item in self.content_items]
        return self.text or ""


@dataclass(frozen=True)
class FunctionCallOutputPayload:
    body: FunctionCallOutputBody = field(default_factory=FunctionCallOutputBody)
    success: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.body, FunctionCallOutputBody):
            object.__setattr__(self, "body", FunctionCallOutputBody.from_value(self.body))

    @classmethod
    def text(cls, content: str, success: bool | None = None) -> "FunctionCallOutputPayload":
        return cls(body=FunctionCallOutputBody.text_body(content), success=success)

    @classmethod
    def from_text(cls, content: str, success: bool | None = None) -> "FunctionCallOutputPayload":
        return cls.text(content, success)

    @classmethod
    def structured(
        cls,
        content_items: tuple[FunctionCallOutputContentItem | JsonValue, ...] | list[FunctionCallOutputContentItem | JsonValue],
        success: bool | None = None,
    ) -> "FunctionCallOutputPayload":
        return cls(body=FunctionCallOutputBody.content_items_body(content_items), success=success)

    @classmethod
    def from_content_items(
        cls,
        content_items: tuple[FunctionCallOutputContentItem | JsonValue, ...] | list[FunctionCallOutputContentItem | JsonValue],
        success: bool | None = None,
    ) -> "FunctionCallOutputPayload":
        return cls.structured(content_items, success)

    @classmethod
    def from_value(cls, value: JsonValue) -> "FunctionCallOutputPayload":
        if isinstance(value, FunctionCallOutputPayload):
            return value
        if isinstance(value, str):
            return cls.text(value)
        if isinstance(value, list | tuple):
            return cls.structured(tuple(value))
        if isinstance(value, dict):
            if "content" in value and isinstance(value["content"], str):
                return cls.text(value["content"])
            if "content_items" in value and isinstance(value["content_items"], list | tuple):
                return cls.structured(tuple(value["content_items"]))
        raise TypeError("function call output payload must be a string or content item list")

    @property
    def content(self) -> str | None:
        return self.text_content()

    @property
    def content_items(self) -> tuple[FunctionCallOutputContentItem, ...] | None:
        return self.body.content_items if self.body.type == "content_items" else None

    def text_content(self) -> str | None:
        return self.body.text if self.body.type == "text" else None

    def to_text(self) -> str | None:
        return self.body.to_text()

    def to_json(self) -> JsonValue:
        return self.body.to_json()


@dataclass(frozen=True)
class SearchToolCallParams:
    query: str
    limit: int | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SearchToolCallParams":
        data = _as_mapping(value, "search tool call params")
        raw_limit = data.get("limit")
        return cls(
            query=_required_str(data, "query"),
            limit=int(raw_limit) if raw_limit is not None else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"query": self.query}
        if self.limit is not None:
            data["limit"] = self.limit
        return data


@dataclass(frozen=True)
class ResponseInputItem:
    type: str
    role: str | None = None
    content: tuple[ContentItem, ...] = ()
    phase: MessagePhase | None = None
    call_id: str | None = None
    output: FunctionCallOutputPayload | JsonValue | None = None
    name: str | None = None
    status: str | None = None
    execution: str | None = None
    tools: tuple[JsonValue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.content, tuple):
            object.__setattr__(self, "content", tuple(self.content))
        if not isinstance(self.tools, tuple):
            object.__setattr__(self, "tools", tuple(self.tools))

    @classmethod
    def message(
        cls,
        role: str,
        content: tuple[ContentItem, ...] | list[ContentItem],
        phase: MessagePhase | None = None,
    ) -> "ResponseInputItem":
        return cls(type="message", role=role, content=tuple(content), phase=phase)

    @classmethod
    def function_call_output(cls, call_id: str, output: FunctionCallOutputPayload | str) -> "ResponseInputItem":
        payload = FunctionCallOutputPayload.from_value(output) if isinstance(output, str) else output
        return cls(type="function_call_output", call_id=call_id, output=payload)

    @classmethod
    def mcp_tool_call_output(cls, call_id: str, output: JsonValue) -> "ResponseInputItem":
        return cls(type="mcp_tool_call_output", call_id=call_id, output=output)

    @classmethod
    def custom_tool_call_output(
        cls,
        call_id: str,
        output: FunctionCallOutputPayload | str,
        name: str | None = None,
    ) -> "ResponseInputItem":
        payload = FunctionCallOutputPayload.from_value(output) if isinstance(output, str) else output
        return cls(type="custom_tool_call_output", call_id=call_id, name=name, output=payload)

    @classmethod
    def tool_search_output(
        cls,
        call_id: str,
        status: str,
        execution: str,
        tools: tuple[JsonValue, ...] | list[JsonValue],
    ) -> "ResponseInputItem":
        return cls(type="tool_search_output", call_id=call_id, status=status, execution=execution, tools=tuple(tools))

    @classmethod
    def from_user_inputs(cls, items: tuple[JsonValue, ...] | list[JsonValue]) -> "ResponseInputItem":
        content: list[ContentItem] = []
        for item in items:
            item_type = getattr(item, "type", None)
            if item_type == "text":
                content.append(ContentItem.input_text(getattr(item, "text", "") or ""))
            elif item_type == "image":
                detail = getattr(item, "detail", None) or DEFAULT_IMAGE_DETAIL
                content.extend(
                    (
                        ContentItem.input_text(image_open_tag_text()),
                        ContentItem.input_image(getattr(item, "image_url", "") or "", detail=detail),
                        ContentItem.input_text(image_close_tag_text()),
                    )
                )
            elif item_type == "local_image":
                detail = getattr(item, "detail", None) or DEFAULT_IMAGE_DETAIL
                path = Path(getattr(item, "path", ""))
                content.extend(
                    (
                        ContentItem.input_text(local_image_open_tag_text(len([c for c in content if c.type == "input_image"]) + 1)),
                        ContentItem.input_text(
                            f"Codex could not read the local image at `{path}`: local image conversion is not available in this port yet"
                        ),
                        ContentItem.input_text(local_image_close_tag_text()),
                    )
                )
                _ = detail
        return cls.message("user", tuple(content))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.role is not None:
            data["role"] = self.role
        if self.content:
            data["content"] = [item.to_mapping() for item in self.content]
        if self.phase is not None:
            data["phase"] = self.phase.value
        if self.call_id is not None:
            data["call_id"] = self.call_id
        if self.output is not None:
            data["output"] = self.output.to_json() if isinstance(self.output, FunctionCallOutputPayload) else self.output
        if self.name is not None:
            data["name"] = self.name
        if self.status is not None:
            data["status"] = self.status
        if self.execution is not None:
            data["execution"] = self.execution
        if self.tools:
            data["tools"] = list(self.tools)
        return data


@dataclass(frozen=True)
class WebSearchAction:
    type: str
    query: str | None = None
    queries: tuple[str, ...] | None = None
    url: str | None = None
    pattern: str | None = None

    @classmethod
    def search(cls, query: str | None = None, queries: tuple[str, ...] | list[str] | None = None) -> "WebSearchAction":
        return cls("search", query=query, queries=tuple(queries) if queries is not None else None)

    @classmethod
    def open_page(cls, url: str | None = None) -> "WebSearchAction":
        return cls("open_page", url=url)

    @classmethod
    def find_in_page(cls, url: str | None = None, pattern: str | None = None) -> "WebSearchAction":
        return cls("find_in_page", url=url, pattern=pattern)

    @classmethod
    def other(cls) -> "WebSearchAction":
        return cls("other")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "WebSearchAction":
        if not isinstance(value, dict):
            raise TypeError("web search action must be a mapping")
        action_type = _required_str(value, "type")
        if action_type == "search":
            queries = value.get("queries")
            return cls.search(
                query=value.get("query") if isinstance(value.get("query"), str) else None,
                queries=tuple(queries) if isinstance(queries, list | tuple) else None,
            )
        if action_type == "open_page":
            return cls.open_page(value.get("url") if isinstance(value.get("url"), str) else None)
        if action_type == "find_in_page":
            return cls.find_in_page(
                url=value.get("url") if isinstance(value.get("url"), str) else None,
                pattern=value.get("pattern") if isinstance(value.get("pattern"), str) else None,
            )
        return cls.other()

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.query is not None:
            data["query"] = self.query
        if self.queries is not None:
            data["queries"] = list(self.queries)
        if self.url is not None:
            data["url"] = self.url
        if self.pattern is not None:
            data["pattern"] = self.pattern
        return data


@dataclass(frozen=True)
class ReasoningItemReasoningSummary:
    type: str
    text: str

    @classmethod
    def summary_text(cls, text: str) -> "ReasoningItemReasoningSummary":
        return cls("summary_text", text)

    def to_mapping(self) -> dict[str, str]:
        return {"type": self.type, "text": self.text}


@dataclass(frozen=True)
class ReasoningItemContent:
    type: str
    text: str

    @classmethod
    def reasoning_text(cls, text: str) -> "ReasoningItemContent":
        return cls("reasoning_text", text)

    @classmethod
    def text_content(cls, text: str) -> "ReasoningItemContent":
        return cls("text", text)

    def to_mapping(self) -> dict[str, str]:
        return {"type": self.type, "text": self.text}


def should_serialize_reasoning_content(content: tuple[ReasoningItemContent, ...] | None) -> bool:
    if content is None:
        return False
    return not any(item.type == "reasoning_text" for item in content)


@dataclass(frozen=True)
class ResponseItem:
    type: str
    id: str | None = None
    role: str | None = None
    content: tuple[ContentItem, ...] = ()
    phase: MessagePhase | None = None
    summary: tuple[ReasoningItemReasoningSummary, ...] = ()
    reasoning_content: tuple[ReasoningItemContent, ...] | None = None
    encrypted_content: str | None = None
    call_id: str | None = None
    name: str | None = None
    namespace: str | None = None
    arguments: str | JsonValue | None = None
    input: str | None = None
    output: FunctionCallOutputPayload | JsonValue | None = None
    status: str | None = None
    execution: str | None = None
    tools: tuple[JsonValue, ...] = ()
    action: WebSearchAction | None = None
    revised_prompt: str | None = None
    result: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("content", "summary", "tools"):
            value = getattr(self, field_name)
            if not isinstance(value, tuple):
                object.__setattr__(self, field_name, tuple(value))
        if self.reasoning_content is not None and not isinstance(self.reasoning_content, tuple):
            object.__setattr__(self, "reasoning_content", tuple(self.reasoning_content))

    @classmethod
    def message(
        cls,
        role: str,
        content: tuple[ContentItem, ...] | list[ContentItem],
        id: str | None = None,
        phase: MessagePhase | None = None,
    ) -> "ResponseItem":
        return cls(type="message", id=id, role=role, content=tuple(content), phase=phase)

    @classmethod
    def function_call(
        cls,
        name: str,
        arguments: str,
        call_id: str,
        namespace: str | None = None,
        id: str | None = None,
    ) -> "ResponseItem":
        return cls(
            type="function_call",
            id=id,
            name=name,
            namespace=namespace,
            arguments=arguments,
            call_id=call_id,
        )

    @classmethod
    def tool_search_call(
        cls,
        arguments: SearchToolCallParams | JsonValue,
        call_id: str | None = None,
        execution: str | None = None,
        id: str | None = None,
    ) -> "ResponseItem":
        if isinstance(arguments, SearchToolCallParams):
            arguments = arguments.to_mapping()
        return cls(
            type="tool_search_call",
            id=id,
            call_id=call_id,
            execution=execution,
            arguments=arguments,
        )

    @classmethod
    def custom_tool_call(
        cls,
        name: str,
        input: str,
        call_id: str,
        id: str | None = None,
    ) -> "ResponseItem":
        return cls(type="custom_tool_call", id=id, name=name, input=input, call_id=call_id)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ResponseItem":
        data = _as_mapping(value, "response item")
        item_type = _required_str(data, "type")
        if item_type == "message":
            return cls.message(
                _required_str(data, "role"),
                tuple(ContentItem.from_mapping(item) for item in data.get("content", ())),
                id=data.get("id") if isinstance(data.get("id"), str) else None,
                phase=MessagePhase(data["phase"]) if isinstance(data.get("phase"), str) else None,
            )
        if item_type == "function_call":
            return cls.function_call(
                _required_str(data, "name"),
                _required_str(data, "arguments"),
                _required_str(data, "call_id"),
                namespace=data.get("namespace") if isinstance(data.get("namespace"), str) else None,
                id=data.get("id") if isinstance(data.get("id"), str) else None,
            )
        if item_type == "tool_search_call":
            return cls.tool_search_call(
                data.get("arguments", {}),
                call_id=data.get("call_id") if isinstance(data.get("call_id"), str) else None,
                execution=data.get("execution") if isinstance(data.get("execution"), str) else None,
                id=data.get("id") if isinstance(data.get("id"), str) else None,
            )
        if item_type == "custom_tool_call":
            return cls.custom_tool_call(
                _required_str(data, "name"),
                _required_str(data, "input"),
                _required_str(data, "call_id"),
                id=data.get("id") if isinstance(data.get("id"), str) else None,
            )
        if item_type == "function_call_output":
            return cls(
                type="function_call_output",
                call_id=_required_str(data, "call_id"),
                output=FunctionCallOutputPayload.from_value(data.get("output", "")),
            )
        if item_type == "custom_tool_call_output":
            return cls(
                type="custom_tool_call_output",
                call_id=_required_str(data, "call_id"),
                name=data.get("name") if isinstance(data.get("name"), str) else None,
                output=FunctionCallOutputPayload.from_value(data.get("output", "")),
            )
        if item_type == "tool_search_output":
            return cls(
                type="tool_search_output",
                call_id=_required_str(data, "call_id"),
                status=data.get("status") if isinstance(data.get("status"), str) else None,
                execution=data.get("execution") if isinstance(data.get("execution"), str) else None,
                tools=tuple(data.get("tools", ())),
            )
        if item_type == "web_search_call":
            return cls.web_search_call(
                id=data.get("id") if isinstance(data.get("id"), str) else None,
                status=data.get("status") if isinstance(data.get("status"), str) else None,
                action=WebSearchAction.from_mapping(data["action"]) if isinstance(data.get("action"), dict) else None,
            )
        return cls(type=item_type)

    @classmethod
    def from_response_input_item(cls, item: ResponseInputItem) -> "ResponseItem":
        if item.type == "message":
            return cls.message(item.role or "", item.content, phase=item.phase)
        if item.type == "function_call_output":
            return cls(type="function_call_output", call_id=item.call_id, output=item.output)
        if item.type == "mcp_tool_call_output":
            return cls(type="function_call_output", call_id=item.call_id, output=item.output)
        if item.type == "custom_tool_call_output":
            return cls(type="custom_tool_call_output", call_id=item.call_id, name=item.name, output=item.output)
        if item.type == "tool_search_output":
            return cls(
                type="tool_search_output",
                call_id=item.call_id,
                status=item.status,
                execution=item.execution,
                tools=item.tools,
            )
        raise ValueError(f"unknown response input item type: {item.type}")

    @classmethod
    def web_search_call(
        cls,
        id: str | None = None,
        status: str | None = None,
        action: WebSearchAction | None = None,
    ) -> "ResponseItem":
        return cls(type="web_search_call", id=id, status=status, action=action)

    @classmethod
    def image_generation_call(
        cls,
        id: str,
        status: str,
        result: str,
        revised_prompt: str | None = None,
    ) -> "ResponseItem":
        return cls(type="image_generation_call", id=id, status=status, revised_prompt=revised_prompt, result=result)

    @classmethod
    def compaction(cls, encrypted_content: str) -> "ResponseItem":
        return cls(type="compaction", encrypted_content=encrypted_content)

    @classmethod
    def compaction_trigger(cls) -> "ResponseItem":
        return cls(type="compaction_trigger")

    @classmethod
    def context_compaction(cls, encrypted_content: str | None = None) -> "ResponseItem":
        return cls(type="context_compaction", encrypted_content=encrypted_content)

    @classmethod
    def other(cls) -> "ResponseItem":
        return cls(type="other")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        for key, value in (
            ("id", self.id),
            ("role", self.role),
            ("call_id", self.call_id),
            ("name", self.name),
            ("namespace", self.namespace),
            ("arguments", self.arguments),
            ("input", self.input),
            ("status", self.status),
            ("execution", self.execution),
            ("encrypted_content", self.encrypted_content),
            ("revised_prompt", self.revised_prompt),
            ("result", self.result),
        ):
            if value is not None:
                data[key] = value
        if self.content:
            data["content"] = [item.to_mapping() for item in self.content]
        if self.phase is not None:
            data["phase"] = self.phase.value
        if self.summary:
            data["summary"] = [item.to_mapping() for item in self.summary]
        if should_serialize_reasoning_content(self.reasoning_content):
            data["content"] = [item.to_mapping() for item in self.reasoning_content or ()]
        if self.output is not None:
            data["output"] = self.output.to_json() if isinstance(self.output, FunctionCallOutputPayload) else self.output
        if self.tools:
            data["tools"] = list(self.tools)
        if self.action is not None:
            data["action"] = self.action.to_mapping()
        return data


@dataclass(frozen=True)
class BaseInstructions:
    text: str

    @classmethod
    def default(cls) -> "BaseInstructions":
        return cls(BASE_INSTRUCTIONS_DEFAULT)


BASE_INSTRUCTIONS_DEFAULT = "You are Codex, based on GPT-5. You are running as a coding agent in the Codex CLI on a user's computer."
MAX_RENDERED_PREFIXES = 100
MAX_ALLOW_PREFIX_TEXT_BYTES = 5000
TRUNCATED_MARKER = "...\n[Some commands were truncated]"


def format_allow_prefixes(prefixes: tuple[tuple[str, ...], ...] | list[list[str]] | list[tuple[str, ...]]) -> str:
    """Render approved command prefixes like upstream ``models.rs``."""

    normalized = [tuple(str(token) for token in prefix) for prefix in prefixes]
    truncated = len(normalized) > MAX_RENDERED_PREFIXES
    normalized.sort(key=lambda prefix: (len(prefix), sum(len(token) for token in prefix), prefix))

    full_text = "\n".join(f"- {_render_command_prefix(prefix)}" for prefix in normalized[:MAX_RENDERED_PREFIXES])
    output = full_text
    if len(output) > MAX_ALLOW_PREFIX_TEXT_BYTES:
        truncated = True
        output = output[:MAX_ALLOW_PREFIX_TEXT_BYTES]
    if truncated:
        return f"{output}{TRUNCATED_MARKER}"
    return output


def _render_command_prefix(prefix: tuple[str, ...]) -> str:
    tokens = ", ".join(json.dumps(token, ensure_ascii=False) for token in prefix)
    return f"[{tokens}]"
VIEW_IMAGE_TOOL_NAME = "view_image"
IMAGE_OPEN_TAG = "<image>"
IMAGE_CLOSE_TAG = "</image>"
LOCAL_IMAGE_OPEN_TAG_PREFIX = "<image name="
LOCAL_IMAGE_OPEN_TAG_SUFFIX = ">"
LOCAL_IMAGE_CLOSE_TAG = IMAGE_CLOSE_TAG


def image_open_tag_text() -> str:
    return IMAGE_OPEN_TAG


def image_close_tag_text() -> str:
    return IMAGE_CLOSE_TAG


def local_image_label_text(label_number: int) -> str:
    return f"[Image #{label_number}]"


def local_image_open_tag_text(label_number: int) -> str:
    return f"{LOCAL_IMAGE_OPEN_TAG_PREFIX}{local_image_label_text(label_number)}{LOCAL_IMAGE_OPEN_TAG_SUFFIX}"


def is_local_image_open_tag_text(text: str) -> bool:
    return text.startswith(LOCAL_IMAGE_OPEN_TAG_PREFIX) and text.endswith(LOCAL_IMAGE_OPEN_TAG_SUFFIX)


def is_image_open_tag_text(text: str) -> bool:
    return text == IMAGE_OPEN_TAG


def is_image_close_tag_text(text: str) -> bool:
    return text == IMAGE_CLOSE_TAG


def is_local_image_close_tag_text(text: str) -> bool:
    return is_image_close_tag_text(text)


def local_image_close_tag_text() -> str:
    return LOCAL_IMAGE_CLOSE_TAG


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


class SandboxPermissions(str, Enum):
    USE_DEFAULT = "use_default"
    REQUIRE_ESCALATED = "require_escalated"
    WITH_ADDITIONAL_PERMISSIONS = "with_additional_permissions"

    @classmethod
    def default(cls) -> "SandboxPermissions":
        return cls.USE_DEFAULT

    def requires_escalated_permissions(self) -> bool:
        return self is SandboxPermissions.REQUIRE_ESCALATED

    def requests_sandbox_override(self) -> bool:
        return self is not SandboxPermissions.USE_DEFAULT

    def uses_additional_permissions(self) -> bool:
        return self is SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS


class NetworkSandboxPolicy(str, Enum):
    RESTRICTED = "restricted"
    ENABLED = "enabled"

    @classmethod
    def default(cls) -> "NetworkSandboxPolicy":
        return cls.RESTRICTED

    def is_enabled(self) -> bool:
        return self is NetworkSandboxPolicy.ENABLED


def _as_mapping(value: JsonValue, label: str = "value") -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _optional_path(value: JsonValue) -> Path | None:
    return None if value is None else Path(str(value))


def is_protected_metadata_name(name: str | os.PathLike[str]) -> bool:
    return os.fspath(name) in PROTECTED_METADATA_PATH_NAMES


def is_protected_metadata_directory_name(name: str | os.PathLike[str]) -> bool:
    return os.fspath(name) in {PROTECTED_METADATA_AGENTS_PATH_NAME, PROTECTED_METADATA_CODEX_PATH_NAME}


def project_roots_glob_pattern(subpath: Path | str) -> str:
    return f"{PROJECT_ROOTS_GLOB_PATTERN_PREFIX}{_path_for_glob(Path(subpath))}"


class FileSystemAccessMode(str, Enum):
    READ = "read"
    WRITE = "write"
    DENY = "deny"

    @classmethod
    def parse(cls, value: str) -> "FileSystemAccessMode":
        if value == "none":
            return cls.DENY
        return cls(value)

    def can_read(self) -> bool:
        return self is not FileSystemAccessMode.DENY

    def can_write(self) -> bool:
        return self is FileSystemAccessMode.WRITE

    def conflict_precedence(self) -> int:
        return {
            FileSystemAccessMode.READ: 0,
            FileSystemAccessMode.WRITE: 1,
            FileSystemAccessMode.DENY: 2,
        }[self]


class FileSystemSandboxKind(str, Enum):
    RESTRICTED = "restricted"
    UNRESTRICTED = "unrestricted"
    EXTERNAL_SANDBOX = "external-sandbox"

    @classmethod
    def default(cls) -> "FileSystemSandboxKind":
        return cls.RESTRICTED


@dataclass(frozen=True)
class FileSystemSpecialPath:
    kind: str
    subpath: Path | None = None
    path: str | None = None

    @classmethod
    def root(cls) -> "FileSystemSpecialPath":
        return cls("root")

    @classmethod
    def minimal(cls) -> "FileSystemSpecialPath":
        return cls("minimal")

    @classmethod
    def project_roots(cls, subpath: Path | str | None = None) -> "FileSystemSpecialPath":
        return cls("project_roots", Path(subpath) if subpath is not None else None)

    @classmethod
    def tmpdir(cls) -> "FileSystemSpecialPath":
        return cls("tmpdir")

    @classmethod
    def slash_tmp(cls) -> "FileSystemSpecialPath":
        return cls("slash_tmp")

    @classmethod
    def unknown(cls, path: str, subpath: Path | str | None = None) -> "FileSystemSpecialPath":
        return cls("unknown", Path(subpath) if subpath is not None else None, path)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemSpecialPath":
        data = _as_mapping(value, "special path")
        kind = str(data["kind"])
        if kind == "root":
            return cls.root()
        if kind == "minimal":
            return cls.minimal()
        if kind in {"project_roots", "current_working_directory"}:
            return cls.project_roots(_optional_path(data.get("subpath")))
        if kind == "tmpdir":
            return cls.tmpdir()
        if kind == "slash_tmp":
            return cls.slash_tmp()
        if kind == "unknown":
            return cls.unknown(str(data.get("path", "")), _optional_path(data.get("subpath")))
        return cls.unknown(kind, _optional_path(data.get("subpath")))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"kind": self.kind}
        if self.subpath is not None:
            data["subpath"] = str(self.subpath)
        if self.path is not None:
            data["path"] = self.path
        return data


@dataclass(frozen=True)
class FileSystemPath:
    type: str
    path: Path | None = None
    pattern: str | None = None
    value: FileSystemSpecialPath | None = None

    @classmethod
    def explicit_path(cls, path: Path | str) -> "FileSystemPath":
        return cls(type="path", path=Path(path))

    @classmethod
    def glob_pattern(cls, pattern: str) -> "FileSystemPath":
        return cls(type="glob_pattern", pattern=pattern)

    @classmethod
    def special(cls, value: FileSystemSpecialPath) -> "FileSystemPath":
        return cls(type="special", value=value)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemPath":
        data = _as_mapping(value, "filesystem path")
        path_type = str(data["type"])
        if path_type == "path":
            return cls.explicit_path(str(data["path"]))
        if path_type == "glob_pattern":
            return cls.glob_pattern(str(data["pattern"]))
        if path_type == "special":
            return cls.special(FileSystemSpecialPath.from_mapping(data["value"]))
        raise ValueError(f"unknown filesystem path type: {path_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "path":
            return {"type": "path", "path": str(self.path)}
        if self.type == "glob_pattern":
            return {"type": "glob_pattern", "pattern": self.pattern}
        if self.type == "special":
            return {"type": "special", "value": self.value.to_mapping() if self.value is not None else None}
        return {"type": self.type}


@dataclass(frozen=True)
class FileSystemSandboxEntry:
    path: FileSystemPath
    access: FileSystemAccessMode

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemSandboxEntry":
        data = _as_mapping(value, "filesystem sandbox entry")
        return cls(
            path=FileSystemPath.from_mapping(data["path"]),
            access=FileSystemAccessMode.parse(str(data["access"])),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"path": self.path.to_mapping(), "access": self.access.value}


@dataclass(frozen=True)
class WritableRoot:
    root: Path
    read_only_subpaths: tuple[Path, ...] = ()
    protected_metadata_names: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root))
        if not isinstance(self.read_only_subpaths, tuple):
            object.__setattr__(self, "read_only_subpaths", tuple(Path(path) for path in self.read_only_subpaths))
        else:
            object.__setattr__(self, "read_only_subpaths", tuple(Path(path) for path in self.read_only_subpaths))
        if not isinstance(self.protected_metadata_names, tuple):
            object.__setattr__(self, "protected_metadata_names", tuple(self.protected_metadata_names))

    def is_path_writable(self, path: Path | str) -> bool:
        path = Path(path)
        if not _path_starts_with(path, self.root):
            return False
        if any(_path_starts_with(path, subpath) for subpath in self.read_only_subpaths):
            return False
        return not self.path_contains_protected_metadata_name(path)

    def path_contains_protected_metadata_name(self, path: Path | str) -> bool:
        relative = _strip_prefix(Path(path), self.root)
        if relative is None or relative == Path("."):
            return False
        first = relative.parts[0] if relative.parts else None
        return first in self.protected_metadata_names


@dataclass(frozen=True)
class FileSystemSemanticSignature:
    has_full_disk_read_access: bool
    has_full_disk_write_access: bool
    include_platform_defaults: bool
    readable_roots: tuple[Path, ...]
    writable_roots: tuple[WritableRoot, ...]
    unreadable_roots: tuple[Path, ...]
    unreadable_globs: tuple[str, ...]


@dataclass(frozen=True)
class SandboxPolicy:
    type: str
    writable_roots: tuple[Path, ...] = ()
    network_access: bool | NetworkSandboxPolicy = False
    exclude_tmpdir_env_var: bool = False
    exclude_slash_tmp: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.writable_roots, tuple):
            object.__setattr__(self, "writable_roots", tuple(Path(path) for path in self.writable_roots))
        else:
            object.__setattr__(self, "writable_roots", tuple(Path(path) for path in self.writable_roots))

    @classmethod
    def danger_full_access(cls) -> "SandboxPolicy":
        return cls("danger-full-access")

    @classmethod
    def read_only(cls, network_access: bool = False) -> "SandboxPolicy":
        return cls("read-only", network_access=network_access)

    @classmethod
    def external_sandbox(
        cls,
        network_access: NetworkSandboxPolicy = NetworkSandboxPolicy.RESTRICTED,
    ) -> "SandboxPolicy":
        return cls("external-sandbox", network_access=network_access)

    @classmethod
    def workspace_write(
        cls,
        writable_roots: tuple[Path | str, ...] | list[Path | str] = (),
        network_access: bool = False,
        exclude_tmpdir_env_var: bool = False,
        exclude_slash_tmp: bool = False,
    ) -> "SandboxPolicy":
        return cls(
            "workspace-write",
            writable_roots=tuple(Path(path) for path in writable_roots),
            network_access=network_access,
            exclude_tmpdir_env_var=exclude_tmpdir_env_var,
            exclude_slash_tmp=exclude_slash_tmp,
        )

    @classmethod
    def new_read_only_policy(cls) -> "SandboxPolicy":
        return cls.read_only(network_access=False)

    @classmethod
    def new_workspace_write_policy(cls) -> "SandboxPolicy":
        return cls.workspace_write()

    def has_full_disk_read_access(self) -> bool:
        return True

    def has_full_disk_write_access(self) -> bool:
        return self.type in {"danger-full-access", "external-sandbox"}

    def has_full_network_access(self) -> bool:
        if self.type == "danger-full-access":
            return True
        if self.type == "external-sandbox":
            return isinstance(self.network_access, NetworkSandboxPolicy) and self.network_access.is_enabled()
        return bool(self.network_access)

    def network_sandbox_policy(self) -> NetworkSandboxPolicy:
        return NetworkSandboxPolicy.ENABLED if self.has_full_network_access() else NetworkSandboxPolicy.RESTRICTED

    def get_writable_roots_with_cwd(self, cwd: Path | str) -> tuple[WritableRoot, ...]:
        if self.type != "workspace-write":
            return ()
        cwd = Path(cwd)
        roots = list(self.writable_roots)
        if cwd.is_absolute():
            roots.append(cwd)
        if not self.exclude_slash_tmp:
            slash_tmp = Path("/tmp")
            if slash_tmp.is_dir():
                roots.append(slash_tmp)
        if not self.exclude_tmpdir_env_var:
            raw_tmpdir = os.environ.get("TMPDIR")
            if raw_tmpdir:
                tmpdir = Path(raw_tmpdir)
                if tmpdir.is_absolute():
                    roots.append(tmpdir)

        cwd_root = cwd if cwd.is_absolute() else None
        return tuple(
            WritableRoot(
                root=root,
                read_only_subpaths=tuple(
                    _default_read_only_subpaths_for_writable_root(
                        root,
                        protect_missing_dot_codex=cwd_root == root,
                    )
                ),
                protected_metadata_names=(),
            )
            for root in roots
        )

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SandboxPolicy":
        data = _as_mapping(value, "sandbox policy")
        policy_type = str(data["type"])
        if policy_type == "danger-full-access":
            return cls.danger_full_access()
        if policy_type == "read-only":
            return cls.read_only(network_access=bool(data.get("network_access", False)))
        if policy_type == "external-sandbox":
            raw_network = data.get("network_access", NetworkSandboxPolicy.RESTRICTED.value)
            return cls.external_sandbox(NetworkSandboxPolicy(str(raw_network)))
        if policy_type == "workspace-write":
            return cls.workspace_write(
                tuple(Path(str(path)) for path in data.get("writable_roots", ())),
                network_access=bool(data.get("network_access", False)),
                exclude_tmpdir_env_var=bool(data.get("exclude_tmpdir_env_var", False)),
                exclude_slash_tmp=bool(data.get("exclude_slash_tmp", False)),
            )
        raise ValueError(f"unknown sandbox policy type: {policy_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "danger-full-access":
            return {"type": self.type}
        if self.type == "read-only":
            data: dict[str, JsonValue] = {"type": self.type}
            if bool(self.network_access):
                data["network_access"] = True
            return data
        if self.type == "external-sandbox":
            return {
                "type": self.type,
                "network_access": (
                    self.network_access.value
                    if isinstance(self.network_access, NetworkSandboxPolicy)
                    else NetworkSandboxPolicy.ENABLED.value if self.network_access else NetworkSandboxPolicy.RESTRICTED.value
                ),
            }
        if self.type == "workspace-write":
            return {
                "type": self.type,
                "writable_roots": [str(path) for path in self.writable_roots],
                "network_access": bool(self.network_access),
                "exclude_tmpdir_env_var": self.exclude_tmpdir_env_var,
                "exclude_slash_tmp": self.exclude_slash_tmp,
            }
        return {"type": self.type}


@dataclass(frozen=True)
class FileSystemPermissions:
    entries: tuple[FileSystemSandboxEntry, ...] = ()
    glob_scan_max_depth: int | None = None

    def is_empty(self) -> bool:
        return len(self.entries) == 0

    @classmethod
    def from_read_write_roots(
        cls,
        read: tuple[Path | str, ...] | list[Path | str] | None,
        write: tuple[Path | str, ...] | list[Path | str] | None,
    ) -> "FileSystemPermissions":
        entries: list[FileSystemSandboxEntry] = []
        for path in read or ():
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.READ))
        for path in write or ():
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.WRITE))
        return cls(tuple(entries))

    def explicit_path_entries(self) -> tuple[tuple[Path, FileSystemAccessMode], ...]:
        return tuple(
            (entry.path.path, entry.access)
            for entry in self.entries
            if entry.path.type == "path" and entry.path.path is not None
        )

    def legacy_read_write_roots(self) -> tuple[tuple[Path, ...] | None, tuple[Path, ...] | None] | None:
        if self.glob_scan_max_depth is not None:
            return None
        read: list[Path] = []
        write: list[Path] = []
        for entry in self.entries:
            if entry.path.type != "path" or entry.path.path is None:
                return None
            if entry.access is FileSystemAccessMode.READ:
                read.append(entry.path.path)
            elif entry.access is FileSystemAccessMode.WRITE:
                write.append(entry.path.path)
            else:
                return None
        return (tuple(read) if read else None, tuple(write) if write else None)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemPermissions":
        data = _as_mapping(value, "filesystem permissions")
        raw_depth = data.get("glob_scan_max_depth")
        glob_scan_max_depth = int(raw_depth) if raw_depth is not None else None
        if glob_scan_max_depth is not None and glob_scan_max_depth <= 0:
            raise ValueError("glob_scan_max_depth must be greater than zero")
        if "entries" in data:
            return cls(
                entries=tuple(FileSystemSandboxEntry.from_mapping(item) for item in data.get("entries", ())),
                glob_scan_max_depth=glob_scan_max_depth,
            )
        return cls.from_read_write_roots(
            tuple(Path(str(path)) for path in data.get("read", ())),
            tuple(Path(str(path)) for path in data.get("write", ())),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"entries": [entry.to_mapping() for entry in self.entries]}
        if self.glob_scan_max_depth is not None:
            data["glob_scan_max_depth"] = self.glob_scan_max_depth
        return data


@dataclass(frozen=True)
class NetworkPermissions:
    enabled: bool | None = None

    def is_empty(self) -> bool:
        return self.enabled is None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "NetworkPermissions":
        data = _as_mapping(value, "network permissions")
        return cls(enabled=data.get("enabled"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {} if self.enabled is None else {"enabled": self.enabled}


@dataclass(frozen=True)
class AdditionalPermissionProfile:
    network: NetworkPermissions | None = None
    file_system: FileSystemPermissions | None = None

    def is_empty(self) -> bool:
        return self.network is None and self.file_system is None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AdditionalPermissionProfile":
        data = _as_mapping(value, "additional permission profile")
        return cls(
            network=NetworkPermissions.from_mapping(data["network"]) if data.get("network") is not None else None,
            file_system=FileSystemPermissions.from_mapping(data["file_system"]) if data.get("file_system") is not None else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.network is not None:
            data["network"] = self.network.to_mapping()
        if self.file_system is not None:
            data["file_system"] = self.file_system.to_mapping()
        return data


class SandboxEnforcement(str, Enum):
    MANAGED = "managed"
    DISABLED = "disabled"
    EXTERNAL = "external"

    @classmethod
    def default(cls) -> "SandboxEnforcement":
        return cls.MANAGED

    @classmethod
    def from_legacy_sandbox_policy(cls, sandbox_policy: SandboxPolicy) -> "SandboxEnforcement":
        if sandbox_policy.type == "danger-full-access":
            return cls.DISABLED
        if sandbox_policy.type == "external-sandbox":
            return cls.EXTERNAL
        return cls.MANAGED


@dataclass(frozen=True)
class FileSystemSandboxPolicy:
    kind: FileSystemSandboxKind = FileSystemSandboxKind.RESTRICTED
    entries: tuple[FileSystemSandboxEntry, ...] = (
        FileSystemSandboxEntry(
            FileSystemPath.special(FileSystemSpecialPath.root()),
            FileSystemAccessMode.READ,
        ),
    )
    glob_scan_max_depth: int | None = None

    @classmethod
    def default(cls) -> "FileSystemSandboxPolicy":
        return cls()

    @classmethod
    def unrestricted(cls) -> "FileSystemSandboxPolicy":
        return cls(kind=FileSystemSandboxKind.UNRESTRICTED, entries=())

    @classmethod
    def external_sandbox(cls) -> "FileSystemSandboxPolicy":
        return cls(kind=FileSystemSandboxKind.EXTERNAL_SANDBOX, entries=())

    @classmethod
    def restricted(cls, entries: tuple[FileSystemSandboxEntry, ...] | list[FileSystemSandboxEntry]) -> "FileSystemSandboxPolicy":
        return cls(kind=FileSystemSandboxKind.RESTRICTED, entries=tuple(entries))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemSandboxPolicy":
        data = _as_mapping(value, "filesystem sandbox policy")
        kind = FileSystemSandboxKind(str(data.get("kind", FileSystemSandboxKind.RESTRICTED.value)))
        return cls(
            kind=kind,
            entries=tuple(FileSystemSandboxEntry.from_mapping(item) for item in data.get("entries", ())),
            glob_scan_max_depth=(
                int(data["glob_scan_max_depth"]) if data.get("glob_scan_max_depth") is not None else None
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"kind": self.kind.value}
        if self.glob_scan_max_depth is not None:
            data["glob_scan_max_depth"] = self.glob_scan_max_depth
        if self.entries:
            data["entries"] = [entry.to_mapping() for entry in self.entries]
        return data

    @classmethod
    def workspace_write(
        cls,
        writable_roots: tuple[Path | str, ...] | list[Path | str] = (),
        exclude_tmpdir_env_var: bool = False,
        exclude_slash_tmp: bool = False,
    ) -> "FileSystemSandboxPolicy":
        entries = [
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
            FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
        ]
        if not exclude_slash_tmp:
            entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.slash_tmp()), FileSystemAccessMode.WRITE))
        if not exclude_tmpdir_env_var:
            entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.tmpdir()), FileSystemAccessMode.WRITE))
        for path in writable_roots:
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.WRITE))
        for name in (".git", ".agents", ".codex"):
            entries.append(
                FileSystemSandboxEntry(
                    FileSystemPath.special(FileSystemSpecialPath.project_roots(Path(name))),
                    FileSystemAccessMode.READ,
                )
            )
        for path in writable_roots:
            for protected_path in _default_read_only_subpaths_for_writable_root(Path(path), False):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        return cls.restricted(tuple(entries))

    @classmethod
    def from_legacy_sandbox_policy(cls, sandbox_policy: SandboxPolicy) -> "FileSystemSandboxPolicy":
        if sandbox_policy.type == "danger-full-access":
            return cls.unrestricted()
        if sandbox_policy.type == "external-sandbox":
            return cls.external_sandbox()
        if sandbox_policy.type == "read-only":
            return cls.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.READ,
                    ),
                )
            )
        if sandbox_policy.type == "workspace-write":
            return cls.workspace_write(
                sandbox_policy.writable_roots,
                sandbox_policy.exclude_tmpdir_env_var,
                sandbox_policy.exclude_slash_tmp,
            )
        raise ValueError(f"unknown sandbox policy type: {sandbox_policy.type}")

    @classmethod
    def from_legacy_sandbox_policy_for_cwd(
        cls,
        sandbox_policy: SandboxPolicy,
        cwd: Path | str,
    ) -> "FileSystemSandboxPolicy":
        policy = cls.from_legacy_sandbox_policy(sandbox_policy)
        if sandbox_policy.type != "workspace-write":
            return policy
        entries = list(policy.entries)
        cwd = Path(cwd)
        if cwd.is_absolute():
            for protected_path in _default_read_only_subpaths_for_writable_root(cwd, True):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        for writable_root in sandbox_policy.writable_roots:
            for protected_path in _default_read_only_subpaths_for_writable_root(writable_root, False):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        return policy._replace(entries=tuple(entries))

    @classmethod
    def from_legacy_sandbox_policy_preserving_deny_entries(
        cls,
        sandbox_policy: SandboxPolicy,
        cwd: Path | str,
        existing: "FileSystemSandboxPolicy",
    ) -> "FileSystemSandboxPolicy":
        rebuilt = cls.from_legacy_sandbox_policy_for_cwd(sandbox_policy, cwd)
        if rebuilt.kind is not FileSystemSandboxKind.RESTRICTED:
            return rebuilt
        entries = list(rebuilt.entries)
        for deny_entry in existing.entries:
            if deny_entry.access is FileSystemAccessMode.DENY and deny_entry not in entries:
                entries.append(deny_entry)
        return rebuilt._replace(entries=tuple(entries), glob_scan_max_depth=existing.glob_scan_max_depth)

    def has_denied_read_restrictions(self) -> bool:
        return self.kind is FileSystemSandboxKind.RESTRICTED and any(
            entry.access is FileSystemAccessMode.DENY for entry in self.entries
        )

    def has_root_access(self, predicate) -> bool:
        return self.kind is FileSystemSandboxKind.RESTRICTED and any(
            entry.path.type == "special"
            and entry.path.value == FileSystemSpecialPath.root()
            and predicate(entry.access)
            for entry in self.entries
        )

    def has_full_disk_read_access(self) -> bool:
        if self.kind in {FileSystemSandboxKind.UNRESTRICTED, FileSystemSandboxKind.EXTERNAL_SANDBOX}:
            return True
        return self.has_root_access(lambda access: access.can_read()) and not self.has_denied_read_restrictions()

    def has_full_disk_write_access(self) -> bool:
        if self.kind in {FileSystemSandboxKind.UNRESTRICTED, FileSystemSandboxKind.EXTERNAL_SANDBOX}:
            return True
        return self.has_root_access(lambda access: access.can_write()) and not self._has_write_narrowing_entries()

    def include_platform_defaults(self) -> bool:
        return (
            not self.has_full_disk_read_access()
            and self.kind is FileSystemSandboxKind.RESTRICTED
            and any(
                entry.path.type == "special"
                and entry.path.value == FileSystemSpecialPath.minimal()
                and entry.access.can_read()
                for entry in self.entries
            )
        )

    def preserve_deny_read_restrictions_from(
        self,
        existing: "FileSystemSandboxPolicy",
    ) -> "FileSystemSandboxPolicy":
        has_deny_read_entries = any(entry.access is FileSystemAccessMode.DENY for entry in existing.entries)
        policy = self
        if self.kind is FileSystemSandboxKind.UNRESTRICTED and has_deny_read_entries:
            policy = FileSystemSandboxPolicy.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.WRITE,
                    ),
                )
            )

        if policy.kind is not FileSystemSandboxKind.RESTRICTED:
            return policy

        entries = list(policy.entries)
        for deny_entry in existing.entries:
            if deny_entry.access is FileSystemAccessMode.DENY and deny_entry not in entries:
                entries.append(deny_entry)
        glob_scan_max_depth = policy.glob_scan_max_depth
        if glob_scan_max_depth is None:
            glob_scan_max_depth = existing.glob_scan_max_depth
        return policy._replace(entries=tuple(entries), glob_scan_max_depth=glob_scan_max_depth)

    def resolve_access_with_cwd(self, path: Path | str, cwd: Path | str) -> FileSystemAccessMode:
        if self.kind in {FileSystemSandboxKind.UNRESTRICTED, FileSystemSandboxKind.EXTERNAL_SANDBOX}:
            return FileSystemAccessMode.WRITE
        target = _resolve_candidate_path(Path(path), Path(cwd))
        if target is None:
            return FileSystemAccessMode.DENY
        matching = [
            entry
            for entry in self._resolved_entries_with_cwd(Path(cwd))
            if _path_starts_with(target, entry.path)
        ]
        if not matching:
            return FileSystemAccessMode.DENY
        return max(matching, key=lambda entry: (len(entry.path.parts), entry.access.conflict_precedence())).access

    def can_read_path_with_cwd(self, path: Path | str, cwd: Path | str) -> bool:
        return self.resolve_access_with_cwd(path, cwd).can_read()

    def can_write_path_with_cwd(self, path: Path | str, cwd: Path | str) -> bool:
        if not self.resolve_access_with_cwd(path, cwd).can_write():
            return False
        if self.has_full_disk_write_access():
            return True
        return not self._is_metadata_write_denied(Path(path), Path(cwd))

    def materialize_project_roots_with_cwd(self, cwd: Path | str) -> "FileSystemSandboxPolicy":
        cwd = Path(cwd)
        cwd_root = cwd if cwd.is_absolute() else None
        entries: list[FileSystemSandboxEntry] = []
        for entry in self.entries:
            path = entry.path
            if path.type == "special" and path.value is not None and path.value.kind == "project_roots":
                resolved_path = _resolve_file_system_path(path, cwd_root)
                if resolved_path is not None:
                    entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(resolved_path), entry.access))
                    continue
            if path.type == "glob_pattern" and path.pattern is not None and cwd_root is not None:
                subpath = _parse_project_roots_glob_pattern(path.pattern)
                if subpath is not None:
                    entries.append(
                        FileSystemSandboxEntry(
                            FileSystemPath.glob_pattern(_resolve_project_roots_glob_pattern(subpath, cwd_root)),
                            entry.access,
                        )
                    )
                    continue
            entries.append(entry)
        return self._replace(entries=tuple(entries))

    def materialize_project_roots_with_workspace_roots(
        self,
        workspace_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        roots = tuple(Path(root) for root in workspace_roots)
        entries: list[FileSystemSandboxEntry] = []
        for entry in self.entries:
            path = entry.path
            if path.type == "special" and path.value is not None and path.value.kind == "project_roots":
                subpath = path.value.subpath
                for root in roots:
                    resolved_path = _resolve_against_base(subpath or Path("."), root)
                    entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(resolved_path), entry.access))
                continue
            if path.type == "glob_pattern" and path.pattern is not None:
                subpath = _parse_project_roots_glob_pattern(path.pattern)
                if subpath is not None:
                    for root in roots:
                        entries.append(
                            FileSystemSandboxEntry(
                                FileSystemPath.glob_pattern(_resolve_project_roots_glob_pattern(subpath, root)),
                                entry.access,
                            )
                        )
                    continue
            entries.append(entry)
        return self._replace(entries=tuple(entries))

    def with_materialized_project_roots_for_workspace_roots(
        self,
        workspace_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        entries = list(self.entries)
        materialized = self.materialize_project_roots_with_workspace_roots(workspace_roots)
        for entry in materialized.entries:
            if entry not in entries:
                entries.append(entry)
        return self._replace(entries=tuple(entries))

    def with_additional_readable_roots(
        self,
        cwd: Path | str,
        additional_readable_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        if self.has_full_disk_read_access():
            return self
        cwd = Path(cwd)
        entries = list(self.entries)
        for path in additional_readable_roots:
            path = Path(path)
            if self.can_read_path_with_cwd(path, cwd):
                continue
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.READ))
        return self._replace(entries=tuple(entries))

    def with_additional_writable_roots(
        self,
        cwd: Path | str,
        additional_writable_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        cwd = Path(cwd)
        entries = list(self.entries)
        for path in additional_writable_roots:
            path = Path(path)
            if self.can_write_path_with_cwd(path, cwd):
                continue
            entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(path), FileSystemAccessMode.WRITE))
        return self._replace(entries=tuple(entries))

    def with_additional_legacy_workspace_writable_roots(
        self,
        additional_writable_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "FileSystemSandboxPolicy":
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return self
        entries = list(self.entries)
        for path in additional_writable_roots:
            path = Path(path)
            entry_path = FileSystemPath.explicit_path(path)
            if not any(entry.access.can_write() and entry.path == entry_path for entry in entries):
                entries.append(FileSystemSandboxEntry(entry_path, FileSystemAccessMode.WRITE))
            for protected_path in _default_read_only_subpaths_for_writable_root(path, False):
                _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
        return self._replace(entries=tuple(entries))

    def get_readable_roots_with_cwd(self, cwd: Path | str) -> tuple[Path, ...]:
        if self.has_full_disk_read_access():
            return ()
        cwd = Path(cwd)
        roots = [
            entry.path
            for entry in self._resolved_entries_with_cwd(cwd)
            if entry.access.can_read() and self.can_read_path_with_cwd(entry.path, cwd)
        ]
        return tuple(_dedup_paths(roots, normalize=True))

    def get_writable_roots_with_cwd(self, cwd: Path | str) -> tuple[WritableRoot, ...]:
        if self.has_full_disk_write_access():
            return ()
        cwd = Path(cwd)
        resolved_entries = self._resolved_entries_with_cwd(cwd)
        writable_entries = [
            entry.path
            for entry in resolved_entries
            if entry.access.can_write() and self.can_write_path_with_cwd(entry.path, cwd)
        ]
        writable_roots: list[WritableRoot] = []
        for root in _dedup_paths(writable_entries.copy(), normalize=True):
            raw_writable_roots = [
                path for path in writable_entries if _normalize_effective_absolute_path(path) == root
            ]
            protected_metadata_names = _protected_metadata_names_for_writable_root(
                self,
                root,
                raw_writable_roots,
                cwd,
            )
            protect_missing_dot_codex = _normalize_effective_absolute_path(_resolve_base_cwd(cwd)) == root
            read_only_subpaths = [
                path
                for path in _default_read_only_subpaths_for_writable_root(root, protect_missing_dot_codex)
                if not _has_explicit_resolved_path_entry(resolved_entries, path)
            ]
            for entry in resolved_entries:
                if entry.access.can_write() or self.can_write_path_with_cwd(entry.path, cwd):
                    continue
                effective_path = _normalize_effective_absolute_path(entry.path)
                if effective_path != root and _path_starts_with(effective_path, root):
                    read_only_subpaths.append(effective_path)
            writable_roots.append(
                WritableRoot(
                    root=root,
                    read_only_subpaths=tuple(_dedup_paths(read_only_subpaths, normalize=False)),
                    protected_metadata_names=tuple(protected_metadata_names),
                )
            )
        return tuple(writable_roots)

    def get_unreadable_roots_with_cwd(self, cwd: Path | str) -> tuple[Path, ...]:
        cwd = Path(cwd)
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return ()
        root = _absolute_root_path_for_cwd(cwd)
        roots = [
            entry.path
            for entry in self._resolved_entries_with_cwd(cwd)
            if entry.access is FileSystemAccessMode.DENY
            and not self.can_read_path_with_cwd(entry.path, cwd)
            and entry.path != root
        ]
        return tuple(_dedup_paths(roots, normalize=True))

    def get_unreadable_globs_with_cwd(self, cwd: Path | str) -> tuple[str, ...]:
        cwd = Path(cwd)
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return ()
        patterns = []
        for entry in self.entries:
            if entry.access is FileSystemAccessMode.DENY and entry.path.type == "glob_pattern" and entry.path.pattern is not None:
                if (subpath := _parse_project_roots_glob_pattern(entry.path.pattern)) is not None:
                    patterns.append(_resolve_project_roots_glob_pattern(subpath, cwd))
                else:
                    patterns.append(str(_resolve_against_base(entry.path.pattern, cwd)))
        return tuple(sorted(set(patterns)))

    def semantic_signature(self, cwd: Path | str) -> FileSystemSemanticSignature:
        cwd = Path(cwd)
        return FileSystemSemanticSignature(
            has_full_disk_read_access=self.has_full_disk_read_access(),
            has_full_disk_write_access=self.has_full_disk_write_access(),
            include_platform_defaults=self.include_platform_defaults(),
            readable_roots=_sorted_paths(self.get_readable_roots_with_cwd(cwd)),
            writable_roots=_sorted_writable_roots(self.get_writable_roots_with_cwd(cwd)),
            unreadable_roots=_sorted_paths(self.get_unreadable_roots_with_cwd(cwd)),
            unreadable_globs=self.get_unreadable_globs_with_cwd(cwd),
        )

    def is_semantically_equivalent_to(
        self,
        other: "FileSystemSandboxPolicy",
        cwd: Path | str,
    ) -> bool:
        return self.semantic_signature(cwd) == other.semantic_signature(cwd)

    def to_legacy_sandbox_policy(
        self,
        network_policy: NetworkSandboxPolicy,
        cwd: Path | str,
    ) -> SandboxPolicy:
        if self.kind is FileSystemSandboxKind.EXTERNAL_SANDBOX:
            return SandboxPolicy.external_sandbox(network_policy)
        if self.kind is FileSystemSandboxKind.UNRESTRICTED:
            if network_policy.is_enabled():
                return SandboxPolicy.danger_full_access()
            return SandboxPolicy.external_sandbox(NetworkSandboxPolicy.RESTRICTED)

        cwd = Path(cwd)
        cwd_absolute = cwd if cwd.is_absolute() else None
        has_full_disk_write_access = self.has_full_disk_write_access()
        workspace_root_writable = False
        writable_roots: list[Path] = []
        tmpdir_writable = False
        slash_tmp_writable = False
        unbridgeable_root_write = False

        for entry in self.entries:
            if entry.path.type == "glob_pattern":
                continue
            if entry.path.type == "path" and entry.path.path is not None:
                if entry.access.can_write():
                    if cwd_absolute is not None and entry.path.path == cwd_absolute:
                        workspace_root_writable = True
                    else:
                        writable_roots.append(entry.path.path)
                continue
            if entry.path.type == "special" and entry.path.value is not None:
                value = entry.path.value
                if value.kind == "root":
                    if entry.access is FileSystemAccessMode.WRITE:
                        unbridgeable_root_write = True
                elif value.kind == "project_roots":
                    if value.subpath is None and entry.access.can_write():
                        workspace_root_writable = True
                    elif entry.access.can_write():
                        resolved_path = _resolve_file_system_special_path(value, cwd_absolute)
                        if resolved_path is not None:
                            writable_roots.append(resolved_path)
                elif value.kind == "tmpdir" and entry.access.can_write():
                    tmpdir_writable = True
                elif value.kind == "slash_tmp" and entry.access.can_write():
                    slash_tmp_writable = True

        if has_full_disk_write_access:
            if network_policy.is_enabled():
                return SandboxPolicy.danger_full_access()
            return SandboxPolicy.external_sandbox(NetworkSandboxPolicy.RESTRICTED)

        if workspace_root_writable:
            return SandboxPolicy.workspace_write(
                _dedup_paths(writable_roots, normalize=False),
                network_access=network_policy.is_enabled(),
                exclude_tmpdir_env_var=not tmpdir_writable,
                exclude_slash_tmp=not slash_tmp_writable,
            )
        if unbridgeable_root_write or writable_roots or tmpdir_writable or slash_tmp_writable:
            raise ValueError(
                "permissions profile requests filesystem writes outside the workspace root, "
                "which is not supported until the runtime enforces FileSystemSandboxPolicy directly"
            )
        return SandboxPolicy.read_only(network_access=network_policy.is_enabled())

    def needs_direct_runtime_enforcement(
        self,
        network_policy: NetworkSandboxPolicy,
        cwd: Path | str,
    ) -> bool:
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return False
        try:
            legacy_policy = self.to_legacy_sandbox_policy(network_policy, cwd)
        except ValueError:
            return True
        if _protected_metadata_names_need_direct_runtime_enforcement(self, legacy_policy, Path(cwd)):
            return True
        return self.semantic_signature(cwd) != _legacy_runtime_file_system_policy_for_cwd(legacy_policy, cwd).semantic_signature(cwd)

    def _has_write_narrowing_entries(self) -> bool:
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return False
        for entry in self.entries:
            if entry.access.can_write():
                continue
            if entry.path.type == "glob_pattern":
                return True
            if entry.path.type == "special" and entry.path.value is not None:
                if entry.path.value == FileSystemSpecialPath.root():
                    if entry.access is FileSystemAccessMode.DENY:
                        return True
                    continue
                if entry.path.value.kind in {"minimal", "unknown"}:
                    continue
            if not self._has_same_target_write_override(entry):
                return True
        return False

    def _has_same_target_write_override(self, entry: FileSystemSandboxEntry) -> bool:
        return any(
            candidate.access.can_write()
            and candidate.access.conflict_precedence() > entry.access.conflict_precedence()
            and _file_system_paths_share_target(candidate.path, entry.path)
            for candidate in self.entries
        )

    def _resolved_entries_with_cwd(self, cwd: Path) -> tuple["_ResolvedFileSystemEntry", ...]:
        resolved = []
        for entry in self.entries:
            path = _resolve_entry_path(entry.path, cwd)
            if path is not None:
                resolved.append(_ResolvedFileSystemEntry(path, entry.access))
        return tuple(resolved)

    def _is_metadata_write_denied(self, path: Path, cwd: Path) -> bool:
        if self.kind is not FileSystemSandboxKind.RESTRICTED:
            return False
        target = _resolve_candidate_path(path, cwd)
        if target is None:
            return True
        metadata = _metadata_child_of_writable_root(self, target, cwd)
        if metadata is None:
            return False
        protected_metadata_path, _ = metadata
        return not _has_explicit_write_entry_for_metadata_path(self, protected_metadata_path, target, cwd)

    def _replace(
        self,
        *,
        entries: tuple[FileSystemSandboxEntry, ...] | None = None,
        glob_scan_max_depth: int | None = None,
    ) -> "FileSystemSandboxPolicy":
        return FileSystemSandboxPolicy(
            kind=self.kind,
            entries=self.entries if entries is None else entries,
            glob_scan_max_depth=self.glob_scan_max_depth if glob_scan_max_depth is None else glob_scan_max_depth,
        )


@dataclass(frozen=True)
class ManagedFileSystemPermissions:
    type: str
    entries: tuple[FileSystemSandboxEntry, ...] = ()
    glob_scan_max_depth: int | None = None

    @classmethod
    def restricted(
        cls,
        entries: tuple[FileSystemSandboxEntry, ...] | list[FileSystemSandboxEntry],
        glob_scan_max_depth: int | None = None,
    ) -> "ManagedFileSystemPermissions":
        return cls(type="restricted", entries=tuple(entries), glob_scan_max_depth=glob_scan_max_depth)

    @classmethod
    def unrestricted(cls) -> "ManagedFileSystemPermissions":
        return cls(type="unrestricted")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ManagedFileSystemPermissions":
        data = _as_mapping(value, "managed filesystem permissions")
        permission_type = str(data["type"])
        if permission_type == "unrestricted":
            return cls.unrestricted()
        if permission_type == "restricted":
            raw_depth = data.get("glob_scan_max_depth")
            glob_scan_max_depth = int(raw_depth) if raw_depth is not None else None
            if glob_scan_max_depth is not None and glob_scan_max_depth <= 0:
                raise ValueError("glob_scan_max_depth must be greater than zero")
            return cls.restricted(
                tuple(FileSystemSandboxEntry.from_mapping(item) for item in data.get("entries", ())),
                glob_scan_max_depth=glob_scan_max_depth,
            )
        raise ValueError(f"unknown managed filesystem permission type: {permission_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "unrestricted":
            return {"type": "unrestricted"}
        data: dict[str, JsonValue] = {
            "type": "restricted",
            "entries": [entry.to_mapping() for entry in self.entries],
        }
        if self.glob_scan_max_depth is not None:
            data["glob_scan_max_depth"] = self.glob_scan_max_depth
        return data

    @classmethod
    def from_sandbox_policy(cls, policy: FileSystemSandboxPolicy) -> "ManagedFileSystemPermissions":
        if policy.kind is FileSystemSandboxKind.UNRESTRICTED:
            return cls.unrestricted()
        if policy.kind is FileSystemSandboxKind.EXTERNAL_SANDBOX:
            raise ValueError("external filesystem policies are represented by PermissionProfile.external")
        return cls.restricted(policy.entries, policy.glob_scan_max_depth)

    def to_sandbox_policy(self) -> FileSystemSandboxPolicy:
        if self.type == "unrestricted":
            return FileSystemSandboxPolicy.unrestricted()
        return FileSystemSandboxPolicy(
            kind=FileSystemSandboxKind.RESTRICTED,
            entries=self.entries,
            glob_scan_max_depth=self.glob_scan_max_depth,
        )


BUILT_IN_PERMISSION_PROFILE_READ_ONLY = ":read-only"
BUILT_IN_PERMISSION_PROFILE_WORKSPACE = ":workspace"
BUILT_IN_PERMISSION_PROFILE_DANGER_FULL_ACCESS = ":danger-full-access"


@dataclass(frozen=True)
class ActivePermissionProfile:
    id: str
    extends: str | None = None

    @classmethod
    def new(cls, id: str) -> "ActivePermissionProfile":
        return cls(id=id)

    @classmethod
    def read_only(cls) -> "ActivePermissionProfile":
        return cls.new(BUILT_IN_PERMISSION_PROFILE_READ_ONLY)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ActivePermissionProfile":
        data = _as_mapping(value, "active permission profile")
        profile_id = data.get("id")
        if not isinstance(profile_id, str):
            raise TypeError("id must be a string")
        extends = data.get("extends")
        if extends is not None and not isinstance(extends, str):
            raise TypeError("extends must be a string")
        return cls(profile_id, extends)

    def to_mapping(self) -> dict[str, str]:
        data = {"id": self.id}
        if self.extends is not None:
            data["extends"] = self.extends
        return data


@dataclass(frozen=True)
class PermissionProfile:
    type: str
    file_system: ManagedFileSystemPermissions | None = None
    network: NetworkSandboxPolicy | None = None

    @classmethod
    def default(cls) -> "PermissionProfile":
        return cls.managed(ManagedFileSystemPermissions.restricted(()), NetworkSandboxPolicy.RESTRICTED)

    @classmethod
    def managed(
        cls,
        file_system: ManagedFileSystemPermissions,
        network: NetworkSandboxPolicy,
    ) -> "PermissionProfile":
        return cls(type="managed", file_system=file_system, network=network)

    @classmethod
    def disabled(cls) -> "PermissionProfile":
        return cls(type="disabled")

    @classmethod
    def external(cls, network: NetworkSandboxPolicy) -> "PermissionProfile":
        return cls(type="external", network=network)

    @classmethod
    def read_only(cls) -> "PermissionProfile":
        return cls.managed(
            ManagedFileSystemPermissions.restricted(
                (
                    FileSystemSandboxEntry(
                        FileSystemPath.special(FileSystemSpecialPath.root()),
                        FileSystemAccessMode.READ,
                    ),
                )
            ),
            NetworkSandboxPolicy.RESTRICTED,
        )

    @classmethod
    def workspace_write(
        cls,
        writable_roots: tuple[Path | str, ...] | list[Path | str] = (),
        network: NetworkSandboxPolicy = NetworkSandboxPolicy.RESTRICTED,
        exclude_tmpdir_env_var: bool = False,
        exclude_slash_tmp: bool = False,
    ) -> "PermissionProfile":
        policy = FileSystemSandboxPolicy.workspace_write(writable_roots, exclude_tmpdir_env_var, exclude_slash_tmp)
        return cls.managed(ManagedFileSystemPermissions.from_sandbox_policy(policy), network)

    def materialize_project_roots_with_workspace_roots(
        self,
        workspace_roots: tuple[Path | str, ...] | list[Path | str],
    ) -> "PermissionProfile":
        if self.type != "managed":
            return self
        policy = self.file_system_sandbox_policy().materialize_project_roots_with_workspace_roots(workspace_roots)
        return PermissionProfile.managed(
            ManagedFileSystemPermissions.from_sandbox_policy(policy),
            self.network_sandbox_policy(),
        )

    @classmethod
    def from_runtime_permissions(
        cls,
        file_system_sandbox_policy: FileSystemSandboxPolicy,
        network_sandbox_policy: NetworkSandboxPolicy,
    ) -> "PermissionProfile":
        if file_system_sandbox_policy.kind is FileSystemSandboxKind.EXTERNAL_SANDBOX:
            return cls.external(network_sandbox_policy)
        return cls.managed(ManagedFileSystemPermissions.from_sandbox_policy(file_system_sandbox_policy), network_sandbox_policy)

    @classmethod
    def from_runtime_permissions_with_enforcement(
        cls,
        enforcement: SandboxEnforcement,
        file_system_sandbox_policy: FileSystemSandboxPolicy,
        network_sandbox_policy: NetworkSandboxPolicy,
    ) -> "PermissionProfile":
        if file_system_sandbox_policy.kind is FileSystemSandboxKind.EXTERNAL_SANDBOX:
            return cls.external(network_sandbox_policy)
        if file_system_sandbox_policy.kind is FileSystemSandboxKind.UNRESTRICTED and enforcement is SandboxEnforcement.DISABLED:
            return cls.disabled()
        return cls.managed(ManagedFileSystemPermissions.from_sandbox_policy(file_system_sandbox_policy), network_sandbox_policy)

    @classmethod
    def from_legacy_sandbox_policy(cls, sandbox_policy: SandboxPolicy) -> "PermissionProfile":
        return cls.from_runtime_permissions_with_enforcement(
            SandboxEnforcement.from_legacy_sandbox_policy(sandbox_policy),
            FileSystemSandboxPolicy.from_legacy_sandbox_policy(sandbox_policy),
            sandbox_policy.network_sandbox_policy(),
        )

    @classmethod
    def from_legacy_sandbox_policy_for_cwd(
        cls,
        sandbox_policy: SandboxPolicy,
        cwd: Path | str,
    ) -> "PermissionProfile":
        return cls.from_runtime_permissions_with_enforcement(
            SandboxEnforcement.from_legacy_sandbox_policy(sandbox_policy),
            FileSystemSandboxPolicy.from_legacy_sandbox_policy_for_cwd(sandbox_policy, cwd),
            sandbox_policy.network_sandbox_policy(),
        )

    def enforcement(self) -> SandboxEnforcement:
        if self.type == "disabled":
            return SandboxEnforcement.DISABLED
        if self.type == "external":
            return SandboxEnforcement.EXTERNAL
        return SandboxEnforcement.MANAGED

    def file_system_sandbox_policy(self) -> FileSystemSandboxPolicy:
        if self.type == "disabled":
            return FileSystemSandboxPolicy.unrestricted()
        if self.type == "external":
            return FileSystemSandboxPolicy.external_sandbox()
        if self.file_system is None:
            return FileSystemSandboxPolicy.default()
        return self.file_system.to_sandbox_policy()

    def network_sandbox_policy(self) -> NetworkSandboxPolicy:
        if self.type == "disabled":
            return NetworkSandboxPolicy.ENABLED
        return self.network or NetworkSandboxPolicy.RESTRICTED

    def to_legacy_sandbox_policy(self, cwd: Path | str) -> SandboxPolicy:
        if self.type == "disabled":
            return SandboxPolicy.danger_full_access()
        if self.type == "external":
            return SandboxPolicy.external_sandbox(self.network_sandbox_policy())
        return self.file_system_sandbox_policy().to_legacy_sandbox_policy(self.network_sandbox_policy(), cwd)

    def to_runtime_permissions(self) -> tuple[FileSystemSandboxPolicy, NetworkSandboxPolicy]:
        return self.file_system_sandbox_policy(), self.network_sandbox_policy()

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "PermissionProfile":
        data = _as_mapping(value, "permission profile")
        if "type" not in data:
            network = NetworkPermissions.from_mapping(data["network"]) if data.get("network") is not None else None
            file_system = FileSystemPermissions.from_mapping(data["file_system"]) if data.get("file_system") is not None else None
            file_system_sandbox_policy = (
                FileSystemSandboxPolicy.restricted(())
                if file_system is None
                else FileSystemSandboxPolicy(
                    kind=FileSystemSandboxKind.RESTRICTED,
                    entries=file_system.entries,
                    glob_scan_max_depth=file_system.glob_scan_max_depth,
                )
            )
            network_sandbox_policy = (
                NetworkSandboxPolicy.ENABLED
                if network is not None and network.enabled
                else NetworkSandboxPolicy.RESTRICTED
            )
            return cls.from_runtime_permissions(file_system_sandbox_policy, network_sandbox_policy)

        profile_type = str(data["type"])
        if profile_type == "managed":
            return cls.managed(
                ManagedFileSystemPermissions.from_mapping(data["file_system"]),
                NetworkSandboxPolicy(str(data["network"])),
            )
        if profile_type == "disabled":
            return cls.disabled()
        if profile_type == "external":
            return cls.external(NetworkSandboxPolicy(str(data["network"])))
        raise ValueError(f"unknown permission profile type: {profile_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "disabled":
            return {"type": "disabled"}
        if self.type == "external":
            return {"type": "external", "network": self.network_sandbox_policy().value}
        return {
            "type": "managed",
            "file_system": self.file_system.to_mapping() if self.file_system is not None else ManagedFileSystemPermissions.restricted(()).to_mapping(),
            "network": self.network_sandbox_policy().value,
        }


@dataclass(frozen=True)
class _ResolvedFileSystemEntry:
    path: Path
    access: FileSystemAccessMode


class ReadDenyMatcher:
    def __init__(
        self,
        denied_candidates: tuple[tuple[Path, ...], ...],
        deny_read_matchers: tuple[re.Pattern[str], ...],
        invalid_pattern: bool = False,
    ) -> None:
        self.denied_candidates = denied_candidates
        self.deny_read_matchers = deny_read_matchers
        self.invalid_pattern = invalid_pattern

    @classmethod
    def new(cls, file_system_sandbox_policy: FileSystemSandboxPolicy, cwd: Path | str) -> "ReadDenyMatcher | None":
        return cls._build(file_system_sandbox_policy, Path(cwd), fail_closed=True)

    @classmethod
    def try_new(cls, file_system_sandbox_policy: FileSystemSandboxPolicy, cwd: Path | str) -> "ReadDenyMatcher | None":
        return cls._build(file_system_sandbox_policy, Path(cwd), fail_closed=False)

    @classmethod
    def _build(
        cls,
        file_system_sandbox_policy: FileSystemSandboxPolicy,
        cwd: Path,
        fail_closed: bool,
    ) -> "ReadDenyMatcher | None":
        if not file_system_sandbox_policy.has_denied_read_restrictions():
            return None
        denied_candidates = tuple(
            tuple(_normalized_and_canonical_candidates(path))
            for path in file_system_sandbox_policy.get_unreadable_roots_with_cwd(cwd)
        )
        matchers: list[re.Pattern[str]] = []
        invalid_pattern = False
        for pattern in file_system_sandbox_policy.get_unreadable_globs_with_cwd(cwd):
            try:
                matchers.append(_build_glob_matcher(pattern))
            except ValueError:
                if fail_closed:
                    invalid_pattern = True
                else:
                    raise
        return cls(denied_candidates, tuple(matchers), invalid_pattern)

    def is_read_denied(self, path: Path | str) -> bool:
        if self.invalid_pattern:
            return True
        path_candidates = _normalized_and_canonical_candidates(Path(path))
        if any(
            candidate == denied_candidate or _path_starts_with(candidate, denied_candidate)
            for denied_group in self.denied_candidates
            for candidate in path_candidates
            for denied_candidate in denied_group
        ):
            return True
        path_strings = [_path_for_glob(candidate) for candidate in path_candidates]
        return any(matcher.fullmatch(path_string) for matcher in self.deny_read_matchers for path_string in path_strings)


def forbidden_agent_metadata_write(
    path: Path | str,
    cwd: Path | str,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
) -> str | None:
    if file_system_sandbox_policy.kind is not FileSystemSandboxKind.RESTRICTED:
        return None
    cwd = Path(cwd)
    target = _resolve_candidate_path(Path(path), cwd)
    if target is None:
        return None
    metadata = _metadata_child_of_writable_root(file_system_sandbox_policy, target, cwd)
    if metadata is None:
        return None
    protected_metadata_path, metadata_name = metadata
    if _has_explicit_write_entry_for_metadata_path(file_system_sandbox_policy, protected_metadata_path, target, cwd):
        return None
    if not file_system_sandbox_policy.can_write_path_with_cwd(target, cwd):
        return metadata_name
    return None


def _resolve_file_system_path(path: FileSystemPath, cwd: Path | None) -> Path | None:
    if path.type == "path":
        return path.path
    if path.type == "glob_pattern":
        return None
    if path.type == "special" and path.value is not None:
        return _resolve_file_system_special_path(path.value, cwd)
    return None


def _resolve_entry_path(path: FileSystemPath, cwd: Path) -> Path | None:
    if path.type == "special" and path.value == FileSystemSpecialPath.root():
        return _absolute_root_path_for_cwd(cwd)
    return _resolve_file_system_path(path, cwd)


def _resolve_file_system_special_path(value: FileSystemSpecialPath, cwd: Path | None) -> Path | None:
    if value.kind in {"root", "minimal", "unknown"}:
        return None
    if value.kind == "project_roots":
        if cwd is None:
            return None
        return _resolve_against_base(value.subpath or Path("."), _resolve_base_cwd(cwd))
    if value.kind == "tmpdir":
        raw = os.environ.get("TMPDIR")
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_absolute() else None
    if value.kind == "slash_tmp":
        slash_tmp = Path("/tmp")
        return slash_tmp if slash_tmp.is_dir() else None
    return None


def _resolve_candidate_path(path: Path, cwd: Path) -> Path | None:
    if path.is_absolute():
        return path
    return _resolve_base_cwd(cwd) / path


def _resolve_against_base(path: Path | str, base: Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else _resolve_base_cwd(base) / path


def _resolve_base_cwd(cwd: Path) -> Path:
    return cwd if cwd.is_absolute() else Path.cwd() / cwd


def _absolute_root_path_for_cwd(cwd: Path) -> Path:
    if cwd.anchor:
        return Path(cwd.anchor)
    return Path("/")


def _file_system_paths_share_target(left: FileSystemPath, right: FileSystemPath) -> bool:
    if left.type == "path" and right.type == "path":
        return left.path == right.path
    if left.type == "special" and right.type == "special":
        return _special_paths_share_target(left.value, right.value)
    if left.type == "path" and right.type == "special" and left.path is not None and right.value is not None:
        return _special_path_matches_absolute_path(right.value, left.path)
    if left.type == "special" and right.type == "path" and left.value is not None and right.path is not None:
        return _special_path_matches_absolute_path(left.value, right.path)
    if left.type == "glob_pattern" and right.type == "glob_pattern":
        return left.pattern == right.pattern
    return False


def _special_paths_share_target(left: FileSystemSpecialPath | None, right: FileSystemSpecialPath | None) -> bool:
    if left is None or right is None:
        return False
    return left == right


def _special_path_matches_absolute_path(value: FileSystemSpecialPath, path: Path) -> bool:
    if value.kind == "root":
        return path == _absolute_root_path_for_cwd(path)
    if value.kind == "slash_tmp":
        return path == Path("/tmp")
    return False


def _metadata_path_name(name: str) -> str | None:
    return name if name in PROTECTED_METADATA_PATH_NAMES else None


def _metadata_child_of_writable_root(
    policy: FileSystemSandboxPolicy,
    target: Path,
    cwd: Path,
) -> tuple[Path, str] | None:
    for entry in policy._resolved_entries_with_cwd(cwd):
        if not entry.access.can_write():
            continue
        relative = _strip_prefix(target, entry.path)
        if relative is None or relative == Path(".") or not relative.parts:
            continue
        metadata_name = _metadata_path_name(relative.parts[0])
        if metadata_name is not None:
            return entry.path / metadata_name, metadata_name
    return None


def _has_explicit_write_entry_for_metadata_path(
    policy: FileSystemSandboxPolicy,
    protected_metadata_path: Path,
    target: Path,
    cwd: Path,
) -> bool:
    return any(
        entry.access.can_write()
        and _path_starts_with(target, entry.path)
        and _path_starts_with(entry.path, protected_metadata_path)
        for entry in policy._resolved_entries_with_cwd(cwd)
    )


def _legacy_runtime_file_system_policy_for_cwd(
    sandbox_policy: SandboxPolicy,
    cwd: Path | str,
) -> FileSystemSandboxPolicy:
    if sandbox_policy.type != "workspace-write":
        return FileSystemSandboxPolicy.from_legacy_sandbox_policy(sandbox_policy)

    entries = [
        FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.root()), FileSystemAccessMode.READ),
        FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.project_roots()), FileSystemAccessMode.WRITE),
    ]
    if not sandbox_policy.exclude_slash_tmp:
        entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.slash_tmp()), FileSystemAccessMode.WRITE))
    if not sandbox_policy.exclude_tmpdir_env_var:
        entries.append(FileSystemSandboxEntry(FileSystemPath.special(FileSystemSpecialPath.tmpdir()), FileSystemAccessMode.WRITE))
    for writable_root in sandbox_policy.writable_roots:
        entries.append(FileSystemSandboxEntry(FileSystemPath.explicit_path(writable_root), FileSystemAccessMode.WRITE))

    cwd = Path(cwd)
    if cwd.is_absolute():
        for protected_path in _default_read_only_subpaths_for_writable_root(cwd, True):
            _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
    for writable_root in sandbox_policy.writable_roots:
        for protected_path in _default_read_only_subpaths_for_writable_root(writable_root, False):
            _append_default_read_only_path_if_no_explicit_rule(entries, protected_path)
    return FileSystemSandboxPolicy.restricted(tuple(entries))


def _protected_metadata_names_need_direct_runtime_enforcement(
    policy: FileSystemSandboxPolicy,
    legacy_policy: SandboxPolicy,
    cwd: Path,
) -> bool:
    legacy_roots = legacy_policy.get_writable_roots_with_cwd(cwd)
    for writable_root in policy.get_writable_roots_with_cwd(cwd):
        legacy_root = next((candidate for candidate in legacy_roots if candidate.root == writable_root.root), None)
        if legacy_root is None:
            if writable_root.protected_metadata_names:
                return True
            continue
        for metadata_name in writable_root.protected_metadata_names:
            metadata_path = writable_root.root / metadata_name
            if not any(subpath == metadata_path for subpath in legacy_root.read_only_subpaths):
                return True
    return False


def _protected_metadata_names_for_writable_root(
    policy: FileSystemSandboxPolicy,
    root: Path,
    raw_writable_roots: list[Path],
    cwd: Path,
) -> list[str]:
    protected_names = []
    for metadata_name in PROTECTED_METADATA_PATH_NAMES:
        metadata_paths = [root / metadata_name]
        metadata_paths.extend(raw_root / metadata_name for raw_root in raw_writable_roots)
        if all(not policy.can_write_path_with_cwd(metadata_path, cwd) for metadata_path in metadata_paths):
            protected_names.append(metadata_name)
    return protected_names


def _default_read_only_subpaths_for_writable_root(writable_root: Path, protect_missing_dot_codex: bool) -> list[Path]:
    subpaths: list[Path] = []
    top_level_git = writable_root / PROTECTED_METADATA_GIT_PATH_NAME
    if top_level_git.is_dir() or top_level_git.is_file():
        subpaths.append(top_level_git)

    top_level_agents = writable_root / PROTECTED_METADATA_AGENTS_PATH_NAME
    if top_level_agents.is_dir():
        subpaths.append(top_level_agents)

    top_level_codex = writable_root / PROTECTED_METADATA_CODEX_PATH_NAME
    if protect_missing_dot_codex or top_level_codex.is_dir():
        subpaths.append(top_level_codex)

    return _dedup_paths(subpaths, normalize=False)


def _append_default_read_only_path_if_no_explicit_rule(
    entries: list[FileSystemSandboxEntry],
    path: Path,
) -> None:
    file_system_path = FileSystemPath.explicit_path(path)
    if any(_file_system_paths_share_target(entry.path, file_system_path) for entry in entries):
        return
    entries.append(FileSystemSandboxEntry(file_system_path, FileSystemAccessMode.READ))


def _has_explicit_resolved_path_entry(resolved_entries: tuple[_ResolvedFileSystemEntry, ...], path: Path) -> bool:
    return any(entry.path == path for entry in resolved_entries)


def _parse_project_roots_glob_pattern(pattern: str) -> Path | None:
    if not pattern.startswith(PROJECT_ROOTS_GLOB_PATTERN_PREFIX):
        return None
    return Path(pattern[len(PROJECT_ROOTS_GLOB_PATTERN_PREFIX) :])


def _resolve_project_roots_glob_pattern(subpath: Path, root: Path) -> str:
    return str(_resolve_against_base(subpath, root))


def _normalized_and_canonical_candidates(path: Path) -> tuple[Path, ...]:
    candidates = [path]
    try:
        canonical = path.resolve(strict=True)
    except OSError:
        canonical = None
    if canonical is not None and canonical not in candidates:
        candidates.append(canonical)
    return tuple(candidates)


def _dedup_paths(paths: list[Path], normalize: bool) -> list[Path]:
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        candidate = _normalize_effective_absolute_path(path) if normalize else path
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            deduped.append(candidate)
    return deduped


def _sorted_paths(paths: tuple[Path, ...] | list[Path]) -> tuple[Path, ...]:
    return tuple(sorted(paths, key=lambda path: str(path)))


def _sorted_writable_roots(roots: tuple[WritableRoot, ...] | list[WritableRoot]) -> tuple[WritableRoot, ...]:
    normalized = [
        WritableRoot(
            root=root.root,
            read_only_subpaths=_sorted_paths(tuple(root.read_only_subpaths)),
            protected_metadata_names=tuple(sorted(set(root.protected_metadata_names))),
        )
        for root in roots
    ]
    return tuple(sorted(normalized, key=lambda root: str(root.root)))


def _normalize_effective_absolute_path(path: Path) -> Path:
    try:
        return path.resolve(strict=False)
    except OSError:
        return path


def _strip_prefix(path: Path, prefix: Path) -> Path | None:
    try:
        relative = path.relative_to(prefix)
    except ValueError:
        return None
    return relative if str(relative) != "" else Path(".")


def _path_starts_with(path: Path, prefix: Path) -> bool:
    return _strip_prefix(path, prefix) is not None


def _build_glob_matcher(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(_glob_to_regex(_path_for_glob(Path(pattern))))
    except re.error as exc:
        raise ValueError(str(exc)) from exc


def _path_for_glob(path: Path) -> str:
    return str(path).replace("\\", "/")


def _glob_to_regex(pattern: str) -> str:
    index = 0
    out = ["^"]
    while index < len(pattern):
        char = pattern[index]
        if char == "*":
            if index + 1 < len(pattern) and pattern[index + 1] == "*":
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    out.append("(?:.*/)?")
                    index += 1
                else:
                    out.append(".*")
                continue
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = pattern.find("]", index + 1)
            if end == -1:
                out.append(re.escape("["))
            else:
                content = pattern[index + 1 : end]
                if content.startswith("!"):
                    content = "^" + re.escape(content[1:])
                else:
                    content = re.escape(content).replace("\\-", "-")
                out.append(f"[{content}]")
                index = end
        else:
            out.append(re.escape(char))
        index += 1
    out.append("$")
    return "".join(out)
