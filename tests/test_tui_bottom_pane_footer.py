from pycodex.tui.bottom_pane.footer import (
    CollaborationModeIndicator,
    FooterKeyHints,
    FooterMode,
    FooterProps,
    ShortcutId,
    ShortcutsState,
    SummaryLeft,
    context_window_line,
    ctrl,
    esc_hint_line,
    esc_hint_mode,
    footer_from_props_lines,
    footer_height,
    footer_snapshots,
    footer_status_line_truncates_to_keep_mode_indicator,
    left_fits,
    mode_indicator_line,
    quit_shortcut_reminder_line,
    reset_mode_after_activity,
    paste_image_shortcut_prefers_ctrl_alt_v_under_wsl,
    shortcut_overlay_lines,
    shows_passive_footer_line,
    single_line_footer_layout,
    status_line_right_indicator_line,
    toggle_shortcut_mode,
    uses_passive_footer_status_layout,
)


def test_toggle_shortcut_mode_matches_rust_base_mode_rules():
    assert toggle_shortcut_mode(FooterMode.COMPOSER_EMPTY, False, True) is FooterMode.SHORTCUT_OVERLAY
    assert toggle_shortcut_mode(FooterMode.SHORTCUT_OVERLAY, False, True) is FooterMode.COMPOSER_EMPTY
    assert toggle_shortcut_mode(FooterMode.SHORTCUT_OVERLAY, False, False) is FooterMode.COMPOSER_HAS_DRAFT
    assert (
        toggle_shortcut_mode(FooterMode.QUIT_SHORTCUT_REMINDER, True, True)
        is FooterMode.QUIT_SHORTCUT_REMINDER
    )


def test_esc_and_activity_reset_modes_match_rust_state_machine():
    assert esc_hint_mode(FooterMode.COMPOSER_EMPTY, False) is FooterMode.ESC_HINT
    assert esc_hint_mode(FooterMode.COMPOSER_HAS_DRAFT, True) is FooterMode.COMPOSER_HAS_DRAFT
    assert reset_mode_after_activity(FooterMode.ESC_HINT) is FooterMode.COMPOSER_EMPTY
    assert reset_mode_after_activity(FooterMode.SHORTCUT_OVERLAY) is FooterMode.COMPOSER_EMPTY
    assert reset_mode_after_activity(FooterMode.HISTORY_SEARCH) is FooterMode.COMPOSER_EMPTY
    assert reset_mode_after_activity(FooterMode.COMPOSER_EMPTY) is FooterMode.COMPOSER_EMPTY


def test_footer_height_uses_rendered_line_count_for_modes():
    assert footer_height(FooterProps(mode=FooterMode.COMPOSER_EMPTY)) == 1
    assert footer_height(FooterProps(mode=FooterMode.QUIT_SHORTCUT_REMINDER)) == 1
    overlay_height = footer_height(FooterProps(mode=FooterMode.SHORTCUT_OVERLAY))
    assert overlay_height == len(shortcut_overlay_lines(ShortcutsState()))
    assert overlay_height > 1


def test_quit_and_esc_hint_copy_follows_running_and_backtrack_flags():
    assert quit_shortcut_reminder_line(FooterProps(is_task_running=False)) == "Press ctrl+c again to quit"
    assert quit_shortcut_reminder_line(FooterProps(is_task_running=True)) == "Press ctrl+c again to interrupt"
    assert esc_hint_line(FooterProps(esc_backtrack_hint=False)) == "Press Esc again to clear"
    assert esc_hint_line(FooterProps(esc_backtrack_hint=True)) == "Press Esc again to go back"


def test_footer_from_props_prefers_status_line_but_queue_hint_yields():
    props = FooterProps(status_line_enabled=True, status_line_value="Status line content")
    assert footer_from_props_lines(props, show_shortcuts_hint=True) == ["Status line content"]

    queued = FooterProps(
        mode=FooterMode.COMPOSER_HAS_DRAFT,
        is_task_running=True,
        status_line_enabled=True,
        status_line_value="Status line content",
    )
    assert footer_from_props_lines(queued, show_queue_hint=True) == ["Tab to queue message"]


def test_mode_indicator_and_single_line_layout_semantics():
    assert mode_indicator_line(CollaborationModeIndicator.PLAN, True) == "Plan mode (shift+tab to cycle)"
    assert left_fits({"width": 12}, 10)
    assert not left_fits({"width": 12}, 11)

    left, show_context = single_line_footer_layout(
        {"width": 80},
        context_width=10,
        collaboration_mode_indicator=CollaborationModeIndicator.PLAN,
        show_cycle_hint=True,
        show_shortcuts_hint=True,
        show_queue_hint=False,
        key_hints=FooterKeyHints.default_bindings(),
    )
    assert left == SummaryLeft.Default()
    assert show_context


def test_context_line_and_shortcut_binding_wsl_variant():
    assert context_window_line(72, None) == "72% context left"
    assert context_window_line(None, 123_456) == "123K tokens"

    paste_descriptor = next(descriptor for descriptor in shortcut_overlay_lines(ShortcutsState(is_wsl=True)) if "paste image" in descriptor)
    assert paste_descriptor.startswith("ctrl+alt+v")

    non_wsl = shortcut_overlay_lines(ShortcutsState(is_wsl=False))
    assert any(line.startswith("ctrl+v") and "paste image" in line for line in non_wsl)


def test_default_key_hints_match_rust_test_bindings_shape():
    hints = FooterKeyHints.default_bindings()
    assert hints.toggle_shortcuts.code == "?"
    assert hints.queue.code == "Tab"
    assert hints.insert_newline == ctrl("j")
    assert hints.history_search.code == "r"


def test_passive_status_line_combines_agent_and_yields_to_queue_hint():
    props = FooterProps(
        mode=FooterMode.COMPOSER_EMPTY,
        status_line_enabled=True,
        status_line_value="Status line content",
        active_agent_label="Robie [explorer]",
    )

    assert (
        status_line_right_indicator_line("Status line content", "Robie [explorer]")
        == "Status line content ? Robie [explorer]"
    )
    assert shows_passive_footer_line(props, show_queue_hint=False) is True
    assert uses_passive_footer_status_layout(props, show_queue_hint=False) is True
    assert footer_from_props_lines(props, show_shortcuts_hint=True) == [
        "Status line content ? Robie [explorer]"
    ]

    assert shows_passive_footer_line(props, show_queue_hint=True) is False
    assert uses_passive_footer_status_layout(props, show_queue_hint=True) is False


def test_footer_rust_snapshot_helpers_have_semantic_coverage():
    assert footer_snapshots() is True
    assert footer_status_line_truncates_to_keep_mode_indicator() is True
    assert paste_image_shortcut_prefers_ctrl_alt_v_under_wsl() is True
