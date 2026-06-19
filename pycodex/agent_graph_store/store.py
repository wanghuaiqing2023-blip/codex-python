"""Storage-neutral agent graph store interface.

Python port of ``codex/codex-rs/agent-graph-store/src/store.rs``.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pycodex.protocol import ThreadId

from .types import ThreadSpawnEdgeStatus


@runtime_checkable
class AgentGraphStore(Protocol):
    """Storage-neutral boundary for persisted thread-spawn parent/child topology."""

    async def upsert_thread_spawn_edge(
        self,
        parent_thread_id: ThreadId,
        child_thread_id: ThreadId,
        status: ThreadSpawnEdgeStatus,
    ) -> None:
        """Insert or replace a directional parent/child edge."""

    async def set_thread_spawn_edge_status(
        self,
        child_thread_id: ThreadId,
        status: ThreadSpawnEdgeStatus,
    ) -> None:
        """Update a spawned thread's incoming edge lifecycle status."""

    async def list_thread_spawn_children(
        self,
        parent_thread_id: ThreadId,
        status_filter: ThreadSpawnEdgeStatus | None,
    ) -> Sequence[ThreadId]:
        """List direct spawned children with optional status filtering."""

    async def list_thread_spawn_descendants(
        self,
        root_thread_id: ThreadId,
        status_filter: ThreadSpawnEdgeStatus | None,
    ) -> Sequence[ThreadId]:
        """List spawned descendants breadth-first by depth, then by thread id."""


REQUIRED_AGENT_GRAPH_STORE_METHODS = (
    "upsert_thread_spawn_edge",
    "set_thread_spawn_edge_status",
    "list_thread_spawn_children",
    "list_thread_spawn_descendants",
)


def validate_agent_graph_store(value: object) -> AgentGraphStore:
    """Return ``value`` after verifying that it exposes async store methods."""

    for method_name in REQUIRED_AGENT_GRAPH_STORE_METHODS:
        method = getattr(value, method_name, None)
        if method is None or not callable(method):
            raise TypeError(f"agent graph store is missing method: {method_name}")
        if not inspect.iscoroutinefunction(method):
            raise TypeError(f"agent graph store method must be async: {method_name}")
    return value  # type: ignore[return-value]


__all__ = [
    "AgentGraphStore",
    "REQUIRED_AGENT_GRAPH_STORE_METHODS",
    "validate_agent_graph_store",
]
