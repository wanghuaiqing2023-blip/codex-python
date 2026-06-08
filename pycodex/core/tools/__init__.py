"""Core tool behavior modules aligned with ``codex-rs/core/src/tools``."""

from .tool_search_entry import (
    ToolSearchEntry,
    ToolSearchInfo,
    coalesce_loadable_tool_specs,
    default_namespace_description,
    loadable_tool_spec_from_spec,
)
from enum import Enum

from pycodex.core.shell import Shell, ShellType
from pycodex.core.user_shell_command import (
    format_exec_output_for_model,
    format_exec_output_str,
)

from .context import (
    TELEMETRY_PREVIEW_MAX_BYTES,
    TELEMETRY_PREVIEW_MAX_LINES,
    TELEMETRY_PREVIEW_TRUNCATION_NOTICE,
)
from .registry import flat_tool_name


class ToolUserShellType(str, Enum):
    ZSH = "zsh"
    BASH = "bash"
    POWERSHELL = "powershell"
    SH = "sh"
    CMD = "cmd"


def tool_user_shell_type(user_shell: Shell) -> ToolUserShellType:
    if not isinstance(user_shell, Shell):
        raise TypeError("user_shell must be a Shell")
    if user_shell.shell_type is ShellType.ZSH:
        return ToolUserShellType.ZSH
    if user_shell.shell_type is ShellType.BASH:
        return ToolUserShellType.BASH
    if user_shell.shell_type is ShellType.POWERSHELL:
        return ToolUserShellType.POWERSHELL
    if user_shell.shell_type is ShellType.SH:
        return ToolUserShellType.SH
    if user_shell.shell_type is ShellType.CMD:
        return ToolUserShellType.CMD
    raise ValueError(f"unsupported shell type: {user_shell.shell_type!r}")


_LAZY_EXPORTS = {
    "ToolRouter": ("pycodex.core.tools.router", "ToolRouter"),
}


def __getattr__(name: str):
    if name in _LAZY_EXPORTS:
        from importlib import import_module

        module_name, attr_name = _LAZY_EXPORTS[name]
        return getattr(import_module(module_name), attr_name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "TELEMETRY_PREVIEW_MAX_BYTES",
    "TELEMETRY_PREVIEW_MAX_LINES",
    "TELEMETRY_PREVIEW_TRUNCATION_NOTICE",
    "ToolSearchEntry",
    "ToolSearchInfo",
    "ToolRouter",
    "ToolUserShellType",
    "coalesce_loadable_tool_specs",
    "default_namespace_description",
    "flat_tool_name",
    "format_exec_output_for_model",
    "format_exec_output_str",
    "loadable_tool_spec_from_spec",
    "tool_user_shell_type",
]
