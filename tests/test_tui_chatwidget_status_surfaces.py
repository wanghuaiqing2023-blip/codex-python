from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from pycodex.tui.bottom_pane.status_line_setup import StatusLineItem
from pycodex.tui.bottom_pane.title_setup import TerminalTitleItem
from pycodex.tui.chatwidget.status_surfaces import (
    TERMINAL_TITLE_ACTION_REQUIRED_PREFIX,
    TERMINAL_TITLE_ACTION_REQUIRED_PREFIX_HIDDEN,
    action_required_terminal_title_prefix_at,
    approval_mode_display,
    five_hour_status_window,
    parse_items_with_invalids,
    permissions_display,
    status_surface_selections,
    terminal_title_spinner_frame_at,
    truncate_terminal_title_part,
    weekly_status_window,
)
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
