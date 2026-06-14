from __future__ import annotations

from io import StringIO

from pycodex.tui.notifications import (
    DesktopNotificationBackend,
    NotificationMethod,
    TerminalInfo,
    TerminalName,
    detect_backend,
    selects_bel_method,
    selects_osc9_method,
    supports_osc9,
    supports_osc9_for_supported_terminals,
    supports_osc9_for_unsupported_terminals,
    test_terminal,
)


def test_selects_osc9_method() -> None:
    assert selects_osc9_method() is True
    assert detect_backend(NotificationMethod.OSC9).method() is NotificationMethod.OSC9


def test_selects_bel_method() -> None:
    assert selects_bel_method() is True
    assert detect_backend(NotificationMethod.BEL).method() is NotificationMethod.BEL


def test_supports_osc9_for_supported_terminals() -> None:
    assert supports_osc9_for_supported_terminals() is True
    for name in [
        TerminalName.GHOSTTY,
        TerminalName.ITERM2,
        TerminalName.KITTY,
        TerminalName.WARP_TERMINAL,
        TerminalName.WEZTERM,
    ]:
        assert supports_osc9(test_terminal(name)) is True


def test_supports_osc9_for_unsupported_terminals() -> None:
    assert supports_osc9_for_unsupported_terminals() is True
    for name in [
        TerminalName.APPLE_TERMINAL,
        TerminalName.ALACRITTY,
        TerminalName.DUMB,
        TerminalName.GNOME_TERMINAL,
        TerminalName.KONSOLE,
        TerminalName.UNKNOWN,
        TerminalName.VSCODE,
        TerminalName.VTE,
        TerminalName.WINDOWS_TERMINAL,
    ]:
        assert supports_osc9(test_terminal(name)) is False


def test_auto_detects_osc9_only_for_supported_terminal() -> None:
    assert detect_backend(NotificationMethod.AUTO, terminal=test_terminal(TerminalName.KITTY)).method() is NotificationMethod.OSC9
    assert detect_backend(NotificationMethod.AUTO, terminal=test_terminal(TerminalName.ALACRITTY)).method() is NotificationMethod.BEL


def test_notify_delegates_to_selected_backend() -> None:
    stream = StringIO()
    backend = detect_backend(NotificationMethod.OSC9, stream=stream)

    backend.notify("done")

    assert stream.getvalue() == "\x1b]9;done\x07"

    stream = StringIO()
    backend = detect_backend(NotificationMethod.BEL, stream=stream)

    backend.notify("ignored")

    assert stream.getvalue() == "\x07"


def test_auto_tmux_supported_terminal_sets_osc9_passthrough() -> None:
    terminal = TerminalInfo(TerminalName.KITTY, multiplexer={"type": "Tmux"})
    stream = StringIO()
    backend = DesktopNotificationBackend.for_method("auto", terminal=terminal, stream=stream)

    backend.notify("done")

    assert backend.method() is NotificationMethod.OSC9
    assert stream.getvalue() == "\x1bPtmux;\x1b\x1b]9;done\x07\x1b\\"
