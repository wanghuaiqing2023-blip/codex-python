"""Network approval state helpers ported from Codex core.

This is the dependency-free slice of
``codex-rs/core/src/tools/network_approval.rs``: host/protocol/port scoping,
pending decisions, session approval caches, and active-call outcomes. The
Session, Guardian, hook runtime, and network proxy integration points remain
outside this module for now.
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.protocol import (
    AskForApproval,
    NetworkApprovalProtocol,
    PermissionProfile,
)

JsonValue = Any
U16_MAX = 2**16 - 1

NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED = "not_allowed"


class NetworkApprovalMode(str, Enum):
    IMMEDIATE = "immediate"
    DEFERRED = "deferred"


def _validate_u16_port(port: int, *, label: str = "port") -> int:
    if isinstance(port, bool) or not isinstance(port, int):
        raise TypeError(f"{label} must be an integer")
    if not 0 <= port <= U16_MAX:
        raise ValueError(f"{label} must fit in u16")
    return port


@dataclass(frozen=True)
class NetworkApprovalSpec:
    network: JsonValue | None
    mode: NetworkApprovalMode
    trigger: JsonValue
    command: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", NetworkApprovalMode(self.mode))
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")


@dataclass(frozen=True)
class NetworkDecision:
    type: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("network decision type must be a string")
        if self.type not in {"allow", "deny"}:
            raise ValueError(f"unknown network decision type: {self.type}")
        if self.type == "allow" and self.reason is not None:
            raise ValueError("allow decision cannot include reason")
        if self.type == "deny" and not isinstance(self.reason, str):
            raise TypeError("deny decision reason must be a string")

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
        if not isinstance(self.host, str):
            raise TypeError("host must be a string")
        if not isinstance(self.protocol, str):
            raise TypeError("protocol must be a string")
        _validate_u16_port(self.port)
        object.__setattr__(self, "host", self.host.lower())

    @classmethod
    def from_request(
        cls,
        request: Mapping[str, JsonValue] | object,
        protocol: NetworkApprovalProtocol | str,
    ) -> "HostApprovalKey":
        return cls(
            host=_request_value(request, "host"),
            protocol=protocol_key_label(protocol),
            port=_request_value(request, "port"),
        )


def protocol_key_label(protocol: NetworkApprovalProtocol | str) -> str:
    if isinstance(protocol, str):
        protocol = NetworkApprovalProtocol.parse(protocol)
    elif not isinstance(protocol, NetworkApprovalProtocol):
        raise TypeError("protocol must be a NetworkApprovalProtocol or string")
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


class InlineNetworkApprovalDisposition(str, Enum):
    ALLOW_CACHED = "allow_cached"
    DENY_CACHED = "deny_cached"
    DENY_POLICY = "deny_policy"
    WAIT_FOR_PENDING = "wait_for_pending"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class NetworkApprovalOutcome:
    type: str
    message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("network approval outcome type must be a string")
        if self.type not in {"denied_by_user", "denied_by_policy"}:
            raise ValueError(f"unknown network approval outcome type: {self.type}")
        if self.type == "denied_by_user" and self.message is not None:
            raise ValueError("denied_by_user outcome cannot include message")
        if self.type == "denied_by_policy" and not isinstance(self.message, str):
            raise TypeError("denied_by_policy message must be a string")

    @classmethod
    def denied_by_user(cls) -> "NetworkApprovalOutcome":
        return cls("denied_by_user")

    @classmethod
    def denied_by_policy(cls, message: str) -> "NetworkApprovalOutcome":
        return cls("denied_by_policy", message)


class NetworkApprovalRejected(RuntimeError):
    pass


class DeferredNetworkApproval:
    def __init__(
        self,
        registration_id: str,
        cancellation_token: CancellationToken,
    ) -> None:
        if not isinstance(registration_id, str):
            raise TypeError("registration_id must be a string")
        if not isinstance(cancellation_token, CancellationToken):
            raise TypeError("cancellation_token must be a CancellationToken")
        self._registration_id = registration_id
        self._cancellation_token = cancellation_token
        self._finish_lock = threading.Lock()
        self._finish_recorded = False
        self._finish_outcome: NetworkApprovalOutcome | None = None

    @property
    def registration_id(self) -> str:
        return self._registration_id

    @property
    def cancellation_token(self) -> CancellationToken:
        return self._cancellation_token

    def is_cancelled(self) -> bool:
        return self._cancellation_token.is_cancelled()

    def finish(self, service: "NetworkApprovalService") -> None:
        if not isinstance(service, NetworkApprovalService):
            raise TypeError("service must be NetworkApprovalService")
        with self._finish_lock:
            if not self._finish_recorded:
                self._finish_outcome = service.finish_call_outcome(self._registration_id)
                self._finish_recorded = True
            outcome = self._finish_outcome
        network_approval_outcome_to_result(outcome)


@dataclass(frozen=True)
class ActiveNetworkApproval:
    registration_id: str | None
    mode: NetworkApprovalMode
    cancellation_token: CancellationToken

    def __post_init__(self) -> None:
        if self.registration_id is not None and not isinstance(self.registration_id, str):
            raise TypeError("registration_id must be a string or None")
        object.__setattr__(self, "mode", NetworkApprovalMode(self.mode))
        if not isinstance(self.cancellation_token, CancellationToken):
            raise TypeError("cancellation_token must be a CancellationToken")

    def into_deferred(self) -> DeferredNetworkApproval | None:
        if self.mode is NetworkApprovalMode.DEFERRED and self.registration_id is not None:
            return DeferredNetworkApproval(self.registration_id, self.cancellation_token)
        return None


def network_approval_outcome_to_result(outcome: NetworkApprovalOutcome | None) -> None:
    if outcome is None:
        return
    if outcome.type == "denied_by_user":
        raise NetworkApprovalRejected("rejected by user")
    if outcome.type == "denied_by_policy":
        raise NetworkApprovalRejected(outcome.message or "")
    raise NetworkApprovalRejected(str(outcome))


def allows_network_approval_flow(policy: AskForApproval | str) -> bool:
    if not isinstance(policy, (AskForApproval, str)):
        raise TypeError("approval_policy must be an AskForApproval or string")
    return AskForApproval(policy) is not AskForApproval.NEVER


def permission_profile_allows_network_approval_flow(
    permission_profile: PermissionProfile,
) -> bool:
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError("permission_profile must be a PermissionProfile")
    return permission_profile.type == "managed"


def begin_network_approval(
    service: "NetworkApprovalService",
    turn_id: str,
    managed_network_active: bool,
    spec: NetworkApprovalSpec | None,
    *,
    registration_id: str | None = None,
) -> ActiveNetworkApproval | None:
    if not isinstance(service, NetworkApprovalService):
        raise TypeError("service must be a NetworkApprovalService")
    if registration_id is not None and not isinstance(registration_id, str):
        raise TypeError("registration_id must be a string")
    if not isinstance(turn_id, str):
        raise TypeError("turn_id must be a string")
    if not isinstance(managed_network_active, bool):
        raise TypeError("managed_network_active must be a bool")
    if spec is None:
        return None
    if not isinstance(spec, NetworkApprovalSpec):
        raise TypeError("spec must be NetworkApprovalSpec or None")
    if not managed_network_active or spec.network is None:
        return None
    registration = registration_id or str(uuid.uuid4())
    token = service.register_call(
        registration,
        turn_id,
        spec.trigger,
        spec.command,
    )
    return ActiveNetworkApproval(registration, spec.mode, token)


def finish_immediate_network_approval(
    service: "NetworkApprovalService",
    active: ActiveNetworkApproval,
) -> None:
    if not isinstance(service, NetworkApprovalService):
        raise TypeError("service must be NetworkApprovalService")
    if not isinstance(active, ActiveNetworkApproval):
        raise TypeError("active must be ActiveNetworkApproval")
    if active.registration_id is None:
        return
    service.finish_call(active.registration_id)


def finish_deferred_network_approval(
    service: "NetworkApprovalService",
    deferred: DeferredNetworkApproval | None,
) -> None:
    if not isinstance(service, NetworkApprovalService):
        raise TypeError("service must be NetworkApprovalService")
    if deferred is None:
        return
    if not isinstance(deferred, DeferredNetworkApproval):
        raise TypeError("deferred must be DeferredNetworkApproval or None")
    deferred.finish(service)


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def cancelled(self) -> None:
        while not self._event.is_set():
            await _sleep_cancel_poll()


async def _sleep_cancel_poll() -> None:
    import asyncio

    await asyncio.sleep(0.05)


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
class InlineNetworkApprovalPlan:
    key: HostApprovalKey
    target: str
    prompt_reason: str
    approval_id: str
    prompt_command: tuple[str, str]
    disposition: InlineNetworkApprovalDisposition
    decision: NetworkDecision | None = None
    pending: PendingHostApproval | None = None
    pending_owner: bool = False
    policy_denial_message: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.key, HostApprovalKey):
            raise TypeError("key must be a HostApprovalKey")
        if not isinstance(self.target, str):
            raise TypeError("target must be a string")
        if not isinstance(self.prompt_reason, str):
            raise TypeError("prompt_reason must be a string")
        if not isinstance(self.approval_id, str):
            raise TypeError("approval_id must be a string")
        if not isinstance(self.prompt_command, tuple) or len(self.prompt_command) != 2:
            raise TypeError("prompt_command must be a two-item tuple")
        object.__setattr__(self, "disposition", InlineNetworkApprovalDisposition(self.disposition))
        if self.decision is not None and not isinstance(self.decision, NetworkDecision):
            raise TypeError("decision must be a NetworkDecision or None")
        if self.pending is not None and not isinstance(self.pending, PendingHostApproval):
            raise TypeError("pending must be a PendingHostApproval or None")
        if not isinstance(self.pending_owner, bool):
            raise TypeError("pending_owner must be a bool")
        if self.policy_denial_message is not None and not isinstance(self.policy_denial_message, str):
            raise TypeError("policy_denial_message must be a string or None")


@dataclass(frozen=True)
class ActiveNetworkApprovalCall:
    registration_id: str
    turn_id: str
    trigger: JsonValue
    command: str
    cancellation_token: CancellationToken

    def __post_init__(self) -> None:
        if not isinstance(self.registration_id, str):
            raise TypeError("registration_id must be a string")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")
        if not isinstance(self.cancellation_token, CancellationToken):
            raise TypeError("cancellation_token must be a CancellationToken")


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
        if not isinstance(registration_id, str):
            raise TypeError("registration_id must be a string")
        if not isinstance(turn_id, str):
            raise TypeError("turn_id must be a string")
        if not isinstance(command, str):
            raise TypeError("command must be a string")
        if cancellation_token is not None and not isinstance(cancellation_token, CancellationToken):
            raise TypeError("cancellation_token must be a CancellationToken")
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
        blocked: Any | Mapping[str, JsonValue],
    ) -> None:
        from pycodex.core.network_policy_decision import denied_network_policy_message

        message = denied_network_policy_message(blocked)
        if message is not None:
            self.record_outcome_for_single_active_call(
                NetworkApprovalOutcome.denied_by_policy(message)
            )

    @staticmethod
    def format_network_target(protocol: str, host: str, port: int) -> str:
        if not isinstance(protocol, str):
            raise TypeError("protocol must be a string")
        if not isinstance(host, str):
            raise TypeError("host must be a string")
        _validate_u16_port(port)
        return f"{protocol}://{host}:{port}"

    @staticmethod
    def approval_id_for_key(key: HostApprovalKey) -> str:
        return f"network#{key.protocol}#{key.host}#{key.port}"


def plan_inline_network_policy_request(
    service: NetworkApprovalService,
    request: Mapping[str, JsonValue] | object,
    protocol: NetworkApprovalProtocol | str,
    *,
    permission_profile: PermissionProfile | None,
    approval_policy: AskForApproval | str,
) -> InlineNetworkApprovalPlan:
    if not isinstance(service, NetworkApprovalService):
        raise TypeError("service must be a NetworkApprovalService")
    if not isinstance(approval_policy, (AskForApproval, str)):
        raise TypeError("approval_policy must be an AskForApproval or string")
    approval_policy = AskForApproval(approval_policy)

    key = HostApprovalKey.from_request(request, protocol)
    host = _request_value(request, "host")
    port = _request_value(request, "port")
    if not isinstance(host, str):
        raise TypeError("host must be a string")
    _validate_u16_port(port)

    raw_target = NetworkApprovalService.format_network_target(key.protocol, host, port)
    normalized_target = NetworkApprovalService.format_network_target(key.protocol, key.host, port)
    target = raw_target
    prompt_reason = f"{key.host} is not in the allowed_domains"
    approval_id = NetworkApprovalService.approval_id_for_key(key)
    prompt_command = ("network-access", target)
    policy_denial_message = f'Network access to "{normalized_target}" was blocked by policy.'

    if key in service.session_denied_hosts:
        return InlineNetworkApprovalPlan(
            key=key,
            target=normalized_target,
            prompt_reason=prompt_reason,
            approval_id=approval_id,
            prompt_command=prompt_command,
            disposition=InlineNetworkApprovalDisposition.DENY_CACHED,
            decision=NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED),
            policy_denial_message=policy_denial_message,
        )

    if key in service.session_approved_hosts:
        return InlineNetworkApprovalPlan(
            key=key,
            target=target,
            prompt_reason=prompt_reason,
            approval_id=approval_id,
            prompt_command=prompt_command,
            disposition=InlineNetworkApprovalDisposition.ALLOW_CACHED,
            decision=NetworkDecision.allow(),
        )

    pending, is_owner = service.get_or_create_pending_approval(key)
    if not is_owner:
        if permission_profile is not None and permission_profile_allows_network_approval_flow(permission_profile):
            decision = pending.decision
            return InlineNetworkApprovalPlan(
                key=key,
                target=target,
                prompt_reason=prompt_reason,
                approval_id=approval_id,
                prompt_command=prompt_command,
                disposition=InlineNetworkApprovalDisposition.WAIT_FOR_PENDING,
                decision=None if decision is None else decision.to_network_decision(),
                pending=pending,
                pending_owner=False,
                policy_denial_message=policy_denial_message,
            )
        pending.set_decision(PendingApprovalDecision.DENY)
        service.pending_host_approvals.pop(key, None)
        service.record_outcome_for_single_active_call(
            NetworkApprovalOutcome.denied_by_policy(policy_denial_message)
        )
        denied_pending = PendingHostApproval()
        denied_pending.set_decision(PendingApprovalDecision.DENY)
        return InlineNetworkApprovalPlan(
            key=key,
            target=normalized_target,
            prompt_reason=prompt_reason,
            approval_id=approval_id,
            prompt_command=prompt_command,
            disposition=InlineNetworkApprovalDisposition.DENY_POLICY,
            decision=NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED),
            pending=denied_pending,
            pending_owner=False,
            policy_denial_message=policy_denial_message,
        )

    if (
        permission_profile is None
        or not permission_profile_allows_network_approval_flow(permission_profile)
        or not allows_network_approval_flow(approval_policy)
    ):
        pending.set_decision(PendingApprovalDecision.DENY)
        service.pending_host_approvals.pop(key, None)
        service.record_outcome_for_single_active_call(
            NetworkApprovalOutcome.denied_by_policy(policy_denial_message)
        )
        return InlineNetworkApprovalPlan(
            key=key,
            target=normalized_target,
            prompt_reason=prompt_reason,
            approval_id=approval_id,
            prompt_command=prompt_command,
            disposition=InlineNetworkApprovalDisposition.DENY_POLICY,
            decision=NetworkDecision.deny(NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED),
            pending=pending,
            pending_owner=True,
            policy_denial_message=policy_denial_message,
        )

    return InlineNetworkApprovalPlan(
        key=key,
        target=target,
        prompt_reason=prompt_reason,
        approval_id=approval_id,
        prompt_command=prompt_command,
        disposition=InlineNetworkApprovalDisposition.REVIEW_REQUIRED,
        pending=pending,
        pending_owner=True,
        policy_denial_message=policy_denial_message,
    )


def _request_value(request: Mapping[str, JsonValue] | object, key: str) -> JsonValue:
    if isinstance(request, Mapping):
        return request[key]
    if not hasattr(request, "__dict__") and not hasattr(request, key):
        raise TypeError("request must be a mapping or object with host and port attributes")
    return getattr(request, key)


@dataclass(frozen=True)
class NetworkReviewDecisionResolution:
    decision: PendingApprovalDecision
    outcome: NetworkApprovalOutcome | None = None
    cache_approved_host: bool = False
    cache_denied_host: bool = False
    policy_amendment: JsonValue | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", PendingApprovalDecision(self.decision))
        if self.outcome is not None and not isinstance(self.outcome, NetworkApprovalOutcome):
            raise TypeError("outcome must be a NetworkApprovalOutcome")
        if not isinstance(self.cache_approved_host, bool):
            raise TypeError("cache_approved_host must be a bool")
        if not isinstance(self.cache_denied_host, bool):
            raise TypeError("cache_denied_host must be a bool")
        if self.cache_approved_host and self.cache_denied_host:
            raise ValueError("a network review decision cannot approve and deny the same host")


def resolve_network_review_decision(review_decision: JsonValue) -> NetworkReviewDecisionResolution:
    from pycodex.protocol.approvals import NetworkPolicyRuleAction, ReviewDecision

    if not isinstance(review_decision, (Mapping, ReviewDecision, str)):
        raise TypeError("review decision must be a mapping, review decision, or string")
    decision = ReviewDecision.from_mapping(review_decision)
    if decision.type in {"approved", "approved_execpolicy_amendment"}:
        return NetworkReviewDecisionResolution(PendingApprovalDecision.ALLOW_ONCE)
    if decision.type == "approved_for_session":
        return NetworkReviewDecisionResolution(
            PendingApprovalDecision.ALLOW_FOR_SESSION,
            cache_approved_host=True,
        )
    if decision.type == "network_policy_amendment":
        amendment = decision.network_policy_amendment
        if amendment is None:
            raise ValueError("network_policy_amendment decision requires an amendment")
        if amendment.action is NetworkPolicyRuleAction.ALLOW:
            return NetworkReviewDecisionResolution(
                PendingApprovalDecision.ALLOW_FOR_SESSION,
                cache_approved_host=True,
                policy_amendment=amendment,
            )
        return NetworkReviewDecisionResolution(
            PendingApprovalDecision.DENY,
            outcome=NetworkApprovalOutcome.denied_by_user(),
            cache_denied_host=True,
            policy_amendment=amendment,
        )
    if decision.type in {"denied", "abort"}:
        return NetworkReviewDecisionResolution(
            PendingApprovalDecision.DENY,
            outcome=NetworkApprovalOutcome.denied_by_user(),
        )
    if decision.type == "timed_out":
        return NetworkReviewDecisionResolution(
            PendingApprovalDecision.DENY,
            outcome=NetworkApprovalOutcome.denied_by_policy("Network approval request timed out."),
        )
    raise ValueError(f"unknown network review decision type: {decision.type}")


def apply_network_review_decision(
    service: NetworkApprovalService,
    key: HostApprovalKey,
    review_decision: JsonValue,
    *,
    registration_id: str | None = None,
) -> NetworkReviewDecisionResolution:
    if not isinstance(service, NetworkApprovalService):
        raise TypeError("service must be a NetworkApprovalService")
    if not isinstance(key, HostApprovalKey):
        raise TypeError("key must be a HostApprovalKey")
    if registration_id is not None and not isinstance(registration_id, str):
        raise TypeError("registration_id must be a string")

    resolution = resolve_network_review_decision(review_decision)
    if resolution.cache_approved_host:
        service.session_denied_hosts.discard(key)
        service.session_approved_hosts.add(key)
    if resolution.cache_denied_host:
        service.session_approved_hosts.discard(key)
        service.session_denied_hosts.add(key)

    pending = service.pending_host_approvals.get(key)
    if pending is not None:
        pending.set_decision(resolution.decision)

    if resolution.policy_amendment is not None:
        service.pending_host_approvals.pop(key, None)

    if registration_id is not None and resolution.outcome is not None:
        service.record_call_outcome(registration_id, resolution.outcome)

    return resolution


__all__ = [
    "NETWORK_APPROVAL_DENY_REASON_NOT_ALLOWED",
    "ActiveNetworkApproval",
    "ActiveNetworkApprovalCall",
    "CancellationToken",
    "DeferredNetworkApproval",
    "HostApprovalKey",
    "InlineNetworkApprovalDisposition",
    "InlineNetworkApprovalPlan",
    "NetworkApprovalMode",
    "NetworkApprovalOutcome",
    "NetworkApprovalRejected",
    "NetworkApprovalService",
    "NetworkApprovalSpec",
    "NetworkDecision",
    "PendingApprovalDecision",
    "PendingHostApproval",
    "NetworkReviewDecisionResolution",
    "apply_network_review_decision",
    "allows_network_approval_flow",
    "begin_network_approval",
    "finish_deferred_network_approval",
    "finish_immediate_network_approval",
    "network_approval_outcome_to_result",
    "permission_profile_allows_network_approval_flow",
    "plan_inline_network_policy_request",
    "protocol_key_label",
    "resolve_network_review_decision",
]
