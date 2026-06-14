"""Multi-agent picker navigation and labeling state.

Rust counterpart: ``codex-rs/tui/src/app/agent_navigation.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from uuid import UUID

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::agent_navigation",
    source="codex/codex-rs/tui/src/app/agent_navigation.rs",
    status="complete",
)


@dataclass(frozen=True)
class AgentPickerThreadEntry:
    agent_nickname: str | None = None
    agent_role: str | None = None
    is_closed: bool = False


class AgentNavigationDirection(Enum):
    Previous = "previous"
    Next = "next"


def _thread_id(value: Any) -> str:
    return str(UUID(str(value)))


def format_agent_picker_item_name(
    agent_nickname: str | None,
    agent_role: str | None,
    is_primary: bool,
) -> str:
    if is_primary:
        return "Main [default]"
    if agent_nickname is not None and agent_role is not None:
        return f"{agent_nickname} [{agent_role}]"
    if agent_nickname is not None:
        return agent_nickname
    if agent_role is not None:
        return f"[{agent_role}]"
    return "Agent"


def previous_agent_shortcut() -> str:
    return "Alt+Left"


def next_agent_shortcut() -> str:
    return "Alt+Right"


@dataclass
class AgentNavigationState:
    """Stable first-seen traversal cache for agent picker rows."""

    threads: dict[str, AgentPickerThreadEntry] = field(default_factory=dict)
    order: list[str] = field(default_factory=list)

    def get(self, thread_id: Any) -> AgentPickerThreadEntry | None:
        try:
            key = _thread_id(thread_id)
        except (TypeError, ValueError, AttributeError):
            return None
        return self.threads.get(key)

    def is_empty(self) -> bool:
        return not self.threads

    def upsert(
        self,
        thread_id: Any,
        agent_nickname: str | None = None,
        agent_role: str | None = None,
        is_closed: bool = False,
    ) -> None:
        key = _thread_id(thread_id)
        if key not in self.threads:
            self.order.append(key)
        self.threads[key] = AgentPickerThreadEntry(
            agent_nickname=agent_nickname,
            agent_role=agent_role,
            is_closed=is_closed,
        )

    def mark_closed(self, thread_id: Any) -> None:
        key = _thread_id(thread_id)
        entry = self.threads.get(key)
        if entry is None:
            self.upsert(key, None, None, True)
            return
        self.threads[key] = AgentPickerThreadEntry(
            agent_nickname=entry.agent_nickname,
            agent_role=entry.agent_role,
            is_closed=True,
        )

    def clear(self) -> None:
        self.threads.clear()
        self.order.clear()

    def remove(self, thread_id: Any) -> None:
        key = _thread_id(thread_id)
        self.threads.pop(key, None)
        self.order = [candidate for candidate in self.order if candidate != key]

    def has_non_primary_thread(self, primary_thread_id: Any | None) -> bool:
        primary = None if primary_thread_id is None else _thread_id(primary_thread_id)
        return any(thread_id != primary for thread_id in self.threads)

    def ordered_threads(self) -> list[tuple[str, AgentPickerThreadEntry]]:
        return [
            (thread_id, self.threads[thread_id])
            for thread_id in self.order
            if thread_id in self.threads
        ]

    def tracked_thread_ids(self) -> list[str]:
        return [thread_id for thread_id, _ in self.ordered_threads()]

    def adjacent_thread_id(
        self,
        current_displayed_thread_id: Any | None,
        direction: AgentNavigationDirection,
    ) -> str | None:
        ordered = self.ordered_threads()
        if len(ordered) < 2 or current_displayed_thread_id is None:
            return None

        current = _thread_id(current_displayed_thread_id)
        ids = [thread_id for thread_id, _ in ordered]
        try:
            current_idx = ids.index(current)
        except ValueError:
            return None

        if direction is AgentNavigationDirection.Next:
            next_idx = (current_idx + 1) % len(ids)
        else:
            next_idx = len(ids) - 1 if current_idx == 0 else current_idx - 1
        return ids[next_idx]

    def active_agent_label(
        self,
        current_displayed_thread_id: Any | None,
        primary_thread_id: Any | None,
    ) -> str | None:
        if len(self.threads) <= 1 or current_displayed_thread_id is None:
            return None

        thread_id = _thread_id(current_displayed_thread_id)
        primary = None if primary_thread_id is None else _thread_id(primary_thread_id)
        is_primary = primary == thread_id
        entry = self.threads.get(thread_id)
        if entry is None:
            return format_agent_picker_item_name(None, None, is_primary)
        return format_agent_picker_item_name(
            entry.agent_nickname,
            entry.agent_role,
            is_primary,
        )

    @staticmethod
    def picker_subtitle() -> str:
        return (
            "Select an agent to watch. "
            f"{previous_agent_shortcut()} previous, {next_agent_shortcut()} next."
        )

    def ordered_thread_ids(self) -> list[str]:
        return self.tracked_thread_ids()


def populated_state() -> tuple[AgentNavigationState, str, str, str]:
    state = AgentNavigationState()
    main_thread_id = "00000000-0000-0000-0000-000000000101"
    first_agent_id = "00000000-0000-0000-0000-000000000102"
    second_agent_id = "00000000-0000-0000-0000-000000000103"

    state.upsert(main_thread_id)
    state.upsert(first_agent_id, "Robie", "explorer", False)
    state.upsert(second_agent_id, "Bob", "worker", False)
    return state, main_thread_id, first_agent_id, second_agent_id


def upsert_preserves_first_seen_order() -> bool:
    state, main_thread_id, first_agent_id, second_agent_id = populated_state()
    state.upsert(first_agent_id, "Robie", "worker", True)
    return state.ordered_thread_ids() == [
        main_thread_id,
        first_agent_id,
        second_agent_id,
    ]


def adjacent_thread_id_wraps_in_spawn_order() -> bool:
    state, main_thread_id, first_agent_id, second_agent_id = populated_state()
    return (
        state.adjacent_thread_id(second_agent_id, AgentNavigationDirection.Next)
        == main_thread_id
        and state.adjacent_thread_id(second_agent_id, AgentNavigationDirection.Previous)
        == first_agent_id
        and state.adjacent_thread_id(main_thread_id, AgentNavigationDirection.Previous)
        == second_agent_id
    )


def picker_subtitle_mentions_shortcuts() -> bool:
    subtitle = AgentNavigationState.picker_subtitle()
    return previous_agent_shortcut() in subtitle and next_agent_shortcut() in subtitle


def active_agent_label_tracks_current_thread() -> bool:
    state, main_thread_id, first_agent_id, _ = populated_state()
    return (
        state.active_agent_label(first_agent_id, main_thread_id)
        == "Robie [explorer]"
        and state.active_agent_label(main_thread_id, main_thread_id)
        == "Main [default]"
    )


__all__ = [
    "AgentNavigationDirection",
    "AgentNavigationState",
    "AgentPickerThreadEntry",
    "RUST_MODULE",
    "active_agent_label_tracks_current_thread",
    "adjacent_thread_id_wraps_in_spawn_order",
    "format_agent_picker_item_name",
    "next_agent_shortcut",
    "picker_subtitle_mentions_shortcuts",
    "populated_state",
    "previous_agent_shortcut",
    "upsert_preserves_first_seen_order",
]
