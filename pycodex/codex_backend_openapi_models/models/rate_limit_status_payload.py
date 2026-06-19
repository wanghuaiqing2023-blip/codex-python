"""Port of Rust ``codex-backend-openapi-models::models::rate_limit_status_payload``.

Rust source:
- ``codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_payload.rs``
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .additional_rate_limit_details import AdditionalRateLimitDetails, UNSET, Unset
from .credit_status_details import CreditStatusDetails
from .rate_limit_status_details import RateLimitStatusDetails


class RateLimitReachedKind(str, Enum):
    RATE_LIMIT_REACHED = "rate_limit_reached"
    WORKSPACE_OWNER_CREDITS_DEPLETED = "workspace_owner_credits_depleted"
    WORKSPACE_MEMBER_CREDITS_DEPLETED = "workspace_member_credits_depleted"
    WORKSPACE_OWNER_USAGE_LIMIT_REACHED = "workspace_owner_usage_limit_reached"
    WORKSPACE_MEMBER_USAGE_LIMIT_REACHED = "workspace_member_usage_limit_reached"
    UNKNOWN = "unknown"

    @classmethod
    def from_raw_value(cls, value: str) -> "RateLimitReachedKind":
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


class PlanType(str, Enum):
    GUEST = "guest"
    FREE = "free"
    GO = "go"
    PLUS = "plus"
    PRO = "pro"
    PRO_LITE = "prolite"
    FREE_WORKSPACE = "free_workspace"
    TEAM = "team"
    SELF_SERVE_BUSINESS_USAGE_BASED = "self_serve_business_usage_based"
    BUSINESS = "business"
    ENTERPRISE_CBP_USAGE_BASED = "enterprise_cbp_usage_based"
    EDUCATION = "education"
    QUORUM = "quorum"
    K12 = "k12"
    ENTERPRISE = "enterprise"
    EDU = "edu"
    UNKNOWN = "unknown"

    @classmethod
    def from_raw_value(cls, value: str) -> "PlanType":
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN


@dataclass(frozen=True)
class RateLimitReachedType:
    kind: RateLimitReachedKind

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RateLimitReachedType":
        raw = value.get("type", RateLimitReachedKind.UNKNOWN.value)
        if not isinstance(raw, str):
            raise TypeError("expected string")
        return cls(kind=RateLimitReachedKind.from_raw_value(raw))

    def to_json_dict(self) -> dict[str, str]:
        return {"type": self.kind.value}


@dataclass(frozen=True)
class RateLimitStatusPayload:
    plan_type: PlanType = PlanType.GUEST
    rate_limit: RateLimitStatusDetails | None | Unset = UNSET
    credits: CreditStatusDetails | None | Unset = UNSET
    additional_rate_limits: tuple[AdditionalRateLimitDetails, ...] | None | Unset = UNSET
    rate_limit_reached_type: RateLimitReachedType | None | Unset = UNSET

    @classmethod
    def new(cls, plan_type: PlanType | str) -> "RateLimitStatusPayload":
        return cls(plan_type=_coerce_plan_type(plan_type))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "RateLimitStatusPayload":
        return cls(
            plan_type=_decode_plan_type(value.get("plan_type", PlanType.GUEST.value)),
            rate_limit=_decode_rate_limit_double_option(value, "rate_limit"),
            credits=_decode_credits_double_option(value, "credits"),
            additional_rate_limits=_decode_additional_rate_limits_double_option(value, "additional_rate_limits"),
            rate_limit_reached_type=_decode_reached_type_double_option(value, "rate_limit_reached_type"),
        )

    def to_json_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"plan_type": self.plan_type.value}
        if not isinstance(self.rate_limit, Unset):
            result["rate_limit"] = _json_value(self.rate_limit)
        if not isinstance(self.credits, Unset):
            result["credits"] = _json_value(self.credits)
        if not isinstance(self.additional_rate_limits, Unset):
            result["additional_rate_limits"] = _additional_rate_limits_to_json(self.additional_rate_limits)
        if not isinstance(self.rate_limit_reached_type, Unset):
            result["rate_limit_reached_type"] = _json_value(self.rate_limit_reached_type)
        return result


def _decode_plan_type(value: Any) -> PlanType:
    if not isinstance(value, str):
        raise TypeError("expected string")
    return PlanType.from_raw_value(value)


def _coerce_plan_type(value: PlanType | str) -> PlanType:
    if isinstance(value, PlanType):
        return value
    return _decode_plan_type(value)


def _decode_rate_limit_double_option(value: Mapping[str, Any], key: str) -> RateLimitStatusDetails | None | Unset:
    raw = _decode_double_option(value, key)
    if raw is None or isinstance(raw, Unset) or isinstance(raw, RateLimitStatusDetails):
        return raw
    if isinstance(raw, Mapping):
        return RateLimitStatusDetails.from_mapping(raw)
    raise TypeError("expected rate limit status object or null")


def _decode_credits_double_option(value: Mapping[str, Any], key: str) -> CreditStatusDetails | None | Unset:
    raw = _decode_double_option(value, key)
    if raw is None or isinstance(raw, Unset) or isinstance(raw, CreditStatusDetails):
        return raw
    if isinstance(raw, Mapping):
        return CreditStatusDetails.from_mapping(raw)
    raise TypeError("expected credit status object or null")


def _decode_additional_rate_limits_double_option(
    value: Mapping[str, Any],
    key: str,
) -> tuple[AdditionalRateLimitDetails, ...] | None | Unset:
    raw = _decode_double_option(value, key)
    if raw is None or isinstance(raw, Unset):
        return raw
    if not isinstance(raw, list):
        raise TypeError("expected additional rate limits array or null")
    return tuple(
        item if isinstance(item, AdditionalRateLimitDetails) else AdditionalRateLimitDetails.from_mapping(_expect_mapping(item))
        for item in raw
    )


def _decode_reached_type_double_option(value: Mapping[str, Any], key: str) -> RateLimitReachedType | None | Unset:
    raw = _decode_double_option(value, key)
    if raw is None or isinstance(raw, Unset) or isinstance(raw, RateLimitReachedType):
        return raw
    if isinstance(raw, Mapping):
        return RateLimitReachedType.from_mapping(raw)
    raise TypeError("expected rate limit reached type object or null")


def _decode_double_option(value: Mapping[str, Any], key: str) -> Any | None | Unset:
    if key not in value:
        return UNSET
    return value[key]


def _additional_rate_limits_to_json(value: tuple[AdditionalRateLimitDetails, ...] | None) -> list[dict[str, Any]] | None:
    if value is None:
        return None
    return [item.to_json_dict() for item in value]


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "to_json_dict"):
        return value.to_json_dict()
    return value


def _expect_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise TypeError("expected object")


__all__ = [
    "PlanType",
    "RateLimitReachedKind",
    "RateLimitReachedType",
    "RateLimitStatusPayload",
]
