from datetime import datetime, timedelta, timezone
import io
import os
from types import SimpleNamespace

from pycodex.tui.app.resize_reflow import bottom_pane_footprint_transition
from pycodex.tui.bottom_pane.status_line_setup import StatusLineItem
from pycodex.tui.bottom_pane.title_setup import TerminalTitleItem
from pycodex.tui.chatwidget.status_surfaces import (
    TERMINAL_TITLE_ACTION_REQUIRED_PREFIX,
    TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN,
    TerminalLiveStatusSurface,
    TerminalStatusSurfaceWriter,
    TerminalTurnStatusState,
    action_required_terminal_title_prefix_at,
    approval_mode_display,
    five_hour_status_window,
    parse_items_with_invalids,
    permissions_display,
    run_state_status_text,
    run_terminal_live_status_text_show,
    run_terminal_turn_status_refresh,
    run_terminal_turn_status_render,
    should_render_terminal_turn_status,
    status_surface_selections,
    terminal_live_status_projection,
    terminal_live_status_text,
    terminal_turn_elapsed_seconds,
    terminal_turn_status_cleared,
    terminal_turn_status_header,
    terminal_turn_status_render_plan,
    terminal_turn_status_suppressed,
    terminal_title_spinner_frame_at,
    truncate_terminal_title_part,
    weekly_status_window,
)
from pycodex.tui.chatwidget.status_surfaces import (
    run_terminal_live_status_action_plan,
    run_terminal_live_status_hide,
    run_terminal_live_status_show,
    terminal_live_status_hide_plan,
    terminal_live_status_show_plan,
    terminal_live_status_transition_to_inactive,
    terminal_live_status_transition_to_status,
)
from pycodex.tui.chatwidget.status_state import TerminalTitleStatusKind
from pycodex.tui.status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay


NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)


class FlushTrackingStringIO(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1
        super().flush()


def _window(minutes: int) -> RateLimitWindowDisplay:
    return RateLimitWindowDisplay(used_percent=50.0, window_minutes=minutes)


def test_status_surface_selections_detect_git_dependencies() -> None:
    # Rust parity: StatusSurfaceSelections::uses_git_branch / uses_git_summary.
    selections = status_surface_selections(
        status_line_ids=["pull-request-number", "branch-changes"],
        terminal_title_ids=["git-branch"],
    )

    assert selections.uses_git_branch()
    assert selections.uses_git_summary()
    assert selections.status_line_items == (
        StatusLineItem.PULL_REQUEST_NUMBER,
        StatusLineItem.BRANCH_CHANGES,
    )
    assert selections.terminal_title_items == (TerminalTitleItem.GIT_BRANCH,)


def test_parse_items_with_invalids_deduplicates_invalids_in_order() -> None:
    # Rust parity: parse_items_with_invalids quotes unknown ids and keeps first invalid order.
    items, invalid = parse_items_with_invalids(
        ["model", "bogus", "bogus", "current-dir"],
        StatusLineItem.parse,
    )

    assert items == [StatusLineItem.MODEL_NAME, StatusLineItem.CURRENT_DIR]
    assert invalid == ['"bogus"']


def test_five_hour_window_selection_prefers_primary_then_secondary_then_non_weekly() -> None:
    # Rust parity: five_hour_status_window fallback order.
    primary_5h = _window(5 * 60)
    secondary_weekly = _window(7 * 24 * 60)
    snapshot = RateLimitSnapshotDisplay("codex", NOW, primary=primary_5h, secondary=secondary_weekly)
    assert five_hour_status_window(snapshot) == (primary_5h, False)

    primary_weekly = _window(7 * 24 * 60)
    secondary_5h = _window(5 * 60)
    snapshot = RateLimitSnapshotDisplay("codex", NOW, primary=primary_weekly, secondary=secondary_5h)
    assert five_hour_status_window(snapshot) == (secondary_5h, True)

    primary_daily = _window(24 * 60)
    snapshot = RateLimitSnapshotDisplay("codex", NOW, primary=primary_daily, secondary=None)
    assert five_hour_status_window(snapshot) == (primary_daily, False)


def test_weekly_window_selection_prefers_weekly_then_secondary() -> None:
    # Rust parity: weekly_status_window uses labelled weekly first, then any secondary.
    primary_daily = _window(24 * 60)
    secondary_monthly = _window(30 * 24 * 60)
    snapshot = RateLimitSnapshotDisplay("codex", NOW, primary=primary_daily, secondary=secondary_monthly)
    assert weekly_status_window(snapshot) == (secondary_monthly, True)

    primary_weekly = _window(7 * 24 * 60)
    snapshot = RateLimitSnapshotDisplay("codex", NOW, primary=primary_weekly, secondary=secondary_monthly)
    assert weekly_status_window(snapshot) == (primary_weekly, False)


def test_terminal_title_truncation_and_animation_helpers() -> None:
    # Rust parity: truncate_terminal_title_part and action-required prefix phase.
    assert truncate_terminal_title_part("abcdef", 0) == ""
    assert truncate_terminal_title_part("abcdef", 2) == "ab"
    assert truncate_terminal_title_part("abcdef", 5) == "ab..."
    assert terminal_title_spinner_frame_at(timedelta(milliseconds=0))
    assert terminal_title_spinner_frame_at(timedelta(milliseconds=100))
    assert action_required_terminal_title_prefix_at(timedelta(seconds=0)) == TERMINAL_TITLE_ACTION_REQUIRED_PREFIX
    assert (
        action_required_terminal_title_prefix_at(timedelta(seconds=1))
        == TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN
    )
    assert (
        action_required_terminal_title_prefix_at(timedelta(seconds=1), animations=False)
        == TERMINAL_TITLE_ACTION_REQUIRED_PREFIX
    )


def test_run_state_status_text_matches_rust_task_state_buckets() -> None:
    # Rust parity: chatwidget/status_surfaces.rs::run_state_status_text.
    assert run_state_status_text(TerminalTitleStatusKind.Working, task_running=False) == "Ready"
    assert run_state_status_text(TerminalTitleStatusKind.Thinking, task_running=False) == "Ready"
    assert run_state_status_text(TerminalTitleStatusKind.Working, task_running=True) == "Working"
    assert run_state_status_text(TerminalTitleStatusKind.Thinking, task_running=True) == "Thinking"
    assert (
        run_state_status_text(TerminalTitleStatusKind.WaitingForBackgroundTerminal, task_running=True)
        == "Waiting"
    )
    assert run_state_status_text(TerminalTitleStatusKind.Working, task_running=True, mcp_startup_active=True) == "Starting"


def test_terminal_live_turn_status_text_and_tick_gate() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces drives live status
    # strings; tui::terminal_runtime only writes the resulting surface.
    assert terminal_live_status_text("Working") == "\u2022 Working"
    assert terminal_live_status_text("retry", "slow") == "\u2022 retry \u2514 slow"
    assert terminal_turn_status_header(2) == "Working (2s \u2022 esc to interrupt)"
    assert terminal_turn_status_header(-1) == "Working (0s \u2022 esc to interrupt)"
    assert should_render_terminal_turn_status(
        active=False,
        last_second=None,
        elapsed_seconds=0,
        suppressed=False,
    )
    assert not should_render_terminal_turn_status(
        active=True,
        last_second=3,
        elapsed_seconds=3,
        suppressed=False,
    )
    assert should_render_terminal_turn_status(
        active=True,
        last_second=3,
        elapsed_seconds=3,
        suppressed=False,
        force=True,
    )
    assert not should_render_terminal_turn_status(
        active=True,
        last_second=3,
        elapsed_seconds=4,
        suppressed=True,
    )


def test_terminal_live_status_projection_clips_for_bottom_pane_row() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns live status text
    # projection; terminal adapters only place the projected row in the pane.
    assert terminal_live_status_projection("\u2022 Working", columns=10).line == "\u2022 Working"
    assert terminal_live_status_projection("\u2022 Working", columns=6).line == "\u2022 Wor"
    assert terminal_live_status_projection(None, columns=10).line is None


def test_run_terminal_live_status_text_show_builds_text_and_delegates_surface_effects() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns live status text
    # refresh; codex-tui::bottom_pane owns status-indicator footprint effects.
    writer = io.StringIO()
    calls: list[object] = []
    initial = TerminalLiveStatusSurface.inactive()

    shown = run_terminal_live_status_text_show(
        writer,
        initial,
        "retry",
        "slow",
        stdin_is_terminal=True,
        layout_active=True,
        check_resize=lambda: calls.append("resize"),
        repaint_footprint=lambda previous: calls.append(previous),
        render_bottom_pane=lambda: calls.append("render"),
    )

    assert shown == TerminalLiveStatusSurface.active_status("\u2022 retry \u2514 slow")
    assert calls == ["resize", initial, "render"]


def test_terminal_status_surface_writer_updates_state_before_repaint() -> None:
    # Rust owner: chatwidget::status_surfaces owns status state refresh while
    # bottom_pane owns footprint repaint effects. The terminal runner should
    # not duplicate this apply-before-repaint ordering.
    writer = io.StringIO()
    calls: list[object] = []
    holder: dict[str, TerminalStatusSurfaceWriter] = {}

    status = TerminalStatusSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        check_resize=lambda: calls.append("resize"),
        repaint_footprint=lambda previous: calls.append(
            ("repaint", previous, holder["status"].live_status)
        ),
        render_bottom_pane=lambda: calls.append("render"),
    )
    holder["status"] = status
    initial = status.live_status

    status.show_live_status("retry", "slow")

    expected = TerminalLiveStatusSurface.active_status("\u2022 retry \u2514 slow")
    assert status.live_status == expected
    assert calls == ["resize", ("repaint", initial, expected), "render"]


def test_terminal_status_surface_writer_owns_turn_status_refresh_state() -> None:
    # Rust owner: chatwidget::status_surfaces owns the force-render callback
    # used when a turn starts; terminal_runtime should pass this method instead
    # of spelling out render_turn_status(force=True).
    writer = io.StringIO()
    calls: list[str] = []
    status = TerminalStatusSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        check_resize=lambda: calls.append("resize"),
        repaint_footprint=lambda _previous: calls.append("repaint"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    status.start_turn(10.0)
    status.turn_started_at = -1.0
    status.render_turn_status_force()
    assert status.turn_status.active is True
    assert status.live_status.text is not None

    status.start_turn(10.0)
    status.render_turn_status(force=True, now=12.4)
    status.refresh_turn_status_if_due(now=12.9)
    status.refresh_turn_status_if_due(now=13.1)

    assert status.turn_status.active is True
    assert status.turn_status.last_second == 3
    assert status.live_status.text == "\u2022 Working (3s \u2022 esc to interrupt)"
    status.suppress_turn_status()
    suppressed_text = status.live_status.text
    status.refresh_turn_status_if_due(now=14.1)
    assert status.live_status.text == suppressed_text
    assert status.turn_status.suppressed is True
    status.clear_turn_status()
    assert status.turn_status == TerminalTurnStatusState.inactive()


def test_terminal_status_surface_writer_hides_live_status_surface() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns protocol-facing
    # live-status hide/clear transitions. terminal_runtime should bind these
    # methods directly instead of spelling out redraw_bottom_pane policy.
    writer = io.StringIO()
    calls: list[str] = []
    status = TerminalStatusSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        repaint_footprint=lambda _previous: calls.append("repaint"),
        render_bottom_pane=lambda: calls.append("render"),
    )

    status.show_live_status("Working")
    assert status.live_status.footprint_active is True

    status.hide_live_status()

    assert status.live_status == TerminalLiveStatusSurface.inactive()
    assert calls[-2:] == ["repaint", "render"]

    status.show_live_status("Working")
    calls.clear()
    status.clear_live_status()
    assert status.live_status == TerminalLiveStatusSurface.inactive()
    assert calls[-2:] == ["repaint", "render"]


def test_terminal_turn_status_state_owns_tick_gate_state() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns the active-turn
    # status tick gate. The terminal runner stores the returned state and
    # performs the terminal write side effect.
    state = TerminalTurnStatusState.inactive()
    assert state.should_render(0)
    assert not state.should_refresh()

    state = state.after_render(0)
    assert state.should_refresh()
    assert not state.should_render(0)
    assert state.should_render(0, force=True)
    assert state.should_render(1)

    suppressed = state.suppress()
    assert not suppressed.should_refresh()
    assert not suppressed.should_render(2)
    assert suppressed.cleared() == TerminalTurnStatusState.inactive()


def test_terminal_status_surface_writer_owns_composer_cursor_visibility() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns active-turn
    # status state for the terminal product path. terminal_runtime should ask
    # this owner whether the composer cursor is visible instead of inspecting
    # turn state in a local lambda.
    status = TerminalStatusSurfaceWriter(io.StringIO())

    assert status.composer_cursor_visible() is True
    status.turn_status = TerminalTurnStatusState.inactive().after_render(0)
    assert status.composer_cursor_visible() is False
    status.clear_turn_status()
    assert status.composer_cursor_visible() is True


def test_terminal_status_surface_writer_binds_bottom_pane_render_callback() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns the
    # protocol-facing status writer callbacks. The terminal runtime may wire
    # bottom-pane rendering after component construction, but the binding
    # method lives with the status owner.
    calls: list[str] = []
    status = TerminalStatusSurfaceWriter(io.StringIO())

    status.bind_render_bottom_pane(lambda: calls.append("render"))
    status.render_bottom_pane()

    assert calls == ["render"]


def test_terminal_turn_status_render_plan_owns_elapsed_header_and_state_transition() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns active-turn
    # status text and refresh gating. The terminal runner only writes the
    # returned header when one is requested.
    assert terminal_turn_elapsed_seconds(0.0, now=10.0) == 0
    assert terminal_turn_elapsed_seconds(10.3, now=12.9) == 2
    assert terminal_turn_elapsed_seconds(12.9, now=10.3) == 0

    initial = TerminalTurnStatusState.inactive()
    plan = terminal_turn_status_render_plan(initial, started_at=10.0, now=12.4)

    assert plan.header == "Working (2s \u2022 esc to interrupt)"
    assert plan.state.active is True
    assert plan.state.last_second == 2

    skipped = terminal_turn_status_render_plan(plan.state, started_at=10.0, now=12.9)
    assert skipped.header is None
    assert skipped.state == plan.state

    forced = terminal_turn_status_render_plan(plan.state, started_at=10.0, now=12.9, force=True)
    assert forced.header == "Working (2s \u2022 esc to interrupt)"


def test_run_terminal_turn_status_render_writes_when_plan_requests_header() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns active-turn
    # status render dispatch; terminal runtime only supplies the write effect.
    written: list[str] = []
    state = TerminalTurnStatusState.inactive()

    state = run_terminal_turn_status_render(
        state,
        started_at=10.0,
        now=12.4,
        write_live_status=written.append,
    )
    skipped = run_terminal_turn_status_render(
        state,
        started_at=10.0,
        now=12.9,
        write_live_status=written.append,
    )

    assert written == ["Working (2s \u2022 esc to interrupt)"]
    assert state.active is True
    assert state.last_second == 2
    assert skipped == state


def test_terminal_turn_status_refresh_and_state_effects_are_surface_owned() -> None:
    # Rust owner: codex-tui::chatwidget::status_surfaces owns the active-turn
    # status refresh and state effects; terminal runtime only wires callbacks.
    written: list[str] = []
    inactive = TerminalTurnStatusState.inactive()

    assert (
        run_terminal_turn_status_refresh(
            inactive,
            started_at=10.0,
            write_live_status=written.append,
        )
        == inactive
    )
    assert written == []

    active = inactive.after_render(1)
    refreshed = run_terminal_turn_status_refresh(
        active,
        started_at=10.0,
        now=12.4,
        write_live_status=written.append,
    )

    assert written == ["Working (2s \u2022 esc to interrupt)"]
    assert refreshed.active is True
    assert refreshed.last_second == 2
    assert terminal_turn_status_suppressed(refreshed).suppressed is True
    assert terminal_turn_status_cleared(refreshed) == TerminalTurnStatusState.inactive()


def test_permissions_display_matches_rust_profile_summary_rules() -> None:
    # Rust parity: permissions_display preserves named active profiles, then summarizes effective profile.
    custom_profile = SimpleNamespace(id="team-safe")
    permissions = SimpleNamespace(
        active_permission_profile=lambda: custom_profile,
        effective_permission_profile=lambda: "read-only",
    )
    assert permissions_display(SimpleNamespace(permissions=permissions)) == "team-safe"

    permissions = SimpleNamespace(
        active_permission_profile=lambda: SimpleNamespace(id=":read-only"),
        effective_permission_profile=lambda: "read-only",
    )
    assert permissions_display(SimpleNamespace(permissions=permissions)) == "Read Only"

    permissions = SimpleNamespace(
        active_permission_profile=lambda: None,
        effective_permission_profile=lambda: SimpleNamespace(
            value="workspace-write",
            network_access=False,
        ),
    )
    assert permissions_display(SimpleNamespace(permissions=permissions)) == "Workspace"

    permissions = SimpleNamespace(
        active_permission_profile=lambda: None,
        effective_permission_profile=lambda: SimpleNamespace(
            value="workspace-write",
            network_access=True,
        ),
    )
    assert permissions_display(SimpleNamespace(permissions=permissions)) == "Custom permissions"

    permissions = SimpleNamespace(
        active_permission_profile=lambda: None,
        effective_permission_profile=lambda: "disabled",
    )
    assert permissions_display(SimpleNamespace(permissions=permissions)) == "Full Access"


def test_approval_mode_display_matches_auto_review_special_case() -> None:
    # Rust parity: approval_mode_display maps on-request + AutoReview to auto-review.
    permissions = SimpleNamespace(approval_policy=SimpleNamespace(value=lambda: "on-request"))
    config = SimpleNamespace(permissions=permissions, approvals_reviewer="auto-review")
    assert approval_mode_display(config) == "auto-review"

    config = SimpleNamespace(permissions=permissions, approvals_reviewer="human")
    assert approval_mode_display(config) == "on-request"


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
