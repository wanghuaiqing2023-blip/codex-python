"""Parity tests for Rust ``codex-tui::chatwidget::turn_runtime``.

Rust source: ``codex/codex-rs/tui/src/chatwidget/turn_runtime.rs``.
"""

from pycodex.tui.chatwidget.turn_runtime import (
    ChatWidgetTurnRuntime,
    ModeKind,
    PlanItem,
    RateLimitErrorKind,
    RateLimitReachedType,
    RuntimeMetricsSummary,
    StepStatus,
    TerminalTurnSubmissionRunner,
    TokenUsageInfo,
    TurnAbortReason,
    UpdatePlanArgs,
    interrupted_turn_message,
    run_terminal_turn_submission,
    run_terminal_turn_start,
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


def test_run_terminal_turn_start_sequences_terminal_callbacks() -> None:
    # Rust owner: codex-tui::chatwidget::turn_runtime owns turn start state
    # setup; terminal runtime supplies timestamp and terminal side effects.
    calls: list[tuple[str, str | float | None]] = []

    started = run_terminal_turn_start(
        "hello",
        started_at=12.5,
        append_history=lambda prompt: calls.append(("append", prompt)),
        apply_started_at=lambda value: calls.append(("started_at", value)),
        reset_assistant_stream=lambda: calls.append(("reset_stream", None)),
        clear_turn_status=lambda: calls.append(("clear_status", None)),
        render_turn_status=lambda: calls.append(("render_status", None)),
    )

    assert started == 12.5
    assert calls == [
        ("append", "hello"),
        ("started_at", 12.5),
        ("reset_stream", None),
        ("clear_status", None),
        ("render_status", None),
    ]


def test_run_terminal_turn_start_allows_missing_history_append() -> None:
    # Rust owner: codex-tui::chatwidget::turn_runtime owns turn-start
    # sequencing; terminal runtime may omit the optional history append
    # callback, but should not pass arbitrary adapter objects through this
    # boundary.
    calls: list[str] = []

    run_terminal_turn_start(
        "hello",
        started_at="now",
        append_history=None,
        apply_started_at=lambda value: calls.append(f"started:{value}"),
        reset_assistant_stream=lambda: calls.append("reset"),
        clear_turn_status=lambda: calls.append("clear"),
        render_turn_status=lambda: calls.append("render"),
    )

    assert calls == ["started:now", "reset", "clear", "render"]


def test_run_terminal_turn_submission_submits_and_consumes_events() -> None:
    # Rust owner: codex-tui::chatwidget input submission/turn runtime owns
    # user-turn submission lifecycle; terminal runtime supplies side effects.
    calls: list[object] = []

    result = run_terminal_turn_submission(
        "hello",
        started_at=1.0,
        append_history=lambda prompt: calls.append(("append", prompt)),
        apply_started_at=lambda value: calls.append(("started", value)),
        reset_assistant_stream=lambda: calls.append("reset"),
        clear_turn_status=lambda: calls.append("clear"),
        render_turn_status=lambda: calls.append("render"),
        submit_user_turn=lambda prompt: calls.append(("submit", prompt)) or "events",
        consume_events=lambda stream: calls.append(("consume", stream)),
        close_turn=lambda: calls.append("close"),
        write_error=lambda text: calls.append(("error", text)),
        set_exit_code=lambda code: calls.append(("exit", code)),
    )

    assert result is True
    assert calls == [
        ("append", "hello"),
        ("started", 1.0),
        "reset",
        "clear",
        "render",
        ("submit", "hello"),
        ("consume", "events"),
    ]


def test_run_terminal_turn_submission_applies_failure_effects() -> None:
    calls: list[object] = []

    def submit(_: str) -> object:
        calls.append("submit")
        raise RuntimeError("boom")

    result = run_terminal_turn_submission(
        "hello",
        started_at="now",
        append_history=None,
        apply_started_at=lambda value: calls.append(("started", value)),
        reset_assistant_stream=lambda: calls.append("reset"),
        clear_turn_status=lambda: calls.append("clear"),
        render_turn_status=lambda: calls.append("render"),
        submit_user_turn=submit,
        consume_events=lambda stream: calls.append(("consume", stream)),
        close_turn=lambda: calls.append("close"),
        write_error=lambda text: calls.append(("error", text)),
        set_exit_code=lambda code: calls.append(("exit", code)),
    )

    assert result is False
    assert calls == [
        ("started", "now"),
        "reset",
        "clear",
        "render",
        "submit",
        "close",
        ("error", "\u25a0 boom"),
        ("exit", 1),
    ]


def test_terminal_turn_submission_runner_binds_runtime_callbacks() -> None:
    # Rust owner: codex-tui::chatwidget::turn_runtime owns terminal turn
    # submission lifecycle. terminal_runtime should consume a bound runner
    # rather than rebuilding started-at and submission callbacks at the call
    # site.
    calls: list[object] = []
    runner = TerminalTurnSubmissionRunner(
        started_at=lambda: "clock",
        append_history=lambda prompt: calls.append(("append", prompt)),
        apply_started_at=lambda value: calls.append(("started", value)),
        reset_assistant_stream=lambda: calls.append("reset"),
        clear_turn_status=lambda: calls.append("clear"),
        render_turn_status=lambda: calls.append("render"),
        submit_user_turn=lambda prompt: calls.append(("submit", prompt)) or "events",
        consume_events=lambda stream: calls.append(("consume", stream)),
        close_turn=lambda: calls.append("close"),
        write_error=lambda text: calls.append(("error", text)),
        set_exit_code=lambda code: calls.append(("exit", code)),
    )

    assert runner.submit("hello") is True
    assert calls == [
        ("append", "hello"),
        ("started", "clock"),
        "reset",
        "clear",
        "render",
        ("submit", "hello"),
        ("consume", "events"),
    ]


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


def test_on_task_complete_records_markdown_separator_notifications_and_clears_state() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.turn_lifecycle.start("now")
    runtime.transcript.had_work_activity = True
    runtime.transcript.needs_final_message_separator = True
    runtime.running_commands.extend(["cmd"])
    runtime.suppressed_exec_calls.extend(["call"])
    runtime.last_unified_wait = object()
    runtime.unified_exec_wait_streak = object()

    runtime.on_task_complete(" final answer ", 2500, from_replay=False)

    assert runtime.turn_lifecycle.agent_turn_running is False
    assert runtime.bottom_pane.task_running is False
    assert runtime.running_commands == []
    assert runtime.suppressed_exec_calls == []
    assert runtime.last_unified_wait is None
    assert runtime.unified_exec_wait_streak is None
    assert runtime.answer_stream_flushes == 1
    assert runtime.unified_exec_wait_flushes == 1
    assert runtime.history[-1]["kind"] == "final_message_separator"
    assert runtime.history[-1]["elapsed_seconds"] == 2
    assert runtime.notifications[-1] == {"kind": "agent_turn_complete", "response": "final answer"}
    assert runtime.ambient_pet_notifications[-1] == {"kind": "review", "body": "final answer"}
    assert runtime.pending_input_preview_refreshes == 1
    assert runtime.pending_rate_limit_prompt_checks == 1


def test_on_task_complete_from_replay_skips_notifications_and_separator_cleanup() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.turn_lifecycle.start("now")
    runtime.transcript.had_work_activity = True
    runtime.transcript.needs_final_message_separator = True
    runtime.transcript.saw_plan_item_this_turn = True

    runtime.on_task_complete("replayed", 1000, from_replay=True)

    assert runtime.history == []
    assert runtime.notifications == []
    assert runtime.ambient_pet_notifications == []
    assert runtime.transcript.saw_plan_item_this_turn is True


def test_on_task_complete_queued_followup_suppresses_waiting_notification() -> None:
    runtime = ChatWidgetTurnRuntime()
    runtime.input_queue.queued_follow_up_messages.append("next")

    runtime.on_task_complete("answer", None, from_replay=False)

    assert runtime.queued_input_send_attempts == 1
    assert runtime.input_queue.queued_follow_up_messages == []
    assert runtime.notifications == []


def test_error_paths_finalize_turn_and_append_expected_history() -> None:
    overloaded = ChatWidgetTurnRuntime()
    overloaded.on_server_overloaded_error("   ")
    assert overloaded.history[-1] == {"kind": "warning", "message": "Codex is currently experiencing high load."}
    assert overloaded.queued_input_send_attempts == 1

    generic = ChatWidgetTurnRuntime()
    generic.on_error("boom")
    assert generic.answer_stream_flushes == 1
    assert generic.history[-1] == {"kind": "error", "message": "boom"}
    assert generic.ambient_pet_notifications[-1] == {"kind": "failed", "body": None}

    cyber = ChatWidgetTurnRuntime()
    cyber.on_cyber_policy_error()
    assert cyber.history[-1] == {"kind": "cyber_policy_error"}


def test_rate_limit_error_maps_workspace_owner_and_member_branches() -> None:
    owner = ChatWidgetTurnRuntime()
    owner.codex_rate_limit_reached_type = RateLimitReachedType.WORKSPACE_OWNER_CREDITS_DEPLETED
    owner.on_rate_limit_error(RateLimitErrorKind.USAGE_LIMIT, "ignored")
    assert owner.codex_rate_limit_reached_type is RateLimitReachedType.WORKSPACE_OWNER_USAGE_LIMIT_REACHED
    assert owner.history[-1]["message"].startswith("Usage limit reached.")

    member = ChatWidgetTurnRuntime()
    member.codex_rate_limit_reached_type = RateLimitReachedType.WORKSPACE_MEMBER_CREDITS_DEPLETED
    member.on_rate_limit_error(RateLimitErrorKind.GENERIC, "add credits")
    assert member.history[-1] == {"kind": "error", "message": "add credits"}
    assert member.workspace_owner_nudges == ["credits"]


def test_handle_non_retry_error_routes_cyber_rate_limit_and_generic_errors() -> None:
    cyber = ChatWidgetTurnRuntime()
    cyber.handle_non_retry_error("blocked", {"cyber_policy": True})
    assert cyber.history[-1] == {"kind": "cyber_policy_error"}

    overloaded = ChatWidgetTurnRuntime()
    overloaded.handle_non_retry_error("busy", {"rate_limit_kind": "server_overloaded"})
    assert overloaded.history[-1] == {"kind": "warning", "message": "busy"}

    generic = ChatWidgetTurnRuntime()
    generic.handle_non_retry_error("plain", None)
    assert generic.history[-1] == {"kind": "error", "message": "plain"}
