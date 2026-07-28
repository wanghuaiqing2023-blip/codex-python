"""Rust-aligned owner for ``codex-rollout-trace::model.runtime``."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

class CodeCellRuntimeStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    YIELDED = "yielded"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"

class TerminalOperationKind(str, Enum):
    EXEC_COMMAND = "exec_command"
    WRITE_STDIN = "write_stdin"

class TerminalObservationSource(str, Enum):
    DIRECT_TOOL_CALL = "direct_tool_call"
    CODE_CELL_OUTPUT = "code_cell_output"

class InteractionEdgeKind(str, Enum):
    SPAWN_AGENT = "spawn_agent"
    ASSIGN_AGENT_TASK = "assign_agent_task"
    SEND_MESSAGE = "send_message"
    AGENT_RESULT = "agent_result"
    CLOSE_AGENT = "close_agent"

@dataclass
class ToolCall:
    tool_call_id: ToolCallId
    mcp_call_id: McpCallId | None
    model_visible_call_id: ModelVisibleCallId | None
    code_mode_runtime_tool_id: str | None
    thread_id: AgentThreadId
    started_by_codex_turn_id: CodexTurnId | None
    execution: ExecutionWindow
    requester: Any
    kind: Any
    model_visible_call_item_ids: list[ConversationItemId]
    model_visible_output_item_ids: list[ConversationItemId]
    terminal_operation_id: Any = None
    summary: Any = None
    raw_invocation_payload_id: RawPayloadId | None = None
    raw_result_payload_id: RawPayloadId | None = None
    raw_runtime_payload_ids: list[RawPayloadId] = field(default_factory=list)

@dataclass(frozen=True)
class ToolCallRequester:
    type: str
    code_cell_id: CodeCellId | None = None

    @classmethod
    def Model(cls) -> "ToolCallRequester":
        return cls("model")

    @classmethod
    def CodeCell(cls, code_cell_id: CodeCellId) -> "ToolCallRequester":
        return cls("code_cell", code_cell_id=code_cell_id)

@dataclass(frozen=True)
class ToolCallKind:
    type: str
    server: str | None = None
    tool: str | None = None
    name: str | None = None

    @classmethod
    def ExecCommand(cls) -> "ToolCallKind":
        return cls("exec_command")

    @classmethod
    def WriteStdin(cls) -> "ToolCallKind":
        return cls("write_stdin")

    @classmethod
    def ApplyPatch(cls) -> "ToolCallKind":
        return cls("apply_patch")

    @classmethod
    def Mcp(cls, *, server: str, tool: str) -> "ToolCallKind":
        return cls("mcp", server=server, tool=tool)

    @classmethod
    def Web(cls) -> "ToolCallKind":
        return cls("web")

    @classmethod
    def ImageGeneration(cls) -> "ToolCallKind":
        return cls("image_generation")

    @classmethod
    def SpawnAgent(cls) -> "ToolCallKind":
        return cls("spawn_agent")

    @classmethod
    def AssignAgentTask(cls) -> "ToolCallKind":
        return cls("assign_agent_task")

    @classmethod
    def SendMessage(cls) -> "ToolCallKind":
        return cls("send_message")

    @classmethod
    def WaitAgent(cls) -> "ToolCallKind":
        return cls("wait_agent")

    @classmethod
    def CloseAgent(cls) -> "ToolCallKind":
        return cls("close_agent")

    @classmethod
    def Other(cls, *, name: str) -> "ToolCallKind":
        return cls("other", name=name)

@dataclass(frozen=True)
class ToolCallSummary:
    type: str
    operation_id: TerminalOperationId | None = None
    target_agent_path: AgentPath | None = None
    task_name: str | None = None
    message_preview: str | None = None
    timeout_ms: int | None = None
    label: str | None = None
    input_preview: str | None = None
    output_preview: str | None = None

    @classmethod
    def Terminal(cls, *, operation_id: TerminalOperationId) -> "ToolCallSummary":
        return cls("terminal", operation_id=operation_id)

    @classmethod
    def Agent(
        cls,
        *,
        target_agent_path: AgentPath,
        message_preview: str,
        task_name: str | None = None,
    ) -> "ToolCallSummary":
        return cls(
            "agent",
            target_agent_path=target_agent_path,
            task_name=task_name,
            message_preview=message_preview,
        )

    @classmethod
    def WaitAgent(
        cls,
        *,
        target_agent_path: AgentPath | None = None,
        timeout_ms: int | None = None,
    ) -> "ToolCallSummary":
        return cls("wait_agent", target_agent_path=target_agent_path, timeout_ms=timeout_ms)

    @classmethod
    def Generic(
        cls,
        *,
        label: str,
        input_preview: str | None = None,
        output_preview: str | None = None,
    ) -> "ToolCallSummary":
        return cls(
            "generic",
            label=label,
            input_preview=input_preview,
            output_preview=output_preview,
        )

@dataclass
class TerminalRequest:
    type: str
    command: list[str] | None = None
    display_command: str | None = None
    cwd: str | None = None
    stdin: str | None = None
    yield_time_ms: int | None = None
    max_output_tokens: int | None = None

    @classmethod
    def ExecCommand(
        cls,
        *,
        command: list[str],
        display_command: str,
        cwd: str,
        yield_time_ms: int | None = None,
        max_output_tokens: int | None = None,
    ) -> "TerminalRequest":
        return cls(
            "exec_command",
            command=command,
            display_command=display_command,
            cwd=cwd,
            yield_time_ms=yield_time_ms,
            max_output_tokens=max_output_tokens,
        )

    @classmethod
    def WriteStdin(
        cls,
        *,
        stdin: str,
        yield_time_ms: int | None = None,
        max_output_tokens: int | None = None,
    ) -> "TerminalRequest":
        return cls(
            "write_stdin",
            stdin=stdin,
            yield_time_ms=yield_time_ms,
            max_output_tokens=max_output_tokens,
        )

@dataclass
class TerminalResult:
    exit_code: int | None
    stdout: str
    stderr: str
    formatted_output: str | None
    original_token_count: int | None = None
    chunk_id: str | None = None

@dataclass
class TerminalModelObservation:
    call_item_ids: list[ConversationItemId]
    output_item_ids: list[ConversationItemId]
    source: TerminalObservationSource

@dataclass
class TerminalOperation:
    operation_id: TerminalOperationId
    terminal_id: TerminalId | None
    tool_call_id: ToolCallId
    kind: TerminalOperationKind
    execution: ExecutionWindow
    request: TerminalRequest
    result: TerminalResult | None
    model_observations: list[TerminalModelObservation]
    raw_payload_ids: list[RawPayloadId]

@dataclass
class TerminalSession:
    terminal_id: TerminalId
    thread_id: AgentThreadId
    created_by_operation_id: TerminalOperationId
    operation_ids: list[TerminalOperationId]
    execution: ExecutionWindow

@dataclass
class CodeCell:
    code_cell_id: CodeCellId
    model_visible_call_id: ModelVisibleCallId
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId
    source_item_id: ConversationItemId
    output_item_ids: list[ConversationItemId]
    runtime_cell_id: str | None
    execution: ExecutionWindow
    runtime_status: CodeCellRuntimeStatus
    initial_response_at_unix_ms: int | None
    initial_response_seq: RawEventSeq | None
    yielded_at_unix_ms: int | None
    yielded_seq: RawEventSeq | None
    source_js: str
    nested_tool_call_ids: list[ToolCallId] = field(default_factory=list)
    wait_tool_call_ids: list[ToolCallId] = field(default_factory=list)

@dataclass(frozen=True)
class TraceAnchor:
    type: str
    tool_call_id: ToolCallId | None = None
    thread_id: AgentThreadId | None = None
    item_id: ConversationItemId | None = None

    @classmethod
    def ToolCall(cls, tool_call_id: ToolCallId) -> "TraceAnchor":
        return cls("tool_call", tool_call_id=tool_call_id)

    @classmethod
    def Thread(cls, thread_id: AgentThreadId) -> "TraceAnchor":
        return cls("thread", thread_id=thread_id)

    @classmethod
    def ConversationItem(cls, item_id: ConversationItemId) -> "TraceAnchor":
        return cls("conversation_item", item_id=item_id)

@dataclass
class InteractionEdge:
    edge_id: EdgeId
    kind: InteractionEdgeKind
    source: TraceAnchor
    target: TraceAnchor
    started_at_unix_ms: int
    ended_at_unix_ms: int | None
    carried_item_ids: list[ConversationItemId]
    carried_raw_payload_ids: list[RawPayloadId]

@dataclass
class CompactionRequest:
    compaction_request_id: CompactionRequestId
    compaction_id: CompactionId
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId
    execution: ExecutionWindow
    model: str
    provider_name: str
    raw_request_payload_id: RawPayloadId
    raw_response_payload_id: RawPayloadId | None

@dataclass
class Compaction:
    compaction_id: CompactionId
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId
    installed_at_unix_ms: int
    marker_item_id: ConversationItemId
    request_ids: list[CompactionRequestId]
    input_item_ids: list[ConversationItemId]
    replacement_item_ids: list[ConversationItemId]
