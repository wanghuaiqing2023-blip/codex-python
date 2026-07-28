"""Rust-aligned owner for ``codex-otel::events.session_telemetry``."""

from __future__ import annotations

import json
import math
import os
import re
import threading
import time
import http.client
import contextvars
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

@dataclass
class SessionTelemetryMetadata:
    conversation_id: str
    auth_mode: str | None
    auth_env: "AuthEnvTelemetryMetadata"
    account_id: str | None
    account_email: str | None
    originator: str
    service_name: str | None
    session_source: str
    model: str
    slug: str
    log_user_prompts: bool
    app_version: str
    terminal_type: str

@dataclass
class AuthEnvTelemetryMetadata:
    openai_api_key_env_present: bool = False
    codex_api_key_env_present: bool = False
    codex_api_key_env_enabled: bool = False
    provider_env_key_name: str | None = None
    provider_env_key_present: bool | None = None
    refresh_token_url_override_present: bool = False

CODEX_OTEL_APP_VERSION = "0.0.0"

@dataclass
class SessionTelemetry:
    metadata: SessionTelemetryMetadata
    metrics: MetricsClient | None = None
    metrics_use_metadata_tags: bool = True
    log_events: list[dict[str, str]] = field(default_factory=list)
    trace_events: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        conversation_id: str,
        model: str,
        slug: str,
        account_id: str | None,
        account_email: str | None,
        auth_mode: TelemetryAuthMode | str | None,
        originator: str,
        log_user_prompts: bool,
        terminal_type: str,
        session_source: str,
    ) -> "SessionTelemetry":
        auth_mode_value = auth_mode.value if isinstance(auth_mode, TelemetryAuthMode) else auth_mode
        metadata = SessionTelemetryMetadata(
            conversation_id=str(conversation_id),
            auth_mode=auth_mode_value,
            auth_env=AuthEnvTelemetryMetadata(),
            account_id=account_id,
            account_email=account_email,
            originator=sanitize_metric_tag_value(originator),
            service_name=None,
            session_source=str(session_source),
            model=str(model),
            slug=str(slug),
            log_user_prompts=log_user_prompts,
            app_version=CODEX_OTEL_APP_VERSION,
            terminal_type=str(terminal_type),
        )
        return cls(metadata=metadata)

    def with_auth_env(self, auth_env: AuthEnvTelemetryMetadata) -> "SessionTelemetry":
        self.metadata.auth_env = auth_env
        return self

    def with_model(self, model: str, slug: str) -> "SessionTelemetry":
        self.metadata.model = str(model)
        self.metadata.slug = str(slug)
        return self

    def with_metrics_service_name(self, service_name: str) -> "SessionTelemetry":
        self.metadata.service_name = sanitize_metric_tag_value(service_name)
        return self

    def with_metrics(self, metrics: MetricsClient) -> "SessionTelemetry":
        self.metrics = metrics
        self.metrics_use_metadata_tags = True
        return self

    def with_metrics_without_metadata_tags(self, metrics: MetricsClient) -> "SessionTelemetry":
        self.metrics = metrics
        self.metrics_use_metadata_tags = False
        return self

    def with_metrics_config(self, config: MetricsConfig) -> "SessionTelemetry":
        return self.with_metrics(MetricsClient.new(config))

    def counter(self, name: str, inc: int, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> None:
        if self.metrics is None:
            return
        self.metrics.counter(name, inc, self._tags_with_metadata(tags))

    def histogram(self, name: str, value: int, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> None:
        if self.metrics is None:
            return
        self.metrics.histogram(name, value, self._tags_with_metadata(tags))

    def record_duration(
        self,
        name: str,
        duration_ms: int | float,
        tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    ) -> None:
        if self.metrics is None:
            return
        self.metrics.record_duration(name, duration_ms, self._tags_with_metadata(tags))

    def record_startup_phase(
        self,
        phase: str,
        duration_ms: int | float,
        status: str | None = None,
    ) -> None:
        tags = [("phase", str(phase))]
        if status is not None:
            tags.append(("status", str(status)))
        self.record_duration(STARTUP_PHASE_DURATION_METRIC, duration_ms, tags)
        attrs = {
            "startup.phase": phase,
            "startup.status": status,
            "duration_ms": _duration_to_millis(duration_ms),
        }
        self._record_log_event("codex.startup_phase", attrs)
        self._record_trace_event("codex.startup_phase", attrs)

    def start_timer(self, name: str, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> Timer:
        if self.metrics is None:
            raise MetricsError("metrics exporter is disabled")
        return self.metrics.start_timer(name, self._tags_with_metadata(tags))

    def shutdown_metrics(self) -> None:
        if self.metrics is not None:
            self.metrics.shutdown()

    def snapshot_metrics(self) -> dict[str, Any]:
        if self.metrics is None:
            raise MetricsError("metrics exporter is disabled")
        return self.metrics.snapshot()

    def reset_runtime_metrics(self) -> None:
        try:
            self.snapshot_metrics()
        except MetricsError:
            return

    def runtime_metrics_summary(self) -> RuntimeMetricsSummary | None:
        try:
            summary = RuntimeMetricsSummary.from_snapshot(self.snapshot_metrics())
        except MetricsError:
            return None
        return None if summary.is_empty() else summary

    def record_plugin_install_elicitation_sent(self, tool_type: str, tool_id: str, tool_name: str) -> None:
        self.counter(PLUGIN_INSTALL_ELICITATION_SENT_METRIC, 1, [( "tool_type", tool_type)])

    def record_plugin_install_suggestion(
        self,
        tool_type: str,
        tool_id: str,
        tool_name: str,
        response_action: str,
        user_confirmed: bool,
        completed: bool,
    ) -> None:
        self.counter(
            PLUGIN_INSTALL_SUGGESTION_METRIC,
            1,
            [
                ("tool_type", tool_type),
                ("response_action", response_action),
                ("completed", "true" if completed else "false"),
            ],
        )

    def record_responses(self, handle_responses_span: Any, event: Any) -> None:
        response_type = self.responses_type(event)
        _record_span_attr(handle_responses_span, "otel.name", response_type)

        kind = _response_event_kind(event)
        value = _response_event_value(event)
        if kind in {"output_item_done", "output_item_added"}:
            _record_span_attr(
                handle_responses_span,
                "from",
                "output_item_done" if kind == "output_item_done" else "output_item_added",
            )
            if _response_item_type(value) == "function_call":
                name = _get_value(value, "name")
                if name is not None:
                    _record_span_attr(handle_responses_span, "tool_name", str(name))
            return

        if kind == "completed":
            token_usage = _get_value(value, "token_usage")
            if token_usage is None:
                return
            _record_span_attr(handle_responses_span, "gen_ai.usage.input_tokens", _token_usage_value(token_usage, "input_tokens"))
            _record_span_attr(
                handle_responses_span,
                "gen_ai.usage.cache_read.input_tokens",
                _token_usage_cached_input(token_usage),
            )
            _record_span_attr(handle_responses_span, "gen_ai.usage.output_tokens", _token_usage_value(token_usage, "output_tokens"))
            _record_span_attr(
                handle_responses_span,
                "codex.usage.reasoning_output_tokens",
                _token_usage_value(token_usage, "reasoning_output_tokens"),
            )
            _record_span_attr(handle_responses_span, "codex.usage.total_tokens", _token_usage_value(token_usage, "total_tokens"))

    @staticmethod
    def responses_type(event: Any) -> str:
        kind = _response_event_kind(event)
        if kind == "created":
            return "created"
        if kind in {"output_item_done", "output_item_added"}:
            return SessionTelemetry.responses_item_type(_response_event_value(event))
        if kind == "completed":
            return "completed"
        if kind == "output_text_delta":
            return "text_delta"
        if kind == "tool_call_input_delta":
            return "tool_input_delta"
        if kind == "reasoning_summary_delta":
            return "reasoning_summary_delta"
        if kind == "reasoning_content_delta":
            return "reasoning_content_delta"
        if kind == "reasoning_summary_part_added":
            return "reasoning_summary_part_added"
        if kind == "server_model":
            return "server_model"
        if kind == "model_verifications":
            return "model_verifications"
        if kind == "server_reasoning_included":
            return "server_reasoning_included"
        if kind == "rate_limits":
            return "rate_limits"
        if kind == "models_etag":
            return "models_etag"
        return str(kind)

    @staticmethod
    def responses_item_type(item: Any) -> str:
        item_type = _response_item_type(item)
        if item_type == "message":
            return f"message_from_{_get_value(item, 'role')}"
        mapping = {
            "reasoning": "reasoning",
            "local_shell_call": "local_shell_call",
            "function_call": "function_call",
            "tool_search_call": "tool_search_call",
            "function_call_output": "function_call_output",
            "tool_search_output": "tool_search_output",
            "custom_tool_call": "custom_tool_call",
            "custom_tool_call_output": "custom_tool_call_output",
            "web_search_call": "web_search_call",
            "image_generation_call": "image_generation_call",
            "compaction": "compaction",
            "compaction_trigger": "compaction_trigger",
            "context_compaction": "context_compaction",
            "other": "other",
        }
        return mapping.get(str(item_type), "other")

    def conversation_starts(
        self,
        provider_name: str,
        reasoning_effort: str | None = None,
        reasoning_summary: str | None = None,
        context_window: int | None = None,
        auto_compact_token_limit: int | None = None,
        approval_policy: str | None = None,
        sandbox_policy: str | None = None,
        mcp_servers: list[str] | tuple[str, ...] = (),
    ) -> None:
        common: dict[str, Any] = {
            "provider_name": provider_name,
            "reasoning_effort": reasoning_effort,
            "reasoning_summary": reasoning_summary,
            "context_window": context_window,
            "auto_compact_token_limit": auto_compact_token_limit,
            "approval_policy": approval_policy,
            "sandbox_policy": sandbox_policy,
        }
        common.update(_auth_env_event_attrs(self.metadata.auth_env))
        self._record_log_event(
            "codex.conversation_starts",
            {**common, "mcp_servers": ", ".join(str(server) for server in mcp_servers)},
        )
        self._record_trace_event(
            "codex.conversation_starts",
            {**common, "mcp_server_count": len(mcp_servers)},
        )

    def user_prompt(self, items: list[Any] | tuple[Any, ...]) -> None:
        prompt_parts: list[str] = []
        text_input_count = 0
        image_input_count = 0
        local_image_input_count = 0
        for item in items:
            kind = _user_input_kind(item)
            if kind == "text":
                text_input_count += 1
                prompt_parts.append(_user_input_text(item))
            elif kind == "image":
                image_input_count += 1
            elif kind == "local_image":
                local_image_input_count += 1
        prompt = "".join(prompt_parts)
        prompt_to_log = prompt if self.metadata.log_user_prompts else "[REDACTED]"
        prompt_len = str(len(prompt))
        self._record_log_event(
            "codex.user_prompt",
            {"prompt_length": prompt_len, "prompt": prompt_to_log},
        )
        self._record_trace_event(
            "codex.user_prompt",
            {
                "prompt_length": prompt_len,
                "text_input_count": str(text_input_count),
                "image_input_count": str(image_input_count),
                "local_image_input_count": str(local_image_input_count),
            },
        )

    def tool_result_with_tags(
        self,
        tool_name: str,
        call_id: str,
        arguments: str,
        duration_ms: int | float,
        success: bool,
        output: str,
        extra_tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
        extra_trace_fields: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    ) -> None:
        success_str = "true" if success else "false"
        tags = [("tool", tool_name), ("success", success_str)]
        tags.extend((str(key), str(value)) for key, value in extra_tags)
        self.counter(TOOL_CALL_COUNT_METRIC, 1, tags)
        self.record_duration(TOOL_CALL_DURATION_METRIC, duration_ms, tags)
        trace_fields = {str(key): str(value) for key, value in extra_trace_fields}
        mcp_server = trace_fields.get("mcp_server", "")
        mcp_server_origin = trace_fields.get("mcp_server_origin", "")
        self._record_log_event(
            "codex.tool_result",
            {
                "tool_name": tool_name,
                "call_id": call_id,
                "arguments": arguments,
                "duration_ms": str(_duration_to_millis(duration_ms)),
                "success": success_str,
                "output": output,
                "mcp_server": mcp_server,
                "mcp_server_origin": mcp_server_origin,
            },
        )
        self._record_trace_event(
            "codex.tool_result",
            {
                "tool_name": tool_name,
                "call_id": call_id,
                "duration_ms": str(_duration_to_millis(duration_ms)),
                "success": success_str,
                "arguments_length": str(len(arguments)),
                "output_length": str(len(output)),
                "output_line_count": str(_rust_line_count(output)),
                "tool_origin": "mcp" if mcp_server else "builtin",
                "mcp_tool": "true" if mcp_server else "false",
            },
        )

    def record_api_request(
        self,
        attempt: int,
        status: int | None,
        error: str | None,
        duration_ms: int | float,
        auth_header_attached: bool = False,
        auth_header_name: str | None = None,
        retry_after_unauthorized: bool = False,
        recovery_mode: str | None = None,
        recovery_phase: str | None = None,
        endpoint: str = "unknown",
        request_id: str | None = None,
        cf_ray: str | None = None,
        auth_error: str | None = None,
        auth_error_code: str | None = None,
    ) -> None:
        success = status is not None and 200 <= status <= 299 and error is None
        status_str = str(status) if status is not None else "none"
        tags = [("status", status_str), ("success", "true" if success else "false")]
        self.counter(API_CALL_COUNT_METRIC, 1, tags)
        self.record_duration(API_CALL_DURATION_METRIC, duration_ms, tags)
        attrs: dict[str, Any] = {
            "duration_ms": _duration_to_millis(duration_ms),
            "http.response.status_code": status,
            "error.message": error,
            "attempt": attempt,
            "auth.header_attached": auth_header_attached,
            "auth.header_name": auth_header_name,
            "auth.retry_after_unauthorized": retry_after_unauthorized,
            "auth.recovery_mode": recovery_mode,
            "auth.recovery_phase": recovery_phase,
            "endpoint": endpoint,
            "auth.request_id": request_id,
            "auth.cf_ray": cf_ray,
            "auth.error": auth_error,
            "auth.error_code": auth_error_code,
        }
        attrs.update(_auth_env_event_attrs(self.metadata.auth_env))
        self._record_log_event("codex.api_request", attrs)
        self._record_trace_event("codex.api_request", attrs)

    def record_auth_recovery(
        self,
        mode: str,
        step: str,
        outcome: str,
        request_id: str | None = None,
        cf_ray: str | None = None,
        auth_error: str | None = None,
        auth_error_code: str | None = None,
        recovery_reason: str | None = None,
        auth_state_changed: bool | None = None,
    ) -> None:
        attrs = {
            "auth.mode": mode,
            "auth.step": step,
            "auth.outcome": outcome,
            "auth.request_id": request_id,
            "auth.cf_ray": cf_ray,
            "auth.error": auth_error,
            "auth.error_code": auth_error_code,
            "auth.recovery_reason": recovery_reason,
            "auth.state_changed": auth_state_changed,
        }
        self._record_log_event("codex.auth_recovery", attrs)
        self._record_trace_event("codex.auth_recovery", attrs)

    def record_websocket_connect(
        self,
        duration_ms: int | float,
        status: int | None = None,
        error: str | None = None,
        auth_header_attached: bool = False,
        auth_header_name: str | None = None,
        retry_after_unauthorized: bool = False,
        recovery_mode: str | None = None,
        recovery_phase: str | None = None,
        endpoint: str = "unknown",
        connection_reused: bool = False,
        request_id: str | None = None,
        cf_ray: str | None = None,
        auth_error: str | None = None,
        auth_error_code: str | None = None,
    ) -> None:
        success = error is None and (status is None or 200 <= status <= 299)
        attrs: dict[str, Any] = {
            "duration_ms": _duration_to_millis(duration_ms),
            "http.response.status_code": status,
            "success": success,
            "error.message": error,
            "auth.header_attached": auth_header_attached,
            "auth.header_name": auth_header_name,
            "auth.retry_after_unauthorized": retry_after_unauthorized,
            "auth.recovery_mode": recovery_mode,
            "auth.recovery_phase": recovery_phase,
            "endpoint": endpoint,
            "auth.connection_reused": connection_reused,
            "auth.request_id": request_id,
            "auth.cf_ray": cf_ray,
            "auth.error": auth_error,
            "auth.error_code": auth_error_code,
        }
        attrs.update(_auth_env_event_attrs(self.metadata.auth_env))
        self._record_log_event("codex.websocket_connect", attrs)
        self._record_trace_event("codex.websocket_connect", attrs)

    def record_websocket_request(
        self,
        duration_ms: int | float,
        error: str | None = None,
        connection_reused: bool = False,
    ) -> None:
        success_str = "true" if error is None else "false"
        tags = [("success", success_str)]
        self.counter(WEBSOCKET_REQUEST_COUNT_METRIC, 1, tags)
        self.record_duration(WEBSOCKET_REQUEST_DURATION_METRIC, duration_ms, tags)
        attrs: dict[str, Any] = {
            "duration_ms": _duration_to_millis(duration_ms),
            "success": success_str,
            "error.message": error,
            "auth.connection_reused": connection_reused,
        }
        attrs.update(_auth_env_event_attrs(self.metadata.auth_env))
        self._record_log_event("codex.websocket_request", attrs)
        self._record_trace_event("codex.websocket_request", attrs)

    def record_websocket_event(self, message: Any, duration_ms: int | float) -> None:
        kind: str | None = None
        success = True
        if message is None:
            success = False
        elif isinstance(message, bytes):
            success = False
        else:
            try:
                value = json.loads(message) if isinstance(message, str) else dict(message)
                kind = value.get("type")
                if kind == RESPONSES_WEBSOCKET_TIMING_KIND:
                    self.record_responses_websocket_timing_metrics(value)
                if kind == "response.failed":
                    success = False
            except Exception:
                kind = "parse_error"
                success = False
        kind_str = kind or WEBSOCKET_UNKNOWN_KIND
        success_str = "true" if success else "false"
        tags = [("kind", kind_str), ("success", success_str)]
        self.counter(WEBSOCKET_EVENT_COUNT_METRIC, 1, tags)
        self.record_duration(WEBSOCKET_EVENT_DURATION_METRIC, duration_ms, tags)

    def log_sse_event(self, event: str | None, data: str | None, duration_ms: int | float) -> None:
        if data is not None and data.strip() == "[DONE]":
            self.sse_event(event or "", duration_ms)
            return
        if event == "response.failed":
            self.sse_event_failed(event, duration_ms, data or "response.failed")
            return
        if data:
            try:
                json.loads(data)
            except json.JSONDecodeError as exc:
                self.sse_event_failed(event, duration_ms, str(exc))
                return
        self.sse_event(event or "", duration_ms)

    def sse_event(self, kind: str, duration_ms: int | float) -> None:
        tags = [("kind", kind), ("success", "true")]
        self.counter(SSE_EVENT_COUNT_METRIC, 1, tags)
        self.record_duration(SSE_EVENT_DURATION_METRIC, duration_ms, tags)

    def sse_event_failed(self, kind: str | None, duration_ms: int | float, error: Any) -> None:
        kind_str = kind or SSE_UNKNOWN_KIND
        tags = [("kind", kind_str), ("success", "false")]
        self.counter(SSE_EVENT_COUNT_METRIC, 1, tags)
        self.record_duration(SSE_EVENT_DURATION_METRIC, duration_ms, tags)

    def record_responses_websocket_timing_metrics(self, value: Mapping[str, Any]) -> None:
        timing = value.get(RESPONSES_WEBSOCKET_TIMING_METRICS_FIELD) or {}
        mapping = (
            (RESPONSES_API_OVERHEAD_FIELD, RESPONSES_API_OVERHEAD_DURATION_METRIC),
            (RESPONSES_API_INFERENCE_FIELD, RESPONSES_API_INFERENCE_TIME_DURATION_METRIC),
            (RESPONSES_API_ENGINE_IAPI_TTFT_FIELD, RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC),
            (RESPONSES_API_ENGINE_SERVICE_TTFT_FIELD, RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC),
            (RESPONSES_API_ENGINE_IAPI_TBT_FIELD, RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC),
            (RESPONSES_API_ENGINE_SERVICE_TBT_FIELD, RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC),
        )
        for field_name, metric_name in mapping:
            duration = _duration_from_ms_value(timing.get(field_name))
            if duration is not None:
                self.record_duration(metric_name, duration, [])

    def _tags_with_metadata(
        self, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...]
    ) -> list[tuple[str, str]]:
        merged = self._metadata_tag_refs()
        merged.extend((str(key), str(value)) for key, value in tags)
        return merged

    def _metadata_tag_refs(self) -> list[tuple[str, str]]:
        if not self.metrics_use_metadata_tags:
            return []
        return SessionMetricTagValues(
            auth_mode=self.metadata.auth_mode,
            session_source=self.metadata.session_source,
            originator=self.metadata.originator,
            service_name=self.metadata.service_name,
            model=self.metadata.model,
            app_version=self.metadata.app_version,
        ).into_tags()

    def _record_log_event(self, event_name: str, attrs: Mapping[str, Any]) -> None:
        event = self._base_log_event(event_name)
        _extend_event_attrs(event, attrs)
        self.log_events.append(event)

    def _record_trace_event(self, event_name: str, attrs: Mapping[str, Any]) -> None:
        event = self._base_trace_event(event_name)
        _extend_event_attrs(event, attrs)
        self.trace_events.append(event)

    def _base_log_event(self, event_name: str) -> dict[str, str]:
        event = {
            "target": OTEL_LOG_ONLY_TARGET,
            "event.name": event_name,
            "conversation.id": self.metadata.conversation_id,
            "app.version": self.metadata.app_version,
            "originator": self.metadata.originator,
            "terminal.type": self.metadata.terminal_type,
            "model": self.metadata.model,
            "slug": self.metadata.slug,
        }
        if self.metadata.auth_mode is not None:
            event["auth_mode"] = self.metadata.auth_mode
        if self.metadata.account_id is not None:
            event["user.account_id"] = self.metadata.account_id
        if self.metadata.account_email is not None:
            event["user.email"] = self.metadata.account_email
        return event

    def _base_trace_event(self, event_name: str) -> dict[str, str]:
        event = {
            "target": OTEL_TRACE_SAFE_TARGET,
            "event.name": event_name,
            "conversation.id": self.metadata.conversation_id,
            "app.version": self.metadata.app_version,
            "originator": self.metadata.originator,
            "terminal.type": self.metadata.terminal_type,
            "model": self.metadata.model,
            "slug": self.metadata.slug,
        }
        if self.metadata.auth_mode is not None:
            event["auth_mode"] = self.metadata.auth_mode
        return event

def _record_span_attr(span: Any, key: str, value: Any) -> None:
    if hasattr(span, "record") and callable(span.record):
        span.record(key, value)
        return
    if isinstance(span, dict):
        span[key] = value
        return
    attrs = getattr(span, "attributes", None)
    if isinstance(attrs, dict):
        attrs[key] = value
        return
    setattr(span, key.replace(".", "_"), value)

def _response_event_kind(event: Any) -> str:
    return str(_get_value(event, "kind") or _get_value(event, "type") or event)

def _response_event_value(event: Any) -> Any:
    return _get_value(event, "value")

def _response_item_type(item: Any) -> str:
    return str(_get_value(item, "type") or "other")

def _get_value(value: Any, key: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(key)
    return getattr(value, key, None)

def _token_usage_value(token_usage: Any, key: str) -> int:
    value = _get_value(token_usage, key)
    return int(value or 0)

def _token_usage_cached_input(token_usage: Any) -> int:
    cached_input = getattr(token_usage, "cached_input", None)
    if callable(cached_input):
        return int(cached_input())
    return _token_usage_value(token_usage, "cached_input_tokens")

def _extend_event_attrs(event: dict[str, str], attrs: Mapping[str, Any]) -> None:
    for key, value in attrs.items():
        if value is not None:
            event[str(key)] = _event_value(value)

def _auth_env_event_attrs(auth_env: AuthEnvTelemetryMetadata) -> dict[str, Any]:
    return {
        "auth.env_openai_api_key_present": auth_env.openai_api_key_env_present,
        "auth.env_codex_api_key_present": auth_env.codex_api_key_env_present,
        "auth.env_codex_api_key_enabled": auth_env.codex_api_key_env_enabled,
        "auth.env_provider_key_name": auth_env.provider_env_key_name,
        "auth.env_provider_key_present": auth_env.provider_env_key_present,
        "auth.env_refresh_token_url_override_present": auth_env.refresh_token_url_override_present,
    }

def _event_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)

def _duration_to_millis(value: int | float) -> int:
    return int(value)

def _rust_line_count(value: str) -> int:
    if value == "":
        return 0
    return len(value.splitlines())

def _user_input_kind(item: Any) -> str:
    if isinstance(item, Mapping):
        kind = item.get("type") or item.get("kind")
        if kind in {"Text", "text"}:
            return "text"
        if kind in {"Image", "image"}:
            return "image"
        if kind in {"LocalImage", "local_image", "localImage"}:
            return "local_image"
    kind = getattr(item, "type", None) or getattr(item, "kind", None)
    if callable(kind):
        kind = kind()
    kind_text = str(kind or "").lower()
    if kind_text in {"text", "userinput.text"}:
        return "text"
    if kind_text in {"image", "userinput.image"}:
        return "image"
    if kind_text in {"localimage", "local_image", "userinput.localimage"}:
        return "local_image"
    if hasattr(item, "text"):
        return "text"
    if hasattr(item, "image_url"):
        return "image"
    if hasattr(item, "path"):
        return "local_image"
    return ""

def _user_input_text(item: Any) -> str:
    if isinstance(item, Mapping):
        return str(item.get("text", ""))
    text = getattr(item, "text", "")
    return str(text() if callable(text) else text)

SSE_UNKNOWN_KIND = "unknown"

WEBSOCKET_UNKNOWN_KIND = "unknown"

RESPONSES_WEBSOCKET_TIMING_KIND = "responsesapi.websocket_timing"

RESPONSES_WEBSOCKET_TIMING_METRICS_FIELD = "timing_metrics"

RESPONSES_API_OVERHEAD_FIELD = "responses_duration_excl_engine_and_client_tool_time_ms"

RESPONSES_API_INFERENCE_FIELD = "engine_service_total_ms"

RESPONSES_API_ENGINE_IAPI_TTFT_FIELD = "engine_iapi_ttft_total_ms"

RESPONSES_API_ENGINE_SERVICE_TTFT_FIELD = "engine_service_ttft_total_ms"

RESPONSES_API_ENGINE_IAPI_TBT_FIELD = "engine_iapi_tbt_across_engine_calls_ms"

RESPONSES_API_ENGINE_SERVICE_TBT_FIELD = "engine_service_tbt_across_engine_calls_ms"

from pycodex.otel import TelemetryAuthMode
from pycodex.otel.metrics.client import MetricsClient
from pycodex.otel.metrics.config import MetricsConfig
from pycodex.otel.metrics.error import MetricsError
from pycodex.otel.metrics.names import API_CALL_COUNT_METRIC, API_CALL_DURATION_METRIC, PLUGIN_INSTALL_ELICITATION_SENT_METRIC, PLUGIN_INSTALL_SUGGESTION_METRIC, RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC, RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC, RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC, RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC, RESPONSES_API_INFERENCE_TIME_DURATION_METRIC, RESPONSES_API_OVERHEAD_DURATION_METRIC, SSE_EVENT_COUNT_METRIC, SSE_EVENT_DURATION_METRIC, STARTUP_PHASE_DURATION_METRIC, TOOL_CALL_COUNT_METRIC, TOOL_CALL_DURATION_METRIC, WEBSOCKET_EVENT_COUNT_METRIC, WEBSOCKET_EVENT_DURATION_METRIC, WEBSOCKET_REQUEST_COUNT_METRIC, WEBSOCKET_REQUEST_DURATION_METRIC
from pycodex.otel.metrics.runtime_metrics import RuntimeMetricsSummary, _duration_from_ms_value
from pycodex.otel.metrics.tags import SessionMetricTagValues
from pycodex.otel.metrics.timer import Timer
from pycodex.otel.targets import OTEL_LOG_ONLY_TARGET, OTEL_TRACE_SAFE_TARGET
from pycodex.utils.string import sanitize_metric_tag_value

__all__ = [name for name in globals() if not name.startswith("_")]
