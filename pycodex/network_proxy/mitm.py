"""Rust-aligned projection of ``codex-network-proxy::mitm``."""

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
class MitmPolicyContext:
    target_host: str
    target_port: int
    mode: NetworkMode
    app_state: "NetworkProxyState"


@dataclass(frozen=True)
class MitmPolicyDecision:
    allowed: bool
    response: "NetworkProxyResponse | None" = None
    hook_actions: MitmHookActions | None = None

    @classmethod
    def allow(cls, hook_actions: MitmHookActions | None = None) -> "MitmPolicyDecision":
        return cls(True, hook_actions=hook_actions)

    @classmethod
    def block(cls, response: "NetworkProxyResponse") -> "MitmPolicyDecision":
        return cls(False, response=response)


async def mitm_blocking_response(request: Any, policy: MitmPolicyContext) -> NetworkProxyResponse | None:
    decision = await evaluate_mitm_policy(request, policy)
    return None if decision.allowed else decision.response


async def evaluate_mitm_policy(request: Any, policy: MitmPolicyContext) -> MitmPolicyDecision:
    method = _request_method(request).upper()
    if method == "CONNECT":
        return MitmPolicyDecision.block(text_response(405, "CONNECT not supported inside MITM"))

    log_path = _request_log_path(request)
    client = _request_client(request)
    request_host = _extract_request_host(request)
    if request_host is not None:
        normalized = normalize_host(request_host)
        if normalized and normalized != policy.target_host:
            return MitmPolicyDecision.block(text_response(400, "host mismatch"))

    host_decision = await policy.app_state.host_blocked(policy.target_host, policy.target_port)
    if host_decision.reason is HostBlockReason.NOT_ALLOWED_LOCAL:
        reason = HostBlockReason.NOT_ALLOWED_LOCAL.as_str()
        await policy.app_state.record_blocked(
            BlockedRequest.new(
                BlockedRequestArgs(
                    host=policy.target_host,
                    reason=reason,
                    client=client,
                    method=method,
                    mode=policy.mode,
                    protocol="https",
                    decision=None,
                    source=None,
                    port=policy.target_port,
                )
            )
        )
        return MitmPolicyDecision.block(blocked_text_response(reason))

    hook_evaluation = await policy.app_state.evaluate_mitm_hook_request(policy.target_host, request)
    hook_actions = None
    if hook_evaluation.kind is HookEvaluation.MATCHED:
        hook_actions = hook_evaluation.actions
    elif hook_evaluation.kind is HookEvaluation.HOOKED_HOST_NO_MATCH:
        await policy.app_state.record_blocked(
            BlockedRequest.new(
                BlockedRequestArgs(
                    host=policy.target_host,
                    reason=REASON_MITM_HOOK_DENIED,
                    client=client,
                    method=method,
                    mode=policy.mode,
                    protocol="https",
                    decision=None,
                    source=None,
                    port=policy.target_port,
                )
            )
        )
        return MitmPolicyDecision.block(blocked_text_response(REASON_MITM_HOOK_DENIED))

    if not policy.mode.allows_method(method):
        await policy.app_state.record_blocked(
            BlockedRequest.new(
                BlockedRequestArgs(
                    host=policy.target_host,
                    reason=REASON_METHOD_NOT_ALLOWED,
                    client=client,
                    method=method,
                    mode=policy.mode,
                    protocol="https",
                    decision=None,
                    source=None,
                    port=policy.target_port,
                )
            )
        )
        return MitmPolicyDecision.block(blocked_text_response(REASON_METHOD_NOT_ALLOWED))

    return MitmPolicyDecision.allow(hook_actions)


def apply_mitm_hook_actions(headers: MutableMapping[str, Any], actions: MitmHookActions | None) -> MutableMapping[str, Any]:
    if actions is None:
        return headers
    for header_name in actions.strip_request_headers:
        _remove_header_case_insensitive(headers, header_name)
    for injected_header in actions.inject_request_headers:
        _remove_header_case_insensitive(headers, injected_header.name)
        headers[injected_header.name] = injected_header.value
    return headers


def _request_method(request: Any) -> str:
    if isinstance(request, Mapping):
        return str(request.get("method", ""))
    return str(getattr(request, "method", ""))


def _request_uri(request: Any) -> str:
    if isinstance(request, Mapping):
        return str(request.get("uri", request.get("url", "")))
    return str(getattr(request, "uri", getattr(request, "url", "")))


def _request_headers(request: Any) -> Mapping[str, Any]:
    if isinstance(request, Mapping):
        headers = request.get("headers", {})
    else:
        headers = getattr(request, "headers", {})
    return headers if isinstance(headers, Mapping) else {}


def _request_client(request: Any) -> str | None:
    if isinstance(request, Mapping):
        client = request.get("client")
    else:
        client = getattr(request, "client", None)
    return str(client) if client is not None else None


def extract_request_host(request: Any) -> str | None:
    headers = _request_headers(request)
    for name, value in headers.items():
        if str(name).lower() == "host":
            return str(value)
    parsed = urlparse(_request_uri(request))
    if parsed.netloc:
        return parsed.netloc
    if parsed.scheme and parsed.path:
        return parsed.path.split("/", 1)[0] or None
    return None


def authority_header_value(host: str, port: int) -> str:
    if ":" in host:
        return f"[{host}]" if int(port) == 443 else f"[{host}]:{int(port)}"
    return host if int(port) == 443 else f"{host}:{int(port)}"


def build_https_uri(authority: str, path: str) -> str:
    target = f"https://{authority}{path}"
    parsed = urlparse(target)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"invalid https URI: {target}")
    return target


def path_and_query(uri: str) -> str:
    parsed = urlparse(uri)
    if parsed.path:
        return f"{parsed.path}?{parsed.query}" if parsed.query else parsed.path
    if parsed.query:
        return f"?{parsed.query}"
    return "/"


def path_for_log(uri: str) -> str:
    return urlparse(uri).path or "/"


def _request_log_path(request: Any) -> str:
    return path_for_log(_request_uri(request))

from .config import NetworkMode
from .http_proxy import (
    _extract_request_host,
    _remove_header_case_insensitive,
)
from .mitm_hook import (
    HookEvaluation,
    MitmHookActions,
)
from .policy import normalize_host
from .reasons import (
    REASON_METHOD_NOT_ALLOWED,
    REASON_MITM_HOOK_DENIED,
)
from .responses import (
    NetworkProxyResponse,
    blocked_text_response,
    text_response,
)
from .runtime import (
    BlockedRequest,
    BlockedRequestArgs,
    HostBlockReason,
)

__all__ = [
    "MitmPolicyContext",
    "MitmPolicyDecision",
    "apply_mitm_hook_actions",
    "authority_header_value",
    "build_https_uri",
    "evaluate_mitm_policy",
    "extract_request_host",
    "mitm_blocking_response",
    "path_and_query",
    "path_for_log",
]
