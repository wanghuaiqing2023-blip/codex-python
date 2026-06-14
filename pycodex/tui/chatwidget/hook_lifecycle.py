"""Hook lifecycle reducer for ``codex-tui::chatwidget::hook_lifecycle``.

Rust wires these operations into ``ChatWidget`` and ``history_cell::HookCell``.
Python keeps the module-local lifecycle decisions as a semantic state model:
active hook cell creation, completion routing, persistent completed-output flush,
idle finishing, and timer scheduling data.  Concrete history-cell rendering,
AppEvent transport, and frame requester side effects remain runtime boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::hook_lifecycle",
    source="codex/codex-rs/tui/src/chatwidget/hook_lifecycle.rs",
)

ANIMATION_FRAME_DELAY_MS = 50


@dataclass(frozen=True)
class HookRun:
    id: str
    persistent: bool = True
    visible_running: bool = True
    timer_deadline_ms: int | None = None
    should_flush: bool = False


@dataclass
class SemanticHookCell:
    active_runs: list[HookRun] = field(default_factory=list)
    completed_runs: list[HookRun] = field(default_factory=list)
    completed_persistent_runs: list[HookRun] = field(default_factory=list)
    flush_when_idle: bool = False
    animations_enabled: bool = False

    @classmethod
    def new_active(cls, run: Any, animations_enabled: bool = False) -> "SemanticHookCell":
        cell = cls(animations_enabled=animations_enabled)
        cell.start_run(run)
        return cell

    @classmethod
    def new_completed(cls, run: Any, animations_enabled: bool = False) -> "SemanticHookCell":
        cell = cls(animations_enabled=animations_enabled)
        cell.add_completed_run(run)
        return cell

    def start_run(self, run: Any) -> None:
        self.active_runs.append(_coerce_run(run))

    def complete_run(self, completed: Any) -> bool:
        run = _coerce_run(completed)
        for idx, active in enumerate(self.active_runs):
            if active.id == run.id:
                del self.active_runs[idx]
                self.add_completed_run(run)
                return True
        return False

    def add_completed_run(self, completed: Any) -> None:
        run = _coerce_run(completed)
        self.completed_runs.append(run)
        if run.persistent:
            self.completed_persistent_runs.append(run)
        if run.should_flush:
            self.flush_when_idle = True

    def take_completed_persistent_runs(self) -> "SemanticHookCell | None":
        if not self.completed_persistent_runs:
            return None
        cell = SemanticHookCell(
            completed_runs=list(self.completed_persistent_runs),
            flush_when_idle=True,
            animations_enabled=self.animations_enabled,
        )
        self.completed_persistent_runs.clear()
        return cell

    def is_empty(self) -> bool:
        return not self.active_runs and not self.completed_runs and not self.completed_persistent_runs

    def should_flush(self) -> bool:
        return self.flush_when_idle and not self.active_runs

    def has_visible_running_run(self) -> bool:
        return any(run.visible_running for run in self.active_runs)

    def advance_time(self, now_ms: int) -> bool:
        changed = False
        updated: list[HookRun] = []
        for run in self.active_runs:
            if run.timer_deadline_ms is not None and run.timer_deadline_ms <= now_ms and not run.visible_running:
                updated.append(_replace_run(run, visible_running=True, timer_deadline_ms=None))
                changed = True
            else:
                updated.append(run)
        self.active_runs = updated
        return changed

    def next_timer_deadline(self) -> int | None:
        deadlines = [run.timer_deadline_ms for run in self.active_runs if run.timer_deadline_ms is not None]
        return min(deadlines) if deadlines else None


@dataclass
class HookLifecycleState:
    animations_enabled: bool = False
    active_hook_cell: SemanticHookCell | None = None
    inserted_history_cells: list[SemanticHookCell] = field(default_factory=list)
    active_cell_revision: int = 0
    redraw_requested: bool = False
    needs_final_message_separator: bool = False
    scheduled_frame_delays_ms: list[int] = field(default_factory=list)

    def on_hook_started(self, run: Any) -> None:
        self.flush_completed_hook_output()
        if self.active_hook_cell is not None:
            self.active_hook_cell.start_run(run)
        else:
            self.active_hook_cell = SemanticHookCell.new_active(run, self.animations_enabled)
        self.bump_active_cell_revision()
        self.request_redraw()

    def on_hook_completed(self, completed: Any) -> None:
        completed_existing_run = False
        if self.active_hook_cell is not None:
            completed_existing_run = self.active_hook_cell.complete_run(completed)
        if completed_existing_run:
            self.bump_active_cell_revision()
        elif self.active_hook_cell is not None:
            self.active_hook_cell.add_completed_run(completed)
            self.bump_active_cell_revision()
        else:
            cell = SemanticHookCell.new_completed(completed, self.animations_enabled)
            if not cell.is_empty():
                self.active_hook_cell = cell
                self.bump_active_cell_revision()
        self.flush_completed_hook_output()
        self.finish_active_hook_cell_if_idle()
        self.request_redraw()

    def flush_completed_hook_output(self) -> SemanticHookCell | None:
        if self.active_hook_cell is None:
            return None
        completed_cell = self.active_hook_cell.take_completed_persistent_runs()
        if completed_cell is None:
            return None
        if self.active_hook_cell.is_empty():
            self.active_hook_cell = None
        self.bump_active_cell_revision()
        self.needs_final_message_separator = True
        self.inserted_history_cells.append(completed_cell)
        return completed_cell

    def finish_active_hook_cell_if_idle(self) -> SemanticHookCell | None:
        cell = self.active_hook_cell
        if cell is None:
            return None
        if cell.is_empty():
            self.active_hook_cell = None
            self.bump_active_cell_revision()
            return None
        if cell.should_flush():
            self.active_hook_cell = None
            self.bump_active_cell_revision()
            self.needs_final_message_separator = True
            self.inserted_history_cells.append(cell)
            return cell
        return None

    def update_due_hook_visibility(self, now_ms: int) -> None:
        if self.active_hook_cell is None:
            return
        if self.active_hook_cell.advance_time(now_ms):
            self.bump_active_cell_revision()
        self.finish_active_hook_cell_if_idle()

    def schedule_hook_timer_if_needed(self, now_ms: int = 0) -> list[int]:
        if self.animations_enabled and self.active_hook_cell is not None and self.active_hook_cell.has_visible_running_run():
            self.scheduled_frame_delays_ms.append(ANIMATION_FRAME_DELAY_MS)
        deadline = self.active_hook_cell.next_timer_deadline() if self.active_hook_cell is not None else None
        if deadline is not None:
            self.scheduled_frame_delays_ms.append(max(int(deadline) - int(now_ms), 0))
        return list(self.scheduled_frame_delays_ms)

    def bump_active_cell_revision(self) -> None:
        self.active_cell_revision += 1

    def request_redraw(self) -> None:
        self.redraw_requested = True


def _coerce_run(value: Any) -> HookRun:
    if isinstance(value, HookRun):
        return value
    if isinstance(value, dict):
        get = value.get
    else:
        get = lambda name, default=None: getattr(value, name, default)
    run_id = get("id", None) or get("run_id", None) or get("name", None)
    if run_id is None:
        raise ValueError("hook run must expose id, run_id, or name")
    return HookRun(
        id=str(run_id),
        persistent=bool(get("persistent", True)),
        visible_running=bool(get("visible_running", True)),
        timer_deadline_ms=get("timer_deadline_ms", None),
        should_flush=bool(get("should_flush", False)),
    )


def _replace_run(run: HookRun, **changes: Any) -> HookRun:
    values = {
        "id": run.id,
        "persistent": run.persistent,
        "visible_running": run.visible_running,
        "timer_deadline_ms": run.timer_deadline_ms,
        "should_flush": run.should_flush,
    }
    values.update(changes)
    return HookRun(**values)


__all__ = [
    "ANIMATION_FRAME_DELAY_MS",
    "HookLifecycleState",
    "HookRun",
    "RUST_MODULE",
    "SemanticHookCell",
]
