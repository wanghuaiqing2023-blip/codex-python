"""Rust-aligned owner for ``codex-otel::metrics.process``."""

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

from pycodex.otel.metrics.client import MetricsClient
from pycodex.otel.metrics.names import PROCESS_START_METRIC
from pycodex.otel.metrics.tags import ORIGINATOR_TAG, bounded_originator_tag_value

__all__ = [name for name in globals() if not name.startswith("_")]
