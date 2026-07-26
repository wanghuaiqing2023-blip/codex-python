"""Rust-aligned projection of ``codex-network-proxy::responses``."""

from __future__ import annotations

import asyncio
import inspect
import ipaddress
import fnmatch
import json
import os
import re
import socket
import stat
import sys
import time
from datetime import UTC, datetime
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from urllib.parse import parse_qsl, urlparse
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any, Mapping, Sequence

JsonValue = Any

@dataclass(frozen=True)
class PolicyDecisionDetails:
    decision: NetworkPolicyDecision
    reason: str
    source: NetworkDecisionSource
    protocol: NetworkProtocol
    host: str
    port: int


@dataclass(frozen=True)
class NetworkProxyResponse:
    status: int
    body: str
    headers: Mapping[str, str] = field(default_factory=dict)


def text_response(status: int, body: str) -> NetworkProxyResponse:
    return NetworkProxyResponse(
        status=int(status),
        body=str(body),
        headers={"content-type": "text/plain"},
    )


def json_response(value: object) -> NetworkProxyResponse:
    try:
        body = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        body = "{}"
    return NetworkProxyResponse(
        status=200,
        body=body,
        headers={"content-type": "application/json"},
    )


def blocked_header_value(reason: str) -> str:
    if reason in {REASON_NOT_ALLOWED, REASON_NOT_ALLOWED_LOCAL}:
        return "blocked-by-allowlist"
    if reason == REASON_DENIED:
        return "blocked-by-denylist"
    if reason == REASON_METHOD_NOT_ALLOWED:
        return "blocked-by-method-policy"
    if reason == REASON_MITM_HOOK_DENIED:
        return "blocked-by-mitm-hook"
    if reason == REASON_MITM_REQUIRED:
        return "blocked-by-mitm-required"
    return "blocked-by-policy"


def blocked_message(reason: str) -> str:
    if reason == REASON_NOT_ALLOWED:
        return "Domain not in allowlist."
    if reason == REASON_NOT_ALLOWED_LOCAL:
        return "Sandbox policy blocks local/private network addresses."
    if reason == REASON_DENIED:
        return "Domain denied by the sandbox policy."
    if reason == REASON_METHOD_NOT_ALLOWED:
        return "Method not allowed in limited mode."
    if reason == REASON_MITM_HOOK_DENIED:
        return "HTTPS request denied by MITM hook policy."
    if reason == REASON_MITM_REQUIRED:
        return "MITM required for limited HTTPS."
    if reason == REASON_PROXY_DISABLED:
        return "network proxy is disabled"
    return "Request blocked by network policy."


def blocked_text_response(reason: str) -> NetworkProxyResponse:
    return NetworkProxyResponse(
        status=403,
        body=blocked_message(reason),
        headers={
            "content-type": "text/plain",
            "x-proxy-error": blocked_header_value(reason),
        },
    )


def blocked_message_with_policy(reason: str, details: PolicyDecisionDetails) -> str:
    if not isinstance(details, PolicyDecisionDetails):
        raise TypeError("details must be PolicyDecisionDetails")
    return blocked_message(reason)


def blocked_text_response_with_policy(
    reason: str,
    details: PolicyDecisionDetails,
) -> NetworkProxyResponse:
    return NetworkProxyResponse(
        status=403,
        body=blocked_message_with_policy(reason, details),
        headers={
            "content-type": "text/plain",
            "x-proxy-error": blocked_header_value(reason),
        },
    )

from .network_policy import (
    NetworkDecisionSource,
    NetworkPolicyDecision,
    NetworkProtocol,
)
from .reasons import (
    REASON_DENIED,
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_HOOK_DENIED,
    REASON_MITM_REQUIRED,
    REASON_NOT_ALLOWED,
    REASON_NOT_ALLOWED_LOCAL,
    REASON_PROXY_DISABLED,
)

__all__ = [
    "NetworkProxyResponse",
    "PolicyDecisionDetails",
    "blocked_header_value",
    "blocked_message",
    "blocked_message_with_policy",
    "blocked_text_response",
    "blocked_text_response_with_policy",
    "json_response",
    "text_response",
]
