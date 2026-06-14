"""Agent-turn lifecycle state for ``codex-tui::chatwidget::turn_lifecycle``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/turn_lifecycle.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::turn_lifecycle",
    source="codex/codex-rs/tui/src/chatwidget/turn_lifecycle.rs",
)


@dataclass
class SleepInhibitor:
    """Semantic stand-in for Rust ``SleepInhibitor`` used by this module."""

    prevent_idle_sleep: bool
    turn_running: bool = False

    def set_turn_running(self, turn_running: bool) -> None:
        self.turn_running = bool(turn_running)

    def is_turn_running(self) -> bool:
        return self.turn_running


@dataclass
class TurnLifecycleState:
    sleep_inhibitor: SleepInhibitor
    agent_turn_running: bool = False
    last_turn_id: str | None = None
    budget_limited_turn_ids: set[str] = field(default_factory=set)
    goal_status_active_turn_started_at: Any | None = None

    @classmethod
    def new(cls, prevent_idle_sleep: bool) -> "TurnLifecycleState":
        return cls(sleep_inhibitor=SleepInhibitor(bool(prevent_idle_sleep)))

    def start(self, now: Any) -> None:
        self.agent_turn_running = True
        self.goal_status_active_turn_started_at = now
        self.sleep_inhibitor.set_turn_running(True)

    def finish(self) -> None:
        self.agent_turn_running = False
        self.goal_status_active_turn_started_at = None
        self.sleep_inhibitor.set_turn_running(False)

    def restore_running(self, running: bool, now: Any) -> None:
        self.agent_turn_running = bool(running)
        self.goal_status_active_turn_started_at = now if running else None
        self.sleep_inhibitor.set_turn_running(running)

    def reset_thread(self) -> None:
        self.finish()
        self.last_turn_id = None
        self.budget_limited_turn_ids.clear()

    def set_prevent_idle_sleep(self, enabled: bool) -> None:
        self.sleep_inhibitor = SleepInhibitor(bool(enabled))
        self.sleep_inhibitor.set_turn_running(self.agent_turn_running)

    def mark_budget_limited(self, turn_id: str) -> None:
        self.budget_limited_turn_ids.add(turn_id)

    def take_budget_limited(self, turn_id: str) -> bool:
        if turn_id not in self.budget_limited_turn_ids:
            return False
        self.budget_limited_turn_ids.remove(turn_id)
        return True


__all__ = [
    "RUST_MODULE",
    "SleepInhibitor",
    "TurnLifecycleState",
]
