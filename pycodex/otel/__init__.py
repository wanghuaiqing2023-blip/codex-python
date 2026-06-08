"""Source-verified public interface slice for ``codex-otel``.

Rust source:
- ``codex/codex-rs/otel/src/lib.rs``
- ``codex/codex-rs/otel/src/config.rs``
- ``codex/codex-rs/otel/src/trace_context.rs``
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class OtelHttpProtocol(str, Enum):
    BINARY = "binary"
    JSON = "json"


@dataclass
class OtelTlsConfig:
    ca_certificate: Any | None = None
    client_certificate: Any | None = None
    client_private_key: Any | None = None


@dataclass
class OtelExporter:
    kind: str
    endpoint: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    protocol: OtelHttpProtocol | None = None
    tls: OtelTlsConfig | None = None

    @classmethod
    def None_(cls) -> "OtelExporter":
        return cls("none")

    @classmethod
    def Statsig(cls) -> "OtelExporter":
        return cls("statsig")

    @classmethod
    def OtlpGrpc(cls, endpoint: str, headers: dict[str, str] | None = None, tls: OtelTlsConfig | None = None) -> "OtelExporter":
        return cls("otlp_grpc", endpoint, headers or {}, None, tls)

    @classmethod
    def OtlpHttp(cls, endpoint: str, headers: dict[str, str] | None = None, protocol: OtelHttpProtocol = OtelHttpProtocol.JSON, tls: OtelTlsConfig | None = None) -> "OtelExporter":
        return cls("otlp_http", endpoint, headers or {}, protocol, tls)


@dataclass
class OtelSettings:
    environment: str
    service_name: str
    service_version: str
    codex_home: Path
    exporter: OtelExporter
    trace_exporter: OtelExporter
    metrics_exporter: OtelExporter
    runtime_metrics: bool
    span_attributes: dict[str, str] = field(default_factory=dict)
    tracestate: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass(frozen=True)
class StatsigMetricsSettings:
    environment: str


def validate_span_attributes(attributes: dict[str, str]) -> None:
    if any(key == "" for key in attributes):
        raise ValueError("configured span attribute key must not be empty")


def validate_tracestate_entries(entries: dict[str, dict[str, str]]) -> None:
    for key, fields in entries.items():
        validate_tracestate_member(key, fields)


def validate_tracestate_member(member_key: str, fields: dict[str, str]) -> None:
    if not member_key or "," in member_key or "=" in member_key:
        raise ValueError("invalid configured tracestate")
    for field_key, value in fields.items():
        if not field_key or any(ch in field_key for ch in ":;,="):
            raise ValueError(f"invalid configured tracestate field key {member_key}.{field_key}")
        if "," in value or "=" in value or ";" in value:
            raise ValueError(f"invalid configured tracestate value for {member_key}.{field_key}")


def sanitize_metric_tag_value(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", value)


@dataclass(frozen=True)
class W3cTraceContext:
    traceparent: str | None = None
    tracestate: str | None = None


def context_from_w3c_trace_context(trace: W3cTraceContext) -> W3cTraceContext | None:
    if trace.traceparent is None:
        return None
    return trace if _valid_traceparent(trace.traceparent) else None


def traceparent_context_from_env() -> W3cTraceContext | None:
    traceparent = os.environ.get("TRACEPARENT")
    if not traceparent or not _valid_traceparent(traceparent):
        return None
    return W3cTraceContext(traceparent, os.environ.get("TRACESTATE"))


def _valid_traceparent(value: str) -> bool:
    return bool(re.fullmatch(r"00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}", value))


def current_span_trace_id() -> str | None:
    return None


def current_span_w3c_trace_context() -> W3cTraceContext | None:
    return None


def span_w3c_trace_context(_span: Any) -> W3cTraceContext | None:
    return None


def set_parent_from_context(_span: Any, _context: Any) -> None:
    return None


def set_parent_from_w3c_trace_context(_span: Any, trace: W3cTraceContext) -> bool:
    return context_from_w3c_trace_context(trace) is not None


class Timer:
    def __init__(self) -> None:
        self.started_at = time.monotonic()

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)


class MetricsError(Exception):
    pass


def start_global_timer(_name: str, _tags: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> Timer:
    raise MetricsError("exporter disabled")


def global_statsig_metrics_settings() -> StatsigMetricsSettings | None:
    return None


@dataclass
class SessionTelemetry:
    session_id: str | None = None


@dataclass
class SessionTelemetryMetadata:
    fields: dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthEnvTelemetryMetadata:
    fields: dict[str, Any] = field(default_factory=dict)


RuntimeMetricTotals = dict[str, Any]
RuntimeMetricsSummary = dict[str, Any]
OtelProvider = object

GOAL_BLOCKED_METRIC = "codex_goal_blocked"
GOAL_BUDGET_LIMITED_METRIC = "codex_goal_budget_limited"
GOAL_COMPLETED_METRIC = "codex_goal_completed"
GOAL_CREATED_METRIC = "codex_goal_created"
GOAL_DURATION_SECONDS_METRIC = "codex_goal_duration_seconds"
GOAL_RESUMED_METRIC = "codex_goal_resumed"
GOAL_TOKEN_COUNT_METRIC = "codex_goal_token_count"
GOAL_USAGE_LIMITED_METRIC = "codex_goal_usage_limited"
GUARDIAN_REVIEW_COUNT_METRIC = "codex_guardian_review_count"
GUARDIAN_REVIEW_DURATION_METRIC = "codex_guardian_review_duration"
GUARDIAN_REVIEW_TOKEN_USAGE_METRIC = "codex_guardian_review_token_usage"
GUARDIAN_REVIEW_TTFT_DURATION_METRIC = "codex_guardian_review_ttft_duration"
HOOK_RUN_DURATION_METRIC = "codex_hook_run_duration"
HOOK_RUN_METRIC = "codex_hook_run"
TOOL_CALL_UNIFIED_EXEC_METRIC = "codex_tool_call_unified_exec"


__all__ = [name for name in globals() if not name.startswith("_")]
