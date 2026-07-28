import importlib

import pytest


@pytest.mark.parametrize(
    ("module_name", "symbol"),
    [
        ("", "ToolDecisionSource"),
        ("config", "OtelExporter"),
        ("events", None),
        ("events.session_telemetry", "SessionTelemetry"),
        ("events.shared", "timestamp"),
        ("metrics", "global_metrics"),
        ("metrics.client", "MetricsClient"),
        ("metrics.config", "MetricsConfig"),
        ("metrics.error", "MetricsError"),
        ("metrics.names", "TOOL_CALL_COUNT_METRIC"),
        ("metrics.process", "record_process_start_once"),
        ("metrics.runtime_metrics", "RuntimeMetricsSummary"),
        ("metrics.tags", "SessionMetricTagValues"),
        ("metrics.timer", "Timer"),
        ("metrics.validation", "validate_metric_name"),
        ("otlp", "build_header_map"),
        ("provider", "OtelProvider"),
        ("targets", "is_trace_safe_target"),
        ("trace_context", "context_from_w3c_trace_context"),
    ],
)
def test_otel_item_has_rust_aligned_owner(
    module_name: str,
    symbol: str | None,
) -> None:
    """Rust source: codex-otel module graph rooted at src/lib.rs."""
    suffix = f".{module_name}" if module_name else ""
    module = importlib.import_module(f"pycodex.otel{suffix}")
    if symbol is None:
        return
    item = getattr(module, symbol)
    if callable(item):
        assert item.__module__ == module.__name__
