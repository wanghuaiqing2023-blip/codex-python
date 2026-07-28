"""Rust-aligned owner for ``codex-rollout-trace::reducer.tool.agents``."""

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

@dataclass
class _PendingAgentInteractionEdge:
    edge_id: EdgeId
    kind: InteractionEdgeKind
    source: TraceAnchor
    target_thread_id: AgentThreadId
    message_content: str
    unresolved_spawn_thread_id: AgentThreadId | None
    started_at_unix_ms: int
    ended_at_unix_ms: int | None
    carried_raw_payload_ids: list[RawPayloadId]

def _start_agent_interaction_from_runtime(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    tool_call_id: ToolCallId,
    runtime_payload: RawPayloadRef,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    kind = _tool_kind_type(tool_call.kind)
    if kind == "close_agent":
        payload = _read_rollout_payload_json(rollout, runtime_payload)
        _upsert_close_agent_interaction(
            rollout,
            tool_call_id=tool_call_id,
            target_thread_id=str(payload.get("receiver_thread_id") or ""),
            ended_at_unix_ms=None,
        )
        return
    if kind not in {"send_message", "assign_agent_task"}:
        return
    payload = _read_rollout_payload_json(rollout, runtime_payload)
    _queue_message_agent_interaction(
        rollout,
        tool_call_id=tool_call_id,
        kind=_interaction_edge_kind_from_tool_kind(kind),
        target_thread_id=str(payload.get("receiver_thread_id") or ""),
        message_content=str(payload.get("prompt") or ""),
        ended_at_unix_ms=None,
    )

def _end_agent_interaction_from_runtime(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    tool_call_id: ToolCallId,
    runtime_payload: RawPayloadRef,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    kind = _tool_kind_type(tool_call.kind)
    payload = _read_rollout_payload_json(rollout, runtime_payload)
    if kind in {"send_message", "assign_agent_task"}:
        _queue_message_agent_interaction(
            rollout,
            tool_call_id=tool_call_id,
            kind=_interaction_edge_kind_from_tool_kind(kind),
            target_thread_id=str(payload.get("receiver_thread_id") or ""),
            message_content=str(payload.get("prompt") or ""),
            ended_at_unix_ms=wall_time_unix_ms,
        )
        return
    if kind == "close_agent":
        _upsert_close_agent_interaction(
            rollout,
            tool_call_id=tool_call_id,
            target_thread_id=str(payload.get("receiver_thread_id") or ""),
            ended_at_unix_ms=wall_time_unix_ms,
        )
        return
    if kind != "spawn_agent":
        return
    child_thread_id = payload.get("new_thread_id")
    if child_thread_id is None:
        return
    sender_thread_id = str(payload.get("sender_thread_id") or tool_call.thread_id)
    child_thread_id = str(child_thread_id)
    _queue_or_resolve_agent_interaction_edge(
        rollout,
        _PendingAgentInteractionEdge(
            edge_id=_spawn_edge_id(sender_thread_id, child_thread_id),
            kind=InteractionEdgeKind.SPAWN_AGENT,
            source=TraceAnchor.ToolCall(tool_call_id),
            target_thread_id=child_thread_id,
            message_content=str(payload.get("prompt") or ""),
            unresolved_spawn_thread_id=child_thread_id,
            started_at_unix_ms=tool_call.execution.started_at_unix_ms,
            ended_at_unix_ms=wall_time_unix_ms,
            carried_raw_payload_ids=_agent_tool_payload_ids(tool_call),
        ),
    )

def _upsert_close_agent_interaction(
    rollout: RolloutTrace,
    *,
    tool_call_id: ToolCallId,
    target_thread_id: AgentThreadId,
    ended_at_unix_ms: int | None,
) -> None:
    if not target_thread_id or target_thread_id not in rollout.threads:
        return
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    _upsert_interaction_edge(
        rollout,
        InteractionEdge(
            edge_id=f"edge:tool:{tool_call_id}",
            kind=InteractionEdgeKind.CLOSE_AGENT,
            source=TraceAnchor.ToolCall(tool_call_id),
            target=TraceAnchor.Thread(target_thread_id),
            started_at_unix_ms=tool_call.execution.started_at_unix_ms,
            ended_at_unix_ms=ended_at_unix_ms,
            carried_item_ids=[],
            carried_raw_payload_ids=_agent_tool_payload_ids(tool_call),
        ),
    )

def _queue_message_agent_interaction(
    rollout: RolloutTrace,
    *,
    tool_call_id: ToolCallId,
    kind: InteractionEdgeKind,
    target_thread_id: AgentThreadId,
    message_content: str,
    ended_at_unix_ms: int | None,
) -> None:
    if not target_thread_id:
        return
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    _queue_or_resolve_agent_interaction_edge(
        rollout,
        _PendingAgentInteractionEdge(
            edge_id=f"edge:tool:{tool_call_id}",
            kind=kind,
            source=TraceAnchor.ToolCall(tool_call_id),
            target_thread_id=target_thread_id,
            message_content=message_content,
            unresolved_spawn_thread_id=None,
            started_at_unix_ms=tool_call.execution.started_at_unix_ms,
            ended_at_unix_ms=ended_at_unix_ms,
            carried_raw_payload_ids=_agent_tool_payload_ids(tool_call),
        ),
    )

def _queue_or_resolve_agent_interaction_edge(
    rollout: RolloutTrace,
    pending: _PendingAgentInteractionEdge,
) -> None:
    item_id = _find_unlinked_inter_agent_message_item(
        rollout,
        pending.target_thread_id,
        pending.message_content,
    )
    if item_id is not None:
        _upsert_agent_interaction_edge_for_item(rollout, pending, item_id)
        return
    for existing in rollout.pending_agent_interaction_edges:
        if existing.edge_id != pending.edge_id:
            continue
        if (
            existing.kind != pending.kind
            or existing.source != pending.source
            or existing.target_thread_id != pending.target_thread_id
            or existing.message_content != pending.message_content
            or existing.unresolved_spawn_thread_id != pending.unresolved_spawn_thread_id
        ):
            raise ValueError(f"pending interaction edge {pending.edge_id} was observed with conflicting delivery data")
        existing.started_at_unix_ms = min(existing.started_at_unix_ms, pending.started_at_unix_ms)
        if existing.ended_at_unix_ms is None or pending.ended_at_unix_ms is None:
            existing.ended_at_unix_ms = existing.ended_at_unix_ms or pending.ended_at_unix_ms
        else:
            existing.ended_at_unix_ms = max(existing.ended_at_unix_ms, pending.ended_at_unix_ms)
        extend_unique(existing.carried_raw_payload_ids, pending.carried_raw_payload_ids)
        return
    rollout.pending_agent_interaction_edges.append(pending)

def _queue_agent_result_interaction_edge(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    edge_id: EdgeId,
    child_thread_id: AgentThreadId,
    child_codex_turn_id: CodexTurnId,
    parent_thread_id: AgentThreadId,
    message: str,
    carried_payload: RawPayloadRef | None,
) -> None:
    source_item_id = _latest_assistant_message_item_for_turn(
        rollout,
        child_thread_id,
        child_codex_turn_id,
    )
    source = (
        TraceAnchor.ConversationItem(source_item_id)
        if source_item_id is not None
        else TraceAnchor.Thread(child_thread_id)
    )
    _queue_or_resolve_agent_interaction_edge(
        rollout,
        _PendingAgentInteractionEdge(
            edge_id=edge_id,
            kind=InteractionEdgeKind.AGENT_RESULT,
            source=source,
            target_thread_id=parent_thread_id,
            message_content=message,
            unresolved_spawn_thread_id=None,
            started_at_unix_ms=wall_time_unix_ms,
            ended_at_unix_ms=wall_time_unix_ms,
            carried_raw_payload_ids=[carried_payload.raw_payload_id] if carried_payload else [],
        ),
    )

def _latest_assistant_message_item_for_turn(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    codex_turn_id: CodexTurnId,
) -> ConversationItemId | None:
    candidates = [
        item
        for item in rollout.conversation_items.values()
        if item.thread_id == thread_id
        and item.codex_turn_id == codex_turn_id
        and item.role == ConversationRole.ASSISTANT
        and item.kind == ConversationItemKind.MESSAGE
    ]
    if not candidates:
        return None
    return max(
        enumerate(candidates),
        key=lambda indexed: (indexed[1].first_seen_at_unix_ms, indexed[0]),
    )[1].item_id

def _attach_agent_interaction_tool_result(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    result_payload: RawPayloadRef | None,
) -> None:
    if result_payload is None:
        return
    for edge in rollout.interaction_edges.values():
        if edge.source == TraceAnchor.ToolCall(tool_call_id):
            push_unique(edge.carried_raw_payload_ids, result_payload.raw_payload_id)
            return
    for pending in rollout.pending_agent_interaction_edges:
        if pending.source == TraceAnchor.ToolCall(tool_call_id):
            push_unique(pending.carried_raw_payload_ids, result_payload.raw_payload_id)

def _resolve_pending_agent_edges_for_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
) -> None:
    message = _inter_agent_message_item(rollout, item_id)
    if message is None:
        return
    thread_id, message_content = message
    for index, pending in enumerate(list(rollout.pending_agent_interaction_edges)):
        if pending.target_thread_id == thread_id and pending.message_content == message_content:
            pending = rollout.pending_agent_interaction_edges.pop(index)
            _upsert_agent_interaction_edge_for_item(rollout, pending, item_id)
            return

def _upsert_agent_interaction_edge_for_item(
    rollout: RolloutTrace,
    pending: _PendingAgentInteractionEdge,
    target_item_id: ConversationItemId,
) -> None:
    _upsert_interaction_edge(
        rollout,
        InteractionEdge(
            edge_id=pending.edge_id,
            kind=pending.kind,
            source=pending.source,
            target=TraceAnchor.ConversationItem(target_item_id),
            started_at_unix_ms=pending.started_at_unix_ms,
            ended_at_unix_ms=pending.ended_at_unix_ms,
            carried_item_ids=[target_item_id],
            carried_raw_payload_ids=pending.carried_raw_payload_ids,
        ),
    )

def _find_unlinked_inter_agent_message_item(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    message_content: str,
) -> ConversationItemId | None:
    thread = rollout.threads.get(thread_id)
    if thread is None:
        return None
    for item_id in thread.conversation_item_ids:
        if _is_interaction_edge_target_item(rollout, item_id):
            continue
        message = _inter_agent_message_item(rollout, item_id)
        if message is not None and message[1] == message_content:
            return item_id
    return None

def _inter_agent_message_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
) -> tuple[AgentThreadId, str] | None:
    item = rollout.conversation_items.get(item_id)
    if item is None or item.role != ConversationRole.ASSISTANT or item.kind != ConversationItemKind.MESSAGE:
        return None
    if len(item.body.parts) != 1 or item.body.parts[0].type != "text":
        return None
    text = item.body.parts[0].text
    if text is None:
        return None
    try:
        communication = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(communication, dict):
        return None
    recipient = communication.get("recipient")
    content = communication.get("content")
    if not isinstance(recipient, str) or not isinstance(content, str):
        return None
    thread = rollout.threads.get(item.thread_id)
    if thread is None or recipient != thread.agent_path:
        return None
    return item.thread_id, content

def _is_interaction_edge_target_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
) -> bool:
    return any(edge.target == TraceAnchor.ConversationItem(item_id) for edge in rollout.interaction_edges.values())

def _resolve_pending_spawn_edge_fallbacks(rollout: RolloutTrace) -> None:
    pending_edges = list(rollout.pending_agent_interaction_edges)
    rollout.pending_agent_interaction_edges.clear()
    for pending in pending_edges:
        child_thread_id = pending.unresolved_spawn_thread_id
        if pending.kind != InteractionEdgeKind.SPAWN_AGENT or child_thread_id is None:
            continue
        if child_thread_id not in rollout.threads:
            continue
        _upsert_interaction_edge(
            rollout,
            InteractionEdge(
                edge_id=pending.edge_id,
                kind=pending.kind,
                source=pending.source,
                target=TraceAnchor.Thread(child_thread_id),
                started_at_unix_ms=pending.started_at_unix_ms,
                ended_at_unix_ms=pending.ended_at_unix_ms,
                carried_item_ids=[],
                carried_raw_payload_ids=pending.carried_raw_payload_ids,
            ),
        )

def _interaction_edge_kind_from_tool_kind(kind: str | None) -> InteractionEdgeKind:
    if kind == "assign_agent_task":
        return InteractionEdgeKind.ASSIGN_AGENT_TASK
    if kind == "send_message":
        return InteractionEdgeKind.SEND_MESSAGE
    if kind == "close_agent":
        return InteractionEdgeKind.CLOSE_AGENT
    if kind == "spawn_agent":
        return InteractionEdgeKind.SPAWN_AGENT
    raise ValueError(f"tool kind {kind!r} is not an agent interaction edge kind")

def _upsert_interaction_edge(rollout: RolloutTrace, edge: InteractionEdge) -> None:
    existing = rollout.interaction_edges.get(edge.edge_id)
    if existing is None:
        rollout.interaction_edges[edge.edge_id] = edge
        return
    if existing.kind != edge.kind or existing.source != edge.source or existing.target != edge.target:
        raise ValueError(f"interaction edge {edge.edge_id} was observed with conflicting endpoints")
    existing.started_at_unix_ms = min(existing.started_at_unix_ms, edge.started_at_unix_ms)
    if existing.ended_at_unix_ms is None or edge.ended_at_unix_ms is None:
        existing.ended_at_unix_ms = existing.ended_at_unix_ms or edge.ended_at_unix_ms
    else:
        existing.ended_at_unix_ms = max(existing.ended_at_unix_ms, edge.ended_at_unix_ms)
    extend_unique(existing.carried_item_ids, edge.carried_item_ids)
    extend_unique(existing.carried_raw_payload_ids, edge.carried_raw_payload_ids)

def _agent_tool_payload_ids(tool_call: ToolCall) -> list[RawPayloadId]:
    payload_ids: list[RawPayloadId] = []
    if tool_call.raw_invocation_payload_id is not None:
        push_unique(payload_ids, tool_call.raw_invocation_payload_id)
    for payload_id in tool_call.raw_runtime_payload_ids:
        push_unique(payload_ids, payload_id)
    if tool_call.raw_result_payload_id is not None:
        push_unique(payload_ids, tool_call.raw_result_payload_id)
    return payload_ids

def _tool_kind_type(kind: Any) -> str | None:
    if isinstance(kind, ToolCallKind):
        return kind.type
    if isinstance(kind, dict):
        value = kind.get("type")
        return value if isinstance(value, str) else None
    return kind if isinstance(kind, str) else None

def _tool_call_kind_from_value(value: Any) -> ToolCallKind:
    if isinstance(value, ToolCallKind):
        return value
    if isinstance(value, str):
        data: dict[str, Any] = {"type": value}
    elif isinstance(value, dict):
        data = value
    else:
        return ToolCallKind.Other(name=str(value))
    kind_type = str(data.get("type") or "")
    if kind_type == "exec_command":
        return ToolCallKind.ExecCommand()
    if kind_type == "write_stdin":
        return ToolCallKind.WriteStdin()
    if kind_type == "apply_patch":
        return ToolCallKind.ApplyPatch()
    if kind_type == "mcp":
        return ToolCallKind.Mcp(server=str(data.get("server") or ""), tool=str(data.get("tool") or ""))
    if kind_type == "web":
        return ToolCallKind.Web()
    if kind_type == "image_generation":
        return ToolCallKind.ImageGeneration()
    if kind_type == "spawn_agent":
        return ToolCallKind.SpawnAgent()
    if kind_type == "assign_agent_task":
        return ToolCallKind.AssignAgentTask()
    if kind_type == "send_message":
        return ToolCallKind.SendMessage()
    if kind_type == "wait_agent":
        return ToolCallKind.WaitAgent()
    if kind_type == "close_agent":
        return ToolCallKind.CloseAgent()
    return ToolCallKind.Other(name=str(data.get("name") or kind_type or value))

def _tool_call_summary_from_value(value: Any) -> ToolCallSummary:
    if isinstance(value, ToolCallSummary):
        return value
    if not isinstance(value, dict):
        return ToolCallSummary.Generic(label=str(value) if value is not None else "")
    summary_type = str(value.get("type") or "")
    if summary_type == "terminal":
        return ToolCallSummary.Terminal(operation_id=str(value.get("operation_id") or ""))
    if summary_type == "agent":
        return ToolCallSummary.Agent(
            target_agent_path=str(value.get("target_agent_path") or ""),
            task_name=value.get("task_name") if isinstance(value.get("task_name"), str) else None,
            message_preview=str(value.get("message_preview") or ""),
        )
    if summary_type == "wait_agent":
        target_agent_path = value.get("target_agent_path")
        timeout_ms = value.get("timeout_ms")
        return ToolCallSummary.WaitAgent(
            target_agent_path=target_agent_path if isinstance(target_agent_path, str) else None,
            timeout_ms=timeout_ms if isinstance(timeout_ms, int) else None,
        )
    return ToolCallSummary.Generic(
        label=str(value.get("label") or ""),
        input_preview=value.get("input_preview") if isinstance(value.get("input_preview"), str) else None,
        output_preview=value.get("output_preview") if isinstance(value.get("output_preview"), str) else None,
    )

def extend_unique(items: list[str], new_items: list[str]) -> None:
    for item in new_items:
        push_unique(items, item)

from pycodex.rollout_trace.model import AgentThreadId, CodexTurnId, ConversationItemId, EdgeId, RolloutTrace, ToolCallId

from pycodex.rollout_trace.model.conversation import ConversationItemKind, ConversationRole

from pycodex.rollout_trace.model.runtime import InteractionEdge, InteractionEdgeKind, ToolCall, ToolCallKind, ToolCallSummary, TraceAnchor

from pycodex.rollout_trace.payload import RawPayloadId, RawPayloadRef

from pycodex.rollout_trace.reducer.code_cell import _read_rollout_payload_json, push_unique

from pycodex.rollout_trace.reducer.thread import _spawn_edge_id
