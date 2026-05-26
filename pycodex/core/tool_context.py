"""Shared tool invocation/output models ported from Codex core.

This is the standard-library slice of ``core/src/tools/context.rs`` that turns
tool runtime outputs into protocol response items.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import (
    CallToolResult,
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ImageDetail,
    ResponseInputItem,
    SearchToolCallParams,
    TruncationMode,
    TruncationPolicyConfig,
    function_call_output_content_items_to_text,
)
from pycodex.core.string_utils import (
    approx_bytes_for_tokens,
    approx_token_count,
    approx_tokens_from_byte_count,
    take_bytes_at_char_boundary,
    truncate_middle_chars,
    truncate_middle_with_token_budget,
)
from pycodex.core.original_image_detail import sanitize_original_image_detail

JsonValue = Any

TELEMETRY_PREVIEW_MAX_BYTES = 2 * 1024
TELEMETRY_PREVIEW_MAX_LINES = 64
TELEMETRY_PREVIEW_TRUNCATION_NOTICE = "[... telemetry preview truncated ...]"


@dataclass(frozen=True)
class ToolPayload:
    type: str
    arguments: str | None = None
    input: str | None = None
    search_arguments: SearchToolCallParams | None = None

    @classmethod
    def function(cls, arguments: str) -> "ToolPayload":
        return cls(type="function", arguments=arguments)

    @classmethod
    def custom(cls, input: str) -> "ToolPayload":
        return cls(type="custom", input=input)

    @classmethod
    def tool_search(cls, arguments: SearchToolCallParams) -> "ToolPayload":
        return cls(type="tool_search", search_arguments=arguments)

    def log_payload(self) -> str | None:
        if self.type == "function":
            return self.arguments
        if self.type == "custom":
            return self.input
        if self.type == "tool_search" and self.search_arguments is not None:
            return self.search_arguments.query
        return None


@dataclass(frozen=True)
class FunctionToolOutput:
    body: tuple[FunctionCallOutputContentItem, ...]
    success: bool | None = None
    post_tool_use_response_value: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "body",
            tuple(FunctionCallOutputContentItem.from_mapping(item) for item in self.body),
        )

    @classmethod
    def from_text(cls, text: str, success: bool | None = None) -> "FunctionToolOutput":
        return cls((FunctionCallOutputContentItem.input_text(text),), success)

    @classmethod
    def from_content(
        cls,
        content: tuple[FunctionCallOutputContentItem | JsonValue, ...] | list[FunctionCallOutputContentItem | JsonValue],
        success: bool | None = None,
    ) -> "FunctionToolOutput":
        return cls(tuple(FunctionCallOutputContentItem.from_mapping(item) for item in content), success)

    def into_text(self) -> str:
        return function_call_output_content_items_to_text(self.body) or ""

    def log_preview(self) -> str:
        return telemetry_preview(self.into_text())

    def success_for_logging(self) -> bool:
        return True if self.success is None else self.success

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return function_tool_response(call_id, payload, self.body, self.success)

    def post_tool_use_response(self, _call_id: str, _payload: ToolPayload) -> JsonValue | None:
        return self.post_tool_use_response_value


@dataclass(frozen=True)
class JsonToolOutput:
    value: JsonValue
    success: bool | None = True

    @classmethod
    def new(cls, value: JsonValue) -> "JsonToolOutput":
        return cls(value, True)

    @classmethod
    def with_success(cls, value: JsonValue, success: bool | None) -> "JsonToolOutput":
        return cls(value, success)

    def log_preview(self) -> str:
        return telemetry_preview(_json_dumps(self.value))

    def success_for_logging(self) -> bool:
        return True if self.success is None else self.success

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return function_tool_response(
            call_id,
            payload,
            (FunctionCallOutputContentItem.input_text(_json_dumps(self.value)),),
            self.success,
        )

    def post_tool_use_response(self, _call_id: str, _payload: ToolPayload) -> JsonValue:
        return self.value

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return self.value


@dataclass(frozen=True)
class McpToolOutput:
    result: CallToolResult
    tool_input: JsonValue
    wall_time_seconds: float
    original_image_detail_supported: bool
    truncation_policy: TruncationPolicyConfig

    def __post_init__(self) -> None:
        if not isinstance(self.result, CallToolResult):
            object.__setattr__(self, "result", CallToolResult.from_mapping(self.result))

    def log_preview(self) -> str:
        payload = self.response_payload()
        preview = payload.to_text()
        if preview is None:
            preview = _json_dumps(self.result.content)
        return telemetry_preview(preview)

    def success_for_logging(self) -> bool:
        return _call_tool_result_success(self.result)

    def to_response_item(self, call_id: str, _payload: ToolPayload) -> ResponseInputItem:
        return ResponseInputItem.function_call_output(call_id, self.response_payload())

    def code_mode_result(self, _payload: ToolPayload) -> JsonValue:
        return self.result.to_mapping()

    def post_tool_use_input(self, _payload: ToolPayload) -> JsonValue:
        return self.tool_input

    def post_tool_use_response(self, _call_id: str, _payload: ToolPayload) -> JsonValue:
        return self.result.to_mapping()

    def response_payload(self) -> FunctionCallOutputPayload:
        payload = _call_tool_result_to_function_payload(self.result)
        header = f"Wall time: {self.wall_time_seconds:.4f} seconds\nOutput:"

        if payload.content_items is not None:
            items = [_sanitize_image_detail(item) for item in payload.content_items]
            items = sanitize_original_image_detail(
                self.original_image_detail_supported,
                items,
            )
            return FunctionCallOutputPayload.from_content_items(
                (FunctionCallOutputContentItem.input_text(header), *items),
                payload.success,
            )

        text = payload.to_text() or ""
        text = header if text == "" else f"{header}\n{text}"
        return FunctionCallOutputPayload.from_text(
            _truncate_mcp_output_text(text, _scaled_truncation_policy(self.truncation_policy, 1.2)),
            payload.success,
        )


@dataclass(frozen=True)
class ApplyPatchToolOutput:
    text: str

    @classmethod
    def from_text(cls, text: str) -> "ApplyPatchToolOutput":
        return cls(text)

    def log_preview(self) -> str:
        return telemetry_preview(self.text)

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return function_tool_response(
            call_id,
            payload,
            (FunctionCallOutputContentItem.input_text(self.text),),
            True,
        )

    def post_tool_use_response(self, _call_id: str, _payload: ToolPayload) -> str:
        return self.text

    def code_mode_result(self, _payload: ToolPayload) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class AbortedToolOutput:
    message: str

    def log_preview(self) -> str:
        return telemetry_preview(self.message)

    def success_for_logging(self) -> bool:
        return False

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        if payload.type == "tool_search":
            return ResponseInputItem.tool_search_output(call_id, "completed", "client", ())
        return function_tool_response(
            call_id,
            payload,
            (FunctionCallOutputContentItem.input_text(self.message),),
            None,
        )


@dataclass(frozen=True)
class ToolSearchOutput:
    tools: tuple[JsonValue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tools", tuple(self.tools))

    def log_preview(self) -> str:
        return telemetry_preview(json.dumps([_to_json_value(tool) for tool in self.tools], separators=(",", ":")))

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, _payload: ToolPayload) -> ResponseInputItem:
        return ResponseInputItem.tool_search_output(
            call_id,
            "completed",
            "client",
            tuple(_to_json_value(tool) for tool in self.tools),
        )


@dataclass(frozen=True)
class ExecCommandToolOutput:
    event_call_id: str
    chunk_id: str
    wall_time_seconds: float
    raw_output: bytes
    truncation_policy: TruncationPolicyConfig
    max_output_tokens: int | None = None
    process_id: int | None = None
    exit_code: int | None = None
    original_token_count: int | None = None
    hook_command: str | None = None

    def log_preview(self) -> str:
        return telemetry_preview(self.response_text())

    def success_for_logging(self) -> bool:
        return True

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return function_tool_response(
            call_id,
            payload,
            (FunctionCallOutputContentItem.input_text(self.response_text()),),
            True,
        )

    def post_tool_use_id(self, call_id: str) -> str:
        return self.event_call_id or call_id

    def post_tool_use_input(self, _payload: ToolPayload) -> JsonValue | None:
        if self.hook_command is None:
            return None
        return {"command": self.hook_command}

    def post_tool_use_response(self, _call_id: str, _payload: ToolPayload) -> JsonValue | None:
        if self.process_id is not None or self.hook_command is None:
            return None
        return self.truncated_output(self.model_output_max_tokens())

    def code_mode_result(self, _payload: ToolPayload) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "wall_time_seconds": self.wall_time_seconds,
            "output": (
                self.truncated_output(self.max_output_tokens)
                if self.max_output_tokens is not None
                else self.raw_output.decode("utf-8", errors="replace")
            ),
        }
        if self.chunk_id:
            data["chunk_id"] = self.chunk_id
        if self.exit_code is not None:
            data["exit_code"] = self.exit_code
        if self.process_id is not None:
            data["session_id"] = self.process_id
        if self.original_token_count is not None:
            data["original_token_count"] = self.original_token_count
        return data

    def model_output_max_tokens(self) -> int:
        token_budget = (
            self.truncation_policy.limit
            if self.truncation_policy.mode is TruncationMode.TOKENS
            else 10_000
        )
        if self.max_output_tokens is None:
            return token_budget
        return min(self.max_output_tokens, token_budget)

    def truncated_output(self, max_tokens: int) -> str:
        text = self.raw_output.decode("utf-8", errors="replace")
        return formatted_truncate_text(text, TruncationPolicyConfig.tokens(max_tokens))

    def response_text(self) -> str:
        sections: list[str] = []
        if self.chunk_id:
            sections.append(f"Chunk ID: {self.chunk_id}")
        sections.append(f"Wall time: {self.wall_time_seconds:.4f} seconds")
        if self.exit_code is not None:
            sections.append(f"Process exited with code {self.exit_code}")
        if self.process_id is not None:
            sections.append(f"Process running with session ID {self.process_id}")
        if self.original_token_count is not None:
            sections.append(f"Original token count: {self.original_token_count}")
        sections.append("Output:")
        sections.append(self.truncated_output(self.model_output_max_tokens()))
        return "\n".join(sections)


def function_tool_response(
    call_id: str,
    payload: ToolPayload,
    body: tuple[FunctionCallOutputContentItem, ...] | list[FunctionCallOutputContentItem],
    success: bool | None,
) -> ResponseInputItem:
    body = tuple(FunctionCallOutputContentItem.from_mapping(item) for item in body)
    if len(body) == 1 and body[0].type == "input_text":
        output = FunctionCallOutputPayload.from_text(body[0].text or "", success=success)
    else:
        output = FunctionCallOutputPayload.from_content_items(body, success=success)

    if payload.type == "custom":
        return ResponseInputItem.custom_tool_call_output(call_id, output)
    return ResponseInputItem.function_call_output(call_id, output)


def telemetry_preview(content: str) -> str:
    truncated_slice = take_bytes_at_char_boundary(content, TELEMETRY_PREVIEW_MAX_BYTES)
    truncated_by_bytes = len(truncated_slice.encode("utf-8")) < len(content.encode("utf-8"))

    lines = truncated_slice.splitlines()
    preview_lines = lines[:TELEMETRY_PREVIEW_MAX_LINES]
    truncated_by_lines = len(lines) > TELEMETRY_PREVIEW_MAX_LINES
    preview = "\n".join(preview_lines)

    if not truncated_by_bytes and not truncated_by_lines:
        return content

    if preview and not preview.endswith("\n"):
        preview += "\n"
    return preview + TELEMETRY_PREVIEW_TRUNCATION_NOTICE


def formatted_truncate_text(content: str, policy: TruncationPolicyConfig) -> str:
    if len(content.encode("utf-8")) <= _policy_byte_budget(policy):
        return content
    truncated = truncate_text(content, policy)
    return f"Total output lines: {len(content.splitlines()) or 1}\n\n{truncated}"


def truncate_text(content: str, policy: TruncationPolicyConfig) -> str:
    if policy.mode is TruncationMode.BYTES:
        return truncate_middle_chars(content, policy.limit)
    truncated, _original_token_count = truncate_middle_with_token_budget(content, policy.limit)
    return truncated


def formatted_truncate_text_content_items_with_policy(
    items: tuple[FunctionCallOutputContentItem, ...] | list[FunctionCallOutputContentItem],
    policy: TruncationPolicyConfig,
) -> tuple[tuple[FunctionCallOutputContentItem, ...], int | None]:
    content_items = tuple(FunctionCallOutputContentItem.from_mapping(item) for item in items)
    text_segments = tuple(
        item.text or ""
        for item in content_items
        if item.type == "input_text"
    )
    if not text_segments:
        return content_items, None

    combined = "\n".join(text_segments)
    if len(combined.encode("utf-8")) <= _policy_byte_budget(policy):
        return content_items, None

    output: list[FunctionCallOutputContentItem] = [
        FunctionCallOutputContentItem.input_text(
            formatted_truncate_text(combined, policy)
        )
    ]
    output.extend(
        item
        for item in content_items
        if item.type in ("input_image", "encrypted_content")
    )
    return tuple(output), approx_token_count(combined)


def truncate_function_output_items_with_policy(
    items: tuple[FunctionCallOutputContentItem, ...] | list[FunctionCallOutputContentItem],
    policy: TruncationPolicyConfig,
) -> tuple[FunctionCallOutputContentItem, ...]:
    content_items = tuple(FunctionCallOutputContentItem.from_mapping(item) for item in items)
    output: list[FunctionCallOutputContentItem] = []
    remaining_budget = _policy_budget_for_mode(policy)
    omitted_text_items = 0

    for item in content_items:
        if item.type == "input_text":
            text = item.text or ""
            if remaining_budget == 0:
                omitted_text_items += 1
                continue

            cost = (
                len(text.encode("utf-8"))
                if policy.mode is TruncationMode.BYTES
                else approx_token_count(text)
            )
            if cost <= remaining_budget:
                output.append(item)
                remaining_budget = max(remaining_budget - cost, 0)
            else:
                snippet_policy = (
                    TruncationPolicyConfig.bytes(remaining_budget)
                    if policy.mode is TruncationMode.BYTES
                    else TruncationPolicyConfig.tokens(remaining_budget)
                )
                snippet = truncate_text(text, snippet_policy)
                if snippet:
                    output.append(FunctionCallOutputContentItem.input_text(snippet))
                else:
                    omitted_text_items += 1
                remaining_budget = 0
        elif item.type in ("input_image", "encrypted_content"):
            output.append(item)

    if omitted_text_items > 0:
        output.append(
            FunctionCallOutputContentItem.input_text(
                f"[omitted {omitted_text_items} text items ...]"
            )
        )

    return tuple(output)


def approx_tokens_from_byte_count_i64(bytes_count: int) -> int:
    if bytes_count <= 0:
        return 0
    return approx_tokens_from_byte_count(bytes_count)


def _to_json_value(value: JsonValue) -> JsonValue:
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    return value


def _call_tool_result_success(result: CallToolResult) -> bool:
    return result.is_error is not True


def _call_tool_result_to_function_payload(result: CallToolResult) -> FunctionCallOutputPayload:
    if result.structured_content is not None:
        return FunctionCallOutputPayload.from_text(
            _json_dumps(result.structured_content),
            _call_tool_result_success(result),
        )

    content_items = _convert_mcp_content_to_items(result.content)
    if content_items is not None:
        return FunctionCallOutputPayload.from_content_items(
            content_items,
            _call_tool_result_success(result),
        )

    return FunctionCallOutputPayload.from_text(
        _json_dumps(result.content),
        _call_tool_result_success(result),
    )


def _convert_mcp_content_to_items(contents: tuple[JsonValue, ...]) -> tuple[FunctionCallOutputContentItem, ...] | None:
    saw_image = False
    items: list[FunctionCallOutputContentItem] = []
    for content in contents:
        if not isinstance(content, dict):
            items.append(FunctionCallOutputContentItem.input_text(_json_dumps(content)))
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
            items.append(FunctionCallOutputContentItem.input_text(_json_dumps(content)))
    return tuple(items) if saw_image else None


def _image_detail_from_mcp_meta(meta: JsonValue) -> ImageDetail | None:
    if not isinstance(meta, dict):
        return None
    detail = meta.get("codex/imageDetail")
    if detail == ImageDetail.HIGH.value:
        return ImageDetail.HIGH
    if detail == ImageDetail.ORIGINAL.value:
        return ImageDetail.ORIGINAL
    return None


def _sanitize_image_detail(item: FunctionCallOutputContentItem) -> FunctionCallOutputContentItem:
    if item.type == "input_image" and item.detail is None:
        return FunctionCallOutputContentItem.input_image(item.image_url or "", DEFAULT_IMAGE_DETAIL)
    return item


def _scaled_truncation_policy(policy: TruncationPolicyConfig, scale: float) -> TruncationPolicyConfig:
    limit = max(1, int(policy.limit * scale))
    if policy.mode is TruncationMode.BYTES:
        return TruncationPolicyConfig.bytes(limit)
    return TruncationPolicyConfig.tokens(limit)


def _truncate_mcp_output_text(content: str, policy: TruncationPolicyConfig) -> str:
    return truncate_text(content, policy)


def _policy_byte_budget(policy: TruncationPolicyConfig) -> int:
    if policy.mode is TruncationMode.BYTES:
        return max(policy.limit, 0)
    return approx_bytes_for_tokens(policy.limit)


def _policy_budget_for_mode(policy: TruncationPolicyConfig) -> int:
    if policy.mode is TruncationMode.BYTES:
        return max(policy.limit, 0)
    return max(policy.limit, 0)


def _json_dumps(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "AbortedToolOutput",
    "ApplyPatchToolOutput",
    "ExecCommandToolOutput",
    "FunctionToolOutput",
    "JsonToolOutput",
    "McpToolOutput",
    "TELEMETRY_PREVIEW_MAX_BYTES",
    "TELEMETRY_PREVIEW_MAX_LINES",
    "TELEMETRY_PREVIEW_TRUNCATION_NOTICE",
    "ToolPayload",
    "ToolSearchOutput",
    "approx_tokens_from_byte_count_i64",
    "formatted_truncate_text_content_items_with_policy",
    "formatted_truncate_text",
    "function_tool_response",
    "telemetry_preview",
    "truncate_function_output_items_with_policy",
    "truncate_text",
]
