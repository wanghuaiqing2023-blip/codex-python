"""Rust-aligned owner for ``codex-otel::metrics.client``."""

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
class MetricsCounterRecord:
    name: str
    inc: int
    tags: list[tuple[str, str]]

@dataclass
class MetricsDurationRecord:
    name: str
    duration_ms: int
    tags: list[tuple[str, str]]

@dataclass
class MetricsHistogramRecord:
    name: str
    value: int
    tags: list[tuple[str, str]]

class MetricsClient:
    def __init__(self, config: MetricsConfig | dict[str, str] | None = None, default_tags: dict[str, str] | None = None) -> None:
        self.config = config if isinstance(config, MetricsConfig) else None
        if isinstance(config, MetricsConfig):
            self.default_tags = dict(config.default_tags)
        elif isinstance(config, dict):
            self.default_tags = dict(config)
        else:
            self.default_tags = dict(default_tags or {})
        validate_tags(self.default_tags)
        self.counter_records: list[MetricsCounterRecord] = []
        self.histogram_records: list[MetricsHistogramRecord] = []
        self.duration_records: list[MetricsDurationRecord] = []
        self.shutdown_called = False
        self.last_export_error: str | None = None

    def counter(self, name: str, inc: int, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> None:
        validate_metric_name(name)
        if inc < 0:
            raise NegativeCounterIncrement(name, inc)
        self.counter_records.append(MetricsCounterRecord(name, inc, self._merged_tags(tags)))

    @classmethod
    def new(cls, config: MetricsConfig) -> "MetricsClient":
        return cls(config)

    def histogram(self, name: str, value: int, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> None:
        validate_metric_name(name)
        self.histogram_records.append(MetricsHistogramRecord(name, int(value), self._merged_tags(tags)))

    def record_duration(
        self,
        name: str,
        duration_ms: int | float,
        tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    ) -> None:
        validate_metric_name(name)
        merged_tags = self._merged_tags(tags)
        try:
            numeric = float(duration_ms)
        except (TypeError, ValueError):
            numeric = 0.0
        if numeric <= 0 or not math.isfinite(numeric):
            duration = 0
        else:
            duration = min((1 << 63) - 1, int(numeric))
        self.duration_records.append(MetricsDurationRecord(name, duration, merged_tags))

    def start_timer(self, name: str, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> Timer:
        validate_metric_name(name)
        validate_tags(dict(tags))
        return Timer(name, tags, self)

    def shutdown(self) -> None:
        self.shutdown_called = True
        self._export_otlp_http_json_metrics()
        return None

    def snapshot(self) -> dict[str, Any]:
        if self.config is None or not self.config.runtime_reader:
            raise RuntimeSnapshotUnavailable()
        metrics: list[dict[str, Any]] = []
        metrics.extend(
            {"name": record.name, "value": record.inc, "tags": list(record.tags), "kind": "counter"}
            for record in self.counter_records
        )
        metrics.extend(
            {"name": record.name, "value": record.value, "tags": list(record.tags), "kind": "histogram"}
            for record in self.histogram_records
        )
        metrics.extend(
            {"name": record.name, "duration_ms": record.duration_ms, "tags": list(record.tags), "kind": "duration"}
            for record in self.duration_records
        )
        return {"metrics": metrics}

    def _merged_tags(self, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> list[tuple[str, str]]:
        merged = dict(self.default_tags)
        for key, value in tags:
            validate_tag_key(key)
            validate_tag_value(value)
            merged[str(key)] = str(value)
        return sorted(merged.items())

    def _export_otlp_http_json_metrics(self) -> None:
        if self.config is None or self.config.exporter.kind != "otlp":
            return
        exporter = self.config.exporter.exporter
        if not isinstance(exporter, OtelExporter) or exporter.kind != "otlp_http":
            return
        if exporter.protocol != OtelHttpProtocol.JSON:
            return
        if not self.counter_records and not self.histogram_records and not self.duration_records:
            return
        try:
            body = json.dumps(
                {
                    "resourceMetrics": [
                        {
                            "resource": {
                                "attributes": [
                                    {"key": "service.name", "value": self.config.service_name},
                                    {"key": SERVICE_VERSION_ATTRIBUTE, "value": self.config.service_version},
                                    {"key": ENV_ATTRIBUTE, "value": self.config.environment},
                                ]
                            },
                            "scopeMetrics": [
                                {
                                    "metrics": [
                                        *[
                                            {
                                                "name": record.name,
                                                "kind": "counter",
                                                "value": record.inc,
                                                "attributes": _metric_record_attributes(record.tags),
                                            }
                                            for record in self.counter_records
                                        ],
                                        *[
                                            {
                                                "name": record.name,
                                                "kind": "histogram",
                                                "value": record.value,
                                                "attributes": _metric_record_attributes(record.tags),
                                            }
                                            for record in self.histogram_records
                                        ],
                                        *[
                                            {
                                                "name": record.name,
                                                "kind": "duration",
                                                "duration_ms": record.duration_ms,
                                                "attributes": _metric_record_attributes(record.tags),
                                            }
                                            for record in self.duration_records
                                        ],
                                    ]
                                }
                            ],
                        }
                    ]
                },
                separators=(",", ":"),
            ).encode("utf-8")
            _post_otlp_http_json(str(exporter.endpoint), exporter.headers, body, "OTEL_EXPORTER_OTLP_METRICS_TIMEOUT")
            self.last_export_error = None
        except Exception as exc:
            self.last_export_error = str(exc)

def _metric_record_attributes(tags: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"key": key, "value": value} for key, value in tags]

from pycodex.otel.config import OtelExporter, OtelHttpProtocol
from pycodex.otel.metrics.config import MetricsConfig
from pycodex.otel.metrics.error import NegativeCounterIncrement, RuntimeSnapshotUnavailable
from pycodex.otel.metrics.timer import Timer
from pycodex.otel.metrics.validation import validate_metric_name, validate_tag_key, validate_tag_value, validate_tags
from pycodex.otel.otlp import _post_otlp_http_json
from pycodex.otel.provider import ENV_ATTRIBUTE, SERVICE_VERSION_ATTRIBUTE

__all__ = [name for name in globals() if not name.startswith("_")]
