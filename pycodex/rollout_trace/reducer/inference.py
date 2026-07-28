"""Rust-aligned owner for ``codex-rollout-trace::reducer.inference``."""

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

def _reduce_inference_request(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    inference_call_id: str,
    thread_id: str,
    codex_turn_id: str,
    request_payload: RawPayloadRef,
) -> list[ConversationItemId]:
    payload = _read_rollout_payload_json(rollout, request_payload)
    if "input" not in payload:
        raise ValueError(f"inference request payload {request_payload.raw_payload_id} did not contain input")
    request_items = payload.get("input")
    if not isinstance(request_items, list):
        raise ValueError(f"inference request payload {request_payload.raw_payload_id} had non-array input")
    normalized = [normalize_model_item(item, request_payload) for item in request_items]
    previous_response_id = payload.get("previous_response_id")
    post_compaction_snapshot = None
    if not isinstance(previous_response_id, str):
        post_compaction_snapshot = rollout.pending_compaction_replacement_item_ids.get(thread_id)
    if isinstance(previous_response_id, str):
        previous_items: list[ConversationItemId] | None = None
        for inference in rollout.inference_calls.values():
            if inference.thread_id == thread_id and inference.response_id == previous_response_id:
                previous_items = list(inference.request_item_ids) + list(inference.response_item_ids)
                break
        if previous_items is None:
            raise ValueError(
                f"incremental inference request {inference_call_id} referenced unknown "
                f"previous_response_id {previous_response_id}"
            )
        delta_item_ids = reconcile_conversation_items(
            rollout,
            normalized,
            thread_id=thread_id,
            codex_turn_id=codex_turn_id,
            wall_time_unix_ms=wall_time_unix_ms,
            produced_by=[],
            start_index=len(previous_items),
            append_only=True,
        )
        item_ids = previous_items + delta_item_ids
    else:
        item_ids = reconcile_conversation_items(
            rollout,
            normalized,
            thread_id=thread_id,
            codex_turn_id=codex_turn_id,
            wall_time_unix_ms=wall_time_unix_ms,
            produced_by=[],
            start_index=0,
            append_only=False,
            snapshot_override=post_compaction_snapshot,
        )
    _append_thread_conversation_items(rollout, thread_id, item_ids)
    if post_compaction_snapshot is not None:
        rollout.pending_compaction_replacement_item_ids.pop(thread_id, None)
    rollout.thread_conversation_snapshots[thread_id] = list(item_ids)
    return item_ids

def _reduce_inference_response(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    inference_call_id: str,
    response_payload: RawPayloadRef,
) -> list[ConversationItemId]:
    payload = _read_rollout_payload_json(rollout, response_payload)
    output_items = payload.get("output_items")
    if not isinstance(output_items, list):
        raise ValueError(f"inference response payload {response_payload.raw_payload_id} did not contain output_items")
    inference = rollout.inference_calls.get(inference_call_id)
    if inference is None:
        raise ValueError(f"inference response referenced unknown call {inference_call_id}")
    normalized = [normalize_model_item(item, response_payload) for item in output_items]
    append_at = len(rollout.thread_conversation_snapshots.get(inference.thread_id, []))
    item_ids = reconcile_conversation_items(
        rollout,
        normalized,
        thread_id=inference.thread_id,
        codex_turn_id=inference.codex_turn_id,
        wall_time_unix_ms=wall_time_unix_ms,
        produced_by=[ProducerRef.Inference(inference_call_id)],
        start_index=append_at,
        append_only=True,
    )
    _append_thread_conversation_items(rollout, inference.thread_id, item_ids)
    rollout.thread_conversation_snapshots.setdefault(inference.thread_id, []).extend(item_ids)
    token_usage = payload.get("token_usage")
    if isinstance(token_usage, dict):
        inference.usage = _token_usage_from_value(token_usage)
    return item_ids

def start_inference_call(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    inference_call_id: str,
    thread_id: str,
    codex_turn_id: str,
    model: str,
    provider_name: str,
    request_payload: RawPayloadRef | None,
) -> None:
    if request_payload is None:
        raise ValueError(f"inference start {inference_call_id} missing request payload")
    if inference_call_id in rollout.inference_calls:
        raise ValueError(f"duplicate inference start for {inference_call_id}")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"inference start {inference_call_id} referenced unknown codex turn {codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"inference start {inference_call_id} used thread {thread_id}, "
            f"but codex turn {codex_turn_id} belongs to {turn.thread_id}"
        )
    if thread_id not in rollout.threads:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    request_item_ids = _reduce_inference_request(
        rollout,
        wall_time_unix_ms=wall_time_unix_ms,
        inference_call_id=inference_call_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        request_payload=request_payload,
    )
    rollout.inference_calls[inference_call_id] = InferenceCall(
        inference_call_id=inference_call_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
        model=model,
        provider_name=provider_name,
        response_id=None,
        upstream_request_id=None,
        request_item_ids=request_item_ids,
        response_item_ids=[],
        tool_call_ids_started_by_response=[],
        usage=None,
        raw_request_payload_id=request_payload.raw_payload_id,
        raw_response_payload_id=None,
    )

def _replay_complete_inference_call(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    payload: dict[str, Any],
) -> None:
    inference_call_id = payload["inference_call_id"]
    inference = rollout.inference_calls.get(inference_call_id)
    if inference is None:
        raise ValueError(f"inference completion referenced unknown call {inference_call_id}")
    payload_type = payload["type"]
    if payload_type == "inference_completed":
        status = ExecutionStatus.COMPLETED
        response_id = payload.get("response_id")
        upstream_request_id = payload.get("upstream_request_id")
        response_payload = _payload_ref_from_json(payload.get("response_payload"))
    elif payload_type == "inference_failed":
        status = ExecutionStatus.FAILED
        response_id = None
        upstream_request_id = payload.get("upstream_request_id")
        response_payload = _payload_ref_from_json(payload.get("partial_response_payload"))
    else:
        status = ExecutionStatus.CANCELLED
        response_id = None
        upstream_request_id = payload.get("upstream_request_id")
        response_payload = _payload_ref_from_json(payload.get("partial_response_payload"))

    inference.response_id = response_id
    if upstream_request_id is not None:
        inference.upstream_request_id = upstream_request_id
    if inference.execution.status == ExecutionStatus.RUNNING:
        inference.execution = ExecutionWindow(
            started_at_unix_ms=inference.execution.started_at_unix_ms,
            started_seq=inference.execution.started_seq,
            ended_at_unix_ms=wall_time_unix_ms,
            ended_seq=seq,
            status=status,
        )
    if response_payload is not None:
        inference.raw_response_payload_id = response_payload.raw_payload_id
        inference.response_item_ids = _reduce_inference_response(
            rollout,
            wall_time_unix_ms=wall_time_unix_ms,
            inference_call_id=inference_call_id,
            response_payload=response_payload,
        )
        _flush_pending_code_cell_starts(rollout)

def _close_running_inference_calls_for_turn_end(
    rollout: RolloutTrace,
    seq: int,
    wall_time_unix_ms: int,
    codex_turn_id: str,
    turn_status: ExecutionStatus,
) -> None:
    if turn_status == ExecutionStatus.RUNNING:
        return
    if turn_status in {ExecutionStatus.COMPLETED, ExecutionStatus.CANCELLED}:
        inference_status = ExecutionStatus.CANCELLED
    elif turn_status == ExecutionStatus.FAILED:
        inference_status = ExecutionStatus.FAILED
    else:
        inference_status = ExecutionStatus.ABORTED
    for inference in rollout.inference_calls.values():
        if inference.codex_turn_id == codex_turn_id and inference.execution.status == ExecutionStatus.RUNNING:
            inference.execution = ExecutionWindow(
                started_at_unix_ms=inference.execution.started_at_unix_ms,
                started_seq=inference.execution.started_seq,
                ended_at_unix_ms=wall_time_unix_ms,
                ended_seq=seq,
                status=inference_status,
            )

from pycodex.rollout_trace.model import ConversationItemId, RolloutTrace

from pycodex.rollout_trace.model.conversation import InferenceCall, ProducerRef

from pycodex.rollout_trace.model.session import ExecutionStatus, ExecutionWindow

from pycodex.rollout_trace.payload import RawPayloadRef

from pycodex.rollout_trace.reducer import _payload_ref_from_json

from pycodex.rollout_trace.reducer.code_cell import _flush_pending_code_cell_starts, _read_rollout_payload_json

from pycodex.rollout_trace.reducer.conversation import _append_thread_conversation_items, reconcile_conversation_items

from pycodex.rollout_trace.reducer.conversation.normalize import _token_usage_from_value, normalize_model_item
