"""Multi-agent session helpers aligned with ``codex-rs/core/src/session/multi_agents.rs``."""

from __future__ import annotations

from typing import Any

from pycodex.features import Feature
from pycodex.protocol import SessionSource


def usage_hint_text(turn_context: Any, session_source: SessionSource) -> str | None:
    features = getattr(turn_context, "features", None)
    enabled = getattr(features, "enabled", None)
    if not callable(enabled) or not enabled(Feature.MULTI_AGENT_V2):
        return None

    config = getattr(turn_context, "config", None)
    multi_agent_v2 = getattr(config, "multi_agent_v2", None)
    if multi_agent_v2 is None:
        return None

    if session_source.type == "subagent":
        subagent_source = session_source.subagent_source
        if subagent_source is not None and subagent_source.type == "thread_spawn":
            return getattr(multi_agent_v2, "subagent_usage_hint_text", None)
        return None

    if session_source.type in {"cli", "vscode", "exec", "mcp", "custom", "unknown"}:
        return getattr(multi_agent_v2, "root_agent_usage_hint_text", None)

    return None


__all__ = ["usage_hint_text"]
