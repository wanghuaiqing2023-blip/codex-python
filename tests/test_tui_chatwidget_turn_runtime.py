"""Parity tests for Rust ``codex-tui::chatwidget::turn_runtime``.

Rust source: ``codex/codex-rs/tui/src/chatwidget/turn_runtime.rs``.
"""

from pycodex.tui.chatwidget.turn_runtime import (
    ChatWidgetTurnRuntime,
    ModeKind,
    PlanItem,
    RuntimeMetricsSummary,
    StepStatus,
    TokenUsageInfo,
    TurnAbortReason,
    UpdatePlanArgs,
    interrupted_turn_message,
)


def test_update_task_running_state_derives_from_turn_or_mcp_startup() -> None:
    runtime = ChatWidgetTurnRuntime()

    runtime.update_task_running_state()
    assert runtime.bottom_pane.task_running is False

    runtime.turn_lifecycle.start("now")
    runtime.update_task_running_state()
    assert runtime.bottom_pane.task_running is True

    runtime.turn_lifecycle.finish()
    runtime.mcp_startup_status = object()
    runtime.update_task_running_state()
    assert runtime.bottom_pane.task_running is True
    assert runtime.plan_mode_nudge_refreshes == 3
    assert runtime.status_surface_refreshes == 3


def test_on_task_started_resets_turn_state_and_marks_working() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.input_queue.user_turn_pending_start = True
    runtime.status_state.retry_status_header = "Retrying"
    runtime.status_state.pending_status_indicator_restore = True
    runtime.full_reasoning_buffer.append("full")
    runtime.reasoning_buffer.append("summary")
    runtime.active_hook_cell = object()

    runtime.on_task_started()

    assert runtime.input_queue.user_turn_pending_start is False
    assert runtime.turn_lifecycle.agent_turn_running is True
    assert runtime.bottom_pane.task_running is True
    assert runtime.bottom_pane.quit_shortcut_hint_cleared is True
    assert runtime.bottom_pane.interrupt_hint_visible is True
    assert runtime.status_state.retry_status_header is None
    assert runtime.status_state.pending_status_indicator_restore is False
    assert runtime.status_state.terminal_title_status_kind.value == "working"
    assert runtime.status_header == "Working"
    assert runtime.full_reasoning_buffer == []
    assert runtime.reasoning_buffer == []
    assert runtime.active_cell_revisions == 1
    assert runtime.redraw_requests == 1
    assert runtime.ambient_pet_notifications[-1] == {"kind": "running", "body": None}


def test_collect_runtime_metrics_delta_merges_and_logs_websocket_timing() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.session_telemetry.pending_delta = RuntimeMetricsSummary(websocket_timing_label="connect 12ms")

    runtime.collect_runtime_metrics_delta()

    assert runtime.turn_runtime_metrics.websocket_timing_label == "connect 12ms"
    assert runtime.history[-1] == {"kind": "plain_lines", "lines": ["WebSocket timing: connect 12ms"]}


def test_finalize_turn_clears_running_state_without_clearing_mcp_startup() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.turn_lifecycle.start("now")
    runtime.running_commands.extend(["cmd"])
    runtime.suppressed_exec_calls.extend(["call"])
    runtime.last_unified_wait = object()
    runtime.unified_exec_wait_streak = object()
    runtime.stream_controller = object()
    runtime.plan_stream_controller = object()
    runtime.status_state.pending_status_indicator_restore = True
    runtime.mcp_startup_status = object()

    runtime.finalize_turn()

    assert runtime.turn_lifecycle.agent_turn_running is False
    assert runtime.bottom_pane.task_running is True
    assert runtime.running_commands == []
    assert runtime.suppressed_exec_calls == []
    assert runtime.last_unified_wait is None
    assert runtime.unified_exec_wait_streak is None
    assert runtime.stream_controller is None
    assert runtime.plan_stream_controller is None
    assert runtime.status_state.pending_status_indicator_restore is False
    assert runtime.status_line_branch_refreshes == 1
    assert runtime.status_line_git_summary_refreshes == 1
    assert runtime.pending_rate_limit_prompt_checks == 1


def test_on_warning_deduplicates_messages_and_requests_redraw() -> None:
    runtime = ChatWidgetTurnRuntime()

    runtime.on_warning("careful")
    runtime.on_warning("careful")
    runtime.on_warning("different")

    assert runtime.history == [
        {"kind": "warning", "message": "careful"},
        {"kind": "warning", "message": "different"},
    ]
    assert runtime.redraw_requests == 2


def test_on_plan_update_records_progress_and_history() -> None:
    runtime = ChatWidgetTurnRuntime()
    update = UpdatePlanArgs(
        [
            PlanItem(StepStatus.COMPLETED, "one"),
            PlanItem(StepStatus.IN_PROGRESS, "two"),
            PlanItem(StepStatus.PENDING, "three"),
        ]
    )

    runtime.on_plan_update(update)

    assert runtime.transcript.saw_plan_update_this_turn is True
    assert runtime.transcript.last_plan_progress == (1, 3)
    assert runtime.status_surface_refreshes == 1
    assert runtime.history[-1] == {"kind": "plan_update", "update": update}


def test_plan_implementation_prompt_guards_and_context_usage_label() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.mode_kind = ModeKind.PLAN
    runtime.transcript.saw_plan_item_this_turn = True
    runtime.transcript.latest_proposed_plan_markdown = "plan"
    runtime.token_info = TokenUsageInfo(total_token_limit=1000, total_tokens=250)

    runtime.maybe_prompt_plan_implementation()

    assert runtime.bottom_pane.selection_views[-1]["context_usage_label"] == "25% used"
    assert runtime.notifications[-1]["kind"] == "plan_mode_prompt"

    blocked = ChatWidgetTurnRuntime()
    blocked.mode_kind = ModeKind.PLAN
    blocked.transcript.saw_plan_item_this_turn = True
    blocked.input_queue.queued_follow_up_messages.append("next")
    blocked.maybe_prompt_plan_implementation()
    assert blocked.bottom_pane.selection_views == []


def test_plan_implementation_context_usage_label_uses_token_fallback() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.token_info = TokenUsageInfo(total_tokens=1536)

    assert runtime.plan_implementation_context_usage_label() == "1.5K used"


def test_interrupted_turn_message_matches_rust_branches() -> None:
    assert interrupted_turn_message(TurnAbortReason.BUDGET_LIMITED) == "Goal budget reached - the turn was stopped."
    assert interrupted_turn_message(TurnAbortReason.OTHER) == (
        "Conversation interrupted - tell the model what to do differently. "
        "Something went wrong? Hit `/feedback` to report the issue."
    )
