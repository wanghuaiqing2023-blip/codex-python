"""Rust-aligned owner for ``codex-otel::config``."""

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


__all__ = [name for name in globals() if not name.startswith("_")]
