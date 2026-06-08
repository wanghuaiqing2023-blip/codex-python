"""Port of Rust ``codex-terminal-detection`` public API.

Rust source:
- ``codex/codex-rs/terminal-detection/src/lib.rs``
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class TerminalName(str, Enum):
    APPLE_TERMINAL = "apple_terminal"
    GHOSTTY = "ghostty"
    ITERM2 = "iterm2"
    WARP_TERMINAL = "warp_terminal"
    VSCODE = "vscode"
    WEZTERM = "wezterm"
    KITTY = "kitty"
    ALACRITTY = "alacritty"
    KONSOLE = "konsole"
    GNOME_TERMINAL = "gnome_terminal"
    VTE = "vte"
    WINDOWS_TERMINAL = "windows_terminal"
    DUMB = "dumb"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Multiplexer:
    type: str
    version: str | None = None

    @classmethod
    def tmux(cls, version: str | None = None) -> "Multiplexer":
        return cls("tmux", version)

    @classmethod
    def zellij(cls, version: str | None = None) -> "Multiplexer":
        return cls("zellij", version)


@dataclass(frozen=True)
class TerminalInfo:
    name: TerminalName
    term_program: str | None = None
    version: str | None = None
    term: str | None = None
    multiplexer: Multiplexer | None = None

    def user_agent_token(self) -> str:
        if self.term_program:
            raw = f"{self.term_program}/{self.version}" if self.version else self.term_program
        elif self.term:
            raw = self.term
        else:
            raw = _format_name_token(self.name, self.version)
        return _sanitize_header_value(raw)

    def is_zellij(self) -> bool:
        return self.multiplexer is not None and self.multiplexer.type == "zellij"


def terminal_info(env: Mapping[str, str] | None = None) -> TerminalInfo:
    return _detect_terminal_info_from_env(os.environ if env is None else env)


def user_agent(env: Mapping[str, str] | None = None) -> str:
    return terminal_info(env).user_agent_token()


def _detect_terminal_info_from_env(env: Mapping[str, str]) -> TerminalInfo:
    multiplexer = _detect_multiplexer(env)
    term_program = _var_non_empty(env, "TERM_PROGRAM")
    if term_program is not None:
        version = _var_non_empty(env, "TERM_PROGRAM_VERSION")
        name = _terminal_name_from_term_program(term_program) or TerminalName.UNKNOWN
        return TerminalInfo(name, term_program=term_program, version=version, multiplexer=multiplexer)
    if "WEZTERM_VERSION" in env:
        return TerminalInfo(TerminalName.WEZTERM, version=_var_non_empty(env, "WEZTERM_VERSION"), multiplexer=multiplexer)
    if any(key in env for key in ("ITERM_SESSION_ID", "ITERM_PROFILE", "ITERM_PROFILE_NAME")):
        return TerminalInfo(TerminalName.ITERM2, multiplexer=multiplexer)
    if "TERM_SESSION_ID" in env:
        return TerminalInfo(TerminalName.APPLE_TERMINAL, multiplexer=multiplexer)
    term = env.get("TERM")
    if "KITTY_WINDOW_ID" in env or (term is not None and "kitty" in term):
        return TerminalInfo(TerminalName.KITTY, multiplexer=multiplexer)
    if "ALACRITTY_SOCKET" in env or term == "alacritty":
        return TerminalInfo(TerminalName.ALACRITTY, multiplexer=multiplexer)
    if "KONSOLE_VERSION" in env:
        return TerminalInfo(TerminalName.KONSOLE, version=_var_non_empty(env, "KONSOLE_VERSION"), multiplexer=multiplexer)
    if "GNOME_TERMINAL_SCREEN" in env:
        return TerminalInfo(TerminalName.GNOME_TERMINAL, multiplexer=multiplexer)
    if "VTE_VERSION" in env:
        return TerminalInfo(TerminalName.VTE, version=_var_non_empty(env, "VTE_VERSION"), multiplexer=multiplexer)
    if "WT_SESSION" in env:
        return TerminalInfo(TerminalName.WINDOWS_TERMINAL, multiplexer=multiplexer)
    if term is not None and term.strip():
        name = TerminalName.DUMB if term == "dumb" else TerminalName.WEZTERM if term in {"wezterm", "wezterm-mux"} else TerminalName.UNKNOWN
        return TerminalInfo(name, term=term, multiplexer=multiplexer)
    return TerminalInfo(TerminalName.UNKNOWN, multiplexer=multiplexer)


def _detect_multiplexer(env: Mapping[str, str]) -> Multiplexer | None:
    if _var_non_empty(env, "TMUX") or _var_non_empty(env, "TMUX_PANE"):
        version = _var_non_empty(env, "TERM_PROGRAM_VERSION") if (env.get("TERM_PROGRAM") or "").lower() == "tmux" else None
        return Multiplexer.tmux(version)
    if _var_non_empty(env, "ZELLIJ") or _var_non_empty(env, "ZELLIJ_SESSION_NAME") or _var_non_empty(env, "ZELLIJ_VERSION"):
        return Multiplexer.zellij(_var_non_empty(env, "ZELLIJ_VERSION"))
    return None


def _terminal_name_from_term_program(value: str) -> TerminalName | None:
    normalized = "".join(ch.lower() for ch in value.strip() if ch not in " -_.")
    return {
        "appleterminal": TerminalName.APPLE_TERMINAL,
        "ghostty": TerminalName.GHOSTTY,
        "iterm": TerminalName.ITERM2,
        "iterm2": TerminalName.ITERM2,
        "itermapp": TerminalName.ITERM2,
        "warp": TerminalName.WARP_TERMINAL,
        "warpterminal": TerminalName.WARP_TERMINAL,
        "vscode": TerminalName.VSCODE,
        "wezterm": TerminalName.WEZTERM,
        "kitty": TerminalName.KITTY,
        "alacritty": TerminalName.ALACRITTY,
        "konsole": TerminalName.KONSOLE,
        "gnometerminal": TerminalName.GNOME_TERMINAL,
        "vte": TerminalName.VTE,
        "windowsterminal": TerminalName.WINDOWS_TERMINAL,
        "dumb": TerminalName.DUMB,
    }.get(normalized)


def _format_name_token(name: TerminalName, version: str | None) -> str:
    mapping = {
        TerminalName.APPLE_TERMINAL: "Apple_Terminal",
        TerminalName.GHOSTTY: "Ghostty",
        TerminalName.ITERM2: "iTerm.app",
        TerminalName.WARP_TERMINAL: "WarpTerminal",
        TerminalName.VSCODE: "vscode",
        TerminalName.WEZTERM: "WezTerm",
        TerminalName.KITTY: "kitty",
        TerminalName.ALACRITTY: "Alacritty",
        TerminalName.KONSOLE: "Konsole",
        TerminalName.GNOME_TERMINAL: "gnome-terminal",
        TerminalName.VTE: "VTE",
        TerminalName.WINDOWS_TERMINAL: "WindowsTerminal",
        TerminalName.DUMB: "dumb",
        TerminalName.UNKNOWN: "unknown",
    }
    base = mapping[name]
    return f"{base}/{version}" if version else base


def _sanitize_header_value(value: str) -> str:
    return "".join(ch if ch.isascii() and (ch.isalnum() or ch in "-_./") else "_" for ch in value)


def _var_non_empty(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    return value if value is not None and value.strip() else None


__all__ = [
    "Multiplexer",
    "TerminalInfo",
    "TerminalName",
    "terminal_info",
    "user_agent",
]
