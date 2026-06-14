import pycodex.tui.tui.keyboard_modes as km


def test_keyboard_enhancement_env_flag_parses_common_values_matches_rust() -> None:
    # Rust: tui/keyboard_modes.rs keyboard_enhancement_env_flag_parses_common_values
    assert km.keyboard_enhancement_env_flag_parses_common_values()


def test_keyboard_enhancement_auto_disables_for_vscode_in_wsl_matches_rust() -> None:
    # Rust: keyboard_enhancement_auto_disables_for_vscode_in_wsl
    assert km.keyboard_enhancement_auto_disables_for_vscode_in_wsl()


def test_keyboard_enhancement_auto_disable_requires_wsl_and_vscode_matches_rust() -> None:
    # Rust: keyboard_enhancement_auto_disable_requires_wsl_and_vscode
    assert km.keyboard_enhancement_auto_disable_requires_wsl_and_vscode()


def test_keyboard_enhancement_env_flag_overrides_auto_detection_matches_rust() -> None:
    # Rust: keyboard_enhancement_env_flag_overrides_auto_detection
    assert km.keyboard_enhancement_env_flag_overrides_auto_detection()


def test_vscode_terminal_detection_uses_linux_and_windows_term_program_matches_rust() -> None:
    # Rust: vscode_terminal_detection_uses_linux_and_windows_term_program
    assert km.vscode_terminal_detection_uses_linux_and_windows_term_program()


def test_tmux_session_detection_accepts_tmux_or_tmux_pane_matches_rust() -> None:
    # Rust: tmux_session_detection_accepts_tmux_or_tmux_pane
    assert km.tmux_session_detection_accepts_tmux_or_tmux_pane()


def test_tmux_modify_other_keys_only_requests_confirmed_csi_u_format_matches_rust() -> None:
    # Rust: tmux_modify_other_keys_only_requests_confirmed_csi_u_format
    assert km.tmux_modify_other_keys_only_requests_confirmed_csi_u_format()


def test_reset_keyboard_enhancement_flags_clears_all_pushed_levels_matches_rust() -> None:
    # Rust: reset_keyboard_enhancement_flags_clears_all_pushed_levels
    assert km.reset_keyboard_enhancement_flags_clears_all_pushed_levels()


def test_enable_modify_other_keys_requests_xterm_keyboard_reporting_matches_rust() -> None:
    # Rust: enable_modify_other_keys_requests_xterm_keyboard_reporting
    assert km.enable_modify_other_keys_requests_xterm_keyboard_reporting()


def test_disable_modify_other_keys_resets_xterm_keyboard_reporting_matches_rust() -> None:
    # Rust: disable_modify_other_keys_resets_xterm_keyboard_reporting
    assert km.disable_modify_other_keys_resets_xterm_keyboard_reporting()


def test_enable_keyboard_enhancement_returns_semantic_command_sequence() -> None:
    env = {"TMUX": "/tmp/tmux"}

    assert km.enable_keyboard_enhancement(env, "csi-u") == [
        "\x1b[>4;0m",
        "PushKeyboardEnhancementFlags",
        "\x1b[>4;2m",
    ]
    assert km.enable_keyboard_enhancement(
        {km.DISABLE_KEYBOARD_ENHANCEMENT_ENV_VAR: "1"},
        "csi-u",
    ) == []


def test_restore_and_reset_sequences_preserve_rust_order() -> None:
    assert km.restore_keyboard_enhancement_stack() == [
        "PopKeyboardEnhancementFlags",
        "\x1b[>4;0m",
    ]
    assert km.reset_keyboard_reporting_after_exit() == [
        "PopKeyboardEnhancementFlags",
        "\x1b[<u",
        "\x1b[>4;0m",
    ]


def test_read_helpers_parse_command_output_semantics() -> None:
    assert km.read_windows_term_program("OTHER=x\nTERM_PROGRAM=vscode\r\n") == "vscode"
    assert km.read_windows_term_program("TERM_PROGRAM=\r\n") is None
    assert km.read_tmux_extended_keys_format(" csi-u\n") == "csi-u"
    assert km.read_tmux_extended_keys_format("\n") is None
