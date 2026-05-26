"""Model-visible session prefix helpers ported from ``core/src/session_prefix.rs``."""

from __future__ import annotations

from pycodex.protocol import AgentStatus

from .context import SubagentNotification


def format_subagent_notification_message(
    agent_reference: str,
    status: AgentStatus | str | dict[str, object],
) -> str:
    parsed_status = AgentStatus.from_mapping(status)
    return SubagentNotification.new(str(agent_reference), parsed_status).render()


def format_subagent_context_line(agent_reference: str, agent_nickname: str | None) -> str:
    if agent_nickname is not None and agent_nickname != "":
        return f"- {agent_reference}: {agent_nickname}"
    return f"- {agent_reference}"


__all__ = [
    "format_subagent_context_line",
    "format_subagent_notification_message",
]
