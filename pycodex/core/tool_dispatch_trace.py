"""Tool dispatch trace payload mapping ported from Codex core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.core.tool_context import ToolPayload
from pycodex.core.tool_registry import ToolCallSource, ToolInvocation
from pycodex.protocol import ResponseInputItem, SearchToolCallParams

JsonValue = Any


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True)
class ToolDispatchRequester:
    type: str
    model_visible_call_id: str | None = None
    runtime_cell_id: str | None = None
    runtime_tool_call_id: str | None = None

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


@dataclass(frozen=True)
class ToolDispatchResult:
    type: str
    response_item: ResponseInputItem | None = None
    value: JsonValue | None = None

    @classmethod
    def direct_response(cls, response_item: ResponseInputItem) -> "ToolDispatchResult":
        return cls(type="direct_response", response_item=response_item)

    @classmethod
    def code_mode_response(cls, value: JsonValue) -> "ToolDispatchResult":
        return cls(type="code_mode_response", value=value)


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
    if payload.type == "function":
        return ToolDispatchPayload(type="function", arguments=payload.arguments or "")
    if payload.type == "tool_search":
        return ToolDispatchPayload(type="tool_search", arguments=payload.search_arguments)
    if payload.type == "custom":
        return ToolDispatchPayload(type="custom", input=payload.input or "")
    return ToolDispatchPayload(type=payload.type)


def execution_status_for_result(result: Any) -> ExecutionStatus:
    success_for_logging = getattr(result, "success_for_logging", None)
    if success_for_logging is None or success_for_logging():
        return ExecutionStatus.COMPLETED
    return ExecutionStatus.FAILED


__all__ = [
    "ExecutionStatus",
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
