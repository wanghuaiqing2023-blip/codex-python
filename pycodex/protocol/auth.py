"""Authentication plan protocol helpers.

Ported from ``codex/codex-rs/protocol/src/auth.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KnownPlan(str, Enum):
    FREE = "free"
    GO = "go"
    PLUS = "plus"
    PRO = "pro"
    PRO_LITE = "prolite"
    TEAM = "team"
    SELF_SERVE_BUSINESS_USAGE_BASED = "self_serve_business_usage_based"
    BUSINESS = "business"
    ENTERPRISE_CBP_USAGE_BASED = "enterprise_cbp_usage_based"
    ENTERPRISE = "enterprise"
    EDU = "edu"

    def display_name(self) -> str:
        return {
            KnownPlan.FREE: "Free",
            KnownPlan.GO: "Go",
            KnownPlan.PLUS: "Plus",
            KnownPlan.PRO: "Pro",
            KnownPlan.PRO_LITE: "Pro Lite",
            KnownPlan.TEAM: "Team",
            KnownPlan.SELF_SERVE_BUSINESS_USAGE_BASED: "Self Serve Business Usage Based",
            KnownPlan.BUSINESS: "Business",
            KnownPlan.ENTERPRISE_CBP_USAGE_BASED: "Enterprise CBP Usage Based",
            KnownPlan.ENTERPRISE: "Enterprise",
            KnownPlan.EDU: "Edu",
        }[self]

    def raw_value(self) -> str:
        return str(self.value)

    def is_workspace_account(self) -> bool:
        return self in {
            KnownPlan.TEAM,
            KnownPlan.SELF_SERVE_BUSINESS_USAGE_BASED,
            KnownPlan.BUSINESS,
            KnownPlan.ENTERPRISE_CBP_USAGE_BASED,
            KnownPlan.ENTERPRISE,
            KnownPlan.EDU,
        }


@dataclass(frozen=True)
class PlanType:
    known: KnownPlan | None = None
    unknown: str | None = None

    @classmethod
    def from_raw_value(cls, raw: str) -> "PlanType":
        normalized = raw.lower()
        aliases = {
            "education": KnownPlan.EDU,
            "edu": KnownPlan.EDU,
            "hc": KnownPlan.ENTERPRISE,
            "enterprise": KnownPlan.ENTERPRISE,
        }
        if normalized in aliases:
            return cls(known=aliases[normalized])
        try:
            return cls(known=KnownPlan(normalized))
        except ValueError:
            return cls(unknown=raw)

    @classmethod
    def known_plan(cls, plan: KnownPlan) -> "PlanType":
        return cls(known=plan)

    @classmethod
    def unknown_plan(cls, raw: str) -> "PlanType":
        return cls(unknown=raw)

    def is_known(self) -> bool:
        return self.known is not None


class RefreshTokenFailedReason(str, Enum):
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"
    REVOKED = "revoked"
    OTHER = "other"


class RefreshTokenFailedError(Exception):
    def __init__(self, reason: RefreshTokenFailedReason, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message
