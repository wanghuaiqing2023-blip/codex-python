"""Source-verified public interface slice for ``codex-otel``.

Rust source:
- ``codex/codex-rs/otel/src/lib.rs``
- ``codex/codex-rs/otel/src/config.rs``
- ``codex/codex-rs/otel/src/trace_context.rs``
"""

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


class OtelHttpProtocol(str, Enum):
    BINARY = "binary"
    JSON = "json"


class TelemetryAuthMode(str, Enum):
    API_KEY = "api_key"
    CHATGPT = "chatgpt"


class ToolDecisionSource(str, Enum):
    AUTOMATED_REVIEWER = "automated_reviewer"
    CONFIG = "config"
    USER = "user"


class ResourceKind(str, Enum):
    LOGS = "logs"
    TRACES = "traces"


ENV_ATTRIBUTE = "env"
HOST_NAME_ATTRIBUTE = "host.name"
SERVICE_VERSION_ATTRIBUTE = "service.version"
OTEL_TARGET_PREFIX = "codex_otel"
OTEL_LOG_ONLY_TARGET = "codex_otel.log_only"
OTEL_TRACE_SAFE_TARGET = "codex_otel.trace_safe"


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


STATSIG_OTLP_HTTP_ENDPOINT = "https://ab.chatgpt.com/otlp/v1/metrics"
STATSIG_API_KEY_HEADER = "statsig-api-key"
STATSIG_API_KEY = "client-MkRuleRQBd6qakfnDYqJVR9JuXcY57Ljly3vi5JVUIO"
OTEL_EXPORTER_OTLP_TIMEOUT = "OTEL_EXPORTER_OTLP_TIMEOUT"
OTEL_EXPORTER_OTLP_TIMEOUT_DEFAULT_MS = 10_000


def resolve_exporter(exporter: OtelExporter) -> OtelExporter:
    if exporter.kind == "statsig":
        # Rust disables the built-in Statsig exporter in debug builds; the
        # Python port mirrors that test/dev posture for dependency-light runs.
        return OtelExporter.None_()
    return replace(
        exporter,
        headers=dict(exporter.headers),
        tls=replace(exporter.tls) if exporter.tls is not None else None,
    )


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


def is_trace_safe_target(target: str) -> bool:
    return target.startswith(OTEL_TRACE_SAFE_TARGET)


def is_log_export_target(target: str) -> bool:
    return target.startswith(OTEL_TARGET_PREFIX) and not is_trace_safe_target(target)


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


_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


def build_header_map(headers: Mapping[str, str]) -> dict[str, str]:
    header_map: dict[str, str] = {}
    for key, value in headers.items():
        key_text = str(key)
        value_text = str(value)
        if _valid_http_header_name(key_text) and _valid_http_header_value(value_text):
            header_map[key_text.lower()] = value_text
    return header_map


def resolve_otlp_timeout(signal_var: str, environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    timeout = _read_timeout_env(signal_var, env)
    if timeout is not None:
        return timeout
    timeout = _read_timeout_env(OTEL_EXPORTER_OTLP_TIMEOUT, env)
    if timeout is not None:
        return timeout
    return OTEL_EXPORTER_OTLP_TIMEOUT_DEFAULT_MS


def _read_timeout_env(var: str, environ: Mapping[str, str]) -> int | None:
    value = environ.get(var)
    if value is None:
        return None
    try:
        parsed = int(str(value), 10)
    except ValueError:
        return None
    if parsed < 0:
        return None
    return parsed


def _valid_http_header_name(value: str) -> bool:
    return bool(_HEADER_NAME_RE.fullmatch(value))


def _valid_http_header_value(value: str) -> bool:
    return all(ch == "\t" or (32 <= ord(ch) != 127) for ch in value)


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
    _encode_tracestate_member_fields(member_key, fields)


def sanitize_metric_tag_value(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]", "_", value)


@dataclass(frozen=True)
class W3cTraceContext:
    traceparent: str | None = None
    tracestate: str | None = None


def context_from_w3c_trace_context(trace: W3cTraceContext) -> W3cTraceContext | None:
    if trace.traceparent is None:
        return None
    return trace if _valid_traceparent(trace.traceparent) and _valid_tracestate_header(trace.tracestate) else None


def traceparent_context_from_env() -> W3cTraceContext | None:
    traceparent = os.environ.get("TRACEPARENT")
    tracestate = os.environ.get("TRACESTATE")
    if not traceparent or not _valid_traceparent(traceparent) or not _valid_tracestate_header(tracestate):
        return None
    return W3cTraceContext(traceparent, tracestate)


def _valid_traceparent(value: str) -> bool:
    match = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})", value)
    if not match:
        return False
    trace_id, span_id, _flags = match.groups()
    return trace_id != "0" * 32 and span_id != "0" * 16


def _valid_tracestate_header(value: str | None) -> bool:
    if value is None or value == "":
        return True
    try:
        _parse_tracestate_header(value)
    except ValueError:
        return False
    return True


def _parse_tracestate_header(value: str) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_member in value.split(","):
        member = raw_member.strip()
        if "=" not in member:
            raise ValueError("invalid configured tracestate")
        key, member_value = member.split("=", 1)
        if key in seen or not _is_tracestate_member_key(key) or not _is_header_safe_tracestate_member_value(member_value):
            raise ValueError("invalid configured tracestate")
        seen.add(key)
        members.append((key, member_value))
    return members


def _encode_tracestate_member_fields(member_key: str, fields: dict[str, str]) -> tuple[str, str]:
    if not _is_tracestate_member_key(member_key):
        raise ValueError("invalid configured tracestate")
    encoded: list[str] = []
    for field_key, value in sorted(fields.items()):
        if not _is_configured_tracestate_field_key(field_key):
            raise ValueError(f"invalid configured tracestate field key {member_key}.{field_key}")
        if not _is_configured_tracestate_field_value(value):
            raise ValueError(f"invalid configured tracestate value for {member_key}.{field_key}")
        encoded.append(f"{field_key}:{value}")
    member_value = ";".join(encoded)
    if not _is_header_safe_tracestate_member_value(member_value):
        raise ValueError(f"invalid configured tracestate value for {member_key}")
    return member_key, member_value


def _merge_tracestate_member_fields(existing: str | None, configured_fields: dict[str, str]) -> str:
    fields: list[str] = []
    seen: set[str] = set()
    if existing:
        for field in (part for part in existing.split(";") if part):
            if ":" in field:
                field_key, _ = field.split(":", 1)
                if field_key in configured_fields:
                    if field_key not in seen:
                        fields.append(f"{field_key}:{configured_fields[field_key]}")
                    seen.add(field_key)
                    continue
                seen.add(field_key)
            fields.append(field)
    for field_key, value in sorted(configured_fields.items()):
        if field_key not in seen:
            fields.append(f"{field_key}:{value}")
    return ";".join(fields)


def merge_tracestate_entries(tracestate: str | None, configured_entries: dict[str, dict[str, str]]) -> str | None:
    try:
        trace_state = _parse_tracestate_header(tracestate) if tracestate else []
    except ValueError:
        trace_state = []
    members = dict(trace_state)
    order = [key for key, _ in trace_state]
    for key, fields in sorted(configured_entries.items(), reverse=True):
        _encode_tracestate_member_fields(key, fields)
        members[key] = _merge_tracestate_member_fields(members.get(key), fields)
        if key in order:
            order.remove(key)
        order.insert(0, key)
    header = ",".join(f"{key}={members[key]}" for key in order if members.get(key) is not None)
    return header or None


def set_tracestate_entries(entries: dict[str, dict[str, str]]) -> None:
    validate_tracestate_entries(entries)
    global _TRACESTATE_ENTRIES
    _TRACESTATE_ENTRIES = {key: dict(value) for key, value in entries.items()}


def configured_tracestate_entries() -> dict[str, dict[str, str]]:
    return {key: dict(value) for key, value in _TRACESTATE_ENTRIES.items()}


def _is_tracestate_member_key(key: str) -> bool:
    if not key or len(key) > 256:
        return False
    if "@" in key:
        tenant, system = key.split("@", 1)
        return bool(tenant) and bool(system) and _is_tracestate_key_part(tenant, 241) and _is_tracestate_key_part(system, 14)
    return _is_tracestate_key_part(key, 256)


def _is_tracestate_key_part(part: str, max_len: int) -> bool:
    if not part or len(part) > max_len or not ("a" <= part[0] <= "z" or part[0].isdigit()):
        return False
    return all(ch.islower() or ch.isdigit() or ch in "_-*/" for ch in part)


def _is_configured_tracestate_field_key(field_key: str) -> bool:
    return bool(field_key) and all(33 <= ord(ch) <= 126 and ch not in ":;,=" for ch in field_key)


def _is_configured_tracestate_field_value(value: str) -> bool:
    return all(_is_tracestate_member_value_char(ch) and ch != ";" for ch in value)


def _is_header_safe_tracestate_member_value(value: str) -> bool:
    return value == "" or (all(_is_tracestate_member_value_char(ch) for ch in value) and value[-1] != " ")


def _is_tracestate_member_value_char(ch: str) -> bool:
    return 32 <= ord(ch) <= 126 and ch not in ",="


_TRACESTATE_ENTRIES: dict[str, dict[str, str]] = {}
_GLOBAL_METRICS: MetricsClient | None = None
_GLOBAL_STATSIG_METRICS_SETTINGS: StatsigMetricsSettings | None = None
_CURRENT_SPAN: contextvars.ContextVar["OtelTraceSpan | None"] = contextvars.ContextVar(
    "codex_otel_current_span",
    default=None,
)


def current_span_trace_id() -> str | None:
    trace = current_span_w3c_trace_context()
    if trace is None or trace.traceparent is None:
        return None
    parts = trace.traceparent.split("-")
    return parts[1] if len(parts) >= 4 and _valid_traceparent(trace.traceparent) else None


def current_span_w3c_trace_context() -> W3cTraceContext | None:
    span = _CURRENT_SPAN.get()
    return span_w3c_trace_context(span)


def span_w3c_trace_context(span: Any) -> W3cTraceContext | None:
    if isinstance(span, OtelTraceSpan):
        return span.w3c_trace_context()
    return None


def set_parent_from_context(span: Any, context: Any) -> None:
    if isinstance(span, OtelTraceSpan) and isinstance(context, W3cTraceContext):
        span.parent = context


def set_parent_from_w3c_trace_context(span: Any, trace: W3cTraceContext) -> bool:
    context = context_from_w3c_trace_context(trace)
    if context is None:
        return False
    set_parent_from_context(span, context)
    return True


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


class Timer:
    def __init__(
        self,
        name: str | None = None,
        tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
        client: Any | None = None,
    ) -> None:
        self.name = name
        self.tags = [(str(key), str(value)) for key, value in tags]
        self.client = client
        self.started_at = time.monotonic()

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_at) * 1000)

    def record(self, additional_tags: list[tuple[str, str]] | tuple[tuple[str, str], ...] = ()) -> None:
        if self.client is None or self.name is None:
            return
        tags = [(str(key), str(value)) for key, value in additional_tags]
        tags.extend(self.tags)
        self.client.record_duration(self.name, self.elapsed_ms(), tags)

    def __del__(self) -> None:
        try:
            self.record(())
        except Exception:
            return


class MetricsError(Exception):
    pass


class InvalidMetricName(MetricsError):
    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"invalid metric name: {name}")


class EmptyMetricName(MetricsError):
    def __init__(self) -> None:
        super().__init__("metric name must not be empty")


class InvalidTagComponent(MetricsError):
    def __init__(self, label: str, value: str) -> None:
        self.label = label
        self.value = value
        super().__init__(f"invalid {label}: {value}")


class EmptyTagComponent(MetricsError):
    def __init__(self, label: str) -> None:
        self.label = label
        super().__init__(f"{label} must not be empty")


class NegativeCounterIncrement(MetricsError):
    def __init__(self, name: str, inc: int) -> None:
        self.name = name
        self.inc = inc
        super().__init__(f"counter {name} increment must be non-negative: {inc}")


class RuntimeSnapshotUnavailable(MetricsError):
    def __init__(self) -> None:
        super().__init__("runtime metrics snapshot reader is not enabled")


@dataclass(frozen=True)
class MetricsExporter:
    kind: str
    exporter: Any = None

    @classmethod
    def Otlp(cls, exporter: OtelExporter) -> "MetricsExporter":
        return cls("otlp", exporter)

    @classmethod
    def InMemory(cls, exporter: Any = None) -> "MetricsExporter":
        return cls("in_memory", exporter)


@dataclass(frozen=True)
class MetricsConfig:
    environment: str
    service_name: str
    service_version: str
    exporter: MetricsExporter
    export_interval: Any | None = None
    runtime_reader: bool = False
    default_tags: dict[str, str] = field(default_factory=dict)

    @classmethod
    def otlp(
        cls,
        environment: str,
        service_name: str,
        service_version: str,
        exporter: OtelExporter,
    ) -> "MetricsConfig":
        return cls(
            environment=str(environment),
            service_name=str(service_name),
            service_version=str(service_version),
            exporter=MetricsExporter.Otlp(exporter),
        )

    @classmethod
    def in_memory(
        cls,
        environment: str,
        service_name: str,
        service_version: str,
        exporter: Any = None,
    ) -> "MetricsConfig":
        return cls(
            environment=str(environment),
            service_name=str(service_name),
            service_version=str(service_version),
            exporter=MetricsExporter.InMemory(exporter),
        )

    def with_export_interval(self, interval: Any) -> "MetricsConfig":
        return replace(self, export_interval=interval)

    def with_runtime_reader(self) -> "MetricsConfig":
        return replace(self, runtime_reader=True)

    def with_tag(self, key: str, value: str) -> "MetricsConfig":
        validate_tag_key(key)
        validate_tag_value(value)
        default_tags = dict(self.default_tags)
        default_tags[str(key)] = str(value)
        return replace(self, default_tags=default_tags)


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


def _post_otlp_http_json(endpoint: str, headers: Mapping[str, str], body: bytes, timeout_var: str) -> None:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid OTLP HTTP endpoint: {endpoint}")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(
        parsed.hostname,
        parsed.port,
        timeout=resolve_otlp_timeout(timeout_var) / 1000,
    )
    request_headers = dict(build_header_map(headers))
    request_headers["content-type"] = "application/json"
    request_headers["content-length"] = str(len(body))
    try:
        conn.request("POST", path, body=body, headers=request_headers)
        response = conn.getresponse()
        response.read()
        if response.status < 200 or response.status >= 300:
            raise OSError(f"OTLP HTTP export failed with status {response.status}")
    finally:
        conn.close()


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


def validate_metric_name(name: str) -> None:
    if not name:
        raise EmptyMetricName()
    if not all(ch.isascii() and (ch.isalnum() or ch in "._-") for ch in name):
        raise InvalidMetricName(name)


def validate_tag_key(key: str) -> None:
    _validate_tag_component(key, "tag key")


def validate_tag_value(value: str) -> None:
    _validate_tag_component(value, "tag value")


def validate_tags(tags: dict[str, str]) -> None:
    for key, value in tags.items():
        validate_tag_key(key)
        validate_tag_value(value)


def _validate_tag_component(value: str, label: str) -> None:
    if not value:
        raise EmptyTagComponent(label)
    if not all(ch.isascii() and (ch.isalnum() or ch in "._-/") for ch in value):
        raise InvalidTagComponent(label, value)


APP_VERSION_TAG = "app.version"
AUTH_MODE_TAG = "auth_mode"
MODEL_TAG = "model"
ORIGINATOR_TAG = "originator"
SERVICE_NAME_TAG = "service_name"
SESSION_SOURCE_TAG = "session_source"

KNOWN_ORIGINATOR_TAG_VALUES = (
    "codex_desktop",
    "codex-app-server",
    "codex_mcp_server",
    "codex_cli_rs",
    "codex-tui",
    "codex_vscode",
    "none",
    "codex_exec",
    "codex-cli",
    "codex_sdk_ts",
    "codex-app-server-sdk",
)


def bounded_originator_tag_value(originator: str) -> str:
    sanitized = sanitize_metric_tag_value(originator)
    return sanitized if sanitized in KNOWN_ORIGINATOR_TAG_VALUES else "other"


@dataclass(frozen=True)
class SessionMetricTagValues:
    auth_mode: str | None
    session_source: str
    originator: str
    service_name: str | None
    model: str
    app_version: str

    def into_tags(self) -> list[tuple[str, str]]:
        tags: list[tuple[str, str]] = []
        _push_optional_tag(tags, AUTH_MODE_TAG, self.auth_mode)
        _push_optional_tag(tags, SESSION_SOURCE_TAG, self.session_source)
        _push_optional_tag(tags, ORIGINATOR_TAG, self.originator)
        _push_optional_tag(tags, SERVICE_NAME_TAG, self.service_name)
        _push_optional_tag(tags, MODEL_TAG, self.model)
        _push_optional_tag(tags, APP_VERSION_TAG, self.app_version)
        return tags


def _push_optional_tag(tags: list[tuple[str, str]], key: str, value: str | None) -> None:
    if value is None:
        return
    validate_tag_key(key)
    validate_tag_value(value)
    tags.append((key, value))


_PROCESS_START_RECORDED = False
_PROCESS_START_LOCK = threading.Lock()


def record_process_start_once(metrics: MetricsClient, originator: str) -> bool:
    global _PROCESS_START_RECORDED
    with _PROCESS_START_LOCK:
        if _PROCESS_START_RECORDED:
            return False
        _PROCESS_START_RECORDED = True
    metrics.counter(PROCESS_START_METRIC, 1, [(ORIGINATOR_TAG, bounded_originator_tag_value(originator))])
    return True


def _reset_process_start_once_for_tests() -> None:
    global _PROCESS_START_RECORDED
    with _PROCESS_START_LOCK:
        _PROCESS_START_RECORDED = False


def install_global_metrics(metrics: MetricsClient) -> None:
    global _GLOBAL_METRICS
    _GLOBAL_METRICS = metrics


def global_metrics() -> MetricsClient | None:
    return _GLOBAL_METRICS


def install_global_statsig_metrics_settings(settings: StatsigMetricsSettings) -> None:
    global _GLOBAL_STATSIG_METRICS_SETTINGS
    _GLOBAL_STATSIG_METRICS_SETTINGS = settings


def _reset_global_otel_state_for_tests() -> None:
    global _GLOBAL_METRICS, _GLOBAL_STATSIG_METRICS_SETTINGS, _TRACESTATE_ENTRIES
    _GLOBAL_METRICS = None
    _GLOBAL_STATSIG_METRICS_SETTINGS = None
    _TRACESTATE_ENTRIES = {}


def start_global_timer(name: str, tags: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> Timer:
    metrics = global_metrics()
    if metrics is None:
        raise MetricsError("metrics exporter is disabled")
    return metrics.start_timer(name, tags)


def global_statsig_metrics_settings() -> StatsigMetricsSettings | None:
    return _GLOBAL_STATSIG_METRICS_SETTINGS


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

TOOL_CALL_COUNT_METRIC = "codex.tool.call"
TOOL_CALL_DURATION_METRIC = "codex.tool.call.duration_ms"
TOOL_CALL_UNIFIED_EXEC_METRIC = "codex.tool.unified_exec"
PROCESS_START_METRIC = "codex.process.start"
API_CALL_COUNT_METRIC = "codex.api_request"
API_CALL_DURATION_METRIC = "codex.api_request.duration_ms"
SSE_EVENT_COUNT_METRIC = "codex.sse_event"
SSE_EVENT_DURATION_METRIC = "codex.sse_event.duration_ms"
WEBSOCKET_REQUEST_COUNT_METRIC = "codex.websocket.request"
WEBSOCKET_REQUEST_DURATION_METRIC = "codex.websocket.request.duration_ms"
WEBSOCKET_EVENT_COUNT_METRIC = "codex.websocket.event"
WEBSOCKET_EVENT_DURATION_METRIC = "codex.websocket.event.duration_ms"
RESPONSES_API_OVERHEAD_DURATION_METRIC = "codex.responses_api_overhead.duration_ms"
RESPONSES_API_INFERENCE_TIME_DURATION_METRIC = "codex.responses_api_inference_time.duration_ms"
RESPONSES_API_ENGINE_IAPI_TTFT_DURATION_METRIC = "codex.responses_api_engine_iapi_ttft.duration_ms"
RESPONSES_API_ENGINE_SERVICE_TTFT_DURATION_METRIC = "codex.responses_api_engine_service_ttft.duration_ms"
RESPONSES_API_ENGINE_IAPI_TBT_DURATION_METRIC = "codex.responses_api_engine_iapi_tbt.duration_ms"
RESPONSES_API_ENGINE_SERVICE_TBT_DURATION_METRIC = "codex.responses_api_engine_service_tbt.duration_ms"
TURN_E2E_DURATION_METRIC = "codex.turn.e2e_duration_ms"
TURN_TTFT_DURATION_METRIC = "codex.turn.ttft.duration_ms"
TURN_TTFM_DURATION_METRIC = "codex.turn.ttfm.duration_ms"
TURN_NETWORK_PROXY_METRIC = "codex.turn.network_proxy"
TURN_MEMORY_METRIC = "codex.turn.memory"
TURN_TOOL_CALL_METRIC = "codex.turn.tool.call"
TURN_TOKEN_USAGE_METRIC = "codex.turn.token_usage"
GUARDIAN_REVIEW_COUNT_METRIC = "codex.guardian.review"
GUARDIAN_REVIEW_DURATION_METRIC = "codex.guardian.review.duration_ms"
GUARDIAN_REVIEW_TTFT_DURATION_METRIC = "codex.guardian.review.ttft.duration_ms"
GUARDIAN_REVIEW_TOKEN_USAGE_METRIC = "codex.guardian.review.token_usage"
GOAL_CREATED_METRIC = "codex.goal.created"
GOAL_RESUMED_METRIC = "codex.goal.resumed"
GOAL_COMPLETED_METRIC = "codex.goal.completed"
GOAL_BUDGET_LIMITED_METRIC = "codex.goal.budget_limited"
GOAL_USAGE_LIMITED_METRIC = "codex.goal.usage_limited"
GOAL_BLOCKED_METRIC = "codex.goal.blocked"
GOAL_TOKEN_COUNT_METRIC = "codex.goal.token_count"
GOAL_DURATION_SECONDS_METRIC = "codex.goal.duration_s"
PLUGIN_INSTALL_ELICITATION_SENT_METRIC = "codex.plugins.install_elicitation.sent"
PLUGIN_INSTALL_SUGGESTION_METRIC = "codex.plugins.install_suggestion"
CURATED_PLUGINS_STARTUP_SYNC_METRIC = "codex.plugins.startup_sync"
CURATED_PLUGINS_STARTUP_SYNC_FINAL_METRIC = "codex.plugins.startup_sync.final"
HOOK_RUN_METRIC = "codex.hooks.run"
HOOK_RUN_DURATION_METRIC = "codex.hooks.run.duration_ms"
STARTUP_PHASE_DURATION_METRIC = "codex.startup.phase.duration_ms"
STARTUP_PREWARM_DURATION_METRIC = "codex.startup_prewarm.duration_ms"
STARTUP_PREWARM_AGE_AT_FIRST_TURN_METRIC = "codex.startup_prewarm.age_at_first_turn_ms"
THREAD_STARTED_METRIC = "codex.thread.started"
THREAD_SKILLS_ENABLED_TOTAL_METRIC = "codex.thread.skills.enabled_total"
THREAD_SKILLS_KEPT_TOTAL_METRIC = "codex.thread.skills.kept_total"
THREAD_SKILLS_DESCRIPTION_TRUNCATED_CHARS_METRIC = "codex.thread.skills.description_truncated_chars"
THREAD_SKILLS_TRUNCATED_METRIC = "codex.thread.skills.truncated"


__all__ = [name for name in globals() if not name.startswith("_")]
