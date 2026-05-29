"""Network policy decision payloads.

Ported from ``codex/codex-rs/protocol/src/network_policy.rs`` and the enum
wire names in ``codex/codex-rs/network-proxy/src/network_policy.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .approvals import NetworkApprovalProtocol


JsonValue = Any


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


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    if key not in value:
        raise KeyError(key)
    raw = value[key]
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
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    if not 0 <= raw <= 65535:
        raise ValueError(f"{key} must fit in u16")
    return raw


def _optional_protocol(value: dict[str, JsonValue], key: str) -> NetworkApprovalProtocol | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return NetworkApprovalProtocol.parse(raw)


def _ensure_optional_str(raw: JsonValue, key: str) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _ensure_optional_u16(raw: JsonValue, key: str) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    if not 0 <= raw <= 65535:
        raise ValueError(f"{key} must fit in u16")
    return raw


@dataclass(frozen=True)
class NetworkPolicyDecisionPayload:
    decision: NetworkPolicyDecision
    source: NetworkDecisionSource
    protocol: NetworkApprovalProtocol | None = None
    host: str | None = None
    reason: str | None = None
    port: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", NetworkPolicyDecision(self.decision))
        object.__setattr__(self, "source", NetworkDecisionSource(self.source))
        if self.protocol is not None and not isinstance(self.protocol, NetworkApprovalProtocol):
            if isinstance(self.protocol, str):
                object.__setattr__(self, "protocol", NetworkApprovalProtocol.parse(self.protocol))
            else:
                raise TypeError("protocol must be a NetworkApprovalProtocol or None")
        object.__setattr__(self, "host", _ensure_optional_str(self.host, "host"))
        object.__setattr__(self, "reason", _ensure_optional_str(self.reason, "reason"))
        object.__setattr__(self, "port", _ensure_optional_u16(self.port, "port"))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "NetworkPolicyDecisionPayload":
        data = _mapping(value, "network policy decision payload")
        return cls(
            decision=NetworkPolicyDecision(_required_str(data, "decision")),
            source=NetworkDecisionSource(_required_str(data, "source")),
            protocol=_optional_protocol(data, "protocol"),
            host=_optional_str(data, "host"),
            reason=_optional_str(data, "reason"),
            port=_optional_int(data, "port"),
        )

    def is_ask_from_decider(self) -> bool:
        return self.decision is NetworkPolicyDecision.ASK and self.source is NetworkDecisionSource.DECIDER

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "decision": self.decision.value,
            "source": self.source.value,
        }
        if self.protocol is not None:
            data["protocol"] = self.protocol.value
        if self.host is not None:
            data["host"] = self.host
        if self.reason is not None:
            data["reason"] = self.reason
        if self.port is not None:
            data["port"] = self.port
        return data
