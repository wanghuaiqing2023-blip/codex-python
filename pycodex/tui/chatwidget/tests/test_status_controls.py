from pathlib import Path

from pycodex.tui.chatwidget.status_controls import (
    RateLimitWindowDisplay,
    ReasoningEffortConfig,
    SetupViewRequest,
    StatusControlsConfig,
    StatusControlsState,
    StatusDetailsCapitalization,
    StatusOutputCell,
    StatusSurfacePreviewData,
    TokenInfo,
    TokenUsage,
    add_status_output,
    cancel_status_line_setup,
    cancel_terminal_title_setup,
    finish_status_rate_limit_refresh,
    open_status_line_setup,
    open_terminal_title_setup,
    preview_terminal_title,
    refresh_status_line,
    revert_terminal_title_setup_preview,
    set_active_agent_label,
    set_status,
    set_status_header,
    set_status_line,
    set_status_line_branch,
    set_status_line_git_summary,
    set_status_line_hyperlink,
    setup_status_line,
    setup_terminal_title,
    status_line_context_remaining_percent,
    status_line_context_used_percent,
    status_line_context_window_size,
    status_line_limit_display,
    status_line_reasoning_effort_label,
    status_line_total_usage,
    status_surface_preview_data,
    terminal_title_preview_data,
)
from pycodex.tui.chatwidget.status_state import STATUS_DETAILS_DEFAULT_MAX_LINES, StatusIndicatorState


def test_set_status_trims_and_capitalizes_details_and_updates_bottom_pane():
    """Rust codex-tui chatwidget::status_controls::set_status."""

    state = StatusControlsState(config=StatusControlsConfig(tui_terminal_title=["status"]))

    set_status(state, "Working", "   waiting for tool", StatusDetailsCapitalization.CapitalizeFirst, 3)

    assert state.status_state.current_status == StatusIndicatorState("Working", "Waiting for tool", 3)
    assert state.bottom_pane.status_updates == [
        ("Working", "Waiting for tool", StatusDetailsCapitalization.Preserve, 3)
    ]
    assert state.refreshed_status_surfaces == 1


def test_set_status_preserves_details_or_clears_empty_details():
    state = StatusControlsState()

    set_status(state, "Header", "   keep Case", StatusDetailsCapitalization.Preserve, 2)
    assert state.status_state.current_status.details == "keep Case"

    set_status(state, "Header", "", StatusDetailsCapitalization.CapitalizeFirst, 2)
    assert state.status_state.current_status.details is None


def test_set_status_header_uses_default_detail_settings():
    state = StatusControlsState()

    set_status_header(state, "Thinking")

    assert state.status_state.current_status == StatusIndicatorState(
        "Thinking",
        None,
        STATUS_DETAILS_DEFAULT_MAX_LINES,
    )


def test_status_line_pass_through_setters_update_bottom_pane_state():
    state = StatusControlsState()

    set_status_line(state, "ready")
    set_status_line_hyperlink(state, "https://example.test")
    set_active_agent_label(state, "Agent A")

    assert state.bottom_pane.status_line == "ready"
    assert state.bottom_pane.status_line_hyperlink == "https://example.test"
    assert state.bottom_pane.active_agent_label == "Agent A"


def test_setup_status_line_persists_ids_colors_and_refreshes():
    state = StatusControlsState()

    setup_status_line(state, ["model", "git-branch"], use_theme_colors=True)

    assert state.config.tui_status_line == ["model", "git-branch"]
    assert state.config.tui_status_line_use_colors is True
    assert state.refreshed_status_surfaces == 1


def test_refresh_status_line_forwards_to_status_surfaces():
    state = StatusControlsState()

    refresh_status_line(state)
    cancel_status_line_setup(state)

    assert state.refreshed_status_surfaces == 1


def test_terminal_title_preview_revert_and_setup_semantics():
    state = StatusControlsState(config=StatusControlsConfig(tui_terminal_title=["app-name"]))

    preview_terminal_title(state, ["status", "model"])
    assert state.config.tui_terminal_title == ["status", "model"]
    assert state.terminal_title_setup_original_items == ["app-name"]
    assert state.refreshed_terminal_title == 1

    preview_terminal_title(state, ["cwd"])
    assert state.terminal_title_setup_original_items == ["app-name"]

    revert_terminal_title_setup_preview(state)
    assert state.config.tui_terminal_title == ["app-name"]
    assert state.terminal_title_setup_original_items is None

    preview_terminal_title(state, ["status"])
    setup_terminal_title(state, ["model"])
    assert state.config.tui_terminal_title == ["model"]
    before = state.refreshed_terminal_title
    revert_terminal_title_setup_preview(state)
    assert state.refreshed_terminal_title == before


def test_terminal_title_revert_preserves_original_none():
    state = StatusControlsState(config=StatusControlsConfig(tui_terminal_title=None))

    preview_terminal_title(state, ["status"])
    revert_terminal_title_setup_preview(state)

    assert state.config.tui_terminal_title is None


def test_status_line_branch_and_git_summary_ignore_stale_cwd():
    state = StatusControlsState(status_line_branch_cwd=Path("/repo"), status_line_branch_pending=True)

    set_status_line_branch(state, Path("/other"), "main")
    assert state.status_line_branch is None
    assert state.status_line_branch_pending is False
    assert state.status_line_branch_lookup_complete is False

    state.status_line_branch_pending = True
    set_status_line_branch(state, Path("/repo"), "main")
    assert state.status_line_branch == "main"
    assert state.status_line_branch_pending is False
    assert state.status_line_branch_lookup_complete is True
    assert state.refreshed_status_surfaces == 1

    state.status_line_git_summary_cwd = Path("/repo")
    state.status_line_git_summary_pending = True
    set_status_line_git_summary(state, Path("/other"), {"dirty": True})
    assert state.status_line_git_summary is None
    assert state.status_line_git_summary_pending is False

    state.status_line_git_summary_pending = True
    set_status_line_git_summary(state, Path("/repo"), {"dirty": True})
    assert state.status_line_git_summary == {"dirty": True}
    assert state.status_line_git_summary_lookup_complete is True


def test_context_window_remaining_used_and_total_usage_semantics():
    state = StatusControlsState(config=StatusControlsConfig(model_context_window=1000))
    assert status_line_context_window_size(state) == 1000
    assert status_line_context_remaining_percent(state) == 100
    assert status_line_context_used_percent(state) == 0
    assert status_line_total_usage(state) == TokenUsage()

    state.token_info = TokenInfo(
        total_token_usage=TokenUsage(total_tokens=300),
        last_token_usage=TokenUsage(total_tokens=250),
        model_context_window=500,
    )
    assert status_line_context_window_size(state) == 500
    assert status_line_context_remaining_percent(state) == 50
    assert status_line_context_used_percent(state) == 50
    assert status_line_total_usage(state) == TokenUsage(total_tokens=300)


def test_add_status_output_and_finish_rate_limit_refresh_semantics():
    state = StatusControlsState(
        token_info=TokenInfo(total_token_usage=TokenUsage(total_tokens=42)),
        rate_limit_snapshots_by_limit_id={"codex": RateLimitWindowDisplay(used_percent=25.0)},
        model="gpt-test",
        collaboration_mode="solo",
    )

    cell = add_status_output(state, refreshing_rate_limits=True, request_id=7)

    assert cell == StatusOutputCell(
        refreshing_rate_limits=True,
        request_id=7,
        token_info=state.token_info,
        total_usage=TokenUsage(total_tokens=42),
        rate_limit_snapshots=[RateLimitWindowDisplay(used_percent=25.0)],
        model="gpt-test",
        collaboration_mode="solo",
        reasoning_effort_override=None,
    )
    assert state.history == [cell]
    assert len(state.refreshing_status_outputs) == 1

    state.rate_limit_snapshots_by_limit_id["codex"] = RateLimitWindowDisplay(used_percent=10.0)
    finish_status_rate_limit_refresh(state, 7, now="now")

    assert state.refreshing_status_outputs == []
    assert state.redraw_requests == 1


def test_preview_data_and_setup_view_semantics():
    state = StatusControlsState(
        config=StatusControlsConfig(tui_status_line=["model"], tui_terminal_title=["status"]),
        preview_values={"model": "gpt-test"},
        terminal_title_values={"status": "Working"},
        rate_limit_snapshots_by_limit_id={"codex": RateLimitWindowDisplay(used_percent=25.0)},
    )

    preview = status_surface_preview_data(state)
    assert preview == StatusSurfacePreviewData(
        live_values={"model": "gpt-test"},
        suppressed_placeholders=["five_hour_limit", "weekly_limit"],
    )
    title_preview = terminal_title_preview_data(state)
    assert title_preview.live_values["status"] == "Working"

    status_view = open_status_line_setup(state)
    assert status_view == SetupViewRequest(
        kind="status_line",
        configured_items=["model"],
        use_theme_colors=False,
        preview_data=preview,
        keymap=None,
    )

    title_view = open_terminal_title_setup(state)
    assert title_view.kind == "terminal_title"
    assert title_view.configured_items == ["status"]
    assert state.bottom_pane.shown_views == [status_view, title_view]


def test_limit_display_clamps_remaining_percent_and_formats_label():
    assert status_line_limit_display(None, "5h") is None
    assert status_line_limit_display(RateLimitWindowDisplay(used_percent=17.2), "5h") == "5h 83% left"
    assert status_line_limit_display(RateLimitWindowDisplay(used_percent=-20), "5h") == "5h 100% left"
    assert status_line_limit_display(RateLimitWindowDisplay(used_percent=120), "5h") == "5h 0% left"


def test_reasoning_effort_label_matches_rust_mapping():
    assert status_line_reasoning_effort_label(ReasoningEffortConfig.Minimal) == "minimal"
    assert status_line_reasoning_effort_label(ReasoningEffortConfig.Low) == "low"
    assert status_line_reasoning_effort_label(ReasoningEffortConfig.Medium) == "medium"
    assert status_line_reasoning_effort_label(ReasoningEffortConfig.High) == "high"
    assert status_line_reasoning_effort_label(ReasoningEffortConfig.XHigh) == "xhigh"
    assert status_line_reasoning_effort_label(ReasoningEffortConfig.None_) == "default"
    assert status_line_reasoning_effort_label(None) == "default"


def test_set_status_does_not_refresh_surfaces_when_terminal_title_ignores_status() -> None:
    state = StatusControlsState(config=StatusControlsConfig(tui_terminal_title=["model", "cwd"]))

    set_status(state, "Working", " details", StatusDetailsCapitalization.Preserve, 1)

    assert state.refreshed_status_surfaces == 0
    assert state.bottom_pane.status_updates[-1] == ("Working", "details", StatusDetailsCapitalization.Preserve, 1)


def test_cancel_terminal_title_setup_reverts_preview() -> None:
    state = StatusControlsState(config=StatusControlsConfig(tui_terminal_title=["app-name"]))

    preview_terminal_title(state, ["status"])
    cancel_terminal_title_setup(state)

    assert state.config.tui_terminal_title == ["app-name"]
    assert state.terminal_title_setup_original_items is None
    assert state.refreshed_terminal_title == 2


def test_finish_status_rate_limit_refresh_ignores_missing_request_without_redraw() -> None:
    state = StatusControlsState()
    cell = add_status_output(state, refreshing_rate_limits=True, request_id=7)

    finish_status_rate_limit_refresh(state, 8, now="now")

    assert state.refreshing_status_outputs[0][0] == 7
    assert state.refreshing_status_outputs[0][1].cell is cell
    assert state.redraw_requests == 0


def test_add_status_output_without_request_id_does_not_track_refresh_handle() -> None:
    state = StatusControlsState()

    cell = add_status_output(state, refreshing_rate_limits=False, request_id=None)

    assert state.history == [cell]
    assert state.refreshing_status_outputs == []
