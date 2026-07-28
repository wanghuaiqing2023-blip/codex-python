"""Rust-aligned owner for ``codex-rollout-trace::tool_dispatch``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.rollout_trace.model import *
from pycodex.rollout_trace.payload import *
from pycodex.rollout_trace.raw_event import *
from pycodex.rollout_trace.bundle import *
from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext, _jsonable, _unix_time_ms

class ToolDispatchTraceContext(_NoOpTraceContext):
    @classmethod
    def start(cls, writer: TraceWriter, invocation: "ToolDispatchInvocation") -> "ToolDispatchTraceContext":
        if _suppresses_tool_dispatch_trace(invocation):
            return cls.disabled()
        context = cls()
        context.enabled = True
        context.writer = writer
        context.thread_id = invocation.thread_id
        context.codex_turn_id = invocation.codex_turn_id
        context.tool_call_id = invocation.tool_call_id
        _record_tool_dispatch_started(context, invocation)
        return context

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def record_completed(self, status: ExecutionStatus, result: Any) -> None:
        if not self.is_enabled():
            return None
        if isinstance(result, ToolDispatchResult):
            if result.type == "direct_response":
                response = {"type": "direct_response", "response_item": result.value}
            elif result.type == "code_mode_response":
                response = {"type": "code_mode_response", "value": result.value}
            else:
                response = {"type": result.type, "value": result.value}
        else:
            response = {"type": "direct_response", "response_item": result}
        _append_tool_dispatch_ended(self, status, response)
        return None

    def record_failed(self, error: Any) -> None:
        if self.is_enabled():
            _append_tool_dispatch_ended(
                self,
                ExecutionStatus.FAILED,
                {"type": "error", "error": str(error)},
            )
        return None

@dataclass
class ToolDispatchInvocation:
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId
    tool_call_id: ToolCallId
    tool_name: str
    tool_namespace: str | None
    requester: Any
    payload: Any

@dataclass
class ToolDispatchRequester:
    type: str
    model_visible_call_id: str | None = None
    runtime_cell_id: str | None = None
    runtime_tool_call_id: str | None = None

    @classmethod
    def Model(cls, model_visible_call_id: str) -> "ToolDispatchRequester":
        return cls("model", model_visible_call_id=model_visible_call_id)

    @classmethod
    def CodeCell(
        cls,
        *,
        runtime_cell_id: str,
        runtime_tool_call_id: str,
    ) -> "ToolDispatchRequester":
        return cls(
            "code_cell",
            runtime_cell_id=runtime_cell_id,
            runtime_tool_call_id=runtime_tool_call_id,
        )

@dataclass
class ToolDispatchPayload:
    type: str
    value: Any

    @classmethod
    def Function(cls, arguments: str) -> "ToolDispatchPayload":
        return cls("function", arguments)

    @classmethod
    def ToolSearch(cls, arguments: Any) -> "ToolDispatchPayload":
        return cls("tool_search", arguments)

    @classmethod
    def Custom(cls, input: str) -> "ToolDispatchPayload":
        return cls("custom", input)

    @classmethod
    def LocalShell(
        cls,
        *,
        command: list[str],
        workdir: str | None = None,
        timeout_ms: int | None = None,
        sandbox_permissions: Any = None,
        prefix_rule: list[str] | None = None,
        additional_permissions: Any = None,
        justification: str | None = None,
    ) -> "ToolDispatchPayload":
        return cls(
            "local_shell",
            {
                "command": command,
                "workdir": workdir,
                "timeout_ms": timeout_ms,
                "sandbox_permissions": sandbox_permissions,
                "prefix_rule": prefix_rule,
                "additional_permissions": additional_permissions,
                "justification": justification,
            },
        )

@dataclass
class ToolDispatchResult:
    type: str
    value: Any

    @classmethod
    def DirectResponse(cls, response_item: Any) -> "ToolDispatchResult":
        return cls("direct_response", response_item)

    @classmethod
    def CodeModeResponse(cls, value: Any) -> "ToolDispatchResult":
        return cls("code_mode_response", value)

def _suppresses_tool_dispatch_trace(invocation: ToolDispatchInvocation) -> bool:
    return (
        isinstance(invocation.payload, ToolDispatchPayload)
        and invocation.payload.type == "custom"
        and invocation.tool_namespace is None
        and invocation.tool_name == "exec"
    )

def _record_tool_dispatch_started(
    context: ToolDispatchTraceContext,
    invocation: ToolDispatchInvocation,
) -> None:
    payload = _tool_dispatch_payload_json(invocation.payload)
    request = {
        "tool_name": invocation.tool_name,
        "tool_namespace": invocation.tool_namespace,
        "payload": payload,
    }
    request_payload = context.writer.write_json_payload(RawPayloadKind.TOOL_INVOCATION, request)
    model_visible_call_id, code_mode_runtime_tool_id, requester = _tool_dispatch_requester_fields(
        invocation.requester
    )
    context.writer.append_with_context(
        RawTraceEventContext(
            thread_id=invocation.thread_id,
            codex_turn_id=invocation.codex_turn_id,
        ),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id=invocation.tool_call_id,
            model_visible_call_id=model_visible_call_id,
            code_mode_runtime_tool_id=code_mode_runtime_tool_id,
            requester=requester,
            kind=_dispatched_tool_kind(invocation.tool_name),
            summary=ToolCallSummary.Generic(
                label=_dispatched_tool_label(invocation.tool_name, invocation.tool_namespace),
                input_preview=_tool_dispatch_payload_preview(invocation.payload),
            ),
            invocation_payload=request_payload,
        ),
    )

def _append_tool_dispatch_ended(
    context: ToolDispatchTraceContext,
    status: ExecutionStatus,
    response: dict[str, Any],
) -> None:
    response_payload = context.writer.write_json_payload(RawPayloadKind.TOOL_RESULT, response)
    context.writer.append_with_context(
        RawTraceEventContext(
            thread_id=context.thread_id,
            codex_turn_id=context.codex_turn_id,
        ),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id=context.tool_call_id,
            status=status,
            result_payload=response_payload,
        ),
        )

def _code_cell_status_for_runtime_response(response: Any) -> CodeCellRuntimeStatus:
    response_type = response.get("type") if isinstance(response, dict) else getattr(response, "type", None)
    if response_type == "yielded":
        return CodeCellRuntimeStatus.YIELDED
    if response_type == "terminated":
        return CodeCellRuntimeStatus.TERMINATED
    if response_type == "result":
        error_text = response.get("error_text") if isinstance(response, dict) else getattr(response, "error_text", None)
        return CodeCellRuntimeStatus.FAILED if error_text is not None else CodeCellRuntimeStatus.COMPLETED
    return CodeCellRuntimeStatus.COMPLETED

def _code_cell_response_payload(writer: TraceWriter, response: Any) -> RawPayloadRef:
    response_payload = response.to_mapping() if hasattr(response, "to_mapping") else response
    return writer.write_json_payload(
        RawPayloadKind.TOOL_RESULT,
        {"response": response_payload},
    )

def _tool_dispatch_requester_fields(requester: Any) -> tuple[str | None, str | None, RawToolCallRequester]:
    requester_type = requester.type if isinstance(requester, ToolDispatchRequester) else getattr(requester, "type", None)
    if requester_type == "code_cell":
        runtime_cell_id = getattr(requester, "runtime_cell_id", None)
        runtime_tool_call_id = getattr(requester, "runtime_tool_call_id", None)
        return None, runtime_tool_call_id, RawToolCallRequester.CodeCell(runtime_cell_id or "")
    model_visible_call_id = getattr(requester, "model_visible_call_id", None)
    return model_visible_call_id, None, RawToolCallRequester.Model()

def _dispatched_tool_kind(tool_name: str) -> ToolCallKind:
    if tool_name in {"exec_command", "local_shell", "shell", "shell_command"}:
        return ToolCallKind.ExecCommand()
    if tool_name == "write_stdin":
        return ToolCallKind.WriteStdin()
    if tool_name == "apply_patch":
        return ToolCallKind.ApplyPatch()
    if tool_name in {"web_search", "web_search_preview"}:
        return ToolCallKind.Web()
    if tool_name in {"image_generation", "image_query"}:
        return ToolCallKind.ImageGeneration()
    if tool_name == "spawn_agent":
        return ToolCallKind.SpawnAgent()
    if tool_name == "send_message":
        return ToolCallKind.SendMessage()
    if tool_name == "followup_task":
        return ToolCallKind.AssignAgentTask()
    if tool_name == "wait_agent":
        return ToolCallKind.WaitAgent()
    if tool_name == "close_agent":
        return ToolCallKind.CloseAgent()
    return ToolCallKind.Other(name=tool_name)

def _dispatched_tool_label(tool_name: str, tool_namespace: str | None) -> str:
    if tool_namespace is None:
        return tool_name
    return f"{tool_namespace}.{tool_name}"

def _tool_dispatch_payload_json(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, ToolDispatchPayload):
        return {"type": "function", "arguments": str(payload)}
    if payload.type == "function":
        return {"type": "function", "arguments": payload.value}
    if payload.type == "tool_search":
        return {"type": "tool_search", "arguments": payload.value}
    if payload.type == "custom":
        return {"type": "custom", "input": payload.value}
    if payload.type == "local_shell" and isinstance(payload.value, dict):
        return {"type": "local_shell", **payload.value}
    return {"type": payload.type, "value": payload.value}

def _tool_dispatch_payload_preview(payload: Any) -> str:
    if not isinstance(payload, ToolDispatchPayload):
        return _truncate_preview(str(payload))
    if payload.type == "function":
        return _truncate_preview(str(payload.value))
    if payload.type == "tool_search":
        query = payload.value.get("query") if isinstance(payload.value, dict) else getattr(payload.value, "query", payload.value)
        return _truncate_preview(str(query))
    if payload.type == "custom":
        return _truncate_preview(str(payload.value))
    if payload.type == "local_shell" and isinstance(payload.value, dict):
        return _truncate_preview(" ".join(str(part) for part in payload.value.get("command", [])))
    return _truncate_preview(str(payload.value))

def _truncate_preview(value: str) -> str:
    max_preview_chars = 160
    if len(value) <= max_preview_chars:
        return value
    return value[:max_preview_chars] + "..."

from pycodex.rollout_trace.model import AgentThreadId, CodexTurnId, ToolCallId

from pycodex.rollout_trace.model.runtime import CodeCellRuntimeStatus, ToolCallKind, ToolCallSummary

from pycodex.rollout_trace.model.session import ExecutionStatus

from pycodex.rollout_trace.payload import RawPayloadKind, RawPayloadRef

from pycodex.rollout_trace.raw_event import RawToolCallRequester, RawTraceEventContext, RawTraceEventPayload

from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext
