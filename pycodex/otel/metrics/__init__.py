"""Rust-aligned owner for ``codex-otel::metrics``."""

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

_GLOBAL_METRICS: MetricsClient | None = None

_GLOBAL_STATSIG_METRICS_SETTINGS: StatsigMetricsSettings | None = None

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

from pycodex.otel.config import StatsigMetricsSettings
from pycodex.otel.metrics.client import MetricsClient
from pycodex.otel.metrics.config import MetricsConfig, MetricsExporter
from pycodex.otel.metrics.error import MetricsError
from pycodex.otel.metrics.names import *
from pycodex.otel.metrics.names import __all__ as _METRIC_NAME_EXPORTS
from pycodex.otel.metrics.process import record_process_start_once
from pycodex.otel.metrics.tags import ORIGINATOR_TAG, SessionMetricTagValues, bounded_originator_tag_value
from pycodex.otel.metrics.timer import Timer

__all__ = [
    "MetricsClient",
    "MetricsConfig",
    "MetricsError",
    "MetricsExporter",
    "ORIGINATOR_TAG",
    "SessionMetricTagValues",
    "bounded_originator_tag_value",
    "global_metrics",
    "record_process_start_once",
    *_METRIC_NAME_EXPORTS,
]
