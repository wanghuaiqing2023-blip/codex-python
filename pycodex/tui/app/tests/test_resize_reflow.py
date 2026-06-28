from pycodex.tui.app.resize_reflow import (
    HistoryCell,
    HistoryLineWrapPolicy,
    HyperlinkLine,
    InitialHistoryReplayBuffer,
    ResizeReflowPlan,
    ResizeReflowState,
    begin_initial_history_replay_buffer_plan,
    begin_thread_switch_history_replay_buffer_plan,
    buffer_initial_history_replay_display_lines,
    display_lines_for_history_insert,
    finish_initial_history_replay_buffer_plan,
    handle_draw_size_change_plan,
    insert_history_cell_lines_plan,
    maybe_finish_stream_reflow_plan,
    maybe_run_resize_reflow,
    history_line_wrap_policy,
    render_transcript_lines_for_reflow,
    reflow_transcript_now,
    reset_history_emission_state,
    should_mark_reflow_as_stream_time,
    trailing_run_start,
)


def test_trailing_run_start_includes_first_non_continuation_cell():
    """Rust codex-tui app::resize_reflow::trailing_run_start."""

    cells = [
        HistoryCell(["old"], cell_type="Other"),
        HistoryCell(["a"], cell_type="AgentMessageCell", stream_continuation=False),
        HistoryCell(["b"], cell_type="AgentMessageCell", stream_continuation=True),
        HistoryCell(["c"], cell_type="AgentMessageCell", stream_continuation=True),
    ]

    assert trailing_run_start(cells, "AgentMessageCell") == 1


def test_trailing_run_start_ignores_non_matching_tail():
    cells = [
        HistoryCell(["a"], cell_type="AgentMessageCell"),
        HistoryCell(["other"], cell_type="Other", stream_continuation=True),
    ]

    assert trailing_run_start(cells, "AgentMessageCell") == 2


def test_buffer_initial_history_replay_display_lines_keeps_newest_rows():
    """Rust buffer_initial_history_replay_display_lines drops oldest rows over cap."""

    buffer = InitialHistoryReplayBuffer()

    buffer_initial_history_replay_display_lines(buffer, ["a", "b", "c"], max_rows=2)
    buffer_initial_history_replay_display_lines(buffer, ["d"], max_rows=2)

    assert list(buffer.retained_lines) == [HyperlinkLine("c"), HyperlinkLine("d")]


def test_history_line_wrap_policy_matches_raw_output_mode():
    assert history_line_wrap_policy(raw_output_mode=True) is HistoryLineWrapPolicy.Terminal
    assert history_line_wrap_policy(raw_output_mode=False) is HistoryLineWrapPolicy.PreWrap


def test_display_lines_for_history_insert_inserts_separator_after_first_non_stream_cell():
    state = ResizeReflowState()

    first = display_lines_for_history_insert(state, HistoryCell(["first"]), width=80)
    second = display_lines_for_history_insert(state, HistoryCell(["second"]), width=80)
    continuation = display_lines_for_history_insert(
        state,
        HistoryCell(["continued"], stream_continuation=True),
        width=80,
    )

    assert first == [HyperlinkLine("first")]
    assert second == [HyperlinkLine(""), HyperlinkLine("second")]
    assert continuation == [HyperlinkLine("continued")]


def test_render_transcript_lines_for_reflow_adds_separators_and_applies_row_cap():
    state = ResizeReflowState()
    cells = [
        HistoryCell(["one"], cell_type="A"),
        HistoryCell(["two"], cell_type="B"),
        HistoryCell(["three"], cell_type="C"),
    ]

    result = render_transcript_lines_for_reflow(cells, width=80, row_cap=4, state=state)

    assert result.lines == [
        HyperlinkLine(""),
        HyperlinkLine("two"),
        HyperlinkLine(""),
        HyperlinkLine("three"),
    ]
    assert state.has_emitted_history_lines is True


def test_render_transcript_lines_extends_to_start_of_stream_continuation_run_before_trimming():
    cells = [
        HistoryCell(["older"], cell_type="Other"),
        HistoryCell(["start"], cell_type="AgentMessageCell", stream_continuation=False),
        HistoryCell(["cont1"], cell_type="AgentMessageCell", stream_continuation=True),
        HistoryCell(["cont2"], cell_type="AgentMessageCell", stream_continuation=True),
    ]

    result = render_transcript_lines_for_reflow(cells, width=80, row_cap=3)

    assert result.lines == [HyperlinkLine("start"), HyperlinkLine("cont1"), HyperlinkLine("cont2")]


def test_should_mark_reflow_as_stream_time_matches_active_stream_or_trailing_cells():
    assert should_mark_reflow_as_stream_time([], active_agent_stream=True) is True
    assert should_mark_reflow_as_stream_time([], active_plan_stream=True) is True
    assert should_mark_reflow_as_stream_time([HistoryCell(["x"], cell_type="AgentMessageCell")]) is True
    assert should_mark_reflow_as_stream_time([HistoryCell(["x"], cell_type="ProposedPlanStreamCell")]) is True
    assert should_mark_reflow_as_stream_time([HistoryCell(["x"], cell_type="Other")]) is False


def test_reset_history_emission_state_clears_flag_and_deferred_lines():
    state = ResizeReflowState(has_emitted_history_lines=True)
    deferred = [HyperlinkLine("queued")]

    reset_history_emission_state(state, deferred)

    assert state.has_emitted_history_lines is False
    assert deferred == []


def test_initial_replay_and_insert_history_runtime_paths_are_semantic_plans():
    state = ResizeReflowState(raw_output_mode=True)
    assert begin_initial_history_replay_buffer_plan(True) == ResizeReflowPlan(
        action="begin_initial_history_replay_buffer",
        updates=(("initial_history_replay_buffer", True),),
    )
    assert begin_thread_switch_history_replay_buffer_plan(True, 10).action == "begin_thread_switch_history_replay_buffer"

    insert = insert_history_cell_lines_plan(state, HistoryCell(["hello"]), 80)
    assert insert.action == "insert_history_lines"
    assert insert.wrap_policy is HistoryLineWrapPolicy.Terminal

    buffer = InitialHistoryReplayBuffer()
    buffer_initial_history_replay_display_lines(buffer, ["tail"], 10)
    flush = finish_initial_history_replay_buffer_plan(state, buffer, 80)
    assert flush.action == "flush_initial_history_replay_buffer"
    assert flush.lines == (HyperlinkLine("tail"),)


def test_resize_scheduling_and_reflow_runtime_paths_are_semantic_plans():
    state = ResizeReflowState(transcript_cells=[HistoryCell(["one"]), HistoryCell(["two"])])

    scheduled = handle_draw_size_change_plan(state, width=100, height=24, last_width=80, last_height=24, stream_time=True)
    assert scheduled.action == "schedule_resize_reflow"
    assert scheduled.schedule_frame
    assert ("transcript_reflow.stream_time", True) in scheduled.updates

    reflow = reflow_transcript_now(state, 100)
    assert reflow.action == "reflow_transcript_now"
    assert reflow.wrap_policy is HistoryLineWrapPolicy.PreWrap
    assert ("clear_terminal_for_resize_replay", True) in reflow.updates

    run = maybe_run_resize_reflow(state, 100, pending_due=True)
    assert run.action == "run_resize_reflow"
    assert run.schedule_frame_in == "TRANSCRIPT_REFLOW_DEBOUNCE"

    deferred = maybe_run_resize_reflow(state, 100, pending_due=False)
    assert deferred.action == "defer_resize_reflow"
    assert deferred.schedule_frame_in == "pending_until"


def test_maybe_finish_stream_reflow_runs_immediate_source_backed_reflow_after_stream_resize() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow::App::maybe_finish_stream_reflow drains
    #   TranscriptReflowState::take_stream_finish_reflow_needed().
    # - If a resize happened while streaming, it schedules an immediate reflow
    #   and runs maybe_run_resize_reflow so finalized source-backed cells replace
    #   transient stream rows.
    state = ResizeReflowState(transcript_cells=[HistoryCell(["finalized stream"])])
    state.transcript_reflow.mark_resize_requested_during_stream()

    plan = maybe_finish_stream_reflow_plan(state, 100)

    assert plan.action == "finish_stream_reflow"
    assert plan.schedule_frame is True
    assert ("transcript_reflow.schedule_immediate", True) in plan.updates
    assert ("transcript_reflow.mark_reflowed_width", 100) in plan.updates
    assert plan.lines == (HyperlinkLine("finalized stream"),)
    assert not state.transcript_reflow.take_stream_finish_reflow_needed()


def test_maybe_finish_stream_reflow_schedules_frame_when_existing_pending_reflow_is_due() -> None:
    # Rust source contract:
    # - App::maybe_finish_stream_reflow schedules a frame when no stream-finish
    #   repair is needed but an existing pending resize reflow is due.
    state = ResizeReflowState(transcript_cells=[HistoryCell(["history"])])

    plan = maybe_finish_stream_reflow_plan(state, 100, pending_due=True)

    assert plan.action == "stream_finish_pending_reflow_due"
    assert plan.schedule_frame is True
    assert plan.updates == (("frame_requester.schedule_frame", True),)


def test_maybe_finish_stream_reflow_disabled_clears_transcript_reflow_state() -> None:
    # Rust source contract:
    # - App::maybe_finish_stream_reflow clears TranscriptReflowState when
    #   TerminalResizeReflow is disabled.
    state = ResizeReflowState(transcript_cells=[HistoryCell(["history"])])
    state.transcript_reflow.note_width(80)
    state.transcript_reflow.schedule_debounced(100)
    state.transcript_reflow.mark_ran_during_stream()

    plan = maybe_finish_stream_reflow_plan(state, 100, enabled=False)

    assert plan.action == "clear_disabled_stream_finish_reflow"
    assert state.transcript_reflow.last_observed_width is None
    assert not state.transcript_reflow.has_pending_reflow()
    assert not state.transcript_reflow.take_stream_finish_reflow_needed()
