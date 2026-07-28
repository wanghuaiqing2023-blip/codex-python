"""Rust-aligned owner for ``codex-rollout-trace::inference``."""

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

INFERENCE_CALL_ID_HEADER = "x-codex-inference-call-id"

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

from pycodex.rollout_trace.model import AgentThreadId, CodexTurnId

from pycodex.rollout_trace.payload import RawPayloadKind, RawPayloadRef

from pycodex.rollout_trace.raw_event import RawTraceEventContext, RawTraceEventPayload

from pycodex.rollout_trace.writer import TraceWriter, _NoOpTraceContext, _jsonable
