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
from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

REDUCED_STATE_FILE_NAME = "state.json"
CODEX_ROLLOUT_TRACE_ROOT_ENV = "CODEX_ROLLOUT_TRACE_ROOT"
RAW_TRACE_EVENT_SCHEMA_VERSION = 1
MCP_CALL_ID_META_KEY = "codex_bridge_mcp_call_id"

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
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
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
        refs: list[RawPayloadRef] = []

        def walk(value: Any) -> None:
            if isinstance(value, RawPayloadRef):
                refs.append(value)
            elif isinstance(value, dict):
                for item in value.values():
                    walk(item)
            elif isinstance(value, (list, tuple)):
                for item in value:
                    walk(item)

        walk(self.fields)
        return refs


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
        self.payloads_dir = bundle_dir / "payloads"
        self.trace_id = trace_id
        self.rollout_id = rollout_id
        self.root_thread_id = root_thread_id
        self.next_seq = 1
        self.next_payload_ordinal = 1
        self.payloads_dir.mkdir(parents=True, exist_ok=True)
        self.event_log_path = bundle_dir / "trace.jsonl"
        manifest = {
            "schema_version": 1,
            "trace_id": trace_id,
            "rollout_id": rollout_id,
            "root_thread_id": root_thread_id,
            "started_at_unix_ms": _unix_time_ms(),
        }
        _write_json(bundle_dir / "manifest.json", manifest)
        self.event_log_path.touch(exist_ok=True)

    @classmethod
    def create(cls, bundle_dir: str | os.PathLike[str], trace_id: str, rollout_id: str, root_thread_id: AgentThreadId) -> "TraceWriter":
        return cls(Path(bundle_dir), trace_id, rollout_id, root_thread_id)

    def write_json_payload(self, kind: RawPayloadKind, value: Any) -> RawPayloadRef:
        ordinal = self.next_payload_ordinal
        self.next_payload_ordinal += 1
        payload_ref = RawPayloadRef(f"raw_payload:{ordinal}", kind, f"payloads/{ordinal}.json")
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
    def record_started(self, model_visible_call_id: str, source_js: str) -> None:
        return None

    def record_initial_response(self, response: Any) -> None:
        return None

    def record_ended(self, response: Any) -> None:
        return None


class InferenceTraceAttempt(_NoOpTraceContext):
    def add_request_headers(self, headers: dict[str, str]) -> None:
        return None

    def record_started(self, request: Any) -> None:
        return None

    def record_completed(self, response_id: str, upstream_request_id: str | None, token_usage: Any, output_items: list[Any]) -> None:
        return None

    def record_failed(self, error: Any, upstream_request_id: str | None, output_items: list[Any]) -> None:
        return None

    def record_cancelled(self, reason: Any, upstream_request_id: str | None, output_items: list[Any]) -> None:
        return None


class InferenceTraceContext(_NoOpTraceContext):
    def start_attempt(self) -> InferenceTraceAttempt:
        return InferenceTraceAttempt.disabled()


class ToolDispatchTraceContext(_NoOpTraceContext):
    def record_completed(self, status: ExecutionStatus, result: Any) -> None:
        return None

    def record_failed(self, error: Any) -> None:
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
        context.writer = TraceWriter.create(
            Path(root) / f"trace-{uuid.uuid4()}-{metadata.thread_id}",
            str(uuid.uuid4()),
            metadata.thread_id,
            metadata.thread_id,
        )
        context.writer.append(RawTraceEventPayload.variant("RolloutStarted", trace_id=context.writer.trace_id, root_thread_id=metadata.thread_id))
        context.writer.append(RawTraceEventPayload.variant("ThreadStarted", thread_id=metadata.thread_id, agent_path=metadata.agent_path, metadata_payload=None))
        return context

    def is_enabled(self) -> bool:
        return bool(getattr(self, "enabled", False))

    def record_ended(self, status: RolloutStatus) -> None:
        writer = getattr(self, "writer", None)
        if writer is not None:
            writer.append(RawTraceEventPayload.variant("RolloutEnded", status=status))

    def start_child_thread_trace_or_disabled(self, metadata: ThreadStartedTraceMetadata) -> "ThreadTraceContext":
        return ThreadTraceContext.disabled()

    def record_protocol_event(self, event: Any) -> None:
        return None

    def record_codex_turn_event(self, default_turn_id: str, event: Any) -> None:
        return None

    def record_tool_call_event(self, codex_turn_id: str, event: Any) -> None:
        return None

    def record_agent_result_interaction(self, child_codex_turn_id: str, parent_thread_id: str, payload: AgentResultTracePayload) -> None:
        return None

    def record_codex_turn_started(self, codex_turn_id: str) -> None:
        writer = getattr(self, "writer", None)
        if writer is not None:
            writer.append(RawTraceEventPayload.variant("CodexTurnStarted", codex_turn_id=codex_turn_id, thread_id=writer.root_thread_id))

    def start_code_cell_trace(self, *args: Any, **kwargs: Any) -> CodeCellTraceContext:
        return CodeCellTraceContext.disabled()

    def code_cell_trace_context(self, *args: Any, **kwargs: Any) -> CodeCellTraceContext:
        return CodeCellTraceContext.disabled()

    def start_tool_dispatch_trace(self, invocation: Any) -> ToolDispatchTraceContext:
        return ToolDispatchTraceContext.disabled()

    def inference_trace_context(self, *args: Any, **kwargs: Any) -> InferenceTraceContext:
        return InferenceTraceContext.disabled()

    def compaction_trace_context(self, *args: Any, **kwargs: Any) -> "CompactionTraceContext":
        return CompactionTraceContext.disabled()

    def start_mcp_call_trace(self, tool_call_id: str) -> McpCallTraceContext:
        return McpCallTraceContext.disabled()


class CompactionTraceContext(_NoOpTraceContext):
    pass


class CompactionTraceAttempt(_NoOpTraceContext):
    pass


@dataclass
class CompactionCheckpointTracePayload:
    input_items: list[Any]
    replacement_items: list[Any]


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


@dataclass
class ToolDispatchPayload:
    type: str
    value: Any


@dataclass
class ToolDispatchResult:
    type: str
    value: Any


def replay_bundle(bundle_dir: str | os.PathLike[str]) -> Any:
    raise NotImplementedError("rollout-trace reducer replay is not ported yet")


__all__ = [name for name in globals() if not name.startswith("_")]
