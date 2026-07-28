"""Rust-aligned owner for ``codex-rollout-trace::writer``."""

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

def _jsonable(value: Any) -> Any:
    if isinstance(value, RawPayloadKind):
        return {"type": value.value}
    if isinstance(value, RawTraceEventPayload):
        return {"type": value.type, **_jsonable(value.fields)}
    if isinstance(value, RawToolCallRequester):
        result: dict[str, Any] = {"type": value.type}
        if value.type == "code_cell":
            result["runtime_cell_id"] = value.runtime_cell_id
        return result
    if isinstance(value, RawTraceEvent):
        return {
            "schema_version": value.schema_version,
            "seq": value.seq,
            "wall_time_unix_ms": value.wall_time_unix_ms,
            "rollout_id": value.rollout_id,
            "thread_id": value.thread_id,
            "codex_turn_id": value.codex_turn_id,
            "payload": _jsonable(value.payload),
        }
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, ConversationPart):
        result: dict[str, Any] = {"type": value.type}
        for key in ("text", "label", "value", "summary", "raw_payload_id", "language", "source"):
            item = getattr(value, key)
            if item is not None:
                result[key] = item
        return result
    if isinstance(value, ProducerRef):
        result: dict[str, Any] = {"type": value.type}
        for key in (
            "inference_call_id",
            "tool_call_id",
            "code_cell_id",
            "edge_id",
            "compaction_id",
        ):
            item = getattr(value, key)
            if item is not None:
                result[key] = item
        return result
    if isinstance(value, AgentOrigin):
        result: dict[str, Any] = {"type": value.type}
        for key in ("parent_thread_id", "spawn_edge_id", "task_name", "agent_role"):
            item = getattr(value, key)
            if item is not None:
                result[key] = item
        return result
    if isinstance(value, ToolCallRequester):
        result: dict[str, Any] = {"type": value.type}
        if value.code_cell_id is not None:
            result["code_cell_id"] = value.code_cell_id
        return result
    if isinstance(value, ToolCallKind):
        result: dict[str, Any] = {"type": value.type}
        for key in ("server", "tool", "name"):
            item = getattr(value, key)
            if item is not None:
                result[key] = item
        return result
    if isinstance(value, ToolCallSummary):
        result: dict[str, Any] = {"type": value.type}
        variant_fields = {
            "terminal": ("operation_id",),
            "agent": ("target_agent_path", "task_name", "message_preview"),
            "wait_agent": ("target_agent_path", "timeout_ms"),
            "generic": ("label", "input_preview", "output_preview"),
        }[value.type]
        for key in variant_fields:
            result[key] = _jsonable(getattr(value, key))
        return result
    if isinstance(value, TerminalRequest):
        result: dict[str, Any] = {"type": value.type}
        variant_fields = {
            "exec_command": ("command", "display_command", "cwd", "yield_time_ms", "max_output_tokens"),
            "write_stdin": ("stdin", "yield_time_ms", "max_output_tokens"),
        }[value.type]
        for key in variant_fields:
            result[key] = _jsonable(getattr(value, key))
        return result
    if isinstance(value, TraceAnchor):
        result: dict[str, Any] = {"type": value.type}
        for key in ("tool_call_id", "thread_id", "item_id"):
            item = getattr(value, key)
            if item is not None:
                result[key] = item
        return result
    if isinstance(value, RolloutTrace):
        return {
            "schema_version": value.schema_version,
            "trace_id": value.trace_id,
            "rollout_id": value.rollout_id,
            "started_at_unix_ms": value.started_at_unix_ms,
            "ended_at_unix_ms": value.ended_at_unix_ms,
            "status": _jsonable(value.status),
            "root_thread_id": value.root_thread_id,
            "threads": _jsonable(value.threads),
            "codex_turns": _jsonable(value.codex_turns),
            "conversation_items": _jsonable(value.conversation_items),
            "inference_calls": _jsonable(value.inference_calls),
            "code_cells": _jsonable(value.code_cells),
            "tool_calls": _jsonable(value.tool_calls),
            "terminal_sessions": _jsonable(value.terminal_sessions),
            "terminal_operations": _jsonable(value.terminal_operations),
            "compactions": _jsonable(value.compactions),
            "compaction_requests": _jsonable(value.compaction_requests),
            "interaction_edges": _jsonable(value.interaction_edges),
            "raw_payloads": _jsonable(value.raw_payloads),
        }
    if is_dataclass(value):
        return {item.name: _jsonable(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value

class TraceWriter:
    def __init__(self, bundle_dir: Path, trace_id: str, rollout_id: str, root_thread_id: AgentThreadId) -> None:
        self.bundle_dir = bundle_dir
        self.payloads_dir = bundle_dir / PAYLOADS_DIR_NAME
        self.trace_id = trace_id
        self.rollout_id = rollout_id
        self.root_thread_id = root_thread_id
        self.next_seq = 1
        self.next_payload_ordinal = 1
        self.payloads_dir.mkdir(parents=True, exist_ok=True)
        self.event_log_path = bundle_dir / RAW_EVENT_LOG_FILE_NAME
        manifest = {
            "schema_version": 1,
            "trace_id": trace_id,
            "rollout_id": rollout_id,
            "root_thread_id": root_thread_id,
            "started_at_unix_ms": _unix_time_ms(),
            "raw_event_log": RAW_EVENT_LOG_FILE_NAME,
            "payloads_dir": PAYLOADS_DIR_NAME,
        }
        _write_json(bundle_dir / MANIFEST_FILE_NAME, manifest)
        self.event_log_path.touch(exist_ok=True)

    @classmethod
    def create(cls, bundle_dir: str | os.PathLike[str], trace_id: str, rollout_id: str, root_thread_id: AgentThreadId) -> "TraceWriter":
        return cls(Path(bundle_dir), trace_id, rollout_id, root_thread_id)

    def write_json_payload(self, kind: RawPayloadKind, value: Any) -> RawPayloadRef:
        ordinal = self.next_payload_ordinal
        self.next_payload_ordinal += 1
        payload_ref = RawPayloadRef(f"raw_payload:{ordinal}", kind, f"{PAYLOADS_DIR_NAME}/{ordinal}.json")
        _write_json(self.bundle_dir / payload_ref.path, value)
        return payload_ref

    def append(self, payload: RawTraceEventPayload) -> RawTraceEvent:
        return self.append_with_context(RawTraceEventContext(), payload)

    def append_with_context(self, context: RawTraceEventContext, payload: RawTraceEventPayload) -> RawTraceEvent:
        event = RawTraceEvent(
            RAW_TRACE_EVENT_SCHEMA_VERSION,
            self.next_seq,
            _unix_time_ms(),
            self.rollout_id,
            context.thread_id,
            context.codex_turn_id,
            payload,
        )
        self.next_seq += 1
        with self.event_log_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(_jsonable(event), separators=(",", ":")) + "\n")
        return event

def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(value), indent=2), encoding="utf-8")

def _unix_time_ms() -> int:
    return int(time.time() * 1000)

class _NoOpTraceContext:
    enabled: bool = False

    @classmethod
    def disabled(cls):
        return cls()

    def is_enabled(self) -> bool:
        return False

from pycodex.rollout_trace.bundle import MANIFEST_FILE_NAME, PAYLOADS_DIR_NAME, RAW_EVENT_LOG_FILE_NAME

from pycodex.rollout_trace.model import AgentThreadId, RolloutTrace

from pycodex.rollout_trace.model.conversation import ConversationPart, ProducerRef

from pycodex.rollout_trace.model.runtime import TerminalRequest, ToolCallKind, ToolCallRequester, ToolCallSummary, TraceAnchor

from pycodex.rollout_trace.model.session import AgentOrigin

from pycodex.rollout_trace.payload import RawPayloadKind, RawPayloadRef

from pycodex.rollout_trace.raw_event import RAW_TRACE_EVENT_SCHEMA_VERSION, RawToolCallRequester, RawTraceEvent, RawTraceEventContext, RawTraceEventPayload
