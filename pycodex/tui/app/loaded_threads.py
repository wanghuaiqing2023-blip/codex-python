"""Loaded subagent thread discovery helpers for the TUI app.

Rust counterpart: ``codex-rs/tui/src/app/loaded_threads.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from uuid import UUID

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    path="app/loaded_threads.rs",
    status="complete",
    notes=(
        "Ports the pure subagent spawn-tree discovery helper. Python uses "
        "JSON-like semantic session-source data instead of Rust SessionSource."
    ),
)


@dataclass(frozen=True, order=True)
class LoadedSubagentThread:
    """A subagent thread loaded below a primary thread."""

    thread_id: str
    agent_nickname: str | None = None
    agent_role: str | None = None


@dataclass(frozen=True)
class Thread:
    """Minimal semantic model for the Rust ``codex_core::protocol::Thread``."""

    id: str
    source: Any
    agent_nickname: str | None = None
    agent_role: str | None = None


def _canonical_thread_id(value: Any) -> str | None:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _field_any(value: Any, names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        item = _field(value, name, default)
        if item is not default:
            return item
    return default


def _coerce_thread(value: Any) -> Thread | None:
    thread_id = _canonical_thread_id(_field(value, "id"))
    if thread_id is None:
        return None
    return Thread(
        id=thread_id,
        source=_field(value, "source"),
        agent_nickname=_field(value, "agent_nickname"),
        agent_role=_field(value, "agent_role"),
    )


def thread_spawn_parent_thread_id(source: Any) -> str | None:
    """Return the parent thread id from a subagent thread-spawn source.

    Rust serializes ``SessionSource`` and reads
    ``subAgent.thread_spawn.parent_thread_id``. The Python port accepts that
    JSON shape directly, plus snake/camel aliases for local semantic models.
    Invalid or missing ids are ignored, matching Rust's ``Option`` boundary.
    """

    sub_agent = _field_any(source, ("subAgent", "sub_agent"))
    if sub_agent is None:
        return None
    thread_spawn = _field_any(sub_agent, ("thread_spawn", "threadSpawn"))
    if thread_spawn is None:
        return None
    return _canonical_thread_id(_field(thread_spawn, "parent_thread_id"))


def find_loaded_subagent_threads_for_primary(
    threads: Iterable[Any], primary_thread_id: Any
) -> list[LoadedSubagentThread]:
    """Find all loaded subagent descendants for ``primary_thread_id``.

    The traversal mirrors the Rust implementation: invalid thread ids are
    skipped, spawn-parent edges are followed transitively, each child thread is
    included once, and the final list is sorted by thread id string.
    """

    primary = _canonical_thread_id(primary_thread_id)
    if primary is None:
        return []

    threads_by_id: dict[str, Thread] = {}
    for item in threads:
        thread = _coerce_thread(item)
        if thread is not None:
            threads_by_id[thread.id] = thread

    included: set[str] = set()
    pending = [primary]
    while pending:
        parent = pending.pop()
        for thread_id, thread in threads_by_id.items():
            if thread_id == primary or thread_id in included:
                continue
            if thread_spawn_parent_thread_id(thread.source) == parent:
                included.add(thread_id)
                pending.append(thread_id)

    return sorted(
        (
            LoadedSubagentThread(
                thread_id=thread_id,
                agent_nickname=threads_by_id[thread_id].agent_nickname,
                agent_role=threads_by_id[thread_id].agent_role,
            )
            for thread_id in included
        ),
        key=lambda item: item.thread_id,
    )


def test_thread(
    thread_id: Any,
    source: Any,
    agent_nickname: str | None = None,
    agent_role: str | None = None,
) -> Thread:
    """Build the minimal thread fixture used by the Rust module tests."""

    canonical = _canonical_thread_id(thread_id)
    if canonical is None:
        raise ValueError(f"invalid thread id: {thread_id!r}")
    return Thread(
        id=canonical,
        source=source,
        agent_nickname=agent_nickname,
        agent_role=agent_role,
    )


def thread_spawn_source(
    parent_thread_id: Any,
    *,
    depth: int = 1,
    agent_nickname: str = "",
    agent_role: str = "",
) -> dict[str, Any]:
    """Build a JSON-like ``SessionSource::SubAgent`` spawn source."""

    parent = _canonical_thread_id(parent_thread_id)
    if parent is None:
        raise ValueError(f"invalid parent thread id: {parent_thread_id!r}")
    return {
        "subAgent": {
            "thread_spawn": {
                "parent_thread_id": parent,
                "depth": depth,
                "agent_nickname": agent_nickname,
                "agent_role": agent_role,
            }
        }
    }


def finds_loaded_subagent_tree_for_primary_thread() -> bool:
    """Executable Python copy of the Rust unit test's behavior contract."""

    primary = "00000000-0000-0000-0000-000000000001"
    child = "00000000-0000-0000-0000-000000000002"
    grandchild = "00000000-0000-0000-0000-000000000003"
    unrelated_parent = "00000000-0000-0000-0000-000000000004"
    unrelated_child = "00000000-0000-0000-0000-000000000005"

    threads = [
        test_thread(primary, {"cli": {}}),
        test_thread(child, thread_spawn_source(primary), "Scout", "explorer"),
        test_thread(grandchild, thread_spawn_source(child), "Atlas", "worker"),
        test_thread(
            unrelated_child,
            thread_spawn_source(unrelated_parent),
            "Other",
            "observer",
        ),
    ]

    return find_loaded_subagent_threads_for_primary(threads, primary) == [
        LoadedSubagentThread(child, "Scout", "explorer"),
        LoadedSubagentThread(grandchild, "Atlas", "worker"),
    ]


__all__ = [
    "LoadedSubagentThread",
    "RUST_MODULE",
    "Thread",
    "find_loaded_subagent_threads_for_primary",
    "finds_loaded_subagent_tree_for_primary_thread",
    "test_thread",
    "thread_spawn_parent_thread_id",
    "thread_spawn_source",
]
