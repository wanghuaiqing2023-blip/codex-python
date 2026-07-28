"""Rust-aligned owner for ``codex-otel::metrics.tags``."""

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

from pycodex.otel.metrics.validation import validate_tag_key, validate_tag_value
from pycodex.utils.string import sanitize_metric_tag_value

__all__ = [name for name in globals() if not name.startswith("_")]
