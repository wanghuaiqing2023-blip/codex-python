"""Rust-aligned owner for ``codex-rollout-trace::reducer.compaction``."""

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

def start_compaction_request(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    compaction_id: str,
    compaction_request_id: str,
    thread_id: str,
    codex_turn_id: str,
    model: str,
    provider_name: str,
    request_payload: RawPayloadRef | None,
) -> None:
    if request_payload is None:
        raise ValueError(f"compaction request {compaction_request_id} missing request payload")
    if compaction_request_id in rollout.compaction_requests:
        raise ValueError(f"duplicate compaction request start for {compaction_request_id}")
    if thread_id not in rollout.threads:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"compaction request {compaction_request_id} referenced unknown codex turn {codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"compaction request {compaction_request_id} used thread {thread_id}, "
            f"but codex turn {codex_turn_id} belongs to {turn.thread_id}"
        )
    rollout.compaction_requests[compaction_request_id] = CompactionRequest(
        compaction_request_id=compaction_request_id,
        compaction_id=compaction_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
        model=model,
        provider_name=provider_name,
        raw_request_payload_id=request_payload.raw_payload_id,
        raw_response_payload_id=None,
    )

def _replay_complete_compaction_request(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    compaction_id: str,
    compaction_request_id: str,
    status: ExecutionStatus,
    response_payload: RawPayloadRef | None,
) -> None:
    request = rollout.compaction_requests.get(compaction_request_id)
    if request is None:
        raise ValueError(f"compaction request completion referenced unknown request {compaction_request_id}")
    if request.compaction_id != compaction_id:
        raise ValueError(
            f"compaction request {compaction_request_id} completion used compaction {compaction_id}, "
            f"but start used {request.compaction_id}"
        )
    request.execution = ExecutionWindow(
        started_at_unix_ms=request.execution.started_at_unix_ms,
        started_seq=request.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=status,
    )
    request.raw_response_payload_id = response_payload.raw_payload_id if response_payload else None

def _replay_compaction_installed(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    thread_id: str,
    codex_turn_id: str,
    compaction_id: str,
    checkpoint_payload: RawPayloadRef | None,
) -> None:
    if checkpoint_payload is None:
        raise ValueError(f"compaction install {compaction_id} missing checkpoint payload")
    if compaction_id in rollout.compactions:
        raise ValueError(f"duplicate compaction install for {compaction_id}")
    if thread_id not in rollout.threads:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"compaction install {compaction_id} referenced unknown codex turn {codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"compaction install {compaction_id} used thread {thread_id}, "
            f"but codex turn {codex_turn_id} belongs to {turn.thread_id}"
        )
    request_ids = [
        request.compaction_request_id
        for request in rollout.compaction_requests.values()
        if request.compaction_id == compaction_id
    ]
    checkpoint = _read_rollout_payload_json(rollout, checkpoint_payload)
    input_history = checkpoint.get("input_history")
    replacement_history = checkpoint.get("replacement_history")
    if not isinstance(input_history, list):
        raise ValueError(f"compaction checkpoint payload {checkpoint_payload.raw_payload_id} did not contain array input_history")
    if not isinstance(replacement_history, list):
        raise ValueError(f"compaction checkpoint payload {checkpoint_payload.raw_payload_id} did not contain array replacement_history")
    input_items = [normalize_model_item(item, checkpoint_payload) for item in input_history]
    replacement_items = [normalize_model_item(item, checkpoint_payload) for item in replacement_history]
    input_item_ids = _reconcile_detached_conversation_items(
        rollout,
        input_items,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        wall_time_unix_ms=wall_time_unix_ms,
        produced_by=[],
        candidates=list(rollout.thread_conversation_snapshots.get(thread_id, [])),
    )
    compaction_producer = [ProducerRef.Compaction(compaction_id)]
    marker_item_id = _create_conversation_item(
        rollout,
        thread_id,
        codex_turn_id,
        wall_time_unix_ms,
        _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=None,
            kind=ConversationItemKind.COMPACTION_MARKER,
            body=ConversationBody([]),
            call_id=None,
        ),
        compaction_producer,
    )
    replacement_item_ids = _reconcile_detached_conversation_items(
        rollout,
        replacement_items,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        wall_time_unix_ms=wall_time_unix_ms,
        produced_by=compaction_producer,
        candidates=[],
    )
    _append_thread_conversation_items(rollout, thread_id, input_item_ids)
    _append_thread_conversation_items(rollout, thread_id, [marker_item_id])
    _append_thread_conversation_items(rollout, thread_id, replacement_item_ids)
    rollout.pending_compaction_replacement_item_ids[thread_id] = list(replacement_item_ids)
    rollout.compactions[compaction_id] = Compaction(
        compaction_id=compaction_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        installed_at_unix_ms=wall_time_unix_ms,
        marker_item_id=marker_item_id,
        request_ids=request_ids,
        input_item_ids=input_item_ids,
        replacement_item_ids=replacement_item_ids,
    )

from pycodex.rollout_trace.model import RolloutTrace

from pycodex.rollout_trace.model.conversation import ConversationBody, ConversationItemKind, ConversationRole, ProducerRef

from pycodex.rollout_trace.model.runtime import Compaction, CompactionRequest

from pycodex.rollout_trace.model.session import ExecutionStatus, ExecutionWindow

from pycodex.rollout_trace.payload import RawPayloadRef

from pycodex.rollout_trace.reducer.code_cell import _read_rollout_payload_json

from pycodex.rollout_trace.reducer.conversation import _append_thread_conversation_items, _create_conversation_item, _reconcile_detached_conversation_items

from pycodex.rollout_trace.reducer.conversation.normalize import _NormalizedConversationItem, normalize_model_item
