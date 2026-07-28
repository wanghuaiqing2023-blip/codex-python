"""Rust-aligned owner for ``codex-rollout-trace::reducer.tool.terminal``."""

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

def _start_terminal_operation_from_invocation(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    thread_id: str,
    tool_call_id: str,
    kind: Any,
    invocation_payload: RawPayloadRef | None,
) -> TerminalOperationId | None:
    if terminal_operation_kind(kind) != TerminalOperationKind.WRITE_STDIN:
        return None
    if invocation_payload is None:
        return None
    payload = _read_rollout_payload_json(rollout, invocation_payload)
    terminal_id, request = _parse_dispatch_terminal_request(payload, invocation_payload.raw_payload_id)
    return _insert_terminal_operation(
        rollout,
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=thread_id,
        tool_call_id=tool_call_id,
        operation_kind=TerminalOperationKind.WRITE_STDIN,
        raw_payload=invocation_payload,
        terminal_id=terminal_id,
        request=request,
    )

def _start_terminal_operation_from_runtime(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    thread_id: str,
    tool_call_id: str,
    kind: Any,
    runtime_payload: RawPayloadRef,
) -> TerminalOperationId | None:
    operation_kind = terminal_operation_kind(kind)
    if operation_kind is None:
        return None
    payload = _read_rollout_payload_json(rollout, runtime_payload)
    terminal_id, request = _parse_protocol_terminal_request(payload, operation_kind)
    return _insert_terminal_operation(
        rollout,
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=thread_id,
        tool_call_id=tool_call_id,
        operation_kind=operation_kind,
        raw_payload=runtime_payload,
        terminal_id=terminal_id,
        request=request,
    )

def _insert_terminal_operation(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    thread_id: str,
    tool_call_id: str,
    operation_kind: TerminalOperationKind,
    raw_payload: RawPayloadRef,
    terminal_id: str | None,
    request: TerminalRequest,
) -> TerminalOperationId:
    operation_id = _next_terminal_operation_id(rollout)
    rollout.terminal_operations[operation_id] = TerminalOperation(
        operation_id=operation_id,
        terminal_id=terminal_id,
        tool_call_id=tool_call_id,
        kind=operation_kind,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
        request=request,
        result=None,
        model_observations=[],
        raw_payload_ids=[raw_payload.raw_payload_id],
    )
    if terminal_id is not None:
        _ensure_terminal_session(
            rollout,
            thread_id=thread_id,
            terminal_id=terminal_id,
            operation_id=operation_id,
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
        )
    return operation_id

def _end_terminal_operation(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    thread_id: str,
    operation_id: str,
    status: ExecutionStatus,
    response_payload: RawPayloadRef | None,
) -> None:
    operation = rollout.terminal_operations.get(operation_id)
    if operation is None:
        raise ValueError(f"terminal end referenced unknown operation {operation_id}")
    terminal_id = operation.terminal_id
    if response_payload is not None:
        value = _read_rollout_payload_json(rollout, response_payload)
        response_terminal_id, result = _parse_terminal_response_payload(
            value,
            operation.kind,
            response_payload.raw_payload_id,
        )
        push_unique(operation.raw_payload_ids, response_payload.raw_payload_id)
        if terminal_id is not None and response_terminal_id is not None and terminal_id != response_terminal_id:
            raise ValueError(
                f"terminal operation {operation_id} changed process id from {terminal_id} to {response_terminal_id}"
            )
        if terminal_id is None and response_terminal_id is not None:
            operation.terminal_id = response_terminal_id
            terminal_id = response_terminal_id
        operation.result = result
    operation.execution = ExecutionWindow(
        started_at_unix_ms=operation.execution.started_at_unix_ms,
        started_seq=operation.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=status,
    )
    if terminal_id is not None:
        _ensure_terminal_session(
            rollout,
            thread_id=thread_id,
            terminal_id=terminal_id,
            operation_id=operation_id,
            started_at_unix_ms=operation.execution.started_at_unix_ms,
            started_seq=operation.execution.started_seq,
        )

def _ensure_terminal_session(
    rollout: RolloutTrace,
    *,
    thread_id: str,
    terminal_id: str,
    operation_id: str,
    started_at_unix_ms: int,
    started_seq: int,
) -> None:
    session = rollout.terminal_sessions.get(terminal_id)
    if session is None:
        session = TerminalSession(
            terminal_id=terminal_id,
            thread_id=thread_id,
            created_by_operation_id=operation_id,
            operation_ids=[],
            execution=ExecutionWindow(
                started_at_unix_ms=started_at_unix_ms,
                started_seq=started_seq,
                status=ExecutionStatus.RUNNING,
            ),
        )
        rollout.terminal_sessions[terminal_id] = session
    if session.thread_id != thread_id:
        raise ValueError(f"terminal session {terminal_id} belongs to thread {session.thread_id}, not {thread_id}")
    push_unique(session.operation_ids, operation_id)

def _sync_terminal_model_observation(rollout: RolloutTrace, tool_call_id: str) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool call {tool_call_id} disappeared during terminal observation linking")
    operation_id = tool_call.terminal_operation_id
    if operation_id is None:
        return
    if not tool_call.model_visible_call_item_ids and not tool_call.model_visible_output_item_ids:
        return
    operation = rollout.terminal_operations.get(operation_id)
    if operation is None:
        raise ValueError(f"terminal operation {operation_id} disappeared during observation linking")
    for observation in operation.model_observations:
        if observation.source == TerminalObservationSource.DIRECT_TOOL_CALL:
            observation.call_item_ids = list(tool_call.model_visible_call_item_ids)
            observation.output_item_ids = list(tool_call.model_visible_output_item_ids)
            return
    operation.model_observations.append(
        TerminalModelObservation(
            call_item_ids=list(tool_call.model_visible_call_item_ids),
            output_item_ids=list(tool_call.model_visible_output_item_ids),
            source=TerminalObservationSource.DIRECT_TOOL_CALL,
        )
    )

def terminal_operation_kind(kind: Any) -> TerminalOperationKind | None:
    kind_type = _tool_kind_type(kind)
    if kind_type == "exec_command":
        return TerminalOperationKind.EXEC_COMMAND
    if kind_type == "write_stdin":
        return TerminalOperationKind.WRITE_STDIN
    return None

def _parse_protocol_terminal_request(
    payload: dict[str, Any],
    operation_kind: TerminalOperationKind,
) -> tuple[str | None, TerminalRequest]:
    terminal_id = payload.get("process_id") if isinstance(payload.get("process_id"), str) else None
    if operation_kind == TerminalOperationKind.EXEC_COMMAND:
        command = payload.get("command")
        if not isinstance(command, list):
            command = []
        command = [str(item) for item in command]
        return terminal_id, TerminalRequest.ExecCommand(
            command=command,
            display_command=" ".join(command),
            cwd=str(payload.get("cwd") or ""),
        )
    return terminal_id, TerminalRequest.WriteStdin(
        stdin=str(payload.get("interaction_input") or ""),
    )

def _parse_dispatch_terminal_request(
    payload: dict[str, Any],
    raw_payload_id: str,
) -> tuple[str, TerminalRequest]:
    tool_name = payload.get("tool_name")
    if tool_name != "write_stdin":
        raise ValueError(f"dispatch terminal request is for {tool_name}, not write_stdin")
    tool_payload = payload.get("payload")
    if not isinstance(tool_payload, dict):
        raise ValueError("write_stdin dispatch payload omitted payload")
    payload_kind = tool_payload.get("type")
    if payload_kind != "function":
        raise ValueError(f"write_stdin dispatch payload used unsupported {payload_kind} payload")
    arguments = tool_payload.get("arguments")
    if not isinstance(arguments, str):
        raise ValueError("write_stdin dispatch payload omitted function arguments")
    try:
        args = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError("parse write_stdin dispatch function arguments") from exc
    if not isinstance(args, dict):
        raise ValueError("parse write_stdin dispatch function arguments")
    terminal_id = _terminal_id_from_json(args.get("session_id"))
    if terminal_id is None:
        raise ValueError("write_stdin dispatch payload omitted session_id")
    return terminal_id, TerminalRequest.WriteStdin(
        stdin=str(args.get("chars") or ""),
        yield_time_ms=_optional_int(args.get("yield_time_ms")),
        max_output_tokens=_optional_int(args.get("max_output_tokens")),
    )

def _parse_terminal_response_payload(
    value: dict[str, Any],
    operation_kind: TerminalOperationKind,
    raw_payload_id: str,
) -> tuple[str | None, TerminalResult]:
    if operation_kind == TerminalOperationKind.EXEC_COMMAND:
        return _parse_protocol_terminal_response(value)
    try:
        return _parse_protocol_terminal_response(value)
    except ValueError:
        try:
            return _parse_dispatch_terminal_response(value)
        except ValueError as exc:
            raise ValueError(f"parse write_stdin terminal response {raw_payload_id}") from exc

def _parse_protocol_terminal_response(payload: dict[str, Any]) -> tuple[str | None, TerminalResult]:
    required = ("stdout", "stderr", "exit_code", "formatted_output")
    if not all(key in payload for key in required):
        raise ValueError("parse exec terminal response")
    terminal_id = payload.get("process_id") if isinstance(payload.get("process_id"), str) else None
    return terminal_id, TerminalResult(
        exit_code=int(payload["exit_code"]),
        stdout=str(payload["stdout"]),
        stderr=str(payload["stderr"]),
        formatted_output=str(payload["formatted_output"]),
    )

def _parse_dispatch_terminal_response(payload: dict[str, Any]) -> tuple[None, TerminalResult]:
    response_type = payload.get("type")
    if response_type == "direct_response":
        response_item = payload.get("response_item")
        output = _json_text_content(response_item.get("output") if isinstance(response_item, dict) else response_item)
        if output is None:
            output = json.dumps(response_item, separators=(",", ":"), ensure_ascii=False)
        return None, TerminalResult(None, output, "", output)
    if response_type == "code_mode_response":
        return None, _parse_code_mode_exec_result(payload.get("value"))
    if response_type == "error":
        error = str(payload.get("error") or "")
        return None, TerminalResult(None, "", error, error)
    raise ValueError("unknown dispatch terminal response")

def _parse_code_mode_exec_result(value: Any) -> TerminalResult:
    if isinstance(value, dict) and isinstance(value.get("output"), str):
        return TerminalResult(
            exit_code=_optional_int(value.get("exit_code")),
            stdout=value["output"],
            stderr="",
            formatted_output=value["output"],
            original_token_count=_optional_int(value.get("original_token_count")),
            chunk_id=value.get("chunk_id") if isinstance(value.get("chunk_id"), str) else None,
        )
    output = _json_text_content(value)
    if output is None:
        output = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return TerminalResult(None, output, "", output)

def _json_text_content(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [item.get("text") for item in value if isinstance(item, dict) and isinstance(item.get("text"), str)]
        text = "\n".join(parts)
        return text or None
    if value is None:
        return None
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)

def _terminal_id_from_json(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int):
        return str(value)
    return None

def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    return None

def _next_terminal_operation_id(rollout: RolloutTrace) -> str:
    ordinal = rollout._next_terminal_operation_ordinal
    rollout._next_terminal_operation_ordinal += 1
    return f"terminal_operation:{ordinal}"

from pycodex.rollout_trace.model import RolloutTrace, TerminalOperationId

from pycodex.rollout_trace.model.runtime import TerminalModelObservation, TerminalObservationSource, TerminalOperation, TerminalOperationKind, TerminalRequest, TerminalResult, TerminalSession

from pycodex.rollout_trace.model.session import ExecutionStatus, ExecutionWindow

from pycodex.rollout_trace.payload import RawPayloadRef

from pycodex.rollout_trace.reducer.code_cell import _read_rollout_payload_json, push_unique

from pycodex.rollout_trace.reducer.tool.agents import _tool_kind_type
