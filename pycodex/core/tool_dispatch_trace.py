"""Tool dispatch trace payload mapping ported from Codex core."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.core.tool_context import ToolPayload
from pycodex.core.tool_registry import ToolCallSource, ToolInvocation
from pycodex.protocol import ResponseInputItem, SearchToolCallParams

JsonValue = Any


def _ensure_str(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    return value


def _ensure_optional_str(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field)


def _ensure_json_value(value: JsonValue, field: str) -> JsonValue:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field} must be JSON-serializable") from exc
    return value


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolDispatchRequester:
    type: str
    model_visible_call_id: str | None = None
    runtime_cell_id: str | None = None
    runtime_tool_call_id: str | None = None

    def __post_init__(self) -> None:
        requester_type = _ensure_str(self.type, "type")
        if requester_type == "model":
            object.__setattr__(self, "model_visible_call_id", _ensure_str(self.model_visible_call_id, "model_visible_call_id"))
            object.__setattr__(self, "runtime_cell_id", None)
            object.__setattr__(self, "runtime_tool_call_id", None)
        elif requester_type == "code_cell":
            object.__setattr__(self, "model_visible_call_id", None)
            object.__setattr__(self, "runtime_cell_id", _ensure_str(self.runtime_cell_id, "runtime_cell_id"))
            object.__setattr__(self, "runtime_tool_call_id", _ensure_str(self.runtime_tool_call_id, "runtime_tool_call_id"))
        else:
            raise ValueError(f"unsupported tool dispatch requester type: {requester_type}")

    @classmethod
    def model(cls, model_visible_call_id: str) -> "ToolDispatchRequester":
        return cls(type="model", model_visible_call_id=model_visible_call_id)

    @classmethod
    def code_cell(cls, runtime_cell_id: str, runtime_tool_call_id: str) -> "ToolDispatchRequester":
        return cls(
            type="code_cell",
            runtime_cell_id=runtime_cell_id,
            runtime_tool_call_id=runtime_tool_call_id,
        )


@dataclass(frozen=True)
class ToolDispatchPayload:
    type: str
    arguments: str | SearchToolCallParams | None = None
    input: str | None = None

    def __post_init__(self) -> None:
        payload_type = _ensure_str(self.type, "type")
        if payload_type == "function":
            object.__setattr__(self, "arguments", _ensure_str(self.arguments, "arguments"))
            object.__setattr__(self, "input", None)
        elif payload_type == "tool_search":
            if not isinstance(self.arguments, SearchToolCallParams):
                raise TypeError("arguments must be SearchToolCallParams for tool_search payloads")
            object.__setattr__(self, "input", None)
        elif payload_type == "custom":
            object.__setattr__(self, "arguments", None)
            object.__setattr__(self, "input", _ensure_str(self.input, "input"))
        else:
            raise ValueError(f"unsupported tool dispatch payload type: {payload_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if isinstance(self.arguments, SearchToolCallParams):
            data["arguments"] = self.arguments.to_mapping()
        elif self.arguments is not None:
            data["arguments"] = self.arguments
        if self.input is not None:
            data["input"] = self.input
        return data


@dataclass(frozen=True)
class ToolDispatchInvocation:
    thread_id: str
    codex_turn_id: str
    tool_call_id: str
    tool_name: str
    tool_namespace: str | None
    requester: ToolDispatchRequester
    payload: ToolDispatchPayload

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "codex_turn_id", _ensure_str(self.codex_turn_id, "codex_turn_id"))
        object.__setattr__(self, "tool_call_id", _ensure_str(self.tool_call_id, "tool_call_id"))
        object.__setattr__(self, "tool_name", _ensure_str(self.tool_name, "tool_name"))
        object.__setattr__(self, "tool_namespace", _ensure_optional_str(self.tool_namespace, "tool_namespace"))
        if not isinstance(self.requester, ToolDispatchRequester):
            raise TypeError("requester must be a ToolDispatchRequester")
        if not isinstance(self.payload, ToolDispatchPayload):
            raise TypeError("payload must be a ToolDispatchPayload")


@dataclass(frozen=True)
class ToolDispatchResult:
    type: str
    response_item: ResponseInputItem | None = None
    value: JsonValue | None = None

    def __post_init__(self) -> None:
        result_type = _ensure_str(self.type, "type")
        if result_type == "direct_response":
            if not isinstance(self.response_item, ResponseInputItem):
                raise TypeError("response_item must be a ResponseInputItem")
            object.__setattr__(self, "value", None)
        elif result_type == "code_mode_response":
            object.__setattr__(self, "response_item", None)
            object.__setattr__(self, "value", _ensure_json_value(self.value, "value"))
        else:
            raise ValueError(f"unsupported tool dispatch result type: {result_type}")

    @classmethod
    def direct_response(cls, response_item: ResponseInputItem) -> "ToolDispatchResult":
        return cls(type="direct_response", response_item=response_item)

    @classmethod
    def code_mode_response(cls, value: JsonValue) -> "ToolDispatchResult":
        return cls(type="code_mode_response", value=value)


class DisabledToolDispatchTraceContext:
    def is_enabled(self) -> bool:
        return False

    def record_completed(self, status: ExecutionStatus, result: ToolDispatchResult) -> None:
        return None

    def record_failed(self, error: Any) -> None:
        return None


@dataclass(frozen=True)
class ToolDispatchTrace:
    context: Any

    @classmethod
    def start(
        cls,
        invocation: ToolInvocation,
        trace_context: Any = None,
        *,
        thread_id: str = "",
        codex_turn_id: str = "",
    ) -> "ToolDispatchTrace":
        if trace_context is None:
            return cls(DisabledToolDispatchTraceContext())
        starter = getattr(trace_context, "start_tool_dispatch_trace", None)
        if callable(starter):
            context = starter(
                lambda: tool_dispatch_invocation(
                    invocation,
                    thread_id=thread_id,
                    codex_turn_id=codex_turn_id,
                )
            )
            return cls(context)
        return cls(trace_context)

    def record_completed(
        self,
        invocation: ToolInvocation,
        call_id: str,
        payload: ToolPayload,
        result: Any,
    ) -> None:
        if not _trace_context_is_enabled(self.context):
            return
        result_payload = tool_dispatch_result(invocation, call_id, payload, result)
        if result_payload is None:
            return
        recorder = getattr(self.context, "record_completed", None)
        if callable(recorder):
            recorder(execution_status_for_result(result), result_payload)

    def record_failed(self, error: Any) -> None:
        recorder = getattr(self.context, "record_failed", None)
        if callable(recorder):
            recorder(error)


def tool_dispatch_invocation(
    invocation: ToolInvocation,
    *,
    thread_id: str,
    codex_turn_id: str,
) -> ToolDispatchInvocation:
    return ToolDispatchInvocation(
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        tool_call_id=invocation.call_id,
        tool_name=invocation.tool_name.name,
        tool_namespace=invocation.tool_name.namespace,
        requester=tool_dispatch_requester(invocation.source, invocation.call_id),
        payload=tool_dispatch_payload(invocation.payload),
    )


def tool_dispatch_requester(source: ToolCallSource, call_id: str) -> ToolDispatchRequester:
    if not isinstance(source, ToolCallSource):
        raise TypeError("source must be a ToolCallSource")
    call_id = _ensure_str(call_id, "call_id")
    if source.type == "code_mode":
        return ToolDispatchRequester.code_cell(
            runtime_cell_id=source.cell_id or "",
            runtime_tool_call_id=source.runtime_tool_call_id or "",
        )
    return ToolDispatchRequester.model(model_visible_call_id=call_id)


def tool_dispatch_result(
    invocation: ToolInvocation,
    call_id: str,
    payload: ToolPayload,
    result: Any,
) -> ToolDispatchResult | None:
    if invocation.source.type == "code_mode":
        code_mode_result = getattr(result, "code_mode_result", None)
        if code_mode_result is None:
            return None
        return ToolDispatchResult.code_mode_response(code_mode_result(payload))

    to_response_item = getattr(result, "to_response_item", None)
    if to_response_item is None:
        return None
    return ToolDispatchResult.direct_response(to_response_item(call_id, payload))


def tool_dispatch_payload(payload: ToolPayload) -> ToolDispatchPayload:
    if not isinstance(payload, ToolPayload):
        raise TypeError("payload must be a ToolPayload")
    if payload.type == "function":
        return ToolDispatchPayload(type="function", arguments=payload.arguments or "")
    if payload.type == "tool_search":
        return ToolDispatchPayload(type="tool_search", arguments=payload.search_arguments)
    if payload.type == "custom":
        return ToolDispatchPayload(type="custom", input=payload.input or "")
    raise ValueError(f"unsupported tool payload type: {payload.type}")


def execution_status_for_result(result: Any) -> ExecutionStatus:
    success_for_logging = getattr(result, "success_for_logging", None)
    if success_for_logging is None or success_for_logging():
        return ExecutionStatus.COMPLETED
    return ExecutionStatus.FAILED


def _trace_context_is_enabled(context: Any) -> bool:
    is_enabled = getattr(context, "is_enabled", None)
    if callable(is_enabled):
        return bool(is_enabled())
    if isinstance(is_enabled, bool):
        return is_enabled
    return True


__all__ = [
    "DisabledToolDispatchTraceContext",
    "ExecutionStatus",
    "ToolDispatchTrace",
    "ToolDispatchInvocation",
    "ToolDispatchPayload",
    "ToolDispatchRequester",
    "ToolDispatchResult",
    "execution_status_for_result",
    "tool_dispatch_invocation",
    "tool_dispatch_payload",
    "tool_dispatch_requester",
    "tool_dispatch_result",
]
