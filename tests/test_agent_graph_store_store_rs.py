from __future__ import annotations

import inspect

import pytest

from pycodex.agent_graph_store import (
    REQUIRED_AGENT_GRAPH_STORE_METHODS,
    AgentGraphStore,
    ThreadSpawnEdgeStatus,
    validate_agent_graph_store,
)
from pycodex.protocol import ThreadId


class MemoryAgentGraphStore:
    def __init__(self) -> None:
        self.children: dict[ThreadId, list[tuple[ThreadId, ThreadSpawnEdgeStatus]]] = {}

    async def upsert_thread_spawn_edge(
        self,
        parent_thread_id: ThreadId,
        child_thread_id: ThreadId,
        status: ThreadSpawnEdgeStatus,
    ) -> None:
        siblings = self.children.setdefault(parent_thread_id, [])
        self.children[parent_thread_id] = [
            (child, edge_status) for child, edge_status in siblings if child != child_thread_id
        ]
        self.children[parent_thread_id].append((child_thread_id, status))

    async def set_thread_spawn_edge_status(
        self,
        child_thread_id: ThreadId,
        status: ThreadSpawnEdgeStatus,
    ) -> None:
        for parent, siblings in list(self.children.items()):
            self.children[parent] = [
                (child, status if child == child_thread_id else edge_status)
                for child, edge_status in siblings
            ]

    async def list_thread_spawn_children(
        self,
        parent_thread_id: ThreadId,
        status_filter: ThreadSpawnEdgeStatus | None,
    ) -> list[ThreadId]:
        siblings = self.children.get(parent_thread_id, [])
        return [
            child
            for child, status in siblings
            if status_filter is None or status is status_filter
        ]

    async def list_thread_spawn_descendants(
        self,
        root_thread_id: ThreadId,
        status_filter: ThreadSpawnEdgeStatus | None,
    ) -> list[ThreadId]:
        del status_filter
        return [child for child, _status in self.children.get(root_thread_id, [])]


def test_agent_graph_store_protocol_lists_required_async_methods():
    # Rust crate/module: codex-agent-graph-store src/store.rs. Behavior
    # contract: the trait has four async methods.
    assert REQUIRED_AGENT_GRAPH_STORE_METHODS == (
        "upsert_thread_spawn_edge",
        "set_thread_spawn_edge_status",
        "list_thread_spawn_children",
        "list_thread_spawn_descendants",
    )
    for method_name in REQUIRED_AGENT_GRAPH_STORE_METHODS:
        assert inspect.iscoroutinefunction(getattr(AgentGraphStore, method_name))


def test_validate_agent_graph_store_accepts_async_implementation():
    # Rust source contract: implementers provide the async graph store boundary.
    store = MemoryAgentGraphStore()

    assert validate_agent_graph_store(store) is store
    assert isinstance(store, AgentGraphStore)


def test_validate_agent_graph_store_rejects_missing_or_sync_methods():
    class Missing:
        pass

    class SyncMethod:
        def upsert_thread_spawn_edge(self, parent_thread_id, child_thread_id, status):
            pass

        async def set_thread_spawn_edge_status(self, child_thread_id, status):
            pass

        async def list_thread_spawn_children(self, parent_thread_id, status_filter):
            return []

        async def list_thread_spawn_descendants(self, root_thread_id, status_filter):
            return []

    with pytest.raises(TypeError, match="missing method"):
        validate_agent_graph_store(Missing())
    with pytest.raises(TypeError, match="must be async"):
        validate_agent_graph_store(SyncMethod())
