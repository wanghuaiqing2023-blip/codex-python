"""Approval protocol types.

Ported from:

- ``codex/codex-rs/protocol/src/approvals.rs``
- the ``ReviewDecision`` and ``FileChange`` slices of
  ``codex/codex-rs/protocol/src/protocol.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .mcp import RequestId
from .models import AdditionalPermissionProfile, PermissionProfile
from .request_permissions import RequestPermissionProfile

JsonValue = Any
I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


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


def _required_int(value: dict[str, JsonValue], key: str) -> int:
    raw = value.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    return raw


def _optional_int(value: dict[str, JsonValue], key: str) -> int | None:
    raw = value.get(key)
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    return raw


def _ensure_i64(value: JsonValue, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    if not I64_MIN <= value <= I64_MAX:
        raise ValueError(f"{key} must fit in i64")
    return value


def _ensure_u16(value: JsonValue, key: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    if not 0 <= value <= 65535:
        raise ValueError(f"{key} must fit in u16")
    return value


def _string_list(value: JsonValue, label: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must be a list of strings")
    return tuple(value)


def _string_tuple(value: JsonValue, label: str) -> tuple[str, ...]:
    return _string_list(value, label)


def _sequence(value: JsonValue, label: str) -> tuple[JsonValue, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise TypeError(f"{label} must be a list")
    return tuple(value)


def _path_list(value: JsonValue, label: str) -> tuple[Path, ...]:
    return tuple(Path(item) for item in _string_list(value, label))


def _parsed_command_tuple(value: JsonValue) -> tuple[Any, ...]:
    return tuple(_parsed_command_from_mapping(item) for item in _sequence(value, "parsed_cmd"))


def _parsed_command_from_mapping(value: JsonValue) -> Any:
    from .parse_command import ParsedCommand

    return ParsedCommand.from_mapping(value)


def _parsed_command_mapping(value: Any) -> JsonValue:
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return to_mapping()
    if isinstance(value, dict):
        return dict(value)
    return value


def _camel_to_snake(value: str) -> str:
    if "_" in value:
        return value
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


@dataclass(frozen=True)
class ResolvedPermissionProfile:
    permission_profile: PermissionProfile

    def __post_init__(self) -> None:
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be a PermissionProfile")


@dataclass(frozen=True)
class EscalationPermissions:
    type: str
    additional_permission_profile: AdditionalPermissionProfile | None = None
    resolved_permission_profile: ResolvedPermissionProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type == "additional_permission_profile":
            if not isinstance(self.additional_permission_profile, AdditionalPermissionProfile):
                raise TypeError("additional_permission_profile must be an AdditionalPermissionProfile")
            if self.resolved_permission_profile is not None:
                raise ValueError("additional_permission_profile variant cannot include resolved_permission_profile")
            return
        if self.type == "resolved_permission_profile":
            if not isinstance(self.resolved_permission_profile, ResolvedPermissionProfile):
                raise TypeError("resolved_permission_profile must be a ResolvedPermissionProfile")
            if self.additional_permission_profile is not None:
                raise ValueError("resolved_permission_profile variant cannot include additional_permission_profile")
            return
        raise ValueError(f"unknown escalation permissions type: {self.type}")

    @classmethod
    def additional(cls, profile: AdditionalPermissionProfile) -> "EscalationPermissions":
        return cls(type="additional_permission_profile", additional_permission_profile=profile)

    @classmethod
    def resolved(cls, profile: ResolvedPermissionProfile) -> "EscalationPermissions":
        return cls(type="resolved_permission_profile", resolved_permission_profile=profile)


@dataclass(frozen=True)
class ExecPolicyAmendment:
    command: tuple[str, ...]

    def __post_init__(self) -> None:
        if isinstance(self.command, str) or not isinstance(self.command, (list, tuple)):
            raise TypeError("command must be a list of strings")
        object.__setattr__(self, "command", tuple(self.command))
        if not all(isinstance(token, str) for token in self.command):
            raise TypeError("command must be a list of strings")

    @classmethod
    def new(cls, command: list[str] | tuple[str, ...]) -> "ExecPolicyAmendment":
        if isinstance(command, str) or not isinstance(command, (list, tuple)):
            raise TypeError("command must be a list of strings")
        return cls(tuple(command))

    def command_tokens(self) -> tuple[str, ...]:
        return self.command

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ExecPolicyAmendment":
        data = _mapping(value, "exec policy amendment")
        command = data.get("command")
        if not isinstance(command, list | tuple) or not all(isinstance(token, str) for token in command):
            raise TypeError("command must be a list of strings")
        return cls(tuple(command))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"command": list(self.command)}


class NetworkApprovalProtocol(str, Enum):
    HTTP = "http"
    HTTPS = "https"
    SOCKS5_TCP = "socks5_tcp"
    SOCKS5_UDP = "socks5_udp"

    @classmethod
    def parse(cls, value: str) -> "NetworkApprovalProtocol":
        if not isinstance(value, str):
            raise TypeError("network approval protocol must be a string")
        if value in {"https_connect", "http-connect"}:
            return cls.HTTPS
        return cls(value)


@dataclass(frozen=True)
class NetworkApprovalContext:
    host: str
    protocol: NetworkApprovalProtocol

    def __post_init__(self) -> None:
        if not isinstance(self.host, str):
            raise TypeError("host must be a string")
        if not isinstance(self.protocol, NetworkApprovalProtocol):
            if isinstance(self.protocol, str):
                object.__setattr__(self, "protocol", NetworkApprovalProtocol.parse(self.protocol))
            else:
                raise TypeError("protocol must be a NetworkApprovalProtocol")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "NetworkApprovalContext":
        data = _mapping(value, "network approval context")
        return cls(host=_required_str(data, "host"), protocol=NetworkApprovalProtocol.parse(_required_str(data, "protocol")))

    def to_mapping(self) -> dict[str, str]:
        return {"host": self.host, "protocol": self.protocol.value}


class NetworkPolicyRuleAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class NetworkPolicyAmendment:
    host: str
    action: NetworkPolicyRuleAction

    def __post_init__(self) -> None:
        if not isinstance(self.host, str):
            raise TypeError("host must be a string")
        object.__setattr__(self, "action", NetworkPolicyRuleAction(self.action))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "NetworkPolicyAmendment":
        data = _mapping(value, "network policy amendment")
        return cls(host=_required_str(data, "host"), action=NetworkPolicyRuleAction(_required_str(data, "action")))

    def to_mapping(self) -> dict[str, str]:
        return {"host": self.host, "action": self.action.value}


class GuardianRiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GuardianUserAuthorization(str, Enum):
    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GuardianAssessmentOutcome(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class GuardianAssessmentStatus(str, Enum):
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"
    ABORTED = "aborted"


class GuardianAssessmentDecisionSource(str, Enum):
    AGENT = "agent"


class GuardianCommandSource(str, Enum):
    SHELL = "shell"
    UNIFIED_EXEC = "unified_exec"


@dataclass(frozen=True)
class GuardianAssessmentAction:
    type: str
    source: GuardianCommandSource | None = None
    command: str | None = None
    cwd: Path | None = None
    program: str | None = None
    argv: tuple[str, ...] = ()
    files: tuple[Path, ...] = ()
    target: str | None = None
    host: str | None = None
    protocol: NetworkApprovalProtocol | None = None
    port: int | None = None
    server: str | None = None
    tool_name: str | None = None
    connector_id: str | None = None
    connector_name: str | None = None
    tool_title: str | None = None
    reason: str | None = None
    permissions: RequestPermissionProfile | None = None

    @classmethod
    def command_action(cls, source: GuardianCommandSource, command: str, cwd: Path) -> "GuardianAssessmentAction":
        return cls(type="command", source=source, command=command, cwd=Path(cwd))

    @classmethod
    def execve(cls, source: GuardianCommandSource, program: str, argv: tuple[str, ...], cwd: Path) -> "GuardianAssessmentAction":
        return cls(type="execve", source=source, program=program, argv=tuple(argv), cwd=Path(cwd))

    @classmethod
    def apply_patch(cls, cwd: Path, files: tuple[Path, ...]) -> "GuardianAssessmentAction":
        return cls(type="apply_patch", cwd=Path(cwd), files=tuple(Path(file) for file in files))

    @classmethod
    def network_access(
        cls,
        target: str,
        host: str,
        protocol: NetworkApprovalProtocol,
        port: int,
    ) -> "GuardianAssessmentAction":
        return cls(type="network_access", target=target, host=host, protocol=protocol, port=port)

    @classmethod
    def mcp_tool_call(
        cls,
        server: str,
        tool_name: str,
        connector_id: str | None = None,
        connector_name: str | None = None,
        tool_title: str | None = None,
    ) -> "GuardianAssessmentAction":
        return cls(
            type="mcp_tool_call",
            server=server,
            tool_name=tool_name,
            connector_id=connector_id,
            connector_name=connector_name,
            tool_title=tool_title,
        )

    @classmethod
    def request_permissions(
        cls,
        permissions: RequestPermissionProfile,
        reason: str | None = None,
    ) -> "GuardianAssessmentAction":
        return cls(type="request_permissions", reason=reason, permissions=permissions)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "GuardianAssessmentAction":
        data = _mapping(value, "guardian assessment action")
        action_type = _required_str(data, "type")
        if action_type == "command":
            return cls.command_action(
                GuardianCommandSource(_required_str(data, "source")),
                _required_str(data, "command"),
                Path(_required_str(data, "cwd")),
            )
        if action_type == "execve":
            return cls.execve(
                GuardianCommandSource(_required_str(data, "source")),
                _required_str(data, "program"),
                _string_list(data.get("argv"), "argv"),
                Path(_required_str(data, "cwd")),
            )
        if action_type == "apply_patch":
            return cls.apply_patch(Path(_required_str(data, "cwd")), _path_list(data.get("files"), "files"))
        if action_type == "network_access":
            return cls.network_access(
                _required_str(data, "target"),
                _required_str(data, "host"),
                NetworkApprovalProtocol.parse(_required_str(data, "protocol")),
                _required_int(data, "port"),
            )
        if action_type == "mcp_tool_call":
            return cls.mcp_tool_call(
                _required_str(data, "server"),
                _required_str(data, "tool_name"),
                connector_id=_optional_str(data, "connector_id"),
                connector_name=_optional_str(data, "connector_name"),
                tool_title=_optional_str(data, "tool_title"),
            )
        if action_type == "request_permissions":
            return cls.request_permissions(
                RequestPermissionProfile.from_mapping(data["permissions"]),
                reason=_optional_str(data, "reason"),
            )
        raise ValueError(f"unknown guardian assessment action type: {action_type}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"type": self.type}
        if self.type == "command":
            data.update(
                {
                    "source": self.source.value if self.source is not None else None,
                    "command": self.command,
                    "cwd": str(self.cwd) if self.cwd is not None else None,
                }
            )
        elif self.type == "execve":
            data.update(
                {
                    "source": self.source.value if self.source is not None else None,
                    "program": self.program,
                    "argv": list(self.argv),
                    "cwd": str(self.cwd) if self.cwd is not None else None,
                }
            )
        elif self.type == "apply_patch":
            data.update(
                {
                    "cwd": str(self.cwd) if self.cwd is not None else None,
                    "files": [str(file) for file in self.files],
                }
            )
        elif self.type == "network_access":
            data.update(
                {
                    "target": self.target,
                    "host": self.host,
                    "protocol": self.protocol.value if self.protocol is not None else None,
                    "port": self.port,
                }
            )
        elif self.type == "mcp_tool_call":
            data.update(
                {
                    "server": self.server,
                    "tool_name": self.tool_name,
                    "connector_id": self.connector_id,
                    "connector_name": self.connector_name,
                    "tool_title": self.tool_title,
                }
            )
        elif self.type == "request_permissions":
            data.update(
                {
                    "reason": self.reason,
                    "permissions": self.permissions.to_mapping() if self.permissions is not None else None,
                }
            )
        return data


@dataclass(frozen=True)
class GuardianAssessmentEvent:
    id: str
    status: GuardianAssessmentStatus
    action: GuardianAssessmentAction
    target_item_id: str | None = None
    turn_id: str = ""
    started_at_ms: int = 0
    completed_at_ms: int | None = None
    risk_level: GuardianRiskLevel | None = None
    user_authorization: GuardianUserAuthorization | None = None
    rationale: str | None = None
    decision_source: GuardianAssessmentDecisionSource | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be a string")
        if self.target_item_id is not None and not isinstance(self.target_item_id, str):
            raise TypeError("target_item_id must be a string")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        object.__setattr__(self, "started_at_ms", _ensure_i64(self.started_at_ms, "started_at_ms"))
        if self.completed_at_ms is not None:
            object.__setattr__(self, "completed_at_ms", _ensure_i64(self.completed_at_ms, "completed_at_ms"))
        object.__setattr__(self, "status", GuardianAssessmentStatus(self.status))
        if self.risk_level is not None:
            object.__setattr__(self, "risk_level", GuardianRiskLevel(self.risk_level))
        if self.user_authorization is not None:
            object.__setattr__(self, "user_authorization", GuardianUserAuthorization(self.user_authorization))
        if self.rationale is not None and not isinstance(self.rationale, str):
            raise TypeError("rationale must be a string")
        if self.decision_source is not None:
            object.__setattr__(self, "decision_source", GuardianAssessmentDecisionSource(self.decision_source))
        if not isinstance(self.action, GuardianAssessmentAction):
            raise TypeError("action must be a GuardianAssessmentAction")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "GuardianAssessmentEvent":
        data = _mapping(value, "guardian assessment event")
        return cls(
            id=_required_str(data, "id"),
            target_item_id=_optional_str(data, "target_item_id"),
            turn_id=_optional_str(data, "turn_id") or "",
            started_at_ms=_ensure_i64(data.get("started_at_ms", 0), "started_at_ms"),
            completed_at_ms=_optional_int(data, "completed_at_ms"),
            status=GuardianAssessmentStatus(_required_str(data, "status")),
            risk_level=GuardianRiskLevel(_required_str(data, "risk_level")) if data.get("risk_level") is not None else None,
            user_authorization=(
                GuardianUserAuthorization(_required_str(data, "user_authorization"))
                if data.get("user_authorization") is not None
                else None
            ),
            rationale=_optional_str(data, "rationale"),
            decision_source=(
                GuardianAssessmentDecisionSource(_required_str(data, "decision_source"))
                if data.get("decision_source") is not None
                else None
            ),
            action=GuardianAssessmentAction.from_mapping(data["action"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "id": self.id,
            "turn_id": self.turn_id,
            "started_at_ms": self.started_at_ms,
            "status": self.status.value,
            "action": self.action.to_mapping(),
        }
        if self.target_item_id is not None:
            data["target_item_id"] = self.target_item_id
        if self.completed_at_ms is not None:
            data["completed_at_ms"] = self.completed_at_ms
        if self.risk_level is not None:
            data["risk_level"] = self.risk_level.value
        if self.user_authorization is not None:
            data["user_authorization"] = self.user_authorization.value
        if self.rationale is not None:
            data["rationale"] = self.rationale
        if self.decision_source is not None:
            data["decision_source"] = self.decision_source.value
        return data


@dataclass(frozen=True)
class ReviewDecision:
    type: str
    proposed_execpolicy_amendment: ExecPolicyAmendment | None = None
    network_policy_amendment: NetworkPolicyAmendment | None = None

    @property
    def kind(self) -> str:
        return self.type

    @classmethod
    def approved(cls) -> "ReviewDecision":
        return cls("approved")

    @classmethod
    def approved_execpolicy_amendment(cls, amendment: ExecPolicyAmendment) -> "ReviewDecision":
        return cls("approved_execpolicy_amendment", proposed_execpolicy_amendment=amendment)

    @classmethod
    def approved_for_session(cls) -> "ReviewDecision":
        return cls("approved_for_session")

    @classmethod
    def network_policy_amendment_decision(cls, amendment: NetworkPolicyAmendment) -> "ReviewDecision":
        return cls("network_policy_amendment", network_policy_amendment=amendment)

    @classmethod
    def denied(cls) -> "ReviewDecision":
        return cls("denied")

    @classmethod
    def timed_out(cls) -> "ReviewDecision":
        return cls("timed_out")

    @classmethod
    def abort(cls) -> "ReviewDecision":
        return cls("abort")

    @classmethod
    def default(cls) -> "ReviewDecision":
        return cls.denied()

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ReviewDecision":
        if isinstance(value, ReviewDecision):
            return value
        if isinstance(value, str):
            normalized = _camel_to_snake(value)
            simple = {
                "approved": cls.approved,
                "accept": cls.approved,
                "approved_for_session": cls.approved_for_session,
                "accept_for_session": cls.approved_for_session,
                "denied": cls.denied,
                "decline": cls.denied,
                "timed_out": cls.timed_out,
                "abort": cls.abort,
                "cancel": cls.abort,
            }.get(value)
            if simple is None:
                simple = {
                    "approved": cls.approved,
                    "accept": cls.approved,
                    "approved_for_session": cls.approved_for_session,
                    "accept_for_session": cls.approved_for_session,
                    "denied": cls.denied,
                    "decline": cls.denied,
                    "timed_out": cls.timed_out,
                    "abort": cls.abort,
                    "cancel": cls.abort,
                }.get(normalized)
            if simple is None:
                raise ValueError(f"unknown review decision: {value}")
            return simple()
        data = _mapping(value, "review decision")
        if len(data) != 1:
            raise ValueError("review decision must have exactly one variant")
        variant, payload = next(iter(data.items()))
        variant = _camel_to_snake(str(variant))
        if variant == "approved_execpolicy_amendment":
            payload_data = _mapping(payload, "approved execpolicy amendment")
            return cls.approved_execpolicy_amendment(
                ExecPolicyAmendment.from_mapping(payload_data["proposed_execpolicy_amendment"])
            )
        if variant == "accept_with_execpolicy_amendment":
            payload_data = _mapping(payload, "accept with execpolicy amendment")
            return cls.approved_execpolicy_amendment(
                ExecPolicyAmendment.from_mapping(payload_data.get("execpolicyAmendment", payload_data.get("execpolicy_amendment")))
            )
        if variant == "network_policy_amendment":
            payload_data = _mapping(payload, "network policy amendment decision")
            return cls.network_policy_amendment_decision(
                NetworkPolicyAmendment.from_mapping(payload_data["network_policy_amendment"])
            )
        if variant == "apply_network_policy_amendment":
            payload_data = _mapping(payload, "apply network policy amendment")
            return cls.network_policy_amendment_decision(
                NetworkPolicyAmendment.from_mapping(payload_data.get("networkPolicyAmendment", payload_data.get("network_policy_amendment")))
            )
        return cls.from_mapping(str(variant))

    def to_mapping(self) -> JsonValue:
        if self.type == "approved_execpolicy_amendment":
            return {
                "approved_execpolicy_amendment": {
                    "proposed_execpolicy_amendment": self.proposed_execpolicy_amendment.to_mapping()
                    if self.proposed_execpolicy_amendment is not None
                    else None
                }
            }
        if self.type == "network_policy_amendment":
            return {
                "network_policy_amendment": {
                    "network_policy_amendment": self.network_policy_amendment.to_mapping()
                    if self.network_policy_amendment is not None
                    else None
                }
            }
        return self.type

    def to_opaque_string(self) -> str:
        if self.type == "approved_execpolicy_amendment":
            return "approved_with_amendment"
        if self.type == "network_policy_amendment":
            if self.network_policy_amendment is not None and self.network_policy_amendment.action is NetworkPolicyRuleAction.ALLOW:
                return "approved_with_network_policy_allow"
            return "denied_with_network_policy_deny"
        return {
            "approved": "approved",
            "approved_for_session": "approved_for_session",
            "denied": "denied",
            "timed_out": "timed_out",
            "abort": "abort",
        }[self.type]


def command_execution_approval_decision_to_mapping(decision: ReviewDecision | JsonValue) -> JsonValue:
    decision = ReviewDecision.from_mapping(decision)
    if decision.type == "approved":
        return "accept"
    if decision.type == "approved_for_session":
        return "acceptForSession"
    if decision.type == "approved_execpolicy_amendment":
        return {
            "acceptWithExecpolicyAmendment": {
                "execpolicyAmendment": (
                    decision.proposed_execpolicy_amendment.to_mapping()
                    if decision.proposed_execpolicy_amendment is not None
                    else None
                )
            }
        }
    if decision.type == "network_policy_amendment":
        return {
            "applyNetworkPolicyAmendment": {
                "networkPolicyAmendment": (
                    decision.network_policy_amendment.to_mapping()
                    if decision.network_policy_amendment is not None
                    else None
                )
            }
        }
    if decision.type in {"denied", "timed_out"}:
        return "decline"
    if decision.type == "abort":
        return "cancel"
    raise ValueError(f"unknown review decision: {decision.type}")


def command_execution_request_approval_response(decision: ReviewDecision | JsonValue) -> dict[str, JsonValue]:
    return {"decision": command_execution_approval_decision_to_mapping(decision)}


def file_change_approval_decision_to_mapping(decision: ReviewDecision | JsonValue) -> str:
    decision = ReviewDecision.from_mapping(decision)
    if decision.type == "approved":
        return "accept"
    if decision.type == "approved_for_session":
        return "acceptForSession"
    if decision.type in {"denied", "timed_out"}:
        return "decline"
    if decision.type == "abort":
        return "cancel"
    raise ValueError(f"unsupported file change approval decision: {decision.type}")


def file_change_request_approval_response(decision: ReviewDecision | JsonValue) -> dict[str, JsonValue]:
    return {"decision": file_change_approval_decision_to_mapping(decision)}


@dataclass(frozen=True)
class ExecApprovalRequestEvent:
    call_id: str
    started_at_ms: int
    command: tuple[str, ...]
    cwd: Path
    parsed_cmd: tuple[Any, ...] = ()
    approval_id: str | None = None
    turn_id: str = ""
    reason: str | None = None
    network_approval_context: NetworkApprovalContext | None = None
    proposed_execpolicy_amendment: ExecPolicyAmendment | None = None
    proposed_network_policy_amendments: tuple[NetworkPolicyAmendment, ...] | None = None
    additional_permissions: AdditionalPermissionProfile | None = None
    available_decisions: tuple[ReviewDecision, ...] | None = None

    def effective_approval_id(self) -> str:
        return self.approval_id or self.call_id

    def effective_available_decisions(self) -> tuple[ReviewDecision, ...]:
        if self.available_decisions is not None:
            return self.available_decisions
        return self.default_available_decisions(
            network_approval_context=self.network_approval_context,
            proposed_execpolicy_amendment=self.proposed_execpolicy_amendment,
            proposed_network_policy_amendments=self.proposed_network_policy_amendments,
            additional_permissions=self.additional_permissions,
        )

    @staticmethod
    def default_available_decisions(
        network_approval_context: NetworkApprovalContext | None = None,
        proposed_execpolicy_amendment: ExecPolicyAmendment | None = None,
        proposed_network_policy_amendments: tuple[NetworkPolicyAmendment, ...] | None = None,
        additional_permissions: AdditionalPermissionProfile | None = None,
    ) -> tuple[ReviewDecision, ...]:
        if network_approval_context is not None:
            decisions = [ReviewDecision.approved(), ReviewDecision.approved_for_session()]
            allow_amendment = next(
                (
                    amendment
                    for amendment in proposed_network_policy_amendments or ()
                    if amendment.action is NetworkPolicyRuleAction.ALLOW
                ),
                None,
            )
            if allow_amendment is not None:
                decisions.append(ReviewDecision.network_policy_amendment_decision(allow_amendment))
            decisions.append(ReviewDecision.abort())
            return tuple(decisions)

        if additional_permissions is not None:
            return (ReviewDecision.approved(), ReviewDecision.abort())

        decisions = [ReviewDecision.approved()]
        if proposed_execpolicy_amendment is not None:
            decisions.append(ReviewDecision.approved_execpolicy_amendment(proposed_execpolicy_amendment))
        decisions.append(ReviewDecision.abort())
        return tuple(decisions)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ExecApprovalRequestEvent":
        data = _mapping(value, "exec approval request event")
        network_amendments = data.get("proposed_network_policy_amendments")
        available_decisions = data.get("available_decisions")
        parsed_cmd = data.get("parsed_cmd", ())
        return cls(
            call_id=_required_str(data, "call_id"),
            approval_id=_optional_str(data, "approval_id"),
            turn_id=_optional_str(data, "turn_id") or "",
            started_at_ms=_ensure_i64(data.get("started_at_ms"), "started_at_ms"),
            command=_string_tuple(data.get("command"), "command"),
            cwd=Path(_required_str(data, "cwd")),
            parsed_cmd=_parsed_command_tuple(parsed_cmd),
            reason=_optional_str(data, "reason"),
            network_approval_context=(
                NetworkApprovalContext.from_mapping(data["network_approval_context"])
                if data.get("network_approval_context") is not None
                else None
            ),
            proposed_execpolicy_amendment=(
                ExecPolicyAmendment.from_mapping(data["proposed_execpolicy_amendment"])
                if data.get("proposed_execpolicy_amendment") is not None
                else None
            ),
            proposed_network_policy_amendments=(
                tuple(NetworkPolicyAmendment.from_mapping(item) for item in _sequence(network_amendments, "proposed_network_policy_amendments"))
                if network_amendments is not None
                else None
            ),
            additional_permissions=(
                AdditionalPermissionProfile.from_mapping(data["additional_permissions"])
                if data.get("additional_permissions") is not None
                else None
            ),
            available_decisions=(
                tuple(ReviewDecision.from_mapping(item) for item in _sequence(available_decisions, "available_decisions"))
                if available_decisions is not None
                else None
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "started_at_ms": self.started_at_ms,
            "command": list(self.command),
            "cwd": str(self.cwd),
            "parsed_cmd": [_parsed_command_mapping(item) for item in self.parsed_cmd],
        }
        if self.approval_id is not None:
            data["approval_id"] = self.approval_id
        if self.reason is not None:
            data["reason"] = self.reason
        if self.network_approval_context is not None:
            data["network_approval_context"] = self.network_approval_context.to_mapping()
        if self.proposed_execpolicy_amendment is not None:
            data["proposed_execpolicy_amendment"] = self.proposed_execpolicy_amendment.to_mapping()
        if self.proposed_network_policy_amendments is not None:
            data["proposed_network_policy_amendments"] = [
                amendment.to_mapping() for amendment in self.proposed_network_policy_amendments
            ]
        if self.additional_permissions is not None:
            data["additional_permissions"] = self.additional_permissions.to_mapping()
        if self.available_decisions is not None:
            data["available_decisions"] = [decision.to_mapping() for decision in self.available_decisions]
        return data


@dataclass(frozen=True)
class ElicitationRequest:
    mode: str
    message_text: str
    requested_schema: JsonValue | None = None
    url: str | None = None
    elicitation_id: str | None = None
    meta: dict[str, Any] | None = None

    @classmethod
    def form(
        cls,
        message: str,
        requested_schema: JsonValue,
        meta: JsonValue | None = None,
    ) -> "ElicitationRequest":
        return cls(mode="form", message_text=message, requested_schema=requested_schema, meta=meta)

    @classmethod
    def url(
        cls,
        message: str,
        url: str,
        elicitation_id: str,
        meta: dict[str, Any] | None = None,
    ) -> "ElicitationRequest":
        return cls(mode="url", message_text=message, url=url, elicitation_id=elicitation_id, meta=meta)

    def message(self) -> str:
        return self.message_text

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ElicitationRequest":
        data = _mapping(value, "elicitation request")
        mode = _required_str(data, "mode")
        meta = data.get("_meta")
        if mode == "form":
            return cls.form(_required_str(data, "message"), data["requested_schema"], meta=meta)
        if mode == "url":
            return cls.url(
                _required_str(data, "message"),
                _required_str(data, "url"),
                _required_str(data, "elicitation_id"),
                meta=meta,
            )
        raise ValueError(f"unknown elicitation request mode: {mode}")

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"mode": self.mode, "message": self.message_text}
        if self.meta is not None:
            data["_meta"] = self.meta
        if self.mode == "form":
            data["requested_schema"] = self.requested_schema
        elif self.mode == "url":
            data["url"] = self.url
            data["elicitation_id"] = self.elicitation_id
        return data


@dataclass(frozen=True)
class ElicitationRequestEvent:
    server_name: str
    id: RequestId | str | int
    request: ElicitationRequest
    turn_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "id", RequestId.from_value(self.id))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ElicitationRequestEvent":
        data = _mapping(value, "elicitation request event")
        return cls(
            turn_id=data.get("turn_id") if data.get("turn_id") is not None else None,
            server_name=_required_str(data, "server_name"),
            id=RequestId.from_value(data["id"]),
            request=ElicitationRequest.from_mapping(data["request"]),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "server_name": self.server_name,
            "id": self.id.to_json(),
            "request": self.request.to_mapping(),
        }
        if self.turn_id is not None:
            data["turn_id"] = self.turn_id
        return data


class ElicitationAction(str, Enum):
    ACCEPT = "accept"
    DECLINE = "decline"
    CANCEL = "cancel"


@dataclass(frozen=True)
class FileChange:
    type: str
    content: str | None = None
    unified_diff: str | None = None
    move_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.type in {"add", "delete"}:
            if not isinstance(self.content, str):
                raise TypeError(f"{self.type} file change requires content")
            if self.unified_diff is not None or self.move_path is not None:
                raise ValueError(f"{self.type} file change cannot include update fields")
            return
        if self.type == "update":
            if not isinstance(self.unified_diff, str):
                raise TypeError("update file change requires unified_diff")
            if self.content is not None:
                raise ValueError("update file change cannot include content")
            if self.move_path is not None:
                if not isinstance(self.move_path, (str, Path)):
                    raise TypeError("move_path must be a string or Path")
                object.__setattr__(self, "move_path", Path(self.move_path))
            return
        raise ValueError(f"unknown file change type: {self.type}")

    @classmethod
    def add(cls, content: str) -> "FileChange":
        return cls(type="add", content=content)

    @classmethod
    def delete(cls, content: str) -> "FileChange":
        return cls(type="delete", content=content)

    @classmethod
    def update(cls, unified_diff: str, move_path: Path | None = None) -> "FileChange":
        return cls(type="update", unified_diff=unified_diff, move_path=move_path)


@dataclass(frozen=True)
class ApplyPatchApprovalRequestEvent:
    call_id: str
    started_at_ms: int
    changes: dict[Path, FileChange]
    turn_id: str = ""
    reason: str | None = None
    grant_root: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        object.__setattr__(self, "started_at_ms", _ensure_i64(self.started_at_ms, "started_at_ms"))
        if not isinstance(self.changes, dict):
            raise TypeError("changes must be a mapping")
        parsed_changes: dict[Path, FileChange] = {}
        for path, change in self.changes.items():
            if not isinstance(path, (str, Path)):
                raise TypeError("change paths must be strings or Path")
            if not isinstance(change, FileChange):
                raise TypeError("change values must be FileChange")
            parsed_changes[Path(path)] = change
        object.__setattr__(self, "changes", parsed_changes)
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string")
        if self.grant_root is not None:
            if not isinstance(self.grant_root, (str, Path)):
                raise TypeError("grant_root must be a string or Path")
            object.__setattr__(self, "grant_root", Path(self.grant_root))
