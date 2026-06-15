"""Terminal keyboard enhancement setup and teardown helpers.

Rust counterpart: ``codex-rs/tui/src/tui/keyboard_modes.rs``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="tui::keyboard_modes",
    source="codex/codex-rs/tui/src/tui/keyboard_modes.rs",
    status="complete",
)

DISABLE_KEYBOARD_ENHANCEMENT_ENV_VAR = "CODEX_TUI_DISABLE_KEYBOARD_ENHANCEMENT"
WINDOWS_TERM_PROGRAM: Optional[str] = None


@dataclass(frozen=True)
class ResetKeyboardEnhancementFlags:
    def write_ansi(self) -> str:
        return "\x1b[<u"

    def execute_winapi(self) -> None:
        raise OSError(
            "keyboard enhancement reset is not implemented for the legacy Windows API"
        )

    def is_ansi_code_supported(self) -> bool:
        return False


@dataclass(frozen=True)
class EnableModifyOtherKeys:
    def write_ansi(self) -> str:
        return "\x1b[>4;2m"

    def execute_winapi(self) -> None:
        raise OSError("modifyOtherKeys enable is not implemented for the legacy Windows API")

    def is_ansi_code_supported(self) -> bool:
        return False


@dataclass(frozen=True)
class DisableModifyOtherKeys:
    def write_ansi(self) -> str:
        return "\x1b[>4;0m"

    def execute_winapi(self) -> None:
        raise OSError("modifyOtherKeys reset is not implemented for the legacy Windows API")

    def is_ansi_code_supported(self) -> bool:
        return False


def parse_bool_env(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "1" or stripped.lower() in {"true", "yes"}:
        return True
    if stripped == "0" or stripped.lower() in {"false", "no"}:
        return False
    return None


def keyboard_enhancement_disabled_for(
    disable_env: Optional[str],
    is_wsl: bool,
    is_vscode_terminal: bool,
) -> bool:
    parsed = parse_bool_env(disable_env)
    if parsed is not None:
        return parsed
    return bool(is_wsl and is_vscode_terminal)


def running_in_wsl(env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get("WSL_DISTRO_NAME") or env.get("WSL_INTEROP"))


def term_program_is_vscode(value: Optional[str]) -> bool:
    return value is not None and value.lower() == "vscode"


def vscode_terminal_detected(
    linux_term_program: Optional[str],
    windows_term_program_value: Optional[str],
) -> bool:
    return term_program_is_vscode(linux_term_program) or term_program_is_vscode(
        windows_term_program_value
    )


def windows_term_program(env: Optional[Dict[str, str]] = None) -> Optional[str]:
    env = os.environ if env is None else env
    return WINDOWS_TERM_PROGRAM if WINDOWS_TERM_PROGRAM is not None else env.get("TERM_PROGRAM")


def read_windows_term_program(output: Optional[Any] = None) -> Optional[str]:
    if output is None:
        return None
    text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output
    for line in text.splitlines():
        value = line.rstrip("\r")
        if value.startswith("TERM_PROGRAM="):
            found = value[len("TERM_PROGRAM="):]
            return found if found.strip() else None
    return None


def running_in_vscode_terminal(env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return vscode_terminal_detected(env.get("TERM_PROGRAM"), windows_term_program(env))


def keyboard_enhancement_disabled(env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    is_wsl = running_in_wsl(env)
    return keyboard_enhancement_disabled_for(
        env.get(DISABLE_KEYBOARD_ENHANCEMENT_ENV_VAR),
        is_wsl,
        is_wsl and running_in_vscode_terminal(env),
    )


def tmux_session_detected(tmux: Optional[str], tmux_pane: Optional[str]) -> bool:
    return tmux is not None or tmux_pane is not None


def running_in_tmux_session(env: Optional[Dict[str, str]] = None) -> bool:
    env = os.environ if env is None else env
    return tmux_session_detected(env.get("TMUX"), env.get("TMUX_PANE"))


def tmux_should_enable_modify_other_keys_for(
    running_in_tmux_session_value: bool,
    extended_keys_format: Optional[str],
) -> bool:
    return bool(running_in_tmux_session_value and extended_keys_format == "csi-u")


def read_tmux_extended_keys_format(output: Optional[Any] = None) -> Optional[str]:
    if output is None:
        return None
    text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output
    value = text.strip()
    return value or None


def tmux_should_enable_modify_other_keys(
    env: Optional[Dict[str, str]] = None,
    extended_keys_format: Optional[str] = None,
) -> bool:
    return tmux_should_enable_modify_other_keys_for(
        running_in_tmux_session(env),
        extended_keys_format,
    )


def ansi_for(command: Any) -> str:
    return command.write_ansi()


def write_ansi(command: Any) -> str:
    return command.write_ansi()


def execute_winapi(command: Any) -> None:
    if hasattr(command, "execute_winapi"):
        command.execute_winapi()
        return
    raise OSError("command does not support legacy Windows API execution")


def is_ansi_code_supported(command: Any) -> bool:
    if hasattr(command, "is_ansi_code_supported"):
        return bool(command.is_ansi_code_supported())
    return True


def enable_keyboard_enhancement(
    env: Optional[Dict[str, str]] = None,
    extended_keys_format: Optional[str] = None,
) -> List[str]:
    if keyboard_enhancement_disabled(env):
        return []
    commands = [ansi_for(DisableModifyOtherKeys()), "PushKeyboardEnhancementFlags"]
    if tmux_should_enable_modify_other_keys(env, extended_keys_format):
        commands.append(ansi_for(EnableModifyOtherKeys()))
    return commands


def restore_keyboard_enhancement_stack() -> List[str]:
    return ["PopKeyboardEnhancementFlags", ansi_for(DisableModifyOtherKeys())]


def reset_keyboard_reporting_after_exit() -> List[str]:
    return [
        "PopKeyboardEnhancementFlags",
        ansi_for(ResetKeyboardEnhancementFlags()),
        ansi_for(DisableModifyOtherKeys()),
    ]


def keyboard_enhancement_env_flag_parses_common_values() -> bool:
    return (
        parse_bool_env("1") is True
        and parse_bool_env("true") is True
        and parse_bool_env("YES") is True
        and parse_bool_env("0") is False
        and parse_bool_env("false") is False
        and parse_bool_env("NO") is False
        and parse_bool_env("unexpected") is None
        and parse_bool_env(None) is None
    )


def keyboard_enhancement_auto_disables_for_vscode_in_wsl() -> bool:
    return keyboard_enhancement_disabled_for(None, True, True)


def keyboard_enhancement_auto_disable_requires_wsl_and_vscode() -> bool:
    return not keyboard_enhancement_disabled_for(None, True, False) and not keyboard_enhancement_disabled_for(
        None, False, True
    )


def keyboard_enhancement_env_flag_overrides_auto_detection() -> bool:
    return (
        not keyboard_enhancement_disabled_for("0", True, True)
        and keyboard_enhancement_disabled_for("1", False, False)
    )


def vscode_terminal_detection_uses_linux_and_windows_term_program() -> bool:
    return (
        vscode_terminal_detected("vscode", None)
        and vscode_terminal_detected(None, "vscode")
        and not vscode_terminal_detected(None, "WindowsTerminal")
        and not vscode_terminal_detected(None, None)
    )


def tmux_session_detection_accepts_tmux_or_tmux_pane() -> bool:
    return (
        tmux_session_detected("/tmp/tmux-501/default,1,0", None)
        and tmux_session_detected(None, "%0")
        and not tmux_session_detected(None, None)
    )


def tmux_modify_other_keys_only_requests_confirmed_csi_u_format() -> bool:
    return (
        tmux_should_enable_modify_other_keys_for(True, "csi-u")
        and not tmux_should_enable_modify_other_keys_for(True, None)
        and not tmux_should_enable_modify_other_keys_for(True, "xterm")
        and not tmux_should_enable_modify_other_keys_for(True, "")
        and not tmux_should_enable_modify_other_keys_for(False, "csi-u")
    )


def reset_keyboard_enhancement_flags_clears_all_pushed_levels() -> bool:
    return ansi_for(ResetKeyboardEnhancementFlags()) == "\x1b[<u"


def enable_modify_other_keys_requests_xterm_keyboard_reporting() -> bool:
    return ansi_for(EnableModifyOtherKeys()) == "\x1b[>4;2m"


def disable_modify_other_keys_resets_xterm_keyboard_reporting() -> bool:
    return ansi_for(DisableModifyOtherKeys()) == "\x1b[>4;0m"


__all__ = [
    "DISABLE_KEYBOARD_ENHANCEMENT_ENV_VAR",
    "DisableModifyOtherKeys",
    "EnableModifyOtherKeys",
    "RUST_MODULE",
    "ResetKeyboardEnhancementFlags",
    "WINDOWS_TERM_PROGRAM",
    "ansi_for",
    "disable_modify_other_keys_resets_xterm_keyboard_reporting",
    "enable_keyboard_enhancement",
    "enable_modify_other_keys_requests_xterm_keyboard_reporting",
    "execute_winapi",
    "is_ansi_code_supported",
    "keyboard_enhancement_auto_disable_requires_wsl_and_vscode",
    "keyboard_enhancement_auto_disables_for_vscode_in_wsl",
    "keyboard_enhancement_disabled",
    "keyboard_enhancement_disabled_for",
    "keyboard_enhancement_env_flag_overrides_auto_detection",
    "keyboard_enhancement_env_flag_parses_common_values",
    "parse_bool_env",
    "read_tmux_extended_keys_format",
    "read_windows_term_program",
    "reset_keyboard_enhancement_flags_clears_all_pushed_levels",
    "reset_keyboard_reporting_after_exit",
    "restore_keyboard_enhancement_stack",
    "running_in_tmux_session",
    "running_in_vscode_terminal",
    "running_in_wsl",
    "term_program_is_vscode",
    "tmux_modify_other_keys_only_requests_confirmed_csi_u_format",
    "tmux_session_detected",
    "tmux_session_detection_accepts_tmux_or_tmux_pane",
    "tmux_should_enable_modify_other_keys",
    "tmux_should_enable_modify_other_keys_for",
    "vscode_terminal_detected",
    "vscode_terminal_detection_uses_linux_and_windows_term_program",
    "windows_term_program",
    "write_ansi",
]
