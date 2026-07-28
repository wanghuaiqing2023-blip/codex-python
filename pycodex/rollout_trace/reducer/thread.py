"""Rust-aligned owner for ``codex-rollout-trace::reducer.thread``."""

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

def _replay_start_thread(
    rollout: RolloutTrace,
    bundle_dir: Path,
    *,
    seq: int,
    wall_time_unix_ms: int,
    thread_id: str,
    agent_path: str,
    metadata_payload: RawPayloadRef | None,
) -> None:
    if thread_id in rollout.threads:
        raise ValueError(f"duplicate thread start for {thread_id}")
    metadata = _read_payload_json(bundle_dir, metadata_payload) if metadata_payload else None
    spawn = _thread_spawn_metadata(metadata) if isinstance(metadata, dict) else None
    if spawn is not None:
        agent_path = spawn.get("agent_path") or (metadata or {}).get("agent_path") or agent_path
        task_name = spawn.get("task_name") or task_name_from_agent_path(agent_path)
        origin = AgentOrigin.Spawned(
            parent_thread_id=spawn["parent_thread_id"],
            spawn_edge_id=_spawn_edge_id(spawn["parent_thread_id"], thread_id),
            task_name=task_name,
            agent_role=spawn.get("agent_role") or "",
        )
    else:
        agent_path = (metadata or {}).get("agent_path") or agent_path
        origin = AgentOrigin.Root()
    rollout.threads[thread_id] = AgentThread(
        thread_id=thread_id,
        agent_path=agent_path,
        nickname=(metadata or {}).get("nickname"),
        origin=origin,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
        default_model=(metadata or {}).get("model"),
    )

def _replay_end_thread(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    thread_id: str,
    status: RolloutStatus,
) -> None:
    thread = rollout.threads.get(thread_id)
    if thread is None:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    thread.execution = ExecutionWindow(
        started_at_unix_ms=thread.execution.started_at_unix_ms,
        started_seq=thread.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=_execution_status_from_rollout_status(status),
    )

def _replay_start_codex_turn(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    codex_turn_id: str,
    thread_id: str,
) -> None:
    if codex_turn_id in rollout.codex_turns:
        raise ValueError(f"duplicate codex turn start for {codex_turn_id}")
    if thread_id not in rollout.threads:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    rollout.codex_turns[codex_turn_id] = CodexTurn(
        codex_turn_id=codex_turn_id,
        thread_id=thread_id,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
    )

def _replay_end_codex_turn(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    codex_turn_id: str,
    status: ExecutionStatus,
) -> None:
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"codex turn end referenced unknown turn {codex_turn_id}")
    if event_thread_id is not None and turn.thread_id != event_thread_id:
        raise ValueError(
            f"codex turn end for {codex_turn_id} used thread {event_thread_id}, "
            f"but the turn belongs to {turn.thread_id}"
        )
    turn.execution = ExecutionWindow(
        started_at_unix_ms=turn.execution.started_at_unix_ms,
        started_seq=turn.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=status,
    )
    _close_running_inference_calls_for_turn_end(rollout, seq, wall_time_unix_ms, codex_turn_id, status)
    _terminate_running_code_cells_for_turn_end(rollout, seq, wall_time_unix_ms, codex_turn_id, status)

def task_name_from_agent_path(agent_path: str) -> str:
    for segment in reversed(agent_path.split("/")):
        if segment:
            return segment
    return agent_path

def _spawn_edge_id(parent_thread_id: str, child_thread_id: str) -> str:
    return f"edge:spawn:{parent_thread_id}:{child_thread_id}"

def _execution_status_from_rollout_status(status: RolloutStatus) -> ExecutionStatus:
    if status == RolloutStatus.RUNNING:
        return ExecutionStatus.RUNNING
    if status == RolloutStatus.COMPLETED:
        return ExecutionStatus.COMPLETED
    if status == RolloutStatus.FAILED:
        return ExecutionStatus.FAILED
    return ExecutionStatus.ABORTED

from pycodex.rollout_trace.model import RolloutTrace

from pycodex.rollout_trace.model.session import AgentOrigin, AgentThread, CodexTurn, ExecutionStatus, ExecutionWindow, RolloutStatus

from pycodex.rollout_trace.payload import RawPayloadRef

from pycodex.rollout_trace.reducer import _read_payload_json, _thread_spawn_metadata

from pycodex.rollout_trace.reducer.code_cell import _terminate_running_code_cells_for_turn_end

from pycodex.rollout_trace.reducer.inference import _close_running_inference_calls_for_turn_end
