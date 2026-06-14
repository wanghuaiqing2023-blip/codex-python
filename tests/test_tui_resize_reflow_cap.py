from pycodex.tui.resize_reflow_cap import (
    ALACRITTY_RESIZE_REFLOW_MAX_ROWS,
    DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS,
    VSCODE_RESIZE_REFLOW_MAX_ROWS,
    WEZTERM_RESIZE_REFLOW_MAX_ROWS,
    WINDOWS_TERMINAL_RESIZE_REFLOW_MAX_ROWS,
    TerminalInfo,
    TerminalName,
    TerminalResizeReflowConfig,
    TerminalResizeReflowMaxRows,
    auto_resize_reflow_max_rows,
    resize_reflow_max_rows,
    resize_reflow_max_rows_for,
)


def test_auto_resize_reflow_max_rows_uses_terminal_defaults():
    # Rust: codex-tui, resize_reflow_cap.rs, auto_resize_reflow_max_rows_uses_terminal_defaults.
    cases = [
        (TerminalName.VSCODE, VSCODE_RESIZE_REFLOW_MAX_ROWS),
        (TerminalName.WINDOWS_TERMINAL, WINDOWS_TERMINAL_RESIZE_REFLOW_MAX_ROWS),
        (TerminalName.WEZTERM, WEZTERM_RESIZE_REFLOW_MAX_ROWS),
        (TerminalName.ALACRITTY, ALACRITTY_RESIZE_REFLOW_MAX_ROWS),
        (TerminalName.GHOSTTY, DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS),
        (TerminalName.UNKNOWN, DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS),
    ]

    for terminal_name, expected_max_rows in cases:
        assert auto_resize_reflow_max_rows(terminal_name, running_in_vscode_terminal=False) == expected_max_rows


def test_auto_resize_reflow_max_rows_fallback_bucket_covers_all_other_terminals():
    # Rust: resize_reflow_cap.rs::auto_resize_reflow_max_rows fallback match arm.
    fallback_names = [
        TerminalName.APPLE_TERMINAL,
        TerminalName.GHOSTTY,
        TerminalName.ITERM2,
        TerminalName.WARP_TERMINAL,
        TerminalName.KITTY,
        TerminalName.KONSOLE,
        TerminalName.GNOME_TERMINAL,
        TerminalName.VTE,
        TerminalName.DUMB,
        TerminalName.UNKNOWN,
    ]

    for terminal_name in fallback_names:
        assert (
            auto_resize_reflow_max_rows(terminal_name, running_in_vscode_terminal=False)
            == DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS
        )


def test_auto_resize_reflow_max_rows_prefers_vscode_probe():
    # Rust: codex-tui, resize_reflow_cap.rs, auto_resize_reflow_max_rows_prefers_vscode_probe.
    assert (
        auto_resize_reflow_max_rows(TerminalName.WINDOWS_TERMINAL, running_in_vscode_terminal=True)
        == VSCODE_RESIZE_REFLOW_MAX_ROWS
    )


def test_configured_resize_reflow_max_rows_overrides_auto_detection():
    # Rust: codex-tui, resize_reflow_cap.rs, configured_resize_reflow_max_rows_overrides_auto_detection.
    terminal = TerminalInfo(name=TerminalName.VSCODE)
    config = TerminalResizeReflowConfig(max_rows=TerminalResizeReflowMaxRows.limit_rows(42))

    assert resize_reflow_max_rows_for(config, terminal, running_in_vscode_terminal=False) == 42


def test_disabled_resize_reflow_max_rows_keeps_all_rows():
    # Rust: codex-tui, resize_reflow_cap.rs, disabled_resize_reflow_max_rows_keeps_all_rows.
    terminal = TerminalInfo(name=TerminalName.VSCODE)
    config = TerminalResizeReflowConfig(max_rows=TerminalResizeReflowMaxRows.disabled())

    assert resize_reflow_max_rows_for(config, terminal, running_in_vscode_terminal=False) is None


def test_unknown_terminal_uses_fallback_even_under_multiplexer():
    # Rust: codex-tui, resize_reflow_cap.rs, unknown_terminal_uses_fallback_even_under_multiplexer.
    terminal = TerminalInfo(
        name=TerminalName.UNKNOWN,
        term="xterm-256color",
        multiplexer={"kind": "tmux", "version": None},
    )

    assert (
        resize_reflow_max_rows_for(
            TerminalResizeReflowConfig(),
            terminal,
            running_in_vscode_terminal=False,
        )
        == DEFAULT_TERMINAL_RESIZE_REFLOW_FALLBACK_MAX_ROWS
    )


def test_public_resolver_accepts_scalar_config_shapes():
    terminal = TerminalInfo(name=TerminalName.ALACRITTY)

    assert resize_reflow_max_rows("auto", terminal=terminal) == ALACRITTY_RESIZE_REFLOW_MAX_ROWS
    assert resize_reflow_max_rows(0, terminal=terminal) is None
    assert resize_reflow_max_rows(123, terminal=terminal) == 123
