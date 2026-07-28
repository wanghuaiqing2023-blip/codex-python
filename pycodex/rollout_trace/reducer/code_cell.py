"""Rust-aligned owner for ``codex-rollout-trace::reducer.code_cell``."""

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

@dataclass(frozen=True)
class _PendingCodeCellStart:
    seq: RawEventSeq
    wall_time_unix_ms: int
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId | None
    code_cell_id: CodeCellId
    runtime_cell_id: str
    model_visible_call_id: ModelVisibleCallId
    source_js: str

@dataclass(frozen=True)
class _PendingCodeCellLifecycleEvent:
    seq: RawEventSeq
    wall_time_unix_ms: int
    type: str
    runtime_cell_id: str | None = None
    status: CodeCellRuntimeStatus | None = None

def push_unique(items: list[str], item_id: str) -> None:
    if item_id not in items:
        items.append(item_id)

def _replay_start_or_queue_code_cell(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    runtime_cell_id: str,
    model_visible_call_id: str,
    source_js: str,
) -> None:
    thread_id = _code_cell_event_thread_id(
        rollout,
        event_thread_id,
        event_codex_turn_id,
        runtime_cell_id,
        "code cell start",
    )
    code_cell_id = _reduced_code_cell_id_for_model_visible_call(model_visible_call_id)
    pending = _PendingCodeCellStart(
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=thread_id,
        codex_turn_id=event_codex_turn_id,
        code_cell_id=code_cell_id,
        runtime_cell_id=runtime_cell_id,
        model_visible_call_id=model_visible_call_id,
        source_js=source_js,
    )
    if _source_item_id_for_pending_code_cell(rollout, pending) is None:
        if code_cell_id in rollout.code_cells or code_cell_id in rollout.pending_code_cell_starts:
            raise ValueError(f"duplicate code cell start for {code_cell_id}")
        rollout.pending_code_cell_starts[code_cell_id] = pending
        return
    _start_code_cell(rollout, pending)

def _flush_pending_code_cell_starts(rollout: RolloutTrace) -> None:
    ready_ids = [
        code_cell_id
        for code_cell_id, pending in rollout.pending_code_cell_starts.items()
        if _source_item_id_for_pending_code_cell(rollout, pending) is not None
    ]
    for code_cell_id in ready_ids:
        pending = rollout.pending_code_cell_starts.pop(code_cell_id)
        _start_code_cell(rollout, pending)

def _start_code_cell(rollout: RolloutTrace, pending: _PendingCodeCellStart) -> None:
    if pending.code_cell_id in rollout.code_cells:
        raise ValueError(f"duplicate code cell start for {pending.code_cell_id}")
    if pending.codex_turn_id is None:
        raise ValueError(f"code cell start {pending.code_cell_id} did not include a Codex turn id")
    _validate_code_cell_turn(rollout, pending.thread_id, pending.codex_turn_id)
    source_item_id = _source_item_id_for_code_cell_start(
        rollout,
        pending.thread_id,
        pending.code_cell_id,
        pending.model_visible_call_id,
    )
    output_item_ids = _model_visible_code_cell_item_ids(
        rollout,
        pending.thread_id,
        pending.model_visible_call_id,
        ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT,
    )
    rollout.code_cells[pending.code_cell_id] = CodeCell(
        code_cell_id=pending.code_cell_id,
        model_visible_call_id=pending.model_visible_call_id,
        thread_id=pending.thread_id,
        codex_turn_id=pending.codex_turn_id,
        source_item_id=source_item_id,
        output_item_ids=list(output_item_ids),
        runtime_cell_id=pending.runtime_cell_id,
        execution=ExecutionWindow(
            started_at_unix_ms=pending.wall_time_unix_ms,
            started_seq=pending.seq,
            status=ExecutionStatus.RUNNING,
        ),
        runtime_status=CodeCellRuntimeStatus.STARTING,
        initial_response_at_unix_ms=None,
        initial_response_seq=None,
        yielded_at_unix_ms=None,
        yielded_seq=None,
        source_js=pending.source_js,
    )
    _record_runtime_code_cell_id(
        rollout,
        pending.thread_id,
        pending.runtime_cell_id,
        pending.code_cell_id,
    )
    for item_id in output_item_ids:
        _add_code_cell_output_item(rollout, pending.code_cell_id, item_id)
    _flush_pending_code_cell_lifecycle_events(rollout, pending.code_cell_id)

def _replay_record_or_queue_code_cell_initial_response(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    runtime_cell_id: str,
    status: CodeCellRuntimeStatus,
) -> None:
    thread_id = _code_cell_event_thread_id(
        rollout,
        event_thread_id,
        event_codex_turn_id,
        runtime_cell_id,
        "code cell initial response",
    )
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        code_cell_id = _pending_code_cell_id_for_runtime_cell_id(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        raise ValueError(f"code cell initial response referenced unknown cell {runtime_cell_id}")
    if code_cell_id not in rollout.code_cells:
        if code_cell_id in rollout.pending_code_cell_starts:
            _queue_code_cell_lifecycle_event(
                rollout,
                code_cell_id,
                _PendingCodeCellLifecycleEvent(
                    seq=seq,
                    wall_time_unix_ms=wall_time_unix_ms,
                    type="initial_response",
                    runtime_cell_id=runtime_cell_id,
                    status=status,
                ),
            )
            return
        raise ValueError(f"code cell initial response referenced unknown cell {code_cell_id}")
    _record_code_cell_initial_response(
        rollout,
        seq,
        wall_time_unix_ms,
        code_cell_id,
        runtime_cell_id,
        status,
    )

def _record_code_cell_initial_response(
    rollout: RolloutTrace,
    seq: int,
    wall_time_unix_ms: int,
    code_cell_id: CodeCellId,
    runtime_cell_id: str,
    status: CodeCellRuntimeStatus,
) -> None:
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        raise ValueError(f"code cell initial response referenced unknown cell {code_cell_id}")
    cell.runtime_cell_id = runtime_cell_id
    if cell.initial_response_at_unix_ms is None:
        cell.initial_response_at_unix_ms = wall_time_unix_ms
        cell.initial_response_seq = seq
    if status == CodeCellRuntimeStatus.YIELDED:
        cell.yielded_at_unix_ms = wall_time_unix_ms
        cell.yielded_seq = seq
    cell.runtime_status = status

def _replay_end_or_queue_code_cell(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    runtime_cell_id: str,
    status: CodeCellRuntimeStatus,
) -> None:
    thread_id = _code_cell_event_thread_id(
        rollout,
        event_thread_id,
        event_codex_turn_id,
        runtime_cell_id,
        "code cell end",
    )
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        code_cell_id = _pending_code_cell_id_for_runtime_cell_id(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        raise ValueError(f"code cell end referenced unknown cell {runtime_cell_id}")
    if code_cell_id not in rollout.code_cells:
        if code_cell_id in rollout.pending_code_cell_starts:
            _queue_code_cell_lifecycle_event(
                rollout,
                code_cell_id,
                _PendingCodeCellLifecycleEvent(
                    seq=seq,
                    wall_time_unix_ms=wall_time_unix_ms,
                    type="ended",
                    status=status,
                ),
            )
            return
        raise ValueError(f"code cell end referenced unknown cell {code_cell_id}")
    _end_code_cell(rollout, seq, wall_time_unix_ms, code_cell_id, status)

def _end_code_cell(
    rollout: RolloutTrace,
    seq: int,
    wall_time_unix_ms: int,
    code_cell_id: CodeCellId,
    status: CodeCellRuntimeStatus,
) -> None:
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        raise ValueError(f"code cell end referenced unknown cell {code_cell_id}")
    if cell.initial_response_at_unix_ms is None:
        cell.initial_response_at_unix_ms = wall_time_unix_ms
        cell.initial_response_seq = seq
    cell.execution = ExecutionWindow(
        started_at_unix_ms=cell.execution.started_at_unix_ms,
        started_seq=cell.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=_execution_status_for_code_cell(status),
    )
    cell.runtime_status = status

def _terminate_running_code_cells_for_turn_end(
    rollout: RolloutTrace,
    seq: int,
    wall_time_unix_ms: int,
    codex_turn_id: str,
    turn_status: ExecutionStatus,
) -> None:
    if turn_status in {ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED}:
        return
    runtime_status = (
        CodeCellRuntimeStatus.FAILED
        if turn_status == ExecutionStatus.FAILED
        else CodeCellRuntimeStatus.TERMINATED
    )
    for code_cell_id, cell in list(rollout.code_cells.items()):
        if cell.codex_turn_id == codex_turn_id and cell.execution.status == ExecutionStatus.RUNNING:
            _end_code_cell(rollout, seq, wall_time_unix_ms, code_cell_id, runtime_status)

def _queue_code_cell_lifecycle_event(
    rollout: RolloutTrace,
    code_cell_id: CodeCellId,
    event: _PendingCodeCellLifecycleEvent,
) -> None:
    events = rollout.pending_code_cell_lifecycle_events.setdefault(code_cell_id, [])
    events.append(event)
    events.sort(key=lambda queued: queued.seq)

def _flush_pending_code_cell_lifecycle_events(
    rollout: RolloutTrace,
    code_cell_id: CodeCellId,
) -> None:
    for event in rollout.pending_code_cell_lifecycle_events.pop(code_cell_id, []):
        if event.type == "initial_response":
            if event.runtime_cell_id is None or event.status is None:
                raise ValueError(f"code cell {code_cell_id} had incomplete pending initial response")
            _record_code_cell_initial_response(
                rollout,
                event.seq,
                event.wall_time_unix_ms,
                code_cell_id,
                event.runtime_cell_id,
                event.status,
            )
        elif event.type == "ended":
            if event.status is None:
                raise ValueError(f"code cell {code_cell_id} had incomplete pending end")
            _end_code_cell(rollout, event.seq, event.wall_time_unix_ms, code_cell_id, event.status)

def _attach_model_visible_code_cell_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
    call_id: str | None,
    kind: ConversationItemKind,
) -> None:
    if call_id is None or kind != ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT:
        return
    code_cell_id = _reduced_code_cell_id_for_model_visible_call(call_id)
    if code_cell_id not in rollout.code_cells:
        return
    _add_code_cell_output_item(rollout, code_cell_id, item_id)

def _add_code_cell_output_item(
    rollout: RolloutTrace,
    code_cell_id: CodeCellId,
    item_id: ConversationItemId,
) -> None:
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        raise ValueError(f"code cell {code_cell_id} disappeared during output linking")
    if item_id not in cell.output_item_ids:
        cell.output_item_ids.append(item_id)
    item = rollout.conversation_items.get(item_id)
    if item is None:
        raise ValueError(f"conversation item {item_id} disappeared during code-cell output linking")
    producer = ProducerRef.CodeCell(code_cell_id)
    if producer not in item.produced_by:
        item.produced_by.append(producer)

def _source_item_id_for_pending_code_cell(
    rollout: RolloutTrace,
    pending: _PendingCodeCellStart,
) -> ConversationItemId | None:
    items = _model_visible_code_cell_item_ids(
        rollout,
        pending.thread_id,
        pending.model_visible_call_id,
        ConversationItemKind.CUSTOM_TOOL_CALL,
    )
    return items[0] if items else None

def _source_item_id_for_code_cell_start(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    code_cell_id: CodeCellId,
    model_visible_call_id: ModelVisibleCallId,
) -> ConversationItemId:
    items = _model_visible_code_cell_item_ids(
        rollout,
        thread_id,
        model_visible_call_id,
        ConversationItemKind.CUSTOM_TOOL_CALL,
    )
    if not items:
        raise ValueError(
            f"code cell {code_cell_id} referenced model-visible call {model_visible_call_id}, "
            "but no custom tool call item was observed"
        )
    return items[0]

def _model_visible_code_cell_item_ids(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    call_id: ModelVisibleCallId,
    kind: ConversationItemKind,
) -> list[ConversationItemId]:
    return [
        item.item_id
        for item in rollout.conversation_items.values()
        if item.thread_id == thread_id and item.call_id == call_id and item.kind == kind
    ]

def _code_cell_event_thread_id(
    rollout: RolloutTrace,
    thread_id: str | None,
    codex_turn_id: str | None,
    runtime_cell_id: str,
    event_name: str,
) -> str:
    if thread_id is not None:
        return thread_id
    if codex_turn_id is None:
        raise ValueError(f"{event_name} {runtime_cell_id} did not include a thread id")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"{event_name} {runtime_cell_id} referenced unknown Codex turn {codex_turn_id}")
    return turn.thread_id

def _validate_code_cell_turn(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    codex_turn_id: CodexTurnId,
) -> None:
    if thread_id not in rollout.threads:
        raise ValueError(f"code cell start referenced unknown thread {thread_id}")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"code cell start referenced unknown Codex turn {codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"code cell start used thread {thread_id}, but Codex turn {codex_turn_id} belongs to {turn.thread_id}"
        )

def _reduced_code_cell_id_for_model_visible_call(model_visible_call_id: str) -> CodeCellId:
    return f"code_cell:{model_visible_call_id}"

def _record_runtime_code_cell_id(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    runtime_cell_id: str,
    code_cell_id: CodeCellId,
) -> None:
    key = (thread_id, runtime_cell_id)
    existing = rollout.code_cell_ids_by_runtime.get(key)
    if existing is not None and existing != code_cell_id:
        raise ValueError(
            f"runtime code cell {runtime_cell_id} in thread {thread_id} mapped to both "
            f"{existing} and {code_cell_id}"
        )
    rollout.code_cell_ids_by_runtime[key] = code_cell_id

def _code_cell_id_for_runtime_cell_id_if_known(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    runtime_cell_id: str,
) -> CodeCellId | None:
    return rollout.code_cell_ids_by_runtime.get((thread_id, runtime_cell_id))

def _pending_code_cell_id_for_runtime_cell_id(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    runtime_cell_id: str,
) -> CodeCellId | None:
    for code_cell_id, pending in rollout.pending_code_cell_starts.items():
        if pending.thread_id == thread_id and pending.runtime_cell_id == runtime_cell_id:
            return code_cell_id
    return None

def _execution_status_for_code_cell(status: CodeCellRuntimeStatus) -> ExecutionStatus:
    if status in {
        CodeCellRuntimeStatus.STARTING,
        CodeCellRuntimeStatus.RUNNING,
        CodeCellRuntimeStatus.YIELDED,
    }:
        return ExecutionStatus.RUNNING
    if status == CodeCellRuntimeStatus.COMPLETED:
        return ExecutionStatus.COMPLETED
    if status == CodeCellRuntimeStatus.FAILED:
        return ExecutionStatus.FAILED
    return ExecutionStatus.CANCELLED

def _read_rollout_payload_json(rollout: RolloutTrace, payload_ref: RawPayloadRef) -> dict[str, Any]:
    if rollout._bundle_dir is None:
        raise ValueError("rollout replay has no bundle directory")
    payload = _read_payload_json(rollout._bundle_dir, payload_ref)
    if not isinstance(payload, dict):
        raise ValueError(f"payload {payload_ref.raw_payload_id} was not a JSON object")
    return payload

from pycodex.rollout_trace.model import AgentThreadId, CodeCellId, CodexTurnId, ConversationItemId, ModelVisibleCallId, RolloutTrace

from pycodex.rollout_trace.model.conversation import ConversationItemKind, ProducerRef

from pycodex.rollout_trace.model.runtime import CodeCell, CodeCellRuntimeStatus

from pycodex.rollout_trace.model.session import ExecutionStatus, ExecutionWindow

from pycodex.rollout_trace.payload import RawPayloadRef

from pycodex.rollout_trace.raw_event import RawEventSeq

from pycodex.rollout_trace.reducer import _read_payload_json
