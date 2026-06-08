"""OpenTelemetry initialization mapping helpers.

Ported from the pure configuration mapping portions of
``codex/codex-rs/core/src/otel_init.rs``. This module builds stdlib data
structures that mirror the settings passed to the Rust OTEL provider; it does
not initialize an OpenTelemetry SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.features import Feature, Features


class OtelHttpProtocol(str, Enum):
    BINARY = "binary"
    JSON = "json"


@dataclass(frozen=True)
class OtelTlsConfig:
    ca_certificate: Path | None = None
    client_certificate: Path | None = None
    client_private_key: Path | None = None

    def __post_init__(self) -> None:
        for field_name in ("ca_certificate", "client_certificate", "client_private_key"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, Path):
                object.__setattr__(self, field_name, Path(value))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> "OtelTlsConfig | None":
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise TypeError("tls config must be a mapping or None")
        return cls(
            ca_certificate=_optional_path(value, "ca_certificate"),
            client_certificate=_optional_path(value, "client_certificate"),
            client_private_key=_optional_path(value, "client_private_key"),
        )


@dataclass(frozen=True)
class OtelExporterKind:
    kind: str
    endpoint: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    protocol: OtelHttpProtocol | None = None
    tls: OtelTlsConfig | None = None

    def __post_init__(self) -> None:
        if self.kind not in {"none", "statsig", "otlp-http", "otlp-grpc"}:
            raise ValueError(f"unknown otel exporter kind: {self.kind}")
        if self.endpoint is not None and not isinstance(self.endpoint, str):
            raise TypeError("endpoint must be a string or None")
        object.__setattr__(self, "headers", _string_mapping(self.headers, "headers"))
        if self.protocol is not None and not isinstance(self.protocol, OtelHttpProtocol):
            object.__setattr__(self, "protocol", OtelHttpProtocol(self.protocol))
        if self.tls is not None and not isinstance(self.tls, OtelTlsConfig):
            if isinstance(self.tls, Mapping):
                object.__setattr__(self, "tls", OtelTlsConfig.from_mapping(self.tls))
            else:
                raise TypeError("tls must be OtelTlsConfig, mapping, or None")

    @classmethod
    def none(cls) -> "OtelExporterKind":
        return cls("none")

    @classmethod
    def statsig(cls) -> "OtelExporterKind":
        return cls("statsig")

    @classmethod
    def otlp_http(
        cls,
        endpoint: str,
        *,
        headers: Mapping[str, str] | None = None,
        protocol: OtelHttpProtocol | str = OtelHttpProtocol.JSON,
        tls: OtelTlsConfig | Mapping[str, Any] | None = None,
    ) -> "OtelExporterKind":
        return cls("otlp-http", endpoint=endpoint, headers=dict(headers or {}), protocol=OtelHttpProtocol(protocol), tls=tls)

    @classmethod
    def otlp_grpc(
        cls,
        endpoint: str,
        *,
        headers: Mapping[str, str] | None = None,
        tls: OtelTlsConfig | Mapping[str, Any] | None = None,
    ) -> "OtelExporterKind":
        return cls("otlp-grpc", endpoint=endpoint, headers=dict(headers or {}), tls=tls)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | str | None) -> "OtelExporterKind":
        if value is None:
            return cls.none()
        if isinstance(value, str):
            normalized = value.replace("_", "-")
            if normalized == "none":
                return cls.none()
            if normalized == "statsig":
                return cls.statsig()
            raise ValueError(f"unknown otel exporter kind: {value}")
        if not isinstance(value, Mapping):
            raise TypeError("otel exporter kind must be a string, mapping, or None")
        kind = _required_str(value, "kind").replace("_", "-")
        if kind == "none":
            return cls.none()
        if kind == "statsig":
            return cls.statsig()
        if kind == "otlp-http":
            return cls.otlp_http(
                _required_str(value, "endpoint"),
                headers=_optional_string_mapping(value, "headers"),
                protocol=OtelHttpProtocol(_required_str(value, "protocol").replace("_", "-")),
                tls=OtelTlsConfig.from_mapping(value.get("tls")) if value.get("tls") is not None else None,
            )
        if kind == "otlp-grpc":
            return cls.otlp_grpc(
                _required_str(value, "endpoint"),
                headers=_optional_string_mapping(value, "headers"),
                tls=OtelTlsConfig.from_mapping(value.get("tls")) if value.get("tls") is not None else None,
            )
        raise ValueError(f"unknown otel exporter kind: {kind}")


@dataclass(frozen=True)
class OtelConfig:
    log_user_prompt: bool = False
    environment: str = "dev"
    exporter: OtelExporterKind = field(default_factory=OtelExporterKind.none)
    trace_exporter: OtelExporterKind = field(default_factory=OtelExporterKind.none)
    metrics_exporter: OtelExporterKind = field(default_factory=OtelExporterKind.statsig)
    span_attributes: dict[str, str] = field(default_factory=dict)
    tracestate: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.log_user_prompt, bool):
            raise TypeError("log_user_prompt must be a bool")
        if not isinstance(self.environment, str):
            raise TypeError("environment must be a string")
        for field_name in ("exporter", "trace_exporter", "metrics_exporter"):
            value = getattr(self, field_name)
            if not isinstance(value, OtelExporterKind):
                object.__setattr__(self, field_name, OtelExporterKind.from_mapping(value))
        object.__setattr__(self, "span_attributes", _string_mapping(self.span_attributes, "span_attributes"))
        object.__setattr__(self, "tracestate", _nested_string_mapping(self.tracestate, "tracestate"))


@dataclass(frozen=True)
class OtelSettings:
    service_name: str
    service_version: str
    codex_home: Path
    environment: str
    exporter: OtelExporterKind
    trace_exporter: OtelExporterKind
    metrics_exporter: OtelExporterKind
    runtime_metrics: bool
    span_attributes: dict[str, str]
    tracestate: dict[str, dict[str, str]]


@dataclass(frozen=True)
class OtelProvider:
    settings: OtelSettings

    def metrics(self) -> "OtelProvider | None":
        return None if self.settings.metrics_exporter.kind == "none" else self


def build_provider(
    config: Any,
    service_version: str,
    service_name_override: str | None,
    default_analytics_enabled: bool,
    *,
    originator: str = "codex",
) -> OtelProvider | None:
    if not isinstance(service_version, str):
        raise TypeError("service_version must be a string")
    if service_name_override is not None and not isinstance(service_name_override, str):
        raise TypeError("service_name_override must be a string or None")
    if not isinstance(default_analytics_enabled, bool):
        raise TypeError("default_analytics_enabled must be a bool")
    if not isinstance(originator, str):
        raise TypeError("originator must be a string")

    otel = _otel_config(config)
    exporter = _to_otel_exporter(otel.exporter)
    trace_exporter = _to_otel_exporter(otel.trace_exporter)
    analytics_enabled = _analytics_enabled(config, default_analytics_enabled)
    metrics_exporter = _to_otel_exporter(otel.metrics_exporter) if analytics_enabled else OtelExporterKind.none()
    if exporter.kind == "none" and trace_exporter.kind == "none" and metrics_exporter.kind == "none":
        return None

    settings = OtelSettings(
        service_name=service_name_override or originator,
        service_version=service_version,
        codex_home=_codex_home(config),
        environment=otel.environment,
        exporter=exporter,
        trace_exporter=trace_exporter,
        metrics_exporter=metrics_exporter,
        runtime_metrics=_runtime_metrics_enabled(config),
        span_attributes=dict(otel.span_attributes),
        tracestate={key: dict(value) for key, value in otel.tracestate.items()},
    )
    return OtelProvider(settings)


def codex_export_filter(meta: object) -> bool:
    target = meta
    if not isinstance(target, str):
        attr = getattr(meta, "target", None)
        target = attr() if callable(attr) else attr
    return isinstance(target, str) and target.startswith("codex_otel")


def record_process_start(otel: OtelProvider | None, originator: str) -> bool:
    if not isinstance(originator, str):
        raise TypeError("originator must be a string")
    return otel is not None and otel.metrics() is not None


def install_sqlite_telemetry(otel: OtelProvider | None, originator: str) -> bool:
    if not isinstance(originator, str):
        raise TypeError("originator must be a string")
    return otel is not None and otel.metrics() is not None


def _to_otel_exporter(kind: OtelExporterKind) -> OtelExporterKind:
    if not isinstance(kind, OtelExporterKind):
        raise TypeError("otel exporter must be OtelExporterKind")
    return kind


def _otel_config(config: Any) -> OtelConfig:
    value = getattr(config, "otel", None)
    if value is None and isinstance(config, Mapping):
        value = config.get("otel")
    if value is None:
        return OtelConfig()
    if isinstance(value, OtelConfig):
        return value
    if isinstance(value, Mapping):
        return OtelConfig(
            log_user_prompt=value.get("log_user_prompt", False),
            environment=value.get("environment", "dev"),
            exporter=OtelExporterKind.from_mapping(value.get("exporter")),
            trace_exporter=OtelExporterKind.from_mapping(value.get("trace_exporter")),
            metrics_exporter=OtelExporterKind.from_mapping(value.get("metrics_exporter", "statsig")),
            span_attributes=_optional_string_mapping(value, "span_attributes"),
            tracestate=_optional_nested_string_mapping(value, "tracestate"),
        )
    raise TypeError("config.otel must be OtelConfig, mapping, or None")


def _analytics_enabled(config: Any, default: bool) -> bool:
    value = getattr(config, "analytics_enabled", None)
    if value is None and isinstance(config, Mapping):
        value = config.get("analytics_enabled")
    if value is None:
        return default
    if not isinstance(value, bool):
        raise TypeError("analytics_enabled must be a bool or None")
    return value


def _runtime_metrics_enabled(config: Any) -> bool:
    features = getattr(config, "features", None)
    if features is None and isinstance(config, Mapping):
        features = config.get("features")
    return isinstance(features, Features) and features.enabled(Feature.RUNTIME_METRICS)


def _codex_home(config: Any) -> Path:
    value = getattr(config, "codex_home", None)
    if value is None and isinstance(config, Mapping):
        value = config.get("codex_home")
    return Path(value or ".")


def _optional_path(value: Mapping[str, Any], key: str) -> Path | None:
    item = value.get(key)
    if item is None:
        return None
    if not isinstance(item, (str, Path)):
        raise TypeError(f"{key} must be a path string or None")
    return Path(item)


def _required_str(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TypeError(f"{key} must be a string")
    return item


def _optional_string_mapping(value: Mapping[str, Any], key: str) -> dict[str, str]:
    item = value.get(key, {})
    return _string_mapping(item, key)


def _optional_nested_string_mapping(value: Mapping[str, Any], key: str) -> dict[str, dict[str, str]]:
    item = value.get(key, {})
    return _nested_string_mapping(item, key)


def _string_mapping(value: Mapping[str, str] | None, label: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in value.items()):
        raise TypeError(f"{label} must contain string keys and values")
    return dict(value)


def _nested_string_mapping(value: Mapping[str, Mapping[str, str]] | None, label: str) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a mapping")
    return {key: _string_mapping(inner, f"{label}.{key}") for key, inner in value.items() if isinstance(key, str)}


__all__ = [
    "OtelConfig",
    "OtelExporterKind",
    "OtelHttpProtocol",
    "OtelProvider",
    "OtelSettings",
    "OtelTlsConfig",
    "build_provider",
    "codex_export_filter",
    "install_sqlite_telemetry",
    "record_process_start",
]
