"""Agent registry helpers ported from ``core/src/agent/registry.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import Iterable

from pycodex.protocol import AgentPath, SessionSource, SubAgentSource, ThreadId
from pycodex.protocol.error import CodexErr

from .agent_roles import format_agent_nickname


I32_MAX = 2_147_483_647


@dataclass
class AgentMetadata:
    agent_id: ThreadId | None = None
    agent_path: AgentPath | None = None
    agent_nickname: str | None = None
    agent_role: str | None = None
    last_task_message: str | None = None

    def __post_init__(self) -> None:
        if self.agent_id is not None and not isinstance(self.agent_id, ThreadId):
            self.agent_id = ThreadId.from_string(str(self.agent_id))
        if self.agent_path is not None and not isinstance(self.agent_path, AgentPath):
            self.agent_path = AgentPath.from_string(str(self.agent_path))


def session_depth(session_source: SessionSource) -> int:
    """Return the nesting depth recorded on a thread-spawn session source."""

    if (
        session_source.type == "subagent"
        and isinstance(session_source.subagent_source, SubAgentSource)
        and session_source.subagent_source.type == "thread_spawn"
    ):
        return int(session_source.subagent_source.depth or 0)
    return 0


def next_thread_spawn_depth(session_source: SessionSource) -> int:
    """Return the depth that should be assigned to a spawned child thread."""

    depth = session_depth(session_source)
    return I32_MAX if depth >= I32_MAX else depth + 1


def exceeds_thread_spawn_depth_limit(depth: int, max_depth: int) -> bool:
    """Return whether a proposed spawn depth exceeds the configured limit."""

    return depth > max_depth


class AgentRegistry:
    """Track active sub-agents, spawn limits, nicknames, and agent paths."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._agent_tree: dict[str, AgentMetadata] = {}
        self._used_agent_nicknames: set[str] = set()
        self._nickname_reset_count = 0
        self._total_count = 0

    @property
    def total_count(self) -> int:
        with self._lock:
            return self._total_count

    @property
    def nickname_reset_count(self) -> int:
        with self._lock:
            return self._nickname_reset_count

    @property
    def used_agent_nicknames(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._used_agent_nicknames)

    def reserve_spawn_slot(self, max_threads: int | None = None) -> "SpawnReservation":
        with self._lock:
            if max_threads is not None and self._total_count >= max_threads:
                raise CodexErr.agent_limit_reached(max_threads)
            self._total_count += 1
        return SpawnReservation(self)

    def release_spawned_thread(self, thread_id: ThreadId) -> None:
        with self._lock:
            removed_key: str | None = None
            for key, metadata in self._agent_tree.items():
                if metadata.agent_id == thread_id:
                    removed_key = key
                    break
            if removed_key is None:
                return

            metadata = self._agent_tree.pop(removed_key)
            removed_counted_agent = not (metadata.agent_path is not None and metadata.agent_path.is_root())
            if removed_counted_agent and self._total_count > 0:
                self._total_count -= 1

    def register_root_thread(self, thread_id: ThreadId) -> None:
        with self._lock:
            self._agent_tree.setdefault(
                AgentPath.ROOT,
                AgentMetadata(agent_id=thread_id, agent_path=AgentPath.root()),
            )

    def agent_id_for_path(self, agent_path: AgentPath | str) -> ThreadId | None:
        path = agent_path if isinstance(agent_path, AgentPath) else AgentPath.from_string(str(agent_path))
        with self._lock:
            metadata = self._agent_tree.get(path.as_str())
            return metadata.agent_id if metadata is not None else None

    def agent_metadata_for_thread(self, thread_id: ThreadId) -> AgentMetadata | None:
        with self._lock:
            for metadata in self._agent_tree.values():
                if metadata.agent_id == thread_id:
                    return AgentMetadata(**metadata.__dict__)
        return None

    def live_agents(self) -> list[AgentMetadata]:
        with self._lock:
            return [
                AgentMetadata(**metadata.__dict__)
                for metadata in self._agent_tree.values()
                if metadata.agent_id is not None
                and not (metadata.agent_path is not None and metadata.agent_path.is_root())
            ]

    def update_last_task_message(self, thread_id: ThreadId, last_task_message: str) -> None:
        with self._lock:
            for metadata in self._agent_tree.values():
                if metadata.agent_id == thread_id:
                    metadata.last_task_message = last_task_message
                    return

    def _register_spawned_thread(self, agent_metadata: AgentMetadata) -> None:
        if agent_metadata.agent_id is None:
            return
        with self._lock:
            key = (
                agent_metadata.agent_path.as_str()
                if agent_metadata.agent_path is not None
                else f"thread:{agent_metadata.agent_id}"
            )
            if agent_metadata.agent_nickname is not None:
                self._used_agent_nicknames.add(agent_metadata.agent_nickname)
            self._agent_tree[key] = agent_metadata

    def _reserve_agent_nickname(self, names: Iterable[str], preferred: str | None = None) -> str | None:
        with self._lock:
            if preferred is not None:
                agent_nickname = preferred
            else:
                names_tuple = tuple(names)
                if not names_tuple:
                    return None
                available_names = [
                    format_agent_nickname(name, self._nickname_reset_count)
                    for name in names_tuple
                    if format_agent_nickname(name, self._nickname_reset_count) not in self._used_agent_nicknames
                ]
                if available_names:
                    agent_nickname = available_names[0]
                else:
                    self._used_agent_nicknames.clear()
                    self._nickname_reset_count += 1
                    agent_nickname = format_agent_nickname(names_tuple[0], self._nickname_reset_count)
            self._used_agent_nicknames.add(agent_nickname)
            return agent_nickname

    def _reserve_agent_path(self, agent_path: AgentPath) -> None:
        with self._lock:
            key = agent_path.as_str()
            if key in self._agent_tree:
                raise CodexErr.unsupported_operation(f"agent path `{agent_path}` already exists")
            self._agent_tree[key] = AgentMetadata(agent_path=agent_path)

    def _release_reserved_agent_path(self, agent_path: AgentPath) -> None:
        with self._lock:
            metadata = self._agent_tree.get(agent_path.as_str())
            if metadata is not None and metadata.agent_id is None:
                self._agent_tree.pop(agent_path.as_str(), None)

    def _release_spawn_slot(self) -> None:
        with self._lock:
            if self._total_count > 0:
                self._total_count -= 1


class SpawnReservation:
    """A reserved spawn slot that rolls back if it is not committed."""

    def __init__(self, state: AgentRegistry) -> None:
        self._state = state
        self._active = True
        self._reserved_agent_nickname: str | None = None
        self._reserved_agent_path: AgentPath | None = None

    @property
    def active(self) -> bool:
        return self._active

    def reserve_agent_nickname_with_preference(
        self,
        names: Iterable[str],
        preferred: str | None = None,
    ) -> str:
        agent_nickname = self._state._reserve_agent_nickname(names, preferred)
        if agent_nickname is None:
            raise CodexErr.unsupported_operation("no available agent nicknames")
        self._reserved_agent_nickname = agent_nickname
        return agent_nickname

    def reserve_agent_path(self, agent_path: AgentPath | str) -> None:
        path = agent_path if isinstance(agent_path, AgentPath) else AgentPath.from_string(str(agent_path))
        self._state._reserve_agent_path(path)
        self._reserved_agent_path = path

    def commit(self, agent_metadata: AgentMetadata) -> None:
        self._reserved_agent_nickname = None
        self._reserved_agent_path = None
        self._state._register_spawned_thread(agent_metadata)
        self._active = False

    def release(self) -> None:
        if not self._active:
            return
        if self._reserved_agent_path is not None:
            self._state._release_reserved_agent_path(self._reserved_agent_path)
            self._reserved_agent_path = None
        self._state._release_spawn_slot()
        self._active = False

    def __enter__(self) -> "SpawnReservation":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()

    def __del__(self) -> None:  # pragma: no cover - exercised implicitly by CPython refcounts.
        self.release()


__all__ = [
    "AgentMetadata",
    "AgentRegistry",
    "SpawnReservation",
    "exceeds_thread_spawn_depth_limit",
    "next_thread_spawn_depth",
    "session_depth",
]
