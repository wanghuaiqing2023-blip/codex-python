from __future__ import annotations

from pycodex.terminal_detection import (
    Multiplexer,
    TerminalInfo,
    TerminalName,
    TmuxClientInfo,
    parse_zellij_version,
    terminal_info,
    user_agent,
)


def test_detects_term_program() -> None:
    # Rust: terminal_tests.rs detects_term_program.
    env = {"TERM_PROGRAM": "iTerm.app", "TERM_PROGRAM_VERSION": "3.5.0", "WEZTERM_VERSION": "2024.2"}
    assert terminal_info(env) == TerminalInfo(TerminalName.ITERM2, term_program="iTerm.app", version="3.5.0")
    assert user_agent(env) == "iTerm.app/3.5.0"

    env = {"TERM_PROGRAM": "iTerm.app", "TERM_PROGRAM_VERSION": ""}
    assert terminal_info(env) == TerminalInfo(TerminalName.ITERM2, term_program="iTerm.app")
    assert user_agent(env) == "iTerm.app"


def test_terminal_info_reports_is_zellij() -> None:
    # Rust: terminal_tests.rs terminal_info_reports_is_zellij.
    assert TerminalInfo(TerminalName.UNKNOWN, multiplexer=Multiplexer.zellij()).is_zellij()
    assert not TerminalInfo(TerminalName.UNKNOWN, multiplexer=Multiplexer.tmux()).is_zellij()


def test_detects_named_terminals_from_explicit_environment() -> None:
    # Rust: terminal_tests.rs detects_iterm2/detects_apple_terminal/detects_ghostty/detects_vscode/detects_warp_terminal.
    cases = [
        ({"ITERM_SESSION_ID": "w0t1p0"}, TerminalInfo(TerminalName.ITERM2), "iTerm.app"),
        ({"TERM_PROGRAM": "Apple_Terminal"}, TerminalInfo(TerminalName.APPLE_TERMINAL, term_program="Apple_Terminal"), "Apple_Terminal"),
        ({"TERM_SESSION_ID": "A1B2C3"}, TerminalInfo(TerminalName.APPLE_TERMINAL), "Apple_Terminal"),
        ({"TERM_PROGRAM": "Ghostty"}, TerminalInfo(TerminalName.GHOSTTY, term_program="Ghostty"), "Ghostty"),
        ({"TERM_PROGRAM": "vscode", "TERM_PROGRAM_VERSION": "1.86.0"}, TerminalInfo(TerminalName.VSCODE, term_program="vscode", version="1.86.0"), "vscode/1.86.0"),
        (
            {"TERM_PROGRAM": "WarpTerminal", "TERM_PROGRAM_VERSION": "v0.2025.12.10.08.12.stable_03"},
            TerminalInfo(TerminalName.WARP_TERMINAL, term_program="WarpTerminal", version="v0.2025.12.10.08.12.stable_03"),
            "WarpTerminal/v0.2025.12.10.08.12.stable_03",
        ),
    ]
    for env, expected, token in cases:
        assert terminal_info(env) == expected
        assert user_agent(env) == token


def test_detects_tmux_multiplexer_and_client_details() -> None:
    # Rust: detects_tmux_multiplexer/detects_tmux_client_termtype/detects_tmux_client_termname/detects_tmux_term_program_uses_client_termtype.
    terminal = terminal_info(
        {"TMUX": "/tmp/tmux-1000/default,123,0", "TERM_PROGRAM": "tmux"},
        tmux_client_info=TmuxClientInfo("xterm-256color", "screen-256color"),
    )
    assert terminal == TerminalInfo(
        TerminalName.UNKNOWN,
        term_program="xterm-256color",
        term="screen-256color",
        multiplexer=Multiplexer.tmux(),
    )
    assert terminal.user_agent_token() == "xterm-256color"

    terminal = terminal_info(
        {"TMUX": "/tmp/tmux-1000/default,123,0", "TERM_PROGRAM": "tmux"},
        tmux_client_info=TmuxClientInfo("WezTerm", None),
    )
    assert terminal == TerminalInfo(TerminalName.WEZTERM, term_program="WezTerm", multiplexer=Multiplexer.tmux())

    terminal = terminal_info(
        {"TMUX": "/tmp/tmux-1000/default,123,0", "TERM_PROGRAM": "tmux"},
        tmux_client_info=TmuxClientInfo(None, "xterm-256color"),
    )
    assert terminal == TerminalInfo(TerminalName.UNKNOWN, term="xterm-256color", multiplexer=Multiplexer.tmux())

    terminal = terminal_info(
        {"TMUX": "/tmp/tmux-1000/default,123,0", "TERM_PROGRAM": "tmux", "TERM_PROGRAM_VERSION": "3.6a"},
        tmux_client_info=TmuxClientInfo("ghostty 1.2.3", "xterm-ghostty"),
    )
    assert terminal == TerminalInfo(
        TerminalName.GHOSTTY,
        term_program="ghostty",
        version="1.2.3",
        term="xterm-ghostty",
        multiplexer=Multiplexer.tmux("3.6a"),
    )
    assert terminal.user_agent_token() == "ghostty/1.2.3"


def test_detects_zellij_multiplexer_and_parses_version() -> None:
    # Rust: detects_zellij_multiplexer/detects_zellij_multiplexer_version/detects_zellij_multiplexer_command_version/parses_zellij_version_output.
    assert terminal_info({"ZELLIJ": "1"}) == TerminalInfo(TerminalName.UNKNOWN, multiplexer=Multiplexer.zellij())
    assert terminal_info({"ZELLIJ_VERSION": "0.43.1"}) == TerminalInfo(
        TerminalName.UNKNOWN, multiplexer=Multiplexer.zellij("0.43.1")
    )
    assert terminal_info({"ZELLIJ": "1"}, zellij_version="0.44.1") == TerminalInfo(
        TerminalName.UNKNOWN, multiplexer=Multiplexer.zellij("0.44.1")
    )
    assert parse_zellij_version("zellij 0.44.1") == "0.44.1"
    assert parse_zellij_version("0.44.1") == "0.44.1"
    assert parse_zellij_version("") is None


def test_detects_wezterm_variants() -> None:
    # Rust: terminal_tests.rs detects_wezterm.
    cases = [
        ({"WEZTERM_VERSION": "2024.2"}, TerminalInfo(TerminalName.WEZTERM, version="2024.2"), "WezTerm/2024.2"),
        ({"TERM_PROGRAM": "WezTerm", "TERM_PROGRAM_VERSION": "2024.2"}, TerminalInfo(TerminalName.WEZTERM, term_program="WezTerm", version="2024.2"), "WezTerm/2024.2"),
        ({"WEZTERM_VERSION": ""}, TerminalInfo(TerminalName.WEZTERM), "WezTerm"),
        ({"TERM": "wezterm"}, TerminalInfo(TerminalName.WEZTERM, term="wezterm"), "wezterm"),
        ({"TERM": "wezterm-mux"}, TerminalInfo(TerminalName.WEZTERM, term="wezterm-mux"), "wezterm-mux"),
    ]
    for env, expected, token in cases:
        assert terminal_info(env) == expected
        assert user_agent(env) == token


def test_detects_kitty_and_alacritty_priority() -> None:
    # Rust: terminal_tests.rs detects_kitty and detects_alacritty.
    assert terminal_info({"KITTY_WINDOW_ID": "1"}) == TerminalInfo(TerminalName.KITTY)
    assert user_agent({"KITTY_WINDOW_ID": "1"}) == "kitty"
    assert terminal_info({"TERM_PROGRAM": "kitty", "TERM_PROGRAM_VERSION": "0.30.1"}) == TerminalInfo(
        TerminalName.KITTY, term_program="kitty", version="0.30.1"
    )
    assert terminal_info({"TERM": "xterm-kitty", "ALACRITTY_SOCKET": "/tmp/alacritty"}) == TerminalInfo(TerminalName.KITTY)

    assert terminal_info({"ALACRITTY_SOCKET": "/tmp/alacritty"}) == TerminalInfo(TerminalName.ALACRITTY)
    assert user_agent({"ALACRITTY_SOCKET": "/tmp/alacritty"}) == "Alacritty"
    assert terminal_info({"TERM_PROGRAM": "Alacritty", "TERM_PROGRAM_VERSION": "0.13.2"}) == TerminalInfo(
        TerminalName.ALACRITTY, term_program="Alacritty", version="0.13.2"
    )
    assert terminal_info({"TERM": "alacritty"}) == TerminalInfo(TerminalName.ALACRITTY)


def test_detects_desktop_terminal_families() -> None:
    # Rust: detects_konsole/detects_gnome_terminal/detects_vte/detects_windows_terminal.
    cases = [
        ({"KONSOLE_VERSION": "230800"}, TerminalInfo(TerminalName.KONSOLE, version="230800"), "Konsole/230800"),
        ({"TERM_PROGRAM": "Konsole", "TERM_PROGRAM_VERSION": "230800"}, TerminalInfo(TerminalName.KONSOLE, term_program="Konsole", version="230800"), "Konsole/230800"),
        ({"KONSOLE_VERSION": ""}, TerminalInfo(TerminalName.KONSOLE), "Konsole"),
        ({"GNOME_TERMINAL_SCREEN": "1"}, TerminalInfo(TerminalName.GNOME_TERMINAL), "gnome-terminal"),
        ({"TERM_PROGRAM": "gnome-terminal", "TERM_PROGRAM_VERSION": "3.50"}, TerminalInfo(TerminalName.GNOME_TERMINAL, term_program="gnome-terminal", version="3.50"), "gnome-terminal/3.50"),
        ({"VTE_VERSION": "7000"}, TerminalInfo(TerminalName.VTE, version="7000"), "VTE/7000"),
        ({"TERM_PROGRAM": "VTE", "TERM_PROGRAM_VERSION": "7000"}, TerminalInfo(TerminalName.VTE, term_program="VTE", version="7000"), "VTE/7000"),
        ({"WT_SESSION": "1"}, TerminalInfo(TerminalName.WINDOWS_TERMINAL), "WindowsTerminal"),
        ({"TERM_PROGRAM": "WindowsTerminal", "TERM_PROGRAM_VERSION": "1.21"}, TerminalInfo(TerminalName.WINDOWS_TERMINAL, term_program="WindowsTerminal", version="1.21"), "WindowsTerminal/1.21"),
    ]
    for env, expected, token in cases:
        assert terminal_info(env) == expected
        assert user_agent(env) == token


def test_detects_term_fallbacks() -> None:
    # Rust: terminal_tests.rs detects_term_fallbacks.
    cases = [
        ({"TERM": "xterm-256color"}, TerminalInfo(TerminalName.UNKNOWN, term="xterm-256color"), "xterm-256color"),
        ({"TERM": "dumb"}, TerminalInfo(TerminalName.DUMB, term="dumb"), "dumb"),
        ({}, TerminalInfo(TerminalName.UNKNOWN), "unknown"),
    ]
    for env, expected, token in cases:
        assert terminal_info(env) == expected
        assert user_agent(env) == token


def test_user_agent_token_sanitizes_header_value() -> None:
    # Rust: sanitize_header_value replaces invalid User-Agent characters with underscores.
    terminal = TerminalInfo(TerminalName.UNKNOWN, term_program="Bad Term", version="1(2)")
    assert terminal.user_agent_token() == "Bad_Term/1_2_"
