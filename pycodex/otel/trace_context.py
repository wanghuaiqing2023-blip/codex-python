"""Rust-aligned owner for ``codex-otel::trace_context``."""

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

def validate_tracestate_entries(entries: dict[str, dict[str, str]]) -> None:
    for key, fields in entries.items():
        validate_tracestate_member(key, fields)

def validate_tracestate_member(member_key: str, fields: dict[str, str]) -> None:
    _encode_tracestate_member_fields(member_key, fields)

def context_from_w3c_trace_context(trace: W3cTraceContext) -> W3cTraceContext | None:
    if trace.traceparent is None:
        return None
    return trace if _valid_traceparent(trace.traceparent) and _valid_tracestate_header(trace.tracestate) else None

def traceparent_context_from_env() -> W3cTraceContext | None:
    traceparent = os.environ.get("TRACEPARENT")
    tracestate = os.environ.get("TRACESTATE")
    if not traceparent or not _valid_traceparent(traceparent) or not _valid_tracestate_header(tracestate):
        return None
    return W3cTraceContext(traceparent, tracestate)

def _valid_traceparent(value: str) -> bool:
    match = re.fullmatch(r"00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})", value)
    if not match:
        return False
    trace_id, span_id, _flags = match.groups()
    return trace_id != "0" * 32 and span_id != "0" * 16

def _valid_tracestate_header(value: str | None) -> bool:
    if value is None or value == "":
        return True
    try:
        _parse_tracestate_header(value)
    except ValueError:
        return False
    return True

def _parse_tracestate_header(value: str) -> list[tuple[str, str]]:
    members: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_member in value.split(","):
        member = raw_member.strip()
        if "=" not in member:
            raise ValueError("invalid configured tracestate")
        key, member_value = member.split("=", 1)
        if key in seen or not _is_tracestate_member_key(key) or not _is_header_safe_tracestate_member_value(member_value):
            raise ValueError("invalid configured tracestate")
        seen.add(key)
        members.append((key, member_value))
    return members

def _encode_tracestate_member_fields(member_key: str, fields: dict[str, str]) -> tuple[str, str]:
    if not _is_tracestate_member_key(member_key):
        raise ValueError("invalid configured tracestate")
    encoded: list[str] = []
    for field_key, value in sorted(fields.items()):
        if not _is_configured_tracestate_field_key(field_key):
            raise ValueError(f"invalid configured tracestate field key {member_key}.{field_key}")
        if not _is_configured_tracestate_field_value(value):
            raise ValueError(f"invalid configured tracestate value for {member_key}.{field_key}")
        encoded.append(f"{field_key}:{value}")
    member_value = ";".join(encoded)
    if not _is_header_safe_tracestate_member_value(member_value):
        raise ValueError(f"invalid configured tracestate value for {member_key}")
    return member_key, member_value

def _merge_tracestate_member_fields(existing: str | None, configured_fields: dict[str, str]) -> str:
    fields: list[str] = []
    seen: set[str] = set()
    if existing:
        for field in (part for part in existing.split(";") if part):
            if ":" in field:
                field_key, _ = field.split(":", 1)
                if field_key in configured_fields:
                    if field_key not in seen:
                        fields.append(f"{field_key}:{configured_fields[field_key]}")
                    seen.add(field_key)
                    continue
                seen.add(field_key)
            fields.append(field)
    for field_key, value in sorted(configured_fields.items()):
        if field_key not in seen:
            fields.append(f"{field_key}:{value}")
    return ";".join(fields)

def merge_tracestate_entries(tracestate: str | None, configured_entries: dict[str, dict[str, str]]) -> str | None:
    try:
        trace_state = _parse_tracestate_header(tracestate) if tracestate else []
    except ValueError:
        trace_state = []
    members = dict(trace_state)
    order = [key for key, _ in trace_state]
    for key, fields in sorted(configured_entries.items(), reverse=True):
        _encode_tracestate_member_fields(key, fields)
        members[key] = _merge_tracestate_member_fields(members.get(key), fields)
        if key in order:
            order.remove(key)
        order.insert(0, key)
    header = ",".join(f"{key}={members[key]}" for key in order if members.get(key) is not None)
    return header or None

def set_tracestate_entries(entries: dict[str, dict[str, str]]) -> None:
    validate_tracestate_entries(entries)
    global _TRACESTATE_ENTRIES
    _TRACESTATE_ENTRIES = {key: dict(value) for key, value in entries.items()}

def configured_tracestate_entries() -> dict[str, dict[str, str]]:
    return {key: dict(value) for key, value in _TRACESTATE_ENTRIES.items()}

def _is_tracestate_member_key(key: str) -> bool:
    if not key or len(key) > 256:
        return False
    if "@" in key:
        tenant, system = key.split("@", 1)
        return bool(tenant) and bool(system) and _is_tracestate_key_part(tenant, 241) and _is_tracestate_key_part(system, 14)
    return _is_tracestate_key_part(key, 256)

def _is_tracestate_key_part(part: str, max_len: int) -> bool:
    if not part or len(part) > max_len or not ("a" <= part[0] <= "z" or part[0].isdigit()):
        return False
    return all(ch.islower() or ch.isdigit() or ch in "_-*/" for ch in part)

def _is_configured_tracestate_field_key(field_key: str) -> bool:
    return bool(field_key) and all(33 <= ord(ch) <= 126 and ch not in ":;,=" for ch in field_key)

def _is_configured_tracestate_field_value(value: str) -> bool:
    return all(_is_tracestate_member_value_char(ch) and ch != ";" for ch in value)

def _is_header_safe_tracestate_member_value(value: str) -> bool:
    return value == "" or (all(_is_tracestate_member_value_char(ch) for ch in value) and value[-1] != " ")

def _is_tracestate_member_value_char(ch: str) -> bool:
    return 32 <= ord(ch) <= 126 and ch not in ",="

_TRACESTATE_ENTRIES: dict[str, dict[str, str]] = {}

_CURRENT_SPAN: contextvars.ContextVar["OtelTraceSpan | None"] = contextvars.ContextVar(
    "codex_otel_current_span",
    default=None,
)

def current_span_trace_id() -> str | None:
    trace = current_span_w3c_trace_context()
    if trace is None or trace.traceparent is None:
        return None
    parts = trace.traceparent.split("-")
    return parts[1] if len(parts) >= 4 and _valid_traceparent(trace.traceparent) else None

def current_span_w3c_trace_context() -> W3cTraceContext | None:
    span = _CURRENT_SPAN.get()
    return span_w3c_trace_context(span)

def span_w3c_trace_context(span: Any) -> W3cTraceContext | None:
    if isinstance(span, OtelTraceSpan):
        return span.w3c_trace_context()
    return None

def set_parent_from_context(span: Any, context: Any) -> None:
    if isinstance(span, OtelTraceSpan) and isinstance(context, W3cTraceContext):
        span.parent = context

def set_parent_from_w3c_trace_context(span: Any, trace: W3cTraceContext) -> bool:
    context = context_from_w3c_trace_context(trace)
    if context is None:
        return False
    set_parent_from_context(span, context)
    return True

from pycodex.otel.provider import OtelTraceSpan
from pycodex.protocol import W3cTraceContext

__all__ = [name for name in globals() if not name.startswith("_")]
