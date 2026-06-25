from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/hook_lifecycle.rs
# Behavior contract: ChatWidget hook lifecycle reducer for active cell creation,
# completion routing, persistent output flushing, idle finishing, visibility
# timers, and frame scheduling. Concrete HistoryCell/AppEvent rendering remains
# a neighboring runtime boundary.

from pycodex.tui.chatwidget.hook_lifecycle import ANIMATION_FRAME_DELAY_MS, HookLifecycleState, HookRun, SemanticHookCell


def test_on_hook_started_creates_active_cell_and_appends_subsequent_runs():
    state = HookLifecycleState(animations_enabled=True)

    state.on_hook_started(HookRun("hook-1"))
    state.on_hook_started(HookRun("hook-2"))

    assert [run.id for run in state.active_hook_cell.active_runs] == ["hook-1", "hook-2"]
    assert state.active_cell_revision == 2
    assert state.redraw_requested is True


def test_on_hook_started_flushes_completed_persistent_output_before_starting_new_run():
    state = HookLifecycleState()
    state.active_hook_cell = SemanticHookCell.new_completed(HookRun("old", persistent=True))

    state.on_hook_started(HookRun("new"))

    assert [run.id for run in state.inserted_history_cells[0].completed_runs] == ["old"]
    assert [run.id for run in state.active_hook_cell.active_runs] == ["new"]
    assert state.needs_final_message_separator is True


def test_on_hook_completed_existing_active_run_flushes_persistent_output_and_clears_empty_cell():
    state = HookLifecycleState()
    state.on_hook_started(HookRun("hook-1", persistent=True))

    state.on_hook_completed(HookRun("hook-1", persistent=True))

    assert state.active_hook_cell is None
    assert [run.id for run in state.inserted_history_cells[0].completed_runs] == ["hook-1"]
    assert state.needs_final_message_separator is True


def test_on_hook_completed_without_active_cell_creates_completed_cell_when_not_empty():
    state = HookLifecycleState()

    state.on_hook_completed(HookRun("hook-1", persistent=False, should_flush=False))

    assert state.active_hook_cell is not None
    assert [run.id for run in state.active_hook_cell.completed_runs] == ["hook-1"]


def test_finish_active_hook_cell_if_idle_drops_empty_or_flushes_should_flush_cell():
    state = HookLifecycleState()
    state.active_hook_cell = SemanticHookCell()

    assert state.finish_active_hook_cell_if_idle() is None
    assert state.active_hook_cell is None

    state.active_hook_cell = SemanticHookCell.new_completed(HookRun("hook-2", persistent=False, should_flush=True))
    flushed = state.finish_active_hook_cell_if_idle()

    assert flushed is not None
    assert state.active_hook_cell is None
    assert state.inserted_history_cells[-1] is flushed


def test_update_due_hook_visibility_advances_cell_and_can_finish_idle():
    state = HookLifecycleState()
    state.active_hook_cell = SemanticHookCell.new_active(
        HookRun("hook-1", visible_running=False, timer_deadline_ms=100),
    )

    state.update_due_hook_visibility(50)
    assert state.active_hook_cell.active_runs[0].visible_running is False

    state.update_due_hook_visibility(100)
    assert state.active_hook_cell.active_runs[0].visible_running is True
    assert state.active_cell_revision == 1


def test_schedule_hook_timer_if_needed_schedules_animation_and_next_deadline():
    state = HookLifecycleState(animations_enabled=True)
    state.active_hook_cell = SemanticHookCell.new_active(HookRun("hook-1", visible_running=True, timer_deadline_ms=250))

    assert state.schedule_hook_timer_if_needed(now_ms=100) == [ANIMATION_FRAME_DELAY_MS, 150]


def test_schedule_hook_timer_if_needed_saturates_past_deadline_delay():
    state = HookLifecycleState(animations_enabled=False)
    state.active_hook_cell = SemanticHookCell.new_active(HookRun("hook-1", visible_running=False, timer_deadline_ms=50))

    assert state.schedule_hook_timer_if_needed(now_ms=100) == [0]
