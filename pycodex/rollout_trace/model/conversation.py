"""Rust-aligned owner for ``codex-rollout-trace::model.conversation``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

class ConversationRole(str, Enum):
    SYSTEM = "system"
    DEVELOPER = "developer"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"

class ConversationChannel(str, Enum):
    ANALYSIS = "analysis"
    COMMENTARY = "commentary"
    FINAL = "final"
    SUMMARY = "summary"

class ConversationItemKind(str, Enum):
    MESSAGE = "message"
    REASONING = "reasoning"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"
    CUSTOM_TOOL_CALL = "custom_tool_call"
    CUSTOM_TOOL_CALL_OUTPUT = "custom_tool_call_output"
    COMPACTION_MARKER = "compaction_marker"

@dataclass(frozen=True)
class ConversationPart:
    type: str
    text: str | None = None
    label: str | None = None
    value: str | None = None
    summary: str | None = None
    raw_payload_id: RawPayloadId | None = None
    language: str | None = None
    source: str | None = None

    @classmethod
    def Text(cls, text: str) -> "ConversationPart":
        return cls("text", text=text)

    @classmethod
    def Summary(cls, text: str) -> "ConversationPart":
        return cls("summary", text=text)

    @classmethod
    def Encoded(cls, label: str, value: str) -> "ConversationPart":
        return cls("encoded", label=label, value=value)

    @classmethod
    def Json(cls, summary: str, raw_payload_id: RawPayloadId) -> "ConversationPart":
        return cls("json", summary=summary, raw_payload_id=raw_payload_id)

    @classmethod
    def Code(cls, language: str, source: str) -> "ConversationPart":
        return cls("code", language=language, source=source)

    @classmethod
    def PayloadRef(cls, label: str, raw_payload_id: RawPayloadId) -> "ConversationPart":
        return cls("payload_ref", label=label, raw_payload_id=raw_payload_id)

@dataclass(frozen=True)
class ConversationBody:
    parts: list[ConversationPart]

@dataclass(frozen=True)
class ProducerRef:
    type: str
    inference_call_id: InferenceCallId | None = None
    tool_call_id: ToolCallId | None = None
    code_cell_id: CodeCellId | None = None
    edge_id: EdgeId | None = None
    compaction_id: CompactionId | None = None

    @classmethod
    def UserInput(cls) -> "ProducerRef":
        return cls("user_input")

    @classmethod
    def Inference(cls, inference_call_id: InferenceCallId) -> "ProducerRef":
        return cls("inference", inference_call_id=inference_call_id)

    @classmethod
    def Compaction(cls, compaction_id: CompactionId) -> "ProducerRef":
        return cls("compaction", compaction_id=compaction_id)

    @classmethod
    def Tool(cls, tool_call_id: ToolCallId) -> "ProducerRef":
        return cls("tool", tool_call_id=tool_call_id)

    @classmethod
    def CodeCell(cls, code_cell_id: CodeCellId) -> "ProducerRef":
        return cls("code_cell", code_cell_id=code_cell_id)

    @classmethod
    def InteractionEdge(cls, edge_id: EdgeId) -> "ProducerRef":
        return cls("interaction_edge", edge_id=edge_id)

    @classmethod
    def Harness(cls) -> "ProducerRef":
        return cls("harness")

@dataclass
class ConversationItem:
    item_id: ConversationItemId
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId | None
    first_seen_at_unix_ms: int
    role: ConversationRole
    channel: ConversationChannel | None
    kind: ConversationItemKind
    body: ConversationBody
    call_id: ModelVisibleCallId | None
    produced_by: list[ProducerRef]

@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int

@dataclass
class InferenceCall:
    inference_call_id: InferenceCallId
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId
    execution: ExecutionWindow
    model: str
    provider_name: str
    response_id: str | None
    upstream_request_id: str | None
    request_item_ids: list[ConversationItemId]
    response_item_ids: list[ConversationItemId]
    tool_call_ids_started_by_response: list[ToolCallId]
    usage: Any
    raw_request_payload_id: RawPayloadId
    raw_response_payload_id: RawPayloadId | None
