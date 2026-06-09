"""Agent module namespace aligned with ``codex-rs/core/src/agent/mod.rs``."""

from __future__ import annotations

from pycodex.protocol import AgentStatus

from .control import AgentControl, ListedAgent, LiveAgent, SpawnAgentForkMode, SpawnAgentOptions
from .registry import exceeds_thread_spawn_depth_limit, next_thread_spawn_depth
from .status import agent_status_from_event

__all__ = [
    "AgentControl",
    "AgentStatus",
    "ListedAgent",
    "LiveAgent",
    "SpawnAgentForkMode",
    "SpawnAgentOptions",
    "agent_status_from_event",
    "exceeds_thread_spawn_depth_limit",
    "next_thread_spawn_depth",
]
