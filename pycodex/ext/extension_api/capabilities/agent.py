"""Agent-spawn capability owned by ``codex-extension-api::capabilities::agent``."""

from __future__ import annotations

from typing import Any, Awaitable, Protocol, TypeVar


T = TypeVar("T")
AgentSpawnFuture = Awaitable[T]


class AgentSpawner(Protocol):
    def spawn_subagent(
        self,
        forked_from_thread_id: Any,
        request: Any,
    ) -> AgentSpawnFuture[Any]: ...


__all__ = ["AgentSpawnFuture", "AgentSpawner"]
