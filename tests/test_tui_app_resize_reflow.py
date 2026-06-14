from pycodex.tui.app.resize_reflow import (
    HistoryCell,
    HistoryLineWrapPolicy,
    HyperlinkLine,
    InitialHistoryReplayBuffer,
    ResizeReflowState,
    buffer_initial_history_replay_display_lines,
    display_lines_for_history_insert,
    history_line_wrap_policy,
    render_transcript_lines_for_reflow,
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
