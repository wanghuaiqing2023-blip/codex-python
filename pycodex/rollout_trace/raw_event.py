"""Rust-aligned owner for ``codex-rollout-trace::raw_event``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.rollout_trace.payload import RawPayloadRef

RAW_TRACE_EVENT_SCHEMA_VERSION = 1

RawEventSeq = int

def _snake(enum_name: str) -> str:
    out = []
    for index, char in enumerate(enum_name):
        if char.isupper() and index:
            out.append("_")
        out.append(char.lower())
    return "".join(out)

@dataclass(frozen=True)
class RawTraceEventContext:
    thread_id: AgentThreadId | None = None
    codex_turn_id: CodexTurnId | None = None

@dataclass(frozen=True)
class RawToolCallRequester:
    type: str
    runtime_cell_id: str | None = None

    @classmethod
    def Model(cls) -> "RawToolCallRequester":
        return cls("model")

    @classmethod
    def CodeCell(cls, runtime_cell_id: str) -> "RawToolCallRequester":
        return cls("code_cell", runtime_cell_id)

@dataclass(frozen=True)
class RawTraceEventPayload:
    type: str
    fields: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def variant(cls, name: str, **fields: Any) -> "RawTraceEventPayload":
        return cls(_snake(name), fields)

    def raw_payload_refs(self) -> list[RawPayloadRef]:
        fields = self.fields
        single_ref_fields = {
            "inference_started": "request_payload",
            "inference_completed": "response_payload",
            "compaction_request_started": "request_payload",
            "compaction_request_completed": "response_payload",
            "compaction_installed": "checkpoint_payload",
            "protocol_event_observed": "event_payload",
            "tool_call_runtime_started": "runtime_payload",
            "tool_call_runtime_ended": "runtime_payload",
        }
        optional_ref_fields = {
            "thread_started": "metadata_payload",
            "inference_failed": "partial_response_payload",
            "inference_cancelled": "partial_response_payload",
            "tool_call_started": "invocation_payload",
            "tool_call_ended": "result_payload",
            "code_cell_initial_response": "response_payload",
            "code_cell_ended": "response_payload",
            "agent_result_observed": "carried_payload",
        }
        if self.type in single_ref_fields:
            ref = fields.get(single_ref_fields[self.type])
            return [ref] if isinstance(ref, RawPayloadRef) else []
        if self.type in optional_ref_fields:
            ref = fields.get(optional_ref_fields[self.type])
            return [ref] if isinstance(ref, RawPayloadRef) else []
        if self.type == "other":
            payloads = fields.get("payloads", [])
            return [ref for ref in payloads if isinstance(ref, RawPayloadRef)]
        return []

@dataclass(frozen=True)
class RawTraceEvent:
    schema_version: int
    seq: RawEventSeq
    wall_time_unix_ms: int
    rollout_id: str
    thread_id: AgentThreadId | None
    codex_turn_id: CodexTurnId | None
    payload: RawTraceEventPayload
