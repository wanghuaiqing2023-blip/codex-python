"""Rust-aligned owner for ``codex-rollout-trace::protocol_event``."""

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

def _protocol_event_type(event: Any) -> str | None:
    if isinstance(event, dict):
        event_type = event.get("type")
        return event_type if isinstance(event_type, str) else None
    event_type = getattr(event, "type", None)
    if isinstance(event_type, str):
        return event_type
    return event.__class__.__name__ if event is not None else None

def _protocol_event_field(event: Any, name: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)

def wrapped_protocol_event_type(event: Any) -> str | None:
    event_type = _protocol_event_type(event)
    wrapped = {
        "session_configured",
        "turn_started",
        "turn_complete",
        "turn_aborted",
        "thread_rolled_back",
        "error",
        "warning",
        "shutdown_complete",
    }
    return event_type if event_type in wrapped else None

def _codex_turn_trace_event(
    thread_id: AgentThreadId,
    default_turn_id: str,
    event: Any,
) -> tuple[str, RawTraceEventPayload] | None:
    event_type = _protocol_event_type(event)
    if event_type == "turn_started":
        codex_turn_id = str(_protocol_event_field(event, "turn_id"))
        return codex_turn_id, RawTraceEventPayload.variant(
            "CodexTurnStarted",
            codex_turn_id=codex_turn_id,
            thread_id=thread_id,
        )
    if event_type == "turn_complete":
        codex_turn_id = str(_protocol_event_field(event, "turn_id"))
        return codex_turn_id, RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id=codex_turn_id,
            status=ExecutionStatus.COMPLETED,
        )
    if event_type == "turn_aborted":
        turn_id = _protocol_event_field(event, "turn_id")
        codex_turn_id = str(turn_id) if turn_id is not None else default_turn_id
        return codex_turn_id, RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id=codex_turn_id,
            status=_execution_status_for_abort_reason(_protocol_event_field(event, "reason")),
        )
    return None

def _tool_runtime_trace_event(event: Any) -> tuple[str, str, ExecutionStatus | None] | None:
    event_type = _protocol_event_type(event)
    if event_type in {"exec_command_begin", "exec_command_end"} and _protocol_event_field(event, "source") == "user_shell":
        return None
    if event_type in {
        "exec_command_begin",
        "patch_apply_begin",
        "mcp_tool_call_begin",
        "collab_agent_spawn_begin",
        "collab_agent_interaction_begin",
        "collab_waiting_begin",
        "collab_close_begin",
    }:
        return "started", str(_protocol_event_field(event, "call_id")), None
    if event_type == "exec_command_end":
        return (
            "ended",
            str(_protocol_event_field(event, "call_id")),
            _execution_status_for_exec_command_status(_protocol_event_field(event, "status")),
        )
    if event_type == "patch_apply_end":
        return (
            "ended",
            str(_protocol_event_field(event, "call_id")),
            _execution_status_for_patch_apply_status(_protocol_event_field(event, "status")),
        )
    if event_type == "mcp_tool_call_end":
        return (
            "ended",
            str(_protocol_event_field(event, "call_id")),
            ExecutionStatus.COMPLETED if bool(_protocol_event_field(event, "ok", True)) else ExecutionStatus.FAILED,
        )
    if event_type == "collab_agent_spawn_end":
        return (
            "ended",
            str(_protocol_event_field(event, "call_id")),
            ExecutionStatus.COMPLETED if _protocol_event_field(event, "new_thread_id") is not None else ExecutionStatus.FAILED,
        )
    if event_type in {
        "collab_agent_interaction_end",
        "collab_waiting_end",
        "collab_close_end",
    }:
        return "ended", str(_protocol_event_field(event, "call_id")), ExecutionStatus.COMPLETED
    return None

def _execution_status_for_exec_command_status(status: Any) -> ExecutionStatus:
    if status == "completed":
        return ExecutionStatus.COMPLETED
    if status == "failed":
        return ExecutionStatus.FAILED
    if status == "declined":
        return ExecutionStatus.CANCELLED
    return ExecutionStatus.FAILED

def _execution_status_for_patch_apply_status(status: Any) -> ExecutionStatus:
    if status == "completed":
        return ExecutionStatus.COMPLETED
    if status == "failed":
        return ExecutionStatus.FAILED
    if status == "declined":
        return ExecutionStatus.CANCELLED
    return ExecutionStatus.FAILED

def _execution_status_for_abort_reason(reason: Any) -> ExecutionStatus:
    if reason in {"interrupted", "replaced", "review_ended", "budget_limited"}:
        return ExecutionStatus.CANCELLED
    return ExecutionStatus.CANCELLED

from pycodex.rollout_trace.model import AgentThreadId

from pycodex.rollout_trace.model.session import ExecutionStatus

from pycodex.rollout_trace.raw_event import RawTraceEventPayload
