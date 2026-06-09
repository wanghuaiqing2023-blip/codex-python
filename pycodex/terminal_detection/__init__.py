"""Port of Rust ``codex-terminal-detection`` public API.

Rust source:
- ``codex/codex-rs/terminal-detection/src/lib.rs``
"""

from __future__ import annotations

import os
import subprocess
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
class TmuxClientInfo:
    termtype: str | None = None
    termname: str | None = None


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


def terminal_info(
    env: Mapping[str, str] | None = None,
    *,
    tmux_client_info: TmuxClientInfo | None = None,
    zellij_version: str | None = None,
) -> TerminalInfo:
    process_env = env is None
    return _detect_terminal_info_from_env(
        os.environ if env is None else env,
        tmux_client_info=tmux_client_info if tmux_client_info is not None else (_tmux_client_info() if process_env else TmuxClientInfo()),
        zellij_version=zellij_version if zellij_version is not None else (_zellij_version_from_command() if process_env else None),
    )


def user_agent(env: Mapping[str, str] | None = None) -> str:
    return terminal_info(env).user_agent_token()


def _detect_terminal_info_from_env(
    env: Mapping[str, str],
    *,
    tmux_client_info: TmuxClientInfo | None = None,
    zellij_version: str | None = None,
) -> TerminalInfo:
    multiplexer = _detect_multiplexer(env, zellij_version=zellij_version)
    term_program = _var_non_empty(env, "TERM_PROGRAM")
    if term_program is not None:
        if _is_tmux_term_program(term_program) and multiplexer is not None and multiplexer.type == "tmux":
            terminal = _terminal_from_tmux_client_info(tmux_client_info or TmuxClientInfo(), multiplexer)
            if terminal is not None:
                return terminal
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


def _detect_multiplexer(env: Mapping[str, str], *, zellij_version: str | None = None) -> Multiplexer | None:
    if _var_non_empty(env, "TMUX") or _var_non_empty(env, "TMUX_PANE"):
        version = _var_non_empty(env, "TERM_PROGRAM_VERSION") if _is_tmux_term_program(env.get("TERM_PROGRAM") or "") else None
        return Multiplexer.tmux(version)
    if _var_non_empty(env, "ZELLIJ") or _var_non_empty(env, "ZELLIJ_SESSION_NAME") or _var_non_empty(env, "ZELLIJ_VERSION"):
        return Multiplexer.zellij(_var_non_empty(env, "ZELLIJ_VERSION") or _none_if_whitespace(zellij_version))
    return None


def _is_tmux_term_program(value: str) -> bool:
    return value.lower() == "tmux"


def _terminal_from_tmux_client_info(client_info: TmuxClientInfo, multiplexer: Multiplexer | None) -> TerminalInfo | None:
    termtype = _none_if_whitespace(client_info.termtype)
    termname = _none_if_whitespace(client_info.termname)
    if termtype is not None:
        program, version = _split_term_program_and_version(termtype)
        name = _terminal_name_from_term_program(program) or TerminalName.UNKNOWN
        return TerminalInfo(name, term_program=program, version=version, term=termname, multiplexer=multiplexer)
    if termname is not None:
        name = TerminalName.DUMB if termname == "dumb" else TerminalName.WEZTERM if termname in {"wezterm", "wezterm-mux"} else TerminalName.UNKNOWN
        return TerminalInfo(name, term=termname, multiplexer=multiplexer)
    return None


def _split_term_program_and_version(value: str) -> tuple[str, str | None]:
    parts = value.split()
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else None)


def _tmux_client_info() -> TmuxClientInfo:
    return TmuxClientInfo(
        termtype=_tmux_display_message("#{client_termtype}"),
        termname=_tmux_display_message("#{client_termname}"),
    )


def _tmux_display_message(format_value: str) -> str | None:
    try:
        output = subprocess.run(
            ["tmux", "display-message", "-p", format_value],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if output.returncode != 0:
        return None
    return _none_if_whitespace(output.stdout.strip())


def _zellij_version_from_command() -> str | None:
    try:
        output = subprocess.run(
            ["zellij", "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    if output.returncode != 0:
        return None
    return parse_zellij_version(output.stdout.strip())


def parse_zellij_version(value: str) -> str | None:
    value = _none_if_whitespace(value)
    if value is None:
        return None
    parts = value.split()
    if len(parts) >= 2 and parts[0].lower() == "zellij":
        return parts[1]
    return value


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
    return _none_if_whitespace(value)


def _none_if_whitespace(value: str | None) -> str | None:
    return value if value is not None and value.strip() else None


__all__ = [
    "Multiplexer",
    "TmuxClientInfo",
    "TerminalInfo",
    "TerminalName",
    "parse_zellij_version",
    "terminal_info",
    "user_agent",
]
