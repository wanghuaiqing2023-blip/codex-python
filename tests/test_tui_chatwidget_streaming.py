from pycodex.tui.chatwidget.status_state import TerminalTitleStatusKind
from pycodex.tui.chatwidget.streaming import (
    CommitTickScope,
    MessagePhase,
    ModeKind,
    StreamControllerState,
    StreamingWidgetState,
    extract_first_bold,
)


def test_extract_first_bold_matches_rust_wait_for_closing_behavior() -> None:
    # Rust parity: chatwidget.rs::extract_first_bold used by chatwidget::streaming.
    assert extract_first_bold("before ** Header ** after") == "Header"
    assert extract_first_bold("before **   ** after") is None
    assert extract_first_bold("before ** pending") is None
    assert extract_first_bold("no bold here") is None


def test_restore_reasoning_status_header_prefers_bold_header_then_working() -> None:
    # Rust parity: ChatWidget::restore_reasoning_status_header.
    state = StreamingWidgetState(reasoning_buffer="text **Plan** more", task_running=True)
    state.restore_reasoning_status_header()
    assert state.status_state.current_status.header == "Plan"
    assert state.status_state.terminal_title_status_kind is TerminalTitleStatusKind.Thinking

    state = StreamingWidgetState(reasoning_buffer="text", task_running=True)
    state.restore_reasoning_status_header()
    assert state.status_state.current_status.header == "Working"
    assert state.status_state.terminal_title_status_kind is TerminalTitleStatusKind.Working


def test_restore_status_indicator_waits_for_pending_running_and_idle() -> None:
    # Rust parity: ChatWidget::maybe_restore_status_indicator_after_stream_idle.
    state = StreamingWidgetState(
        task_running=True,
        stream_controller=StreamControllerState(queued_lines=1),
    )
    state.status_state.pending_status_indicator_restore = True
    state.status_indicator_visible = False

    assert not state.maybe_restore_status_indicator_after_stream_idle()
    state.stream_controller.queued_lines = 0
    assert state.maybe_restore_status_indicator_after_stream_idle()
    assert state.status_indicator_visible
    assert not state.status_state.pending_status_indicator_restore


def test_reasoning_delta_updates_header_unless_exec_wait_streak_precedes_it() -> None:
    # Rust parity: ChatWidget::on_agent_reasoning_delta.
    state = StreamingWidgetState()
    state.on_agent_reasoning_delta("hello **Thinking**")
    assert state.status_state.current_status.header == "Thinking"
    assert state.status_state.terminal_title_status_kind is TerminalTitleStatusKind.Thinking
    assert state.redraw_requests == 1

    blocked = StreamingWidgetState(unified_exec_wait_streak=True)
    blocked.on_agent_reasoning_delta("hello **Ignored**")
    assert blocked.status_state.current_status.header == "Working"
    assert blocked.redraw_requests == 1


def test_reasoning_section_break_and_final_record_transcript_only_summary() -> None:
    # Rust parity: ChatWidget::on_reasoning_section_break / on_agent_reasoning_final.
    state = StreamingWidgetState(reasoning_buffer="first")
    state.on_reasoning_section_break()
    assert state.full_reasoning_buffer == "first\n\n"
    assert state.reasoning_buffer == ""

    state.reasoning_buffer = "second"
    state.on_agent_reasoning_final()
    assert state.history == [("reasoning_summary", "first\n\nsecond")]
    assert state.full_reasoning_buffer == ""
    assert state.reasoning_buffer == ""


def test_agent_message_completion_restore_flag_depends_on_phase() -> None:
    # Rust parity: ChatWidget::on_agent_message_item_completed phase restore rules.
    final = StreamingWidgetState(task_running=True, input_queue_pending_steers=False)
    final.on_agent_message_item_completed("answer", MessagePhase.FinalAnswer)
    assert final.history == [("agent_markdown", "answer")]
    assert not final.status_state.pending_status_indicator_restore

    commentary = StreamingWidgetState(
        task_running=True,
        stream_controller=StreamControllerState(queued_lines=1),
    )
    commentary.on_agent_message_item_completed("commentary", MessagePhase.Commentary)
    assert commentary.status_state.pending_status_indicator_restore


def test_active_stream_tail_requires_controller_and_tail_cell_then_clear_bumps_revision() -> None:
    # Rust parity: active_cell_is_stream_tail / has_active_stream_tail / clear_active_stream_tail.
    state = StreamingWidgetState(
        stream_controller=StreamControllerState(),
        active_cell_kind="streaming_agent_tail",
    )
    assert state.active_cell_is_stream_tail()
    assert state.has_active_stream_tail()
    assert state.clear_active_stream_tail()
    assert state.active_cell_kind is None
    assert state.active_cell_revision == 1


def test_flush_answer_stream_consolidates_source_resets_chunking_and_stops_animation() -> None:
    state = StreamingWidgetState(stream_controller=StreamControllerState(queued_lines=0, source="**hi**", live_tail=False))

    state.flush_answer_stream_with_separator()

    assert state.stream_controller is None
    assert state.history == [("agent_stream", "**hi**")]
    assert state.consolidation_events == [("agent_message", "**hi**")]
    assert state.adaptive_chunking_resets == 1
    assert state.stop_commit_animation_events == 1


def test_handle_streaming_delta_starts_controller_separator_and_tail() -> None:
    state = StreamingWidgetState(
        needs_final_message_separator=True,
        had_work_activity=True,
        unified_exec_wait_streak=True,
        active_cell_kind="exec_cell",
    )

    state.handle_streaming_delta("hello\n")

    assert state.unified_exec_wait_flushes == 1
    assert state.active_exec_cell_flushed == 1
    assert state.history[0] == ("final_message_separator", "")
    assert state.stream_controller is not None
    assert state.active_cell_kind == "streaming_agent_tail"
    assert state.status_indicator_visible is False
    assert state.start_commit_animation_events == 1


def test_finalize_completed_assistant_message_uses_payload_only_without_controller() -> None:
    state = StreamingWidgetState()

    state.finalize_completed_assistant_message("answer")

    assert state.consolidation_events == [("agent_message", "answer")]
    assert state.stream_controller is None
    assert state.redraw_requests >= 1


def test_plan_delta_ignored_outside_plan_mode_and_streams_inside_plan_mode() -> None:
    chat = StreamingWidgetState(mode_kind=ModeKind.Chat)
    chat.on_plan_delta("plan")
    assert chat.plan_stream_controller is None

    state = StreamingWidgetState(mode_kind=ModeKind.Plan, unified_exec_wait_streak=True, active_cell_kind="exec_cell")
    state.on_plan_delta("step one\n")

    assert state.plan_item_active is True
    assert state.plan_delta_buffer == "step one\n"
    assert state.unified_exec_wait_flushes == 1
    assert state.active_exec_cell_flushed == 1
    assert state.plan_stream_controller is not None
    assert state.active_cell_kind == "streaming_plan_tail"


def test_plan_item_completed_records_markdown_and_proposed_plan_or_consolidates_empty_source() -> None:
    state = StreamingWidgetState(mode_kind=ModeKind.Plan)
    state.on_plan_delta("streamed plan")

    state.on_plan_item_completed("")

    assert state.plan_item_active is False
    assert state.saw_plan_item_this_turn is True
    assert state.latest_proposed_plan_markdown == "streamed plan"
    assert ("agent_markdown", "streamed plan") in state.history
    assert ("proposed_plan", "streamed plan") in state.history
    assert state.status_state.pending_status_indicator_restore is False


def test_commit_tick_commits_stream_lines_stops_animation_and_refreshes_metrics() -> None:
    state = StreamingWidgetState(
        task_running=True,
        stream_controller=StreamControllerState(queued_lines=1, source="one", tail_lines=["one"], live_tail=True),
    )

    state.run_commit_tick_with_scope(CommitTickScope.AnyMode)

    assert ("stream_line", "one") in state.history
    assert state.stream_controller is not None
    assert state.stream_controller.queued_lines == 0
    assert state.stop_commit_animation_events == 1
    assert state.task_running_metrics_refreshes == 1


def test_defer_or_handle_queues_during_stream_and_flushes_fifo_on_finish() -> None:
    state = StreamingWidgetState(stream_controller=StreamControllerState())
    seen = []

    state.defer_or_handle(lambda queue: queue.append(lambda _state: seen.append("queued")), lambda _state: seen.append("handled"))
    assert seen == []
    assert len(state.interrupt_queue) == 1

    state.handle_stream_finished()

    assert seen == ["queued"]
    assert state.interrupt_queue == []
