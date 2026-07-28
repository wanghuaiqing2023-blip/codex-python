"""Rust-aligned owner for ``codex-otel::otlp``."""

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

OTEL_EXPORTER_OTLP_TIMEOUT = "OTEL_EXPORTER_OTLP_TIMEOUT"

OTEL_EXPORTER_OTLP_TIMEOUT_DEFAULT_MS = 10_000

_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")

def build_header_map(headers: Mapping[str, str]) -> dict[str, str]:
    header_map: dict[str, str] = {}
    for key, value in headers.items():
        key_text = str(key)
        value_text = str(value)
        if _valid_http_header_name(key_text) and _valid_http_header_value(value_text):
            header_map[key_text.lower()] = value_text
    return header_map

def resolve_otlp_timeout(signal_var: str, environ: Mapping[str, str] | None = None) -> int:
    env = os.environ if environ is None else environ
    timeout = _read_timeout_env(signal_var, env)
    if timeout is not None:
        return timeout
    timeout = _read_timeout_env(OTEL_EXPORTER_OTLP_TIMEOUT, env)
    if timeout is not None:
        return timeout
    return OTEL_EXPORTER_OTLP_TIMEOUT_DEFAULT_MS

def _read_timeout_env(var: str, environ: Mapping[str, str]) -> int | None:
    value = environ.get(var)
    if value is None:
        return None
    try:
        parsed = int(str(value), 10)
    except ValueError:
        return None
    if parsed < 0:
        return None
    return parsed

def _valid_http_header_name(value: str) -> bool:
    return bool(_HEADER_NAME_RE.fullmatch(value))

def _valid_http_header_value(value: str) -> bool:
    return all(ch == "\t" or (32 <= ord(ch) != 127) for ch in value)

def _post_otlp_http_json(endpoint: str, headers: Mapping[str, str], body: bytes, timeout_var: str) -> None:
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid OTLP HTTP endpoint: {endpoint}")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = connection_cls(
        parsed.hostname,
        parsed.port,
        timeout=resolve_otlp_timeout(timeout_var) / 1000,
    )
    request_headers = dict(build_header_map(headers))
    request_headers["content-type"] = "application/json"
    request_headers["content-length"] = str(len(body))
    try:
        conn.request("POST", path, body=body, headers=request_headers)
        response = conn.getresponse()
        response.read()
        if response.status < 200 or response.status >= 300:
            raise OSError(f"OTLP HTTP export failed with status {response.status}")
    finally:
        conn.close()


__all__ = [name for name in globals() if not name.startswith("_")]
