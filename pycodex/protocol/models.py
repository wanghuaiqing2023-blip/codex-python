"""Small shared model protocol types.

Ported in slices from ``codex/codex-rs/protocol/src/models.rs``.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .permissions import (
    FileSystemAccessMode as _FileSystemAccessMode,
    FileSystemPath as _FileSystemPath,
    FileSystemSandboxEntry as _FileSystemSandboxEntry,
    FileSystemSandboxKind as _FileSystemSandboxKind,
    FileSystemSandboxPolicy as _FileSystemSandboxPolicy,
    FileSystemSpecialPath as _FileSystemSpecialPath,
    NetworkSandboxPolicy as _NetworkSandboxPolicy,
)

if TYPE_CHECKING:
    from .protocol import SandboxPolicy


JsonValue = Any


def _sandbox_policy_type() -> type[SandboxPolicy]:
    from .protocol import SandboxPolicy

    return SandboxPolicy


class ImageDetail(str, Enum):
    AUTO = "auto"
    LOW = "low"
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

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type in {"input_text", "output_text"}:
            if not isinstance(self.text, str):
                raise TypeError("text must be a string")
            if self.image_url is not None:
                raise ValueError(f"{self.type} content item cannot include image_url")
            if self.detail is not None:
                raise ValueError(f"{self.type} content item cannot include detail")
            return
        if self.type == "input_image":
            if not isinstance(self.image_url, str):
                raise TypeError("image_url must be a string")
            if self.text is not None:
                raise ValueError("input_image content item cannot include text")
            if self.detail is not None and not isinstance(self.detail, ImageDetail):
                object.__setattr__(self, "detail", ImageDetail(self.detail))
            return
        raise ValueError(f"unknown content item type: {self.type}")

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
            return cls.input_image(
                _required_str(value, "image_url"),
                detail=_optional_image_detail(value, "detail"),
            )
        if item_type == "output_text":
            return cls.output_text(_required_str(value, "text"))
        raise ValueError(f"unknown content item type: {item_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.type in {"input_text", "output_text"}:
            data["text"] = self.text
        elif self.type == "input_image":
            data["image_url"] = self.image_url
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

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type == "input_text":
            if not isinstance(self.text, str):
                raise TypeError("text must be a string")
            if self.image_url is not None or self.detail is not None or self.encrypted_content is not None:
                raise ValueError("input_text function output item cannot include other payload fields")
            return
        if self.type == "input_image":
            if not isinstance(self.image_url, str):
                raise TypeError("image_url must be a string")
            if self.text is not None or self.encrypted_content is not None:
                raise ValueError("input_image function output item cannot include text or encrypted_content")
            if self.detail is not None and not isinstance(self.detail, ImageDetail):
                object.__setattr__(self, "detail", ImageDetail(self.detail))
            return
        if self.type == "encrypted_content":
            if not isinstance(self.encrypted_content, str):
                raise TypeError("encrypted_content must be a string")
            if self.text is not None or self.image_url is not None or self.detail is not None:
                raise ValueError("encrypted_content function output item cannot include other payload fields")
            return
        raise ValueError(f"unknown function call output content item type: {self.type}")

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
            return cls.input_image(
                _required_str(data, "image_url"),
                detail=_optional_image_detail(data, "detail"),
            )
        if item_type == "encrypted_content":
            return cls.encrypted(_required_str(data, "encrypted_content"))
        raise ValueError(f"unknown function call output content item type: {item_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        if self.type == "input_text":
            return {"type": "input_text", "text": self.text}
        if self.type == "input_image":
            data: dict[str, JsonValue] = {"type": "input_image", "image_url": self.image_url}
            if self.detail is not None:
                data["detail"] = self.detail.value
            return data
        if self.type == "encrypted_content":
            return {"type": "encrypted_content", "encrypted_content": self.encrypted_content}
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


def convert_mcp_content_to_items(contents: tuple[JsonValue, ...] | list[JsonValue]) -> tuple[FunctionCallOutputContentItem, ...] | None:
    """Convert MCP content blocks to function-call output content items.

    Mirrors ``codex-protocol/src/models.rs`` for MCP content blocks that
    include images: data URLs are preserved as-is, raw base64 image data is
    wrapped in a data URL using the block MIME type, and image items receive
    the default image detail unless MCP metadata requests a valid override.
    """

    saw_image = False
    items: list[FunctionCallOutputContentItem] = []
    for content in contents:
        if not isinstance(content, dict):
            items.append(FunctionCallOutputContentItem.input_text(json.dumps(content, ensure_ascii=False, separators=(",", ":"))))
            continue

        content_type = content.get("type")
        if content_type == "text" and isinstance(content.get("text"), str):
            items.append(FunctionCallOutputContentItem.input_text(content["text"]))
        elif content_type == "image" and isinstance(content.get("data"), str):
            saw_image = True
            data = content["data"]
            image_url = (
                data
                if data.startswith("data:")
                else f"data:{content.get('mimeType') or content.get('mime_type') or 'application/octet-stream'};base64,{data}"
            )
            detail = _image_detail_from_mcp_meta(content.get("_meta"))
            items.append(FunctionCallOutputContentItem.input_image(image_url, detail or DEFAULT_IMAGE_DETAIL))
        else:
            items.append(FunctionCallOutputContentItem.input_text(json.dumps(content, ensure_ascii=False, separators=(",", ":"))))
    return tuple(items) if saw_image else None


def _image_detail_from_mcp_meta(meta: JsonValue) -> ImageDetail | None:
    if not isinstance(meta, dict):
        return None
    detail = meta.get("codex/imageDetail")
    if detail == ImageDetail.AUTO.value:
        return ImageDetail.AUTO
    if detail == ImageDetail.LOW.value:
        return ImageDetail.LOW
    if detail == ImageDetail.HIGH.value:
        return ImageDetail.HIGH
    if detail == ImageDetail.ORIGINAL.value:
        return ImageDetail.ORIGINAL
    return None


@dataclass(frozen=True)
class FunctionCallOutputBody:
    type: str = "text"
    text: str | None = ""
    content_items: tuple[FunctionCallOutputContentItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type == "text":
            if not isinstance(self.text, str):
                raise TypeError("text must be a string")
            if self.content_items:
                raise ValueError("text function output body cannot include content_items")
            return
        if self.type == "content_items":
            if self.text is not None:
                raise ValueError("content_items function output body cannot include text")
            if isinstance(self.content_items, str) or not isinstance(self.content_items, (list, tuple)):
                raise TypeError("content_items must be a list or tuple")
            object.__setattr__(
                self,
                "content_items",
                tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.content_items),
            )
            return
        raise ValueError(f"unknown function call output body type: {self.type}")

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
            content_items=content_items,
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
            return self.text
        return function_call_output_content_items_to_text(self.content_items)

    def to_json(self) -> JsonValue:
        if self.type == "content_items":
            return [item.to_mapping() for item in self.content_items]
        return self.text


@dataclass(frozen=True)
class FunctionCallOutputPayload:
    body: FunctionCallOutputBody = field(default_factory=FunctionCallOutputBody)
    success: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.body, FunctionCallOutputBody):
            object.__setattr__(self, "body", FunctionCallOutputBody.from_value(self.body))
        if self.success is not None and not isinstance(self.success, bool):
            raise TypeError("success must be a bool or None")

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

    def __post_init__(self) -> None:
        if not isinstance(self.query, str):
            raise TypeError("query must be a string")
        if self.limit is not None:
            if not isinstance(self.limit, int) or isinstance(self.limit, bool):
                raise TypeError("limit must be an integer or None")
            if self.limit < 0:
                raise ValueError("limit must be non-negative")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "SearchToolCallParams":
        data = _as_mapping(value, "search tool call params")
        return cls(
            query=_required_str(data, "query"),
            limit=_optional_usize(data, "limit"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"query": self.query}
        if self.limit is not None:
            data["limit"] = self.limit
        return data


@dataclass(frozen=True)
class ShellCommandToolCallParams:
    command: str
    workdir: str | None = None
    login: bool | None = None
    timeout_ms: int | None = None
    sandbox_permissions: SandboxPermissions | None = None
    prefix_rule: tuple[str, ...] | None = None
    additional_permissions: AdditionalPermissionProfile | None = None
    justification: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")
        if self.workdir is not None and not isinstance(self.workdir, str):
            raise TypeError("workdir must be a string or None")
        if self.login is not None and not isinstance(self.login, bool):
            raise TypeError("login must be a bool or None")
        if self.timeout_ms is not None:
            if not isinstance(self.timeout_ms, int) or isinstance(self.timeout_ms, bool):
                raise TypeError("timeout_ms must be an integer or None")
            if self.timeout_ms < 0 or self.timeout_ms > 2**64 - 1:
                raise ValueError("timeout_ms must fit in u64")
        if self.sandbox_permissions is not None and not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.prefix_rule is not None:
            if isinstance(self.prefix_rule, str) or not isinstance(self.prefix_rule, (list, tuple)):
                raise TypeError("prefix_rule must be a list or tuple of strings")
            if not all(isinstance(item, str) for item in self.prefix_rule):
                raise TypeError("prefix_rule entries must be strings")
            object.__setattr__(self, "prefix_rule", tuple(self.prefix_rule))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ShellCommandToolCallParams":
        data = _as_mapping(value, "shell command tool call params")
        timeout_ms = data.get("timeout_ms", data.get("timeout"))
        raw_additional = data.get("additional_permissions")
        return cls(
            command=_required_str(data, "command"),
            workdir=_optional_str_value(data, "workdir"),
            login=_optional_bool_value(data, "login"),
            timeout_ms=_optional_u64_value(timeout_ms, "timeout_ms"),
            sandbox_permissions=(
                SandboxPermissions(_optional_str_value(data, "sandbox_permissions"))
                if data.get("sandbox_permissions") is not None
                else None
            ),
            prefix_rule=_optional_str_tuple(data, "prefix_rule"),
            additional_permissions=(
                AdditionalPermissionProfile.from_mapping(raw_additional)
                if raw_additional is not None
                else None
            ),
            justification=_optional_str_value(data, "justification"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"command": self.command}
        if self.workdir is not None:
            data["workdir"] = self.workdir
        if self.login is not None:
            data["login"] = self.login
        if self.timeout_ms is not None:
            data["timeout_ms"] = self.timeout_ms
        if self.sandbox_permissions is not None:
            data["sandbox_permissions"] = self.sandbox_permissions.value
        if self.prefix_rule is not None:
            data["prefix_rule"] = list(self.prefix_rule)
        if self.additional_permissions is not None:
            data["additional_permissions"] = self.additional_permissions.to_mapping()
        if self.justification is not None:
            data["justification"] = self.justification
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
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type not in {
            "message",
            "function_call_output",
            "mcp_tool_call_output",
            "custom_tool_call_output",
            "tool_search_output",
        }:
            raise ValueError("unknown response input item type")
        if self.type == "message":
            if not isinstance(self.role, str):
                raise TypeError("role must be a string")
            if isinstance(self.content, (str, bytes)) or not isinstance(self.content, (list, tuple)):
                raise TypeError("content must be a list or tuple")
            content = tuple(self.content)
            if not all(isinstance(item, ContentItem) for item in content):
                raise TypeError("content entries must be ContentItem")
            object.__setattr__(self, "content", content)
            object.__setattr__(self, "phase", self.phase if self.phase is None else MessagePhase(self.phase))
            return
        if self.type in {"function_call_output", "mcp_tool_call_output", "custom_tool_call_output", "tool_search_output"}:
            if not isinstance(self.call_id, str):
                raise TypeError("call_id must be a string")
        if self.type == "function_call_output":
            if self.output is None:
                raise TypeError("output is required")
            if not isinstance(self.output, FunctionCallOutputPayload):
                object.__setattr__(self, "output", FunctionCallOutputPayload.from_value(self.output))
            return
        if self.type == "mcp_tool_call_output":
            if self.output is None:
                raise TypeError("output is required")
            return
        if self.type == "custom_tool_call_output":
            if self.name is not None and not isinstance(self.name, str):
                raise TypeError("name must be a string or None")
            if self.output is None:
                raise TypeError("output is required")
            if not isinstance(self.output, FunctionCallOutputPayload):
                object.__setattr__(self, "output", FunctionCallOutputPayload.from_value(self.output))
            return
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if not isinstance(self.execution, str):
            raise TypeError("execution must be a string")
        if isinstance(self.tools, (str, bytes)) or not isinstance(self.tools, (list, tuple)):
            raise TypeError("tools must be a list or tuple")
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
    def function_call_output(cls, call_id: str, output: FunctionCallOutputPayload | JsonValue) -> "ResponseInputItem":
        return cls(type="function_call_output", call_id=call_id, output=output)

    @classmethod
    def mcp_tool_call_output(cls, call_id: str, output: JsonValue) -> "ResponseInputItem":
        return cls(type="mcp_tool_call_output", call_id=call_id, output=output)

    @classmethod
    def custom_tool_call_output(
        cls,
        call_id: str,
        output: FunctionCallOutputPayload | JsonValue,
        name: str | None = None,
    ) -> "ResponseInputItem":
        return cls(type="custom_tool_call_output", call_id=call_id, name=name, output=output)

    @classmethod
    def tool_search_output(
        cls,
        call_id: str,
        status: str,
        execution: str,
        tools: tuple[JsonValue, ...] | list[JsonValue],
    ) -> "ResponseInputItem":
        if isinstance(tools, (str, bytes)) or not isinstance(tools, (list, tuple)):
            raise TypeError("tools must be a list or tuple")
        return cls(type="tool_search_output", call_id=call_id, status=status, execution=execution, tools=tuple(tools))

    @classmethod
    def from_user_inputs(cls, items: tuple[JsonValue, ...] | list[JsonValue]) -> "ResponseInputItem":
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("items must be a list or tuple of UserInput")
        content: list[ContentItem] = []
        image_index = 0
        for item in items:
            if not hasattr(item, "type"):
                raise TypeError("items entries must be UserInput-like values")
            item_type = item.type
            if item_type == "text":
                if not isinstance(item.text, str):
                    raise TypeError("text input requires text")
                content.append(ContentItem.input_text(item.text))
            elif item_type == "image":
                image_index += 1
                detail = item.detail or DEFAULT_IMAGE_DETAIL
                if not isinstance(item.image_url, str):
                    raise TypeError("image input requires image_url")
                content.append(ContentItem.input_image(item.image_url, detail=detail))
            elif item_type == "local_image":
                image_index += 1
                detail = item.detail or DEFAULT_IMAGE_DETAIL
                if not isinstance(item.path, (str, Path)):
                    raise TypeError("local_image input requires path")
                content.extend(_local_image_content_items_with_label_number(Path(item.path), image_index, detail))
            elif item_type in {"skill", "mention"}:
                continue
            else:
                raise ValueError(f"unknown user input type: {item_type}")
        return cls.message("user", tuple(content))

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.type == "message":
            data["role"] = self.role
            data["content"] = [item.to_mapping() for item in self.content]
            if self.phase is not None:
                data["phase"] = self.phase.value
            return data
        if self.type in {"function_call_output", "mcp_tool_call_output", "custom_tool_call_output", "tool_search_output"}:
            data["call_id"] = self.call_id
        if self.type in {"function_call_output", "mcp_tool_call_output", "custom_tool_call_output"}:
            if isinstance(self.output, FunctionCallOutputPayload):
                data["output"] = self.output.to_json()
            else:
                data["output"] = self.output
        if self.type == "custom_tool_call_output" and self.name is not None:
            data["name"] = self.name
        if self.type == "tool_search_output":
            data["status"] = self.status
            data["execution"] = self.execution
            data["tools"] = list(self.tools)
        return data


@dataclass(frozen=True)
class LocalShellExecAction:
    command: tuple[str, ...]
    timeout_ms: int | None = None
    working_directory: str | None = None
    env: dict[str, str] | None = None
    user: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.command, str) or not isinstance(self.command, (list, tuple)):
            raise TypeError("command must be a list or tuple of strings")
        object.__setattr__(self, "command", tuple(self.command))
        if not all(isinstance(item, str) for item in self.command):
            raise TypeError("command entries must be strings")
        if self.timeout_ms is not None:
            if not isinstance(self.timeout_ms, int) or isinstance(self.timeout_ms, bool):
                raise TypeError("timeout_ms must be an integer or None")
            if self.timeout_ms < 0 or self.timeout_ms > 2**64 - 1:
                raise ValueError("timeout_ms must fit in u64")
        if self.working_directory is not None and not isinstance(self.working_directory, str):
            raise TypeError("working_directory must be a string or None")
        if self.env is not None:
            if not isinstance(self.env, dict):
                raise TypeError("env must be a mapping or None")
            if not all(isinstance(key, str) and isinstance(value, str) for key, value in self.env.items()):
                raise TypeError("env entries must be strings")
            object.__setattr__(self, "env", dict(self.env))
        if self.user is not None and not isinstance(self.user, str):
            raise TypeError("user must be a string or None")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "LocalShellExecAction":
        data = _as_mapping(value, "local shell exec action")
        return cls(
            command=_required_value(data, "command"),
            timeout_ms=data.get("timeout_ms"),
            working_directory=data.get("working_directory"),
            env=data.get("env"),
            user=data.get("user"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"command": list(self.command)}
        if self.timeout_ms is not None:
            data["timeout_ms"] = self.timeout_ms
        if self.working_directory is not None:
            data["working_directory"] = self.working_directory
        if self.env is not None:
            data["env"] = dict(self.env)
        if self.user is not None:
            data["user"] = self.user
        return data


@dataclass(frozen=True)
class LocalShellAction:
    type: str
    exec: LocalShellExecAction | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type != "exec":
            raise ValueError(f"unknown local shell action type: {self.type}")
        if not isinstance(self.exec, LocalShellExecAction):
            raise TypeError("exec must be LocalShellExecAction")

    @classmethod
    def exec_action(cls, action: LocalShellExecAction) -> "LocalShellAction":
        return cls("exec", action)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "LocalShellAction":
        data = _as_mapping(value, "local shell action")
        action_type = _required_str(data, "type")
        if action_type == "exec":
            return cls.exec_action(LocalShellExecAction.from_mapping(data))
        raise ValueError(f"unknown local shell action type: {action_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"type": "exec", **self.exec.to_mapping()}


class LocalShellStatus(str, Enum):
    COMPLETED = "completed"
    IN_PROGRESS = "in_progress"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class WebSearchAction:
    type: str
    query: str | None = None
    queries: tuple[str, ...] | None = None
    url: str | None = None
    pattern: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type == "search":
            if self.query is not None and not isinstance(self.query, str):
                raise TypeError("query must be a string or None")
            if self.queries is not None:
                if isinstance(self.queries, str) or not isinstance(self.queries, (list, tuple)):
                    raise TypeError("queries must be a list or tuple of strings")
                if not all(isinstance(item, str) for item in self.queries):
                    raise TypeError("queries entries must be strings")
                object.__setattr__(self, "queries", tuple(self.queries))
            if self.url is not None or self.pattern is not None:
                raise ValueError("search web search action cannot include url or pattern")
            return
        if self.type == "open_page":
            if self.url is not None and not isinstance(self.url, str):
                raise TypeError("url must be a string or None")
            if self.query is not None or self.queries is not None or self.pattern is not None:
                raise ValueError("open_page web search action cannot include query, queries, or pattern")
            return
        if self.type == "find_in_page":
            if self.url is not None and not isinstance(self.url, str):
                raise TypeError("url must be a string or None")
            if self.pattern is not None and not isinstance(self.pattern, str):
                raise TypeError("pattern must be a string or None")
            if self.query is not None or self.queries is not None:
                raise ValueError("find_in_page web search action cannot include query or queries")
            return
        if self.type == "other":
            if self.query is not None or self.queries is not None or self.url is not None or self.pattern is not None:
                raise ValueError("other web search action cannot include fields")
            return
        raise ValueError(f"unknown web search action type: {self.type}")

    @classmethod
    def search(cls, query: str | None = None, queries: tuple[str, ...] | list[str] | None = None) -> "WebSearchAction":
        if query is not None and not isinstance(query, str):
            raise TypeError("query must be a string or None")
        if queries is not None:
            if isinstance(queries, str) or not isinstance(queries, (list, tuple)):
                raise TypeError("queries must be a list or tuple of strings")
            if not all(isinstance(item, str) for item in queries):
                raise TypeError("queries entries must be strings")
        return cls("search", query=query, queries=tuple(queries) if queries is not None else None)

    @classmethod
    def open_page(cls, url: str | None = None) -> "WebSearchAction":
        if url is not None and not isinstance(url, str):
            raise TypeError("url must be a string or None")
        return cls("open_page", url=url)

    @classmethod
    def find_in_page(cls, url: str | None = None, pattern: str | None = None) -> "WebSearchAction":
        if url is not None and not isinstance(url, str):
            raise TypeError("url must be a string or None")
        if pattern is not None and not isinstance(pattern, str):
            raise TypeError("pattern must be a string or None")
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
            return cls.search(
                query=_optional_str_value(value, "query"),
                queries=_optional_str_tuple(value, "queries"),
            )
        if action_type == "open_page":
            return cls.open_page(_optional_str_value(value, "url"))
        if action_type == "find_in_page":
            return cls.find_in_page(
                url=_optional_str_value(value, "url"),
                pattern=_optional_str_value(value, "pattern"),
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

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type != "summary_text":
            raise ValueError(f"unknown reasoning summary type: {self.type}")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    @classmethod
    def summary_text(cls, text: str) -> "ReasoningItemReasoningSummary":
        return cls("summary_text", text)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReasoningItemReasoningSummary":
        data = _as_mapping(value, "reasoning summary")
        summary_type = _required_str(data, "type")
        if summary_type != "summary_text":
            raise ValueError(f"unknown reasoning summary type: {summary_type}")
        return cls.summary_text(_required_str(data, "text"))

    def to_mapping(self) -> dict[str, str]:
        return {"type": self.type, "text": self.text}


@dataclass(frozen=True)
class ReasoningItemContent:
    type: str
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type not in {"reasoning_text", "text"}:
            raise ValueError(f"unknown reasoning content type: {self.type}")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    @classmethod
    def reasoning_text(cls, text: str) -> "ReasoningItemContent":
        return cls("reasoning_text", text)

    @classmethod
    def text_content(cls, text: str) -> "ReasoningItemContent":
        return cls("text", text)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReasoningItemContent":
        data = _as_mapping(value, "reasoning content")
        content_type = _required_str(data, "type")
        if content_type == "reasoning_text":
            return cls.reasoning_text(_required_str(data, "text"))
        if content_type == "text":
            return cls.text_content(_required_str(data, "text"))
        raise ValueError(f"unknown reasoning content type: {content_type}")

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
    action: WebSearchAction | LocalShellAction | None = None
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
    def reasoning(
        cls,
        id: str,
        summary: tuple[ReasoningItemReasoningSummary | str, ...] | list[ReasoningItemReasoningSummary | str] = (),
        content: tuple[ReasoningItemContent | str, ...] | list[ReasoningItemContent | str] | None = None,
        encrypted_content: str | None = None,
    ) -> "ResponseItem":
        return cls(
            type="reasoning",
            id=id,
            summary=tuple(
                item if isinstance(item, ReasoningItemReasoningSummary) else ReasoningItemReasoningSummary.summary_text(item)
                for item in summary
            ),
            reasoning_content=(
                None
                if content is None
                else tuple(
                    item if isinstance(item, ReasoningItemContent) else ReasoningItemContent.text_content(item)
                    for item in content
                )
            ),
            encrypted_content=encrypted_content,
        )

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
        status: str | None = None,
        execution: str | None = None,
        id: str | None = None,
    ) -> "ResponseItem":
        if isinstance(arguments, SearchToolCallParams):
            arguments = arguments.to_mapping()
        return cls(
            type="tool_search_call",
            id=id,
            call_id=call_id,
            status=status,
            execution=execution,
            arguments=arguments,
        )

    @classmethod
    def custom_tool_call(
        cls,
        name: str,
        input: str,
        call_id: str,
        status: str | None = None,
        id: str | None = None,
    ) -> "ResponseItem":
        return cls(type="custom_tool_call", id=id, status=status, name=name, input=input, call_id=call_id)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ResponseItem":
        data = _as_mapping(value, "response item")
        item_type = _required_str(data, "type")
        if item_type == "message":
            return cls.message(
                _required_str(data, "role"),
                tuple(ContentItem.from_mapping(item) for item in _required_value(data, "content")),
                id=_optional_str_value(data, "id"),
                phase=_optional_message_phase(data, "phase"),
            )
        if item_type == "reasoning":
            raw_content = data.get("content")
            return cls(
                type="reasoning",
                id=_optional_str_value(data, "id"),
                summary=tuple(
                    ReasoningItemReasoningSummary.from_mapping(item)
                    for item in _required_value(data, "summary")
                ),
                reasoning_content=(
                    tuple(ReasoningItemContent.from_mapping(item) for item in raw_content)
                    if raw_content is not None
                    else None
                ),
                encrypted_content=_optional_str_value(data, "encrypted_content"),
            )
        if item_type == "local_shell_call":
            return cls(
                type="local_shell_call",
                id=_optional_str_value(data, "id"),
                call_id=_optional_str_value(data, "call_id"),
                status=LocalShellStatus(_required_str(data, "status")).value,
                action=LocalShellAction.from_mapping(_required_value(data, "action")),
            )
        if item_type == "function_call":
            return cls.function_call(
                _required_str(data, "name"),
                _required_str(data, "arguments"),
                _required_str(data, "call_id"),
                namespace=_optional_str_value(data, "namespace"),
                id=_optional_str_value(data, "id"),
            )
        if item_type == "tool_search_call":
            return cls.tool_search_call(
                _required_value(data, "arguments"),
                call_id=_optional_str_value(data, "call_id"),
                status=_optional_str_value(data, "status"),
                execution=_required_str(data, "execution"),
                id=_optional_str_value(data, "id"),
            )
        if item_type == "custom_tool_call":
            return cls.custom_tool_call(
                _required_str(data, "name"),
                _required_str(data, "input"),
                _required_str(data, "call_id"),
                status=_optional_str_value(data, "status"),
                id=_optional_str_value(data, "id"),
            )
        if item_type == "function_call_output":
            output_payload = FunctionCallOutputPayload.from_value(_required_value(data, "output"))
            return cls(
                type="function_call_output",
                call_id=_required_str(data, "call_id"),
                output=FunctionCallOutputPayload(output_payload.body, success=_optional_bool_field(data, "success")),
            )
        if item_type == "custom_tool_call_output":
            output_payload = FunctionCallOutputPayload.from_value(_required_value(data, "output"))
            return cls(
                type="custom_tool_call_output",
                call_id=_required_str(data, "call_id"),
                name=_optional_str_value(data, "name"),
                output=FunctionCallOutputPayload(output_payload.body, success=_optional_bool_field(data, "success")),
            )
        if item_type == "tool_search_output":
            return cls(
                type="tool_search_output",
                call_id=_optional_str_value(data, "call_id"),
                status=_required_str(data, "status"),
                execution=_required_str(data, "execution"),
                tools=tuple(_required_value(data, "tools")),
            )
        if item_type == "web_search_call":
            return cls.web_search_call(
                id=_optional_str_value(data, "id"),
                status=_optional_str_value(data, "status"),
                action=_optional_web_search_action(data, "action"),
            )
        if item_type == "image_generation_call":
            return cls.image_generation_call(
                id=_required_str(data, "id"),
                status=_required_str(data, "status"),
                revised_prompt=_optional_str_value(data, "revised_prompt"),
                result=_required_str(data, "result"),
            )
        if item_type in {"compaction", "compaction_summary"}:
            return cls.compaction(_required_str(data, "encrypted_content"))
        if item_type == "compaction_trigger":
            return cls.compaction_trigger()
        if item_type == "context_compaction":
            return cls.context_compaction(_optional_str_value(data, "encrypted_content"))
        if item_type == "ghost_snapshot":
            return cls.other()
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
            if self.type == "web_search_call" and key == "id" and self.action is None:
                continue
            if key == "call_id" and self.type in {"tool_search_call", "tool_search_output"}:
                data[key] = value
                continue
            if value is not None:
                data[key] = value
        if self.content:
            data["content"] = [item.to_mapping() for item in self.content]
        if self.phase is not None:
            data["phase"] = self.phase.value
        if self.type == "reasoning":
            data["summary"] = [item.to_mapping() for item in self.summary]
        elif self.summary:
            data["summary"] = [item.to_mapping() for item in self.summary]
        if should_serialize_reasoning_content(self.reasoning_content):
            data["content"] = [item.to_mapping() for item in self.reasoning_content or ()]
        if self.output is not None:
            if isinstance(self.output, FunctionCallOutputPayload):
                data["output"] = self.output.to_json()
            else:
                data["output"] = self.output
        if self.type == "tool_search_output" or self.tools:
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
SUPPORTED_LOCAL_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/gif",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "image/x-tiff",
}


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


def _local_image_content_items_with_label_number(path: Path, label_number: int, detail: ImageDetail) -> tuple[ContentItem, ...]:
    try:
        file_bytes = path.read_bytes()
    except OSError as exc:
        return (ContentItem.input_text(f"Codex could not read the local image at `{path}`: {exc}"),)
    mime_type, _encoding = mimetypes.guess_type(str(path))
    if mime_type is None or mime_type not in SUPPORTED_LOCAL_IMAGE_MIME_TYPES:
        return (
            ContentItem.input_text(
                f"Codex cannot attach image at `{path}`: unsupported image `{mime_type or 'application/octet-stream'}`."
            ),
        )
    if not _looks_like_supported_image(file_bytes, mime_type):
        return (ContentItem.input_text(f"Image located at `{path}` is invalid: could not decode image"),)
    image_url = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('ascii')}"
    return (
        ContentItem.input_text(local_image_open_tag_text(label_number)),
        ContentItem.input_image(image_url, detail=detail),
        ContentItem.input_text(local_image_close_tag_text()),
    )


def _looks_like_supported_image(file_bytes: bytes, mime_type: str) -> bool:
    if mime_type == "image/png":
        return file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type in {"image/jpeg", "image/jpg"}:
        return file_bytes.startswith(b"\xff\xd8\xff")
    if mime_type == "image/gif":
        return file_bytes.startswith((b"GIF87a", b"GIF89a"))
    if mime_type == "image/webp":
        return len(file_bytes) >= 12 and file_bytes.startswith(b"RIFF") and file_bytes[8:12] == b"WEBP"
    if mime_type == "image/bmp":
        return file_bytes.startswith(b"BM")
    if mime_type in {"image/tiff", "image/x-tiff"}:
        return file_bytes.startswith((b"II*\x00", b"MM\x00*"))
    return False


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _required_value(value: dict[str, JsonValue], key: str) -> JsonValue:
    if key not in value:
        raise KeyError(key)
    return value[key]


def _optional_str_value(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str_tuple(value: dict[str, JsonValue], key: str) -> tuple[str, ...] | None:
    raw = value.get(key)
    if raw is None:
        return None
    if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
        raise TypeError(f"{key} must be a list or tuple of strings")
    if not all(isinstance(item, str) for item in raw):
        raise TypeError(f"{key} entries must be strings")
    return tuple(raw)


def _optional_usize(value: dict[str, JsonValue], key: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise TypeError(f"{key} must be an integer")
    if raw < 0:
        raise ValueError(f"{key} must be non-negative")
    return raw


def _optional_u64_value(raw: JsonValue, key: str) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, int) or isinstance(raw, bool):
        raise TypeError(f"{key} must be an integer")
    if raw < 0 or raw > 2**64 - 1:
        raise ValueError(f"{key} must fit in u64")
    return raw


def _optional_bool_value(value: dict[str, JsonValue], key: str) -> bool | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


def _optional_image_detail(value: dict[str, JsonValue], key: str) -> ImageDetail | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return ImageDetail(raw)


def _optional_message_phase(value: dict[str, JsonValue], key: str) -> MessagePhase | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return MessagePhase(raw)


def _optional_web_search_action(value: dict[str, JsonValue], key: str) -> WebSearchAction | None:
    raw = value.get(key)
    if raw is None:
        return None
    return WebSearchAction.from_mapping(raw)


def _optional_bool_field(value: dict[str, JsonValue], key: str, default: bool = False) -> bool:
    raw = value.get(key, default)
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
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


def _as_mapping(value: JsonValue, label: str = "value") -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _optional_path(value: JsonValue) -> Path | None:
    return None if value is None else Path(str(value))


@dataclass(frozen=True)
class FileSystemPermissions:
    entries: tuple[_FileSystemSandboxEntry, ...] = ()
    glob_scan_max_depth: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            object.__setattr__(self, "entries", tuple(self.entries))
        if not all(isinstance(entry, _FileSystemSandboxEntry) for entry in self.entries):
            raise TypeError("entries must contain FileSystemSandboxEntry")
        if self.glob_scan_max_depth is not None:
            if isinstance(self.glob_scan_max_depth, bool) or not isinstance(self.glob_scan_max_depth, int):
                raise TypeError("glob_scan_max_depth must be an integer")
            if self.glob_scan_max_depth <= 0:
                raise ValueError("glob_scan_max_depth must be non-zero")

    def is_empty(self) -> bool:
        return len(self.entries) == 0

    @classmethod
    def from_read_write_roots(
        cls,
        read: tuple[Path | str, ...] | list[Path | str] | None = None,
        write: tuple[Path | str, ...] | list[Path | str] | None = None,
        *,
        read_roots: tuple[Path | str, ...] | list[Path | str] | None = None,
        write_roots: tuple[Path | str, ...] | list[Path | str] | None = None,
    ) -> "FileSystemPermissions":
        if read_roots is not None:
            read = read_roots
        if write_roots is not None:
            write = write_roots
        entries: list[_FileSystemSandboxEntry] = []
        for path in read or ():
            entries.append(_FileSystemSandboxEntry(_FileSystemPath.explicit_path(path), _FileSystemAccessMode.READ))
        for path in write or ():
            entries.append(_FileSystemSandboxEntry(_FileSystemPath.explicit_path(path), _FileSystemAccessMode.WRITE))
        return cls(tuple(entries))

    def explicit_path_entries(self) -> tuple[tuple[Path, _FileSystemAccessMode], ...]:
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
            if entry.access is _FileSystemAccessMode.READ:
                read.append(entry.path.path)
            elif entry.access is _FileSystemAccessMode.WRITE:
                write.append(entry.path.path)
            else:
                return None
        return (tuple(read) if read else None, tuple(write) if write else None)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "FileSystemPermissions":
        data = _as_mapping(value, "filesystem permissions")
        canonical_keys = {"entries", "glob_scan_max_depth"}
        legacy_keys = {"read", "write"}
        allowed_keys = canonical_keys if any(key in data for key in canonical_keys) else legacy_keys
        unknown = set(data) - allowed_keys
        if unknown:
            raise ValueError(f"unknown field: {sorted(unknown)[0]}")
        raw_depth = data.get("glob_scan_max_depth")
        if raw_depth is not None and (isinstance(raw_depth, bool) or not isinstance(raw_depth, int)):
            raise TypeError("glob_scan_max_depth must be an integer")
        glob_scan_max_depth = raw_depth
        if glob_scan_max_depth is not None and glob_scan_max_depth <= 0:
            raise ValueError("glob_scan_max_depth must be greater than zero")
        if "entries" in data:
            return cls(
                entries=tuple(_FileSystemSandboxEntry.from_mapping(item) for item in data.get("entries", ())),
                glob_scan_max_depth=glob_scan_max_depth,
            )
        return cls.from_read_write_roots(
            tuple(Path(str(path)) for path in data.get("read", ())),
            tuple(Path(str(path)) for path in data.get("write", ())),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        legacy_roots = self.legacy_read_write_roots()
        if legacy_roots is not None:
            read, write = legacy_roots
            legacy: dict[str, JsonValue] = {}
            if read:
                legacy["read"] = [str(path) for path in read]
            if write:
                legacy["write"] = [str(path) for path in write]
            return legacy

        data: dict[str, JsonValue] = {"entries": [entry.to_mapping() for entry in self.entries]}
        if self.glob_scan_max_depth is not None:
            data["glob_scan_max_depth"] = self.glob_scan_max_depth
        return data


@dataclass(frozen=True)
class NetworkPermissions:
    enabled: bool | None = None

    def __post_init__(self) -> None:
        if self.enabled is not None and not isinstance(self.enabled, bool):
            raise TypeError("enabled must be a bool")

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

    def __post_init__(self) -> None:
        if self.network is not None and not isinstance(self.network, NetworkPermissions):
            raise TypeError("network must be NetworkPermissions")
        if self.file_system is not None and not isinstance(self.file_system, FileSystemPermissions):
            raise TypeError("file_system must be FileSystemPermissions")

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
class ManagedFileSystemPermissions:
    type: str
    entries: tuple[_FileSystemSandboxEntry, ...] = ()
    glob_scan_max_depth: int | None = None

    def __post_init__(self) -> None:
        if self.type not in {"restricted", "unrestricted"}:
            raise ValueError(f"unknown managed filesystem permission type: {self.type}")
        if not isinstance(self.entries, tuple):
            object.__setattr__(self, "entries", tuple(self.entries))
        if not all(isinstance(entry, _FileSystemSandboxEntry) for entry in self.entries):
            raise TypeError("entries must contain FileSystemSandboxEntry")
        if self.type == "unrestricted" and self.entries:
            raise ValueError("unrestricted managed filesystem permissions cannot include entries")
        if self.type == "unrestricted" and self.glob_scan_max_depth is not None:
            raise ValueError("unrestricted managed filesystem permissions cannot include glob_scan_max_depth")
        if self.glob_scan_max_depth is not None:
            if isinstance(self.glob_scan_max_depth, bool) or not isinstance(self.glob_scan_max_depth, int):
                raise TypeError("glob_scan_max_depth must be an integer")
            if self.glob_scan_max_depth <= 0:
                raise ValueError("glob_scan_max_depth must be non-zero")

    @classmethod
    def restricted(
        cls,
        entries: tuple[_FileSystemSandboxEntry, ...] | list[_FileSystemSandboxEntry],
        glob_scan_max_depth: int | None = None,
    ) -> "ManagedFileSystemPermissions":
        return cls(type="restricted", entries=tuple(entries), glob_scan_max_depth=glob_scan_max_depth)

    @classmethod
    def unrestricted(cls) -> "ManagedFileSystemPermissions":
        return cls(type="unrestricted")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ManagedFileSystemPermissions":
        data = _as_mapping(value, "managed filesystem permissions")
        if not isinstance(data.get("type"), str):
            raise TypeError("type must be a string")
        permission_type = data["type"]
        if permission_type == "unrestricted":
            unknown = set(data) - {"type"}
            if unknown:
                raise ValueError(f"unknown field: {sorted(unknown)[0]}")
            return cls.unrestricted()
        if permission_type == "restricted":
            unknown = set(data) - {"type", "entries", "glob_scan_max_depth"}
            if unknown:
                raise ValueError(f"unknown field: {sorted(unknown)[0]}")
            raw_depth = data.get("glob_scan_max_depth")
            if raw_depth is not None and (isinstance(raw_depth, bool) or not isinstance(raw_depth, int)):
                raise TypeError("glob_scan_max_depth must be an integer")
            glob_scan_max_depth = raw_depth
            if glob_scan_max_depth is not None and glob_scan_max_depth <= 0:
                raise ValueError("glob_scan_max_depth must be greater than zero")
            return cls.restricted(
                tuple(_FileSystemSandboxEntry.from_mapping(item) for item in data.get("entries", ())),
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
    def from_sandbox_policy(cls, policy: _FileSystemSandboxPolicy) -> "ManagedFileSystemPermissions":
        if policy.kind is _FileSystemSandboxKind.UNRESTRICTED:
            return cls.unrestricted()
        if policy.kind is _FileSystemSandboxKind.EXTERNAL_SANDBOX:
            raise ValueError("external filesystem policies are represented by PermissionProfile.external")
        return cls.restricted(policy.entries, policy.glob_scan_max_depth)

    def to_sandbox_policy(self) -> _FileSystemSandboxPolicy:
        if self.type == "unrestricted":
            return _FileSystemSandboxPolicy.unrestricted()
        return _FileSystemSandboxPolicy(
            kind=_FileSystemSandboxKind.RESTRICTED,
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

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if self.extends is not None and not isinstance(self.extends, str):
            raise TypeError("extends must be a string")

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
    network: _NetworkSandboxPolicy | None = None

    def __post_init__(self) -> None:
        if self.type not in {"managed", "disabled", "external"}:
            raise ValueError(f"unknown permission profile type: {self.type}")
        if self.type == "managed":
            if not isinstance(self.file_system, ManagedFileSystemPermissions):
                raise TypeError("managed permission profile requires ManagedFileSystemPermissions")
            if not isinstance(self.network, _NetworkSandboxPolicy):
                raise TypeError("managed permission profile requires NetworkSandboxPolicy")
        elif self.type == "disabled":
            if self.file_system is not None:
                raise ValueError("disabled permission profile cannot include file_system")
            if self.network is not None:
                raise ValueError("disabled permission profile cannot include network")
        elif self.type == "external":
            if self.file_system is not None:
                raise ValueError("external permission profile cannot include file_system")
            if not isinstance(self.network, _NetworkSandboxPolicy):
                raise TypeError("external permission profile requires NetworkSandboxPolicy")

    @classmethod
    def default(cls) -> "PermissionProfile":
        return cls.managed(ManagedFileSystemPermissions.restricted(()), _NetworkSandboxPolicy.RESTRICTED)

    @classmethod
    def managed(
        cls,
        file_system: ManagedFileSystemPermissions,
        network: _NetworkSandboxPolicy,
    ) -> "PermissionProfile":
        return cls(type="managed", file_system=file_system, network=network)

    @classmethod
    def disabled(cls) -> "PermissionProfile":
        return cls(type="disabled")

    @classmethod
    def external(cls, network: _NetworkSandboxPolicy) -> "PermissionProfile":
        return cls(type="external", network=network)

    @classmethod
    def read_only(cls) -> "PermissionProfile":
        return cls.managed(
            ManagedFileSystemPermissions.restricted(
                (
                    _FileSystemSandboxEntry(
                        _FileSystemPath.special(_FileSystemSpecialPath.root()),
                        _FileSystemAccessMode.READ,
                    ),
                )
            ),
            _NetworkSandboxPolicy.RESTRICTED,
        )

    @classmethod
    def workspace_write(
        cls,
        writable_roots: tuple[Path | str, ...] | list[Path | str] = (),
        network: _NetworkSandboxPolicy = _NetworkSandboxPolicy.RESTRICTED,
        exclude_tmpdir_env_var: bool = False,
        exclude_slash_tmp: bool = False,
    ) -> "PermissionProfile":
        policy = _FileSystemSandboxPolicy.workspace_write(writable_roots, exclude_tmpdir_env_var, exclude_slash_tmp)
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
        file_system_sandbox_policy: _FileSystemSandboxPolicy,
        network_sandbox_policy: _NetworkSandboxPolicy,
    ) -> "PermissionProfile":
        if file_system_sandbox_policy.kind is _FileSystemSandboxKind.EXTERNAL_SANDBOX:
            return cls.external(network_sandbox_policy)
        return cls.managed(ManagedFileSystemPermissions.from_sandbox_policy(file_system_sandbox_policy), network_sandbox_policy)

    @classmethod
    def from_runtime_permissions_with_enforcement(
        cls,
        enforcement: SandboxEnforcement,
        file_system_sandbox_policy: _FileSystemSandboxPolicy,
        network_sandbox_policy: _NetworkSandboxPolicy,
    ) -> "PermissionProfile":
        if file_system_sandbox_policy.kind is _FileSystemSandboxKind.EXTERNAL_SANDBOX:
            return cls.external(network_sandbox_policy)
        if file_system_sandbox_policy.kind is _FileSystemSandboxKind.UNRESTRICTED and enforcement is SandboxEnforcement.DISABLED:
            return cls.disabled()
        return cls.managed(ManagedFileSystemPermissions.from_sandbox_policy(file_system_sandbox_policy), network_sandbox_policy)

    @classmethod
    def from_legacy_sandbox_policy(cls, sandbox_policy: SandboxPolicy) -> "PermissionProfile":
        return cls.from_runtime_permissions_with_enforcement(
            SandboxEnforcement.from_legacy_sandbox_policy(sandbox_policy),
            _FileSystemSandboxPolicy.from_legacy_sandbox_policy(sandbox_policy),
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
            _FileSystemSandboxPolicy.from_legacy_sandbox_policy_for_cwd(sandbox_policy, cwd),
            sandbox_policy.network_sandbox_policy(),
        )

    def enforcement(self) -> SandboxEnforcement:
        if self.type == "disabled":
            return SandboxEnforcement.DISABLED
        if self.type == "external":
            return SandboxEnforcement.EXTERNAL
        return SandboxEnforcement.MANAGED

    def file_system_sandbox_policy(self) -> _FileSystemSandboxPolicy:
        if self.type == "disabled":
            return _FileSystemSandboxPolicy.unrestricted()
        if self.type == "external":
            return _FileSystemSandboxPolicy.external_sandbox()
        if self.file_system is None:
            return _FileSystemSandboxPolicy.default()
        return self.file_system.to_sandbox_policy()

    def network_sandbox_policy(self) -> _NetworkSandboxPolicy:
        if self.type == "disabled":
            return _NetworkSandboxPolicy.ENABLED
        return self.network or _NetworkSandboxPolicy.RESTRICTED

    def to_legacy_sandbox_policy(self, cwd: Path | str) -> SandboxPolicy:
        if self.type == "disabled":
            return _sandbox_policy_type().danger_full_access()
        if self.type == "external":
            return _sandbox_policy_type().external_sandbox(self.network_sandbox_policy())
        return self.file_system_sandbox_policy().to_legacy_sandbox_policy(self.network_sandbox_policy(), cwd)

    def to_runtime_permissions(self) -> tuple[_FileSystemSandboxPolicy, _NetworkSandboxPolicy]:
        return self.file_system_sandbox_policy(), self.network_sandbox_policy()

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "PermissionProfile":
        data = _as_mapping(value, "permission profile")
        if "type" not in data:
            network = NetworkPermissions.from_mapping(data["network"]) if data.get("network") is not None else None
            file_system = FileSystemPermissions.from_mapping(data["file_system"]) if data.get("file_system") is not None else None
            file_system_sandbox_policy = (
                _FileSystemSandboxPolicy.restricted(())
                if file_system is None
                else _FileSystemSandboxPolicy(
                    kind=_FileSystemSandboxKind.RESTRICTED,
                    entries=file_system.entries,
                    glob_scan_max_depth=file_system.glob_scan_max_depth,
                )
            )
            network_sandbox_policy = (
                _NetworkSandboxPolicy.ENABLED
                if network is not None and network.enabled
                else _NetworkSandboxPolicy.RESTRICTED
            )
            return cls.from_runtime_permissions(file_system_sandbox_policy, network_sandbox_policy)

        if not isinstance(data["type"], str):
            raise TypeError("type must be a string")
        profile_type = data["type"]
        if profile_type == "managed":
            unknown = set(data) - {"type", "file_system", "network"}
            if unknown:
                raise ValueError(f"unknown field: {sorted(unknown)[0]}")
            return cls.managed(
                ManagedFileSystemPermissions.from_mapping(data["file_system"]),
                _NetworkSandboxPolicy.parse(data["network"]),
            )
        if profile_type == "disabled":
            unknown = set(data) - {"type"}
            if unknown:
                raise ValueError(f"unknown field: {sorted(unknown)[0]}")
            return cls.disabled()
        if profile_type == "external":
            unknown = set(data) - {"type", "network"}
            if unknown:
                raise ValueError(f"unknown field: {sorted(unknown)[0]}")
            return cls.external(_NetworkSandboxPolicy.parse(data["network"]))
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
