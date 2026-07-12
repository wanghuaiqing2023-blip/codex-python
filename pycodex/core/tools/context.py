"""Shared tool invocation/output models ported from Codex core.

This is the standard-library slice of ``core/src/tools/context.rs`` that turns
tool runtime outputs into protocol response items.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from pycodex.protocol import (
    CallToolResult,
    DEFAULT_IMAGE_DETAIL,
    FunctionCallOutputContentItem,
    FunctionCallOutputPayload,
    ImageDetail,
    ResponseInputItem,
    SearchToolCallParams,
    ToolName,
    TruncationMode,
    TruncationPolicyConfig,
    convert_mcp_content_to_items,
    function_call_output_content_items_to_text,
)
from pycodex.utils.output_truncation import (
    approx_tokens_from_byte_count_i64,
    formatted_truncate_text,
    formatted_truncate_text_content_items_with_policy,
    truncate_function_output_items_with_policy,
    truncate_function_output_payload,
    truncate_text,
)
from pycodex.utils.string import (
    take_bytes_at_char_boundary,
)
from pycodex.tools.original_image_detail import sanitize_original_image_detail

JsonValue = Any

TELEMETRY_PREVIEW_MAX_BYTES = 2 * 1024
TELEMETRY_PREVIEW_MAX_LINES = 64
TELEMETRY_PREVIEW_TRUNCATION_NOTICE = "[... telemetry preview truncated ...]"


@runtime_checkable
class ToolOutput(Protocol):
    """Protocol-shaped counterpart of Rust's ``dyn ToolOutput`` trait."""

    def log_preview(self) -> str:
        ...

    def success_for_logging(self) -> bool:
        ...

    def to_response_item(self, call_id: str, payload: "ToolPayload") -> ResponseInputItem:
        ...


def boxed_tool_output(output: ToolOutput) -> ToolOutput:
    """Validate and return a Python tool output object.

    Rust boxes ``ToolOutput`` trait objects before handing them to the tool
    runtime. Python keeps objects by reference, so this helper preserves the
    boundary check without introducing an unnecessary wrapper.
    """

    for method_name in ("log_preview", "success_for_logging", "to_response_item"):
        if not callable(getattr(output, method_name, None)):
            raise TypeError(f"tool output must expose {method_name}()")
    return output


SharedTurnDiffTracker = Any


@dataclass(frozen=True)
class ToolCallSource:
    type: str
    cell_id: str | None = None
    runtime_tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("tool call source type must be a string")
        if self.type == "direct":
            if self.cell_id is not None or self.runtime_tool_call_id is not None:
                raise ValueError("direct tool call source must not include code-mode fields")
        elif self.type == "code_mode":
            if not isinstance(self.cell_id, str):
                raise TypeError("code_mode tool call source requires a string cell_id")
            if not isinstance(self.runtime_tool_call_id, str):
                raise TypeError("code_mode tool call source requires a string runtime_tool_call_id")
        else:
            raise ValueError(f"unsupported tool call source type: {self.type}")

    @classmethod
    def direct(cls) -> "ToolCallSource":
        return cls("direct")

    @classmethod
    def code_mode(cls, cell_id: str, runtime_tool_call_id: str) -> "ToolCallSource":
        return cls("code_mode", cell_id, runtime_tool_call_id)

    @property
    def is_direct(self) -> bool:
        return self.type == "direct"

    @property
    def is_code_mode(self) -> bool:
        return self.type == "code_mode"


@dataclass(frozen=True)
class ToolPayload:
    type: str
    arguments: str | None = None
    input: str | None = None
    search_arguments: SearchToolCallParams | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("tool payload type must be a string")
        if self.type == "function":
            if not isinstance(self.arguments, str):
                raise TypeError("function payload arguments must be a string")
            if self.input is not None or self.search_arguments is not None:
                raise ValueError("function payload must not include custom or tool_search fields")
        elif self.type == "custom":
            if not isinstance(self.input, str):
                raise TypeError("custom payload input must be a string")
            if self.arguments is not None or self.search_arguments is not None:
                raise ValueError("custom payload must not include function or tool_search fields")
        elif self.type == "tool_search":
            if not isinstance(self.search_arguments, SearchToolCallParams):
                raise TypeError("tool_search payload arguments must be SearchToolCallParams")
            if self.arguments is not None or self.input is not None:
                raise ValueError("tool_search payload must not include function or custom fields")
        else:
            raise ValueError(f"unsupported tool payload type: {self.type}")

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
class ToolInvocation:
    session: Any
    turn: Any
    cancellation_token: Any
    tracker: SharedTurnDiffTracker
    call_id: str
    tool_name: ToolName | str
    source: ToolCallSource
    payload: ToolPayload

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id:
            raise TypeError("tool invocation call_id must be a non-empty string")
        try:
            tool_name = ToolName.from_value(self.tool_name)
        except TypeError as err:
            raise TypeError("tool invocation tool_name must be ToolName or a non-empty string") from err
        if not tool_name.name:
            raise TypeError("tool invocation tool_name must be a non-empty string")
        object.__setattr__(self, "tool_name", tool_name)
        if not isinstance(self.source, ToolCallSource):
            raise TypeError("tool invocation source must be ToolCallSource")
        if not isinstance(self.payload, ToolPayload):
            raise TypeError("tool invocation payload must be ToolPayload")

    @property
    def is_code_mode(self) -> bool:
        return self.source.is_code_mode


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
            items = truncate_function_output_items_with_policy(
                (FunctionCallOutputContentItem.input_text(header), *items),
                _scaled_truncation_policy(self.truncation_policy, 1.2),
            )
            return FunctionCallOutputPayload.from_content_items(
                items,
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
class PostToolUseFeedbackOutput:
    original: Any
    model_visible: FunctionToolOutput

    def __post_init__(self) -> None:
        if not isinstance(self.model_visible, FunctionToolOutput):
            raise TypeError("model_visible must be FunctionToolOutput")
        for method_name in (
            "log_preview",
            "success_for_logging",
            "to_response_item",
        ):
            if not callable(getattr(self.original, method_name, None)):
                raise TypeError(f"original must expose {method_name}()")

    def log_preview(self) -> str:
        return self.original.log_preview()

    def success_for_logging(self) -> bool:
        return self.original.success_for_logging()

    def to_response_item(self, call_id: str, payload: ToolPayload) -> ResponseInputItem:
        return self.model_visible.to_response_item(call_id, payload)

    def code_mode_result(self, payload: ToolPayload) -> JsonValue:
        method = getattr(self.original, "code_mode_result", None)
        if method is None:
            return response_input_to_code_mode_result(self.original.to_response_item("", payload))
        return method(payload)


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
        from pycodex.protocol.exec_output import bytes_to_string_smart

        data: dict[str, JsonValue] = {
            "wall_time_seconds": self.wall_time_seconds,
            "output": (
                self.truncated_output(self.max_output_tokens)
                if self.max_output_tokens is not None
                else bytes_to_string_smart(self.raw_output)
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
        from pycodex.protocol.exec_output import bytes_to_string_smart

        text = bytes_to_string_smart(self.raw_output)
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


def response_input_to_code_mode_result(response: ResponseInputItem) -> JsonValue:
    if not isinstance(response, ResponseInputItem):
        raise TypeError("response must be ResponseInputItem")
    if response.type == "message":
        return _content_items_to_code_mode_result(response.content)
    if response.type in {"function_call_output", "custom_tool_call_output"}:
        output = response.output
        if isinstance(output, FunctionCallOutputPayload):
            if output.content_items is not None:
                return _content_items_to_code_mode_result(output.content_items)
            return output.to_text() or ""
        return output
    if response.type == "tool_search_output":
        return list(response.tools)
    if response.type == "mcp_tool_call_output":
        output = response.output
        to_mapping = getattr(output, "to_mapping", None)
        if callable(to_mapping):
            return to_mapping()
        return output
    return {}


def _content_items_to_code_mode_result(items: Any) -> str:
    parts: list[str] = []
    for item in items:
        item_type = getattr(item, "type", None)
        if item_type in {"input_text", "output_text"}:
            text = getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text)
        elif item_type == "input_image":
            image_url = getattr(item, "image_url", None)
            if isinstance(image_url, str) and image_url.strip():
                parts.append(image_url)
    return "\n".join(parts)


def telemetry_preview(content: str) -> str:
    truncated_slice = take_bytes_at_char_boundary(content, TELEMETRY_PREVIEW_MAX_BYTES)
    truncated_by_bytes = len(truncated_slice.encode("utf-8")) < len(content.encode("utf-8"))

    lines_iter = iter(truncated_slice.splitlines())
    preview_lines: list[str] = []
    for _ in range(TELEMETRY_PREVIEW_MAX_LINES):
        try:
            preview_lines.append(next(lines_iter))
        except StopIteration:
            break
    truncated_by_lines = next(lines_iter, None) is not None
    preview = "\n".join(preview_lines)

    if not truncated_by_bytes and not truncated_by_lines:
        return content

    if len(preview) < len(truncated_slice) and truncated_slice[len(preview) : len(preview) + 1] == "\n":
        preview += "\n"
    if preview and not preview.endswith("\n"):
        preview += "\n"
    return preview + TELEMETRY_PREVIEW_TRUNCATION_NOTICE


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


def call_tool_result_to_function_payload(result: CallToolResult | JsonValue) -> FunctionCallOutputPayload:
    if not isinstance(result, CallToolResult):
        result = CallToolResult.from_mapping(result)
    return _call_tool_result_to_function_payload(result)


def _convert_mcp_content_to_items(contents: tuple[JsonValue, ...]) -> tuple[FunctionCallOutputContentItem, ...] | None:
    return convert_mcp_content_to_items(contents)


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


def _json_dumps(value: JsonValue) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "AbortedToolOutput",
    "ApplyPatchToolOutput",
    "ExecCommandToolOutput",
    "FunctionToolOutput",
    "JsonToolOutput",
    "McpToolOutput",
    "PostToolUseFeedbackOutput",
    "TELEMETRY_PREVIEW_MAX_BYTES",
    "TELEMETRY_PREVIEW_MAX_LINES",
    "TELEMETRY_PREVIEW_TRUNCATION_NOTICE",
    "ToolPayload",
    "ToolSearchOutput",
    "approx_tokens_from_byte_count_i64",
    "formatted_truncate_text_content_items_with_policy",
    "formatted_truncate_text",
    "function_tool_response",
    "call_tool_result_to_function_payload",
    "response_input_to_code_mode_result",
    "telemetry_preview",
    "truncate_function_output_payload",
    "truncate_function_output_items_with_policy",
    "truncate_text",
]
