"""Model-visible session prefix helpers ported from ``core/src/session_prefix.rs``."""

from __future__ import annotations

from pycodex.protocol import AgentStatus

from .context import SubagentNotification


def format_subagent_notification_message(
    agent_reference: str,
    status: AgentStatus,
) -> str:
    if not isinstance(agent_reference, str):
        raise TypeError("agent_reference must be a string")
    if not isinstance(status, AgentStatus):
        raise TypeError("status must be an AgentStatus")
    return SubagentNotification.new(agent_reference, status).render()


def format_subagent_context_line(agent_reference: str, agent_nickname: str | None) -> str:
    if not isinstance(agent_reference, str):
        raise TypeError("agent_reference must be a string")
    if agent_nickname is not None and not isinstance(agent_nickname, str):
        raise TypeError("agent_nickname must be a string or None")
    if agent_nickname is not None and agent_nickname != "":
        return f"- {agent_reference}: {agent_nickname}"
    return f"- {agent_reference}"


__all__ = [
    "format_subagent_context_line",
    "format_subagent_notification_message",
]
