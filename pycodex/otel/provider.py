"""Rust-aligned owner for ``codex-otel::provider``."""

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

class ResourceKind(str, Enum):
    LOGS = "logs"
    TRACES = "traces"

ENV_ATTRIBUTE = "env"

HOST_NAME_ATTRIBUTE = "host.name"

SERVICE_VERSION_ATTRIBUTE = "service.version"

def normalize_host_name(host_name: str | None) -> str | None:
    if host_name is None:
        return None
    stripped = host_name.strip()
    return stripped or None

def resource_attributes(
    settings: OtelSettings,
    host_name: str | None = None,
    kind: ResourceKind | str = ResourceKind.LOGS,
) -> list[tuple[str, str]]:
    attributes = [
        (SERVICE_VERSION_ATTRIBUTE, settings.service_version),
        (ENV_ATTRIBUTE, settings.environment),
    ]
    kind_value = kind.value if isinstance(kind, ResourceKind) else str(kind)
    if kind_value == ResourceKind.LOGS.value:
        normalized_host_name = normalize_host_name(host_name)
        if normalized_host_name is not None:
            attributes.append((HOST_NAME_ATTRIBUTE, normalized_host_name))
    return attributes

def _metadata_target(meta: Any) -> str:
    if isinstance(meta, str):
        return meta
    target = getattr(meta, "target", "")
    return target() if callable(target) else str(target)

def _metadata_is_span(meta: Any) -> bool:
    is_span = getattr(meta, "is_span", False)
    return bool(is_span() if callable(is_span) else is_span)

def codex_export_filter(meta: Any) -> bool:
    return log_export_filter(meta)

def log_export_filter(meta: Any) -> bool:
    return is_log_export_target(_metadata_target(meta))

def trace_export_filter(meta: Any) -> bool:
    return _metadata_is_span(meta) or is_trace_safe_target(_metadata_target(meta))

@dataclass
class OtelTraceSpan:
    provider: "OtelProvider"
    name: str
    attributes: dict[str, str] = field(default_factory=dict)
    parent: W3cTraceContext | None = None
    _token: contextvars.Token[Any] | None = field(default=None, init=False, repr=False)

    def __enter__(self) -> "OtelTraceSpan":
        self._token = _CURRENT_SPAN.set(self)
        if self not in self.provider.finished_spans:
            self.provider.finished_spans.append(self)
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        if self._token is not None:
            _CURRENT_SPAN.reset(self._token)
            self._token = None

    def w3c_trace_context(self) -> W3cTraceContext | None:
        parent = context_from_w3c_trace_context(self.parent) if self.parent is not None else None
        if parent is None:
            return None
        return W3cTraceContext(
            traceparent=parent.traceparent,
            tracestate=merge_tracestate_entries(parent.tracestate, configured_tracestate_entries()),
        )

@dataclass
class OtelLogger:
    exporter: OtelExporter | None
    records: list[dict[str, Any]] = field(default_factory=list)

    def emit(self, event_name: str, attributes: Mapping[str, Any] | None = None, body: str | None = None) -> None:
        record = {"event.name": str(event_name)}
        if attributes:
            record.update({str(key): value for key, value in attributes.items()})
        if body is not None:
            record["body"] = str(body)
        self.records.append(record)

@dataclass
class OtelProvider:
    logger: OtelLogger | None = None
    tracer_provider: object | None = None
    tracer: object | None = None
    metrics_client: MetricsClient | None = None
    environment: str = ""
    service_name: str = ""
    service_version: str = ""
    trace_exporter: OtelExporter | None = None
    span_attributes: dict[str, str] = field(default_factory=dict)
    finished_spans: list[OtelTraceSpan] = field(default_factory=list)
    last_trace_export_error: str | None = None
    last_log_export_error: str | None = None

    @classmethod
    def from_settings(cls, settings: OtelSettings) -> "OtelProvider | None":
        log_enabled = settings.exporter.kind != "none"
        trace_enabled = settings.trace_exporter.kind != "none"
        log_exporter = resolve_exporter(settings.exporter)
        metric_exporter = resolve_exporter(settings.metrics_exporter)
        trace_exporter = resolve_exporter(settings.trace_exporter)
        log_enabled = log_exporter.kind != "none"
        metrics_enabled = metric_exporter.kind != "none"

        if not log_enabled and not trace_enabled and not metrics_enabled:
            set_tracestate_entries({})
            return None

        if trace_enabled:
            validate_span_attributes(settings.span_attributes)
        validate_tracestate_entries(settings.tracestate)

        metrics = None
        if metrics_enabled:
            metrics_config = MetricsConfig.otlp(
                settings.environment,
                settings.service_name,
                settings.service_version,
                metric_exporter,
            )
            if settings.runtime_metrics:
                metrics_config = metrics_config.with_runtime_reader()
            metrics = MetricsClient.new(metrics_config)

        provider = cls(
            logger=OtelLogger(log_exporter) if log_enabled else None,
            tracer_provider=object() if trace_enabled else None,
            tracer=object() if trace_enabled else None,
            metrics_client=metrics,
            environment=settings.environment,
            service_name=settings.service_name,
            service_version=settings.service_version,
            trace_exporter=trace_exporter if trace_enabled else None,
            span_attributes=dict(settings.span_attributes),
        )
        set_tracestate_entries(settings.tracestate)
        if metrics is not None:
            install_global_metrics(metrics)
            if settings.metrics_exporter.kind == "statsig":
                install_global_statsig_metrics_settings(StatsigMetricsSettings(settings.environment))
        return provider

    def shutdown(self) -> None:
        self._export_otlp_http_json_traces()
        if self.metrics_client is not None:
            self.metrics_client.shutdown()
        self._export_otlp_http_json_logs()

    def metrics(self) -> MetricsClient | None:
        return self.metrics_client

    def trace_span(self, name: str, attributes: Mapping[str, str] | None = None) -> OtelTraceSpan:
        span_attributes = dict(self.span_attributes)
        if attributes:
            span_attributes.update({str(key): str(value) for key, value in attributes.items()})
        return OtelTraceSpan(self, str(name), span_attributes)

    def logger_layer(self) -> object | None:
        return object() if self.logger is not None else None

    def tracing_layer(self) -> object | None:
        return object() if self.tracer is not None else None

    def _export_otlp_http_json_traces(self) -> None:
        exporter = self.trace_exporter
        if exporter is None or exporter.kind != "otlp_http" or exporter.protocol != OtelHttpProtocol.JSON:
            return
        if not self.finished_spans:
            return
        try:
            body = json.dumps(
                {
                    "resourceSpans": [
                        {
                            "resource": {
                                "attributes": [
                                    {"key": "service.name", "value": self.service_name},
                                    {"key": SERVICE_VERSION_ATTRIBUTE, "value": self.service_version},
                                    {"key": ENV_ATTRIBUTE, "value": self.environment},
                                ]
                            },
                            "scopeSpans": [
                                {
                                    "spans": [
                                        {
                                            "name": span.name,
                                            "attributes": _metric_record_attributes(sorted(span.attributes.items())),
                                        }
                                        for span in self.finished_spans
                                    ]
                                }
                            ],
                        }
                    ]
                },
                separators=(",", ":"),
            ).encode("utf-8")
            _post_otlp_http_json(str(exporter.endpoint), exporter.headers, body, "OTEL_EXPORTER_OTLP_TRACES_TIMEOUT")
            self.last_trace_export_error = None
        except Exception as exc:
            self.last_trace_export_error = str(exc)

    def emit_log_event(self, event_name: str, attributes: Mapping[str, Any] | None = None, body: str | None = None) -> None:
        if self.logger is not None:
            self.logger.emit(event_name, attributes, body)

    def _export_otlp_http_json_logs(self) -> None:
        logger = self.logger
        if logger is None:
            return
        exporter = logger.exporter
        if exporter is None or exporter.kind != "otlp_http" or exporter.protocol != OtelHttpProtocol.JSON:
            return
        if not logger.records:
            return
        try:
            body = json.dumps(
                {
                    "resourceLogs": [
                        {
                            "resource": {
                                "attributes": [
                                    {"key": "service.name", "value": self.service_name},
                                    {"key": SERVICE_VERSION_ATTRIBUTE, "value": self.service_version},
                                    {"key": ENV_ATTRIBUTE, "value": self.environment},
                                ]
                            },
                            "scopeLogs": [
                                {
                                    "logRecords": [
                                        {
                                            "body": {"stringValue": str(record.get("body", record.get("event.name", "")))},
                                            "attributes": [
                                                {"key": str(key), "value": str(value)}
                                                for key, value in sorted(record.items())
                                                if key != "body"
                                            ],
                                        }
                                        for record in logger.records
                                    ]
                                }
                            ],
                        }
                    ]
                },
                separators=(",", ":"),
            ).encode("utf-8")
            _post_otlp_http_json(str(exporter.endpoint), exporter.headers, body, "OTEL_EXPORTER_OTLP_LOGS_TIMEOUT")
            self.last_log_export_error = None
        except Exception as exc:
            self.last_log_export_error = str(exc)

    @staticmethod
    def codex_export_filter(meta: Any) -> bool:
        return codex_export_filter(meta)

    @staticmethod
    def log_export_filter(meta: Any) -> bool:
        return log_export_filter(meta)

    @staticmethod
    def trace_export_filter(meta: Any) -> bool:
        return trace_export_filter(meta)

    def __del__(self) -> None:
        try:
            self.shutdown()
        except Exception:
            return

from pycodex.otel.config import OtelExporter, OtelHttpProtocol, OtelSettings, StatsigMetricsSettings, resolve_exporter, validate_span_attributes
from pycodex.otel.metrics import install_global_metrics, install_global_statsig_metrics_settings
from pycodex.otel.metrics.client import MetricsClient, _metric_record_attributes
from pycodex.otel.metrics.config import MetricsConfig
from pycodex.otel.otlp import _post_otlp_http_json
from pycodex.otel.targets import is_log_export_target, is_trace_safe_target
from pycodex.otel.trace_context import _CURRENT_SPAN, configured_tracestate_entries, context_from_w3c_trace_context, merge_tracestate_entries, set_tracestate_entries, validate_tracestate_entries
from pycodex.protocol import W3cTraceContext

__all__ = [name for name in globals() if not name.startswith("_")]
