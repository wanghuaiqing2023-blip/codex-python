"""Network policy decision helpers ported from Codex core."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.protocol import (
    NetworkApprovalContext,
    NetworkApprovalProtocol,
    NetworkPolicyAmendment,
    NetworkPolicyDecision,
    NetworkPolicyDecisionPayload,
    NetworkPolicyRuleAction,
)

from pycodex.execpolicy import Decision

JsonValue = Any


class ExecPolicyNetworkRuleProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5_TCP = "socks5_tcp"
    SOCKS5_UDP = "socks5_udp"


@dataclass(frozen=True)
class BlockedRequest:
    host: str
    reason: str
    client: str | None = None
    method: str | None = None
    mode: str | None = None
    protocol: str = ""
    decision: str | None = None
    source: str | None = None
    port: int | None = None
    timestamp: int = 0

    def __post_init__(self) -> None:
        _ensure_str(self.host, "host")
        _ensure_str(self.reason, "reason")
        _ensure_optional_str_value(self.client, "client")
        _ensure_optional_str_value(self.method, "method")
        _ensure_optional_str_value(self.mode, "mode")
        _ensure_str(self.protocol, "protocol")
        _ensure_optional_str_value(self.decision, "decision")
        _ensure_optional_str_value(self.source, "source")
        _ensure_optional_int_value(self.port, "port")
        _ensure_int_value(self.timestamp, "timestamp")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "BlockedRequest":
        if not isinstance(value, dict):
            raise TypeError("blocked request must be a mapping")
        return cls(
            host=_required_str(value, "host"),
            reason=_required_str(value, "reason"),
            client=_optional_str(value, "client"),
            method=_optional_str(value, "method"),
            mode=_optional_str(value, "mode"),
            protocol=_optional_str(value, "protocol") or "",
            decision=_optional_str(value, "decision"),
            source=_optional_str(value, "source"),
            port=_optional_int(value, "port"),
            timestamp=_optional_int(value, "timestamp") or 0,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "host": self.host,
            "reason": self.reason,
            "protocol": self.protocol,
            "timestamp": self.timestamp,
        }
        if self.client is not None:
            data["client"] = self.client
        if self.method is not None:
            data["method"] = self.method
        if self.mode is not None:
            data["mode"] = self.mode
        if self.decision is not None:
            data["decision"] = self.decision
        if self.source is not None:
            data["source"] = self.source
        if self.port is not None:
            data["port"] = self.port
        return data


@dataclass(frozen=True)
class ExecPolicyNetworkRuleAmendment:
    protocol: ExecPolicyNetworkRuleProtocol
    decision: Decision
    justification: str

    def __post_init__(self) -> None:
        if not isinstance(self.protocol, ExecPolicyNetworkRuleProtocol):
            raise TypeError("protocol must be an ExecPolicyNetworkRuleProtocol")
        if not isinstance(self.decision, Decision):
            raise TypeError("decision must be a Decision")
        _ensure_str(self.justification, "justification")


def parse_network_policy_decision(value: str | None) -> NetworkPolicyDecision | None:
    if value is None:
        return None
    _ensure_str(value, "value")
    if value == "deny":
        return NetworkPolicyDecision.DENY
    if value == "ask":
        return NetworkPolicyDecision.ASK
    return None


def network_approval_context_from_payload(
    payload: NetworkPolicyDecisionPayload | dict[str, JsonValue],
) -> NetworkApprovalContext | None:
    if not isinstance(payload, NetworkPolicyDecisionPayload):
        payload = NetworkPolicyDecisionPayload.from_mapping(payload)
    if not payload.is_ask_from_decider():
        return None

    protocol = payload.protocol
    if protocol is None:
        return None

    host = (payload.host or "").strip()
    if not host:
        return None

    return NetworkApprovalContext(host=host, protocol=protocol)


def denied_network_policy_message(
    blocked: BlockedRequest | dict[str, JsonValue],
) -> str | None:
    if not isinstance(blocked, BlockedRequest):
        blocked = BlockedRequest.from_mapping(blocked)

    decision = parse_network_policy_decision(blocked.decision)
    if decision is not NetworkPolicyDecision.DENY:
        return None

    host = blocked.host.strip()
    if not host:
        return "Network access was blocked by policy."

    detail = {
        "denied": "domain is explicitly denied by policy and cannot be approved from this prompt",
        "not_allowed": "domain is not on the allowlist for the current sandbox mode",
        "not_allowed_local": "local/private network addresses are blocked by the sandbox policy",
        "method_not_allowed": "request method is blocked by the current network mode",
        "proxy_disabled": "network proxy is disabled",
    }.get(blocked.reason, "request is blocked by network policy")

    return f'Network access to "{host}" was blocked: {detail}.'


def execpolicy_network_rule_amendment(
    amendment: NetworkPolicyAmendment,
    network_approval_context: NetworkApprovalContext,
    host: str,
) -> ExecPolicyNetworkRuleAmendment:
    if not isinstance(amendment, NetworkPolicyAmendment):
        raise TypeError("amendment must be a NetworkPolicyAmendment")
    if not isinstance(network_approval_context, NetworkApprovalContext):
        raise TypeError("network_approval_context must be a NetworkApprovalContext")
    _ensure_str(host, "host")
    protocol = _execpolicy_protocol(network_approval_context.protocol)
    if amendment.action is NetworkPolicyRuleAction.ALLOW:
        decision = Decision.ALLOW
        action_verb = "Allow"
    elif amendment.action is NetworkPolicyRuleAction.DENY:
        decision = Decision.FORBIDDEN
        action_verb = "Deny"
    else:
        raise ValueError("unsupported network policy rule action")
    protocol_label = _protocol_label(network_approval_context.protocol)
    return ExecPolicyNetworkRuleAmendment(
        protocol=protocol,
        decision=decision,
        justification=f"{action_verb} {protocol_label} access to {host}",
    )


def _execpolicy_protocol(protocol: NetworkApprovalProtocol) -> ExecPolicyNetworkRuleProtocol:
    if protocol is NetworkApprovalProtocol.HTTP:
        return ExecPolicyNetworkRuleProtocol.HTTP
    if protocol is NetworkApprovalProtocol.HTTPS:
        return ExecPolicyNetworkRuleProtocol.HTTPS
    if protocol is NetworkApprovalProtocol.SOCKS5_TCP:
        return ExecPolicyNetworkRuleProtocol.SOCKS5_TCP
    if protocol is NetworkApprovalProtocol.SOCKS5_UDP:
        return ExecPolicyNetworkRuleProtocol.SOCKS5_UDP
    raise ValueError("unsupported network approval protocol")


def _protocol_label(protocol: NetworkApprovalProtocol) -> str:
    if protocol is NetworkApprovalProtocol.HTTP:
        return "http"
    if protocol is NetworkApprovalProtocol.HTTPS:
        return "https_connect"
    if protocol is NetworkApprovalProtocol.SOCKS5_TCP:
        return "socks5_tcp"
    if protocol is NetworkApprovalProtocol.SOCKS5_UDP:
        return "socks5_udp"
    raise ValueError("unsupported network approval protocol")


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_int(value: dict[str, JsonValue], key: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    _ensure_int_value(raw, key)
    return raw


def _ensure_str(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")


def _ensure_optional_str_value(value: object, name: str) -> None:
    if value is None:
        return
    _ensure_str(value, name)


def _ensure_int_value(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")


def _ensure_optional_int_value(value: object, name: str) -> None:
    if value is None:
        return
    _ensure_int_value(value, name)


__all__ = [
    "BlockedRequest",
    "ExecPolicyNetworkRuleAmendment",
    "ExecPolicyNetworkRuleProtocol",
    "denied_network_policy_message",
    "execpolicy_network_rule_amendment",
    "network_approval_context_from_payload",
    "parse_network_policy_decision",
]
