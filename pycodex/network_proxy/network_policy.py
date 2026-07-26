"""Rust-aligned projection of ``codex-network-proxy::network_policy``."""

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

AUDIT_TARGET = "codex_otel.network_proxy"


POLICY_DECISION_EVENT_NAME = "codex.network_proxy.policy_decision"


POLICY_SCOPE_DOMAIN = "domain"


POLICY_SCOPE_NON_DOMAIN = "non_domain"


POLICY_DECISION_ALLOW = "allow"


POLICY_DECISION_DENY = "deny"


POLICY_REASON_ALLOW = "allow"


DEFAULT_METHOD = "none"


DEFAULT_CLIENT_ADDRESS = "unknown"


class NetworkProtocol(str, Enum):
    HTTP = "http"
    HTTPS_CONNECT = "https_connect"
    SOCKS5_TCP = "socks5_tcp"
    SOCKS5_UDP = "socks5_udp"

    def as_policy_protocol(self) -> str:
        return self.value


class NetworkPolicyDecision(str, Enum):
    DENY = "deny"
    ASK = "ask"

    def as_str(self) -> str:
        return self.value


class NetworkDecisionSource(str, Enum):
    BASELINE_POLICY = "baseline_policy"
    MODE_GUARD = "mode_guard"
    PROXY_STATE = "proxy_state"
    DECIDER = "decider"

    def as_str(self) -> str:
        return self.value


@dataclass(frozen=True)
class NetworkPolicyRequestArgs:
    protocol: NetworkProtocol
    host: str
    port: int
    client_addr: str | None = None
    method: str | None = None
    command: str | None = None
    exec_policy_hint: str | None = None


@dataclass(frozen=True)
class NetworkPolicyRequest:
    protocol: NetworkProtocol
    host: str
    port: int
    client_addr: str | None = None
    method: str | None = None
    command: str | None = None
    exec_policy_hint: str | None = None

    @classmethod
    def new(cls, args: NetworkPolicyRequestArgs) -> "NetworkPolicyRequest":
        return cls(
            protocol=NetworkProtocol(args.protocol),
            host=args.host,
            port=args.port,
            client_addr=args.client_addr,
            method=args.method,
            command=args.command,
            exec_policy_hint=args.exec_policy_hint,
        )


@dataclass(frozen=True)
class NetworkDecision:
    kind: str
    reason: str | None = None
    source: NetworkDecisionSource | None = None
    decision: NetworkPolicyDecision | None = None

    @classmethod
    def allow(cls) -> "NetworkDecision":
        return cls("allow")

    @classmethod
    def deny(cls, reason: str) -> "NetworkDecision":
        return cls.deny_with_source(reason, NetworkDecisionSource.DECIDER)

    @classmethod
    def ask(cls, reason: str) -> "NetworkDecision":
        return cls.ask_with_source(reason, NetworkDecisionSource.DECIDER)

    @classmethod
    def deny_with_source(
        cls,
        reason: str,
        source: NetworkDecisionSource | str,
    ) -> "NetworkDecision":
        return cls(
            "deny",
            reason or REASON_POLICY_DENIED,
            NetworkDecisionSource(source),
            NetworkPolicyDecision.DENY,
        )

    @classmethod
    def ask_with_source(
        cls,
        reason: str,
        source: NetworkDecisionSource | str,
    ) -> "NetworkDecision":
        return cls(
            "deny",
            reason or REASON_POLICY_DENIED,
            NetworkDecisionSource(source),
            NetworkPolicyDecision.ASK,
        )

    @property
    def is_allow(self) -> bool:
        return self.kind == "allow"


@dataclass(frozen=True)
class BlockDecisionAuditEventArgs:
    source: NetworkDecisionSource
    reason: str
    protocol: NetworkProtocol
    server_address: str
    server_port: int
    method: str | None = None
    client_addr: str | None = None


async def ask_not_allowed_policy_decider(_request: object) -> str:
    return "ask:not_allowed"


async def evaluate_host_policy(
    state: NetworkProxyState,
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object | None,
    request: NetworkPolicyRequest,
) -> NetworkDecision:
    host_blocked = getattr(state, "host_blocked", None)
    if not callable(host_blocked):
        raise TypeError("state must provide host_blocked(host, port)")
    host_decision = host_blocked(request.host, request.port)
    if inspect.isawaitable(host_decision):
        host_decision = await host_decision
    if not isinstance(host_decision, HostBlockDecision):
        raise TypeError("host_blocked must return HostBlockDecision")

    if host_decision.allowed:
        decision = NetworkDecision.allow()
        policy_override = False
    elif host_decision.reason is HostBlockReason.NOT_ALLOWED:
        if decider is not None:
            decider_decision = await _call_network_policy_decider(decider, request)
            decision = map_decider_decision(decider_decision)
            policy_override = decision.is_allow
        else:
            decision = NetworkDecision.deny_with_source(
                HostBlockReason.NOT_ALLOWED.as_str(),
                NetworkDecisionSource.BASELINE_POLICY,
            )
            policy_override = False
    else:
        reason = host_decision.reason or HostBlockReason.NOT_ALLOWED
        decision = NetworkDecision.deny_with_source(
            reason.as_str(),
            NetworkDecisionSource.BASELINE_POLICY,
        )
        policy_override = False

    if decision.is_allow:
        policy_decision = POLICY_DECISION_ALLOW
        source = NetworkDecisionSource.DECIDER if policy_override else NetworkDecisionSource.BASELINE_POLICY
        reason = HostBlockReason.NOT_ALLOWED.as_str() if policy_override else POLICY_REASON_ALLOW
    else:
        if decision.decision is None or decision.source is None or decision.reason is None:
            raise ValueError("deny network decision must carry decision, source, and reason")
        policy_decision = decision.decision.as_str()
        source = decision.source
        reason = decision.reason

    _emit_policy_audit_event(
        state,
        scope=POLICY_SCOPE_DOMAIN,
        decision=policy_decision,
        source=source.as_str(),
        reason=reason,
        protocol=request.protocol,
        server_address=request.host,
        server_port=request.port,
        method=request.method,
        client_addr=request.client_addr,
        policy_override=policy_override,
    )
    return decision


def emit_block_decision_audit_event(
    state: NetworkProxyState,
    args: BlockDecisionAuditEventArgs,
) -> None:
    _emit_non_domain_policy_decision_audit_event(state, args, POLICY_DECISION_DENY)


def emit_allow_decision_audit_event(
    state: NetworkProxyState,
    args: BlockDecisionAuditEventArgs,
) -> None:
    _emit_non_domain_policy_decision_audit_event(state, args, POLICY_DECISION_ALLOW)


def map_decider_decision(decision: NetworkDecision) -> NetworkDecision:
    if not isinstance(decision, NetworkDecision):
        raise TypeError("decider must return NetworkDecision")
    if decision.is_allow:
        return decision
    if decision.reason is None or decision.decision is None:
        raise ValueError("deny network decision must carry reason and decision")
    return NetworkDecision(
        "deny",
        decision.reason,
        NetworkDecisionSource.DECIDER,
        decision.decision,
    )


async def _call_network_policy_decider(
    decider: Callable[[NetworkPolicyRequest], NetworkDecision | Awaitable[NetworkDecision]] | object,
    request: NetworkPolicyRequest,
) -> NetworkDecision:
    decide = getattr(decider, "decide", None)
    result = decide(request) if callable(decide) else decider(request)  # type: ignore[operator]
    if inspect.isawaitable(result):
        result = await result
    if not isinstance(result, NetworkDecision):
        raise TypeError("decider must return NetworkDecision")
    return result


def _emit_non_domain_policy_decision_audit_event(
    state: NetworkProxyState,
    args: BlockDecisionAuditEventArgs,
    decision: str,
) -> None:
    _emit_policy_audit_event(
        state,
        scope=POLICY_SCOPE_NON_DOMAIN,
        decision=decision,
        source=NetworkDecisionSource(args.source).as_str(),
        reason=args.reason,
        protocol=NetworkProtocol(args.protocol),
        server_address=args.server_address,
        server_port=args.server_port,
        method=args.method,
        client_addr=args.client_addr,
        policy_override=False,
    )


def _emit_policy_audit_event(
    state: NetworkProxyState,
    *,
    scope: str,
    decision: str,
    source: str,
    reason: str,
    protocol: NetworkProtocol,
    server_address: str,
    server_port: int,
    method: str | None,
    client_addr: str | None,
    policy_override: bool,
) -> None:
    event: dict[str, str] = {
        "target": AUDIT_TARGET,
        "event.name": POLICY_DECISION_EVENT_NAME,
        "event.timestamp": _audit_timestamp(),
        "network.policy.scope": scope,
        "network.policy.decision": decision,
        "network.policy.source": source,
        "network.policy.reason": reason,
        "network.transport.protocol": NetworkProtocol(protocol).as_policy_protocol(),
        "server.address": server_address,
        "server.port": str(server_port),
        "http.request.method": method or DEFAULT_METHOD,
        "client.address": client_addr or DEFAULT_CLIENT_ADDRESS,
        "network.policy.override": str(policy_override).lower(),
    }
    metadata = _audit_metadata_mapping(getattr(state, "audit_metadata", None))
    for source_key, event_key in (
        ("conversation_id", "conversation.id"),
        ("app_version", "app.version"),
        ("auth_mode", "auth_mode"),
        ("originator", "originator"),
        ("user_account_id", "user.account_id"),
        ("user_email", "user.email"),
        ("terminal_type", "terminal.type"),
        ("model", "model"),
        ("slug", "slug"),
    ):
        value = metadata.get(source_key)
        if value is not None:
            event[event_key] = str(value)

    record = getattr(state, "record_audit_event", None)
    if callable(record):
        record(event)
        return
    events = getattr(state, "audit_events", None)
    if events is not None:
        events.append(event)


def _audit_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _audit_metadata_mapping(metadata: object) -> Mapping[str, JsonValue]:
    if metadata is None:
        return {}
    if isinstance(metadata, NetworkProxyAuditMetadata):
        return metadata.value
    if isinstance(metadata, Mapping):
        return metadata
    return {
        key: value
        for key in (
            "conversation_id",
            "app_version",
            "auth_mode",
            "originator",
            "user_account_id",
            "user_email",
            "terminal_type",
            "model",
            "slug",
        )
        if (value := getattr(metadata, key, None)) is not None
    }

from .reasons import REASON_POLICY_DENIED
from .runtime import (
    HostBlockDecision,
    HostBlockReason,
    NetworkProxyAuditMetadata,
    NetworkProxyState,
)

__all__ = [
    "AUDIT_TARGET",
    "BlockDecisionAuditEventArgs",
    "DEFAULT_CLIENT_ADDRESS",
    "DEFAULT_METHOD",
    "NetworkDecision",
    "NetworkDecisionSource",
    "NetworkPolicyDecision",
    "NetworkPolicyRequest",
    "NetworkPolicyRequestArgs",
    "NetworkProtocol",
    "POLICY_DECISION_ALLOW",
    "POLICY_DECISION_DENY",
    "POLICY_DECISION_EVENT_NAME",
    "POLICY_REASON_ALLOW",
    "POLICY_SCOPE_DOMAIN",
    "POLICY_SCOPE_NON_DOMAIN",
    "ask_not_allowed_policy_decider",
    "emit_allow_decision_audit_event",
    "emit_block_decision_audit_event",
    "evaluate_host_policy",
    "map_decider_decision",
]
