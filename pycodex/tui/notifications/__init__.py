"""Behavior port for Rust ``codex-tui::notifications``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .._porting import RustTuiModule
from .bel import BelBackend
from .osc9 import Osc9Backend

RUST_MODULE = RustTuiModule(crate="codex-tui", module="notifications", source="codex/codex-rs/tui/src/notifications/mod.rs")


class NotificationMethod(Enum):
    AUTO = "auto"
    OSC9 = "osc9"
    BEL = "bel"


class TerminalName(Enum):
    GHOSTTY = "Ghostty"
    ITERM2 = "Iterm2"
    KITTY = "Kitty"
    WARP_TERMINAL = "WarpTerminal"
    WEZTERM = "WezTerm"
    APPLE_TERMINAL = "AppleTerminal"
    ALACRITTY = "Alacritty"
    DUMB = "Dumb"
    GNOME_TERMINAL = "GnomeTerminal"
    KONSOLE = "Konsole"
    UNKNOWN = "Unknown"
    VSCODE = "VsCode"
    VTE = "Vte"
    WINDOWS_TERMINAL = "WindowsTerminal"


@dataclass(frozen=True)
class TerminalInfo:
    name: TerminalName | str
    term_program: str | None = None
    version: str | None = None
    term: str | None = None
    multiplexer: Any = None


@dataclass
class DesktopNotificationBackend:
    kind: NotificationMethod
    backend: Osc9Backend | BelBackend

    @classmethod
    def for_method(
        cls,
        method: NotificationMethod | str,
        *,
        terminal: TerminalInfo | Any | None = None,
        stream: Any = None,
    ) -> "DesktopNotificationBackend":
        method = _coerce_method(method)
        if method is NotificationMethod.AUTO:
            if terminal is not None and supports_osc9(terminal):
                return cls(NotificationMethod.OSC9, Osc9Backend.new(dcs_passthrough=_is_tmux(terminal), stream=stream))
            return cls(NotificationMethod.BEL, BelBackend(stream))
        if method is NotificationMethod.OSC9:
            return cls(NotificationMethod.OSC9, Osc9Backend.new(dcs_passthrough=_is_tmux(terminal), stream=stream))
        if method is NotificationMethod.BEL:
            return cls(NotificationMethod.BEL, BelBackend(stream))
        raise AssertionError(f"unhandled notification method: {method}")

    def method(self) -> NotificationMethod:
        return self.kind

    def notify(self, message: str) -> None:
        self.backend.notify(message)


def detect_backend(
    method: NotificationMethod | str,
    *,
    terminal: TerminalInfo | Any | None = None,
    stream: Any = None,
) -> DesktopNotificationBackend:
    return DesktopNotificationBackend.for_method(method, terminal=terminal, stream=stream)


def supports_osc9(terminal: TerminalInfo | Any) -> bool:
    name = _terminal_name(terminal)
    return name in {
        TerminalName.GHOSTTY,
        TerminalName.ITERM2,
        TerminalName.KITTY,
        TerminalName.WARP_TERMINAL,
        TerminalName.WEZTERM,
    }


def test_terminal(name: TerminalName | str) -> TerminalInfo:
    return TerminalInfo(name=name)


def selects_osc9_method() -> bool:
    return detect_backend(NotificationMethod.OSC9).method() is NotificationMethod.OSC9


def selects_bel_method() -> bool:
    return detect_backend(NotificationMethod.BEL).method() is NotificationMethod.BEL


def supports_osc9_for_supported_terminals() -> bool:
    return all(
        supports_osc9(test_terminal(name))
        for name in [
            TerminalName.GHOSTTY,
            TerminalName.ITERM2,
            TerminalName.KITTY,
            TerminalName.WARP_TERMINAL,
            TerminalName.WEZTERM,
        ]
    )


def supports_osc9_for_unsupported_terminals() -> bool:
    return all(
        not supports_osc9(test_terminal(name))
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
        ]
    )


def _coerce_method(method: NotificationMethod | str) -> NotificationMethod:
    if isinstance(method, NotificationMethod):
        return method
    normalized = str(method).lower()
    mapping = {
        "auto": NotificationMethod.AUTO,
        "notificationmethod.auto": NotificationMethod.AUTO,
        "osc9": NotificationMethod.OSC9,
        "notificationmethod.osc9": NotificationMethod.OSC9,
        "bel": NotificationMethod.BEL,
        "notificationmethod.bel": NotificationMethod.BEL,
    }
    if normalized not in mapping:
        raise ValueError(f"unknown notification method: {method}")
    return mapping[normalized]


def _terminal_name(terminal: TerminalInfo | Any) -> TerminalName | str:
    raw = terminal.get("name") if isinstance(terminal, dict) else getattr(terminal, "name", terminal)
    if isinstance(raw, TerminalName):
        return raw
    text = str(raw)
    for name in TerminalName:
        if text in {name.value, name.name, name.name.lower(), name.value.lower()}:
            return name
    return text


def _is_tmux(terminal: TerminalInfo | Any | None) -> bool:
    if terminal is None:
        return False
    mux = terminal.get("multiplexer") if isinstance(terminal, dict) else getattr(terminal, "multiplexer", None)
    if mux is None:
        return False
    if isinstance(mux, dict):
        mux = mux.get("type", mux.get("name", mux))
    return "tmux" in str(mux).lower()


__all__ = [
    "DesktopNotificationBackend",
    "NotificationMethod",
    "RUST_MODULE",
    "TerminalInfo",
    "TerminalName",
    "detect_backend",
    "selects_bel_method",
    "selects_osc9_method",
    "supports_osc9",
    "supports_osc9_for_supported_terminals",
    "supports_osc9_for_unsupported_terminals",
    "test_terminal",
]
