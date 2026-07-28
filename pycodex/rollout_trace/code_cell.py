"""Rust-aligned owner for ``codex-rollout-trace::code_cell``."""

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

from pycodex.rollout_trace.model import AgentThreadId, CodexTurnId

from pycodex.rollout_trace.raw_event import RawTraceEventContext, RawTraceEventPayload

from pycodex.rollout_trace.tool_dispatch import _code_cell_response_payload, _code_cell_status_for_runtime_response

from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext
