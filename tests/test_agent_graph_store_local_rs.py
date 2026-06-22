from __future__ import annotations

import asyncio

import pytest

from pycodex.agent_graph_store import (
    AgentGraphStoreError,
    LocalAgentGraphStore,
    ThreadSpawnEdgeStatus,
    to_state_status,
)
from pycodex.protocol import ThreadId
from pycodex.state import DirectionalThreadSpawnEdgeStatus


def _run(coro):
    return asyncio.run(coro)


def _thread_id(value: int) -> ThreadId:
    return ThreadId.from_string(f"00000000-0000-0000-0000-{value:012d}")


class FakeThreadStore:
    def __init__(self) -> None:
        self.children: dict[ThreadId, list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]] = {}
        self.calls: list[tuple[str, object | None]] = []

    async def upsert_thread_spawn_edge(
        self,
        parent_thread_id: ThreadId,
        child_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus,
    ) -> None:
        siblings = [
            (child, edge_status)
            for child, edge_status in self.children.get(parent_thread_id, [])
            if child != child_thread_id
        ]
        siblings.append((child_thread_id, status))
        self.children[parent_thread_id] = siblings

    async def set_thread_spawn_edge_status(
        self,
        child_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus,
    ) -> bool:
        for parent, siblings in list(self.children.items()):
            self.children[parent] = [
                (child, status if child == child_thread_id else edge_status)
                for child, edge_status in siblings
            ]
        return True

    async def list_thread_spawn_children_with_status(
        self,
        parent_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus,
    ) -> list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]:
        self.calls.append(("children_with_status", status))
        return [
            (child, edge_status)
            for child, edge_status in sorted(
                self.children.get(parent_thread_id, []),
                key=lambda item: str(item[0]),
            )
            if edge_status is status
        ]

    async def list_thread_spawn_children(self, parent_thread_id: ThreadId) -> list[ThreadId]:
        self.calls.append(("children", None))
        return [
            child
            for child, _status in sorted(
                self.children.get(parent_thread_id, []),
                key=lambda item: str(item[0]),
            )
        ]

    async def list_thread_spawn_descendants_with_status(
        self,
        root_thread_id: ThreadId,
        status: DirectionalThreadSpawnEdgeStatus,
    ) -> list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]:
        self.calls.append(("descendants_with_status", status))
        return self._descendant_rows(root_thread_id, status)

    async def list_thread_spawn_descendants(self, root_thread_id: ThreadId) -> list[ThreadId]:
        self.calls.append(("descendants", None))
        return [child for child, _status in self._descendant_rows(root_thread_id)]

    def _descendant_rows(
        self,
        root_thread_id: ThreadId,
        status_filter: DirectionalThreadSpawnEdgeStatus | None = None,
    ) -> list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]]:
        results: list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]] = []
        parents = [root_thread_id]
        while parents:
            depth_rows: list[tuple[ThreadId, DirectionalThreadSpawnEdgeStatus]] = []
            for parent in parents:
                for child, edge_status in self.children.get(parent, []):
                    if status_filter is None or edge_status is status_filter:
                        depth_rows.append((child, edge_status))
            depth_rows.sort(key=lambda item: str(item[0]))
            results.extend(depth_rows)
            parents = [child for child, _status in depth_rows]
        return results


class FakeStateRuntime:
    def __init__(self) -> None:
        self.threads = FakeThreadStore()

    def codex_home(self) -> str:
        return "/tmp/codex-home"


def test_to_state_status_maps_agent_graph_status_to_state_status():
    # Rust crate/module: codex-agent-graph-store src/local.rs::to_state_status.
    assert to_state_status(ThreadSpawnEdgeStatus.Open) is DirectionalThreadSpawnEdgeStatus.OPEN
    assert to_state_status(ThreadSpawnEdgeStatus.Closed) is DirectionalThreadSpawnEdgeStatus.CLOSED
    assert to_state_status("open") is DirectionalThreadSpawnEdgeStatus.OPEN


def test_local_store_upserts_and_lists_direct_children_with_status_filters():
    # Rust test: local_store_upserts_and_lists_direct_children_with_status_filters.
    runtime = FakeStateRuntime()
    store = LocalAgentGraphStore.new(runtime)
    parent = _thread_id(1)
    first_child = _thread_id(2)
    second_child = _thread_id(3)

    _run(store.upsert_thread_spawn_edge(parent, second_child, ThreadSpawnEdgeStatus.Closed))
    _run(store.upsert_thread_spawn_edge(parent, first_child, ThreadSpawnEdgeStatus.Open))

    assert _run(store.list_thread_spawn_children(parent, None)) == [first_child, second_child]
    assert _run(store.list_thread_spawn_children(parent, ThreadSpawnEdgeStatus.Open)) == [first_child]
    assert _run(store.list_thread_spawn_children(parent, ThreadSpawnEdgeStatus.Closed)) == [second_child]
    assert ("children_with_status", DirectionalThreadSpawnEdgeStatus.OPEN) in runtime.threads.calls


def test_local_store_updates_edge_status():
    # Rust test: local_store_updates_edge_status.
    runtime = FakeStateRuntime()
    store = LocalAgentGraphStore(runtime)
    parent = _thread_id(10)
    child = _thread_id(11)

    _run(store.upsert_thread_spawn_edge(parent, child, ThreadSpawnEdgeStatus.Open))
    _run(store.set_thread_spawn_edge_status(child, ThreadSpawnEdgeStatus.Closed))

    assert _run(store.list_thread_spawn_children(parent, ThreadSpawnEdgeStatus.Open)) == []
    assert _run(store.list_thread_spawn_children(parent, ThreadSpawnEdgeStatus.Closed)) == [child]


def test_local_store_lists_descendants_breadth_first_with_status_filters():
    # Rust test: local_store_lists_descendants_breadth_first_with_status_filters.
    runtime = FakeStateRuntime()
    store = LocalAgentGraphStore(runtime)
    root = _thread_id(20)
    earlier_child = _thread_id(21)
    later_child = _thread_id(22)
    closed_grandchild = _thread_id(23)
    open_grandchild = _thread_id(24)
    closed_child = _thread_id(25)
    closed_great_grandchild = _thread_id(26)

    for parent, child, status in [
        (root, later_child, ThreadSpawnEdgeStatus.Open),
        (root, earlier_child, ThreadSpawnEdgeStatus.Open),
        (earlier_child, open_grandchild, ThreadSpawnEdgeStatus.Open),
        (later_child, closed_grandchild, ThreadSpawnEdgeStatus.Closed),
        (root, closed_child, ThreadSpawnEdgeStatus.Closed),
        (closed_child, closed_great_grandchild, ThreadSpawnEdgeStatus.Closed),
    ]:
        _run(store.upsert_thread_spawn_edge(parent, child, status))

    assert _run(store.list_thread_spawn_descendants(root, None)) == [
        earlier_child,
        later_child,
        closed_child,
        closed_grandchild,
        open_grandchild,
        closed_great_grandchild,
    ]
    assert _run(store.list_thread_spawn_descendants(root, ThreadSpawnEdgeStatus.Open)) == [
        earlier_child,
        later_child,
        open_grandchild,
    ]
    assert _run(store.list_thread_spawn_descendants(root, ThreadSpawnEdgeStatus.Closed)) == [
        closed_child,
        closed_great_grandchild,
    ]
    assert (
        "descendants_with_status",
        DirectionalThreadSpawnEdgeStatus.CLOSED,
    ) in runtime.threads.calls


def test_local_store_wraps_state_errors_as_internal_errors():
    class FailingThreads(FakeThreadStore):
        async def list_thread_spawn_children(self, parent_thread_id: ThreadId) -> list[ThreadId]:
            raise RuntimeError("boom")

    runtime = FakeStateRuntime()
    runtime.threads = FailingThreads()

    with pytest.raises(AgentGraphStoreError, match="agent graph store internal error: boom"):
        _run(LocalAgentGraphStore(runtime).list_thread_spawn_children(_thread_id(30), None))
