"""Rust-aligned owner for ``codex-otel::crate``."""

from __future__ import annotations

from enum import Enum

class TelemetryAuthMode(str, Enum):
    API_KEY = "api_key"
    CHATGPT = "chatgpt"

class ToolDecisionSource(str, Enum):
    AUTOMATED_REVIEWER = "automated_reviewer"
    CONFIG = "config"
    USER = "user"

def start_global_timer(name: str, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> Timer:
    metrics = global_metrics()
    if metrics is None:
        raise MetricsError("metrics exporter is disabled")
    return metrics.start_timer(name, tags)

def global_statsig_metrics_settings() -> StatsigMetricsSettings | None:
    return _GLOBAL_STATSIG_METRICS_SETTINGS

from pycodex.otel.config import (
    OtelExporter,
    OtelHttpProtocol,
    OtelSettings,
    OtelTlsConfig,
    StatsigMetricsSettings,
    validate_span_attributes,
)
from pycodex.otel.events.session_telemetry import (
    AuthEnvTelemetryMetadata,
    SessionTelemetry,
    SessionTelemetryMetadata,
)
from pycodex.otel.metrics import _GLOBAL_STATSIG_METRICS_SETTINGS, global_metrics
from pycodex.otel.metrics.error import MetricsError
from pycodex.otel.metrics.timer import Timer
from pycodex.protocol import W3cTraceContext
from pycodex.utils.string import sanitize_metric_tag_value
from pycodex.otel.metrics import *
from pycodex.otel.metrics.runtime_metrics import (
    RuntimeMetricTotals,
    RuntimeMetricsSummary,
)
from pycodex.otel.provider import OtelProvider
from pycodex.otel.trace_context import (
    context_from_w3c_trace_context,
    current_span_trace_id,
    current_span_w3c_trace_context,
    set_parent_from_context,
    set_parent_from_w3c_trace_context,
    span_w3c_trace_context,
    traceparent_context_from_env,
    validate_tracestate_entries,
    validate_tracestate_member,
)

__all__ = [name for name in globals() if not name.startswith("_")]
