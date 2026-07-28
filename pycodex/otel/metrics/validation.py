"""Rust-aligned owner for ``codex-otel::metrics.validation``."""

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

from pycodex.otel.metrics.error import EmptyMetricName, EmptyTagComponent, InvalidMetricName, InvalidTagComponent

__all__ = [name for name in globals() if not name.startswith("_")]
