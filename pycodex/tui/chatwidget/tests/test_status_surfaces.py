from datetime import datetime, timedelta, timezone
import io
from types import SimpleNamespace

from pycodex.tui.bottom_pane.terminal_surface import TerminalLiveStatusSurface
from pycodex.tui.bottom_pane.status_line_setup import StatusLineItem
from pycodex.tui.bottom_pane.title_setup import TerminalTitleItem
from pycodex.tui.chatwidget.status_surfaces import (
    TERMINAL_TITLE_ACTION_REQUIRED_PREFIX,
    TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN,
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
from pycodex.tui.chatwidget.status_state import TerminalTitleStatusKind
from pycodex.tui.status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay


NOW = datetime(2026, 6, 12, tzinfo=timezone.utc)


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
    writer = io.StringIO()
    status = TerminalStatusSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
    )

    status.show_live_status("Working")
    assert status.live_status.footprint_active is True

    status.hide_inline_status(redraw_bottom_pane=True)

    assert status.live_status == TerminalLiveStatusSurface.inactive()


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
