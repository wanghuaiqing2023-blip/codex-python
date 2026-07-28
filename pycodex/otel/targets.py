"""Rust-aligned owner for ``codex-otel::targets``."""

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

OTEL_TARGET_PREFIX = "codex_otel"

OTEL_LOG_ONLY_TARGET = "codex_otel.log_only"

OTEL_TRACE_SAFE_TARGET = "codex_otel.trace_safe"

def is_trace_safe_target(target: str) -> bool:
    return target.startswith(OTEL_TRACE_SAFE_TARGET)

def is_log_export_target(target: str) -> bool:
    return target.startswith(OTEL_TARGET_PREFIX) and not is_trace_safe_target(target)


__all__ = [name for name in globals() if not name.startswith("_")]
