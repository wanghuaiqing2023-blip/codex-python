"""Rust-aligned owner for ``codex-rollout-trace::model``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

AgentThreadId = str

AgentPath = str

CodexTurnId = str

ConversationItemId = str

InferenceCallId = str

McpCallId = str

ToolCallId = str

ModelVisibleCallId = str

CodeModeRuntimeToolId = str

CodeCellId = str

TerminalId = str

TerminalOperationId = str

CompactionId = str

CompactionRequestId = str

EdgeId = str

CorrelationId = str

@dataclass
class RolloutTrace:
    schema_version: int
    trace_id: str
    rollout_id: str
    started_at_unix_ms: int
    ended_at_unix_ms: int | None
    status: RolloutStatus
    root_thread_id: AgentThreadId
    threads: dict[AgentThreadId, AgentThread] = field(default_factory=dict)
    codex_turns: dict[CodexTurnId, CodexTurn] = field(default_factory=dict)
    conversation_items: dict[ConversationItemId, Any] = field(default_factory=dict)
    inference_calls: dict[InferenceCallId, Any] = field(default_factory=dict)
    code_cells: dict[CodeCellId, Any] = field(default_factory=dict)
    tool_calls: dict[ToolCallId, Any] = field(default_factory=dict)
    terminal_sessions: dict[TerminalId, Any] = field(default_factory=dict)
    terminal_operations: dict[TerminalOperationId, Any] = field(default_factory=dict)
    compactions: dict[CompactionId, Any] = field(default_factory=dict)
    compaction_requests: dict[CompactionRequestId, Any] = field(default_factory=dict)
    interaction_edges: dict[EdgeId, Any] = field(default_factory=dict)
    raw_payloads: dict[RawPayloadId, RawPayloadRef] = field(default_factory=dict)
    thread_conversation_snapshots: dict[AgentThreadId, list[ConversationItemId]] = field(default_factory=dict, repr=False)
    pending_compaction_replacement_item_ids: dict[AgentThreadId, list[ConversationItemId]] = field(default_factory=dict, repr=False)
    code_cell_ids_by_runtime: dict[tuple[AgentThreadId, str], CodeCellId] = field(default_factory=dict, repr=False)
    pending_code_cell_starts: dict[CodeCellId, Any] = field(default_factory=dict, repr=False)
    pending_code_cell_lifecycle_events: dict[CodeCellId, list[Any]] = field(default_factory=dict, repr=False)
    pending_agent_interaction_edges: list[_PendingAgentInteractionEdge] = field(default_factory=list, repr=False)
    _bundle_dir: Path | None = field(default=None, repr=False)
    _next_conversation_item_ordinal: int = field(default=1, repr=False)
    _next_terminal_operation_ordinal: int = field(default=1, repr=False)

from pycodex.rollout_trace.model.conversation import *
from pycodex.rollout_trace.model.runtime import *
from pycodex.rollout_trace.model.session import *
