from pycodex.tui.chatwidget.status_state import TerminalTitleStatusKind
from pycodex.tui.chatwidget.streaming import (
    MessagePhase,
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
