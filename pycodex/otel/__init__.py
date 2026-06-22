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
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


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


def start_global_timer(_name: str, _tags: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> Timer:
    raise MetricsError("exporter disabled")


def global_statsig_metrics_settings() -> StatsigMetricsSettings | None:
    return None


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


OtelProvider = object

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
