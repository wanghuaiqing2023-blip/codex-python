"""Rust-aligned owner for ``codex-otel::metrics.config``."""

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

from pycodex.otel.config import OtelExporter
from pycodex.otel.metrics.validation import validate_tag_key, validate_tag_value

__all__ = [name for name in globals() if not name.startswith("_")]
