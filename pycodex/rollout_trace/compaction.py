"""Rust-aligned owner for ``codex-rollout-trace::compaction``."""

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

from pycodex.rollout_trace.model import AgentThreadId, CodexTurnId, CompactionId

from pycodex.rollout_trace.payload import RawPayloadKind

from pycodex.rollout_trace.raw_event import RawTraceEventContext, RawTraceEventPayload

from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext
