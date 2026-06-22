"""Local state-runtime backed agent graph store.

Python port of ``codex/codex-rs/agent-graph-store/src/local.rs``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pycodex.protocol import ThreadId
from pycodex.state import DirectionalThreadSpawnEdgeStatus, StateRuntime

from .error import AgentGraphStoreError, Internal, internal
from .types import ThreadSpawnEdgeStatus


class LocalAgentGraphStore:
    """SQLite-backed store adapter using an existing state runtime."""

    def __init__(self, state_db: StateRuntime | Any) -> None:
        self.state_db = state_db

    @classmethod
    def new(cls, state_db: StateRuntime | Any) -> "LocalAgentGraphStore":
        return cls(state_db)

    def __repr__(self) -> str:
        codex_home = _codex_home(self.state_db)
        return f"LocalAgentGraphStore(codex_home={codex_home!r}, ..)"

    async def upsert_thread_spawn_edge(
        self,
        parent_thread_id: ThreadId,
        child_thread_id: ThreadId,
        status: ThreadSpawnEdgeStatus,
    ) -> None:
        store = _thread_store(self.state_db)
        try:
            await store.upsert_thread_spawn_edge(
                parent_thread_id,
                child_thread_id,
                to_state_status(status),
            )
        except AgentGraphStoreError:
            raise
        except Exception as exc:
            raise internal_error(exc) from exc

    async def set_thread_spawn_edge_status(
        self,
        child_thread_id: ThreadId,
        status: ThreadSpawnEdgeStatus,
    ) -> None:
        store = _thread_store(self.state_db)
        try:
            await store.set_thread_spawn_edge_status(child_thread_id, to_state_status(status))
        except AgentGraphStoreError:
            raise
        except Exception as exc:
            raise internal_error(exc) from exc

    async def list_thread_spawn_children(
        self,
        parent_thread_id: ThreadId,
        status_filter: ThreadSpawnEdgeStatus | None,
    ) -> list[ThreadId]:
        store = _thread_store(self.state_db)
        try:
            if status_filter is not None:
                rows = await store.list_thread_spawn_children_with_status(
                    parent_thread_id,
                    to_state_status(status_filter),
                )
                return _thread_ids(rows)
            return list(await store.list_thread_spawn_children(parent_thread_id))
        except AgentGraphStoreError:
            raise
        except Exception as exc:
            raise internal_error(exc) from exc

    async def list_thread_spawn_descendants(
        self,
        root_thread_id: ThreadId,
        status_filter: ThreadSpawnEdgeStatus | None,
    ) -> list[ThreadId]:
        store = _thread_store(self.state_db)
        try:
            if status_filter is not None:
                rows = await store.list_thread_spawn_descendants_with_status(
                    root_thread_id,
                    to_state_status(status_filter),
                )
                return _thread_ids(rows)
            return list(await store.list_thread_spawn_descendants(root_thread_id))
        except AgentGraphStoreError:
            raise
        except Exception as exc:
            raise internal_error(exc) from exc


def to_state_status(status: ThreadSpawnEdgeStatus) -> DirectionalThreadSpawnEdgeStatus:
    """Convert the agent-graph status enum to the state-runtime status enum."""

    if not isinstance(status, ThreadSpawnEdgeStatus):
        status = ThreadSpawnEdgeStatus.from_json(status)  # type: ignore[arg-type]
    if status is ThreadSpawnEdgeStatus.Open:
        return DirectionalThreadSpawnEdgeStatus.OPEN
    if status is ThreadSpawnEdgeStatus.Closed:
        return DirectionalThreadSpawnEdgeStatus.CLOSED
    raise ValueError(f"unknown thread spawn edge status: {status}")


def internal_error(err: object) -> Internal:
    return internal(str(err))


def _thread_store(state_db: Any) -> Any:
    if all(hasattr(state_db, name) for name in _STATE_THREAD_METHODS):
        return state_db
    threads = getattr(state_db, "threads", None)
    if threads is None:
        raise internal_error("state runtime is missing thread graph methods")
    return threads


def _codex_home(state_db: Any) -> Any:
    codex_home = getattr(state_db, "codex_home", None)
    if callable(codex_home):
        return codex_home()
    return codex_home


def _thread_ids(rows: Sequence[Any]) -> list[ThreadId]:
    result: list[ThreadId] = []
    for row in rows:
        if isinstance(row, tuple):
            result.append(row[0])
        else:
            result.append(row)
    return result


_STATE_THREAD_METHODS = (
    "upsert_thread_spawn_edge",
    "set_thread_spawn_edge_status",
    "list_thread_spawn_children_with_status",
    "list_thread_spawn_children",
    "list_thread_spawn_descendants_with_status",
    "list_thread_spawn_descendants",
)


__all__ = [
    "LocalAgentGraphStore",
    "internal_error",
    "to_state_status",
]
