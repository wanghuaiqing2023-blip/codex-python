"""Network approval state helpers ported from Codex core.

This is the dependency-free slice of
``codex-rs/core/src/tools/network_approval.rs``: host/protocol/port scoping,
pending decisions, session approval caches, and active-call outcomes. The
Session, Guardian, hook runtime, and network proxy integration points remain
outside this module for now.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.core.network_policy_decision import (
    BlockedRequest,
    denied_network_policy_message,
)
from pycodex.protocol import (
    AskForApproval,
    NetworkApprovalProtocol,
    PermissionProfile,
)

JsonValue = Any

NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED = "not_allowed"


class NetworkApprovalMode(str, Enum):
    IMMEDIATE = "immediate"
    DEFERRED = "deferred"


@dataclass(frozen=True)
class NetworkApprovalSpec:
    network: JsonValue | None
    mode: NetworkApprovalMode
    trigger: JsonValue
    command: str


@dataclass(frozen=True)
class NetworkDecision:
    type: str
    reason: str | None = None

    @classmethod
    def allow(cls) -> "NetworkDecision":
        return cls("allow")

    @classmethod
    def deny(cls, reason: str) -> "NetworkDecision":
        return cls("deny", reason)


@dataclass(frozen=True)
class HostApprovalKey:
    host: str
    protocol: str
    port: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "host", self.host.lower())

    @classmethod
    def from_request(
        cls,
        request: Mapping[str, JsonValue] | object,
        protocol: NetworkApprovalProtocol | str,
    ) -> "HostApprovalKey":
        return cls(
            host=str(_request_value(request, "host")),
            protocol=protocol_key_label(protocol),
            port=int(_request_value(request, "port")),
        )


def protocol_key_label(protocol: NetworkApprovalProtocol | str) -> str:
    if isinstance(protocol, str):
        protocol = NetworkApprovalProtocol.parse(protocol)
    if protocol is NetworkApprovalProtocol.HTTP:
        return "http"
    if protocol is NetworkApprovalProtocol.HTTPS:
        return "https"
    if protocol is NetworkApprovalProtocol.SOCKS5_TCP:
        return "socks5-tcp"
    return "socks5-udp"


class PendingApprovalDecision(str, Enum):
    ALLOW_ONCE = "allow_once"
    ALLOW_FOR_SESSION = "allow_for_session"
    DENY = "deny"

    def to_network_decision(self) -> NetworkDecision:
        if self in {PendingApprovalDecision.ALLOW_ONCE, PendingApprovalDecision.ALLOW_FOR_SESSION}:
            return NetworkDecision.allow()
        return NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED)


@dataclass(frozen=True)
class NetworkApprovalOutcome:
    type: str
    message: str | None = None

    @classmethod
    def denied_by_user(cls) -> "NetworkApprovalOutcome":
        return cls("denied_by_user")

    @classmethod
    def denied_by_policy(cls, message: str) -> "NetworkApprovalOutcome":
        return cls("denied_by_policy", message)


class NetworkApprovalRejected(RuntimeError):
    pass


def network_approval_outcome_to_result(outcome: NetworkApprovalOutcome | None) -> None:
    if outcome is None:
        return
    if outcome.type == "denied_by_user":
        raise NetworkApprovalRejected("rejected by user")
    if outcome.type == "denied_by_policy":
        raise NetworkApprovalRejected(outcome.message or "")
    raise NetworkApprovalRejected(str(outcome))


def allows_network_approval_flow(policy: AskForApproval | str) -> bool:
    return AskForApproval(policy) is not AskForApproval.NEVER


def permission_profile_allows_network_approval_flow(
    permission_profile: PermissionProfile,
) -> bool:
    return permission_profile.type == "managed"


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()


class PendingHostApproval:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._decision: PendingApprovalDecision | None = None

    @property
    def decision(self) -> PendingApprovalDecision | None:
        with self._condition:
            return self._decision

    def wait_for_decision(self, timeout: float | None = None) -> PendingApprovalDecision | None:
        with self._condition:
            if self._decision is None:
                self._condition.wait(timeout)
            return self._decision

    def set_decision(self, decision: PendingApprovalDecision) -> None:
        with self._condition:
            self._decision = PendingApprovalDecision(decision)
            self._condition.notify_all()


@dataclass(frozen=True)
class ActiveNetworkApprovalCall:
    registration_id: str
    turn_id: str
    trigger: JsonValue
    command: str
    cancellation_token: CancellationToken


class NetworkApprovalService:
    def __init__(self) -> None:
        self.active_calls: OrderedDict[str, ActiveNetworkApprovalCall] = OrderedDict()
        self.call_outcomes: dict[str, NetworkApprovalOutcome] = {}
        self.pending_host_approvals: dict[HostApprovalKey, PendingHostApproval] = {}
        self.session_approved_hosts: set[HostApprovalKey] = set()
        self.session_denied_hosts: set[HostApprovalKey] = set()

    def sync_session_approved_hosts_to(self, other: "NetworkApprovalService") -> None:
        other.session_approved_hosts.clear()
        other.session_approved_hosts.update(self.session_approved_hosts)

    def get_or_create_pending_approval(
        self,
        key: HostApprovalKey,
    ) -> tuple[PendingHostApproval, bool]:
        existing = self.pending_host_approvals.get(key)
        if existing is not None:
            return existing, False
        created = PendingHostApproval()
        self.pending_host_approvals[key] = created
        return created, True

    def register_call(
        self,
        registration_id: str,
        turn_id: str,
        trigger: JsonValue,
        command: str,
        cancellation_token: CancellationToken | None = None,
    ) -> CancellationToken:
        token = cancellation_token or CancellationToken()
        self.active_calls[registration_id] = ActiveNetworkApprovalCall(
            registration_id=registration_id,
            turn_id=turn_id,
            trigger=trigger,
            command=command,
            cancellation_token=token,
        )
        return token

    def unregister_call(self, registration_id: str) -> None:
        self.remove_call(registration_id)

    def resolve_single_active_call(self) -> ActiveNetworkApprovalCall | None:
        if len(self.active_calls) == 1:
            return next(iter(self.active_calls.values()))
        return None

    def record_call_outcome(
        self,
        registration_id: str,
        outcome: NetworkApprovalOutcome,
    ) -> None:
        call = self.active_calls.get(registration_id)
        if call is None:
            return
        if self.call_outcomes.get(registration_id) == NetworkApprovalOutcome.denied_by_user():
            return
        self.call_outcomes[registration_id] = outcome
        call.cancellation_token.cancel()

    def record_outcome_for_single_active_call(self, outcome: NetworkApprovalOutcome) -> None:
        owner_call = self.resolve_single_active_call()
        if owner_call is not None:
            self.record_call_outcome(owner_call.registration_id, outcome)

    def remove_call(self, registration_id: str) -> NetworkApprovalOutcome | None:
        self.active_calls.pop(registration_id, None)
        return self.call_outcomes.pop(registration_id, None)

    def finish_call_outcome(self, registration_id: str) -> NetworkApprovalOutcome | None:
        return self.remove_call(registration_id)

    def finish_call(self, registration_id: str) -> None:
        network_approval_outcome_to_result(self.finish_call_outcome(registration_id))

    def take_call_outcome(self, registration_id: str) -> NetworkApprovalOutcome | None:
        return self.call_outcomes.pop(registration_id, None)

    def record_blocked_request(
        self,
        blocked: BlockedRequest | Mapping[str, JsonValue],
    ) -> None:
        message = denied_network_policy_message(blocked)
        if message is not None:
            self.record_outcome_for_single_active_call(
                NetworkApprovalOutcome.denied_by_policy(message)
            )

    @staticmethod
    def format_network_target(protocol: str, host: str, port: int) -> str:
        return f"{protocol}://{host}:{port}"

    @staticmethod
    def approval_id_for_key(key: HostApprovalKey) -> str:
        return f"network#{key.protocol}#{key.host}#{key.port}"


def _request_value(request: Mapping[str, JsonValue] | object, key: str) -> JsonValue:
    if isinstance(request, Mapping):
        return request[key]
    return getattr(request, key)


__all__ = [
    "NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED",
    "ActiveNetworkApprovalCall",
    "CancellationToken",
    "HostApprovalKey",
    "NetworkApprovalMode",
    "NetworkApprovalOutcome",
    "NetworkApprovalRejected",
    "NetworkApprovalService",
    "NetworkApprovalSpec",
    "NetworkDecision",
    "PendingApprovalDecision",
    "PendingHostApproval",
    "allows_network_approval_flow",
    "network_approval_outcome_to_result",
    "permission_profile_allows_network_approval_flow",
    "protocol_key_label",
]
