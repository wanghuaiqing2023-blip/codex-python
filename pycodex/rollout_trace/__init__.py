"""Source-verified Python interface for ``codex-rollout-trace``.

Rust reference:
- ``codex/codex-rs/rollout-trace/src/lib.rs``
- ``payload.rs``, ``raw_event.rs``, ``writer.rs``, ``mcp.rs``
- no-op-capable context handles in ``thread.rs``, ``inference.rs``,
  ``code_cell.rs``, ``tool_dispatch.rs``
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

MANIFEST_FILE_NAME = "manifest.json"
RAW_EVENT_LOG_FILE_NAME = "trace.jsonl"
PAYLOADS_DIR_NAME = "payloads"
REDUCED_STATE_FILE_NAME = "state.json"
CODEX_ROLLOUT_TRACE_ROOT_ENV = "CODEX_ROLLOUT_TRACE_ROOT"
RAW_TRACE_EVENT_SCHEMA_VERSION = 1
MCP_CALL_ID_META_KEY = "codex_bridge_mcp_call_id"
INFERENCE_CALL_ID_HEADER = "x-codex-inference-call-id"

RawPayloadId = str
RawEventSeq = int
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


def _snake(enum_name: str) -> str:
    out = []
    for index, char in enumerate(enum_name):
        if char.isupper() and index:
            out.append("_")
        out.append(char.lower())
    return "".join(out)


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


def trace_response_item_json(item: Any) -> Any:
    """Serialize a response item for trace evidence.

    Rust's normal protocol serializer omits readable reasoning content when
    shaping future model input. The rollout-trace serializer keeps that content
    in raw trace payloads.
    """

    value = _jsonable(item)
    if not isinstance(value, dict) or value.get("type") != "reasoning":
        return value

    content = None
    if isinstance(item, dict):
        content = item.get("content")
    else:
        content = getattr(item, "content", None)
    if content is not None:
        value["content"] = _jsonable(content)
    return value


class RawPayloadKind(str, Enum):
    INFERENCE_REQUEST = "inference_request"
    INFERENCE_RESPONSE = "inference_response"
    COMPACTION_REQUEST = "compaction_request"
    COMPACTION_CHECKPOINT = "compaction_checkpoint"
    COMPACTION_RESPONSE = "compaction_response"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    TOOL_RUNTIME_EVENT = "tool_runtime_event"
    TERMINAL_RUNTIME_EVENT = "terminal_runtime_event"
    PROTOCOL_EVENT = "protocol_event"
    SESSION_METADATA = "session_metadata"
    AGENT_RESULT = "agent_result"


@dataclass(frozen=True)
class RawPayloadRef:
    raw_payload_id: RawPayloadId
    kind: RawPayloadKind
    path: str


class RolloutStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class ExecutionStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ABORTED = "aborted"


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


@dataclass(frozen=True)
class ExecutionWindow:
    started_at_unix_ms: int
    started_seq: RawEventSeq
    ended_at_unix_ms: int | None = None
    ended_seq: RawEventSeq | None = None
    status: ExecutionStatus = ExecutionStatus.RUNNING


@dataclass(frozen=True)
class AgentOrigin:
    type: str
    parent_thread_id: AgentThreadId | None = None
    spawn_edge_id: EdgeId | None = None
    task_name: str | None = None
    agent_role: str | None = None

    @classmethod
    def Root(cls) -> "AgentOrigin":
        return cls("root")

    @classmethod
    def Spawned(
        cls,
        *,
        parent_thread_id: AgentThreadId,
        spawn_edge_id: EdgeId,
        task_name: str,
        agent_role: str,
    ) -> "AgentOrigin":
        return cls(
            "spawned",
            parent_thread_id=parent_thread_id,
            spawn_edge_id=spawn_edge_id,
            task_name=task_name,
            agent_role=agent_role,
        )


@dataclass
class AgentThread:
    thread_id: AgentThreadId
    agent_path: AgentPath
    nickname: str | None
    origin: AgentOrigin
    execution: ExecutionWindow
    default_model: str | None
    conversation_item_ids: list[ConversationItemId] = field(default_factory=list)


@dataclass
class CodexTurn:
    codex_turn_id: CodexTurnId
    thread_id: AgentThreadId
    execution: ExecutionWindow
    input_item_ids: list[ConversationItemId] = field(default_factory=list)


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
class _PendingAgentInteractionEdge:
    edge_id: EdgeId
    kind: InteractionEdgeKind
    source: TraceAnchor
    target_thread_id: AgentThreadId
    message_content: str
    unresolved_spawn_thread_id: AgentThreadId | None
    started_at_unix_ms: int
    ended_at_unix_ms: int | None
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


@dataclass
class McpCallTraceContext:
    mcp_call_id: McpCallId | None = None

    @classmethod
    def disabled(cls) -> "McpCallTraceContext":
        return cls(None)

    @classmethod
    def enabled(cls, mcp_call_id: McpCallId) -> "McpCallTraceContext":
        return cls(mcp_call_id)

    def add_request_meta(self, meta: dict[str, Any] | None) -> dict[str, Any] | None:
        if self.mcp_call_id is None:
            return meta
        if meta is None:
            meta = {}
        if not isinstance(meta, dict):
            return meta
        return {**meta, MCP_CALL_ID_META_KEY: self.mcp_call_id}


class _NoOpTraceContext:
    enabled: bool = False

    @classmethod
    def disabled(cls):
        return cls()

    def is_enabled(self) -> bool:
        return False


class CodeCellTraceContext(_NoOpTraceContext):
    @classmethod
    def enabled(
        cls,
        writer: TraceWriter,
        thread_id: AgentThreadId,
        codex_turn_id: CodexTurnId,
        runtime_cell_id: str,
    ) -> "CodeCellTraceContext":
        context = cls()
        context.enabled = True
        context.writer = writer
        context.thread_id = thread_id
        context.codex_turn_id = codex_turn_id
        context.runtime_cell_id = runtime_cell_id
        return context

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def record_started(self, model_visible_call_id: str, source_js: str) -> None:
        writer = getattr(self, "writer", None)
        if writer is not None:
            writer.append_with_context(
                RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
                RawTraceEventPayload.variant(
                    "CodeCellStarted",
                    runtime_cell_id=self.runtime_cell_id,
                    model_visible_call_id=model_visible_call_id,
                    source_js=source_js,
                ),
            )
        return None

    def record_initial_response(self, response: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is not None:
            writer.append_with_context(
                RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
                RawTraceEventPayload.variant(
                    "CodeCellInitialResponse",
                    runtime_cell_id=self.runtime_cell_id,
                    status=_code_cell_status_for_runtime_response(response),
                    response_payload=_code_cell_response_payload(writer, response),
                ),
            )
        return None

    def record_ended(self, response: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is not None:
            writer.append_with_context(
                RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
                RawTraceEventPayload.variant(
                    "CodeCellEnded",
                    runtime_cell_id=self.runtime_cell_id,
                    status=_code_cell_status_for_runtime_response(response),
                    response_payload=_code_cell_response_payload(writer, response),
                ),
            )
        return None


class InferenceTraceAttempt(_NoOpTraceContext):
    @classmethod
    def enabled(
        cls,
        writer: TraceWriter,
        thread_id: AgentThreadId,
        codex_turn_id: CodexTurnId,
        model: str,
        provider_name: str,
    ) -> "InferenceTraceAttempt":
        attempt = cls()
        attempt.enabled = True
        attempt.writer = writer
        attempt.thread_id = thread_id
        attempt.codex_turn_id = codex_turn_id
        attempt.model = model
        attempt.provider_name = provider_name
        attempt.inference_call_id = str(uuid.uuid4())
        attempt.terminal_recorded = False
        return attempt

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def add_request_headers(self, headers: dict[str, str]) -> None:
        inference_call_id = getattr(self, "inference_call_id", None)
        if inference_call_id is not None:
            headers[INFERENCE_CALL_ID_HEADER] = inference_call_id

    def record_started(self, request: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return None
        request_payload = writer.write_json_payload(RawPayloadKind.INFERENCE_REQUEST, request)
        writer.append_with_context(
            RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
            RawTraceEventPayload.variant(
                "InferenceStarted",
                inference_call_id=self.inference_call_id,
                thread_id=self.thread_id,
                codex_turn_id=self.codex_turn_id,
                model=self.model,
                provider_name=self.provider_name,
                request_payload=request_payload,
            ),
        )

    def record_completed(self, response_id: str, upstream_request_id: str | None, token_usage: Any, output_items: list[Any]) -> None:
        if self._take_terminal():
            response_payload = self._write_response_payload(response_id, upstream_request_id, token_usage, output_items)
            self.writer.append_with_context(
                RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
                RawTraceEventPayload.variant(
                    "InferenceCompleted",
                    inference_call_id=self.inference_call_id,
                    response_id=response_id,
                    upstream_request_id=upstream_request_id,
                    response_payload=response_payload,
                ),
            )

    def record_failed(self, error: Any, upstream_request_id: str | None, output_items: list[Any]) -> None:
        if self._take_terminal():
            partial = None
            if output_items:
                partial = self._write_response_payload(None, upstream_request_id, None, output_items)
            self.writer.append_with_context(
                RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
                RawTraceEventPayload.variant(
                    "InferenceFailed",
                    inference_call_id=self.inference_call_id,
                    upstream_request_id=upstream_request_id,
                    error=str(error),
                    partial_response_payload=partial,
                ),
            )

    def record_cancelled(self, reason: Any, upstream_request_id: str | None, output_items: list[Any]) -> None:
        if self._take_terminal():
            partial = None
            if output_items:
                partial = self._write_response_payload(None, upstream_request_id, None, output_items)
            self.writer.append_with_context(
                RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
                RawTraceEventPayload.variant(
                    "InferenceCancelled",
                    inference_call_id=self.inference_call_id,
                    upstream_request_id=upstream_request_id,
                    reason=str(reason),
                    partial_response_payload=partial,
                ),
            )

    def _take_terminal(self) -> bool:
        if not self.is_enabled() or getattr(self, "terminal_recorded", False):
            return False
        self.terminal_recorded = True
        return True

    def _write_response_payload(
        self,
        response_id: str | None,
        upstream_request_id: str | None,
        token_usage: Any,
        output_items: list[Any],
    ) -> RawPayloadRef:
        return self.writer.write_json_payload(
            RawPayloadKind.INFERENCE_RESPONSE,
            {
                "response_id": response_id,
                "upstream_request_id": upstream_request_id,
                "token_usage": token_usage,
                "output_items": [trace_response_item_json(item) for item in output_items],
            },
        )


class InferenceTraceContext(_NoOpTraceContext):
    @classmethod
    def enabled(
        cls,
        writer: TraceWriter,
        thread_id: AgentThreadId,
        codex_turn_id: CodexTurnId,
        model: str,
        provider_name: str,
    ) -> "InferenceTraceContext":
        context = cls()
        context.enabled = True
        context.writer = writer
        context.thread_id = thread_id
        context.codex_turn_id = codex_turn_id
        context.model = model
        context.provider_name = provider_name
        return context

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def start_attempt(self) -> InferenceTraceAttempt:
        writer = getattr(self, "writer", None)
        if writer is not None:
            return InferenceTraceAttempt.enabled(
                writer,
                self.thread_id,
                self.codex_turn_id,
                self.model,
                self.provider_name,
            )
        return InferenceTraceAttempt.disabled()


class ToolDispatchTraceContext(_NoOpTraceContext):
    @classmethod
    def start(cls, writer: TraceWriter, invocation: "ToolDispatchInvocation") -> "ToolDispatchTraceContext":
        if _suppresses_tool_dispatch_trace(invocation):
            return cls.disabled()
        context = cls()
        context.enabled = True
        context.writer = writer
        context.thread_id = invocation.thread_id
        context.codex_turn_id = invocation.codex_turn_id
        context.tool_call_id = invocation.tool_call_id
        _record_tool_dispatch_started(context, invocation)
        return context

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def record_completed(self, status: ExecutionStatus, result: Any) -> None:
        if not self.is_enabled():
            return None
        if isinstance(result, ToolDispatchResult):
            if result.type == "direct_response":
                response = {"type": "direct_response", "response_item": result.value}
            elif result.type == "code_mode_response":
                response = {"type": "code_mode_response", "value": result.value}
            else:
                response = {"type": result.type, "value": result.value}
        else:
            response = {"type": "direct_response", "response_item": result}
        _append_tool_dispatch_ended(self, status, response)
        return None

    def record_failed(self, error: Any) -> None:
        if self.is_enabled():
            _append_tool_dispatch_ended(
                self,
                ExecutionStatus.FAILED,
                {"type": "error", "error": str(error)},
            )
        return None


@dataclass
class ThreadStartedTraceMetadata:
    thread_id: str
    agent_path: str
    task_name: str | None
    nickname: str | None
    agent_role: str | None
    session_source: Any
    cwd: Path
    rollout_path: Path | None
    model: str
    provider_name: str
    approval_policy: str
    sandbox_policy: str


@dataclass
class AgentResultTracePayload:
    child_agent_path: str
    message: str
    status: Any


class ThreadTraceContext(_NoOpTraceContext):
    @classmethod
    def start_root_or_disabled(cls, metadata: ThreadStartedTraceMetadata) -> "ThreadTraceContext":
        root = os.environ.get(CODEX_ROLLOUT_TRACE_ROOT_ENV)
        if not root:
            return cls.disabled()
        return cls.start_root_in_root_for_test(root, metadata)

    @classmethod
    def start_root_in_root_for_test(cls, root: str | os.PathLike[str], metadata: ThreadStartedTraceMetadata) -> "ThreadTraceContext":
        context = cls()
        context.enabled = True
        trace_id = str(uuid.uuid4())
        context.writer = TraceWriter.create(
            Path(root) / f"trace-{trace_id}-{metadata.thread_id}",
            trace_id,
            metadata.thread_id,
            metadata.thread_id,
        )
        context.root_thread_id = metadata.thread_id
        context.thread_id = metadata.thread_id
        context.writer.append(RawTraceEventPayload.variant("RolloutStarted", trace_id=context.writer.trace_id, root_thread_id=metadata.thread_id))
        context._record_thread_started(metadata)
        return context

    @classmethod
    def start(
        cls,
        writer: TraceWriter,
        root_thread_id: AgentThreadId,
        metadata: ThreadStartedTraceMetadata,
    ) -> "ThreadTraceContext":
        context = cls()
        context.enabled = True
        context.writer = writer
        context.root_thread_id = root_thread_id
        context.thread_id = metadata.thread_id
        context._record_thread_started(metadata)
        return context

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def record_ended(self, status: RolloutStatus) -> None:
        writer = getattr(self, "writer", None)
        if writer is not None:
            thread_id = getattr(self, "thread_id", writer.root_thread_id)
            writer.append(
                RawTraceEventPayload.variant(
                    "ThreadEnded",
                    thread_id=thread_id,
                    status=status,
                )
            )
            if thread_id == getattr(self, "root_thread_id", writer.root_thread_id):
                writer.append(RawTraceEventPayload.variant("RolloutEnded", status=status))

    def start_child_thread_trace_or_disabled(self, metadata: ThreadStartedTraceMetadata) -> "ThreadTraceContext":
        writer = getattr(self, "writer", None)
        if writer is None:
            return ThreadTraceContext.disabled()
        return ThreadTraceContext.start(
            writer,
            getattr(self, "root_thread_id", writer.root_thread_id),
            metadata,
        )

    def record_protocol_event(self, event: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return None
        event_type = _wrapped_protocol_event_type(event)
        if event_type is None:
            return None
        event_payload = writer.write_json_payload(RawPayloadKind.PROTOCOL_EVENT, event)
        writer.append(
            RawTraceEventPayload.variant(
                "ProtocolEventObserved",
                event_type=event_type,
                event_payload=event_payload,
            )
        )
        return None

    def record_codex_turn_event(self, default_turn_id: str, event: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return None
        thread_id = getattr(self, "thread_id", writer.root_thread_id)
        trace_event = _codex_turn_trace_event(thread_id, default_turn_id, event)
        if trace_event is None:
            return None
        context_turn_id, payload = trace_event
        writer.append_with_context(
            RawTraceEventContext(thread_id=thread_id, codex_turn_id=context_turn_id),
            payload,
        )
        return None

    def record_tool_call_event(self, codex_turn_id: str, event: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return None
        trace_event = _tool_runtime_trace_event(event)
        if trace_event is None:
            return None
        event_kind, tool_call_id, status = trace_event
        runtime_payload = writer.write_json_payload(RawPayloadKind.TOOL_RUNTIME_EVENT, event)
        payload_name = "ToolCallRuntimeStarted" if event_kind == "started" else "ToolCallRuntimeEnded"
        fields: dict[str, Any] = {
            "tool_call_id": tool_call_id,
            "runtime_payload": runtime_payload,
        }
        if status is not None:
            fields["status"] = status
        writer.append_with_context(
            RawTraceEventContext(
                thread_id=getattr(self, "thread_id", writer.root_thread_id),
                codex_turn_id=codex_turn_id,
            ),
            RawTraceEventPayload.variant(payload_name, **fields),
        )
        return None

    def record_agent_result_interaction(self, child_codex_turn_id: str, parent_thread_id: str, payload: AgentResultTracePayload) -> None:
        return None

    def record_codex_turn_started(self, codex_turn_id: str) -> None:
        writer = getattr(self, "writer", None)
        if writer is not None:
            thread_id = getattr(self, "thread_id", writer.root_thread_id)
            writer.append_with_context(
                RawTraceEventContext(thread_id=thread_id, codex_turn_id=codex_turn_id),
                RawTraceEventPayload.variant(
                    "CodexTurnStarted",
                    codex_turn_id=codex_turn_id,
                    thread_id=thread_id,
                ),
            )

    def _record_thread_started(self, metadata: ThreadStartedTraceMetadata) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return
        metadata_payload = writer.write_json_payload(RawPayloadKind.SESSION_METADATA, metadata)
        writer.append(
            RawTraceEventPayload.variant(
                "ThreadStarted",
                thread_id=metadata.thread_id,
                agent_path=metadata.agent_path,
                metadata_payload=metadata_payload,
            )
        )

    def start_code_cell_trace(self, *args: Any, **kwargs: Any) -> CodeCellTraceContext:
        codex_turn_id = args[0] if len(args) > 0 else kwargs.get("codex_turn_id")
        runtime_cell_id = args[1] if len(args) > 1 else kwargs.get("runtime_cell_id")
        model_visible_call_id = args[2] if len(args) > 2 else kwargs.get("model_visible_call_id")
        source_js = args[3] if len(args) > 3 else kwargs.get("source_js")
        context = self.code_cell_trace_context(codex_turn_id, runtime_cell_id)
        if model_visible_call_id is not None and source_js is not None:
            context.record_started(model_visible_call_id, source_js)
        return context

    def code_cell_trace_context(self, *args: Any, **kwargs: Any) -> CodeCellTraceContext:
        writer = getattr(self, "writer", None)
        if writer is not None:
            codex_turn_id = args[0] if len(args) > 0 else kwargs.get("codex_turn_id")
            runtime_cell_id = args[1] if len(args) > 1 else kwargs.get("runtime_cell_id")
            if codex_turn_id is not None and runtime_cell_id is not None:
                return CodeCellTraceContext.enabled(
                    writer,
                    getattr(self, "thread_id", writer.root_thread_id),
                    codex_turn_id,
                    runtime_cell_id,
                )
        return CodeCellTraceContext.disabled()

    def start_tool_dispatch_trace(self, invocation: Any) -> ToolDispatchTraceContext:
        writer = getattr(self, "writer", None)
        if writer is None:
            return ToolDispatchTraceContext.disabled()
        resolved = invocation() if callable(invocation) else invocation
        if resolved is None:
            return ToolDispatchTraceContext.disabled()
        return ToolDispatchTraceContext.start(writer, resolved)

    def inference_trace_context(self, *args: Any, **kwargs: Any) -> InferenceTraceContext:
        writer = getattr(self, "writer", None)
        if writer is not None:
            codex_turn_id = args[0] if len(args) > 0 else kwargs.get("codex_turn_id")
            model = args[1] if len(args) > 1 else kwargs.get("model")
            provider_name = args[2] if len(args) > 2 else kwargs.get("provider_name")
            if codex_turn_id is not None and model is not None and provider_name is not None:
                return InferenceTraceContext.enabled(
                    writer,
                    getattr(self, "thread_id", writer.root_thread_id),
                    codex_turn_id,
                    model,
                    provider_name,
                )
        return InferenceTraceContext.disabled()

    def compaction_trace_context(self, *args: Any, **kwargs: Any) -> "CompactionTraceContext":
        writer = getattr(self, "writer", None)
        if writer is not None:
            codex_turn_id = args[0] if len(args) > 0 else kwargs.get("codex_turn_id")
            compaction_id = args[1] if len(args) > 1 else kwargs.get("compaction_id")
            model = args[2] if len(args) > 2 else kwargs.get("model")
            provider_name = args[3] if len(args) > 3 else kwargs.get("provider_name")
            if codex_turn_id is not None and compaction_id is not None and model is not None and provider_name is not None:
                return CompactionTraceContext.enabled(
                    writer,
                    getattr(self, "thread_id", writer.root_thread_id),
                    codex_turn_id,
                    compaction_id,
                    model,
                    provider_name,
                )
        return CompactionTraceContext.disabled()

    def start_mcp_call_trace(self, tool_call_id: str) -> McpCallTraceContext:
        writer = getattr(self, "writer", None)
        if writer is None:
            return McpCallTraceContext.disabled()
        mcp_call_id = str(uuid.uuid4())
        writer.append(
            RawTraceEventPayload.variant(
                "McpToolCallCorrelationAssigned",
                tool_call_id=tool_call_id,
                mcp_call_id=mcp_call_id,
            )
        )
        return McpCallTraceContext.enabled(mcp_call_id)


class CompactionTraceContext(_NoOpTraceContext):
    @classmethod
    def enabled(
        cls,
        writer: TraceWriter,
        thread_id: AgentThreadId,
        codex_turn_id: CodexTurnId,
        compaction_id: CompactionId,
        model: str,
        provider_name: str,
    ) -> "CompactionTraceContext":
        context = cls()
        context.enabled = True
        context.writer = writer
        context.thread_id = thread_id
        context.codex_turn_id = codex_turn_id
        context.compaction_id = compaction_id
        context.model = model
        context.provider_name = provider_name
        return context

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def start_attempt(self, request: Any) -> "CompactionTraceAttempt":
        writer = getattr(self, "writer", None)
        if writer is None:
            return CompactionTraceAttempt.disabled()
        attempt = CompactionTraceAttempt.enabled(
            writer,
            self.thread_id,
            self.codex_turn_id,
            self.compaction_id,
            self.model,
            self.provider_name,
        )
        attempt.record_started(request)
        return attempt

    def record_installed(self, checkpoint: "CompactionCheckpointTracePayload") -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return
        checkpoint_payload = writer.write_json_payload(RawPayloadKind.COMPACTION_CHECKPOINT, checkpoint)
        writer.append_with_context(
            RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
            RawTraceEventPayload.variant(
                "CompactionInstalled",
                compaction_id=self.compaction_id,
                checkpoint_payload=checkpoint_payload,
            ),
        )


class CompactionTraceAttempt(_NoOpTraceContext):
    _next_request_ordinal = 1

    @classmethod
    def enabled(
        cls,
        writer: TraceWriter,
        thread_id: AgentThreadId,
        codex_turn_id: CodexTurnId,
        compaction_id: CompactionId,
        model: str,
        provider_name: str,
    ) -> "CompactionTraceAttempt":
        attempt = cls()
        attempt.enabled = True
        attempt.writer = writer
        attempt.thread_id = thread_id
        attempt.codex_turn_id = codex_turn_id
        attempt.compaction_id = compaction_id
        attempt.model = model
        attempt.provider_name = provider_name
        attempt.compaction_request_id = f"compaction_request:{cls._next_request_ordinal}"
        cls._next_request_ordinal += 1
        return attempt

    def is_enabled(self) -> bool:
        return bool(self.__dict__.get("enabled", False))

    def record_started(self, request: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return
        request_payload = writer.write_json_payload(RawPayloadKind.COMPACTION_REQUEST, request)
        writer.append_with_context(
            RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
            RawTraceEventPayload.variant(
                "CompactionRequestStarted",
                compaction_id=self.compaction_id,
                compaction_request_id=self.compaction_request_id,
                thread_id=self.thread_id,
                codex_turn_id=self.codex_turn_id,
                model=self.model,
                provider_name=self.provider_name,
                request_payload=request_payload,
            ),
        )

    def record_completed(self, output_items: list[Any]) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return
        response_payload = writer.write_json_payload(
            RawPayloadKind.COMPACTION_RESPONSE,
            {"output_items": output_items},
        )
        writer.append_with_context(
            RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
            RawTraceEventPayload.variant(
                "CompactionRequestCompleted",
                compaction_id=self.compaction_id,
                compaction_request_id=self.compaction_request_id,
                response_payload=response_payload,
            ),
        )

    def record_result(self, result: Any) -> None:
        if isinstance(result, Exception):
            self.record_failed(result)
        else:
            self.record_completed(result)

    def record_failed(self, error: Any) -> None:
        writer = getattr(self, "writer", None)
        if writer is None:
            return
        writer.append_with_context(
            RawTraceEventContext(thread_id=self.thread_id, codex_turn_id=self.codex_turn_id),
            RawTraceEventPayload.variant(
                "CompactionRequestFailed",
                compaction_id=self.compaction_id,
                compaction_request_id=self.compaction_request_id,
                error=str(error),
            ),
        )


@dataclass
class CompactionCheckpointTracePayload:
    input_history: list[Any] = field(default_factory=list)
    replacement_history: list[Any] = field(default_factory=list)


@dataclass
class ToolDispatchInvocation:
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId
    tool_call_id: ToolCallId
    tool_name: str
    tool_namespace: str | None
    requester: Any
    payload: Any


@dataclass
class ToolDispatchRequester:
    type: str
    model_visible_call_id: str | None = None
    runtime_cell_id: str | None = None
    runtime_tool_call_id: str | None = None

    @classmethod
    def Model(cls, model_visible_call_id: str) -> "ToolDispatchRequester":
        return cls("model", model_visible_call_id=model_visible_call_id)

    @classmethod
    def CodeCell(
        cls,
        *,
        runtime_cell_id: str,
        runtime_tool_call_id: str,
    ) -> "ToolDispatchRequester":
        return cls(
            "code_cell",
            runtime_cell_id=runtime_cell_id,
            runtime_tool_call_id=runtime_tool_call_id,
        )


@dataclass
class ToolDispatchPayload:
    type: str
    value: Any

    @classmethod
    def Function(cls, arguments: str) -> "ToolDispatchPayload":
        return cls("function", arguments)

    @classmethod
    def ToolSearch(cls, arguments: Any) -> "ToolDispatchPayload":
        return cls("tool_search", arguments)

    @classmethod
    def Custom(cls, input: str) -> "ToolDispatchPayload":
        return cls("custom", input)

    @classmethod
    def LocalShell(
        cls,
        *,
        command: list[str],
        workdir: str | None = None,
        timeout_ms: int | None = None,
        sandbox_permissions: Any = None,
        prefix_rule: list[str] | None = None,
        additional_permissions: Any = None,
        justification: str | None = None,
    ) -> "ToolDispatchPayload":
        return cls(
            "local_shell",
            {
                "command": command,
                "workdir": workdir,
                "timeout_ms": timeout_ms,
                "sandbox_permissions": sandbox_permissions,
                "prefix_rule": prefix_rule,
                "additional_permissions": additional_permissions,
                "justification": justification,
            },
        )


@dataclass
class ToolDispatchResult:
    type: str
    value: Any

    @classmethod
    def DirectResponse(cls, response_item: Any) -> "ToolDispatchResult":
        return cls("direct_response", response_item)

    @classmethod
    def CodeModeResponse(cls, value: Any) -> "ToolDispatchResult":
        return cls("code_mode_response", value)


def _suppresses_tool_dispatch_trace(invocation: ToolDispatchInvocation) -> bool:
    return (
        isinstance(invocation.payload, ToolDispatchPayload)
        and invocation.payload.type == "custom"
        and invocation.tool_namespace is None
        and invocation.tool_name == "exec"
    )


def _record_tool_dispatch_started(
    context: ToolDispatchTraceContext,
    invocation: ToolDispatchInvocation,
) -> None:
    payload = _tool_dispatch_payload_json(invocation.payload)
    request = {
        "tool_name": invocation.tool_name,
        "tool_namespace": invocation.tool_namespace,
        "payload": payload,
    }
    request_payload = context.writer.write_json_payload(RawPayloadKind.TOOL_INVOCATION, request)
    model_visible_call_id, code_mode_runtime_tool_id, requester = _tool_dispatch_requester_fields(
        invocation.requester
    )
    context.writer.append_with_context(
        RawTraceEventContext(
            thread_id=invocation.thread_id,
            codex_turn_id=invocation.codex_turn_id,
        ),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id=invocation.tool_call_id,
            model_visible_call_id=model_visible_call_id,
            code_mode_runtime_tool_id=code_mode_runtime_tool_id,
            requester=requester,
            kind=_dispatched_tool_kind(invocation.tool_name),
            summary=ToolCallSummary.Generic(
                label=_dispatched_tool_label(invocation.tool_name, invocation.tool_namespace),
                input_preview=_tool_dispatch_payload_preview(invocation.payload),
            ),
            invocation_payload=request_payload,
        ),
    )


def _append_tool_dispatch_ended(
    context: ToolDispatchTraceContext,
    status: ExecutionStatus,
    response: dict[str, Any],
) -> None:
    response_payload = context.writer.write_json_payload(RawPayloadKind.TOOL_RESULT, response)
    context.writer.append_with_context(
        RawTraceEventContext(
            thread_id=context.thread_id,
            codex_turn_id=context.codex_turn_id,
        ),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id=context.tool_call_id,
            status=status,
            result_payload=response_payload,
        ),
        )


def _code_cell_status_for_runtime_response(response: Any) -> CodeCellRuntimeStatus:
    response_type = response.get("type") if isinstance(response, dict) else getattr(response, "type", None)
    if response_type == "yielded":
        return CodeCellRuntimeStatus.YIELDED
    if response_type == "terminated":
        return CodeCellRuntimeStatus.TERMINATED
    if response_type == "result":
        error_text = response.get("error_text") if isinstance(response, dict) else getattr(response, "error_text", None)
        return CodeCellRuntimeStatus.FAILED if error_text is not None else CodeCellRuntimeStatus.COMPLETED
    return CodeCellRuntimeStatus.COMPLETED


def _code_cell_response_payload(writer: TraceWriter, response: Any) -> RawPayloadRef:
    response_payload = response.to_mapping() if hasattr(response, "to_mapping") else response
    return writer.write_json_payload(
        RawPayloadKind.TOOL_RESULT,
        {"response": response_payload},
    )


def _tool_dispatch_requester_fields(requester: Any) -> tuple[str | None, str | None, RawToolCallRequester]:
    requester_type = requester.type if isinstance(requester, ToolDispatchRequester) else getattr(requester, "type", None)
    if requester_type == "code_cell":
        runtime_cell_id = getattr(requester, "runtime_cell_id", None)
        runtime_tool_call_id = getattr(requester, "runtime_tool_call_id", None)
        return None, runtime_tool_call_id, RawToolCallRequester.CodeCell(runtime_cell_id or "")
    model_visible_call_id = getattr(requester, "model_visible_call_id", None)
    return model_visible_call_id, None, RawToolCallRequester.Model()


def _dispatched_tool_kind(tool_name: str) -> ToolCallKind:
    if tool_name in {"exec_command", "local_shell", "shell", "shell_command"}:
        return ToolCallKind.ExecCommand()
    if tool_name == "write_stdin":
        return ToolCallKind.WriteStdin()
    if tool_name == "apply_patch":
        return ToolCallKind.ApplyPatch()
    if tool_name in {"web_search", "web_search_preview"}:
        return ToolCallKind.Web()
    if tool_name in {"image_generation", "image_query"}:
        return ToolCallKind.ImageGeneration()
    if tool_name == "spawn_agent":
        return ToolCallKind.SpawnAgent()
    if tool_name == "send_message":
        return ToolCallKind.SendMessage()
    if tool_name == "followup_task":
        return ToolCallKind.AssignAgentTask()
    if tool_name == "wait_agent":
        return ToolCallKind.WaitAgent()
    if tool_name == "close_agent":
        return ToolCallKind.CloseAgent()
    return ToolCallKind.Other(name=tool_name)


def _dispatched_tool_label(tool_name: str, tool_namespace: str | None) -> str:
    if tool_namespace is None:
        return tool_name
    return f"{tool_namespace}.{tool_name}"


def _tool_dispatch_payload_json(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, ToolDispatchPayload):
        return {"type": "function", "arguments": str(payload)}
    if payload.type == "function":
        return {"type": "function", "arguments": payload.value}
    if payload.type == "tool_search":
        return {"type": "tool_search", "arguments": payload.value}
    if payload.type == "custom":
        return {"type": "custom", "input": payload.value}
    if payload.type == "local_shell" and isinstance(payload.value, dict):
        return {"type": "local_shell", **payload.value}
    return {"type": payload.type, "value": payload.value}


def _tool_dispatch_payload_preview(payload: Any) -> str:
    if not isinstance(payload, ToolDispatchPayload):
        return _truncate_preview(str(payload))
    if payload.type == "function":
        return _truncate_preview(str(payload.value))
    if payload.type == "tool_search":
        query = payload.value.get("query") if isinstance(payload.value, dict) else getattr(payload.value, "query", payload.value)
        return _truncate_preview(str(query))
    if payload.type == "custom":
        return _truncate_preview(str(payload.value))
    if payload.type == "local_shell" and isinstance(payload.value, dict):
        return _truncate_preview(" ".join(str(part) for part in payload.value.get("command", [])))
    return _truncate_preview(str(payload.value))


def _truncate_preview(value: str) -> str:
    max_preview_chars = 160
    if len(value) <= max_preview_chars:
        return value
    return value[:max_preview_chars] + "..."


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


def _wrapped_protocol_event_type(event: Any) -> str | None:
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
        _replay_start_inference_call(
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
        _replay_start_compaction_request(
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
        _replay_start_tool_call(
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
        task_name = spawn.get("task_name") or _task_name_from_agent_path(agent_path)
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


@dataclass(frozen=True)
class _NormalizedConversationItem:
    role: ConversationRole
    channel: ConversationChannel | None
    kind: ConversationItemKind
    body: ConversationBody
    call_id: str | None = None


@dataclass(frozen=True)
class _PendingCodeCellStart:
    seq: RawEventSeq
    wall_time_unix_ms: int
    thread_id: AgentThreadId
    codex_turn_id: CodexTurnId | None
    code_cell_id: CodeCellId
    runtime_cell_id: str
    model_visible_call_id: ModelVisibleCallId
    source_js: str


@dataclass(frozen=True)
class _PendingCodeCellLifecycleEvent:
    seq: RawEventSeq
    wall_time_unix_ms: int
    type: str
    runtime_cell_id: str | None = None
    status: CodeCellRuntimeStatus | None = None


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
    normalized = [_normalize_model_item(item, request_payload) for item in request_items]
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
        delta_item_ids = _reconcile_conversation_items(
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
        item_ids = _reconcile_conversation_items(
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
    normalized = [_normalize_model_item(item, response_payload) for item in output_items]
    append_at = len(rollout.thread_conversation_snapshots.get(inference.thread_id, []))
    item_ids = _reconcile_conversation_items(
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


def _reconcile_conversation_items(
    rollout: RolloutTrace,
    items: list[_NormalizedConversationItem],
    *,
    thread_id: str,
    codex_turn_id: str,
    wall_time_unix_ms: int,
    produced_by: list[ProducerRef],
    start_index: int,
    append_only: bool,
    snapshot_override: list[ConversationItemId] | None = None,
) -> list[ConversationItemId]:
    previous_snapshot = list(
        snapshot_override
        if snapshot_override is not None
        else rollout.thread_conversation_snapshots.get(thread_id, [])
    )
    item_ids: list[ConversationItemId] = []
    for offset, item in enumerate(items):
        _ensure_call_id_consistency(rollout, thread_id, item)
        index = start_index + offset
        if index < len(previous_snapshot) and _conversation_item_matches(
            rollout.conversation_items.get(previous_snapshot[index]), item
        ):
            item_id = previous_snapshot[index]
        elif not append_only:
            item_id = _find_matching_snapshot_item(rollout, previous_snapshot, item_ids, item)
            if item_id is None:
                item_id = _create_conversation_item(
                    rollout,
                    thread_id,
                    codex_turn_id,
                    wall_time_unix_ms,
                    item,
                    produced_by,
                )
        else:
            item_id = _create_conversation_item(
                rollout,
                thread_id,
                codex_turn_id,
                wall_time_unix_ms,
                item,
                produced_by,
            )
        _update_conversation_item_from_sighting(rollout, item_id, item, produced_by)
        _attach_model_visible_tool_item(rollout, item_id, item.call_id, item.kind)
        _attach_model_visible_code_cell_item(rollout, item_id, item.call_id, item.kind)
        _resolve_pending_agent_edges_for_item(rollout, item_id)
        item_ids.append(item_id)
    return item_ids


def _create_conversation_item(
    rollout: RolloutTrace,
    thread_id: str,
    codex_turn_id: str | None,
    first_seen_at_unix_ms: int,
    item: _NormalizedConversationItem,
    produced_by: list[ProducerRef],
) -> ConversationItemId:
    item_id = f"conversation_item:{rollout._next_conversation_item_ordinal}"
    rollout._next_conversation_item_ordinal += 1
    rollout.conversation_items[item_id] = ConversationItem(
        item_id=item_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        first_seen_at_unix_ms=first_seen_at_unix_ms,
        role=item.role,
        channel=item.channel,
        kind=item.kind,
        body=item.body,
        call_id=item.call_id,
        produced_by=list(produced_by),
    )
    return item_id


def _update_conversation_item_from_sighting(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
    normalized: _NormalizedConversationItem,
    produced_by: list[ProducerRef],
) -> None:
    item = rollout.conversation_items[item_id]
    if item.kind == ConversationItemKind.REASONING:
        item.body = _merge_reasoning_body(item.body, normalized.body)
    for producer in produced_by:
        if producer not in item.produced_by:
            item.produced_by.append(producer)


def _append_thread_conversation_items(
    rollout: RolloutTrace,
    thread_id: str,
    item_ids: list[ConversationItemId],
) -> None:
    thread = rollout.threads.get(thread_id)
    if thread is None:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    for item_id in item_ids:
        if item_id not in thread.conversation_item_ids:
            thread.conversation_item_ids.append(item_id)


def _find_matching_snapshot_item(
    rollout: RolloutTrace,
    previous_snapshot: list[ConversationItemId],
    used_item_ids: list[ConversationItemId],
    normalized: _NormalizedConversationItem,
) -> ConversationItemId | None:
    for item_id in previous_snapshot:
        if item_id not in used_item_ids and _conversation_item_matches(
            rollout.conversation_items.get(item_id), normalized
        ):
            return item_id
    return None


def _reconcile_detached_conversation_items(
    rollout: RolloutTrace,
    items: list[_NormalizedConversationItem],
    *,
    thread_id: str,
    codex_turn_id: str,
    wall_time_unix_ms: int,
    produced_by: list[ProducerRef],
    candidates: list[ConversationItemId],
) -> list[ConversationItemId]:
    item_ids: list[ConversationItemId] = []
    for item in items:
        _ensure_call_id_consistency(rollout, thread_id, item)
        item_id = _find_matching_snapshot_item(rollout, candidates, item_ids, item)
        if item_id is None:
            item_id = _create_conversation_item(
                rollout,
                thread_id,
                codex_turn_id,
                wall_time_unix_ms,
                item,
                produced_by,
            )
        _update_conversation_item_from_sighting(rollout, item_id, item, produced_by)
        _attach_model_visible_tool_item(rollout, item_id, item.call_id, item.kind)
        _attach_model_visible_code_cell_item(rollout, item_id, item.call_id, item.kind)
        item_ids.append(item_id)
    return item_ids


def _ensure_call_id_consistency(
    rollout: RolloutTrace,
    thread_id: str,
    normalized: _NormalizedConversationItem,
) -> None:
    if normalized.call_id is None:
        return
    for item in rollout.conversation_items.values():
        if (
            item.thread_id == thread_id
            and item.call_id == normalized.call_id
            and item.kind == normalized.kind
            and not _conversation_item_matches(item, normalized)
        ):
            raise ValueError(
                f"model-visible call id {normalized.call_id} was reused with different content"
            )


def _conversation_item_matches(
    item: ConversationItem | None,
    normalized: _NormalizedConversationItem,
) -> bool:
    if item is None:
        return False
    if item.kind == ConversationItemKind.REASONING and normalized.kind == ConversationItemKind.REASONING:
        body_matches = _reasoning_body_matches(item.body, normalized.body)
    else:
        body_matches = _conversation_body_matches(item.body, normalized.body)
    return (
        item.role == normalized.role
        and item.channel == normalized.channel
        and item.kind == normalized.kind
        and body_matches
        and item.call_id == normalized.call_id
    )


def _conversation_body_matches(left: ConversationBody, right: ConversationBody) -> bool:
    if len(left.parts) != len(right.parts):
        return False
    for left_part, right_part in zip(left.parts, right.parts):
        if left_part.type == "json" and right_part.type == "json":
            if left_part.summary != right_part.summary:
                return False
        elif left_part != right_part:
            return False
    return True


def _reasoning_body_matches(left: ConversationBody, right: ConversationBody) -> bool:
    if _conversation_body_matches(left, right):
        return True
    left_encoded = _reasoning_encoded_part(left)
    right_encoded = _reasoning_encoded_part(right)
    return left_encoded is not None and left_encoded == right_encoded


def _reasoning_encoded_part(body: ConversationBody) -> tuple[str | None, str | None] | None:
    for part in body.parts:
        if part.type == "encoded" and part.label == "encrypted_content":
            return (part.label, part.value)
    return None


def _merge_reasoning_body(existing: ConversationBody, incoming: ConversationBody) -> ConversationBody:
    if _conversation_body_matches(existing, incoming):
        return existing
    if not _reasoning_body_matches(existing, incoming):
        raise ValueError("reasoning item merge attempted with different encrypted_content identity")
    existing_text = [part for part in existing.parts if part.type == "text"]
    existing_summary = [part for part in existing.parts if part.type == "summary"]
    if existing_text and existing_summary:
        return existing
    incoming_text = [part for part in incoming.parts if part.type == "text"]
    incoming_summary = [part for part in incoming.parts if part.type == "summary"]
    encoded = [part for part in existing.parts if part.type == "encoded"] or [
        part for part in incoming.parts if part.type == "encoded"
    ]
    return ConversationBody((existing_text or incoming_text) + (existing_summary or incoming_summary) + encoded)


def _normalize_model_item(item: Any, raw_payload: RawPayloadRef) -> _NormalizedConversationItem:
    if not isinstance(item, dict):
        raise ValueError(f"model item in payload {raw_payload.raw_payload_id} did not contain a string type")
    item_type = item.get("type")
    if not isinstance(item_type, str):
        raise ValueError(f"model item in payload {raw_payload.raw_payload_id} did not contain a string type")
    if item_type == "message":
        role_value = item.get("role")
        if not isinstance(role_value, str):
            raise ValueError(f"message item in payload {raw_payload.raw_payload_id} did not contain a string role")
        role = _role_from_str(role_value, raw_payload)
        return _NormalizedConversationItem(
            role=role,
            channel=_channel_from_phase(item.get("phase")),
            kind=ConversationItemKind.MESSAGE,
            body=ConversationBody(_content_parts(item.get("content"), raw_payload)),
        )
    if item_type == "reasoning":
        return _normalize_reasoning_item(item, raw_payload)
    if item_type == "function_call":
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL,
            body=_raw_text_or_json_body(item.get("arguments"), raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type == "function_call_output":
        return _NormalizedConversationItem(
            role=ConversationRole.TOOL,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL_OUTPUT,
            body=_tool_output_body(item.get("output"), raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type == "custom_tool_call":
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.CUSTOM_TOOL_CALL,
            body=_custom_tool_call_body(item, raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type == "custom_tool_call_output":
        return _NormalizedConversationItem(
            role=ConversationRole.TOOL,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT,
            body=_tool_output_body(item.get("output"), raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type in {"tool_search_call", "web_search_call", "image_generation_call", "local_shell_call"}:
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL,
            body=_json_body(item, raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type in {"tool_search_output", "mcp_tool_call_output"}:
        return _NormalizedConversationItem(
            role=ConversationRole.TOOL,
            channel=ConversationChannel.COMMENTARY,
            kind=ConversationItemKind.FUNCTION_CALL_OUTPUT,
            body=_json_body(item, raw_payload),
            call_id=_optional_str(item.get("call_id")),
        )
    if item_type in {"compaction", "compaction_summary", "context_compaction"}:
        return _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=ConversationChannel.SUMMARY,
            kind=ConversationItemKind.MESSAGE,
            body=_compaction_body(item, raw_payload),
        )
    raise ValueError(f"unsupported model item type {item_type} in payload {raw_payload.raw_payload_id}")


def _normalize_reasoning_item(item: dict[str, Any], raw_payload: RawPayloadRef) -> _NormalizedConversationItem:
    parts: list[ConversationPart] = []
    _append_reasoning_parts(item, "content", raw_payload, parts, summary=False)
    _append_reasoning_parts(item, "summary", raw_payload, parts, summary=True)
    encrypted_content = item.get("encrypted_content")
    if encrypted_content is not None:
        if not isinstance(encrypted_content, str):
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had non-string encrypted_content")
        parts.append(ConversationPart.Encoded("encrypted_content", encrypted_content))
    if not parts:
        raise ValueError(
            f"reasoning item in payload {raw_payload.raw_payload_id} contained no content, summary, or encrypted_content"
        )
    return _NormalizedConversationItem(
        role=ConversationRole.ASSISTANT,
        channel=ConversationChannel.ANALYSIS,
        kind=ConversationItemKind.REASONING,
        body=ConversationBody(parts),
    )


def _append_reasoning_parts(
    item: dict[str, Any],
    key: str,
    raw_payload: RawPayloadRef,
    parts: list[ConversationPart],
    *,
    summary: bool,
) -> None:
    if key not in item:
        return
    values = item.get(key)
    if key == "content" and values is None:
        return
    if not isinstance(values, list):
        raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had non-array {key}")
    for content_item in values:
        if not isinstance(content_item, dict):
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had {key} entry without string type")
        item_type = content_item.get("type")
        if summary:
            if item_type != "summary_text":
                raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had unsupported summary type {item_type}")
        elif item_type not in {"reasoning_text", "text"}:
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had unsupported content type {item_type}")
        text = content_item.get("text")
        if not isinstance(text, str):
            expected = "summary" if summary else "content"
            raise ValueError(f"reasoning item in payload {raw_payload.raw_payload_id} had {expected} entry without string text")
        parts.append(ConversationPart.Summary(text) if summary else ConversationPart.Text(text))


def _custom_tool_call_body(item: dict[str, Any], raw_payload: RawPayloadRef) -> ConversationBody:
    input_value = item.get("input")
    if not isinstance(input_value, str):
        return _json_body(item, raw_payload)
    if item.get("name") == "exec":
        return ConversationBody([ConversationPart.Code("javascript", input_value)])
    return ConversationBody([ConversationPart.Text(input_value)])


def _role_from_str(role: Any, raw_payload: RawPayloadRef) -> ConversationRole:
    try:
        return ConversationRole(role)
    except ValueError as exc:
        raise ValueError(f"unsupported message role {role} in payload {raw_payload.raw_payload_id}") from exc


def _channel_from_phase(phase: Any) -> ConversationChannel | None:
    if phase == "commentary":
        return ConversationChannel.COMMENTARY
    if phase == "final_answer":
        return ConversationChannel.FINAL
    if phase == "summary":
        return ConversationChannel.SUMMARY
    return None


def _content_parts(content: Any, raw_payload: RawPayloadRef) -> list[ConversationPart]:
    if not isinstance(content, list):
        return [ConversationPart.PayloadRef("content", raw_payload.raw_payload_id)]
    parts: list[ConversationPart] = []
    for part in content:
        if not isinstance(part, dict):
            parts.append(ConversationPart.PayloadRef("content", raw_payload.raw_payload_id))
            continue
        part_type = part.get("type")
        if part_type in {"input_text", "output_text", "text"} and isinstance(part.get("text"), str):
            parts.append(ConversationPart.Text(part["text"]))
        elif part_type == "input_image":
            parts.append(ConversationPart.PayloadRef("input_image", raw_payload.raw_payload_id))
        elif isinstance(part_type, str):
            parts.append(ConversationPart.PayloadRef(part_type, raw_payload.raw_payload_id))
        else:
            parts.append(ConversationPart.PayloadRef("content", raw_payload.raw_payload_id))
    return parts or [ConversationPart.PayloadRef("empty_content", raw_payload.raw_payload_id)]


def _raw_text_or_json_body(value: Any, raw_payload: RawPayloadRef) -> ConversationBody:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ConversationBody([ConversationPart.Text(value)])
        return _json_body(parsed, raw_payload)
    if value is not None:
        return _json_body(value, raw_payload)
    return ConversationBody([ConversationPart.PayloadRef("payload", raw_payload.raw_payload_id)])


def _tool_output_body(output: Any, raw_payload: RawPayloadRef) -> ConversationBody:
    if isinstance(output, str):
        return ConversationBody([ConversationPart.Text(output)])
    if isinstance(output, list):
        return ConversationBody(_content_parts(output, raw_payload))
    if output is not None:
        return _json_body(output, raw_payload)
    return ConversationBody([ConversationPart.PayloadRef("tool_output", raw_payload.raw_payload_id)])


def _compaction_body(item: dict[str, Any], raw_payload: RawPayloadRef) -> ConversationBody:
    encrypted_content = item.get("encrypted_content")
    if not isinstance(encrypted_content, str):
        raise ValueError(f"compaction item in payload {raw_payload.raw_payload_id} did not contain string encrypted_content")
    return ConversationBody([ConversationPart.Encoded("encrypted_content", encrypted_content)])


def _json_body(value: Any, raw_payload: RawPayloadRef) -> ConversationBody:
    return ConversationBody([ConversationPart.Json(_summarize_json(value), raw_payload.raw_payload_id)])


def _summarize_json(value: Any) -> str:
    summary = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    if len(summary) > 240:
        return summary[:240] + "..."
    return summary


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _token_usage_from_value(value: dict[str, Any]) -> TokenUsage:
    return TokenUsage(
        input_tokens=max(int(value.get("input_tokens") or 0), 0),
        cached_input_tokens=max(int(value.get("cached_input_tokens") or 0), 0),
        output_tokens=max(int(value.get("output_tokens") or 0), 0),
        reasoning_output_tokens=max(int(value.get("reasoning_output_tokens") or 0), 0),
    )


def _replay_start_tool_call(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    payload: dict[str, Any],
) -> None:
    tool_call_id = payload["tool_call_id"]
    if tool_call_id in rollout.tool_calls:
        raise ValueError(f"duplicate tool call start for {tool_call_id}")
    model_visible_call_id = _optional_str(payload.get("model_visible_call_id"))
    if model_visible_call_id is not None and _single_tool_for_model_visible_call(rollout, model_visible_call_id) is not None:
        raise ValueError(f"duplicate tool call for model-visible call id {model_visible_call_id}")
    thread_id = _tool_thread_id(rollout, event_thread_id, event_codex_turn_id)
    _validate_tool_turn(rollout, thread_id, event_codex_turn_id)
    requester = _reduce_tool_call_requester(rollout, thread_id, payload.get("requester"))
    invocation_payload = _payload_ref_from_json(payload.get("invocation_payload"))
    kind = _tool_call_kind_from_value(payload.get("kind"))
    summary = _tool_call_summary_from_value(payload.get("summary"))
    rollout.tool_calls[tool_call_id] = ToolCall(
        tool_call_id=tool_call_id,
        mcp_call_id=None,
        model_visible_call_id=model_visible_call_id,
        code_mode_runtime_tool_id=_optional_str(payload.get("code_mode_runtime_tool_id")),
        thread_id=thread_id,
        started_by_codex_turn_id=event_codex_turn_id,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
        requester=requester,
        kind=kind,
        model_visible_call_item_ids=[],
        model_visible_output_item_ids=[],
        summary=summary,
        raw_invocation_payload_id=invocation_payload.raw_payload_id if invocation_payload else None,
    )
    terminal_operation_id = _start_terminal_operation_from_invocation(
        rollout,
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=thread_id,
        tool_call_id=tool_call_id,
        kind=kind,
        invocation_payload=invocation_payload,
    )
    if terminal_operation_id is not None:
        tool_call = rollout.tool_calls[tool_call_id]
        tool_call.terminal_operation_id = terminal_operation_id
        tool_call.summary = ToolCallSummary.Terminal(operation_id=terminal_operation_id)
    _link_tool_call_to_code_cell(rollout, tool_call_id, requester)
    _link_wait_tool_call_from_request_payload(
        rollout,
        thread_id,
        tool_call_id,
        invocation_payload,
    )
    if model_visible_call_id is not None:
        for item in list(rollout.conversation_items.values()):
            if item.thread_id == thread_id and item.call_id == model_visible_call_id:
                _attach_model_visible_tool_item(rollout, item.item_id, item.call_id, item.kind)


def _replay_end_tool_call(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    tool_call_id: str,
    status: ExecutionStatus,
    result_payload: RawPayloadRef | None,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool call end referenced unknown call {tool_call_id}")
    tool_call.execution = ExecutionWindow(
        started_at_unix_ms=tool_call.execution.started_at_unix_ms,
        started_seq=tool_call.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=status,
    )
    tool_call.raw_result_payload_id = result_payload.raw_payload_id if result_payload else None
    if tool_call.terminal_operation_id is not None and not tool_call.raw_runtime_payload_ids:
        _end_terminal_operation(
            rollout,
            seq=seq,
            wall_time_unix_ms=wall_time_unix_ms,
            thread_id=tool_call.thread_id,
            operation_id=tool_call.terminal_operation_id,
            status=status,
            response_payload=result_payload,
        )
    _attach_agent_interaction_tool_result(rollout, tool_call_id, result_payload)


def _assign_mcp_tool_call_correlation(
    rollout: RolloutTrace,
    *,
    tool_call_id: ToolCallId,
    mcp_call_id: McpCallId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"MCP correlation referenced unknown tool call {tool_call_id}")
    if tool_call.mcp_call_id is not None:
        raise ValueError(f"duplicate MCP correlation for tool call {tool_call_id}")
    tool_call.mcp_call_id = mcp_call_id


def _replay_start_tool_runtime_observation(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    tool_call_id: str,
    runtime_payload: RawPayloadRef | None,
) -> None:
    if runtime_payload is None:
        raise ValueError(f"tool runtime start {tool_call_id} missing runtime payload")
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool runtime start referenced unknown call {tool_call_id}")
    _push_unique(tool_call.raw_runtime_payload_ids, runtime_payload.raw_payload_id)
    if tool_call.terminal_operation_id is not None and _terminal_operation_kind(tool_call.kind) is not None:
        raise ValueError(f"tool runtime start would create a second terminal operation for {tool_call_id}")
    terminal_operation_id = _start_terminal_operation_from_runtime(
        rollout,
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=tool_call.thread_id,
        tool_call_id=tool_call_id,
        kind=tool_call.kind,
        runtime_payload=runtime_payload,
    )
    if terminal_operation_id is not None:
        tool_call.terminal_operation_id = terminal_operation_id
        tool_call.summary = ToolCallSummary.Terminal(operation_id=terminal_operation_id)
        _sync_terminal_model_observation(rollout, tool_call_id)
    _start_agent_interaction_from_runtime(
        rollout,
        wall_time_unix_ms=wall_time_unix_ms,
        tool_call_id=tool_call_id,
        runtime_payload=runtime_payload,
    )


def _replay_end_tool_runtime_observation(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    tool_call_id: str,
    status: ExecutionStatus,
    runtime_payload: RawPayloadRef | None,
) -> None:
    if runtime_payload is None:
        raise ValueError(f"tool runtime end {tool_call_id} missing runtime payload")
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool runtime end referenced unknown call {tool_call_id}")
    _push_unique(tool_call.raw_runtime_payload_ids, runtime_payload.raw_payload_id)
    if tool_call.terminal_operation_id is not None:
        _end_terminal_operation(
            rollout,
            seq=seq,
            wall_time_unix_ms=wall_time_unix_ms,
            thread_id=tool_call.thread_id,
            operation_id=tool_call.terminal_operation_id,
            status=status,
            response_payload=runtime_payload,
        )
    _end_agent_interaction_from_runtime(
        rollout,
        wall_time_unix_ms=wall_time_unix_ms,
        tool_call_id=tool_call_id,
        runtime_payload=runtime_payload,
    )


def _start_agent_interaction_from_runtime(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    tool_call_id: ToolCallId,
    runtime_payload: RawPayloadRef,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    kind = _tool_kind_type(tool_call.kind)
    if kind == "close_agent":
        payload = _read_rollout_payload_json(rollout, runtime_payload)
        _upsert_close_agent_interaction(
            rollout,
            tool_call_id=tool_call_id,
            target_thread_id=str(payload.get("receiver_thread_id") or ""),
            ended_at_unix_ms=None,
        )
        return
    if kind not in {"send_message", "assign_agent_task"}:
        return
    payload = _read_rollout_payload_json(rollout, runtime_payload)
    _queue_message_agent_interaction(
        rollout,
        tool_call_id=tool_call_id,
        kind=_interaction_edge_kind_from_tool_kind(kind),
        target_thread_id=str(payload.get("receiver_thread_id") or ""),
        message_content=str(payload.get("prompt") or ""),
        ended_at_unix_ms=None,
    )


def _end_agent_interaction_from_runtime(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    tool_call_id: ToolCallId,
    runtime_payload: RawPayloadRef,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    kind = _tool_kind_type(tool_call.kind)
    payload = _read_rollout_payload_json(rollout, runtime_payload)
    if kind in {"send_message", "assign_agent_task"}:
        _queue_message_agent_interaction(
            rollout,
            tool_call_id=tool_call_id,
            kind=_interaction_edge_kind_from_tool_kind(kind),
            target_thread_id=str(payload.get("receiver_thread_id") or ""),
            message_content=str(payload.get("prompt") or ""),
            ended_at_unix_ms=wall_time_unix_ms,
        )
        return
    if kind == "close_agent":
        _upsert_close_agent_interaction(
            rollout,
            tool_call_id=tool_call_id,
            target_thread_id=str(payload.get("receiver_thread_id") or ""),
            ended_at_unix_ms=wall_time_unix_ms,
        )
        return
    if kind != "spawn_agent":
        return
    child_thread_id = payload.get("new_thread_id")
    if child_thread_id is None:
        return
    sender_thread_id = str(payload.get("sender_thread_id") or tool_call.thread_id)
    child_thread_id = str(child_thread_id)
    _queue_or_resolve_agent_interaction_edge(
        rollout,
        _PendingAgentInteractionEdge(
            edge_id=_spawn_edge_id(sender_thread_id, child_thread_id),
            kind=InteractionEdgeKind.SPAWN_AGENT,
            source=TraceAnchor.ToolCall(tool_call_id),
            target_thread_id=child_thread_id,
            message_content=str(payload.get("prompt") or ""),
            unresolved_spawn_thread_id=child_thread_id,
            started_at_unix_ms=tool_call.execution.started_at_unix_ms,
            ended_at_unix_ms=wall_time_unix_ms,
            carried_raw_payload_ids=_agent_tool_payload_ids(tool_call),
        ),
    )


def _upsert_close_agent_interaction(
    rollout: RolloutTrace,
    *,
    tool_call_id: ToolCallId,
    target_thread_id: AgentThreadId,
    ended_at_unix_ms: int | None,
) -> None:
    if not target_thread_id or target_thread_id not in rollout.threads:
        return
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    _upsert_interaction_edge(
        rollout,
        InteractionEdge(
            edge_id=f"edge:tool:{tool_call_id}",
            kind=InteractionEdgeKind.CLOSE_AGENT,
            source=TraceAnchor.ToolCall(tool_call_id),
            target=TraceAnchor.Thread(target_thread_id),
            started_at_unix_ms=tool_call.execution.started_at_unix_ms,
            ended_at_unix_ms=ended_at_unix_ms,
            carried_item_ids=[],
            carried_raw_payload_ids=_agent_tool_payload_ids(tool_call),
        ),
    )


def _queue_message_agent_interaction(
    rollout: RolloutTrace,
    *,
    tool_call_id: ToolCallId,
    kind: InteractionEdgeKind,
    target_thread_id: AgentThreadId,
    message_content: str,
    ended_at_unix_ms: int | None,
) -> None:
    if not target_thread_id:
        return
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        return
    _queue_or_resolve_agent_interaction_edge(
        rollout,
        _PendingAgentInteractionEdge(
            edge_id=f"edge:tool:{tool_call_id}",
            kind=kind,
            source=TraceAnchor.ToolCall(tool_call_id),
            target_thread_id=target_thread_id,
            message_content=message_content,
            unresolved_spawn_thread_id=None,
            started_at_unix_ms=tool_call.execution.started_at_unix_ms,
            ended_at_unix_ms=ended_at_unix_ms,
            carried_raw_payload_ids=_agent_tool_payload_ids(tool_call),
        ),
    )


def _queue_or_resolve_agent_interaction_edge(
    rollout: RolloutTrace,
    pending: _PendingAgentInteractionEdge,
) -> None:
    item_id = _find_unlinked_inter_agent_message_item(
        rollout,
        pending.target_thread_id,
        pending.message_content,
    )
    if item_id is not None:
        _upsert_agent_interaction_edge_for_item(rollout, pending, item_id)
        return
    for existing in rollout.pending_agent_interaction_edges:
        if existing.edge_id != pending.edge_id:
            continue
        if (
            existing.kind != pending.kind
            or existing.source != pending.source
            or existing.target_thread_id != pending.target_thread_id
            or existing.message_content != pending.message_content
            or existing.unresolved_spawn_thread_id != pending.unresolved_spawn_thread_id
        ):
            raise ValueError(f"pending interaction edge {pending.edge_id} was observed with conflicting delivery data")
        existing.started_at_unix_ms = min(existing.started_at_unix_ms, pending.started_at_unix_ms)
        if existing.ended_at_unix_ms is None or pending.ended_at_unix_ms is None:
            existing.ended_at_unix_ms = existing.ended_at_unix_ms or pending.ended_at_unix_ms
        else:
            existing.ended_at_unix_ms = max(existing.ended_at_unix_ms, pending.ended_at_unix_ms)
        _extend_unique(existing.carried_raw_payload_ids, pending.carried_raw_payload_ids)
        return
    rollout.pending_agent_interaction_edges.append(pending)


def _queue_agent_result_interaction_edge(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    edge_id: EdgeId,
    child_thread_id: AgentThreadId,
    child_codex_turn_id: CodexTurnId,
    parent_thread_id: AgentThreadId,
    message: str,
    carried_payload: RawPayloadRef | None,
) -> None:
    source_item_id = _latest_assistant_message_item_for_turn(
        rollout,
        child_thread_id,
        child_codex_turn_id,
    )
    source = (
        TraceAnchor.ConversationItem(source_item_id)
        if source_item_id is not None
        else TraceAnchor.Thread(child_thread_id)
    )
    _queue_or_resolve_agent_interaction_edge(
        rollout,
        _PendingAgentInteractionEdge(
            edge_id=edge_id,
            kind=InteractionEdgeKind.AGENT_RESULT,
            source=source,
            target_thread_id=parent_thread_id,
            message_content=message,
            unresolved_spawn_thread_id=None,
            started_at_unix_ms=wall_time_unix_ms,
            ended_at_unix_ms=wall_time_unix_ms,
            carried_raw_payload_ids=[carried_payload.raw_payload_id] if carried_payload else [],
        ),
    )


def _latest_assistant_message_item_for_turn(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    codex_turn_id: CodexTurnId,
) -> ConversationItemId | None:
    candidates = [
        item
        for item in rollout.conversation_items.values()
        if item.thread_id == thread_id
        and item.codex_turn_id == codex_turn_id
        and item.role == ConversationRole.ASSISTANT
        and item.kind == ConversationItemKind.MESSAGE
    ]
    if not candidates:
        return None
    return max(
        enumerate(candidates),
        key=lambda indexed: (indexed[1].first_seen_at_unix_ms, indexed[0]),
    )[1].item_id


def _attach_agent_interaction_tool_result(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    result_payload: RawPayloadRef | None,
) -> None:
    if result_payload is None:
        return
    for edge in rollout.interaction_edges.values():
        if edge.source == TraceAnchor.ToolCall(tool_call_id):
            _push_unique(edge.carried_raw_payload_ids, result_payload.raw_payload_id)
            return
    for pending in rollout.pending_agent_interaction_edges:
        if pending.source == TraceAnchor.ToolCall(tool_call_id):
            _push_unique(pending.carried_raw_payload_ids, result_payload.raw_payload_id)


def _resolve_pending_agent_edges_for_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
) -> None:
    message = _inter_agent_message_item(rollout, item_id)
    if message is None:
        return
    thread_id, message_content = message
    for index, pending in enumerate(list(rollout.pending_agent_interaction_edges)):
        if pending.target_thread_id == thread_id and pending.message_content == message_content:
            pending = rollout.pending_agent_interaction_edges.pop(index)
            _upsert_agent_interaction_edge_for_item(rollout, pending, item_id)
            return


def _upsert_agent_interaction_edge_for_item(
    rollout: RolloutTrace,
    pending: _PendingAgentInteractionEdge,
    target_item_id: ConversationItemId,
) -> None:
    _upsert_interaction_edge(
        rollout,
        InteractionEdge(
            edge_id=pending.edge_id,
            kind=pending.kind,
            source=pending.source,
            target=TraceAnchor.ConversationItem(target_item_id),
            started_at_unix_ms=pending.started_at_unix_ms,
            ended_at_unix_ms=pending.ended_at_unix_ms,
            carried_item_ids=[target_item_id],
            carried_raw_payload_ids=pending.carried_raw_payload_ids,
        ),
    )


def _find_unlinked_inter_agent_message_item(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    message_content: str,
) -> ConversationItemId | None:
    thread = rollout.threads.get(thread_id)
    if thread is None:
        return None
    for item_id in thread.conversation_item_ids:
        if _is_interaction_edge_target_item(rollout, item_id):
            continue
        message = _inter_agent_message_item(rollout, item_id)
        if message is not None and message[1] == message_content:
            return item_id
    return None


def _inter_agent_message_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
) -> tuple[AgentThreadId, str] | None:
    item = rollout.conversation_items.get(item_id)
    if item is None or item.role != ConversationRole.ASSISTANT or item.kind != ConversationItemKind.MESSAGE:
        return None
    if len(item.body.parts) != 1 or item.body.parts[0].type != "text":
        return None
    text = item.body.parts[0].text
    if text is None:
        return None
    try:
        communication = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(communication, dict):
        return None
    recipient = communication.get("recipient")
    content = communication.get("content")
    if not isinstance(recipient, str) or not isinstance(content, str):
        return None
    thread = rollout.threads.get(item.thread_id)
    if thread is None or recipient != thread.agent_path:
        return None
    return item.thread_id, content


def _is_interaction_edge_target_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
) -> bool:
    return any(edge.target == TraceAnchor.ConversationItem(item_id) for edge in rollout.interaction_edges.values())


def _resolve_pending_spawn_edge_fallbacks(rollout: RolloutTrace) -> None:
    pending_edges = list(rollout.pending_agent_interaction_edges)
    rollout.pending_agent_interaction_edges.clear()
    for pending in pending_edges:
        child_thread_id = pending.unresolved_spawn_thread_id
        if pending.kind != InteractionEdgeKind.SPAWN_AGENT or child_thread_id is None:
            continue
        if child_thread_id not in rollout.threads:
            continue
        _upsert_interaction_edge(
            rollout,
            InteractionEdge(
                edge_id=pending.edge_id,
                kind=pending.kind,
                source=pending.source,
                target=TraceAnchor.Thread(child_thread_id),
                started_at_unix_ms=pending.started_at_unix_ms,
                ended_at_unix_ms=pending.ended_at_unix_ms,
                carried_item_ids=[],
                carried_raw_payload_ids=pending.carried_raw_payload_ids,
            ),
        )


def _interaction_edge_kind_from_tool_kind(kind: str | None) -> InteractionEdgeKind:
    if kind == "assign_agent_task":
        return InteractionEdgeKind.ASSIGN_AGENT_TASK
    if kind == "send_message":
        return InteractionEdgeKind.SEND_MESSAGE
    if kind == "close_agent":
        return InteractionEdgeKind.CLOSE_AGENT
    if kind == "spawn_agent":
        return InteractionEdgeKind.SPAWN_AGENT
    raise ValueError(f"tool kind {kind!r} is not an agent interaction edge kind")


def _upsert_interaction_edge(rollout: RolloutTrace, edge: InteractionEdge) -> None:
    existing = rollout.interaction_edges.get(edge.edge_id)
    if existing is None:
        rollout.interaction_edges[edge.edge_id] = edge
        return
    if existing.kind != edge.kind or existing.source != edge.source or existing.target != edge.target:
        raise ValueError(f"interaction edge {edge.edge_id} was observed with conflicting endpoints")
    existing.started_at_unix_ms = min(existing.started_at_unix_ms, edge.started_at_unix_ms)
    if existing.ended_at_unix_ms is None or edge.ended_at_unix_ms is None:
        existing.ended_at_unix_ms = existing.ended_at_unix_ms or edge.ended_at_unix_ms
    else:
        existing.ended_at_unix_ms = max(existing.ended_at_unix_ms, edge.ended_at_unix_ms)
    _extend_unique(existing.carried_item_ids, edge.carried_item_ids)
    _extend_unique(existing.carried_raw_payload_ids, edge.carried_raw_payload_ids)


def _agent_tool_payload_ids(tool_call: ToolCall) -> list[RawPayloadId]:
    payload_ids: list[RawPayloadId] = []
    if tool_call.raw_invocation_payload_id is not None:
        _push_unique(payload_ids, tool_call.raw_invocation_payload_id)
    for payload_id in tool_call.raw_runtime_payload_ids:
        _push_unique(payload_ids, payload_id)
    if tool_call.raw_result_payload_id is not None:
        _push_unique(payload_ids, tool_call.raw_result_payload_id)
    return payload_ids


def _tool_kind_type(kind: Any) -> str | None:
    if isinstance(kind, ToolCallKind):
        return kind.type
    if isinstance(kind, dict):
        value = kind.get("type")
        return value if isinstance(value, str) else None
    return kind if isinstance(kind, str) else None


def _tool_call_kind_from_value(value: Any) -> ToolCallKind:
    if isinstance(value, ToolCallKind):
        return value
    if isinstance(value, str):
        data: dict[str, Any] = {"type": value}
    elif isinstance(value, dict):
        data = value
    else:
        return ToolCallKind.Other(name=str(value))
    kind_type = str(data.get("type") or "")
    if kind_type == "exec_command":
        return ToolCallKind.ExecCommand()
    if kind_type == "write_stdin":
        return ToolCallKind.WriteStdin()
    if kind_type == "apply_patch":
        return ToolCallKind.ApplyPatch()
    if kind_type == "mcp":
        return ToolCallKind.Mcp(server=str(data.get("server") or ""), tool=str(data.get("tool") or ""))
    if kind_type == "web":
        return ToolCallKind.Web()
    if kind_type == "image_generation":
        return ToolCallKind.ImageGeneration()
    if kind_type == "spawn_agent":
        return ToolCallKind.SpawnAgent()
    if kind_type == "assign_agent_task":
        return ToolCallKind.AssignAgentTask()
    if kind_type == "send_message":
        return ToolCallKind.SendMessage()
    if kind_type == "wait_agent":
        return ToolCallKind.WaitAgent()
    if kind_type == "close_agent":
        return ToolCallKind.CloseAgent()
    return ToolCallKind.Other(name=str(data.get("name") or kind_type or value))


def _tool_call_summary_from_value(value: Any) -> ToolCallSummary:
    if isinstance(value, ToolCallSummary):
        return value
    if not isinstance(value, dict):
        return ToolCallSummary.Generic(label=str(value) if value is not None else "")
    summary_type = str(value.get("type") or "")
    if summary_type == "terminal":
        return ToolCallSummary.Terminal(operation_id=str(value.get("operation_id") or ""))
    if summary_type == "agent":
        return ToolCallSummary.Agent(
            target_agent_path=str(value.get("target_agent_path") or ""),
            task_name=value.get("task_name") if isinstance(value.get("task_name"), str) else None,
            message_preview=str(value.get("message_preview") or ""),
        )
    if summary_type == "wait_agent":
        target_agent_path = value.get("target_agent_path")
        timeout_ms = value.get("timeout_ms")
        return ToolCallSummary.WaitAgent(
            target_agent_path=target_agent_path if isinstance(target_agent_path, str) else None,
            timeout_ms=timeout_ms if isinstance(timeout_ms, int) else None,
        )
    return ToolCallSummary.Generic(
        label=str(value.get("label") or ""),
        input_preview=value.get("input_preview") if isinstance(value.get("input_preview"), str) else None,
        output_preview=value.get("output_preview") if isinstance(value.get("output_preview"), str) else None,
    )


def _extend_unique(items: list[str], new_items: list[str]) -> None:
    for item in new_items:
        _push_unique(items, item)


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
    if _terminal_operation_kind(kind) != TerminalOperationKind.WRITE_STDIN:
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
    operation_kind = _terminal_operation_kind(kind)
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
        _push_unique(operation.raw_payload_ids, response_payload.raw_payload_id)
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
    _push_unique(session.operation_ids, operation_id)


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


def _terminal_operation_kind(kind: Any) -> TerminalOperationKind | None:
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


def _push_unique(items: list[str], item_id: str) -> None:
    if item_id not in items:
        items.append(item_id)


def _tool_thread_id(
    rollout: RolloutTrace,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
) -> str:
    if event_thread_id is not None:
        return event_thread_id
    if event_codex_turn_id is None:
        raise ValueError("tool call start did not include thread or Codex turn context")
    turn = rollout.codex_turns.get(event_codex_turn_id)
    if turn is None:
        raise ValueError(f"tool call start referenced unknown Codex turn {event_codex_turn_id}")
    return turn.thread_id


def _validate_tool_turn(
    rollout: RolloutTrace,
    thread_id: str,
    event_codex_turn_id: str | None,
) -> None:
    if thread_id not in rollout.threads:
        raise ValueError(f"tool call start referenced unknown thread {thread_id}")
    if event_codex_turn_id is None:
        return
    turn = rollout.codex_turns.get(event_codex_turn_id)
    if turn is None:
        raise ValueError(f"tool call start referenced unknown Codex turn {event_codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"tool call start used thread {thread_id}, but Codex turn {event_codex_turn_id} belongs to {turn.thread_id}"
        )


def _reduce_tool_call_requester(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    requester: Any,
) -> Any:
    requester_type = requester.get("type") if isinstance(requester, dict) else getattr(requester, "type", None)
    if requester_type != "code_cell":
        return ToolCallRequester.Model()
    runtime_cell_id = (
        requester.get("runtime_cell_id")
        if isinstance(requester, dict)
        else getattr(requester, "runtime_cell_id", None)
    )
    if not isinstance(runtime_cell_id, str):
        raise ValueError("code-mode nested tool requester did not include runtime_cell_id")
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        raise ValueError(
            f"code-mode nested tool referenced unknown runtime cell {runtime_cell_id} "
            f"in thread {thread_id}"
        )
    return ToolCallRequester.CodeCell(code_cell_id)


def _link_tool_call_to_code_cell(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    requester: Any,
) -> None:
    requester_type = requester.get("type") if isinstance(requester, dict) else getattr(requester, "type", None)
    if requester_type != "code_cell":
        return
    code_cell_id = requester.get("code_cell_id") if isinstance(requester, dict) else getattr(requester, "code_cell_id", None)
    if not isinstance(code_cell_id, str):
        return
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        return
    if tool_call_id not in cell.nested_tool_call_ids:
        cell.nested_tool_call_ids.append(tool_call_id)


def _link_wait_tool_call_from_request_payload(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    tool_call_id: ToolCallId,
    request_payload: RawPayloadRef | None,
) -> None:
    if request_payload is None:
        return
    payload = _read_rollout_payload_json(rollout, request_payload)
    if payload.get("tool_name") != "wait":
        return
    arguments = payload.get("payload", {}).get("arguments") if isinstance(payload.get("payload"), dict) else None
    if not isinstance(arguments, str):
        raise ValueError(f"wait tool request payload {request_payload.raw_payload_id} did not contain function arguments")
    try:
        decoded = json.loads(arguments)
    except json.JSONDecodeError as exc:
        raise ValueError(f"wait tool request payload {request_payload.raw_payload_id} had invalid JSON arguments") from exc
    runtime_cell_id = decoded.get("cell_id") if isinstance(decoded, dict) else None
    if not isinstance(runtime_cell_id, str):
        raise ValueError(f"wait tool request payload {request_payload.raw_payload_id} did not contain cell_id")
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        return
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        return
    if tool_call_id not in cell.wait_tool_call_ids:
        cell.wait_tool_call_ids.append(tool_call_id)


def _single_tool_for_model_visible_call(
    rollout: RolloutTrace,
    model_visible_call_id: str,
) -> ToolCallId | None:
    matches = [
        tool.tool_call_id
        for tool in rollout.tool_calls.values()
        if tool.model_visible_call_id == model_visible_call_id
    ]
    if len(matches) > 1:
        raise ValueError(f"multiple tool calls matched model-visible call id {model_visible_call_id}")
    return matches[0] if matches else None


def _attach_model_visible_tool_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
    call_id: str | None,
    kind: ConversationItemKind,
) -> None:
    if call_id is None:
        return
    if kind not in {ConversationItemKind.FUNCTION_CALL, ConversationItemKind.FUNCTION_CALL_OUTPUT}:
        return
    tool_call_id = _single_tool_for_model_visible_call(rollout, call_id)
    if tool_call_id is None:
        return
    if kind == ConversationItemKind.FUNCTION_CALL:
        _add_tool_call_item(rollout, tool_call_id, item_id)
        _link_tool_to_inference_response(rollout, tool_call_id)
    else:
        _add_tool_output_item(rollout, tool_call_id, item_id)
    _sync_terminal_model_observation(rollout, tool_call_id)


def _add_tool_call_item(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    item_id: ConversationItemId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool call {tool_call_id} disappeared during conversation linking")
    if item_id not in tool_call.model_visible_call_item_ids:
        tool_call.model_visible_call_item_ids.append(item_id)


def _add_tool_output_item(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
    item_id: ConversationItemId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None:
        raise ValueError(f"tool call {tool_call_id} disappeared during output linking")
    if item_id not in tool_call.model_visible_output_item_ids:
        tool_call.model_visible_output_item_ids.append(item_id)
    item = rollout.conversation_items.get(item_id)
    if item is None:
        raise ValueError(f"conversation item {item_id} disappeared during output linking")
    producer = ProducerRef.Tool(tool_call_id)
    if producer not in item.produced_by:
        item.produced_by.append(producer)


def _link_tool_to_inference_response(
    rollout: RolloutTrace,
    tool_call_id: ToolCallId,
) -> None:
    tool_call = rollout.tool_calls.get(tool_call_id)
    if tool_call is None or not tool_call.model_visible_call_item_ids:
        return
    call_item_ids = set(tool_call.model_visible_call_item_ids)
    for inference in rollout.inference_calls.values():
        if call_item_ids.intersection(inference.response_item_ids) and tool_call_id not in inference.tool_call_ids_started_by_response:
            inference.tool_call_ids_started_by_response.append(tool_call_id)


def _replay_start_or_queue_code_cell(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    runtime_cell_id: str,
    model_visible_call_id: str,
    source_js: str,
) -> None:
    thread_id = _code_cell_event_thread_id(
        rollout,
        event_thread_id,
        event_codex_turn_id,
        runtime_cell_id,
        "code cell start",
    )
    code_cell_id = _reduced_code_cell_id_for_model_visible_call(model_visible_call_id)
    pending = _PendingCodeCellStart(
        seq=seq,
        wall_time_unix_ms=wall_time_unix_ms,
        thread_id=thread_id,
        codex_turn_id=event_codex_turn_id,
        code_cell_id=code_cell_id,
        runtime_cell_id=runtime_cell_id,
        model_visible_call_id=model_visible_call_id,
        source_js=source_js,
    )
    if _source_item_id_for_pending_code_cell(rollout, pending) is None:
        if code_cell_id in rollout.code_cells or code_cell_id in rollout.pending_code_cell_starts:
            raise ValueError(f"duplicate code cell start for {code_cell_id}")
        rollout.pending_code_cell_starts[code_cell_id] = pending
        return
    _start_code_cell(rollout, pending)


def _flush_pending_code_cell_starts(rollout: RolloutTrace) -> None:
    ready_ids = [
        code_cell_id
        for code_cell_id, pending in rollout.pending_code_cell_starts.items()
        if _source_item_id_for_pending_code_cell(rollout, pending) is not None
    ]
    for code_cell_id in ready_ids:
        pending = rollout.pending_code_cell_starts.pop(code_cell_id)
        _start_code_cell(rollout, pending)


def _start_code_cell(rollout: RolloutTrace, pending: _PendingCodeCellStart) -> None:
    if pending.code_cell_id in rollout.code_cells:
        raise ValueError(f"duplicate code cell start for {pending.code_cell_id}")
    if pending.codex_turn_id is None:
        raise ValueError(f"code cell start {pending.code_cell_id} did not include a Codex turn id")
    _validate_code_cell_turn(rollout, pending.thread_id, pending.codex_turn_id)
    source_item_id = _source_item_id_for_code_cell_start(
        rollout,
        pending.thread_id,
        pending.code_cell_id,
        pending.model_visible_call_id,
    )
    output_item_ids = _model_visible_code_cell_item_ids(
        rollout,
        pending.thread_id,
        pending.model_visible_call_id,
        ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT,
    )
    rollout.code_cells[pending.code_cell_id] = CodeCell(
        code_cell_id=pending.code_cell_id,
        model_visible_call_id=pending.model_visible_call_id,
        thread_id=pending.thread_id,
        codex_turn_id=pending.codex_turn_id,
        source_item_id=source_item_id,
        output_item_ids=list(output_item_ids),
        runtime_cell_id=pending.runtime_cell_id,
        execution=ExecutionWindow(
            started_at_unix_ms=pending.wall_time_unix_ms,
            started_seq=pending.seq,
            status=ExecutionStatus.RUNNING,
        ),
        runtime_status=CodeCellRuntimeStatus.STARTING,
        initial_response_at_unix_ms=None,
        initial_response_seq=None,
        yielded_at_unix_ms=None,
        yielded_seq=None,
        source_js=pending.source_js,
    )
    _record_runtime_code_cell_id(
        rollout,
        pending.thread_id,
        pending.runtime_cell_id,
        pending.code_cell_id,
    )
    for item_id in output_item_ids:
        _add_code_cell_output_item(rollout, pending.code_cell_id, item_id)
    _flush_pending_code_cell_lifecycle_events(rollout, pending.code_cell_id)


def _replay_record_or_queue_code_cell_initial_response(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    runtime_cell_id: str,
    status: CodeCellRuntimeStatus,
) -> None:
    thread_id = _code_cell_event_thread_id(
        rollout,
        event_thread_id,
        event_codex_turn_id,
        runtime_cell_id,
        "code cell initial response",
    )
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        code_cell_id = _pending_code_cell_id_for_runtime_cell_id(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        raise ValueError(f"code cell initial response referenced unknown cell {runtime_cell_id}")
    if code_cell_id not in rollout.code_cells:
        if code_cell_id in rollout.pending_code_cell_starts:
            _queue_code_cell_lifecycle_event(
                rollout,
                code_cell_id,
                _PendingCodeCellLifecycleEvent(
                    seq=seq,
                    wall_time_unix_ms=wall_time_unix_ms,
                    type="initial_response",
                    runtime_cell_id=runtime_cell_id,
                    status=status,
                ),
            )
            return
        raise ValueError(f"code cell initial response referenced unknown cell {code_cell_id}")
    _record_code_cell_initial_response(
        rollout,
        seq,
        wall_time_unix_ms,
        code_cell_id,
        runtime_cell_id,
        status,
    )


def _record_code_cell_initial_response(
    rollout: RolloutTrace,
    seq: int,
    wall_time_unix_ms: int,
    code_cell_id: CodeCellId,
    runtime_cell_id: str,
    status: CodeCellRuntimeStatus,
) -> None:
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        raise ValueError(f"code cell initial response referenced unknown cell {code_cell_id}")
    cell.runtime_cell_id = runtime_cell_id
    if cell.initial_response_at_unix_ms is None:
        cell.initial_response_at_unix_ms = wall_time_unix_ms
        cell.initial_response_seq = seq
    if status == CodeCellRuntimeStatus.YIELDED:
        cell.yielded_at_unix_ms = wall_time_unix_ms
        cell.yielded_seq = seq
    cell.runtime_status = status


def _replay_end_or_queue_code_cell(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    event_thread_id: str | None,
    event_codex_turn_id: str | None,
    runtime_cell_id: str,
    status: CodeCellRuntimeStatus,
) -> None:
    thread_id = _code_cell_event_thread_id(
        rollout,
        event_thread_id,
        event_codex_turn_id,
        runtime_cell_id,
        "code cell end",
    )
    code_cell_id = _code_cell_id_for_runtime_cell_id_if_known(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        code_cell_id = _pending_code_cell_id_for_runtime_cell_id(rollout, thread_id, runtime_cell_id)
    if code_cell_id is None:
        raise ValueError(f"code cell end referenced unknown cell {runtime_cell_id}")
    if code_cell_id not in rollout.code_cells:
        if code_cell_id in rollout.pending_code_cell_starts:
            _queue_code_cell_lifecycle_event(
                rollout,
                code_cell_id,
                _PendingCodeCellLifecycleEvent(
                    seq=seq,
                    wall_time_unix_ms=wall_time_unix_ms,
                    type="ended",
                    status=status,
                ),
            )
            return
        raise ValueError(f"code cell end referenced unknown cell {code_cell_id}")
    _end_code_cell(rollout, seq, wall_time_unix_ms, code_cell_id, status)


def _end_code_cell(
    rollout: RolloutTrace,
    seq: int,
    wall_time_unix_ms: int,
    code_cell_id: CodeCellId,
    status: CodeCellRuntimeStatus,
) -> None:
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        raise ValueError(f"code cell end referenced unknown cell {code_cell_id}")
    if cell.initial_response_at_unix_ms is None:
        cell.initial_response_at_unix_ms = wall_time_unix_ms
        cell.initial_response_seq = seq
    cell.execution = ExecutionWindow(
        started_at_unix_ms=cell.execution.started_at_unix_ms,
        started_seq=cell.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=_execution_status_for_code_cell(status),
    )
    cell.runtime_status = status


def _terminate_running_code_cells_for_turn_end(
    rollout: RolloutTrace,
    seq: int,
    wall_time_unix_ms: int,
    codex_turn_id: str,
    turn_status: ExecutionStatus,
) -> None:
    if turn_status in {ExecutionStatus.RUNNING, ExecutionStatus.COMPLETED}:
        return
    runtime_status = (
        CodeCellRuntimeStatus.FAILED
        if turn_status == ExecutionStatus.FAILED
        else CodeCellRuntimeStatus.TERMINATED
    )
    for code_cell_id, cell in list(rollout.code_cells.items()):
        if cell.codex_turn_id == codex_turn_id and cell.execution.status == ExecutionStatus.RUNNING:
            _end_code_cell(rollout, seq, wall_time_unix_ms, code_cell_id, runtime_status)


def _queue_code_cell_lifecycle_event(
    rollout: RolloutTrace,
    code_cell_id: CodeCellId,
    event: _PendingCodeCellLifecycleEvent,
) -> None:
    events = rollout.pending_code_cell_lifecycle_events.setdefault(code_cell_id, [])
    events.append(event)
    events.sort(key=lambda queued: queued.seq)


def _flush_pending_code_cell_lifecycle_events(
    rollout: RolloutTrace,
    code_cell_id: CodeCellId,
) -> None:
    for event in rollout.pending_code_cell_lifecycle_events.pop(code_cell_id, []):
        if event.type == "initial_response":
            if event.runtime_cell_id is None or event.status is None:
                raise ValueError(f"code cell {code_cell_id} had incomplete pending initial response")
            _record_code_cell_initial_response(
                rollout,
                event.seq,
                event.wall_time_unix_ms,
                code_cell_id,
                event.runtime_cell_id,
                event.status,
            )
        elif event.type == "ended":
            if event.status is None:
                raise ValueError(f"code cell {code_cell_id} had incomplete pending end")
            _end_code_cell(rollout, event.seq, event.wall_time_unix_ms, code_cell_id, event.status)


def _attach_model_visible_code_cell_item(
    rollout: RolloutTrace,
    item_id: ConversationItemId,
    call_id: str | None,
    kind: ConversationItemKind,
) -> None:
    if call_id is None or kind != ConversationItemKind.CUSTOM_TOOL_CALL_OUTPUT:
        return
    code_cell_id = _reduced_code_cell_id_for_model_visible_call(call_id)
    if code_cell_id not in rollout.code_cells:
        return
    _add_code_cell_output_item(rollout, code_cell_id, item_id)


def _add_code_cell_output_item(
    rollout: RolloutTrace,
    code_cell_id: CodeCellId,
    item_id: ConversationItemId,
) -> None:
    cell = rollout.code_cells.get(code_cell_id)
    if cell is None:
        raise ValueError(f"code cell {code_cell_id} disappeared during output linking")
    if item_id not in cell.output_item_ids:
        cell.output_item_ids.append(item_id)
    item = rollout.conversation_items.get(item_id)
    if item is None:
        raise ValueError(f"conversation item {item_id} disappeared during code-cell output linking")
    producer = ProducerRef.CodeCell(code_cell_id)
    if producer not in item.produced_by:
        item.produced_by.append(producer)


def _source_item_id_for_pending_code_cell(
    rollout: RolloutTrace,
    pending: _PendingCodeCellStart,
) -> ConversationItemId | None:
    items = _model_visible_code_cell_item_ids(
        rollout,
        pending.thread_id,
        pending.model_visible_call_id,
        ConversationItemKind.CUSTOM_TOOL_CALL,
    )
    return items[0] if items else None


def _source_item_id_for_code_cell_start(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    code_cell_id: CodeCellId,
    model_visible_call_id: ModelVisibleCallId,
) -> ConversationItemId:
    items = _model_visible_code_cell_item_ids(
        rollout,
        thread_id,
        model_visible_call_id,
        ConversationItemKind.CUSTOM_TOOL_CALL,
    )
    if not items:
        raise ValueError(
            f"code cell {code_cell_id} referenced model-visible call {model_visible_call_id}, "
            "but no custom tool call item was observed"
        )
    return items[0]


def _model_visible_code_cell_item_ids(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    call_id: ModelVisibleCallId,
    kind: ConversationItemKind,
) -> list[ConversationItemId]:
    return [
        item.item_id
        for item in rollout.conversation_items.values()
        if item.thread_id == thread_id and item.call_id == call_id and item.kind == kind
    ]


def _code_cell_event_thread_id(
    rollout: RolloutTrace,
    thread_id: str | None,
    codex_turn_id: str | None,
    runtime_cell_id: str,
    event_name: str,
) -> str:
    if thread_id is not None:
        return thread_id
    if codex_turn_id is None:
        raise ValueError(f"{event_name} {runtime_cell_id} did not include a thread id")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"{event_name} {runtime_cell_id} referenced unknown Codex turn {codex_turn_id}")
    return turn.thread_id


def _validate_code_cell_turn(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    codex_turn_id: CodexTurnId,
) -> None:
    if thread_id not in rollout.threads:
        raise ValueError(f"code cell start referenced unknown thread {thread_id}")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"code cell start referenced unknown Codex turn {codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"code cell start used thread {thread_id}, but Codex turn {codex_turn_id} belongs to {turn.thread_id}"
        )


def _reduced_code_cell_id_for_model_visible_call(model_visible_call_id: str) -> CodeCellId:
    return f"code_cell:{model_visible_call_id}"


def _record_runtime_code_cell_id(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    runtime_cell_id: str,
    code_cell_id: CodeCellId,
) -> None:
    key = (thread_id, runtime_cell_id)
    existing = rollout.code_cell_ids_by_runtime.get(key)
    if existing is not None and existing != code_cell_id:
        raise ValueError(
            f"runtime code cell {runtime_cell_id} in thread {thread_id} mapped to both "
            f"{existing} and {code_cell_id}"
        )
    rollout.code_cell_ids_by_runtime[key] = code_cell_id


def _code_cell_id_for_runtime_cell_id_if_known(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    runtime_cell_id: str,
) -> CodeCellId | None:
    return rollout.code_cell_ids_by_runtime.get((thread_id, runtime_cell_id))


def _pending_code_cell_id_for_runtime_cell_id(
    rollout: RolloutTrace,
    thread_id: AgentThreadId,
    runtime_cell_id: str,
) -> CodeCellId | None:
    for code_cell_id, pending in rollout.pending_code_cell_starts.items():
        if pending.thread_id == thread_id and pending.runtime_cell_id == runtime_cell_id:
            return code_cell_id
    return None


def _execution_status_for_code_cell(status: CodeCellRuntimeStatus) -> ExecutionStatus:
    if status in {
        CodeCellRuntimeStatus.STARTING,
        CodeCellRuntimeStatus.RUNNING,
        CodeCellRuntimeStatus.YIELDED,
    }:
        return ExecutionStatus.RUNNING
    if status == CodeCellRuntimeStatus.COMPLETED:
        return ExecutionStatus.COMPLETED
    if status == CodeCellRuntimeStatus.FAILED:
        return ExecutionStatus.FAILED
    return ExecutionStatus.CANCELLED


def _read_rollout_payload_json(rollout: RolloutTrace, payload_ref: RawPayloadRef) -> dict[str, Any]:
    if rollout._bundle_dir is None:
        raise ValueError("rollout replay has no bundle directory")
    payload = _read_payload_json(rollout._bundle_dir, payload_ref)
    if not isinstance(payload, dict):
        raise ValueError(f"payload {payload_ref.raw_payload_id} was not a JSON object")
    return payload


def _replay_start_inference_call(
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


def _replay_start_compaction_request(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    compaction_id: str,
    compaction_request_id: str,
    thread_id: str,
    codex_turn_id: str,
    model: str,
    provider_name: str,
    request_payload: RawPayloadRef | None,
) -> None:
    if request_payload is None:
        raise ValueError(f"compaction request {compaction_request_id} missing request payload")
    if compaction_request_id in rollout.compaction_requests:
        raise ValueError(f"duplicate compaction request start for {compaction_request_id}")
    if thread_id not in rollout.threads:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"compaction request {compaction_request_id} referenced unknown codex turn {codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"compaction request {compaction_request_id} used thread {thread_id}, "
            f"but codex turn {codex_turn_id} belongs to {turn.thread_id}"
        )
    rollout.compaction_requests[compaction_request_id] = CompactionRequest(
        compaction_request_id=compaction_request_id,
        compaction_id=compaction_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        execution=ExecutionWindow(
            started_at_unix_ms=wall_time_unix_ms,
            started_seq=seq,
            status=ExecutionStatus.RUNNING,
        ),
        model=model,
        provider_name=provider_name,
        raw_request_payload_id=request_payload.raw_payload_id,
        raw_response_payload_id=None,
    )


def _replay_complete_compaction_request(
    rollout: RolloutTrace,
    *,
    seq: int,
    wall_time_unix_ms: int,
    compaction_id: str,
    compaction_request_id: str,
    status: ExecutionStatus,
    response_payload: RawPayloadRef | None,
) -> None:
    request = rollout.compaction_requests.get(compaction_request_id)
    if request is None:
        raise ValueError(f"compaction request completion referenced unknown request {compaction_request_id}")
    if request.compaction_id != compaction_id:
        raise ValueError(
            f"compaction request {compaction_request_id} completion used compaction {compaction_id}, "
            f"but start used {request.compaction_id}"
        )
    request.execution = ExecutionWindow(
        started_at_unix_ms=request.execution.started_at_unix_ms,
        started_seq=request.execution.started_seq,
        ended_at_unix_ms=wall_time_unix_ms,
        ended_seq=seq,
        status=status,
    )
    request.raw_response_payload_id = response_payload.raw_payload_id if response_payload else None


def _replay_compaction_installed(
    rollout: RolloutTrace,
    *,
    wall_time_unix_ms: int,
    thread_id: str,
    codex_turn_id: str,
    compaction_id: str,
    checkpoint_payload: RawPayloadRef | None,
) -> None:
    if checkpoint_payload is None:
        raise ValueError(f"compaction install {compaction_id} missing checkpoint payload")
    if compaction_id in rollout.compactions:
        raise ValueError(f"duplicate compaction install for {compaction_id}")
    if thread_id not in rollout.threads:
        raise ValueError(f"trace event referenced unknown thread {thread_id}")
    turn = rollout.codex_turns.get(codex_turn_id)
    if turn is None:
        raise ValueError(f"compaction install {compaction_id} referenced unknown codex turn {codex_turn_id}")
    if turn.thread_id != thread_id:
        raise ValueError(
            f"compaction install {compaction_id} used thread {thread_id}, "
            f"but codex turn {codex_turn_id} belongs to {turn.thread_id}"
        )
    request_ids = [
        request.compaction_request_id
        for request in rollout.compaction_requests.values()
        if request.compaction_id == compaction_id
    ]
    checkpoint = _read_rollout_payload_json(rollout, checkpoint_payload)
    input_history = checkpoint.get("input_history")
    replacement_history = checkpoint.get("replacement_history")
    if not isinstance(input_history, list):
        raise ValueError(f"compaction checkpoint payload {checkpoint_payload.raw_payload_id} did not contain array input_history")
    if not isinstance(replacement_history, list):
        raise ValueError(f"compaction checkpoint payload {checkpoint_payload.raw_payload_id} did not contain array replacement_history")
    input_items = [_normalize_model_item(item, checkpoint_payload) for item in input_history]
    replacement_items = [_normalize_model_item(item, checkpoint_payload) for item in replacement_history]
    input_item_ids = _reconcile_detached_conversation_items(
        rollout,
        input_items,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        wall_time_unix_ms=wall_time_unix_ms,
        produced_by=[],
        candidates=list(rollout.thread_conversation_snapshots.get(thread_id, [])),
    )
    compaction_producer = [ProducerRef.Compaction(compaction_id)]
    marker_item_id = _create_conversation_item(
        rollout,
        thread_id,
        codex_turn_id,
        wall_time_unix_ms,
        _NormalizedConversationItem(
            role=ConversationRole.ASSISTANT,
            channel=None,
            kind=ConversationItemKind.COMPACTION_MARKER,
            body=ConversationBody([]),
            call_id=None,
        ),
        compaction_producer,
    )
    replacement_item_ids = _reconcile_detached_conversation_items(
        rollout,
        replacement_items,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        wall_time_unix_ms=wall_time_unix_ms,
        produced_by=compaction_producer,
        candidates=[],
    )
    _append_thread_conversation_items(rollout, thread_id, input_item_ids)
    _append_thread_conversation_items(rollout, thread_id, [marker_item_id])
    _append_thread_conversation_items(rollout, thread_id, replacement_item_ids)
    rollout.pending_compaction_replacement_item_ids[thread_id] = list(replacement_item_ids)
    rollout.compactions[compaction_id] = Compaction(
        compaction_id=compaction_id,
        thread_id=thread_id,
        codex_turn_id=codex_turn_id,
        installed_at_unix_ms=wall_time_unix_ms,
        marker_item_id=marker_item_id,
        request_ids=request_ids,
        input_item_ids=input_item_ids,
        replacement_item_ids=replacement_item_ids,
    )


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
        "task_name": spawn.get("task_name") or metadata.get("task_name") or (_task_name_from_agent_path(agent_path) if agent_path else None),
        "agent_role": spawn.get("agent_role") or metadata.get("agent_role"),
    }


def _task_name_from_agent_path(agent_path: str) -> str:
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


__all__ = [
    "AgentOrigin",
    "AgentPath",
    "AgentResultTracePayload",
    "AgentThread",
    "AgentThreadId",
    "CODEX_ROLLOUT_TRACE_ROOT_ENV",
    "CodeCell",
    "CodeCellId",
    "CodeCellRuntimeStatus",
    "CodeCellTraceContext",
    "CodeModeRuntimeToolId",
    "CodexTurn",
    "CodexTurnId",
    "Compaction",
    "CompactionCheckpointTracePayload",
    "CompactionId",
    "CompactionRequest",
    "CompactionRequestId",
    "CompactionTraceAttempt",
    "CompactionTraceContext",
    "ConversationBody",
    "ConversationChannel",
    "ConversationItem",
    "ConversationItemId",
    "ConversationItemKind",
    "ConversationPart",
    "ConversationRole",
    "CorrelationId",
    "EdgeId",
    "ExecutionStatus",
    "ExecutionWindow",
    "INFERENCE_CALL_ID_HEADER",
    "InferenceCall",
    "InferenceCallId",
    "InferenceTraceAttempt",
    "InferenceTraceContext",
    "InteractionEdge",
    "InteractionEdgeKind",
    "MCP_CALL_ID_META_KEY",
    "McpCallId",
    "McpCallTraceContext",
    "ModelVisibleCallId",
    "ProducerRef",
    "REDUCED_STATE_FILE_NAME",
    "RawEventSeq",
    "RawPayloadId",
    "RawPayloadKind",
    "RawPayloadRef",
    "RawToolCallRequester",
    "RawTraceEvent",
    "RawTraceEventContext",
    "RawTraceEventPayload",
    "RolloutStatus",
    "RolloutTrace",
    "TerminalId",
    "TerminalModelObservation",
    "TerminalObservationSource",
    "TerminalOperation",
    "TerminalOperationId",
    "TerminalOperationKind",
    "TerminalRequest",
    "TerminalResult",
    "TerminalSession",
    "ThreadStartedTraceMetadata",
    "ThreadTraceContext",
    "TokenUsage",
    "ToolCall",
    "ToolCallId",
    "ToolCallKind",
    "ToolCallRequester",
    "ToolCallSummary",
    "ToolDispatchInvocation",
    "ToolDispatchPayload",
    "ToolDispatchRequester",
    "ToolDispatchResult",
    "ToolDispatchTraceContext",
    "TraceAnchor",
    "TraceWriter",
    "replay_bundle",
    "trace_response_item_json",
]
