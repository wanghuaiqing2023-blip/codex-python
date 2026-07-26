from __future__ import annotations

from dataclasses import dataclass

from pycodex.protocol import NetworkPolicyAmendment, NetworkPolicyRuleAction

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class NetworkRuleSaved(ContextualUserFragmentBase):
    action: NetworkPolicyRuleAction
    host: str

    def __post_init__(self) -> None:
        if not isinstance(self.action, NetworkPolicyRuleAction):
            object.__setattr__(self, "action", NetworkPolicyRuleAction(str(self.action)))

    @classmethod
    def new(cls, amendment: NetworkPolicyAmendment) -> "NetworkRuleSaved":
        return cls(amendment.action, amendment.host)

    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        action, list_name = (
            ("Allowed", "allowlist")
            if self.action is NetworkPolicyRuleAction.ALLOW
            else ("Denied", "denylist")
        )
        return f"{action} network rule saved in execpolicy ({list_name}): {self.host}"


__all__ = ["NetworkRuleSaved"]
