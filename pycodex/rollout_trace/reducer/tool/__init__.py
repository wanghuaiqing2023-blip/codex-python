"""Rust-aligned owner for ``codex-rollout-trace::reducer.tool``."""

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

def start_tool_call(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    payload: dict[str, Any],
) -> None:
    tool_call_id = payload["tool_call_id"]
    if tool_call_id in rollout.tool_calls:
        raise ValueError(f"duplicate tool call start for {tool_call_id}")
    model_visible_call_id = _optional_str(payload.get("model_visible_call_id"))
    if model_visible_call_id is not None and _single_tool_for_model_visible_call(rollout, model_visible_call_id) is not None:
        raise ValueError(f"duplicate tool call for model-visible call id {model_visible_call_id}")
    thread_id = _tool_thread_id(rollout, event_thread_id, event_codex_turn_id)
    _validate_tool_turn(rollout, thread_id, event_codex_turn_id)
    requester = _reduce_tool_call_requester(rollout, thread_id, payload.get("requester"))
    invocation_payload = _payload_ref_from_json(payload.get("invocation_payload"))
    kind = _tool_call_kind_from_value(payload.get("kind"))
    summary = _tool_call_summary_from_value(payload.get("summary"))
    rollout.tool_calls[tool_call_id] = ToolCall(
        tool_call_id=tool_call_id,
        mcp_call_id=None,
        model_visible_call_id=model_visible_call_id,
        code_mode_runtime_tool_id=_optional_str(payload.get("code_mode_runtime_tool_id")),
        thread_id=thread_id,
        started_by_codex_turn_id=event_codex_turn_id,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
        requester=requester,
        kind=kind,
        model_visible_call_item_ids=[],
        model_visible_output_item_ids=[],
        summary=summary,
        raw_invocation_payload_id=invocation_payload.raw_payload_id if invocation_payload else None,
    )
    terminal_operation_id = _start_terminal_operation_from_invocation(
        rollout,
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=thread_id,
        tool_call_id=tool_call_id,
        kind=kind,
        invocation_payload=invocation_payload,
    )
    if terminal_operation_id is not None:
        tool_call = rollout.tool_calls[tool_call_id]
        tool_call.terminal_operation_id = terminal_operation_id
        tool_call.summary = ToolCallSummary.Terminal(operation_id=terminal_operation_id)
    _link_tool_call_to_code_cell(rollout, tool_call_id, requester)
    _link_wait_tool_call_from_request_payload(
        rollout,
        thread_id,
        tool_call_id,
        invocation_payload,
    )
    if model_visible_call_id is not None:
        for item in list(rollout.conversation_items.values()):
            if item.thread_id == thread_id and item.call_id == model_visible_call_id:
                _attach_model_visible_tool_item(rollout, item.item_id, item.call_id, item.kind)

def _replay_end_tool_call(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    tool_call_id: str,
    status: ExecutionStatus,
    result_payload: RawPayloadRef | None,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool call end referenced unknown call {tool_call_id}")
    tool_call.execution = ExecutionWindow(
        started_at_unix_ms=tool_call.execution.started_at_unix_ms,
        started_seq=tool_call.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=status,
    )
    tool_call.raw_result_payload_id = result_payload.raw_payload_id if result_payload else None
    if tool_call.terminal_operation_id is not None and not tool_call.raw_runtime_payload_ids:
        _end_terminal_operation(
            rollout,
            seq=seq,
            wall_time_unix_ms=wall_time_unix_ms,
            thread_id=tool_call.thread_id,
            operation_id=tool_call.terminal_operation_id,
            status=status,
            response_payload=result_payload,
        )
    _attach_agent_interaction_tool_result(rollout, tool_call_id, result_payload)

def _assign_mcp_tool_call_correlation(
    rollout: RolloutTrace,
    *,
    tool_call_id: ToolCallId,
    mcp_call_id: McpCallId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"MCP correlation referenced unknown tool call {tool_call_id}")
    if tool_call.mcp_call_id is not None:
        raise ValueError(f"duplicate MCP correlation for tool call {tool_call_id}")
    tool_call.mcp_call_id = mcp_call_id

def _replay_start_tool_runtime_observation(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    tool_call_id: str,
    runtime_payload: RawPayloadRef | None,
) -> None:
    if runtime_payload is None:
        raise ValueError(f"tool runtime start {tool_call_id} missing runtime payload")
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool runtime start referenced unknown call {tool_call_id}")
    push_unique(tool_call.raw_runtime_payload_ids, runtime_payload.raw_payload_id)
    if tool_call.terminal_operation_id is not None and terminal_operation_kind(tool_call.kind) is not None:
        raise ValueError(f"tool runtime start would create a second terminal operation for {tool_call_id}")
    terminal_operation_id = _start_terminal_operation_from_runtime(
        rollout,
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=tool_call.thread_id,
        tool_call_id=tool_call_id,
        kind=tool_call.kind,
        runtime_payload=runtime_payload,
    )
    if terminal_operation_id is not None:
        tool_call.terminal_operation_id = terminal_operation_id
        tool_call.summary = ToolCallSummary.Terminal(operation_id=terminal_operation_id)
        _sync_terminal_model_observation(rollout, tool_call_id)
    _start_agent_interaction_from_runtime(
        rollout,
        wall_time_unix_ms=wall_time_unix_ms,
        tool_call_id=tool_call_id,
        runtime_payload=runtime_payload,
    )

def _replay_end_tool_runtime_observation(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    tool_call_id: str,
    status: ExecutionStatus,
    runtime_payload: RawPayloadRef | None,
) -> None:
    if runtime_payload is None:
        raise ValueError(f"tool runtime end {tool_call_id} missing runtime payload")
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool runtime end referenced unknown call {tool_call_id}")
    push_unique(tool_call.raw_runtime_payload_ids, runtime_payload.raw_payload_id)
    if tool_call.terminal_operation_id is not None:
        _end_terminal_operation(
            rollout,
            seq=seq,
            wall_time_unix_ms=wall_time_unix_ms,
            thread_id=tool_call.thread_id,
            operation_id=tool_call.terminal_operation_id,
            status=status,
            response_payload=runtime_payload,
        )
    _end_agent_interaction_from_runtime(
        rollout,
        wall_time_unix_ms=wall_time_unix_ms,
        tool_call_id=tool_call_id,
        runtime_payload=runtime_payload,
    )

def _tool_thread_id(
    rollout: RolloutTrace,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
) -> str:
    if event_thread_id is not None:
        return event_thread_id
    if event_codex_turn_id is None:
        raise ValueError("tool call start did not include thread or Codex turn context")
    turn = rollout.codex_turns.get(event_codex_turn_id)
    if turn is None:
        raise ValueError(f"tool call start referenced unknown Codex turn {event_codex_turn_id}")
    return turn.thread_id

def _validate_tool_turn(
    rollout: RolloutTrace,
    thread_id: str,
    event_codex_turn_id: str | None,
) -> None:
    if thread_id not in rollout.threads:
        raise ValueError(f"tool call start referenced unknown thread {thread_id}")
    if event_codex_turn_id is None:
        return
    turn = rollout.codex_turns.get(event_codex_turn_id)
    if turn is None:
        raise ValueError(f"tool call start referenced unknown Codex turn {event_codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"tool call start used thread {thread_id}, but Codex turn {event_codex_turn_id} belongs to {turn.thread_id}"
        )

def _reduce_tool_call_requester(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    requester: Any,
) -> Any:
    requester_type = requester.get("type") if isinstance(requester, dict) else getattr(requester, "type", None)
    if requester_type != "code_cell":
        return ToolCallRequester.Model()
    runtime_cell_id = (
        requester.get("runtime_cell_id")
        if isinstance(requester, dict)
        else getattr(requester, "runtime_cell_id", None)
    )
    if not isinstance(runtime_cell_id, str):
        raise ValueError("code-mode nested tool requester did not include runtime_cell_id")
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        raise ValueError(
            f"code-mode nested tool referenced unknown runtime cell {runtime_cell_id} "
            f"in thread {thread_id}"
        )
    return ToolCallRequester.CodeCell(code_cell_id)

def _link_tool_call_to_code_cell(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    requester: Any,
) -> None:
    requester_type = requester.get("type") if isinstance(requester, dict) else getattr(requester, "type", None)
    if requester_type != "code_cell":
        return
    code_cell_id = requester.get("code_cell_id") if isinstance(requester, dict) else getattr(requester, "code_cell_id", None)
    if not isinstance(code_cell_id, str):
        return
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        return
    if tool_call_id not in cell.nested_tool_call_ids:
        cell.nested_tool_call_ids.append(tool_call_id)

def _link_wait_tool_call_from_request_payload(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    tool_call_id: ToolCallId,
    request_payload: RawPayloadRef | None,
) -> None:
    if request_payload is None:
        return
    payload = _read_rollout_payload_json(rollout, request_payload)
    if payload.get("tool_name") != "wait":
        return
    arguments = payload.get("payload", {}).get("arguments") if isinstance(payload.get("payload"), dict) else None
    if not isinstance(arguments, str):
        raise ValueError(f"wait tool request payload {request_payload.raw_payload_id} did not contain function arguments")
    try:
        decoded = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"wait tool request payload {request_payload.raw_payload_id} had invalid JSON arguments") from exc
    runtime_cell_id = decoded.get("cell_id") if isinstance(decoded, dict) else None
    if not isinstance(runtime_cell_id, str):
        raise ValueError(f"wait tool request payload {request_payload.raw_payload_id} did not contain cell_id")
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        return
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        return
    if tool_call_id not in cell.wait_tool_call_ids:
        cell.wait_tool_call_ids.append(tool_call_id)

def _single_tool_for_model_visible_call(
    rollout: RolloutTrace,
    model_visible_call_id: str,
) -> ToolCallId | None:
    matches = [
        tool.tool_call_id
        for tool in rollout.tool_calls.values()
        if tool.model_visible_call_id == model_visible_call_id
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple tool calls matched model-visible call id {model_visible_call_id}")
    return matches[0] if matches else None

def _attach_model_visible_tool_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
    call_id: str | None,
    kind: ConversationItemKind,
) -> None:
    if call_id is None:
        return
    if kind not in {ConversationItemKind.FUNCTION_CALL, ConversationItemKind.FUNCTION_CALL_OUTPUT}:
        return
    tool_call_id = _single_tool_for_model_visible_call(rollout, call_id)
    if tool_call_id is None:
        return
    if kind == ConversationItemKind.FUNCTION_CALL:
        _add_tool_call_item(rollout, tool_call_id, item_id)
        _link_tool_to_inference_response(rollout, tool_call_id)
    else:
        _add_tool_output_item(rollout, tool_call_id, item_id)
    _sync_terminal_model_observation(rollout, tool_call_id)

def _add_tool_call_item(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    item_id: ConversationItemId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool call {tool_call_id} disappeared during conversation linking")
    if item_id not in tool_call.model_visible_call_item_ids:
        tool_call.model_visible_call_item_ids.append(item_id)

def _add_tool_output_item(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    item_id: ConversationItemId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool call {tool_call_id} disappeared during output linking")
    if item_id not in tool_call.model_visible_output_item_ids:
        tool_call.model_visible_output_item_ids.append(item_id)
    item = rollout.conversation_items.get(item_id)
    if item is None:
        raise ValueError(f"conversation item {item_id} disappeared during output linking")
    producer = ProducerRef.Tool(tool_call_id)
    if producer not in item.produced_by:
        item.produced_by.append(producer)

def _link_tool_to_inference_response(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None or not tool_call.model_visible_call_item_ids:
        return
    call_item_ids = set(tool_call.model_visible_call_item_ids)
    for inference in rollout.inference_calls.values():
        if call_item_ids.intersection(inference.response_item_ids) and tool_call_id not in inference.tool_call_ids_started_by_response:
            inference.tool_call_ids_started_by_response.append(tool_call_id)

from pycodex.rollout_trace.model import AgentThreadId, ConversationItemId, McpCallId, RolloutTrace, ToolCallId

from pycodex.rollout_trace.model.conversation import ConversationItemKind, ProducerRef

from pycodex.rollout_trace.model.runtime import ToolCall, ToolCallRequester, ToolCallSummary

from pycodex.rollout_trace.model.session import ExecutionStatus, ExecutionWindow

from pycodex.rollout_trace.payload import RawPayloadRef

from pycodex.rollout_trace.reducer import _payload_ref_from_json

from pycodex.rollout_trace.reducer.code_cell import _code_cell_id_for_runtime_cell_id_if_known, _read_rollout_payload_json, push_unique

from pycodex.rollout_trace.reducer.conversation.normalize import _optional_str

from pycodex.rollout_trace.reducer.tool.agents import _attach_agent_interaction_tool_result, _end_agent_interaction_from_runtime, _start_agent_interaction_from_runtime, _tool_call_kind_from_value, _tool_call_summary_from_value

from pycodex.rollout_trace.reducer.tool.terminal import _end_terminal_operation, _start_terminal_operation_from_invocation, _start_terminal_operation_from_runtime, _sync_terminal_model_observation, terminal_operation_kind
