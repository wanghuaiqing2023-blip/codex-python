"""Rust-aligned owner for ``codex-otel::metrics.runtime_metrics``."""

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

U64_MAX = (1 << 64) - 1

@dataclass
class RuntimeMetricTotals:
    count: int = 0
    duration_ms: int = 0

    def is_empty(self) -> bool:
        return self.count == 0 and self.duration_ms == 0

    def merge(self, other: "RuntimeMetricTotals") -> None:
        self.count = min(U64_MAX, self.count + other.count)
        self.duration_ms = min(U64_MAX, self.duration_ms + other.duration_ms)

@dataclass
class RuntimeMetricsSummary:
    tool_calls: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    api_calls: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    streaming_events: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    websocket_calls: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    websocket_events: RuntimeMetricTotals = field(default_factory=RuntimeMetricTotals)
    responses_api_overhead_ms: int = 0
    responses_api_inference_time_ms: int = 0
    responses_api_engine_iapi_ttft_ms: int = 0
    responses_api_engine_service_ttft_ms: int = 0
    responses_api_engine_iapi_tbt_ms: int = 0
    responses_api_engine_service_tbt_ms: int = 0
    turn_ttft_ms: int = 0
    turn_ttfm_ms: int = 0

    def is_empty(self) -> bool:
        return (
            self.tool_calls.is_empty()
            and self.api_calls.is_empty()
            and self.streaming_events.is_empty()
            and self.websocket_calls.is_empty()
            and self.websocket_events.is_empty()
            and self.responses_api_overhead_ms == 0
            and self.responses_api_inference_time_ms == 0
            and self.responses_api_engine_iapi_ttft_ms == 0
            and self.responses_api_engine_service_ttft_ms == 0
            and self.responses_api_engine_iapi_tbt_ms == 0
            and self.responses_api_engine_service_tbt_ms == 0
            and self.turn_ttft_ms == 0
            and self.turn_ttfm_ms == 0
        )

    def merge(self, other: "RuntimeMetricsSummary") -> None:
        self.tool_calls.merge(other.tool_calls)
        self.api_calls.merge(other.api_calls)
        self.streaming_events.merge(other.streaming_events)
        self.websocket_calls.merge(other.websocket_calls)
        self.websocket_events.merge(other.websocket_events)
        for field_name in (
            "responses_api_overhead_ms",
            "responses_api_inference_time_ms",
            "responses_api_engine_iapi_ttft_ms",
            "responses_api_engine_service_ttft_ms",
            "responses_api_engine_iapi_tbt_ms",
            "responses_api_engine_service_tbt_ms",
            "turn_ttft_ms",
            "turn_ttfm_ms",
        ):
            value = getattr(other, field_name)
            if value > 0:
                setattr(self, field_name, value)

    def responses_api_summary(self) -> "RuntimeMetricsSummary":
        return RuntimeMetricsSummary(
            responses_api_overhead_ms=self.responses_api_overhead_ms,
            responses_api_inference_time_ms=self.responses_api_inference_time_ms,
            responses_api_engine_iapi_ttft_ms=self.responses_api_engine_iapi_ttft_ms,
            responses_api_engine_service_ttft_ms=self.responses_api_engine_service_ttft_ms,
            responses_api_engine_iapi_tbt_ms=self.responses_api_engine_iapi_tbt_ms,
            responses_api_engine_service_tbt_ms=self.responses_api_engine_service_tbt_ms,
        )

    @classmethod
    def from_snapshot(cls, snapshot: Any) -> "RuntimeMetricsSummary":
        return cls(
            tool_calls=RuntimeMetricTotals(
                count=sum_counter(snapshot, TOOL_CALL_COUNT_METRIC),
                duration_ms=sum_histogram_ms(snapshot, TOOL_CALL_DURATION_METRIC),
            ),
            api_calls=RuntimeMetricTotals(
                count=sum_counter(snapshot, API_CALL_COUNT_METRIC),
                duration_ms=sum_histogram_ms(snapshot, API_CALL_DURATION_METRIC),
            ),
            streaming_events=RuntimeMetricTotals(
                count=sum_counter(snapshot, SSE_EVENT_COUNT_METRIC),
                duration_ms=sum_histogram_ms(snapshot, SSE_EVENT_DURATION_METRIC),
            ),
            websocket_calls=RuntimeMetricTotals(
                count=sum_counter(snapshot, WEBSOCKET_REQUEST_COUNT_METRIC),
                duration_ms=sum_histogram_ms(snapshot, WEBSOCKET_REQUEST_DURATION_METRIC),
            ),
            websocket_events=RuntimeMetricTotals(
                count=sum_counter(snapshot, WEBSOCKET_EVENT_COUNT_METRIC),
                duration_ms=sum_histogram_ms(snapshot, WEBSOCKET_EVENT_DURATION_METRIC),
            ),
            responses_api_overhead_ms=sum_histogram_ms(snapshot, RESPONSES_API_OVERHEAD_DURATION_METRIC),
            responses_api_inference_time_ms=sum_histogram_ms(snapshot, RESPONSES_API_INFERENCE_TIME_DURATION_METRIC),
            responses_api_engine_iapi_ttft_ms=sum_histogram_ms(snapshot, RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC),
            responses_api_engine_service_ttft_ms=sum_histogram_ms(
                snapshot, RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC
            ),
            responses_api_engine_iapi_tbt_ms=sum_histogram_ms(snapshot, RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC),
            responses_api_engine_service_tbt_ms=sum_histogram_ms(
                snapshot, RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC
            ),
            turn_ttft_ms=sum_histogram_ms(snapshot, TURN_TTFT_DURATION_METRIC),
            turn_ttfm_ms=sum_histogram_ms(snapshot, TURN_TTFM_DURATION_METRIC),
        )

def sum_counter(snapshot: Any, name: str) -> int:
    total = 0
    for metric in _iter_metrics(snapshot):
        if _metric_name(metric) == name:
            total = min(U64_MAX, total + _sum_metric_values(metric, ("sum", "count", "value", "values")))
    return total

def sum_histogram_ms(snapshot: Any, name: str) -> int:
    total = 0
    for metric in _iter_metrics(snapshot):
        if _metric_name(metric) == name:
            total = min(U64_MAX, total + _sum_metric_values(metric, ("histogram", "sum", "duration_ms", "values")))
    return total

def _iter_metrics(snapshot: Any) -> list[Any]:
    if snapshot is None:
        return []
    if isinstance(snapshot, Mapping):
        if "metrics" in snapshot:
            return list(snapshot["metrics"] or [])
        scopes = snapshot.get("scope_metrics") or snapshot.get("scopes") or []
        metrics: list[Any] = []
        for scope in scopes:
            if isinstance(scope, Mapping):
                metrics.extend(scope.get("metrics") or [])
            else:
                metrics.extend(getattr(scope, "metrics", []) or [])
        return metrics
    metrics_attr = getattr(snapshot, "metrics", None)
    if metrics_attr is not None:
        value = metrics_attr() if callable(metrics_attr) else metrics_attr
        return list(value or [])
    scope_metrics = getattr(snapshot, "scope_metrics", None)
    scopes = scope_metrics() if callable(scope_metrics) else scope_metrics
    metrics = []
    for scope in scopes or []:
        scope_value = getattr(scope, "metrics", None)
        scope_metrics_value = scope_value() if callable(scope_value) else scope_value
        metrics.extend(scope_metrics_value or [])
    return metrics

def _metric_name(metric: Any) -> str | None:
    if isinstance(metric, Mapping):
        return metric.get("name")
    name = getattr(metric, "name", None)
    return name() if callable(name) else name

def _sum_metric_values(metric: Any, keys: tuple[str, ...]) -> int:
    if isinstance(metric, Mapping):
        for key in keys:
            if key in metric:
                return _coerce_metric_value(metric[key])
        data_points = metric.get("data_points") or metric.get("points")
    else:
        data_points = getattr(metric, "data_points", None) or getattr(metric, "points", None)
        if callable(data_points):
            data_points = data_points()
        for key in keys:
            if hasattr(metric, key):
                return _coerce_metric_value(getattr(metric, key))
    return sum(_coerce_metric_value(point) for point in data_points or [])

def _coerce_metric_value(value: Any) -> int:
    if callable(value):
        value = value()
    if isinstance(value, Mapping):
        if "value" in value:
            value = value["value"]
        elif "sum" in value:
            value = value["sum"]
        else:
            value = sum(_coerce_metric_value(item) for item in value.values())
    elif isinstance(value, (list, tuple)):
        value = sum(_coerce_metric_value(item) for item in value)
    else:
        point_value = getattr(value, "value", None)
        point_sum = getattr(value, "sum", None)
        if point_value is not None:
            value = point_value() if callable(point_value) else point_value
        elif point_sum is not None:
            value = point_sum() if callable(point_sum) else point_sum
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    if numeric <= 0 or not math.isfinite(numeric):
        return 0
    return min(U64_MAX, int(math.floor(numeric + 0.5)))

def _duration_from_ms_value(value: Any) -> int | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0 or not math.isfinite(numeric):
        return None
    return min(U64_MAX, int(math.floor(numeric + 0.5)))

from pycodex.otel.metrics.names import API_CALL_COUNT_METRIC, API_CALL_DURATION_METRIC, RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC, RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC, RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC, RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC, RESPONSES_API_INFERENCE_TIME_DURATION_METRIC, RESPONSES_API_OVERHEAD_DURATION_METRIC, SSE_EVENT_COUNT_METRIC, SSE_EVENT_DURATION_METRIC, TOOL_CALL_COUNT_METRIC, TOOL_CALL_DURATION_METRIC, TURN_TTFM_DURATION_METRIC, TURN_TTFT_DURATION_METRIC, WEBSOCKET_EVENT_COUNT_METRIC, WEBSOCKET_EVENT_DURATION_METRIC, WEBSOCKET_REQUEST_COUNT_METRIC, WEBSOCKET_REQUEST_DURATION_METRIC

__all__ = [name for name in globals() if not name.startswith("_")]
