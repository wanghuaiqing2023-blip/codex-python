"""Account protocol helpers.

Ported from ``codex/codex-rs/protocol/src/account.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .auth import KnownPlan
from .auth import PlanType as AuthPlanType


class PlanType(str, Enum):
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
    UNKNOWN = "unknown"

    @classmethod
    def default(cls) -> "PlanType":
        return cls.FREE

    @classmethod
    def parse(cls, raw: str) -> "PlanType":
        try:
            return cls(raw.lower())
        except ValueError:
            return cls.UNKNOWN

    def to_json(self) -> str:
        return str(self.value)

    def is_team_like(self) -> bool:
        return self in {PlanType.TEAM, PlanType.SELF_SERVE_BUSINESS_USAGE_BASED}

    def is_business_like(self) -> bool:
        return self in {PlanType.BUSINESS, PlanType.ENTERPRISE_CBP_USAGE_BASED}

    def is_workspace_account(self) -> bool:
        return self in {
            PlanType.TEAM,
            PlanType.SELF_SERVE_BUSINESS_USAGE_BASED,
            PlanType.BUSINESS,
            PlanType.ENTERPRISE_CBP_USAGE_BASED,
            PlanType.ENTERPRISE,
            PlanType.EDU,
        }

    @classmethod
    def from_auth_plan_type(cls, plan_type: AuthPlanType) -> "PlanType":
        if plan_type.known is None:
            return cls.UNKNOWN
        return cls.from_known_plan(plan_type.known)

    @classmethod
    def from_known_plan(cls, plan: KnownPlan) -> "PlanType":
        return cls(plan.raw_value())


@dataclass(frozen=True)
class ProviderAccount:
    kind: str
    email: str | None = None
    plan_type: PlanType | None = None

    @classmethod
    def api_key(cls) -> "ProviderAccount":
        return cls(kind="api_key")

    @classmethod
    def chatgpt(cls, email: str, plan_type: PlanType) -> "ProviderAccount":
        return cls(kind="chatgpt", email=email, plan_type=plan_type)

    @classmethod
    def amazon_bedrock(cls) -> "ProviderAccount":
        return cls(kind="amazon_bedrock")
