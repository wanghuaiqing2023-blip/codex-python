from pycodex.tui.bottom_pane.footer import (
    CollaborationModeIndicator,
    FooterKeyHints,
    FooterMode,
    FooterProps,
    GoalStatusIndicator,
    ShortcutId,
    ShortcutsState,
    SummaryLeft,
    TerminalIdleFooterData,
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
    goal_status_indicator_line,
    status_line_right_indicator_line,
    run_terminal_idle_footer_text,
    run_terminal_idle_footer_text_from_runtime,
    terminal_idle_footer_data_from_runtime,
    terminal_footer_projection,
    terminal_idle_footer_text,
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
    assert esc_hint_line(FooterProps(esc_backtrack_hint=False)) == "esc esc to edit previous message"
    assert esc_hint_line(FooterProps(esc_backtrack_hint=True)) == "esc again to edit previous message"


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
    assert "ctrl + alt + v to paste images" in paste_descriptor

    non_wsl = shortcut_overlay_lines(ShortcutsState(is_wsl=False))
    assert any("ctrl + v to paste images" in line for line in non_wsl)


def test_shortcut_overlay_lines_match_rust_footer_snapshot_semantics():
    # Rust source/test contract:
    # - codex-tui/src/bottom_pane/footer.rs::shortcut_overlay_lines orders
    #   shortcut hints in two columns and appends the /keymap customization row.
    # - Snapshot:
    #   bottom_pane/chat_composer__tests__footer_mode_shortcut_overlay.snap.
    lines = shortcut_overlay_lines(ShortcutsState(use_shift_enter_hint=True))

    assert any("/ for commands" in line and "! for shell commands" in line for line in lines)
    assert any("shift + Enter for newline" in line and "Tab to queue message" in line for line in lines)
    assert any("@ for file paths" in line and "ctrl + v to paste images" in line for line in lines)
    assert any("ctrl + r search history" in line and "ctrl + c to exit" in line for line in lines)
    assert any("alt + , reasoning down" in line and "alt + . reasoning up" in line for line in lines)
    assert "ctrl + t to view transcript" in lines
    assert lines[-1] == "customize shortcuts with /keymap"


def test_default_key_hints_match_rust_test_bindings_shape():
    hints = FooterKeyHints.default_bindings()
    assert hints.toggle_shortcuts.code == "?"
    assert hints.queue.code == "Tab"
    assert hints.insert_newline == ctrl("j")
    assert hints.history_search.code == "r"


def test_passive_status_line_combines_agent_and_yields_to_queue_hint():
    # Rust source/test contract:
    # - codex-tui/src/bottom_pane/footer.rs::passive_footer_status_line
    #   appends FooterProps.active_agent_label to an enabled status line with
    #   " · ".
    # - codex-tui/src/bottom_pane/footer.rs::footer_snapshots includes
    #   footer_active_agent_label and footer_status_line_with_active_agent_label.
    props = FooterProps(
        mode=FooterMode.COMPOSER_EMPTY,
        status_line_enabled=True,
        status_line_value="Status line content",
        active_agent_label="Robie [explorer]",
    )

    assert (
        status_line_right_indicator_line("Status line content", "Robie [explorer]")
        == "Status line content · Robie [explorer]"
    )
    assert status_line_right_indicator_line(None, "Robie [explorer]") == "Robie [explorer]"
    assert shows_passive_footer_line(props, show_queue_hint=False) is True
    assert uses_passive_footer_status_layout(props, show_queue_hint=False) is True
    assert footer_from_props_lines(props, show_shortcuts_hint=True) == [
        "Status line content · Robie [explorer]"
    ]

    assert shows_passive_footer_line(props, show_queue_hint=True) is False
    assert uses_passive_footer_status_layout(props, show_queue_hint=True) is False


def test_terminal_idle_footer_text_formats_model_fast_and_cwd():
    # Rust crate/module:
    # - codex-tui::bottom_pane::footer
    # Contract: the real-terminal scrollback path keeps passive footer
    # formatting in the footer module, with caller-provided model/cwd state.
    assert (
        terminal_idle_footer_text(
            TerminalIdleFooterData(
                model_with_reasoning="gpt-test high",
                cwd="C:/repo",
                show_fast_status=True,
            )
        )
        == "gpt-test high fast · ~\\repo"
    )
    assert (
        terminal_idle_footer_text(
            TerminalIdleFooterData(
                model_with_reasoning="gpt-test high fast",
                cwd="C:/repo",
                show_fast_status=True,
            )
        )
        == "gpt-test high fast · ~\\repo"
    )
    assert terminal_idle_footer_text(TerminalIdleFooterData("gpt-test high", None, False)) == "gpt-test high"


def test_terminal_idle_footer_data_from_runtime_uses_runtime_providers():
    # Rust owner: bottom_pane/footer.rs owns passive footer inputs and display
    # shape; the terminal runner should only supply runtime provider callbacks.
    class Runtime:
        model = "gpt-provider"
        cwd = "C:/workspace/repo"
        fast = True

    runtime = Runtime()

    data = terminal_idle_footer_data_from_runtime(
        runtime,
        model_with_reasoning=lambda value: f"{value.model} high",
        cwd=lambda value: value.cwd,
        show_fast_status=lambda value: value.fast,
    )

    assert data == TerminalIdleFooterData(
        model_with_reasoning="gpt-provider high",
        cwd="C:/workspace/repo",
        show_fast_status=True,
    )


def test_run_terminal_idle_footer_text_formats_provider_values():
    class Runtime:
        model = "gpt-provider high"
        cwd = "C:/workspace/repo"
        fast = True

    text = run_terminal_idle_footer_text(
        Runtime(),
        model_with_reasoning=lambda value: value.model,
        cwd=lambda value: value.cwd,
        show_fast_status=lambda value: value.fast,
    )
    assert text == terminal_idle_footer_text(
        TerminalIdleFooterData("gpt-provider high", "C:/workspace/repo", True)
    )


def test_terminal_footer_projection_owns_live_pane_line_clipping():
    # Rust owner: codex-tui::bottom_pane::footer owns passive footer display
    # text before terminal_surface places it in the live viewport.
    projected = terminal_footer_projection("gpt-test high · ~\\codex-python", columns=14)

    assert projected.line == "gpt-test high"


def test_run_terminal_idle_footer_text_from_runtime_uses_canonical_providers(monkeypatch):
    # Rust owner: bottom_pane/footer.rs owns passive footer text.  The terminal
    # runner should ask this module for provider-backed footer formatting.
    from pycodex.tui import runtime_projection

    class Runtime:
        pass

    monkeypatch.setattr(
        runtime_projection,
        "_runtime_model_with_reasoning",
        lambda runtime: "runtime-model high",
    )
    monkeypatch.setattr(runtime_projection, "_runtime_cwd", lambda runtime: "C:/workspace/repo")
    monkeypatch.setattr(runtime_projection, "_runtime_show_fast_status", lambda runtime: True)

    assert run_terminal_idle_footer_text_from_runtime(Runtime()) == terminal_idle_footer_text(
        TerminalIdleFooterData("runtime-model high", "C:/workspace/repo", True)
    )


def test_goal_status_indicator_line_matches_rust_footer_labels():
    # Rust source: codex-tui/src/bottom_pane/footer.rs::goal_status_indicator_line.
    assert goal_status_indicator_line(GoalStatusIndicator.Active("3m")) == "Pursuing goal (3m)"
    assert goal_status_indicator_line(GoalStatusIndicator("Paused")) == "Goal paused (/goal resume)"
    assert goal_status_indicator_line(GoalStatusIndicator("Blocked")) == "Goal blocked (/goal resume)"
    assert goal_status_indicator_line(GoalStatusIndicator("UsageLimited")) == "Goal hit usage limits (/goal resume)"
    assert goal_status_indicator_line(GoalStatusIndicator.BudgetLimited("9K / 10K tokens")) == "Goal unmet (9K / 10K tokens)"
    assert goal_status_indicator_line(GoalStatusIndicator.Complete("12m")) == "Goal achieved (12m)"
    assert (
        status_line_right_indicator_line("gpt-test", goal_status_indicator=GoalStatusIndicator.Active("0s"))
        == "gpt-test · Pursuing goal (0s)"
    )


def test_footer_rust_snapshot_helpers_have_semantic_coverage():
    assert footer_snapshots() is True
    assert footer_status_line_truncates_to_keep_mode_indicator() is True
    assert paste_image_shortcut_prefers_ctrl_alt_v_under_wsl() is True
