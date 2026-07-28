"""Rust-aligned owner for ``codex-otel::metrics.error``."""

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


__all__ = [name for name in globals() if not name.startswith("_")]
