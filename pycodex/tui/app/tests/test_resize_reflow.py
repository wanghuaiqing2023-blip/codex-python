from pycodex.tui.app.resize_reflow import (
    HistoryCell,
    HistoryLineWrapPolicy,
    HyperlinkLine,
    InitialHistoryReplayBuffer,
    ResizeReflowPlan,
    ResizeReflowState,
    TerminalBottomPaneFootprintRenderPass,
    TerminalBottomPaneFootprintTracker,
    TerminalResizeCoordinator,
    TerminalResizeHistoryReplayer,
    TerminalResizeReflowPlan,
    TerminalResizeRuntimeState,
    begin_initial_history_replay_buffer_plan,
    begin_thread_switch_history_replay_buffer_plan,
    bottom_pane_footprint_transition,
    bottom_pane_footprint_transition_for_footprints,
    buffer_initial_history_replay_display_lines,
    create_terminal_bottom_pane_footprint_cycle_runner,
    create_terminal_bottom_pane_footprint_tracker,
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
    render_terminal_typed_transcript_lines,
    replay_terminal_history_state_scrollback_for_resize_width,
    render_transcript_lines_for_reflow,
    reflow_transcript_now,
    reset_history_emission_state,
    run_terminal_bottom_pane_footprint_clear_cycle,
    run_terminal_bottom_pane_footprint_external_repaint,
    run_terminal_bottom_pane_footprint_render_cycle,
    run_terminal_bottom_pane_footprint_render_cycle_for_context,
    run_terminal_bottom_pane_footprint_render_cycle_for_view_state,
    run_terminal_bottom_pane_footprint_reflow,
    run_terminal_layout_activation,
    run_terminal_layout_deactivation,
    run_terminal_history_state_viewport_repaint_for_width,
    run_terminal_history_state_scrollback_replay_for_resize_width,
    run_terminal_history_state_scrollback_replay_insert_for_resize_width,
    run_terminal_resize_reflow_plan,
    run_terminal_size_change_reflow,
    should_mark_reflow_as_stream_time,
    terminal_history_bottom_row,
    terminal_history_bottom_row_for_context,
    terminal_history_bottom_row_for_view_state,
    terminal_history_state_for_resize_replay,
    trailing_run_start,
)
from pycodex.tui.bottom_pane.terminal_footprint import TerminalBottomPaneFootprint
from pycodex.tui.chatwidget.status_surfaces import TerminalLiveStatusSurface
from pycodex.tui.insert_history import TerminalHistoryState
from pycodex.tui.history_cell.messages import AgentMarkdownCell, new_user_prompt

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


def test_terminal_history_bottom_row_tracks_live_viewport_footprint() -> None:
    # Rust owners: codex-tui::insert_history writes history above the inline
    # viewport, and app::resize_reflow rebuilds that viewport after bottom-pane
    # footprint changes. Python keeps the same boundary as a history/reflow
    # calculation rather than a bottom-pane frame projection.
    size = os.terminal_size((80, 24))

    assert terminal_history_bottom_row(size, live_status_active=False) == 20
    assert terminal_history_bottom_row(size, live_status_active=True) == 18
    assert terminal_history_bottom_row(size, live_status_active=False, popup_height=3) == 19
    assert terminal_history_bottom_row(size, live_status_active=True, popup_height=3) == 18
    assert terminal_history_bottom_row(size, live_status_active=False, reserve_active_bottom_pane=True) == 18

    class RenderContext:
        popup_height = 3

    assert (
        terminal_history_bottom_row_for_context(
            size,
            live_status=TerminalLiveStatusSurface.inactive(),
            bottom_pane_context=RenderContext(),
        )
        == 19
    )
    assert (
        terminal_history_bottom_row_for_context(
            size,
            live_status=TerminalLiveStatusSurface.active_status("working"),
            bottom_pane_context=RenderContext(),
        )
        == 18
    )
    assert (
        terminal_history_bottom_row_for_context(
            size,
            live_status=TerminalLiveStatusSurface.inactive(),
            bottom_pane_context=RenderContext(),
            reserve_active_bottom_pane=True,
        )
        == 18
    )

    class RenderContextProvider:
        def __init__(self) -> None:
            self.calls: list[tuple[os.terminal_size, bool]] = []

        def render_context_for_size(self, provider_size, composer_cursor_visible):
            self.calls.append((provider_size, composer_cursor_visible()))
            return RenderContext()

    provider = RenderContextProvider()
    assert (
        terminal_history_bottom_row_for_view_state(
            size,
            live_status=TerminalLiveStatusSurface.inactive(),
            bottom_pane_state=provider,
            composer_cursor_visible=lambda: True,
        )
        == 19
    )
    assert provider.calls == [(size, True)]


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


def test_bottom_pane_footprint_transition_maps_live_rows_for_reflow() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow consumes bottom-pane footprint changes
    #   as affected live rows before planning retained-history repaint.
    # - bottom_pane supplies compact footprint values; transition comparison
    #   and changed/no-op detection belong to resize_reflow.
    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")

    grow = bottom_pane_footprint_transition(size, inactive, active)
    same = bottom_pane_footprint_transition(size, active, TerminalLiveStatusSurface.active_status("\u2022 Thinking"))
    shrink = bottom_pane_footprint_transition(size, active, inactive)
    popup = bottom_pane_footprint_transition_for_footprints(
        size,
        TerminalBottomPaneFootprint(live_status_active=False, popup_height=0),
        TerminalBottomPaneFootprint(live_status_active=False, popup_height=4),
    )

    assert grow.old_rows == (21, 22, 23, 24)
    assert grow.new_rows == (19, 20, 21, 22, 23, 24)
    assert grow.changed
    assert not same.changed
    assert shrink.changed
    assert popup.old_rows == (21, 22, 23, 24)
    assert popup.new_rows == (19, 20, 21, 22, 23, 24)
    assert popup.changed


def test_bottom_pane_footprint_tracker_plans_active_view_reflow_timing() -> None:
    # Rust source contract:
    # - codex-tui::bottom_pane owns the desired active BottomPaneView footprint.
    # - codex-tui::app::resize_reflow owns grow/shrink repaint timing so
    #   transcript history remains visible around live-pane footprint changes.
    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    tracker = TerminalBottomPaneFootprintTracker()

    slash_popup = tracker.plan_reflow(size, inactive, popup_height=3, popup_is_active_view=False)
    assert not slash_popup.repaint_needed

    grow = tracker.plan_reflow(size, inactive, popup_height=4, popup_is_active_view=True)
    assert grow.previous == TerminalBottomPaneFootprint(live_status_active=False, popup_height=0)
    assert grow.current == TerminalBottomPaneFootprint(live_status_active=False, popup_height=4)
    assert grow.repaint_before_render
    assert not grow.repaint_after_render

    tracker.update_after_render(inactive, popup_height=4, popup_is_active_view=True)
    shrink = tracker.plan_reflow(size, inactive, popup_height=0, popup_is_active_view=False)
    assert shrink.previous == TerminalBottomPaneFootprint(live_status_active=False, popup_height=4)
    assert shrink.current == TerminalBottomPaneFootprint(live_status_active=False, popup_height=0)
    assert not shrink.repaint_before_render
    assert shrink.repaint_after_render


def test_create_terminal_bottom_pane_footprint_tracker_keeps_tracker_state_in_owner() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns bottom-pane footprint
    # tracker state construction; terminal controllers should request the
    # owner-managed tracker instead of instantiating repaint state directly.
    tracker = create_terminal_bottom_pane_footprint_tracker()

    assert isinstance(tracker, TerminalBottomPaneFootprintTracker)
    assert tracker.previous() == TerminalBottomPaneFootprint(live_status_active=False, popup_height=0)


def test_bottom_pane_footprint_tracker_runs_render_cycle_around_reflow() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns before/after history repaint timing
    #   for bottom-pane footprint changes.
    # - Terminal controllers supply repaint/render callbacks instead of
    #   duplicating the sequencing.
    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    tracker = TerminalBottomPaneFootprintTracker()
    calls: list[str] = []

    rendered = tracker.render_with_reflow(
        size,
        inactive,
        popup_height=4,
        popup_is_active_view=True,
        repaint=lambda previous, current: calls.append(f"repaint:{previous.popup_height}->{current.popup_height}"),
        render=lambda: calls.append("render") or True,
        render_after_repaint=lambda: calls.append("rerender") or True,
    )

    assert rendered is True
    assert calls == ["repaint:0->4", "render"]
    assert tracker.popup_height == 4
    assert tracker.popup_was_active_view is True

    calls.clear()

    rendered = tracker.render_with_reflow(
        size,
        inactive,
        popup_height=0,
        popup_is_active_view=False,
        repaint=lambda previous, current: calls.append(f"repaint:{previous.popup_height}->{current.popup_height}"),
        render=lambda: calls.append("render") or True,
        render_after_repaint=lambda: calls.append("rerender") or True,
    )

    assert rendered is True
    assert calls == ["render", "repaint:4->0", "rerender"]
    assert tracker.popup_height == 0
    assert tracker.popup_was_active_view is False


def test_bottom_pane_footprint_tracker_supplies_render_passes_for_controller() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns before/after history repaint timing
    #   for bottom-pane footprint changes.
    # - Python's hybrid controller supplies the concrete render callback, but
    #   resize_reflow owns which live-pane footprint the first and follow-up
    #   render must clear.
    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    tracker = TerminalBottomPaneFootprintTracker()
    calls: list[str] = []
    passes: list[TerminalBottomPaneFootprintRenderPass] = []

    def render(pass_state: TerminalBottomPaneFootprintRenderPass) -> bool:
        passes.append(pass_state)
        calls.append("render")
        return True

    assert tracker.render_with_reflow_passes(
        size,
        inactive,
        popup_height=4,
        popup_is_active_view=True,
        check_resize=True,
        repaint=lambda previous, current: calls.append(f"repaint:{previous.popup_height}->{current.popup_height}"),
        render=render,
    )

    assert calls == ["repaint:0->4", "render"]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=True,
            clear_popup_height=0,
            clear_live_status_active=False,
        )
    ]

    calls.clear()
    passes.clear()

    assert tracker.render_with_reflow_passes(
        size,
        inactive,
        popup_height=0,
        popup_is_active_view=False,
        check_resize=True,
        repaint=lambda previous, current: calls.append(f"repaint:{previous.popup_height}->{current.popup_height}"),
        render=render,
    )

    assert calls == ["render", "repaint:4->0", "render"]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=True,
            clear_popup_height=4,
            clear_live_status_active=False,
        ),
        TerminalBottomPaneFootprintRenderPass(
            check_resize=False,
            clear_popup_height=0,
            clear_live_status_active=False,
        ),
    ]


def test_bottom_pane_footprint_cycle_runner_builds_history_bottom_row_callback() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns history viewport bounds
    # above the inline bottom pane. Terminal controllers should bind their
    # terminal-size/live-status/bottom-pane-state providers once and consume
    # this owner callback instead of collecting those values locally.
    class Context:
        def __init__(self, popup_height: int) -> None:
            self.popup_height = popup_height
            self.popup_is_active_view = False

    class PaneState:
        def __init__(self) -> None:
            self.popup_height = 3
            self.calls: list[tuple[os.terminal_size, bool]] = []

        def render_context_for_size(self, size, composer_cursor_visible):
            visible = composer_cursor_visible()
            self.calls.append((size, visible))
            return Context(self.popup_height if visible else 0)

    size = [os.terminal_size((80, 24))]
    live_status = [TerminalLiveStatusSurface.inactive()]
    cursor_visible = [True]
    pane_state = PaneState()
    runner = create_terminal_bottom_pane_footprint_cycle_runner()
    history_bottom_row = runner.history_bottom_row_callback(
        terminal_size=lambda: size[0],
        live_status=lambda: live_status[0],
        bottom_pane_state=pane_state,
        composer_cursor_visible=lambda: cursor_visible[0],
    )

    assert history_bottom_row() == terminal_history_bottom_row_for_view_state(
        size[0],
        live_status=live_status[0],
        bottom_pane_state=pane_state,
        composer_cursor_visible=lambda: cursor_visible[0],
    )
    assert history_bottom_row(True) == terminal_history_bottom_row(
        size[0],
        live_status_active=False,
        popup_height=0,
        reserve_active_bottom_pane=True,
    )

    size[0] = os.terminal_size((80, 30))
    pane_state.popup_height = 0
    cursor_visible[0] = False

    assert history_bottom_row() == terminal_history_bottom_row(
        size[0],
        live_status_active=False,
        popup_height=0,
    )
    assert pane_state.calls[-1] == (os.terminal_size((80, 30)), False)


def test_bottom_pane_footprint_cycle_runner_builds_clear_callback() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns the remembered bottom-pane
    # footprint reset after a live-pane clear. Terminal controllers should bind
    # a clear callback once and supply only the terminal-projection clear
    # factory.
    live_status = [TerminalLiveStatusSurface.active_status("working")]
    calls: list[str] = []
    runner = create_terminal_bottom_pane_footprint_cycle_runner()
    runner.tracker.live_status_active = True
    runner.tracker.popup_height = 4
    runner.tracker.active_tail_height = 3
    runner.tracker.composer_height = 2

    def clear_factory(
        status: TerminalLiveStatusSurface,
        check_resize: bool,
        footprint: TerminalBottomPaneFootprint,
    ):
        calls.append(f"factory:{status.active}:{check_resize}")
        calls.append(f"footprint:{footprint}")

        def clear() -> bool:
            calls.append("clear")
            return True

        return clear

    clear = runner.clear_callback(
        live_status=lambda: live_status[0],
        clear_factory=clear_factory,
    )

    assert clear(False) is True

    assert calls == [
        "factory:True:False",
        "footprint:TerminalBottomPaneFootprint(live_status_active=True, popup_height=4, "
        "active_tail_height=3, composer_height=2)",
        "clear",
    ]
    assert runner.tracker.previous() == TerminalBottomPaneFootprint()


def test_bottom_pane_footprint_cycle_runner_builds_render_for_view_state_callback() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns bottom-pane footprint
    # render-cycle timing. Terminal controllers should bind size/status/state
    # providers once and supply only a terminal-projection render-pass factory.
    class Context:
        popup_height = 3
        popup_is_active_view = True

    class PaneState:
        def __init__(self) -> None:
            self.calls: list[tuple[os.terminal_size, bool]] = []

        def render_context_for_size(self, size, composer_cursor_visible):
            visible = composer_cursor_visible()
            self.calls.append((size, visible))
            return Context()

    size = [os.terminal_size((80, 24))]
    live_status = [TerminalLiveStatusSurface.inactive()]
    cursor_visible = [False]
    pane_state = PaneState()
    calls: list[str] = []
    passes: list[TerminalBottomPaneFootprintRenderPass] = []
    runner = create_terminal_bottom_pane_footprint_cycle_runner()

    def render_factory(status: TerminalLiveStatusSurface, clear_external_blank_rows: bool):
        calls.append(f"factory:{status.active}:{clear_external_blank_rows}")

        def render(pass_state, context) -> bool:
            passes.append(pass_state)
            calls.append(f"render:{context.popup_height}")
            return True

        return render

    def run_external_repaint(repaint):
        calls.append("external:start")
        repaint()
        calls.append("external:done")

    render_for_view_state = runner.render_for_view_state_callback(
        terminal_size=lambda: size[0],
        live_status=lambda: live_status[0],
        bottom_pane_state=pane_state,
        composer_cursor_visible=lambda: cursor_visible[0],
        repaint_footprint=lambda previous, current: calls.append(
            f"repaint:{previous.popup_height}->{current.popup_height}"
        ),
        run_external_repaint=run_external_repaint,
        render_factory=render_factory,
    )

    assert render_for_view_state(check_resize=False, clear_external_blank_rows=True)

    assert pane_state.calls == [(os.terminal_size((80, 24)), False)]
    assert calls == [
        "factory:False:True",
        "external:start",
        "repaint:0->3",
        "external:done",
        "render:3",
    ]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=False,
            clear_popup_height=0,
            clear_live_status_active=False,
        )
    ]


def test_bottom_pane_footprint_clear_cycle_updates_tracker_only_after_clear() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns the remembered bottom-pane
    #   footprint used by future history repaint decisions.
    # - Terminal controllers supply the concrete clear callback; they do not
    #   update tracker state directly.
    tracker = TerminalBottomPaneFootprintTracker(
        live_status_active=True,
        popup_height=3,
        popup_was_active_view=True,
    )
    calls: list[str] = []

    assert not run_terminal_bottom_pane_footprint_clear_cycle(
        tracker,
        lambda: calls.append("skip") or False,
    )
    assert calls == ["skip"]
    assert tracker.live_status_active is True
    assert tracker.popup_height == 3
    assert tracker.popup_was_active_view is True

    assert run_terminal_bottom_pane_footprint_clear_cycle(
        tracker,
        lambda: calls.append("clear") or True,
    )
    assert calls == ["skip", "clear"]
    assert tracker.live_status_active is False
    assert tracker.popup_height == 0


def test_bottom_pane_footprint_external_repaint_uses_resize_owner_lifecycle() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns no-op detection and external repaint
    #   dispatch around bottom-pane footprint changes.
    # - Terminal controllers supply callbacks; they do not own the branching.
    previous = TerminalBottomPaneFootprint(live_status_active=False, popup_height=0)
    same = TerminalBottomPaneFootprint(live_status_active=False, popup_height=0)
    current = TerminalBottomPaneFootprint(live_status_active=False, popup_height=4)
    calls: list[str] = []

    def run_external_repaint(repaint):
        calls.append("external:start")
        repaint()
        calls.append("external:done")

    def repaint(prev: TerminalBottomPaneFootprint, cur: TerminalBottomPaneFootprint) -> None:
        calls.append(f"repaint:{prev.popup_height}->{cur.popup_height}")

    assert not run_terminal_bottom_pane_footprint_external_repaint(
        previous,
        current,
        None,
        run_external_repaint=run_external_repaint,
    )
    assert not run_terminal_bottom_pane_footprint_external_repaint(
        previous,
        same,
        repaint,
        run_external_repaint=run_external_repaint,
    )
    assert calls == []

    assert run_terminal_bottom_pane_footprint_external_repaint(
        previous,
        current,
        repaint,
        run_external_repaint=run_external_repaint,
    )
    assert calls == ["external:start", "repaint:0->4", "external:done"]


def test_bottom_pane_footprint_render_cycle_wraps_external_repaint_lifecycle() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns bottom-pane footprint repaint
    #   timing around live-pane renders.
    # - Python controllers supply callbacks; resize_reflow owns the external
    #   repaint lifecycle and follow-up render pass parameters.
    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    tracker = TerminalBottomPaneFootprintTracker()
    calls: list[str] = []
    passes: list[TerminalBottomPaneFootprintRenderPass] = []

    def run_external_repaint(repaint):
        calls.append("external:start")
        repaint()
        calls.append("external:done")

    def repaint(prev: TerminalBottomPaneFootprint, cur: TerminalBottomPaneFootprint) -> None:
        calls.append(f"repaint:{prev.popup_height}->{cur.popup_height}")

    def render(pass_state: TerminalBottomPaneFootprintRenderPass) -> bool:
        passes.append(pass_state)
        calls.append("render")
        return True

    assert run_terminal_bottom_pane_footprint_render_cycle(
        tracker,
        size,
        inactive,
        popup_height=4,
        popup_is_active_view=True,
        check_resize=True,
        render=render,
        repaint_footprint=repaint,
        run_external_repaint=run_external_repaint,
    )

    assert calls == ["external:start", "repaint:0->4", "external:done", "render"]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=True,
            clear_popup_height=0,
            clear_live_status_active=False,
        )
    ]

    calls.clear()
    passes.clear()

    assert run_terminal_bottom_pane_footprint_render_cycle(
        tracker,
        size,
        inactive,
        popup_height=0,
        popup_is_active_view=False,
        check_resize=True,
        render=render,
        repaint_footprint=repaint,
        run_external_repaint=run_external_repaint,
    )

    assert calls == ["render", "external:start", "repaint:4->0", "external:done", "render"]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=True,
            clear_popup_height=4,
            clear_live_status_active=False,
        ),
        TerminalBottomPaneFootprintRenderPass(
            check_resize=False,
            clear_popup_height=0,
            clear_live_status_active=False,
        ),
    ]


def test_bottom_pane_footprint_render_cycle_for_context_reads_popup_footprint() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns bottom-pane footprint repaint
    #   timing.
    # - Terminal controllers pass the bottom-pane render context through this
    #   owner boundary instead of reading popup footprint fields locally.
    class RenderContext:
        popup_height = 3
        popup_is_active_view = True

    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    tracker = TerminalBottomPaneFootprintTracker()
    calls: list[str] = []
    passes: list[TerminalBottomPaneFootprintRenderPass] = []

    def run_external_repaint(repaint):
        calls.append("external:start")
        repaint()
        calls.append("external:done")

    def repaint(prev: TerminalBottomPaneFootprint, cur: TerminalBottomPaneFootprint) -> None:
        calls.append(f"repaint:{prev.popup_height}->{cur.popup_height}")

    def render(pass_state: TerminalBottomPaneFootprintRenderPass) -> bool:
        passes.append(pass_state)
        calls.append("render")
        return True

    assert run_terminal_bottom_pane_footprint_render_cycle_for_context(
        tracker,
        size,
        inactive,
        bottom_pane_context=RenderContext(),
        check_resize=False,
        render=render,
        repaint_footprint=repaint,
        run_external_repaint=run_external_repaint,
    )

    assert calls == ["external:start", "repaint:0->3", "external:done", "render"]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=False,
            clear_popup_height=0,
            clear_live_status_active=False,
        )
    ]
    assert tracker.previous() == TerminalBottomPaneFootprint(
        live_status_active=False,
        popup_height=3,
    )


def test_bottom_pane_footprint_render_cycle_for_view_state_projects_context_once() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns the bottom-pane footprint render
    #   cycle and consumes the bottom-pane render context for repaint timing.
    # - Terminal controllers provide owner state and render callbacks, but they
    #   should not decide when to fetch the context from the bottom-pane owner.
    class RenderContext:
        popup_height = 2
        popup_is_active_view = True

    class RenderContextProvider:
        def __init__(self) -> None:
            self.context = RenderContext()
            self.calls: list[tuple[os.terminal_size, bool]] = []

        def render_context_for_size(self, provider_size, composer_cursor_visible):
            self.calls.append((provider_size, composer_cursor_visible()))
            return self.context

    size = os.terminal_size((80, 24))
    provider = RenderContextProvider()
    inactive = TerminalLiveStatusSurface.inactive()
    tracker = TerminalBottomPaneFootprintTracker()
    calls: list[str] = []
    contexts: list[object] = []
    passes: list[TerminalBottomPaneFootprintRenderPass] = []

    def run_external_repaint(repaint):
        calls.append("external:start")
        repaint()
        calls.append("external:done")

    def repaint(prev: TerminalBottomPaneFootprint, cur: TerminalBottomPaneFootprint) -> None:
        calls.append(f"repaint:{prev.popup_height}->{cur.popup_height}")

    def render(pass_state: TerminalBottomPaneFootprintRenderPass, context: object) -> bool:
        passes.append(pass_state)
        contexts.append(context)
        calls.append("render")
        return True

    assert run_terminal_bottom_pane_footprint_render_cycle_for_view_state(
        tracker,
        size,
        inactive,
        bottom_pane_state=provider,
        composer_cursor_visible=lambda: True,
        check_resize=False,
        render=render,
        repaint_footprint=repaint,
        run_external_repaint=run_external_repaint,
    )

    assert provider.calls == [(size, True)]
    assert contexts == [provider.context]
    assert calls == ["external:start", "repaint:0->2", "external:done", "render"]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=False,
            clear_popup_height=0,
            clear_live_status_active=False,
        )
    ]
    assert tracker.previous() == TerminalBottomPaneFootprint(
        live_status_active=False,
        popup_height=2,
    )


def test_bottom_pane_footprint_cycle_runner_owns_tracker_state_for_controller() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow owns the stateful bottom-pane footprint
    #   lifecycle used by terminal controllers.
    # - Controllers provide owner state and callbacks through a semantic
    #   runner instead of holding the raw tracker and calling low-level cycle
    #   helpers themselves.
    class RenderContext:
        popup_height = 3
        popup_is_active_view = True

    class RenderContextProvider:
        def __init__(self) -> None:
            self.context = RenderContext()
            self.calls: list[tuple[os.terminal_size, bool]] = []

        def render_context_for_size(self, provider_size, composer_cursor_visible):
            self.calls.append((provider_size, composer_cursor_visible()))
            return self.context

    runner = create_terminal_bottom_pane_footprint_cycle_runner()
    provider = RenderContextProvider()
    size = os.terminal_size((80, 24))
    calls: list[str] = []
    passes: list[TerminalBottomPaneFootprintRenderPass] = []

    def run_external_repaint(repaint):
        calls.append("external:start")
        repaint()
        calls.append("external:done")

    def repaint(prev: TerminalBottomPaneFootprint, cur: TerminalBottomPaneFootprint) -> None:
        calls.append(f"repaint:{prev.popup_height}->{cur.popup_height}")

    def render(pass_state: TerminalBottomPaneFootprintRenderPass, context: object) -> bool:
        passes.append(pass_state)
        calls.append(f"render:{context.popup_height}")
        return True

    assert runner.history_bottom_row(
        size,
        live_status=TerminalLiveStatusSurface.inactive(),
        bottom_pane_state=provider,
        composer_cursor_visible=lambda: True,
    ) == 19

    assert runner.render_for_view_state(
        size,
        TerminalLiveStatusSurface.inactive(),
        bottom_pane_state=provider,
        composer_cursor_visible=lambda: True,
        check_resize=False,
        render=render,
        repaint_footprint=repaint,
        run_external_repaint=run_external_repaint,
    )

    assert provider.calls == [(size, True), (size, True)]
    assert calls == ["external:start", "repaint:0->3", "external:done", "render:3"]
    assert passes == [
        TerminalBottomPaneFootprintRenderPass(
            check_resize=False,
            clear_popup_height=0,
            clear_live_status_active=False,
        )
    ]
    assert runner.tracker.previous() == TerminalBottomPaneFootprint(
        live_status_active=False,
        popup_height=3,
    )

    assert runner.clear(lambda: calls.append("clear") or True)
    assert runner.tracker.previous() == TerminalBottomPaneFootprint()


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


def test_typed_transcript_reflow_rerenders_markdown_source_for_current_width() -> None:
    # Fixed Rust owner/evidence: app::resize_reflow replays canonical
    # HistoryCell values; AgentMarkdownCell renders raw source at each width.
    cell = AgentMarkdownCell.new(
        "A long agent message that must wrap differently after a resize.\n",
        ".",
    )

    wide = render_terminal_typed_transcript_lines([cell], 80)
    narrow = render_terminal_typed_transcript_lines([cell], 24)

    assert wide[0].startswith("\u2022 ")
    assert len(narrow) > len(wide)
    assert "".join(line.strip("\u2022 ") for line in narrow) != ""


def test_typed_transcript_keeps_rust_user_to_assistant_spacing() -> None:
    # Fixed Rust baseline 1c7832f:
    # - history_cell::messages::UserHistoryCell supplies its trailing blank.
    # - app::resize_reflow inserts one separator before the next non-stream
    #   continuation HistoryCell. Together they produce two blank rows.
    lines = render_terminal_typed_transcript_lines(
        [
            new_user_prompt("hello"),
            AgentMarkdownCell.new("answer", "."),
        ],
        80,
    )

    user_row = lines.index("\u203a hello")
    assistant_row = lines.index("\u2022 answer")
    assert lines[user_row + 1 : assistant_row] == ["", ""]


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
        current_size=os.terminal_size((80, 24)),
        active_stream=False,
    )

    assert plan.initialized is True
    assert plan.changed is False
    assert plan.last_terminal_size == os.terminal_size((80, 24))
    assert plan.reflow == TerminalResizeReflowPlan("none")


def test_plan_terminal_size_change_reflow_keeps_pending_state_when_size_unchanged() -> None:
    plan = plan_terminal_size_change_reflow(
        previous_size=os.terminal_size((80, 24)),
        current_size=os.terminal_size((80, 24)),
        active_stream=False,
        pending=True,
    )

    assert plan.changed is False
    assert plan.last_terminal_size == os.terminal_size((80, 24))
    assert plan.reflow == TerminalResizeReflowPlan("none", pending=True)


def test_plan_terminal_size_change_reflow_replays_or_defers_changed_size() -> None:
    replay = plan_terminal_size_change_reflow(
        previous_size=os.terminal_size((80, 24)),
        current_size=os.terminal_size((100, 30)),
        active_stream=False,
    )
    deferred = plan_terminal_size_change_reflow(
        previous_size=os.terminal_size((80, 24)),
        current_size=os.terminal_size((100, 30)),
        active_stream=True,
    )

    assert replay.changed is True
    assert replay.last_terminal_size == os.terminal_size((100, 30))
    assert replay.reflow == TerminalResizeReflowPlan("replay_history_scrollback")
    assert deferred.changed is True
    assert deferred.last_terminal_size == os.terminal_size((100, 30))
    assert deferred.reflow == TerminalResizeReflowPlan("defer_until_stream_finish", pending=True)


def test_terminal_resize_runtime_state_tracks_app_owned_size_and_guard() -> None:
    # Rust source contract:
    # - codex-tui::app::resize_reflow handles resize replay decisions while
    #   App-owned draw-size state prevents recursive resize repairs.
    inactive = TerminalResizeRuntimeState.inactive()
    active = inactive.activated(os.terminal_size((80, 24)))
    handling = active.begin_handling()
    finished = handling.end_handling()

    assert inactive.last_terminal_size is None
    assert inactive.handling_resize is False
    assert active.last_terminal_size == os.terminal_size((80, 24))
    assert active.handling_resize is False
    assert handling.last_terminal_size == os.terminal_size((80, 24))
    assert handling.handling_resize is True
    assert finished == active
    assert active.deactivated() == inactive


def test_terminal_resize_runtime_state_applies_size_plan_without_dropping_guard() -> None:
    state = TerminalResizeRuntimeState.inactive().activated(os.terminal_size((80, 24))).begin_handling()
    plan = plan_terminal_size_change_reflow(
        previous_size=os.terminal_size((80, 24)),
        current_size=os.terminal_size((100, 30)),
        active_stream=False,
    )

    next_state = state.after_size_plan(plan)

    assert next_state.last_terminal_size == os.terminal_size((100, 30))
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
        current_size=os.terminal_size((80, 24)),
        render_bottom_pane=lambda: calls.append("render"),
    )
    skipped_active, skipped_state = run_terminal_layout_activation(
        terminal_active=False,
        state=state,
        current_size=os.terminal_size((100, 30)),
        render_bottom_pane=lambda: calls.append("skipped-render"),
    )

    assert layout_active is True
    assert state.last_terminal_size == os.terminal_size((80, 24))
    assert state.handling_resize is False
    assert skipped_active is False
    assert skipped_state == state
    assert calls == ["render"]


def test_run_terminal_layout_deactivation_resets_scroll_region_and_state() -> None:
    # Rust source contract:
    # - leaving the terminal layout resets the terminal scroll region through
    #   custom_terminal while app::resize_reflow owns resize-state teardown.
    calls: list[str] = []
    active = TerminalResizeRuntimeState.inactive().activated(os.terminal_size((80, 24)))

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
    assert idle.action == "replay_history_scrollback"
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
    active = TerminalResizeRuntimeState.inactive().activated(os.terminal_size((80, 24)))
    guarded = active.begin_handling()

    inactive_state, inactive_pending = run_terminal_size_change_reflow(
        terminal_active=False,
        state=active,
        current_size=os.terminal_size((100, 30)),
        active_stream=False,
        pending=True,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )
    guarded_state, guarded_pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=guarded,
        current_size=os.terminal_size((100, 30)),
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
        current_size=os.terminal_size((80, 24)),
        active_stream=False,
        pending=True,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )

    assert state.last_terminal_size == os.terminal_size((80, 24))
    assert state.handling_resize is False
    assert pending is True
    assert calls == []


def test_run_terminal_size_change_reflow_defers_active_stream_resize() -> None:
    calls: list[str] = []

    state, pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=TerminalResizeRuntimeState.inactive().activated(os.terminal_size((80, 24))),
        current_size=os.terminal_size((100, 30)),
        active_stream=True,
        pending=False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )

    assert state.last_terminal_size == os.terminal_size((100, 30))
    assert state.handling_resize is False
    assert pending is True
    assert calls == ["defer_until_stream_finish"]


def test_run_terminal_size_change_reflow_resets_then_replays_changed_size() -> None:
    calls: list[str] = []

    state, pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=TerminalResizeRuntimeState.inactive().activated(os.terminal_size((80, 24))),
        current_size=os.terminal_size((100, 30)),
        active_stream=False,
        pending=True,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
    )

    assert state.last_terminal_size == os.terminal_size((100, 30))
    assert state.handling_resize is False
    assert pending is False
    assert calls == ["reset", "replay_history_scrollback"]


def test_run_terminal_size_change_reflow_syncs_handling_guard_around_replay() -> None:
    calls: list[str] = []

    state, pending = run_terminal_size_change_reflow(
        terminal_active=True,
        state=TerminalResizeRuntimeState.inactive().activated(os.terminal_size((80, 24))),
        current_size=os.terminal_size((100, 30)),
        active_stream=False,
        pending=False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        run_reflow_plan=lambda plan: calls.append(plan.action),
        enter_resize_handling=lambda state: calls.append(f"enter:{state.handling_resize}"),
        exit_resize_handling=lambda state: calls.append(f"exit:{state.handling_resize}"),
    )

    assert state.last_terminal_size == os.terminal_size((100, 30))
    assert state.handling_resize is False
    assert pending is False
    assert calls == ["enter:True", "reset", "replay_history_scrollback", "exit:False"]


def test_terminal_resize_coordinator_owns_layout_lifecycle_state() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns terminal resize/layout
    # lifecycle state; tui::terminal_runtime supplies only environment effects.
    calls: list[str] = []
    size = {"value": os.terminal_size((80, 24))}
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
    size["value"] = os.terminal_size((100, 30))
    coordinator.check_size_change()
    coordinator.transcript_reflow.set_due_for_test()
    coordinator.check_size_change()
    coordinator.deactivate_layout()

    assert coordinator.layout_active is False
    assert coordinator.state == TerminalResizeRuntimeState.inactive()
    assert coordinator.pending is False
    assert calls == ["render", "reset", "replay", "render", "reset"]


def test_terminal_resize_coordinator_exposes_dynamic_layout_active_provider() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns terminal resize/layout
    # state. terminal_runtime may pass this bound provider to neighboring owners,
    # but it must not snapshot the property or rebuild the state predicate.
    terminal_active = {"value": True}
    coordinator = TerminalResizeCoordinator(
        terminal_active=lambda: terminal_active["value"],
        current_size=lambda: os.terminal_size((80, 24)),
        active_stream=lambda: False,
        reset_terminal_scroll_region=lambda: None,
        render_bottom_pane=lambda: None,
        repaint_history_viewport=lambda: None,
        replay_history_scrollback=lambda: None,
    )

    assert coordinator.terminal_layout_active_state() is False
    coordinator.activate_layout()
    assert coordinator.terminal_layout_active_state() is True

    terminal_active["value"] = False
    assert coordinator.terminal_layout_active_state() is False


def test_terminal_resize_coordinator_wraps_replay_in_external_repaint_lifecycle() -> None:
    # Rust owner: codex-tui::app::resize_reflow owns replay-plan dispatch,
    # while codex-tui::custom_terminal owns the external repaint lifecycle used
    # to invalidate live frame buffers around terminal scrollback replay.
    calls: list[str] = []

    def run_external_repaint(repaint):
        calls.append("external:start")
        try:
            return repaint()
        finally:
            calls.append("external:end")

    coordinator = TerminalResizeCoordinator(
        terminal_active=lambda: True,
        current_size=lambda: os.terminal_size((80, 24)),
        active_stream=lambda: False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        render_bottom_pane=lambda: calls.append("render"),
        repaint_history_viewport=lambda: calls.append("repaint"),
        replay_history_scrollback=lambda: calls.append("replay"),
        run_external_repaint=run_external_repaint,
    )

    assert coordinator.run_reflow_plan(TerminalResizeReflowPlan("replay_history_scrollback")) is True
    assert calls == ["external:start", "replay", "external:end", "render"]


def test_terminal_resize_coordinator_defers_stream_resize_until_finish() -> None:
    calls: list[str] = []
    size = {"value": os.terminal_size((80, 24))}
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
    size["value"] = os.terminal_size((100, 30))
    coordinator.check_size_change()
    stream["active"] = False
    coordinator.run_stream_finish_reflow()

    assert coordinator.layout_active is True
    assert coordinator.state.last_terminal_size == os.terminal_size((100, 30))
    assert coordinator.pending is False
    assert calls == ["render", "reset", "replay", "render"]


def test_terminal_resize_coordinator_coalesces_continuous_resize_until_debounce_due() -> None:
    # Rust owner/source:
    # codex-tui::app::resize_reflow::handle_draw_size_change and
    # codex-tui::transcript_reflow::TranscriptReflowState debounce resize bursts
    # and rebuild once at the final observed geometry.
    calls: list[str] = []
    size = {"value": os.terminal_size((80, 24))}
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
    for next_size in ((90, 26), (110, 32), (100, 30)):
        size["value"] = os.terminal_size(next_size)
        coordinator.check_size_change()

    assert coordinator.pending is True
    assert calls == ["render"]

    coordinator.transcript_reflow.set_due_for_test()
    coordinator.check_size_change()

    assert coordinator.pending is False
    assert coordinator.state.last_terminal_size == os.terminal_size((100, 30))
    assert coordinator.transcript_reflow.last_reflow_width == 100
    assert calls == ["render", "reset", "replay", "render"]


def test_terminal_resize_coordinator_required_stream_finish_replays_canonical_scrollback() -> None:
    # Rust owner/source:
    # codex-tui::app::agent_message_consolidation consolidates the transient
    # stream. Because Python retains the stream as one mutable live tail, this
    # is Rust ConsolidationScrollbackReflow::Required and must source-replay.
    calls: list[str] = []

    def external(repaint):
        calls.append("external:start")
        try:
            return repaint()
        finally:
            calls.append("external:end")

    coordinator = TerminalResizeCoordinator(
        terminal_active=lambda: True,
        current_size=lambda: os.terminal_size((80, 24)),
        active_stream=lambda: False,
        reset_terminal_scroll_region=lambda: calls.append("reset"),
        render_bottom_pane=lambda: calls.append("render"),
        repaint_history_viewport=lambda: calls.append("viewport"),
        replay_history_scrollback=lambda: calls.append("replay"),
        run_external_repaint=external,
        render_after_external_repaint=lambda: calls.append("frame"),
    )

    assert coordinator.run_stream_finish_reflow() is True
    assert calls == ["reset", "external:start", "replay", "external:end", "frame"]


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
    assert calls == ["apply", ("insert", ["old", "", "new"], True)]
