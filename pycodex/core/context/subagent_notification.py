from __future__ import annotations

import json
from dataclasses import dataclass

from pycodex.protocol import AgentStatus

from .fragment import ContextualUserFragmentBase


@dataclass(frozen=True)
class SubagentNotification(ContextualUserFragmentBase):
    agent_reference: str
    status: AgentStatus

    @classmethod
    def new(cls, agent_reference: str, status: AgentStatus) -> "SubagentNotification":
        return cls(agent_reference, status)

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "<subagent_notification>", "</subagent_notification>"

    def body(self) -> str:
        payload = {"agent_path": self.agent_reference, "status": self.status.to_mapping()}
        return f"\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n"


__all__ = ["SubagentNotification"]
