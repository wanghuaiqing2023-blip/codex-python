"""Rust-aligned owner for ``codex-rollout-trace::reducer``."""

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

def replay_bundle(bundle_dir: str | os.PathLike[str]) -> RolloutTrace:
    bundle_path = Path(bundle_dir)
    manifest = json.loads((bundle_path / MANIFEST_FILE_NAME).read_text(encoding="utf-8"))
    rollout = RolloutTrace(
        schema_version=1,
        trace_id=manifest["trace_id"],
        rollout_id=manifest["rollout_id"],
        started_at_unix_ms=manifest["started_at_unix_ms"],
        ended_at_unix_ms=None,
        status=RolloutStatus.RUNNING,
        root_thread_id=manifest["root_thread_id"],
        _bundle_dir=bundle_path,
    )
    for line_index, line in enumerate((bundle_path / RAW_EVENT_LOG_FILE_NAME).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        event = json.loads(line)
        try:
            _apply_replayed_event(rollout, bundle_path, event)
        except Exception as exc:
            raise ValueError(f"apply trace event line {line_index}: {exc}") from exc
    _resolve_pending_spawn_edge_fallbacks(rollout)
    return rollout

def _apply_replayed_event(rollout: RolloutTrace, bundle_dir: Path, event: dict[str, Any]) -> None:
    payload = event["payload"]
    for payload_ref in _raw_payload_refs_from_payload(payload):
        rollout.raw_payloads[payload_ref.raw_payload_id] = payload_ref

    payload_type = payload["type"]
    if payload_type == "rollout_started":
        rollout.trace_id = payload["trace_id"]
        rollout.root_thread_id = payload["root_thread_id"]
    elif payload_type == "rollout_ended":
        rollout.status = RolloutStatus(payload["status"])
        rollout.ended_at_unix_ms = event["wall_time_unix_ms"]
    elif payload_type == "thread_started":
        _replay_start_thread(
            rollout,
            bundle_dir,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            thread_id=payload["thread_id"],
            agent_path=payload["agent_path"],
            metadata_payload=_payload_ref_from_json(payload.get("metadata_payload")),
        )
    elif payload_type == "thread_ended":
        _replay_end_thread(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            thread_id=payload["thread_id"],
            status=RolloutStatus(payload["status"]),
        )
    elif payload_type == "codex_turn_started":
        _replay_start_codex_turn(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            codex_turn_id=payload["codex_turn_id"],
            thread_id=payload["thread_id"],
        )
    elif payload_type == "codex_turn_ended":
        _replay_end_codex_turn(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            event_thread_id=event.get("thread_id"),
            codex_turn_id=payload["codex_turn_id"],
            status=ExecutionStatus(payload["status"]),
        )
    elif payload_type == "inference_started":
        start_inference_call(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            inference_call_id=payload["inference_call_id"],
            thread_id=payload["thread_id"],
            codex_turn_id=payload["codex_turn_id"],
            model=payload["model"],
            provider_name=payload["provider_name"],
            request_payload=_payload_ref_from_json(payload["request_payload"]),
        )
    elif payload_type in {"inference_completed", "inference_failed", "inference_cancelled"}:
        _replay_complete_inference_call(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            payload=payload,
        )
    elif payload_type == "compaction_request_started":
        start_compaction_request(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            compaction_id=payload["compaction_id"],
            compaction_request_id=payload["compaction_request_id"],
            thread_id=payload["thread_id"],
            codex_turn_id=payload["codex_turn_id"],
            model=payload["model"],
            provider_name=payload["provider_name"],
            request_payload=_payload_ref_from_json(payload["request_payload"]),
        )
    elif payload_type == "compaction_request_completed":
        _replay_complete_compaction_request(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            compaction_id=payload["compaction_id"],
            compaction_request_id=payload["compaction_request_id"],
            status=ExecutionStatus.COMPLETED,
            response_payload=_payload_ref_from_json(payload.get("response_payload")),
        )
    elif payload_type == "compaction_request_failed":
        _replay_complete_compaction_request(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            compaction_id=payload["compaction_id"],
            compaction_request_id=payload["compaction_request_id"],
            status=ExecutionStatus.FAILED,
            response_payload=None,
        )
    elif payload_type == "compaction_installed":
        thread_id = event.get("thread_id")
        codex_turn_id = event.get("codex_turn_id")
        if thread_id is None:
            raise ValueError(f"compaction installed event {payload['compaction_id']} did not include a thread id")
        if codex_turn_id is None:
            raise ValueError(f"compaction installed event {payload['compaction_id']} did not include a codex turn id")
        _replay_compaction_installed(
            rollout,
            wall_time_unix_ms=event["wall_time_unix_ms"],
            thread_id=thread_id,
            codex_turn_id=codex_turn_id,
            compaction_id=payload["compaction_id"],
            checkpoint_payload=_payload_ref_from_json(payload["checkpoint_payload"]),
        )
    elif payload_type == "tool_call_started":
        start_tool_call(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            event_thread_id=event.get("thread_id"),
            event_codex_turn_id=event.get("codex_turn_id"),
            payload=payload,
        )
    elif payload_type == "tool_call_ended":
        _replay_end_tool_call(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            tool_call_id=payload["tool_call_id"],
            status=ExecutionStatus(payload["status"]),
            result_payload=_payload_ref_from_json(payload.get("result_payload")),
        )
    elif payload_type == "tool_call_runtime_started":
        _replay_start_tool_runtime_observation(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            tool_call_id=payload["tool_call_id"],
            runtime_payload=_payload_ref_from_json(payload["runtime_payload"]),
        )
    elif payload_type == "tool_call_runtime_ended":
        _replay_end_tool_runtime_observation(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            tool_call_id=payload["tool_call_id"],
            status=ExecutionStatus(payload["status"]),
            runtime_payload=_payload_ref_from_json(payload["runtime_payload"]),
        )
    elif payload_type == "code_cell_started":
        _replay_start_or_queue_code_cell(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            event_thread_id=event.get("thread_id"),
            event_codex_turn_id=event.get("codex_turn_id"),
            runtime_cell_id=payload["runtime_cell_id"],
            model_visible_call_id=payload["model_visible_call_id"],
            source_js=payload["source_js"],
        )
    elif payload_type == "code_cell_initial_response":
        _replay_record_or_queue_code_cell_initial_response(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            event_thread_id=event.get("thread_id"),
            event_codex_turn_id=event.get("codex_turn_id"),
            runtime_cell_id=payload["runtime_cell_id"],
            status=CodeCellRuntimeStatus(payload["status"]),
        )
    elif payload_type == "code_cell_ended":
        _replay_end_or_queue_code_cell(
            rollout,
            seq=event["seq"],
            wall_time_unix_ms=event["wall_time_unix_ms"],
            event_thread_id=event.get("thread_id"),
            event_codex_turn_id=event.get("codex_turn_id"),
            runtime_cell_id=payload["runtime_cell_id"],
            status=CodeCellRuntimeStatus(payload["status"]),
        )
    elif payload_type == "mcp_tool_call_correlation_assigned":
        _assign_mcp_tool_call_correlation(
            rollout,
            tool_call_id=payload["tool_call_id"],
            mcp_call_id=payload["mcp_call_id"],
        )
    elif payload_type == "agent_result_observed":
        _queue_agent_result_interaction_edge(
            rollout,
            wall_time_unix_ms=event["wall_time_unix_ms"],
            edge_id=payload["edge_id"],
            child_thread_id=payload["child_thread_id"],
            child_codex_turn_id=payload["child_codex_turn_id"],
            parent_thread_id=payload["parent_thread_id"],
            message=payload["message"],
            carried_payload=_payload_ref_from_json(payload.get("carried_payload")),
        )
    elif payload_type == "other":
        raise ValueError("raw trace event has no reducer implementation")
    elif payload_type in {"protocol_event_observed"}:
        return
    else:
        raise NotImplementedError(f"raw trace event has no reducer implementation: {payload_type}")

def _raw_payload_refs_from_payload(payload: dict[str, Any]) -> list[RawPayloadRef]:
    single = {
        "inference_started": "request_payload",
        "inference_completed": "response_payload",
        "compaction_request_started": "request_payload",
        "compaction_request_completed": "response_payload",
        "compaction_installed": "checkpoint_payload",
        "protocol_event_observed": "event_payload",
        "tool_call_runtime_started": "runtime_payload",
        "tool_call_runtime_ended": "runtime_payload",
    }
    optional = {
        "thread_started": "metadata_payload",
        "inference_failed": "partial_response_payload",
        "inference_cancelled": "partial_response_payload",
        "tool_call_started": "invocation_payload",
        "tool_call_ended": "result_payload",
        "code_cell_initial_response": "response_payload",
        "code_cell_ended": "response_payload",
        "agent_result_observed": "carried_payload",
    }
    payload_type = payload["type"]
    if payload_type in single:
        ref = _payload_ref_from_json(payload.get(single[payload_type]))
        return [ref] if ref else []
    if payload_type in optional:
        ref = _payload_ref_from_json(payload.get(optional[payload_type]))
        return [ref] if ref else []
    if payload_type == "other":
        return [ref for item in payload.get("payloads", []) if (ref := _payload_ref_from_json(item))]
    return []

def _payload_ref_from_json(value: Any) -> RawPayloadRef | None:
    if value is None:
        return None
    if isinstance(value, RawPayloadRef):
        return value
    return RawPayloadRef(
        raw_payload_id=value["raw_payload_id"],
        kind=RawPayloadKind(value["kind"]["type"]),
        path=value["path"],
    )

def _read_payload_json(bundle_dir: Path, payload_ref: RawPayloadRef | None) -> Any:
    if payload_ref is None:
        return None
    return json.loads((bundle_dir / payload_ref.path).read_text(encoding="utf-8"))

def _thread_spawn_metadata(metadata: dict[str, Any] | None) -> dict[str, str] | None:
    if not metadata:
        return None
    session_source = metadata.get("session_source")
    if not isinstance(session_source, dict):
        return None
    subagent = session_source.get("subagent")
    if not isinstance(subagent, dict):
        return None
    spawn = subagent.get("thread_spawn")
    if not isinstance(spawn, dict) or "parent_thread_id" not in spawn:
        return None
    agent_path = spawn.get("agent_path") or metadata.get("agent_path")
    return {
        "parent_thread_id": spawn["parent_thread_id"],
        "agent_path": agent_path,
        "task_name": spawn.get("task_name") or metadata.get("task_name") or (task_name_from_agent_path(agent_path) if agent_path else None),
        "agent_role": spawn.get("agent_role") or metadata.get("agent_role"),
    }

from pycodex.rollout_trace.bundle import MANIFEST_FILE_NAME, RAW_EVENT_LOG_FILE_NAME

from pycodex.rollout_trace.model import RolloutTrace

from pycodex.rollout_trace.model.runtime import CodeCellRuntimeStatus

from pycodex.rollout_trace.model.session import ExecutionStatus, RolloutStatus

from pycodex.rollout_trace.payload import RawPayloadKind, RawPayloadRef

from pycodex.rollout_trace.reducer.code_cell import _replay_end_or_queue_code_cell, _replay_record_or_queue_code_cell_initial_response, _replay_start_or_queue_code_cell

from pycodex.rollout_trace.reducer.compaction import _replay_compaction_installed, _replay_complete_compaction_request, start_compaction_request

from pycodex.rollout_trace.reducer.inference import _replay_complete_inference_call, start_inference_call

from pycodex.rollout_trace.reducer.thread import _replay_end_codex_turn, _replay_end_thread, _replay_start_codex_turn, _replay_start_thread, task_name_from_agent_path

from pycodex.rollout_trace.reducer.tool import _assign_mcp_tool_call_correlation, _replay_end_tool_call, _replay_end_tool_runtime_observation, _replay_start_tool_runtime_observation, start_tool_call

from pycodex.rollout_trace.reducer.tool.agents import _queue_agent_result_interaction_edge, _resolve_pending_spawn_edge_fallbacks
