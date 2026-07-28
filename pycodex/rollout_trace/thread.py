"""Rust-aligned owner for ``codex-rollout-trace::thread``."""

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

CODEX_ROLLOUT_TRACE_ROOT_ENV = "CODEX_ROLLOUT_TRACE_ROOT"

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
        event_type = wrapped_protocol_event_type(event)
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

from pycodex.rollout_trace.code_cell import CodeCellTraceContext

from pycodex.rollout_trace.compaction import CompactionTraceContext

from pycodex.rollout_trace.inference import InferenceTraceContext

from pycodex.rollout_trace.mcp import McpCallTraceContext

from pycodex.rollout_trace.model import AgentThreadId

from pycodex.rollout_trace.model.session import RolloutStatus

from pycodex.rollout_trace.payload import RawPayloadKind

from pycodex.rollout_trace.protocol_event import _codex_turn_trace_event, _tool_runtime_trace_event, wrapped_protocol_event_type

from pycodex.rollout_trace.raw_event import RawTraceEventContext, RawTraceEventPayload

from pycodex.rollout_trace.tool_dispatch import ToolDispatchTraceContext

from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext
