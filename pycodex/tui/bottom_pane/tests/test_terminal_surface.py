import io
import os

from pycodex.tui.bottom_pane.terminal_surface import (
    TerminalBottomPaneFrameWrite,
    TerminalBottomPaneFootprint,
    TerminalBottomPanePopupLine,
    TerminalBottomPaneSurfaceWriter,
    TerminalBottomPaneState,
    TerminalLiveStatusSurface,
    bottom_pane_footprint_transition,
    bottom_pane_rows_for_size,
    clear_bottom_pane_and_flush,
    composer_line_text,
    history_bottom_row,
    render_bottom_pane,
    render_bottom_pane_and_flush,
    run_terminal_bottom_pane_action_plan,
    run_terminal_bottom_pane_clear,
    run_terminal_bottom_pane_render,
    run_terminal_live_status_action_plan,
    run_terminal_live_status_hide,
    run_terminal_live_status_show,
    terminal_bottom_pane_frame,
    terminal_bottom_pane_clear_plan,
    terminal_bottom_pane_render_plan,
    terminal_command_popup_visible_for_draft,
    terminal_live_status_hide_plan,
    terminal_live_status_show_plan,
    terminal_live_status_transition_to_inactive,
    terminal_live_status_transition_to_status,
)
from pycodex.tui.bottom_pane.list_selection_view import SelectionItem, SelectionViewParams


class FlushTrackingStringIO(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


def test_bottom_pane_rows_reserve_idle_and_status_footprints() -> None:
    size = os.terminal_size((80, 24))

    assert bottom_pane_rows_for_size(size, live_status_active=False) == [21, 22, 23, 24]
    assert bottom_pane_rows_for_size(size, live_status_active=True) == [19, 20, 21, 22, 23, 24]
    assert history_bottom_row(size, live_status_active=False) == 20
    assert history_bottom_row(size, live_status_active=True) == 18
    assert history_bottom_row(size, live_status_active=False, reserve_active_bottom_pane=True) == 18


def test_live_status_surface_controls_bottom_pane_footprint() -> None:
    # Rust owner: codex-tui::bottom_pane owns whether status indicator state
    # expands the live bottom pane; the terminal runner only applies the plan.
    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    non_tty_active = TerminalLiveStatusSurface.active_status()
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")

    assert not inactive.active
    assert inactive.render_text is None
    assert not inactive.footprint_active
    assert non_tty_active.active
    assert non_tty_active.render_text is None
    assert not non_tty_active.footprint_active
    assert active.render_text == "\u2022 Working"
    assert active.footprint_active
    assert active.rows_for_size(size) == [19, 20, 21, 22, 23, 24]

    grow = bottom_pane_footprint_transition(size, inactive, active)
    same = bottom_pane_footprint_transition(size, active, TerminalLiveStatusSurface.active_status("\u2022 Thinking"))
    shrink = bottom_pane_footprint_transition(size, active, inactive)

    assert grow.old_rows == (21, 22, 23, 24)
    assert grow.new_rows == (19, 20, 21, 22, 23, 24)
    assert grow.changed
    assert not same.changed
    assert shrink.changed


def test_bottom_pane_action_plans_skip_or_prepare_clear_and_render() -> None:
    # Rust owner: codex-tui::bottom_pane owns whether the live pane should draw;
    # the terminal runner should only execute prepared terminal side effects.
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")

    skip = terminal_bottom_pane_render_plan(
        stdin_is_terminal=False,
        layout_active=True,
        check_resize=True,
        draft="hi",
        footer_text="footer",
        live_status=active,
    )
    clear = terminal_bottom_pane_clear_plan(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=True,
        live_status=active,
    )
    render = terminal_bottom_pane_render_plan(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="hi",
        footer_text="footer",
        live_status=active,
    )

    assert not skip.should_run
    assert clear.action == "clear"
    assert clear.check_resize is True
    assert clear.live_status_active is True
    assert render.action == "render"
    assert render.check_resize is False
    assert render.state == TerminalBottomPaneState(
        draft="hi",
        footer_text="footer",
        live_status_text="\u2022 Working",
    )


def test_run_bottom_pane_action_plan_executes_clear_and_render() -> None:
    clear_writer = FlushTrackingStringIO()
    render_writer = FlushTrackingStringIO()
    size = os.terminal_size((40, 12))
    clear = terminal_bottom_pane_clear_plan(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        live_status=TerminalLiveStatusSurface.inactive(),
    )
    render = terminal_bottom_pane_render_plan(
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=False,
        draft="hi",
        footer_text="gpt-test high",
        live_status=TerminalLiveStatusSurface.inactive(),
    )

    run_terminal_bottom_pane_action_plan(clear_writer, size, clear)
    run_terminal_bottom_pane_action_plan(render_writer, size, render)

    assert clear_writer.flush_count == 1
    assert "\x1b[9;1H\x1b[2K" in clear_writer.getvalue()
    assert render_writer.flush_count == 1
    assert "\x1b[10;1H\u203a hi" in render_writer.getvalue()
    assert "\x1b[12;1Hgpt-test high" in render_writer.getvalue()


def test_run_terminal_bottom_pane_clear_skips_when_terminal_surface_inactive() -> None:
    # Rust owner: codex-tui::bottom_pane owns whether the pane should draw; the
    # terminal runner only supplies state and callbacks.
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    ran = run_terminal_bottom_pane_clear(
        writer,
        stdin_is_terminal=False,
        layout_active=True,
        live_status=TerminalLiveStatusSurface.active_status("\u2022 Working"),
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )

    assert ran is False
    assert calls == []
    assert writer.getvalue() == ""
    assert writer.flush_count == 0


def test_run_terminal_bottom_pane_clear_checks_resize_then_executes_plan() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []

    ran = run_terminal_bottom_pane_clear(
        writer,
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=True,
        live_status=TerminalLiveStatusSurface.inactive(),
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
    )

    assert ran is True
    assert calls == ["resize", "size"]
    assert writer.flush_count == 1
    assert "\x1b[9;1H\x1b[2K" in writer.getvalue()


def test_run_terminal_bottom_pane_render_checks_resize_then_executes_plan() -> None:
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    cursor: list[tuple[int, int]] = []

    ran = run_terminal_bottom_pane_render(
        writer,
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=True,
        draft="hi",
        footer_text="gpt-test high",
        live_status=TerminalLiveStatusSurface.active_status("\u2022 Working"),
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
        move_cursor=lambda row, column: cursor.append((row, column)),
    )

    assert ran is True
    assert calls == ["resize", "size"]
    assert writer.flush_count == 1
    output = writer.getvalue()
    assert "\x1b[7;1H\u2022 Working" in output
    assert "\x1b[10;1H\u203a hi" in output
    assert "\x1b[12;1Hgpt-test high" in output
    assert cursor == [(10, len(composer_line_text("hi")) + 1)]


def test_terminal_bottom_pane_surface_writer_owns_draft_and_terminal_callbacks() -> None:
    # Rust owner: codex-tui::bottom_pane owns composer/status/footer surface
    # rendering.  The terminal runner should supply environment callbacks while
    # this boundary tracks draft text and computes the live-pane footprint.
    writer = FlushTrackingStringIO()
    calls: list[str] = []
    live = [TerminalLiveStatusSurface.inactive()]

    surface = TerminalBottomPaneSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=lambda: live[0],
        terminal_size=lambda: calls.append("size") or os.terminal_size((40, 12)),
        resize=lambda: calls.append("resize"),
        footer_text=lambda: calls.append("footer") or "gpt-test high",
    )

    assert surface.history_bottom_row() == 8
    live[0] = TerminalLiveStatusSurface.active_status("\u2022 Working")
    assert surface.history_bottom_row() == 6
    assert surface.history_bottom_row(True) == 6

    surface.apply_draft("hello")
    assert surface.render(check_resize=True) is True
    assert calls[-3:] == ["footer", "resize", "size"]
    output = writer.getvalue()
    assert "\x1b[7;1H\u2022 Working" in output
    assert "\x1b[10;1H\u203a hello" in output
    assert "\x1b[12;1Hgpt-test high" in output

    assert surface.clear(check_resize=False) is True
    assert calls[-1] == "size"


def test_live_status_transition_helpers_preserve_previous_and_current_state() -> None:
    # Rust owner: codex-tui::bottom_pane owns status indicator surface state.
    # The terminal runner applies terminal side effects after receiving these
    # previous/current states.
    inactive = TerminalLiveStatusSurface.inactive()

    shown = terminal_live_status_transition_to_status(inactive, "\u2022 Working")
    assert shown.previous is inactive
    assert shown.current == TerminalLiveStatusSurface.active_status("\u2022 Working")
    assert shown.current.footprint_active

    non_tty = terminal_live_status_transition_to_status(shown.current)
    assert non_tty.previous == shown.current
    assert non_tty.current.active
    assert non_tty.current.render_text is None
    assert not non_tty.current.footprint_active

    hidden = terminal_live_status_transition_to_inactive(shown.current)
    assert hidden.previous == shown.current
    assert hidden.current == TerminalLiveStatusSurface.inactive()


def test_live_status_show_plan_routes_terminal_and_inline_side_effects() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane::ensure_status_indicator
    # owns status-indicator visibility and redraw requests; the terminal runner
    # should only execute the planned terminal side effects.
    inactive = TerminalLiveStatusSurface.inactive()

    tty = terminal_live_status_show_plan(
        inactive,
        "\u2022 Working",
        stdin_is_terminal=True,
        layout_active=True,
    )
    inline = terminal_live_status_show_plan(
        inactive,
        "\u2022 Working",
        stdin_is_terminal=False,
        layout_active=False,
    )

    assert tty.transition.current == TerminalLiveStatusSurface.active_status("\u2022 Working")
    assert tty.check_resize is True
    assert tty.repaint_footprint is True
    assert tty.render_bottom_pane is True
    assert tty.inline_status_text is None
    assert inline.transition.current == TerminalLiveStatusSurface.active_status("\u2022 Working")
    assert inline.inline_status_text == "\u2022 Working"
    assert inline.flush_writer is True
    assert inline.render_bottom_pane is False


def test_live_status_hide_plan_routes_terminal_and_inline_side_effects() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane::hide_status_indicator.
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")

    redraw = terminal_live_status_hide_plan(
        active,
        stdin_is_terminal=True,
        redraw_bottom_pane=True,
    )
    flush_only = terminal_live_status_hide_plan(
        active,
        stdin_is_terminal=True,
        redraw_bottom_pane=False,
    )
    inline = terminal_live_status_hide_plan(
        active,
        stdin_is_terminal=False,
    )
    inactive = terminal_live_status_hide_plan(
        TerminalLiveStatusSurface.inactive(),
        stdin_is_terminal=True,
    )

    assert redraw.transition.current == TerminalLiveStatusSurface.inactive()
    assert redraw.repaint_footprint is True
    assert redraw.render_bottom_pane is True
    assert redraw.flush_writer is False
    assert flush_only.repaint_footprint is True
    assert flush_only.render_bottom_pane is False
    assert flush_only.flush_writer is True
    assert inline.clear_inline_status is True
    assert inline.flush_writer is True
    assert inactive.changed is False
    assert inactive.repaint_footprint is False


def test_run_live_status_action_plan_executes_terminal_callbacks() -> None:
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")
    plan = terminal_live_status_hide_plan(
        active,
        stdin_is_terminal=True,
        redraw_bottom_pane=True,
    )
    calls: list[object] = []

    run_terminal_live_status_action_plan(
        io.StringIO(),
        plan,
        repaint_footprint=lambda previous: calls.append(previous),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert calls == [active, "render"]


def test_run_live_status_action_plan_executes_inline_writer_effects() -> None:
    writer = FlushTrackingStringIO()
    shown = terminal_live_status_show_plan(
        TerminalLiveStatusSurface.inactive(),
        "\u2022 Working",
        stdin_is_terminal=False,
        layout_active=False,
    )
    hidden = terminal_live_status_hide_plan(
        TerminalLiveStatusSurface.active_status("\u2022 Working"),
        stdin_is_terminal=False,
    )

    run_terminal_live_status_action_plan(
        writer,
        shown,
        repaint_footprint=lambda previous: None,
        render_bottom_pane=lambda: None,
    )
    run_terminal_live_status_action_plan(
        writer,
        hidden,
        repaint_footprint=lambda previous: None,
        render_bottom_pane=lambda: None,
    )

    output = writer.getvalue()
    assert "\u2022 Working" in output
    assert "\r\x1b[2K" in output
    assert writer.flush_count == 2


def test_run_live_status_show_and_hide_return_surface_state_and_execute_effects() -> None:
    # Rust owner: codex-tui::bottom_pane::BottomPane owns status-indicator
    # visibility transitions; terminal runtime supplies the side-effect hooks.
    writer = FlushTrackingStringIO()
    calls: list[object] = []
    initial = TerminalLiveStatusSurface.inactive()

    shown = run_terminal_live_status_show(
        writer,
        initial,
        "\u2022 Working",
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=lambda: calls.append("resize"),
        repaint_footprint=lambda previous: calls.append(previous),
        render_bottom_pane=lambda: calls.append("render"),
    )
    hidden = run_terminal_live_status_hide(
        writer,
        shown,
        stdin_is_terminal=True,
        redraw_bottom_pane=False,
        repaint_footprint=lambda previous: calls.append(previous),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert shown == TerminalLiveStatusSurface.active_status("\u2022 Working")
    assert hidden == TerminalLiveStatusSurface.inactive()
    assert calls == ["resize", initial, "render", shown]
    assert writer.flush_count == 1


def test_run_live_status_show_applies_state_before_repaint() -> None:
    applied: list[TerminalLiveStatusSurface] = []
    observed_during_repaint: list[TerminalLiveStatusSurface] = []

    shown = run_terminal_live_status_show(
        io.StringIO(),
        TerminalLiveStatusSurface.inactive(),
        "\u2022 Working",
        stdin_is_terminal=True,
        layout_active=False,
        check_resize=lambda: None,
        apply_state=applied.append,
        repaint_footprint=lambda previous: observed_during_repaint.extend(applied),
        render_bottom_pane=lambda: None,
    )

    assert shown == TerminalLiveStatusSurface.active_status("\u2022 Working")
    assert applied == [shown]
    assert observed_during_repaint == [shown]


def test_run_live_status_show_and_hide_handle_inline_surface() -> None:
    writer = FlushTrackingStringIO()

    shown = run_terminal_live_status_show(
        writer,
        TerminalLiveStatusSurface.inactive(),
        "\u2022 Working",
        stdin_is_terminal=False,
        layout_active=False,
        check_resize=lambda: writer.write("<resize>"),
        repaint_footprint=lambda previous: writer.write("<repaint>"),
        render_bottom_pane=lambda: writer.write("<render>"),
    )
    hidden = run_terminal_live_status_hide(
        writer,
        shown,
        stdin_is_terminal=False,
        repaint_footprint=lambda previous: writer.write("<repaint>"),
        render_bottom_pane=lambda: writer.write("<render>"),
    )

    assert shown.active
    assert hidden == TerminalLiveStatusSurface.inactive()
    assert "\u2022 Working" in writer.getvalue()
    assert "\r\x1b[2K" in writer.getvalue()
    assert writer.flush_count == 2


def test_render_bottom_pane_paints_status_composer_footer_and_cursor() -> None:
    writer = io.StringIO()
    cursor: list[tuple[int, int]] = []
    size = os.terminal_size((40, 12))

    render_bottom_pane(
        writer,
        size,
        TerminalBottomPaneState(
            draft="hello",
            footer_text="gpt-test high \u00b7 ~\\repo",
            live_status_text="\u2022 Working",
        ),
        move_cursor=lambda row, column: cursor.append((row, column)),
    )

    output = writer.getvalue()
    assert "\x1b[r" in output
    assert "\x1b[7;1H\x1b[2K" in output
    assert "\x1b[7;1H\u2022 Working" in output
    assert "\x1b[10;1H\u203a hello" in output
    assert "\x1b[12;1Hgpt-test high \u00b7 ~\\repo" in output
    assert cursor == [(10, len(composer_line_text("hello")) + 1)]


def test_terminal_command_popup_visibility_tracks_slash_command_name() -> None:
    # Rust owner: bottom_pane::chat_composer::sync_command_popup opens the
    # slash-command popup while editing the first-line command name and hides
    # it once the cursor is in command arguments.
    assert terminal_command_popup_visible_for_draft("/") is True
    assert terminal_command_popup_visible_for_draft("/m") is True
    assert terminal_command_popup_visible_for_draft("/model") is True
    assert terminal_command_popup_visible_for_draft("/model ") is False
    assert terminal_command_popup_visible_for_draft("hello /m") is False


def test_render_bottom_pane_paints_slash_popup_below_composer_with_highlight() -> None:
    writer = io.StringIO()
    cursor: list[tuple[int, int]] = []
    size = os.terminal_size((72, 12))

    render_bottom_pane(
        writer,
        size,
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(
                TerminalBottomPanePopupLine("/model            choose what model and reasoning effort to use", True),
                TerminalBottomPanePopupLine("/memories         configure memory use and generation", False),
            ),
        ),
        move_cursor=lambda row, column: cursor.append((row, column)),
    )

    output = writer.getvalue()
    assert "\x1b[9;1H\u203a /m" in output
    assert "\x1b[10;1H\x1b[94m/model" in output
    assert "\x1b[7m/model" not in output
    assert "\x1b[11;1H/memories" in output
    assert "\x1b[12;1Hgpt-test high" in output
    assert cursor == [(9, len(composer_line_text("/m")) + 1)]


def test_terminal_bottom_pane_frame_models_popup_layout_and_render_policy() -> None:
    size = os.terminal_size((72, 12))

    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(
                TerminalBottomPanePopupLine("/model choose", True),
                TerminalBottomPanePopupLine("/memories configure", False),
            ),
        ),
    )

    assert frame.clear_rows == (9, 10, 11, 12)
    assert frame.writes == (
        TerminalBottomPaneFrameWrite(9, 1, "\u203a /m"),
        TerminalBottomPaneFrameWrite(10, 1, "/model choose", True),
        TerminalBottomPaneFrameWrite(11, 1, "/memories configure", False),
        TerminalBottomPaneFrameWrite(12, 1, "gpt-test high"),
    )
    assert frame.cursor_row == 9
    assert frame.cursor_column == len(composer_line_text("/m")) + 1


def test_render_bottom_pane_clears_previous_larger_popup_footprint() -> None:
    writer = io.StringIO()
    size = os.terminal_size((72, 12))

    render_bottom_pane(
        writer,
        size,
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(TerminalBottomPanePopupLine("/model choose", True),),
        ),
        clear_popup_height=3,
    )

    output = writer.getvalue()
    assert "\x1b[8;1H\x1b[2K" in output
    assert "\x1b[9;1H\x1b[2K" in output
    assert "\x1b[10;1H\x1b[2K" in output
    assert "\x1b[11;1H\x1b[2K" in output
    assert "\x1b[12;1H\x1b[2K" in output
    assert "\x1b[10;1H\x1b[94m/model choose\x1b[0m" in output


def test_terminal_bottom_pane_frame_clears_previous_larger_popup_footprint() -> None:
    frame = terminal_bottom_pane_frame(
        os.terminal_size((72, 12)),
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(TerminalBottomPanePopupLine("/model choose", True),),
        ),
        clear_popup_height=3,
    )

    assert frame.clear_rows == (8, 9, 10, 11, 12)
    assert TerminalBottomPaneFrameWrite(10, 1, "/model choose", True) in frame.writes


def test_terminal_bottom_pane_surface_writer_syncs_command_popup_and_selection() -> None:
    # Rust owner: ChatComposer::handle_key_event dispatches Up/Down to the
    # active command popup, then syncs and redraws bottom_pane.
    writer = FlushTrackingStringIO()
    surface = TerminalBottomPaneSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((80, 16)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
    )

    surface.apply_draft("/m")
    assert surface.command_popup_visible is True
    assert surface.command_popup.selected_item().command() == "model"

    assert surface.handle_composer_key("/m", "down") == "/m"
    assert surface.command_popup.selected_item().command() == "memories"

    completed = surface.handle_composer_key("/m", "tab")
    assert completed == "/memories "

    surface.apply_draft(completed or "")
    assert surface.command_popup_visible is False


def test_terminal_bottom_pane_surface_writer_routes_model_to_active_selection_view() -> None:
    # Rust owner: ChatComposer::handle_key_event dispatches /model through
    # chatwidget::model_popups into a BottomPaneView/ListSelectionView instead
    # of submitting it as a user turn.
    writer = FlushTrackingStringIO()
    surface = TerminalBottomPaneSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((96, 18)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        open_model_view=lambda: SelectionViewParams(
            header=("Select Model and Effort", "Access legacy models by running codex -m <model_name> or in your config.toml"),
            items=[
                SelectionItem(name="gpt-5.5", description="Frontier model", is_current=True),
                SelectionItem(name="gpt-5.4", description="Strong model"),
            ],
        ),
    )

    assert surface.handle_composer_key("/model", "enter") == ""
    assert surface.active_view is not None
    assert surface.command_popup_visible is False

    surface.render(check_resize=False)
    output = writer.getvalue()
    assert "Select Model and Effort" in output
    assert "\x1b[94m> 1. * gpt-5.5" in output

    assert surface.handle_composer_key("", "down") == ""
    surface.render(check_resize=False)
    output = writer.getvalue()
    assert "\x1b[94m> 2.   gpt-5.4" in output


def test_terminal_bottom_pane_surface_writer_reflows_history_when_popup_footprint_grows() -> None:
    # Rust owner: bottom_pane computes active view height, while
    # app::resize_reflow repairs the transcript viewport when that bottom-pane
    # footprint changes. Opening any selection popup must use that shared
    # footprint path rather than a /model-specific clear.
    writer = FlushTrackingStringIO()
    transitions: list[tuple[TerminalBottomPaneFootprint, TerminalBottomPaneFootprint]] = []
    surface = TerminalBottomPaneSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((96, 18)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        repaint_footprint=lambda previous, current: transitions.append((previous, current)),
    )

    surface.render(check_resize=False)
    surface.show_selection_view(
        SelectionViewParams(
            header="Select Model and Effort",
            items=[
                SelectionItem(name="gpt-5.5", description="Frontier model", is_current=True),
                SelectionItem(name="gpt-5.4", description="Strong model"),
            ],
        )
    )
    surface.render(check_resize=False)

    assert transitions
    previous, current = transitions[-1]
    assert previous.popup_height == 0
    assert current.popup_height > 0


def test_terminal_bottom_pane_surface_writer_pushes_child_selection_view() -> None:
    # Rust owner: bottom_pane owns a view stack.  Terminal rendering should keep
    # parent/child selection views inside the same frame pipeline instead of
    # special-casing model -> reasoning popups in the runner.
    writer = FlushTrackingStringIO()
    emitted: list[object] = []

    def handle_events(events: tuple[object, ...]) -> SelectionViewParams | None:
        emitted.extend(events)
        if "open_child" in events:
            return SelectionViewParams(
                header="Select Reasoning Level",
                items=[
                    SelectionItem(name="Medium", actions=["medium"], dismiss_on_select=True),
                    SelectionItem(name="High", actions=["high"], dismiss_on_select=True),
                ],
            )
        return None

    surface = TerminalBottomPaneSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((96, 18)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        on_selection_events=handle_events,
    )
    surface.show_selection_view(
        SelectionViewParams(
            header="Select Model and Effort",
            items=[
                SelectionItem(
                    name="gpt-5.4",
                    actions=["open_child"],
                    dismiss_on_select=False,
                    dismiss_parent_on_child_accept=True,
                )
            ],
        )
    )

    assert surface.handle_composer_key("", "enter") == ""
    assert len(surface.view_stack) == 2
    assert surface.active_view is surface.view_stack[-1]

    surface.render(check_resize=False)
    output = writer.getvalue()
    assert "Select Reasoning Level" in output
    assert "\x1b[94m> 1.   Medium" in output

    assert surface.handle_composer_key("", "down") == ""
    surface.render(check_resize=False)
    output = writer.getvalue()
    assert "\x1b[94m> 2.   High" in output

    assert surface.handle_composer_key("", "enter") == ""
    assert surface.active_view is None
    assert surface.view_stack == []
    assert emitted == ["open_child", "high"]


def test_terminal_bottom_pane_surface_writer_normalizes_text_enter_for_selection_view() -> None:
    # Rust owner: codex-tui::tui::event_stream normalizes platform key payloads
    # before active BottomPaneView handling.  The terminal adapter should accept
    # CR/LF-shaped Enter events at the shared frame boundary, not in individual
    # slash commands.
    writer = FlushTrackingStringIO()
    emitted: list[object] = []
    surface = TerminalBottomPaneSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((96, 18)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        on_selection_events=lambda events: emitted.extend(events) or None,
    )
    surface.show_selection_view(
        SelectionViewParams(
            header="Select Reasoning Level",
            items=[
                SelectionItem(name="Low", actions=["low"], dismiss_on_select=True),
                SelectionItem(name="Medium", actions=["medium"], dismiss_on_select=True),
            ],
        )
    )

    assert surface.handle_composer_key("", "down") == ""
    assert surface.handle_composer_key("", "text", "\r") == ""

    assert surface.active_view is None
    assert emitted == ["medium"]


def test_clear_bottom_pane_and_flush_flushes_writer() -> None:
    writer = FlushTrackingStringIO()

    clear_bottom_pane_and_flush(writer, os.terminal_size((40, 12)), live_status_active=False)

    assert writer.flush_count == 1
    output = writer.getvalue()
    assert "\x1b[r" in output
    assert "\x1b[9;1H\x1b[2K" in output
    assert "\x1b[12;1H\x1b[2K" in output


def test_render_bottom_pane_and_flush_flushes_writer() -> None:
    writer = FlushTrackingStringIO()

    render_bottom_pane_and_flush(
        writer,
        os.terminal_size((40, 12)),
        TerminalBottomPaneState(draft="hi", footer_text="gpt-test high"),
    )

    assert writer.flush_count == 1
    output = writer.getvalue()
    assert "\x1b[10;1H\u203a hi" in output
    assert "\x1b[12;1Hgpt-test high" in output
