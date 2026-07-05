from pycodex.tui.app.resize_reflow import (
    HistoryCell,
    HistoryLineWrapPolicy,
    HyperlinkLine,
    InitialHistoryReplayBuffer,
    ResizeReflowPlan,
    ResizeReflowState,
    TerminalResizeCoordinator,
    TerminalResizeHistoryReplayer,
    TerminalResizeReflowPlan,
    TerminalResizeRuntimeState,
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
    plan_terminal_bottom_pane_footprint_reflow,
    plan_terminal_resize_reflow,
    plan_terminal_size_change_reflow,
    plan_terminal_stream_finish_reflow,
    repaint_terminal_history_projection_viewport,
    repaint_terminal_history_projection_viewport_and_flush,
    repaint_terminal_history_projection_viewport_for_width_and_flush,
    repaint_terminal_history_state_viewport_for_width_and_flush,
    repaint_terminal_history_viewport,
    replay_terminal_history_projection_cells,
    replay_terminal_history_projection_cells_for_width,
    replay_terminal_history_scrollback_for_resize,
    replay_terminal_history_scrollback_for_resize_width,
    replay_terminal_history_state_scrollback_for_resize_width,
    render_transcript_lines_for_reflow,
    reflow_transcript_now,
    reset_history_emission_state,
    run_terminal_bottom_pane_footprint_reflow,
    run_terminal_layout_activation,
    run_terminal_layout_deactivation,
    run_terminal_history_state_viewport_repaint_for_width,
    run_terminal_history_state_scrollback_replay_for_resize_width,
    run_terminal_history_state_scrollback_replay_insert_for_resize_width,
    run_terminal_resize_reflow_plan,
    run_terminal_size_change_reflow,
    should_mark_reflow_as_stream_time,
    terminal_history_state_for_resize_replay,
    trailing_run_start,
)
from pycodex.tui.bottom_pane.terminal_surface import TerminalBottomPaneFootprint, TerminalLiveStatusSurface
from pycodex.tui.insert_history import TerminalHistoryState

import os
from io import StringIO


class FlushTrackingStringIO(StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


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


def test_bottom_pane_popup_footprint_change_repaints_history_viewport() -> None:
    # Rust source contract:
    # - codex-tui::bottom_pane changes desired height when a popup/view opens.
    # - codex-tui::app::resize_reflow owns repairing the visible transcript
    #   viewport for bottom-pane footprint changes, not individual commands.
    previous = TerminalBottomPaneFootprint(live_status_active=False, popup_height=0)
    current = TerminalBottomPaneFootprint(live_status_active=False, popup_height=4)

    plan = plan_terminal_bottom_pane_footprint_reflow(
        terminal_size=os.terminal_size((96, 24)),
        previous=TerminalLiveStatusSurface.inactive(),
        current=TerminalLiveStatusSurface.inactive(),
        previous_footprint=previous,
        current_footprint=current,
        active_stream=False,
    )

    assert plan == TerminalResizeReflowPlan("repaint_history_viewport", pending=False)


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


def test_repaint_terminal_history_viewport_anchors_retained_tail_above_bottom_pane() -> None:
    # Rust source contract:
    # - app::resize_reflow rebuilds the visible history area from retained
    #   source-backed history lines after terminal or bottom-pane footprint
    #   changes.
    writer = StringIO()

    painted = repaint_terminal_history_viewport(
        writer,
        ["old", "middle", "new"],
        bottom_row=2,
        columns=10,
    )

    output = writer.getvalue()
    assert painted is True
    assert "\x1b[r" in output
    assert "\x1b[1;1H\x1b[2K" in output
    assert "\x1b[2;1H\x1b[2K" in output
    assert "\x1b[1;1Hmiddle" in output
    assert "\x1b[2;1Hnew" in output
    assert "old" not in output


def test_repaint_terminal_history_viewport_truncates_to_visible_columns() -> None:
    writer = StringIO()

    repaint_terminal_history_viewport(
        writer,
        ["abcdef"],
        bottom_row=1,
        columns=4,
    )

    assert "\x1b[1;1Habc" in writer.getvalue()
    assert "abcdef" not in writer.getvalue()


def test_terminal_history_projection_cell_helpers_wrap_and_replay_cells() -> None:
    replayed: list[list[str]] = []

    assert replay_terminal_history_projection_cells(
        ["alpha", "beta"],
        lambda cell: [cell.upper()],
        lambda lines: replayed.append(lines),
    )
    assert replayed == [["ALPHA", "", "BETA"]]

    writer = StringIO()
    assert repaint_terminal_history_projection_viewport(
        writer,
        ["old", "new"],
        lambda cell: [cell],
        bottom_row=1,
        columns=10,
    )
    output = writer.getvalue()
    assert "old" not in output
    assert "\x1b[1;1Hnew" in output


def test_terminal_history_projection_width_helpers_use_insert_history_wrapping() -> None:
    replayed: list[list[str]] = []

    assert replay_terminal_history_projection_cells_for_width(
        ["\u2022 alpha beta gamma"],
        10,
        lambda lines: replayed.append(lines),
    )

    assert replayed[0][0].startswith("\u2022 ")
    assert len(replayed[0]) >= 2

    writer = FlushTrackingStringIO()
    assert repaint_terminal_history_projection_viewport_for_width_and_flush(
        writer,
        ["\u2022 alpha beta gamma"],
        10,
        bottom_row=2,
        columns=20,
    )
    assert writer.flush_count == 1
    assert "\x1b[1;1H" in writer.getvalue()


def test_repaint_terminal_history_projection_viewport_and_flush_flushes_writer() -> None:
    writer = FlushTrackingStringIO()

    assert repaint_terminal_history_projection_viewport_and_flush(
        writer,
        ["new"],
        lambda cell: [cell],
        bottom_row=1,
        columns=10,
    )

    assert writer.flush_count == 1
    assert "\x1b[1;1Hnew" in writer.getvalue()


def test_replay_terminal_history_scrollback_for_resize_clears_replays_and_renders_bottom_pane() -> None:
    writer = StringIO()
    replayed: list[list[str]] = []

    assert replay_terminal_history_scrollback_for_resize(
        writer,
        ["alpha", "beta"],
        lambda cell: [cell],
        lambda lines: replayed.append(lines),
        render_bottom_pane=lambda: writer.write("<bottom-pane>"),
    )

    output = writer.getvalue()
    assert output.startswith("\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H")
    assert output.endswith("<bottom-pane>")
    assert replayed == [["alpha", "", "beta"]]


def test_replay_terminal_history_scrollback_for_resize_width_uses_insert_history_wrapping() -> None:
    writer = FlushTrackingStringIO()
    replayed: list[list[str]] = []

    assert replay_terminal_history_scrollback_for_resize_width(
        writer,
        ["\u2022 alpha beta gamma"],
        10,
        lambda lines: replayed.append(lines),
        render_bottom_pane=lambda: writer.write("<bottom-pane>"),
    )

    assert writer.flush_count == 1
    assert writer.getvalue().endswith("<bottom-pane>")
    assert replayed[0][0].startswith("\u2022 ")
    assert len(replayed[0]) >= 2


def test_terminal_history_state_for_resize_replay_resets_write_markers_only() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow clears/rebuilds the terminal surface from
    #   retained source-backed history; stale write markers from the old surface
    #   must not leak into the replay.
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=True,
        projection_cells=("alpha", "beta"),
    )

    replay_state = terminal_history_state_for_resize_replay(state)

    assert replay_state.history_has_content is False
    assert replay_state.history_ended_with_blank is False
    assert replay_state.projection_cells == ("alpha", "beta")


def test_terminal_history_state_resize_helpers_use_retained_projection_cells() -> None:
    state = TerminalHistoryState(projection_cells=("old", "new"))
    writer = FlushTrackingStringIO()
    replayed: list[list[str]] = []

    assert repaint_terminal_history_state_viewport_for_width_and_flush(
        writer,
        state,
        20,
        bottom_row=1,
        columns=20,
    )
    assert writer.flush_count == 1
    assert "old" not in writer.getvalue()
    assert "\x1b[1;1Hnew" in writer.getvalue()

    replay_writer = FlushTrackingStringIO()
    assert replay_terminal_history_state_scrollback_for_resize_width(
        replay_writer,
        state,
        20,
        lambda lines: replayed.append(lines),
        render_bottom_pane=lambda: replay_writer.write("<bottom-pane>"),
    )
    assert replay_writer.flush_count == 1
    assert replay_writer.getvalue().endswith("<bottom-pane>")
    assert replayed == [["old", "", "new"]]


def test_run_terminal_history_state_viewport_repaint_for_width_guards_inactive_path() -> None:
    # Rust owner: codex-tui::app::resize_reflow only repaints retained terminal
    # history when the real terminal layout is active.
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    painted = run_terminal_history_state_viewport_repaint_for_width(
        writer,
        TerminalHistoryState(projection_cells=("old", "new")),
        20,
        terminal_active=False,
        history_bottom_row=lambda: calls.append("bottom") or 1,
        terminal_columns=lambda: calls.append("columns") or 20,
    )

    assert painted is False
    assert calls == []
    assert writer.getvalue() == ""
    assert writer.flush_count == 0


def test_run_terminal_history_state_viewport_repaint_for_width_uses_callbacks() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    painted = run_terminal_history_state_viewport_repaint_for_width(
        writer,
        TerminalHistoryState(projection_cells=("old", "new")),
        20,
        terminal_active=True,
        history_bottom_row=lambda: calls.append("bottom") or 1,
        terminal_columns=lambda: calls.append("columns") or 20,
    )

    assert painted is True
    assert calls == ["bottom", "columns"]
    assert writer.flush_count == 1
    assert "old" not in writer.getvalue()
    assert "\x1b[1;1Hnew" in writer.getvalue()


def test_run_terminal_history_state_scrollback_replay_resets_then_replays() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns resize replay ordering:
    # reset stale insert-history markers before clearing/rebuilding scrollback.
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=True,
        projection_cells=("old", "new"),
    )
    writer = FlushTrackingStringIO()
    calls: list[object] = []
    applied: list[TerminalHistoryState] = []

    replayed = run_terminal_history_state_scrollback_replay_for_resize_width(
        writer,
        state,
        20,
        lambda lines: calls.append(("insert", lines, applied[-1].history_has_content)),
        apply_history_state=lambda next_state: (applied.append(next_state), calls.append("apply")),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert replayed is True
    assert writer.flush_count == 1
    assert applied[0].history_has_content is False
    assert applied[0].history_ended_with_blank is False
    assert applied[0].projection_cells == ("old", "new")
    assert calls == ["apply", ("insert", ["old", "", "new"], False), "render"]


def test_run_terminal_history_state_scrollback_replay_insert_preserves_live_status_footprint() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns resize replay ordering.
    # The terminal product path must rebuild retained scrollback while
    # reserving an active bottom-pane status footprint.
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=True,
        projection_cells=("old", "new"),
    )
    writer = FlushTrackingStringIO()
    calls: list[object] = []
    applied: list[TerminalHistoryState] = []

    replayed = run_terminal_history_state_scrollback_replay_insert_for_resize_width(
        writer,
        state,
        20,
        live_status_footprint_active=True,
        apply_history_state=lambda next_state: (applied.append(next_state), calls.append("apply")),
        insert_replayed_history_lines=lambda lines, reserve: calls.append(("insert", lines, reserve)),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert replayed is True
    assert writer.flush_count == 1
    assert applied[0].history_has_content is False
    assert calls == ["apply", ("insert", ["old", "", "new"], True), "render"]


def test_plan_terminal_resize_reflow_defers_stream_time_changes() -> None:
    plan = plan_terminal_resize_reflow(
        trigger="terminal_resize",
        changed=True,
        active_stream=True,
        pending=False,
    )

    assert plan.action == "defer_until_stream_finish"
    assert plan.pending is True


def test_plan_terminal_resize_reflow_routes_terminal_and_pane_repairs() -> None:
    resize = plan_terminal_resize_reflow(
        trigger="terminal_resize",
        changed=True,
        active_stream=False,
    )
    footprint = plan_terminal_resize_reflow(
        trigger="bottom_pane_footprint",
        changed=True,
        active_stream=False,
    )
    unchanged = plan_terminal_resize_reflow(
        trigger="terminal_resize",
        changed=False,
        active_stream=False,
        pending=True,
    )

    assert resize.action == "replay_history_scrollback"
    assert resize.pending is False
    assert footprint.action == "repaint_history_viewport"
    assert footprint.pending is False
    assert unchanged.action == "none"
    assert unchanged.pending is True


def test_plan_terminal_bottom_pane_footprint_reflow_maps_surface_change_to_resize_plan() -> None:
    # Rust source contract:
    # - codex-tui::bottom_pane requests redraw when status indicator footprint
    #   changes, and app::resize_reflow maps that footprint change to retained
    #   history viewport repair in the terminal product path.
    size = os.terminal_size((80, 24))
    idle = TerminalLiveStatusSurface.inactive()
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")

    repair = plan_terminal_bottom_pane_footprint_reflow(
        terminal_size=size,
        previous=idle,
        current=active,
        active_stream=False,
    )
    deferred = plan_terminal_bottom_pane_footprint_reflow(
        terminal_size=size,
        previous=idle,
        current=active,
        active_stream=True,
    )
    unchanged = plan_terminal_bottom_pane_footprint_reflow(
        terminal_size=size,
        previous=active,
        current=TerminalLiveStatusSurface.active_status("\u2022 Thinking"),
        active_stream=False,
        pending=True,
    )

    assert repair == TerminalResizeReflowPlan("repaint_history_viewport")
    assert deferred == TerminalResizeReflowPlan("defer_until_stream_finish", pending=True)
    assert unchanged == TerminalResizeReflowPlan("none", pending=True)


def test_run_terminal_bottom_pane_footprint_reflow_guards_inactive_path() -> None:
    size = os.terminal_size((80, 24))
    calls: list[TerminalResizeReflowPlan] = []

    ran = run_terminal_bottom_pane_footprint_reflow(
        terminal_active=False,
        terminal_size=size,
        previous=TerminalLiveStatusSurface.inactive(),
        current=TerminalLiveStatusSurface.active_status("\u2022 Working"),
        active_stream=False,
        pending=False,
        run_reflow_plan=calls.append,
    )

    assert ran is False
    assert calls == []


def test_run_terminal_bottom_pane_footprint_reflow_dispatches_even_none_plan() -> None:
    size = os.terminal_size((80, 24))
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")
    calls: list[TerminalResizeReflowPlan] = []

    ran = run_terminal_bottom_pane_footprint_reflow(
        terminal_active=True,
        terminal_size=size,
        previous=active,
        current=TerminalLiveStatusSurface.active_status("\u2022 Thinking"),
        active_stream=False,
        pending=True,
        run_reflow_plan=calls.append,
    )

    assert ran is True
    assert calls == [TerminalResizeReflowPlan("none", pending=True)]


def test_plan_terminal_size_change_reflow_initializes_without_replay() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow::App::handle_draw_size_change
    #   initializes resize tracking without rebuilding previously emitted
    #   terminal scrollback.
    plan = plan_terminal_size_change_reflow(
        previous_size=None,
        current_size=(80, 24),
        active_stream=False,
    )

    assert plan.initialized is True
    assert plan.changed is False
    assert plan.last_terminal_size == (80, 24)
    assert plan.reflow == TerminalResizeReflowPlan("none")


def test_plan_terminal_size_change_reflow_keeps_pending_state_when_size_unchanged() -> None:
    plan = plan_terminal_size_change_reflow(
        previous_size=(80, 24),
        current_size=(80, 24),
        active_stream=False,
        pending=True,
    )

    assert plan.changed is False
    assert plan.last_terminal_size == (80, 24)
    assert plan.reflow == TerminalResizeReflowPlan("none", pending=True)


def test_plan_terminal_size_change_reflow_replays_or_defers_changed_size() -> None:
    replay = plan_terminal_size_change_reflow(
        previous_size=(80, 24),
        current_size=(100, 30),
        active_stream=False,
    )
    deferred = plan_terminal_size_change_reflow(
        previous_size=(80, 24),
        current_size=(100, 30),
        active_stream=True,
    )

    assert replay.changed is True
    assert replay.last_terminal_size == (100, 30)
    assert replay.reflow == TerminalResizeReflowPlan("replay_history_scrollback")
    assert deferred.changed is True
    assert deferred.last_terminal_size == (100, 30)
    assert deferred.reflow == TerminalResizeReflowPlan("defer_until_stream_finish", pending=True)


def test_terminal_resize_runtime_state_tracks_app_owned_size_and_guard() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow handles resize replay decisions while
    #   App-owned draw-size state prevents recursive resize repairs.
    inactive = TerminalResizeRuntimeState.inactive()
    active = inactive.activated((80, 24))
    handling = active.begin_handling()
    finished = handling.end_handling()

    assert inactive.last_terminal_size is None
    assert inactive.handling_resize is False
    assert active.last_terminal_size == (80, 24)
    assert active.handling_resize is False
    assert handling.last_terminal_size == (80, 24)
    assert handling.handling_resize is True
    assert finished == active
    assert active.deactivated() == inactive


def test_terminal_resize_runtime_state_applies_size_plan_without_dropping_guard() -> None:
    state = TerminalResizeRuntimeState.inactive().activated((80, 24)).begin_handling()
    plan = plan_terminal_size_change_reflow(
        previous_size=(80, 24),
        current_size=(100, 30),
        active_stream=False,
    )

    next_state = state.after_size_plan(plan)

    assert next_state.last_terminal_size == (100, 30)
    assert next_state.handling_resize is True


def test_run_terminal_layout_activation_sets_size_and_renders_bottom_pane() -> None:
    # Rust source contract:
    # - codex-tui::app owns draw-size/layout lifecycle state while bottom_pane
    #   redraw is the terminal-side effect supplied by the runner.
    calls: list[str] = []
    inactive = TerminalResizeRuntimeState.inactive()

    layout_active, state = run_terminal_layout_activation(
        terminal_active=True,
        state=inactive,
        current_size=(80, 24),
        render_bottom_pane=lambda: calls.append("render"),
    )
    skipped_active, skipped_state = run_terminal_layout_activation(
        terminal_active=False,
        state=state,
        current_size=(100, 30),
        render_bottom_pane=lambda: calls.append("skipped-render"),
    )

    assert layout_active is True
    assert state.last_terminal_size == (80, 24)
    assert state.handling_resize is False
    assert skipped_active is False
    assert skipped_state == state
    assert calls == ["render"]


def test_run_terminal_layout_deactivation_resets_scroll_region_and_state() -> None:
    # Rust source contract:
    # - leaving the terminal layout resets the terminal scroll region through
    #   custom_terminal while app::resize_reflow owns resize-state teardown.
    calls: list[str] = []
    active = TerminalResizeRuntimeState.inactive().activated((80, 24))

    layout_active, state = run_terminal_layout_deactivation(
        terminal_active=True,
        state=active,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
    )
    skipped_active, skipped_state = run_terminal_layout_deactivation(
        terminal_active=False,
        state=active,
        reset_terminal_scroll_region=lambda: calls.append("skipped-reset"),
    )

    assert layout_active is False
    assert state == TerminalResizeRuntimeState.inactive()
    assert skipped_active is False
    assert skipped_state == active
    assert calls == ["reset"]


def test_plan_terminal_stream_finish_reflow_repairs_deferred_resize_once() -> None:
    repair = plan_terminal_stream_finish_reflow(pending=True)
    idle = plan_terminal_stream_finish_reflow(pending=False)

    assert repair.action == "replay_history_scrollback"
    assert repair.pending is False
    assert idle.action == "repaint_history_viewport"
    assert idle.pending is False


def test_run_terminal_resize_reflow_plan_dispatches_terminal_actions() -> None:
    calls: list[str] = []

    assert run_terminal_resize_reflow_plan(
        TerminalResizeReflowPlan("repaint_history_viewport"),
        repaint_history_viewport=lambda: calls.append("repaint"),
        replay_history_scrollback=lambda: calls.append("replay"),
    )
    assert calls == ["repaint"]

    assert run_terminal_resize_reflow_plan(
        TerminalResizeReflowPlan("replay_history_scrollback"),
        repaint_history_viewport=lambda: calls.append("repaint"),
        replay_history_scrollback=lambda: calls.append("replay"),
    )
    assert calls == ["repaint", "replay"]

    assert not run_terminal_resize_reflow_plan(
        TerminalResizeReflowPlan("none"),
        repaint_history_viewport=lambda: calls.append("repaint"),
        replay_history_scrollback=lambda: calls.append("replay"),
    )
    assert calls == ["repaint", "replay"]


def test_run_terminal_size_change_reflow_ignores_inactive_or_guarded_path() -> None:
    # Rust owner: codex-tui::app::resize_reflow guards resize work outside the
    # active terminal surface and during recursive resize handling; the runner
    # should only supply observed state and side-effect callbacks.
    calls: list[str] = []
    active = TerminalResizeRuntimeState.inactive().activated((80, 24))
    guarded = active.begin_handling()

    inactive_state, inactive_pending = run_terminal_size_change_reflow(
        terminal_active=False,
        state=active,
        current_size=(100, 30),
        active_stream=False,
        pending=True,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )
    guarded_state, guarded_pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=guarded,
        current_size=(100, 30),
        active_stream=False,
        pending=True,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )

    assert inactive_state == active
    assert inactive_pending is True
    assert guarded_state == guarded
    assert guarded_pending is True
    assert calls == []


def test_run_terminal_size_change_reflow_initializes_without_replay() -> None:
    calls: list[str] = []

    state, pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=TerminalResizeRuntimeState.inactive(),
        current_size=(80, 24),
        active_stream=False,
        pending=True,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )

    assert state.last_terminal_size == (80, 24)
    assert state.handling_resize is False
    assert pending is True
    assert calls == []


def test_run_terminal_size_change_reflow_defers_active_stream_resize() -> None:
    calls: list[str] = []

    state, pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=TerminalResizeRuntimeState.inactive().activated((80, 24)),
        current_size=(100, 30),
        active_stream=True,
        pending=False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )

    assert state.last_terminal_size == (100, 30)
    assert state.handling_resize is False
    assert pending is True
    assert calls == ["defer_until_stream_finish"]


def test_run_terminal_size_change_reflow_resets_then_replays_changed_size() -> None:
    calls: list[str] = []

    state, pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=TerminalResizeRuntimeState.inactive().activated((80, 24)),
        current_size=(100, 30),
        active_stream=False,
        pending=True,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )

    assert state.last_terminal_size == (100, 30)
    assert state.handling_resize is False
    assert pending is False
    assert calls == ["reset", "replay_history_scrollback"]


def test_run_terminal_size_change_reflow_syncs_handling_guard_around_replay() -> None:
    calls: list[str] = []

    state, pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=TerminalResizeRuntimeState.inactive().activated((80, 24)),
        current_size=(100, 30),
        active_stream=False,
        pending=False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
        enter_resize_handling=lambda state: calls.append(f"enter:{state.handling_resize}"),
        exit_resize_handling=lambda state: calls.append(f"exit:{state.handling_resize}"),
    )

    assert state.last_terminal_size == (100, 30)
    assert state.handling_resize is False
    assert pending is False
    assert calls == ["enter:True", "reset", "replay_history_scrollback", "exit:False"]


def test_terminal_resize_coordinator_owns_layout_lifecycle_state() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns terminal resize/layout
    # lifecycle state; tui::terminal_runtime supplies only environment effects.
    calls: list[str] = []
    size = {"value": (80, 24)}
    coordinator = TerminalResizeCoordinator(
        terminal_active=lambda: True,
        current_size=lambda: size["value"],
        active_stream=lambda: False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        render_bottom_pane=lambda: calls.append("render"),
        repaint_history_viewport=lambda: calls.append("repaint"),
        replay_history_scrollback=lambda: calls.append("replay"),
    )

    coordinator.activate_layout()
    size["value"] = (100, 30)
    coordinator.check_size_change()
    coordinator.deactivate_layout()

    assert coordinator.layout_active is False
    assert coordinator.state == TerminalResizeRuntimeState.inactive()
    assert coordinator.pending is False
    assert calls == ["render", "reset", "replay", "reset"]


def test_terminal_resize_coordinator_defers_stream_resize_until_finish() -> None:
    calls: list[str] = []
    size = {"value": (80, 24)}
    stream = {"active": True}
    coordinator = TerminalResizeCoordinator(
        terminal_active=lambda: True,
        current_size=lambda: size["value"],
        active_stream=lambda: stream["active"],
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        render_bottom_pane=lambda: calls.append("render"),
        repaint_history_viewport=lambda: calls.append("repaint"),
        replay_history_scrollback=lambda: calls.append("replay"),
    )

    coordinator.activate_layout()
    size["value"] = (100, 30)
    coordinator.check_size_change()
    stream["active"] = False
    coordinator.run_stream_finish_reflow()

    assert coordinator.layout_active is True
    assert coordinator.state.last_terminal_size == (100, 30)
    assert coordinator.pending is False
    assert calls == ["render", "replay"]


def test_terminal_resize_coordinator_dispatches_bottom_pane_footprint_reflow() -> None:
    calls: list[str] = []
    coordinator = TerminalResizeCoordinator(
        terminal_active=lambda: True,
        current_size=lambda: os.terminal_size((80, 24)),
        active_stream=lambda: False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        render_bottom_pane=lambda: calls.append("render"),
        repaint_history_viewport=lambda: calls.append("repaint"),
        replay_history_scrollback=lambda: calls.append("replay"),
    )
    coordinator.activate_layout()

    ran = coordinator.run_bottom_pane_footprint_reflow(
        previous=TerminalLiveStatusSurface.inactive(),
        current=TerminalLiveStatusSurface.active_status("\u2022 Working"),
    )

    assert ran is True
    assert coordinator.pending is False
    assert calls == ["render", "repaint"]


def test_terminal_resize_history_replayer_repaints_viewport_from_live_state() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns retained-history viewport
    # repair while tui.rs supplies terminal effects and current layout state.
    writer = FlushTrackingStringIO()
    state = {"history": TerminalHistoryState(projection_cells=("old", "new"))}
    calls: list[str] = []

    replayer = TerminalResizeHistoryReplayer(
        writer,
        history_state=lambda: state["history"],
        history_wrap_width=lambda: 20,
        terminal_active=lambda: True,
        live_status_footprint_active=lambda: False,
        history_bottom_row=lambda: calls.append("bottom") or 1,
        terminal_columns=lambda: calls.append("columns") or 20,
        insert_replayed_history_lines=lambda lines, reserve: calls.append("insert"),
        apply_history_state=lambda next_state: calls.append("apply"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert replayer.repaint_viewport() is True

    assert calls == ["bottom", "columns"]
    assert writer.flush_count == 1
    assert "old" not in writer.getvalue()
    assert "\x1b[1;1Hnew" in writer.getvalue()


def test_terminal_resize_history_replayer_repaints_active_stream_projection() -> None:
    # Rust owner: codex-tui::app::resize_reflow repairs the current viewport
    # from retained history plus the active assistant stream projection while
    # bottom_pane restores ownership of live rows.
    writer = FlushTrackingStringIO()
    state = {"history": TerminalHistoryState(projection_cells=("\u203a question",))}
    calls: list[str] = []

    replayer = TerminalResizeHistoryReplayer(
        writer,
        history_state=lambda: state["history"],
        history_wrap_width=lambda: 40,
        terminal_active=lambda: True,
        live_status_footprint_active=lambda: False,
        history_bottom_row=lambda: 4,
        terminal_columns=lambda: 40,
        insert_replayed_history_lines=lambda lines, reserve: calls.append("insert"),
        apply_history_state=lambda next_state: calls.append("apply"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert replayer.repaint_viewport("\u2022 partial") is True

    output = writer.getvalue()
    assert "\u203a question" in output
    assert "\u2022 partial" in output
    assert state["history"].projection_cells == ("\u203a question",)
    assert calls == ["render"]


def test_terminal_resize_history_replayer_replays_scrollback_with_status_reservation() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns resize replay ordering:
    # reset stale insert-history markers, clear terminal scrollback, replay
    # retained projection rows, then restore the bottom-pane surface.
    writer = FlushTrackingStringIO()
    state = TerminalHistoryState(
        history_has_content=True,
        history_ended_with_blank=True,
        projection_cells=("old", "new"),
    )
    applied: list[TerminalHistoryState] = []
    calls: list[object] = []

    replayer = TerminalResizeHistoryReplayer(
        writer,
        history_state=lambda: state,
        history_wrap_width=lambda: 20,
        terminal_active=lambda: True,
        live_status_footprint_active=lambda: True,
        history_bottom_row=lambda: 1,
        terminal_columns=lambda: 20,
        insert_replayed_history_lines=lambda lines, reserve: calls.append(("insert", lines, reserve)),
        apply_history_state=lambda next_state: (applied.append(next_state), calls.append("apply")),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert replayer.replay_scrollback() is True

    assert writer.flush_count == 1
    assert applied[0].history_has_content is False
    assert applied[0].history_ended_with_blank is False
    assert applied[0].projection_cells == ("old", "new")
    assert calls == ["apply", ("insert", ["old", "", "new"], True), "render"]
