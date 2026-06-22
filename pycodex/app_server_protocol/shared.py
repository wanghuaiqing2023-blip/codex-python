"""Shared v2 protocol types ported from ``protocol/v2/shared.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc

    def to_mapping(self) -> str:
        return self.value

    def to_camel_mapping(self) -> str:
        return self.value


def default_enabled() -> bool:
    return True


class NonSteerableTurnKind(_StringEnum):
    REVIEW = "review"
    COMPACT = "compact"


@dataclass(frozen=True)
class CodexErrorInfo:
    type: str
    http_status_code: int | None = None
    turn_kind: NonSteerableTurnKind | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", _ensure_error_type(self.type))
        object.__setattr__(self, "http_status_code", _optional_u16(self.http_status_code, "http_status_code"))
        if self.turn_kind is not None:
            object.__setattr__(self, "turn_kind", NonSteerableTurnKind.parse(self.turn_kind))

    @classmethod
    def context_window_exceeded(cls) -> "CodexErrorInfo":
        return cls("context_window_exceeded")

    @classmethod
    def usage_limit_exceeded(cls) -> "CodexErrorInfo":
        return cls("usage_limit_exceeded")

    @classmethod
    def server_overloaded(cls) -> "CodexErrorInfo":
        return cls("server_overloaded")

    @classmethod
    def cyber_policy(cls) -> "CodexErrorInfo":
        return cls("cyber_policy")

    @classmethod
    def http_connection_failed(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("http_connection_failed", http_status_code=http_status_code)

    @classmethod
    def response_stream_connection_failed(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("response_stream_connection_failed", http_status_code=http_status_code)

    @classmethod
    def internal_server_error(cls) -> "CodexErrorInfo":
        return cls("internal_server_error")

    @classmethod
    def unauthorized(cls) -> "CodexErrorInfo":
        return cls("unauthorized")

    @classmethod
    def bad_request(cls) -> "CodexErrorInfo":
        return cls("bad_request")

    @classmethod
    def thread_rollback_failed(cls) -> "CodexErrorInfo":
        return cls("thread_rollback_failed")

    @classmethod
    def sandbox_error(cls) -> "CodexErrorInfo":
        return cls("sandbox_error")

    @classmethod
    def response_stream_disconnected(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("response_stream_disconnected", http_status_code=http_status_code)

    @classmethod
    def response_too_many_failed_attempts(cls, http_status_code: int | None = None) -> "CodexErrorInfo":
        return cls("response_too_many_failed_attempts", http_status_code=http_status_code)

    @classmethod
    def active_turn_not_steerable(cls, turn_kind: NonSteerableTurnKind | str) -> "CodexErrorInfo":
        return cls("active_turn_not_steerable", turn_kind=turn_kind)

    @classmethod
    def other(cls) -> "CodexErrorInfo":
        return cls("other")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "CodexErrorInfo":
        if isinstance(value, CodexErrorInfo):
            return value
        if isinstance(value, str):
            return cls(_camel_to_snake(value))
        data = _mapping(value, "CodexErrorInfo")
        if len(data) != 1:
            raise ValueError("CodexErrorInfo must have exactly one variant")
        raw_variant, payload = next(iter(data.items()))
        variant = _camel_to_snake(str(raw_variant))
        if variant in _HTTP_ERROR_VARIANTS:
            payload_data = _mapping(payload or {}, variant)
            status = payload_data.get("http_status_code", payload_data.get("httpStatusCode"))
            return cls(variant, http_status_code=_optional_u16(status, "http_status_code"))
        if variant == "active_turn_not_steerable":
            payload_data = _mapping(payload or {}, variant)
            turn_kind = payload_data.get("turn_kind", payload_data.get("turnKind"))
            return cls.active_turn_not_steerable(NonSteerableTurnKind.parse(turn_kind))
        return cls(variant)

    def affects_turn_status(self) -> bool:
        return self.type not in {"thread_rollback_failed", "active_turn_not_steerable"}

    def to_mapping(self) -> JsonValue:
        return self.to_camel_mapping()

    def to_camel_mapping(self) -> JsonValue:
        variant = _snake_to_camel(self.type)
        if self.type in _HTTP_ERROR_VARIANTS:
            return {variant: {"httpStatusCode": self.http_status_code}}
        if self.type == "active_turn_not_steerable":
            if self.turn_kind is None:
                raise ValueError("active_turn_not_steerable requires turn_kind")
            return {variant: {"turnKind": self.turn_kind.value}}
        return variant


class AskForApproval(_StringEnum):
    UNLESS_TRUSTED = "untrusted"
    ON_FAILURE = "on-failure"
    ON_REQUEST = "on-request"
    NEVER = "never"

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "AskForApproval | GranularAskForApproval":
        if isinstance(value, (AskForApproval, GranularAskForApproval)):
            return value
        if isinstance(value, str):
            return cls.parse(value)
        data = _mapping(value, "AskForApproval")
        if len(data) == 1 and "granular" in data:
            return GranularAskForApproval.from_mapping(data["granular"])
        raise ValueError("AskForApproval must be a string or {'granular': {...}}")

    @classmethod
    def default(cls) -> "AskForApproval":
        return cls.ON_REQUEST


@dataclass(frozen=True)
class GranularAskForApproval:
    sandbox_approval: bool
    rules: bool
    mcp_elicitations: bool
    skill_approval: bool = False
    request_permissions: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "sandbox_approval", _ensure_bool(self.sandbox_approval, "sandbox_approval"))
        object.__setattr__(self, "rules", _ensure_bool(self.rules, "rules"))
        object.__setattr__(self, "skill_approval", _ensure_bool(self.skill_approval, "skill_approval"))
        object.__setattr__(
            self,
            "request_permissions",
            _ensure_bool(self.request_permissions, "request_permissions"),
        )
        object.__setattr__(self, "mcp_elicitations", _ensure_bool(self.mcp_elicitations, "mcp_elicitations"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GranularAskForApproval":
        data = _mapping(value, "GranularAskForApproval")
        return cls(
            sandbox_approval=_ensure_bool(data["sandbox_approval"], "sandbox_approval"),
            rules=_ensure_bool(data["rules"], "rules"),
            skill_approval=_ensure_bool(data.get("skill_approval", False), "skill_approval"),
            request_permissions=_ensure_bool(data.get("request_permissions", False), "request_permissions"),
            mcp_elicitations=_ensure_bool(data["mcp_elicitations"], "mcp_elicitations"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "granular": {
                "sandbox_approval": self.sandbox_approval,
                "rules": self.rules,
                "skill_approval": self.skill_approval,
                "request_permissions": self.request_permissions,
                "mcp_elicitations": self.mcp_elicitations,
            }
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


class ApprovalsReviewer(_StringEnum):
    USER = "user"
    AUTO_REVIEW = "guardian_subagent"

    @classmethod
    def parse(cls, value: JsonValue) -> "ApprovalsReviewer":
        raw = getattr(value, "value", value)
        if raw == "auto_review":
            return cls.AUTO_REVIEW
        return super().parse(raw)

    @classmethod
    def default(cls) -> "ApprovalsReviewer":
        return cls.USER


class SandboxMode(_StringEnum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


_HTTP_ERROR_VARIANTS = {
    "http_connection_failed",
    "response_stream_connection_failed",
    "response_stream_disconnected",
    "response_too_many_failed_attempts",
}

_ERROR_TYPES = {
    "context_window_exceeded",
    "usage_limit_exceeded",
    "server_overloaded",
    "cyber_policy",
    "http_connection_failed",
    "response_stream_connection_failed",
    "internal_server_error",
    "unauthorized",
    "bad_request",
    "thread_rollback_failed",
    "sandbox_error",
    "response_stream_disconnected",
    "response_too_many_failed_attempts",
    "active_turn_not_steerable",
    "other",
}


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_u16(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**16 - 1:
        raise TypeError(f"{field_name} must be an unsigned 16-bit integer or None")
    return value


def _ensure_error_type(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("CodexErrorInfo type must be a string")
    normalized = _camel_to_snake(value)
    if normalized not in _ERROR_TYPES:
        choices = ", ".join(sorted(_ERROR_TYPES))
        raise ValueError(f"invalid CodexErrorInfo type: {value}; expected one of: {choices}")
    return normalized


def _camel_to_snake(value: str) -> str:
    if "_" in value or "-" in value:
        return value
    chars: list[str] = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            chars.append("_")
        chars.append(char.lower())
    return "".join(chars)


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


__all__ = [
    "ApprovalsReviewer",
    "AskForApproval",
    "CodexErrorInfo",
    "GranularAskForApproval",
    "NonSteerableTurnKind",
    "SandboxMode",
    "default_enabled",
]
