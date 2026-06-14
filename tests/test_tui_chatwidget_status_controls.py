from pathlib import Path

from pycodex.tui.chatwidget.status_controls import (
    RateLimitWindowDisplay,
    ReasoningEffortConfig,
    StatusControlsConfig,
    StatusControlsState,
    StatusDetailsCapitalization,
    TokenInfo,
    TokenUsage,
    preview_terminal_title,
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
    assert state.refreshed_status_line == 1


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
    assert state.terminal_title_setup_original_items is None
    before = state.refreshed_terminal_title
    revert_terminal_title_setup_preview(state)
    assert state.refreshed_terminal_title == before


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
