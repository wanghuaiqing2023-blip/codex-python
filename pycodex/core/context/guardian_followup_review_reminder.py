from __future__ import annotations

from .fragment import ContextualUserFragmentBase


class GuardianFollowupReviewReminder(ContextualUserFragmentBase):
    @classmethod
    def role(cls) -> str:
        return "developer"

    def body(self) -> str:
        return (
            "Use prior reviews as context, not binding precedent. "
            "Follow the Workspace Policy. "
            "If the user explicitly approves a previously rejected action after being informed of the "
            'concrete risks, set outcome to "allow" unless the policy explicitly disallows user '
            "overwrites in such cases."
        )


__all__ = ["GuardianFollowupReviewReminder"]
